"""系统备份执行引擎 — 数据库导出、文件收集、镜像导出、FTP 上传、验证、清理"""
import os
import re
import io
import shutil
import tarfile
import tempfile
import ftplib
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)

# 备份内容类型中文标签
CONTENT_LABELS = {
    "database": "数据库",
    "configs": "配置文件",
    "images": "Docker镜像",
    "uploads": "上传文件",
}


class LogCapture:
    """捕获备份过程中的日志输出到内存缓冲区。"""

    def __init__(self):
        self._buffer = io.StringIO()
        self._started = datetime.now()

    def write(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._buffer.write(f"[{ts}] {msg}\n")

    def getvalue(self) -> str:
        return self._buffer.getvalue()

    def close(self):
        self._buffer.close()


def run_backup(job_id: int, manual: bool = False) -> int:
    """执行一次备份，返回 BackupHistory.id。"""
    from app.database import SessionLocal
    from app.models.backup_job import BackupJob
    from app.models.backup_history import BackupHistory

    log = LogCapture()
    db = SessionLocal()
    try:
        job = db.query(BackupJob).get(job_id)
        if not job:
            raise ValueError(f"备份任务不存在: {job_id}")

        log.write(f"开始执行备份任务：{job.name}")
        log.write(f"备份模式：{job.mode}，保留天数：{job.retention_days}")

        # 检查是否已有运行中的备份
        running = db.query(BackupHistory).filter(
            BackupHistory.job_id == job_id,
            BackupHistory.status == "running",
        ).first()
        if running:
            log.write("已有运行中的备份任务，跳过本次执行")
            logger.warning("备份任务 %s 已有运行中的备份，跳过本次执行", job.name)
            return running.id

        # 验证本地目录
        if job.mode == "local":
            if not job.local_path:
                raise ValueError("本地备份目录未配置")
            os.makedirs(job.local_path, exist_ok=True)
            log.write(f"本地备份目录：{job.local_path}")

        # 生成时间戳和目录名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r'[^\w\-]', '_', job.name)
        backup_dir_name = f"backup_{safe_name}_{timestamp}"
        work_dir = os.path.join(tempfile.gettempdir(), backup_dir_name)
        os.makedirs(work_dir, exist_ok=True)
        log.write(f"临时工作目录：{work_dir}")

        # 解析备份内容
        contents = [c.strip() for c in job.backup_contents.split(",") if c.strip()]
        content_labels = [CONTENT_LABELS.get(c, c) for c in contents]
        log.write(f"备份内容：{', '.join(content_labels)}")

        # 创建历史记录
        now = datetime.now()
        history = BackupHistory(
            job_id=job.id,
            job_name=job.name,
            status="running",
            started_at=now,
            storage_location=job.mode,
            content_summary=",".join(content_labels),
            log_output="",
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        archive_path = None
        try:
            # 1. 数据库导出
            if "database" in contents:
                log.write("── 开始导出数据库 ──")
                try:
                    _dump_database(work_dir, log)
                    log.write("数据库导出完成")
                except Exception as e:
                    log.write(f"数据库导出失败：{e}")
                    raise

            # 2. 配置文件收集
            if "configs" in contents:
                log.write("── 开始收集配置文件 ──")
                try:
                    n = _collect_configs(work_dir, log)
                    log.write(f"配置文件收集完成：{n} 个文件")
                except Exception as e:
                    log.write(f"配置文件收集失败：{e}")
                    raise

            # 3. Docker 镜像导出
            if "images" in contents:
                log.write("── 开始导出 Docker 镜像 ──")
                try:
                    n = _export_images(work_dir, log)
                    log.write(f"Docker 镜像导出：{n} 个")
                except Exception as e:
                    log.write(f"Docker 镜像导出失败（已跳过）：{e}")

            # 4. 上传文件打包
            if "uploads" in contents:
                log.write("── 开始打包上传文件 ──")
                try:
                    _archive_uploads(work_dir, log)
                    log.write("上传文件打包完成")
                except Exception as e:
                    log.write(f"上传文件打包失败：{e}")
                    raise

            # 5. 创建最终压缩包
            log.write("── 创建压缩包 ──")
            archive_name = f"{backup_dir_name}.tar.gz"
            archive_path = os.path.join(tempfile.gettempdir(), archive_name)
            _create_final_archive(work_dir, archive_path, log)
            archive_size = os.path.getsize(archive_path)
            log.write(f"压缩包创建完成：{archive_name} ({archive_size / (1024 * 1024):.1f} MB)")

            # 6. FTP 上传（如需要）
            if job.mode == "ftp":
                log.write(f"── 上传到 FTP：{job.ftp_host}:{job.ftp_port} ──")
                try:
                    _upload_ftp(archive_path, job, log)
                    log.write("FTP 上传成功")
                    os.remove(archive_path)
                    history.file_path = f"ftp://{job.ftp_host}:{job.ftp_port}{job.ftp_remote_path or '/'}{archive_name}"
                except Exception as e:
                    log.write(f"FTP 上传失败：{e}，保留本地文件")
                    history.file_path = archive_path
                    history.storage_location = "local"
            else:
                # 本地模式：移动到目标目录
                dest_path = os.path.join(job.local_path, archive_name)
                shutil.move(archive_path, dest_path)
                archive_path = dest_path
                history.file_path = dest_path
                log.write(f"备份文件已保存到：{dest_path}")

            file_size = os.path.getsize(history.file_path) if os.path.isfile(history.file_path) else archive_size
            history.file_name = archive_name
            history.file_size = file_size
            history.status = "success"
            history.completed_at = datetime.now()
            if history.started_at:
                history.duration_seconds = int((history.completed_at - history.started_at).total_seconds())

            job.last_run_at = history.completed_at
            job.last_status = "success"
            log.write(f"✅ 备份成功完成，耗时 {history.duration_seconds} 秒")

        except Exception as e:
            log.write(f"❌ 备份失败：{e}")
            logger.exception("备份失败 job_id=%s name=%s", job_id, job.name)
            history.status = "failed"
            history.error_message = str(e)[:2000]
            history.completed_at = datetime.now()
            if history.started_at:
                history.duration_seconds = int((history.completed_at - history.started_at).total_seconds())
            job.last_run_at = history.completed_at
            job.last_status = "failed"

        # 保存日志
        history.log_output = log.getvalue()
        db.commit()

        # 清理临时目录
        shutil.rmtree(work_dir, ignore_errors=True)
        log.close()

        # 执行保留策略（仅在成功时）
        if history.status == "success":
            try:
                _cleanup_retention(job, log)
            except Exception:
                pass

        return history.id

    finally:
        db.close()


def _dump_database(output_dir: str, log: LogCapture) -> str:
    """导出 MySQL 数据库，返回生成的 SQL 文件路径。"""
    sql_path = os.path.join(output_dir, "database.sql")

    # 从 DATABASE_URL 解析连接参数
    db_url = os.environ.get("DATABASE_URL", "")
    match = re.match(r"mysql\+pymysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", db_url)
    if not match:
        # 也尝试 mysql:// 格式
        match = re.match(r"mysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", db_url)
    if not match:
        raise RuntimeError(f"无法解析 DATABASE_URL: {db_url}")

    user, pwd, host, port, db_name = match.groups()
    log.write(f"数据库连接：{host}:{port}/{db_name}，用户：{user}")

    # 使用 mysqldump 直接连接
    env = os.environ.copy()
    env["MYSQL_PWD"] = pwd
    cmd = [
        "mysqldump", "-u", user, "-h", host, "-P", port,
        "--all-databases", "--single-transaction", "--routines", "--triggers",
        f"--result-file={sql_path}",
    ]
    log.write(f"执行命令：mysqldump -u {user} -h {host} -P {port} --all-databases ...")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"mysqldump 失败 (exit={result.returncode}): {result.stderr[:500]}")

    dump_size = os.path.getsize(sql_path) if os.path.exists(sql_path) else 0
    log.write(f"SQL 文件大小：{dump_size / (1024 * 1024):.1f} MB")
    return sql_path


def _collect_configs(output_dir: str, log: LogCapture) -> int:
    """收集系统配置文件，返回收集到的文件数量。"""
    configs_dir = os.path.join(output_dir, "configs")
    os.makedirs(configs_dir, exist_ok=True)

    # 容器内 /app 即 backend/ 目录
    app_dir = "/app"
    # 项目根目录的配置文件可能在 /app/.. (如果挂载了整个项目)
    # 实际上只有 /app 被挂载，所以只收集 /app 内的配置
    config_files = [
        # 后端配置（可访问）
        ("/app/Dockerfile", "backend_Dockerfile"),
        ("/app/Dockerfile.worker", "backend_Dockerfile.worker"),
        ("/app/requirements.txt", "backend_requirements.txt"),
        ("/app/.env", "backend_.env"),
    ]

    copied = 0
    for src_path, dst_name in config_files:
        if os.path.isfile(src_path):
            shutil.copy2(src_path, os.path.join(configs_dir, dst_name))
            log.write(f"  收集：{dst_name}")
            copied += 1
        else:
            log.write(f"  跳过（不存在）：{dst_name}")

    # 尝试通过环境变量记录关键配置
    env_info = []
    for key in ["DATABASE_URL", "REDIS_URL", "JWT_ALGORITHM", "TZ"]:
        val = os.environ.get(key, "")
        if val:
            # 隐藏密码
            if "DATABASE_URL" in key or "REDIS_URL" in key:
                val = re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', val)
            env_info.append(f"{key}={val}")
    if env_info:
        with open(os.path.join(configs_dir, "env_summary.txt"), "w") as f:
            f.write("\n".join(env_info))
        log.write(f"  环境变量摘要已保存 ({len(env_info)} 项)")

    return copied


def _export_images(output_dir: str, log: LogCapture) -> int:
    """导出 Docker 镜像为 tar 文件。需要 Docker 命令可用。"""
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # 检查 Docker 是否可用
    try:
        result = subprocess.run(
            ["docker", "info"], check=True, capture_output=True, timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        log.write("Docker 不可用（容器内无 Docker 命令），跳过镜像导出")
        log.write("提示：如需备份镜像，请在宿主机上运行 docker save 命令")
        return 0

    # 发现 OmniView 相关镜像
    try:
        result = subprocess.run(
            ["docker", "images", "--filter", "reference=omniview-*",
             "--format", "{{.Repository}}:{{.Tag}}"],
            check=True, capture_output=True, text=True, timeout=30,
        )
        omniview_images = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    except subprocess.CalledProcessError:
        omniview_images = []

    # 基础镜像
    base_images = ["mysql:8.0.40", "redis:alpine"]
    all_images = base_images + omniview_images

    exported = 0
    for img in all_images:
        try:
            safe_name = img.replace(":", "_").replace("/", "_")
            tar_path = os.path.join(images_dir, f"{safe_name}.tar")
            subprocess.run(
                ["docker", "save", img, "-o", tar_path],
                check=True, capture_output=True, timeout=600,
            )
            log.write(f"  导出镜像：{img}")
            exported += 1
        except subprocess.CalledProcessError as e:
            log.write(f"  镜像导出失败 {img}：{e.stderr.decode() if e.stderr else str(e)[:200]}")

    log.write(f"共导出 {exported}/{len(all_images)} 个镜像")
    return exported


def _archive_uploads(output_dir: str, log: LogCapture) -> str:
    """打包上传文件目录。"""
    # 容器内 uploads 目录位置
    uploads_dir = "/app/uploads"
    tar_path = os.path.join(output_dir, "uploads.tar.gz")

    if os.path.isdir(uploads_dir):
        file_count = sum(1 for _ in os.listdir(uploads_dir))
        if file_count > 0:
            with tarfile.open(tar_path, "w:gz") as tar:
                tar.add(uploads_dir, arcname="uploads")
            tar_size = os.path.getsize(tar_path)
            log.write(f"打包 {file_count} 个文件，大小 {tar_size / 1024:.0f} KB")
        else:
            with open(os.path.join(output_dir, "uploads_empty.txt"), "w") as f:
                f.write("no uploads")
            log.write("上传文件目录为空")
    else:
        with open(os.path.join(output_dir, "uploads_empty.txt"), "w") as f:
            f.write("uploads dir not found")
        log.write("上传文件目录不存在，跳过")

    return tar_path if os.path.exists(tar_path) else output_dir


def _create_final_archive(source_dir: str, archive_path: str, log: LogCapture) -> str:
    """将备份工作目录打包为单个 tar.gz 文件。"""
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in sorted(os.listdir(source_dir)):
            tar.add(os.path.join(source_dir, item), arcname=item)
    return archive_path


def _upload_ftp(local_path: str, job, log: LogCapture) -> bool:
    """通过 FTP 上传文件到远程服务器。"""
    ftp = ftplib.FTP()
    try:
        log.write(f"连接到 {job.ftp_host}:{job.ftp_port} ...")
        ftp.connect(job.ftp_host, job.ftp_port, timeout=30)
        ftp.login(job.ftp_user, job.ftp_password)
        ftp.set_pasv(True)
        log.write("FTP 登录成功")

        # 创建远程目录（逐级创建）
        if job.ftp_remote_path:
            remote_dir = job.ftp_remote_path.strip("/")
            parts = [p for p in remote_dir.split("/") if p]
            for part in parts:
                try:
                    ftp.cwd(part)
                except ftplib.error_perm:
                    ftp.mkd(part)
                    ftp.cwd(part)
                    log.write(f"  创建远程目录：{part}")
            log.write(f"远程目录：/{remote_dir}")

        # 上传文件
        filename = os.path.basename(local_path)
        file_size = os.path.getsize(local_path)
        log.write(f"开始上传 {filename} ({file_size / (1024 * 1024):.1f} MB)...")
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {filename}", f)
        log.write("上传完成")
        return True
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


def test_ftp_connection(host: str, port: int, user: str, password: str) -> dict:
    """测试 FTP 服务器连接。"""
    ftp = ftplib.FTP()
    try:
        ftp.connect(host, port, timeout=10)
        ftp.login(user, password)
        ftp.quit()
        return {"success": True, "message": "FTP 连接测试成功"}
    except ftplib.error_perm as e:
        return {"success": False, "message": f"FTP 认证失败：{e}"}
    except ftplib.error_temp as e:
        return {"success": False, "message": f"FTP 临时错误：{e}"}
    except Exception as e:
        return {"success": False, "message": f"FTP 连接失败：{e}"}


def verify_backup(history_id: int) -> dict:
    """验证备份文件完整性（只读，不影响生产环境）。"""
    from app.database import SessionLocal
    from app.models.backup_history import BackupHistory

    db = SessionLocal()
    try:
        history = db.query(BackupHistory).get(history_id)
        if not history:
            return {"success": False, "message": "备份记录不存在"}

        archive_path = history.file_path
        if not archive_path or not os.path.exists(archive_path):
            if history.storage_location == "ftp":
                return {"success": False, "message": "FTP 远程文件需先下载到本地再验证"}
            return {"success": False, "message": "备份文件不存在"}

        tmp_dir = tempfile.mkdtemp(prefix="backup_verify_")
        report = {"success": True, "checks": [], "message": ""}

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(tmp_dir)

            # 检查数据库 SQL 文件
            sql_file = os.path.join(tmp_dir, "database.sql")
            if os.path.exists(sql_file):
                with open(sql_file, "r", encoding="utf-8", errors="ignore") as f:
                    head = f.read(5000)
                has_create = "CREATE" in head.upper() or "INSERT" in head.upper()
                size_mb = os.path.getsize(sql_file) / (1024 * 1024)
                if has_create and os.path.getsize(sql_file) > 100:
                    report["checks"].append(f"✅ 数据库 SQL 有效 ({size_mb:.1f} MB)")
                else:
                    report["checks"].append(f"⚠️ 数据库 SQL 可能不完整 ({size_mb:.1f} MB)")
                    report["success"] = False

            # 检查配置文件
            configs_dir = os.path.join(tmp_dir, "configs")
            if os.path.isdir(configs_dir):
                config_files = os.listdir(configs_dir)
                report["checks"].append(f"✅ 配置文件 {len(config_files)} 个")
            else:
                report["checks"].append("ℹ️ 无配置文件")

            # 检查 Docker 镜像
            images_dir = os.path.join(tmp_dir, "images")
            if os.path.isdir(images_dir):
                image_files = [f for f in os.listdir(images_dir) if f.endswith(".tar")]
                if image_files:
                    test_file = os.path.join(images_dir, image_files[0])
                    try:
                        subprocess.run(
                            ["tar", "-tf", test_file],
                            check=True, capture_output=True, timeout=30,
                        )
                        report["checks"].append(f"✅ Docker 镜像 {len(image_files)} 个（可读取）")
                    except subprocess.CalledProcessError:
                        report["checks"].append(f"⚠️ Docker 镜像 {len(image_files)} 个（读取失败）")
                        report["success"] = False
                else:
                    report["checks"].append("ℹ️ 无 Docker 镜像")
            else:
                report["checks"].append("ℹ️ 无 Docker 镜像")

            # 检查上传文件
            uploads_tar = os.path.join(tmp_dir, "uploads.tar.gz")
            if os.path.exists(uploads_tar):
                with tarfile.open(uploads_tar, "r:gz") as ut:
                    members = ut.getmembers()
                    report["checks"].append(f"✅ 上传文件 {len(members)} 个条目")
            elif os.path.exists(os.path.join(tmp_dir, "uploads_empty.txt")):
                report["checks"].append("ℹ️ 上传文件目录为空")
            else:
                report["checks"].append("ℹ️ 无上传文件")

            report["message"] = "验证完成：" + "；".join(report["checks"])
            if report["success"]:
                history.verified = True
                history.verified_at = datetime.now()
                db.commit()

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return report

    finally:
        db.close()


def _cleanup_retention(job, log: LogCapture = None) -> None:
    """清理超过保留期的旧备份文件。"""
    if job.retention_days <= 0:
        if log:
            log.write("保留天数=0，跳过清理")
        return

    local_path = job.local_path
    if not local_path or not os.path.isdir(local_path):
        return

    import time
    cutoff = time.time() - job.retention_days * 86400
    pattern = re.compile(r"^backup_.*\.tar\.gz$")

    deleted = 0
    for fname in os.listdir(local_path):
        if not pattern.match(fname):
            continue
        fpath = os.path.join(local_path, fname)
        try:
            if os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                deleted += 1
                msg = f"清理过期备份：{fname}"
                if log:
                    log.write(msg)
                else:
                    logger.info(msg)
        except OSError:
            pass

    if deleted > 0:
        msg = f"保留策略清理完成：删除 {deleted} 个过期备份"
        if log:
            log.write(msg)
        else:
            logger.info(msg)
