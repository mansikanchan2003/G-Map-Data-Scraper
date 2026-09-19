import os
import sys
from datetime import datetime, timezone
from sqlalchemy import create_engine, MetaData

import os
from dotenv import load_dotenv
import urllib.parse
load_dotenv()
POSTGRES_URL = os.getenv('DATABASE_URL')
if not POSTGRES_URL:
    pwd = os.getenv('POSTGRES_PASSWORD')
    pwd_escaped = urllib.parse.quote_plus(pwd) if pwd else ""
    POSTGRES_URL = f"postgresql+psycopg://gmap_user:{pwd_escaped}@postgres:5432/gmap_scraper"

# Setup database URLs
SQLITE_URL = "sqlite:///data/gmaps_discovery.db"

# Create engines
sqlite_engine = create_engine(SQLITE_URL)
pg_engine = create_engine(POSTGRES_URL)

# Reflect tables
sqlite_metadata = MetaData()
sqlite_metadata.reflect(bind=sqlite_engine)
pg_metadata = MetaData()
pg_metadata.reflect(bind=pg_engine)

def migrate_table(table_name, transform_fn=None):
    print(f"Migrating {table_name}...")
    sqlite_table = sqlite_metadata.tables[table_name]
    pg_table = pg_metadata.tables[table_name]
    
    with sqlite_engine.connect() as src_conn, pg_engine.begin() as dst_conn:
        result = src_conn.execute(sqlite_table.select())
        rows = result.fetchall()
        
        if not rows:
            print(f"  No rows in {table_name}")
            return len(rows)
            
        insert_data = []
        for row in rows:
            # SQLAlchemy 2.0 Row is a tuple-like object, convert to dict
            row_dict = row._asdict()
            if transform_fn:
                row_dict = transform_fn(row_dict)
            insert_data.append(row_dict)
            
        # Batch insert
        batch_size = 500
        for i in range(0, len(insert_data), batch_size):
            batch = insert_data[i:i+batch_size]
            dst_conn.execute(pg_table.insert(), batch)
            
        print(f"  Migrated {len(rows)} rows to {table_name}")
        return len(rows)

def transform_datetime(dt_str):
    if not dt_str:
        return None
    if isinstance(dt_str, datetime):
        if dt_str.tzinfo is None:
            return dt_str.replace(tzinfo=timezone.utc)
        return dt_str
    if isinstance(dt_str, str):
        try:
            # Handle fractional seconds
            if '.' in dt_str:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S.%f")
            else:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return dt_str

def transform_locations(row):
    row['created_at'] = transform_datetime(row.get('created_at'))
    row['updated_at'] = transform_datetime(row.get('updated_at'))
    return row

def transform_categories(row):
    row['created_at'] = transform_datetime(row.get('created_at'))
    row['updated_at'] = transform_datetime(row.get('updated_at'))
    return row

def transform_jobs(row):
    row['created_at'] = transform_datetime(row.get('created_at'))
    row['updated_at'] = transform_datetime(row.get('updated_at'))
    return row

def transform_businesses(row):
    row['created_at'] = transform_datetime(row.get('created_at'))
    row['updated_at'] = transform_datetime(row.get('updated_at'))
    row['email_enriched_at'] = transform_datetime(row.get('email_enriched_at'))
    if 'is_valid' in row and row['is_valid'] is not None:
        row['is_valid'] = bool(row['is_valid'])
    return row

def transform_run_log(row):
    row['created_at'] = transform_datetime(row.get('created_at'))
    row['updated_at'] = transform_datetime(row.get('updated_at'))
    row['started_at'] = transform_datetime(row.get('started_at'))
    row['completed_at'] = transform_datetime(row.get('completed_at'))
    if 'trigger_source' in row and row['trigger_source']:
        row['trigger_source'] = row['trigger_source'][:20]
    return row

def main():
    print("Starting migration...")
    migrate_table('locations', transform_locations)
    migrate_table('categories', transform_categories)
    migrate_table('jobs', transform_jobs)
    migrate_table('businesses', transform_businesses)
    migrate_table('run_log', transform_run_log)
    print("Migration complete!")

if __name__ == "__main__":
    main()
