{{
    config(
        materialized='table',
        schema='gold',
        tags=['marts', 'finsurv', 'compliance']
    )
}}

/*
    Fact model: fct_compliance_events
    Grain: one row per transaction
    Purpose: Adds cumulative ADA tracking per originator, and a breach flag
             that downstream models and dashboards can filter on.

    Source: stg_finsurv_transactions (staging view on silver)
    Rules: R1,000,000 Annual Discretionary Allowance per originator per
           calendar year (sum of amount_zar).
*/

WITH transactions AS (
    SELECT
        swift_uetr,
        ledger_tx_hash,
        originator_kyc_id_hash,
        amount_zar,
        currency_code,
        value_date,
        calendar_year,
        bop_code,
        allowance_type,
        data_source,
        dbt_loaded_at
    FROM {{ ref('stg_finsurv_transactions') }}
),

-- Cumulative YTD total per originator, in chronological order
cumulative AS (
    SELECT
        swift_uetr,
        ledger_tx_hash,
        originator_kyc_id_hash,
        amount_zar,
        currency_code,
        value_date,
        calendar_year,
        bop_code,
        allowance_type,
        data_source,
        dbt_loaded_at,

        SUM(amount_zar) OVER (
            PARTITION BY originator_kyc_id_hash, calendar_year
            ORDER BY value_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS ytd_transfer_zar,

        ROW_NUMBER() OVER (
            PARTITION BY originator_kyc_id_hash, calendar_year
            ORDER BY value_date
        ) AS tx_sequence_ytd

    FROM transactions
)

SELECT
    swift_uetr,
    ledger_tx_hash,
    originator_kyc_id_hash,
    amount_zar,
    currency_code,
    value_date,
    calendar_year,
    bop_code,
    allowance_type,
    data_source,
    dbt_loaded_at,
    ytd_transfer_zar,
    tx_sequence_ytd,

    -- Breach flag: over R1M YTD
    CASE
        WHEN ytd_transfer_zar > 1000000 THEN TRUE
        ELSE FALSE
    END AS is_ada_breach

FROM cumulative