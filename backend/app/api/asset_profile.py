"""资产画像 API — 跨系统数据关联统一视图。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.asset_profile import AssetProfileResponse, AssetProfileStats, AssetProfileRow
from app.services.asset_profile_service import build_asset_profile, compute_stats, filter_sort_paginate, get_network_names, get_source_names
from app.services.cache_service import get_json, set_json
from app.api.deps import get_current_user
from app.utils.export import export_to_excel

router = APIRouter(prefix="/asset-profile", tags=["资产画像"])

ASSET_PROFILE_TTL = 300  # 资产画像缓存 5 分钟


def _get_cached_profile(db: Session) -> list[dict]:
    """获取缓存的资产画像数据，缓存命中直接返回，未命中则构建并缓存。"""
    cached = get_json("asset_profile:rows")
    if cached is not None:
        return cached

    rows = build_asset_profile(db)
    set_json("asset_profile:rows", rows, ttl=ASSET_PROFILE_TTL)
    return rows


@router.get("", response_model=AssetProfileResponse)
def get_asset_profile(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200000),
    search: str = Query("", description="全局搜索（匹配所有字段）"),
    sort_by: str = Query("", description="排序字段名（如：公网IP、虚拟机名称 等）"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    status: str = Query("", description="状态过滤：up/down/user-down"),
    network: str = Query("", description="网络名称过滤（vCenter 网络）"),
    source: str = Query("", description="来源过滤（精确匹配），如：ZDNS / F5 / ZDNS,F5,vCenter,Switch"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    rows = _get_cached_profile(db)
    stats = compute_stats(rows)
    network_names = get_network_names(rows)
    source_names = get_source_names(rows)
    result = filter_sort_paginate(
        rows, search=search, sort_by=sort_by, sort_dir=sort_dir,
        page=page, size=size, status=status, network=network, source=source,
    )

    return AssetProfileResponse(
        rows=[AssetProfileRow(**r) for r in result["rows"]],
        total=result["total"],
        page=result["page"],
        size=result["size"],
        stats=AssetProfileStats(**stats),
        network_names=network_names,
        source_names=source_names,
    )


@router.get("/export")
def export_asset_profile(
    search: str = Query("", description="全局搜索（匹配所有字段）"),
    status: str = Query("", description="状态过滤：up/down/user-down"),
    network: str = Query("", description="网络名称过滤（vCenter 网络）"),
    source: str = Query("", description="来源过滤（精确匹配）"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    rows = _get_cached_profile(db)
    filtered = filter_sort_paginate(
        rows, search=search, status=status, network=network, source=source,
        page=1, size=100000,
    )
    headers = ["域名", "来源", "公网IP", "端口", "内网服务IP", "内网端口", "状态", "虚拟机名称", "IP地址", "MAC地址", "网络", "VLAN", "文件夹", "ESXi主机", "F5_VS", "F5_Pool", "F5_Rule", "椒图主机", "椒图OS", "椒图内核", "椒图CPU", "椒图内存", "椒图磁盘", "椒图分组", "椒图状态"]
    header_key_map = {
        "ESXi主机": "esxi_host", "F5_VS": "f5_vs_name", "F5_Pool": "f5_pool_name",
        "F5_Rule": "f5_rule_name", "椒图主机": "qax_machine_name", "椒图OS": "qax_os",
        "椒图内核": "qax_kernel", "椒图CPU": "qax_cpu", "椒图内存": "qax_memory",
        "椒图磁盘": "qax_disk", "椒图分组": "qax_group", "椒图状态": "qax_online_status",
    }
    xls_rows = [[r.get(header_key_map.get(h, h), "") for h in headers] for r in filtered["rows"]]
    return export_to_excel(headers, xls_rows, "asset_profile.xlsx", sheet_title="资产画像")
