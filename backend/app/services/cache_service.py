"""Redis 缓存服务 — 通用缓存读写封装，用于资产画像和仪表盘缓存加速。"""
import json
import logging

from redis import Redis

from app.config import settings

logger = logging.getLogger(__name__)

CACHE_PREFIX = "omniview:cache:"

_redis: Redis | None = None


def _get_redis() -> Redis:
    """懒初始化 Redis 连接（与 progress_broker 共用同一 Redis 实例）。"""
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def get_cache(key: str) -> str | None:
    """读取缓存值，key 不存在则返回 None。"""
    try:
        return _get_redis().get(f"{CACHE_PREFIX}{key}")
    except Exception:
        logger.exception("Redis 缓存读取失败 key=%s", key)
        return None


def set_cache(key: str, value: str, ttl: int = 300) -> bool:
    """写入缓存，ttl 秒后自动过期。"""
    try:
        _get_redis().setex(f"{CACHE_PREFIX}{key}", ttl, value)
        return True
    except Exception:
        logger.exception("Redis 缓存写入失败 key=%s", key)
        return False


def delete_cache(key: str) -> bool:
    """删除指定缓存键。"""
    try:
        _get_redis().delete(f"{CACHE_PREFIX}{key}")
        return True
    except Exception:
        logger.exception("Redis 缓存删除失败 key=%s", key)
        return False


def invalidate_pattern(pattern: str) -> int:
    """按模式批量删除缓存键，返回删除数量。"""
    try:
        r = _get_redis()
        keys = list(r.scan_iter(match=f"{CACHE_PREFIX}{pattern}", count=100))
        if keys:
            return r.delete(*keys)
        return 0
    except Exception:
        logger.exception("Redis 缓存批量删除失败 pattern=%s", pattern)
        return 0


def get_json(key: str) -> dict | list | None:
    """读取 JSON 格式的缓存值，自动反序列化。"""
    raw = get_cache(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def set_json(key: str, value, ttl: int = 300) -> bool:
    """写入 JSON 格式的缓存值，自动序列化。"""
    return set_cache(key, json.dumps(value, ensure_ascii=False, default=str), ttl=ttl)
