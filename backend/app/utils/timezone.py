"""全局时区工具 — 统一使用东八区 (Asia/Shanghai)"""
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))


def now() -> datetime:
    """返回当前东八区时间（naive，无时区标记，可直接存入数据库）。"""
    return datetime.now(TZ).replace(tzinfo=None)
