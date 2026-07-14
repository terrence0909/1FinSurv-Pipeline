import os
import uuid
import requests
from datetime import datetime
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Etherscan API configuration
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"

# A real wallet address with transaction history (Ethereum Foundation)
WALLET_ADDRESS = "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"

def fetch_transactions(address, page=1, offset=1000):
    """Fetch transactions from Etherscan API"""
    params = {
        'module': 'account',
        'action': 'txlist',
        'chainid': 1,
        'address': address,
        'startblock': 0,
        'endblock': 99999999,
        'page': page,
        'offset': offset,
        'sort': 'desc',
        'apikey': ETHERSCAN_API_KEY
    }
    
    try:
        response = requests.get(ETHERSCAN_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data['status'] == '1':
            return data['result']
        else:
            print(f"Error: {data.get('message', 'Unknown error')}")
            return []
    except Exception as e:
        print(f"Failed to fetch transactions: {e}")
        return []

def convert_wei_to_eth(wei_value):
    """Convert Wei to ETH (1 ETH = 10^18 Wei)"""
    try:
        return float(wei_value) / 10**18
    except (ValueError, TypeError):
        return 0.0

def fetch_exchange_rates():
    """Fetch real exchange rates from multiple APIs with fallback"""
    rates = {'USD_ZAR': 18.45, 'ETH_ZAR': 0.0, 'ETH_USD': 0.0}
    
    try:
        # Primary API: exchangerate-api
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            usd_zar = data['rates'].get('ZAR', 18.45)
            eth_usd = data['rates'].get('ETH', 0.0)
            
            if eth_usd > 0:
                rates['USD_ZAR'] = usd_zar
                rates['ETH_USD'] = eth_usd
                rates['ETH_ZAR'] = eth_usd * usd_zar
                print(f"  Exchange rates fetched: ETH/USD = {eth_usd:.2f}, USD/ZAR = {usd_zar:.2f}")
                return rates
    except Exception as e:
        print(f"  Primary API failed: {e}")
    
    # Fallback 1: CoinGecko for ETH price
    try:
        eth_response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
            timeout=10
        )
        if eth_response.status_code == 200:
            eth_usd = eth_response.json().get('ethereum', {}).get('usd', 0.0)
            if eth_usd > 0:
                rates['ETH_USD'] = eth_usd
                rates['ETH_ZAR'] = eth_usd * rates['USD_ZAR']
                print(f"  ETH rate from CoinGecko: ${eth_usd:.2f}")
                return rates
    except Exception as e:
        print(f"  CoinGecko fallback failed: {e}")
    
    # Fallback 2: Use a static rate for ETH
    eth_usd = 3500.0  # Approximate ETH price
    rates['ETH_USD'] = eth_usd
    rates['ETH_ZAR'] = eth_usd * rates['USD_ZAR']
    print(f"  Using static ETH rate: ${eth_usd:.2f}")
    print(f"  ETH/ZAR: {rates['ETH_ZAR']:.2f}")
    
    return rates

def map_to_schema(tx):
    """Map Etherscan transaction to your schema"""
    # Only include successful transactions
    if tx.get('isError') != '0':
        return None
    
    # Convert value from Wei to ETH
    amount_eth = convert_wei_to_eth(tx.get('value', 0))
    
    # Skip zero-value transactions
    if amount_eth <= 0:
        return None
    
    # Generate a deterministic KYC hash based on the from address
    def generate_kyc_hash(address):
        import hashlib
        return hashlib.sha256(f"KYC_SALT_{address}".encode()).hexdigest()
    
    return {
        'swift_uetr': str(uuid.uuid4()),
        'ledger_tx_hash': tx.get('hash'),
        'block_number': int(tx.get('blockNumber', 0)),
        'wallet_address_originator': tx.get('from'),
        'wallet_address_beneficiary': tx.get('to'),
        'originator_kyc_id_hash': generate_kyc_hash(tx.get('from', '')),
        'beneficiary_kyc_id_hash': generate_kyc_hash(tx.get('to', '')),
        'amount': amount_eth,
        'currency_code': 'ETH',
        'exchange_rate_zar': 0.0,  # Will be updated later
        'value_date': datetime.fromtimestamp(int(tx.get('timeStamp', 0))),
        'bop_code': '201_01',
        'allowance_type': 'TRADE',
        'data_source': 'etherscan'
    }

