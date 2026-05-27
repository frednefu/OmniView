from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.database import engine, Base
from app.models import User, Switch, ScanResult, RouteTable, ScanLog, Subnet, History, VCenter, VMInventory, EsxiHost, Datastore
from app.api.router import api_router
from app.services.scheduler_service import start_scheduler, shutdown_scheduler
from app.version import get_version


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
