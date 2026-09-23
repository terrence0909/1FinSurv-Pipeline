{{
    config(
        materialized='table',
        schema='gold',
        tags=['marts', 'finsurv', 'dimension']
    )
}}

/*
    Dimension: dim_currency
    Source: distinct currency_codes observed in Silver
    Purpose: reference for currency joins in downstream models
*/

WITH observed_currencies AS (
    SELECT DISTINCT currency_code
    FROM {{ ref('stg_finsurv_transactions') }}
    WHERE currency_code IS NOT NULL
)

SELECT
    currency_code,
    CASE currency_code
        WHEN 'ZAR' THEN 'South African Rand'
        WHEN 'USD' THEN 'United States Dollar'
        WHEN 'EUR' THEN 'Euro'
        WHEN 'GBP' THEN 'British Pound'
        WHEN 'JPY' THEN 'Japanese Yen'
        WHEN 'ETH' THEN 'Ethereum'
        ELSE 'Unknown'
    END AS currency_name,
    CASE
        WHEN currency_code IN ('ZAR', 'USD', 'EUR', 'GBP', 'JPY') THEN TRUE
        WHEN currency_code = 'ETH' THEN FALSE
        ELSE FALSE
    END AS is_sarb_approved
FROM observed_currencies