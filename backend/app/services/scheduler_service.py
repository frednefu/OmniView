"""APScheduler 定时扫描调度器。"""
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

        # 重置卡住的 running 状态
        if sw.last_scan_status == "running":
            sw.last_scan_status = "failed"
            sw.last_scan_error = "上次扫描意外中断，已自动重置"

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
    except Exception:
        logger.exception("定时扫描准备失败 switch_id=%s", switch_id)
        return
    finally:
        db.close()

    try:
        from app.tasks.scan_tasks import scan_switch_task
        scan_switch_task.delay(switch_id, scan_log_id)
    except Exception:
        logger.exception("定时扫描提交失败 switch_id=%s", switch_id)


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
    except Exception:
        logger.exception("vCenter 定时扫描准备失败 vcenter_id=%s", vcenter_id)
        return
    finally:
        db.close()

    try:
        from app.tasks.scan_tasks import scan_vcenter_task
        scan_vcenter_task.delay(vcenter_id, scan_log_id)
    except Exception:
        logger.exception("vCenter 定时扫描提交失败 vcenter_id=%s", vcenter_id)


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

    # 注册过期 Worker 清理任务（每 30 秒检查一次）
    if not scheduler.get_job("cleanup_stale_workers"):
        scheduler.add_job(
            _cleanup_stale_workers,
            trigger=IntervalTrigger(seconds=30),
            id="cleanup_stale_workers",
            replace_existing=True,
            misfire_grace_time=15,
        )

    # 鼎甲备份扫描任务
    try:
        from app.models.dingjia import DingJiaDevice
        ddb = SessionLocal()
        dj_devices = ddb.query(DingJiaDevice).filter(DingJiaDevice.is_active == True).all()
        for d in dj_devices:
            jid = f"dingjia_{d.id}"
            if not scheduler.get_job(jid):
                scheduler.add_job(
                    _dingjia_scan_job, trigger=IntervalTrigger(seconds=d.scan_interval),
                    id=jid, args=[d.id], replace_existing=True, misfire_grace_time=60,
                )
        ddb.close()
    except Exception:
        pass

    # 资产同步任务（每 30 分钟）
    if not scheduler.get_job("asset_sync"):
        scheduler.add_job(
            _asset_sync_job,
            trigger=IntervalTrigger(minutes=30),
            id="asset_sync",
            replace_existing=True,
            misfire_grace_time=300,
        )
    # 过期外链清理（每 10 分钟）
    if not scheduler.get_job("cleanup_expired_links"):
        scheduler.add_job(
            _cleanup_expired_links,
            trigger=IntervalTrigger(minutes=10),
            id="cleanup_expired_links",
            replace_existing=True,
            misfire_grace_time=60,
        )

    if not scheduler.running:
        scheduler.start()
        logger.info("定时扫描调度器已启动")


