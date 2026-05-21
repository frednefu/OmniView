from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from math import ceil

from app.database import get_db
from app.models.switch import Switch
from app.models.scan_log import ScanLog, ScanStatus, TriggerType
from app.schemas.switch import SwitchCreate, SwitchUpdate, SwitchOut
from app.schemas.scan import ScanLogOut, PaginatedResponse
from app.api.deps import get_current_user, require_admin
from app.services.scanner_service import trigger_scan

router = APIRouter(prefix="/switches", tags=["交换机"])


@router.get("", response_model=PaginatedResponse)
def list_switches(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=128),
    is_active: bool = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(Switch)
    if search:
        q = q.filter(
            (Switch.name.contains(search)) | (Switch.ip_address.contains(search))
        )
    if is_active is not None:
        q = q.filter(Switch.is_active == is_active)
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(Switch.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[SwitchOut.model_validate(s) for s in items],
        total=total, page=page, size=size, pages=pages,
    )


@router.post("", response_model=SwitchOut)
def create_switch(body: SwitchCreate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    existing = db.query(Switch).filter(Switch.ip_address == body.ip_address).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="交换机 IP 已存在")
    sw = Switch(**body.model_dump(), created_by=admin.id)
    db.add(sw)
    db.commit()
    db.refresh(sw)
    return SwitchOut.model_validate(sw)


@router.get("/{switch_id}", response_model=SwitchOut)
def get_switch(switch_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    sw = db.query(Switch).get(switch_id)
    if not sw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="交换机不存在")
    return SwitchOut.model_validate(sw)


@router.put("/{switch_id}", response_model=SwitchOut)
def update_switch(switch_id: int, body: SwitchUpdate, db: Session = Depends(get_db), admin=Depends(require_admin)):
    sw = db.query(Switch).get(switch_id)
    if not sw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="交换机不存在")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(sw, key, val)
    db.commit()
    db.refresh(sw)
    return SwitchOut.model_validate(sw)


@router.delete("/{switch_id}")
def delete_switch(switch_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    sw = db.query(Switch).get(switch_id)
    if not sw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="交换机不存在")
    db.delete(sw)
    db.commit()
    return {"message": "交换机已删除"}


@router.post("/{switch_id}/scan", response_model=ScanLogOut)
def trigger_switch_scan(
    switch_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    sw = db.query(Switch).get(switch_id)
    if not sw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="交换机不存在")

    # Check for existing running scan
    running = db.query(ScanLog).filter(
        ScanLog.switch_id == switch_id,
        ScanLog.status == ScanStatus.running,
    ).first()
    if running:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该交换机正在扫描中")

    scan_log_id = trigger_scan(sw, TriggerType.manual, "")
    scan_log = db.query(ScanLog).get(scan_log_id)
    return ScanLogOut.model_validate(scan_log)
