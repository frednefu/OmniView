from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models.scan_result import ScanResult
from app.schemas.scan import ScanResultOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/search", tags=["搜索"])


@router.get("", response_model=list[ScanResultOut])
def search(
    q: str = Query(..., min_length=2, max_length=64),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    results = db.query(ScanResult).filter(
        or_(
            ScanResult.ip_address.contains(q),
            ScanResult.mac_address.contains(q),
        )
    ).order_by(ScanResult.id.desc()).limit(limit).all()
    return [ScanResultOut.model_validate(r) for r in results]
