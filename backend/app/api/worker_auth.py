"""Worker 共享密钥认证 — 独立于用户 JWT 认证，用于 Worker 注册/心跳/注销。"""
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings

worker_security_scheme = HTTPBearer()


def verify_worker_token(
    credentials: HTTPAuthorizationCredentials = Depends(worker_security_scheme),
) -> str:
    """验证 Worker 共享密钥（时序安全比较），返回 worker_name 供后续使用。"""
    if not secrets.compare_digest(credentials.credentials, settings.worker_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的 Worker 认证令牌")
    return "worker"
