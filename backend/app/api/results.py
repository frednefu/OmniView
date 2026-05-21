from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from math import ceil

from app.database import get_db
from app.models.scan_result import ScanResult
from app.models.route_table import RouteTable
from app.schemas.scan import ScanResultOut, RouteTableOut, PaginatedResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/results", tags=["扫描结果"])


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
    q = db.query(ScanResult)
    if switch_id:
        q = q.filter(ScanResult.switch_id == switch_id)
    if mac:
        q = q.filter(ScanResult.mac_address.contains(mac))
    if ip:
        q = q.filter(ScanResult.ip_address.contains(ip))
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(ScanResult.id.desc()).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[ScanResultOut.model_validate(r) for r in items],
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
    q = db.query(RouteTable)
    if switch_id:
        q = q.filter(RouteTable.switch_id == switch_id)
    if cidr:
        q = q.filter(RouteTable.cidr.contains(cidr))
    total = q.count()
    pages = ceil(total / size) if total > 0 else 0
    items = q.order_by(RouteTable.id.desc()).offset((page - 1) * size).limit(size).all()
    return PaginatedResponse(
        items=[RouteTableOut.model_validate(r) for r in items],
        total=total, page=page, size=size, pages=pages,
    )
