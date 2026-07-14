"""F5 系统运维 — 数据聚合服务层"""
from __future__ import annotations
import json
from collections import defaultdict
from sqlalchemy.orm import Session

from app.models.f5 import F5VirtualServer, F5PoolMember, F5Rule, F5ApplicationMap
from app.models.zdns import ZDNSDomainMap


import re

def _short(name: str) -> str:
    """提取 F5 短名称（去掉 /Common/ 等分区前缀）"""
    if not name:
        return ""
    return name.rsplit("/", 1)[-1]


def _clean_domain(name: str) -> str:
    """清洗域名：去掉 :port 后缀，用于与 ZDNS 匹配"""
    if not name:
        return ""
    return re.sub(r":\d+$", "", name.strip())


# ══════════════════════════════════════════════════════════════════
# 虚拟服务器视图
# ══════════════════════════════════════════════════════════════════

def build_virtual_server_view(db: Session, f5_device_id: int) -> list[dict]:
    """聚合 VS + ZDNS 域名 + 内网服务器成员，按 (vs_ip, vs_port) 分组"""
    # 1. 加载该设备全部 VS
    vs_rows = db.query(F5VirtualServer).filter(
        F5VirtualServer.f5_device_id == f5_device_id
    ).all()

    if not vs_rows:
        return []

    # 2. 按 (vs_ip, vs_port) 分组，同时收集 iRule 名称
    groups: dict[tuple, dict] = {}
    for vs in vs_rows:
        key = (vs.vs_ip or "", vs.vs_port)
        if key not in groups:
            groups[key] = {"vs_names": [], "irules": set(), "vs_ip": vs.vs_ip or "", "vs_port": vs.vs_port}
        groups[key]["vs_names"].append(vs.name)
        # 解析 rules JSON 字段
        if vs.rules:
            try:
                rule_list = json.loads(vs.rules)
                for r in rule_list:
                    groups[key]["irules"].add(_short(r))
            except (json.JSONDecodeError, TypeError):
                pass

    # 3. ApplicationMap：该设备的全部映射条目（归一化 port：NULL 按 0 处理）
    app_rows = db.query(F5ApplicationMap).filter(
        F5ApplicationMap.f5_device_id == f5_device_id
    ).all()

    # irule 域名按 VS 分组，同时保留原始名称和清洗后的名称
    irule_domains_by_vs: dict[tuple, dict[str, str]] = defaultdict(dict)  # vs_key -> {clean_name: original_name}
    app_by_vs: dict[tuple, list] = defaultdict(list)
    all_clean_domains: set[str] = set()
    for a in app_rows:
        port = a.vs_port if a.vs_port is not None else 0
        key = (a.vs_ip or "", port)
        app_by_vs[key].append(a)
        if a.domain_name and a.source == "irule":
            clean = _clean_domain(a.domain_name)
            if clean not in irule_domains_by_vs[key]:
                irule_domains_by_vs[key][clean] = a.domain_name  # 保留原始名
            all_clean_domains.add(clean)

    # 查询全部 irule 域名（清洗后）在 ZDNS 中的存活状态及记录类型
    zdns_info: dict[str, str] = {}  # clean_domain -> record_type
    if all_clean_domains:
        exist_rows = db.query(
            ZDNSDomainMap.domain_name, ZDNSDomainMap.record_type
        ).filter(
            ZDNSDomainMap.domain_name.in_(all_clean_domains)
        ).distinct().all()
        for r in exist_rows:
            zdns_info[r[0]] = r[1] or "A"

    # 5. 构建结果
    result = []
    for (vs_ip, vs_port), group in groups.items():
        # VS 分组也用归一化 port
        vs_port_norm = vs_port if vs_port is not None else 0
        vs_key = (vs_ip, vs_port_norm)
        # clean_name -> original_name 映射
        expected_map = irule_domains_by_vs.get(vs_key, {})
        expected_clean = set(expected_map.keys())

        # 域名列表：仅显示 irule 绑定的域名，标注 ZDNS 存活状态
        domains = []
        for clean in sorted(expected_clean):
            domains.append({
                "domain_name": expected_map[clean],
                "record_type": zdns_info.get(clean, "—"),
                "zdns_exists": clean in zdns_info,
            })

        # 状态判断：基于域名列中全部域名的存活情况
        all_alive = all(d["zdns_exists"] for d in domains)
        any_alive = any(d["zdns_exists"] for d in domains)
        if all_alive:
            status = "active"
        elif any_alive:
            status = "partial"
        else:
            status = "deregistered"

        # 内网服务器：按 (pool, rule) 分组成员，合并同 pool+rule 不同 domain 的重复条目
        entries = app_by_vs.get(vs_key, [])
        server_groups: dict[tuple, dict] = defaultdict(lambda: {"domain": "", "source": "", "members": {}})
        for a in entries:
            if not a.member_ip:
                continue
            sg_key = (_short(a.pool_name), _short(a.rule_name))
            grp = server_groups[sg_key]
            # 收集 irule 域名
            if a.domain_name and a.source == "irule" and not grp["domain"]:
                grp["domain"] = a.domain_name
            # 标注来源
            if a.source == "irule":
                grp["source"] = "irule"
            elif not grp["source"]:
                grp["source"] = "pool"
            # 成员去重
            member_key = (a.member_ip, a.member_port or 0)
            if member_key not in grp["members"]:
                grp["members"][member_key] = {
                    "ip": a.member_ip,
                    "port": a.member_port,
                    "state": a.member_state or "",
                }

        internal_servers = []
        member_count = 0
        for (pool, rule), grp in server_groups.items():
            members = list(grp["members"].values())
            member_count += len(members)
            internal_servers.append({
                "pool_name": pool,
                "rule_name": rule,
                "domain": grp["domain"],
                "source": grp["source"],
                "members": members,
            })

        result.append({
            "f5_device_id": f5_device_id,
            "vs_ip": vs_ip,
            "vs_port": vs_port,
            "vs_names": ", ".join(sorted(group["vs_names"])),
            "irules": sorted(group["irules"]),
            "domains": domains,
            "internal_servers": internal_servers,
            "status": status,
            "member_count": member_count,
        })

    return result


