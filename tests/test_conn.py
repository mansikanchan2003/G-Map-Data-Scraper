import psycopg
import sys
import os
from dotenv import load_dotenv

def verify_connection():
    load_dotenv()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("No DATABASE_URL found in environment.")
        sys.exit(1)

    try:
        print("Connecting with DATABASE_URL...")
        conn = psycopg.connect(db_url)
        print("Success connecting to PostgreSQL!")
        conn.close()
        sys.exit(0)
    except Exception as e:
        print("Failed to connect:", type(e).__name__)
        sys.exit(1)

if __name__ == "__main__":
    verify_connection()
