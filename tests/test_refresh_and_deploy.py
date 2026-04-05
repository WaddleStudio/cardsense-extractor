from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from jobs.refresh_and_deploy import clean_stored_card_names, find_latest_jsonl, run_sync
from extractor.supabase_store import SyncFilter


def _sync_result() -> SimpleNamespace:
    return SimpleNamespace(
        runs_upserted=1,
        versions_upserted=2,
        current_upserted=3,
        failures=0,
        reconnects=0,
        table_durations={},
    )


def test_run_sync_prefers_pooler_before_direct_url(monkeypatch):
    pool_url = "postgresql://postgres.demo:secret@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
    direct_url = "postgresql://postgres:secret@db.demo.supabase.co:5432/postgres"
    monkeypatch.setenv("SUPABASE_POOL_MODE", pool_url)
    monkeypatch.setenv("SUPABASE_DATABASE_URL", direct_url)

    with (
        patch("jobs.refresh_and_deploy.load_dotenv"),
        patch("extractor.supabase_store.validate_supabase_url") as mock_validate,
        patch("extractor.supabase_store.get_reconnect_warn_threshold", return_value=3),
        patch("extractor.supabase_store.sync_sqlite_to_supabase", return_value=_sync_result()) as mock_sync,
    ):
        assert run_sync("dummy.db") is True

    assert mock_validate.call_args_list == [call(pool_url), call(direct_url)]
    assert mock_sync.call_args_list == [call("dummy.db", pool_url, SyncFilter())]


def test_run_sync_prefers_rest_transport_when_configured(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv(
        "SUPABASE_POOL_MODE",
        "postgresql://postgres.demo:secret@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres",
    )

    with (
        patch("jobs.refresh_and_deploy.load_dotenv"),
        patch("extractor.supabase_store.validate_supabase_project_url") as mock_validate_project_url,
        patch("extractor.supabase_store.validate_supabase_url") as mock_validate_dsn,
        patch("extractor.supabase_store.get_http_timeout_seconds", return_value=60),
        patch("extractor.supabase_store.get_reconnect_warn_threshold", return_value=3),
        patch("extractor.supabase_store.sync_sqlite_to_supabase_http", return_value=_sync_result()) as mock_http_sync,
        patch("extractor.supabase_store.sync_sqlite_to_supabase") as mock_pg_sync,
    ):
        assert run_sync("dummy.db") is True

    mock_validate_project_url.assert_called_once_with("https://demo.supabase.co")
    mock_validate_dsn.assert_called_once()
    assert mock_http_sync.call_args_list == [call("dummy.db", "https://demo.supabase.co", "service-role-key", SyncFilter())]
    mock_pg_sync.assert_not_called()


def test_run_sync_falls_back_to_direct_url_when_pooler_fails(monkeypatch):
    pool_url = "postgresql://postgres.demo:secret@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
    direct_url = "postgresql://postgres:secret@db.demo.supabase.co:5432/postgres"
    monkeypatch.setenv("SUPABASE_POOL_MODE", pool_url)
    monkeypatch.setenv("SUPABASE_DATABASE_URL", direct_url)

    with (
        patch("jobs.refresh_and_deploy.load_dotenv"),
        patch("extractor.supabase_store.validate_supabase_url"),
        patch("extractor.supabase_store.get_reconnect_warn_threshold", return_value=3),
        patch(
            "extractor.supabase_store.sync_sqlite_to_supabase",
            side_effect=[Exception("pooler unavailable"), _sync_result()],
        ) as mock_sync,
    ):
        assert run_sync("dummy.db") is True

    assert mock_sync.call_args_list == [
        call("dummy.db", pool_url, SyncFilter()),
        call("dummy.db", direct_url, SyncFilter()),
    ]


def test_run_sync_passes_scope_filter(monkeypatch):
    monkeypatch.setenv("SUPABASE_POOL_MODE", "postgresql://postgres.demo:secret@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres")

    with (
        patch("jobs.refresh_and_deploy.load_dotenv"),
        patch("extractor.supabase_store.validate_supabase_url"),
        patch("extractor.supabase_store.get_reconnect_warn_threshold", return_value=3),
        patch("extractor.supabase_store.sync_sqlite_to_supabase", return_value=_sync_result()) as mock_sync,
    ):
        assert run_sync("dummy.db", sync_bank="cathay", sync_card="cathay_cube") is True

    assert mock_sync.call_args_list == [
        call(
            "dummy.db",
            "postgresql://postgres.demo:secret@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres",
            SyncFilter(bank_code="CATHAY", card_code="CATHAY_CUBE"),
        )
    ]


def test_find_latest_jsonl_prefers_timestamped_output_over_full_latest_alias(tmp_path, monkeypatch):
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()

    full_latest = outputs_dir / "esun-real-full-latest.jsonl"
    full_latest.write_text("old", encoding="utf-8")

    older = outputs_dir / "esun-real-20260331-172145.jsonl"
    older.write_text("older", encoding="utf-8")

    newest = outputs_dir / "esun-real-20260331-175216.jsonl"
    newest.write_text("newest", encoding="utf-8")

    os.utime(full_latest, (100, 100))
    os.utime(older, (200, 200))
    os.utime(newest, (300, 300))

    monkeypatch.setattr("jobs.refresh_and_deploy.project_root", str(tmp_path))

    assert find_latest_jsonl("ESUN") == str(newest)


def test_clean_stored_card_names_delegates_to_db_cleaner():
    with patch("jobs.clean_card_names_in_db.clean_database", return_value={"rows_updated": 3, "title_updates": 2, "payload_updates": 1}) as mock_clean:
        clean_stored_card_names("dummy.db")

    mock_clean.assert_called_once_with(Path(os.path.abspath("dummy.db")))
