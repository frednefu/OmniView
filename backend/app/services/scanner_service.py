"""
Scanner service — bridges the existing switchReader SNMP engine to the web backend.
Reuses functions from switchReader/switchReader.py directly.
"""
import sys
import os
import asyncio
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.switch import Switch
from app.models.scan_log import ScanLog, ScanStatus, TriggerType
from app.models.scan_result import ScanResult
from app.models.route_table import RouteTable
from app.config import settings

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
    db.query(ScanResult).filter(ScanResult.switch_id == switch_id).delete()
    for entry in host_data:
        sr = ScanResult(
            switch_id=switch_id,
            ip_address=_clean(entry.get("IP地址", "")),
            mac_address=_clean(entry.get("MAC地址", "")),
            vlan_bd=entry.get("VLAN/BD"),
            vlan_type=_clean(entry.get("VLAN类型", "") or ""),
            physical_port=_clean(entry.get("物理端口", "") or ""),
            virtual_port=_clean(entry.get("虚拟端口", "") or ""),
            switch_type="L3" if entry.get("交换机类型") == "三层" else "L2",
            scan_log_id=scan_log_id,
        )
        db.add(sr)


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
            scan_log.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        db.rollback()
        scan_log = db.query(ScanLog).get(scan_log_id)
        if scan_log:
            scan_log.status = ScanStatus.failed
            scan_log.error_message = str(e)
            scan_log.completed_at = datetime.now(timezone.utc)
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
