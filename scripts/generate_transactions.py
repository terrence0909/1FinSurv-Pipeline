import os
import uuid
import random
import json
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Realistic wallet addresses (simulating SWIFT-connected banks)
BANK_WALLETS = {
    'HSBC': '0x95222290DD7278Aa3Ddd389Cc1E1d165CC4BAfe5',
    'UBS': '0x281055afc982d96fab65b3a49cac8b878184cb16',
    'Citi': '0x3a5f1c9e8b2d4f6a7c3e9f1b2d4c6a8e9f0b1c2d',
    'BNP': '0x7f83b1a2c3d4e5f60718293a4b5c6d7e8f90a1b2',
    'Wells Fargo': '0x8a4b2c1d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b'
}

# Realistic BOP codes with descriptions
BOP_CODES = {
    '101_01': {'desc': 'Imported goods - Advance payment', 'group': 'Outward - Trade'},
    '101_02': {'desc': 'Imported goods - Open account', 'group': 'Outward - Trade'},
    '511_01': {'desc': 'Gift to non-resident', 'group': 'Outward - Capital Transfers'},
    '511_02': {'desc': 'Alimony or maintenance', 'group': 'Outward - Capital Transfers'},
    '201_01': {'desc': 'Exports of goods', 'group': 'Inward - Trade'},
    '301_01': {'desc': 'Professional services', 'group': 'Inward - Services'},
    '401_01': {'desc': 'Dividend payments', 'group': 'Outward - Income'},
    '401_02': {'desc': 'Interest payments', 'group': 'Outward - Income'}
}

ALLOWANCE_TYPES = ['SDA', 'FDA', 'TRADE']
CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'ZAR']
EXCHANGE_RATES = {'USD': 18.45, 'EUR': 19.87, 'GBP': 23.12, 'JPY': 0.12, 'ZAR': 1.0}

def generate_transaction(date_override=None):
    """Generate a realistic blockchain transaction"""
    bank = random.choice(list(BANK_WALLETS.keys()))
    bop_code = random.choice(list(BOP_CODES.keys()))
    
    # Amount varies by BOP category
    if bop_code.startswith('1') or bop_code.startswith('2'):  # Trade
        amount = round(random.uniform(10000, 500000), 2)
    elif bop_code.startswith('5'):  # Transfers
        amount = round(random.uniform(1000, 50000), 2)
    else:  # Income
        amount = round(random.uniform(500, 10000), 2)
    
    currency = random.choice(CURRENCIES)
    
    return {
        'swift_uetr': str(uuid.uuid4()),
        'ledger_tx_hash': f"0x{''.join(random.choices('0123456789abcdef', k=64))}",
        'block_number': random.randint(14000000, 16000000),
        'wallet_address_originator': BANK_WALLETS[bank],
        'wallet_address_beneficiary': random.choice(list(BANK_WALLETS.values())),
        'originator_kyc_id_hash': f"{''.join(random.choices('0123456789abcdef', k=64))}",
        'beneficiary_kyc_id_hash': f"{''.join(random.choices('0123456789abcdef', k=64))}",
        'amount': amount,
        'currency_code': currency,
        'exchange_rate_zar': EXCHANGE_RATES[currency],
        'value_date': date_override if date_override else (datetime.now() - timedelta(days=random.randint(0, 90))),
        'bop_code': bop_code,
        'allowance_type': random.choice(ALLOWANCE_TYPES),
        'bank': bank
    }

