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

# Sidebar controls
st.sidebar.header("Dashboard Controls")

# Data source filter
data_source = st.sidebar.selectbox(
    "Data Source",
    ["All", "Mock Data", "Etherscan (Real)"],
    help="Filter transactions by source. All shows both mock and real data."
)

# Date range filter
days_filter = st.sidebar.selectbox(
    "Date Range",
    [30, 60, 90, 180, 365],
    index=4,
    help="Number of days of history to display"
)

auto_refresh = st.sidebar.checkbox("Auto-refresh every 30 seconds", value=False)
refresh_button = st.sidebar.button("Refresh Now")

if auto_refresh:
    st.sidebar.info("Auto-refresh enabled - updates every 30s")
    time.sleep(1)
    st.rerun()

if refresh_button:
    st.cache_data.clear()
    st.rerun()

@st.cache_data(ttl=30)
def load_dashboard_data(data_source_filter="All", days=365):
    # Build source filter
    source_filter = ""
    if data_source_filter == "Mock Data":
        source_filter = "AND t.data_source = 'mock'"
    elif data_source_filter == "Etherscan (Real)":
        source_filter = "AND t.data_source = 'etherscan'"
    
    # Stats query with source filter
    stats_query = f"""
        SELECT 
            COUNT(*) as total_transactions,
            SUM(CASE WHEN validation_status = 'PASSED_VALIDATION' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN validation_status = 'FAILED_VALIDATION' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN validation_status = 'SUBMITTED' THEN 1 ELSE 0 END) as submitted
        FROM tx_finsurv_validation v
        JOIN tx_blockchain_payments t ON v.tx_id = t.tx_id
        WHERE 1=1 {source_filter}
    """
    stats = load_data(stats_query)
    
    # Daily query with date range and source filter
    daily_query = f"""
        SELECT 
            DATE(value_date) as date,
            COUNT(*) as transactions,
            SUM(amount * exchange_rate_zar) as total_zar
        FROM tx_blockchain_payments t
        WHERE value_date >= CURRENT_DATE - INTERVAL '{days} days'
        {source_filter.replace('AND', 'AND') if source_filter else ''}
        GROUP BY DATE(value_date)
        ORDER BY date
    """
    daily = load_data(daily_query)
    
    # BOP query with source filter
    bop_query = f"""
        SELECT 
            b.category_group,
            COUNT(*) as count,
            SUM(t.amount * t.exchange_rate_zar) as total_zar
        FROM tx_blockchain_payments t
        JOIN ref_bop_codes b ON t.bop_code = b.bop_code
        WHERE 1=1 {source_filter}
        GROUP BY b.category_group
        ORDER BY total_zar DESC
    """
    bop = load_data(bop_query)
    
    # Recent transactions with source filter
    recent_query = f"""
        SELECT 
            t.swift_uetr,
            t.amount,
            t.currency_code,
            t.bop_code,
            v.validation_status,
            t.value_date,
            COALESCE(t.data_source, 'mock') as data_source
        FROM tx_blockchain_payments t
        JOIN tx_finsurv_validation v ON t.tx_id = v.tx_id
        WHERE 1=1 {source_filter}
        ORDER BY t.value_date DESC
        LIMIT 20
    """
    recent = load_data(recent_query)
    
    # Source breakdown (only for "All" view)
    source_breakdown = pd.DataFrame()
    if data_source_filter == "All":
        source_query = """
            SELECT 
                COALESCE(t.data_source, 'mock') as source,
                COUNT(*) as count
            FROM tx_blockchain_payments t
            GROUP BY COALESCE(t.data_source, 'mock')
        """
        source_breakdown = load_data(source_query)
    
    # Total by source
    source_totals_query = """
        SELECT 
            COALESCE(t.data_source, 'mock') as source,
            COUNT(*) as count,
            SUM(CASE WHEN v.validation_status = 'PASSED_VALIDATION' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN v.validation_status = 'FAILED_VALIDATION' THEN 1 ELSE 0 END) as failed
        FROM tx_blockchain_payments t
        JOIN tx_finsurv_validation v ON t.tx_id = v.tx_id
        GROUP BY COALESCE(t.data_source, 'mock')
    """
    source_totals = load_data(source_totals_query)
    
    return stats, daily, bop, recent, source_breakdown, source_totals

with st.spinner("Loading dashboard data..."):
    stats, daily, bop, recent, source_breakdown, source_totals = load_dashboard_data(data_source, days_filter)

# KPI Cards
col1, col2, col3, col4 = st.columns(4)

with col1:
    total = stats['total_transactions'].iloc[0] if not stats.empty else 0
    st.metric("Total Transactions", f"{total:,}")

with col2:
    passed = stats['passed'].iloc[0] if not stats.empty else 0
    pass_rate = (passed / total * 100) if total > 0 else 0
    st.metric("Passed Validation", f"{passed:,}", delta=f"{pass_rate:.1f}%")

