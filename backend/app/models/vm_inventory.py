from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.database import Base


class VMInventory(Base):
    __tablename__ = "vm_inventory"
    __table_args__ = (
        Index("idx_vmi_vcenter", "vcenter_id"),
        Index("idx_vmi_ip", "ip_address"),
        Index("idx_vmi_mac", "mac_address"),
        Index("idx_vmi_name", "vm_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    vcenter_id = Column(Integer, ForeignKey("vcenters.id", ondelete="CASCADE"), nullable=False)

    datacenter = Column(String(128), default="")
    cluster = Column(String(128), default="")
    esxi_host = Column(String(255), default="")
    resource_pool = Column(String(255), default="")
    vm_folder = Column(String(255), default="")
    vm_name = Column(String(255), nullable=False)
    power_state = Column(String(32), default="")
    ip_address = Column(String(1024), default="")
    mac_address = Column(String(1024), default="")
    network_name = Column(String(1024), default="")
    vlan_id = Column(String(255), default="")
    os_name = Column(String(255), default="")
    cpu_count = Column(Integer, nullable=True)
    memory_gb = Column(Float, nullable=True)
    remark = Column(String(512), default="")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    vcenter = relationship("VCenter", back_populates="vm_inventories")
