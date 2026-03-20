import argparse
import json
import os
from collections import Counter
from pathlib import Path


project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze CardSense extractor JSONL output")
    parser.add_argument("--input", default=os.getenv("CARDSENSE_INPUT_JSONL"), help="Input JSONL path")
    parser.add_argument("--top", type=int, default=15, help="Top N groups to print")
    return parser.parse_args()


def run(input_path: str, top: int) -> int:
    target = Path(input_path)
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]

    print(f"input={target}")
    print(f"promotions={len(rows)}")
    print(f"cards={len({row['cardCode'] for row in rows})}")

    print("category_counts")
    for key, value in Counter(row["category"] for row in rows).most_common():
        print(f"{key}\t{value}")

    print("channel_counts")
    for key, value in Counter(row["channel"] for row in rows).most_common():
        print(f"{key}\t{value}")

    print("other_top_cards")
    for key, value in Counter(row["cardCode"] for row in rows if row.get("category") == "OTHER").most_common(top):
        print(f"{key}\t{value}")

    print("all_top_cards")
    for key, value in Counter(row["cardCode"] for row in rows if row.get("channel") == "ALL").most_common(top):
        print(f"{key}\t{value}")

    print("other_top_titles")
    for key, value in Counter(row["title"] for row in rows if row.get("category") == "OTHER").most_common(top):
        print(f"{key}\t{value}")

    print("all_top_titles")
    for key, value in Counter(row["title"] for row in rows if row.get("channel") == "ALL").most_common(top):
        print(f"{key}\t{value}")

    return 0


if __name__ == "__main__":
    arguments = parse_args()
    if not arguments.input:
        raise SystemExit("Missing --input or CARDSENSE_INPUT_JSONL")
    raise SystemExit(run(arguments.input, arguments.top))