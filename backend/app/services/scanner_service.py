"""
Scanner service — bridges the existing switchReader SNMP engine to the web backend.
Reuses _async_scan_switch() from switchReader/switchReader.py directly.
"""
import sys
import os
import asyncio
import traceback
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.switch import Switch
from app.models.scan_log import ScanLog, ScanStatus, TriggerType
from app.models.scan_result import ScanResult
from app.models.route_table import RouteTable

# Ensure switchReader is importable
_sw_reader_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'switchReader')
if _sw_reader_dir not in sys.path:
    sys.path.insert(0, _sw_reader_dir)


def _build_switch_config(switch: Switch) -> dict:
    """Map a Switch DB model to the dict format expected by switchReader."""
    cfg = {
        "ip": switch.ip_address,
        "community": switch.community,
        "mib": switch.mib_type.value if hasattr(switch.mib_type, 'value') else switch.mib_type,
    }
    return cfg


def _store_host_results(db: Session, switch_id: int, scan_log_id: int, host_data: list[dict]):
    """Insert scan results, replacing old data for this switch."""
    # Delete old results for this switch
    db.query(ScanResult).filter(ScanResult.switch_id == switch_id).delete()

    for entry in host_data:
        sr = ScanResult(
            switch_id=switch_id,
            ip_address=entry.get("IP地址", ""),
            mac_address=entry.get("MAC地址", ""),
            vlan_bd=entry.get("VLAN/BD"),
            vlan_type=entry.get("VLAN类型", "") or "",
            physical_port=entry.get("物理端口", "") or "",
            virtual_port=entry.get("虚拟端口", "") or "",
            switch_type="L3" if entry.get("交换机类型") == "三层" else "L2",
            scan_log_id=scan_log_id,
        )
        db.add(sr)


def _store_route_results(db: Session, switch_id: int, scan_log_id: int, route_data: list[dict]):
    """Insert route table data, replacing old data for this switch."""
    db.query(RouteTable).filter(RouteTable.switch_id == switch_id).delete()

    for entry in route_data:
        rt = RouteTable(
            switch_id=switch_id,
            target_network=entry.get("目标网络", ""),
            subnet_mask=entry.get("子网掩码", ""),
            cidr=entry.get("CIDR", ""),
            gateway=entry.get("网关", ""),
            interface_name=entry.get("接口", ""),
            route_type=entry.get("路由类型", ""),
            protocol=entry.get("协议", ""),
            scan_log_id=scan_log_id,
        )
        db.add(rt)


async def _run_scan_async(switch: Switch, scan_log_id: int, db_url: str):
    """Run an SNMP scan asynchronously and store results in the database.

    This function runs in a background task. It creates its own DB session
    and imports switchReader functions at call time to avoid Slim lifecycle issues.
    """
    from switchReader import switchReader as swr

    config = _build_switch_config(switch)

    # Create Slim and run scan
    slim = swr.Slim()
    try:
        switch_type = await swr._detect_switch_type(slim, config['ip'], config['community'])
        if switch_type == 'L3':
            host_data = await swr._scan_l3_switch(slim, config['ip'], config['community'], config.get('mib', 'standard'))
            route_data = await swr._get_route_table(slim, config['ip'], config['community'])
        else:
            host_data = await swr._scan_l2_switch(slim, config['ip'], config['community'], config.get('mib', 'standard'))
            route_data = []
    finally:
        slim.close()

    # Store results in new DB session
    engine = swr.SessionLocal() if hasattr(swr, 'SessionLocal') else None
    from app.database import SessionLocal as AppSessionLocal
    db = AppSessionLocal()
    try:
        _store_host_results(db, switch.id, scan_log_id, host_data)
        _store_route_results(db, switch.id, scan_log_id, route_data)

        scan_log = db.query(ScanLog).get(scan_log_id)
        if scan_log:
            scan_log.status = ScanStatus.success
            scan_log.hosts_found = len(host_data)
            scan_log.routes_found = len(route_data)
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


def trigger_scan(switch: Switch, triggered_by: TriggerType, db_url: str) -> int:
    """Trigger an async scan for a switch. Returns the scan_log_id."""
    from app.database import SessionLocal

    db_sync = SessionLocal()
    try:
        scan_log = ScanLog(
            switch_id=switch.id,
            status=ScanStatus.running,
            triggered_by=triggered_by,
        )
        db_sync.add(scan_log)
        db_sync.commit()
        db_sync.refresh(scan_log)
        scan_log_id = scan_log.id
    finally:
        db_sync.close()

    # Launch async scan in background
    asyncio.create_task(_run_scan_async(switch, scan_log_id, db_url))

    return scan_log_id
