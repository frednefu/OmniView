from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models.subnet import Subnet
from app.models.route_table import RouteTable
from app.schemas.subnet import SubnetCreate, SubnetUpdate, SubnetOut
from app.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/subnets", tags=["地址段"])


def _is_admin(u):
    if hasattr(u, "role"):
        r = u.role
        return (r.value if hasattr(r, "value") else r) == "admin"
    return False


@router.get("/creators")
def get_subnet_creators(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """获取有地址段数据的用户列表（管理员用）。"""
    if not _is_admin(current_user):
        return {"items": []}
    rows = db.execute(text(
        "SELECT DISTINCT s.created_by, u.name FROM subnets s "
        "LEFT JOIN users u ON s.created_by = u.id WHERE s.created_by IS NOT NULL ORDER BY u.name"
    )).fetchall()
    return {"items": [{"id": r.created_by, "name": r.name or f"用户{r.created_by}"} for r in rows]}


@router.get("/route-cidrs")
def get_route_cidrs(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """获取路由表中去重后的 CIDR 列表（用于自动补全）。"""
    rows = db.execute(text(
        "SELECT cidr, MAX(gateway) as gateway, MAX(interface_name) as vlan "
        "FROM route_tables WHERE cidr IS NOT NULL AND cidr != '' "
        "AND cidr != '0.0.0.0/0' "
        "GROUP BY cidr ORDER BY cidr"
    )).fetchall()
    return {"items": [{"cidr": r.cidr, "gateway": r.gateway or "", "vlan": r.vlan or ""} for r in rows]}


@router.get("/{subnet_id}", response_model=SubnetOut)
def get_subnet(subnet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    sn = db.query(Subnet).get(subnet_id)
    if not sn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地址段不存在")
    return SubnetOut.model_validate(sn)


_SORTABLE = {"id","name","subnet_cidr","gateway","vlan_id","description","is_managed","created_at"}

@router.get("")
def list_subnets(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                 search: str = Query(""), sort_field: str = Query(""), sort_order: str = Query("desc"),
                 created_by: int = Query(None),
                 db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    q = db.query(Subnet)
    if not _is_admin(current_user):
        q = q.filter(Subnet.created_by == current_user.id)
    elif created_by:
        q = q.filter(Subnet.created_by == created_by)
    # 管理员不传 created_by 时显示全部数据
    if search:
        q = q.filter(Subnet.name.contains(search) | Subnet.subnet_cidr.contains(search) | Subnet.gateway.contains(search))
    total = q.count()
    # 排序
    if sort_field and sort_field in _SORTABLE:
        col = getattr(Subnet, sort_field, None)
        if col:
            q = q.order_by(col.desc()) if sort_order == "desc" else q.order_by(col.asc())
        else:
            q = q.order_by(Subnet.id.desc())
    else:
        q = q.order_by(Subnet.id.desc())
    items = q.offset((page - 1) * size).limit(size).all()
    # 批量查询创建人姓名
    user_ids = {s.created_by for s in items if s.created_by}
    user_map = {}
    if user_ids:
        from app.models.user import User
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {u.id: u.name or u.username for u in users}
    return {"items": [{
        "id": s.id, "name": s.name, "subnet_cidr": s.subnet_cidr,
        "gateway": s.gateway, "vlan_id": s.vlan_id,
        "description": s.description, "is_managed": s.is_managed,
        "created_by": s.created_by, "created_by_name": user_map.get(s.created_by, ""),
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    } for s in items], "total": total}


@router.post("", response_model=SubnetOut)
def create_subnet(body: SubnetCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # CIDR 允许不同用户重复添加，同一用户不能重复
    existing = db.query(Subnet).filter(
        Subnet.subnet_cidr == body.subnet_cidr,
        Subnet.created_by == current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"您已添加过地址段 {body.subnet_cidr}，请勿重复添加")
    data = body.model_dump()
    data["created_by"] = current_user.id
    sn = Subnet(**data)
    db.add(sn)
    db.commit()
    db.refresh(sn)
    return SubnetOut.model_validate(sn)


@router.put("/{subnet_id}", response_model=SubnetOut)
def update_subnet(subnet_id: int, body: SubnetUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    sn = db.query(Subnet).get(subnet_id)
    if not sn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地址段不存在")
    if not _is_admin(current_user) and sn.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能编辑自己创建的地址段")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(sn, key, val)
    db.commit()
    db.refresh(sn)
    return SubnetOut.model_validate(sn)


@router.delete("/{subnet_id}")
def delete_subnet(subnet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    sn = db.query(Subnet).get(subnet_id)
    if not sn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地址段不存在")
    if not _is_admin(current_user) and sn.created_by != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能删除自己创建的地址段")
    db.delete(sn)
    db.commit()
    return {"message": "地址段已删除"}
