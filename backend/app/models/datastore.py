from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class Datastore(Base):
    __tablename__ = "datastores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vcenter_id = Column(Integer, ForeignKey("vcenters.id", ondelete="CASCADE"), nullable=False)

    datastore_name = Column(String(255), default="")
    status = Column(String(32), default="")
    ds_type = Column(String(64), default="")
    capacity_gb = Column(Float, default=0.0)
    free_gb = Column(Float, default=0.0)
    mounted_host_count = Column(Integer, default=0)
    storage_type = Column(String(16), default="")

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    vcenter = relationship("VCenter", back_populates="datastores")
