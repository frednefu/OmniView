"""域名管理物理表 — 独立于 ZDNS 扫描数据，同步资产时写入。"""
from sqlalchemy import Column, Integer, String, DateTime, func
from app.database import Base


class DomainInventory(Base):
    __tablename__ = "domain_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_name = Column(String(512), nullable=False, unique=True, index=True, comment="域名")
    record_type = Column(String(10), default="", comment="记录类型")
    ip_address = Column(String(255), default="", comment="IP地址")
    source = Column(String(32), default="ZDNS", comment="来源: ZDNS/F5")
    # 管理字段
    owner_user_id = Column(Integer, nullable=True, comment="认领人ID")
    department_id = Column(Integer, nullable=True, comment="所属部门ID")
    owner_name = Column(String(128), nullable=True, comment="管理员姓名")
    # 关联来源
    source_type = Column(String(16), nullable=True, comment="关联来源: vm/is/phys")
    vm_name = Column(String(255), nullable=True, comment="关联VM名称")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
