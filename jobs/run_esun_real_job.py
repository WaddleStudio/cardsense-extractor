import os
import sys
from collections import Counter
from datetime import datetime

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor import load, validate, versioning
from extractor.esun_real import extract_card_promotions, list_esun_cards
from pydantic import ValidationError


def run(limit: int | None = None) -> int:
    cards = list_esun_cards()
    output_path = os.getenv(
        "CARDSENSE_OUTPUT_JSONL",
        os.path.join(project_root, "outputs", f"esun-real-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"),
    )
    load.configure_output(output_path, reset=True)

    print(f">>> E.SUN card list discovered: {len(cards)} cards")
    load.announce_output()

    selected_cards = cards[:limit] if limit else cards
    print(f">>> Processing {len(selected_cards)} card detail page(s)")

    loaded_count = 0
    failed_count = 0
    category_counter: Counter[str] = Counter()

    for index, card in enumerate(selected_cards, start=1):
        print(f"\n--- Card {index}/{len(selected_cards)}: {card.card_name} ---")
        try:
            enriched_card, promotions = extract_card_promotions(card)
            print(f"Card URL: {enriched_card.detail_url}")
            print(f"Apply URL: {enriched_card.apply_url}")
            print(f"Annual Fee: {enriched_card.annual_fee_summary}")
            print(f"Application Requirements: {len(enriched_card.application_requirements)}")
            print(f"Sections: {', '.join(enriched_card.sections)}")
            print(f"Promotions Extracted: {len(promotions)}")

            for promotion in promotions:
                payload = versioning.assign_version_ids(promotion, promotion["summary"])
                validated = validate.validate_promotion(payload)
                load.load_promotion(validated)
                loaded_count += 1
                category_counter[validated.category] += 1
        except ValidationError as error:
            failed_count += 1
            print(f">>> Validation failed for {card.detail_url}")
            print(error)
        except Exception as error:
            failed_count += 1
            print(f">>> Unexpected error for {card.detail_url}: {error}")

    print("\n=== E.SUN REAL EXTRACTION SUMMARY ===")
    print(f"Cards processed: {len(selected_cards)}")
    print(f"Promotions loaded: {loaded_count}")
    print(f"Card failures: {failed_count}")
    print(f"Category distribution: {dict(category_counter)}")
    print(f"Output file: {output_path}")
    return 0 if loaded_count > 0 else 1


if __name__ == "__main__":
    limit_value = os.getenv("ESUN_REAL_LIMIT")
    limit = int(limit_value) if limit_value else None
    raise SystemExit(run(limit=limit))
