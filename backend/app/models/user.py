from sqlalchemy import Column, Integer, String, Boolean, Enum, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    dept_admin = "dept_admin"
    user = "user"


class UserType(str, enum.Enum):
    internal = "internal"  # 本校
    external = "external"  # 校外


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.user)
    avatar_url = Column(String(512), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    gh = Column(String(32), nullable=True, index=True, comment="工号")
    name = Column(String(128), nullable=True, comment="姓名")
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, comment="所属部门")
    phone = Column(String(32), nullable=True, comment="办公电话")
    mobile = Column(String(32), nullable=True, comment="移动电话")
    gender = Column(String(4), nullable=True, comment="性别")
    user_type = Column(String(8), default="internal", comment="账号类型")
    company = Column(String(256), nullable=True, comment="校外单位名称")
    contact_person = Column(String(64), nullable=True, comment="校外联系人")
    notes = Column(String(512), nullable=True, comment="备注")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    department = relationship("Department", lazy="joined")
