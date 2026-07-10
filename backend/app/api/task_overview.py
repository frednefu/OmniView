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

    # ═══════════ 管理员：部门统计 ═══════════
    if is_admin:
        result["dept_count"] = db.execute(text(
            "SELECT COUNT(*) FROM departments WHERE sfyx='是'"
        )).scalar() or 0

        dept_rows = db.execute(text("""
            SELECT COALESCE(d.dwmc, '未分组') as dept_name, d.id as dept_id,
                   COUNT(DISTINCT v.id) as vm,
                   COUNT(DISTINCT di.id) as domain,
                   COUNT(DISTINCT s.id) as is_count,
                   COUNT(DISTINCT u.id) as admin_count
            FROM departments d
            LEFT JOIN vm_inventory v ON v.department_id = d.id
            LEFT JOIN domain_inventory di ON di.department_id = d.id
            LEFT JOIN info_systems s ON s.dept_id = d.id
            LEFT JOIN users u ON u.department_id = d.id AND u.role IN ('admin','dept_admin')
            WHERE d.sfyx = '是'
            GROUP BY d.id, d.dwmc
            ORDER BY vm DESC
        """)).fetchall()
        result["dept_details"] = [
            {"dept_name": r[0], "dept_id": r[1], "vm": r[2], "domain": r[3],
             "is_count": r[4], "admin_count": r[5]}
            for r in dept_rows
        ]

    # ═══════════ 部门管理员：人员清单 + SC 统计 ═══════════
    if is_dept_admin and not is_admin:
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
        result["members"] = [
            {"user_id": r[0], "name": r[1], "gh": r[2],
             "vm": r[3], "domain": r[4], "is_count": r[5], "sc": r[6]}
            for r in member_rows
        ]

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

    vm_qax = _exec_one(f"""
        SELECT COUNT(DISTINCT v.id) FROM vm_inventory v
        INNER JOIN qax_servers q ON q.intranet_ip = v.ip_address OR q.ipv4 = v.ip_address
           OR v.ip_address LIKE CONCAT('%,', q.intranet_ip)
           OR v.ip_address LIKE CONCAT(q.intranet_ip, ',%')
           OR v.ip_address LIKE CONCAT('%,', q.ipv4)
           OR v.ip_address LIKE CONCAT(q.ipv4, ',%')
        {vm_join}
        {_w(vm_where)}
    """)[0] or 0

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

    # ═══════════ 域名统计 ═══════════
    dom = _exec_one(f"""
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN owner_user_id IS NOT NULL AND claim_status != 'unlinked' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN owner_user_id IS NULL OR claim_status = 'unlinked' THEN 1 ELSE 0 END),0)
        FROM domain_inventory
        {_w(domain_where)}
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
    """递归获取本部门及所有子部门的 ID 列表。"""
    if not dept_id:
        return []
    ids = [dept_id]
    rows = db.execute(text(
        "SELECT id FROM departments WHERE lsdwh = (SELECT dwbm FROM departments WHERE id=:did) AND sfyx='是'"
    ), {"did": dept_id}).fetchall()
    for r in rows:
        ids.extend(_get_sub_dept_ids(db, r[0]))
    return ids
