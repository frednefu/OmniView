"""组织机构管理 — 同步和查询院系所组织树。"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.department import Department
from app.models.user import User
from app.schemas.department import DepartmentTreeNode, DepartmentSyncResult
from app.api.deps import require_admin, get_current_user
from app.services import external_api_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sys/departments", tags=["组织机构"])


def _build_tree(departments: list[Department], dept_user_counts: dict[int, int], all_depts: bool = False) -> list[DepartmentTreeNode]:
    """构建组织树。all_depts=False 时显示有用户部门及其全部上级。"""
    # 建立 dwbm → department 映射
    dept_by_code: dict[str, Department] = {d.dwbm: d for d in departments}

    # 收集需保留的部门 ID：有用户 + 其祖先
    keep_ids: set[int] = set()
    if all_depts:
        keep_ids = {d.id for d in departments}
    else:
        # 先找所有有用户的部门
        user_dept_ids = {d_id for d_id, cnt in dept_user_counts.items() if cnt > 0}
        # 回溯祖先链
        for d_id in list(user_dept_ids):
            current_id = d_id
            while current_id:
                keep_ids.add(current_id)
                dept = next((d for d in departments if d.id == current_id), None)
                if dept and dept.lsdwh and dept.lsdwh in dept_by_code:
                    current_id = dept_by_code[dept.lsdwh].id
                else:
                    break

    # 构建节点映射
    node_map: dict[str, DepartmentTreeNode] = {}
    for d in departments:
        if d.id not in keep_ids:
            continue
        count = dept_user_counts.get(d.id, 0)
        node_map[d.dwbm] = DepartmentTreeNode(
            id=d.id,
            dwbm=d.dwbm,
            dwmc=d.dwmc,
            dwjc=d.dwjc,
            lsdwh=d.lsdwh,
            pxh=d.pxh,
            user_count=count,
            children=[],
        )

    roots = []
    for dwbm, node in node_map.items():
        parent_code = node.lsdwh
        if parent_code and parent_code in node_map:
            node_map[parent_code].children.append(node)
        else:
            roots.append(node)

    def sort_children(nodes):
        nodes.sort(key=lambda n: (n.pxh or "9999", n.dwbm))
        for n in nodes:
            sort_children(n.children)

    sort_children(roots)
    return roots


@router.post("/sync", response_model=DepartmentSyncResult)
def sync_departments(db: Session = Depends(get_db), _=Depends(require_admin)):
    """从外部 API 全量同步组织机构数据。"""
    try:
        items = external_api_service.fetch_all_departments(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败：{e}")

    created, updated = 0, 0
    for item in items:
        dwbm = item.get("DWBM", "").strip()
        if not dwbm:
            continue
        dept = db.query(Department).filter(Department.dwbm == dwbm).first()
        if not dept:
            dept = Department(dwbm=dwbm)
            db.add(dept)
            created += 1
        else:
            updated += 1

        dept.dwmc = item.get("DWMC", "")
        dept.dwywmc = item.get("DWYWMC")
        dept.dwjc = item.get("DWJC")
        dept.dwdz = item.get("DWDZ")
        dept.dwcc = item.get("DWCC")
        dept.lsdwh = item.get("LSDWH")
        dept.dwlbm = item.get("DWLBM")
        dept.dwlbmc = item.get("DWLBMC")
        dept.dwjbm = item.get("DWJBM")
        dept.dwjbmc = item.get("DWJBMC")
        dept.dwxzm = item.get("DWXZM")
        dept.dwxzmc = item.get("DWXZMC")
        dept.dwfzrgh = item.get("DWFZRGH")
        dept.jlny = item.get("JLNY")
        dept.sfst = item.get("SFST")
        dept.pxh = item.get("PXH")
        dept.sfyx = item.get("SFYX")
        dept.tstamp = item.get("TSTAMP")

    db.commit()
    logger.info(f"组织机构同步完成：总计 {len(items)} 条，新增 {created}，更新 {updated}")
    return DepartmentSyncResult(total=len(items), created=created, updated=updated)


@router.get("/tree", response_model=list[DepartmentTreeNode])
def get_department_tree(
    all: bool = Query(False, description="是否显示全部部门（含无账号部门）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取组织树。所有已登录用户均可查看全部部门树。"""
    departments = db.query(Department).all()
    # 统计每个部门的用户数
    from sqlalchemy import func as sa_func
    user_counts = (
        db.query(User.department_id, sa_func.count(User.id))
        .filter(User.department_id.isnot(None))
        .group_by(User.department_id)
        .all()
    )
    dept_user_counts = {d_id: cnt for d_id, cnt in user_counts}
    return _build_tree(departments, dept_user_counts, all_depts=all)


@router.get("/{dept_id}/users")
def get_department_users(
    dept_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """获取指定部门下的用户列表。"""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="部门不存在")
    users = (
        db.query(User)
        .filter(User.department_id == dept_id)
        .order_by(User.id)
        .all()
    )
    return [
        {
            "id": u.id,
            "username": u.username,
            "name": u.name,
            "gh": u.gh,
            "gender": u.gender or "",
            "email": u.email,
            "phone": u.phone,
            "mobile": u.mobile,
            "role": u.role.value if hasattr(u.role, "value") else u.role,
            "is_active": u.is_active,
            "department_name": dept.dwmc,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]
