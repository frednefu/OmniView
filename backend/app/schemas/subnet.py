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


# ── 多数据源统计模型 ──

class VCenterResourceStat(BaseModel):
    vcenter_name: str
    cpu_cores: int
    memory_gb: float


class VCenterStats(BaseModel):
    vcenter_count: int = 0
    vm_total: int = 0
    vm_powered_on: int = 0
    vm_powered_off: int = 0
    total_cpu_cores: int = 0
    total_memory_gb: float = 0.0
    per_vcenter: List[VCenterResourceStat] = []


class F5Stats(BaseModel):
    device_count: int = 0
    vs_count: int = 0
    pool_count: int = 0
    rule_count: int = 0
    app_map_count: int = 0
    pool_member_up: int = 0
    pool_member_down: int = 0


class ZDNSRecordTypeStat(BaseModel):
    record_type: str
    count: int


class ZDNSStats(BaseModel):
    device_count: int = 0
    record_count: int = 0
    domain_map_count: int = 0
    ipv4_count: int = 0
    ipv6_count: int = 0
    internal_count: int = 0
    external_count: int = 0
    record_types: List[ZDNSRecordTypeStat] = []


class SourceScanStat(BaseModel):
    source_type: str
    source_label: str
    count: int


class DashboardStats(BaseModel):
    switch_count: int = 0
    total_ips: int = 0
    total_macs: int = 0
    subnet_count: int = 0
    vcenter: VCenterStats = VCenterStats()
    f5: F5Stats = F5Stats()
    zdns: ZDNSStats = ZDNSStats()
    scan_by_source: List[SourceScanStat] = []
    last_scan_total: int = 0
    last_scan_success: int = 0
    last_scan_failed: int = 0


# ── 子网占用 IP ──

class SubnetOccupiedIp(BaseModel):
    ip: str
    mac: str
    switch_name: str
    vlan: str


class SubnetOccupiedResponse(BaseModel):
    subnet_cidr: str
    subnet_name: str
    occupied: List[SubnetOccupiedIp]
    total: int


class AvailableIpResponse(BaseModel):
    subnet_cidr: str
    available_ips: List[str]
    total_free: int
