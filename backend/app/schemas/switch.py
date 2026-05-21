from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SwitchCreate(BaseModel):
    name: str
    ip_address: str
    community: str
    mib_type: str = "standard"
    snmp_port: int = 161
    snmp_timeout: int = 3
    snmp_retries: int = 2
    scan_interval: int = 3600


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

    class Config:
        from_attributes = True
