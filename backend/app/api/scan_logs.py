from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from math import ceil

from app.database import get_db
from app.models.scan_log import ScanLog
from app.schemas.scan import ScanLogOut, PaginatedResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/scan-logs", tags=["扫描日志"])


@router.get("", response_model=PaginatedResponse)
def list_scan_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    switch_id: int = Query(None),
    status: str = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(ScanLog)
    if switch_id:
        q = q.filter(ScanLog.switch_id == switch_id)
    if status:
        q = q.filter(ScanLog.status == status)
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(ScanLog.started_at.desc()).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[ScanLogOut.model_validate(log) for log in items],
        total=total, page=page, size=size, pages=pages,
    )


@router.get("/{log_id}", response_model=ScanLogOut)
def get_scan_log(log_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    log = db.query(ScanLog).get(log_id)
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="扫描日志不存在")
    return ScanLogOut.model_validate(log)
