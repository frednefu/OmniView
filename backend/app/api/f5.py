"""F5 负载均衡器管理 API — CRUD + 扫描 + 应用映射查询。"""
from math import ceil
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.f5 import F5Device, F5VirtualServer, F5PoolMember, F5Rule, F5ApplicationMap
from app.schemas.f5 import (
    F5DeviceCreate, F5DeviceUpdate, F5DeviceOut,
    F5TestRequest, F5TestResponse,
    F5VirtualServerOut, F5PoolMemberOut, F5RuleOut, F5ApplicationMapOut,
)
from app.schemas.scan import PaginatedResponse
from app.api.deps import get_current_user, require_admin
from app.services.f5_scanner_service import trigger_f5_scan, test_f5_connection
from app.services.scheduler_service import refresh_f5_job
from app.utils.export import export_to_excel

router = APIRouter(prefix="/f5", tags=["F5"])


# ─── 静态路由（必须在 /{id} 之前） ───

@router.post("/test", response_model=F5TestResponse)
async def test_connection(
    body: F5TestRequest,
    current_user=Depends(get_current_user),
):
    result = await test_f5_connection(body.host, body.username, body.password, body.port)
    return result


@router.post("/scan-all")
async def scan_all(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    devices = db.query(F5Device).filter(F5Device.is_active == True).all()
    if not devices:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有可扫描的 F5 设备")
    started = 0
    skipped = 0
    for dev in devices:
        if dev.last_scan_status == "running":
            dev.last_scan_status = None
            dev.last_scan_error = "上次扫描意外中断，已自动重置"
            db.commit()
        await trigger_f5_scan(dev)
        started += 1
    return {"message": f"已触发 {started} 个 F5 扫描",
            "started": started}


@router.delete("/all")
def delete_all(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    count = db.query(F5Device).count()
    if count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有可删除的 F5 设备")
    for dev in db.query(F5Device).all():
        refresh_f5_job(dev.id, 0)
    db.query(F5Device).delete()
    db.commit()
    return {"message": f"已删除 {count} 个 F5 设备及关联数据", "deleted": count}


# ─── 列表 ───

@router.get("")
def list_devices(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    search: str = Query("", max_length=128),
    is_active: bool = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(F5Device)
    if search:
        q = q.filter(
            (F5Device.name.contains(search)) | (F5Device.host.contains(search))
        )
    if is_active is not None:
        q = q.filter(F5Device.is_active == is_active)
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(F5Device.id).offset((page - 1) * size).limit(size).all()
    result = []
    for dev in items:
        d = F5DeviceOut.model_validate(dev).model_dump()
        d["password"] = dev.password or ""
        result.append(d)
    return PaginatedResponse(
        items=result,
        total=total, page=page, size=size, pages=pages,
    )


# ─── 创建 ───

@router.post("", response_model=F5DeviceOut)
def create_device(
    body: F5DeviceCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    existing = db.query(F5Device).filter(F5Device.host == body.host).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="F5 主机地址已存在")
    dev = F5Device(**body.model_dump(), created_by=admin.id)
    db.add(dev)
    db.commit()
    db.refresh(dev)
    if dev.is_active and dev.scan_interval > 0:
        refresh_f5_job(dev.id, dev.scan_interval)
    return F5DeviceOut.model_validate(dev)


# ─── 获取详情 ───

@router.get("/{device_id}")
def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    data = F5DeviceOut.model_validate(dev).model_dump()
    data["password"] = dev.password or ""
    return data


# ─── 更新 ───

@router.put("/{device_id}", response_model=F5DeviceOut)
def update_device(
    device_id: int,
    body: F5DeviceUpdate,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(dev, key, val)
    db.commit()
    db.refresh(dev)
    refresh_f5_job(dev.id, dev.scan_interval if dev.is_active else 0)
    return F5DeviceOut.model_validate(dev)


# ─── 删除 ───

@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    refresh_f5_job(device_id, 0)
    db.delete(dev)
    db.commit()
    return {"message": "F5 设备已删除"}


# ─── 触发扫描 ───

@router.post("/{device_id}/scan")
async def trigger_scan(
    device_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    if dev.last_scan_status == "running":
        dev.last_scan_status = None
        dev.last_scan_error = None
        db.commit()
    scan_log_id = await trigger_f5_scan(dev)
    return {"message": "扫描已触发", "scan_log_id": scan_log_id}


# ─── 取消扫描 ───

@router.post("/{device_id}/cancel-scan")
def cancel_scan(
    device_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    if dev.last_scan_status != "running":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前没有正在进行的扫描")
    dev.last_scan_status = None
    dev.last_scan_error = "用户手动取消"
    db.commit()
    return {"message": "扫描已取消"}


# ─── 虚拟服务器清单 ───

@router.get("/{device_id}/virtual-servers")
def list_virtual_servers(
    device_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    q = db.query(F5VirtualServer).filter(F5VirtualServer.f5_device_id == device_id)
    if search:
        q = q.filter(
            (F5VirtualServer.name.contains(search)) |
            (F5VirtualServer.vs_ip.contains(search)) |
            (F5VirtualServer.destination.contains(search)) |
            (F5VirtualServer.pool_name.contains(search))
        )
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(F5VirtualServer.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[F5VirtualServerOut.model_validate(vs) for vs in items],
        total=total, page=page, size=size, pages=pages,
    )


# ─── Pool 成员清单 ───

@router.get("/{device_id}/pool-members")
def list_pool_members(
    device_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    q = db.query(F5PoolMember).filter(F5PoolMember.f5_device_id == device_id)
    if search:
        q = q.filter(
            (F5PoolMember.pool_name.contains(search)) |
            (F5PoolMember.member_name.contains(search)) |
            (F5PoolMember.member_ip.contains(search))
        )
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(F5PoolMember.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[F5PoolMemberOut.model_validate(pm) for pm in items],
        total=total, page=page, size=size, pages=pages,
    )


# ─── iRules 清单 ───

@router.get("/{device_id}/rules")
def list_rules(
    device_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=500),
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    q = db.query(F5Rule).filter(F5Rule.f5_device_id == device_id)
    if search:
        q = q.filter(
            (F5Rule.rule_name.contains(search)) |
            (F5Rule.rule_content.contains(search))
        )
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(F5Rule.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[F5RuleOut.model_validate(r) for r in items],
        total=total, page=page, size=size, pages=pages,
    )


# ─── 应用映射清单（核心交付物） ───

@router.get("/{device_id}/application-map")
def list_application_map(
    device_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    q = db.query(F5ApplicationMap).filter(F5ApplicationMap.f5_device_id == device_id)
    if search:
        q = q.filter(
            (F5ApplicationMap.domain_name.contains(search)) |
            (F5ApplicationMap.vs_name.contains(search)) |
            (F5ApplicationMap.vs_ip.contains(search)) |
            (F5ApplicationMap.pool_name.contains(search)) |
            (F5ApplicationMap.member_ip.contains(search)) |
            (F5ApplicationMap.rule_name.contains(search))
        )
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(F5ApplicationMap.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[F5ApplicationMapOut.model_validate(r) for r in items],
        total=total, page=page, size=size, pages=pages,
    )


# ─── 导出端点 ───

@router.get("/{device_id}/virtual-servers/export")
def export_virtual_servers(
    device_id: int,
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    q = db.query(F5VirtualServer).filter(F5VirtualServer.f5_device_id == device_id)
    if search:
        q = q.filter(
            (F5VirtualServer.name.contains(search)) |
            (F5VirtualServer.vs_ip.contains(search)) |
            (F5VirtualServer.destination.contains(search)) |
            (F5VirtualServer.pool_name.contains(search))
        )
    items = q.order_by(F5VirtualServer.id).all()
    headers = ["名称", "目标地址", "VS IP", "VS 端口", "Pool", "iRules"]
    xls_rows = [[
        r.name, r.destination, r.vs_ip,
        str(r.vs_port) if r.vs_port is not None else "",
        r.pool_name, r.rules,
    ] for r in items]
    dev_name = dev.name.replace(" ", "_")
    return export_to_excel(headers, xls_rows, f"f5_vs_{dev_name}.xlsx", sheet_title=f"{dev_name}_虚拟服务器")


@router.get("/{device_id}/pool-members/export")
def export_pool_members(
    device_id: int,
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    q = db.query(F5PoolMember).filter(F5PoolMember.f5_device_id == device_id)
    if search:
        q = q.filter(
            (F5PoolMember.pool_name.contains(search)) |
            (F5PoolMember.member_name.contains(search)) |
            (F5PoolMember.member_ip.contains(search))
        )
    items = q.order_by(F5PoolMember.id).all()
    headers = ["Pool名称", "成员名称", "成员IP", "成员端口", "状态"]
    xls_rows = [[
        r.pool_name, r.member_name, r.member_ip,
        str(r.member_port) if r.member_port is not None else "",
        r.member_state,
    ] for r in items]
    dev_name = dev.name.replace(" ", "_")
    return export_to_excel(headers, xls_rows, f"f5_pool_{dev_name}.xlsx", sheet_title=f"{dev_name}_Pool成员")


@router.get("/{device_id}/rules/export")
def export_rules(
    device_id: int,
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    q = db.query(F5Rule).filter(F5Rule.f5_device_id == device_id)
    if search:
        q = q.filter(
            (F5Rule.rule_name.contains(search)) |
            (F5Rule.rule_content.contains(search))
        )
    items = q.order_by(F5Rule.id).all()
    headers = ["规则名称", "规则内容"]
    xls_rows = [[r.rule_name, r.rule_content or ""] for r in items]
    dev_name = dev.name.replace(" ", "_")
    return export_to_excel(headers, xls_rows, f"f5_rules_{dev_name}.xlsx", sheet_title=f"{dev_name}_iRules")


@router.get("/{device_id}/application-map/export")
def export_application_map(
    device_id: int,
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dev = db.query(F5Device).get(device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="F5 设备不存在")
    q = db.query(F5ApplicationMap).filter(F5ApplicationMap.f5_device_id == device_id)
    if search:
        q = q.filter(
            (F5ApplicationMap.domain_name.contains(search)) |
            (F5ApplicationMap.vs_name.contains(search)) |
            (F5ApplicationMap.vs_ip.contains(search)) |
            (F5ApplicationMap.pool_name.contains(search)) |
            (F5ApplicationMap.member_ip.contains(search)) |
            (F5ApplicationMap.rule_name.contains(search))
        )
    items = q.order_by(F5ApplicationMap.id).all()
    headers = ["域名", "VS名称", "VS IP", "VS 端口", "Pool", "规则名称", "成员IP", "成员端口", "成员状态", "来源"]
    xls_rows = [[
        r.domain_name, r.vs_name, r.vs_ip,
        str(r.vs_port) if r.vs_port is not None else "",
        r.pool_name, r.rule_name, r.member_ip,
        str(r.member_port) if r.member_port is not None else "",
        r.member_state, r.source,
    ] for r in items]
    dev_name = dev.name.replace(" ", "_")
    return export_to_excel(headers, xls_rows, f"f5_appmap_{dev_name}.xlsx", sheet_title=f"{dev_name}_应用映射")
