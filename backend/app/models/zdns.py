"""ZDNS 域名服务器模型 — 设备连接 + DNS 记录 + 域名→IP 映射清单。"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from app.database import Base


class ZDNSDevice(Base):
    __tablename__ = "zdns_devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    host = Column(String(255), nullable=False, unique=True, index=True)
    username = Column(String(128), nullable=False)
    password = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False, default=20120)
    scan_interval = Column(Integer, nullable=False, default=86400)
    is_active = Column(Boolean, nullable=False, default=True)

    last_scan_status = Column(String(16), nullable=True)
    last_scan_time = Column(DateTime, nullable=True)
    last_scan_duration = Column(Float, nullable=True)
    last_record_count = Column(Integer, nullable=False, default=0)
    last_zone_count = Column(Integer, nullable=False, default=0)
    last_scan_error = Column(Text, nullable=True)

    ip_scan_interval = Column(Integer, nullable=False, default=86400)
    last_ip_scan_status = Column(String(16), nullable=True)
    last_ip_scan_time = Column(DateTime, nullable=True)
    last_ip_scan_duration = Column(Float, nullable=True)
    last_ip_scan_error = Column(Text, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    records = relationship("ZDNSRecord", back_populates="device", cascade="all, delete-orphan")
    domain_maps = relationship("ZDNSDomainMap", back_populates="device", cascade="all, delete-orphan")


class ZDNSRecord(Base):
    """ZDNS 原始 DNS 记录，每次扫描全量重建。"""
    __tablename__ = "zdns_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zdns_device_id = Column(Integer, ForeignKey("zdns_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    record_id = Column(String(255), default="")
    name = Column(String(255), default="")
    full_domain = Column(String(512), default="", index=True)
    record_type = Column(String(10), default="")
    ttl = Column(Integer, nullable=True)
    rdata = Column(String(1024), default="")
    view_name = Column(String(128), default="")
    zone_name = Column(String(255), default="")
    is_enabled = Column(String(8), default="")
    strategy = Column(String(255), default="")
    expire_time = Column(String(64), default="")
    expire_style = Column(String(32), default="")
    raw_data = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    device = relationship("ZDNSDevice", back_populates="records")


class ZDNSDomainMap(Base):
    """域名→IP 映射清单（核心交付物），仅含 A/AAAA 记录，自动分类 IPv4/IPv6 和 内网/外网。"""
    __tablename__ = "zdns_domain_map"

    id = Column(Integer, primary_key=True, autoincrement=True)
    zdns_device_id = Column(Integer, ForeignKey("zdns_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    domain_name = Column(String(512), default="", index=True)
    record_type = Column(String(10), default="")
    ip_address = Column(String(255), default="")
    ip_category = Column(String(8), default="")
    network_type = Column(String(8), default="")
    ttl = Column(Integer, nullable=True)
    view_name = Column(String(128), default="")
    zone_name = Column(String(255), default="")
    is_enabled = Column(String(8), default="")
    ip_status = Column(String(16), default="")
    owner_user_id = Column(Integer, nullable=True, comment="认领人ID")
    department_id = Column(Integer, nullable=True, comment="所属部门ID")
    owner_name = Column(String(128), nullable=True, comment="管理员姓名")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    device = relationship("ZDNSDevice", back_populates="domain_maps")