def insert_transaction(conn, tx):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tx_blockchain_payments (
            swift_uetr, ledger_tx_hash, block_number,
            wallet_address_originator, wallet_address_beneficiary,
            originator_kyc_id_hash, beneficiary_kyc_id_hash,
            amount, currency_code, exchange_rate_zar, value_date,
            bop_code, allowance_type
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING tx_id
    """, (
        tx['swift_uetr'], tx['ledger_tx_hash'], tx['block_number'],
        tx['wallet_address_originator'], tx['wallet_address_beneficiary'],
        tx['originator_kyc_id_hash'], tx['beneficiary_kyc_id_hash'],
        tx['amount'], tx['currency_code'], tx['exchange_rate_zar'],
        tx['value_date'], tx['bop_code'], tx['allowance_type']
    ))
    tx_id = cur.fetchone()[0]
    conn.commit()
    return tx_id

def validate_transaction(conn, tx_id):
    cur = conn.cursor()
    
    cur.execute("""
        SELECT originator_kyc_id_hash 
        FROM tx_blockchain_payments 
        WHERE tx_id = %s
    """, (tx_id,))
    originator = cur.fetchone()
    
    if not originator:
        return 'FAILED_VALIDATION'
    
    originator_hash = originator[0]
    
    cur.execute("""
        SELECT 
            COALESCE(SUM(amount * exchange_rate_zar), 0) as total_zar
        FROM tx_blockchain_payments
        WHERE originator_kyc_id_hash = %s
        AND value_date >= DATE_TRUNC('year', CURRENT_DATE)
    """, (originator_hash,))
    
    total_zar = cur.fetchone()[0] or 0
    
    if total_zar > 1000000:
        status = 'FAILED_VALIDATION'
        error_log = json.dumps({"reason": "Annual allowance exceeded", "total_zar": str(total_zar)})
    else:
        status = 'PASSED_VALIDATION'
        error_log = None
    
    cur.execute("""
        INSERT INTO tx_finsurv_validation (
            tx_id, validation_status, allowance_limit_checked,
            cryptographic_proof_verified, error_log
        ) VALUES (%s, %s, %s, %s, %s)
    """, (tx_id, status, True, True, error_log))
    
    conn.commit()
    return status

def generate_historical_data(conn, days=90, transactions_per_day=5):
    """Generate transactions spread over the last X days"""
    print(f"Generating {days} days of historical data...")
    
    total_created = 0
    current_date = datetime.now() - timedelta(days=days)
    
    while current_date <= datetime.now():
        # Generate 2-8 transactions per day
        num_tx = random.randint(2, 8)
        for _ in range(num_tx):
            tx = generate_transaction(current_date)
            tx_id = insert_transaction(conn, tx)
            status = validate_transaction(conn, tx_id)
            total_created += 1
        
        # Show progress
        if total_created % 50 == 0:
            print(f"  Generated {total_created} transactions so far...")
        
        current_date += timedelta(days=1)
    
    return total_created

def clear_old_data(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM tx_finsurv_validation CASCADE;")
    cur.execute("DELETE FROM tx_blockchain_payments CASCADE;")
    conn.commit()
    print("Cleared existing data")

if __name__ == "__main__":
    print("Generating realistic transaction data...")
    
    try:
        conn = psycopg2.connect(
            dbname="finsurv",
            user="admin",
            password=os.getenv("PG_PASSWORD", "SecurePass123!"),
            host="localhost",
            port=5432
        )
        
        # Clear existing data for fresh start
        clear_old_data(conn)
        
        # Generate 90 days of historical data
        total = generate_historical_data(conn, days=90)
        
        print(f"\nSummary:")
        print(f"  Total transactions generated: {total}")
        
        # Show breakdown
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN validation_status = 'PASSED_VALIDATION' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN validation_status = 'FAILED_VALIDATION' THEN 1 ELSE 0 END) as failed
            FROM tx_finsurv_validation
        """)
        total, passed, failed = cur.fetchone()
        print(f"  Passed: {passed}, Failed: {failed}")
        
        cur.execute("""
            SELECT currency_code, COUNT(*), SUM(amount) 
            FROM tx_blockchain_payments 
            GROUP BY currency_code
        """)
        print("\nCurrency breakdown:")
        for currency, count, total_amount in cur.fetchall():
            print(f"  {currency}: {count} transactions, total {total_amount:,.2f}")
        
        cur.close()
        conn.close()
        
        print("\nReady for dashboard refresh!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()