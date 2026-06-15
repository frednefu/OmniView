"""鼎甲备份系统扫描服务。

数据来源：
  /d2/r/v2/jobs  — 作业定义（策略名、类型、主机ID等），按 job_id 关联补全信息
  /d2/r/v2/sets  — 备份集（每个 VM 的每次备份 = 一个 set，含 backup_start_time/backup_end_time/duration）
  /d2/r/v2/hosts — 主机列表（IP 映射）
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
    """解析时间戳或时间字符串，统一转为东八区本地时间（naive datetime）。

    鼎甲 API 返回的时间可能有：
    - Unix 时间戳（秒）：从 epoch 转换，指定 tz=TZ
    - 字符串 "YYYY-MM-DD HH:MM:SS"：无时区标记 → 假定已是东八区
    - 字符串 UTC："2026-06-05T00:49:38Z" / "2026-06-05T00:49:38+00:00" → 转为东八区
    """
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)) and val > 0:
            return datetime.fromtimestamp(val, tz=TZ).replace(tzinfo=None)
        if isinstance(val, str) and val.strip():
            s = val.strip()
            # ISO 格式带时区
            if s.endswith("Z") or "+" in s[10:] or (s.count("-") > 2 and "T" in s):
                try:
                    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(TZ)
                    return dt.replace(tzinfo=None)
                except Exception:
                    pass
            # 无时区字符串 → API 返回的是 UTC 时间，需转为东八区
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    dt_utc = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
                    dt_utc = dt_utc.replace(tzinfo=timezone.utc)
                    return dt_utc.astimezone(TZ).replace(tzinfo=None)
                except Exception:
                    continue
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
    从鼎甲备份系统获取每个 VM 的备份记录。

    数据流：
    1. /d2/r/v2/jobs  — 作业定义，按 job_id 索引（补全策略名、主机ID等）
    2. /d2/r/v2/sets  — 备份集，每个 set = 一个 VM 的一次备份
       { resource_name, backup_start_time, backup_end_time, duration,
         backup_type, state, source_size, resource_uuid, job_id, ... }
    3. /d2/r/v2/hosts — 主机列表，按 host_id 索引（补全主机名、IP）
    4. 按 VM 去重聚合：每个 VM 保留最新备份信息 + 所有版本详情
    """
    headers = {"X-Api-Key": api_key, "X-Access-Key": access_key}

    # ── 1. 获取作业定义（补全信息）──
    all_jobs = _paginate(host, "/d2/r/v2/jobs", headers, limit=100)
    logger.info(f"获取到 {len(all_jobs)} 个作业")

    job_map = {}
    for job in all_jobs:
        jid = job.get("id", "")
        if jid:
            job_map[jid] = job

    # ── 2. 获取主机列表 ──
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
                    "name": h.get("nodename") or h.get("sysname") or f"Host-{h.get('id', '')}",
                    "ips": ips,
                    "address": h.get("address", "")
                }
    except Exception as e:
        logger.warning(f"获取主机列表失败: {e}")

    # ── 3. 获取所有备份集（每个 VM 每次备份 = 一个 set）──
    all_sets = _paginate(host, "/d2/r/v2/sets", headers, limit=200)
    logger.info(f"获取到 {len(all_sets)} 个备份集")

    # ── 4. 按 VM 去重聚合 ──
    # vm_name → { info, versions: [...] }
    vm_map = {}

    for s in all_sets:
        # VM 名称：sets API 用 minor_resource_name 存储 VM 名
        vm_name = (s.get("minor_resource_name") or s.get("resource_name")
                   or s.get("item_name") or "").strip()
        if not vm_name:
            continue

        # 时间：sets API 字段名为 backup_start_time / backup_end_time
        start_dt = _parse_dt(s.get("backup_start_time"))
        end_dt = _parse_dt(s.get("backup_end_time"))

        # 持续时间：sets API 不返回 duration，从起止时间计算
        dur = None
        if start_dt and end_dt:
            dur = int((end_dt - start_dt).total_seconds())
            if dur < 0:
                dur = None

        # 大小
        size_bytes = s.get("source_size") or 0
        try:
            size_gb = round(float(size_bytes) / (1024 ** 3), 1) if size_bytes else None
        except (ValueError, TypeError):
            size_gb = None

        # 类型：full / incremental
        backup_type = s.get("type", "")
        backup_subtype = ""  # sets API 无 subtype

        # 主机：sets 用 host_uuid，直接查 host_map
        hid = s.get("host_uuid", "")
        host_info = host_map.get(hid, {})

        # VM UUID
        vm_uuid = s.get("resource_uuid") or s.get("minor_resource_id") or ""

        # 初始化或更新 VM 条目
        if vm_name not in vm_map:
            vm_map[vm_name] = {
                "job_id": s.get("definition_uuid", ""),
                "job_name": s.get("name", ""),
                "host_id": hid,
                "host_name": host_info.get("name", ""),
                "host_ip": (host_info.get("ips") or [None])[0] or host_info.get("address", "") or "",
                "vm_name": vm_name,
                "vm_uuid": vm_uuid,
                "backup_type": backup_type,
                "backup_subtype": "",
                "agent": "",
                "state": "completed",
                "last_run_result": "completed",
                "last_run_time": None,
                "last_completed_time": None,
                "duration_seconds": None,
                "vm_size_gb": None,
                "versions": [],
            }

        entry = vm_map[vm_name]

        # 更新 UUID（取第一个非空值）
        if vm_uuid and not entry["vm_uuid"]:
            entry["vm_uuid"] = vm_uuid
        # 更新大小（取最大值）
        if size_gb and (not entry["vm_size_gb"] or size_gb > entry["vm_size_gb"]):
            entry["vm_size_gb"] = size_gb

        # 收集版本（sets 中每条记录都是一个可恢复的备份版本）
        if start_dt:
            entry["versions"].append({
                "time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_dt.strftime("%Y-%m-%d %H:%M:%S") if end_dt else None,
                "duration_seconds": dur,
                "type": backup_type,
                "subtype": "",
                "size_gb": size_gb,
            })

            # 更新主记录为最新版本
            if not entry["last_run_time"] or start_dt > entry["last_run_time"]:
                entry["last_run_time"] = start_dt
                entry["last_completed_time"] = end_dt
                entry["duration_seconds"] = dur
                entry["backup_type"] = backup_type
                entry["job_name"] = s.get("name", entry["job_name"])

    # ── 5. 如果 sets 为空，回退到 jobs 数据 ──
    if not all_sets:
        logger.warning("备份集为空，回退到仅用作业数据")
        for job in all_jobs:
            hid = job.get("host_id", "")
            host_info = host_map.get(hid, {})
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
                if vm_name in vm_map:
                    continue

                st = _parse_dt(job.get("last_run_time"))
                et = _parse_dt(job.get("last_completed_time"))
                dur = None
                if st and et:
                    dur = int((et - st).total_seconds())
                    if dur < 0:
                        dur = None

                vm_map[vm_name] = {
                    "job_id": job.get("id", ""),
                    "job_name": job.get("name", ""),
                    "host_id": hid,
                    "host_name": host_info.get("name", ""),
                    "host_ip": (host_info.get("ips") or [None])[0] or host_info.get("address", "") or "",
                    "vm_name": vm_name,
                    "vm_uuid": entry.get("uuid", ""),
                    "backup_type": job.get("type", ""),
                    "backup_subtype": job.get("subtype", ""),
                    "agent": job.get("agent", ""),
                    "state": job.get("state", ""),
                    "last_run_result": job.get("last_run_result", ""),
                    "last_run_time": st,
                    "last_completed_time": et,
                    "duration_seconds": dur,
                    "vm_size_gb": round(entry.get("size", 0) / (1024 ** 3), 1) if entry.get("size") else None,
                    "versions": [],
                }

    # ── 6. 排序版本 & 组装结果 ──
    results = []
    for vm_name, entry in vm_map.items():
        versions = entry.pop("versions", [])
        if versions:
            versions.sort(key=lambda v: v.get("time") or "")
        results.append({
            "job_id": entry["job_id"],
            "job_name": entry["job_name"],
            "host_id": entry["host_id"],
            "host_name": entry["host_name"],
            "host_ip": entry["host_ip"],
            "vm_name": entry["vm_name"],
            "vm_uuid": entry["vm_uuid"],
            "backup_type": entry["backup_type"],
            "backup_subtype": entry["backup_subtype"],
            "agent": entry["agent"],
            "state": entry["state"],
            "last_run_result": entry["last_run_result"],
            "last_run_time": entry["last_run_time"],
            "last_completed_time": entry["last_completed_time"],
            "duration_seconds": entry["duration_seconds"],
            "backup_versions": len(versions),
            "backup_versions_detail": json.dumps(versions, ensure_ascii=False) if versions else None,
            "vm_size_gb": entry["vm_size_gb"],
        })

    logger.info(f"扫描完成：{len(results)} 个 VM 备份记录")
    total_versions = sum(r["backup_versions"] for r in results)
    logger.info(f"共 {total_versions} 个可恢复版本")

    return results
