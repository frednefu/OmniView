import os
import time
import logging.config
from contextlib import asynccontextmanager

# 配置 uvicorn 日志格式（仅在 worker 子进程生效，避免 reloader 父进程重复输出）
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s: %(message)s", "datefmt": "%Y-%m-%d %H:%M:%S"}
    },
    "handlers": {
        "default": {"class": "logging.StreamHandler", "formatter": "default", "stream": "ext://sys.stdout"}
    },
    "loggers": {
        "uvicorn.access": {"level": "INFO", "handlers": ["default"], "propagate": False},
        "uvicorn.error": {"level": "INFO", "handlers": ["default"], "propagate": False},
    }
})
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from sqlalchemy import inspect, text

from app.database import engine, Base
from app.models import User, Switch, ScanResult, RouteTable, ScanLog, Subnet, History, VCenter, VMInventory, EsxiHost, Datastore, Department, StaffInfo, ApiConfig, AssetInventory, SharedLink, OperationLog
from app.api.router import api_router
from app.services.scheduler_service import start_scheduler, shutdown_scheduler
from app.version import get_version


def _drop_created_by_fk():
    """移除设备表中 created_by 外键约束，允许自由删除用户。"""
    tables = ["switches", "vcenters", "f5_devices", "zdns_devices", "qax_devices"]
    try:
        inspector = inspect(engine)
        with engine.connect() as conn:
            for table in tables:
                for fk in inspector.get_foreign_keys(table):
                    if fk.get("constrained_columns") == ["created_by"]:
                        fk_name = fk["name"]
                        conn.execute(text(f"ALTER TABLE {table} DROP FOREIGN KEY {fk_name}"))
                        conn.commit()
    except Exception:
        pass


