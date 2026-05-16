"""Audit promotion validity dates in the CardSense SQLite database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "cardsense.db"


@dataclass(frozen=True)
class PromotionExpiryRow:
    bank_code: str
    card_code: str
    promo_version_id: str
    title: str
    valid_until: str


@dataclass(frozen=True)
class PromotionExpiryAudit:
    today: date
    warning_days: int
    total_count: int
    active_count: int
    expired_active_count: int
    expiring_soon_count: int
    expired_samples: list[PromotionExpiryRow]
    expiring_soon_samples: list[PromotionExpiryRow]


def audit_promotion_expiry(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    today: date | None = None,
    warning_days: int = 30,
    sample_limit: int = 10,
) -> PromotionExpiryAudit:
    """Return expiry health metrics for promotion_current."""

    if warning_days < 0:
        raise ValueError("warning_days must be >= 0")
    if sample_limit < 0:
        raise ValueError("sample_limit must be >= 0")

    audit_date = today or date.today()
    warning_until = audit_date + timedelta(days=warning_days)

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        total_count = _count(connection, "SELECT count(*) FROM promotion_current")
        active_count = _count(
            connection,
            """
            SELECT count(*)
            FROM promotion_current
            WHERE upper(coalesce(status, 'ACTIVE')) = 'ACTIVE'
            """,
        )
        expired_active_count = _count(
            connection,
            """
            SELECT count(*)
            FROM promotion_current
            WHERE upper(coalesce(status, 'ACTIVE')) = 'ACTIVE'
              AND date(valid_until) < date(?)
            """,
            (audit_date.isoformat(),),
        )
        expiring_soon_count = _count(
            connection,
            """
            SELECT count(*)
            FROM promotion_current
            WHERE upper(coalesce(status, 'ACTIVE')) = 'ACTIVE'
              AND date(valid_until) BETWEEN date(?) AND date(?)
            """,
            (audit_date.isoformat(), warning_until.isoformat()),
        )
        expired_samples = _fetch_samples(
            connection,
            """
            SELECT bank_code, card_code, promo_version_id, title, valid_until
            FROM promotion_current
            WHERE upper(coalesce(status, 'ACTIVE')) = 'ACTIVE'
              AND date(valid_until) < date(?)
            ORDER BY date(valid_until) DESC, bank_code, card_code, promo_version_id
            LIMIT ?
            """,
            (audit_date.isoformat(), sample_limit),
        )
        expiring_soon_samples = _fetch_samples(
            connection,
            """
            SELECT bank_code, card_code, promo_version_id, title, valid_until
            FROM promotion_current
            WHERE upper(coalesce(status, 'ACTIVE')) = 'ACTIVE'
              AND date(valid_until) BETWEEN date(?) AND date(?)
            ORDER BY date(valid_until), bank_code, card_code, promo_version_id
            LIMIT ?
            """,
            (audit_date.isoformat(), warning_until.isoformat(), sample_limit),
        )
    finally:
        connection.close()

    return PromotionExpiryAudit(
        today=audit_date,
        warning_days=warning_days,
        total_count=total_count,
        active_count=active_count,
        expired_active_count=expired_active_count,
        expiring_soon_count=expiring_soon_count,
        expired_samples=expired_samples,
        expiring_soon_samples=expiring_soon_samples,
    )


def format_audit(audit: PromotionExpiryAudit) -> list[str]:
    lines = [
        ">>> PROMOTION EXPIRY AUDIT",
        f"  today: {audit.today.isoformat()}",
        f"  total rows: {audit.total_count}",
        f"  ACTIVE status rows: {audit.active_count}",
        f"  expired ACTIVE rows: {audit.expired_active_count}",
        f"  expiring in {audit.warning_days} days: {audit.expiring_soon_count}",
    ]

    if audit.expired_samples:
        lines.append("  expired samples:")
        for row in audit.expired_samples:
            lines.append(
                "    "
                f"{row.valid_until} {row.bank_code}/{row.card_code} "
                f"{row.promo_version_id} {row.title}"
            )

    if audit.expiring_soon_samples:
        lines.append("  expiring soon samples:")
        for row in audit.expiring_soon_samples:
            lines.append(
                "    "
                f"{row.valid_until} {row.bank_code}/{row.card_code} "
                f"{row.promo_version_id} {row.title}"
            )

    return lines


def _count(connection: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> int:
    return int(connection.execute(sql, params).fetchone()[0])


def _fetch_samples(
    connection: sqlite3.Connection,
    sql: str,
    params: tuple[object, ...],
) -> list[PromotionExpiryRow]:
    return [
        PromotionExpiryRow(
            bank_code=row["bank_code"],
            card_code=row["card_code"],
            promo_version_id=row["promo_version_id"],
            title=row["title"],
            valid_until=row["valid_until"],
        )
        for row in connection.execute(sql, params).fetchall()
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit promotion_current expiry health.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite DB path")
    parser.add_argument("--today", default=None, help="Override audit date, YYYY-MM-DD")
    parser.add_argument("--warning-days", type=int, default=30, help="Near-expiry window")
    parser.add_argument("--sample-limit", type=int, default=10, help="Rows to print per bucket")
    parser.add_argument(
        "--fail-on-expired",
        action="store_true",
        help="Return exit code 1 when ACTIVE rows are already expired",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit_date = date.fromisoformat(args.today) if args.today else None
    audit = audit_promotion_expiry(
        args.db,
        today=audit_date,
        warning_days=args.warning_days,
        sample_limit=args.sample_limit,
    )
    for line in format_audit(audit):
        print(line)
    if args.fail_on_expired and audit.expired_active_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
