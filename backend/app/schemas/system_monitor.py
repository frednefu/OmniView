"""系统监控 — Pydantic Schema"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


# ═══════════ 资产关联 ═══════════

class AssetLinkCreate(BaseModel):
    asset_type: str
    asset_key: str
    asset_label: str = ""
    notes: str = ""


class AssetLinkBatch(BaseModel):
    assets: list[AssetLinkCreate]


class AssetLinkOut(BaseModel):
    id: int
    info_system_id: int
    asset_type: str
    asset_key: str
    asset_label: str = ""
    notes: str = ""
    created_by: Optional[int] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class AssetWithStatus(AssetLinkOut):
    """关联资产 + 实时运行状态"""
    status: str = "unknown"       # up / down / unknown
    status_label: str = ""        # 运行中 / 已关机 / 离线 / ...
    status_detail: str = ""       # 补充信息


# ═══════════ 系统列表 ═══════════

class SystemSummary(BaseModel):
    id: int
    system_name: str
    dept_name: str = ""
    asset_count: int = 0
    abnormal_count: int = 0
    status: str = "normal"  # normal / warning / critical


# ═══════════ 拓扑 ═══════════

class TopoNode(BaseModel):
    name: str
    category: str = ""     # system / domain / vm / f5_vs / f5_member / backup / qax
    label: str = ""        # 显示标签
    status: str = "unknown"
    status_label: str = ""


class TopoLink(BaseModel):
    source: str
    target: str
    label: str = ""


class TopologyData(BaseModel):
    nodes: list[TopoNode] = []
    links: list[TopoLink] = []


# ═══════════ 全局总览 ═══════════

class MonitorOverview(BaseModel):
    total_systems: int = 0
    normal_count: int = 0
    warning_count: int = 0
    critical_count: int = 0
    systems: list[SystemSummary] = []


# ═══════════ 资产搜索 ═══════════

class AssetSearchResult(BaseModel):
    """添加关联时搜索资产的返回结构"""
    items: list[dict] = []
    total: int = 0
