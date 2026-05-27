import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.models.switch import Switch
from app.models.scan_result import ScanResult
from app.models.subnet import Subnet
from app.models.vcenter import VCenter
from app.models.vm_inventory import VMInventory
from app.models.esxi_host import EsxiHost
from app.models.datastore import Datastore
from app.models.f5 import F5Device, F5VirtualServer, F5PoolMember, F5Rule, F5ApplicationMap
from app.models.zdns import ZDNSDevice, ZDNSRecord, ZDNSDomainMap
from app.models.qax import QianXinDevice, QianXinServer
from app.models.scan_log import ScanLog, ScanStatus
from app.models.history import History
from app.schemas.subnet import (
    DashboardStats, AssetDashboardStats, VCenterStats, VCenterResourceStat,
    F5Stats, ZDNSStats, ZDNSRecordTypeStat, QAXStats,
    SourceScanStat, DistributionItem, DatastoreTypeStat,
    SubnetUtilization, AvailableIpResponse,
    SubnetOccupiedResponse, SubnetOccupiedIp,
    AssetDomainItem, AssetServiceItem, AssetDetailResponse,
)
from app.api.deps import get_current_user
from app.services.subnet_service import get_subnet_utilization, get_available_ips, get_occupied_ips
from app.services.cache_service import get_json, set_json

_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

# ── 辅助函数：OS 归并 & 分桶 ──

def _normalize_qax_os(rows) -> list:
    """椒图 OS 归并：提取主版本/年份，合并相近版本"""
    buckets: dict[str, int] = {}
    for os_name, cnt in rows:
        if not os_name:
            continue
        label = os_name.strip()
        # CentOS: 提取主版本 → "CentOS 7"（兼容 "CentOS Linux 7 (Core)" / "CentOS release 6.3 (Final)"）
        m = re.match(r'CentOS\s+(?:Linux\s+|release\s+)?(\d+)', label)
        if m:
            label = f'CentOS {m.group(1)}'
        # Windows Server: 提取年份 → "Windows Server 2016"
        elif label.startswith('Microsoft Windows Server'):
            m = re.match(r'Microsoft Windows Server (\d{4})', label)
            if m:
                label = f'Windows Server {m.group(1)}'
        # openEuler: 保留主版本
        elif label.startswith('openEuler'):
            m = re.match(r'openEuler (\d+\.\d+)', label)
            if m:
                label = f'openEuler {m.group(1)}'
        # Ubuntu: 保留版本号
        elif label.startswith('Ubuntu'):
            m = re.match(r'Ubuntu (\d+\.\d+)', label)
            if m:
                label = f'Ubuntu {m.group(1)}'
        buckets[label] = buckets.get(label, 0) + cnt
    sorted_items = sorted(buckets.items(), key=lambda x: x[1], reverse=True)
    return [DistributionItem(label=k, count=v) for k, v in sorted_items]


