"""信息资产管理 Schemas"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class VMAssetOut(BaseModel):
    id: int
    vm_name: str
    ip_address: str
    mac_address: str
    vm_folder: str
    os_name: Optional[str] = None
    power_state: Optional[str] = None
    vcenter_name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    claim_status: str = "unlinked"
    claimed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DomainAssetOut(BaseModel):
    domain_name: str
    record_type: Optional[str] = None
    ip_address: Optional[str] = None
    source: str  # "ZDNS" or "F5"
    vm_name: Optional[str] = None
    vm_id: Optional[int] = None


class AssetSearchRequest(BaseModel):
    keyword: str


class AssetSearchResult(BaseModel):
    asset_type: str  # "vm" or "domain"
    id: Optional[int] = None
    name: str
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    vm_folder: Optional[str] = None
    department_name: Optional[str] = None
    claim_status: Optional[str] = None


class ClaimRequest(BaseModel):
    vm_ids: List[int] = []
    department_id: Optional[int] = None  # 管理员可选


class AssignRequest(BaseModel):
    vm_ids: List[int]
    department_id: Optional[int] = None
    user_id: Optional[int] = None


class MatchPreviewItem(BaseModel):
    vm_id: int
    vm_name: str
    vm_folder: str
    matched_segment: str
    matched_dept_id: int
    matched_dept_name: str


class AutoMatchPreview(BaseModel):
    items: List[MatchPreviewItem]
    total_vms: int
    matched_count: int


class AutoMatchResult(BaseModel):
    total_vms: int
    matched: int
    failed: int
    details: List[dict] = []
    errors: List[str] = []
    message: str = ""
