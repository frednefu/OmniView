from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── F5 设备 CRUD ──

class F5DeviceCreate(BaseModel):
    name: str
    host: str
    username: str
    password: str
    port: int = 443
    scan_interval: int = 86400


class F5DeviceUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    port: Optional[int] = None
    scan_interval: Optional[int] = None
    is_active: Optional[bool] = None


class F5DeviceOut(BaseModel):
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
    last_vs_count: int = 0
    last_pool_count: int = 0
    last_scan_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── 连接测试 ──

class F5TestRequest(BaseModel):
    host: str
    username: str
    password: str
    port: int = 443


class F5TestResponse(BaseModel):
    ok: bool
    message: str


# ── 扫描数据输出 ──

class F5VirtualServerOut(BaseModel):
    id: int
    f5_device_id: int
    name: str
    destination: str = ""
    vs_ip: str = ""
    vs_port: Optional[int] = None
    pool_name: str = ""
    rules: str = "[]"
    raw_config: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class F5PoolMemberOut(BaseModel):
    id: int
    f5_device_id: int
    pool_name: str = ""
    member_name: str = ""
    member_ip: str = ""
    member_port: Optional[int] = None
    member_state: str = ""
    raw_config: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class F5RuleOut(BaseModel):
    id: int
    f5_device_id: int
    rule_name: str = ""
    rule_content: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class F5ApplicationMapOut(BaseModel):
    id: int
    f5_device_id: int
    domain_name: str = ""
    vs_name: str = ""
    vs_ip: str = ""
    vs_port: Optional[int] = None
    pool_name: str = ""
    rule_name: str = ""
    member_ip: str = ""
    member_port: Optional[int] = None
    member_state: str = ""
    source: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


# ── 搜索结果（全局应用映射） ──

class F5ApplicationSearchResult(BaseModel):
    """用于跨设备搜索应用映射"""
    items: list
    total: int
