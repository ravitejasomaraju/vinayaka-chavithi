import os
import psycopg


def get_connection():
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        return psycopg.connect(database_url)

    return psycopg.connect(
        host="localhost",
        port=5432,
        dbname="vinayaka_chavithi",
        user="postgres",
        password="1811"
    )