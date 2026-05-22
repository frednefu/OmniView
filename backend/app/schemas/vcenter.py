from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class VCenterCreate(BaseModel):
    name: str
    host: str
    username: str
    password: str
    port: int = 443
    scan_interval: int = 3600


class VCenterUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    port: Optional[int] = None
    scan_interval: Optional[int] = None
    is_active: Optional[bool] = None


class VCenterOut(BaseModel):
    id: int
    name: str
    host: str
    username: str
    port: int
    scan_interval: int
    is_active: bool
    last_scan_status: Optional[str] = None
    last_scan_time: Optional[datetime] = None
    last_vm_count: int = 0
    last_scan_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VCenterTestRequest(BaseModel):
    host: str
    username: str
    password: str
    port: int = 443


class VCenterTestResponse(BaseModel):
    ok: bool
    message: str


class VMInventoryOut(BaseModel):
    id: int
    vcenter_id: int
    vcenter_name: str = ""
    vcenter_host: str = ""
    datacenter: str
    cluster: str
    esxi_host: str
    resource_pool: str
    vm_folder: str
    vm_name: str
    power_state: str
    ip_address: str
    mac_address: str
    network_name: str
    vlan_id: str
    os_name: str
    cpu_count: Optional[int] = None
    memory_gb: Optional[float] = None
    remark: str
    created_at: datetime

    class Config:
        from_attributes = True
