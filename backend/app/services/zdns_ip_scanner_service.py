"""ZDNS IP 可达性扫描 — 对域名映射中的 IP 执行 ping 探测，更新在线状态。"""
import asyncio
import logging
import platform
import subprocess
from datetime import datetime

from app.database import SessionLocal
from app.models.zdns import ZDNSDevice, ZDNSDomainMap
from app.models.scan_result import ScanResult
from app.models.f5 import F5PoolMember, F5ApplicationMap
from app.models.scan_log import ScanLog, ScanStatus, TriggerType

logger = logging.getLogger(__name__)


# 模块级缓存：IPv6 可用性检测结果（只需检测一次）
_ipv6_available = None


def _check_ipv6_available() -> bool:
    """检测当前环境是否支持 IPv6 网络（模块级缓存，只检测一次）。"""
    global _ipv6_available
    if _ipv6_available is not None:
        return _ipv6_available
    import socket
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout(1.5)
        s.connect(("2001:4860:4860::8888", 80))  # Google DNS IPv6
        s.close()
        _ipv6_available = True
    except (OSError, Exception):
        _ipv6_available = False
    return _ipv6_available


def _ping6_via_proxy(ips: list[str], timeout: int = 3) -> dict[str, bool]:
    """通过宿主机 ping6 代理检测 IPv6 连通性（Docker 无 IPv6 时使用）。"""
    import urllib.request, json as _json
    try:
        data = _json.dumps({"ips": ips}).encode()
        req = urllib.request.Request(
            "http://host.docker.internal:5199/ping6",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=timeout + 5)
        return _json.loads(resp.read())
    except Exception:
        return {ip: False for ip in ips}


def _tcp_probe(ip_address: str, port: int = 80, timeout: int = 3) -> bool:
    """通过 TCP 连接检测目标是否可达。"""
    import socket
    try:
        family = socket.AF_INET6 if ":" in ip_address else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip_address, port))
        sock.close()
        return True
    except Exception:
        return False


def _ping_ip(ip_address: str, timeout: int = 3) -> bool | None:
    """跨平台可达性检测。IPv4 用 ICMP ping + TCP 备用。
    IPv6 在 Docker 环境无网络时返回 None（表示无法检测，应标记为"待定"）。"""
    is_ipv6 = ":" in ip_address

    if is_ipv6:
        if not _check_ipv6_available():
            return None  # 无法检测，标记为"待定"
        # IPv6 环境可用：TCP 探测 + ICMP ping
        for port in (80, 443, 22, 8080, 8443):
            if _tcp_probe(ip_address, port, timeout):
                return True
        if platform.system() == "Windows":
            cmd = ["ping", "-6", "-n", "1", "-w", str(timeout * 1000), ip_address]
        else:
            cmd = ["ping", "-6", "-c", "1", "-W", str(timeout), ip_address]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
            return result.returncode == 0
        except Exception:
            return False

    # IPv4: 优先 ICMP ping
    if platform.system() == "Windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip_address]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout), ip_address]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        if result.returncode == 0:
            return True
    except Exception:
        pass
    # ICMP 失败，TCP 探测常用端口作为补充
    for port in (80, 443, 22):
        if _tcp_probe(ip_address, port, timeout):
            return True
    return False


