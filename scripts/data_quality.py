import os
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    """Get database connection"""
    return psycopg2.connect(
        dbname="finsurv",
        user="admin",
        password=os.getenv("PG_PASSWORD", "SecurePass123!"),
        host="localhost",
        port=5432
    )

def run_quality_checks():
    """Run comprehensive data quality checks"""
    conn = get_connection()
    cur = conn.cursor()
    
    print("=" * 70)
    print("DATA QUALITY REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 1. Overall Statistics
    print("\n1. OVERALL STATISTICS")
    print("-" * 50)
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT swift_uetr) as unique_uetr,
            COUNT(DISTINCT ledger_tx_hash) as unique_hashes,
            MIN(value_date) as oldest_tx,
            MAX(value_date) as newest_tx
        FROM tx_blockchain_payments
    """)
    total, unique_uetr, unique_hashes, oldest, newest = cur.fetchone()
    print(f"   Total transactions: {total:,}")
    print(f"   Unique UETRs: {unique_uetr:,}")
    print(f"   Unique hashes: {unique_hashes:,}")
    print(f"   Date range: {oldest.strftime('%Y-%m-%d')} to {newest.strftime('%Y-%m-%d')}")
    
    # 2. Validation Status
    print("\n2. VALIDATION STATUS")
    print("-" * 50)
    cur.execute("""
        SELECT 
            validation_status,
            COUNT(*) as count,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as percentage
        FROM tx_finsurv_validation
        GROUP BY validation_status
        ORDER BY count DESC
    """)
    for status, count, pct in cur.fetchall():
        print(f"   {status}: {count:,} ({pct:.1f}%)")
    
    # 3. Data Source Breakdown
    print("\n3. DATA SOURCE BREAKDOWN")
    print("-" * 50)
    cur.execute("""
        SELECT 
            COALESCE(data_source, 'unknown') as source,
            COUNT(*) as count,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as percentage,
            SUM(CASE WHEN validation_status = 'PASSED_VALIDATION' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN validation_status = 'FAILED_VALIDATION' THEN 1 ELSE 0 END) as failed
        FROM tx_blockchain_payments t
        JOIN tx_finsurv_validation v ON t.tx_id = v.tx_id
        GROUP BY COALESCE(data_source, 'unknown')
        ORDER BY count DESC
    """)
    for source, count, pct, passed, failed in cur.fetchall():
        pass_rate = (passed / count * 100) if count > 0 else 0
        print(f"   {source}: {count:,} ({pct:.1f}%) - Pass rate: {pass_rate:.1f}%")
    
    # 4. Currency Distribution
    print("\n4. CURRENCY DISTRIBUTION")
    print("-" * 50)
    cur.execute("""
        SELECT 
            currency_code,
            COUNT(*) as count,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount,
            MIN(amount) as min_amount,
            MAX(amount) as max_amount
        FROM tx_blockchain_payments
        GROUP BY currency_code
        ORDER BY count DESC
    """)
    for currency, count, total_amt, avg_amt, min_amt, max_amt in cur.fetchall():
        print(f"   {currency}: {count:,} transactions")
        print(f"      Total: {total_amt:,.2f}, Avg: {avg_amt:,.2f}")
        print(f"      Min: {min_amt:,.2f}, Max: {max_amt:,.2f}")
    
    # 5. BOP Category Breakdown
    print("\n5. BOP CATEGORY BREAKDOWN")
    print("-" * 50)
    cur.execute("""
        SELECT 
            b.category_group,
            COUNT(*) as count,
            SUM(t.amount * t.exchange_rate_zar) as total_zar
        FROM tx_blockchain_payments t
        JOIN ref_bop_codes b ON t.bop_code = b.bop_code
        GROUP BY b.category_group
        ORDER BY total_zar DESC
    """)
    for category, count, total_zar in cur.fetchall():
        print(f"   {category}: {count:,} transactions, ZAR {total_zar:,.2f}")
    
    # 6. Quality Issues
    print("\n6. QUALITY ISSUES")
    print("-" * 50)
    
    # Null values
    cur.execute("""
        SELECT 
            SUM(CASE WHEN swift_uetr IS NULL THEN 1 ELSE 0 END) as null_uetr,
            SUM(CASE WHEN ledger_tx_hash IS NULL THEN 1 ELSE 0 END) as null_hash,
            SUM(CASE WHEN amount IS NULL THEN 1 ELSE 0 END) as null_amount,
            SUM(CASE WHEN currency_code IS NULL THEN 1 ELSE 0 END) as null_currency,
            SUM(CASE WHEN value_date IS NULL THEN 1 ELSE 0 END) as null_date,
            SUM(CASE WHEN bop_code IS NULL THEN 1 ELSE 0 END) as null_bop
        FROM tx_blockchain_payments
    """)
    null_uetr, null_hash, null_amount, null_currency, null_date, null_bop = cur.fetchone()
    total_issues = null_uetr + null_hash + null_amount + null_currency + null_date + null_bop
    if total_issues > 0:
        print("   Null values found:")
        if null_uetr > 0:
            print(f"      - Null UETR: {null_uetr}")
        if null_hash > 0:
            print(f"      - Null hash: {null_hash}")
        if null_amount > 0:
            print(f"      - Null amount: {null_amount}")
        if null_currency > 0:
            print(f"      - Null currency: {null_currency}")
        if null_date > 0:
            print(f"      - Null date: {null_date}")
        if null_bop > 0:
            print(f"      - Null BOP: {null_bop}")
    else:
        print("   No null values found")
    
    # Duplicate hashes
    cur.execute("""
        SELECT ledger_tx_hash, COUNT(*) 
        FROM tx_blockchain_payments 
        GROUP BY ledger_tx_hash 
        HAVING COUNT(*) > 1
        LIMIT 10
    """)
    duplicates = cur.fetchall()
    if duplicates:
        print(f"   Duplicate hashes found: {len(duplicates)} (showing first 10)")
        for hash_val, count in duplicates[:10]:
            print(f"      - {hash_val[:20]}... appears {count} times")
    else:
        print("   No duplicate hashes found")
    
    # Failed transactions with errors
    cur.execute("""
        SELECT 
            COUNT(*) as failed_count,
            COUNT(DISTINCT tx_id) as unique_failures
        FROM tx_finsurv_validation
        WHERE validation_status = 'FAILED_VALIDATION'
        AND error_log IS NOT NULL
    """)
    failed_count, unique_failures = cur.fetchone()
    if failed_count > 0:
        print(f"   Failed transactions: {failed_count:,}")
        print(f"      Unique failure events: {unique_failures:,}")
        
        cur.execute("""
            SELECT error_log 
            FROM tx_finsurv_validation
            WHERE validation_status = 'FAILED_VALIDATION'
            AND error_log IS NOT NULL
            LIMIT 3
        """)
        print("      Sample errors:")
        for (error_log,) in cur.fetchall():
            print(f"      - {error_log}")
    else:
        print("   No failed transactions with errors")
    
    # 7. Time-based Analysis
    print("\n7. TIME-BASED ANALYSIS")
    print("-" * 50)
    
    cur.execute("""
        SELECT 
            EXTRACT(DOW FROM value_date) as day_of_week,
            COUNT(*) as count
        FROM tx_blockchain_payments
        GROUP BY EXTRACT(DOW FROM value_date)
        ORDER BY day_of_week
    """)
    day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    print("   Transactions by day of week:")
    for dow, count in cur.fetchall():
        print(f"      {day_names[int(dow)]}: {count:,}")
    
    cur.execute("""
        SELECT 
            EXTRACT(HOUR FROM value_date) as hour,
            COUNT(*) as count
        FROM tx_blockchain_payments
        GROUP BY EXTRACT(HOUR FROM value_date)
        ORDER BY hour
    """)
    print("   Peak hours:")
    hours = cur.fetchall()
    if hours:
        hours.sort(key=lambda x: x[1], reverse=True)
        for hour, count in hours[:3]:
            print(f"      {int(hour):02d}:00 - {count:,} transactions")
    
    # 8. Alert Summary
    print("\n8. ALERT SUMMARY")
    print("-" * 50)
    
    cur.execute("""
        SELECT 
            (SUM(CASE WHEN validation_status = 'PASSED_VALIDATION' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) as pass_rate
        FROM tx_finsurv_validation
    """)
    pass_rate = cur.fetchone()[0] or 0
    
    if pass_rate < 80:
        print(f"   CRITICAL: Pass rate is {pass_rate:.1f}% (below 80% threshold)")
    elif pass_rate < 90:
        print(f"   WARNING: Pass rate is {pass_rate:.1f}% (below 90% threshold)")
    else:
        print(f"   Pass rate is {pass_rate:.1f}%")
    
    cur.execute("""
        SELECT COUNT(*) 
        FROM tx_blockchain_payments 
        WHERE amount = 0
    """)
    zero_count = cur.fetchone()[0]
    if zero_count > 0:
        print(f"   {zero_count} zero-value transactions found")
    
    cur.execute("""
        SELECT COUNT(*) 
        FROM tx_blockchain_payments t
        LEFT JOIN tx_finsurv_validation v ON t.tx_id = v.tx_id
        WHERE v.tx_id IS NULL
    """)
    unvalidated = cur.fetchone()[0]
    if unvalidated > 0:
        print(f"   {unvalidated} transactions without validation records")
    
    print("\n" + "=" * 70)
    print("QUALITY CHECKS COMPLETE")
    print("=" * 70)
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    run_quality_checks()