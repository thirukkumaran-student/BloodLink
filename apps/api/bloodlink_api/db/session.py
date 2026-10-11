"""Database engine + session management (owner: D1).

The only place a database connection is created. Applications (API and web) go
through the API; neither client module may import this (enforced by
``tests/test_architecture.py``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from bloodlink_api.core.settings import get_settings
from bloodlink_api.db.base import Base


def build_engine(database_url: str | None = None, *, echo: bool | None = None) -> Engine:
    settings = get_settings()
    url = database_url or settings.resolved_database_url()
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, echo=settings.sql_echo if echo is None else echo, **kwargs)

    if url.startswith("sqlite"):
        # SQLite needs FK enforcement switched on per connection.
        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory


def get_db() -> Iterator[Session]:
    """FastAPI dependency — one transaction-scoped session per request."""
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Session for scripts, seeders and background tasks."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    """Create tables from the canonical metadata (dev/test convenience)."""
    import bloodlink_api.db.models  # noqa: F401  (register all mappers)

    Base.metadata.create_all(bind=get_engine())


def drop_all() -> None:
    """Drop every table.

    Only for a throwaway database: the test suite uses it when it runs against
    PostgreSQL, where a file cannot simply be deleted between runs.
    """
    import bloodlink_api.db.models  # noqa: F401  (register all mappers)

    Base.metadata.drop_all(bind=get_engine())


def reset_engine() -> None:
    """Test helper: drop cached engine/session factory."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
