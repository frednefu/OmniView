from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from math import ceil

from app.database import get_db
from app.models.scan_result import ScanResult
from app.models.route_table import RouteTable
from app.models.switch import Switch
from app.schemas.scan import ScanResultOut, RouteTableOut, PaginatedResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/results", tags=["扫描结果"])


def _latest_ids_subquery(db):
    """获取每个 (IP, MAC, switch_id) 组合中最新的 scan_result id。"""
    return (
        db.query(func.max(ScanResult.id).label("max_id"))
        .group_by(ScanResult.ip_address, ScanResult.mac_address, ScanResult.switch_id)
        .subquery()
    )


def _enrich_result(row: ScanResult) -> dict:
    d = ScanResultOut.model_validate(row).model_dump()
    if row.switch:
        d["switch_name"] = row.switch.name
        d["switch_ip"] = row.switch.ip_address
    return d


def _enrich_route(row: RouteTable) -> dict:
    d = RouteTableOut.model_validate(row).model_dump()
    if row.switch:
        d["switch_name"] = row.switch.name
        d["switch_ip"] = row.switch.ip_address
    return d


@router.get("", response_model=PaginatedResponse)
def list_results(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    switch_id: int = Query(None),
    mac: str = Query("", max_length=17),
    ip: str = Query("", max_length=45),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # 只查询每个 (IP, MAC, switch) 组合中最新的记录
    latest = _latest_ids_subquery(db)
    base = db.query(ScanResult).filter(
        ScanResult.id.in_(db.query(latest.c.max_id))
    )
    if switch_id:
        base = base.filter(ScanResult.switch_id == switch_id)
    if mac:
        base = base.filter(ScanResult.mac_address.contains(mac))
    if ip:
        base = base.filter(ScanResult.ip_address.contains(ip))
    total = base.count()
    pages = ceil(total / size) if total > 0 else 0
    items = (
        base.options(joinedload(ScanResult.switch))
        .order_by(ScanResult.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return PaginatedResponse(
        items=[_enrich_result(r) for r in items],
        total=total, page=page, size=size, pages=pages,
    )


@router.get("/routes", response_model=PaginatedResponse)
def list_routes(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    switch_id: int = Query(None),
    cidr: str = Query("", max_length=49),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    base = db.query(RouteTable)
    if switch_id:
        base = base.filter(RouteTable.switch_id == switch_id)
    if cidr:
        base = base.filter(RouteTable.cidr.contains(cidr))
    total = base.count()
    pages = ceil(total / size) if total > 0 else 0
    items = (
        base.options(joinedload(RouteTable.switch))
        .order_by(RouteTable.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return PaginatedResponse(
        items=[_enrich_route(r) for r in items],
        total=total, page=page, size=size, pages=pages,
    )
