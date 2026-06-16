"""vCenter 管理 API — CRUD + 扫描 + VM 清单查询。"""
from math import ceil
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.vcenter import VCenter
from app.models.vm_inventory import VMInventory
from app.models.esxi_host import EsxiHost
from app.models.datastore import Datastore
from app.schemas.vcenter import (
    VCenterCreate, VCenterUpdate, VCenterOut,
    VCenterTestRequest, VCenterTestResponse, VMInventoryOut,
    EsxiHostOut, DatastoreOut,
)
from app.schemas.scan import PaginatedResponse
from app.api.deps import get_current_user, require_admin
from app.services.vcenter_scanner_service import trigger_vcenter_scan, test_vcenter_connection
from app.services.scheduler_service import refresh_vcenter_job
from app.utils.export import export_to_excel

router = APIRouter(prefix="/vcenters", tags=["vCenter"])


import re
from sqlalchemy.sql.elements import ColumnElement

def _enrich_vm(vm: VMInventory) -> dict:
    d = VMInventoryOut.model_validate(vm).model_dump()
    if vm.vcenter:
        d["vcenter_name"] = vm.vcenter.name
        d["vcenter_host"] = vm.vcenter.host
    return d


_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

def _is_complete_ip(s: str) -> bool:
    return bool(_IP_RE.match(s))

def _apply_search_filter(query, model, search: str):
    """智能搜索：完整 IP → 精确匹配；否则 → 模糊匹配。"""
    if _is_complete_ip(search):
        if hasattr(model, "ip_address"):
            return query.filter(model.ip_address == search)
        return query.filter(
            model.vm_name.contains(search)
            | model.ip_address.contains(search)
            | model.mac_address.contains(search)
            | model.os_name.contains(search)
            | model.cluster.contains(search)
            | model.esxi_host.contains(search)
            | model.network_name.contains(search)
            | model.vm_folder.contains(search)
        )
    return query.filter(
        model.vm_name.contains(search)
        | model.ip_address.contains(search)
        | model.mac_address.contains(search)
        | model.os_name.contains(search)
        | model.cluster.contains(search)
        | model.esxi_host.contains(search)
        | model.network_name.contains(search)
        | model.vm_folder.contains(search)
    )


# ─── 静态路由（必须在 /{id} 之前） ───

@router.get("/vms")
def list_all_vms(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=256),
    vcenter_id: int = Query(None),
    power_state: str = Query(""),
    os_name: str = Query(""),
    network_name: str = Query(""),
    vm_folder: str = Query(""),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(VMInventory)
    if vcenter_id:
        q = q.filter(VMInventory.vcenter_id == vcenter_id)
    if search:
        q = _apply_search_filter(q, VMInventory, search)
    if power_state:
        q = q.filter(VMInventory.power_state == power_state)
    if os_name:
        q = q.filter(VMInventory.os_name.contains(os_name))
    if network_name:
        q = q.filter(VMInventory.network_name.contains(network_name))
    if vm_folder:
        q = q.filter(VMInventory.vm_folder.contains(vm_folder))
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(VMInventory.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[_enrich_vm(vm) for vm in items],
        total=total, page=page, size=size, pages=pages,
    )


