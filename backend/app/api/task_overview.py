"""待办任务概览 API — 按角色聚合 VM/域名/信息系统/供应链统计数据"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User, UserRole

router = APIRouter(prefix="/task-overview", tags=["待办任务"])


@router.get("")
def get_task_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取待办任务概览数据（根据用户角色自动切换统计范围）。"""
    is_admin = current_user.role == UserRole.admin
    is_dept_admin = current_user.role == UserRole.dept_admin
    uid = current_user.id
    gh = current_user.gh or ""
    did = current_user.department_id

    result = {}
    dept_ids = None
    ids_str = ""

    # ── 数据范围 ──
    vm_join = ""   # extra FROM-JOIN for vm queries
    vm_where = ""  # WHERE clause for vm queries
    domain_where = ""
    is_where = ""
    sc_where = ""

    if is_admin:
        pass  # all empty = no filter
    elif is_dept_admin:
        dept_ids = _get_sub_dept_ids(db, did)
        if dept_ids:
            ids_str = ",".join(str(d) for d in dept_ids)
            vm_where = f"v.department_id IN ({ids_str})"
            domain_where = f"department_id IN ({ids_str})"
            is_where = f"dept_id IN ({ids_str})"
            sc_where = f"s2.dept_id IN ({ids_str})"
            user_scope = f"WHERE u.department_id IN ({ids_str})"
        else:
            vm_where = "1=0"
            domain_where = "1=0"
            is_where = "1=0"
            sc_where = "1=0"
            user_scope = "WHERE 1=0"
    else:
        vm_join = "JOIN asset_inventory a ON a.vm_name=v.vm_name"
        vm_where = f"a.owner_user_id={uid}"
        domain_where = f"owner_user_id={uid}"
        is_where = f"manager_gh='{gh}'"
        sc_where = f"s2.manager_gh='{gh}'"

    def _w(cond):
        """Wrap condition into WHERE clause."""
        return f"WHERE {cond}" if cond else ""

    # ═══════════ 管理员：部门统计（预加载+过滤零值） ═══════════
    if is_admin:
        # 一次性加载：交换机MAC→IP、QAX IP、鼎甲VM
        sw_mac_ips = {}
        for sr in db.execute(text(
            "SELECT mac_address, ip_address FROM scan_results WHERE mac_address IS NOT NULL AND mac_address != ''"
        )).fetchall():
            ip = (sr.ip_address or "").strip()
            if not ip or ":" in ip: continue
            for mac in (sr.mac_address or "").split(","):
                mac = mac.strip().lower()
                if mac: sw_mac_ips.setdefault(mac, []).append(ip)
        qax_ips = {r[0] for r in db.execute(text(
            "SELECT DISTINCT ipv4 FROM qax_servers WHERE ipv4 IS NOT NULL AND ipv4 != ''"
        )).fetchall()}
        dj_vms = {r[0] for r in db.execute(text(
            "SELECT DISTINCT vm_name FROM dingjia_backup_records"
        )).fetchall()}

        # 按部门聚合 VM：总数/开关机/备份/椒图（Python 单次遍历）
        dept_vm = {}  # did -> {total, on, off, backup, qax}
        vm_rows = db.execute(text(
            "SELECT department_id, vm_name, power_state, ip_address, mac_address FROM vm_inventory WHERE department_id IS NOT NULL"
        )).fetchall()
        for vr in vm_rows:
            did = vr.department_id
            if did not in dept_vm:
                dept_vm[did] = {"total": 0, "on": 0, "off": 0, "backup": 0, "qax": 0}
            d = dept_vm[did]
            d["total"] += 1
            if vr.power_state == "poweredOn": d["on"] += 1
            elif vr.power_state == "poweredOff": d["off"] += 1
            if vr.vm_name in dj_vms: d["backup"] += 1
            v_ips = [ip.strip() for ip in (vr.ip_address or "").split(",") if ip.strip()]
            v_macs = [mac.strip().lower() for mac in (vr.mac_address or "").split(",") if mac.strip()]
            if not v_ips:
                for mac in v_macs:
                    if mac in sw_mac_ips:
                        v_ips.extend(sw_mac_ips[mac])
            if any(ip in qax_ips for ip in v_ips):
                d["qax"] += 1

        # 部门基础信息：域名 + IS 计数
        dept_domain_counts = {}
        for dr in db.execute(text(
            "SELECT department_id, COUNT(*) as cnt FROM domain_inventory WHERE department_id IS NOT NULL GROUP BY department_id"
        )).fetchall():
            dept_domain_counts[dr.department_id] = dr.cnt

        dept_rows = db.execute(text("""
            SELECT d.id, COALESCE(d.dwmc, '未分组') as dept_name,
                   COUNT(DISTINCT s.id) as is_count
            FROM departments d
            LEFT JOIN info_systems s ON s.dept_id = d.id
            WHERE d.sfyx = '1'
            GROUP BY d.id, d.dwmc
        """)).fetchall()

        # 按部门统计认领人：VM/域名/IS 的 owner/manager 去重 + 用户详情
        dept_claimers = {}  # did -> set of user_ids
        all_claimer_ids = set()
        # VM 认领人
        for vr in db.execute(text(
            "SELECT a.owner_user_id, v.department_id FROM asset_inventory a JOIN vm_inventory v ON v.vm_name=a.vm_name WHERE a.owner_user_id IS NOT NULL AND v.department_id IS NOT NULL"
        )).fetchall():
            dept_claimers.setdefault(vr.department_id, set()).add(vr.owner_user_id)
            all_claimer_ids.add(vr.owner_user_id)
        # 域名认领人
        for dr in db.execute(text(
            "SELECT owner_user_id, department_id FROM domain_inventory WHERE owner_user_id IS NOT NULL AND department_id IS NOT NULL"
        )).fetchall():
            dept_claimers.setdefault(dr.department_id, set()).add(dr.owner_user_id)
            all_claimer_ids.add(dr.owner_user_id)
        # IS 管理员
        for ir in db.execute(text(
            "SELECT u.id, s.dept_id FROM info_systems s JOIN users u ON u.gh=s.manager_gh WHERE s.manager_gh IS NOT NULL AND s.manager_gh != '' AND s.dept_id IS NOT NULL"
        )).fetchall():
            dept_claimers.setdefault(ir.dept_id, set()).add(ir.id)
            all_claimer_ids.add(ir.id)
        # 批量加载用户详情
        user_info = {}
        if all_claimer_ids:
            uid_str = ",".join(str(uid) for uid in all_claimer_ids)
            for ur in db.execute(text(
                f"SELECT u.id, u.name, u.gh, COALESCE(d.dwmc,'') as dept_name, u.mobile FROM users u LEFT JOIN departments d ON u.department_id=d.id WHERE u.id IN ({uid_str})"
            )).fetchall():
                user_info[ur.id] = {"name": ur.name or "", "gh": ur.gh or "", "dept": ur.dept_name or "", "mobile": ur.mobile or ""}

        dept_details = []
        for r in dept_rows:
            did = r[0]
            vm = dept_vm.get(did, {"total": 0, "on": 0, "off": 0, "backup": 0, "qax": 0})
            total = vm["total"]
            # 过滤全零部门
            if total == 0 and dept_domain_counts.get(did, 0) == 0 and r[2] == 0 and len(dept_claimers.get(did, set())) == 0:
                continue
            claimer_ids = dept_claimers.get(did, set())
            dept_details.append({
                "dept_name": r[1], "dept_id": did,
                "vm": total, "vm_on": vm["on"], "vm_off": vm["off"],
                "backup": vm["backup"], "qax": vm["qax"],
                "domain": dept_domain_counts.get(did, 0), "is_count": r[2],
                "admin_count": len(claimer_ids),
                "admins": [user_info[uid] for uid in claimer_ids if uid in user_info],
            })
        result["dept_details"] = dept_details

    # ═══════════ 部门管理员：人员清单 + 备份/椒图统计（含交换机IP增强） ═══════════
    if is_dept_admin and not is_admin:
        # 基础成员统计（VM/域名/IS/SC）
        members_sql = f"""
            SELECT u.id, u.name, u.gh,
                   COUNT(DISTINCT a.id) as vm,
                   COUNT(DISTINCT di.id) as domain,
                   COUNT(DISTINCT s.id) as is_count,
                   COUNT(DISTINCT sc.id) as sc
            FROM users u
            LEFT JOIN asset_inventory a ON a.owner_user_id = u.id
            LEFT JOIN domain_inventory di ON di.owner_user_id = u.id
            LEFT JOIN info_systems s ON s.manager_gh = u.gh
            LEFT JOIN supply_chains sc ON sc.company_name = s.vendor_name
            {user_scope}
            GROUP BY u.id, u.name, u.gh
            ORDER BY vm DESC
        """
        member_rows = db.execute(text(members_sql)).fetchall()

        # 加载成员资产 VM 详情用于备份/椒图统计
        member_vm_names = {}
        if member_rows:
            user_ids = [r[0] for r in member_rows]
            uid_str = ",".join(str(uid) for uid in user_ids)
            vm_rows = db.execute(text(f"""
                SELECT a.owner_user_id, v.vm_name, v.ip_address, v.mac_address, v.power_state
                FROM asset_inventory a
                JOIN vm_inventory v ON v.vm_name = a.vm_name
                WHERE a.owner_user_id IN ({uid_str})
            """)).fetchall()
            for vr in vm_rows:
                member_vm_names.setdefault(vr.owner_user_id, []).append(vr)

        # 交换机 MAC→IP + QAX IP 集合 + 鼎甲 VM 集合
        _switch_mac_ips = {}
        for sr in db.execute(text(
            "SELECT mac_address, ip_address FROM scan_results WHERE mac_address IS NOT NULL AND mac_address != ''"
        )).fetchall():
            ip = (sr.ip_address or "").strip()
            if not ip or ":" in ip: continue
            for mac in (sr.mac_address or "").split(","):
                mac = mac.strip().lower()
                if mac: _switch_mac_ips.setdefault(mac, []).append(ip)
        _qax_ips = {r[0] for r in db.execute(text(
            "SELECT DISTINCT ipv4 FROM qax_servers WHERE ipv4 IS NOT NULL AND ipv4 != ''"
        )).fetchall()}
        _dj_vms = {r[0] for r in db.execute(text(
            "SELECT DISTINCT vm_name FROM dingjia_backup_records WHERE vm_name IS NOT NULL AND vm_name != ''"
        )).fetchall()}

        members = []
        for r in member_rows:
            uid = r[0]
            vms = member_vm_names.get(uid, [])
            backup_cnt = sum(1 for v in vms if v.vm_name in _dj_vms)
            qax_cnt = 0
            for v in vms:
                v_ips = [ip.strip() for ip in (v.ip_address or "").split(",") if ip.strip()]
                v_macs = [mac.strip().lower() for mac in (v.mac_address or "").split(",") if mac.strip()]
                if not v_ips:
                    for mac in v_macs:
                        if mac in _switch_mac_ips:
                            v_ips.extend(_switch_mac_ips[mac])
                if any(ip in _qax_ips for ip in v_ips):
                    qax_cnt += 1
            vm_on = sum(1 for v in vms if v.power_state == 'poweredOn')
            vm_off = sum(1 for v in vms if v.power_state == 'poweredOff')
            members.append({
                "user_id": uid, "name": r[1], "gh": r[2],
                "vm": r[3], "vm_on": vm_on, "vm_off": vm_off,
                "domain": r[4], "is_count": r[5], "sc": r[6],
                "backup": backup_cnt, "qax": qax_cnt,
            })
        result["members"] = members

    # ═══════════ VM 统计 ═══════════
    def _exec_one(sql):
        return db.execute(text(sql)).fetchone()

    vm_power = _exec_one(f"""
        SELECT COALESCE(SUM(CASE WHEN v.power_state='poweredOn' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN v.power_state='poweredOff' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN v.power_state NOT IN ('poweredOn','poweredOff') OR v.power_state IS NULL OR v.power_state='' THEN 1 ELSE 0 END),0)
        FROM vm_inventory v
        {vm_join}
        {_w(vm_where)}
    """)
    vm_on, vm_off, vm_other = vm_power[0] or 0, vm_power[1] or 0, vm_power[2] or 0
    vm_total = vm_on + vm_off + vm_other

    vm_backup = _exec_one(f"""
        SELECT COUNT(DISTINCT v.id) FROM vm_inventory v
        INNER JOIN dingjia_backup_records db ON db.vm_name = v.vm_name
        {vm_join}
        {_w(vm_where)}
    """)[0] or 0

    # 椒图统计：使用与 VM 清单一致的增强逻辑（含交换机 MAC→IP 回填）
    qax_ips_set = {r[0] for r in db.execute(text(
        "SELECT DISTINCT ipv4 FROM qax_servers WHERE ipv4 IS NOT NULL AND ipv4 != ''"
    )).fetchall()}
    # 交换机 MAC→IP 映射
    switch_mac_ips = {}
    for sr in db.execute(text(
        "SELECT mac_address, ip_address FROM scan_results WHERE mac_address IS NOT NULL AND mac_address != ''"
    )).fetchall():
        ip = (sr.ip_address or "").strip()
        if not ip or ":" in ip: continue
        for mac in (sr.mac_address or "").split(","):
            mac = mac.strip().lower()
            if mac: switch_mac_ips.setdefault(mac, []).append(ip)
    vm_qax = 0
    vm_rows = db.execute(text(f"""
        SELECT v.id, v.ip_address, v.mac_address FROM vm_inventory v
        {vm_join} {_w(vm_where)}
    """)).fetchall()
    for v in vm_rows:
        v_ips = [ip.strip() for ip in (v.ip_address or "").split(",") if ip.strip()]
        v_macs = [mac.strip().lower() for mac in (v.mac_address or "").split(",") if mac.strip()]
        if not v_ips:
            for mac in v_macs:
                if mac in switch_mac_ips:
                    v_ips.extend(switch_mac_ips[mac])
        if any(ip in qax_ips_set for ip in v_ips):
            vm_qax += 1

    # 认领/待认领
    _cl_join = vm_join if vm_join else "JOIN asset_inventory a ON a.vm_name=v.vm_name"
    _cl_where = vm_where if vm_where else "1=1"
    vm_cl = _exec_one(f"""
        SELECT COALESCE(SUM(CASE WHEN v.power_state='poweredOn' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN v.power_state='poweredOff' THEN 1 ELSE 0 END),0)
        FROM vm_inventory v
        {_cl_join}
        WHERE {_cl_where} AND a.claim_status != 'unlinked'
    """)
    vm_un = _exec_one(f"""
        SELECT COALESCE(SUM(CASE WHEN v.power_state='poweredOn' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN v.power_state='poweredOff' THEN 1 ELSE 0 END),0)
        FROM vm_inventory v
        {_cl_join}
        WHERE {_cl_where} AND (a.claim_status = 'unlinked' OR a.claim_status IS NULL)
    """)

    result["vm"] = {
        "total": vm_total, "power_on": vm_on, "power_off": vm_off,
        "backed_up": vm_backup, "qax_installed": vm_qax,
        "claimed": {"on": vm_cl[0] or 0, "off": vm_cl[1] or 0},
        "unclaimed": {"on": vm_un[0] or 0, "off": vm_un[1] or 0},
    }

    # ═══════════ 域名统计（与域名清单 phys 补充逻辑一致） ═══════════
    dom_where = domain_where
    if dom_where:
        dom_where += " AND NOT (owner_user_id IS NULL AND claim_status NOT IN ('unlinked',''))"
    else:
        dom_where = "NOT (owner_user_id IS NULL AND claim_status NOT IN ('unlinked',''))"
    dom = _exec_one(f"""
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN owner_user_id IS NOT NULL THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN owner_user_id IS NULL THEN 1 ELSE 0 END),0)
        FROM domain_inventory
        {_w(dom_where)}
    """)
    result["domain"] = {"total": dom[0] or 0, "claimed": dom[1] or 0, "unclaimed": dom[2] or 0}

    # ═══════════ 信息系统统计 ═══════════
    iss = _exec_one(f"""
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN manager_gh IS NOT NULL AND manager_gh != '' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN manager_gh IS NULL OR manager_gh = '' THEN 1 ELSE 0 END),0)
        FROM info_systems s
        {_w(is_where)}
    """)
    result["is"] = {"total": iss[0] or 0, "claimed": iss[1] or 0, "unclaimed": iss[2] or 0}

    # ═══════════ IS 数据完整性 ═══════════
    isc = _exec_one(f"""
        SELECT COUNT(*),
            COALESCE(SUM(CASE WHEN system_name IS NOT NULL AND system_name != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN system_type IS NOT NULL AND system_type != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN sub_type IS NOT NULL AND sub_type != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN domain IS NOT NULL AND domain != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN manager_name IS NOT NULL AND manager_name != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN dept_id IS NOT NULL THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN djdj_level IS NOT NULL AND djdj_level != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN vendor_name IS NOT NULL AND vendor_name != '' THEN 1 ELSE 0 END),0)
        FROM info_systems s
        {_w(is_where)}
    """)
    total_is = isc[0] or 1
    result["is_completeness"] = {
        "system_name": pct(isc[1], total_is), "system_type": pct(isc[2], total_is),
        "sub_type": pct(isc[3], total_is), "domain": pct(isc[4], total_is),
        "manager": pct(isc[5], total_is), "dept": pct(isc[6], total_is),
        "djdj": pct(isc[7], total_is), "vendor": pct(isc[8], total_is),
    }

    # ═══════════ SC 完整性（通过 IS vendor_name 关联计算） ═══════════
    sc_join = ""
    if sc_where:
        sc_join = "JOIN info_systems s2 ON sc.company_name = s2.vendor_name"
    sc_sql = f"""
        SELECT COUNT(*),
            COALESCE(SUM(CASE WHEN company_name IS NOT NULL AND company_name != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN credit_code IS NOT NULL AND credit_code != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN address IS NOT NULL AND address != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN security_dept IS NOT NULL AND security_dept != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN security_contact IS NOT NULL AND security_contact != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN security_phone IS NOT NULL AND security_phone != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN company_type IS NOT NULL AND company_type != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN industry IS NOT NULL AND industry != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN service_type IS NOT NULL AND service_type != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN data_level IS NOT NULL AND data_level != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN data_location IS NOT NULL AND data_location != '' THEN 1 ELSE 0 END),0)
        FROM supply_chains sc
        {sc_join}
        {_w(sc_where)}
    """
    scc = _exec_one(sc_sql)
    total_sc = scc[0] or 1
    result["sc_completeness"] = {
        "company_name": {"label": "单位名称", "pct": pct(scc[1], total_sc)},
        "credit_code": {"label": "信用代码", "pct": pct(scc[2], total_sc)},
        "address": {"label": "注册地址", "pct": pct(scc[3], total_sc)},
        "security_dept": {"label": "责任部门", "pct": pct(scc[4], total_sc)},
        "security_contact": {"label": "安全联系人", "pct": pct(scc[5], total_sc)},
        "security_phone": {"label": "联系电话", "pct": pct(scc[6], total_sc)},
        "company_type": {"label": "单位类型", "pct": pct(scc[7], total_sc)},
        "industry": {"label": "服务行业", "pct": pct(scc[8], total_sc)},
        "service_type": {"label": "服务类型", "pct": pct(scc[9], total_sc)},
        "data_level": {"label": "数据级别", "pct": pct(scc[10], total_sc)},
        "data_location": {"label": "存储位置", "pct": pct(scc[11], total_sc)},
    }

    return result


def pct(val, total):
    return round((val or 0) / total * 100)


def _get_sub_dept_ids(db, dept_id):
    """获取部门及其所有下级部门 ID 列表（与 assets.py 逻辑一致）。"""
    if not dept_id:
        return []
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
