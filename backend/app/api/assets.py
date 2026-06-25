"""信息资产管理 — 部门资产查询、未关联资产、搜索。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.models.department import Department

router = APIRouter(prefix="/assets", tags=["信息资产管理"])


def _is_admin_user(u) -> bool:
    if hasattr(u, "role"):
        r = u.role
        return (r.value if hasattr(r, "value") else r) == "admin"
    return False


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
                         "ip_address": r.ip_address, "source": "ZDNS", "vm_name": None, "vm_id": None, "source_type": ""}
    return list(seen.values())


@router.get("/vm-filters")
def get_vm_filters(department_id: int = Query(None, description="按部门筛选文件夹"),
                   db: Session = Depends(get_db), _=Depends(get_current_user)):
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

    # 文件夹：可选按部门（含子部门）过滤
    # department_id=0 表示未关联资产（claim_status='unlinked'或未在asset_inventory中）
    if department_id == 0:
        folders = db.execute(text(
            "SELECT DISTINCT v.vm_folder FROM vm_inventory v "
            "LEFT JOIN asset_inventory a ON v.vm_name = a.vm_name "
            "WHERE (a.id IS NULL OR a.claim_status = 'unlinked') "
            "AND v.vm_folder IS NOT NULL AND v.vm_folder != ''"
        )).fetchall()
    elif department_id is not None and department_id > 0:
        sub_ids = _get_sub_dept_ids(db, department_id)
        placeholders = ",".join(str(s) for s in sub_ids)
        folders = db.execute(text(
            f"SELECT DISTINCT v.vm_folder FROM vm_inventory v "
            f"JOIN asset_inventory a ON v.vm_name = a.vm_name "
            f"WHERE a.department_id IN ({placeholders}) AND v.vm_folder IS NOT NULL AND v.vm_folder != ''"
        )).fetchall()
    else:
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


@router.post("/sync")
def sync_assets(db: Session = Depends(get_db), _=Depends(require_admin)):
    """从 vm_inventory 同步新 VM 到 asset_inventory（新 VM 标记为 unlinked）。

    还清理 asset_inventory 中在 vm_inventory 已不存在的僵尸记录。
    """
    from app.models.scan_log import ScanLog as SL, ScanStatus as SST, TriggerType as TT
    from datetime import datetime as dt, timezone as tz, timedelta as td
    tz8 = tz(td(hours=8))
    now_start = dt.now(tz8).replace(tzinfo=None)
    sl = SL(source_type="asset_sync", source_name="资产同步",
            triggered_by=TT.manual, status=SST.running, started_at=now_start)
    db.add(sl); db.commit(); db.refresh(sl)

    vi_total = db.execute(text("SELECT COUNT(*) FROM vm_inventory")).scalar() or 0
    ai_before = db.execute(text("SELECT COUNT(*) FROM asset_inventory")).scalar() or 0

    # 1. 将 vm_inventory 中新增的 VM 插入 asset_inventory（显式设为 unlinked）
    new_rows = db.execute(text(
        "INSERT IGNORE INTO asset_inventory (vm_name, claim_status) "
        "SELECT vm_name, 'unlinked' FROM vm_inventory WHERE vm_name IS NOT NULL AND vm_name != ''"
    ))
    db.commit()
    new_count = new_rows.rowcount

    # 1a. 修复已有的 NULL claim_status → 'unlinked'（历史遗留）
    fixed_rows = db.execute(text(
        "UPDATE asset_inventory SET claim_status = 'unlinked' WHERE claim_status IS NULL"
    ))
    db.commit()

    # 2. 清理 vm_inventory 中超过 30 天未更新的僵尸记录（可能来自已删除的 vCenter）
    vm_stale = db.execute(text(
        "DELETE FROM vm_inventory "
        "WHERE updated_at < DATE_SUB(NOW(), INTERVAL 30 DAY)"
    ))
    db.commit()
    vm_stale_count = vm_stale.rowcount

    # 2b. 清理 asset_inventory 中在 vm_inventory 已不存在的记录
    stale_rows = db.execute(text(
        "DELETE FROM asset_inventory "
        "WHERE vm_name NOT IN (SELECT vm_name FROM vm_inventory WHERE vm_name IS NOT NULL AND vm_name != '')"
    ))
    db.commit()
    stale_count = stale_rows.rowcount

    # 3. 域名同步：有部门归属的VM → 复制负责人/部门/认领状态到 vm_inventory（域名通过IP匹配显示）
    domain_claimed = db.execute(text(
        "UPDATE vm_inventory v "
        "JOIN asset_inventory a ON v.vm_name = a.vm_name "
        "SET v.department_id = a.department_id, "
        "    v.owner_user_id = a.owner_user_id, "
        "    v.claim_status = COALESCE(a.claim_status, 'manual') "
        "WHERE a.department_id IS NOT NULL "
        "  AND (v.department_id IS NULL OR v.owner_user_id IS NULL "
        "       OR v.department_id != a.department_id "
        "       OR v.owner_user_id != a.owner_user_id)"
    ))
    db.commit()
    domain_count = domain_claimed.rowcount

    # 4. 信息系统域名同步：InfoSystem.domain → ZDNS 域名 → VM → 复制管理员/部门
    is_synced = 0
    try:
        from app.models.info_system import InfoSystem, SupplyChain
        systems = db.query(InfoSystem).filter(
            InfoSystem.domain.isnot(None), InfoSystem.domain != "",
            InfoSystem.manager_name.isnot(None), InfoSystem.manager_name != "",
        ).all()
        for s in systems:
            # 清洗域名：去掉 http/https 前缀和路径
            raw_domains = [d.strip() for d in s.domain.split(",") if d.strip()]
            clean_domains = []
            for d in raw_domains:
                d = d.lower()
                for p in ("https://", "http://"):
                    if d.startswith(p):
                        d = d[len(p):]
                d = d.split("/")[0].split(":")[0]  # 去路径和端口
                if d:
                    clean_domains.append(d)
            if not clean_domains:
                continue
            for dom in clean_domains:
                # 匹配 ZDNS 域名
                zdns = db.execute(text(
                    "SELECT ip_address FROM zdns_domain_map WHERE LOWER(domain_name)=:d LIMIT 1"
                ), {"d": dom}).fetchone()
                if not zdns or not zdns.ip_address or not zdns.ip_address.strip():
                    continue
                ip = zdns.ip_address.strip()
                # 更新匹配该 IP 的 VM 的管理员和部门
                updated = db.execute(text(
                    "UPDATE vm_inventory v SET "
                    "  department_id = COALESCE(v.department_id, :dept), "
                    "  owner_user_id = COALESCE(v.owner_user_id, "
                    "    (SELECT id FROM users WHERE name=:mgr_name LIMIT 1)) "
                    "WHERE (v.ip_address LIKE :ip1 OR v.ip_address LIKE :ip2 OR v.ip_address = :ip3) "
                    "  AND (v.department_id IS NULL OR v.owner_user_id IS NULL)"
                ), {"dept": s.dept_id, "mgr_name": s.manager_name,
                    "ip1": f"{ip},%", "ip2": f"%,{ip}", "ip3": ip}).rowcount
                is_synced += updated
        if is_synced > 0:
            db.commit()
    except Exception:
        db.rollback()

    # 5. 数据关联：有管理员的VM → 匹配域名 → 回写信息系统的管理员
    is_manager_synced = 0
    try:
        # 查询有 owner 的 VM，获取其 IP、owner 信息
        vm_rows = db.execute(text(
            "SELECT v.ip_address, v.owner_user_id, u.name as owner_name, u.gh as owner_gh "
            "FROM vm_inventory v JOIN users u ON v.owner_user_id = u.id "
            "WHERE v.owner_user_id IS NOT NULL"
        )).fetchall()
        if vm_rows:
            # 预加载 ZDNS 域名→IP 映射
            zdns_all = db.execute(text(
                "SELECT LOWER(domain_name) as d, ip_address FROM zdns_domain_map"
            )).fetchall()
            zdns_by_ip = {}
            for z in zdns_all:
                ip = (z.ip_address or "").strip()
                if ip and ip not in zdns_by_ip:
                    zdns_by_ip[ip] = z.d

            # 为每个 VM 的 IP 查找对应域名，匹配 InfoSystem
            for v in vm_rows:
                if not v.ip_address:
                    continue
                vm_ips = [ip.strip() for ip in v.ip_address.split(",") if ip.strip()]
                for ip in vm_ips:
                    domain = zdns_by_ip.get(ip)
                    if not domain:
                        continue
                    # 查找域名匹配的信息系统（管理员为空时更新）
                    updated = db.execute(text(
                        "UPDATE info_systems SET manager_name = :name, manager_gh = :gh "
                        "WHERE (manager_gh IS NULL OR manager_gh = '') "
                        "AND (LOWER(domain) LIKE :d1 OR LOWER(domain) LIKE :d2 OR LOWER(domain) = :d3)"
                    ), {
                        "name": v.owner_name, "gh": v.owner_gh,
                        "d1": f"%{domain}%", "d2": f"%{domain},%", "d3": domain,
                    }).rowcount
                    is_manager_synced += updated
        if is_manager_synced > 0:
            db.commit()
    except Exception:
        db.rollback()

    ai_after = db.execute(text("SELECT COUNT(*) FROM asset_inventory")).scalar() or 0
    unlinked = db.execute(text(
        "SELECT COUNT(*) FROM asset_inventory WHERE claim_status = 'unlinked'"
    )).scalar() or 0

    msg_parts = [f"同步完成：新增 {new_count} 个 VM，清理资产 {stale_count} 条"]
    if vm_stale_count:
        msg_parts.insert(1, f"清理过期VM {vm_stale_count} 条")
    if domain_count:
        msg_parts.append(f"域名同步 {domain_count} 条")
    if is_synced:
        msg_parts.append(f"信息系统域名同步 {is_synced} 条")
    if is_manager_synced:
        msg_parts.append(f"管理员关联 {is_manager_synced} 条")
    msg_parts.append(f"共 {ai_after} 个（{unlinked} 个未关联）")

    # 标记扫描日志成功
    now_end = dt.now(tz8).replace(tzinfo=None)
    sl.status = SST.success
    sl.hosts_found = new_count + stale_count + domain_count + is_synced + is_manager_synced
    sl.completed_at = now_end
    sl.duration_seconds = round((now_end - now_start).total_seconds(), 1)
    db.commit()

    return {
        "message": "，".join(msg_parts),
        "new": new_count, "stale": stale_count,
        "domain_claimed": domain_count, "is_synced": is_synced,
        "is_manager_synced": is_manager_synced,
        "total": ai_after, "unlinked": unlinked,
    }


@router.post("/batch-cancel")
def batch_cancel(body: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """批量申请注销（本人认领的记录可申请）。"""
    ids = body.get("ids", [])
    typ = body.get("type", "")
    if not ids: raise HTTPException(400, "请选择记录")
    count = 0
    if typ == "vm":
        # 只有本人认领的VM才能申请注销
        id_tuple = tuple(int(i) for i in ids if str(i).isdigit())
        if not id_tuple:
            raise HTTPException(400, "无效的ID列表")
        if len(id_tuple) == 1:
            where_in = f"({id_tuple[0]})"
        else:
            where_in = str(id_tuple)
        rows = db.execute(text(
            f"SELECT v.id FROM vm_inventory v JOIN asset_inventory a ON v.vm_name=a.vm_name "
            f"WHERE v.id IN {where_in} AND a.owner_user_id=:uid"
        ), {"uid": user.id}).fetchall()
        allowed = tuple(r.id for r in rows)
        if allowed:
            update_in = f"({allowed[0]})" if len(allowed) == 1 else str(allowed)
            db.execute(text(f"UPDATE vm_inventory SET claim_status='申请注销' WHERE id IN {update_in}"))
            count = len(allowed)
    elif typ == "domain":
        # 域名：通过IP匹配找对应VM的owner，本人认领的才能注销
        for domain_name in ids:
            d = db.execute(text(
                "SELECT ip_address FROM zdns_domain_map WHERE domain_name=:d LIMIT 1"
            ), {"d": domain_name}).fetchone()
            if not d or not d.ip_address:
                continue
            ip = d.ip_address.strip()
            vm = db.execute(text(
                "SELECT v.id FROM vm_inventory v WHERE v.ip_address LIKE :ip1 OR v.ip_address LIKE :ip2 OR v.ip_address=:ip3 LIMIT 1"
            ), {"ip1": f"{ip},%", "ip2": f"%,{ip}", "ip3": ip}).fetchone()
            if vm:
                owner = db.execute(text(
                    "SELECT a.owner_user_id FROM asset_inventory a JOIN vm_inventory v ON a.vm_name=v.vm_name WHERE v.id=:vid"
                ), {"vid": vm.id}).fetchone()
                if owner and owner.owner_user_id == user.id:
                    db.execute(text(f"UPDATE vm_inventory SET claim_status='申请注销' WHERE id={vm.id}"))
                    count += 1
    elif typ == "info_system":
        user_gh = str(user.gh or user.id)
        for rid in ids:
            sid = int(rid) if str(rid).isdigit() else None
            if not sid: continue
            from app.models.info_system import InfoSystem
            s = db.query(InfoSystem).get(sid)
            if s and (str(s.manager_gh or '') == user_gh or s.created_by == user.id or _is_admin_user(user)):
                s.fill_type = "申请注销"
                count += 1
    else:
        raise HTTPException(400, "不支持的类型")
    db.commit()
    return {"message": f"已申请注销 {count} 条"}


@router.post("/batch-uncancel")
def batch_uncancel(body: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """批量撤销注销（恢复为手动状态）。"""
    ids = body.get("ids", [])
    typ = body.get("type", "")
    if not ids: raise HTTPException(400, "请选择记录")
    count = 0
    if typ == "vm":
        id_tuple = tuple(int(i) for i in ids if str(i).isdigit())
        if not id_tuple: raise HTTPException(400, "无效的ID列表")
        where_in = f"({id_tuple[0]})" if len(id_tuple) == 1 else str(id_tuple)
        rows = db.execute(text(
            f"SELECT v.id FROM vm_inventory v JOIN asset_inventory a ON v.vm_name=a.vm_name "
            f"WHERE v.id IN {where_in} AND a.owner_user_id=:uid AND v.claim_status='申请注销'"
        ), {"uid": user.id}).fetchall()
        allowed = tuple(r.id for r in rows)
        if allowed:
            up = f"({allowed[0]})" if len(allowed) == 1 else str(allowed)
            db.execute(text(f"UPDATE vm_inventory SET claim_status='manual' WHERE id IN {up}"))
            count = len(allowed)
    elif typ == "domain":
        for domain_name in ids:
            d = db.execute(text("SELECT ip_address FROM zdns_domain_map WHERE domain_name=:d LIMIT 1"), {"d": domain_name}).fetchone()
            if not d or not d.ip_address: continue
            ip = d.ip_address.strip()
            vm = db.execute(text("SELECT v.id FROM vm_inventory v WHERE v.ip_address LIKE :ip1 OR v.ip_address LIKE :ip2 OR v.ip_address=:ip3 LIMIT 1"), {"ip1": f"{ip},%", "ip2": f"%,{ip}", "ip3": ip}).fetchone()
            if vm:
                owner = db.execute(text("SELECT a.owner_user_id FROM asset_inventory a JOIN vm_inventory v ON a.vm_name=v.vm_name WHERE v.id=:vid"), {"vid": vm.id}).fetchone()
                if owner and owner.owner_user_id == user.id:
                    db.execute(text(f"UPDATE vm_inventory SET claim_status='manual' WHERE id={vm.id}"))
                    count += 1
    elif typ == "info_system":
        user_gh = str(user.gh or user.id)
        for rid in ids:
            sid = int(rid) if str(rid).isdigit() else None
            if not sid: continue
            from app.models.info_system import InfoSystem
            s = db.query(InfoSystem).get(sid)
            if s and s.fill_type == '申请注销' and (str(s.manager_gh or '') == user_gh or _is_admin_user(user)):
                s.fill_type = '手动'
                count += 1
    else:
        raise HTTPException(400, "不支持的类型")
    db.commit()
    return {"message": f"已撤销注销 {count} 条"}


@router.get("/tree")
def get_asset_tree(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # VM 按部门统计（从 asset_inventory）
    vm_counts = {}
    dept_ips = {}
    vm_rows = db.execute(text(
        "SELECT a.department_id, v.ip_address FROM asset_inventory a "
        "JOIN vm_inventory v ON a.vm_name = v.vm_name "
        "WHERE a.department_id IS NOT NULL AND a.claim_status != 'unlinked'"
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
    from app.models.info_system import InfoSystem
    unlinked_vms = db.execute(text(
        "SELECT COUNT(*) FROM vm_inventory v LEFT JOIN asset_inventory a ON v.vm_name = a.vm_name "
        "WHERE a.id IS NULL OR a.claim_status = 'unlinked'"
    )).scalar() or 0
    linked_ips = set()
    for ips in dept_ips.values():
        linked_ips.update(ips)
    unlinked_domains = len(_collect_domains(db, linked_ips))
    unlinked_systems = db.query(InfoSystem).filter(
        (InfoSystem.dept_id == None) | (InfoSystem.dept_id == 0)
    ).count()

    # InfoSystem 按部门统计
    sys_counts = {}
    sys_rows = db.execute(text(
        "SELECT dept_id, COUNT(*) as c FROM info_systems WHERE dept_id IS NOT NULL AND dept_id > 0 GROUP BY dept_id"
    )).fetchall()
    for r in sys_rows:
        sys_counts[r.dept_id] = r.c

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
        sc = sys_counts.get(d.id, 0)
        kids = [make_node(c) for c in children_by_parent.get(d.dwbm, [])]
        tv = vc + sum(k["vm_count"] for k in kids)
        td = dc + sum(k["domain_count"] for k in kids)
        ts = sc + sum(k["system_count"] for k in kids)
        return {"id": d.id, "label": d.dwjc or d.dwmc or d.dwbm, "full_name": d.dwmc,
                "vm_count": tv, "domain_count": td, "system_count": ts,
                "count": tv + td + ts, "children": kids}

    roots = [make_node(d) for d in children_by_parent.get("__root__", [])]
    roots.sort(key=lambda n: n["label"])
    roots.append({"id": -1, "label": "未关联资产",
                  "vm_count": unlinked_vms, "domain_count": unlinked_domains, "system_count": unlinked_systems,
                  "count": unlinked_vms + unlinked_domains + unlinked_systems, "children": []})
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

    # 椒图安全关联（IP 匹配）
    qax_ips = set()
    try:
        qax_rows = db.execute(text("SELECT DISTINCT ipv4 FROM qax_servers WHERE ipv4 IS NOT NULL AND ipv4 != ''")).fetchall()
        qax_ips = {r.ipv4.strip() for r in qax_rows}
    except Exception:
        pass

    # 鼎甲备份关联（VM 名称匹配）
    dj_backup_info = {}
    try:
        dj_rows = db.execute(text("SELECT vm_name, last_run_time FROM dingjia_backup_records WHERE vm_name IS NOT NULL AND vm_name != ''")).fetchall()
        for r in dj_rows:
            name = r.vm_name
            if name not in dj_backup_info or (r.last_run_time and (not dj_backup_info[name] or r.last_run_time > dj_backup_info[name])):
                dj_backup_info[name] = r.last_run_time
    except Exception:
        pass

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
            "has_qax": any(ip in qax_ips for ip in vm_ips_r) if vm_ips_r else False,
            "has_backup": r.vm_name in dj_backup_info if hasattr(r, "vm_name") else False,
            "last_backup_time": dj_backup_info.get(r.vm_name).isoformat() if dj_backup_info.get(r.vm_name) else None,
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
    has_qax: str = Query("", max_length=4, description="安全: yes/no"),
    has_backup: str = Query("", max_length=4, description="备份: yes/no"),
    power_state: str = Query("", max_length=32),
    os_name: str = Query("", max_length=128),
    network_name: str = Query("", max_length=256),
    vm_folder: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visible_depts = _get_visible_dept_ids(db, current_user)
    # 非管理员只能看到自己认领的 + 未认领的
    owner_filter = ""
    if not _is_admin_user(current_user):
        owner_filter = f"AND (a.owner_user_id = {current_user.id} OR a.owner_user_id IS NULL)"
    if dept_id == 0:
        q = db.execute(text(
            f"SELECT v.*, a.department_id, a.owner_user_id, a.claim_status, a.claimed_by, a.claimed_at, "
            "d.dwmc as dept_name, COALESCE(u.name, u.username) as owner_name, "
            "vc.name as vcenter_name FROM vm_inventory v "
            "LEFT JOIN asset_inventory a ON v.vm_name = a.vm_name "
            "LEFT JOIN departments d ON a.department_id = d.id "
            "LEFT JOIN users u ON a.owner_user_id = u.id "
            "LEFT JOIN vcenters vc ON v.vcenter_id = vc.id "
            f"WHERE (a.id IS NULL OR a.claim_status = 'unlinked') {owner_filter}"
        ))
    else:
        sub_ids = _get_sub_dept_ids(db, dept_id)
        placeholders = ",".join(str(s) for s in sub_ids)
        q = db.execute(text(
            f"SELECT v.*, a.department_id, a.owner_user_id, a.claim_status, a.claimed_by, a.claimed_at, "
            f"d.dwmc as dept_name, COALESCE(u.name, u.username) as owner_name, "
            f"vc.name as vcenter_name FROM vm_inventory v "
            f"LEFT JOIN asset_inventory a ON v.vm_name = a.vm_name "
            f"LEFT JOIN departments d ON a.department_id = d.id "
            f"LEFT JOIN users u ON a.owner_user_id = u.id "
            f"LEFT JOIN vcenters vc ON v.vcenter_id = vc.id "
            f"WHERE a.department_id IN ({placeholders}) {owner_filter}"
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
    if has_qax == "yes":
        all_items = [it for it in all_items if it.get("has_qax")]
    elif has_qax == "no":
        all_items = [it for it in all_items if not it.get("has_qax")]
    if has_backup == "yes":
        all_items = [it for it in all_items if it.get("has_backup")]
    elif has_backup == "no":
        all_items = [it for it in all_items if not it.get("has_backup")]
    if power_state:
        all_items = [it for it in all_items if (it["power_state"] or "") == power_state]
    if os_name:
        all_items = [it for it in all_items if os_name.lower() in (it["os_name"] or "").lower()]
    if network_name:
        all_items = [it for it in all_items if network_name.lower() in (it["network_name"] or "").lower()]
    if vm_folder:
        all_items = [it for it in all_items if vm_folder.lower() in (it["vm_folder"] or "").lower()]

    all_items.sort(key=lambda x: (
        (x.get("resource_pool") or "").lower(),
        (x.get("vm_name") or "").lower(),
        0 if x.get("power_state") == "poweredOn" else 1,
    ))
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
            f"SELECT v.ip_address, v.vm_name, v.id, COALESCE(u.name, u.username) as owner_name, "
            f"d.dwmc as dept_name FROM vm_inventory v "
            f"LEFT JOIN users u ON v.owner_user_id = u.id "
            f"LEFT JOIN departments d ON v.department_id = d.id "
            f"WHERE v.department_id IN ({placeholders})"
        )).fetchall()
        vm_ips = set()
        vm_by_ip = {}
        for r in vm_rows:
            for ip in (r.ip_address or "").split(","):
                ip = ip.strip()
                if ip:
                    vm_ips.add(ip)
                    vm_by_ip[ip] = (r.vm_name, r.id, r.owner_name, r.dept_name)
        all_domains = _collect_domains(db)
        results = []
        matched_domain_ips = set()
        for d in all_domains:
            if d["ip_address"] and d["ip_address"].strip() in vm_ips:
                ip = d["ip_address"].strip()
                vi = vm_by_ip[ip]
                d["vm_name"] = vi[0]
                d["vm_id"] = vi[1]
                d["owner_name"] = vi[2]
                d["dept_name"] = vi[3] or ""
                d["source_type"] = "vm"
                results.append(d)
                matched_domain_ips.add(ip)

        # 补充：信息系统域名匹配（预加载 ZDNS 全表避免 N+1 查询）
        from app.models.info_system import InfoSystem
        # 预加载 ZDNS 域名→记录 映射（一次性查询替代逐条查询）
        zdns_all = db.execute(text(
            "SELECT LOWER(domain_name) as d, domain_name, ip_address, record_type FROM zdns_domain_map"
        )).fetchall()
        zdns_map = {r.d: r for r in zdns_all}
        # 预加载 InfoSystem + 部门
        is_systems = db.query(InfoSystem).filter(
            InfoSystem.domain.isnot(None), InfoSystem.domain != "",
            InfoSystem.manager_name.isnot(None), InfoSystem.manager_name != "",
        ).all()
        is_dept_map = {}
        is_dept_ids = {s.dept_id for s in is_systems if s.dept_id}
        if is_dept_ids:
            depts = db.query(Department).filter(Department.id.in_(is_dept_ids)).all()
            is_dept_map = {d.id: d.dwmc for d in depts}
        # 预计算子部门列表
        sub_ids_set = set(_get_sub_dept_ids(db, dept_id)) if dept_id > 0 else None
        seen_domains = {d["domain_name"].lower() for d in results}
        for s in is_systems:
            if sub_ids_set and s.dept_id and s.dept_id not in sub_ids_set:
                continue
            raw = [x.strip() for x in s.domain.split(",") if x.strip()]
            for x in raw:
                x = x.lower()
                for p in ("https://", "http://"):
                    if x.startswith(p): x = x[len(p):]
                x = x.split("/")[0].split(":")[0]
                if not x or x in seen_domains:
                    continue
                zdns = zdns_map.get(x)
                if not zdns:
                    continue
                dept_name = is_dept_map.get(s.dept_id, "")
                results.append({
                    "domain_name": zdns.domain_name,
                    "record_type": zdns.record_type,
                    "ip_address": zdns.ip_address,
                    "source": "ZDNS",
                    "vm_name": s.system_name or "",
                    "vm_id": None,
                    "owner_name": s.manager_name or "",
                    "dept_name": dept_name,
                    "source_type": "is",
                })
                seen_domains.add(x)

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


@router.get("/departments/{dept_id}/systems")
def get_dept_systems(
    dept_id: int, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    search: str = Query(""), fill_type: str = Query(""), claimed: str = Query(""),
    db: Session = Depends(get_db), current_user=Depends(get_current_user),
):
    """按部门获取信息系统列表。dept_id=0 返回未关联部门的系统。"""
    from app.models.info_system import InfoSystem
    q = db.query(InfoSystem)
    # 非管理员：本单位 + (自己是管理员 或 未分配)
    if not _is_admin_user(current_user):
        dept = getattr(current_user, 'department_id', None)
        if dept:
            q = q.filter((InfoSystem.dept_id == dept) | (InfoSystem.dept_id == None))
        uid = str(current_user.gh or current_user.id)
        q = q.filter((InfoSystem.manager_gh == uid) | (InfoSystem.manager_gh == None) | (InfoSystem.manager_gh == ""))
    if dept_id == 0:
        q = q.filter((InfoSystem.dept_id == None) | (InfoSystem.dept_id == 0))
    elif dept_id > 0:
        sub_ids = _get_sub_dept_ids(db, dept_id)
        q = q.filter(InfoSystem.dept_id.in_(sub_ids))
    if search:
        q = q.filter(
            InfoSystem.system_name.contains(search) |
            InfoSystem.ip_address.contains(search) |
            InfoSystem.domain.contains(search)
        )
    if fill_type:
        q = q.filter(InfoSystem.fill_type == fill_type)
    if claimed == "yes":
        q = q.filter(InfoSystem.manager_gh.isnot(None), InfoSystem.manager_gh != "")
    elif claimed == "no":
        q = q.filter((InfoSystem.manager_gh == None) | (InfoSystem.manager_gh == ""))
    total = q.count()
    items = q.order_by(InfoSystem.system_name).offset((page - 1) * size).limit(size).all()
    # 批量查询部门名称
    dept_ids = {r.dept_id for r in items if r.dept_id}
    dept_map = {}
    if dept_ids:
        depts = db.query(Department).filter(Department.id.in_(dept_ids)).all()
        dept_map = {d.id: d.dwmc for d in depts}
    return {"items": [{
        "id": r.id, "asset_id": r.asset_id, "system_name": r.system_name,
        "system_type": r.system_type, "sub_type": r.sub_type,
        "ip_address": r.ip_address, "domain": r.domain,
        "entry_url": r.entry_url, "org_name": r.org_name,
        "manager_name": r.manager_name, "owner_name": r.owner_name,
        "fill_type": r.fill_type, "url_status": r.url_status,
        "dept_id": r.dept_id, "dept_name": dept_map.get(r.dept_id, ""),
        "djdj_status": r.djdj_status, "djdj_level": r.djdj_level,
        "remark": r.remark,
    } for r in items], "total": total}


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
