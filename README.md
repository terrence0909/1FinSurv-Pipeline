# FinSurv Lakehouse — Real-Time Cross-Border Compliance on Azure

> A streaming lakehouse that ingests SARB FinSurv cross-border payment feeds, validates them against Exchange Control rules in real time, and produces audit-ready compliance data — built on Azure Databricks, Delta Lake, and dbt.

---

## Why this exists

South African banks must report every cross-border payment to the SARB Financial Surveillance (FinSurv) department **within 24 hours** of settlement. Missing the window, misclassifying a BOP code, or breaching the R1,000,000 Annual Discretionary Allowance carries regulatory consequences.

The original pipeline (see `legacy/`) proved the compliance logic works — 430 transactions, 79% pass rate, validated against ADA limits, BOP codes, and currency eligibility. But it had architectural limits:

- **Batch-only.** A daily Airflow DAG cannot alert on a breach that happens at 10:00 if the next run is at 23:00.
- **No quarantine.** Failed transactions were flagged but not traceable. Auditors could not see *why* a record failed.
- **No lakehouse.** PostgreSQL stored results, but there was no Bronze/Silver/Gold separation, no Delta Lake, no dbt.
- **No cloud-native stack.** No Event Hubs, no ADLS Gen2, no Unity Catalog.

This repository is the rebuild. Same domain. Same rules. Modern architecture.

---

## Architecture
┌─────────────────────┐
│ SWIFT Producer │ Simulates real-time cross-border payments
│ (Kafka protocol) │
└────────┬────────────┘
│
▼
┌─────────────────────┐
│ Azure Event Hubs │ Kafka-compatible streaming endpoint
└────────┬────────────┘
│
▼
┌─────────────────────┐
│ Bronze (Delta) │ Raw append-only ingest via Spark Structured Streaming
│ finsurv_raw │
└────────┬────────────┘
│
▼
┌─────────────────────┐ ┌─────────────────────┐
│ Silver (Delta) │ │ Quarantine (Delta) │
│ finsurv_validated │────▶│ failed_records │
│ │ │ + failure_reason │
└────────┬────────────┘ └─────────────────────┘
│
▼
┌─────────────────────┐
│ Gold (dbt models) │ fct_compliance_events, dim_currency, dim_bop
│ Analytics-ready │
└────────┬────────────┘
│
▼
┌─────────────────────┐
│ Databricks SQL │ Real-time compliance dashboard
└─────────────────────┘

text

---

## Compliance rules implemented

| Rule | Description | Enforcement |
|---|---|---|
| **Annual Discretionary Allowance (ADA)** | Individuals cannot transfer > R1,000,000 offshore per calendar year | Silver layer — cumulative check per sender |
| **BOP category validation** | Every transaction must carry a valid Balance of Payments code | Silver layer — schema + referential check |
| **Currency eligibility** | Only SARB-approved currencies accepted | Silver layer — lookup against approved list |

Records that fail any rule are routed to the **quarantine Delta table** with the specific failure reason, timestamp, and source message. Nothing is silently dropped.

---

## Tech stack

| Layer | v1 (Legacy) | v2 (Current) |
|---|---|---|
| Ingestion | Python script | Azure Event Hubs (Kafka protocol) |
| Storage | PostgreSQL 15 | Azure Data Lake Storage Gen2 (Delta Lake) |
| Processing | Python validation | Databricks + Spark Structured Streaming |
| Transformation | Python scripts | dbt-databricks |
| Orchestration | Apache Airflow | Databricks Workflows |
| Serving | Streamlit | Databricks SQL Dashboard |
| IaC | Docker Compose | Terraform |
| CI | None | GitHub Actions |

---

## Repository structure
.
├── legacy/ # v1 — Airflow + Postgres (preserved for comparison)
├── infra/
│ ├── terraform/ # Azure resources: Event Hubs, ADLS, Databricks, Unity Catalog
│ └── databricks/ # Cluster config, workflow definitions
├── src/
│ ├── producers/ # Kafka producer simulating SWIFT messages
│ ├── bronze/ # Event Hubs → Delta ingest
│ └── silver/ # Validation + quarantine routing
├── dbt/
│ ├── models/
│ │ ├── staging/ # stg_finsurv_transactions
│ │ ├── marts/ # fct_compliance_events, dim_currency, dim_bop_category
│ │ └── quarantine/ # quarantine_summary
│ └── tests/ # dbt tests for ADA limits, BOP codes
├── docs/
│ ├── architecture.md # Detailed medallion design
│ ├── azure_setup.md # Provisioning guide
│ └── migration_notes.md # What changed from v1 → v2 and why
└── .github/workflows/ # CI: lint, dbt parse, pytest

text

---

## Migration notes (v1 → v2)

**What stayed the same:**
- Domain logic: ADA limits, BOP codes, currency eligibility
- Business narrative: SARB 24-hour reporting window
- Data model concepts: transactions, senders, currencies, BOP categories

**What changed and why:**
- **Airflow → Databricks Workflows:** Native integration with Delta Lake and Unity Catalog, less orchestration glue.
- **Postgres → Delta Lake:** ACID transactions on the data lake, time travel for audits, schema evolution without migrations.
- **Python validation → dbt tests + quarantine layer:** Validation logic is version-controlled SQL, and failures are traceable rather than silent.
- **Batch DAG → Structured Streaming:** Real-time breach detection within the 24-hour window, not the next day.
- **Docker Compose → Terraform:** Reproducible Azure infrastructure as code.

---

## What I learned (to be filled in during build)

> _This section will be updated as the build progresses. Follow the commit history to see the journey._

---

## Roadmap

- [ ] Deploy Event Hubs + ADLS via Terraform
- [ ] Configure Unity Catalog external location for Bronze/Silver/Gold
- [ ] Run Spark Structured Streaming job end-to-end
- [ ] Deploy dbt models as Databricks Workflow
- [ ] Build Databricks SQL compliance dashboard
- [ ] Configure GitHub Actions CI

---

## Related work

- **Project ZAR** — broader banking compliance platform
- **ArtBurst** — serverless real-time auction platform (AWS)

---

## Note

This pipeline implements common FinSurv validation rules for demonstration. Production deployments must be reviewed against the current SARB Exchange Control Manual.