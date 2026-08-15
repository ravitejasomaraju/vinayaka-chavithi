import os
import psycopg

def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured. Set your Supabase PostgreSQL connection string in Render environment variables.")
    return psycopg.connect(database_url)
