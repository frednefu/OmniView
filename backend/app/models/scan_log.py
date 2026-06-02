from sqlalchemy import Column, Integer, String, Enum, Float, DateTime, ForeignKey, func, Text
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class ScanStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"


class TriggerType(str, enum.Enum):
    scheduled = "scheduled"
    manual = "manual"


class StepStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    switch_id = Column(Integer, ForeignKey("switches.id", ondelete="SET NULL"), nullable=True)
    source_type = Column(String(16), nullable=False, default="switch")
    source_id = Column(Integer, nullable=True)
    source_name = Column(String(255), default="")
    status = Column(Enum(ScanStatus), nullable=False, default=ScanStatus.running)
    triggered_by = Column(Enum(TriggerType), nullable=False, default=TriggerType.manual)
    hosts_found = Column(Integer, default=0)
    routes_found = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Phase C: 扫描实时进度
    progress_pct = Column(Integer, default=0)
    current_step = Column(String(128), default="")
    log_output = Column(Text, nullable=True)  # 终端风格日志输出
    worker_name = Column(String(128), nullable=True)  # 执行此扫描的 Worker 名称

    switch = relationship("Switch", back_populates="scan_logs")
    steps = relationship("ScanStep", back_populates="scan_log", cascade="all, delete-orphan")


class ScanStep(Base):
    __tablename__ = "scan_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_log_id = Column(Integer, ForeignKey("scan_logs.id", ondelete="CASCADE"), nullable=False)
    step_order = Column(Integer, nullable=False)
    step_name = Column(String(128), nullable=False)
    status = Column(Enum(StepStatus), nullable=False, default=StepStatus.pending)
    items_total = Column(Integer, default=0)
    items_processed = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    scan_log = relationship("ScanLog", back_populates="steps")
