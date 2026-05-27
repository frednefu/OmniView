"""扫描步骤追踪辅助 — 每个函数独立管理 DB 会话，实时提交，供 API 轮询/WebSocket 推送。"""
import logging
import time
from datetime import datetime

from app.database import SessionLocal
from app.models.scan_log import ScanLog, ScanStep, StepStatus

logger = logging.getLogger(__name__)

# 节流：同一 scan_log_id 两次通知间隔至少 1.5 秒，避免高频写入时 DB/Redis/W前端 被淹没
_notify_last: dict[int, float] = {}
_NOTIFY_THROTTLE = 1.5


def _notify(scan_log_id: int):
    """DB 变更后通知 WebSocket 订阅者（节流：最少间隔 1.5s）。"""
    now = time.time()
    last = _notify_last.get(scan_log_id, 0)
    if now - last < _NOTIFY_THROTTLE:
        return
    _notify_last[scan_log_id] = now
    try:
        from app.services.progress_broker import publish_scan_update
        publish_scan_update(scan_log_id)
    except Exception:
        pass


def add_step(scan_log_id: int, step_order: int, step_name: str) -> int:
    """创建一个 running 状态的步骤，同时更新 scan_log.current_step。返回 step_id。"""
    db = SessionLocal()
    try:
        step = ScanStep(
            scan_log_id=scan_log_id,
            step_order=step_order,
            step_name=step_name,
            status=StepStatus.running,
            started_at=datetime.now(),
        )
        db.add(step)
        log = db.query(ScanLog).get(scan_log_id)
        if log:
            log.current_step = step_name
        db.commit()
        db.refresh(step)
        _notify(scan_log_id)
        return step.id
    except Exception:
        db.rollback()
        logger.exception("创建扫描步骤失败 scan_log_id=%s step=%s", scan_log_id, step_name)
        return 0
    finally:
        db.close()


def finish_step(step_id: int, status: str = "success",
                items_total: int = 0, items_processed: int = 0,
                error_message: str | None = None):
    """将步骤标记为 success 或 failed。"""
    if not step_id:
        return
    db = SessionLocal()
    try:
        step = db.query(ScanStep).get(step_id)
        if step:
            step.status = StepStatus.success if status == "success" else StepStatus.failed
            step.items_total = items_total
            step.items_processed = items_processed
            step.completed_at = datetime.now()
            if error_message:
                step.error_message = error_message
            db.commit()
            _notify(step.scan_log_id)
    except Exception:
        db.rollback()
        logger.exception("更新扫描步骤失败 step_id=%s", step_id)
    finally:
        db.close()


def update_progress(scan_log_id: int, progress_pct: int, current_step: str | None = None):
    """更新 scan_log 的进度百分比和当前步骤名。"""
    db = SessionLocal()
    try:
        log = db.query(ScanLog).get(scan_log_id)
        if log:
            log.progress_pct = progress_pct
            if current_step:
                log.current_step = current_step
            db.commit()
            _notify(scan_log_id)
    except Exception:
        db.rollback()
    finally:
        db.close()


def mark_queued(scan_log_id: int):
    """标记扫描已入队，等待 Worker 调度。在 trigger_* 中调用。"""
    update_progress(scan_log_id, 0, "已加入队列，等待 Worker 调度")


def mark_started(scan_log_id: int):
    """标记 Worker 已接收任务，开始扫描。在 _run_*_scan_async 开头调用。"""
    update_progress(scan_log_id, 2, "Worker 已接收，开始扫描")


def append_log(scan_log_id: int, message: str):
    """追加一行时间戳日志到 scan_log.log_output。"""
    db = SessionLocal()
    try:
        log = db.query(ScanLog).get(scan_log_id)
        if log:
            ts = datetime.now().strftime("%H:%M:%S")
            line = f"[{ts}] {message}\n"
            if log.log_output:
                log.log_output = (log.log_output or "") + line
            else:
                log.log_output = line
            db.commit()
            _notify(scan_log_id)
    except Exception:
        db.rollback()
    finally:
        db.close()
