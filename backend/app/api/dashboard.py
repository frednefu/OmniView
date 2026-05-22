from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.switch import Switch
from app.models.scan_result import ScanResult
from app.models.subnet import Subnet
from app.models.vcenter import VCenter
from app.models.vm_inventory import VMInventory
from app.models.f5 import F5Device, F5VirtualServer, F5PoolMember, F5Rule, F5ApplicationMap
from app.models.zdns import ZDNSDevice, ZDNSRecord, ZDNSDomainMap
from app.models.scan_log import ScanLog, ScanStatus
from app.models.history import History
from app.schemas.subnet import (
    DashboardStats, VCenterStats, VCenterResourceStat, F5Stats, ZDNSStats, ZDNSRecordTypeStat,
    SourceScanStat, SubnetUtilization, AvailableIpResponse, SubnetOccupiedResponse, SubnetOccupiedIp,
)
from app.api.deps import get_current_user
from app.services.subnet_service import get_subnet_utilization, get_available_ips, get_occupied_ips

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # ── 交换机 ──
    switch_count = db.query(func.count(Switch.id)).filter(Switch.is_active == True).scalar() or 0
    total_ips = db.query(func.count(func.distinct(ScanResult.ip_address))).filter(
        ScanResult.ip_address != ""
    ).scalar() or 0
    total_macs = db.query(func.count(func.distinct(ScanResult.mac_address))).scalar() or 0

    # ── 子网 ──
    subnet_count = db.query(func.count(Subnet.id)).scalar() or 0

    # ── vCenter + VM ──
    vcenter_count = db.query(func.count(VCenter.id)).filter(VCenter.is_active == True).scalar() or 0
    vm_total = db.query(func.count(VMInventory.id)).scalar() or 0
    vm_powered_on = db.query(func.count(VMInventory.id)).filter(
        VMInventory.power_state == "poweredOn"
    ).scalar() or 0
    vm_powered_off = db.query(func.count(VMInventory.id)).filter(
        VMInventory.power_state == "poweredOff"
    ).scalar() or 0
    cpu_row = db.query(
        func.coalesce(func.sum(VMInventory.cpu_count), 0),
        func.coalesce(func.sum(VMInventory.memory_gb), 0.0),
    ).first()
    total_cpu_cores = cpu_row[0] or 0
    total_memory_gb = round(float(cpu_row[1] or 0.0), 1)

    # per-vCenter 资源
    vc_resource_rows = db.query(
        VCenter.name,
        func.coalesce(func.sum(VMInventory.cpu_count), 0),
        func.coalesce(func.sum(VMInventory.memory_gb), 0.0),
    ).join(VMInventory, VCenter.id == VMInventory.vcenter_id, isouter=True).group_by(
        VCenter.id, VCenter.name
    ).all()
    per_vcenter = [
        VCenterResourceStat(vcenter_name=r[0], cpu_cores=r[1] or 0, memory_gb=round(float(r[2] or 0), 1))
        for r in vc_resource_rows
    ]

    vcenter = VCenterStats(
        vcenter_count=vcenter_count,
        vm_total=vm_total,
        vm_powered_on=vm_powered_on,
        vm_powered_off=vm_powered_off,
        total_cpu_cores=total_cpu_cores,
        total_memory_gb=total_memory_gb,
        per_vcenter=per_vcenter,
    )

    # ── F5 ──
    f5_device_count = db.query(func.count(F5Device.id)).filter(F5Device.is_active == True).scalar() or 0
    vs_count = db.query(func.count(F5VirtualServer.id)).scalar() or 0
    pool_count = db.query(func.count(func.distinct(F5PoolMember.pool_name))).scalar() or 0
    rule_count = db.query(func.count(F5Rule.id)).scalar() or 0
    app_map_count = db.query(func.count(F5ApplicationMap.id)).scalar() or 0
    pool_up = db.query(func.count(F5PoolMember.id)).filter(
        F5PoolMember.member_state.ilike("%up%")
    ).scalar() or 0
    pool_down = db.query(func.count(F5PoolMember.id)).filter(
        F5PoolMember.member_state.ilike("%down%")
    ).scalar() or 0

    f5 = F5Stats(
        device_count=f5_device_count,
        vs_count=vs_count,
        pool_count=pool_count,
        rule_count=rule_count,
        app_map_count=app_map_count,
        pool_member_up=pool_up,
        pool_member_down=pool_down,
    )

    # ── ZDNS ──
    zdns_device_count = db.query(func.count(ZDNSDevice.id)).filter(ZDNSDevice.is_active == True).scalar() or 0
    record_count = db.query(func.count(ZDNSRecord.id)).scalar() or 0
    domain_map_count = db.query(func.count(ZDNSDomainMap.id)).scalar() or 0
    ipv4_count = db.query(func.count(ZDNSDomainMap.id)).filter(
        ZDNSDomainMap.ip_category == "IPv4"
    ).scalar() or 0
    ipv6_count = db.query(func.count(ZDNSDomainMap.id)).filter(
        ZDNSDomainMap.ip_category == "IPv6"
    ).scalar() or 0
    internal_count = db.query(func.count(ZDNSDomainMap.id)).filter(
        ZDNSDomainMap.network_type == "内网"
    ).scalar() or 0
    external_count = db.query(func.count(ZDNSDomainMap.id)).filter(
        ZDNSDomainMap.network_type == "外网"
    ).scalar() or 0

    # ZDNS 记录类型分布
    type_rows = db.query(
        ZDNSRecord.record_type, func.count(ZDNSRecord.id)
    ).group_by(ZDNSRecord.record_type).order_by(func.count(ZDNSRecord.id).desc()).all()
    record_types = [ZDNSRecordTypeStat(record_type=r[0] or "其他", count=r[1]) for r in type_rows]

    zdns = ZDNSStats(
        device_count=zdns_device_count,
        record_count=record_count,
        domain_map_count=domain_map_count,
        ipv4_count=ipv4_count,
        ipv6_count=ipv6_count,
        internal_count=internal_count,
        external_count=external_count,
        record_types=record_types,
    )

    # ── 各数据源扫描次数 ──
    source_rows = db.query(
        ScanLog.source_type, func.count(ScanLog.id)
    ).group_by(ScanLog.source_type).all()
    source_labels = {"switch": "交换机", "vcenter": "vCenter", "f5": "F5", "zdns": "ZDNS"}
    scan_by_source = [
        SourceScanStat(source_type=row[0], source_label=source_labels.get(row[0], row[0]), count=row[1])
        for row in source_rows
    ]

    # ── 最近扫描成功率 ──
    last_scan_total = db.query(func.count(ScanLog.id)).scalar() or 0
    last_scan_success = db.query(func.count(ScanLog.id)).filter(
        ScanLog.status == ScanStatus.success
    ).scalar() or 0
    last_scan_failed = db.query(func.count(ScanLog.id)).filter(
        ScanLog.status == ScanStatus.failed
    ).scalar() or 0

    return DashboardStats(
        switch_count=switch_count,
        total_ips=total_ips,
        total_macs=total_macs,
        subnet_count=subnet_count,
        vcenter=vcenter,
        f5=f5,
        zdns=zdns,
        scan_by_source=scan_by_source,
        last_scan_total=last_scan_total,
        last_scan_success=last_scan_success,
        last_scan_failed=last_scan_failed,
    )


@router.get("/subnet-utilization", response_model=list[SubnetUtilization])
def subnet_utilization(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return [SubnetUtilization(**item) for item in get_subnet_utilization(db)]


@router.get("/available-ips", response_model=AvailableIpResponse)
def available_ips(
    subnet_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = get_available_ips(db, subnet_id, limit)
    return AvailableIpResponse(**result)


@router.get("/subnet-occupied-ips", response_model=SubnetOccupiedResponse)
def subnet_occupied_ips(
    subnet_id: int = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = get_occupied_ips(db, subnet_id, page, size)
    return SubnetOccupiedResponse(**result)
