-- Supabase (PostgreSQL) schema for cardsense promotion data.
-- Run once against your Supabase project to create the tables.
-- Key difference from cardsense_schema.sql (SQLite):
--   requires_registration is BOOLEAN (not INTEGER 0/1)

CREATE TABLE IF NOT EXISTS extract_runs (
    run_id TEXT PRIMARY KEY,
    bank_code TEXT,
    source TEXT NOT NULL,
    extractor_version TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    cards_processed INTEGER DEFAULT 0,
    promotions_loaded INTEGER DEFAULT 0,
    failures INTEGER DEFAULT 0,
    input_file TEXT,
    output_file TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS promotion_versions (
    promo_version_id TEXT PRIMARY KEY,
    promo_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    bank_code TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    card_code TEXT NOT NULL,
    card_name TEXT NOT NULL,
    card_status TEXT,
    annual_fee INTEGER,
    apply_url TEXT,
    category TEXT NOT NULL,
    channel TEXT,
    cashback_type TEXT NOT NULL,
    cashback_value NUMERIC NOT NULL,
    min_amount INTEGER DEFAULT 0,
    max_cashback INTEGER,
    frequency_limit TEXT,
    requires_registration BOOLEAN NOT NULL DEFAULT FALSE,
    recommendation_scope TEXT NOT NULL DEFAULT 'RECOMMENDABLE',
    eligibility_type TEXT NOT NULL DEFAULT 'GENERAL',
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    conditions_json TEXT NOT NULL,
    excluded_conditions_json TEXT NOT NULL,
    source_url TEXT NOT NULL,
    raw_text_hash TEXT NOT NULL,
    summary TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    plan_id TEXT,
    run_id TEXT REFERENCES extract_runs(run_id),
    raw_payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pv_promo_id ON promotion_versions (promo_id);
CREATE INDEX IF NOT EXISTS idx_pv_bank_card ON promotion_versions (bank_code, card_code);
CREATE INDEX IF NOT EXISTS idx_pv_valid_until ON promotion_versions (valid_until);

CREATE TABLE IF NOT EXISTS promotion_current (
    promo_id TEXT PRIMARY KEY,
    promo_version_id TEXT NOT NULL REFERENCES promotion_versions(promo_version_id),
    title TEXT NOT NULL DEFAULT '',
    bank_code TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    card_code TEXT NOT NULL,
    card_name TEXT NOT NULL,
    card_status TEXT,
    annual_fee INTEGER,
    apply_url TEXT,
    category TEXT NOT NULL,
    channel TEXT,
    cashback_type TEXT NOT NULL,
    cashback_value NUMERIC NOT NULL,
    min_amount INTEGER DEFAULT 0,
    max_cashback INTEGER,
    frequency_limit TEXT,
    requires_registration BOOLEAN NOT NULL DEFAULT FALSE,
    recommendation_scope TEXT NOT NULL DEFAULT 'RECOMMENDABLE',
    eligibility_type TEXT NOT NULL DEFAULT 'GENERAL',
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    conditions_json TEXT NOT NULL,
    excluded_conditions_json TEXT NOT NULL,
    source_url TEXT NOT NULL,
    raw_text_hash TEXT NOT NULL,
    summary TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    plan_id TEXT,
    run_id TEXT REFERENCES extract_runs(run_id),
    raw_payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pc_bank_category ON promotion_current (bank_code, category);
CREATE INDEX IF NOT EXISTS idx_pc_status_dates ON promotion_current (status, valid_from, valid_until);
