"""Tests for extractor/supabase_store.py — psycopg2 is mocked throughout."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, call, patch

import pytest

from extractor.supabase_store import SyncResult, sync_sqlite_to_supabase, validate_supabase_url


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sqlite_db():
    """Temporary SQLite DB with one row in each of the three tables."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE extract_runs (
            run_id TEXT PRIMARY KEY, bank_code TEXT, source TEXT NOT NULL,
            extractor_version TEXT, started_at TEXT NOT NULL, finished_at TEXT,
            status TEXT NOT NULL, cards_processed INTEGER DEFAULT 0,
            promotions_loaded INTEGER DEFAULT 0, failures INTEGER DEFAULT 0,
            input_file TEXT, output_file TEXT, notes TEXT
        );
        INSERT INTO extract_runs VALUES
            ('run1','TEST','test','1.0','2026-01-01T00:00:00',NULL,'SUCCESS',1,2,0,'in.jsonl',NULL,NULL);

        CREATE TABLE promotion_versions (
            promo_version_id TEXT PRIMARY KEY, promo_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '', bank_code TEXT NOT NULL,
            bank_name TEXT NOT NULL, card_code TEXT NOT NULL, card_name TEXT NOT NULL,
            card_status TEXT, annual_fee INTEGER, apply_url TEXT,
            category TEXT NOT NULL, channel TEXT, cashback_type TEXT NOT NULL,
            cashback_value NUMERIC NOT NULL, min_amount INTEGER DEFAULT 0,
            max_cashback INTEGER, frequency_limit TEXT,
            requires_registration INTEGER NOT NULL DEFAULT 0,
            recommendation_scope TEXT NOT NULL DEFAULT 'RECOMMENDABLE',
            eligibility_type TEXT NOT NULL DEFAULT 'GENERAL',
            valid_from TEXT NOT NULL, valid_until TEXT NOT NULL,
            conditions_json TEXT NOT NULL, excluded_conditions_json TEXT NOT NULL,
            source_url TEXT NOT NULL, raw_text_hash TEXT NOT NULL,
            summary TEXT NOT NULL, extractor_version TEXT NOT NULL,
            extracted_at TEXT NOT NULL, confidence REAL NOT NULL,
            status TEXT NOT NULL, run_id TEXT, raw_payload_json TEXT NOT NULL
        );
        INSERT INTO promotion_versions VALUES
            ('ver1','promo1','Test Promo','TEST','Test Bank','TEST_CARD','Test Card',
             'ACTIVE',0,NULL,'ONLINE',NULL,'PERCENT',3.0,0,NULL,NULL,
             1,'RECOMMENDABLE','GENERAL','2026-01-01','2026-12-31',
             '[]','[]','https://example.com','abc123','summary','1.0',
             '2026-01-01T00:00:00',0.9,'ACTIVE','run1','{}');

        CREATE TABLE promotion_current (
            promo_id TEXT PRIMARY KEY, promo_version_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '', bank_code TEXT NOT NULL,
            bank_name TEXT NOT NULL, card_code TEXT NOT NULL, card_name TEXT NOT NULL,
            card_status TEXT, annual_fee INTEGER, apply_url TEXT,
            category TEXT NOT NULL, channel TEXT, cashback_type TEXT NOT NULL,
            cashback_value NUMERIC NOT NULL, min_amount INTEGER DEFAULT 0,
            max_cashback INTEGER, frequency_limit TEXT,
            requires_registration INTEGER NOT NULL DEFAULT 0,
            recommendation_scope TEXT NOT NULL DEFAULT 'RECOMMENDABLE',
            eligibility_type TEXT NOT NULL DEFAULT 'GENERAL',
            valid_from TEXT NOT NULL, valid_until TEXT NOT NULL,
            conditions_json TEXT NOT NULL, excluded_conditions_json TEXT NOT NULL,
            source_url TEXT NOT NULL, raw_text_hash TEXT NOT NULL,
            summary TEXT NOT NULL, extractor_version TEXT NOT NULL,
            extracted_at TEXT NOT NULL, confidence REAL NOT NULL,
            status TEXT NOT NULL, run_id TEXT, raw_payload_json TEXT NOT NULL
        );
        INSERT INTO promotion_current VALUES
            ('promo1','ver1','Test Promo','TEST','Test Bank','TEST_CARD','Test Card',
             'ACTIVE',0,NULL,'ONLINE',NULL,'PERCENT',3.0,0,NULL,NULL,
             1,'RECOMMENDABLE','GENERAL','2026-01-01','2026-12-31',
             '[]','[]','https://example.com','abc123','summary','1.0',
             '2026-01-01T00:00:00',0.9,'ACTIVE','run1','{}');
    """)
    conn.commit()
    conn.close()

    yield db_path

    os.unlink(db_path)


@pytest.fixture()
def mock_pg():
    """Mock psycopg2.connect — returns a context-manager-aware connection mock."""
    with patch("extractor.supabase_store.psycopg2") as mock_psycopg2:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_psycopg2.connect.return_value = mock_conn
        mock_psycopg2.extras = MagicMock()
        yield mock_psycopg2, mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sync_returns_sync_result(sqlite_db, mock_pg):
    result = sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    assert isinstance(result, SyncResult)


def test_validate_supabase_url_rejects_placeholder_pooler_host():
    with pytest.raises(ValueError, match="placeholder host"):
        validate_supabase_url(
            "postgresql://postgres:secret@aws-0-region.pooler.supabase.com:6543/postgres"
        )


def test_sync_counts_all_three_tables(sqlite_db, mock_pg):
    result = sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    assert result.runs_upserted == 1
    assert result.versions_upserted == 1
    assert result.current_upserted == 1
    assert result.failures == 0


def test_sync_uses_configurable_statement_timeout(sqlite_db, mock_pg, monkeypatch):
    monkeypatch.setenv("SUPABASE_STATEMENT_TIMEOUT_MS", "98765")
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    assert mock_psycopg2.connect.call_args.kwargs["options"] == "-c statement_timeout=98765"


def test_sync_requires_registration_converted_to_bool(sqlite_db, mock_pg):
    """SQLite stores requires_registration as INTEGER 0/1; Supabase needs BOOLEAN."""
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")

    # Collect all rows passed to execute_values
    all_calls = mock_psycopg2.extras.execute_values.call_args_list
    # Find the promotion_versions upsert call (second table synced)
    versions_call = all_calls[1]
    rows = versions_call[0][2]  # positional arg: list of row tuples
    assert len(rows) == 1
    row = rows[0]
    # requires_registration is at index 17 in the promotion_versions column order
    requires_reg_value = row[17]
    assert requires_reg_value is True
    assert isinstance(requires_reg_value, bool)


def test_sync_passes_batch_size_to_execute_values(sqlite_db, mock_pg, monkeypatch):
    monkeypatch.setenv("SUPABASE_SYNC_BATCH_SIZE", "7")
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    assert mock_psycopg2.extras.execute_values.call_args.kwargs["page_size"] == 7


def test_sync_retries_failed_batch_with_smaller_chunks(sqlite_db, mock_pg, monkeypatch):
    monkeypatch.setenv("SUPABASE_SYNC_BATCH_SIZE", "2")
    mock_psycopg2, mock_conn, mock_cursor = mock_pg

    call_count = {"n": 0}

    def flaky_execute_values(cursor, sql, rows, page_size=None):
        if "promotion_versions" in sql and len(rows) == 2 and call_count["n"] == 0:
            call_count["n"] += 1
            raise Exception("statement timeout")

    mock_psycopg2.extras.execute_values.side_effect = flaky_execute_values
    result = sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")

    assert result.versions_upserted == 1
    assert result.failures == 0


def test_sync_skips_current_rows_when_parent_version_not_synced(sqlite_db, mock_pg, capsys):
    mock_psycopg2, mock_conn, mock_cursor = mock_pg

    def fail_versions(cursor, sql, rows, page_size=None):
        if "promotion_versions" in sql:
            raise Exception("statement timeout")

    mock_psycopg2.extras.execute_values.side_effect = fail_versions
    result = sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    output = capsys.readouterr().out

    assert result.versions_upserted == 0
    assert result.current_upserted == 0
    assert "skipping 1 promotion_current rows" in output


def test_sync_requires_registration_zero_becomes_false(sqlite_db, mock_pg):
    """SQLite requires_registration=0 → PostgreSQL False."""
    # Update the fixture row to requires_registration=0
    conn = sqlite3.connect(sqlite_db)
    conn.execute("UPDATE promotion_versions SET requires_registration = 0")
    conn.execute("UPDATE promotion_current SET requires_registration = 0")
    conn.commit()
    conn.close()

    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")

    all_calls = mock_psycopg2.extras.execute_values.call_args_list
    versions_call = all_calls[1]
    rows = versions_call[0][2]
    requires_reg_value = rows[0][17]
    assert requires_reg_value is False
    assert isinstance(requires_reg_value, bool)


def test_sync_commits_per_table(sqlite_db, mock_pg):
    """Each table upsert is followed by a commit."""
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    # Three tables → three commits
    assert mock_conn.commit.call_count == 3


def test_sync_closes_pg_connection_on_success(sqlite_db, mock_pg):
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    mock_conn.close.assert_called_once()


def test_sync_closes_pg_connection_on_error(sqlite_db, mock_pg):
    """pg connection must be closed even when execute_values raises."""
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    mock_psycopg2.extras.execute_values.side_effect = Exception("DB error")
    result = sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    mock_conn.close.assert_called_once()
    assert result.failures > 0


def test_sync_upsert_order_runs_before_versions_before_current(sqlite_db, mock_pg):
    """Foreign-key constraint requires: extract_runs → promotion_versions → promotion_current."""
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    calls = mock_psycopg2.extras.execute_values.call_args_list
    assert len(calls) == 3
    # Verify SQL snippets identify the three tables in order
    assert "extract_runs" in calls[0][0][1]
    assert "promotion_versions" in calls[1][0][1]
    assert "promotion_current" in calls[2][0][1]
