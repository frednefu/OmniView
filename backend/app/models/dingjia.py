"""鼎甲备份系统模型。"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, func
from app.database import Base


class DingJiaDevice(Base):
    __tablename__ = "dingjia_devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, comment="设备名称")
    host = Column(String(255), nullable=False, comment="服务器 IP")
    api_key = Column(String(256), nullable=False, comment="API Key")
    access_key = Column(String(256), nullable=False, comment="Access Key")
    port = Column(Integer, default=80, comment="端口")
    scan_interval = Column(Integer, default=86400, comment="扫描间隔(秒)")
    is_active = Column(Boolean, default=True, comment="是否启用")
    last_scan_status = Column(String(16), nullable=True, comment="扫描状态")
    last_scan_time = Column(DateTime, nullable=True, comment="扫描时间")
    last_scan_duration = Column(Integer, nullable=True, comment="扫描耗时(秒)")
    last_scan_error = Column(Text, nullable=True, comment="扫描错误")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DingJiaBackupRecord(Base):
    __tablename__ = "dingjia_backup_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer, nullable=False, index=True, comment="设备 ID")
    job_id = Column(String(64), nullable=False, comment="作业 UUID")
    job_name = Column(String(255), nullable=False, comment="作业名称")
    host_id = Column(String(64), nullable=True, comment="主机 ID")
    host_name = Column(String(255), nullable=True, comment="主机名称")
    host_ip = Column(String(255), nullable=True, comment="主机 IP")
    vm_uuid = Column(String(128), nullable=True, comment="VM UUID")
    vm_name = Column(String(255), nullable=True, index=True, comment="VM 名称")
    backup_type = Column(String(32), nullable=True, comment="backup/restore")
    backup_subtype = Column(String(32), nullable=True, comment="full/incremental")
    agent = Column(String(128), nullable=True, comment="代理类型")
    state = Column(String(32), nullable=True, comment="作业状态")
    last_run_result = Column(String(32), nullable=True, comment="最近结果")
    last_run_time = Column(DateTime, nullable=True, comment="最近开始时间")
    last_completed_time = Column(DateTime, nullable=True, comment="最近结束时间")
    next_run_time = Column(DateTime, nullable=True, comment="下次运行时间（保留兼容）")
    duration_seconds = Column(Integer, nullable=True, comment="持续时间(秒)")
    backup_versions = Column(Integer, default=1, comment="备份版本数(可恢复的还原点)")
    backup_versions_detail = Column(Text, nullable=True, comment="备份版本详情(JSON数组: [{time,type,size}])")
    vm_size_gb = Column(Float, nullable=True, comment="VM 大小(GB)")
    scanned_at = Column(DateTime, server_default=func.now(), comment="扫描时间")
