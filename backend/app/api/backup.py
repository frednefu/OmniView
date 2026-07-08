"""系统备份 API — 备份任务 CRUD、手动执行、历史查询、下载、验证、FTP 测试"""
import os
import queue
import threading
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
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


def _get_ftp_job(history, db):
    """获取 FTP 连接配置，验证有效后返回 job。"""
    from app.models.backup_job import BackupJob
    job = db.query(BackupJob).get(history.job_id) if history.job_id else None
    if not job:
        raise HTTPException(400, "关联的备份任务已不存在")
    if not job.ftp_host:
        raise HTTPException(400, "FTP 服务器地址未配置")
    return job


def _ftp_file_name(history) -> str:
    """从历史记录中提取 FTP 远程文件名。"""
    name = history.file_name
    if name:
        return name
    return os.path.basename(history.file_path or "backup.tar.gz")


def _ftp_download_to_local(history, db, log_func=None) -> str:
    """从 FTP 下载备份文件到临时目录（用于验证），返回本地路径。调用方负责清理。"""
    import tempfile

    job = _get_ftp_job(history, db)
    remote_file = _ftp_file_name(history)
    tmp_path = os.path.join(tempfile.gettempdir(), f"ftp_verify_{history.id}_{remote_file}")

    import ftplib
    ftp = ftplib.FTP()
    try:
        if log_func:
            log_func(f"连接 {job.ftp_host}:{job.ftp_port} ...")
        ftp.connect(job.ftp_host, job.ftp_port, timeout=30)
        ftp.login(job.ftp_user, job.ftp_password)
        ftp.set_pasv(True)

        file_size = 0
        try:
            file_size = ftp.size(remote_file) or 0
        except Exception:
            pass

        if log_func:
            if file_size:
                log_func(f"文件大小：{file_size / (1024 * 1024):.1f} MB，开始下载...")
            else:
                log_func("开始下载（大小未知）...")

        bytes_done = [0]
        last_pct = [0]

        def progress_writer(data):
            with open(tmp_path, "ab") as f:
                f.write(data)
            bytes_done[0] += len(data)
            if file_size and log_func:
                pct = int(bytes_done[0] * 100 / file_size)
                if pct >= last_pct[0] + 10:  # 每10%汇报一次
                    last_pct[0] = pct
                    log_func(f"下载进度：{pct}% ({bytes_done[0] / (1024 * 1024):.0f} MB)")

        # 先清空临时文件
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        ftp.retrbinary(f"RETR {remote_file}", progress_writer, blocksize=1024 * 1024)

        actual_size = os.path.getsize(tmp_path)
        if log_func:
            log_func(f"下载完成：{actual_size / (1024 * 1024):.1f} MB")
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
    """下载备份文件。本地文件直接返回；FTP 文件流式传输（不落盘）。"""
    history = db.query(BackupHistory).get(history_id)
    if not history:
        raise HTTPException(404, "备份记录不存在")

    filename = history.file_name or "backup.tar.gz"

    # 本地文件直接返回
    if history.storage_location == "local":
        if history.file_path and os.path.isfile(history.file_path):
            from urllib.parse import quote
            safe_filename = quote(filename, safe='')
            return FileResponse(
                history.file_path,
                filename=filename,
                media_type="application/gzip",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}"},
            )
        else:
            raise HTTPException(404, "本地备份文件不存在（容器重建后临时目录中的文件会丢失，请将备份目录挂载为 Docker 卷）")

    # FTP 远程文件：流式传输（FTP → HTTP，不落盘）
    if history.storage_location == "ftp" and history.job_id:
        job = _get_ftp_job(history, db)
        remote_file = _ftp_file_name(history)

        import ftplib
        try:
            ftp = ftplib.FTP()
            ftp.connect(job.ftp_host, job.ftp_port, timeout=30)
            ftp.login(job.ftp_user, job.ftp_password)
            ftp.set_pasv(True)
        except ftplib.error_perm as e:
            raise HTTPException(400, f"FTP 认证失败：{e}")
        except Exception as e:
            raise HTTPException(400, f"FTP 连接失败：{e}")

        q = queue.Queue(maxsize=50)
        download_error = [None]

        # 获取文件大小用于 Content-Length
        file_size = 0
        try:
            file_size = ftp.size(remote_file) or 0
        except Exception:
            pass

        def ftp_callback(data):
            q.put(data)

        def ftp_worker():
            try:
                ftp.retrbinary(f"RETR {remote_file}", ftp_callback, blocksize=1024 * 1024)
            except Exception as e:
                download_error[0] = e
            finally:
                q.put(None)  # sentinel
                try:
                    ftp.quit()
                except Exception:
                    pass

        t = threading.Thread(target=ftp_worker, daemon=True)
        t.start()

        def stream_generator():
            while True:
                chunk = q.get()
                if chunk is None:
                    break
                yield chunk
            # sentinel 之后检查错误（必须在 break 之后，否则错误被吞掉）
            if download_error[0]:
                raise download_error[0]

        # filename 可能含中文，用 RFC 5987 编码避免 latin-1 错误
        from urllib.parse import quote
        safe_filename = quote(filename, safe='')
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
        }
        if file_size:
            headers["Content-Length"] = str(file_size)

        return StreamingResponse(
            stream_generator(),
            media_type="application/gzip",
            headers=headers,
        )

    raise HTTPException(404, "备份文件不存在")


