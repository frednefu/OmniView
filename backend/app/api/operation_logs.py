"""操作日志 API。"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models.operation_log import OperationLog
from app.api.deps import require_admin

router = APIRouter(prefix="/operation-logs", tags=["操作日志"])

_SORTABLE = {"id", "username", "method", "api_path", "status_code", "duration_ms", "created_at"}


@router.get("")
def list_logs(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    search: str = Query(""), sort_field: str = Query("created_at"),
    sort_order: str = Query("desc"), username: str = Query(""),
    method: str = Query(""), status: str = Query(""),
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    q = db.query(OperationLog)
    if search:
        q = q.filter(
            OperationLog.username.contains(search) |
            OperationLog.api_path.contains(search) |
            OperationLog.detail.contains(search)
        )
    if username:
        q = q.filter(OperationLog.username.contains(username))
    if method:
        q = q.filter(OperationLog.method == method.upper())
    if status == "success":
        q = q.filter(OperationLog.status_code < 400)
    elif status == "failed":
        q = q.filter(OperationLog.status_code >= 400)
    total = q.count()
    # 排序
    if sort_field in _SORTABLE:
        col = getattr(OperationLog, sort_field)
        q = q.order_by(col.desc()) if sort_order == "desc" else q.order_by(col.asc())
    else:
        q = q.order_by(OperationLog.created_at.desc())
    items = q.offset((page - 1) * size).limit(size).all()
    return {"items": [{
        "id": r.id, "username": r.username, "ip_address": r.ip_address,
        "method": r.method, "api_path": r.api_path, "status_code": r.status_code,
        "duration_ms": r.duration_ms, "detail": r.detail,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in items], "total": total}


@router.delete("")
def clean_logs(before_days: int = Query(30, ge=1, le=365, description="清理多少天前的日志"),
               db: Session = Depends(get_db), _=Depends(require_admin)):
    """按天数清理旧日志。"""
    cutoff = datetime.now() - timedelta(days=before_days)
    result = db.query(OperationLog).filter(OperationLog.created_at < cutoff).delete()
    db.commit()
    return {"message": f"已清理 {result} 条日志（{before_days}天前）", "deleted": result}
