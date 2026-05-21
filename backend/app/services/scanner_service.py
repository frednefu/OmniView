"""
Scanner service — bridges the existing switchReader SNMP engine to the web backend.
Reuses functions from switchReader/switchReader.py directly.
"""
import sys
import os
import asyncio
from datetime import datetime

from app.database import SessionLocal
from app.models.switch import Switch
from app.models.scan_log import ScanLog, ScanStatus, TriggerType
from app.models.scan_result import ScanResult
from app.models.route_table import RouteTable
from app.config import settings
from app.services.history_service import detect_changes

# Ensure switchReader is importable
_sw_reader_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'switchReader')
if _sw_reader_dir not in sys.path:
    sys.path.insert(0, _sw_reader_dir)

import switchReader as swr


import re

_SAFE_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

def _clean(v):
    """Sanitize a value for DB storage: strip control chars, truncate to safe length."""
    if v is None:
        return ""
    s = str(v)
    s = _SAFE_RE.sub('', s)
    return s[:256]

def _build_switch_config(switch: Switch) -> dict:
    cfg = {
        "ip": switch.ip_address,
        "community": switch.community,
        "mib": switch.mib_type.value if hasattr(switch.mib_type, 'value') else switch.mib_type,
    }
    return cfg


def _store_host_results(db, switch_id: int, scan_log_id: int, host_data: list):
    """
    增量保存扫描结果：
    - 核心键 (IP, MAC, 物理端口) 不变且追踪字段未变 → 只更新 updated_at，不产生历史
    - 核心键存在但追踪字段变化 → 插入新行保留历史，产生 modified 记录
    - 核心键不存在 → 插入新行，产生 added 记录
    - 旧核心键在新数据中消失 → 产生 deleted 记录（旧数据保留作为历史）
    """
    from app.services.history_service import _fields_differ

    # 构建 MAC→IP 回填映射
    mac_ip_map = {}
    existing_rows = db.query(
        ScanResult.mac_address, ScanResult.ip_address
    ).filter(
        ScanResult.ip_address != "",
        ScanResult.ip_address.isnot(None),
    ).order_by(ScanResult.id.desc()).all()
    for mac, ip in existing_rows:
        if mac and mac not in mac_ip_map:
            mac_ip_map[mac] = ip

    # 快照旧数据：(IP, MAC, physical_port) → ScanResult
    old_rows = db.query(ScanResult).filter(ScanResult.switch_id == switch_id).all()
    old_by_key = {}
    for r in old_rows:
        old_by_key[(r.ip_address, r.mac_address, r.physical_port)] = r

    now = datetime.now()
    new_by_key = {}
    handled_old_keys = set()

    for entry in host_data:
        ip = _clean(entry.get("IP地址", ""))
        mac = _clean(entry.get("MAC地址", ""))
        if not ip and mac and mac in mac_ip_map:
            ip = mac_ip_map[mac]

        physical_port = _clean(entry.get("物理端口", "") or "")
        key = (ip, mac, physical_port)
        old_r = old_by_key.get(key)

        new_vlan_bd = entry.get("VLAN/BD")
        new_vlan_type = _clean(entry.get("VLAN类型", "") or "")
        new_virtual_port = _clean(entry.get("虚拟端口", "") or "")
        new_switch_type = "L3" if entry.get("交换机类型") == "三层" else "L2"

        if old_r and not _fields_differ(old_r, new_vlan_bd, new_vlan_type,
                                         new_virtual_port, new_switch_type):
            # 核心键未变且追踪字段相同 → 仅更新时间戳，复用旧行
            old_r.updated_at = now
            old_r.scan_log_id = scan_log_id
            new_by_key[key] = old_r
            handled_old_keys.add(key)
            continue

        # 新记录或字段变化 → 插入新行
        sr = ScanResult(
            switch_id=switch_id,
            ip_address=ip,
            mac_address=mac,
            vlan_bd=new_vlan_bd,
            vlan_type=new_vlan_type,
            physical_port=physical_port,
            virtual_port=new_virtual_port,
            switch_type=new_switch_type,
            scan_log_id=scan_log_id,
            created_at=now,
            updated_at=now,
        )
        db.add(sr)
        new_by_key[key] = sr
        if old_r:
            handled_old_keys.add(key)

    # 变更检测并写入历史
    detect_changes(db, switch_id, scan_log_id, old_by_key, new_by_key, handled_old_keys)


