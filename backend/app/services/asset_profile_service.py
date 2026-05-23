"""资产画像数据关联引擎 — 跨 ZDNS / F5 / vCenter / 交换机 构建统一资产视图。

数据链路：
  域名(ZDNS+F5) → 公网IP(ZDNS) → 端口(F5 VS) → 内网服务IP:端口(F5 Pool Member)
  → 虚拟机名称(vCenter) → IP地址/MAC地址/网络/VLAN/文件夹(vCenter + 交换机)

匹配规则：
  - VM 查找：先用成员 IP 匹配 VMInventory.ip_address，未命中则走交换机
    scan_results 获取 MAC，再用 MAC 匹配 VMInventory.mac_address
  - IP地址：vCenter IP 优先，为空则用 pool 成员 IP
  - MAC地址：vCenter MAC 优先，为空则用交换机查到的 MAC
"""

import logging
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models.zdns import ZDNSDomainMap
from app.models.f5 import F5VirtualServer, F5PoolMember, F5ApplicationMap
from app.models.vm_inventory import VMInventory
from app.models.scan_result import ScanResult

logger = logging.getLogger(__name__)


def _split_csv(value: str) -> list[str]:
    """拆分 CSV/逗号分隔字段，返回去重非空列表。"""
    if not value:
        return []
    return list(dict.fromkeys(s.strip() for s in value.split(",") if s.strip()))


def _match_ip_in_field(field_value: str, target_ip: str) -> bool:
    """检查 target_ip 是否出现在逗号分隔的 IP 字段中。"""
    if not field_value or not target_ip:
        return False
    return target_ip in (s.strip() for s in field_value.split(","))


def _dedupe_list(lst: list) -> list:
    """保序去重（按 vm_name 去重 dict，按值去重普通类型）。"""
    seen = set()
    result = []
    for item in lst:
        if isinstance(item, dict):
            key = item.get("vm_name", id(item))
        else:
            key = item
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _find_vms_by_ip(
    target_ip: str,
    vm_by_ip: dict[str, list[dict]],
    vm_by_mac: dict[str, list[dict]],
    switch_ip_to_mac: dict[str, list[str]],
) -> list[dict]:
    """根据 IP 查找 VM：先直接匹配 vCenter IP，未命中则走交换机 MAC → vCenter MAC。"""
    # 第一步：直接 IP 匹配
    vms = list(vm_by_ip.get(target_ip, []))
    if vms:
        return _dedupe_list(vms)

    # 第二步：IP → 交换机 MAC → vCenter MAC
    mac_list = switch_ip_to_mac.get(target_ip, [])
    for mac in mac_list:
        for v in vm_by_mac.get(mac.lower(), []):
            if v not in vms:
                vms.append(v)
    return vms


