import enum
from sqlalchemy import Column, Integer, String, Enum, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import relationship
from app.database import Base


class ChangeType(str, enum.Enum):
    added = "added"
    deleted = "deleted"
    modified = "modified"


class SourceType(str, enum.Enum):
    switch = "switch"
    vcenter = "vcenter"
    f5 = "f5"
    zdns = "zdns"
    qax = "qax"


class History(Base):
    __tablename__ = "history_records"
    __table_args__ = (
        Index("idx_hr_ip", "ip_address"),
        Index("idx_hr_mac", "mac_address"),
        Index("idx_hr_switch", "switch_id"),
        Index("idx_hr_scan_log", "scan_log_id"),
        Index("idx_hr_ip_mac", "ip_address", "mac_address"),
        Index("idx_hr_created", "created_at"),
        Index("idx_hr_change_type", "change_type"),
        Index("idx_hr_source", "source_type"),
        Index("idx_hr_dedup", "dedup_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    switch_id = Column(Integer, ForeignKey("switches.id", ondelete="SET NULL"), nullable=True)
    scan_log_id = Column(Integer, ForeignKey("scan_logs.id", ondelete="SET NULL"), nullable=True)
    change_type = Column(Enum(ChangeType), nullable=False)
    ip_address = Column(String(255), nullable=False, default="")
    mac_address = Column(String(17), nullable=False)

    # 旧字段（交换机专用，保持向后兼容）
    old_vlan_bd = Column(Integer, nullable=True)
    new_vlan_bd = Column(Integer, nullable=True)
    old_vlan_type = Column(String(16), default="")
    new_vlan_type = Column(String(16), default="")
    old_physical_port = Column(String(64), default="")
    new_physical_port = Column(String(64), default="")
    old_virtual_port = Column(String(64), default="")
    new_virtual_port = Column(String(64), default="")
    old_switch_type = Column(String(4), default="")
    new_switch_type = Column(String(4), default="")

    # 新字段 — 通用数据源支持
    source_type = Column(String(16), default="switch")
    source_id = Column(Integer, nullable=True)
    source_name = Column(String(255), default="")
    dedup_key = Column(String(512), default="")
    change_detail = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    switch = relationship("Switch", back_populates="history_records")
    scan_log = relationship("ScanLog")
