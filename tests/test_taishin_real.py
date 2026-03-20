from __future__ import annotations

import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Card listing
# ---------------------------------------------------------------------------

def test_list_taishin_cards_discovers_cards_from_listing_fixture():
    from extractor.taishin_real import list_taishin_cards

    html = _load_fixture("taishin_listing.html")

    with patch("extractor.ingest.fetch_rendered_page", return_value=html):
        cards = list_taishin_cards()

    assert len(cards) >= 10, f"Expected >= 10 cards, got {len(cards)}"
    for card in cards:
        assert card.card_code.startswith("TAISHIN_"), f"card_code should start with TAISHIN_: {card.card_code}"
        assert "卡" in card.card_name, f"card_name should contain 卡: {card.card_name}"
        assert card.detail_url.startswith("https://www.taishinbank.com.tw"), f"detail_url bad: {card.detail_url}"


# ---------------------------------------------------------------------------
# Promotion extraction
# ---------------------------------------------------------------------------

def test_extract_card_promotions_from_detail_fixture():
    from extractor.taishin_real import CardRecord, extract_card_promotions

    html = _load_fixture("taishin_card_cg003.html")

    card = CardRecord(
        card_code="TAISHIN_CG003_CARD001",
        card_name="國泰航空翱翔鈦金卡/鈦金卡",
        detail_url="https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg003/card001/",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    with patch("extractor.ingest.fetch_rendered_page", return_value=html):
        enriched, promotions = extract_card_promotions(card)

    assert len(promotions) >= 1, f"Expected >= 1 promotion, got {len(promotions)}"

    for promo in promotions:
        assert promo["bankCode"] == "TAISHIN"
        assert promo["cardCode"] == "TAISHIN_CG003_CARD001"
        assert promo["cashbackValue"] > 0, f"cashbackValue should be > 0: {promo}"
        assert promo["validFrom"], f"validFrom missing: {promo}"
        assert promo["validUntil"], f"validUntil missing: {promo}"
        assert promo["category"], f"category missing: {promo}"
        assert promo["channel"], f"channel missing: {promo}"
