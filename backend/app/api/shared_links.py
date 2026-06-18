"""外链填报 API — 创建/管理临时外链 + 外部访问。"""
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.shared_link import SharedLink, _gen_token
from app.models.info_system import SupplyChain, InfoSystem
from app.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/shared-links", tags=["外链填报"])

TZ = timezone(timedelta(hours=8))


class CreateLinkBody(BaseModel):
    target_type: str = "supply_chain"
    target_id: int
    title: str = ""
    password: str = ""          # 空字符串=不设密码
    expire_hours: int = 0       # 0=永不过期


def _hash_pwd(pwd: str) -> str | None:
    if not pwd or not pwd.strip():
        return None
    return hashlib.sha256(pwd.encode()).hexdigest()


def _check_pwd(pwd: str, hashed: str | None) -> bool:
    if not hashed:
        return True
    if not pwd:
        return False
    return hashlib.sha256(pwd.encode()).hexdigest() == hashed


# ── 管理端 API ──

@router.get("")
def list_all_links(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                  search: str = Query(""), db: Session = Depends(get_db), _=Depends(require_admin)):
    """管理员查看所有外链。"""
    from app.models.user import User
    q = db.query(SharedLink)
    if search:
        q = q.filter(
            SharedLink.title.contains(search) |
            SharedLink.token.contains(search)
        )
    total = q.count()
    items = q.order_by(SharedLink.created_at.desc()).offset((page - 1) * size).limit(size).all()
    # 获取创建人姓名
    user_ids = {l.created_by for l in items if l.created_by}
    users = {u.id: u.name for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return {"items": [{
        "id": l.id, "token": l.token, "title": l.title,
        "target_type": l.target_type, "target_id": l.target_id,
        "has_password": bool(l.password), "is_active": l.is_active,
        "access_count": l.access_count or 0,
        "expire_at": l.expire_at.isoformat() if l.expire_at else None,
        "created_by_name": users.get(l.created_by, ""),
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "url": f"/s/{l.token}",
    } for l in items], "total": total}


@router.post("")
def create_link(body: CreateLinkBody, db: Session = Depends(get_db), user=Depends(require_admin)):
    """创建外链。"""
    if body.target_type == "supply_chain":
        target = db.query(SupplyChain).get(body.target_id)
        if not target:
            raise HTTPException(404, "供应链记录不存在")
    elif body.target_type == "info_system":
        target = db.query(InfoSystem).get(body.target_id)
        if not target:
            raise HTTPException(404, "信息系统记录不存在")
    else:
        raise HTTPException(400, "不支持的目标类型")

    link = SharedLink(
        token=_gen_token(),
        target_type=body.target_type,
        target_id=body.target_id,
        title=body.title or f"外链填报 - {getattr(target, 'company_name', '')}",
        password=_hash_pwd(body.password),
        expire_at=datetime.now(TZ).replace(tzinfo=None) + timedelta(hours=body.expire_hours)
        if body.expire_hours > 0 else None,
        created_by=user.id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    return {
        "id": link.id,
        "token": link.token,
        "title": link.title,
        "has_password": bool(link.password),
        "expire_at": link.expire_at.isoformat() if link.expire_at else None,
        "is_active": link.is_active,
        "url": f"/s/{link.token}",
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


@router.get("/by-target")
def list_links(target_type: str = "supply_chain", target_id: int = Query(...),
               db: Session = Depends(get_db), _=Depends(require_admin)):
    """查询某个记录的所有外链。"""
    links = db.query(SharedLink).filter(
        SharedLink.target_type == target_type,
        SharedLink.target_id == target_id,
    ).order_by(SharedLink.created_at.desc()).all()
    return {"items": [{
        "id": l.id, "token": l.token, "title": l.title,
        "has_password": bool(l.password), "is_active": l.is_active,
        "access_count": l.access_count,
        "expire_at": l.expire_at.isoformat() if l.expire_at else None,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "url": f"/s/{l.token}",
    } for l in links]}


@router.put("/{token}/toggle")
def toggle_link(token: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    """手动启用/关闭外链。"""
    link = db.query(SharedLink).filter(SharedLink.token == token).first()
    if not link:
        raise HTTPException(404, "外链不存在")
    link.is_active = not link.is_active
    db.commit()
    return {"message": "已启用" if link.is_active else "已关闭", "is_active": link.is_active}


@router.delete("/{token}")
def delete_link(token: str, db: Session = Depends(get_db), _=Depends(require_admin)):
    """删除外链。"""
    link = db.query(SharedLink).filter(SharedLink.token == token).first()
    if not link:
        raise HTTPException(404, "外链不存在")
    db.delete(link)
    db.commit()
    return {"message": "已删除"}


# ── 外部访问 API（无需登录）──

@router.get("/shared/{token}")
def access_shared(token: str, password: str = Query(""), db: Session = Depends(get_db)):
    """外部访问：验证外链并返回填报数据。"""
    link = db.query(SharedLink).filter(SharedLink.token == token).first()
    if not link:
        raise HTTPException(404, "外链不存在或已删除")
    if not link.is_active:
        raise HTTPException(403, "外链已关闭")
    if link.expire_at and datetime.now(TZ).replace(tzinfo=None) > link.expire_at:
        raise HTTPException(403, "外链已过期")

    # 验证密码
    if not _check_pwd(password, link.password):
        raise HTTPException(403, "访问密码错误")

    link.access_count = (link.access_count or 0) + 1
    db.commit()

    # 返回目标数据
    if link.target_type == "supply_chain":
        target = db.query(SupplyChain).get(link.target_id)
        if not target:
            raise HTTPException(404, "记录不存在")
        data = {c.name: getattr(target, c.name) for c in target.__table__.columns
                if c.name not in ("id", "created_at", "updated_at")}
        # 日期转字符串
        for k, v in data.items():
            if hasattr(v, 'isoformat'):
                data[k] = v.isoformat()
            elif v is None:
                data[k] = ""
        return {"title": link.title, "has_password": bool(link.password), "target_type": link.target_type, "data": data}
    elif link.target_type == "info_system":
        target = db.query(InfoSystem).get(link.target_id)
        if not target:
            raise HTTPException(404, "记录不存在")
        data = {c.name: getattr(target, c.name) for c in target.__table__.columns
                if c.name not in ("id", "created_at", "updated_at")}
        for k, v in data.items():
            if hasattr(v, 'isoformat'):
                data[k] = v.isoformat()
            elif v is None:
                data[k] = ""
        return {"title": link.title, "has_password": bool(link.password), "target_type": link.target_type, "data": data}
    raise HTTPException(400, "不支持的目标类型")


@router.post("/shared/{token}")
def save_shared(token: str, body: dict, password: str = Query(""), db: Session = Depends(get_db)):
    """外部保存：通过外链提交填报数据。"""
    link = db.query(SharedLink).filter(SharedLink.token == token).first()
    if not link:
        raise HTTPException(404, "外链不存在或已删除")
    if not link.is_active:
        raise HTTPException(403, "外链已关闭")
    if link.expire_at and datetime.now(TZ).replace(tzinfo=None) > link.expire_at:
        raise HTTPException(403, "外链已过期")

    if not _check_pwd(password, link.password):
        raise HTTPException(403, "访问密码错误")

    if link.target_type == "supply_chain":
        target = db.query(SupplyChain).get(link.target_id)
        if not target:
            raise HTTPException(404, "记录不存在")

        valid_cols = {c.name for c in target.__table__.columns
                      if c.name not in ("id", "created_at", "updated_at")}
        changed = []
        for k, v in body.items():
            if k in valid_cols:
                old = getattr(target, k)
                new = v if v != "" else None
                if old != new:
                    setattr(target, k, new)
                    changed.append(k)
        db.commit()
        # 自动创建供应链记录
        from app.api.info_systems import _ensure_supply_chain
        _ensure_supply_chain(db, body.get("vendor_name", ""))
        return {"message": f"保存成功，更新 {len(changed)} 个字段", "changed": changed}
    elif link.target_type == "info_system":
        target = db.query(InfoSystem).get(link.target_id)
        if not target:
            raise HTTPException(404, "记录不存在")
        valid_cols = {c.name for c in target.__table__.columns
                      if c.name not in ("id", "created_at", "updated_at", "asset_id")}
        changed = []
        for k, v in body.items():
            if k in valid_cols:
                old = getattr(target, k)
                new = v if v != "" else None
                if old != new:
                    setattr(target, k, new)
                    changed.append(k)
        db.commit()
        from app.api.info_systems import _ensure_supply_chain
        _ensure_supply_chain(db, body.get("vendor_name", ""))
        return {"message": f"保存成功，更新 {len(changed)} 个字段", "changed": changed}
    raise HTTPException(400, "不支持的目标类型")
