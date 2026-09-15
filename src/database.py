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

def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_db(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
