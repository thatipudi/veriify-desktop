"""One-time database bootstrap for Veriify.

Starts PostgreSQL (if managed by Homebrew) and creates the `veriify` database.
Run once before the first launch:  python setup_db.py
"""

import os
import subprocess
import sys
import time

import psycopg2


def setup():
    # Start PostgreSQL if not running (ignore errors — it may already be up,
    # or managed some other way).
    try:
        subprocess.run(
            ["brew", "services", "start", "postgresql@17"],
            capture_output=True,
        )
        time.sleep(2)
    except FileNotFoundError:
        pass  # brew not installed — assume Postgres is already running

    db_name = os.getenv("DB_NAME", "veriify")
    db_user = os.getenv("DB_USER", os.environ.get("USER", "postgres"))
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")

    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user=db_user,
            host=db_host,
            port=db_port,
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (db_name,))
        if not cur.fetchone():
            # Database names can't be parameterized — db_name is from our own env.
            cur.execute(f'CREATE DATABASE "{db_name}"')
            print(f"✅ Database '{db_name}' created")
        else:
            print(f"✅ Database '{db_name}' already exists")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Load .env so DB_NAME / DB_USER etc. are honored.
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    setup()
