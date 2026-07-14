from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
import sys
sys.path.insert(0, '/opt/airflow/scripts')

def update_rates():
    from update_exchange_rates import update_exchange_rates
    update_exchange_rates()

default_args = {
    'owner': 'data_engineer',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'exchange_rate_updates',
    default_args=default_args,
    description='Update exchange rates daily',
    schedule_interval='0 6 * * *',  # Run daily at 6 AM
    catchup=False,
)

update_task = PythonOperator(
    task_id='update_exchange_rates',
    python_callable=update_rates,
    dag=dag,
)

run_quality_check = BashOperator(
    task_id='run_quality_checks',
    bash_command='python /opt/airflow/scripts/data_quality.py',
    dag=dag,
)

update_task >> run_quality_check