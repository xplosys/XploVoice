# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Database engine and tenant-scoped sessions.

Tenant isolation is enforced by PostgreSQL Row-Level Security. The application connects with a runtime role
that has neither SUPERUSER nor BYPASSRLS, and sets `app.tenant_id` / `app.user_id` transaction-locally only
after the server has verified the caller's identity and membership. A browser-supplied tenant id is never used.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def set_context(session: Session, *, tenant_id: UUID | None = None, user_id: UUID | None = None) -> None:
    """Set RLS context for the current transaction only (SET LOCAL semantics via set_config(..., true))."""
    session.execute(
        text("select set_config('app.tenant_id', :t, true), set_config('app.user_id', :u, true)"),
        {"t": str(tenant_id) if tenant_id else "", "u": str(user_id) if user_id else ""},
    )


@contextmanager
def session_scope(*, tenant_id: UUID | None = None, user_id: UUID | None = None) -> Iterator[Session]:
    get_engine()
    assert _session_factory is not None
    session = _session_factory()
    try:
        session.begin()
        set_context(session, tenant_id=tenant_id, user_id=user_id)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
