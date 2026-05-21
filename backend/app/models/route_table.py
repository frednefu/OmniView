from sqlalchemy import Column, BigInteger, Integer, String, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.database import Base


class RouteTable(Base):
    __tablename__ = "route_tables"
    __table_args__ = (
        Index("idx_rt_cidr", "cidr"),
        Index("idx_rt_switch", "switch_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    switch_id = Column(Integer, ForeignKey("switches.id", ondelete="CASCADE"), nullable=False)
    target_network = Column(String(45), nullable=False)
    subnet_mask = Column(String(45), nullable=False)
    cidr = Column(String(49), nullable=False)
    gateway = Column(String(45), default="")
    interface_name = Column(String(64), default="")
    route_type = Column(String(16), default="")
    protocol = Column(String(16), default="")
    scan_log_id = Column(Integer, ForeignKey("scan_logs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    switch = relationship("Switch", back_populates="route_tables")
