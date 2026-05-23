"""资产画像 Schema — 跨系统数据关联统一视图。"""
from pydantic import BaseModel
from typing import List, Optional


class AssetProfileRow(BaseModel):
    """资产画像单行数据"""
    域名: str = ""
    来源: str = ""
    公网IP: str = ""
    端口: str = ""
    内网服务IP: str = ""
    内网端口: str = ""
    状态: str = ""
    虚拟机名称: str = ""
    IP地址: str = ""
    MAC地址: str = ""
    网络: str = ""
    VLAN: str = ""
    文件夹: str = ""


class AssetProfileStats(BaseModel):
    """资产画像统计摘要"""
    域名数量: int = 0
    公网IP端口数量: int = 0
    虚拟机数量: int = 0
    虚拟机IP端口数量: int = 0
    vlan数量: int = 0
    文件夹数量: int = 0


class AssetProfileResponse(BaseModel):
    """资产画像分页响应"""
    rows: List[AssetProfileRow] = []
    total: int = 0
    page: int = 1
    size: int = 50
    stats: AssetProfileStats = AssetProfileStats()
    network_names: List[str] = []
    source_names: List[str] = []
