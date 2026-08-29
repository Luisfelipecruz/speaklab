"""Alembic environment.

Two things here are not boilerplate.

**The URL comes from config, not from alembic.ini.** `SYNC_DATABASE_URL` is derived from
`DATABASE_URL` by stripping the `+asyncpg` driver suffix, so there is one database
setting in this project and migrations cannot end up pointing somewhere the app is not.
`ALEMBIC_DATABASE_URL` overrides it — an environment variable rather than
`config.set_main_option`, because the ini parser interpolates `%` and a password
containing one would turn a scratch-database override into an unreadable error.

**`target_metadata` comes from importing `db_models`, the barrel.** A model file that
exists but is not imported there is invisible to autogenerate, and the resulting
migration is silently missing a table.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from config import SYNC_DATABASE_URL
from db_models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return os.environ.get("ALEMBIC_DATABASE_URL") or SYNC_DATABASE_URL


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting. `alembic upgrade head --sql`."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Native Postgres enums are created and dropped explicitly by the revision, so
        # the generated SQL is the whole story rather than most of it.
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Without this, a column whose type changes reads as no change at all and
            # autogenerate emits an empty revision — the worst possible outcome, since
            # it looks like success.
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
