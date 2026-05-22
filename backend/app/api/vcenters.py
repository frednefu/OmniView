"""vCenter 管理 API — CRUD + 扫描 + VM 清单查询。"""
from math import ceil
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.vcenter import VCenter
from app.models.vm_inventory import VMInventory
from app.schemas.vcenter import (
    VCenterCreate, VCenterUpdate, VCenterOut,
    VCenterTestRequest, VCenterTestResponse, VMInventoryOut,
)
from app.schemas.scan import PaginatedResponse
from app.api.deps import get_current_user, require_admin
from app.services.vcenter_scanner_service import trigger_vcenter_scan, test_vcenter_connection
from app.services.scheduler_service import refresh_vcenter_job

router = APIRouter(prefix="/vcenters", tags=["vCenter"])


def _enrich_vm(vm: VMInventory) -> dict:
    d = VMInventoryOut.model_validate(vm).model_dump()
    if vm.vcenter:
        d["vcenter_name"] = vm.vcenter.name
        d["vcenter_host"] = vm.vcenter.host
    return d


# ─── 静态路由（必须在 /{id} 之前） ───

@router.get("/vms")
def list_all_vms(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=256),
    vcenter_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(VMInventory)
    if vcenter_id:
        q = q.filter(VMInventory.vcenter_id == vcenter_id)
    if search:
        q = q.filter(
            (VMInventory.vm_name.contains(search)) |
            (VMInventory.ip_address.contains(search)) |
            (VMInventory.mac_address.contains(search))
        )
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(VMInventory.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[_enrich_vm(vm) for vm in items],
        total=total, page=page, size=size, pages=pages,
    )


@router.post("/test", response_model=VCenterTestResponse)
async def test_connection(
    body: VCenterTestRequest,
    current_user=Depends(get_current_user),
):
    result = await test_vcenter_connection(body.host, body.username, body.password, body.port)
    return result


@router.post("/scan-all")
async def scan_all(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    vcenters = db.query(VCenter).filter(VCenter.is_active == True).all()
    if not vcenters:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有可扫描的 vCenter")
    started = 0
    skipped = 0
    for vc in vcenters:
        if vc.last_scan_status == "running":
            skipped += 1
            continue
        await trigger_vcenter_scan(vc)
        started += 1
    return {"message": f"已触发 {started} 个 vCenter 扫描" + (f"，{skipped} 个正在扫描中跳过" if skipped else ""),
            "started": started, "skipped": skipped}


@router.delete("/all")
def delete_all(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    count = db.query(VCenter).count()
    if count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有可删除的 vCenter")
    for vc in db.query(VCenter).all():
        refresh_vcenter_job(vc.id, 0)
    db.query(VCenter).delete()
    db.commit()
    return {"message": f"已删除 {count} 个 vCenter 及关联数据", "deleted": count}


# ─── 列表 ───

@router.get("")
def list_vcenters(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=128),
    is_active: bool = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(VCenter)
    if search:
        q = q.filter(
            (VCenter.name.contains(search)) | (VCenter.host.contains(search))
        )
    if is_active is not None:
        q = q.filter(VCenter.is_active == is_active)
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(VCenter.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[VCenterOut.model_validate(vc) for vc in items],
        total=total, page=page, size=size, pages=pages,
    )


# ─── 创建 ───

@router.post("", response_model=VCenterOut)
def create_vcenter(
    body: VCenterCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    existing = db.query(VCenter).filter(VCenter.host == body.host).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="vCenter 主机地址已存在")
    vc = VCenter(**body.model_dump(), created_by=admin.id)
    db.add(vc)
    db.commit()
    db.refresh(vc)
    if vc.is_active and vc.scan_interval > 0:
        refresh_vcenter_job(vc.id, vc.scan_interval)
    return VCenterOut.model_validate(vc)


# ─── 获取详情 ───

@router.get("/{vcenter_id}", response_model=VCenterOut)
def get_vcenter(
    vcenter_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    return VCenterOut.model_validate(vc)


# ─── 更新 ───

@router.put("/{vcenter_id}", response_model=VCenterOut)
def update_vcenter(
    vcenter_id: int,
    body: VCenterUpdate,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(vc, key, val)
    db.commit()
    db.refresh(vc)
    refresh_vcenter_job(vc.id, vc.scan_interval if vc.is_active else 0)
    return VCenterOut.model_validate(vc)


# ─── 删除 ───

@router.delete("/{vcenter_id}")
def delete_vcenter(
    vcenter_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    refresh_vcenter_job(vcenter_id, 0)
    db.delete(vc)
    db.commit()
    return {"message": "vCenter 已删除"}


# ─── 触发扫描 ───

@router.post("/{vcenter_id}/scan")
async def trigger_scan(
    vcenter_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    if vc.last_scan_status == "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该 vCenter 正在扫描中")
    await trigger_vcenter_scan(vc)
    return {"message": "扫描已触发"}


# ─── 该 vCenter 的 VM 清单 ───

@router.get("/{vcenter_id}/vms")
def list_vcenter_vms(
    vcenter_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=256),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    q = db.query(VMInventory).filter(VMInventory.vcenter_id == vcenter_id)
    if search:
        q = q.filter(
            (VMInventory.vm_name.contains(search)) |
            (VMInventory.ip_address.contains(search))
        )
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(VMInventory.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[_enrich_vm(vm) for vm in items],
        total=total, page=page, size=size, pages=pages,
    )
