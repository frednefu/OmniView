"""信息资产管理 — 部门资产查询、未关联资产、搜索。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.department import Department

router = APIRouter(prefix="/assets", tags=["信息资产管理"])


def _get_sub_dept_ids(db: Session, dept_id: int) -> list[int]:
    """获取部门及其所有下级部门 ID 列表。"""
    dept = db.execute(text("SELECT dwbm FROM departments WHERE id=:id"), {"id": dept_id}).fetchone()
    if not dept:
        return [dept_id]
    all_depts = db.execute(text("SELECT id, dwbm, lsdwh FROM departments")).fetchall()
    children_map = {}
    for d in all_depts:
        children_map.setdefault(d.lsdwh or "__root__", []).append(d.id)

    result = [dept_id]
    def collect(dwbm):
        for cid in children_map.get(dwbm, []):
            if cid not in result:
                result.append(cid)
                child = next((d for d in all_depts if d.id == cid), None)
                if child:
                    collect(child.dwbm)
    collect(dept.dwbm)
    return result


def _should_skip_domain(name: str) -> bool:
    """排除 in-addr.arpa 等反向解析域名。"""
    if not name:
        return True
    return ".in-addr.arpa" in name.lower()


def _collect_domains(db: Session, linked_ips: set = None) -> list[dict]:
    """收集 ZDNS + F5 域名，去重合并，排除反向解析。"""
    seen = {}
    zdns_rows = db.execute(text(
        "SELECT domain_name, record_type, ip_address FROM zdns_domain_map"
    )).fetchall()
    for r in zdns_rows:
        name = (r.domain_name or "").strip()
        if _should_skip_domain(name):
            continue
        if linked_ips is not None and (r.ip_address or "").strip() in linked_ips:
            continue
        key = name.lower()
        if key not in seen:
            seen[key] = {"domain_name": name, "record_type": r.record_type,
                         "ip_address": r.ip_address, "source": "ZDNS", "vm_name": None, "vm_id": None}
    return list(seen.values())


@router.get("/vm-filters")
def get_vm_filters(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """获取 VM 筛选选项。"""
    power_states = db.execute(text(
        "SELECT DISTINCT power_state FROM vm_inventory WHERE power_state IS NOT NULL AND power_state != ''"
    )).fetchall()
    os_names = db.execute(text(
        "SELECT DISTINCT os_name FROM vm_inventory WHERE os_name IS NOT NULL AND os_name != ''"
    )).fetchall()
    networks = db.execute(text(
        "SELECT DISTINCT network_name FROM vm_inventory WHERE network_name IS NOT NULL AND network_name != ''"
    )).fetchall()
    folders = db.execute(text(
        "SELECT DISTINCT vm_folder FROM vm_inventory WHERE vm_folder IS NOT NULL AND vm_folder != ''"
    )).fetchall()
    return {
        "power_states": [r.power_state for r in power_states],
        "os_names": [r.os_name for r in os_names],
        "networks": [r.network_name for r in networks],
        "folders": [r.vm_folder for r in folders],
    }


def _get_visible_dept_ids(db: Session, user: User) -> set[int] | None:
    """获取用户可见的部门 ID 集合。admin 返回 None（全部可见）。
    普通用户：从所属部门向上找到处级单位，然后向下收集所有子部门。"""
    if user.role.value == "admin" if hasattr(user.role, "value") else user.role == "admin":
        return None
    dept = user.department
    if not dept or not dept.dwbm:
        return set()

    all_depts = db.execute(text("SELECT id, dwbm, lsdwh FROM departments")).fetchall()
    dept_map = {d.dwbm: d for d in all_depts}
    children_map = {}
    for d in all_depts:
        children_map.setdefault(d.lsdwh or "__root__", []).append(d.id)

    # 向上追溯到处级单位：lsdwh 长度=2 的是根的直接下级，其上上级即为处级
    current = dept
    while current.lsdwh and current.lsdwh in dept_map:
        parent = dept_map[current.lsdwh]
        # 当 parent 的 lsdwh 长度=2 时，parent 是根直属，current 是处级
        if parent.lsdwh and len(parent.lsdwh) <= 2:
            break
        current = parent

    # current 现在是处级单位，收集其及所有子部门
    def collect(dwbm, result):
        result.add(dept_map[dwbm].id)
        for child_id in children_map.get(dwbm, []):
            child_dwbm = next((d.dwbm for d in all_depts if d.id == child_id), None)
            if child_dwbm:
                collect(child_dwbm, result)

    visible = set()
    collect(current.dwbm, visible)
    return visible


@router.get("/tree")
def get_asset_tree(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # VM 按部门统计
    vm_counts = {}
    dept_ips = {}  # department_id → set of IPs
    vm_rows = db.execute(text(
        "SELECT department_id, ip_address FROM vm_inventory "
        "WHERE department_id IS NOT NULL AND claim_status != 'unlinked'"
    )).fetchall()
    for r in vm_rows:
        vm_counts[r.department_id] = vm_counts.get(r.department_id, 0) + 1
        if r.department_id not in dept_ips:
            dept_ips[r.department_id] = set()
        for ip in (r.ip_address or "").split(","):
            ip = ip.strip()
            if ip:
                dept_ips[r.department_id].add(ip)

    # 按部门统计域名（仅 ZDNS，排除 in-addr.arpa）
    domain_counts = {}
    all_domain_ips = {}
    zdns_rows = db.execute(text("SELECT DISTINCT domain_name, ip_address FROM zdns_domain_map")).fetchall()
    for r in zdns_rows:
        name = (r.domain_name or "").strip()
        if _should_skip_domain(name):
            continue
        ip = (r.ip_address or "").strip()
        if ip:
            all_domain_ips[name.lower()] = ip

    for name, ip in all_domain_ips.items():
        for did, ips in dept_ips.items():
            if ip in ips:
                domain_counts[did] = domain_counts.get(did, 0) + 1
                break

    # 部门列表
    depts = db.execute(text("SELECT id, dwmc, dwjc, dwbm, lsdwh, pxh FROM departments")).fetchall()
    dept_by_code = {d.dwbm: d for d in depts}

    # 未关联统计
    unlinked_vms = db.execute(text(
        "SELECT COUNT(*) FROM vm_inventory WHERE department_id IS NULL OR claim_status = 'unlinked'"
    )).scalar() or 0
    linked_ips = set()
    for ips in dept_ips.values():
        linked_ips.update(ips)
    unlinked_domains = len(_collect_domains(db, linked_ips))

    # 构建树
    children_by_parent = {}
    for d in depts:
        key = d.lsdwh if d.lsdwh else "__root__"
        if key not in children_by_parent:
            children_by_parent[key] = []
        children_by_parent[key].append(d)

    def make_node(d):
        vc = vm_counts.get(d.id, 0)
        dc = domain_counts.get(d.id, 0)
        kids = [make_node(c) for c in children_by_parent.get(d.dwbm, [])]
        tv = vc + sum(k["vm_count"] for k in kids)
        td = dc + sum(k["domain_count"] for k in kids)
        return {"id": d.id, "label": d.dwjc or d.dwmc or d.dwbm, "full_name": d.dwmc,
                "vm_count": tv, "domain_count": td, "system_count": 0,
                "count": tv + td, "children": kids}

    roots = [make_node(d) for d in children_by_parent.get("__root__", [])]
    roots.sort(key=lambda n: n["label"])
    roots.append({"id": -1, "label": "未关联资产",
                  "vm_count": unlinked_vms, "domain_count": unlinked_domains, "system_count": 0,
                  "count": unlinked_vms + unlinked_domains, "children": []})
    # 非管理员只显示本处级单位子树（含祖先节点）
    visible = _get_visible_dept_ids(db, current_user)
    if visible is not None:
        # 扩展 visible 包含所有祖先节点
        extended = set(visible)
        for did in list(visible):
            d = next((x for x in depts if x.id == did), None)
            while d and d.lsdwh and d.lsdwh in dept_by_code:
                parent = dept_by_code[d.lsdwh]
                extended.add(parent.id)
                d = parent
        def filter_tree(nodes):
            result = []
            for n in nodes:
                if n["id"] == -1 or n["id"] in extended:
                    if n.get("children"):
                        n["children"] = filter_tree(n["children"])
                    result.append(n)
            return result
        roots = filter_tree(roots)
    return {"nodes": roots}


def _enrich_vms(db: Session, vm_rows: list) -> list[dict]:
    """增强 VM 数据：椒图 OS、F5 公网IP/域名、交换机 MAC→IP。"""
    if not vm_rows:
        return []

    # 收集 IPv4
    vm_ips = set()
    for r in vm_rows:
        for ip in (r.ip_address or "").split(","):
            ip = ip.strip()
            if ip and ":" not in ip:
                vm_ips.add(ip)

    # 椒图 OS
    qax_os = {}
    ip_list = list(vm_ips)
    for i in range(0, len(ip_list), 30):
        batch = ip_list[i:i + 30]
        quoted = ",".join([f"'{ip}'" for ip in batch])
        try:
            rows = db.execute(text(f"SELECT ipv4, os_name FROM qax_servers WHERE ipv4 IN ({quoted})")).fetchall()
            for qr in rows:
                if qr.os_name and qr.ipv4:
                    qax_os[qr.ipv4.strip()] = qr.os_name
        except Exception:
            pass

    # F5 映射
    f5_data = {}
    try:
        rows = db.execute(text(
            "SELECT member_ip, vs_ip, domain_name FROM f5_application_map WHERE member_ip IS NOT NULL AND member_ip != ''"
        )).fetchall()
        for r in rows:
            key = r.member_ip.strip() if r.member_ip else ""
            if key and key not in f5_data:
                f5_data[key] = []
            if key:
                f5_data[key].append({"public_ip": r.vs_ip, "domain": r.domain_name})
    except Exception:
        pass

    # 交换机 MAC→IP + IP 子网统计
    switch_mac_ips = {}  # mac → list of IPs
    subnet_counts = {}   # /24 subnet → count
    try:
        rows = db.execute(text(
            "SELECT mac_address, ip_address FROM scan_results WHERE mac_address IS NOT NULL AND mac_address != ''"
        )).fetchall()
        for r in rows:
            ip = (r.ip_address or "").strip()
            if not ip or ":" in ip:
                continue
            subnet = ".".join(ip.split(".")[:3])
            subnet_counts[subnet] = subnet_counts.get(subnet, 0) + 1
            for mac in (r.mac_address or "").split(","):
                mac = mac.strip().lower()
                if mac:
                    switch_mac_ips.setdefault(mac, []).append(ip)
    except Exception:
        pass

    # 按 IP 数量最多的子网排序（用于选择最佳 IP）
    best_subnets = sorted(subnet_counts.items(), key=lambda x: -x[1])

    # 组装
    items = []
    for r in vm_rows:
        vm_ips_r = [ip.strip() for ip in (r.ip_address or "").split(",") if ip.strip()]
        vm_macs = [mac.strip().lower() for mac in (r.mac_address or "").split(",") if mac.strip()]

        # IP 增强：如果 VM 的 IP 为空，从 MAC 查交换机 IP
        if not vm_ips_r:
            for mac in vm_macs:
                if mac in switch_mac_ips:
                    vm_ips_r.extend(switch_mac_ips[mac])

        # 选择最佳 IP：优先取数量最多的 /24 子网中的 IP
        best_ip = r.ip_address or ""
        if vm_ips_r:
            best_ip = vm_ips_r[0]  # default first
            for sub, _ in best_subnets:
                matching = [ip for ip in vm_ips_r if ip.startswith(sub + ".")]
                if matching:
                    best_ip = matching[0]
                    break

        os_name = r.os_name or ""
        for ip in vm_ips_r:
            if ip in qax_os:
                os_name = qax_os[ip]
                break

        # 公网IP/域名：用 VM IP 和 VM 名称匹配
        f5_ips, f5_doms = set(), set()
        for ip in vm_ips_r:
            if ip in f5_data:
                for e in f5_data[ip]:
                    if e["public_ip"]: f5_ips.add(e["public_ip"])
                    if e["domain"]: f5_doms.add(e["domain"])
        # 也用 VM 名称去 F5 数据中匹配
        vm_name_lower = (r.vm_name or "").lower()
        for key, entries in f5_data.items():
            for e in entries:
                if e.get("domain") and vm_name_lower in (e["domain"] or "").lower():
                    f5_doms.add(e["domain"])
                    if e.get("public_ip"):
                        f5_ips.add(e["public_ip"])

        sw_ips = set()
        for mac in vm_macs:
            if mac in switch_mac_ips:
                sw_ips.update(switch_mac_ips[mac])

        items.append({
            "id": r.id, "vm_name": r.vm_name,
            "ip_address": best_ip, "mac_address": r.mac_address,
            "vm_folder": r.vm_folder, "os_name": os_name,
            "power_state": r.power_state,
            "cpu_count": r.cpu_count, "memory_gb": r.memory_gb,
            "provisioned_gb": r.provisioned_gb, "used_gb": r.used_gb,
            "network_name": r.network_name,
            "department_id": r.department_id,
            "department_name": r.dept_name if hasattr(r, "dept_name") else None,
            "owner_user_id": r.owner_user_id,
            "owner_name": r.owner_name if hasattr(r, "owner_name") else None,
            "vcenter_name": r.vcenter_name if hasattr(r, "vcenter_name") and r.vcenter_name else "",
            "resource_pool": r.resource_pool or "",
            "remark": r.remark or "",
            "claim_status": r.claim_status or "unlinked",
            "claimed_at": r.claimed_at.isoformat() if hasattr(r, "claimed_at") and r.claimed_at else None,
            "f5_public_ips": ",".join(sorted(f5_ips)) if f5_ips else "",
            "f5_domains": ",".join(sorted(f5_doms)) if f5_doms else "",
            "switch_ips": ",".join(sw_ips) if sw_ips else "",
        })
    return items


@router.get("/departments/{dept_id}/vms")
def get_dept_vms(
    dept_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=128),
    claim_status: str = Query("", max_length=16, description="分组状态"),
    claimed: str = Query("", max_length=8, description="认领状态: yes/no"),
    power_state: str = Query("", max_length=32),
    os_name: str = Query("", max_length=128),
    network_name: str = Query("", max_length=256),
    vm_folder: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible_depts = _get_visible_dept_ids(db, current_user)
    if dept_id == 0:
        q = db.execute(text(
            "SELECT v.*, d.dwmc as dept_name, COALESCE(u.name, u.username) as owner_name, "
            "vc.name as vcenter_name FROM vm_inventory v "
            "LEFT JOIN departments d ON v.department_id = d.id "
            "LEFT JOIN users u ON v.owner_user_id = u.id "
            "LEFT JOIN vcenters vc ON v.vcenter_id = vc.id "
            "WHERE v.department_id IS NULL OR v.claim_status = 'unlinked'"
        ))
    else:
        sub_ids = _get_sub_dept_ids(db, dept_id)
        placeholders = ",".join(str(s) for s in sub_ids)
        q = db.execute(text(
            f"SELECT v.*, d.dwmc as dept_name, COALESCE(u.name, u.username) as owner_name, "
            f"vc.name as vcenter_name FROM vm_inventory v "
            f"LEFT JOIN departments d ON v.department_id = d.id "
            f"LEFT JOIN users u ON v.owner_user_id = u.id "
            f"LEFT JOIN vcenters vc ON v.vcenter_id = vc.id "
            f"WHERE v.department_id IN ({placeholders})"
        ))

    rows = q.fetchall()
    if visible_depts is not None:
        rows = [r for r in rows if r.department_id in visible_depts]
    all_items = _enrich_vms(db, rows)
    if search:
        kw = search.lower()
        all_items = [it for it in all_items
                     if kw in (it["vm_name"] or "").lower()
                     or kw in (it["ip_address"] or "").lower()
                     or kw in (it["f5_domains"] or "").lower()]
    if claim_status:
        all_items = [it for it in all_items if (it.get("claim_status") or "unlinked") == claim_status]
    if claimed == "yes":
        all_items = [it for it in all_items if it.get("owner_name")]
    elif claimed == "no":
        all_items = [it for it in all_items if not it.get("owner_name")]
    if power_state:
        all_items = [it for it in all_items if (it["power_state"] or "") == power_state]
    if os_name:
        all_items = [it for it in all_items if os_name.lower() in (it["os_name"] or "").lower()]
    if network_name:
        all_items = [it for it in all_items if network_name.lower() in (it["network_name"] or "").lower()]
    if vm_folder:
        all_items = [it for it in all_items if vm_folder.lower() in (it["vm_folder"] or "").lower()]

    all_items.sort(key=lambda x: (x.get("vm_name") or "").lower())
    total = len(all_items)
    start = (page - 1) * size
    return {"items": all_items[start:start + size], "total": total, "page": page, "size": size}


@router.get("/departments/{dept_id}/domains")
def get_dept_domains(
    dept_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str = Query("", max_length=256),
    record_type: str = Query("", max_length=32),
    claimed: str = Query("", max_length=8),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible = _get_visible_dept_ids(db, current_user)
    if dept_id == 0:
        linked_ips = set()
        if visible is not None:
            # 仅统计可见部门 VM 的 IP
            placeholders = ",".join([str(d) for d in visible])
            linked_rows = db.execute(text(
                f"SELECT ip_address FROM vm_inventory WHERE department_id IN ({placeholders}) AND claim_status != 'unlinked'"
            )).fetchall()
        else:
            linked_rows = db.execute(text(
                "SELECT ip_address FROM vm_inventory WHERE department_id IS NOT NULL AND claim_status != 'unlinked'"
            )).fetchall()
        for r in linked_rows:
            for ip in (r.ip_address or "").split(","):
                ip = ip.strip()
                if ip:
                    linked_ips.add(ip)
        results = _collect_domains(db, linked_ips)
    else:
        if visible is not None and dept_id not in visible:
            return {"items": [], "total": 0}
        sub_ids = _get_sub_dept_ids(db, dept_id)
        placeholders = ",".join(str(s) for s in sub_ids)
        vm_rows = db.execute(text(
            f"SELECT v.ip_address, v.vm_name, v.id, COALESCE(u.name, u.username) as owner_name FROM vm_inventory v "
            f"LEFT JOIN users u ON v.owner_user_id = u.id WHERE v.department_id IN ({placeholders})"
        )).fetchall()
        vm_ips = set()
        vm_by_ip = {}
        for r in vm_rows:
            for ip in (r.ip_address or "").split(","):
                ip = ip.strip()
                if ip:
                    vm_ips.add(ip)
                    vm_by_ip[ip] = (r.vm_name, r.id, r.owner_name)
        all_domains = _collect_domains(db)
        results = []
        for d in all_domains:
            if d["ip_address"] and d["ip_address"].strip() in vm_ips:
                ip = d["ip_address"].strip()
                vi = vm_by_ip[ip]
                d["vm_name"] = vi[0]
                d["vm_id"] = vi[1]
                d["owner_name"] = vi[2]
                results.append(d)

    if search:
        kw = search.lower()
        results = [d for d in results if kw in d["domain_name"].lower() or kw in (d["ip_address"] or "").lower()]
    if record_type:
        results = [d for d in results if (d.get("record_type") or "") == record_type]
    if claimed == "yes":
        results = [d for d in results if d.get("owner_name")]
    elif claimed == "no":
        results = [d for d in results if not d.get("owner_name")]

    results.sort(key=lambda x: (x.get("domain_name") or "").lower())
    total = len(results)
    start = (page - 1) * size
    return {"items": results[start:start + size], "total": total, "page": page, "size": size}


@router.get("/search")
def search_assets(
    keyword: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    results = []
    kw = keyword.strip()
    if not kw:
        return {"items": results}

    is_admin = current_user.role.value == "admin" if hasattr(current_user.role, "value") else current_user.role == "admin"
    visible = _get_visible_dept_ids(db, current_user)

    vm_q = db.execute(text(
        "SELECT v.id, v.vm_name, v.ip_address, v.mac_address, v.vm_folder, "
        "v.claim_status, v.department_id, d.dwmc as dept_name "
        "FROM vm_inventory v LEFT JOIN departments d ON v.department_id = d.id "
        "WHERE v.vm_name LIKE :kw OR v.ip_address LIKE :kw OR v.mac_address LIKE :kw"
    ), {"kw": f"%{kw}%"})
    for r in vm_q.fetchall():
        if visible is not None and r.department_id not in visible:
            continue
        results.append({"asset_type": "vm", "id": r.id, "name": r.vm_name,
                        "ip_address": r.ip_address, "mac_address": r.mac_address,
                        "vm_folder": r.vm_folder, "department_name": r.dept_name,
                        "claim_status": r.claim_status or "unlinked"})

    zdns_q = db.execute(text(
        "SELECT domain_name, ip_address, record_type FROM zdns_domain_map "
        "WHERE domain_name LIKE :kw OR ip_address LIKE :kw"
    ), {"kw": f"%{kw}%"})
    for r in zdns_q.fetchall():
        results.append({"asset_type": "domain", "id": None, "name": r.domain_name,
                        "ip_address": r.ip_address, "mac_address": None,
                        "vm_folder": None, "department_name": None, "claim_status": None})

    f5_q = db.execute(text(
        "SELECT domain_name, vs_ip FROM f5_application_map "
        "WHERE domain_name LIKE :kw AND domain_name IS NOT NULL AND domain_name != ''"
    ), {"kw": f"%{kw}%"})
    for r in f5_q.fetchall():
        results.append({"asset_type": "domain", "id": None, "name": r.domain_name,
                        "ip_address": r.vs_ip, "mac_address": None,
                        "vm_folder": None, "department_name": None, "claim_status": None})

    return {"items": results[:100]}
