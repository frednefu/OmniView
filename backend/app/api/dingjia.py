"""鼎甲备份管理 API。"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models.dingjia import DingJiaDevice, DingJiaBackupRecord
from app.models.scan_log import ScanLog, ScanStatus, TriggerType
from app.api.deps import get_current_user, require_admin
from app.services import dingjia_scanner

router = APIRouter(prefix="/dingjia", tags=["鼎甲备份"])


@router.get("")
def list_devices(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    search: str = Query(""), db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(DingJiaDevice)
    if search:
        q = q.filter(DingJiaDevice.name.contains(search) | DingJiaDevice.host.contains(search))
    total = q.count()
    items = q.order_by(DingJiaDevice.id).offset((page - 1) * size).limit(size).all()
    def _mask(k): return k[:4] + "****" + k[-4:] if k and len(k) > 8 else "****"
    return {"items": [{
        "id": d.id, "name": d.name, "host": d.host, "port": d.port,
        "api_key_masked": _mask(d.api_key), "access_key_masked": _mask(d.access_key),
        "scan_interval": d.scan_interval, "is_active": d.is_active,
        "last_scan_status": d.last_scan_status, "last_scan_time": d.last_scan_time.isoformat() if d.last_scan_time else None,
        "last_scan_duration": d.last_scan_duration,
    } for d in items], "total": total}


@router.get("/{dev_id}")
def get_device(dev_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    dev = db.query(DingJiaDevice).get(dev_id)
    if not dev: raise HTTPException(404, "设备不存在")
    return {"id": dev.id, "name": dev.name, "host": dev.host, "port": dev.port,
            "api_key": dev.api_key, "access_key": dev.access_key,
            "scan_interval": dev.scan_interval, "is_active": dev.is_active}


@router.post("")
def create_device(body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    dev = DingJiaDevice(
        name=body["name"], host=body["host"], api_key=body["api_key"],
        access_key=body["access_key"], port=body.get("port", 80),
        scan_interval=body.get("scan_interval", 86400),
    )
    db.add(dev); db.commit(); db.refresh(dev)
    return {"id": dev.id, "message": "设备已创建"}


@router.put("/{dev_id}")
def update_device(dev_id: int, body: dict, db: Session = Depends(get_db), _=Depends(require_admin)):
    dev = db.query(DingJiaDevice).get(dev_id)
    if not dev: raise HTTPException(404, "设备不存在")
    for k in ["name","host","port","scan_interval","is_active"]:
        if k in body: setattr(dev, k, body[k])
    for k in ["api_key","access_key"]:
        if k in body and body[k]: setattr(dev, k, body[k])
    db.commit()
    return {"message": "已更新"}


@router.delete("/{dev_id}")
def delete_device(dev_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    db.query(DingJiaDevice).filter(DingJiaDevice.id == dev_id).delete()
    db.query(DingJiaBackupRecord).filter(DingJiaBackupRecord.device_id == dev_id).delete()
    db.commit()
    return {"message": "已删除"}


@router.post("/test")
def test_conn(body: dict, _=Depends(require_admin)):
    return dingjia_scanner.test_connection(body["host"], body["api_key"], body["access_key"])


@router.post("/{dev_id}/scan")
def scan_device(dev_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    dev = db.query(DingJiaDevice).get(dev_id)
    if not dev: raise HTTPException(404, "设备不存在")

    from datetime import timezone as dt_timezone, timedelta as dt_timedelta
    tz = dt_timezone(dt_timedelta(hours=8))
    now8 = datetime.now(tz).replace(tzinfo=None)
    scan_log = ScanLog(source_type="dingjia", source_id=dev_id, source_name=dev.name,
                       triggered_by=TriggerType.manual, status=ScanStatus.queued, started_at=now8)
    db.add(scan_log); db.commit(); db.refresh(scan_log)

    from app.tasks.scan_tasks import scan_dingjia_task
    scan_dingjia_task.delay(dev_id, scan_log.id)
    return {"message": "扫描任务已提交，请稍后查看扫描日志", "scan_log_id": scan_log.id}


# 允许排序的列名白名单（防 SQL 注入）
_SORTABLE_COLS = {
    "vm_name", "vm_size_gb", "backup_versions", "backup_subtype",
    "last_run_result", "last_run_time", "last_completed_time",
    "next_run_time", "host_ip", "job_name", "backup_type", "state",
}

@router.get("/{dev_id}/records")
def list_records(
    dev_id: int, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    search: str = Query(""), sort_field: str = Query(""),
    sort_order: str = Query("desc", max_length=4),
    db: Session = Depends(get_db), _=Depends(get_current_user),
):
    q = db.query(DingJiaBackupRecord).filter(DingJiaBackupRecord.device_id == dev_id)
    if search:
        q = q.filter(
            DingJiaBackupRecord.job_name.contains(search) |
            DingJiaBackupRecord.host_name.contains(search) |
            DingJiaBackupRecord.vm_name.contains(search)
        )
    total = q.count()
    # 排序
    if sort_field and sort_field in _SORTABLE_COLS:
        col = getattr(DingJiaBackupRecord, sort_field, None)
        if col is not None:
            q = q.order_by(col.desc()) if sort_order == "desc" else q.order_by(col.asc())
        else:
            q = q.order_by(DingJiaBackupRecord.id.desc())
    else:
        q = q.order_by(DingJiaBackupRecord.id.desc())
    items = q.offset((page - 1) * size).limit(size).all()
    return {"items": [{
        "id": r.id, "job_name": r.job_name, "host_name": r.host_name, "host_ip": r.host_ip,
        "vm_name": r.vm_name, "backup_type": r.backup_type, "backup_subtype": r.backup_subtype,
        "agent": r.agent, "state": r.state, "last_run_result": r.last_run_result,
        "last_run_time": r.last_run_time.isoformat() if r.last_run_time else None,
        "last_completed_time": r.last_completed_time.isoformat() if r.last_completed_time else None,
        "next_run_time": r.next_run_time.isoformat() if r.next_run_time else None,
        "backup_versions": r.backup_versions, "vm_size_gb": r.vm_size_gb,
    } for r in items], "total": total}
