"""备份任务 Pydantic Schema"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Backup Job ────────────────────────────────────────────

class BackupJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="任务名称")
    enabled: bool = Field(True, description="是否启用")
    mode: str = Field("local", description="备份模式: local/ftp")
    local_path: Optional[str] = Field(None, max_length=512, description="本地备份目录路径")
    ftp_host: Optional[str] = Field(None, max_length=256, description="FTP服务器地址")
    ftp_port: Optional[int] = Field(21, description="FTP端口")
    ftp_user: Optional[str] = Field(None, max_length=128, description="FTP用户名")
    ftp_password: Optional[str] = Field(None, max_length=256, description="FTP密码")
    ftp_remote_path: Optional[str] = Field(None, max_length=512, description="FTP远程目录")
    backup_contents: str = Field("database,configs,images,uploads", description="备份内容（逗号分隔）")
    cron_expression: str = Field("0 2 * * *", max_length=64, description="Cron表达式(6段: 秒 分 时 日 月 周)")
    retention_days: int = Field(30, ge=0, description="保留天数(0=永久)")


class BackupJobUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128, description="任务名称")
    enabled: Optional[bool] = Field(None, description="是否启用")
    mode: Optional[str] = Field(None, description="备份模式: local/ftp")
    local_path: Optional[str] = Field(None, max_length=512, description="本地备份目录路径")
    ftp_host: Optional[str] = Field(None, max_length=256, description="FTP服务器地址")
    ftp_port: Optional[int] = Field(None, description="FTP端口")
    ftp_user: Optional[str] = Field(None, max_length=128, description="FTP用户名")
    ftp_password: Optional[str] = Field(None, max_length=256, description="FTP密码")
    ftp_remote_path: Optional[str] = Field(None, max_length=512, description="FTP远程目录")
    backup_contents: Optional[str] = Field(None, description="备份内容（逗号分隔）")
    cron_expression: Optional[str] = Field(None, max_length=64, description="Cron表达式(6段: 秒 分 时 日 月 周)")
    retention_days: Optional[int] = Field(None, ge=0, description="保留天数(0=永久)")


class BackupJobOut(BaseModel):
    id: int
    name: str
    enabled: bool
    mode: str
    local_path: Optional[str] = None
    ftp_host: Optional[str] = None
    ftp_port: Optional[int] = None
    ftp_user: Optional[str] = None
    ftp_password: Optional[str] = None
    ftp_remote_path: Optional[str] = None
    backup_contents: str
    cron_expression: str
    retention_days: int
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Backup History ────────────────────────────────────────

class BackupHistoryOut(BaseModel):
    id: int
    job_id: Optional[int] = None
    job_name: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    storage_location: Optional[str] = None
    content_summary: Optional[str] = None
    error_message: Optional[str] = None
    log_output: Optional[str] = None
    verify_log: Optional[str] = None
    verified: bool = False
    verified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── FTP 测试 ──────────────────────────────────────────────

class FtpTestRequest(BaseModel):
    host: str = Field(..., max_length=256, description="FTP服务器地址")
    port: int = Field(21, description="FTP端口")
    user: str = Field(..., max_length=128, description="FTP用户名")
    password: str = Field(..., max_length=256, description="FTP密码")


class FtpTestResponse(BaseModel):
    success: bool
    message: str
