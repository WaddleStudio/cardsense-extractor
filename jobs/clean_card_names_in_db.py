from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from extractor.normalize import clean_card_name


TARGET_TABLES = ("promotion_current", "promotion_versions")


def _clean_title_prefix(title: str | None, old_name: str, new_name: str) -> str | None:
    if not title or old_name == new_name:
        return title
    prefix = f"{old_name} "
    if title.startswith(prefix):
        return f"{new_name} {title[len(prefix):]}"
    return title


def _clean_raw_payload_json(raw_payload_json: str | None, old_name: str, new_name: str) -> str | None:
    if not raw_payload_json or old_name == new_name:
        return raw_payload_json

    try:
        payload = json.loads(raw_payload_json)
    except json.JSONDecodeError:
        return raw_payload_json

    changed = False
    if payload.get("cardName") == old_name:
        payload["cardName"] = new_name
        changed = True

    title = payload.get("title")
    cleaned_title = _clean_title_prefix(title, old_name, new_name)
    if cleaned_title != title:
        payload["title"] = cleaned_title
        changed = True

    if not changed:
        return raw_payload_json
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def clean_database(db_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    stats = {"rows_updated": 0, "title_updates": 0, "payload_updates": 0}

    try:
        for table in TARGET_TABLES:
            rows = connection.execute(
                f"SELECT rowid, card_name, title, raw_payload_json FROM {table}"
            ).fetchall()

            for row in rows:
                old_name = row["card_name"]
                new_name = clean_card_name(old_name)
                if not old_name or not new_name or new_name == old_name:
                    continue

                new_title = _clean_title_prefix(row["title"], old_name, new_name)
                new_payload = _clean_raw_payload_json(row["raw_payload_json"], old_name, new_name)

                connection.execute(
                    f"""
                    UPDATE {table}
                    SET card_name = ?, title = ?, raw_payload_json = ?
                    WHERE rowid = ?
                    """,
                    (new_name, new_title, new_payload, row["rowid"]),
                )
                stats["rows_updated"] += 1
                if new_title != row["title"]:
                    stats["title_updates"] += 1
                if new_payload != row["raw_payload_json"]:
                    stats["payload_updates"] += 1

        connection.commit()
        return stats
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean stored card_name values in CardSense SQLite DBs.")
    parser.add_argument("db_paths", nargs="+", help="Path(s) to SQLite database files")
    args = parser.parse_args()

    for raw_path in args.db_paths:
        db_path = Path(raw_path).resolve()
        stats = clean_database(db_path)
        print(
            f"{db_path}: updated {stats['rows_updated']} rows "
            f"(title_updates={stats['title_updates']}, payload_updates={stats['payload_updates']})"
        )


if __name__ == "__main__":
    main()
