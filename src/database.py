from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool, QueuePool
from src.config import settings

# ---------------------------------------------------------------------------
# Engine configuration: PostgreSQL uses connection pooling;
# SQLite uses check_same_thread=False for single-file dev usage.
# ---------------------------------------------------------------------------

if settings.is_postgresql:
    engine = create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,       # detect stale connections before use
        pool_recycle=1800,        # recycle connections every 30 minutes
        echo=False
    )
else:
    # SQLite: single-file, development / test only
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        echo=False
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def _migrate_db(eng) -> None:
    """
    Ad-hoc schema migration for SQLite local development.
    For PostgreSQL production, use Alembic: `alembic upgrade head`.
    This function is intentionally a no-op for PostgreSQL.
    """
    if not settings.is_sqlite:
        return

    from sqlalchemy import inspect, text
    inspector = inspect(eng)

    if "businesses" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("businesses")]
        with eng.connect() as conn:
            if "email_source_url" not in columns:
                conn.execute(text("ALTER TABLE businesses ADD COLUMN email_source_url VARCHAR(500)"))
            if "email_enrichment_status" not in columns:
                conn.execute(text("ALTER TABLE businesses ADD COLUMN email_enrichment_status VARCHAR(100)"))
            if "email_enriched_at" not in columns:
                conn.execute(text("ALTER TABLE businesses ADD COLUMN email_enriched_at DATETIME"))
            conn.commit()

    if "run_log" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("run_log")]
        with eng.connect() as conn:
            if "jobs_total" not in columns:
                conn.execute(text("ALTER TABLE run_log ADD COLUMN jobs_total INTEGER NOT NULL DEFAULT 0"))
            if "jobs_retried" not in columns:
                conn.execute(text("ALTER TABLE run_log ADD COLUMN jobs_retried INTEGER NOT NULL DEFAULT 0"))
            if "jobs_recovered" not in columns:
                conn.execute(text("ALTER TABLE run_log ADD COLUMN jobs_recovered INTEGER NOT NULL DEFAULT 0"))
            if "email_enriched" not in columns:
                conn.execute(text("ALTER TABLE run_log ADD COLUMN email_enriched INTEGER NOT NULL DEFAULT 0"))
            if "email_found" not in columns:
                conn.execute(text("ALTER TABLE run_log ADD COLUMN email_found INTEGER NOT NULL DEFAULT 0"))
            if "email_not_found" not in columns:
                conn.execute(text("ALTER TABLE run_log ADD COLUMN email_not_found INTEGER NOT NULL DEFAULT 0"))
            if "email_failed" not in columns:
                conn.execute(text("ALTER TABLE run_log ADD COLUMN email_failed INTEGER NOT NULL DEFAULT 0"))
            if "errors_count" not in columns:
                conn.execute(text("ALTER TABLE run_log ADD COLUMN errors_count INTEGER NOT NULL DEFAULT 0"))
            conn.commit()


def init_db() -> None:
    """
    Initialize database schema.

    - SQLite (development): creates all tables and runs ad-hoc column migrations.
    - PostgreSQL (production): only creates tables if they do not exist.
      For schema evolution on PostgreSQL, use: `alembic upgrade head`.

    This function NEVER drops existing tables or data.
    """
    Base.metadata.create_all(bind=engine)
    _migrate_db(engine)


def get_db():
    """FastAPI dependency: yields a SQLAlchemy session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
