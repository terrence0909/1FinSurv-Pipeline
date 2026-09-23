import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def query_transactions():
    try:
        conn = psycopg2.connect(
            dbname="finsurv",
            user="admin",
            password=os.getenv("PG_PASSWORD", "SecurePass123!"),
            host="localhost",
            port=5432
        )
        cur = conn.cursor()
        
        # Query the view
        cur.execute("""
            SELECT 
                transaction_reference,
                transaction_amount,
                transaction_currency,
                equivalent_zar_amount,
                sarb_bop_code,
                bop_description,
                internal_status
            FROM vw_finsurv_submission_payload
        """)
        
        rows = cur.fetchall()
        print("Transactions ready for 1FinSurv submission:")
        print("-" * 70)
        for row in rows:
            print(f"Reference: {row[0]}")
            print(f"  Amount: {row[1]} {row[2]} (ZAR {row[3]:,.2f})")
            print(f"  BOP Code: {row[4]} - {row[5]}")
            print(f"  Status: {row[6]}")
            print("-" * 70)
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Query failed: {e}")
        return False

if __name__ == "__main__":
    query_transactions()