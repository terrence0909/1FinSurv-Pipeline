/*
    Assertion: Every bop_code in the submission payload exists in dim_bop_category
    Fails if: any submission row has a bop_code not covered by the dimension
*/

SELECT
    p.transaction_reference,
    p.sarb_bop_code
FROM {{ ref('finsurv_submission_payload') }} p
LEFT JOIN {{ ref('dim_bop_category') }} b
    ON p.sarb_bop_code = b.bop_code
WHERE b.bop_code IS NULL