def _normalize_vm_os(rows) -> list:
    """vCenter VM OS 归并：提取主版本/年份，合并相近版本"""
    buckets: dict[str, int] = {}
    for os_name, cnt in rows:
        if not os_name:
            continue
        label = os_name.strip()
        # Windows: "Microsoft Windows Server 2012 (64-bit)" / "Microsoft Windows Server 2016 or later (64-bit)"
        if 'Windows' in label:
            m = re.match(r'Microsoft Windows Server (\d{4})', label)
            if m:
                label = f'Windows Server {m.group(1)}'
            elif 'Windows 10' in label:
                label = 'Windows 10'
            elif 'Windows 7' in label:
                label = 'Windows 7'
            else:
                label = label.replace('Microsoft ', '')
        # CentOS: "CentOS 7 (64-bit)" / "CentOS 4/5/6/7 (64-bit)" / "CentOS 4/5/6 (64-bit)"
        elif 'CentOS' in label:
            m = re.match(r'CentOS (\d+(?:/\d+)*)', label)
            if m:
                vers = m.group(1).split('/')
                if len(vers) == 1:
                    label = f'CentOS {vers[0]}'
                else:
                    label = f'CentOS {vers[0]}-{vers[-1]}'
        # RHEL / Red Hat: "Red Hat Enterprise Linux 7 (64-bit)"
        elif 'Red Hat' in label:
            m = re.search(r'Red Hat Enterprise Linux (\d+)', label)
            if m:
                label = f'RHEL {m.group(1)}'
        # Ubuntu: "Ubuntu Linux (64-bit)"
        elif 'Ubuntu' in label:
            m = re.search(r'Ubuntu\s+(?:Linux\s+)?(\d+\.\d+)', label)
            if m:
                label = f'Ubuntu {m.group(1)}'
            else:
                label = 'Ubuntu Linux'
        # Debian: "Debian GNU/Linux 10 (64-bit)"
        elif 'Debian' in label:
            m = re.search(r'Debian GNU/Linux (\d+)', label)
            if m:
                label = f'Debian {m.group(1)}'
        # Oracle Linux: "Oracle Linux 7 (64-bit)" / "Oracle Linux 4/5/6/7 (64-bit)"
        elif 'Oracle Linux' in label:
            m = re.match(r'Oracle Linux (\d+(?:/\d+)*)', label)
            if m:
                vers = m.group(1).split('/')
                if len(vers) == 1:
                    label = f'Oracle Linux {vers[0]}'
                else:
                    label = f'Oracle Linux {vers[0]}-{vers[-1]}'
        # SUSE / SLES: "SUSE Linux Enterprise 11 (64-bit)"
        elif 'SUSE' in label:
            m = re.search(r'SUSE\s+(?:Linux\s+)?(?:Enterprise\s+)?(\d+)', label)
            if m:
                label = f'SLES {m.group(1)}'
        # Other 3.x / Other 2.6.x 合并
        elif label.startswith('Other 3.x'):
            label = 'Other Linux 3.x'
        elif label.startswith('Other 2.6.x'):
            label = 'Other Linux 2.6.x'
        elif label.startswith('Other Linux'):
            label = 'Other Linux'
        elif label.startswith('Other '):
            label = 'Other'
        # 去掉常见的后缀
        label = label.replace(' (64-bit)', '').replace(' (32-bit)', '').replace(' or later', '')
        buckets[label] = buckets.get(label, 0) + cnt
    sorted_items = sorted(buckets.items(), key=lambda x: x[1], reverse=True)
    return [DistributionItem(label=k, count=v) for k, v in sorted_items]


def _bucket_cpu_cores(values: list) -> list:
    """CPU 核数分桶：1-2, 3-4, 5-8, 9-16, 17+"""
    buckets = {"1-2核": 0, "3-4核": 0, "5-8核": 0, "9-16核": 0, "17核以上": 0}
    for v in values:
        if v is None:
            continue
        if v <= 2:
            buckets["1-2核"] += 1
        elif v <= 4:
            buckets["3-4核"] += 1
        elif v <= 8:
            buckets["5-8核"] += 1
        elif v <= 16:
            buckets["9-16核"] += 1
        else:
            buckets["17核以上"] += 1
    return [DistributionItem(label=k, count=v) for k, v in buckets.items() if v > 0]


def _bucket_memory(values: list) -> list:
    """内存容量分桶：0-2GB, 2-4GB, 4-8GB, 8-16GB, 16-32GB, 32-64GB, 64GB+"""
    buckets = {"0-2GB": 0, "2-4GB": 0, "4-8GB": 0, "8-16GB": 0, "16-32GB": 0, "32-64GB": 0, "64GB以上": 0}
    for v in values:
        if v is None:
            continue
        if v < 2:
            buckets["0-2GB"] += 1
        elif v < 4:
            buckets["2-4GB"] += 1
        elif v < 8:
            buckets["4-8GB"] += 1
        elif v < 16:
            buckets["8-16GB"] += 1
        elif v < 32:
            buckets["16-32GB"] += 1
        elif v < 64:
            buckets["32-64GB"] += 1
        else:
            buckets["64GB以上"] += 1
    return [DistributionItem(label=k, count=v) for k, v in buckets.items() if v > 0]


