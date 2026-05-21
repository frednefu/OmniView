from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.subnet import Subnet
from app.schemas.subnet import SubnetCreate, SubnetUpdate, SubnetOut
from app.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/subnets", tags=["地址段"])


@router.get("", response_model=list[SubnetOut])
def list_subnets(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return [SubnetOut.model_validate(s) for s in db.query(Subnet).order_by(Subnet.id).all()]


@router.post("", response_model=SubnetOut)
def create_subnet(body: SubnetCreate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    existing = db.query(Subnet).filter(Subnet.subnet_cidr == body.subnet_cidr).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="地址段已存在")
    sn = Subnet(**body.model_dump())
    db.add(sn)
    db.commit()
    db.refresh(sn)
    return SubnetOut.model_validate(sn)


@router.get("/{subnet_id}", response_model=SubnetOut)
def get_subnet(subnet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    sn = db.query(Subnet).get(subnet_id)
    if not sn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地址段不存在")
    return SubnetOut.model_validate(sn)


@router.put("/{subnet_id}", response_model=SubnetOut)
def update_subnet(subnet_id: int, body: SubnetUpdate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    sn = db.query(Subnet).get(subnet_id)
    if not sn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地址段不存在")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(sn, key, val)
    db.commit()
    db.refresh(sn)
    return SubnetOut.model_validate(sn)


@router.delete("/{subnet_id}")
def delete_subnet(subnet_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    sn = db.query(Subnet).get(subnet_id)
    if not sn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地址段不存在")
    db.delete(sn)
    db.commit()
    return {"message": "地址段已删除"}
