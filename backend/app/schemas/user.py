from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserLogin(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: Optional[str] = None
    email: Optional[str] = None
    role: str = "user"
    gh: Optional[str] = None
    name: Optional[str] = None
    department_id: Optional[int] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    gender: Optional[str] = None
    user_type: str = "internal"
    company: Optional[str] = None
    contact_person: Optional[str] = None
    notes: Optional[str] = None


class UserUpdate(BaseModel):
    model_config = {"extra": "ignore"}

    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    gh: Optional[str] = None
    name: Optional[str] = None
    department_id: Optional[int] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    user_type: Optional[str] = None
    company: Optional[str] = None
    contact_person: Optional[str] = None
    notes: Optional[str] = None
    gender: Optional[str] = None


class ProfileUpdate(BaseModel):
    avatar_url: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    gender: Optional[str] = None
    company: Optional[str] = None
    contact_person: Optional[str] = None
    notes: Optional[str] = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    avatar_url: Optional[str] = None
    is_active: bool
    gh: Optional[str] = None
    name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    gender: Optional[str] = None
    user_type: Optional[str] = None
    company: Optional[str] = None
    contact_person: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
