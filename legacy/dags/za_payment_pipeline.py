"""
ZA Payment Risk Pipeline — Airflow DAG.

Orchestrates the daily FinSurv reporting cycle:
  1. Validate bronze record count
  2. Run dbt models (staging → marts)
  3. Run dbt tests
  4. Generate FinSurv daily report
  5. Route SAR alerts

Schedule: Daily at 22:00 SAST (20:00 UTC) — ahead of the
SARB FinSurv 24-hour reporting deadline.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.trigger_rule import TriggerRule
import logging

logger = logging.getLogger(__name__)

DBT_DIR = "/Users/tshepotau/za-payment-risk-pipeline/dbt_project"

DEFAULT_ARGS = {
    "owner": "tshepo-tau",
    "depends_on_past": False,
    "start_date": datetime(2026, 9, 1),
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def check_bronze_record_count(**context):
    """Verify the seed/bronze layer has data before running transforms."""
    import os
    import duckdb

    db_path = "/Users/tshepotau/za-payment-risk-pipeline/data/za_payments.duckdb"

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DuckDB file not found at {db_path}")

    conn   = duckdb.connect(db_path, read_only=True)
    result = conn.execute("SELECT COUNT(*) FROM main_raw.sample_payments").fetchone()
    conn.close()

    count = result[0] if result else 0
    logger.info(f"Bronze record count: {count}")

    if count < 1:
        raise ValueError(f"No records found in bronze layer. Check the seed.")

    return count


def check_for_critical_alerts(**context):
    """Branch based on whether CRITICAL transactions exist."""
    import duckdb

    db_path = "/Users/tshepotau/za-payment-risk-pipeline/data/za_payments.duckdb"
    conn    = duckdb.connect(db_path, read_only=True)
    result  = conn.execute("""
        SELECT COUNT(*)
        FROM main.finsurvreport_daily
        WHERE risk_critical_count > 0
    """).fetchone()
    conn.close()

    critical_count = result[0] if result else 0
    logger.info(f"Critical transaction count: {critical_count}")

    return "handle_critical_alerts" if critical_count > 0 else "no_critical_alerts"


def generate_finsurvreport(**context):
    """Log the FinSurv daily report summary."""
    import duckdb
    import json

    db_path = "/Users/tshepotau/za-payment-risk-pipeline/data/za_payments.duckdb"
    conn    = duckdb.connect(db_path, read_only=True)
    rows    = conn.execute("""
        SELECT
            report_date,
            bank_code,
            total_transactions,
            compliance_pass_rate_pct,
            risk_critical_count,
            sar_required_count,
            total_volume_zar
        FROM main.finsurvreport_daily
        ORDER BY report_date DESC, total_volume_zar DESC
    """).fetchall()
    conn.close()

    report = {
        "report_date":  str(datetime.utcnow().date()),
        "generated_at": datetime.utcnow().isoformat(),
        "schema":       "FINSURVR_v2.1",
        "status":       "READY_FOR_SUBMISSION",
        "summary":      [
            {
                "bank_code":              r[1],
                "total_transactions":     r[2],
                "compliance_pass_rate":   f"{r[3]}%",
                "critical_count":         r[4],
                "sar_required":           r[5],
                "total_volume_zar":       f"R{r[6]:,.2f}",
            }
            for r in rows
        ],
    }

    logger.info("FinSurv Report Generated:")
    logger.info(json.dumps(report, indent=2))
    return report


with DAG(
    dag_id="za_payment_risk_pipeline",
    default_args=DEFAULT_ARGS,
    description="ZA Payment Risk — daily SARB FinSurv compliance pipeline",
    schedule_interval="0 20 * * *",
    catchup=False,
    tags=["za-payment-risk", "finsurvreport", "compliance", "dbt", "streaming"],
    max_active_runs=1,
) as dag:

    # ── Step 1: Validate bronze ────────────────────────────────────
    validate_bronze = PythonOperator(
        task_id="validate_bronze_record_count",
        python_callable=check_bronze_record_count,
    )

    # ── Step 2: dbt run ────────────────────────────────────────────
    dbt_run_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"cd {DBT_DIR} && dbt run --select staging --profiles-dir . --no-use-colors",
    )

    dbt_run_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=f"cd {DBT_DIR} && dbt run --select marts --profiles-dir . --no-use-colors",
    )

    # ── Step 3: dbt test ───────────────────────────────────────────
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_DIR} && dbt test --profiles-dir . --no-use-colors",
    )

    # ── Step 4: Generate report ────────────────────────────────────
    generate_report = PythonOperator(
        task_id="generate_finsurvreport",
        python_callable=generate_finsurvreport,
    )

    # ── Step 5: Branch on critical alerts ─────────────────────────
    check_alerts = BranchPythonOperator(
        task_id="check_for_critical_alerts",
        python_callable=check_for_critical_alerts,
    )

    handle_critical = BashOperator(
        task_id="handle_critical_alerts",
        bash_command="echo 'CRITICAL alerts detected — routing to SAR filing queue'",
    )

    no_critical = EmptyOperator(
        task_id="no_critical_alerts",
    )

    # ── Step 6: Done ───────────────────────────────────────────────
    pipeline_complete = EmptyOperator(
        task_id="pipeline_complete",
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )

    # ── Dependencies ───────────────────────────────────────────────
    validate_bronze >> dbt_run_staging >> dbt_run_marts >> dbt_test
    dbt_test >> generate_report >> check_alerts
    check_alerts >> [handle_critical, no_critical]
    [handle_critical, no_critical] >> pipeline_complete
