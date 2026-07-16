"""系统监控 — 信息系统与资产关联模型"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from app.database import Base


class SystemAssetLink(Base):
    __tablename__ = "system_asset_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    info_system_id = Column(Integer, ForeignKey("info_systems.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_type = Column(String(32), nullable=False, comment="域名/虚拟机/F5 VS/F5成员/备份/椒图")
    asset_key = Column(String(512), nullable=False, comment="资产唯一标识")
    asset_label = Column(String(64), nullable=True, comment="组件角色：前端/中间件/数据库/负载均衡/存储/安全/备份/其他")
    notes = Column(String(255), nullable=True, comment="备注")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
