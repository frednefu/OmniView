"""F5 系统运维 — API 端点"""
from __future__ import annotations
from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user
from app.services.f5_ops_service import (
    build_virtual_server_view,
    build_pool_view,
    build_rule_view,
)
from app.schemas.f5_ops import (
    F5OpsVSItem,
    F5OpsPoolItem,
    F5OpsRuleItem,
    PaginatedF5OpsResponse,
)

router = APIRouter(prefix="/ops/f5", tags=["F5运维"])


def _paginate(items: list, page: int, size: int) -> dict:
    total = len(items)
    pages = ceil(total / size) if total > 0 else 0
    start = (page - 1) * size
    paged = items[start:start + size]
    return {"items": paged, "total": total, "page": page, "size": size, "pages": pages}


def _search(items: list, search: str, fields: list[str]) -> list:
    """对 dict 列表进行文本过滤"""
    if not search:
        return items
    q = search.lower()
    return [
        item for item in items
        if any(q in str(item.get(f, "")).lower() for f in fields)
    ]


# ══════════════════════════════════════════════════════════════════
# 端点 1：虚拟服务器
# ══════════════════════════════════════════════════════════════════

@router.get("/virtual-servers", response_model=PaginatedF5OpsResponse)
def list_virtual_servers(
    f5_device_id: int = Query(..., description="F5 设备 ID"),
    search: str = Query("", max_length=255),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    data = build_virtual_server_view(db, f5_device_id)
    if search:
        data = _search(data, search, ["vs_ip", "vs_names", "domains_text"])
        # 特殊处理：搜索域名列表
        q = search.lower()
        data = [
            d for d in data
            if q in str(d.get("vs_ip", "")).lower()
            or q in str(d.get("vs_names", "")).lower()
            or any(q in dom.get("domain_name", "").lower() for dom in d.get("domains", []))
        ]

    result = _paginate(data, page, size)
    result["items"] = [F5OpsVSItem(**item) for item in result["items"]]
    return result


# ══════════════════════════════════════════════════════════════════
# 端点 2：资源池
# ══════════════════════════════════════════════════════════════════

@router.get("/pools", response_model=PaginatedF5OpsResponse)
def list_pools(
    f5_device_id: int = Query(..., description="F5 设备 ID"),
    search: str = Query("", max_length=255),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    data = build_pool_view(db, f5_device_id)
    if search:
        q = search.lower()
        data = [
            d for d in data
            if q in d.get("pool_name", "").lower()
            or any(q in vs.lower() for vs in d.get("referenced_vs", []))
            or any(q in r.lower() for r in d.get("referenced_rules", []))
        ]

    result = _paginate(data, page, size)
    result["items"] = [F5OpsPoolItem(**item) for item in result["items"]]
    return result


# ══════════════════════════════════════════════════════════════════
# 端点 3：iRules
# ══════════════════════════════════════════════════════════════════

@router.get("/rules", response_model=PaginatedF5OpsResponse)
def list_rules(
    f5_device_id: int = Query(..., description="F5 设备 ID"),
    search: str = Query("", max_length=255),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    data = build_rule_view(db, f5_device_id)
    if search:
        q = search.lower()
        data = [
            d for d in data
            if q in d.get("rule_name", "").lower()
            or any(q in m.get("domain", "").lower() for m in d.get("domain_pool_mappings", []))
            or any(q in m.get("pool", "").lower() for m in d.get("domain_pool_mappings", []))
        ]

    result = _paginate(data, page, size)
    result["items"] = [F5OpsRuleItem(**item) for item in result["items"]]
    return result