def build_asset_profile(db: Session) -> list[dict]:
    """构建完整资产画像数据，返回行列表。"""

    # ═══════════════════════════════════════════════════════════════
    # 1. 收集域名（仅 ZDNSDomainMap + F5ApplicationMap，排除通配符）
    # ═══════════════════════════════════════════════════════════════
    zdns_domain_set: set[str] = set()
    f5_domain_set: set[str] = set()
    for (d,) in db.query(ZDNSDomainMap.domain_name).filter(
        ZDNSDomainMap.domain_name != "",
        ZDNSDomainMap.domain_name.notlike("*%"),
        ~ZDNSDomainMap.domain_name.contains("in-addr.arpa"),
    ).distinct().all():
        zdns_domain_set.add(d)

    for (d,) in db.query(F5ApplicationMap.domain_name).filter(
        F5ApplicationMap.domain_name != "",
    ).distinct().all():
        f5_domain_set.add(d)

    all_domains = zdns_domain_set | f5_domain_set
    if not all_domains:
        return []

    # ═══════════════════════════════════════════════════════════════
    # 2. ZDNS 域名 → IP 映射（不限定内外网，所有 IP 都纳入）
    # ═══════════════════════════════════════════════════════════════
    domain_public_ips: dict[str, list[str]] = defaultdict(list)
    zdns_rows = db.query(ZDNSDomainMap.domain_name, ZDNSDomainMap.ip_address).filter(
        ZDNSDomainMap.ip_address != "",
        ZDNSDomainMap.domain_name.in_(all_domains),
    ).all()
    for domain, ip in zdns_rows:
        if ip and ip not in domain_public_ips[domain]:
            domain_public_ips[domain].append(ip)

    # 补充 F5 域名的 VS IP（ZDNS 无 IP 或域名仅存在于 F5 时，从 ApplicationMap 获取）
    f5_domains_needing_ip = {d for d in f5_domain_set if not domain_public_ips.get(d)}
    if f5_domains_needing_ip:
        f5_ips = db.query(
            F5ApplicationMap.domain_name, F5ApplicationMap.vs_ip
        ).filter(
            F5ApplicationMap.vs_ip != "",
            F5ApplicationMap.domain_name.in_(f5_domains_needing_ip),
        ).distinct().all()
        for domain, ip in f5_ips:
            if ip and ip not in domain_public_ips[domain]:
                domain_public_ips[domain].append(ip)

    # 全局公网 IP 集合
    all_public_ips = set()
    for ips in domain_public_ips.values():
        all_public_ips.update(ips)

    # ═══════════════════════════════════════════════════════════════
    # 3. F5 VS 数据：公网IP → [(vs_port, pool_name, vs_name)]
    # ═══════════════════════════════════════════════════════════════
    f5_vs_list = db.query(F5VirtualServer).all()
    vs_by_ip: dict[str, list[dict]] = defaultdict(list)
    for vs in f5_vs_list:
        if vs.vs_ip:
            vs_by_ip[vs.vs_ip].append({
                "vs_port": vs.vs_port,
                "pool_name": vs.pool_name,
                "vs_name": vs.name,
            })

    # ═══════════════════════════════════════════════════════════════
    # 4. F5 Pool Member 数据：pool_name → [(member_ip, member_port)]
    # ═══════════════════════════════════════════════════════════════
    f5_pm_list = db.query(F5PoolMember).all()
    members_by_pool: dict[str, list[dict]] = defaultdict(list)
    for pm in f5_pm_list:
        if pm.pool_name:
            members_by_pool[pm.pool_name].append({
                "member_ip": pm.member_ip,
                "member_port": pm.member_port,
                "member_state": pm.member_state,
            })

    # 同时构建 (vs_ip, vs_port) → members 映射（从 application_map）
    f5_app_list = db.query(F5ApplicationMap).all()
    members_by_vs: dict[tuple, list[dict]] = defaultdict(list)
    for am in f5_app_list:
        if am.vs_ip:
            key = (am.vs_ip, am.vs_port)
            members_by_vs[key].append({
                "member_ip": am.member_ip,
                "member_port": am.member_port,
                "member_state": am.member_state,
                "domain_name": am.domain_name,
            })

    # ═══════════════════════════════════════════════════════════════
    # 5. vCenter VM 数据
    # ═══════════════════════════════════════════════════════════════
    vm_list = db.query(VMInventory).all()

    # VM IP 索引：ip → [(vm_name, ip_address, mac_address, network_name, vlan_id, vm_folder)]
    vm_by_ip: dict[str, list[dict]] = defaultdict(list)
    # VM MAC 索引：mac → [same]
    vm_by_mac: dict[str, list[dict]] = defaultdict(list)
    for vm in vm_list:
        vm_info = {
            "vm_name": vm.vm_name,
            "ip_address": vm.ip_address,
            "mac_address": vm.mac_address,
            "network_name": vm.network_name,
            "vlan_id": vm.vlan_id,
            "vm_folder": vm.vm_folder,
        }
        for ip in _split_csv(vm.ip_address):
            vm_by_ip[ip].append(vm_info)
        for mac in _split_csv(vm.mac_address):
            vm_by_mac[mac.lower()].append(vm_info)

    # ═══════════════════════════════════════════════════════════════
    # 6. 交换机 IP → MAC 映射
    # ═══════════════════════════════════════════════════════════════
    sr_rows = db.query(ScanResult.ip_address, ScanResult.mac_address).filter(
        ScanResult.ip_address != "",
        ScanResult.mac_address != "",
    ).all()
    switch_ip_to_mac: dict[str, list[str]] = defaultdict(list)
    for ip, mac in sr_rows:
        if mac not in switch_ip_to_mac[ip]:
            switch_ip_to_mac[ip].append(mac)

    # ═══════════════════════════════════════════════════════════════
    # 7. 辅助：构建单行数据
    # ═══════════════════════════════════════════════════════════════
    def _make_row(
        domain: str, pub_ip: str, port: str,
        internal_ip: str, internal_port: str,
        vm: dict | None = None,
        fallback_ip_for_mac: str = "",
        member_state: str = "",
        source: str = "",
    ) -> dict:
        """构建一行资产数据。vm 为 None 时 VM 相关字段为空。"""
        if vm is None:
            return {
                "域名": domain,
                "来源": source,
                "公网IP": pub_ip,
                "端口": port,
                "内网服务IP": internal_ip,
                "内网端口": internal_port,
                "状态": member_state,
                "虚拟机名称": "",
                "IP地址": internal_ip,
                "MAC地址": "",
                "网络": "",
                "VLAN": "",
                "文件夹": "",
            }
        # VM 存在
        vm_ip = vm["ip_address"] if vm["ip_address"] else internal_ip
        vm_mac = vm["mac_address"]
        if not vm_mac and fallback_ip_for_mac:
            sw_macs = switch_ip_to_mac.get(fallback_ip_for_mac, [])
            vm_mac = ", ".join(sw_macs) if sw_macs else ""
        return {
            "域名": domain,
            "来源": source,
            "公网IP": pub_ip,
            "端口": port,
            "内网服务IP": internal_ip,
            "内网端口": internal_port,
            "状态": member_state,
            "虚拟机名称": vm["vm_name"],
            "IP地址": vm_ip,
            "MAC地址": vm_mac,
            "网络": vm["network_name"],
            "VLAN": vm["vlan_id"],
            "文件夹": vm["vm_folder"],
        }

    def _dedup_key(row: dict) -> tuple:
        return tuple(str(v) for v in row.values())

    # ═══════════════════════════════════════════════════════════════
    # 8. 组装行数据
    # ═══════════════════════════════════════════════════════════════
    rows: list[dict] = []
    seen_row_keys = set()

    def _emit_row(*args, **kwargs):
        """构建行并去重添加。自动计算融合来源。"""
        domain_val = args[0] if args else kwargs.get("domain", "")
        vm = args[5] if len(args) > 5 and args[5] is not None else None
        fallback_ip = kwargs.get("fallback_ip_for_mac", "")

        src_parts = []
        if domain_val in zdns_domain_set:
            src_parts.append("ZDNS")
        if domain_val in f5_domain_set:
            src_parts.append("F5")
        if vm is not None:
            src_parts.append("vCenter")
        if fallback_ip and switch_ip_to_mac.get(fallback_ip):
            src_parts.append("Switch")

        kwargs["source"] = ",".join(src_parts)
        row = _make_row(*args, **kwargs)
        key = _dedup_key(row)
        if key not in seen_row_keys:
            seen_row_keys.add(key)
            rows.append(row)

    for domain in all_domains:
        public_ips = domain_public_ips.get(domain, [])
        if not public_ips:
            _emit_row(domain, "", "", "", "", None)
            continue

        for pub_ip in public_ips:
            vs_entries = vs_by_ip.get(pub_ip, [])

            if not vs_entries:
                # 无 F5 VS：尝试通过交换机→vCenter 查找 VM（用公网 IP）
                matched_vms = _find_vms_by_ip(pub_ip, vm_by_ip, vm_by_mac, switch_ip_to_mac)
                if not matched_vms:
                    _emit_row(domain, pub_ip, "", "", "", None)
                else:
                    for vm in matched_vms:
                        _emit_row(domain, pub_ip, "", pub_ip, "", vm, fallback_ip_for_mac=pub_ip)
                continue

            for vs in vs_entries:
                vs_port = vs["vs_port"]
                vs_port_str = str(vs_port) if vs_port is not None else ""
                pool_name = vs["pool_name"]

                # 从 application_map 获取成员，按域名过滤防止跨域污染
                members = [
                    m for m in members_by_vs.get((pub_ip, vs_port), [])
                    if m["domain_name"] == domain
                ]
                if not members:
                    members = members_by_pool.get(pool_name, [])

                if not members:
                    # 有 VS 但无成员：尝试用 VS IP 查 VM
                    matched_vms = _find_vms_by_ip(pub_ip, vm_by_ip, vm_by_mac, switch_ip_to_mac)
                    if not matched_vms:
                        _emit_row(domain, pub_ip, vs_port_str, "", "", None)
                    else:
                        for vm in matched_vms:
                            _emit_row(domain, pub_ip, vs_port_str, pub_ip, "", vm, fallback_ip_for_mac=pub_ip)
                    continue

                for member in members:
                    member_ip = member["member_ip"]
                    member_port = member.get("member_port")
                    member_port_str = str(member_port) if member_port is not None else ""

                    member_state = member.get("member_state", "")

                    if not member_ip:
                        _emit_row(domain, pub_ip, vs_port_str, "", member_port_str, None, member_state=member_state)
                        continue

                    matched_vms = _find_vms_by_ip(member_ip, vm_by_ip, vm_by_mac, switch_ip_to_mac)
                    if not matched_vms:
                        _emit_row(domain, pub_ip, vs_port_str, member_ip, member_port_str, None, member_state=member_state)
                    else:
                        for vm in matched_vms:
                            _emit_row(domain, pub_ip, vs_port_str, member_ip, member_port_str, vm, fallback_ip_for_mac=member_ip, member_state=member_state)

    return rows


