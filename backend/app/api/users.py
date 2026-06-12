"""用户管理 API — 仅管理员可操作。"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from math import ceil

from app.database import get_db
from app.models.user import User
from app.models.department import Department
from app.models.staff_info import StaffInfo
from app.schemas.user import UserCreate, UserUpdate, UserOut, PasswordChange
from app.utils.security import hash_password
from app.api.deps import require_admin

router = APIRouter(prefix="/users", tags=["用户管理"])


def _user_out(user: User) -> UserOut:
    data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "avatar_url": user.avatar_url,
        "is_active": user.is_active,
        "gh": user.gh,
        "name": user.name,
        "department_id": user.department_id,
        "department_name": user.department.dwmc if user.department else None,
        "phone": user.phone,
        "mobile": user.mobile,
        "gender": user.gender or "",
        "user_type": user.user_type or "internal",
        "company": user.company,
        "contact_person": user.contact_person,
        "notes": user.notes,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
    return UserOut(**data)


@router.get("")
def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=128),
    department_id: int = Query(None, description="按部门筛选"),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    q = db.query(User)
    if search:
        q = q.filter(
            (User.username.contains(search))
            | (User.email.contains(search))
            | (User.gh.contains(search))
            | (User.name.contains(search))
        )
    if department_id is not None:
        q = q.filter(User.department_id == department_id)
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(User.id).offset((page - 1) * size).limit(size).all()
    return {
        "items": [_user_out(u) for u in items],
        "total": total, "page": page, "size": size, "pages": pages,
    }


@router.post("", response_model=UserOut)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    email = body.email
    phone = body.phone
    mobile = body.mobile
    name = body.name
    # 从 StaffInfo 自动填充联系方式
    if body.gh:
        staff = db.query(StaffInfo).filter(StaffInfo.gh == body.gh).first()
        if staff:
            if not email:
                email = staff.dzyx
            if not phone:
                phone = staff.bgdh
            if not mobile:
                mobile = staff.yddh
            if not name:
                name = staff.xm
    password = body.password or (body.gh or body.username)
    if email and db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已存在")
    user = User(
        username=body.username,
        password_hash=hash_password(password),
        role=body.role,
        email=email,
        gh=body.gh,
        name=name,
        department_id=body.department_id,
        phone=phone,
        mobile=mobile,
        gender=body.gender,
        user_type=body.user_type or "internal",
        company=body.company,
        contact_person=body.contact_person,
        notes=body.notes,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return _user_out(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if body.email is not None:
        existing = db.query(User).filter(User.email == body.email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已被其他用户使用")
        user.email = body.email
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.gh is not None:
        user.gh = body.gh
    if body.name is not None:
        user.name = body.name
    if body.department_id is not None:
        user.department_id = body.department_id
    if body.phone is not None:
        user.phone = body.phone
    if body.mobile is not None:
        user.mobile = body.mobile
    if body.gender is not None:
        user.gender = body.gender
    if body.user_type is not None:
        user.user_type = body.user_type
    if body.company is not None:
        user.company = body.company
    if body.contact_person is not None:
        user.contact_person = body.contact_person
    if body.notes is not None:
        user.notes = body.notes
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    try:
        db.delete(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该用户有关联的业务数据，无法删除。请先禁用该用户，或将其关联数据转移后再删除。",
        )
    return {"message": "用户已删除"}


@router.post("/batch-delete")
def batch_delete_users(
    body: dict,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """批量删除用户。"""
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的用户")
    deleted = 0
    errors = []
    for uid in ids:
        try:
            user = db.query(User).get(uid)
            if user and user.id != admin.id:
                db.delete(user)
                db.commit()
                deleted += 1
            elif user:
                errors.append(f"{user.username}: 不能删除自己")
        except IntegrityError:
            db.rollback()
            errors.append(f"ID={uid}: 有关联数据无法删除")
    return {"message": f"成功删除 {deleted} 个用户", "deleted": deleted, "errors": errors}


@router.post("/batch-disable")
def batch_disable_users(
    body: dict,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """批量禁用/启用用户。"""
    ids = body.get("ids", [])
    action = body.get("action", "disable")  # disable or enable
    if not ids:
        raise HTTPException(status_code=400, detail="请选择用户")
    new_state = 0 if action == "disable" else 1
    updated = 0
    for uid in ids:
        user = db.query(User).get(uid)
        if user and user.id != admin.id:
            user.is_active = bool(new_state)
            updated += 1
    db.commit()
    return {"message": f"成功{action} {updated} 个用户", "updated": updated}


@router.put("/{user_id}/reset-password")
def reset_password(user_id: int, body: PasswordChange, db: Session = Depends(get_db), admin=Depends(require_admin)):
    """管理员重置其他用户的密码。"""
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"message": "密码已重置"}
