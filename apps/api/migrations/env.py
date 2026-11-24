# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Alembic runs as the owner role (XV_MIGRATION_DATABASE_URL), never as the runtime role."""

from alembic import context
from sqlalchemy import create_engine

from xplovoice_api.core.config import get_settings


def run() -> None:
    engine = create_engine(get_settings().migration_database_url)
    with engine.connect() as conn:
        context.configure(connection=conn, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run()
