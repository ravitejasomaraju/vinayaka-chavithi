import psycopg

try:
    conn = psycopg.connect(
        host="localhost",
        port=5432,
        dbname="vinayaka_chavithi",
        user="postgres",
        password="1811"
    )

    print("Database connected successfully!")

    conn.close()

except Exception as e:
    print("Database connection failed!")
    print(e)