"""Worker 节点注册模型 — 追踪各 Worker 节点的在线状态和能力。"""
from sqlalchemy import Column, Integer, String, DateTime, func, JSON
from app.database import Base


class ScanWorker(Base):
    __tablename__ = "scan_workers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    worker_name = Column(String(128), unique=True, nullable=False)
    token_hash = Column(String(256), nullable=False)
    ip_address = Column(String(45), nullable=True)
    status = Column(String(16), nullable=False, default="online")
    capabilities = Column(JSON, nullable=True)
    current_tasks = Column(Integer, default=0)
    max_tasks = Column(Integer, default=4)
    version = Column(String(32), default="")
    last_heartbeat = Column(DateTime, nullable=True)
    registered_at = Column(DateTime, server_default=func.now(), nullable=False)
