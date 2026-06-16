"""外链填报模型。"""
import uuid
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, func
from app.database import Base


def _gen_token():
    return uuid.uuid4().hex + uuid.uuid4().hex  # 64位随机token


class SharedLink(Base):
    __tablename__ = "shared_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(64), unique=True, nullable=False, index=True, default=_gen_token,
                   comment="加密访问令牌")
    target_type = Column(String(32), nullable=False, comment="目标类型: supply_chain")
    target_id = Column(Integer, nullable=False, comment="目标记录ID")
    title = Column(String(256), nullable=True, comment="外链标题")
    password = Column(String(128), nullable=True, comment="访问密码(明文哈希)")
    expire_at = Column(DateTime, nullable=True, comment="失效时间")
    is_active = Column(Boolean, default=True, comment="是否启用")
    access_count = Column(Integer, default=0, comment="访问次数")
    created_by = Column(Integer, nullable=True, comment="创建人ID")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