with col3:
    failed = stats['failed'].iloc[0] if not stats.empty else 0
    st.metric("Failed Validation", f"{failed:,}")

with col4:
    submitted = stats['submitted'].iloc[0] if not stats.empty else 0
    st.metric("Submitted to SARB", f"{submitted:,}")

# Source breakdown (only for "All" view)
if data_source == "All" and not source_breakdown.empty:
    st.subheader("Data Source Breakdown")
    col1, col2 = st.columns([2, 1])
    with col1:
        fig = px.pie(
            source_breakdown,
            values='count',
            names='source',
            title="Transactions by Source",
            hole=0.3
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.write("")
        st.write("**Source Summary**")
        for _, row in source_breakdown.iterrows():
            source_label = "Etherscan (Real)" if row['source'] == 'etherscan' else "Mock Data"
            pct = (row['count'] / source_breakdown['count'].sum() * 100) if source_breakdown['count'].sum() > 0 else 0
            st.write(f"- **{source_label}**: {row['count']:,} transactions")
            st.write(f"  ({pct:.1f}%)")
        
        # Source quality breakdown
        if not source_totals.empty:
            st.write("")
            st.write("**Validation by Source**")
            for _, row in source_totals.iterrows():
                source_label = "Etherscan (Real)" if row['source'] == 'etherscan' else "Mock Data"
                passed_rate = (row['passed'] / row['count'] * 100) if row['count'] > 0 else 0
                st.write(f"- **{source_label}**: {passed_rate:.1f}% pass rate")

# Charts
col1, col2 = st.columns(2)

with col1:
    st.subheader("Daily Transaction Volume")
    if not daily.empty and len(daily) > 0:
        # Calculate rolling average for smoother view
        daily['rolling_avg'] = daily['transactions'].rolling(window=7, min_periods=1).mean()
        
        fig = px.line(
            daily, 
            x='date', 
            y=['transactions', 'rolling_avg'],
            title=f"Transactions per Day (Last {days_filter} days)",
            labels={'value': 'Transactions', 'variable': 'Metric'},
            color_discrete_map={'transactions': '#1f77b4', 'rolling_avg': '#ff7f0e'}
        )
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Number of Transactions",
            legend_title=""
        )
        fig.update_traces(
            hovertemplate='<b>%{x}</b><br>Transactions: %{y}<extra></extra>'
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"No data available for the last {days_filter} days")

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
        fig.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2))
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
        elif currency == 'ETH':
            return f"{amount:.4f} ETH"
        else:
            return f"{amount:,.2f} {currency}"
    
    def format_source(source):
        if source == 'etherscan':
            return 'Real'
        else:
            return 'Mock'
    
    recent['status_display'] = recent['validation_status'].apply(format_status)
    recent['amount_display'] = recent.apply(
        lambda row: format_currency(row['amount'], row['currency_code']), 
        axis=1
    )
    recent['source_display'] = recent['data_source'].apply(format_source)
    
    # Format date for display
    recent['date_display'] = recent['value_date'].dt.strftime('%Y-%m-%d %H:%M')
    
    # Add status color indicators
    def status_color(status):
        colors = {
            'Passed': 'green',
            'Failed': 'red',
            'Pending': 'orange',
            'Submitted': 'blue'
        }
        return colors.get(status, 'gray')
    
    recent['status_color'] = recent['status_display'].apply(status_color)
    
    display_cols = ['swift_uetr', 'amount_display', 'currency_code', 'bop_code', 'status_display', 'source_display', 'date_display']
    column_config = {
        'swift_uetr': 'Transaction Reference',
        'amount_display': 'Amount',
        'currency_code': 'Currency',
        'bop_code': 'BOP Code',
        'status_display': 'Status',
        'source_display': 'Source',
        'date_display': 'Date'
    }
    
    st.dataframe(
        recent[display_cols],
        column_config=column_config,
        use_container_width=True
    )
    
    # Summary stats for recent transactions
    col1, col2, col3 = st.columns(3)
    with col1:
        total_recent = len(recent)
        st.caption(f"Showing {total_recent} most recent transactions")
    with col2:
        recent_passed = len(recent[recent['validation_status'] == 'PASSED_VALIDATION'])
        st.caption(f"Recent pass rate: {(recent_passed/total_recent*100):.1f}%")
    with col3:
        real_count = len(recent[recent['data_source'] == 'etherscan'])
        st.caption(f"Real data in recent: {real_count} ({real_count/total_recent*100:.0f}%)")
else:
    st.info("No recent transactions found")

# Footer
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
with col2:
    st.caption(f"Total transactions: {total:,}")
with col3:
    st.caption("Data sources: Mock Generator | Etherscan V2 API")

if auto_refresh:
    st.caption("Auto-refreshing every 30 seconds...")