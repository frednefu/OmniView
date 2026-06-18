"""操作日志模型 — 记录 API 调用审计信息。"""
from sqlalchemy import Column, Integer, String, DateTime, Text, func
from app.database import Base


class OperationLog(Base):
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, comment="操作用户ID")
    username = Column(String(128), nullable=True, comment="操作用户名")
    ip_address = Column(String(64), nullable=True, comment="客户端IP")
    method = Column(String(8), nullable=True, comment="HTTP方法")
    api_path = Column(String(256), nullable=True, index=True, comment="API路径")
    status_code = Column(Integer, nullable=True, comment="HTTP状态码")
    duration_ms = Column(Integer, nullable=True, comment="请求耗时(毫秒)")
    detail = Column(String(512), nullable=True, comment="操作描述/错误信息")
    user_agent = Column(String(512), nullable=True, comment="浏览器UA")
    created_at = Column(DateTime, server_default=func.now(), index=True, comment="操作时间")
