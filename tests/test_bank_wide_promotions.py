import os
import sys
from types import SimpleNamespace

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.bank_wide_promotions import apply_bank_wide_promotion_supplements
from extractor.promotion_rules import append_bank_wide_promotion_condition


def test_append_bank_wide_promotion_condition_marks_explicit_bank_wide_copy():
    conditions = append_bank_wide_promotion_condition(
        "全卡適用 國內一般消費 2%",
        "本活動不限卡別，全卡適用，國內一般消費享 2% 回饋。",
        "RECOMMENDABLE",
        [],
        requires_registration=False,
        plan_id=None,
        subcategory="GENERAL",
    )

    assert any(condition["value"] == "BANK_WIDE_PROMOTION" for condition in conditions)


def test_apply_bank_wide_promotion_supplements_clones_to_cobrand_card():
    source_card = SimpleNamespace(card_code="BANK_CORE", card_name="核心回饋卡")
    target_card = SimpleNamespace(card_code="BANK_CO", card_name="百貨聯名卡")
    source_promotion = {
        "title": "核心回饋卡 全卡適用 國內一般消費 2%",
        "summary": "核心回饋卡 全卡適用 國內一般消費 2%",
        "cardCode": "BANK_CORE",
        "cardName": "核心回饋卡",
        "bankCode": "BANK",
        "category": "ONLINE",
        "subcategory": "GENERAL",
        "channel": "ALL",
        "cashbackType": "PERCENT",
        "cashbackValue": 2.0,
        "minAmount": 0,
        "maxCashback": None,
        "validFrom": "2026-01-01",
        "validUntil": "2026-12-31",
        "requiresRegistration": False,
        "recommendationScope": "RECOMMENDABLE",
        "conditions": [{"type": "TEXT", "value": "BANK_WIDE_PROMOTION", "label": "Bank-wide promotion candidate"}],
        "planId": None,
    }

    updated, supplement_count = apply_bank_wide_promotion_supplements([
        (source_card, [source_promotion]),
        (target_card, []),
    ])

    assert supplement_count == 1
    target_promotions = updated[1][1]
    assert len(target_promotions) == 1
    assert target_promotions[0]["cardCode"] == "BANK_CO"
    assert target_promotions[0]["cardName"] == "百貨聯名卡"
    assert any(condition["value"] == "BANK_WIDE_SUPPLEMENT" for condition in target_promotions[0]["conditions"])
    assert any(condition["value"] == "BANK_WIDE_SOURCE_CARD_BANK_CORE" for condition in target_promotions[0]["conditions"])


def test_apply_bank_wide_promotion_supplements_skips_duplicate_equivalent_rows():
    source_card = SimpleNamespace(card_code="BANK_CORE", card_name="核心回饋卡")
    target_card = SimpleNamespace(card_code="BANK_CO", card_name="百貨聯名卡")
    source_promotion = {
        "title": "核心回饋卡 全卡適用 國內一般消費 2%",
        "summary": "核心回饋卡 全卡適用 國內一般消費 2%",
        "cardCode": "BANK_CORE",
        "cardName": "核心回饋卡",
        "bankCode": "BANK",
        "category": "ONLINE",
        "subcategory": "GENERAL",
        "channel": "ALL",
        "cashbackType": "PERCENT",
        "cashbackValue": 2.0,
        "minAmount": 0,
        "maxCashback": None,
        "validFrom": "2026-01-01",
        "validUntil": "2026-12-31",
        "requiresRegistration": False,
        "recommendationScope": "RECOMMENDABLE",
        "conditions": [{"type": "TEXT", "value": "BANK_WIDE_PROMOTION", "label": "Bank-wide promotion candidate"}],
        "planId": None,
    }
    existing_target_promotion = {
        **source_promotion,
        "title": "百貨聯名卡 全卡適用 國內一般消費 2%",
        "summary": "百貨聯名卡 全卡適用 國內一般消費 2%",
        "cardCode": "BANK_CO",
        "cardName": "百貨聯名卡",
    }

    updated, supplement_count = apply_bank_wide_promotion_supplements([
        (source_card, [source_promotion]),
        (target_card, [existing_target_promotion]),
    ])

    assert supplement_count == 0
    assert len(updated[1][1]) == 1