async def _run_zdns_ip_scan_async(zdns_device_id: int, scan_log_id: int | None = None):
    """异步执行 IP 可达性扫描，在线程池中运行 ping。"""
    from datetime import datetime as dt
    from app.services.scan_step_service import add_step, finish_step, update_progress, mark_started, append_log

    loop = asyncio.get_running_loop()
    start_time = dt.now()
    scan_successful = True
    device = None
    total_checked = 0
    online_count = 0
    offline_count = 0

    db = SessionLocal()
    try:
        device = db.query(ZDNSDevice).get(zdns_device_id)
        if not device or not device.is_active:
            return

        if scan_log_id:
            mark_started(scan_log_id)
            append_log(scan_log_id, f"开始 ZDNS IP 可达性扫描 {device.host}")

        device.last_ip_scan_status = "running"
        device.last_ip_scan_error = None
        db.commit()

        # 获取该设备所有域名映射 IP（去重非空）
        rows = db.query(ZDNSDomainMap).filter(
            ZDNSDomainMap.zdns_device_id == zdns_device_id,
            ZDNSDomainMap.ip_address != "",
        ).all()

        if not rows:
            device.last_ip_scan_status = "success"
            device.last_ip_scan_time = dt.now()
            device.last_ip_scan_duration = 0.0
            db.commit()
            if scan_log_id:
                update_progress(scan_log_id, 100)
                _finish_scan_log(scan_log_id, 0, 0)
            return

        unique_ips = list(set(r.ip_address for r in rows))

        if scan_log_id:
            update_progress(scan_log_id, 5, f"查询已知在线 IP (共 {len(unique_ips)} 个)")

        # 批量查交换机 scan_results：已存在于交换机中的 IP 直接视为在线
        switch_ips = set()
        if unique_ips:
            sr_rows = db.query(ScanResult.ip_address).filter(
                ScanResult.ip_address.in_(unique_ips)
            ).distinct().all()
            switch_ips = {r[0] for r in sr_rows}

        # 批量查 F5 成员：状态为 up 的 IP 也视为在线
        f5_up_ips = set()
        if unique_ips:
            pm_rows = db.query(F5PoolMember.member_ip).filter(
                F5PoolMember.member_ip.in_(unique_ips),
                F5PoolMember.member_state == "up",
            ).distinct().all()
            f5_up_ips = {r[0] for r in pm_rows}
            am_rows = db.query(F5ApplicationMap.member_ip).filter(
                F5ApplicationMap.member_ip.in_(unique_ips),
                F5ApplicationMap.member_state == "up",
            ).distinct().all()
            f5_up_ips.update(r[0] for r in am_rows)

        # 确定需要 ping 的 IP：不在交换机中且不在 F5 up 中的
        known_online = switch_ips | f5_up_ips
        ips_to_ping = [ip for ip in unique_ips if ip not in known_online]

        # 检测 IPv6 可用性
        ipv6_ok = _check_ipv6_available()
        # 分离 IPv4/IPv6
        ipv6_ips = [ip for ip in ips_to_ping if ":" in ip]
        ipv4_ips = [ip for ip in ips_to_ping if ":" not in ip]

        if scan_log_id:
            append_log(scan_log_id, f"唯一 IP: {len(unique_ips)} 个")
            append_log(scan_log_id, f"IPv6 网络: {'容器直连' if ipv6_ok else '宿主机代理'}")
            append_log(scan_log_id, f"来源于交换机: {len(switch_ips)} 个, 来源于 F5 up: {len(f5_up_ips - switch_ips)} 个")
            append_log(scan_log_id, f"已知在线: {len(known_online)} 个")
            append_log(scan_log_id, f"待 Ping: IPv4={len(ipv4_ips)} IPv6={len(ipv6_ips)}")
            update_progress(scan_log_id, 20, f"待 Ping {len(ips_to_ping)} 个 IP")

        # 为已知在线的 IP 更新状态
        for r in rows:
            if r.ip_address in known_online:
                r.ip_status = "online"

        ping_results = {}
        step1_id = None

        if ipv4_ips:
            # IPv4: 容器内 ICMP ping（限并发 20）
            semaphore = asyncio.Semaphore(20)

            async def _ping4(ip):
                async with semaphore:
                    reachable = await loop.run_in_executor(None, _ping_ip, ip)
                    return ip, reachable

            if scan_log_id:
                step1_id = add_step(scan_log_id, 1, f"IPv4 Ping ({len(ipv4_ips)} 个 IP)")
                append_log(scan_log_id, f"开始 IPv4 Ping {len(ipv4_ips)} 个...")
            batch_size = max(1, len(ipv4_ips) // 4) if ipv4_ips else 1
            for batch_idx in range(0, len(ipv4_ips), batch_size):
                batch = ipv4_ips[batch_idx:batch_idx + batch_size]
                tasks = [_ping4(ip) for ip in batch]
                batch_results = await asyncio.gather(*tasks)
                ping_results.update(dict(batch_results))
            if scan_log_id and ipv4_ips:
                v4_online = sum(1 for v in ping_results.values() if v is True)
                append_log(scan_log_id, f"IPv4 Ping 完成: 在线 {v4_online}, 离线 {len(ipv4_ips) - v4_online}")

        if ipv6_ips:
            # IPv6: 容器直连或将批量请求通过宿主机代理
            if ipv6_ok:
                semaphore = asyncio.Semaphore(20)

                async def _ping6(ip):
                    async with semaphore:
                        reachable = await loop.run_in_executor(None, _ping_ip, ip)
                        return ip, reachable

                if scan_log_id:
                    append_log(scan_log_id, f"开始容器直连 IPv6 Ping {len(ipv6_ips)} 个...")
                for batch_idx in range(0, len(ipv6_ips), 20):
                    batch = ipv6_ips[batch_idx:batch_idx + 20]
                    tasks = [_ping6(ip) for ip in batch]
                    batch_results = await asyncio.gather(*tasks)
                    ping_results.update(dict(batch_results))
            else:
                if scan_log_id:
                    append_log(scan_log_id, f"开始宿主机代理 IPv6 Ping {len(ipv6_ips)} 个...")
                # 批量发送到宿主机代理（一次请求）
                proxy_results = await loop.run_in_executor(None, _ping6_via_proxy, ipv6_ips)
                ping_results.update(proxy_results)
            if scan_log_id:
                v6_online = sum(1 for ip in ipv6_ips if ping_results.get(ip) is True)
                append_log(scan_log_id, f"IPv6 Ping 完成: 在线 {v6_online}, 离线 {len(ipv6_ips) - v6_online}")

        # 应用 ping 结果
        pending_count = 0
        for r in rows:
            if r.ip_address in ping_results:
                total_checked += 1
                result = ping_results[r.ip_address]
                if result is True:
                    r.ip_status = "online"
                    online_count += 1
                elif result is None:
                    r.ip_status = "pending"
                    pending_count += 1
                else:
                        r.ip_status = "offline"
                        offline_count += 1

            if scan_log_id and step1_id:
                finish_step(step1_id, "success", len(ips_to_ping), len(ips_to_ping))
                parts = [f"在线 {online_count}", f"离线 {offline_count}"]
                if pending_count: parts.append(f"待定 {pending_count}")
                append_log(scan_log_id, f"Ping 完成: {', '.join(parts)} (总已知在线 {len(known_online) + online_count})")
                update_progress(scan_log_id, 90, "Ping 探测完成")

        db.commit()

        duration = round((dt.now() - start_time).total_seconds(), 1)
        device.last_ip_scan_status = "success"
        device.last_ip_scan_time = dt.now()
        device.last_ip_scan_duration = duration
        db.commit()
        logger.info(
            "ZDNS IP扫描完成 device_id=%s, 已在线=%s, 探测=%s(在线%s/离线%s), 耗时%ss",
            zdns_device_id, len(known_online), total_checked, online_count, offline_count, duration,
        )
    except Exception as e:
        scan_successful = False
        duration = round((dt.now() - start_time).total_seconds(), 1)
        logger.exception("ZDNS IP扫描失败 device_id=%s", zdns_device_id)
        if scan_log_id:
            append_log(scan_log_id, f"扫描失败: {e}")
            update_progress(scan_log_id, 0, f"扫描失败: {str(e)[:120]}")
        try:
            if device:
                device.last_ip_scan_status = "failed"
                device.last_ip_scan_error = str(e)
                device.last_ip_scan_duration = duration
                db.commit()
        except Exception:
            pass
    finally:
        db.close()

    # 更新扫描日志
    if scan_log_id:
        _finish_scan_log(scan_log_id, online_count, offline_count, scan_successful)


def _finish_scan_log(scan_log_id: int, online_count: int, offline_count: int, success: bool = True):
    """更新 ZDNS IP 扫描日志为完成状态。"""
    from datetime import datetime as dt
    _db = SessionLocal()
    try:
        log = _db.query(ScanLog).get(scan_log_id)
        if log:
            log.status = ScanStatus.success if success else ScanStatus.failed
            log.hosts_found = online_count
            log.routes_found = offline_count
            log.completed_at = dt.now()
            log.progress_pct = 100 if success else 0
            log.current_step = ""
            if not success and log.error_message is None:
                log.error_message = "扫描执行异常，请查看终端输出"
            if log.started_at:
                log.duration_seconds = round((dt.now() - log.started_at).total_seconds(), 1)
            _db.commit()
    except Exception:
        pass
    finally:
        _db.close()


async def trigger_zdns_ip_scan(device: ZDNSDevice, triggered_by: str = "manual") -> int:
    """触发异步 IP 扫描，立即返回 scan_log_id。"""
    db = SessionLocal()
    try:
        db_device = db.query(ZDNSDevice).get(device.id)
        if db_device:
            db_device.last_ip_scan_status = "running"
            db_device.last_ip_scan_error = None

        trigger = TriggerType.manual if triggered_by == "manual" else TriggerType.scheduled
        scan_log = ScanLog(
            source_type="zdns_ip",
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
    from app.services.scan_step_service import mark_queued
    mark_queued(scan_log_id)
    from app.tasks.scan_tasks import scan_zdns_ip_task
    scan_zdns_ip_task.delay(device.id, scan_log_id)
    return scan_log_id
