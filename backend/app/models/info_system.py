"""信息系统管理模型。"""
from sqlalchemy import Column, Integer, String, DateTime, Date, Text, func
from app.database import Base


class InfoSystem(Base):
    __tablename__ = "info_systems"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(String(32), unique=True, nullable=False, index=True, comment="资产ID")
    system_name = Column(String(256), nullable=False, comment="信息系统名称")
    system_type = Column(String(64), nullable=True, comment="资产类型")
    sub_type = Column(String(128), nullable=True, comment="信息系统类型")
    ip_address = Column(String(256), nullable=True, comment="IP地址")
    domain = Column(String(512), nullable=True, comment="域名/URL")
    org_name = Column(String(256), nullable=True, comment="单位名称")
    dept_name = Column(String(256), nullable=True, comment="运维单位")
    contact = Column(String(64), nullable=True, comment="联系人")
    contact_phone = Column(String(32), nullable=True, comment="联系电话")
    fill_type = Column(String(16), default="导入", comment="填报类型: 导入/手动/自动")
    djdj_status = Column(String(32), nullable=True, comment="等保状态")
    djdj_no = Column(String(64), nullable=True, comment="等保备案编号")
    djdj_level = Column(String(16), nullable=True, comment="等保等级")
    djdj_date = Column(Date, nullable=True, comment="等保备案日期")
    icp_no = Column(String(64), nullable=True, comment="ICP备案编号")
    icp_date = Column(Date, nullable=True, comment="ICP备案日期")
    djdj_sys_name = Column(String(256), nullable=True, comment="等保系统名称")
    djdj_org = Column(String(256), nullable=True, comment="等保测评单位")
    has_website = Column(String(8), nullable=True, comment="是否有网站")
    internal_url = Column(String(512), nullable=True, comment="内网URL")
    ip_range = Column(String(128), nullable=True, comment="IP地址段")
    remark = Column(Text, nullable=True, comment="备注")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DjDjRecord(Base):
    __tablename__ = "djdj_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_no = Column(String(64), unique=True, nullable=False, comment="备案编号")
    system_name = Column(String(256), nullable=False, comment="系统名称")
    org_name = Column(String(256), nullable=True, comment="备案单位")
    level = Column(String(16), nullable=True, comment="备案等级")
    record_date = Column(Date, nullable=True, comment="备案日期")
    eval_org = Column(String(256), nullable=True, comment="测评单位")
    image_path = Column(String(512), nullable=True, comment="备案证明图片路径")
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class IcpRecord(Base):
    __tablename__ = "icp_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    icp_no = Column(String(64), unique=True, nullable=False, comment="ICP备案编号")
    org_name = Column(String(256), nullable=True, comment="备案主体")
    domain = Column(String(512), nullable=True, comment="备案域名")
    record_date = Column(Date, nullable=True, comment="备案日期")
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
