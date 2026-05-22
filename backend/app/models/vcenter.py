from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from app.database import Base


class VCenter(Base):
    __tablename__ = "vcenters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    host = Column(String(255), nullable=False, unique=True, index=True)
    username = Column(String(128), nullable=False)
    password = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False, default=443)
    scan_interval = Column(Integer, nullable=False, default=3600)
    is_active = Column(Boolean, nullable=False, default=True)

    last_scan_status = Column(String(16), nullable=True)
    last_scan_time = Column(DateTime, nullable=True)
    last_vm_count = Column(Integer, nullable=False, default=0)
    last_scan_error = Column(Text, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    vm_inventories = relationship("VMInventory", back_populates="vcenter", cascade="all, delete-orphan")
