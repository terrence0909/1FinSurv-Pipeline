import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def cleanup_zero_transactions():
    """Remove zero-value transactions from the database"""
    conn = psycopg2.connect(
        dbname="finsurv",
        user="admin",
        password=os.getenv("PG_PASSWORD", "SecurePass123!"),
        host="localhost",
        port=5432
    )
    cur = conn.cursor()
    
    # Count before
    cur.execute("SELECT COUNT(*) FROM tx_blockchain_payments WHERE amount = 0")
    before_count = cur.fetchone()[0]
    
    if before_count == 0:
        print("No zero-value transactions found.")
        cur.close()
        conn.close()
        return
    
    print(f"Found {before_count} zero-value transactions.")
    
    # Delete validation records first (due to foreign key)
    cur.execute("""
        DELETE FROM tx_finsurv_validation 
        WHERE tx_id IN (SELECT tx_id FROM tx_blockchain_payments WHERE amount = 0)
    """)
    
    # Delete the transactions
    cur.execute("DELETE FROM tx_blockchain_payments WHERE amount = 0")
    
    conn.commit()
    
    # Count after
    cur.execute("SELECT COUNT(*) FROM tx_blockchain_payments WHERE amount = 0")
    after_count = cur.fetchone()[0]
    
    print(f"Removed {before_count - after_count} zero-value transactions.")
    print(f"Remaining transactions: {after_count}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    cleanup_zero_transactions()