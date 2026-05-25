import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.models import User, Switch, ScanResult, RouteTable, ScanLog, Subnet, History, VCenter, VMInventory, EsxiHost, Datastore
from app.api.router import api_router
from app.services.scheduler_service import start_scheduler, shutdown_scheduler


def _migrate_vm_inventory_columns():
    """为已有 vm_inventory 表添加新列（SQLite ALTER TABLE）"""
    import sqlite3
    try:
        db_path = engine.url.database
        if db_path and db_path != ":memory:":
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cols = [r[1] for r in cur.execute("PRAGMA table_info(vm_inventory)").fetchall()]
            if "provisioned_gb" not in cols:
                cur.execute("ALTER TABLE vm_inventory ADD COLUMN provisioned_gb FLOAT")
            if "used_gb" not in cols:
                cur.execute("ALTER TABLE vm_inventory ADD COLUMN used_gb FLOAT")
            conn.commit()
            conn.close()
    except Exception:
        pass


def _migrate_datastore_columns():
    """为已有 datastores 表添加新列（mounted_host_count / storage_type）"""
    import sqlite3
    try:
        db_path = engine.url.database
        if db_path and db_path != ":memory:":
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cols = [r[1] for r in cur.execute("PRAGMA table_info(datastores)").fetchall()]
            if "mounted_host_count" not in cols:
                cur.execute("ALTER TABLE datastores ADD COLUMN mounted_host_count INTEGER DEFAULT 0")
            if "storage_type" not in cols:
                cur.execute("ALTER TABLE datastores ADD COLUMN storage_type VARCHAR(16) DEFAULT ''")
            conn.commit()
            conn.close()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_vm_inventory_columns()
    _migrate_datastore_columns()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="IPAM API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