def _normalize_cpu_types(rows) -> list:
    """ESXi CPU 型号归并：去除冗余后缀，合并同一系列。"""
    buckets: dict[str, int] = {}
    for cpu_model, cnt in rows:
        if not cpu_model:
            continue
        label = cpu_model.strip()
        label = re.sub(r'\s*(CPU|Processor)\s*$', '', label, flags=re.IGNORECASE)
        label = re.sub(r'\s*@\s*\d+\.?\d*GHz.*$', '', label)
        label = re.sub(r'\s+\d+-\w+$', '', label)
        if 'Intel' in label or 'Xeon' in label:
            label = label.replace('Intel(R) ', 'Intel ').replace('(R)', '')
            label = re.sub(r'Intel\s+Xeon\s+CPU\s+', 'Intel Xeon ', label)
            label = re.sub(r'(\d)\d{2,}(?:\s*(v\d|@.*)?$)', r'\1xx', label)
        elif 'AMD' in label or 'EPYC' in label:
            label = label.replace('(R)', '').replace('(tm)', '').replace('(TM)', '')
            label = re.sub(r'(\d)\d{2,}P?\s*.*$', r'\1xx', label)
        buckets[label] = buckets.get(label, 0) + cnt
    sorted_items = sorted(buckets.items(), key=lambda x: x[1], reverse=True)
    return [DistributionItem(label=k, count=v) for k, v in sorted_items]


router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


