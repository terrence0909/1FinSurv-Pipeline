# Databricks notebook source
# MAGIC %sql
# MAGIC CREATE CATALOG IF NOT EXISTS finsurv;
# MAGIC USE CATALOG finsurv;
# MAGIC
# MAGIC CREATE SCHEMA IF NOT EXISTS bronze;
# MAGIC CREATE SCHEMA IF NOT EXISTS silver;
# MAGIC CREATE SCHEMA IF NOT EXISTS gold;
# MAGIC CREATE SCHEMA IF NOT EXISTS quarantine;
# MAGIC
# MAGIC SHOW SCHEMAS;

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE finsurv.bronze.finsurv_raw (
# MAGIC   message_id STRING,
# MAGIC   ingested_at TIMESTAMP,
# MAGIC   data_source STRING,
# MAGIC   payload STRING
# MAGIC );
# MAGIC
# MAGIC INSERT INTO finsurv.bronze.finsurv_raw VALUES
# MAGIC   ('msg-001', current_timestamp(), 'mock', '{"swift_uetr":"a4b2c1d3-e4f5-6a7b-8c9d-0e1f2a3b4c5d","ledger_tx_hash":"0x7f83...","amount":50000.00,"currency_code":"USD","exchange_rate_zar":18.45,"value_date":"2026-09-01T10:00:00Z","bop_code":"511_01","allowance_type":"SDA","wallet_address_originator":"0x9522...","originator_kyc_id_hash":"e3b0c44298fc1c14..."}'),
# MAGIC   ('msg-002', current_timestamp(), 'etherscan', '{"swift_uetr":"b5c3d2e4-f5a6-7b8c-9d0e-1f2a3b4c5d6e","ledger_tx_hash":"0x8a4b...","amount":1.25,"currency_code":"ETH","exchange_rate_zar":65000.00,"value_date":"2026-09-15T14:30:00Z","bop_code":"201_01","allowance_type":"TRADE","wallet_address_originator":"0xde0B...","originator_kyc_id_hash":"cbf29ce484222325..."}');
# MAGIC
# MAGIC SELECT * FROM finsurv.bronze.finsurv_raw;
# MAGIC

# COMMAND ----------

from pyspark.sql.functions import from_json, col, expr
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType

# Define the schema
schema = StructType([
    StructField("swift_uetr", StringType()),
    StructField("ledger_tx_hash", StringType()),
    StructField("amount", DoubleType()),
    StructField("currency_code", StringType()),
    StructField("exchange_rate_zar", DoubleType()),
    StructField("value_date", TimestampType()),
    StructField("bop_code", StringType()),
    StructField("allowance_type", StringType()),
    StructField("wallet_address_originator", StringType()),
    StructField("originator_kyc_id_hash", StringType()),
])

# Read Bronze, parse JSON, compute amount_zar
silver_df = (
    spark.table("finsurv.bronze.finsurv_raw")
    .withColumn("parsed", from_json(col("payload"), schema))
    .select(
        "message_id",
        "data_source",
        "ingested_at",
        col("parsed.swift_uetr").alias("swift_uetr"),
        col("parsed.ledger_tx_hash").alias("ledger_tx_hash"),
        col("parsed.amount").alias("amount"),
        col("parsed.currency_code").alias("currency_code"),
        col("parsed.exchange_rate_zar").alias("exchange_rate_zar"),
        (col("parsed.amount") * col("parsed.exchange_rate_zar")).alias("amount_zar"),
        col("parsed.value_date").alias("value_date"),
        col("parsed.bop_code").alias("bop_code"),
        col("parsed.allowance_type").alias("allowance_type"),
        col("parsed.wallet_address_originator").alias("wallet_address_originator"),
        col("parsed.originator_kyc_id_hash").alias("originator_kyc_id_hash"),
    )
)

# Write to Silver
silver_df.write.mode("overwrite").saveAsTable("finsurv.silver.finsurv_validated")

# Display
display(spark.table("finsurv.silver.finsurv_validated"))

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   originator_kyc_id_hash,
# MAGIC   SUM(amount_zar) AS ytd_total_zar,
# MAGIC   CASE WHEN SUM(amount_zar) > 1000000 THEN 'FAILED_VALIDATION' ELSE 'PASSED_VALIDATION' END AS status
# MAGIC FROM finsurv.silver.finsurv_validated
# MAGIC WHERE YEAR(value_date) = YEAR(CURRENT_DATE())
# MAGIC GROUP BY originator_kyc_id_hash;