"""地址段仪表盘隐藏记录 — 用户可逐条控制订阅地址段的仪表盘展示。"""
from sqlalchemy import Column, Integer, UniqueConstraint
from app.database import Base


class SubnetHidden(Base):
    __tablename__ = "subnet_hidden"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True, comment="用户ID")
    subnet_id = Column(Integer, nullable=False, index=True, comment="地址段ID")

    __table_args__ = (
        UniqueConstraint("user_id", "subnet_id", name="uq_user_subnet_hidden"),
    )