# ══════════════════════════════════════════════════════════════════
# 资源池视图
# ══════════════════════════════════════════════════════════════════

def build_pool_view(db: Session, f5_device_id: int) -> list[dict]:
    """聚合 Pool 成员 + 引用 VS + 引用 Rules"""
    # 1. 全部 Pool 成员
    members = db.query(F5PoolMember).filter(
        F5PoolMember.f5_device_id == f5_device_id
    ).all()

    if not members:
        return []

    # 按 pool_name 分组成员
    pool_members: dict[str, list] = defaultdict(list)
    for m in members:
        short_name = _short(m.pool_name)
        pool_members[short_name].append({
            "ip": m.member_ip or "",
            "port": m.member_port,
            "state": m.member_state or "",
        })

    # 2. 全部 VS（用于查找 pool 引用）
    vs_rows = db.query(F5VirtualServer).filter(
        F5VirtualServer.f5_device_id == f5_device_id
    ).all()

    pool_vs_refs: dict[str, list] = defaultdict(list)
    for vs in vs_rows:
        pool_short = _short(vs.pool_name)
        if pool_short:
            pool_vs_refs[pool_short].append(vs.name)

    # 3. ApplicationMap (source=irule) 用于查找 rule 引用
    app_rows = db.query(F5ApplicationMap).filter(
        F5ApplicationMap.f5_device_id == f5_device_id,
        F5ApplicationMap.source == "irule",
    ).all()

    pool_rule_refs: dict[str, set] = defaultdict(set)
    for a in app_rows:
        pool_short = _short(a.pool_name)
        rule_short = _short(a.rule_name)
        if pool_short and rule_short:
            pool_rule_refs[pool_short].add(rule_short)

    # 4. 构建结果
    result = []
    for pool_name, member_list in pool_members.items():
        # 状态
        up_count = sum(1 for m in member_list if m["state"].lower() == "up")
        down_count = sum(1 for m in member_list if m["state"].lower() in ("down", "checking"))
        unknown = len(member_list) - up_count - down_count

        if up_count > 0 and down_count == 0 and unknown == 0:
            status = "up"
        elif down_count > 0 and up_count > 0:
            status = "mixed"
        elif down_count > 0 and up_count == 0:
            status = "down"
        else:
            status = "mixed"

        # 引用状态：VS 和 iRules 都有 → full，有一个 → partial，都没有 → none
        has_vs = bool(pool_vs_refs.get(pool_name))
        has_rule = bool(pool_rule_refs.get(pool_name))
        if has_vs and has_rule:
            ref_status = "full"
        elif has_vs or has_rule:
            ref_status = "partial"
        else:
            ref_status = "none"

        result.append({
            "f5_device_id": f5_device_id,
            "pool_name": pool_name,
            "status": status,
            "ref_status": ref_status,
            "members": member_list,
            "referenced_vs": sorted(pool_vs_refs.get(pool_name, [])),
            "referenced_rules": sorted(pool_rule_refs.get(pool_name, [])),
            "member_count": len(member_list),
        })

    return result


