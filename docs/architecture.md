# FinSurv Lakehouse — Architecture (v2)

This document defines the v2 data architecture on Azure. It is the evolution of v1 (see `docs/v1-current-state.md`). Same schema, same rules, same two data sources — new infrastructure.

---

## Design goals

1. **Preserve the SWIFT-shaped schema.** Don't break the domain model. `swift_uetr`, `ledger_tx_hash`, `originator_kyc_id_hash`, `bop_code`, `allowance_type` all stay.
2. **Add a real quarantine layer.** Failed records become first-class data, not just JSONB logs.
3. **Move from batch to streaming.** Event Hubs feeds Bronze in near-real-time.
4. **Move transformations into dbt.** Validation and reporting logic become version-controlled SQL.
5. **Preserve multi-source ingestion.** Mock and Etherscan both feed the same Bronze table.
6. **Run on Azure.** Databricks + ADLS Gen2 + Unity Catalog + Event Hubs. The stack SA banks use.
7. **Extend into AML signals.** Cross-border payments are a high-risk AML typology. The pipeline flags three AML patterns in addition to FinSurv rules: sanctions hits, structuring patterns, and velocity anomalies. These are additive to FinSurv validation, not a replacement for a full AML system.

---

## Regulatory context

Swift's blockchain-based ledger entered initial pilots in July 2026 for tokenised deposit settlement, with FirstRand Bank as the only South African bank in the first live cohort (Absa is in the broader consortium). SARB and National Treasury published draft cross-border crypto guidelines in August 2026, proposing that all offshore crypto payments route through authorised providers and be reported to FinSurv with limits aligned to the existing Single Discretionary Allowance (R2m) and Foreign Capital Allowance (R10m).

ISO 20022 became mandatory for cross-border payment instructions on 22 November 2025.

This project sits at the intersection of these three developments. Bronze ingests both ISO 20022-shaped messages and on-chain transactions; Silver validates both against the same Exchange Control rules; Gold serves a unified FinSurv submission payload. It is a demonstration of the compliance layer that SA banks piloting tokenised deposits will need.

---

## High-level architecture
┌──────────────────────┐ ┌──────────────────────┐
│ Mock Producer │ │ Etherscan Poller │
│ (Kafka protocol) │ │ (scheduled → EHub) │
└──────────┬───────────┘ └──────────┬───────────┘
│ │
└───────────┬───────────────┘
▼
┌─────────────────┐
│ Azure Event │
│ Hubs │
└────────┬────────┘
│ Spark Structured Streaming
▼
┌─────────────────────────────┐
│ Bronze: finsurv_raw │ append-only, schema-on-read
│ (Delta, ADLS Gen2) │
└────────┬────────────────────┘
│
▼
┌─────────────────────────────┐ ┌─────────────────────────────┐
│ Silver: finsurv_validated │───▶│ Quarantine: finsurv_qtn │
│ (Delta, validated) │ │ (failed + failure_rule) │
└────────┬────────────────────┘ └─────────────────────────────┘
│
▼
┌─────────────────────────────┐
│ Gold: dbt models │ stg_, fct_, dim_*, qtn_summary
│ (Delta, analytics-ready) │
└────────┬────────────────────┘
│
▼
┌─────────────────────────────┐
│ Databricks SQL Dashboard │
└─────────────────────────────┘

text

---

## Bronze: `finsurv_raw`

**Purpose:** Immutable append-only ingest of every message from Event Hubs. No transformation.

**Schema (Delta, ADLS Gen2):**

| Column | Type | Notes |
|---|---|---|
| `message_id` | STRING | UUID assigned at producer |
| `ingested_at` | TIMESTAMP | Spark `current_timestamp()` |
| `event_hub_partition` | INT | Event Hubs partition |
| `event_hub_offset` | LONG | For replay/ordering |
| `data_source` | STRING | `mock` or `etherscan` |
| `payload` | STRING | Raw JSON of the transaction |

**Why raw JSON:** Preserves v1's dual-source pattern. If Etherscan changes its response shape, Bronze still captures it. Parsing happens in Silver.

---

## Silver: `finsurv_validated`

**Purpose:** Clean, typed, validated, deduplicated transactions. **Same column names as v1.**

**Schema (Delta):**

| Column | Type | Source |
|---|---|---|
| `tx_id` | STRING | Generated (UUID) |
| `swift_uetr` | STRING | From payload — UNIQUE |
| `ledger_tx_hash` | STRING | From payload — UNIQUE |
| `block_number` | BIGINT | From payload |
| `wallet_address_originator` | STRING | From payload |
| `wallet_address_beneficiary` | STRING | From payload |
| `originator_kyc_id_hash` | STRING | SHA-256 of wallet |
| `beneficiary_kyc_id_hash` | STRING | SHA-256 of wallet |
| `amount` | DECIMAL(18,4) | From payload |
| `currency_code` | STRING | ISO 4217 |
| `exchange_rate_zar` | DECIMAL(12,6) | From payload |
| `amount_zar` | DECIMAL(18,2) | **Computed** = amount × exchange_rate_zar |
| `value_date` | TIMESTAMP | From payload |
| `bop_code` | STRING | FK to `ref_bop_codes` |
| `allowance_type` | STRING | SDA / FDA / TRADE |
| `data_source` | STRING | `mock` or `etherscan` |
| `validated_at` | TIMESTAMP | Spark `current_timestamp()` |
| `calendar_year` | INT | Extracted from `value_date` |

