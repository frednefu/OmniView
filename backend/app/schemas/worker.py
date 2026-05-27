"""Worker 注册/心跳/注销请求与响应模式。"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class WorkerRegisterRequest(BaseModel):
    worker_name: str
    capabilities: Optional[dict] = None
    version: Optional[str] = None


class WorkerRegisterResponse(BaseModel):
    worker_id: int
    worker_name: str
    message: str


class WorkerHeartbeatRequest(BaseModel):
    current_tasks: Optional[int] = None
    status: Optional[str] = None


class WorkerDeregisterRequest(BaseModel):
    reason: Optional[str] = None


class WorkerOut(BaseModel):
    id: int
    worker_name: str
    ip_address: Optional[str] = None
    status: str
    capabilities: Optional[dict] = None
    current_tasks: int
    max_tasks: int
    version: str
    last_heartbeat: Optional[datetime] = None
    registered_at: datetime

    class Config:
        from_attributes = True
