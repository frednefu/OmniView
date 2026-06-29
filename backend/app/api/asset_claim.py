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
    """认领资产到本部门。非管理员只能认领无主或自己已认领的资产。"""
    is_admin = current_user.role.value == "admin" if hasattr(current_user.role, "value") else current_user.role == "admin"
    dept_id = body.department_id if is_admin and body.department_id else current_user.department_id
    if not dept_id:
        raise HTTPException(status_code=400, detail="您没有所属部门")

    claimed = 0
    skipped = 0
    for vid in body.vm_ids:
        vm = db.execute(text("SELECT vm_name FROM vm_inventory WHERE id=:id"), {"id": vid}).fetchone()
        if not vm:
            skipped += 1
            continue
        # 检查资产是否已被其他人认领
        exist = db.execute(text(
            "SELECT owner_user_id FROM asset_inventory WHERE vm_name=:n AND owner_user_id IS NOT NULL"
        ), {"n": vm.vm_name}).fetchone()
        if exist and not is_admin and exist.owner_user_id != current_user.id:
            skipped += 1  # 已是他人资产，跳过
            continue
        db.execute(text(
            "INSERT INTO asset_inventory (vm_name, department_id, owner_user_id, claim_status, claimed_by, claimed_at) "
            "VALUES (:n, :d, :u, 'manual', :u, NOW()) "
            "ON DUPLICATE KEY UPDATE department_id=COALESCE(department_id,:d), owner_user_id=:u, claim_status='manual', claimed_by=:u, claimed_at=NOW()"
        ), {"n": vm.vm_name, "d": dept_id, "u": current_user.id})
        claimed += 1
    db.commit()
    if skipped and not claimed:
        raise HTTPException(status_code=403, detail=f"操作失败：{skipped} 个资产已被他人认领，您无权覆盖")
    suffix = f"，{skipped} 个已被他人认领已跳过" if skipped else ""
    return {"message": f"成功认领 {claimed} 个资产{suffix}", "claimed": claimed, "skipped": skipped}


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
    """撤销认领：清空负责人。非管理员只能撤销自己认领的资产。"""
    if not body.vm_ids:
        raise HTTPException(status_code=400, detail="请选择资产")

    is_admin = current_user.role.value == "admin" if hasattr(current_user.role, "value") else current_user.role == "admin"
    revoked = 0
    skipped = 0
    for vid in body.vm_ids:
        vm = db.execute(text("SELECT vm_name FROM vm_inventory WHERE id=:id"), {"id": vid}).fetchone()
        if not vm:
            skipped += 1
            continue
        # 非管理员只能撤销自己认领的
        exist = db.execute(text(
            "SELECT owner_user_id FROM asset_inventory WHERE vm_name=:n AND owner_user_id IS NOT NULL"
        ), {"n": vm.vm_name}).fetchone()
        if exist and not is_admin and exist.owner_user_id != current_user.id:
            skipped += 1  # 不是自己认领的，跳过
            continue
        db.execute(text(
            "UPDATE asset_inventory SET owner_user_id=NULL, claimed_by=NULL, claim_status='unlinked', claimed_at=NULL WHERE vm_name=:n"
        ), {"n": vm.vm_name})
        revoked += 1
    db.commit()
    if skipped and not revoked:
        raise HTTPException(status_code=403, detail=f"操作失败：{skipped} 个资产不是您认领的，无权撤销")
    suffix = f"，{skipped} 个非本人认领已跳过" if skipped else ""
    return {"message": f"成功撤销 {revoked} 个资产认领{suffix}", "revoked": revoked, "skipped": skipped}


@router.post("/reset-all")
def reset_all_assets(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """重置所有关联数据。"""
    result = db.execute(text("UPDATE asset_inventory SET department_id=NULL, owner_user_id=NULL, claim_status='unlinked', claimed_by=NULL, claimed_at=NULL"))
    db.commit()
    return {"message": f"已重置 {result.rowcount} 条资产关联数据", "count": result.rowcount}
