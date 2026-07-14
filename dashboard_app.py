import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime
import time

load_dotenv()

# Page config
st.set_page_config(
    page_title="SARB FinSurv Compliance Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("SARB FinSurv Compliance Dashboard")
st.markdown("Real-time blockchain payment monitoring for regulatory reporting")

# Database connection
@st.cache_resource
def get_connection():
    try:
        conn = psycopg2.connect(
            dbname="finsurv",
            user="admin",
            password=os.getenv("PG_PASSWORD", "SecurePass123!"),
            host="localhost",
            port=5432
        )
        return conn
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None

def load_data(query):
    conn = get_connection()
    if conn is None:
        return pd.DataFrame()
    
    try:
        if conn.closed:
            conn = psycopg2.connect(
                dbname="finsurv",
                user="admin",
                password=os.getenv("PG_PASSWORD", "SecurePass123!"),
                host="localhost",
                port=5432
            )
            st.cache_resource.clear()
            get_connection()
        
        df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        st.error(f"Query failed: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=30)
def load_dashboard_data():
    stats_query = """
        SELECT 
            COUNT(*) as total_transactions,
            SUM(CASE WHEN validation_status = 'PASSED_VALIDATION' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN validation_status = 'FAILED_VALIDATION' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN validation_status = 'SUBMITTED' THEN 1 ELSE 0 END) as submitted
        FROM tx_finsurv_validation
    """
    stats = load_data(stats_query)
    
    daily_query = """
        SELECT 
            DATE(value_date) as date,
            COUNT(*) as transactions,
            SUM(amount * exchange_rate_zar) as total_zar
        FROM tx_blockchain_payments
        WHERE value_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY DATE(value_date)
        ORDER BY date
    """
    daily = load_data(daily_query)
    
    bop_query = """
        SELECT 
            b.category_group,
            COUNT(*) as count,
            SUM(t.amount * t.exchange_rate_zar) as total_zar
        FROM tx_blockchain_payments t
        JOIN ref_bop_codes b ON t.bop_code = b.bop_code
        GROUP BY b.category_group
        ORDER BY total_zar DESC
    """
    bop = load_data(bop_query)
    
    recent_query = """
        SELECT 
            t.swift_uetr,
            t.amount,
            t.currency_code,
            t.bop_code,
            v.validation_status,
            t.value_date
        FROM tx_blockchain_payments t
        JOIN tx_finsurv_validation v ON t.tx_id = v.tx_id
        ORDER BY t.value_date DESC
        LIMIT 20
    """
    recent = load_data(recent_query)
    
    return stats, daily, bop, recent

# Sidebar controls
st.sidebar.header("Dashboard Controls")
auto_refresh = st.sidebar.checkbox("Auto-refresh every 30 seconds", value=False)
refresh_button = st.sidebar.button("Refresh Now")

if auto_refresh:
    st.sidebar.info("Auto-refresh enabled - updates every 30s")
    time.sleep(1)
    st.rerun()

if refresh_button:
    st.cache_data.clear()
    st.rerun()

with st.spinner("Loading dashboard data..."):
    stats, daily, bop, recent = load_dashboard_data()

# KPI Cards
col1, col2, col3, col4 = st.columns(4)

with col1:
    total = stats['total_transactions'].iloc[0] if not stats.empty else 0
    st.metric("Total Transactions", total)

with col2:
    passed = stats['passed'].iloc[0] if not stats.empty else 0
    st.metric("Passed Validation", passed)

with col3:
    failed = stats['failed'].iloc[0] if not stats.empty else 0
    st.metric("Failed Validation", failed)

with col4:
    submitted = stats['submitted'].iloc[0] if not stats.empty else 0
    st.metric("Submitted to SARB", submitted)

# Charts
col1, col2 = st.columns(2)

with col1:
    st.subheader("Daily Transaction Volume")
    if not daily.empty and len(daily) > 0:
        fig = px.line(
            daily, 
            x='date', 
            y='transactions',
            title="Transactions per Day",
            markers=True
        )
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Number of Transactions"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data available for the last 30 days")

with col2:
    st.subheader("BOP Category Breakdown")
    if not bop.empty and len(bop) > 0:
        fig = px.pie(
            bop,
            values='total_zar',
            names='category_group',
            title="Flow by Category (ZAR)",
            hole=0.3
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No BOP category data available")

# Recent Transactions
st.subheader("Recent Transactions")
if not recent.empty and len(recent) > 0:
    def format_status(status):
        status_map = {
            'PASSED_VALIDATION': 'Passed',
            'FAILED_VALIDATION': 'Failed',
            'PENDING': 'Pending',
            'SUBMITTED': 'Submitted'
        }
        return status_map.get(status, status)
    
    def format_currency(amount, currency):
        if currency == 'ZAR':
            return f"R {amount:,.2f}"
        else:
            return f"{amount:,.2f} {currency}"
    
    recent['status_display'] = recent['validation_status'].apply(format_status)
    recent['amount_display'] = recent.apply(
        lambda row: format_currency(row['amount'], row['currency_code']), 
        axis=1
    )
    
    st.dataframe(
        recent[['swift_uetr', 'amount_display', 'bop_code', 'status_display', 'value_date']],
        column_config={
            'swift_uetr': 'Transaction Reference',
            'amount_display': 'Amount',
            'bop_code': 'BOP Code',
            'status_display': 'Status',
            'value_date': 'Date'
        },
        use_container_width=True
    )
    
    st.caption(f"Showing {len(recent)} most recent transactions")
else:
    st.info("No recent transactions found")

# Footer
st.markdown("---")
col1, col2 = st.columns(2)
with col1:
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
with col2:
    st.caption("Data source: SARB FinSurv PostgreSQL Pipeline")

if auto_refresh:
    st.caption("Auto-refreshing every 30 seconds...")