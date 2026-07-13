from math import ceil
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.history import History, ChangeType
from app.schemas.history import HistoryOut
from app.schemas.scan import PaginatedResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/history", tags=["历史记录"])


def _enrich(row: History) -> dict:
    # 解析 change_detail JSON 字符串 → dict
    if row.change_detail is not None and isinstance(row.change_detail, str):
        import json
        try:
            row.change_detail = json.loads(row.change_detail)
        except (json.JSONDecodeError, TypeError):
            row.change_detail = None
    d = HistoryOut.model_validate(row).model_dump()
    if row.switch:
        d["switch_name"] = row.switch.name
        d["switch_ip"] = row.switch.ip_address
    return d


@router.get("", response_model=PaginatedResponse)
def list_history(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    source_type: str = Query(None),
    source_id: int = Query(None),
    source_name: str = Query(None, max_length=255),
    switch_id: int = Query(None),
    change_type: str = Query(None),
    ip: str = Query("", max_length=45),
    mac: str = Query("", max_length=17),
    vm_name: str = Query("", max_length=255),
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    base = db.query(History)
    if source_type:
        base = base.filter(History.source_type == source_type)
    if source_id:
        base = base.filter(History.source_id == source_id)
    if source_name:
        base = base.filter(History.source_name == source_name)
    if switch_id:
        base = base.filter(History.switch_id == switch_id)
    if change_type:
        base = base.filter(History.change_type == change_type)
    if ip:
        # IP 搜索同时匹配 ip_address、dedup_key（域名）和 change_detail
        base = base.filter(
            History.ip_address.contains(ip) |
            History.dedup_key.contains(ip) |
            History.change_detail.contains(ip)
        )
    if mac:
        base = base.filter(History.mac_address.contains(mac))
    if vm_name:
        base = base.filter(History.change_detail.contains(vm_name))
    if start_date:
        base = base.filter(History.created_at >= start_date)
    if end_date:
        base = base.filter(History.created_at <= end_date)

    total = base.count()
    pages = ceil(total / size) if total > 0 else 0
    items = (
        base.options(joinedload(History.switch))
        .order_by(History.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return PaginatedResponse(
        items=[_enrich(r) for r in items],
        total=total, page=page, size=size, pages=pages,
    )


@router.get("/ip/{ip}", response_model=list[HistoryOut])
def history_by_ip(
    ip: str,
    source_type: str = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    base = db.query(History).filter(History.ip_address == ip)
    if source_type:
        base = base.filter(History.source_type == source_type)
    rows = (
        base.options(joinedload(History.switch))
        .order_by(History.id.desc())
        .limit(200)
        .all()
    )
    return [_enrich(r) for r in rows]


@router.get("/mac/{mac}", response_model=list[HistoryOut])
def history_by_mac(
    mac: str,
    source_type: str = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    base = db.query(History).filter(History.mac_address == mac)
    if source_type:
        base = base.filter(History.source_type == source_type)
    rows = (
        base.options(joinedload(History.switch))
        .order_by(History.id.desc())
        .limit(200)
        .all()
    )
    return [_enrich(r) for r in rows]