def compute_stats(rows: list[dict]) -> dict:
    """根据已构建的行数据计算统计摘要。"""
    domains = set()
    public_ip_ports = set()
    vm_names = set()
    vm_ip_ports = set()
    vlans = set()
    folders = set()

    for r in rows:
        if r["域名"]:
            domains.add(r["域名"])
        if r["公网IP"]:
            pub_key = (r["公网IP"], r["端口"]) if r["端口"] else (r["公网IP"],)
            public_ip_ports.add(pub_key)
        if r["虚拟机名称"]:
            vm_names.add(r["虚拟机名称"])
        if r["IP地址"]:
            vm_key = (r["IP地址"], r["内网端口"]) if r["内网端口"] else (r["IP地址"],)
            vm_ip_ports.add(vm_key)
        if r["VLAN"]:
            # VLAN 字段可能逗号分隔多个值
            for v in _split_csv(r["VLAN"]):
                vlans.add(v)
        if r["文件夹"]:
            folders.add(r["文件夹"])

    return {
        "域名数量": len(domains),
        "公网IP端口数量": len(public_ip_ports),
        "虚拟机数量": len(vm_names),
        "虚拟机IP端口数量": len(vm_ip_ports),
        "vlan数量": len(vlans),
        "文件夹数量": len(folders),
    }


