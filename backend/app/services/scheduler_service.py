"""APScheduler 定时扫描调度器。"""
import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import SessionLocal
from app.models.switch import Switch
from app.models.scan_log import ScanLog, ScanStatus, TriggerType
from app.models.vcenter import VCenter
from app.models.f5 import F5Device
from app.models.zdns import ZDNSDevice
from app.models.qax import QianXinDevice
from app.services.scanner_service import _run_scan_async
from app.services.vcenter_scanner_service import _run_vcenter_scan_async
from app.services.f5_scanner_service import _run_f5_scan_async
from app.services.zdns_scanner_service import _run_zdns_scan_async
from app.services.zdns_ip_scanner_service import _run_zdns_ip_scan_async
from app.services.qax_scanner_service import _run_qax_scan_async

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def _create_scan_log(db, source_type, source_id, source_name):
    """创建扫描日志并返回 scan_log_id。"""
    scan_log = ScanLog(
        source_type=source_type,
        source_id=source_id,
        source_name=source_name,
        status=ScanStatus.running,
        triggered_by=TriggerType.scheduled,
        started_at=datetime.now(),
    )
    db.add(scan_log)
    db.commit()
    db.refresh(scan_log)
    return scan_log.id


def _complete_scan_log(scan_log_id, status, hosts_found=0, routes_found=0, error_msg=None):
    """更新扫描日志为完成状态。"""
    db = SessionLocal()
    try:
        log = db.query(ScanLog).get(scan_log_id)
        if log:
            log.status = status
            log.hosts_found = hosts_found
            log.routes_found = routes_found
            log.error_message = error_msg
            log.completed_at = datetime.now()
            if log.started_at:
                log.duration_seconds = round((log.completed_at - log.started_at).total_seconds(), 1)
            db.commit()
    except Exception:
        logger.exception("更新扫描日志失败 scan_log_id=%s", scan_log_id)
    finally:
        db.close()


def _scan_job(switch_id: int):
    """单个交换机扫描 job（在独立线程中运行）。"""
    db = SessionLocal()
    try:
        sw = db.query(Switch).get(switch_id)
        if not sw or not sw.is_active:
            return

        running = db.query(ScanLog).filter(
            ScanLog.source_type == "switch",
            ScanLog.source_id == switch_id,
            ScanLog.status == ScanStatus.running,
        ).first()
        if running:
            running.status = ScanStatus.failed
            running.error_message = "上次扫描意外中断，已自动重置"
            db.commit()

        scan_log_id = _create_scan_log(db, "switch", switch_id, sw.name)

        # 在线程中运行异步扫描
        asyncio.run(_run_scan_async(sw, scan_log_id))
    except Exception:
        logger.exception("定时扫描失败 switch_id=%s", switch_id)
    finally:
        db.close()


def _vcenter_scan_job(vcenter_id: int):
    """单个 vCenter 扫描 job（在独立线程中运行）。"""
    db = SessionLocal()
    try:
        vc = db.query(VCenter).get(vcenter_id)
        if not vc or not vc.is_active:
            return
        if vc.last_scan_status == "running":
            vc.last_scan_status = None
            vc.last_scan_error = "上次扫描意外中断，已自动重置"
            db.commit()

        scan_log_id = _create_scan_log(db, "vcenter", vcenter_id, vc.name)

        asyncio.run(_run_vcenter_scan_async(vcenter_id, scan_log_id))
    except Exception:
        logger.exception("vCenter 定时扫描失败 vcenter_id=%s", vcenter_id)
    finally:
        db.close()