def _migrate_columns(table_name: str, columns: list[tuple[str, str]]):
    """通用列迁移：检测缺失列并 ALTER TABLE ADD COLUMN。"""
    try:
        inspector = inspect(engine)
        existing = {c["name"] for c in inspector.get_columns(table_name)}
        with engine.connect() as conn:
            for col_name, col_type in columns:
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _drop_created_by_fk()
    # 迁移 vm_inventory 管理字段到 asset_inventory
    try:
        with engine.connect() as conn:
            cnt = conn.execute(text("SELECT COUNT(*) FROM asset_inventory")).scalar()
            if cnt == 0:
                conn.execute(text(
                    "INSERT IGNORE INTO asset_inventory (vm_name, department_id, owner_user_id, claim_status, claimed_by, claimed_at) "
                    "SELECT vm_name, department_id, owner_user_id, COALESCE(claim_status,'unlinked'), claimed_by, claimed_at "
                    "FROM vm_inventory WHERE vm_name IS NOT NULL AND vm_name != ''"
                ))
                conn.commit()
    except Exception:
        pass
    _migrate_columns("vm_inventory", [("provisioned_gb", "FLOAT"), ("used_gb", "FLOAT")])
    _migrate_columns("datastores", [("mounted_host_count", "INTEGER DEFAULT 0"), ("storage_type", "VARCHAR(16) DEFAULT ''")])
    _migrate_columns("switches", [
        ("last_scan_status", "VARCHAR(16)"),
        ("last_scan_time", "DATETIME"),
        ("last_scan_duration", "FLOAT"),
        ("last_hosts_found", "INTEGER DEFAULT 0"),
        ("last_routes_found", "INTEGER DEFAULT 0"),
        ("last_scan_error", "TEXT"),
    ])
    _migrate_columns("scan_workers", [
        ("capabilities", "JSON"),
        ("current_tasks", "INTEGER DEFAULT 0"),
        ("max_tasks", "INTEGER DEFAULT 4"),
        ("version", "VARCHAR(32) DEFAULT ''"),
    ])
    _migrate_columns("vm_inventory", [
        ("department_id", "INTEGER"),
        ("owner_user_id", "INTEGER"),
        ("claim_status", "VARCHAR(16) DEFAULT 'unlinked'"),
        ("claimed_by", "INTEGER"),
        ("claimed_at", "DATETIME"),
    ])
    _migrate_columns("users", [
        ("gh", "VARCHAR(32)"),
        ("department_id", "INTEGER"),
        ("phone", "VARCHAR(32)"),
        ("mobile", "VARCHAR(32)"),
        ("name", "VARCHAR(128)"),
        ("user_type", "VARCHAR(8) DEFAULT 'internal'"),
        ("company", "VARCHAR(256)"),
        ("contact_person", "VARCHAR(64)"),
        ("notes", "VARCHAR(512)"),
        ("gender", "VARCHAR(4)"),
    ])
    _migrate_columns("info_systems", [
        ("vendor_name", "VARCHAR(256)"),
        ("product_name", "VARCHAR(256)"),
        ("product_version", "VARCHAR(128)"),
        ("source_type", "VARCHAR(32)"),
        ("vendor_contact", "VARCHAR(64)"),
        ("vendor_phone", "VARCHAR(32)"),
        ("ops_contact", "VARCHAR(64)"),
        ("ops_phone", "VARCHAR(32)"),
    ])
    _migrate_columns("djdj_records", [
        ("image_path", "VARCHAR(512)"),
    ])
    _migrate_columns("dingjia_backup_records", [
        ("vm_uuid", "VARCHAR(128)"),
        ("backup_versions", "INTEGER DEFAULT 1"),
        ("backup_versions_detail", "TEXT"),
        ("vm_size_gb", "FLOAT"),
        ("duration_seconds", "INTEGER"),
    ])
    # 外链填报
    try:
        Base.metadata.create_all(bind=engine, tables=[SharedLink.__table__])
    except Exception:
        pass
    # 操作日志
    try:
        Base.metadata.create_all(bind=engine, tables=[OperationLog.__table__])
    except Exception:
        pass
    _migrate_columns("operation_logs", [("function_name", "VARCHAR(256)")])
    _migrate_columns("subnets", [("created_by", "INTEGER")])
    _migrate_columns("zdns_domain_map", [
        ("owner_user_id", "INTEGER"), ("department_id", "INTEGER"), ("owner_name", "VARCHAR(128)")
    ])
    try:
        Base.metadata.create_all(bind=engine, tables=[DomainInventory.__table__])
    except Exception:
        pass
    # 去掉 subnet_cidr 全局唯一约束，改为 (cidr+created_by) 组合
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE subnets DROP INDEX subnet_cidr"))
            conn.commit()
    except Exception:
        pass
    # 信息系统新增归属字段
    _migrate_columns("info_systems", [
        ("dept_id", "INTEGER"),
        ("manager_name", "VARCHAR(64)"),
        ("manager_gh", "VARCHAR(32)"),
        ("owner_name", "VARCHAR(64)"),
        ("owner_gh", "VARCHAR(32)"),
    ])
    # 信息系统入口地址 + URL验证状态
    _migrate_columns("info_systems", [
        ("entry_url", "VARCHAR(512)"),
        ("url_status", "VARCHAR(16)"),
        ("created_by", "INTEGER"),
        ("claimed_by", "INTEGER"),
        ("claimed_at", "DATETIME"),
    ])
    _migrate_columns("supply_chains", [("created_by", "INTEGER"), ("claimed_by", "INTEGER"), ("claimed_at", "DATETIME")])
    _migrate_columns("djdj_records", [("created_by", "INTEGER"), ("claimed_by", "INTEGER"), ("claimed_at", "DATETIME")])
    _migrate_columns("icp_records", [("created_by", "INTEGER"), ("claimed_by", "INTEGER"), ("claimed_at", "DATETIME")])
    # 更新 scan_logs 表 status 列支持 queued
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE scan_logs MODIFY COLUMN status VARCHAR(16) NOT NULL DEFAULT 'running'"))
            conn.commit()
    except Exception:
        pass
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="OmniView API", version=get_version(), lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 操作日志中间件 — 记录所有 API 调用
@app.middleware("http")
async def operation_log_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = int((time.time() - start) * 1000)

    # 捕获响应体 — JSONResponse 在构造时即将 body 存入 self.body
    response_body = b""
    try:
        if hasattr(response, "body") and response.body:
            response_body = response.body if isinstance(response.body, bytes) else response.body.encode()
        elif hasattr(response, "body_iterator"):
            # 回退：消费 body_iterator
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            response_body = b"".join(chunks)
            response = Response(content=response_body, status_code=response.status_code,
                              headers=dict(response.headers), media_type=getattr(response, "media_type", None))
    except Exception:
        pass

    try:
        _log_operation(request, response, duration, response_body)
    except Exception as e:
        import logging
        logging.getLogger("operation_log").warning(f"操作日志写入失败: {e}")
    return response


