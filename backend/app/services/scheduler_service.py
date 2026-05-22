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
from app.services.scanner_service import _run_scan_async
from app.services.vcenter_scanner_service import _run_vcenter_scan_async

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def _scan_job(switch_id: int):
    """单个交换机扫描 job（在独立线程中运行）。"""
    db = SessionLocal()
    try:
        sw = db.query(Switch).get(switch_id)
        if not sw or not sw.is_active:
            return

        running = db.query(ScanLog).filter(
            ScanLog.switch_id == switch_id,
            ScanLog.status == ScanStatus.running,
        ).first()
        if running:
            return

        scan_log = ScanLog(
            switch_id=switch_id,
            status=ScanStatus.running,
            triggered_by=TriggerType.scheduled,
            started_at=datetime.now(),
        )
        db.add(scan_log)
        db.commit()
        db.refresh(scan_log)
        scan_log_id = scan_log.id

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
        if not vc or not vc.is_active or vc.last_scan_status == "running":
            return
        asyncio.run(_run_vcenter_scan_async(vcenter_id))
    except Exception:
        logger.exception("vCenter 定时扫描失败 vcenter_id=%s", vcenter_id)
    finally:
        db.close()


def start_scheduler():
    """启动调度器，为所有启用的交换机和 vCenter 创建定时任务。"""
    db = SessionLocal()
    try:
        switches = db.query(Switch).filter(Switch.is_active == True, Switch.scan_interval > 0).all()
        for sw in switches:
            _add_job(sw.id, sw.scan_interval)
        vcenters = db.query(VCenter).filter(VCenter.is_active == True, VCenter.scan_interval > 0).all()
        for vc in vcenters:
            _add_vcenter_job(vc.id, vc.scan_interval)
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
    """更新或移除单个任务的调度。"""
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