@router.get("/vms/export")
def export_all_vms(
    search: str = Query("", max_length=256),
    vcenter_id: int = Query(None),
    power_state: str = Query(""),
    os_name: str = Query(""),
    network_name: str = Query(""),
    vm_folder: str = Query(""),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    q = db.query(VMInventory)
    if vcenter_id:
        q = q.filter(VMInventory.vcenter_id == vcenter_id)
    if search:
        q = _apply_search_filter(q, VMInventory, search)
    if power_state:
        q = q.filter(VMInventory.power_state == power_state)
    if os_name:
        q = q.filter(VMInventory.os_name.contains(os_name))
    if network_name:
        q = q.filter(VMInventory.network_name.contains(network_name))
    if vm_folder:
        q = q.filter(VMInventory.vm_folder.contains(vm_folder))
    items = q.order_by(VMInventory.id).all()
    enriched = [_enrich_vm(vm) for vm in items]
    headers = ["vCenter名称", "vCenter主机", "数据中心", "集群", "ESXi主机", "资源池", "文件夹",
               "虚拟机名称", "电源状态", "IP地址", "MAC地址", "网络", "VLAN",
               "操作系统", "CPU", "内存(GB)", "备注"]
    xls_rows = [[
        r.get("vcenter_name", ""), r.get("vcenter_host", ""),
        r.get("datacenter", ""), r.get("cluster", ""), r.get("esxi_host", ""),
        r.get("resource_pool", ""), r.get("vm_folder", ""),
        r.get("vm_name", ""), r.get("power_state", ""),
        r.get("ip_address", ""), r.get("mac_address", ""),
        r.get("network_name", ""), r.get("vlan_id", ""),
        r.get("os_name", ""), r.get("cpu_count", ""), r.get("memory_gb", ""),
        r.get("remark", ""),
    ] for r in enriched]
    return export_to_excel(headers, xls_rows, "vm_inventory.xlsx", sheet_title="VM清单")


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
            vc.last_scan_status = None
            vc.last_scan_error = "上次扫描意外中断，已自动重置"
            db.commit()
        await trigger_vcenter_scan(vc)
        started += 1
    return {"message": f"已触发 {started} 个 vCenter 扫描",
            "started": started}


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
    result = []
    for vc in items:
        d = VCenterOut.model_validate(vc).model_dump()
        d["password"] = vc.password or ""
        result.append(d)
    return PaginatedResponse(
        items=result,
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

@router.get("/{vcenter_id}")
def get_vcenter(
    vcenter_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    data = VCenterOut.model_validate(vc).model_dump()
    data["password"] = vc.password or ""
    return data


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
        vc.last_scan_status = None
        vc.last_scan_error = "上次扫描意外中断，已自动重置"
        db.commit()
    scan_log_id = await trigger_vcenter_scan(vc)
    return {"message": "扫描已触发", "scan_log_id": scan_log_id}


# ─── 取消扫描 ───

@router.post("/{vcenter_id}/cancel-scan")
def cancel_scan(
    vcenter_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    if vc.last_scan_status != "running":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前没有正在进行的扫描")
    vc.last_scan_status = None
    vc.last_scan_error = "用户手动取消"
    db.commit()
    return {"message": "扫描已取消"}


# ─── 该 vCenter 的 VM 清单 ───

@router.get("/{vcenter_id}/vms")
def list_vcenter_vms(
    vcenter_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=256),
    power_state: str = Query("", description="电源状态过滤：poweredOn/poweredOff"),
    os_name: str = Query("", description="操作系统过滤（模糊）"),
    network_name: str = Query("", description="网络名称过滤（模糊）"),
    vm_folder: str = Query("", description="文件夹过滤（模糊）"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    q = db.query(VMInventory).filter(VMInventory.vcenter_id == vcenter_id)
    if search:
        q = _apply_search_filter(q, VMInventory, search)
    if power_state:
        q = q.filter(VMInventory.power_state == power_state)
    if os_name:
        q = q.filter(VMInventory.os_name.contains(os_name))
    if network_name:
        q = q.filter(VMInventory.network_name.contains(network_name))
    if vm_folder:
        q = q.filter(VMInventory.vm_folder.contains(vm_folder))
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(VMInventory.id).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[_enrich_vm(vm) for vm in items],
        total=total, page=page, size=size, pages=pages,
    )


@router.get("/{vcenter_id}/vms/export")
def export_vcenter_vms(
    vcenter_id: int,
    search: str = Query("", max_length=256),
    power_state: str = Query(""),
    os_name: str = Query(""),
    network_name: str = Query(""),
    vm_folder: str = Query(""),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    q = db.query(VMInventory).filter(VMInventory.vcenter_id == vcenter_id)
    if search:
        q = _apply_search_filter(q, VMInventory, search)
    if power_state:
        q = q.filter(VMInventory.power_state == power_state)
    if os_name:
        q = q.filter(VMInventory.os_name.contains(os_name))
    if network_name:
        q = q.filter(VMInventory.network_name.contains(network_name))
    if vm_folder:
        q = q.filter(VMInventory.vm_folder.contains(vm_folder))
    items = q.order_by(VMInventory.id).all()
    enriched = [_enrich_vm(vm) for vm in items]
    headers = ["vCenter名称", "vCenter主机", "数据中心", "集群", "ESXi主机", "资源池", "文件夹",
               "虚拟机名称", "电源状态", "IP地址", "MAC地址", "网络", "VLAN",
               "操作系统", "CPU", "内存(GB)", "备注"]
    xls_rows = [[
        r.get("vcenter_name", ""), r.get("vcenter_host", ""),
        r.get("datacenter", ""), r.get("cluster", ""), r.get("esxi_host", ""),
        r.get("resource_pool", ""), r.get("vm_folder", ""),
        r.get("vm_name", ""), r.get("power_state", ""),
        r.get("ip_address", ""), r.get("mac_address", ""),
        r.get("network_name", ""), r.get("vlan_id", ""),
        r.get("os_name", ""), r.get("cpu_count", ""), r.get("memory_gb", ""),
        r.get("remark", ""),
    ] for r in enriched]
    vc_name = vc.name.replace(" ", "_") if vc else "unknown"
    return export_to_excel(headers, xls_rows, f"vm_{vc_name}.xlsx", sheet_title=f"{vc_name}_VM清单")


@router.get("/{vcenter_id}/vm-filter-options")
def vm_filter_options(
    vcenter_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """返回该 vCenter 下 VM 的过滤选项（电源状态、操作系统、网络、文件夹）。"""
    base = db.query(VMInventory).filter(VMInventory.vcenter_id == vcenter_id)
    power_states = sorted([
        r[0] for r in base.with_entities(VMInventory.power_state).filter(
            VMInventory.power_state != ""
        ).distinct().all() if r[0]
    ])
    os_names = sorted([
        r[0] for r in base.with_entities(VMInventory.os_name).filter(
            VMInventory.os_name != ""
        ).distinct().all() if r[0]
    ])
    networks = sorted([
        r[0] for r in base.with_entities(VMInventory.network_name).filter(
            VMInventory.network_name != ""
        ).distinct().all() if r[0]
    ])
    folders = sorted([
        r[0] for r in base.with_entities(VMInventory.vm_folder).filter(
            VMInventory.vm_folder != ""
        ).distinct().all() if r[0]
    ])
    return {
        "power_states": power_states,
        "os_names": os_names,
        "networks": networks,
        "folders": folders,
    }


# ─── ESXi 主机清单 ───

@router.get("/{vcenter_id}/hosts")
def list_vcenter_hosts(
    vcenter_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    hosts = db.query(EsxiHost).filter(EsxiHost.vcenter_id == vcenter_id).order_by(EsxiHost.host_name).all()
    return {"items": [EsxiHostOut.model_validate(h) for h in hosts], "total": len(hosts)}


# ─── 存储器清单 ───

@router.get("/{vcenter_id}/datastores")
def list_vcenter_datastores(
    vcenter_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    vc = db.query(VCenter).get(vcenter_id)
    if not vc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vCenter 不存在")
    datastores = db.query(Datastore).filter(Datastore.vcenter_id == vcenter_id).order_by(Datastore.datastore_name).all()
    return {"items": [DatastoreOut.model_validate(ds) for ds in datastores], "total": len(datastores)}
