from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago
import os
import sys

# Add scripts directory to path
sys.path.insert(0, '/opt/airflow/scripts')

def run_transaction_generator():
    """Run the transaction generation script"""
    from generate_transactions import run_generation
    run_generation()

def run_dashboard_summary():
    """Run dashboard summary"""
    from dashboard import show_dashboard
    show_dashboard()

default_args = {
    'owner': 'data_engineer',
    'depends_on_past': False,
    'start_date': days_ago(1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'finsurv_compliance_pipeline',
    default_args=default_args,
    description='SARB FinSurv compliance pipeline',
    schedule_interval='*/15 * * * *',  # Run every 15 minutes
    catchup=False,
    tags=['compliance', 'sarb', 'blockchain'],
)

# Task 1: Generate new transactions
generate_task = PythonOperator(
    task_id='generate_transactions',
    python_callable=run_transaction_generator,
    dag=dag,
)

# Task 2: Run validation (part of generator script)

# Task 3: Check for failed validations
check_failures = BashOperator(
    task_id='check_failed_validations',
    bash_command='''docker exec finsurv_postgres psql -U admin -d finsurv -c "
        SELECT COUNT(*) FROM tx_finsurv_validation 
        WHERE validation_status = 'FAILED_VALIDATION' 
        AND updated_at > NOW() - INTERVAL '1 hour'
    " | grep -v "count" | grep -v "row"''',
    dag=dag,
)

# Task 4: Generate daily report
report_task = BashOperator(
    task_id='generate_daily_report',
    bash_command='''docker exec finsurv_postgres psql -U admin -d finsurv -c "
        SELECT 
            DATE(value_date) as date,
            COUNT(*) as total_tx,
            SUM(CASE WHEN validation_status = 'PASSED_VALIDATION' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN validation_status = 'FAILED_VALIDATION' THEN 1 ELSE 0 END) as failed,
            SUM(amount * exchange_rate_zar) as total_zar
        FROM tx_blockchain_payments t
        JOIN tx_finsurv_validation v ON t.tx_id = v.tx_id
        WHERE value_date >= CURRENT_DATE - INTERVAL '1 day'
        GROUP BY DATE(value_date)
        ORDER BY DATE(value_date) DESC
    "''',
    dag=dag,
)

# Define task dependencies
generate_task >> check_failures >> report_task