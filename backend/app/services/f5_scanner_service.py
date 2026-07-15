"""F5 BIG-IP iControl REST API 采集引擎"""
import json
import re
import ssl
import asyncio
import logging
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from base64 import b64encode

from app.database import SessionLocal
from app.models.f5 import F5Device, F5VirtualServer, F5PoolMember, F5Rule, F5ApplicationMap

logger = logging.getLogger(__name__)

# 域名提取正则（大小写不敏感）
# F5 iRules 中域名可能以多种 TCL 语法出现：
#   HTTP::host eq "domain"            — 标准 F5 语法
#   [HTTP::host] equals "domain"      — TCL if 条件
#   switch -glob [HTTP::host] { "domain*" { pool ... } }  — TCL switch 分支
_DOMAIN_POOL_PATTERNS = [
    re.compile(r'HTTP::host\]\s+equals\s+"([^"]+)"\s*\}\s*\{\s*pool\s+(\S+)', re.IGNORECASE),
    re.compile(r'HTTP::host\s+eq\s+"([^"]+)"\s*\}\s*\{\s*pool\s+(\S+)', re.IGNORECASE),
    # 场景A: pool 与域名同行: "domain*" { pool pool_name }
    re.compile(r'"([^"]+?)(?:\*|\.\*)?"\s*\{\s*pool\s+(\S+)', re.IGNORECASE),
    # 场景B: pool 在下一行（跨注释）: "domain*" {\n  # comment\n  pool pool_name }
    re.compile(r'"([^"]+?)(?:\*|\.\*)?"\s*\{.*?(?:^|\n)\s*pool\s+(\S+)', re.IGNORECASE | re.DOTALL | re.MULTILINE),
]


def _make_request(host: str, username: str, password: str, port: int, path: str) -> dict:
    """向 F5 iControl REST API 发送 GET 请求并解析 JSON 响应。"""
    url = f"https://{host}:{port}{path}"
    credentials = b64encode(f"{username}:{password}".encode()).decode()
    req = Request(url)
    req.add_header("Authorization", f"Basic {credentials}")
    req.add_header("Content-Type", "application/json")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        resp = urlopen(req, context=ctx, timeout=30)
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}
    except HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code}: {err_body or str(e)}") from None
    except URLError as e:
        raise RuntimeError(f"连接失败: {e.reason}") from None


def _parse_destination(destination: str) -> tuple:
    """解析 /Common/10.0.0.100:443 或 /Common/2001:db8::1.443 格式的 destination，返回 (ip, port)。

    F5 IPv6 格式：2001:db8::1.443 或用方括号 [2001:db8::1]:443。
    """
    if not destination:
        return "", None
    # 去掉 /Partition/ 前缀
    parts = destination.rsplit("/", 1)
    addr_part = parts[-1]

    # IPv6 方括号形式：[2001:db8::1]:443
    if addr_part.startswith("["):
        bracket_end = addr_part.find("]")
        if bracket_end > 0:
            ip = addr_part[1:bracket_end]
            rest = addr_part[bracket_end + 1:]
            if rest.startswith(":"):
                port_str = rest[1:]
            elif rest.startswith("."):
                port_str = rest[1:]
            else:
                port_str = rest
            try:
                return ip, int(port_str)
            except (ValueError, TypeError):
                return ip, None
        return addr_part, None

    # 检查是否为 IPv6（包含多个 ":" 且不是端口分隔符）
    colon_count = addr_part.count(":")
    if colon_count > 1:
        # IPv6 地址，端口可能用 "." 分隔：2001:db8::1.443
        if "." in addr_part:
            ip, port_str = addr_part.rsplit(".", 1)
            try:
                return ip, int(port_str)
            except (ValueError, TypeError):
                pass
        # 纯 IPv6 地址，无端口
        return addr_part, None

    # IPv4：10.0.0.100:443
    if ":" in addr_part:
        ip, port_str = addr_part.rsplit(":", 1)
        try:
            return ip, int(port_str)
        except ValueError:
            return ip, None
    return addr_part, None


