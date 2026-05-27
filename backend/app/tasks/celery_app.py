"""Celery 应用实例 — Redis broker + backend，含 Worker 自动注册/注销 + 定时心跳。"""
import hashlib
import multiprocessing
import os
import signal
import socket
import threading
import time
import urllib.request
import json
import logging

from celery import Celery
from celery.signals import worker_ready, worker_shutdown, task_prerun, task_postrun
from kombu import Queue

from app.config import settings
from app.version import get_version

logger = logging.getLogger(__name__)

# 任务类型 → 队列名映射
_TASK_TYPE_QUEUE = {
    "switch": "scan:switch",
    "vcenter": "scan:vcenter",
    "f5": "scan:f5",
    "zdns": "scan:zdns",
    "zdns_ip": "scan:zdns_ip",
    "qax": "scan:qax",
}

# 任务函数路径 → 队列名路由
_TASK_ROUTES = {
    "app.tasks.scan_tasks.scan_switch_task": {"queue": "scan:switch"},
    "app.tasks.scan_tasks.scan_vcenter_task": {"queue": "scan:vcenter"},
    "app.tasks.scan_tasks.scan_f5_task": {"queue": "scan:f5"},
    "app.tasks.scan_tasks.scan_zdns_task": {"queue": "scan:zdns"},
    "app.tasks.scan_tasks.scan_zdns_ip_task": {"queue": "scan:zdns_ip"},
    "app.tasks.scan_tasks.scan_qax_task": {"queue": "scan:qax"},
}

# Worker 只订阅自己能力范围内的队列
_WORKER_TASK_TYPES = [t.strip() for t in os.environ.get("WORKER_TASK_TYPES", "switch,vcenter,f5,zdns,zdns_ip,qax").split(",") if t.strip()]
_WORKER_QUEUES = [Queue(name=q, routing_key=q) for t, q in _TASK_TYPE_QUEUE.items() if t in _WORKER_TASK_TYPES]

celery_app = Celery(
    "omniview",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.scan_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    task_queues=_WORKER_QUEUES,
    task_routes=_TASK_ROUTES,
    task_create_missing_queues=True,
)


def _register_worker():
    """向 API 服务器注册当前 Worker。"""
    api_base = os.environ.get("API_BASE_URL", "http://backend:8000")
    worker_name = os.environ.get("WORKER_NAME", socket.gethostname())
    version = os.environ.get("WORKER_VERSION") or get_version()
    worker_token = settings.worker_token
    concurrency = int(os.environ.get("WORKER_CONCURRENCY", "4"))
    task_types = _WORKER_TASK_TYPES

    try:
        data = json.dumps({
            "worker_name": worker_name,
            "capabilities": {"task_types": task_types},
            "version": version,
            "max_tasks": concurrency,
        }).encode()
        req = urllib.request.Request(
            f"{api_base}/api/workers/register",
            data=data,
            headers={
                "Authorization": f"Bearer {worker_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode())
        logger.info("Worker 注册成功: %s (ID=%s)", result["worker_name"], result["worker_id"])
        return result["worker_id"]
    except Exception as e:
        logger.warning("Worker 注册失败: %s", e)
        return None


# 跨进程共享任务计数器 — prefork 池下主进程心跳能读取子进程的变更
_task_counter = multiprocessing.Value('i', 0)


@task_prerun.connect
def _on_task_start(sender=None, **kwargs):
    with _task_counter.get_lock():
        _task_counter.value += 1


@task_postrun.connect
def _on_task_end(sender=None, **kwargs):
    with _task_counter.get_lock():
        _task_counter.value = max(0, _task_counter.value - 1)


def _send_heartbeat(worker_id):
    """向 API 发送心跳（在当前线程中执行）。"""
    api_base = os.environ.get("API_BASE_URL", "http://backend:8000")
    worker_token = settings.worker_token
    try:
        current_tasks = _task_counter.value
        status = "busy" if current_tasks > 0 else "online"
        data = json.dumps({"current_tasks": current_tasks, "status": status}).encode()
        req = urllib.request.Request(
            f"{api_base}/api/workers/{worker_id}/heartbeat",
            data=data,
            headers={
                "Authorization": f"Bearer {worker_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.warning("Worker 心跳发送失败 (ID=%s): %s", worker_id, e)


def _heartbeat_loop(worker_id):
    """后台心跳线程：每 15 秒向 API 上报心跳。"""
    while not _heartbeat_stop.is_set():
        _heartbeat_stop.wait(15)
        if not _heartbeat_stop.is_set():
            _send_heartbeat(worker_id)


def _deregister_worker():
    """向 API 发送注销请求（供 Celery 信号和 SIGTERM 处理器共用）。"""
    global _WORKER_ID, _heartbeat_thread
    _heartbeat_stop.set()
    if _heartbeat_thread and _heartbeat_thread.is_alive():
        _heartbeat_thread.join(timeout=3)
    if not _WORKER_ID:
        return
    api_base = os.environ.get("API_BASE_URL", "http://backend:8000")
    worker_token = settings.worker_token
    try:
        req = urllib.request.Request(
            f"{api_base}/api/workers/{_WORKER_ID}/deregister",
            headers={"Authorization": f"Bearer {worker_token}"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        logger.info("Worker (ID=%s) 已注销", _WORKER_ID)
    except Exception as e:
        logger.warning("Worker 注销失败: %s", e)


def _sigterm_handler(signum, frame):
    """SIGTERM 信号处理器 — 在进程被 kill 前立即注销。"""
    logger.info("收到 SIGTERM，正在注销 Worker...")
    _deregister_worker()


_WORKER_ID = None
_heartbeat_thread = None
_heartbeat_stop = threading.Event()


@worker_ready.connect
def on_worker_ready(sender=None, **kwargs):
    """Worker 就绪后自动注册并启动心跳线程。"""
    global _WORKER_ID, _heartbeat_thread
    _WORKER_ID = _register_worker()
    if _WORKER_ID:
        _heartbeat_stop.clear()
        _heartbeat_thread = threading.Thread(
            target=_heartbeat_loop, args=(_WORKER_ID,), daemon=True
        )
        _heartbeat_thread.start()
        # 注册 SIGTERM 处理器，确保 docker stop 时立即注销
        signal.signal(signal.SIGTERM, _sigterm_handler)
        logger.info("Worker 心跳线程已启动 (ID=%s, 间隔=15s)", _WORKER_ID)


@worker_shutdown.connect
def on_worker_shutdown(sender=None, **kwargs):
    """Worker 关闭时停止心跳并自动注销（Celery 信号，作为补充保障）。"""
    _deregister_worker()