def _asset_sync_job():
    """定时同步 vm_inventory → asset_inventory（含域名认领 + 信息系统域名同步）。"""
    from sqlalchemy import text
    from app.models.scan_log import ScanLog, ScanStatus, TriggerType
    from datetime import timezone as dt_tz, timedelta as dt_td

    db = SessionLocal()
    # 创建扫描日志
    tz8 = dt_tz(dt_td(hours=8))
    now8 = datetime.now(tz8).replace(tzinfo=None)
    scan_log = ScanLog(
        source_type="asset_sync",
        source_name="资产同步",
        triggered_by=TriggerType.scheduled,
        status=ScanStatus.running,
        started_at=now8,
    )
    db.add(scan_log)
    db.commit()
    db.refresh(scan_log)

    try:
        r = db.execute(text(
            "INSERT IGNORE INTO asset_inventory (vm_name, claim_status) "
            "SELECT vm_name, 'unlinked' FROM vm_inventory WHERE vm_name IS NOT NULL AND vm_name != ''"
        ))
        # 清理超过30天未更新的僵尸VM
        vs = db.execute(text(
            "DELETE FROM vm_inventory WHERE updated_at < DATE_SUB(NOW(), INTERVAL 30 DAY)"
        ))
        d = db.execute(text(
            "DELETE FROM asset_inventory "
            "WHERE vm_name NOT IN (SELECT vm_name FROM vm_inventory WHERE vm_name IS NOT NULL AND vm_name != '')"
        ))
        # 域名同步
        dc = db.execute(text(
            "UPDATE vm_inventory v JOIN asset_inventory a ON v.vm_name = a.vm_name "
            "SET v.department_id = a.department_id, v.owner_user_id = a.owner_user_id, "
            "    v.claim_status = COALESCE(a.claim_status, 'manual') "
            "WHERE a.department_id IS NOT NULL "
            "  AND (v.department_id IS NULL OR v.owner_user_id IS NULL "
            "       OR v.department_id != a.department_id OR v.owner_user_id != a.owner_user_id)"
        ))
        # 信息系统域名同步
        try:
            from app.models.info_system import InfoSystem
            systems = db.query(InfoSystem).filter(
                InfoSystem.domain.isnot(None), InfoSystem.domain != "",
                InfoSystem.manager_name.isnot(None), InfoSystem.manager_name != "",
            ).all()
            for s in systems:
                raw = [d.strip() for d in s.domain.split(",") if d.strip()]
                clean = []
                for d in raw:
                    d = d.lower()
                    for p in ("https://", "http://"):
                        if d.startswith(p): d = d[len(p):]
                    d = d.split("/")[0].split(":")[0]
                    if d: clean.append(d)
                for dom in clean:
                    zdns = db.execute(text(
                        "SELECT ip_address FROM zdns_domain_map WHERE LOWER(domain_name)=:d LIMIT 1"
                    ), {"d": dom}).fetchone()
                    if not zdns or not zdns.ip_address or not zdns.ip_address.strip():
                        continue
                    ip = zdns.ip_address.strip()
                    db.execute(text(
                        "UPDATE vm_inventory v SET department_id = COALESCE(v.department_id, :dept), "
                        "  owner_user_id = COALESCE(v.owner_user_id, "
                        "    (SELECT id FROM users WHERE name=:mgr_name LIMIT 1)) "
                        "WHERE (v.ip_address LIKE :ip1 OR v.ip_address LIKE :ip2 OR v.ip_address = :ip3) "
                        "  AND (v.department_id IS NULL OR v.owner_user_id IS NULL)"
                    ), {"dept": s.dept_id, "mgr_name": s.manager_name,
                        "ip1": f"{ip},%", "ip2": f"%,{ip}", "ip3": ip})
        except Exception:
            pass
        # 数据关联：有管理员的VM → 回写信息系统管理员
        mgr_synced = 0
        try:
            vm_rows = db.execute(text(
                "SELECT v.ip_address, u.name as owner_name, u.gh as owner_gh "
                "FROM vm_inventory v JOIN users u ON v.owner_user_id = u.id "
                "WHERE v.owner_user_id IS NOT NULL"
            )).fetchall()
            if vm_rows:
                zdns_all = db.execute(text(
                    "SELECT LOWER(domain_name) as d, ip_address FROM zdns_domain_map"
                )).fetchall()
                zdns_by_ip = {}
                for z in zdns_all:
                    ip = (z.ip_address or "").strip()
                    if ip and ip not in zdns_by_ip:
                        zdns_by_ip[ip] = z.d
                for v in vm_rows:
                    if not v.ip_address: continue
                    for ip in [x.strip() for x in v.ip_address.split(",") if x.strip()]:
                        domain = zdns_by_ip.get(ip)
                        if domain:
                            upd = db.execute(text(
                                "UPDATE info_systems SET manager_name=:name, manager_gh=:gh "
                                "WHERE (manager_gh IS NULL OR manager_gh='') "
                                "AND (LOWER(domain) LIKE :d1 OR LOWER(domain) LIKE :d2 OR LOWER(domain)=:d3)"
                            ), {"name": v.owner_name, "gh": v.owner_gh,
                                "d1": f"%{domain}%", "d2": f"%{domain},%", "d3": domain})
                            mgr_synced += upd.rowcount
        except Exception as e:
            logger.warning(f"管理员关联失败: {e}")
        db.commit()
        # 更新扫描日志为成功
        now_end = datetime.now(tz8).replace(tzinfo=None)
        scan_log.status = ScanStatus.success
        scan_log.hosts_found = getattr(r, 'rowcount', 0) + getattr(vs, 'rowcount', 0) + getattr(d, 'rowcount', 0) + getattr(dc, 'rowcount', 0) + mgr_synced
        scan_log.completed_at = now_end
        scan_log.duration_seconds = round((now_end - now8).total_seconds(), 1) if now8 else None
        db.commit()
        rc = getattr(r, 'rowcount', 0)
        if rc > 0:
            logger.info(f"资产同步：新增 {rc} 个 VM")
        if getattr(vs, 'rowcount', 0) > 0:
            logger.info(f"资产同步：清理 {getattr(vs, 'rowcount', 0)} 条过期VM")
        if getattr(d, 'rowcount', 0) > 0:
            logger.info(f"资产同步：清理 {getattr(d, 'rowcount', 0)} 条僵尸记录")
        if getattr(dc, 'rowcount', 0) > 0:
            logger.info(f"资产同步：域名认领 {getattr(dc, 'rowcount', 0)} 条")
        if mgr_synced > 0:
            logger.info(f"资产同步：管理员关联 {mgr_synced} 条")
        # 同步 DomainInventory 物理表（不覆盖已有认领信息）
        try:
            from app.models.domain_inventory import DomainInventory
            db.execute(text(
                "INSERT IGNORE INTO domain_inventory (domain_name, record_type, ip_address, source) "
                "SELECT domain_name, record_type, ip_address, 'ZDNS' FROM zdns_domain_map WHERE domain_name NOT LIKE '%.in-addr.arpa'"
            )).rowcount
            db.execute(text(
                "UPDATE domain_inventory d JOIN zdns_domain_map z ON d.domain_name=z.domain_name "
                "SET d.ip_address=z.ip_address, d.record_type=z.record_type"
            ))
            db.execute(text(
                "UPDATE domain_inventory d JOIN (SELECT DISTINCT z.domain_name, a.owner_user_id, u.name as owner_name, a.department_id "
                "FROM zdns_domain_map z JOIN vm_inventory v ON (v.ip_address LIKE CONCAT('%,',z.ip_address) OR v.ip_address LIKE CONCAT(z.ip_address,',%') OR v.ip_address=z.ip_address) "
                "JOIN asset_inventory a ON v.vm_name=a.vm_name LEFT JOIN users u ON a.owner_user_id=u.id WHERE a.owner_user_id IS NOT NULL"
                ") t ON d.domain_name=t.domain_name AND d.owner_user_id IS NULL "
                "SET d.owner_user_id=t.owner_user_id, d.owner_name=t.owner_name, d.department_id=t.department_id, d.vm_name='', d.source_type='vm'"
            )).rowcount
            from app.models.info_system import InfoSystem
            is_rows = db.query(InfoSystem).filter(InfoSystem.domain.isnot(None), InfoSystem.domain!="").all()
            for s in is_rows:
                for raw in [x.strip() for x in s.domain.split(",") if x.strip()]:
                    dom = raw.lower()
                    for p in ("https://","http://"):
                        if dom.startswith(p): dom = dom[len(p):]
                    dom = dom.split("/")[0].split(":")[0]
                    if not dom: continue
                    db.execute(text(
                        "UPDATE domain_inventory SET owner_name=COALESCE(NULLIF(owner_name,''),:o), department_id=COALESCE(department_id,:d), vm_name=COALESCE(NULLIF(vm_name,''),:v), source_type=COALESCE(NULLIF(source_type,''),'is') "
                        "WHERE domain_name=:dn AND (owner_user_id IS NULL OR department_id IS NULL)"
                    ), {"o":s.manager_name or "","d":s.dept_id,"v":s.system_name,"dn":dom})
            db.execute(text(
                "DELETE FROM domain_inventory WHERE source='ZDNS' AND domain_name NOT IN (SELECT domain_name FROM zdns_domain_map)"
            ))
            db.commit()
            logger.info("资产同步：DomainInventory 已更新")
        except Exception as e:
            logger.warning(f"DomainInventory 同步失败: {e}")
    except Exception as e:
        logger.error(f"资产同步失败：{e}")
        db.rollback()
        try:
            scan_log.status = ScanStatus.failed
            scan_log.error_message = str(e)
            db.commit()
        except Exception:
            pass
    finally:
        db.close()