def _extract_domain_pool_pairs(rule_contents: dict) -> dict:
    """从 iRule TCL 内容中提取 (域名, pool) 对。返回 {rule_name: [(domain, pool_name), ...]}。"""
    result = {}
    for rule_name, content in rule_contents.items():
        if not content:
            continue
        pairs = []
        seen = set()
        for pattern in _DOMAIN_POOL_PATTERNS:
            for match in pattern.findall(content):
                domain = match[0].strip()
                pool = match[1].strip().rstrip("}")
                if domain and pool and (domain, pool) not in seen:
                    pairs.append((domain, pool))
                    seen.add((domain, pool))
        if pairs:
            result[rule_name] = pairs
    return result


def _ref_to_subpath(ref: str) -> str:
    """将 /Partition/Name 转换为 F5 API 子路径格式 ~Partition~Name。"""
    if not ref:
        return ""
    return "~" + "~".join(ref.strip("/").split("/"))


def _do_f5_scan(host: str, username: str, password: str, port: int) -> dict:
    """同步扫描 F5 设备，返回原始数据 dict。"""
    logger.info("开始扫描 F5 %s", host)

    # 1. 获取所有 Virtual Server
    vs_data = _make_request(host, username, password, port, "/mgmt/tm/ltm/virtual")
    vs_items = vs_data.get("items", []) if isinstance(vs_data, dict) else []

    virtual_servers = []
    rule_short_names = set()
    pool_short_names = set()
    # 保存 ref 映射: short_name -> full_ref，用于构造 API 子路径
    pool_ref_map = {}
    rule_ref_map = {}

    for item in vs_items:
        if not isinstance(item, dict):
            continue
        destination = item.get("destination", "")
        vs_ip, vs_port = _parse_destination(destination)

        # Pool 引用: "/Common/pool1"
        pool_ref = item.get("pool", "")
        pool_name = pool_ref.rsplit("/", 1)[-1] if pool_ref else ""
        if pool_name and pool_ref:
            pool_short_names.add(pool_name)
            pool_ref_map[pool_name] = pool_ref

        # 提取 iRule — F5 API 中 rules 是 ["/Common/rule1", ...]
        rules_list = []
        rules = item.get("rules", [])
        if isinstance(rules, list):
            for rn in rules:
                if isinstance(rn, str):
                    rn_clean = rn.rsplit("/", 1)[-1] if "/" in rn else rn
                    rules_list.append(rn_clean)
                    rule_short_names.add(rn_clean)
                    rule_ref_map[rn_clean] = rn

        # fallback: rulesReference.items
        if not rules_list:
            rules_ref = item.get("rulesReference")
            if isinstance(rules_ref, dict):
                ref_items = rules_ref.get("items", [])
                if isinstance(ref_items, list):
                    for rule_item in ref_items:
                        if isinstance(rule_item, dict):
                            rn = rule_item.get("name", "")
                            fl = rule_item.get("fullPath", "") or ""
                            if rn:
                                rules_list.append(rn)
                                rule_short_names.add(rn)
                                if fl:
                                    rule_ref_map[rn] = fl

        virtual_servers.append({
            "name": item.get("name", ""),
            "destination": destination,
            "vs_ip": vs_ip,
            "vs_port": vs_port,
            "pool_name": pool_name,
            "rules": json.dumps(rules_list, ensure_ascii=False),
            "raw_config": json.dumps(item, ensure_ascii=False),
        })

    # 2. 获取所有 Pool 及成员 — 使用 /mgmt/tm/ltm/pool 列表并用 fullPath 构造成员 URL
    pool_members = []
    pools_data = _make_request(host, username, password, port, "/mgmt/tm/ltm/pool?expandSubcollections=true")
    pool_items = pools_data.get("items", []) if isinstance(pools_data, dict) else []
    logger.info("F5 API 返回 %d 个 Pool", len(pool_items))
    for pool_item in pool_items:
        if not isinstance(pool_item, dict):
            continue
        pn = pool_item.get("name", "")
        full_path = pool_item.get("fullPath", "") or ""
        if not pn:
            continue
        if pn not in pool_short_names:
            pool_short_names.add(pn)
        # 用 fullPath 构造正确的子路径
        if full_path and full_path not in pool_ref_map.values():
            pool_ref_map[pn] = full_path

        # 调用 Pool 的 members 端点获取完整成员详情
        member_items = []
        pool_subpath = _ref_to_subpath(pool_ref_map.get(pn, f"/Common/{pn}"))
        try:
            members_data = _make_request(host, username, password, port,
                                         f"/mgmt/tm/ltm/pool/{pool_subpath}/members")
            member_items = members_data.get("items", []) if isinstance(members_data, dict) else []
        except Exception as e:
            logger.warning("获取 Pool %s 成员失败 (%s)，使用 membersReference fallback", pn, e)
            members_ref = pool_item.get("membersReference")
            if isinstance(members_ref, dict):
                member_items = members_ref.get("items", []) or []

        for member_item in member_items:
            if not isinstance(member_item, dict):
                continue
            full_path_m = member_item.get("fullPath", "") or member_item.get("name", "")
            mname = member_item.get("name", "")
            mip = member_item.get("address", "")
            mport = None

            if full_path_m:
                last = full_path_m.rsplit("/", 1)[-1] if "/" in full_path_m else full_path_m
                if ":" in last:
                    parts = last.rsplit(":", 1)
                    try:
                        mport = int(parts[-1])
                        if not mip:
                            mip = parts[0]
                    except ValueError:
                        pass
                elif "." in last:
                    parts = last.rsplit(".", 1)
                    try:
                        mport = int(parts[-1])
                        if not mip:
                            mip = parts[0]
                    except ValueError:
                        pass
            if not mip:
                mip = member_item.get("address", "") or ""
            if not mip and mname:
                last = mname.rsplit("/", 1)[-1] if "/" in mname else mname
                if ":" in last:
                    parts = last.rsplit(":", 1)
                    mip = parts[0]

            pool_members.append({
                "pool_name": pn,
                "member_name": mname,
                "member_ip": mip,
                "member_port": mport,
                "member_state": member_item.get("state", "") or "",
                "raw_config": json.dumps(member_item, ensure_ascii=False),
            })

        # 空成员池也记录一条占位行，确保池列表完整
        if not member_items:
            pool_members.append({
                "pool_name": pn,
                "member_name": "",
                "member_ip": "",
                "member_port": None,
                "member_state": "",
                "raw_config": "",
            })

    # 3. 获取所有 iRule 内容 — 使用完整 ref 路径
    rules = []
    rule_contents = {}
    for rn in rule_short_names:
        rule_subpath = _ref_to_subpath(rule_ref_map.get(rn, f"/Common/{rn}"))
        try:
            rule_detail = _make_request(host, username, password, port,
                                        f"/mgmt/tm/ltm/rule/{rule_subpath}")
            content = rule_detail.get("apiAnonymous", "") or ""
            rule_contents[rn] = content
            rules.append({
                "rule_name": rn,
                "rule_content": content,
            })
        except Exception as e:
            logger.warning("获取 iRule %s 失败 (%s)", rn, e)
            rules.append({"rule_name": rn, "rule_content": ""})
            rule_contents[rn] = ""

    return {
        "virtual_servers": virtual_servers,
        "pool_members": pool_members,
        "rules": rules,
        "rule_contents": rule_contents,
    }


