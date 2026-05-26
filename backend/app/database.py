from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

_connect_args = {}
if "sqlite" in settings.database_url:
    _connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    settings.database_url,
    pool_size=20, max_overflow=40, pool_recycle=3600,
    connect_args=_connect_args,
)


@event.listens_for(engine, "connect")
def _on_connect(dbapi_conn, _connection_record):
    """SQLite：每次连接时启用 WAL 模式 + 外键约束。

    WAL 模式允许多个读操作与一个写操作并发，避免 "database is locked" 错误。
    """
    if "sqlite" in settings.database_url:
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
