{{
    config(
        materialized='view',
        schema='silver',
        tags=['staging', 'finsurv']
    )
}}

/*
    Staging model: stg_finsurv_transactions
    Reads from finsurv.silver.finsurv_validated (produced by Spark/Silver layer)
    Renames columns to dbt conventions and adds metadata for downstream models.

    Source: finsurv.silver.finsurv_validated
    Grain: one row per validated transaction
*/

SELECT
    message_id,
    swift_uetr,
    ledger_tx_hash,
    amount,
    currency_code,
    exchange_rate_zar,
    amount_zar,
    value_date,
    YEAR(value_date)                    AS calendar_year,
    bop_code,
    allowance_type,
    wallet_address_originator,
    originator_kyc_id_hash,
    data_source,
    ingested_at                         AS bronze_ingested_at,
    CURRENT_TIMESTAMP()                 AS dbt_loaded_at

FROM {{ source('silver', 'finsurv_validated') }}