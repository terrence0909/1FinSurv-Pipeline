# scripts/test_db_connection.py
import os
import psycopg2
from dotenv import load_dotenv

# Load .env file
load_dotenv()

def test_connection():
    try:
        conn = psycopg2.connect(
            dbname="finsurv",
            user="admin",
            password=os.getenv("PG_PASSWORD", "SecurePass123!"),
            host="localhost",
            port=5432
        )
        cur = conn.cursor()
        cur.execute("SELECT message FROM test_connection LIMIT 1;")
        result = cur.fetchone()
        print(f"Database connection successful! Message: {result[0]}")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    test_connection()