def _build_application_map(scan_result: dict) -> list:
    """根据扫描结果构建域名 → VS → Pool 成员映射。"""
    virtual_servers = scan_result["virtual_servers"]
    pool_members = scan_result["pool_members"]
    rule_contents = scan_result.get("rule_contents", {})

    # 提取 iRule 中的域名→pool 对: rule_name -> [(domain, pool_name), ...]
    domain_pool_map = _extract_domain_pool_pairs(rule_contents)

    # 构建 pool -> members 映射
    pool_member_map = {}
    for pm in pool_members:
        pn = pm["pool_name"]
        if pn not in pool_member_map:
            pool_member_map[pn] = []
        pool_member_map[pn].append(pm)

    app_rows = []
    for vs in virtual_servers:
        vs_name = vs["name"]
        vs_ip = vs["vs_ip"]
        vs_port = vs["vs_port"]
        vs_pool = vs["pool_name"]
        rules_str = vs.get("rules", "[]")
        try:
            vs_rule_names = json.loads(rules_str)
        except (json.JSONDecodeError, TypeError):
            vs_rule_names = []

        processed_rule_keys = set()

        # ── 1. 处理 iRules: 从规则中提取域名→pool 对 ──
        for rn in vs_rule_names:
            if rn not in domain_pool_map:
                continue
            for domain, irule_pool in domain_pool_map[rn]:
                rk = (domain, irule_pool, rn)
                if rk in processed_rule_keys:
                    continue
                processed_rule_keys.add(rk)

                members = pool_member_map.get(irule_pool, [])
                if members:
                    for member in members:
                        app_rows.append({
                            "domain_name": domain,
                            "vs_name": vs_name,
                            "vs_ip": vs_ip,
                            "vs_port": vs_port,
                            "pool_name": irule_pool,
                            "rule_name": rn,
                            "member_ip": member["member_ip"],
                            "member_port": member["member_port"],
                            "member_state": member.get("member_state", ""),
                            "source": "irule",
                        })
                else:
                    app_rows.append({
                        "domain_name": domain,
                        "vs_name": vs_name,
                        "vs_ip": vs_ip,
                        "vs_port": vs_port,
                        "pool_name": irule_pool,
                        "rule_name": rn,
                        "member_ip": "",
                        "member_port": None,
                        "member_state": "",
                        "source": "irule",
                    })

        # ── 2. 处理 VS 直接关联的 pool ──
        if vs_pool:
            members = pool_member_map.get(vs_pool, [])
            rule_names_str = ", ".join(vs_rule_names) if vs_rule_names else ""
            source_type = "pool" if vs_rule_names else "vs_name"
            # pool 来源用 VS 名称作域名，与 iRule 域名区分
            domain = vs_name

            if members:
                for member in members:
                    app_rows.append({
                        "domain_name": domain,
                        "vs_name": vs_name,
                        "vs_ip": vs_ip,
                        "vs_port": vs_port,
                        "pool_name": vs_pool,
                        "rule_name": rule_names_str,
                        "member_ip": member["member_ip"],
                        "member_port": member["member_port"],
                        "member_state": member.get("member_state", ""),
                        "source": source_type,
                    })
            else:
                app_rows.append({
                    "domain_name": domain,
                    "vs_name": vs_name,
                    "vs_ip": vs_ip,
                    "vs_port": vs_port,
                    "pool_name": vs_pool,
                    "rule_name": rule_names_str,
                    "member_ip": "",
                    "member_port": None,
                    "member_state": "",
                    "source": source_type,
                })
        elif not processed_rule_keys:
            # 无 pool 也无 iRules: 只输出 VS 信息
            app_rows.append({
                "domain_name": vs_name,
                "vs_name": vs_name,
                "vs_ip": vs_ip,
                "vs_port": vs_port,
                "pool_name": "",
                "rule_name": "",
                "member_ip": "",
                "member_port": None,
                "member_state": "",
                "source": "vs_name",
            })

    return app_rows


