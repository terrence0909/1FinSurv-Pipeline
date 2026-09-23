/*
    Assertion: swift_uetr is unique in fct_compliance_events
    Fails if: any swift_uetr appears more than once
*/

SELECT
    swift_uetr,
    COUNT(*) AS occurrences
FROM {{ ref('fct_compliance_events') }}
GROUP BY swift_uetr
HAVING COUNT(*) > 1