"""备份任务配置模型"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.database import Base


class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(128), nullable=False, comment="任务名称")
    enabled = Column(Boolean, default=True, comment="是否启用")

    # 备份模式：local / ftp
    mode = Column(String(16), nullable=False, default="local", comment="备份模式: local/ftp")
    local_path = Column(String(512), nullable=True, comment="本地备份目录路径")

    # FTP 配置
    ftp_host = Column(String(256), nullable=True, comment="FTP服务器地址")
    ftp_port = Column(Integer, nullable=True, default=21, comment="FTP端口")
    ftp_user = Column(String(128), nullable=True, comment="FTP用户名")
    ftp_password = Column(String(256), nullable=True, comment="FTP密码")
    ftp_remote_path = Column(String(512), nullable=True, comment="FTP远程目录")

    # 备份内容（逗号分隔：database,configs,images,uploads）
    backup_contents = Column(String(256), nullable=False, default="database,configs,images,uploads",
                             comment="备份内容: database,configs,images,uploads")

    # 调度配置（6 段 cron：秒 分 时 日 月 周）
    cron_expression = Column(String(64), nullable=False, default="0 2 * * *",
                             comment="Cron表达式(6段: 秒 分 时 日 月 周)")

    # 保留策略
    retention_days = Column(Integer, nullable=False, default=30, comment="保留天数(0=永久)")

    # 状态追踪
    last_run_at = Column(DateTime, nullable=True, comment="上次执行时间")
    last_status = Column(String(16), nullable=True, comment="上次执行状态: success/failed")

    # 审计
    created_by = Column(Integer, nullable=True, comment="创建人ID")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
