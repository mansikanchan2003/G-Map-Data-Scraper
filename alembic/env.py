"""Alembic Environment Configuration

Reads DATABASE_URL from application settings so the same migration command
works for both SQLite (development) and PostgreSQL (production).

Usage:
  # SQLite (development — default):
  alembic upgrade head

  # PostgreSQL (production):
  DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname alembic upgrade head
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# ---------------------------------------------------------------------------
# Import application models so Alembic's autogenerate can see them.
# ---------------------------------------------------------------------------
from src.database import Base  # noqa: F401 — registers metadata
import src.models  # noqa: F401 — imports all ORM models

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from application settings.
# This ensures alembic always uses the same DB as the running application.
from src.config import settings as app_settings

config.set_main_option("sqlalchemy.url", str(app_settings.database_url).replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (against a live database)."""
    url = config.get_main_option("sqlalchemy.url")

    # Use NullPool for PostgreSQL during migrations to avoid connection leaks.
    poolclass = pool.NullPool if app_settings.is_postgresql else pool.StaticPool

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=poolclass,
        url=url,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
