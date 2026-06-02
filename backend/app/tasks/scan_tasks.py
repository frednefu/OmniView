"""Celery 扫描任务 — 各数据源的异步扫描执行。

每个任务在被 Worker 拉取后：
1. 记录执行该任务的 Worker 名称到 scan_log
2. 从数据库加载设备信息
3. 调用对应的 _run_*_scan_async 执行扫描
4. _run_*_scan_async 内部会自行更新 scan_log 和设备状态
"""

import asyncio
import logging
import os
import socket

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models.scan_log import ScanLog

logger = logging.getLogger(__name__)


def _record_worker(scan_log_id: int):
    """将当前 Worker 名称写入 scan_log，便于前台追溯任务由哪个节点执行。"""
    worker = os.environ.get("WORKER_NAME") or socket.gethostname()
    db = SessionLocal()
    try:
        log = db.query(ScanLog).get(scan_log_id)
        if log:
            log.worker_name = worker
            db.commit()
    except Exception:
        logger.exception("记录 Worker 名称失败 scan_log_id=%s", scan_log_id)
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60, queue="scan:switch")
def scan_switch_task(self, switch_id: int, scan_log_id: int):
    """交换机 SNMP 扫描任务。"""
    _record_worker(scan_log_id)

    from app.models.switch import Switch
    from app.services.scanner_service import _run_scan_async

    db = SessionLocal()
    try:
        sw = db.query(Switch).get(switch_id)
        if not sw:
            logger.warning("交换机不存在 switch_id=%s", switch_id)
            return {"error": "switch_not_found"}
        sw_obj = sw
    finally:
        db.close()

    try:
        asyncio.run(_run_scan_async(sw_obj, scan_log_id))
    except Exception as e:
        logger.exception("Celery 交换机扫描失败 switch_id=%s", switch_id)
        raise


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60, queue="scan:vcenter")
def scan_vcenter_task(self, vcenter_id: int, scan_log_id: int):
    """vCenter 扫描任务。"""
    _record_worker(scan_log_id)

    from app.services.vcenter_scanner_service import _run_vcenter_scan_async

    try:
        asyncio.run(_run_vcenter_scan_async(vcenter_id, scan_log_id))
    except Exception as e:
        logger.exception("Celery vCenter 扫描失败 vcenter_id=%s", vcenter_id)
        raise


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60, queue="scan:f5")
def scan_f5_task(self, device_id: int, scan_log_id: int):
    """F5 设备扫描任务。"""
    _record_worker(scan_log_id)

    from app.services.f5_scanner_service import _run_f5_scan_async

    try:
        asyncio.run(_run_f5_scan_async(device_id, scan_log_id))
    except Exception as e:
        logger.exception("Celery F5 扫描失败 device_id=%s", device_id)
        raise


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60, queue="scan:zdns")
def scan_zdns_task(self, device_id: int, scan_log_id: int):
    """ZDNS 设备扫描任务。"""
    _record_worker(scan_log_id)

    from app.services.zdns_scanner_service import _run_zdns_scan_async

    try:
        asyncio.run(_run_zdns_scan_async(device_id, scan_log_id))
    except Exception as e:
        logger.exception("Celery ZDNS 扫描失败 device_id=%s", device_id)
        raise


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60, queue="scan:zdns_ip")
def scan_zdns_ip_task(self, device_id: int, scan_log_id: int):
    """ZDNS IP 可达性扫描任务。"""
    _record_worker(scan_log_id)

    from app.services.zdns_ip_scanner_service import _run_zdns_ip_scan_async

    try:
        asyncio.run(_run_zdns_ip_scan_async(device_id, scan_log_id))
    except Exception as e:
        logger.exception("Celery ZDNS IP扫描失败 device_id=%s", device_id)
        raise


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60, queue="scan:qax")
def scan_qax_task(self, device_id: int, scan_log_id: int):
    """椒图设备扫描任务。"""
    _record_worker(scan_log_id)

    from app.services.qax_scanner_service import _run_qax_scan_async

    try:
        asyncio.run(_run_qax_scan_async(device_id, scan_log_id))
    except Exception as e:
        logger.exception("Celery 椒图扫描失败 device_id=%s", device_id)
        raise


@celery_app.task(bind=True, max_retries=1, default_retry_delay=60, queue="scan:dingjia")
def scan_dingjia_task(self, device_id: int, scan_log_id: int):
    """鼎甲备份扫描任务。"""
    _record_worker(scan_log_id)
    from app.services.dingjia_scanner import fetch_backup_data, TZ as DJ_TZ
    from app.models.dingjia import DingJiaDevice, DingJiaBackupRecord
    from app.models.scan_log import ScanLog, ScanStatus
    from datetime import datetime, timezone, timedelta

    db = SessionLocal()
    try:
        dev = db.query(DingJiaDevice).get(device_id)
        if not dev:
            raise Exception(f"设备不存在: {device_id}")
        # 更新 scan_log 状态
        log = db.query(ScanLog).get(scan_log_id)
        if log:
            log.status = ScanStatus.running
            db.commit()

        now_start = datetime.now(DJ_TZ).replace(tzinfo=None)
        # 更新 started_at 为东八区时间
        if log:
            log.started_at = now_start
            db.commit()
        records = fetch_backup_data(dev.host, dev.api_key, dev.access_key)
        db.query(DingJiaBackupRecord).filter(DingJiaBackupRecord.device_id == device_id).delete()
        for r in records:
            db.add(DingJiaBackupRecord(device_id=device_id, **r))
        now_end = datetime.now(DJ_TZ).replace(tzinfo=None)
        dev.last_scan_status = "success"
        dev.last_scan_time = now_end
        dev.last_scan_duration = int((now_end - now_start).total_seconds())
        if log:
            log.status = ScanStatus.success
            log.hosts_found = len(records)
            log.duration_seconds = (now_end - now_start).total_seconds()
            log.completed_at = now_end
        db.commit()
    except Exception as e:
        logger.exception("Celery 鼎甲备份扫描失败 device_id=%s", device_id)
        if 'log' in dir() and log:
            log.status = ScanStatus.failed; log.error_message = str(e)
            db.commit()
        raise
    finally:
        db.close()
