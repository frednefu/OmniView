from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.switch import Switch
from app.models.scan_result import ScanResult
from app.models.subnet import Subnet
from app.schemas.subnet import DashboardStats, SubnetUtilization, AvailableIpResponse
from app.api.deps import get_current_user
from app.services.subnet_service import get_subnet_utilization, get_available_ips

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    switch_count = db.query(func.count(Switch.id)).filter(Switch.is_active == True).scalar() or 0
    total_ips = db.query(func.count(func.distinct(ScanResult.ip_address))).filter(
        ScanResult.ip_address != ""
    ).scalar() or 0
    total_macs = db.query(func.count(func.distinct(ScanResult.mac_address))).scalar() or 0
    subnet_count = db.query(func.count(Subnet.id)).filter(Subnet.is_managed == True).scalar() or 0

    return DashboardStats(
        switch_count=switch_count,
        total_ips=total_ips,
        total_macs=total_macs,
        subnet_count=subnet_count,
    )


@router.get("/subnet-utilization", response_model=list[SubnetUtilization])
def subnet_utilization(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return [SubnetUtilization(**item) for item in get_subnet_utilization(db)]


@router.get("/available-ips", response_model=AvailableIpResponse)
def available_ips(
    subnet_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = get_available_ips(db, subnet_id, limit)
    return AvailableIpResponse(**result)
