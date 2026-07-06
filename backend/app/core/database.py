"""SQLAlchemy engine/session. Postgres in production, SQLite fallback in dev.

Pool sizing is load-test informed (Phase 6): the SQLAlchemy default
(pool_size=5, max_overflow=10) exhausts under ~60 concurrent chat requests
and queues connections until timeout. We run a wider pool, and for SQLite
additionally enable WAL + a busy timeout so concurrent readers never block
behind the single writer.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15} if _is_sqlite else {},
    pool_pre_ping=True,
    pool_size=5 if _is_sqlite else 25,   # SQLite: writes serialize anyway; keep it modest
    max_overflow=60,                      # absorb bursts instead of timing out
    pool_timeout=30,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover — exercised implicitly
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")      # readers don't block behind the writer
        cursor.execute("PRAGMA busy_timeout=15000")    # wait for the writer instead of erroring
        cursor.execute("PRAGMA synchronous=NORMAL")    # safe with WAL, much faster
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    # Import models so metadata is populated before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