@router.post("/history/{history_id}/verify")
def verify_backup_api(
    history_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """启动备份验证（后台线程执行，立即返回）。"""
    history = db.query(BackupHistory).get(history_id)
    if not history:
        raise HTTPException(404, "备份记录不存在")

    # 重置验证状态
    history.verified = False
    history.verify_log = "正在准备验证...\n"
    db.commit()

    def _verify_thread():
        from app.database import SessionLocal
        from app.models.backup_history import BackupHistory
        from app.services.backup_service import verify_backup

        vdb = SessionLocal()
        try:
            h = vdb.query(BackupHistory).get(history_id)
            if not h:
                return

            def log_progress(msg):
                try:
                    ldb = SessionLocal()
                    h2 = ldb.query(BackupHistory).get(history_id)
                    if h2:
                        h2.verify_log = (h2.verify_log or "") + msg + "\n"
                        ldb.commit()
                    ldb.close()
                except Exception:
                    pass

            local_path = h.file_path
            tmp_path = None

            # FTP 文件先下载
            if h.storage_location == "ftp":
                if not h.job_id or not h.file_name:
                    log_progress("验证失败：FTP 配置不完整")
                    h.verify_log = (h.verify_log or "") + "验证失败：FTP 配置不完整\n"
                    vdb.commit()
                    return

                log_progress(f"开始从 FTP 下载备份文件：{h.file_name}")
                try:
                    tmp_path = _ftp_download_to_local(h, vdb, log_func=log_progress)
                    local_path = tmp_path
                except HTTPException as e:
                    log_progress(f"FTP 下载失败：{e.detail}")
                    h.verify_log = (h.verify_log or "") + f"FTP 下载失败：{e.detail}\n"
                    vdb.commit()
                    return
                except Exception as e:
                    log_progress(f"FTP 下载失败：{e}")
                    h.verify_log = (h.verify_log or "") + f"FTP 下载失败：{e}\n"
                    vdb.commit()
                    return

            if not local_path or not os.path.isfile(local_path):
                log_progress("验证失败：备份文件不存在")
                return

            # 验证
            log_progress("开始验证备份文件完整性...")
            try:
                result = verify_backup(history_id, local_path=local_path)
                log_progress(result.get("message", "验证完成"))
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    log_progress("已清理临时下载文件")

        except Exception as e:
            try:
                ldb = SessionLocal()
                h2 = ldb.query(BackupHistory).get(history_id)
                if h2:
                    h2.verify_log = (h2.verify_log or "") + f"验证异常：{e}\n"
                    ldb.commit()
                ldb.close()
            except Exception:
                pass
        finally:
            vdb.close()

    t = threading.Thread(target=_verify_thread, daemon=True)
    t.start()

    return {"message": "验证任务已提交", "history_id": history_id}


@router.get("/history/{history_id}/verify-progress")
def get_verify_progress(
    history_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """获取验证进度（含实时日志）。"""
    history = db.query(BackupHistory).get(history_id)
    if not history:
        raise HTTPException(404, "备份记录不存在")
    return {
        "id": history.id,
        "verified": history.verified,
        "verify_log": history.verify_log or "",
        "verified_at": str(history.verified_at) if history.verified_at else None,
    }


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