DASHBOARD_STATS_TTL = 30  # 仪表盘统计缓存 30 秒


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # Redis 缓存命中直接返回
    cached = get_json("dashboard:stats")
    if cached is not None:
        return DashboardStats(**cached)

    # ── 交换机 ──
    switch_count = db.query(func.count(Switch.id)).filter(Switch.is_active == True).scalar() or 0
    total_ips = db.query(func.count(func.distinct(ScanResult.ip_address))).filter(
        ScanResult.ip_address != ""
    ).scalar() or 0
    total_macs = db.query(func.count(func.distinct(ScanResult.mac_address))).filter(
        ScanResult.mac_address != "", ScanResult.mac_address.isnot(None)
    ).scalar() or 0

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

    # vCenter VM OS 分布（GROUP BY os_name，过滤空值，Python 层归并）
    vm_os_rows = db.query(
        VMInventory.os_name, func.count(VMInventory.id)
    ).filter(VMInventory.os_name != "").group_by(VMInventory.os_name).order_by(
        func.count(VMInventory.id).desc()
    ).all()
    vcenter_os_dist = _normalize_vm_os(vm_os_rows)

    # CPU 核数分桶
    cpu_values = db.query(VMInventory.cpu_count).filter(
        VMInventory.cpu_count.isnot(None)
    ).all()
    cpu_cores_dist = _bucket_cpu_cores([r[0] for r in cpu_values])

    # 内存分桶
    mem_values = db.query(VMInventory.memory_gb).filter(
        VMInventory.memory_gb.isnot(None)
    ).all()
    memory_dist = _bucket_memory([r[0] for r in mem_values])

    # ESXi CPU 类型分布
    cpu_type_rows = db.query(
        EsxiHost.processor_type, func.count(EsxiHost.id)
    ).filter(EsxiHost.processor_type != "").group_by(EsxiHost.processor_type).order_by(
        func.count(EsxiHost.id).desc()
    ).all()
    esxi_cpu_types = _normalize_cpu_types(cpu_type_rows)

    # Datastore 汇总
    ds_summary = db.query(
        func.coalesce(func.sum(Datastore.capacity_gb), 0.0),
        func.coalesce(func.sum(Datastore.free_gb), 0.0),
    ).first()
    ds_total_capacity = round(float(ds_summary[0] or 0.0), 1)
    ds_total_free = round(float(ds_summary[1] or 0.0), 1)

    # Datastore 按存储类型分组
    ds_type_rows = db.query(
        Datastore.storage_type,
        func.count(Datastore.id),
        func.coalesce(func.sum(Datastore.capacity_gb), 0.0),
        func.coalesce(func.sum(Datastore.free_gb), 0.0),
    ).filter(Datastore.storage_type != "").group_by(Datastore.storage_type).all()
    datastore_by_type = [
        DatastoreTypeStat(
            storage_type=row[0],
            count=row[1],
            capacity_gb=round(float(row[2] or 0.0), 1),
            free_gb=round(float(row[3] or 0.0), 1),
        )
        for row in ds_type_rows
    ]

    vcenter = VCenterStats(
        vcenter_count=vcenter_count,
        vm_total=vm_total,
        vm_powered_on=vm_powered_on,
        vm_powered_off=vm_powered_off,
        total_cpu_cores=total_cpu_cores,
        total_memory_gb=total_memory_gb,
        per_vcenter=per_vcenter,
        os_distribution=vcenter_os_dist,
        cpu_cores_distribution=cpu_cores_dist,
        memory_distribution=memory_dist,
        esxi_cpu_types=esxi_cpu_types,
        datastore_total_capacity_gb=ds_total_capacity,
        datastore_total_free_gb=ds_total_free,
        datastore_by_type=datastore_by_type,
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

    # ── 椒图（QAX） ──
    qax_device_count = db.query(func.count(QianXinDevice.id)).filter(
        QianXinDevice.enabled == True
    ).scalar() or 0
    qax_server_count = db.query(func.count(QianXinServer.id)).scalar() or 0
    qax_os_rows = db.query(
        QianXinServer.operation_system, func.count(QianXinServer.id)
    ).group_by(QianXinServer.operation_system).order_by(
        func.count(QianXinServer.id).desc()
    ).all()
    qax_os_dist = _normalize_qax_os(qax_os_rows)

    qax = QAXStats(
        device_count=qax_device_count,
        server_count=qax_server_count,
        os_distribution=qax_os_dist,
    )

    # ── 各数据源扫描次数 ──
    source_rows = db.query(
        ScanLog.source_type, func.count(ScanLog.id)
    ).group_by(ScanLog.source_type).all()
    source_labels = {"switch": "交换机", "vcenter": "vCenter", "f5": "F5", "zdns": "ZDNS", "zdns_ip": "IP扫描", "qax": "椒图"}
    scan_by_source = [
        SourceScanStat(source_type=row[0], source_label=source_labels.get(row[0], row[0]), count=row[1])
        for row in source_rows
    ]

    # ── 资产画像 ──
    zdns_domain_set = set()
    for (d,) in db.query(ZDNSDomainMap.domain_name).filter(
        ZDNSDomainMap.domain_name != "",
        ZDNSDomainMap.domain_name.notlike("*%"),
        ~ZDNSDomainMap.domain_name.contains("in-addr.arpa"),
    ).distinct().all():
        zdns_domain_set.add(d)
    f5_domain_set = set()
    for (d,) in db.query(F5ApplicationMap.domain_name).filter(
        F5ApplicationMap.domain_name != "",
    ).distinct().all():
        f5_domain_set.add(d)
    # 排除 VS 伪域名（不含 "." 的名称，如 vs_202_118_223_70_443）
    real_f5 = {d for d in f5_domain_set if '.' in d}
    # 有效域名 = ZDNS + F5 真实域名（排除 VS 伪域名，与资产画像口径一致）
    valid_domains = zdns_domain_set | real_f5

    # 公网服务：只统计 real_f5 域名关联的 F5 VS (IP:port)
    pub_services = set()
    for am in db.query(F5ApplicationMap.domain_name, F5ApplicationMap.vs_ip, F5ApplicationMap.vs_port).filter(
        F5ApplicationMap.domain_name.in_(real_f5),
        F5ApplicationMap.vs_ip != "",
        F5ApplicationMap.vs_port.isnot(None),
    ).distinct().all():
        pub_services.add((am.vs_ip, str(am.vs_port)))

    # 内网服务：只统计 real_f5 域名关联的内网成员 (IP:port)
    int_services = set()
    for am in db.query(F5ApplicationMap.member_ip, F5ApplicationMap.member_port).filter(
        F5ApplicationMap.domain_name.in_(real_f5),
        F5ApplicationMap.member_ip != "",
        F5ApplicationMap.member_port.isnot(None),
    ).distinct().all():
        int_services.add((am.member_ip, str(am.member_port)))

    asset = AssetDashboardStats(
        域名总数=len(valid_domains),
        zdns域名=len(zdns_domain_set),
        f5域名=len(real_f5),
        公网服务=len(pub_services),
        内网服务=len(int_services),
    )

    # ── 最近扫描成功率 ──
    last_scan_total = db.query(func.count(ScanLog.id)).scalar() or 0
    last_scan_success = db.query(func.count(ScanLog.id)).filter(
        ScanLog.status == ScanStatus.success
    ).scalar() or 0
    last_scan_failed = db.query(func.count(ScanLog.id)).filter(
        ScanLog.status == ScanStatus.failed
    ).scalar() or 0

    result = DashboardStats(
        switch_count=switch_count,
        total_ips=total_ips,
        total_macs=total_macs,
        subnet_count=subnet_count,
        vcenter=vcenter,
        f5=f5,
        zdns=zdns,
        qax=qax,
        asset=asset,
        scan_by_source=scan_by_source,
        last_scan_total=last_scan_total,
        last_scan_success=last_scan_success,
        last_scan_failed=last_scan_failed,
    )
    set_json("dashboard:stats", result.model_dump(), ttl=DASHBOARD_STATS_TTL)
    return result


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
    search: str = Query("", description="全局搜索（IP/MAC/VM名称/域名）"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = get_occupied_ips(db, subnet_id, page, size, search=search)
    return SubnetOccupiedResponse(**result)


@router.get("/asset-details", response_model=AssetDetailResponse)
def asset_details(
    type: str = Query(..., description="domains | public_services | internal_services"),
    search: str = Query("", description="搜索关键词"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = search.lower() if search else ""

    if type == "domains":
        # 收集去重域名 + 来源标记
        zdns_set = set()
        for (d,) in db.query(ZDNSDomainMap.domain_name).filter(
            ZDNSDomainMap.domain_name != "",
            ZDNSDomainMap.domain_name.notlike("*%"),
            ~ZDNSDomainMap.domain_name.contains("in-addr.arpa"),
        ).distinct().all():
            zdns_set.add(d)

        f5_real = set()
        for (d,) in db.query(F5ApplicationMap.domain_name).filter(
            F5ApplicationMap.domain_name != "",
        ).distinct().all():
            if '.' in d:
                f5_real.add(d)

        items = []
        all_domains = zdns_set | f5_real
        for d in sorted(all_domains):
            if q and q not in d.lower():
                continue
            src_parts = []
            if d in zdns_set:
                src_parts.append("ZDNS")
            if d in f5_real:
                src_parts.append("F5")
            items.append(AssetDomainItem(domain_name=d, source=",".join(src_parts)))

        return AssetDetailResponse(type=type, items=items, total=len(items))

    if type == "public_services":
        # 只统计 real_f5 域名关联的 F5 VS (IP:port)
        real_f5 = set()
        for (d,) in db.query(F5ApplicationMap.domain_name).filter(
            F5ApplicationMap.domain_name != "",
        ).distinct().all():
            if '.' in d:
                real_f5.add(d)

        items = []
        seen = set()
        for am in db.query(F5ApplicationMap.vs_ip, F5ApplicationMap.vs_port).filter(
            F5ApplicationMap.domain_name.in_(real_f5),
            F5ApplicationMap.vs_ip != "",
            F5ApplicationMap.vs_port.isnot(None),
        ).distinct().all():
            key = (am.vs_ip, str(am.vs_port))
            if key in seen:
                continue
            seen.add(key)
            if q and q not in am.vs_ip.lower() and q not in str(am.vs_port):
                continue
            items.append(AssetServiceItem(ip=am.vs_ip, port=str(am.vs_port)))

        items.sort(key=lambda x: (x.ip, x.port))
        return AssetDetailResponse(type=type, items=items, total=len(items))

    if type == "internal_services":
        # 只统计 real_f5 域名关联的内网成员 (IP:port)
        real_f5 = set()
        for (d,) in db.query(F5ApplicationMap.domain_name).filter(
            F5ApplicationMap.domain_name != "",
        ).distinct().all():
            if '.' in d:
                real_f5.add(d)

        items = []
        seen = set()
        for am in db.query(F5ApplicationMap.member_ip, F5ApplicationMap.member_port).filter(
            F5ApplicationMap.domain_name.in_(real_f5),
            F5ApplicationMap.member_ip != "",
            F5ApplicationMap.member_port.isnot(None),
        ).distinct().all():
            key = (am.member_ip, str(am.member_port))
            if key in seen:
                continue
            seen.add(key)
            if q and q not in am.member_ip.lower() and q not in str(am.member_port):
                continue
            items.append(AssetServiceItem(ip=am.member_ip, port=str(am.member_port)))

        items.sort(key=lambda x: (x.ip, x.port))
        return AssetDetailResponse(type=type, items=items, total=len(items))

    return AssetDetailResponse(type=type, items=[], total=0)


class IpMacItem(BaseModel):
    value: str


class IpMacListResponse(BaseModel):
    items: list[IpMacItem]
    total: int


@router.get("/ip-mac-list", response_model=IpMacListResponse)
def ip_mac_list(
    type: str = Query("ip", description="ip 或 mac"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str = Query("", description="搜索"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = search.lower() if search else ""

    if type == "ip":
        rows = db.query(ScanResult.ip_address).filter(
            ScanResult.ip_address != "", ScanResult.ip_address.isnot(None),
        ).all()
        seen = set()
        all_vals: list[str] = []
        for (ip,) in rows:
            if ip not in seen:
                seen.add(ip)
                if not q or q in ip.lower():
                    all_vals.append(ip)
    else:
        rows = db.query(ScanResult.mac_address).filter(
            ScanResult.mac_address != "", ScanResult.mac_address.isnot(None),
        ).all()
        seen = set()
        all_vals: list[str] = []
        for (mac,) in rows:
            m = mac.lower()
            if m not in seen:
                seen.add(m)
                if not q or q in mac.lower():
                    all_vals.append(mac)

    total = len(all_vals)
    start = (page - 1) * size
    paged = all_vals[start:start + size]

    return IpMacListResponse(
        items=[IpMacItem(value=v) for v in paged],
        total=total,
    )


@router.get("/vm-details")
def vm_details(
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=200),
    search: str = Query("", description="搜索名称/IP/MAC/OS/集群/主机/网络/文件夹等"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = search.lower() if search else ""
    base = db.query(VMInventory)

    if q:
        if _IP_RE.match(search):
            base = base.filter(VMInventory.ip_address == search)
        else:
            base = base.filter(
                VMInventory.vm_name.ilike(f"%{q}%")
                | VMInventory.ip_address.ilike(f"%{q}%")
                | VMInventory.mac_address.ilike(f"%{q}%")
                | VMInventory.os_name.ilike(f"%{q}%")
                | VMInventory.cluster.ilike(f"%{q}%")
                | VMInventory.esxi_host.ilike(f"%{q}%")
                | VMInventory.network_name.ilike(f"%{q}%")
                | VMInventory.vm_folder.ilike(f"%{q}%")
                | VMInventory.datacenter.ilike(f"%{q}%")
            )

    total = base.count()
    rows = base.order_by(VMInventory.vm_name).offset((page - 1) * size).limit(size).all()

    items = []
    for vm in rows:
        items.append({
            "vm_name": vm.vm_name,
            "power_state": vm.power_state or "",
            "ip_address": vm.ip_address or "",
            "mac_address": vm.mac_address or "",
            "os_name": vm.os_name or "",
            "cpu_count": vm.cpu_count or 0,
            "memory_gb": vm.memory_gb or 0.0,
            "datacenter": vm.datacenter or "",
            "cluster": vm.cluster or "",
            "esxi_host": vm.esxi_host or "",
            "network_name": vm.network_name or "",
            "vlan_id": vm.vlan_id or "",
            "resource_pool": vm.resource_pool or "",
            "vm_folder": vm.vm_folder or "",
        })

    return {"items": items, "total": total, "page": page, "size": size}