**Design decision:** `amount_zar` is computed at Silver instead of Gold because ADA is denominated in ZAR. One currency simplifies the cumulative check.

---

## Quarantine: `finsurv_quarantine`

**Purpose:** Every record that fails a validation rule lands here. Nothing is silently dropped. This is the layer v1 lacked.

**Schema (Delta):**

| Column | Type | Notes |
|---|---|---|
| `message_id` | STRING | FK back to Bronze |
| `swift_uetr` | STRING | From payload (may be null) |
| `failed_at` | TIMESTAMP | When validation failed |
| `failure_rule` | STRING | Enum: `ADA_LIMIT`, `BOP_INVALID`, `CURRENCY_INVALID`, `SCHEMA_MALFORMED`, `DUPLICATE_TX_HASH` |
| `failure_reason` | STRING | Human-readable explanation |
| `originator_kyc_id_hash` | STRING | Extracted if possible |
| `amount_zar` | DECIMAL(18,2) | Extracted if possible |
| `raw_payload` | STRING | Original JSON — preserved for audit |

**Design decision:** `failure_rule` is a controlled vocabulary. This lets you aggregate failures by rule type in Databricks SQL. `failure_reason` is for humans; `failure_rule` is for machines.

---

## Gold: dbt models

Executed as a Databricks Workflow task after Silver completes.

### Models

| Model | Type | Grain | Source |
|---|---|---|---|
| `stg_finsurv_transactions` | staging | one row per tx | `finsurv_validated` |
| `fct_compliance_events` | fact | one row per tx | `stg_finsurv_transactions` |
| `dim_currency` | dimension | currency code | `ref_currency_codes` |
| `dim_bop_category` | dimension | BOP code | `ref_bop_codes` |
| `quarantine_summary` | aggregate | date × failure_rule | `finsurv_quarantine` |

### The submission view

The v1 view `vw_finsurv_submission_payload` becomes a **dbt model** named `finsurv_submission_payload`. Same columns. Same joins. Now version-controlled and testable.

### dbt tests

| Test | Asserts |
|---|---|
| `test_ada_limit` | No originator exceeds R1M YTD without an `is_ada_breach` flag |
| `test_bop_codes` | Every `bop_code` in `fct_compliance_events` exists in `dim_bop_category` |
| `test_currency_approved` | Every currency is in `ref_currency_codes` |
| `test_unique_uetr` | `swift_uetr` is unique across Silver |
| `test_unique_hash` | `ledger_tx_hash` is unique across Silver |

---

## AML signal layer

Beyond FinSurv validation, the pipeline flags three AML patterns on the same Silver-layer transactions. These are not a full AML system — they are demonstrations of the patterns a bank's AML monitoring would look for.

### Rules

| Rule | `failure_rule` value | Trigger |
|---|---|---|
| Sanctions hit | `SANCTIONS_HIT` | Originator or beneficiary wallet on `ref_sanctioned_wallets` |
| Structuring | `STRUCTURING_PATTERN` | Multiple sub-threshold payments by same originator within 7 days |
| Velocity anomaly | `VELOCITY_ANOMALY` | Originator's 24h volume exceeds 5x their 30-day average |

### Reference tables

- `ref_sanctioned_wallets` — wallet addresses on OFAC, EU, UN, and FIC lists
- `ref_pep_entities` — politically exposed persons (future)

### Gold model

- `fct_aml_alerts` — one row per AML flag, joinable to `fct_compliance_events`

---

## v1 → v2 migration table

| Layer | v1 | v2 |
|---|---|---|
| Ingestion | Python scripts + Etherscan polling | Event Hubs (Kafka protocol) |
| Storage | PostgreSQL 15 (Docker) | ADLS Gen2 + Delta Lake |
| Processing | Airflow DAG + Python | Databricks + Spark Structured Streaming |
| Transformation | Python scripts | dbt-databricks |
| Validation | `tx_finsurv_validation` status | Silver + `finsurv_quarantine` |
| Orchestration | Airflow | Databricks Workflows |
| Serving | Streamlit | Databricks SQL Dashboard |
| IaC | docker-compose.yml | Terraform |
| CI | None | GitHub Actions |

---

## Design decisions worth discussing

- **Why keep SWIFT-shaped schema?** Because v1's schema was validated against 646 real transactions and 79% pass rate. Breaking it would mean re-validating the whole model.
- **Why quarantine instead of drop?** Regulatory data. Auditors need to see *why* a record failed, not just that it did.
- **Why Event Hubs and not Kafka?** Event Hubs has a Kafka-compatible endpoint. No cluster management. Native Azure integration with Databricks.
- **Why dbt and not Spark SQL?** Version control, tests-as-code, lineage graphs. For compliance work, "what changed and when" matters.
- **Why two sources in Bronze?** Because v1 proved multi-source ingestion works. Removing it would be a regression.

---

## Not in scope

- Actual submission to SARB FinSurv API (demonstration only — see `docs/ethics-and-scope.md`)
- Multi-bank federation
- AML / fraud detection (different domain from FinSurv reporting)
- ML anomaly detection (future)