"""系统状态 API。"""
from fastapi import APIRouter, Depends
from app.api.deps import require_admin
from app.services.scheduler_service import get_scheduler_status

router = APIRouter(prefix="/system", tags=["系统"])


@router.get("/scheduler-status")
def scheduler_status(_=Depends(require_admin)):
    """返回 APScheduler 运行状态和任务列表。"""
    return get_scheduler_status()
