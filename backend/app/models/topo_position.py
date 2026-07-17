"""系统监控 — 拓扑节点位置记忆"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func
from app.database import Base


class TopoPosition(Base):
    __tablename__ = "topo_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    system_id = Column(Integer, nullable=False, index=True, comment="信息系统ID")
    node_name = Column(String(512), nullable=False, comment="节点唯一名称")
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
