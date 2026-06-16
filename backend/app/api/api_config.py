"""API 配置管理 — 管理外部数据中台 API 的连接配置。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.api_config import ApiConfig
from app.schemas.api_config import ApiConfigCreate, ApiConfigUpdate, ApiConfigOut, ApiConfigTestResult
from app.api.deps import require_admin
from app.services import external_api_service

router = APIRouter(prefix="/sys", tags=["API 配置"])


def _mask_secret(config: ApiConfig) -> ApiConfigOut:
    """返回配置输出（保留原始值，前端通过 type=password 掩码显示）。"""
    out = ApiConfigOut.model_validate(config)
    out.app_secret = config.app_secret or ""
    out.app_key = config.app_key or ""
    return out


@router.get("/api-config", response_model=ApiConfigOut)
def get_config(db: Session = Depends(get_db), _=Depends(require_admin)):
    config = db.query(ApiConfig).first()
    if not config:
        raise HTTPException(status_code=404, detail="未配置 API，请先创建配置")
    return _mask_secret(config)


@router.put("/api-config", response_model=ApiConfigOut)
def save_config(body: ApiConfigCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    """创建或更新 API 配置（仅保留一份激活配置）。"""
    config = db.query(ApiConfig).first()
    if not config:
        config = ApiConfig()
        db.add(config)
    config.name = body.name
    config.base_url = body.base_url.rstrip("/")
    config.app_key = body.app_key
    config.app_secret = body.app_secret
    config.access_token = None
    config.token_expires_at = None
    config.is_active = True
    db.commit()
    db.refresh(config)
    return _mask_secret(config)


@router.post("/api-config/test", response_model=ApiConfigTestResult)
def test_config(db: Session = Depends(get_db), _=Depends(require_admin)):
    config = db.query(ApiConfig).filter(ApiConfig.is_active == True).first()
    if not config:
        return ApiConfigTestResult(success=False, message="未找到启用的 API 配置")
    result = external_api_service.test_connection(db)
    return ApiConfigTestResult(**result)