def start_scheduler():
    """启动调度器，为所有启用的设备创建定时任务。"""
    db = SessionLocal()
    try:
        switches = db.query(Switch).filter(Switch.is_active == True, Switch.scan_interval > 0).all()
        for sw in switches:
            _add_job(sw.id, sw.scan_interval)
        vcenters = db.query(VCenter).filter(VCenter.is_active == True, VCenter.scan_interval > 0).all()
        for vc in vcenters:
            _add_vcenter_job(vc.id, vc.scan_interval)
        f5_devices = db.query(F5Device).filter(F5Device.is_active == True, F5Device.scan_interval > 0).all()
        for dev in f5_devices:
            _add_f5_job(dev.id, dev.scan_interval)
        zdns_devices = db.query(ZDNSDevice).filter(ZDNSDevice.is_active == True, ZDNSDevice.scan_interval > 0).all()
        for dev in zdns_devices:
            _add_zdns_job(dev.id, dev.scan_interval)
        zdns_ip_devices = db.query(ZDNSDevice).filter(ZDNSDevice.is_active == True, ZDNSDevice.ip_scan_interval > 0).all()
        for dev in zdns_ip_devices:
            _add_zdns_ip_job(dev.id, dev.ip_scan_interval)
        qax_devices = db.query(QianXinDevice).filter(QianXinDevice.enabled == True, QianXinDevice.scan_interval > 0).all()
        for dev in qax_devices:
            _add_qax_job(dev.id, dev.scan_interval)
    finally:
        db.close()

    if not scheduler.running:
        scheduler.start()
        logger.info("定时扫描调度器已启动")


