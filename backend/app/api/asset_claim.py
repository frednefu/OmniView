"""资产认领 + 管理员指派 — 写入 asset_inventory 表。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user, require_admin
from app.schemas.asset import ClaimRequest, AssignRequest

router = APIRouter(prefix="/assets", tags=["资产认领"])


@router.post("/claim")
def claim_assets(
    body: ClaimRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """认领资产到本部门。"""
    is_admin = current_user.role.value == "admin" if hasattr(current_user.role, "value") else current_user.role == "admin"
    dept_id = body.department_id if is_admin and body.department_id else current_user.department_id
    if not dept_id:
        raise HTTPException(status_code=400, detail="您没有所属部门")

    claimed = 0
    for vid in body.vm_ids:
        # 从 vm_inventory 获取 vm_name
        vm = db.execute(text("SELECT vm_name FROM vm_inventory WHERE id=:id"), {"id": vid}).fetchone()
        if not vm:
            continue
        db.execute(text(
            "INSERT INTO asset_inventory (vm_name, department_id, owner_user_id, claim_status, claimed_by, claimed_at) "
            "VALUES (:n, :d, :u, 'manual', :u, NOW()) "
            "ON DUPLICATE KEY UPDATE department_id=COALESCE(department_id,:d), owner_user_id=:u, claim_status='manual', claimed_by=:u, claimed_at=NOW()"
        ), {"n": vm.vm_name, "d": dept_id, "u": current_user.id})
        claimed += 1
    db.commit()
    return {"message": f"成功认领 {claimed} 个资产", "claimed": claimed}


@router.post("/assign")
def assign_assets(
    body: AssignRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """管理员指派资产到部门或具体用户。"""
    if not body.vm_ids:
        raise HTTPException(status_code=400, detail="请选择资产")

    assigned = 0
    for vid in body.vm_ids:
        vm = db.execute(text("SELECT vm_name FROM vm_inventory WHERE id=:id"), {"id": vid}).fetchone()
        if not vm:
            continue
        updates = ["claim_status='manual'", "claimed_at=NOW()"]
        if body.department_id:
            updates.append(f"department_id={body.department_id}")
        if body.user_id:
            updates.append(f"owner_user_id={body.user_id}")
            updates.append(f"claimed_by={body.user_id}")
        set_clause = ", ".join(updates)
        db.execute(text(
            f"INSERT INTO asset_inventory (vm_name, department_id, owner_user_id, claim_status, claimed_by, claimed_at) "
            f"VALUES (:n, :d, :u, 'manual', :c, NOW()) "
            f"ON DUPLICATE KEY UPDATE {set_clause}"
        ), {"n": vm.vm_name, "d": body.department_id, "u": body.user_id, "c": body.user_id})
        assigned += 1
    db.commit()
    return {"message": f"成功指派 {assigned} 个资产", "assigned": assigned}


@router.post("/revoke")
def revoke_assets(
    body: ClaimRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """撤销认领：清空负责人。"""
    if not body.vm_ids:
        raise HTTPException(status_code=400, detail="请选择资产")

    revoked = 0
    for vid in body.vm_ids:
        vm = db.execute(text("SELECT vm_name FROM vm_inventory WHERE id=:id"), {"id": vid}).fetchone()
        if not vm:
            continue
        db.execute(text(
            "UPDATE asset_inventory SET owner_user_id=NULL, claimed_by=NULL, claim_status='unlinked', claimed_at=NULL WHERE vm_name=:n"
        ), {"n": vm.vm_name})
        revoked += 1
    db.commit()
    return {"message": f"成功撤销 {revoked} 个资产认领", "revoked": revoked}


@router.post("/reset-all")
def reset_all_assets(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """重置所有关联数据。"""
    result = db.execute(text("UPDATE asset_inventory SET department_id=NULL, owner_user_id=NULL, claim_status='unlinked', claimed_by=NULL, claimed_at=NULL"))
    db.commit()
    return {"message": f"已重置 {result.rowcount} 条资产关联数据", "count": result.rowcount}
