import os
import sys
from collections import Counter
from datetime import datetime
from typing import Callable

from extractor import load, validate, versioning
from pydantic import ValidationError


def _console_print(message: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe_message = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe_message)


def run_real_bank_job(
    *,
    bank_label: str,
    output_prefix: str,
    list_cards: Callable[[], list],
    extract_card_promotions: Callable,
    limit: int | None = None,
    allow_empty_promotions: bool = False,
) -> int:
    cards = list_cards()
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    output_path = os.getenv(
        "CARDSENSE_OUTPUT_JSONL",
        os.path.join(project_root, "outputs", f"{output_prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"),
    )
    load.configure_output(output_path, reset=True)

    _console_print(f">>> {bank_label} card list discovered: {len(cards)} cards")
    load.announce_output()

    selected_cards = cards[:limit] if limit else cards
    _console_print(f">>> Processing {len(selected_cards)} card detail page(s)")

    loaded_count = 0
    failed_count = 0
    category_counter: Counter[str] = Counter()
    scope_counter: Counter[str] = Counter()

    for index, card in enumerate(selected_cards, start=1):
        _console_print(f"\n--- Card {index}/{len(selected_cards)}: {card.card_name} ---")
        try:
            enriched_card, promotions = extract_card_promotions(card)
            _console_print(f"Card URL: {enriched_card.detail_url}")
            _console_print(f"Apply URL: {enriched_card.apply_url}")
            _console_print(f"Annual Fee: {enriched_card.annual_fee_summary}")
            _console_print(f"Application Requirements: {len(enriched_card.application_requirements)}")
            _console_print(f"Sections: {', '.join(enriched_card.sections)}")
            _console_print(f"Promotions Extracted: {len(promotions)}")

            for promotion in promotions:
                payload = versioning.assign_version_ids(promotion, promotion["summary"])
                validated = validate.validate_promotion(payload)
                load.load_promotion(validated)
                loaded_count += 1
                category_counter[validated.category] += 1
                scope_counter[validated.recommendationScope] += 1
        except ValidationError as error:
            failed_count += 1
            _console_print(f">>> Validation failed for {card.detail_url}")
            _console_print(str(error))
        except Exception as error:
            failed_count += 1
            _console_print(f">>> Unexpected error for {card.detail_url}: {error}")

    _console_print(f"\n=== {bank_label} REAL EXTRACTION SUMMARY ===")
    _console_print(f"Cards processed: {len(selected_cards)}")
    _console_print(f"Promotions loaded: {loaded_count}")
    _console_print(f"Card failures: {failed_count}")
    _console_print(f"Category distribution: {dict(category_counter)}")
    _console_print(f"Scope distribution: {dict(scope_counter)}")
    _console_print(f"Output file: {output_path}")
    if loaded_count > 0:
        return 0
    if allow_empty_promotions and selected_cards and failed_count == 0:
        return 0
    return 1