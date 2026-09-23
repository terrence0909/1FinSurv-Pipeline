# Ethics and Scope

This project is a **demonstration**. It uses real data, real APIs, and real regulatory concepts, but it is not a production compliance system. This document explains the boundaries.

---

## What this project is

- A **technical demonstration** of how a cross-border payment compliance pipeline can be built on modern cloud infrastructure
- A **learning project** exploring Azure Databricks, Delta Lake, dbt, Event Hubs, and Terraform
- A **portfolio piece** illustrating end-to-end data engineering on a regulated domain

## What this project is NOT

- **Not** a claim that SARB recognizes cryptocurrency as a legitimate cross-border payment rail
- **Not** a production system that any bank should use for actual FinSurv reporting
- **Not** a source of financial or legal advice
- **Not** affiliated with, endorsed by, or connected to the South African Reserve Bank

---

## Specific disclaimers

### On the compliance rules

The R1,000,000 Annual Discretionary Allowance and BOP category codes referenced in this project are based on publicly available SARB Exchange Control documentation. **Production deployments must be reviewed against the current SARB Exchange Control Manual**, which changes periodically.

### On the KYC hashing

Wallet addresses are hashed using `SHA-256(SALT + address)`. This is **sufficient for a demonstration**, but **not production-grade**. A real system would use:
- A **keyed HMAC** (not plain SHA-256)
- With a key stored in a **hardware security module (HSM)** or Azure Key Vault
- With **rotation policies** and **audit logging** on every hash

Using `SHA-256(SALT + address)` in production would make the pseudonyms vulnerable to dictionary attacks, since wallet addresses are public on the blockchain.

### On the Etherscan integration

Transactions are fetched from the **publicly visible Ethereum Foundation wallet** `0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe`. This is a well-known public address, used here for demonstration. No private keys are handled. No transactions are initiated.

### On the mock data

The `generate_transactions.py` script produces **synthetic transactions**. Bank names (HSBC, UBS, Citi, BNP, Wells Fargo) appear as wallet labels for realism but do not imply any real transaction or relationship with those institutions.

---

## Data handling

- Real on-chain data (Ethereum) is **public by nature**. No privacy concern.
- Mock data is **fully synthetic**. No real customer data.
- No PII is stored. Wallet addresses are hashed. Names appear only as schema fields, never populated with real names.
- API keys (`ETHERSCAN_API_KEY`, `PG_PASSWORD`) are stored in `.env`, never committed.

---

## Responsible use

If you fork this repo:

1. **Do not** use it for actual FinSurv reporting without a full compliance review by qualified professionals.
2. **Do not** replace the demo KYC hashing with production HMAC without also implementing key management.
3. **Do not** assume the schema is sufficient for your jurisdiction's regulatory requirements.
4. **Do** read the SARB Exchange Control Manual before assuming any behavior of the pipeline is correct.

---

## Attribution

- **SARB FinSurv** — South African Reserve Bank Financial Surveillance department (public documentation)
- **Etherscan** — Ethereum block explorer API
- **Ethereum Foundation** — wallet address used for demonstration
- **SARB Exchange Control Manual** — the authoritative source for compliance rules

---

## Contact

This is a personal portfolio project. Questions and corrections welcome via GitHub Issues.