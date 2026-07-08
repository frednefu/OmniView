"""备份执行历史模型"""
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Text, Boolean, func
from app.database import Base


class BackupHistory(Base):
    __tablename__ = "backup_history"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    job_id = Column(Integer, nullable=True, index=True, comment="关联的备份任务ID（可空，任务删除后历史保留）")
    job_name = Column(String(128), nullable=True, comment="备份任务名称（执行时快照）")

    # 执行状态
    status = Column(String(16), nullable=False, default="running", comment="状态: running/success/failed")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    duration_seconds = Column(Integer, nullable=True, comment="执行耗时(秒)")

    # 备份文件信息
    file_path = Column(String(512), nullable=True, comment="备份文件路径")
    file_name = Column(String(256), nullable=True, comment="备份文件名")
    file_size = Column(BigInteger, nullable=True, comment="文件大小(字节)")
    storage_location = Column(String(32), nullable=True, comment="存储位置: local/ftp")

    # 内容摘要
    content_summary = Column(String(256), nullable=True, comment="备份内容摘要（如：数据库,配置文件）")
    error_message = Column(Text, nullable=True, comment="错误信息")
    log_output = Column(Text, nullable=True, comment="备份过程日志输出")
    verify_log = Column(Text, nullable=True, comment="验证过程日志输出")

    # 验证
    verified = Column(Boolean, default=False, comment="是否已验证")
    verified_at = Column(DateTime, nullable=True, comment="验证时间")

    # 审计
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
