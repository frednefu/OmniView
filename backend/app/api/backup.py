"""系统备份 API — 备份任务 CRUD、手动执行、历史查询、下载、验证、FTP 测试"""
import os
import threading
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import SessionLocal
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.models.backup_job import BackupJob
from app.models.backup_history import BackupHistory
from app.schemas.backup import (
    BackupJobCreate, BackupJobUpdate, BackupJobOut,
    BackupHistoryOut, FtpTestRequest,
)
from app.services.backup_service import test_ftp_connection, verify_backup, run_backup
from app.services.scheduler_service import refresh_backup_job

router = APIRouter(prefix="/backup", tags=["系统备份"])


# ── 备份任务 CRUD ─────────────────────────────────────────

@router.get("/jobs")
def list_backup_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """列出所有备份任务（分页）。"""
    total = db.query(BackupJob).count()
    jobs = db.query(BackupJob).order_by(desc(BackupJob.created_at)) \
        .offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [BackupJobOut.model_validate(j) for j in jobs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/jobs", status_code=201)
def create_backup_job(
    data: BackupJobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """创建备份任务并注册定时调度。"""
    job = BackupJob(
        name=data.name,
        enabled=data.enabled,
        mode=data.mode,
        local_path=data.local_path,
        ftp_host=data.ftp_host,
        ftp_port=data.ftp_port,
        ftp_user=data.ftp_user,
        ftp_password=data.ftp_password,
        ftp_remote_path=data.ftp_remote_path,
        backup_contents=data.backup_contents,
        cron_expression=data.cron_expression,
        retention_days=data.retention_days,
        created_by=current_user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 注册调度
    try:
        refresh_backup_job(job.id)
    except Exception:
        pass

    return {"message": "备份任务创建成功", "id": job.id}


@router.get("/jobs/{job_id}")
def get_backup_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """获取单个备份任务详情。"""
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(404, "备份任务不存在")
    return BackupJobOut.model_validate(job)


@router.put("/jobs/{job_id}")
def update_backup_job(
    job_id: int,
    data: BackupJobUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """更新备份任务配置并刷新调度。"""
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(404, "备份任务不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(job, key, value)
    db.commit()

    # 刷新调度
    try:
        refresh_backup_job(job.id)
    except Exception:
        pass

    return {"message": "备份任务更新成功"}


@router.delete("/jobs/{job_id}")
def delete_backup_job(
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """删除备份任务并移除调度（历史记录保留）。"""
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(404, "备份任务不存在")

    # 移除调度
    try:
        refresh_backup_job(job_id)
    except Exception:
        pass

    # 断开历史记录关联（保留历史数据）
    db.query(BackupHistory).filter(BackupHistory.job_id == job_id).update(
        {BackupHistory.job_id: None}, synchronize_session=False
    )

    db.delete(job)
    db.commit()

    return {"message": "备份任务已删除"}


@router.post("/jobs/{job_id}/run")
def trigger_backup(
    job_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """手动触发一次备份（后台线程执行，立即返回）。"""
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(404, "备份任务不存在")

    if job.mode == "local" and (not job.local_path):
        raise HTTPException(400, "请先配置本地备份目录路径")

    # 后台线程执行备份
    def _run():
        db2 = SessionLocal()
        try:
            run_backup(job_id, manual=True)
        finally:
            db2.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {"message": "备份任务已提交，正在后台执行"}


# ── 备份历史 ──────────────────────────────────────────────

@router.get("/history")
def list_backup_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    job_id: int = Query(None, description="按任务ID筛选"),
    status: str = Query(None, description="按状态筛选: success/failed/running"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """列出备份历史（分页，可筛选）。"""
    q = db.query(BackupHistory)
    if job_id is not None:
        q = q.filter(BackupHistory.job_id == job_id)
    if status:
        q = q.filter(BackupHistory.status == status)

    total = q.count()
    items = q.order_by(desc(BackupHistory.created_at)) \
        .offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [BackupHistoryOut.model_validate(h) for h in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/history/{history_id}/download")
def download_backup(
    history_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """下载备份文件。"""
    history = db.query(BackupHistory).get(history_id)
    if not history:
        raise HTTPException(404, "备份记录不存在")

    file_path = history.file_path
    if not file_path:
        raise HTTPException(404, "备份文件路径缺失")

    # 本地文件直接返回
    if os.path.isfile(file_path):
        return FileResponse(
            file_path,
            filename=history.file_name or os.path.basename(file_path),
            media_type="application/gzip",
        )

    # FTP 远程文件：先下载到临时目录再返回
    if history.storage_location == "ftp" and history.job_id:
        import tempfile
        from app.models.backup_job import BackupJob
        job = db.query(BackupJob).get(history.job_id)
        if not job:
            raise HTTPException(400, "关联的备份任务已不存在，无法获取 FTP 连接信息")

        import ftplib
        tmp_path = os.path.join(tempfile.gettempdir(), history.file_name or "backup_download.tar.gz")
        ftp = ftplib.FTP()
        try:
            ftp.connect(job.ftp_host, job.ftp_port, timeout=30)
            ftp.login(job.ftp_user, job.ftp_password)
            ftp.set_pasv(True)
            remote_file = history.file_name or os.path.basename(file_path)
            with open(tmp_path, "wb") as f:
                ftp.retrbinary(f"RETR {remote_file}", f.write)
        finally:
            try:
                ftp.quit()
            except Exception:
                pass

        return FileResponse(
            tmp_path,
            filename=history.file_name or "backup.tar.gz",
            media_type="application/gzip",
        )

    raise HTTPException(404, "备份文件不存在")


@router.post("/history/{history_id}/verify")
def verify_backup_api(
    history_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """验证备份文件完整性（只读，不影响生产环境）。"""
    history = db.query(BackupHistory).get(history_id)
    if not history:
        raise HTTPException(404, "备份记录不存在")

    result = verify_backup(history_id)
    return result


@router.delete("/history/{history_id}")
def delete_backup_history(
    history_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """删除备份历史记录及其文件。"""
    history = db.query(BackupHistory).get(history_id)
    if not history:
        raise HTTPException(404, "备份记录不存在")

    # 尝试删除备份文件
    if history.file_path and os.path.isfile(history.file_path):
        try:
            os.remove(history.file_path)
        except OSError:
            pass

    db.delete(history)
    db.commit()

    return {"message": "备份记录已删除"}


# ── FTP 测试 ──────────────────────────────────────────────

@router.post("/test-ftp")
def test_ftp(
    data: FtpTestRequest,
    _: User = Depends(require_admin),
):
    """测试 FTP 服务器连接。"""
    result = test_ftp_connection(data.host, data.port, data.user, data.password)
    return result


# ── 本地文件浏览 ──────────────────────────────────────────

@router.get("/local-files")
def list_local_files(
    path: str = Query("/", description="目录路径"),
    _: User = Depends(require_admin),
):
    """浏览本地目录下的备份文件。"""
    if not os.path.isdir(path):
        return {"items": [], "path": path, "error": "目录不存在"}

    items = []
    try:
        for entry in os.listdir(path):
            full = os.path.join(path, entry)
            is_dir = os.path.isdir(full)
            # 只显示目录和 .tar.gz 文件
            if is_dir or entry.endswith(".tar.gz") or entry.endswith(".gz"):
                try:
                    stat = os.stat(full)
                    items.append({
                        "name": entry,
                        "is_dir": is_dir,
                        "size": stat.st_size if not is_dir else 0,
                        "modified": stat.st_mtime,
                    })
                except OSError:
                    continue
    except PermissionError:
        return {"items": [], "path": path, "error": "权限不足"}

    items.sort(key=lambda x: (not x["is_dir"], x["name"]))
    return {"items": items, "path": path}
