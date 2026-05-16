from __future__ import annotations

from datetime import date

from extractor import db_store


def test_mark_expired_current_promotions_updates_only_active_expired_rows(tmp_path):
    db_path = tmp_path / "cardsense.db"
    connection = db_store.initialize_database(str(db_path))
    connection.executemany(
        """
        INSERT INTO promotion_current (
            promo_id, promo_version_id, title, bank_code, bank_name, card_code, card_name,
            card_status, annual_fee, apply_url, category, subcategory, channel, cashback_type,
            cashback_value, min_amount, max_cashback, frequency_limit, requires_registration,
            recommendation_scope, eligibility_type, plan_id, valid_from, valid_until,
            conditions_json, excluded_conditions_json, source_url, raw_text_hash, summary,
            extractor_version, extracted_at, confidence, status, run_id, raw_payload_json
        ) VALUES (
            ?, ?, ?, 'TEST', 'Test Bank', 'TEST_CARD', 'Test Card',
            'ACTIVE', 0, NULL, 'ONLINE', 'GENERAL', NULL, 'PERCENT',
            3.0, 0, NULL, NULL, 0,
            'RECOMMENDABLE', 'GENERAL', NULL, '2026-01-01', ?,
            '[]', '[]', 'https://example.com', 'hash', 'summary',
            'test', '2026-01-01T00:00:00', 0.9, ?, 'run1', '{}'
        )
        """,
        [
            ("expired", "expired_ver", "Expired", "2026-05-15", "ACTIVE"),
            ("today", "today_ver", "Today", "2026-05-16", "ACTIVE"),
            ("future", "future_ver", "Future", "2026-06-01", "ACTIVE"),
            ("already_inactive", "inactive_ver", "Inactive", "2026-05-01", "INACTIVE"),
        ],
    )
    connection.commit()

    updated = db_store.mark_expired_current_promotions(connection, today=date(2026, 5, 16))

    rows = {
        row["promo_id"]: row["status"]
        for row in connection.execute("SELECT promo_id, status FROM promotion_current")
    }
    connection.close()

    assert updated == 1
    assert rows == {
        "expired": "EXPIRED",
        "today": "ACTIVE",
        "future": "ACTIVE",
        "already_inactive": "INACTIVE",
    }
