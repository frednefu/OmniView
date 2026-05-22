from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class SwitchCreate(BaseModel):
    name: str
    ip_address: str
    community: str
    mib_type: str = "standard"
    snmp_port: int = 161
    snmp_timeout: int = 3
    snmp_retries: int = 2
    scan_interval: int = 86400


class SwitchUpdate(BaseModel):
    name: Optional[str] = None
    community: Optional[str] = None
    mib_type: Optional[str] = None
    snmp_port: Optional[int] = None
    snmp_timeout: Optional[int] = None
    snmp_retries: Optional[int] = None
    scan_interval: Optional[int] = None
    is_active: Optional[bool] = None


class SwitchOut(BaseModel):
    id: int
    name: str
    ip_address: str
    community: str
    mib_type: str
    snmp_port: int
    snmp_timeout: int
    snmp_retries: int
    scan_interval: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_scan_status: Optional[str] = None
    last_hosts_found: int = 0
    last_routes_found: int = 0
    last_scan_time: Optional[datetime] = None
    last_scan_duration: Optional[float] = None

    class Config:
        from_attributes = True


class SwitchTestRequest(BaseModel):
    ip_address: str
    community: str
    snmp_port: int = 161


class SwitchTestResponse(BaseModel):
    ok: bool
    message: str


class SwitchImportRow(BaseModel):
    name: str
    ip_address: str
    community: str
    mib_type: str = "standard"
    snmp_port: int = 161
    scan_interval: int = 86400


class SwitchImportResult(BaseModel):
    created: int
    skipped: int
    errors: List[str]