def _cleanup_expired_links():
    """定期清理已过期的外链。"""
    from app.models.shared_link import SharedLink
    db = SessionLocal()
    try:
        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz).replace(tzinfo=None)
        deleted = db.query(SharedLink).filter(
            SharedLink.expire_at.isnot(None),
            SharedLink.expire_at < now,
        ).delete()
        if deleted > 0:
            db.commit()
            logger.info(f"清理过期外链：{deleted} 条")
    except Exception as e:
        logger.error(f"清理过期外链失败：{e}")
    finally:
        db.close()

_JOB_NAMES = {
    "cleanup_stale_workers": "清理过期Worker",
    "asset_sync": "资产同步",
    "cleanup_expired_links": "清理过期外链",
}


def _job_label(job_id: str) -> str:
    if job_id in _JOB_NAMES:
        return _JOB_NAMES[job_id]
    if job_id.startswith("scan_"):
        return f"交换机扫描-{job_id.split('_',1)[1]}"
    if job_id.startswith("vcenter_"):
        return f"vCenter扫描-{job_id.split('_',1)[1]}"
    if job_id.startswith("f5_"):
        return f"F5扫描-{job_id.split('_',1)[1]}"
    if job_id.startswith("zdns_ip_"):
        return f"ZDNS IP扫描-{job_id.split('_',2)[2] if job_id.count('_')>=2 else job_id.split('_',1)[1]}"
    if job_id.startswith("zdns_"):
        return f"ZDNS扫描-{job_id.split('_',1)[1]}"
    if job_id.startswith("qax_"):
        return f"椒图扫描-{job_id.split('_',1)[1]}"
    if job_id.startswith("dingjia_"):
        return f"鼎甲备份扫描-{job_id.split('_',1)[1]}"
    return job_id


