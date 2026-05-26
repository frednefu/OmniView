"""奇安信椒图（云锁）API 采集引擎"""
import hashlib
import time
import asyncio
import logging
from datetime import datetime

import urllib3
import requests

from app.database import SessionLocal
from app.models.qax import QianXinDevice, QianXinServer, QianXinPort, QianXinProcess, QianXinSoftware

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


class QianXinClient:
    """奇安信云锁 API 客户端"""

    def __init__(self, base_url: str, uuid: str, secret: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.uuid = uuid
        self.secret = secret
        self.timeout = timeout

    def _generate_token(self) -> str:
        timestamp = str(int(time.time()))
        raw = self.uuid + self.secret + timestamp
        secret_md5 = hashlib.md5(raw.encode()).hexdigest()
        return secret_md5 + self.uuid + timestamp

    def _headers(self) -> dict:
        return {
            "Api-Token": self._generate_token(),
            "Content-Type": "application/json",
        }

    def _post(self, path: str, body: dict = None) -> dict:
        url = f"{self.base_url}{path}"
        resp = requests.post(
            url,
            json=body or {},
            headers=self._headers(),
            timeout=self.timeout,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") in (1, "1", 200):
            return data
        raise RuntimeError(f"API 返回错误: code={data.get('code')}, msg={data.get('msg', data.get('message', ''))}")

    def get_server_list(self, page: int = 1, size: int = 10) -> dict:
        """获取服务器列表（单页），返回原始 API 响应用于分页判断。"""
        return self._post(
            "/api/assetSrv/machineController/searchMachineList",
            {"currentPage": page, "maxResults": size},
        )

    def get_all_servers(self, page_size: int = 100) -> list:
        """遍历所有分页，获取全部服务器列表。"""
        return self._get_all_pages(
            "/api/assetSrv/machineController/searchMachineList",
            {},
            page_size,
        )

    def _get_all_pages(self, path: str, base_body: dict, page_size: int = 100) -> list:
        """通用分页遍历，返回全部数据。"""
        all_items = []
        page = 1
        total = 0
        while True:
            body = {**base_body, "currentPage": page, "maxResults": page_size}
            result = self._post(path, body)
            items = _safe_list(result)
            if not items:
                break
            all_items.extend(items)
            inner = result.get("data")
            if isinstance(inner, dict):
                total = inner.get("total") or inner.get("totalCount") or total
            total = result.get("total") or result.get("totalCount") or total
            if total > 0 and len(all_items) >= total:
                break
            page += 1
            if page > 200:
                break
        return all_items

    def get_server_ports(self, machine_uuid: str) -> list:
        return self._get_all_pages(
            "/api/assetSrv/portController/searchMachineUuidPortList",
            {"machineUuid": machine_uuid},
        )

    def get_server_processes(self, machine_uuid: str) -> list:
        return self._get_all_pages(
            "/api/assetSrv/processController/searchMachineUuidProcessList",
            {"machineUuid": machine_uuid},
        )

    def get_server_software(self, machine_uuid: str) -> list:
        return self._get_all_pages(
            "/api/assetSrv/softwareAppController/searchMachineUuidUserList",
            {"machineUuid": machine_uuid},
        )


def _safe_list(data: dict, key: str = "list") -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in (key, "data", "rows", "items", "result", "records"):
            val = data.get(k)
            if isinstance(val, list):
                return val
        inner = data.get("data")
        if isinstance(inner, dict):
            for k in (key, "rows", "items", "list", "result"):
                val = inner.get(k)
                if isinstance(val, list):
                    return val
    return []


def _update_scan_log(scan_log_id: int, success: bool, server_count: int, error_msg: str | None = None):
    """更新扫描日志为最终状态。"""
    from app.models.scan_log import ScanLog, ScanStatus

    try:
        _db = SessionLocal()
        try:
            log = _db.query(ScanLog).get(scan_log_id)
            if log:
                log.status = ScanStatus.success if success else ScanStatus.failed
                log.hosts_found = server_count
                log.error_message = error_msg
                log.completed_at = datetime.now()
                if log.started_at:
                    log.duration_seconds = round((datetime.now() - log.started_at).total_seconds(), 1)
                _db.commit()
        finally:
            _db.close()
    except Exception:
        logger.exception("更新椒图扫描日志失败 scan_log_id=%s", scan_log_id)


def _update_scan_log_failed(scan_log_id: int | None, server_count: int, error_msg: str):
    """提前终止时更新扫描日志为失败。"""
    if not scan_log_id:
        return
    _update_scan_log(scan_log_id, False, server_count, error_msg)


async def _run_qax_scan_async(device_id: int, scan_log_id: int | None = None):
    """异步扫描椒图设备，采集服务器清单及端口/进程/软件详情并写入数据库。

    分阶段执行，避免在 API 调用期间持有数据库会话：
    1. 快照旧服务器数据（用于变更历史 diff）
    2. 通过 API 获取服务器列表
    3. 写入服务器基本信息（短事务）
    4. 逐台采集详情并独立写入（每台服务器一个短事务）
    5. 写入变更历史 + 更新设备状态

    注意：最外层 try/except 确保无论何种异常都能更新设备状态和扫描日志。
    """
    from app.models.scan_log import ScanLog, ScanStatus
    from app.services.history_service import detect_qax_changes

    start_time = datetime.now()
    logger.info("椒图扫描开始 device_id=%s scan_log_id=%s", device_id, scan_log_id)

    server_count = 0
    detail_success = 0
    detail_failed = 0
    scan_success = False
    error_msg = None
    old_by_key = {}
    device_name = ""
    device = None

    try:
        # 阶段 0：验证设备 + 快照旧数据
        db = SessionLocal()
        try:
            device = db.query(QianXinDevice).get(device_id)
            if not device or not device.enabled:
                _update_scan_log_failed(scan_log_id, 0, "设备不存在或已禁用")
                logger.warning("椒图扫描跳过 device_id=%s 设备不存在或已禁用", device_id)
                return

            device_name = device.name
            device.last_scan_status = "running"
            device.last_scan_error = None
            db.commit()

            old_rows = db.query(QianXinServer).filter(
                QianXinServer.device_id == device_id
            ).all()
            for r in old_rows:
                old_by_key[(r.machine_uuid, device_id)] = r
            logger.info("椒图扫描阶段0完成 device=%s 旧记录=%s", device_name, len(old_by_key))
        finally:
            db.close()

        # 阶段 1：通过 API 获取服务器列表（不持有 DB 会话）
        client = QianXinClient(device.host, device.uuid, device.secret)
        loop = asyncio.get_running_loop()
        logger.info("椒图扫描阶段1开始 device=%s 获取服务器列表...", device_name)
        servers = await loop.run_in_executor(None, client.get_all_servers)
        logger.info("椒图扫描阶段1完成 device=%s 服务器数量=%s", device_name, len(servers))

        if not servers:
            _wipe_qax_data(device_id)
            server_count = 0
            scan_success = True
            _finalize_scan_success(device_id, start_time, server_count, 0, 0)
            _write_qax_history(device_id, device_name, old_by_key, {})
            if scan_log_id:
                _update_scan_log(scan_log_id, True, 0, None)
            logger.info("椒图扫描完成 device=%s 无服务器返回", device_name)
            return

        # 阶段 2：写入服务器基本信息（短事务）
        logger.info("椒图扫描阶段2开始 device=%s 写入 %s 台服务器...", device_name, len(servers))
        server_map = _write_qax_servers(device_id, servers)
        server_count = len(servers)
        logger.info("椒图扫描阶段2完成 device=%s 写入完成", device_name)

        # 阶段 3：逐台采集详情
        logger.info("椒图扫描阶段3开始 device=%s 逐台采集详情...", device_name)
        for idx, s in enumerate(servers):
            machine_uuid = s.get("machineUuid", "")
            machine_name = s.get("machineName", "")
            if not machine_uuid:
                continue

            server_id = server_map.get(machine_uuid)
            if not server_id:
                continue

            try:
                ports = await loop.run_in_executor(None, client.get_server_ports, machine_uuid)
                procs = await loop.run_in_executor(None, client.get_server_processes, machine_uuid)
                sw_list = await loop.run_in_executor(None, client.get_server_software, machine_uuid)
                _write_qax_server_details(device_id, server_id, ports, procs, sw_list)
                detail_success += 1
            except Exception as e:
                detail_failed += 1
                logger.warning("采集详情失败 server=%s: %s", machine_name, e)
                try:
                    _write_qax_server_details(device_id, server_id, [], [], [])
                except Exception:
                    pass

            if (idx + 1) % 10 == 0:
                logger.info("椒图扫描进度 device=%s %s/%s 详情成功=%s 失败=%s",
                            device_name, idx + 1, server_count, detail_success, detail_failed)

        logger.info("椒图扫描阶段3完成 device=%s 详情成功=%s 失败=%s",
                    device_name, detail_success, detail_failed)
        scan_success = True

    except Exception as e:
        error_msg = str(e)
        logger.exception("椒图扫描失败 device_id=%s: %s", device_id, error_msg)
        try:
            _finalize_scan_failed(device_id, start_time, error_msg)
        except Exception:
            logger.exception("更新椒图设备失败状态出错 device_id=%s", device_id)
    else:
        # 阶段 4：变更历史 + 最终状态
        logger.info("椒图扫描阶段4开始 device=%s 写入变更历史...", device_name)
        try:
            db = SessionLocal()
            try:
                new_rows = db.query(QianXinServer).filter(
                    QianXinServer.device_id == device_id
                ).all()
                new_by_key = {}
                for r in new_rows:
                    new_by_key[(r.machine_uuid, device_id)] = r
                history_count = detect_qax_changes(db, device_id, device_name, old_by_key, new_by_key)
                db.commit()
                logger.info("椒图变更历史写入完成 device=%s 变更记录=%s", device_name, history_count)
            finally:
                db.close()
        except Exception:
            logger.exception("写入椒图变更历史失败 device_id=%s", device_id)

        _finalize_scan_success(device_id, start_time, server_count, detail_success, detail_failed)
        duration = round((datetime.now() - start_time).total_seconds(), 1)
        logger.info("椒图扫描完成 device=%s 服务器=%s 详情成功=%s 失败=%s 耗时=%ss",
                    device_name, server_count, detail_success, detail_failed, duration)

    # 更新扫描日志（无论成功或失败都执行）
    if scan_log_id:
        _update_scan_log(scan_log_id, scan_success, server_count, error_msg)
        logger.info("椒图扫描日志已更新 scan_log_id=%s success=%s count=%s",
                    scan_log_id, scan_success, server_count)


def _wipe_qax_data(device_id: int):
    """清空指定椒图设备的所有采集数据。"""
    db = SessionLocal()
    try:
        old_ids = [r[0] for r in db.query(QianXinServer.id).filter(
            QianXinServer.device_id == device_id
        ).all()]
        if old_ids:
            db.query(QianXinPort).filter(QianXinPort.server_id.in_(old_ids)).delete(synchronize_session=False)
            db.query(QianXinProcess).filter(QianXinProcess.server_id.in_(old_ids)).delete(synchronize_session=False)
            db.query(QianXinSoftware).filter(QianXinSoftware.server_id.in_(old_ids)).delete(synchronize_session=False)
        db.query(QianXinServer).filter(QianXinServer.device_id == device_id).delete()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _write_qax_servers(device_id: int, servers: list) -> dict:
    """写入服务器基本信息，返回 {machine_uuid: server_id} 映射。"""
    db = SessionLocal()
    server_map = {}
    try:
        _wipe_qax_data(device_id)

        for s in servers:
            server = QianXinServer(
                device_id=device_id,
                machine_uuid=s.get("machineUuid", ""),
                machine_name=s.get("machineName", ""),
                ipv4=s.get("ipv4") or s.get("intranetIp") or "",
                intranet_ip=s.get("intranetIp") or "",
                ipv6=s.get("ipv6") or "",
                operation_system=s.get("operationSystem", ""),
                kernel_version=s.get("kernelVersion", ""),
                cpu=s.get("cpu") or s.get("cpuInfo", ""),
                memory=s.get("memory") or s.get("memoryGb", ""),
                disk_size_str=s.get("diskSizeStr") or s.get("diskSize", ""),
                online_status=s.get("onlineStatus", 0),
                run_status=s.get("runStatus", 0),
                machine_group=s.get("machineGroup", ""),
                port_count=s.get("portCount", 0),
                process_count=s.get("processCount", 0),
                software_count=s.get("softwareAppCount", 0),
                web_count=s.get("webCount", 0),
                web_server_count=s.get("webServerCount", 0),
                database_count=s.get("databaseCount", 0),
            )
            db.add(server)
            db.flush()
            muuid = s.get("machineUuid", "")
            if muuid:
                server_map[muuid] = server.id

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return server_map


def _write_qax_server_details(device_id: int, server_id: int,
                               ports: list, processes: list, software_list: list):
    """写入单台服务器的端口/进程/软件详情（独立短事务）。"""
    db = SessionLocal()
    try:
        db.query(QianXinPort).filter(QianXinPort.server_id == server_id).delete(synchronize_session=False)
        db.query(QianXinProcess).filter(QianXinProcess.server_id == server_id).delete(synchronize_session=False)
        db.query(QianXinSoftware).filter(QianXinSoftware.server_id == server_id).delete(synchronize_session=False)

        for p in ports:
            db.add(QianXinPort(
                device_id=device_id, server_id=server_id,
                port=str(p.get("port", "")),
                protocol=str(p.get("protocol", "")),
                process_name=str(p.get("processName", "")),
                start_user=str(p.get("startUser", "")),
                process_version=str(p.get("processVersion", "")),
            ))
        for p in processes:
            db.add(QianXinProcess(
                device_id=device_id, server_id=server_id,
                process_name=str(p.get("processName", "")),
                pid=str(p.get("pid", "")),
                start_user=str(p.get("startUser", "")),
                cpu_percent=str(p.get("cpuPercent", "")),
                mem_percent=str(p.get("memPercent", "")),
            ))
        for sw in software_list:
            db.add(QianXinSoftware(
                device_id=device_id, server_id=server_id,
                software_name=str(sw.get("softwareName", "")),
                version=str(sw.get("version", "")),
                install_path=str(sw.get("installPath", "")),
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _finalize_scan_success(device_id: int, start_time, server_count: int,
                           detail_success: int, detail_failed: int):
    """更新设备扫描状态为成功。"""
    duration = round((datetime.now() - start_time).total_seconds(), 1)
    db = SessionLocal()
    try:
        dev = db.query(QianXinDevice).get(device_id)
        if dev:
            dev.last_scan_status = "success"
            dev.last_scan_time = datetime.now()
            dev.last_scan_duration = duration
            dev.last_server_count = server_count
            dev.last_scan_error = None
            db.commit()
    finally:
        db.close()


def _finalize_scan_failed(device_id: int, start_time, error_msg: str):
    """更新设备扫描状态为失败。"""
    duration = round((datetime.now() - start_time).total_seconds(), 1)
    db = SessionLocal()
    try:
        dev = db.query(QianXinDevice).get(device_id)
        if dev:
            dev.last_scan_status = "failed"
            dev.last_scan_error = error_msg
            dev.last_scan_duration = duration
            db.commit()
    finally:
        db.close()


def _write_qax_history(device_id: int, device_name: str,
                        old_by_key: dict, new_by_key: dict):
    """写入椒图变更历史。"""
    from app.services.history_service import detect_qax_changes
    db = SessionLocal()
    try:
        detect_qax_changes(db, device_id, device_name, old_by_key, new_by_key)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("写入椒图变更历史失败 device_id=%s", device_id)
    finally:
        db.close()


async def trigger_qax_scan(device: QianXinDevice, triggered_by: str = "manual") -> int:
    """触发异步扫描，立即返回。返回 scan_log_id。"""
    from app.models.scan_log import ScanLog, ScanStatus, TriggerType

    db = SessionLocal()
    try:
        db_device = db.query(QianXinDevice).get(device.id)
        if db_device:
            db_device.last_scan_status = "running"
            db_device.last_scan_error = None

        trigger = TriggerType.manual if triggered_by == "manual" else TriggerType.scheduled
        scan_log = ScanLog(
            source_type="qax",
            source_id=device.id,
            source_name=device.name,
            status=ScanStatus.running,
            triggered_by=trigger,
            started_at=datetime.now(),
        )
        db.add(scan_log)
        db.commit()
        db.refresh(scan_log)
        scan_log_id = scan_log.id
    finally:
        db.close()

    task = asyncio.create_task(_run_qax_scan_async(device.id, scan_log_id))
    task.add_done_callback(_on_scan_task_done)
    return scan_log_id


def _on_scan_task_done(task: asyncio.Task):
    """后台扫描任务完成回调，用于捕获未处理异常。"""
    try:
        exc = task.exception()
        if exc:
            logger.error("椒图后台扫描任务异常终止: %s", exc, exc_info=exc)
        else:
            logger.info("椒图后台扫描任务正常完成")
    except asyncio.CancelledError:
        logger.warning("椒图后台扫描任务被取消")


async def test_qax_connection(host: str, uuid: str, secret: str) -> dict:
    """测试椒图连接。"""
    loop = asyncio.get_running_loop()
    try:
        client = QianXinClient(host, uuid, secret)
        result = await loop.run_in_executor(None, client.get_server_list, 1, 10)
        servers = _safe_list(result)
        # 优先从 data.total 读取真实总数
        total = result.get("total") or result.get("totalCount")
        inner = result.get("data")
        if isinstance(inner, dict):
            total = inner.get("total") or inner.get("totalCount") or total
        if not total:
            total = len(servers)
        return {"ok": True, "message": f"连接成功，共 {total} 台服务器"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
