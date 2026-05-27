"""Worker 管理 API — 注册/心跳/注销（Worker 认证），列表/详情/删除（管理员认证）。"""
import hashlib
from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.scan_worker import ScanWorker
from app.schemas.worker import (
    WorkerRegisterRequest,
    WorkerRegisterResponse,
    WorkerHeartbeatRequest,
    WorkerOut,
)
from app.api.deps import require_admin
from app.api.worker_auth import verify_worker_token

router = APIRouter(prefix="/workers", tags=["Worker管理"])


def _worker_out(w: ScanWorker) -> WorkerOut:
    return WorkerOut.model_validate(w)


@router.post("/register", response_model=WorkerRegisterResponse)
def register_worker(
    body: WorkerRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
    _token: str = Depends(verify_worker_token),
):
    """Worker 注册（幂等：同名 Worker 重新注册时更新记录）。"""
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now()

    existing = db.query(ScanWorker).filter(ScanWorker.worker_name == body.worker_name).first()
    if existing:
        existing.token_hash = token_hash
        existing.ip_address = request.client.host if request.client else None
        existing.status = "online"
        existing.capabilities = body.capabilities
        existing.version = body.version or ""
        existing.last_heartbeat = now
        db.commit()
        return WorkerRegisterResponse(
            worker_id=existing.id,
            worker_name=existing.worker_name,
            message="Worker 已重新注册",
        )

    worker = ScanWorker(
        worker_name=body.worker_name,
        token_hash=token_hash,
        ip_address=request.client.host if request.client else None,
        capabilities=body.capabilities,
        version=body.version or "",
        last_heartbeat=now,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return WorkerRegisterResponse(
        worker_id=worker.id,
        worker_name=worker.worker_name,
        message="Worker 注册成功",
    )


@router.post("/{worker_id}/heartbeat")
def worker_heartbeat(
    worker_id: int,
    body: WorkerHeartbeatRequest,
    db: Session = Depends(get_db),
    _token: str = Depends(verify_worker_token),
):
    """Worker 心跳上报，更新最后心跳时间和可选状态。"""
    worker = db.query(ScanWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker 不存在")
    worker.last_heartbeat = datetime.now()
    if body.current_tasks is not None:
        worker.current_tasks = body.current_tasks
    if body.status is not None:
        worker.status = body.status
    db.commit()
    return {"message": "心跳已接收", "worker_id": worker_id, "last_heartbeat": worker.last_heartbeat.isoformat()}


@router.post("/{worker_id}/deregister")
def deregister_worker(
    worker_id: int,
    db: Session = Depends(get_db),
    _token: str = Depends(verify_worker_token),
):
    """Worker 注销，标记为离线。"""
    worker = db.query(ScanWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker 不存在")
    worker.status = "offline"
    worker.current_tasks = 0
    db.commit()
    return {"message": "Worker 已注销", "worker_id": worker_id}


@router.get("")
def list_workers(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=128),
    status_filter: str = Query("", alias="status"),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """管理员查看所有 Worker 列表（分页）。"""
    q = db.query(ScanWorker)
    if search:
        q = q.filter(ScanWorker.worker_name.contains(search))
    if status_filter:
        q = q.filter(ScanWorker.status == status_filter)
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(ScanWorker.id).offset((page - 1) * size).limit(size).all()
    return {
        "items": [_worker_out(w) for w in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


@router.get("/{worker_id}", response_model=WorkerOut)
def get_worker(
    worker_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """管理员查看单个 Worker 详情。"""
    worker = db.query(ScanWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker 不存在")
    return _worker_out(worker)


@router.delete("/{worker_id}")
def delete_worker(
    worker_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """管理员删除 Worker 记录（用于清理已下线 Worker）。"""
    worker = db.query(ScanWorker).get(worker_id)
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker 不存在")
    db.delete(worker)
    db.commit()
    return {"message": "Worker 记录已删除"}
