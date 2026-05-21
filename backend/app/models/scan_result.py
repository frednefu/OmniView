from sqlalchemy import Column, BigInteger, Integer, String, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.database import Base


class ScanResult(Base):
    __tablename__ = "scan_results"
    __table_args__ = (
        Index("idx_sr_mac", "mac_address"),
        Index("idx_sr_ip", "ip_address"),
        Index("idx_sr_switch", "switch_id"),
        Index("idx_sr_ip_mac", "ip_address", "mac_address"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    switch_id = Column(Integer, ForeignKey("switches.id", ondelete="CASCADE"), nullable=False)
    ip_address = Column(String(45), nullable=False, default="")
    mac_address = Column(String(17), nullable=False)
    vlan_bd = Column(Integer, nullable=True)
    vlan_type = Column(String(16), default="")
    physical_port = Column(String(64), default="")
    virtual_port = Column(String(64), default="")
    switch_type = Column(String(4), nullable=False)
    scan_log_id = Column(Integer, ForeignKey("scan_logs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    switch = relationship("Switch", back_populates="scan_results")
