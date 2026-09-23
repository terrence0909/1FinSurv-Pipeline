# FinSurv v1 — Current State

This document describes the **v1 pipeline** preserved in `legacy/`. It is the baseline that v2 evolves from. Everything in this document is verified against the working code and the live database (646 transactions as of last query).

---

## What v1 is

A cross-border payment compliance pipeline that ingests transaction data from **two sources**, validates each transaction against SARB Financial Surveillance (FinSurv) rules, and exposes submission-ready records through a governed view.

The domain model is **SWIFT-shaped** — transactions carry `swift_uetr` references, BOP codes, allowance types, and settlement dates. This is the schema that SA banks use for FinSurv reporting.

The **second data source is Ethereum** — real on-chain transactions fetched from the Etherscan API, mapped into the same SWIFT-shaped schema. Wallet addresses are hashed into pseudonymous KYC identifiers (`SHA-256(SALT + address)`), so blockchain transactions can flow through the same compliance gate as traditional payments.

---

## Data sources (verified)

| Source | Data origin | Count | Currency |
|---|---|---|---|
| `mock` | `generate_transactions.py` — synthetic SWIFT-style messages | 459 | ZAR, USD, EUR, GBP, JPY |
| `etherscan` | Etherscan API — Ethereum Foundation wallet `0xde0B...` | 187 | ETH |

**Total: 646 transactions.**

The dual-source design proves the schema can absorb a foreign data model (blockchain) without changing the compliance logic.

---

## Schema (PostgreSQL 15)

### Reference tables
- `ref_currency_codes` — ISO 4217 currencies (ZAR, USD, EUR, GBP, JPY)
- `ref_bop_codes` — 10 SARB Balance of Payments category codes across Trade, Capital Transfers, Income, Services
- `ref_validation_statuses` — PENDING, PASSED_VALIDATION, FAILED_VALIDATION, SUBMITTED

### Core tables
- **`tx_blockchain_payments`** — the transaction ledger
  - `tx_id` (PK, UUID), `swift_uetr` (UNIQUE), `ledger_tx_hash` (UNIQUE), `block_number`
  - `wallet_address_originator`, `wallet_address_beneficiary`
  - `originator_kyc_id_hash`, `beneficiary_kyc_id_hash` (SHA-256)
  - `amount`, `currency_code`, `exchange_rate_zar`, `value_date`
  - `bop_code`, `allowance_type`, `data_source`, `created_at`

- **`tx_finsurv_validation`** — validation results
  - `validation_id` (PK), `tx_id` (FK, UNIQUE)
  - `validation_status`, `allowance_limit_checked`, `cryptographic_proof_verified`
  - `finsurv_submission_ref`, `finsurv_submission_date`
  - `error_log` (JSONB), `updated_at`

### View
- **`vw_finsurv_submission_payload`** — the API-ready projection
  - Joins transactions + validation + BOP codes
  - Exposes: `transaction_reference`, `blockchain_proof_hash`, `settlement_timestamp`, `transaction_amount`, `transaction_currency`, `equivalent_zar_amount`, `encrypted_sender_token`, `sarb_bop_code`, `bop_description`, `local_allowance_bucket`, `internal_status`

---

## Compliance rule (v1)

**Annual Discretionary Allowance (ADA):** R1,000,000 per originator per calendar year, summed as `SUM(amount * exchange_rate_zar)` where `value_date >= DATE_TRUNC('year', CURRENT_DATE)`.

Applied per unique `originator_kyc_id_hash`. Transactions that push an originator over R1M YTD are marked `FAILED_VALIDATION` and the reason is logged as JSONB in `error_log`.

**Current results (verified):**
- 511 `PASSED_VALIDATION` (79.1%)
- 135 `FAILED_VALIDATION` (20.9%)

---

## Orchestration

- **Apache Airflow** DAG (`dags/finsurv_pipeline.py`) runs daily
- Tasks: fetch Etherscan data → generate mock data → update exchange rates → revalidate ETH transactions → cleanup zero-value transactions
- Postgres runs in Docker (`docker-compose.yml`)
- **Streamlit** dashboard (`dashboard_app.py`) shows pass rates, breach patterns, currency exposure

---

## Supporting scripts

| Script | Purpose |
|---|---|
| `fetch_etherscan_data.py` | Fetches real Ethereum transactions, maps to schema, validates |
| `generate_transactions.py` | Generates 90 days of synthetic transactions with 15% breach rate |
| `update_exchange_rates.py` | Pulls live FX rates from exchangerate-api, updates ETH/mock rows |
| `data_quality.py` | 8-section quality report: nulls, duplicates, distribution, alerts |
| `cleanup_zero_transactions.py` | Removes zero-value transactions and their validation records |
| `query_transactions.py` | Reads from `vw_finsurv_submission_payload` |
| `test_db_connection.py` | Sanity check |

---

## Known limits (the reason v2 exists)

1. **Batch-only.** The Airflow DAG runs daily. A breach at 10:00 won't be caught until 23:00.
2. **No quarantine.** Failed records are flagged in `tx_finsurv_validation` but not extracted to a separate, traceable table.
3. **PostgreSQL-only storage.** No lakehouse, no time travel, no schema-on-read.
4. **No transformation framework.** Logic lives in Python scripts, not version-controlled SQL (dbt).
5. **No streaming.** Etherscan polling is batch. No Event Hubs / Kafka.

These are the gaps v2 closes.