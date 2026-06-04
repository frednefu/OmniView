import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.database import engine, Base
from app.models import User, Switch, ScanResult, RouteTable, ScanLog, Subnet, History, VCenter, VMInventory, EsxiHost, Datastore, Department, StaffInfo, ApiConfig, AssetInventory
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
        ("vm_size_gb", "FLOAT"),
    ])
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
    ])
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
