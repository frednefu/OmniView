"""地址段订阅 — 用户可订阅他人管理的地址段。"""
from sqlalchemy import Column, Integer, Boolean, DateTime, func, UniqueConstraint
from app.database import Base


class SubnetSubscription(Base):
    __tablename__ = "subnet_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subscriber_id = Column(Integer, nullable=False, index=True, comment="订阅人ID")
    target_user_id = Column(Integer, nullable=False, index=True, comment="被订阅人ID")
    show_in_dashboard = Column(Boolean, default=True, nullable=False, comment="是否在仪表盘中展示")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("subscriber_id", "target_user_id", name="uq_sub_target"),
    )
