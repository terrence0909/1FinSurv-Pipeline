{{
    config(
        materialized='table',
        schema='gold',
        tags=['marts', 'finsurv', 'submission']
    )
}}

/*
    Submission model: finsurv_submission_payload
    Purpose: The submission-ready projection for SARB FinSurv.
             Direct translation of v1's vw_finsurv_submission_payload.

    Grain: one row per validated transaction
    Joins: fct_compliance_events + dim_currency + dim_bop_category
*/

SELECT
    f.swift_uetr                        AS transaction_reference,
    f.ledger_tx_hash                    AS blockchain_proof_hash,
    f.value_date                        AS settlement_timestamp,
    f.amount_zar                        AS equivalent_zar_amount,
    f.currency_code                     AS transaction_currency,
    c.currency_name                     AS transaction_currency_name,
    c.is_sarb_approved                  AS currency_sarb_approved,
    f.originator_kyc_id_hash            AS encrypted_sender_token,
    f.bop_code                          AS sarb_bop_code,
    b.description                       AS bop_description,
    b.category_group                    AS bop_category_group,
    f.allowance_type                    AS local_allowance_bucket,
    f.ytd_transfer_zar                  AS cumulative_ytd_zar,
    f.is_ada_breach                     AS exceeds_ada_limit,
    CASE
        WHEN f.is_ada_breach THEN 'FAILED_VALIDATION'
        ELSE 'PASSED_VALIDATION'
    END                                 AS internal_status,
    f.data_source,
    f.dbt_loaded_at

FROM {{ ref('fct_compliance_events') }} f
LEFT JOIN {{ ref('dim_currency') }} c
    ON f.currency_code = c.currency_code
LEFT JOIN {{ ref('dim_bop_category') }} b
    ON f.bop_code = b.bop_code