def _job_interval_secs(job) -> int:
    if hasattr(job.trigger, 'interval'):
        return job.trigger.interval.days * 86400 + job.trigger.interval.seconds
    return 0


def _format_interval(secs: int) -> str:
    if secs < 60: return f"{secs}秒"
    if secs < 3600: return f"{secs//60}分钟"
    if secs < 86400: return f"{secs//3600}小时"
    return f"{secs//86400}天"


def _dingjia_scan_job(device_id: int):
    """定时执行的鼎甲备份扫描——提交到 Celery 队列。"""
    db = SessionLocal()
    try:
        from app.models.dingjia import DingJiaDevice
        from app.models.scan_log import ScanLog, ScanStatus, TriggerType
        dev = db.query(DingJiaDevice).get(device_id)
        if not dev or not dev.is_active:
            return
        from datetime import timezone as dt_tz, timedelta as dt_td
        tz8 = dt_tz(dt_td(hours=8))
        scan_log = ScanLog(source_type="dingjia", source_id=device_id, source_name=dev.name,
                          triggered_by=TriggerType.scheduled, status=ScanStatus.queued,
                          started_at=datetime.now(tz8).replace(tzinfo=None))
        db.add(scan_log); db.commit(); db.refresh(scan_log)
        from app.tasks.scan_tasks import scan_dingjia_task
        scan_dingjia_task.delay(device_id, scan_log.id)
    except Exception as e:
        logger.error(f"鼎甲备份扫描提交失败 device_id={device_id}：{e}")
    finally:
        db.close()


def get_scheduler_status() -> dict:
    """返回调度器状态及所有任务详情。"""
    jobs = []
    for job in scheduler.get_jobs():
        secs = _job_interval_secs(job)
        jobs.append({
            "id": job.id,
            "name": _job_label(job.id),
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "interval_secs": secs,
            "interval": _format_interval(secs),
        })
    return {
        "running": scheduler.running,
        "jobs": jobs,
        "total": len(jobs),
    }


