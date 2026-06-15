"""鼎甲备份系统扫描服务。

数据来源：
  /d2/r/v2/jobs       — 作业定义（策略名、类型、主机ID等）
  /d2/r/v2/instances  — 作业执行实例（恢复点/备份版本），每次成功执行 = 一个可恢复版本
  /d2/r/v2/hosts      — 主机列表（IP 映射）
"""
import json
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
    """解析时间戳或时间字符串为本地时间。"""
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)) and val > 0:
            return datetime.fromtimestamp(val, tz=TZ).replace(tzinfo=None)
        if isinstance(val, str) and val.strip():
            s = val.strip()
            # 尝试多种格式
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]:
                try:
                    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
            # 尝试ISO格式
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                return dt.astimezone(TZ).replace(tzinfo=None)
            except Exception:
                pass
    except Exception:
        pass
    return None


def _paginate(host: str, path: str, headers: dict, limit: int = 100) -> list[dict]:
    """通用分页拉取 REST API。"""
    all_rows = []
    offset = 0
    while True:
        sep = "&" if "?" in path else "?"
        url = f"http://{host}{path}{sep}limit={limit}&offset={offset}"
        r = httpx.get(url, headers=headers, timeout=30)
        r.encoding = 'utf-8'
        r.raise_for_status()
        data = r.json()
        rows = data.get("rows", [])
        all_rows.extend(rows)
        total = data.get("total", 0)
        offset += len(rows)
        if offset >= total or len(rows) < limit:
            break
    return all_rows


