from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class SubnetCreate(BaseModel):
    subnet_cidr: str
    name: str
    gateway: str = ""
    vlan_id: Optional[int] = None
    description: str = ""
    is_managed: bool = True


class SubnetUpdate(BaseModel):
    name: Optional[str] = None
    gateway: Optional[str] = None
    vlan_id: Optional[int] = None
    description: Optional[str] = None
    is_managed: Optional[bool] = None


class SubnetOut(BaseModel):
    id: int
    subnet_cidr: str
    name: str
    gateway: str
    vlan_id: Optional[int] = None
    description: str
    is_managed: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubnetUtilization(BaseModel):
    subnet_id: int
    subnet_cidr: str
    name: str
    total_ips: int
    used_ips: int
    free_ips: int
    utilization_pct: float


class DashboardStats(BaseModel):
    switch_count: int
    total_ips: int
    total_macs: int
    subnet_count: int


class AvailableIpResponse(BaseModel):
    subnet_cidr: str
    available_ips: List[str]
    total_free: int
