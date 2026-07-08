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


def _flush_log(history_id: int, log: LogCapture):
    """将当前日志实时写入数据库，方便前端轮询查看进度。"""
    try:
        from app.database import SessionLocal
        from app.models.backup_history import BackupHistory
        db = SessionLocal()
        try:
            h = db.query(BackupHistory).get(history_id)
            if h:
                h.log_output = log.getvalue()
                db.commit()
        finally:
            db.close()
    except Exception:
        pass  # 日志刷新失败不应中断备份


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
                _flush_log(history.id, log)
                try:
                    _dump_database(work_dir, log)
                    log.write("数据库导出完成")
                    _flush_log(history.id, log)
                except Exception as e:
                    log.write(f"数据库导出失败：{e}")
                    _flush_log(history.id, log)
                    raise

            # 2. 配置文件收集
            if "configs" in contents:
                log.write("── 开始收集配置文件 ──")
                _flush_log(history.id, log)
                try:
                    n = _collect_configs(work_dir, log)
                    log.write(f"配置文件收集完成：{n} 个文件")
                    _flush_log(history.id, log)
                except Exception as e:
                    log.write(f"配置文件收集失败：{e}")
                    _flush_log(history.id, log)
                    raise

            # 3. Docker 镜像导出
            if "images" in contents:
                log.write("── 开始导出 Docker 镜像 ──")
                _flush_log(history.id, log)
                try:
                    n = _export_images(work_dir, log)
                    log.write(f"Docker 镜像导出：{n} 个")
                    _flush_log(history.id, log)
                except Exception as e:
                    log.write(f"Docker 镜像导出失败（已跳过）：{e}")
                    _flush_log(history.id, log)

            # 4. 上传文件打包
            if "uploads" in contents:
                log.write("── 开始打包上传文件 ──")
                _flush_log(history.id, log)
                try:
                    _archive_uploads(work_dir, log)
                    log.write("上传文件打包完成")
                    _flush_log(history.id, log)
                except Exception as e:
                    log.write(f"上传文件打包失败：{e}")
                    _flush_log(history.id, log)
                    raise

            # 5. 创建最终压缩包
            log.write("── 创建压缩包 ──")
            _flush_log(history.id, log)
            archive_name = f"{backup_dir_name}.tar.gz"
            archive_path = os.path.join(tempfile.gettempdir(), archive_name)
            _create_final_archive(work_dir, archive_path, log)
            archive_size = os.path.getsize(archive_path)
            log.write(f"压缩包创建完成：{archive_name} ({archive_size / (1024 * 1024):.1f} MB)")
            _flush_log(history.id, log)

            # 6. FTP 上传（如需要）
            if job.mode == "ftp":
                log.write(f"── 上传到 FTP：{job.ftp_host}:{job.ftp_port} ──")
                _flush_log(history.id, log)
                try:
                    _upload_ftp(archive_path, job, log)
                    log.write("FTP 上传成功")
                    os.remove(archive_path)
                    history.file_path = f"ftp://{job.ftp_host}:{job.ftp_port}{job.ftp_remote_path or '/'}{archive_name}"
                    _flush_log(history.id, log)
                except Exception as e:
                    log.write(f"FTP 上传失败：{e}，保留本地文件")
                    history.file_path = archive_path
                    history.storage_location = "local"
                    _flush_log(history.id, log)
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
    """导出 Docker 镜像为 tar 文件。通过挂载的 docker.sock 与宿主机 Docker 通信。"""
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # 检查 Docker 是否可用
    try:
        subprocess.run(
            ["docker", "info"], check=True, capture_output=True, timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        log.write("Docker 不可用（容器内无 Docker 命令或 socket 未挂载），跳过镜像导出")
        log.write("提示：请在 docker-compose.yml 中挂载 /var/run/docker.sock")
        return 0

    # 方法1：从运行中的容器发现镜像（最可靠）
    image_set = set()
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Image}}"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        for line in result.stdout.strip().split("\n"):
            img = line.strip()
            if img and ":" in img:  # 过滤掉 <none> 等无效值
                image_set.add(img)
        log.write(f"从容器发现 {len(image_set)} 个镜像")
    except subprocess.CalledProcessError as e:
        log.write(f"容器查询失败：{e.stderr[:200] if e.stderr else str(e)[:200]}")

    # 方法2：补充发现本地构建的项目镜像
    for pattern in ["omniview-*", "claudecode-*"]:
        try:
            result = subprocess.run(
                ["docker", "images", "--filter", f"reference={pattern}",
                 "--format", "{{.Repository}}:{{.Tag}}"],
                check=True, capture_output=True, text=True, timeout=15,
            )
            for line in result.stdout.strip().split("\n"):
                img = line.strip()
                if img and ":" in img:
                    image_set.add(img)
        except subprocess.CalledProcessError:
            pass

    if not image_set:
        log.write("未发现任何 Docker 镜像")
        return 0

    all_images = sorted(image_set)
    log.write(f"共发现 {len(all_images)} 个镜像，开始导出...")

    # 先查询各镜像大小，避免导出超大镜像时超时
    img_sizes = {}
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        for line in result.stdout.strip().split("\n"):
            if "\t" in line:
                name, size = line.split("\t", 1)
                img_sizes[name] = size
    except Exception:
        pass

    exported = 0
    skipped = 0
    for idx, img in enumerate(all_images, 1):
        safe_name = img.replace(":", "_").replace("/", "_")
        tar_path = os.path.join(images_dir, f"{safe_name}.tar")
        size_hint = img_sizes.get(img, "未知")
        try:
            log.write(f"  [{idx}/{len(all_images)}] 导出：{img} (镜像大小: {size_hint})")
            # 每导出一个镜像前刷新日志
            import sys
            # 使用 Popen 以便在超时时终止子进程
            proc = subprocess.Popen(
                ["docker", "save", img, "-o", tar_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            try:
                stdout, stderr = proc.communicate(timeout=600)  # 每个镜像最多10分钟
                if proc.returncode != 0:
                    err = stderr.decode()[:300] if stderr else f"exit={proc.returncode}"
                    raise subprocess.CalledProcessError(proc.returncode, proc.args, stderr)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                log.write(f"    超时（10分钟），已跳过")
                skipped += 1
                continue

            tar_size = os.path.getsize(tar_path) if os.path.exists(tar_path) else 0
            log.write(f"    完成 ({tar_size / (1024 * 1024):.1f} MB)")
            exported += 1
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode() if isinstance(e.stderr, bytes) else str(e.stderr)[:300] if e.stderr else str(e)[:300]
            log.write(f"    失败：{err}")
            skipped += 1
        except Exception as e:
            log.write(f"    失败：{e}")
            skipped += 1

    log.write(f"镜像导出完成：成功 {exported}，跳过 {skipped}，总计 {len(all_images)}")
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


def verify_backup(history_id: int, local_path: str = None) -> dict:
    """验证备份文件完整性（只读，不影响生产环境）。返回详细验证日志。

    Args:
        history_id: 备份历史记录 ID
        local_path: 可选，FTP 文件先下载到本地的路径（验证完成后不会删除）
    """
    from app.database import SessionLocal
    from app.models.backup_history import BackupHistory

    log = LogCapture()
    db = SessionLocal()
    try:
        history = db.query(BackupHistory).get(history_id)
        if not history:
            log.write("验证失败：备份记录不存在")
            return {"success": False, "message": "备份记录不存在", "log_output": log.getvalue()}

        log.write(f"开始验证备份：{history.job_name}")
        log.write(f"备份文件：{history.file_name or '未知'}")
        log.write(f"存储位置：{history.storage_location}")
        log.write(f"内容摘要：{history.content_summary}")

        # 优先使用传入的本地路径（FTP 已下载），否则使用记录中的路径
        archive_path = local_path or history.file_path
        if archive_path and history.storage_location == "ftp" and not local_path:
            log.write("正在从 FTP 下载备份文件...")

        if not archive_path or not os.path.exists(archive_path):
            if history.storage_location == "ftp" and not local_path:
                log.write("验证失败：FTP 远程文件需先下载到本地再验证")
                return {"success": False, "message": "FTP 远程文件需先下载到本地再验证", "log_output": log.getvalue()}
            log.write(f"验证失败：备份文件不存在 ({archive_path})")
            return {"success": False, "message": "备份文件不存在", "log_output": log.getvalue()}

        # 检查文件基本信息
        file_stat = os.stat(archive_path)
        log.write(f"文件大小：{file_stat.st_size / (1024 * 1024):.1f} MB")
        log.write(f"修改时间：{datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")

        report = {"success": True, "checks": [], "message": "", "log_output": ""}
        tmp_dir = tempfile.mkdtemp(prefix="backup_verify_")

        try:
            # 解压
            log.write("── 解压备份文件 ──")
            try:
                with tarfile.open(archive_path, "r:gz") as tar:
                    members = tar.getmembers()
                    log.write(f"压缩包包含 {len(members)} 个条目：")
                    for m in members:
                        log.write(f"  - {m.name} ({m.size:,} 字节{' [目录]' if m.isdir() else ''})")
                    tar.extractall(tmp_dir)
                log.write("解压完成")
            except Exception as e:
                log.write(f"解压失败：{e}")
                report["success"] = False
                report["checks"].append(f"❌ 解压失败：{e}")
                report["message"] = f"验证失败：解压异常 - {e}"
                history.verify_log = log.getvalue()
                db.commit()
                return report

            # 1. 检查数据库 SQL 文件
            log.write("── 检查数据库 SQL 文件 ──")
            sql_file = os.path.join(tmp_dir, "database.sql")
            if os.path.exists(sql_file):
                sql_size = os.path.getsize(sql_file)
                log.write(f"SQL 文件大小：{sql_size / (1024 * 1024):.1f} MB")
                with open(sql_file, "r", encoding="utf-8", errors="ignore") as f:
                    head = f.read(5000)
                has_create = "CREATE" in head.upper()
                has_insert = "INSERT" in head.upper()
                has_drop = "DROP" in head.upper()
                line_count = head.count("\n") + 1
                log.write(f"文件头 {line_count} 行：CREATE={has_create} INSERT={has_insert} DROP={has_drop}")
                if has_create and sql_size > 100:
                    log.write("✅ 数据库 SQL 文件有效")
                    report["checks"].append(f"✅ 数据库 SQL 有效 ({sql_size / (1024 * 1024):.1f} MB)")
                elif sql_size <= 100:
                    log.write("⚠️ SQL 文件过小，可能不完整")
                    report["checks"].append(f"⚠️ 数据库 SQL 文件仅 {sql_size} 字节，可能为空")
                    report["success"] = False
                else:
                    log.write("⚠️ SQL 文件缺少 CREATE/INSERT 语句")
                    report["checks"].append(f"⚠️ 数据库 SQL ({sql_size / (1024 * 1024):.1f} MB) 缺少 CREATE/INSERT 语句")
                    report["success"] = False
            else:
                log.write("ℹ️ 备份中无数据库 SQL 文件")
                report["checks"].append("ℹ️ 无数据库文件（未选择此项）")

            # 2. 检查配置文件
            log.write("── 检查配置文件 ──")
            configs_dir = os.path.join(tmp_dir, "configs")
            if os.path.isdir(configs_dir):
                config_files = sorted(os.listdir(configs_dir))
                log.write(f"配置文件目录包含 {len(config_files)} 个文件：")
                for cf in config_files:
                    cf_path = os.path.join(configs_dir, cf)
                    cf_size = os.path.getsize(cf_path) if os.path.isfile(cf_path) else 0
                    log.write(f"  - {cf} ({cf_size:,} 字节)")
                report["checks"].append(f"✅ 配置文件 {len(config_files)} 个")
            else:
                log.write("ℹ️ 备份中无配置文件目录")
                report["checks"].append("ℹ️ 无配置文件（未选择此项）")

            # 3. 检查 Docker 镜像
            log.write("── 检查 Docker 镜像 ──")
            images_dir = os.path.join(tmp_dir, "images")
            if os.path.isdir(images_dir):
                image_files = sorted([f for f in os.listdir(images_dir) if f.endswith(".tar")])
                if image_files:
                    log.write(f"Docker 镜像目录包含 {len(image_files)} 个 tar 文件：")
                    all_valid = True
                    for img in image_files:
                        img_path = os.path.join(images_dir, img)
                        img_size = os.path.getsize(img_path)
                        log.write(f"  - {img} ({img_size / (1024 * 1024):.1f} MB)")
                        try:
                            result = subprocess.run(
                                ["tar", "-tf", img_path],
                                check=True, capture_output=True, text=True, timeout=30,
                            )
                            layer_count = len(result.stdout.strip().split("\n"))
                            log.write(f"    包含 {layer_count} 层，tar 结构正常")
                        except subprocess.CalledProcessError as e:
                            log.write(f"    ⚠️ tar 结构损坏：{e.stderr[:200] if e.stderr else str(e)[:200]}")
                            all_valid = False
                    if all_valid:
                        report["checks"].append(f"✅ Docker 镜像 {len(image_files)} 个（全部可读取）")
                    else:
                        report["checks"].append(f"⚠️ Docker 镜像 {len(image_files)} 个（部分损坏）")
                        report["success"] = False
                else:
                    log.write("ℹ️ 镜像目录为空")
                    report["checks"].append("ℹ️ 无 Docker 镜像（导出失败或未选择）")
            else:
                log.write("ℹ️ 备份中无 Docker 镜像目录")
                report["checks"].append("ℹ️ 无 Docker 镜像（未选择此项）")

            # 4. 检查上传文件
            log.write("── 检查上传文件 ──")
            uploads_tar = os.path.join(tmp_dir, "uploads.tar.gz")
            if os.path.exists(uploads_tar):
                uploads_size = os.path.getsize(uploads_tar)
                log.write(f"上传文件包大小：{uploads_size / 1024:.0f} KB")
                try:
                    with tarfile.open(uploads_tar, "r:gz") as ut:
                        ut_members = ut.getmembers()
                    log.write(f"包含 {len(ut_members)} 个条目：")
                    for um in ut_members[:20]:  # 最多显示20条
                        log.write(f"  - {um.name} ({um.size:,} 字节)")
                    if len(ut_members) > 20:
                        log.write(f"  ... 还有 {len(ut_members) - 20} 个条目")
                    report["checks"].append(f"✅ 上传文件 {len(ut_members)} 个条目")
                except Exception as e:
                    log.write(f"⚠️ 上传文件包损坏：{e}")
                    report["checks"].append(f"⚠️ 上传文件包无法读取：{e}")
                    report["success"] = False
            elif os.path.exists(os.path.join(tmp_dir, "uploads_empty.txt")):
                log.write("ℹ️ 上传文件目录在备份时为空")
                report["checks"].append("ℹ️ 上传文件为空（备份时无文件）")
            else:
                log.write("ℹ️ 备份中无上传文件包")
                report["checks"].append("ℹ️ 无上传文件（未选择此项）")

            # 汇总
            log.write("── 验证汇总 ──")
            report["message"] = "验证完成：" + "；".join(report["checks"])
            if report["success"]:
                log.write("✅ 验证通过：备份文件完整有效")
                history.verified = True
                history.verified_at = datetime.now()
            else:
                log.write("⚠️ 验证发现问题：备份文件可能不完整")
            history.verify_log = log.getvalue()
            db.commit()

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        report["log_output"] = log.getvalue()
        log.close()
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
