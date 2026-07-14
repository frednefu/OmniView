"""F5 系统运维 — Pydantic 响应模型"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class F5OpsDomainItem(BaseModel):
    """域名项（来自 ZDNS 域名→IP 映射，含状态标记）"""
    domain_name: str
    record_type: str = "A"  # A / AAAA
    zdns_exists: bool = True  # 域名是否在 ZDNS 中存在


class F5OpsMemberItem(BaseModel):
    """内网服务器成员"""
    ip: str
    port: Optional[int] = None
    state: str  # up / down / ...


class F5OpsInternalServer(BaseModel):
    """内网服务器分组（按 Pool + Rule 分组，合并相同成员的重复条目）"""
    pool_name: str
    rule_name: str
    domain: str = ""  # rule 中声明的域名
    source: str = ""  # "irule" | "pool"（标注来源）
    members: list[F5OpsMemberItem] = []


class F5OpsVSItem(BaseModel):
    """虚拟服务器视图项"""
    f5_device_id: int
    vs_ip: str
    vs_port: Optional[int] = None
    vs_names: str  # 逗号分隔的 VS 名称
    irules: list[str] = []  # 关联的 iRule 名称列表
    domains: list[F5OpsDomainItem] = []         # 来自 ZDNS 的域名
    internal_servers: list[F5OpsInternalServer] = []  # 内网服务器分组
    status: str = "active"  # active / partial / deregistered
    member_count: int = 0


class F5OpsPoolMember(BaseModel):
    """Pool 成员"""
    ip: str
    port: Optional[int] = None
    state: str


class F5OpsPoolItem(BaseModel):
    """资源池视图项"""
    f5_device_id: int
    pool_name: str
    status: str = "mixed"  # up / down / mixed
    ref_status: str = "none"  # none / partial / full（引用状态：无引用 / 部分引用 / 引用）
    members: list[F5OpsPoolMember] = []
    referenced_vs: list[str] = []    # 直接引用此 Pool 的 VS 名称
    referenced_rules: list[str] = []  # 引用此 Pool 的 iRule 名称
    member_count: int = 0


class F5OpsDomainPoolMapping(BaseModel):
    """Rule 中的域名→Pool 映射"""
    domain: str
    pool: str
    zdns_exists: bool = False  # 域名是否在 ZDNS 中存在


class F5OpsRuleItem(BaseModel):
    """iRule 视图项"""
    f5_device_id: int
    rule_name: str
    domain_pool_mappings: list[F5OpsDomainPoolMapping] = []
    status: str = "no_domain"  # active / partial / deregistered / no_domain
    mapping_count: int = 0


class PaginatedF5OpsResponse(BaseModel):
    """F5 运维分页响应"""
    items: list = []
    total: int = 0
    page: int = 1
    size: int = 50
    pages: int = 0
