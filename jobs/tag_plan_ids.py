"""
Tag existing promotions with planId based on cardCode + category mapping.

Usage:
    uv run python jobs/tag_plan_ids.py [--db data/cardsense.db] [--dry-run]

This script maps promotions to benefit plans using category heuristics.
It is idempotent — re-running it will update existing tags.

Plan mapping logic:
  CATHAY_CUBE:
    ONLINE, ENTERTAINMENT        → CATHAY_CUBE_DIGITAL   (玩數位)
    SHOPPING, GROCERY            → CATHAY_CUBE_SHOPPING  (樂饗購)
    OVERSEAS, TRANSPORT          → CATHAY_CUBE_TRAVEL    (趣旅行)
    DINING, OTHER                → CATHAY_CUBE_ESSENTIALS(集精選)

  ESUN_UNICARD:
    ONLINE, ENTERTAINMENT        → ESUN_UNICARD_FLEXIBLE (任意選)
    DINING, GROCERY              → ESUN_UNICARD_SIMPLE   (簡單選)
    OVERSEAS, TRANSPORT, SHOPPING, OTHER → ESUN_UNICARD_SIMPLE (簡單選)

  TAISHIN_RICHART (when data exists):
    ONLINE, ENTERTAINMENT        → TAISHIN_RICHART_DIGITAL (數趣刷)
    DINING                       → TAISHIN_RICHART_DINING  (好饗刷)
    OVERSEAS, TRANSPORT          → TAISHIN_RICHART_TRAVEL  (玩旅刷)
    SHOPPING, GROCERY, OTHER     → TAISHIN_RICHART_DAILY   (天天刷)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# cardCode → { category → planId }
PLAN_MAPPING: dict[str, dict[str, str]] = {
    "CATHAY_CUBE": {
        "ONLINE": "CATHAY_CUBE_DIGITAL",
        "ENTERTAINMENT": "CATHAY_CUBE_DIGITAL",
        "SHOPPING": "CATHAY_CUBE_SHOPPING",
        "GROCERY": "CATHAY_CUBE_SHOPPING",
        "OVERSEAS": "CATHAY_CUBE_TRAVEL",
        "TRANSPORT": "CATHAY_CUBE_TRAVEL",
        "DINING": "CATHAY_CUBE_ESSENTIALS",
        "OTHER": "CATHAY_CUBE_ESSENTIALS",
    },
    "ESUN_UNICARD": {
        "ONLINE": "ESUN_UNICARD_FLEXIBLE",
        "ENTERTAINMENT": "ESUN_UNICARD_FLEXIBLE",
        "DINING": "ESUN_UNICARD_SIMPLE",
        "GROCERY": "ESUN_UNICARD_SIMPLE",
        "OVERSEAS": "ESUN_UNICARD_SIMPLE",
        "TRANSPORT": "ESUN_UNICARD_SIMPLE",
        "SHOPPING": "ESUN_UNICARD_SIMPLE",
        "OTHER": "ESUN_UNICARD_SIMPLE",
    },
    "TAISHIN_RICHART": {
        "ONLINE": "TAISHIN_RICHART_DIGITAL",
        "ENTERTAINMENT": "TAISHIN_RICHART_DIGITAL",
        "DINING": "TAISHIN_RICHART_DINING",
        "OVERSEAS": "TAISHIN_RICHART_TRAVEL",
        "TRANSPORT": "TAISHIN_RICHART_TRAVEL",
        "SHOPPING": "TAISHIN_RICHART_DAILY",
        "GROCERY": "TAISHIN_RICHART_DAILY",
        "OTHER": "TAISHIN_RICHART_DAILY",
    },
}


def tag_plan_ids(db_path: str, dry_run: bool = False) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Ensure plan_id column exists
    for table in ("promotion_versions", "promotion_current"):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "plan_id" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN plan_id TEXT")
            conn.commit()
            print(f"  Added plan_id column to {table}")

    total_updated = 0

    for card_code, category_map in PLAN_MAPPING.items():
        rows = conn.execute(
            "SELECT promo_id, promo_version_id, category, plan_id FROM promotion_current WHERE card_code = ?",
            (card_code,),
        ).fetchall()

        if not rows:
            print(f"  {card_code}: no promotions found, skipping")
            continue

        for row in rows:
            category = (row["category"] or "OTHER").upper()
            new_plan_id = category_map.get(category)
            if not new_plan_id:
                continue

            old_plan_id = row["plan_id"]
            if old_plan_id == new_plan_id:
                continue

            action = "would tag" if dry_run else "tagged"
            print(f"  {action} {row['promo_id'][:12]}… ({card_code}/{category}) → {new_plan_id}")

            if not dry_run:
                conn.execute(
                    "UPDATE promotion_current SET plan_id = ? WHERE promo_id = ?",
                    (new_plan_id, row["promo_id"]),
                )
                conn.execute(
                    "UPDATE promotion_versions SET plan_id = ? WHERE promo_version_id = ?",
                    (new_plan_id, row["promo_version_id"]),
                )
                total_updated += 1

    if not dry_run:
        conn.commit()

    conn.close()
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Done. {total_updated} promotions updated.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tag promotions with planId")
    parser.add_argument("--db", default="data/cardsense.db", help="SQLite DB path")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: DB not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Tagging planIds in {db_path} {'(dry run)' if args.dry_run else ''}...")
    tag_plan_ids(str(db_path), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
