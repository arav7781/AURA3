from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, event

import aura.models  # noqa: F401  (registers every table)
from aura.core.config import get_settings
from aura.models.base import Base

config = context.config
if config.config_file_name is not None and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    return config.attributes.get("database_url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url())

    @event.listens_for(engine, "connect")
    def _no_fk_checks(dbapi_conn, _record):  # noqa: ANN001
        # Batch migrations rebuild tables; foreign-key checks must be off, and the pragma has to run
        # outside a transaction, so it is set when the connection opens.
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")

    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