def _log_operation(request: Request, response: Response, duration_ms: int, response_body: bytes = b""):
    """记录 API 操作日志到数据库。"""
    path = request.url.path
    # 跳过静态文件、健康检查、心跳等无意义路径
    if path in ("/health", "/uploads") or path.startswith("/uploads/"):
        return
    if "/workers/" in path and ("/heartbeat" in path or "/register" in path or "/unregister" in path):
        return
    if path in ("/api/version", "/api/system/scheduler-status", "/api/system/scheduler-interval"):
        return

    try:
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            # 从 JWT token 提取用户信息
            user_id = None
            username = ""
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                try:
                    from app.utils.security import decode_access_token
                    payload = decode_access_token(auth[7:])
                    if payload:
                        uid = payload.get("sub", "")
                        user_id = int(uid) if uid.isdigit() else None
                        if user_id:
                            u = db.query(User).get(user_id)
                            username = u.name or u.username if u else uid
                        else:
                            username = uid
                except Exception:
                    pass

            status = response.status_code
            action_label = _path_label(request.method, path)
            detail = ""

            # 从捕获的响应体读取 message
            if response_body:
                try:
                    import json
                    data = json.loads(response_body)
                    if isinstance(data, dict):
                        detail = str(data.get("message", data.get("detail", "")))
                except Exception:
                    pass
            if not detail:
                if status >= 500:
                    detail = "服务器错误"
                elif status >= 400:
                    detail = "请求失败"
                else:
                    detail = "完成"
            if len(detail) > 500:
                detail = detail[:500]

            log = OperationLog(
                user_id=user_id,
                username=username or "",
                ip_address=request.client.host if request.client else "",
                method=request.method,
                api_path=path[:256],              # 实际 API 路径
                function_name=action_label[:256],  # 中文功能描述
                status_code=status,
                duration_ms=duration_ms,
                detail=detail,
                user_agent=(request.headers.get("User-Agent", "") or "")[:512],
            )
            db.add(log)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        import logging
        logging.getLogger("operation_log").warning(f"操作日志DB写入失败: {e}")


