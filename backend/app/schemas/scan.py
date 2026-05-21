from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ScanResultOut(BaseModel):
    id: int
    switch_id: int
    ip_address: str
    mac_address: str
    vlan_bd: Optional[int] = None
    vlan_type: str
    physical_port: str
    virtual_port: str
    switch_type: str
    created_at: datetime

    class Config:
        from_attributes = True


class RouteTableOut(BaseModel):
    id: int
    switch_id: int
    target_network: str
    subnet_mask: str
    cidr: str
    gateway: str
    interface_name: str
    route_type: str
    protocol: str
    created_at: datetime

    class Config:
        from_attributes = True


class ScanLogOut(BaseModel):
    id: int
    switch_id: Optional[int] = None
    status: str
    triggered_by: str
    hosts_found: int
    routes_found: int
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    size: int
    pages: int
