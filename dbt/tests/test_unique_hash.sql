/*
    Assertion: ledger_tx_hash is unique in fct_compliance_events
    Fails if: any ledger_tx_hash appears more than once
*/

SELECT
    ledger_tx_hash,
    COUNT(*) AS occurrences
FROM {{ ref('fct_compliance_events') }}
GROUP BY ledger_tx_hash
HAVING COUNT(*) > 1