# API路径 → 功能模块映射
_PATH_MAP = {
    # 信息资产管理
    "/api/assets/sync": "信息资产管理-信息资产总览-同步资产",
    "/api/assets/tree": "信息资产管理-信息资产总览-加载部门树",
    "/api/assets/vm-filters": "信息资产管理-信息资产总览-加载筛选选项",
    "/api/assets/auto-match/preview": "信息资产管理-信息资产总览-分组预览",
    "/api/assets/auto-match/execute": "信息资产管理-信息资产总览-自动分组",
    "/api/assets/match-owner/start": "信息资产管理-信息资产总览-匹配负责人",
    "/api/assets/match-owner/status": "信息资产管理-信息资产总览-查询匹配进度",
    "/api/assets/claim": "信息资产管理-信息资产总览-认领资产",
    "/api/assets/assign": "信息资产管理-信息资产总览-指派选中",
    "/api/assets/revoke": "信息资产管理-信息资产总览-撤销认领",
    "/api/assets/search": "信息资产管理-信息资产总览-搜索资产",
    "/api/assets/departments": "信息资产管理-信息资产总览-部门资产查询",
    # 信息系统管理
    "/api/info-systems": "信息资产管理-信息系统维护-查询",
    "/api/info-systems/import": "信息资产管理-信息系统维护-导入Excel",
    "/api/info-systems/export": "信息资产管理-信息系统维护-导出Excel",
    "/api/info-systems/sync-from-platform": "信息资产管理-信息系统维护-数据同步",
    "/api/info-systems/staff-search": "信息资产管理-信息系统维护-搜索人员",
    "/api/info-systems/staff-lookup": "信息资产管理-信息系统维护-查询教职工",
    "/api/info-systems/staff-register": "信息资产管理-信息系统维护-注册人员",
    "/api/info-systems/djdj": "信息资产管理-等保信息维护",
    "/api/info-systems/icp": "信息资产管理-ICP备案维护",
    "/api/info-systems/supply-chain": "信息资产管理-供应链信息维护",
    "/api/info-systems/batch-claim": "信息资产管理-批量认领",
    "/api/info-systems/batch-revoke": "信息资产管理-批量撤销认领",
    # 外链
    "/api/shared-links": "系统管理-外链管理",
    "/api/shared-links/shared": "外链填报-保存",
    # 设备管理
    "/api/switches": "集成管理-交换机管理",
    "/api/vcenters": "集成管理-vCenter管理",
    "/api/f5": "集成管理-F5管理",
    "/api/zdns": "集成管理-ZDNS管理",
    "/api/qax": "集成管理-椒图管理",
    "/api/dingjia": "集成管理-鼎甲备份管理",
    # 日志/监控
    "/api/scan-logs": "日志信息-任务日志",
    "/api/operation-logs": "日志信息-操作日志",
    # 用户/系统
    "/api/users": "系统管理-用户管理",
    "/api/auth": "用户认证-登录",
    "/api/system": "系统管理-系统管理",
    "/api/departments": "系统管理-组织机构",
    "/api/workers": "系统管理-Worker管理",
    "/api/history": "日志信息-历史记录",
    "/api/dashboard": "仪表盘-仪表盘",
}

_ACTION_MAP = {"POST": "创建", "PUT": "更新", "DELETE": "删除", "GET": "查询", "PATCH": "修改"}


def _path_label(method: str, path: str) -> str:
    """根据 API 路径和请求方法生成可读的操作描述。"""
    # 先精确匹配
    api_path = path
    if not api_path.startswith("/api/"):
        api_path = "/api" + api_path
    # 去掉尾部数字ID
    import re
    clean = re.sub(r'/\d+$', '', api_path)
    clean = re.sub(r'/\d+/', '/id/', clean)

    # 查找最匹配的路径
    best = ""
    for k, v in _PATH_MAP.items():
        if clean.startswith(k) and len(k) > len(best):
            best = k
    if best:
        label = _PATH_MAP[best]
        action = _ACTION_MAP.get(method, method)
        return f"{label}-{action}"
    # 回退：从路径提取资源名
    parts = [p for p in clean.strip("/").split("/") if p and p != "api"]
    resource = ""
    for p in reversed(parts):
        if p.isdigit() or p == "id" or len(p) == 36:
            continue
        resource = p
        break
    action = _ACTION_MAP.get(method, method)
    return f"{resource}-{action}" if resource else f"{method} {clean}"


app.include_router(api_router)

# WebSocket 端点 — 扫描进度实时推送
from app.api.ws import ws_scan_progress
app.add_websocket_route("/ws/scan-progress", ws_scan_progress)


@app.get("/health")
def health_check():
    return {"status": "ok"}

# 静态文件服务（上传文件）
os.makedirs("uploads/djdj", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