async def _run_f5_scan_async(f5_device_id: int, scan_log_id: int | None = None):
    """异步扫描 F5 设备，采集配置并写入数据库。"""
    from app.services.history_service import detect_f5_changes
    from app.services.scan_step_service import add_step, finish_step, update_progress, mark_started, append_log
    from app.models.scan_log import ScanLog, ScanStatus

    start_time = datetime.now()
    scan_successful = True

    db = SessionLocal()
    device = None
    vs_count = 0
    pool_count = 0
    try:
        device = db.query(F5Device).get(f5_device_id)
        if not device or not device.is_active:
            return

        if scan_log_id:
            mark_started(scan_log_id)
            append_log(scan_log_id, f"开始扫描 F5 {device.host}")
            append_log(scan_log_id, "F5 采集内容: Virtual Server、Pool 成员、iRules、应用映射")
            append_log(scan_log_id, f"正在通过 iControl REST API 连接 {device.host}:{device.port} ...")

        device.last_scan_status = "running"
        device.last_scan_error = None
        db.commit()

        if scan_log_id:
            update_progress(scan_log_id, 5, "连接 F5 并采集数据")
            step1_id = add_step(scan_log_id, 1, "连接 F5 并采集数据")

        loop = asyncio.get_running_loop()
        if scan_log_id:
            append_log(scan_log_id, "请求 F5 Virtual Server 列表...")
        scan_result = await loop.run_in_executor(
            None, _do_f5_scan, device.host, device.username, device.password, device.port
        )

        if scan_log_id:
            # VS 分布统计
            vs_list = scan_result["virtual_servers"]
            vs_with_pool = sum(1 for vs in vs_list if vs.get("pool_name"))
            vs_with_rules = sum(1 for vs in vs_list if vs.get("rules") and vs["rules"] != "[]")
            vs_ips = set(vs.get("vs_ip", "") for vs in vs_list if vs.get("vs_ip"))
            # 统计不重复的池名称
            distinct_pools = len(set(pm["pool_name"] for pm in scan_result["pool_members"]) if scan_result["pool_members"] else [])
            append_log(scan_log_id, f"数据采集完成: VS={len(vs_list)} (关联Pool {vs_with_pool}/关联iRule {vs_with_rules}), Pool={distinct_pools}个, 成员={len(scan_result['pool_members'])}, iRules={len(scan_result['rules'])}")
            append_log(scan_log_id, f"VS IP 分布: {len(vs_ips)} 个独立 IP")

            # Pool member 状态分布
            member_states = {}
            for pm in scan_result["pool_members"]:
                state = pm.get("member_state", "unknown") or "unknown"
                member_states[state] = member_states.get(state, 0) + 1
            if member_states:
                state_parts = [f"{s}:{c}" for s, c in sorted(member_states.items())]
                append_log(scan_log_id, f"Pool 成员状态: {', '.join(state_parts)}")

            # iRule 域名提取预览
            rule_contents = scan_result.get("rule_contents", {})
            if rule_contents:
                domain_pool_map = _extract_domain_pool_pairs(rule_contents)
                domain_count = sum(len(v) for v in domain_pool_map.values())
                if domain_count > 0:
                    append_log(scan_log_id, f"iRule 域名→Pool 映射: {domain_count} 条 (来自 {len(domain_pool_map)} 个 iRule)")
                    # 展示前 5 条
                    shown = 0
                    for rn, pairs in sorted(domain_pool_map.items()):
                        for domain, pool in pairs[:3]:
                            if shown >= 5:
                                break
                            append_log(scan_log_id, f"  {domain} → {pool} ({rn})")
                            shown += 1
                        if shown >= 5:
                            break

            total_collected = len(vs_list) + len(scan_result["pool_members"]) + len(scan_result["rules"])
            update_progress(scan_log_id, 25, "数据分析完成")
            finish_step(step1_id, "success", total_collected, total_collected)
            update_progress(scan_log_id, 35, "开始写入数据库")

        write_db = SessionLocal()
        try:
            # 快照旧应用映射数据
            old_app_rows = write_db.query(F5ApplicationMap).filter(
                F5ApplicationMap.f5_device_id == f5_device_id
            ).all()
            old_by_key = {}
            for r in old_app_rows:
                key = (r.vs_name, r.domain_name, r.pool_name)
                old_by_key[key] = r

            # DELETE + INSERT: F5VirtualServer
            if scan_log_id:
                step2_id = add_step(scan_log_id, 2, "Virtual Server 写入")
            write_db.query(F5VirtualServer).filter(
                F5VirtualServer.f5_device_id == f5_device_id
            ).delete()
            for vs in scan_result["virtual_servers"]:
                write_db.add(F5VirtualServer(f5_device_id=f5_device_id, **vs))
            vs_count = len(scan_result["virtual_servers"])
            if scan_log_id:
                finish_step(step2_id, "success", vs_count, vs_count)
                append_log(scan_log_id, f"Virtual Server 写入完成: {vs_count} 条")
                update_progress(scan_log_id, 50, "Virtual Server 写入完成")

            # DELETE + INSERT: F5PoolMember
            if scan_log_id:
                step3_id = add_step(scan_log_id, 3, "Pool 成员写入")
            write_db.query(F5PoolMember).filter(
                F5PoolMember.f5_device_id == f5_device_id
            ).delete()
            for pm in scan_result["pool_members"]:
                write_db.add(F5PoolMember(f5_device_id=f5_device_id, **pm))
            pool_count = len(scan_result["pool_members"])
            if scan_log_id:
                finish_step(step3_id, "success", pool_count, pool_count)
                update_progress(scan_log_id, 60, "Pool 成员写入完成")

            # DELETE + INSERT: F5Rule
            if scan_log_id:
                step4_id = add_step(scan_log_id, 4, "iRule 写入")
            write_db.query(F5Rule).filter(
                F5Rule.f5_device_id == f5_device_id
            ).delete()
            for rule in scan_result["rules"]:
                write_db.add(F5Rule(f5_device_id=f5_device_id, **rule))
            if scan_log_id:
                finish_step(step4_id, "success", len(scan_result["rules"]), len(scan_result["rules"]))
                update_progress(scan_log_id, 70, "iRule 写入完成")

            # 构建并写入应用映射
            if scan_log_id:
                step5_id = add_step(scan_log_id, 5, "应用映射构建")
            app_rows = _build_application_map(scan_result)
            write_db.query(F5ApplicationMap).filter(
                F5ApplicationMap.f5_device_id == f5_device_id
            ).delete()
            for ar in app_rows:
                write_db.add(F5ApplicationMap(f5_device_id=f5_device_id, **ar))
            if scan_log_id:
                finish_step(step5_id, "success", len(app_rows), len(app_rows))
                append_log(scan_log_id, f"应用映射: {len(app_rows)} 条 (iRule来源 + Pool来源)")
                update_progress(scan_log_id, 85, "应用映射构建完成")

            write_db.flush()  # 确保 INSERT 已刷入，避免 query 返回旧缓存数据

            # 构建新应用映射的 key 字典用于 diff
            new_app_rows = write_db.query(F5ApplicationMap).filter(
                F5ApplicationMap.f5_device_id == f5_device_id
            ).all()
            new_by_key = {}
            for r in new_app_rows:
                key = (r.vs_name, r.domain_name, r.pool_name)
                new_by_key[key] = r

            # 写入历史
            if scan_log_id:
                step6_id = add_step(scan_log_id, 6, "变更检测")
            detect_f5_changes(write_db, f5_device_id, device.name, old_by_key, new_by_key)
            if scan_log_id:
                finish_step(step6_id, "success")
                update_progress(scan_log_id, 95, "变更检测完成")

            write_db.commit()
        except Exception:
            write_db.rollback()
            raise
        finally:
            write_db.close()

        duration = round((datetime.now() - start_time).total_seconds(), 1)
        db_device = db.query(F5Device).get(f5_device_id)
        if db_device:
            db_device.last_scan_status = "success"
            db_device.last_scan_time = datetime.now()
            db_device.last_scan_duration = duration
            db_device.last_vs_count = vs_count
            db_device.last_pool_count = pool_count
            db_device.last_scan_error = None
            db.commit()
        logger.info("F5 %s 扫描完成，VS: %s, Pool Members: %s，耗时 %ss", device.host, vs_count, pool_count, duration)
    except Exception as e:
        scan_successful = False
        duration = round((datetime.now() - start_time).total_seconds(), 1)
        logger.exception("F5 %s 扫描失败", device.host if device else f5_device_id)
        if scan_log_id:
            append_log(scan_log_id, f"扫描失败: {e}")
            update_progress(scan_log_id, 0, f"扫描失败: {str(e)[:120]}")
        try:
            db_device = db.query(F5Device).get(f5_device_id)
            if db_device:
                db_device.last_scan_status = "failed"
                db_device.last_scan_error = str(e)
                db_device.last_scan_duration = duration
                db.commit()
        except Exception:
            pass
    finally:
        db.close()

    # 更新扫描日志
    if scan_log_id:
        _db = SessionLocal()
        try:
            log = _db.query(ScanLog).get(scan_log_id)
            if log:
                log.status = ScanStatus.success if scan_successful else ScanStatus.failed
                log.hosts_found = vs_count + pool_count
                log.completed_at = datetime.now()
                log.progress_pct = 100 if scan_successful else 0
                log.current_step = ""
                if not scan_successful and log.error_message is None:
                    log.error_message = "扫描执行异常，请查看终端输出"
                if log.started_at:
                    log.duration_seconds = round((datetime.now() - log.started_at).total_seconds(), 1)
                _db.commit()
        except Exception:
            pass
        finally:
            _db.close()


async def trigger_f5_scan(device: F5Device, triggered_by: str = "manual") -> int:
    """触发异步扫描，立即返回。返回 scan_log_id。"""
    from app.models.scan_log import ScanLog, ScanStatus, TriggerType

    db = SessionLocal()
    try:
        db_device = db.query(F5Device).get(device.id)
        if db_device:
            db_device.last_scan_status = "running"
            db_device.last_scan_error = None

        trigger = TriggerType.manual if triggered_by == "manual" else TriggerType.scheduled
        scan_log = ScanLog(
            source_type="f5",
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
    from app.tasks.scan_tasks import scan_f5_task
    scan_f5_task.delay(device.id, scan_log_id)
    return scan_log_id


async def test_f5_connection(host: str, username: str, password: str, port: int = 443) -> dict:
    """测试 F5 连接。"""
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None, _make_request, host, username, password, port, "/mgmt/tm/ltm/virtual"
        )
        return {"ok": True, "message": "连接成功"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
