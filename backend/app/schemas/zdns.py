from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ── ZDNS 设备 CRUD ──

class ZDNSDeviceCreate(BaseModel):
    name: str
    host: str
    username: str
    password: str
    port: int = 20120
    scan_interval: int = 86400


class ZDNSDeviceUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    port: Optional[int] = None
    scan_interval: Optional[int] = None
    is_active: Optional[bool] = None


class ZDNSDeviceOut(BaseModel):
    id: int
    name: str
    host: str
    username: str
    port: int
    scan_interval: int
    is_active: bool
    last_scan_status: Optional[str] = None
    last_scan_time: Optional[datetime] = None
    last_scan_duration: Optional[float] = None
    last_record_count: int = 0
    last_zone_count: int = 0
    last_scan_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── 连接测试 ──

class ZDNSTestRequest(BaseModel):
    host: str
    username: str
    password: str
    port: int = 20120


class ZDNSTestResponse(BaseModel):
    ok: bool
    message: str


# ── 扫描数据输出 ──

class ZDNSRecordOut(BaseModel):
    id: int
    zdns_device_id: int
    record_id: str = ""
    name: str = ""
    full_domain: str = ""
    record_type: str = ""
    ttl: Optional[int] = None
    rdata: str = ""
    view_name: str = ""
    zone_name: str = ""
    is_enabled: str = ""
    strategy: str = ""
    expire_time: str = ""
    expire_style: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


class ZDNSDomainMapOut(BaseModel):
    id: int
    zdns_device_id: int
    domain_name: str = ""
    record_type: str = ""
    ip_address: str = ""
    ip_category: str = ""
    network_type: str = ""
    ttl: Optional[int] = None
    view_name: str = ""
    zone_name: str = ""
    is_enabled: str = ""
    created_at: datetime

    class Config:
        from_attributes = True