def _store_route_results(db, switch_id: int, scan_log_id: int, route_data: list):
    db.query(RouteTable).filter(RouteTable.switch_id == switch_id).delete()
    for entry in route_data:
        rt = RouteTable(
            switch_id=switch_id,
            target_network=_clean(entry.get("目标网络", "")),
            subnet_mask=_clean(entry.get("子网掩码", "")),
            cidr=_clean(entry.get("CIDR", "")),
            gateway=_clean(entry.get("网关", "")),
            interface_name=_clean(entry.get("接口", "")),
            route_type=_clean(entry.get("路由类型", "")),
            protocol=_clean(entry.get("协议", "")),
            scan_log_id=scan_log_id,
            created_at=datetime.now(),
        )
        db.add(rt)


async def _run_scan_async(switch: Switch, scan_log_id: int):
    host_data = []
    route_data = []
    error_msg = None

    try:
        slim = swr.Slim()
        try:
            switch_type = await swr._detect_switch_type(slim, switch.ip_address, switch.community)
            if switch_type == 'L3':
                host_data = await swr._scan_l3_switch(slim, switch.ip_address, switch.community, switch.mib_type.value)
                route_data = await swr._get_route_table(slim, switch.ip_address, switch.community)
            else:
                host_data = await swr._scan_l2_switch(slim, switch.ip_address, switch.community, switch.mib_type.value)
                route_data = []
        finally:
            slim.close()
    except Exception as e:
        import traceback
        error_msg = f"{e}\n{traceback.format_exc()[-500:]}"

    db = SessionLocal()
    try:
        if error_msg is None:
            _store_host_results(db, switch.id, scan_log_id, host_data)
            _store_route_results(db, switch.id, scan_log_id, route_data)

        scan_log = db.query(ScanLog).get(scan_log_id)
        if scan_log:
            scan_log.status = ScanStatus.failed if error_msg else ScanStatus.success
            scan_log.hosts_found = len(host_data)
            scan_log.routes_found = len(route_data)
            scan_log.error_message = error_msg
            scan_log.completed_at = datetime.now()
        db.commit()
    except Exception as e:
        db.rollback()
        scan_log = db.query(ScanLog).get(scan_log_id)
        if scan_log:
            scan_log.status = ScanStatus.failed
            scan_log.error_message = str(e)
            scan_log.completed_at = datetime.now()
        db.commit()
    finally:
        db.close()


async def trigger_scan(switch: Switch, triggered_by: TriggerType) -> int:
    """Trigger an async scan for a switch. Returns the scan_log_id."""
    db = SessionLocal()
    try:
        scan_log = ScanLog(
            switch_id=switch.id,
            status=ScanStatus.running,
            triggered_by=triggered_by,
            started_at=datetime.now(),
        )
        db.add(scan_log)
        db.commit()
        db.refresh(scan_log)
        scan_log_id = scan_log.id
    finally:
        db.close()

    asyncio.create_task(_run_scan_async(switch, scan_log_id))
    return scan_log_id


async def test_snmp_connection(ip_address: str, community: str) -> dict:
    """Test SNMP connectivity by reading sysServices OID."""
    slim = swr.Slim()
    try:
        val = await swr._snmp_get_scalar(slim, ip_address, community, swr.OID_SYS_SERVICES)
        if val is not None:
            return {"ok": True, "message": f"连接成功 (sysServices={val})"}
        else:
            return {"ok": False, "message": "SNMP 无响应，请检查 IP/community/端口"}
    except Exception as e:
        return {"ok": False, "message": f"连接失败: {str(e)}"}
    finally:
        slim.close()