# ══════════════════════════════════════════════════════════════════
# iRule 视图
# ══════════════════════════════════════════════════════════════════

def build_rule_view(db: Session, f5_device_id: int) -> list[dict]:
    """聚合 iRule + 域名-Pool 映射 + ZDNS 状态"""
    # 1. 全部 Rules
    rules = db.query(F5Rule).filter(
        F5Rule.f5_device_id == f5_device_id
    ).all()

    if not rules:
        return []

    # 2. ApplicationMap (source=irule) 获取域名-Pool 映射
    app_rows = db.query(F5ApplicationMap).filter(
        F5ApplicationMap.f5_device_id == f5_device_id,
        F5ApplicationMap.source == "irule",
    ).all()

    # 按 rule_name 分组，对 (domain, pool) 去重
    rule_mappings: dict[str, dict] = defaultdict(dict)  # key: (domain, pool) -> item
    for a in app_rows:
        rule_short = _short(a.rule_name)
        if rule_short and a.domain_name:
            key = (a.domain_name, _short(a.pool_name))
            if key not in rule_mappings[rule_short]:
                rule_mappings[rule_short][key] = {
                    "domain": a.domain_name,
                    "pool": _short(a.pool_name),
                }

    # 3. ZDNS 域名是否存在（全局检查，清洗掉 :端口 后缀后匹配）
    all_clean_domains = set()
    domain_clean_map: dict[str, str] = {}  # original -> clean
    for mappings in rule_mappings.values():
        for m in mappings.values():
            clean = _clean_domain(m["domain"])
            all_clean_domains.add(clean)
            domain_clean_map[m["domain"]] = clean

    zdns_existing = set()
    if all_clean_domains:
        zdns_rows = db.query(ZDNSDomainMap.domain_name).filter(
            ZDNSDomainMap.domain_name.in_(all_clean_domains)
        ).distinct().all()
        zdns_existing = {r[0] for r in zdns_rows}

    # 4. 构建结果
    result = []
    for rule in rules:
        rule_short = _short(rule.rule_name)
        mappings = list(rule_mappings.get(rule_short, {}).values())

        # 标记 zdns_exists（清洗端口后缀后匹配）
        for m in mappings:
            m["zdns_exists"] = domain_clean_map.get(m["domain"], m["domain"]) in zdns_existing

        # 状态
        if not mappings:
            status = "no_domain"
        else:
            existing = sum(1 for m in mappings if m["zdns_exists"])
            if existing == len(mappings):
                status = "active"
            elif existing > 0:
                status = "partial"
            else:
                status = "deregistered"

        result.append({
            "f5_device_id": f5_device_id,
            "rule_name": rule_short,
            "domain_pool_mappings": sorted(mappings, key=lambda m: m["domain"]),
            "status": status,
            "mapping_count": len(mappings),
        })

    return result
