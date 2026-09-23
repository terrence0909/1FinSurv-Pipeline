-- =========================================================================
-- 1. REFERENCE TABLES (Lookups)
-- =========================================================================

-- ISO 4217 Currency Codes
CREATE TABLE ref_currency_codes (
    currency_code CHAR(3) PRIMARY KEY,
    currency_name VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

-- SARB FinSurv Balance of Payments (BOP) Category Codes
CREATE TABLE ref_bop_codes (
    bop_code VARCHAR(10) PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    category_group VARCHAR(100) NOT NULL
);

-- FinSurv Validation Status Enum/Lookup
CREATE TABLE ref_validation_statuses (
    status_code VARCHAR(20) PRIMARY KEY,
    description VARCHAR(100) NOT NULL
);

-- =========================================================================
-- 2. CORE TRANSACTION TABLE (SWIFT Blockchain Data & BOP Mapping)
-- =========================================================================
CREATE TABLE tx_blockchain_payments (
    tx_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- SWIFT Ledger Orchestration Metadata
    swift_uetr UUID UNIQUE NOT NULL,
    ledger_tx_hash VARCHAR(66) UNIQUE NOT NULL,
    block_number BIGINT NOT NULL,
    wallet_address_originator VARCHAR(42) NOT NULL,
    wallet_address_beneficiary VARCHAR(42) NOT NULL,
    
    -- Centralized KYC Pointer Hashes
    originator_kyc_id_hash VARCHAR(64) NOT NULL,
    beneficiary_kyc_id_hash VARCHAR(64) NOT NULL,
    
    -- Transactional Value Data
    amount NUMERIC(18, 4) NOT NULL,
    currency_code CHAR(3) NOT NULL REFERENCES ref_currency_codes(currency_code),
    exchange_rate_zar NUMERIC(12, 6) DEFAULT 1.000000,
    value_date TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- FinSurv / Regulatory Flags
    bop_code VARCHAR(10) NOT NULL REFERENCES ref_bop_codes(bop_code),
    allowance_type VARCHAR(20) NOT NULL,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 3. TRANSACTION VALIDATION & REPORTING LAYER
-- =========================================================================
CREATE TABLE tx_finsurv_validation (
    validation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tx_id UUID UNIQUE NOT NULL REFERENCES tx_blockchain_payments(tx_id) ON DELETE CASCADE,
    
    validation_status VARCHAR(20) NOT NULL REFERENCES ref_validation_statuses(status_code) DEFAULT 'PENDING',
    allowance_limit_checked BOOLEAN DEFAULT FALSE,
    cryptographic_proof_verified BOOLEAN DEFAULT FALSE,
    
    finsurv_submission_ref VARCHAR(50) UNIQUE,
    finsurv_submission_date TIMESTAMP WITH TIME ZONE,
    
    error_log JSONB,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================================
-- 4. PERFORMANCE & REPORTING INDEXES
-- =========================================================================
CREATE INDEX idx_tx_value_date ON tx_blockchain_payments(value_date);
CREATE INDEX idx_tx_bop_code ON tx_blockchain_payments(bop_code);
CREATE INDEX idx_validation_status ON tx_finsurv_validation(validation_status);

-- =========================================================================
-- 5. HIGH-UTILITY VIEW FOR 1FINSURV API PAYLOADS
-- =========================================================================
CREATE VIEW vw_finsurv_submission_payload AS
SELECT 
    t.swift_uetr AS transaction_reference,
    t.ledger_tx_hash AS blockchain_proof_hash,
    t.value_date AS settlement_timestamp,
    t.amount AS transaction_amount,
    t.currency_code AS transaction_currency,
    (t.amount * t.exchange_rate_zar) AS equivalent_zar_amount,
    t.originator_kyc_id_hash AS encrypted_sender_token,
    t.bop_code AS sarb_bop_code,
    b.description AS bop_description,
    t.allowance_type AS local_allowance_bucket,
    v.validation_status AS internal_status
FROM tx_blockchain_payments t
JOIN tx_finsurv_validation v ON t.tx_id = v.tx_id
JOIN ref_bop_codes b ON t.bop_code = b.bop_code;

-- =========================================================================
-- 6. SAMPLE SEED DATA
-- =========================================================================

-- Seed Currencies
INSERT INTO ref_currency_codes (currency_code, currency_name) VALUES 
('ZAR', 'South African Rand'),
('USD', 'United States Dollar'),
('EUR', 'Euro'),
('GBP', 'British Pound'),
('JPY', 'Japanese Yen');

-- Seed BOP Codes
INSERT INTO ref_bop_codes (bop_code, description, category_group) VALUES 
('101_01', 'Payment for imported goods - Advance payment', 'Outward - Trade'),
('101_02', 'Payment for imported goods - Open account', 'Outward - Trade'),
('511_01', 'Gift to a non-resident individual', 'Outward - Capital Transfers'),
('511_02', 'Alimony or maintenance payments', 'Outward - Capital Transfers'),
('201_01', 'Exports of goods - Payment received', 'Inward - Trade'),
('401_01', 'Dividend payments to non-residents', 'Outward - Income'),
('401_02', 'Interest payments to non-residents', 'Outward - Income'),
('301_01', 'Services - Professional services', 'Inward - Services'),
('601_01', 'Foreign direct investment - Inward', 'Inward - Capital'),
('601_02', 'Foreign direct investment - Outward', 'Outward - Capital');

-- Seed Validation Statuses
INSERT INTO ref_validation_statuses (status_code, description) VALUES 
('PENDING', 'Awaiting schema and allowance checks'),
('PASSED_VALIDATION', 'Passed technical checks, ready for 1FinSurv submission'),
('FAILED_VALIDATION', 'Failed compliance parameters or schema limits'),
('SUBMITTED', 'Successfully acknowledged by SARB FinSurv');

-- =========================================================================
-- 7. SAMPLE TRANSACTION (For Testing)
-- =========================================================================
INSERT INTO tx_blockchain_payments (
    swift_uetr, ledger_tx_hash, block_number, 
    wallet_address_originator, wallet_address_beneficiary,
    originator_kyc_id_hash, beneficiary_kyc_id_hash,
    amount, currency_code, exchange_rate_zar, value_date,
    bop_code, allowance_type
) VALUES (
    'a4b2c1d3-e4f5-6a7b-8c9d-0e1f2a3b4c5d', 
    '0x7f83b1a2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e',
    14820931,
    '0x95222290DD7278Aa3Ddd389Cc1E1d165CC4BAfe5',
    '0x281055afc982d96fab65b3a49cac8b878184cb16',
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'cbf29ce484222325175d2729a4b27a074127222521d8820127271c7271b12739',
    50000.00, 'USD', 18.450000, NOW(),
    '511_01', 'SDA'
);

-- Initialize its Companion Validation Entry
INSERT INTO tx_finsurv_validation (tx_id, validation_status, allowance_limit_checked, cryptographic_proof_verified)
VALUES (
    (SELECT tx_id FROM tx_blockchain_payments WHERE swift_uetr = 'a4b2c1d3-e4f5-6a7b-8c9d-0e1f2a3b4c5d'),
    'PASSED_VALIDATION',
    TRUE,
    TRUE
);