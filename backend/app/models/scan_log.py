from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, func, Text
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class ScanStatus(str, enum.Enum):
    running = "running"
    success = "success"
    failed = "failed"


class TriggerType(str, enum.Enum):
    scheduled = "scheduled"
    manual = "manual"


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    switch_id = Column(Integer, ForeignKey("switches.id", ondelete="SET NULL"), nullable=True)
    status = Column(Enum(ScanStatus), nullable=False, default=ScanStatus.running)
    triggered_by = Column(Enum(TriggerType), nullable=False, default=TriggerType.manual)
    hosts_found = Column(Integer, default=0)
    routes_found = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    switch = relationship("Switch", back_populates="scan_logs")
