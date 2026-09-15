from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from src.config import settings
import os

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def _migrate_db(engine):
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if 'businesses' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('businesses')]
        with engine.connect() as conn:
            if 'email_source_url' not in columns:
                conn.execute(text('ALTER TABLE businesses ADD COLUMN email_source_url VARCHAR(500)'))
            if 'email_enrichment_status' not in columns:
                conn.execute(text('ALTER TABLE businesses ADD COLUMN email_enrichment_status VARCHAR(100)'))
            if 'email_enriched_at' not in columns:
                conn.execute(text('ALTER TABLE businesses ADD COLUMN email_enriched_at DATETIME'))
            conn.commit()

    if 'run_log' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('run_log')]
        with engine.connect() as conn:
            if 'jobs_total' not in columns:
                conn.execute(text('ALTER TABLE run_log ADD COLUMN jobs_total INTEGER NOT NULL DEFAULT 0'))
            if 'jobs_retried' not in columns:
                conn.execute(text('ALTER TABLE run_log ADD COLUMN jobs_retried INTEGER NOT NULL DEFAULT 0'))
            if 'jobs_recovered' not in columns:
                conn.execute(text('ALTER TABLE run_log ADD COLUMN jobs_recovered INTEGER NOT NULL DEFAULT 0'))
            if 'email_enriched' not in columns:
                conn.execute(text('ALTER TABLE run_log ADD COLUMN email_enriched INTEGER NOT NULL DEFAULT 0'))
            if 'email_found' not in columns:
                conn.execute(text('ALTER TABLE run_log ADD COLUMN email_found INTEGER NOT NULL DEFAULT 0'))
            if 'email_not_found' not in columns:
                conn.execute(text('ALTER TABLE run_log ADD COLUMN email_not_found INTEGER NOT NULL DEFAULT 0'))
            if 'email_failed' not in columns:
                conn.execute(text('ALTER TABLE run_log ADD COLUMN email_failed INTEGER NOT NULL DEFAULT 0'))
            if 'errors_count' not in columns:
                conn.execute(text('ALTER TABLE run_log ADD COLUMN errors_count INTEGER NOT NULL DEFAULT 0'))
            conn.commit()

def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_db(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
