"""待办任务概览 API — 按角色聚合 VM/域名/信息系统/供应链统计数据"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.api.deps import get_current_user, is_admin_or_dept
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
    is_regular = not is_admin and not is_dept_admin

    result = {}

    # ── 确定数据范围 ──
    if is_admin:
        # 全部数据
        vm_filter = ""
        domain_filter = ""
        is_filter = ""
        sc_filter = ""
        user_dept_filter = ""
    elif is_dept_admin:
        # 本部门及子部门
        dept_ids = _get_sub_dept_ids(db, current_user.department_id)
        if dept_ids:
            ids_str = ",".join(str(d) for d in dept_ids)
            vm_filter = f"WHERE v.department_id IN ({ids_str})"
            domain_filter = f"WHERE d.department_id IN ({ids_str})"
            is_filter = f"WHERE s.dept_id IN ({ids_str})"
            sc_filter = f"WHERE sc.info_system_id IN (SELECT id FROM info_systems WHERE dept_id IN ({ids_str}))"
            user_dept_filter = f"WHERE department_id IN ({ids_str})"
        else:
            vm_filter = "WHERE 1=0"
            domain_filter = "WHERE 1=0"
            is_filter = "WHERE 1=0"
            sc_filter = "WHERE 1=0"
            user_dept_filter = "WHERE 1=0"
    else:
        # 普通用户：本人认领
        uid = current_user.id
        gh = current_user.gh or ""
        vm_filter = f"WHERE a.owner_user_id = {uid}"
        domain_filter = f"WHERE d.owner_user_id = {uid}"
        is_filter = f"WHERE s.manager_gh = '{gh}'"
        sc_filter = f"WHERE sc.info_system_id IN (SELECT id FROM info_systems WHERE manager_gh = '{gh}')"

    # ═══════════ 管理员：部门统计 ═══════════
    if is_admin:
        result["dept_count"] = db.execute(text(
            "SELECT COUNT(*) FROM departments WHERE sfyx='是'"
        )).scalar() or 0

        dept_rows = db.execute(text("""
            SELECT COALESCE(d.dwmc, '未分组') as dept_name,
                   COUNT(DISTINCT v.id) as vm,
                   COUNT(DISTINCT di.id) as domain,
                   COUNT(DISTINCT s.id) as is_count,
                   COUNT(DISTINCT sc.id) as sc,
                   COUNT(DISTINCT u.id) as admin_count
            FROM departments d
            LEFT JOIN vm_inventory v ON v.department_id = d.id
            LEFT JOIN domain_inventory di ON di.department_id = d.id
            LEFT JOIN info_systems s ON s.dept_id = d.id
            LEFT JOIN supply_chains sc ON sc.info_system_id = s.id
            LEFT JOIN users u ON u.department_id = d.id AND u.role IN ('admin','dept_admin')
            WHERE d.sfyx = '是'
            GROUP BY d.id
            ORDER BY vm DESC
        """)).fetchall()
        result["dept_details"] = [
            {"dept_name": r[0], "vm": r[1], "domain": r[2],
             "is_count": r[3], "sc": r[4], "admin_count": r[5]}
            for r in dept_rows
        ]

    # ═══════════ 部门管理员：人员清单 ═══════════
    if is_dept_admin and not is_admin:
        members_sql = f"""
            SELECT u.id, u.name, u.gh, u.role,
                   COUNT(DISTINCT a.id) as vm,
                   COUNT(DISTINCT di.id) as domain,
                   COUNT(DISTINCT s.id) as is_count,
                   COUNT(DISTINCT sc.id) as sc
            FROM users u
            LEFT JOIN asset_inventory a ON a.owner_user_id = u.id
            LEFT JOIN domain_inventory di ON di.owner_user_id = u.id
            LEFT JOIN info_systems s ON s.manager_gh = u.gh
            LEFT JOIN supply_chains sc ON sc.info_system_id = s.id
            {user_dept_filter}
            GROUP BY u.id
            ORDER BY vm DESC
        """
        member_rows = db.execute(text(members_sql)).fetchall()
        result["members"] = [
            {"user_id": r[0], "name": r[1], "gh": r[2], "role": r[3],
             "vm": r[4], "domain": r[5], "is_count": r[6], "sc": r[7]}
            for r in member_rows
        ]

    # ═══════════ VM 统计 ═══════════
    # 总数 + 开关机
    vm_power = db.execute(text(f"""
        SELECT COALESCE(SUM(CASE WHEN v.power_state='poweredOn' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN v.power_state='poweredOff' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN v.power_state NOT IN ('poweredOn','poweredOff') OR v.power_state IS NULL OR v.power_state='' THEN 1 ELSE 0 END),0)
        FROM vm_inventory v
        {"JOIN asset_inventory a ON a.vm_name=v.vm_name" if not is_admin else ""}
        {vm_filter.replace("WHERE ","AND ") if not is_admin else ""}
    """)).fetchone() if not is_admin else db.execute(text("""
        SELECT COALESCE(SUM(CASE WHEN power_state='poweredOn' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN power_state='poweredOff' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN power_state NOT IN ('poweredOn','poweredOff') OR power_state IS NULL OR power_state='' THEN 1 ELSE 0 END),0)
        FROM vm_inventory
    """)).fetchone()

    vm_on, vm_off, vm_other = vm_power[0] or 0, vm_power[1] or 0, vm_power[2] or 0
    vm_total = vm_on + vm_off + vm_other

    # 已备份
    vm_backup = db.execute(text(f"""
        SELECT COUNT(DISTINCT v.id)
        FROM vm_inventory v
        INNER JOIN dingjia_backup_records db ON db.vm_name = v.vm_name
        {"JOIN asset_inventory a ON a.vm_name=v.vm_name" if not is_admin else ""}
        {vm_filter.replace("WHERE ","AND ") if not is_admin else ""}
    """)).scalar() if not is_admin else db.execute(text("""
        SELECT COUNT(DISTINCT v.id) FROM vm_inventory v
        INNER JOIN dingjia_backup_records db ON db.vm_name = v.vm_name
    """)).scalar()

    # 已安装椒图
    vm_qax = db.execute(text(f"""
        SELECT COUNT(DISTINCT v.id)
        FROM vm_inventory v
        INNER JOIN qax_servers q ON q.intranet_ip = v.ip_address OR q.ipv4 = v.ip_address
           OR v.ip_address LIKE CONCAT('%,', q.intranet_ip)
           OR v.ip_address LIKE CONCAT(q.intranet_ip, ',%')
        {"JOIN asset_inventory a ON a.vm_name=v.vm_name" if not is_admin else ""}
        {vm_filter.replace("WHERE ","AND ") if not is_admin else ""}
    """)).scalar() if not is_admin else db.execute(text("""
        SELECT COUNT(DISTINCT v.id) FROM vm_inventory v
        INNER JOIN qax_servers q ON q.intranet_ip = v.ip_address OR q.ipv4 = v.ip_address
           OR v.ip_address LIKE CONCAT('%,', q.intranet_ip)
           OR v.ip_address LIKE CONCAT(q.intranet_ip, ',%')
    """)).scalar()

    # 认领/待认领 + 开关机
    vm_claimed_sql = f"""
        SELECT COALESCE(SUM(CASE WHEN v.power_state='poweredOn' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN v.power_state='poweredOff' THEN 1 ELSE 0 END),0)
        FROM vm_inventory v
        JOIN asset_inventory a ON a.vm_name=v.vm_name
        WHERE a.claim_status != 'unlinked'
    """ if is_admin else f"""
        SELECT COALESCE(SUM(CASE WHEN v.power_state='poweredOn' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN v.power_state='poweredOff' THEN 1 ELSE 0 END),0)
        FROM vm_inventory v
        JOIN asset_inventory a ON a.vm_name=v.vm_name
        {"AND " + vm_filter.replace("WHERE ","") if vm_filter else ""}
        AND a.claim_status != 'unlinked'
    """
    vm_claimed = db.execute(text(vm_claimed_sql)).fetchone()

    vm_unclaimed_sql = f"""
        SELECT COALESCE(SUM(CASE WHEN v.power_state='poweredOn' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN v.power_state='poweredOff' THEN 1 ELSE 0 END),0)
        FROM vm_inventory v
        JOIN asset_inventory a ON a.vm_name=v.vm_name
        WHERE (a.claim_status = 'unlinked' OR a.claim_status IS NULL)
    """ if is_admin else f"""
        SELECT COALESCE(SUM(CASE WHEN v.power_state='poweredOn' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN v.power_state='poweredOff' THEN 1 ELSE 0 END),0)
        FROM vm_inventory v
        JOIN asset_inventory a ON a.vm_name=v.vm_name
        {"AND " + vm_filter.replace("WHERE ","") if vm_filter else ""}
        AND (a.claim_status = 'unlinked' OR a.claim_status IS NULL)
    """
    vm_unclaimed = db.execute(text(vm_unclaimed_sql)).fetchone()

    result["vm"] = {
        "total": vm_total, "power_on": vm_on, "power_off": vm_off,
        "backed_up": (vm_backup or 0), "qax_installed": (vm_qax or 0),
        "claimed": {"on": vm_claimed[0] or 0, "off": vm_claimed[1] or 0},
        "unclaimed": {"on": vm_unclaimed[0] or 0, "off": vm_unclaimed[1] or 0},
    }

    # ═══════════ 域名统计 ═══════════
    domain_sql = f"""
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN owner_user_id IS NOT NULL AND claim_status != 'unlinked' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN owner_user_id IS NULL OR claim_status = 'unlinked' THEN 1 ELSE 0 END),0)
        FROM domain_inventory d
        {domain_filter}
    """ if domain_filter else """
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN owner_user_id IS NOT NULL AND claim_status != 'unlinked' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN owner_user_id IS NULL OR claim_status = 'unlinked' THEN 1 ELSE 0 END),0)
        FROM domain_inventory
    """
    domain_stats = db.execute(text(domain_sql)).fetchone()
    result["domain"] = {
        "total": domain_stats[0] or 0,
        "claimed": domain_stats[1] or 0,
        "unclaimed": domain_stats[2] or 0,
    }

    # ═══════════ 信息系统统计 ═══════════
    is_sql = f"""
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN manager_gh IS NOT NULL AND manager_gh != '' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN manager_gh IS NULL OR manager_gh = '' THEN 1 ELSE 0 END),0)
        FROM info_systems s
        {is_filter}
    """ if is_filter else """
        SELECT COUNT(*),
               COALESCE(SUM(CASE WHEN manager_gh IS NOT NULL AND manager_gh != '' THEN 1 ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN manager_gh IS NULL OR manager_gh = '' THEN 1 ELSE 0 END),0)
        FROM info_systems
    """
    is_stats = db.execute(text(is_sql)).fetchone()
    result["is"] = {
        "total": is_stats[0] or 0,
        "claimed": is_stats[1] or 0,
        "unclaimed": is_stats[2] or 0,
    }

    # ═══════════ IS 数据完整性 ═══════════
    is_comp_sql = f"""
        SELECT
            COUNT(*),
            COALESCE(SUM(CASE WHEN system_name IS NOT NULL AND system_name != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN system_type IS NOT NULL AND system_type != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN sub_type IS NOT NULL AND sub_type != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN domain IS NOT NULL AND domain != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN manager_name IS NOT NULL AND manager_name != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN dept_id IS NOT NULL THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN djdj_level IS NOT NULL AND djdj_level != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN vendor_name IS NOT NULL AND vendor_name != '' THEN 1 ELSE 0 END),0)
        FROM info_systems s
        {is_filter}
    """ if is_filter else """
        SELECT
            COUNT(*),
            COALESCE(SUM(CASE WHEN system_name IS NOT NULL AND system_name != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN system_type IS NOT NULL AND system_type != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN sub_type IS NOT NULL AND sub_type != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN domain IS NOT NULL AND domain != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN manager_name IS NOT NULL AND manager_name != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN dept_id IS NOT NULL THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN djdj_level IS NOT NULL AND djdj_level != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN vendor_name IS NOT NULL AND vendor_name != '' THEN 1 ELSE 0 END),0)
        FROM info_systems
    """
    is_comp = db.execute(text(is_comp_sql)).fetchone()
    total_is = is_comp[0] or 1
    result["is_completeness"] = {
        "system_name": round((is_comp[1] or 0) / total_is * 100),
        "system_type": round((is_comp[2] or 0) / total_is * 100),
        "sub_type": round((is_comp[3] or 0) / total_is * 100),
        "domain": round((is_comp[4] or 0) / total_is * 100),
        "manager": round((is_comp[5] or 0) / total_is * 100),
        "dept": round((is_comp[6] or 0) / total_is * 100),
        "djdj": round((is_comp[7] or 0) / total_is * 100),
        "vendor": round((is_comp[8] or 0) / total_is * 100),
    }

    # ═══════════ SC 完整性 ═══════════
    sc_comp_sql = f"""
        SELECT COUNT(*),
            COALESCE(SUM(CASE WHEN company_name IS NOT NULL AND company_name != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN contact_person IS NOT NULL AND contact_person != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN contact_phone IS NOT NULL AND contact_phone != '' THEN 1 ELSE 0 END),0)
        FROM supply_chains sc
        {sc_filter}
    """ if sc_filter else """
        SELECT COUNT(*),
            COALESCE(SUM(CASE WHEN company_name IS NOT NULL AND company_name != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN contact_person IS NOT NULL AND contact_person != '' THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN contact_phone IS NOT NULL AND contact_phone != '' THEN 1 ELSE 0 END),0)
        FROM supply_chains
    """
    sc_comp = db.execute(text(sc_comp_sql)).fetchone()
    total_sc = sc_comp[0] or 1
    result["sc_completeness"] = {
        "company_name": round((sc_comp[1] or 0) / total_sc * 100),
        "contact_person": round((sc_comp[2] or 0) / total_sc * 100),
        "contact_phone": round((sc_comp[3] or 0) / total_sc * 100),
    }

    return result


def _get_sub_dept_ids(db, dept_id):
    """递归获取本部门及所有子部门的 ID 列表。"""
    if not dept_id:
        return []
    ids = [dept_id]
    # 获取子部门
    rows = db.execute(text(
        "SELECT id FROM departments WHERE lsdwh = (SELECT dwbm FROM departments WHERE id=:did) AND sfyx='是'"
    ), {"did": dept_id}).fetchall()
    for r in rows:
        ids.extend(_get_sub_dept_ids(db, r[0]))
    return ids