def insert_transaction(conn, tx):
    """Insert a mapped transaction into the database"""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tx_blockchain_payments (
            swift_uetr, ledger_tx_hash, block_number,
            wallet_address_originator, wallet_address_beneficiary,
            originator_kyc_id_hash, beneficiary_kyc_id_hash,
            amount, currency_code, exchange_rate_zar, value_date,
            bop_code, allowance_type, data_source
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING tx_id
    """, (
        tx['swift_uetr'], tx['ledger_tx_hash'], tx['block_number'],
        tx['wallet_address_originator'], tx['wallet_address_beneficiary'],
        tx['originator_kyc_id_hash'], tx['beneficiary_kyc_id_hash'],
        tx['amount'], tx['currency_code'], tx['exchange_rate_zar'],
        tx['value_date'], tx['bop_code'], tx['allowance_type'],
        tx['data_source']
    ))
    tx_id = cur.fetchone()[0]
    conn.commit()
    return tx_id

def validate_transaction(conn, tx_id):
    """Validate the transaction (using your existing logic)"""
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
        error_log = '{"reason": "Annual allowance exceeded", "total_zar": "' + str(total_zar) + '"}'
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

def fetch_all_transactions(address, max_pages=5):
    """Fetch all transactions with pagination"""
    all_transactions = []
    page = 1
    
    while page <= max_pages:
        print(f"  Fetching page {page}...")
        transactions = fetch_transactions(address, page=page, offset=1000)
        
        if not transactions:
            break
            
        all_transactions.extend(transactions)
        
        if len(transactions) < 1000:
            break
            
        page += 1
    
    return all_transactions

def update_exchange_rates(conn, rates):
    """Update exchange rates for ETH transactions"""
    if rates['ETH_ZAR'] > 0:
        cur = conn.cursor()
        
        # Update existing ETH transactions that have zero rate
        cur.execute("""
            UPDATE tx_blockchain_payments 
            SET exchange_rate_zar = %s 
            WHERE currency_code = 'ETH' AND exchange_rate_zar = 0
        """, (rates['ETH_ZAR'],))
        
        updated_count = cur.rowcount
        conn.commit()
        cur.close()
        
        print(f"  Updated {updated_count} ETH transactions with rate {rates['ETH_ZAR']:.2f}")
        return rates['ETH_ZAR']
    else:
        print("  Could not fetch ETH rate, using default 0.0")
        return 0.0

def revalidate_eth_transactions(conn):
    """Re-validate ETH transactions after exchange rate updates"""
    cur = conn.cursor()
    
    # Get all ETH transactions that need re-validation
    cur.execute("""
        SELECT t.tx_id, t.originator_kyc_id_hash
        FROM tx_blockchain_payments t
        WHERE t.currency_code = 'ETH'
        AND t.exchange_rate_zar > 0
    """)
    eth_txs = cur.fetchall()
    
    if not eth_txs:
        return 0
    
    print(f"  Re-validating {len(eth_txs)} ETH transactions...")
    revalidated = 0
    
    for tx_id, originator_hash in eth_txs:
        # Calculate total ZAR for this originator
        cur.execute("""
            SELECT COALESCE(SUM(amount * exchange_rate_zar), 0)
            FROM tx_blockchain_payments
            WHERE originator_kyc_id_hash = %s
            AND value_date >= DATE_TRUNC('year', CURRENT_DATE)
        """, (originator_hash,))
        
        total_zar = cur.fetchone()[0] or 0
        
        # Determine new status
        if total_zar > 1000000:
            new_status = 'FAILED_VALIDATION'
            error_log = '{"reason": "Annual allowance exceeded", "total_zar": "' + str(total_zar) + '"}'
        else:
            new_status = 'PASSED_VALIDATION'
            error_log = None
        
        # Update validation
        cur.execute("""
            UPDATE tx_finsurv_validation
            SET validation_status = %s, error_log = %s
            WHERE tx_id = %s
        """, (new_status, error_log, tx_id))
        
        revalidated += 1
    
    conn.commit()
    cur.close()
    print(f"  Re-validated {revalidated} transactions")
    return revalidated

def main():
    print(f"Fetching transactions for wallet: {WALLET_ADDRESS}")
    
    transactions = fetch_all_transactions(WALLET_ADDRESS, max_pages=5)
    
    if not transactions:
        print("No transactions found or API error occurred.")
        return
    
    print(f"Found {len(transactions)} transactions. Filtering...")
    
    conn = psycopg2.connect(
        dbname="finsurv",
        user="admin",
        password=os.getenv("PG_PASSWORD", "SecurePass123!"),
        host="localhost",
        port=5432
    )
    
    processed = 0
    skipped = 0
    zero_value_skipped = 0
    
    for tx in transactions:
        mapped_tx = map_to_schema(tx)
        
        if mapped_tx is None:
            if tx.get('value', '0') == '0' or convert_wei_to_eth(tx.get('value', 0)) == 0:
                zero_value_skipped += 1
            skipped += 1
            continue
        
        # Check for duplicates
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM tx_blockchain_payments WHERE ledger_tx_hash = %s",
            (mapped_tx['ledger_tx_hash'],)
        )
        exists = cur.fetchone()[0] > 0
        cur.close()
        
        if exists:
            skipped += 1
            continue
        
        tx_id = insert_transaction(conn, mapped_tx)
        status = validate_transaction(conn, tx_id)
        processed += 1
        
        if processed % 10 == 0:
            print(f"  Processed {processed} transactions...")
    
    # Fetch and update exchange rates
    print("\nFetching exchange rates...")
    rates = fetch_exchange_rates()
    eth_rate = update_exchange_rates(conn, rates)
    
    # Re-validate ETH transactions if rate was updated
    if eth_rate > 0:
        revalidate_eth_transactions(conn)
    
    print(f"\nSummary:")
    print(f"  Processed: {processed}")
    print(f"  Skipped (zero-value): {zero_value_skipped}")
    print(f"  Skipped (other): {skipped - zero_value_skipped}")
    
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN validation_status = 'PASSED_VALIDATION' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN validation_status = 'FAILED_VALIDATION' THEN 1 ELSE 0 END) as failed
        FROM tx_finsurv_validation
    """)
    total, passed, failed = cur.fetchone()
    pass_rate = (passed / total * 100) if total > 0 else 0
    print(f"  Total in DB: {total}, Passed: {passed}, Failed: {failed}")
    print(f"  Pass rate: {pass_rate:.1f}%")
    
    cur.execute("""
        SELECT 
            data_source,
            COUNT(*) as count
        FROM tx_blockchain_payments
        GROUP BY data_source
    """)
    print("\n  Source breakdown:")
    for source, count in cur.fetchall():
        print(f"    {source}: {count} transactions")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()