import os
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def update_exchange_rates():
    """Update exchange rates for all currencies"""
    try:
        # Fetch USD rates
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url)
        data = response.json()
        rates = data['rates']
        
        usd_zar = rates['ZAR']
        
        # Currency codes in your system
        currencies = {
            'ZAR': 1.0,
            'USD': 1.0,  # Base
            'EUR': rates['EUR'] / usd_zar,
            'GBP': rates['GBP'] / usd_zar,
            'JPY': rates['JPY'] / usd_zar,
            'ETH': rates.get('ETH', 0.0017) / usd_zar,
        }
        
        conn = psycopg2.connect(
            dbname="finsurv",
            user="admin",
            password=os.getenv("PG_PASSWORD", "SecurePass123!"),
            host="localhost",
            port=5432
        )
        cur = conn.cursor()
        
        for currency, rate in currencies.items():
            cur.execute("""
                UPDATE tx_blockchain_payments 
                SET exchange_rate_zar = %s 
                WHERE currency_code = %s AND data_source = 'mock'
            """, (rate * usd_zar, currency))
        
        conn.commit()
        
        print("Exchange rates updated successfully:")
        for currency, rate in currencies.items():
            print(f"  {currency}/ZAR: {rate * usd_zar:.4f}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Failed to update exchange rates: {e}")

if __name__ == "__main__":
    update_exchange_rates()