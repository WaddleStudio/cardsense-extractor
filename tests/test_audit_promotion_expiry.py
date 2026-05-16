from __future__ import annotations

import sqlite3
from datetime import date

from jobs.audit_promotion_expiry import audit_promotion_expiry, format_audit


def test_audit_counts_expired_and_expiring_promotions(tmp_path):
    db_path = tmp_path / "cardsense.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE promotion_current (
            bank_code TEXT,
            card_code TEXT,
            promo_version_id TEXT,
            title TEXT,
            valid_until TEXT,
            status TEXT
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO promotion_current
        (bank_code, card_code, promo_version_id, title, valid_until, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("ESUN", "CARD_A", "ver_expired", "Expired promo", "2026-05-15", "ACTIVE"),
            ("ESUN", "CARD_A", "ver_today", "Expires today", "2026-05-16", "ACTIVE"),
            ("CATHAY", "CARD_B", "ver_soon", "Expires soon", "2026-06-01", "ACTIVE"),
            ("CTBC", "CARD_C", "ver_later", "Later promo", "2026-07-31", "ACTIVE"),
            ("FUBON", "CARD_D", "ver_inactive", "Inactive expired", "2026-05-01", "INACTIVE"),
        ],
    )
    connection.commit()
    connection.close()

    audit = audit_promotion_expiry(
        db_path,
        today=date(2026, 5, 16),
        warning_days=30,
        sample_limit=5,
    )

    assert audit.total_count == 5
    assert audit.active_count == 4
    assert audit.expired_active_count == 1
    assert audit.expiring_soon_count == 2
    assert [row.promo_version_id for row in audit.expired_samples] == ["ver_expired"]
    assert {row.promo_version_id for row in audit.expiring_soon_samples} == {
        "ver_today",
        "ver_soon",
    }


def test_format_audit_includes_actionable_samples(tmp_path):
    db_path = tmp_path / "cardsense.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE promotion_current (
            bank_code TEXT,
            card_code TEXT,
            promo_version_id TEXT,
            title TEXT,
            valid_until TEXT,
            status TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO promotion_current
        (bank_code, card_code, promo_version_id, title, valid_until, status)
        VALUES ('ESUN', 'CARD_A', 'ver_expired', 'Expired promo', '2026-05-15', 'ACTIVE')
        """
    )
    connection.commit()
    connection.close()

    lines = format_audit(
        audit_promotion_expiry(db_path, today=date(2026, 5, 16), sample_limit=1)
    )

    assert "  expired ACTIVE rows: 1" in lines
    assert any("ver_expired Expired promo" in line for line in lines)