def fetch_backup_data(host: str, api_key: str, access_key: str) -> list[dict]:
    """
    从鼎甲备份系统获取完整备份数据。

    流程：
    1. 获取所有作业定义 (jobs) — 获取策略/类型/主机映射
    2. 获取所有备份实例 (instances) — 获取每个版本的执行时间、大小、状态
    3. 获取主机列表 (hosts) — IP 映射
    4. 按 VM 聚合：从 instances 统计版本数和版本详情
    """
    headers = {"X-Api-Key": api_key, "X-Access-Key": access_key}

    # ── 1. 获取主机列表 ──
    host_map = {}
    try:
        hosts = _paginate(host, "/d2/r/v2/hosts", headers, limit=500)
        for h in hosts:
            huuid = h.get("uuid", "")
            if huuid:
                ips = [iface.get("address", "") for iface in h.get("interfaces", [])
                       if iface.get("address", "")
                       and iface.get("address") != "127.0.0.1"
                       and ":" not in iface.get("address", "")]
                host_map[huuid] = {
                    "name": h.get("nodename") or h.get("sysname") or f"Host-{h.get('id','')}",
                    "ips": ips,
                    "address": h.get("address", "")
                }
    except Exception as e:
        logger.warning(f"获取主机列表失败: {e}")

    # ── 2. 获取所有作业 ──
    all_jobs = _paginate(host, "/d2/r/v2/jobs", headers, limit=100)
    logger.info(f"获取到 {len(all_jobs)} 个作业")

    # 构建 job_id → job 映射
    job_map = {}
    for job in all_jobs:
        jid = job.get("id", "")
        if jid:
            job_map[jid] = job

    # ── 3. 获取所有备份实例（恢复点/版本） ──
    all_instances = []
    try:
        all_instances = _paginate(host, "/d2/r/v2/instances", headers, limit=200)
        logger.info(f"获取到 {len(all_instances)} 个备份实例")
    except Exception as e:
        logger.warning(f"获取实例列表失败（回退到仅用作业数据）: {e}")

    # ── 4. 按 VM 聚合版本数据 ──
    # vm_key → { versions: [{time, type, subtype, size, state, result}], ... }
    vm_aggregate = {}

    def _ensure_vm(vm_name: str, job: dict, hid: str):
        """初始化 VM 聚合条目。"""
        key = vm_name
        if key not in vm_aggregate:
            host_info = host_map.get(hid, {})
            vm_aggregate[key] = {
                "job_id": job.get("id", ""),
                "job_name": job.get("name", ""),
                "host_id": hid,
                "host_name": host_info.get("name", ""),
                "host_ip": (host_info.get("ips") or [None])[0] or host_info.get("address", "") or "",
                "vm_name": vm_name,
                "vm_uuid": "",
                "backup_type": job.get("type", ""),
                "backup_subtype": job.get("subtype", ""),
                "agent": job.get("agent", ""),
                "state": job.get("state", ""),
                "last_run_result": job.get("last_run_result", ""),
                "last_run_time": None,
                "last_completed_time": None,
                "next_run_time": _parse_dt(job.get("next_run_time")),
                "vm_size_gb": None,
                "versions": [],  # 可恢复版本列表
            }

    # 4a. 从 instances 提取版本信息（主要数据来源）
    for inst in all_instances:
        job_id = inst.get("job_id") or inst.get("id")
        job = job_map.get(job_id, {})
        hid = job.get("host_id", "")

        # 实例来源 entries — 包含 VM 列表
        source = inst.get("source", {}) or {}
        entries = source.get("entries", [])
        if not isinstance(entries, list):
            entries = []

        inst_time = _parse_dt(inst.get("start_time") or inst.get("begin_time"))
        inst_end = _parse_dt(inst.get("end_time") or inst.get("completed_time"))
        inst_state = inst.get("state", "")
        inst_result = inst.get("last_run_result") or inst.get("result", "")
        inst_type = inst.get("type") or job.get("type", "")
        inst_subtype = inst.get("subtype") or job.get("subtype", "")

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            vm_name = entry.get("name", "")
            if not vm_name:
                continue
            vm_size = entry.get("size", 0)

            _ensure_vm(vm_name, job, hid)
            agg = vm_aggregate[vm_name]

            # 更新 VM UUID 和大小
            if entry.get("uuid"):
                agg["vm_uuid"] = entry.get("uuid", "")
            if vm_size:
                size_gb = round(vm_size / (1024**3), 1)
                if not agg["vm_size_gb"] or size_gb > (agg["vm_size_gb"] or 0):
                    agg["vm_size_gb"] = size_gb

            # 只统计成功完成的实例（可恢复版本）
            if inst_state in ("completed", "") and inst_result not in ("failed", "error"):
                agg["versions"].append({
                    "time": inst_time.strftime("%Y-%m-%d %H:%M:%S") if inst_time else None,
                    "end_time": inst_end.strftime("%Y-%m-%d %H:%M:%S") if inst_end else None,
                    "type": inst_type,
                    "subtype": inst_subtype,
                    "size_gb": size_gb,
                })

    # 4b. 从 jobs 补全没有实例的 VM（兼容旧版/只有作业数据的情况）
    for job in all_jobs:
        hid = job.get("host_id", "")
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

            _ensure_vm(vm_name, job, hid)

            agg = vm_aggregate[vm_name]
            # 从作业级别补充时间信息
            job_time = _parse_dt(job.get("last_run_time")) or _parse_dt(job.get("last_completed_time"))
            job_end = _parse_dt(job.get("last_completed_time"))
            if not agg["last_run_time"] or (job_time and job_time > agg["last_run_time"]):
                agg["last_run_time"] = job_time
                agg["last_completed_time"] = job_end
                agg["state"] = job.get("state", agg["state"])
                agg["last_run_result"] = job.get("last_run_result", agg["last_run_result"])
                agg["backup_type"] = job.get("type", agg["backup_type"])
                agg["backup_subtype"] = job.get("subtype", agg["backup_subtype"])
                agg["agent"] = job.get("agent", agg["agent"])

            # 补充 VM UUID 和大小
            if entry.get("uuid") and not agg["vm_uuid"]:
                agg["vm_uuid"] = entry.get("uuid", "")
            esize = entry.get("size", 0)
            if esize and not agg["vm_size_gb"]:
                agg["vm_size_gb"] = round(esize / (1024**3), 1)

    # 4c. 从 instances 更新 last_run_time / last_completed_time
    for vm_name, agg in vm_aggregate.items():
        versions = agg["versions"]
        if versions:
            # 按时间排序
            versions.sort(key=lambda v: v.get("time") or "")
            # 最新版本时间 → last_run_time / last_completed_time
            latest = versions[-1]
            if latest.get("time"):
                t = _parse_dt(latest["time"])
                if t:
                    agg["last_run_time"] = t
            if latest.get("end_time"):
                t = _parse_dt(latest["end_time"])
                if t:
                    agg["last_completed_time"] = t

    # ── 5. 组装返回结果 ──
    results = []
    for vm_name, agg in vm_aggregate.items():
        versions = agg.pop("versions", [])
        results.append({
            "job_id": agg["job_id"],
            "job_name": agg["job_name"],
            "host_id": agg["host_id"],
            "host_name": agg["host_name"],
            "host_ip": agg["host_ip"],
            "vm_name": agg["vm_name"],
            "vm_uuid": agg["vm_uuid"],
            "backup_type": agg["backup_type"],
            "backup_subtype": agg["backup_subtype"],
            "agent": agg["agent"],
            "state": agg["state"],
            "last_run_result": agg["last_run_result"],
            "last_run_time": agg["last_run_time"],
            "last_completed_time": agg["last_completed_time"],
            "next_run_time": agg["next_run_time"],
            "backup_versions": len(versions),
            "backup_versions_detail": json.dumps(versions, ensure_ascii=False) if versions else None,
            "vm_size_gb": agg["vm_size_gb"],
        })

    logger.info(f"扫描完成：{len(results)} 个 VM 备份记录")
    if all_instances:
        total_versions = sum(r["backup_versions"] for r in results)
        logger.info(f"共 {total_versions} 个可恢复版本")

    return results
