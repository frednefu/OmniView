"""信息资产管理 — 独立于 vCenter 扫描数据的管理字段。"""
from sqlalchemy import Column, Integer, String, DateTime, func
from app.database import Base


class AssetInventory(Base):
    __tablename__ = "asset_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vm_name = Column(String(255), unique=True, nullable=False, index=True, comment="VM 名称")
    department_id = Column(Integer, nullable=True, comment="所属部门")
    owner_user_id = Column(Integer, nullable=True, comment="负责人")
    claim_status = Column(String(16), default="unlinked", comment="分组状态")
    claimed_by = Column(Integer, nullable=True, comment="认领人")
    claimed_at = Column(DateTime, nullable=True, comment="认领时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
