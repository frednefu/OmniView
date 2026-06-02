"""系统状态 API。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.api.deps import require_admin
from app.services.scheduler_service import get_scheduler_status, update_job_interval

router = APIRouter(prefix="/system", tags=["系统"])


class UpdateIntervalBody(BaseModel):
    job_id: str
    interval_secs: int


@router.get("/scheduler-status")
def scheduler_status(_=Depends(require_admin)):
    """返回 APScheduler 运行状态和任务列表。"""
    return get_scheduler_status()


@router.put("/scheduler-interval")
def set_job_interval(body: UpdateIntervalBody, _=Depends(require_admin)):
    """修改定时任务的运行周期。"""
    if body.interval_secs < 10:
        raise HTTPException(status_code=400, detail="周期不能小于10秒")
    ok = update_job_interval(body.job_id, body.interval_secs)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"message": f"任务 {body.job_id} 周期已修改为 {body.interval_secs} 秒"}
