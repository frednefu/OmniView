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


def _get_ftp_file(history, db, log_func=None) -> str:
    """从 FTP 下载备份文件到临时目录，返回本地路径。调用方负责清理。"""
    import tempfile
    from app.models.backup_job import BackupJob

    job = db.query(BackupJob).get(history.job_id) if history.job_id else None
    if not job:
        raise HTTPException(400, "关联的备份任务已不存在，无法获取 FTP 连接信息")
    if not job.ftp_host:
        raise HTTPException(400, "FTP 服务器地址未配置")

    remote_file = history.file_name
    if not remote_file:
        remote_file = os.path.basename(history.file_path or "backup.tar.gz")

    tmp_path = os.path.join(tempfile.gettempdir(), f"ftp_download_{history.id}_{remote_file}")

    import ftplib
    ftp = ftplib.FTP()
    try:
        if log_func:
            log_func(f"连接 {job.ftp_host}:{job.ftp_port} ...")
        ftp.connect(job.ftp_host, job.ftp_port, timeout=30)
        ftp.login(job.ftp_user, job.ftp_password)
        ftp.set_pasv(True)

        # 获取文件大小（部分 FTP 服务器不支持 SIZE 命令）
        file_size = 0
        try:
            file_size = ftp.size(remote_file) or 0
        except Exception:
            pass

        if log_func:
            if file_size:
                log_func(f"FTP 连接成功，文件大小：{file_size / (1024 * 1024):.1f} MB")
            else:
                log_func("FTP 连接成功，开始下载...")

        with open(tmp_path, "wb") as f:
            ftp.retrbinary(f"RETR {remote_file}", f.write)

        actual_size = os.path.getsize(tmp_path)
        if log_func:
            log_func(f"FTP 下载完成，本地文件大小：{actual_size / (1024 * 1024):.1f} MB")
    except ftplib.error_perm as e:
        raise HTTPException(400, f"FTP 权限错误：{e}")
    except ftplib.error_temp as e:
        raise HTTPException(400, f"FTP 临时错误：{e}")
    except Exception as e:
        raise HTTPException(400, f"FTP 下载失败：{e}")
    finally:
        try:
            ftp.quit()
        except Exception:
            pass
    return tmp_path


@router.get("/history/{history_id}/download")
def download_backup(
    history_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """下载备份文件（本地直接返回，FTP 先下载再返回）。"""
    history = db.query(BackupHistory).get(history_id)
    if not history:
        raise HTTPException(404, "备份记录不存在")

    filename = history.file_name or "backup.tar.gz"

    # 本地文件直接返回
    if history.file_path and os.path.isfile(history.file_path):
        return FileResponse(
            history.file_path,
            filename=filename,
            media_type="application/gzip",
        )

    # FTP 远程文件：下载到临时目录后返回
    if history.storage_location == "ftp" and history.job_id:
        try:
            tmp_path = _get_ftp_file(history, db)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"FTP 下载失败：{e}")

        from starlette.background import BackgroundTask

        def cleanup(path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

        return FileResponse(
            tmp_path,
            filename=filename,
            media_type="application/gzip",
            background=BackgroundTask(cleanup, tmp_path),
        )

    raise HTTPException(404, "备份文件不存在")


@router.post("/history/{history_id}/verify")
def verify_backup_api(
    history_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """验证备份文件完整性（只读，不影响生产环境）。FTP 文件自动下载后验证。"""
    history = db.query(BackupHistory).get(history_id)
    if not history:
        raise HTTPException(404, "备份记录不存在")

    local_path = history.file_path
    tmp_path = None

    # FTP 文件先下载到本地
    if history.storage_location == "ftp":
        if not history.job_id:
            return {"success": False, "message": "关联的备份任务已不存在，无法获取 FTP 连接信息", "log_output": ""}
        if not history.file_name:
            return {"success": False, "message": "备份文件名缺失", "log_output": ""}
        try:
            tmp_path = _get_ftp_file(history, db)
            local_path = tmp_path
        except HTTPException as e:
            return {"success": False, "message": e.detail, "log_output": f"FTP 下载失败：{e.detail}"}
        except Exception as e:
            return {"success": False, "message": f"FTP 下载失败：{e}", "log_output": ""}

    if not local_path or not os.path.isfile(local_path):
        return {"success": False, "message": "备份文件不存在", "log_output": ""}

    # 验证（传入本地路径）
    try:
        result = verify_backup(history_id, local_path=local_path)
    finally:
        # 验证完成后清理 FTP 临时下载文件
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return result


@router.get("/history/{history_id}/log")
def get_backup_log(
    history_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """获取备份执行过程的控制台日志。"""
    history = db.query(BackupHistory).get(history_id)
    if not history:
        raise HTTPException(404, "备份记录不存在")
    return {
        "id": history.id,
        "job_name": history.job_name,
        "status": history.status,
        "log_output": history.log_output or "",
    }


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