def update_job_interval(job_id: str, interval_secs: int) -> bool:
    """修改任务的运行周期（同步更新数据库）。"""
    job = scheduler.get_job(job_id)
    if not job:
        return False
    from apscheduler.triggers.interval import IntervalTrigger
    scheduler.reschedule_job(
        job_id,
        trigger=IntervalTrigger(seconds=interval_secs),
        misfire_grace_time=job.misfire_grace_time,
    )
    # 同步更新数据库中的 scan_interval
    db = SessionLocal()
    try:
        if job_id.startswith("scan_"):
            sw_id = int(job_id.split("_", 1)[1])
            sw = db.query(Switch).get(sw_id)
            if sw: sw.scan_interval = interval_secs
        elif job_id.startswith("vcenter_"):
            vc_id = int(job_id.split("_", 1)[1])
            vc = db.query(VCenter).get(vc_id)
            if vc: vc.scan_interval = interval_secs
        elif job_id.startswith("f5_"):
            f5_id = int(job_id.split("_", 1)[1])
            dev = db.query(F5Device).get(f5_id)
            if dev: dev.scan_interval = interval_secs
        elif job_id.startswith("zdns_ip_"):
            # zdns_ip_{dev_id}
            zdns_id = int(job_id.split("_", 2)[2])
            dev = db.query(ZDNSDevice).get(zdns_id)
            if dev: dev.ip_scan_interval = interval_secs
        elif job_id.startswith("zdns_"):
            zdns_id = int(job_id.split("_", 1)[1])
            dev = db.query(ZDNSDevice).get(zdns_id)
            if dev: dev.scan_interval = interval_secs
        elif job_id.startswith("qax_"):
            qax_id = int(job_id.split("_", 1)[1])
            dev = db.query(QianXinDevice).get(qax_id)
            if dev: dev.scan_interval = interval_secs
        elif job_id.startswith("dingjia_"):
            from app.models.dingjia import DingJiaDevice
            dj_id = int(job_id.split("_", 1)[1])
            dev = db.query(DingJiaDevice).get(dj_id)
            if dev: dev.scan_interval = interval_secs
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
    return True


def shutdown_scheduler():
    """关闭调度器。"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("定时扫描调度器已关闭")


def _cleanup_stale_workers():
    """定期检查并标记心跳过期的 Worker 为离线（超过 45 秒无心跳视为离线）。"""
    from datetime import timedelta
    from app.models.scan_worker import ScanWorker
    db = SessionLocal()
    try:
        threshold = datetime.now() - timedelta(seconds=45)
        stale = db.query(ScanWorker).filter(
            ScanWorker.status == "online",
            ScanWorker.last_heartbeat < threshold,
        ).all()
        for w in stale:
            w.status = "offline"
            w.current_tasks = 0
            logger.info("Worker %s (ID=%s) 心跳过期，已标记为离线", w.worker_name, w.id)
        if stale:
            db.commit()
    except Exception:
        logger.exception("过期 Worker 清理失败")
    finally:
        db.close()


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
    except Exception:
        logger.exception("F5 定时扫描准备失败 f5_device_id=%s", f5_device_id)
        return
    finally:
        db.close()

    try:
        from app.tasks.scan_tasks import scan_f5_task
        scan_f5_task.delay(f5_device_id, scan_log_id)
    except Exception:
        logger.exception("F5 定时扫描提交失败 f5_device_id=%s", f5_device_id)


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
    except Exception:
        logger.exception("ZDNS 定时扫描准备失败 zdns_device_id=%s", zdns_device_id)
        return
    finally:
        db.close()

    try:
        from app.tasks.scan_tasks import scan_zdns_task
        scan_zdns_task.delay(zdns_device_id, scan_log_id)
    except Exception:
        logger.exception("ZDNS 定时扫描提交失败 zdns_device_id=%s", zdns_device_id)


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
    except Exception:
        logger.exception("ZDNS IP 扫描准备失败 zdns_device_id=%s", zdns_device_id)
        return
    finally:
        db.close()

    try:
        from app.tasks.scan_tasks import scan_zdns_ip_task
        scan_zdns_ip_task.delay(zdns_device_id, scan_log_id)
    except Exception:
        logger.exception("ZDNS IP 扫描提交失败 zdns_device_id=%s", zdns_device_id)


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
    """单个椒图设备扫描 job（在独立线程中运行）。

    重要：调用 asyncio.run() 前必须关闭 DB 会话，避免跨线程连接冲突。
    """
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
        dev_name = dev.name
    except Exception:
        logger.exception("椒图定时扫描准备失败 device_id=%s", device_id)
        return
    finally:
        db.close()

    try:
        from app.tasks.scan_tasks import scan_qax_task
        scan_qax_task.delay(device_id, scan_log_id)
    except Exception:
        logger.exception("椒图定时扫描提交失败 device_id=%s", device_id)


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
