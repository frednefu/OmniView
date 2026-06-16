"""奇安信椒图管理 API — CRUD + 扫描 + 服务器数据查询。"""
from math import ceil
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.qax import QianXinDevice, QianXinServer, QianXinPort, QianXinProcess, QianXinSoftware
from app.schemas.qax import (
    QianXinDeviceCreate, QianXinDeviceUpdate, QianXinDeviceOut,
    QAXTestRequest, QAXTestResponse,
    QianXinServerOut, QianXinPortOut, QianXinProcessOut, QianXinSoftwareOut,
)
from app.schemas.scan import PaginatedResponse
from app.api.deps import get_current_user, require_admin
from app.services.qax_scanner_service import trigger_qax_scan, test_qax_connection
from app.services.scheduler_service import refresh_qax_job

router = APIRouter(prefix="/qax", tags=["QAX"])


# ─── 静态路由（必须在 /{id} 之前） ───

@router.post("/test", response_model=QAXTestResponse)
async def test_connection(
    body: QAXTestRequest,
    current_user=Depends(get_current_user),
):
    result = await test_qax_connection(body.host, body.uuid, body.secret)
    return result


@router.post("/scan-all")
async def scan_all(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    devices = db.query(QianXinDevice).filter(QianXinDevice.enabled == True).all()
    if not devices:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有可扫描的椒图设备")
    started = 0
    skipped = 0
    for dev in devices:
        if dev.last_scan_status == "running":
            dev.last_scan_status = None
            dev.last_scan_error = "上次扫描意外中断，已自动重置"
            db.commit()
        await trigger_qax_scan(dev)
        started += 1
    return {"message": f"已触发 {started} 个椒图扫描",
            "started": started}


@router.delete("/all")
def delete_all(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    count = db.query(QianXinDevice).count()
    if count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有可删除的椒图设备")
    for dev in db.query(QianXinDevice).all():
        refresh_qax_job(dev.id, 0)
    db.query(QianXinDevice).delete()
    db.commit()
    return {"message": f"已删除 {count} 个椒图设备及关联数据", "deleted": count}


# ─── 列表 ───

@router.get("")
def list_devices(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    search: str = Query("", max_length=128),
    enabled: bool = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(QianXinDevice)
    if search:
        q = q.filter(
            (QianXinDevice.name.contains(search)) | (QianXinDevice.host.contains(search))
        )
    if enabled is not None:
        q = q.filter(QianXinDevice.enabled == enabled)
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(QianXinDevice.id).offset((page - 1) * size).limit(size).all()
    result = []
    for dev in items:
        d = QianXinDeviceOut.model_validate(dev).model_dump()
        d["secret"] = dev.secret or ""
        result.append(d)
    return PaginatedResponse(
        items=result,
        total=total, page=page, size=size, pages=pages,
    )


# ─── 创建 ───

@router.post("", response_model=QianXinDeviceOut)
def create_device(
    body: QianXinDeviceCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    existing = db.query(QianXinDevice).filter(QianXinDevice.host == body.host).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="椒图主机地址已存在")
    dev = QianXinDevice(**body.model_dump(), created_by=admin.id)
    db.add(dev)
    db.commit()
    db.refresh(dev)
    if dev.enabled and dev.scan_interval > 0:
        refresh_qax_job(dev.id, dev.scan_interval)
    return QianXinDeviceOut.model_validate(dev)


# ─── 获取详情 ───

@router.get("/{device_id}")
def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(QianXinDevice).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="椒图设备不存在")
    data = QianXinDeviceOut.model_validate(dev).model_dump()
    data["secret"] = dev.secret or ""
    return data


# ─── 更新 ───

@router.put("/{device_id}", response_model=QianXinDeviceOut)
def update_device(
    device_id: int,
    body: QianXinDeviceUpdate,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    dev = db.query(QianXinDevice).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="椒图设备不存在")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(dev, key, val)
    db.commit()
    db.refresh(dev)
    refresh_qax_job(dev.id, dev.scan_interval if dev.enabled else 0)
    return QianXinDeviceOut.model_validate(dev)


# ─── 删除 ───

@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    dev = db.query(QianXinDevice).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="椒图设备不存在")
    refresh_qax_job(device_id, 0)
    db.delete(dev)
    db.commit()
    return {"message": "椒图设备已删除"}


# ─── 触发扫描 ───

@router.post("/{device_id}/scan")
async def trigger_scan(
    device_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    dev = db.query(QianXinDevice).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="椒图设备不存在")
    if dev.last_scan_status == "running":
        dev.last_scan_status = None
        dev.last_scan_error = None
        db.commit()
    scan_log_id = await trigger_qax_scan(dev)
    return {"message": "扫描已触发", "scan_log_id": scan_log_id}


# ─── 取消扫描 ───

@router.post("/{device_id}/cancel-scan")
def cancel_scan(
    device_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    dev = db.query(QianXinDevice).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="椒图设备不存在")
    if dev.last_scan_status != "running":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前没有正在进行的扫描")
    dev.last_scan_status = None
    dev.last_scan_error = "用户手动取消"
    db.commit()
    return {"message": "扫描已取消"}


# ─── 服务器清单 ───

@router.get("/{device_id}/servers")
def list_servers(
    device_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(QianXinDevice).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="椒图设备不存在")
    q = db.query(QianXinServer).filter(QianXinServer.device_id == device_id)
    if search:
        q = q.filter(
            (QianXinServer.machine_name.contains(search)) |
            (QianXinServer.ipv4.contains(search)) |
            (QianXinServer.intranet_ip.contains(search)) |
            (QianXinServer.operation_system.contains(search)) |
            (QianXinServer.machine_group.contains(search))
        )
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(QianXinServer.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[QianXinServerOut.model_validate(s) for s in items],
        total=total, page=page, size=size, pages=pages,
    )


# ─── 端口列表 ───

@router.get("/{device_id}/servers/{server_id}/ports")
def list_ports(
    device_id: int,
    server_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _check_device(db, device_id)
    q = db.query(QianXinPort).filter(
        QianXinPort.device_id == device_id,
        QianXinPort.server_id == server_id,
    )
    if search:
        q = q.filter(
            (QianXinPort.port.contains(search)) |
            (QianXinPort.process_name.contains(search)) |
            (QianXinPort.start_user.contains(search))
        )
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(QianXinPort.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[QianXinPortOut.model_validate(p) for p in items],
        total=total, page=page, size=size, pages=pages,
    )


# ─── 进程列表 ───

@router.get("/{device_id}/servers/{server_id}/processes")
def list_processes(
    device_id: int,
    server_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _check_device(db, device_id)
    q = db.query(QianXinProcess).filter(
        QianXinProcess.device_id == device_id,
        QianXinProcess.server_id == server_id,
    )
    if search:
        q = q.filter(
            (QianXinProcess.process_name.contains(search)) |
            (QianXinProcess.pid.contains(search)) |
            (QianXinProcess.start_user.contains(search))
        )
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(QianXinProcess.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[QianXinProcessOut.model_validate(p) for p in items],
        total=total, page=page, size=size, pages=pages,
    )


# ─── 软件列表 ───

@router.get("/{device_id}/servers/{server_id}/software")
def list_software(
    device_id: int,
    server_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _check_device(db, device_id)
    q = db.query(QianXinSoftware).filter(
        QianXinSoftware.device_id == device_id,
        QianXinSoftware.server_id == server_id,
    )
    if search:
        q = q.filter(
            (QianXinSoftware.software_name.contains(search)) |
            (QianXinSoftware.version.contains(search)) |
            (QianXinSoftware.install_path.contains(search))
        )
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(QianXinSoftware.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[QianXinSoftwareOut.model_validate(s) for s in items],
        total=total, page=page, size=size, pages=pages,
    )


def _check_device(db: Session, device_id: int):
    dev = db.query(QianXinDevice).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="椒图设备不存在")
