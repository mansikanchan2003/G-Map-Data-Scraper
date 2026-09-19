import os
import sys
from sqlalchemy import create_engine, MetaData, select, func

import urllib.parse
from dotenv import load_dotenv

load_dotenv()
POSTGRES_URL = os.getenv('DATABASE_URL')
if not POSTGRES_URL:
    pwd = os.getenv('POSTGRES_PASSWORD')
    pwd_escaped = urllib.parse.quote_plus(pwd) if pwd else ""
    POSTGRES_URL = f"postgresql+psycopg://gmap_user:{pwd_escaped}@postgres:5432/gmap_scraper"

SQLITE_URL = "sqlite:///data/gmaps_discovery.db"

def validate():
    sqlite_engine = create_engine(SQLITE_URL)
    pg_engine = create_engine(POSTGRES_URL)

    metadata = MetaData()
    metadata.reflect(bind=sqlite_engine)

    tables = ['locations', 'categories', 'jobs', 'businesses', 'run_log']

    print("--- MIGRATION VALIDATION REPORT ---")
    print(f"{'TABLE':<15} | {'SQLITE':<10} | {'POSTGRES':<10} | {'DIFF':<10}")
    print("-" * 55)

    sqlite_counts = {}
    pg_counts = {}

    for table in tables:
        t = metadata.tables[table]
        with sqlite_engine.connect() as sc:
            sq_c = sc.scalar(select(func.count()).select_from(t))
            sqlite_counts[table] = sq_c
        with pg_engine.connect() as pc:
            pg_c = pc.scalar(select(func.count()).select_from(t))
            pg_counts[table] = pg_c

        diff = pg_c - sq_c
        print(f"{table:<15} | {sq_c:<10} | {pg_c:<10} | {diff:<10}")

    print("\n--- SPECIFIC VALIDATIONS ---")
    
    # Pending Jobs
    t_jobs = metadata.tables['jobs']
    with sqlite_engine.connect() as sc:
        sq_pending = sc.scalar(select(func.count()).select_from(t_jobs).where(t_jobs.c.status == 'PENDING'))
    with pg_engine.connect() as pc:
        pg_pending = pc.scalar(select(func.count()).select_from(t_jobs).where(t_jobs.c.status == 'PENDING'))
    
    print(f"PENDING jobs: SQLite={sq_pending}, Postgres={pg_pending} (Diff: {pg_pending - sq_pending})")
    
    # Null distributions (example: businesses.is_valid)
    t_biz = metadata.tables['businesses']
    with sqlite_engine.connect() as sc:
        sq_valid_null = sc.scalar(select(func.count()).select_from(t_biz).where(t_biz.c.is_valid == None))
    with pg_engine.connect() as pc:
        pg_valid_null = pc.scalar(select(func.count()).select_from(t_biz).where(t_biz.c.is_valid == None))
        
    print(f"Businesses is_valid IS NULL: SQLite={sq_valid_null}, Postgres={pg_valid_null} (Diff: {pg_valid_null - sq_valid_null})")

if __name__ == "__main__":
    validate()