def shutdown_scheduler():
    """关闭调度器。"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("定时扫描调度器已关闭")


def refresh_job(switch_id: int, scan_interval: int):
    """更新或移除单个交换机任务。"""
    job_id = f"scan_{switch_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if scan_interval > 0 and scheduler.running:
        _add_job(switch_id, scan_interval)


def _add_job(switch_id: int, scan_interval: int):
    """添加单个交换机的定时扫描任务。"""
    scheduler.add_job(
        _scan_job,
        trigger=IntervalTrigger(seconds=scan_interval),
        id=f"scan_{switch_id}",
        args=[switch_id],
        replace_existing=True,
        misfire_grace_time=60,
    )


def refresh_vcenter_job(vcenter_id: int, scan_interval: int):
    """更新或移除单个 vCenter 的调度任务。"""
    job_id = f"vcenter_{vcenter_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if scan_interval > 0 and scheduler.running:
        _add_vcenter_job(vcenter_id, scan_interval)


def _add_vcenter_job(vcenter_id: int, scan_interval: int):
    """添加单个 vCenter 的定时扫描任务。"""
    scheduler.add_job(
        _vcenter_scan_job,
        trigger=IntervalTrigger(seconds=scan_interval),
        id=f"vcenter_{vcenter_id}",
        args=[vcenter_id],
        replace_existing=True,
        misfire_grace_time=60,
    )


def _f5_scan_job(f5_device_id: int):
    """单个 F5 设备扫描 job（在独立线程中运行）。"""
    db = SessionLocal()
    try:
        dev = db.query(F5Device).get(f5_device_id)
        if not dev or not dev.is_active:
            return
        if dev.last_scan_status == "running":
            dev.last_scan_status = None
            dev.last_scan_error = "上次扫描意外中断，已自动重置"
            db.commit()

        scan_log_id = _create_scan_log(db, "f5", f5_device_id, dev.name)

        asyncio.run(_run_f5_scan_async(f5_device_id, scan_log_id))
    except Exception:
        logger.exception("F5 定时扫描失败 f5_device_id=%s", f5_device_id)
    finally:
        db.close()


def refresh_f5_job(f5_device_id: int, scan_interval: int):
    """更新或移除单个 F5 设备的调度任务。"""
    job_id = f"f5_{f5_device_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if scan_interval > 0 and scheduler.running:
        _add_f5_job(f5_device_id, scan_interval)


def _add_f5_job(f5_device_id: int, scan_interval: int):
    """添加单个 F5 设备的定时扫描任务。"""
    scheduler.add_job(
        _f5_scan_job,
        trigger=IntervalTrigger(seconds=scan_interval),
        id=f"f5_{f5_device_id}",
        args=[f5_device_id],
        replace_existing=True,
        misfire_grace_time=60,
    )


def _zdns_scan_job(zdns_device_id: int):
    """单个 ZDNS 设备扫描 job（在独立线程中运行）。"""
    db = SessionLocal()
    try:
        dev = db.query(ZDNSDevice).get(zdns_device_id)
        if not dev or not dev.is_active:
            return
        if dev.last_scan_status == "running":
            dev.last_scan_status = None
            dev.last_scan_error = "上次扫描意外中断，已自动重置"
            db.commit()

        scan_log_id = _create_scan_log(db, "zdns", zdns_device_id, dev.name)

        asyncio.run(_run_zdns_scan_async(zdns_device_id, scan_log_id))
    except Exception:
        logger.exception("ZDNS 定时扫描失败 zdns_device_id=%s", zdns_device_id)
    finally:
        db.close()


def refresh_zdns_job(zdns_device_id: int, scan_interval: int):
    """更新或移除单个 ZDNS 设备的调度任务。"""
    job_id = f"zdns_{zdns_device_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if scan_interval > 0 and scheduler.running:
        _add_zdns_job(zdns_device_id, scan_interval)


def _add_zdns_job(zdns_device_id: int, scan_interval: int):
    """添加单个 ZDNS 设备的定时扫描任务。"""
    scheduler.add_job(
        _zdns_scan_job,
        trigger=IntervalTrigger(seconds=scan_interval),
        id=f"zdns_{zdns_device_id}",
        args=[zdns_device_id],
        replace_existing=True,
        misfire_grace_time=60,
    )


def _zdns_ip_scan_job(zdns_device_id: int):
    """单个 ZDNS 设备 IP 可达性扫描 job（在独立线程中运行）。"""
    db = SessionLocal()
    try:
        dev = db.query(ZDNSDevice).get(zdns_device_id)
        if not dev or not dev.is_active:
            return
        if dev.last_ip_scan_status == "running":
            dev.last_ip_scan_status = None
            dev.last_ip_scan_error = "上次扫描意外中断，已自动重置"
            db.commit()

        scan_log_id = _create_scan_log(db, "zdns_ip", zdns_device_id, dev.name)

        asyncio.run(_run_zdns_ip_scan_async(zdns_device_id, scan_log_id))
    except Exception:
        logger.exception("ZDNS IP 扫描失败 zdns_device_id=%s", zdns_device_id)
    finally:
        db.close()


def refresh_zdns_ip_job(zdns_device_id: int, ip_scan_interval: int):
    """更新或移除单个 ZDNS 设备的 IP 扫描调度任务。"""
    job_id = f"zdns_ip_{zdns_device_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if ip_scan_interval > 0 and scheduler.running:
        _add_zdns_ip_job(zdns_device_id, ip_scan_interval)


def _add_zdns_ip_job(zdns_device_id: int, ip_scan_interval: int):
    """添加单个 ZDNS 设备的 IP 扫描调度任务。"""
    scheduler.add_job(
        _zdns_ip_scan_job,
        trigger=IntervalTrigger(seconds=ip_scan_interval),
        id=f"zdns_ip_{zdns_device_id}",
        args=[zdns_device_id],
        replace_existing=True,
        misfire_grace_time=60,
    )


def _qax_scan_job(device_id: int):
    """单个椒图设备扫描 job（在独立线程中运行）。"""
    db = SessionLocal()
    try:
        dev = db.query(QianXinDevice).get(device_id)
        if not dev or not dev.enabled:
            return
        if dev.last_scan_status == "running":
            dev.last_scan_status = None
            dev.last_scan_error = "上次扫描意外中断，已自动重置"
            db.commit()

        scan_log_id = _create_scan_log(db, "qax", device_id, dev.name)

        asyncio.run(_run_qax_scan_async(device_id, scan_log_id))
    except Exception:
        logger.exception("椒图定时扫描失败 device_id=%s", device_id)
    finally:
        db.close()


def refresh_qax_job(device_id: int, scan_interval: int):
    """更新或移除单个椒图设备的调度任务。"""
    job_id = f"qax_{device_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    if scan_interval > 0 and scheduler.running:
        _add_qax_job(device_id, scan_interval)


def _add_qax_job(device_id: int, scan_interval: int):
    """添加单个椒图设备的定时扫描任务。"""
    scheduler.add_job(
        _qax_scan_job,
        trigger=IntervalTrigger(seconds=scan_interval),
        id=f"qax_{device_id}",
        args=[device_id],
        replace_existing=True,
        misfire_grace_time=60,
    )
