{{
    config(
        materialized='table',
        schema='gold',
        tags=['marts', 'finsurv', 'dimension']
    )
}}

/*
    Dimension: dim_bop_category
    Source: distinct bop_codes observed in Silver + descriptions
    Purpose: reference for BOP joins in downstream models

    Note: In v2 with Azure, this would be sourced from a ref_bop_codes table
    that Spark maintains. For now, descriptions are hardcoded to match v1's
    ref_bop_codes seed data.
*/

WITH observed_bops AS (
    SELECT DISTINCT bop_code
    FROM {{ ref('stg_finsurv_transactions') }}
    WHERE bop_code IS NOT NULL
)

SELECT
    bop_code,
    CASE bop_code
        WHEN '101_01' THEN 'Payment for imported goods - Advance payment'
        WHEN '101_02' THEN 'Payment for imported goods - Open account'
        WHEN '511_01' THEN 'Gift to a non-resident individual'
        WHEN '511_02' THEN 'Alimony or maintenance payments'
        WHEN '201_01' THEN 'Exports of goods - Payment received'
        WHEN '401_01' THEN 'Dividend payments to non-residents'
        WHEN '401_02' THEN 'Interest payments to non-residents'
        WHEN '301_01' THEN 'Services - Professional services'
        WHEN '601_01' THEN 'Foreign direct investment - Inward'
        WHEN '601_02' THEN 'Foreign direct investment - Outward'
        ELSE 'Unknown BOP code'
    END AS description,
    CASE
        WHEN bop_code LIKE '1%' THEN 'Outward - Trade'
        WHEN bop_code LIKE '2%' THEN 'Inward - Trade'
        WHEN bop_code LIKE '3%' THEN 'Inward - Services'
        WHEN bop_code LIKE '4%' THEN 'Outward - Income'
        WHEN bop_code LIKE '5%' THEN 'Outward - Capital Transfers'
        WHEN bop_code LIKE '6%' THEN 'Capital'
        ELSE 'Unknown'
    END AS category_group
FROM observed_bops