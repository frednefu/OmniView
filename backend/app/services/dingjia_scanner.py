"""鼎甲备份系统扫描服务。"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

logger = logging.getLogger(__name__)
TZ = timezone(timedelta(hours=8))  # Asia/Shanghai


def test_connection(host: str, api_key: str, access_key: str) -> dict:
    headers = {"X-Api-Key": api_key, "X-Access-Key": access_key}
    try:
        r = httpx.get(f"http://{host}/d2/r/v2/jobs?limit=1", headers=headers, timeout=15)
        if r.status_code == 200:
            return {"success": True, "message": "连接成功"}
        return {"success": False, "message": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _parse_dt(val) -> Optional[datetime]:
    """解析时间戳或时间字符串。"""
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return datetime.fromtimestamp(val, tz=TZ).replace(tzinfo=None)
        if isinstance(val, str) and val.strip():
            # Try "2026-05-31 19:09:41" format
            return datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return None


def fetch_backup_data(host: str, api_key: str, access_key: str) -> list[dict]:
    headers = {"X-Api-Key": api_key, "X-Access-Key": access_key}

    # 获取所有作业
    all_jobs = []
    offset = 0
    limit = 100
    while True:
        r = httpx.get(f"http://{host}/d2/r/v2/jobs?limit={limit}&offset={offset}", headers=headers, timeout=30)
        r.encoding = 'utf-8'
        r.raise_for_status()
        data = r.json()
        rows = data.get("rows", [])
        all_jobs.extend(rows)
        total = data.get("total", 0)
        offset += len(rows)
        if offset >= total or len(rows) < limit:
            break

    # 获取主机列表（按 uuid 索引，job的host_id对应host的uuid）
    host_map = {}
    try:
        r2 = httpx.get(f"http://{host}/d2/r/v2/hosts?limit=500", headers=headers, timeout=30)
        for h in r2.json().get("rows", []):
            huuid = h.get("uuid", "")
            if huuid:
                ips = [iface.get("address", "") for iface in h.get("interfaces", [])
                       if iface.get("address", "") and iface.get("address") != "127.0.0.1"
                       and ":" not in iface.get("address", "")]
                host_map[huuid] = {
                    "name": h.get("nodename") or h.get("sysname") or f"Host-{h.get('id','')}",
                    "ips": ips,
                    "address": h.get("address", "")
                }
    except Exception:
        pass

    # 统计每个 VM 的备份版本数
    vm_version_counts = {}
    for job in all_jobs:
        source = job.get("source", {}) or {}
        entries = source.get("entries", [])
        for entry in (entries if isinstance(entries, list) else []):
            if isinstance(entry, dict) and entry.get("name"):
                vm_name = entry.get("name", "")
                if vm_name:
                    vm_version_counts[vm_name] = vm_version_counts.get(vm_name, 0) + 1

    # 组装结果
    vm_records = {}
    for job in all_jobs:
        hid = job.get("host_id", "")
        host_info = host_map.get(hid, {})
        host_ip = (host_info.get("ips") or [None])[0] or host_info.get("address", "") or ""
        host_name = host_info.get("name", "")

        source = job.get("source", {}) or {}
        entries = source.get("entries", [])
        if not isinstance(entries, list):
            continue

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            vm_name = entry.get("name", "")
            if not vm_name:
                continue

            job_time = _parse_dt(job.get("last_run_time")) or _parse_dt(job.get("last_completed_time"))
            key = vm_name
            existing = vm_records.get(key)
            if not existing or (job_time and (not existing["last_run_time"] or job_time > existing["last_run_time"])):
                vm_records[key] = {
                    "job_id": job.get("id", ""),
                    "job_name": job.get("name", ""),
                    "host_id": hid,
                    "host_name": host_name,
                    "host_ip": host_ip,
                    "vm_name": vm_name,
                    "vm_uuid": entry.get("uuid", ""),
                    "backup_type": job.get("type", ""),
                    "backup_subtype": job.get("subtype", ""),
                    "agent": job.get("agent", ""),
                    "state": job.get("state", ""),
                    "last_run_result": job.get("last_run_result", ""),
                    "last_run_time": job_time,
                    "last_completed_time": _parse_dt(job.get("last_completed_time")),
                    "next_run_time": _parse_dt(job.get("next_run_time")),
                    "backup_versions": vm_version_counts.get(vm_name, 1),
                    "vm_size_gb": round(entry.get("size", 0) / (1024**3), 1) if entry.get("size") else None,
                }

    return list(vm_records.values())