def get_network_names(rows: list[dict]) -> list[str]:
    """从行数据中提取去重排序的网络名称列表（供筛选下拉框使用）。"""
    names = set()
    for r in rows:
        n = r.get("网络", "")
        if n:
            names.add(n)
    return sorted(names)


def get_source_names(rows: list[dict]) -> list[str]:
    """从行数据中提取去重排序的来源组合列表（供筛选下拉框使用）。"""
    names = set()
    for r in rows:
        s = r.get("来源", "")
        if s:
            names.add(s)
    return sorted(names)


def filter_sort_paginate(
    rows: list[dict],
    search: str = "",
    sort_by: str = "",
    sort_dir: str = "asc",
    page: int = 1,
    size: int = 50,
    status: str = "",
    network: str = "",
    source: str = "",
) -> dict:
    """对资产行数据进行搜索过滤、排序和分页。"""
    # 搜索过滤
    if search:
        q = search.lower()
        filtered = []
        for r in rows:
            if any(q in str(v).lower() for v in r.values()):
                filtered.append(r)
        rows = filtered

    # 状态过滤
    if status:
        rows = [r for r in rows if r.get("状态", "").lower() == status.lower()]

    # 网络名称过滤（vCenter 网络）
    if network:
        rows = [r for r in rows if r.get("网络", "") == network]

    # 来源过滤（精确匹配）
    if source:
        rows = [r for r in rows if r.get("来源", "") == source]

    # 排序
    sort_key = ""
    if rows and sort_by and sort_by in rows[0]:
        sort_key = sort_by
    if sort_key:
        reverse = sort_dir.lower() == "desc"
        rows = sorted(rows, key=lambda x: (x[sort_key] is None, str(x[sort_key]).lower()), reverse=reverse)
    else:
        # 默认按域名→公网IP→端口排序
        rows = sorted(rows, key=lambda x: (x["域名"], x["公网IP"], str(x["端口"])))

    total = len(rows)
    start = (page - 1) * size
    paged = rows[start:start + size]

    return {"rows": paged, "total": total, "page": page, "size": size}
