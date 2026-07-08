"""系统备份执行引擎 — 数据库导出、文件收集、镜像导出、FTP 上传、验证、清理"""
import os
import re
import gzip
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


def run_backup(job_id: int, manual: bool = False) -> int:
    """执行一次备份，返回 BackupHistory.id。"""
    from app.database import SessionLocal
    from app.models.backup_job import BackupJob
    from app.models.backup_history import BackupHistory

    db = SessionLocal()
    try:
        job = db.query(BackupJob).get(job_id)
        if not job:
            raise ValueError(f"备份任务不存在: {job_id}")

        # 检查是否已有运行中的备份
        running = db.query(BackupHistory).filter(
            BackupHistory.job_id == job_id,
            BackupHistory.status == "running",
        ).first()
        if running:
            logger.warning("备份任务 %s 已有运行中的备份，跳过本次执行", job.name)
            return running.id

        # 生成时间戳和目录名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir_name = f"backup_{job.name.replace(' ', '_')}_{timestamp}"
        work_dir = os.path.join(job.local_path or tempfile.gettempdir(), backup_dir_name)
        os.makedirs(work_dir, exist_ok=True)

        # 解析备份内容
        contents = [c.strip() for c in job.backup_contents.split(",") if c.strip()]
        content_labels = [CONTENT_LABELS.get(c, c) for c in contents]

        # 创建历史记录
        now = datetime.now()
        history = BackupHistory(
            job_id=job.id,
            job_name=job.name,
            status="running",
            started_at=now,
            storage_location=job.mode,
            content_summary=",".join(content_labels),
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        try:
            # 执行各项备份
            results = {}
            if "database" in contents:
                results["database"] = _dump_database(work_dir)
            if "configs" in contents:
                results["configs"] = _collect_configs(work_dir)
            if "images" in contents:
                results["images"] = _export_images(work_dir)
            if "uploads" in contents:
                results["uploads"] = _archive_uploads(work_dir)

            # 打包
            archive_name = f"{backup_dir_name}.tar.gz"
            archive_path = os.path.join(job.local_path or tempfile.gettempdir(), archive_name)
            _create_final_archive(work_dir, archive_path)

            # FTP 上传（如需要）
            if job.mode == "ftp":
                try:
                    _upload_ftp(archive_path, job)
                    # 上传成功后删除本地文件
                    os.remove(archive_path)
                    history.file_path = f"ftp://{job.ftp_host}:{job.ftp_port}{job.ftp_remote_path or '/'}{archive_name}"
                except Exception as e:
                    logger.error("FTP 上传失败：%s", e)
                    # FTP 失败时保留本地文件
                    history.file_path = archive_path
                    history.storage_location = "local"
            else:
                history.file_path = archive_path

            file_size = os.path.getsize(archive_path) if os.path.exists(archive_path) else 0
            history.file_name = archive_name
            history.file_size = file_size
            history.status = "success"
            history.completed_at = datetime.now()
            if history.started_at:
                history.duration_seconds = int((history.completed_at - history.started_at).total_seconds())

            # 更新任务状态
            job.last_run_at = history.completed_at
            job.last_status = "success"
            db.commit()

            logger.info("备份完成：%s → %s (%.1f MB)", job.name, archive_name, file_size / (1024 * 1024))

            # 清理临时工作目录
            shutil.rmtree(work_dir, ignore_errors=True)

            # 执行保留策略
            _cleanup_retention(job)

        except Exception as e:
            logger.exception("备份失败 job_id=%s name=%s", job_id, job.name)
            history.status = "failed"
            history.error_message = str(e)[:2000]
            history.completed_at = datetime.now()
            if history.started_at:
                history.duration_seconds = int((history.completed_at - history.started_at).total_seconds())
            job.last_run_at = history.completed_at
            job.last_status = "failed"
            db.commit()
            # 清理临时目录
            shutil.rmtree(work_dir, ignore_errors=True)

        return history.id

    finally:
        db.close()


def _dump_database(output_dir: str) -> str:
    """导出 MySQL 数据库，返回生成的 SQL 文件路径。"""
    password = os.environ.get("MYSQL_ROOT_PASSWORD", "")
    sql_path = os.path.join(output_dir, "database.sql")

    # 使用 docker exec 执行 mysqldump
    cmd = [
        "docker", "exec", "omniview-mysql",
        "mysqldump", "-u", "root", f"-p{password}",
        "--all-databases", "--single-transaction", "--routines", "--triggers",
        "--result-file=/tmp/backup_db.sql",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        # 从容器复制文件出来
        subprocess.run(
            ["docker", "cp", "omniview-mysql:/tmp/backup_db.sql", sql_path],
            check=True, capture_output=True, text=True, timeout=60,
        )
        # 清理容器内临时文件
        subprocess.run(
            ["docker", "exec", "omniview-mysql", "rm", "-f", "/tmp/backup_db.sql"],
            check=False, capture_output=True, text=True, timeout=30,
        )
        logger.info("数据库导出完成：%s", sql_path)
    except subprocess.CalledProcessError as e:
        # 尝试直接从宿主机 mysqldump（非 Docker 环境）
        logger.warning("docker exec 导出失败，尝试本机 mysqldump：%s", e.stderr)
        db_url = os.environ.get("DATABASE_URL", "")
        # 从 DATABASE_URL 解析连接参数
        # 格式: mysql+pymysql://user:pass@host:port/db
        match = re.match(r"mysql\+pymysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", db_url)
        if match:
            user, pwd, host, port, db_name = match.groups()
            env = os.environ.copy()
            env["MYSQL_PWD"] = pwd
            cmd2 = [
                "mysqldump", "-u", user, "-h", host, "-P", port,
                "--all-databases", "--single-transaction", "--routines", "--triggers",
                f"--result-file={sql_path}",
            ]
            subprocess.run(cmd2, check=True, capture_output=True, text=True, timeout=600, env=env)
            logger.info("数据库导出完成（本机）：%s", sql_path)
        else:
            raise RuntimeError(f"数据库导出失败：无法解析 DATABASE_URL，docker exec 错误：{e.stderr}")

    return sql_path


def _collect_configs(output_dir: str) -> str:
    """收集系统配置文件，返回配置文件存档路径。"""
    configs_dir = os.path.join(output_dir, "configs")
    os.makedirs(configs_dir, exist_ok=True)

    # 项目根目录（容器内 /app 即 backend 目录，需返回上级）
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
    project_root = os.path.dirname(app_dir)  # 项目根目录

    # 关键配置文件列表（相对于项目根目录）
    config_files = [
        ".env",
        "docker-compose.yml",
        "docker-compose.worker.yml",
        "docker-compose.local.yml",
        "backend/Dockerfile",
        "backend/Dockerfile.worker",
        "backend/requirements.txt",
        "frontend/Dockerfile",
        "frontend/nginx.conf",
    ]

    copied = 0
    for f in config_files:
        src = os.path.join(project_root, f)
        dst = os.path.join(configs_dir, f.replace("/", "_").replace("\\", "_"))
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied += 1

    logger.info("配置文件收集完成：%d 个文件", copied)
    return configs_dir


def _export_images(output_dir: str) -> str:
    """导出 Docker 镜像为 tar 文件。需要 Docker socket 访问权限。"""
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # 检查 Docker 是否可用
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True, timeout=10)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Docker 不可用，跳过镜像导出")
        return images_dir

    # 发现 OmniView 相关镜像
    try:
        result = subprocess.run(
            ["docker", "images", "--filter", "reference=omniview-*", "--format", "{{.Repository}}:{{.Tag}}"],
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
            exported += 1
        except subprocess.CalledProcessError as e:
            logger.warning("镜像导出失败 %s：%s", img, e.stderr)

    logger.info("Docker 镜像导出完成：%d/%d", exported, len(all_images))
    return images_dir


def _archive_uploads(output_dir: str) -> str:
    """打包上传文件目录。"""
    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
    tar_path = os.path.join(output_dir, "uploads.tar.gz")

    if os.path.isdir(uploads_dir) and os.listdir(uploads_dir):
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(uploads_dir, arcname="uploads")
        logger.info("上传文件打包完成：%s", tar_path)
    else:
        # 创建空标记文件
        with open(os.path.join(output_dir, "uploads_empty.txt"), "w") as f:
            f.write("no uploads")
        logger.info("上传文件目录为空，跳过")
    return tar_path if os.path.exists(tar_path) else output_dir


def _create_final_archive(source_dir: str, archive_path: str) -> str:
    """将备份工作目录打包为单个 tar.gz 文件。"""
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in os.listdir(source_dir):
            tar.add(os.path.join(source_dir, item), arcname=item)
    logger.info("备份压缩包创建完成：%s", archive_path)
    return archive_path


def _upload_ftp(local_path: str, job) -> bool:
    """通过 FTP 上传文件到远程服务器。"""
    ftp = ftplib.FTP()
    try:
        ftp.connect(job.ftp_host, job.ftp_port, timeout=30)
        ftp.login(job.ftp_user, job.ftp_password)
        ftp.set_pasv(True)

        # 创建远程目录（逐级创建）
        if job.ftp_remote_path:
            remote_dir = job.ftp_remote_path.strip("/")
            parts = remote_dir.split("/")
            for part in parts:
                if not part:
                    continue
                try:
                    ftp.cwd(part)
                except ftplib.error_perm:
                    ftp.mkd(part)
                    ftp.cwd(part)

        # 上传文件
        filename = os.path.basename(local_path)
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {filename}", f)

        logger.info("FTP 上传完成：%s → %s:%s/%s", filename, job.ftp_host, job.ftp_port, filename)
        return True
    except Exception as e:
        logger.error("FTP 上传失败：%s", e)
        raise
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

        # 获取备份文件
        archive_path = history.file_path
        if not archive_path or not os.path.exists(archive_path):
            if history.storage_location == "ftp":
                return {"success": False, "message": "FTP 远程文件需先下载到本地再验证"}
            return {"success": False, "message": "备份文件不存在"}

        # 解压到临时目录
        tmp_dir = tempfile.mkdtemp(prefix="backup_verify_")
        report = {"success": True, "checks": [], "message": ""}

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(tmp_dir)

            items = os.listdir(tmp_dir)

            # 检查数据库 SQL 文件
            sql_file = os.path.join(tmp_dir, "database.sql")
            if os.path.exists(sql_file):
                with open(sql_file, "r", encoding="utf-8", errors="ignore") as f:
                    head = f.read(5000)
                has_create = "CREATE" in head.upper() or "INSERT" in head.upper()
                size_mb = os.path.getsize(sql_file) / (1024 * 1024)
                if has_create and os.path.getsize(sql_file) > 100:
                    report["checks"].append(f"✅ 数据库 SQL 有效 ({size_mb:.1f} MB，含 CREATE/INSERT)")
                else:
                    report["checks"].append(f"⚠️ 数据库 SQL 可能不完整 ({size_mb:.1f} MB)")
                    report["success"] = False

            # 检查配置文件
            configs_dir = os.path.join(tmp_dir, "configs")
            if os.path.isdir(configs_dir):
                config_files = os.listdir(configs_dir)
                report["checks"].append(f"✅ 配置文件 {len(config_files)} 个")
            else:
                report["checks"].append("ℹ️ 无配置文件（未选择此项）")

            # 检查 Docker 镜像
            images_dir = os.path.join(tmp_dir, "images")
            if os.path.isdir(images_dir):
                image_files = [f for f in os.listdir(images_dir) if f.endswith(".tar")]
                if image_files:
                    # 用 tar -t 验证第一个
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
                report["checks"].append("ℹ️ 无 Docker 镜像（未选择此项）")

            # 检查上传文件
            uploads_tar = os.path.join(tmp_dir, "uploads.tar.gz")
            if os.path.exists(uploads_tar):
                with tarfile.open(uploads_tar, "r:gz") as ut:
                    members = ut.getmembers()
                    report["checks"].append(f"✅ 上传文件 {len(members)} 个条目")
            elif os.path.exists(os.path.join(tmp_dir, "uploads_empty.txt")):
                report["checks"].append("ℹ️ 上传文件目录为空")
            else:
                report["checks"].append("ℹ️ 无上传文件（未选择此项）")

            report["message"] = "验证完成：" + "；".join(report["checks"])
            if report["success"]:
                history.verified = True
                history.verified_at = datetime.now()
                db.commit()
                logger.info("备份验证通过 history_id=%s", history_id)
            else:
                logger.warning("备份验证发现问题 history_id=%s", history_id)

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return report

    finally:
        db.close()


def _cleanup_retention(job) -> None:
    """清理超过保留期的旧备份文件。"""
    if job.retention_days <= 0:
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
                logger.info("清理过期备份：%s", fname)
        except OSError:
            pass

    if deleted > 0:
        logger.info("保留策略清理完成：删除 %d 个过期备份", deleted)
