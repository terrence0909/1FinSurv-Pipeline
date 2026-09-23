/*
    Assertion: No originator exceeds R1,000,000 YTD without is_ada_breach = TRUE
    Fails if: any row has ytd_transfer_zar > 1000000 but is_ada_breach = FALSE
*/

SELECT
    swift_uetr,
    originator_kyc_id_hash,
    calendar_year,
    ytd_transfer_zar,
    is_ada_breach
FROM {{ ref('fct_compliance_events') }}
WHERE ytd_transfer_zar > 1000000
  AND is_ada_breach = FALSE