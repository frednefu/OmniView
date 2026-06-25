from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.database import Base


class Subnet(Base):
    __tablename__ = "subnets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subnet_cidr = Column(String(255), nullable=False)  # 唯一性由 (cidr + created_by) 应用层保证
    name = Column(String(128), nullable=False)
    gateway = Column(String(255), default="")
    vlan_id = Column(Integer, nullable=True)
    description = Column(String(256), default="")
    is_managed = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, nullable=True, comment="创建人ID")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
