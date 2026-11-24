# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Session for unauthenticated endpoints (register, login, refresh). No tenant context is set up front;
services set it only after verifying identity."""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from .context import open_session


def get_public_session() -> Iterator[Session]:
    session = open_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
