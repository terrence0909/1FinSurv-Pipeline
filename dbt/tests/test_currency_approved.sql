/*
    Assertion: Every transaction_currency is either SARB-approved or ETH
               (ETH is tracked but not SARB-approved — a known exception)
    Fails if: any submission row uses a currency not in dim_currency
              OR a currency that is neither approved nor ETH
*/

SELECT
    p.transaction_reference,
    p.transaction_currency,
    c.is_sarb_approved
FROM {{ ref('finsurv_submission_payload') }} p
LEFT JOIN {{ ref('dim_currency') }} c
    ON p.transaction_currency = c.currency_code
WHERE c.currency_code IS NULL
   OR (c.is_sarb_approved = FALSE AND p.transaction_currency != 'ETH')