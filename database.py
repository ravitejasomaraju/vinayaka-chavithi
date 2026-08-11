import psycopg


def get_connection():
    return psycopg.connect(
        host="localhost",
        port=5432,
        dbname="vinayaka_chavithi",
        user="postgres",
        password="1811"
    )