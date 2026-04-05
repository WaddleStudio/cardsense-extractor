import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.esun_real import _dedupe_promotions, _extract_reward, _infer_channel, _normalize_promotion_title
from extractor.normalize import clean_card_name
from extractor.promotion_rules import SUBCATEGORY_SIGNALS, infer_subcategory


def test_extract_reward_prefers_percent_when_title_is_percent_offer():
    reward = _extract_reward(
        "一般消費最高 14.5% 回饋",
        "指定通路最高回饋 500 點，活動期間加碼最高 14.5%。",
    )

    assert reward == {"type": "PERCENT", "value": 14.5}


def test_normalize_promotion_title_drops_note_noise_and_uses_body_fallback():
    title = _normalize_promotion_title(
        "玉山世界卡",
        "玉山世界卡",
        "一般消費享 1% 玉山 e point 回饋",
    )

    assert title == "一般消費享 1% 玉山 e point 回饋"


def test_dedupe_promotions_removes_exact_duplicate_rows():
    promotions = [
        {
            "cardCode": "ESUN_WORLD",
            "title": "玉山世界卡 海外消費",
            "category": "OVERSEAS",
            "channel": "ONLINE",
            "cashbackType": "PERCENT",
            "cashbackValue": 10.0,
            "minAmount": 0,
            "maxCashback": 500,
            "validFrom": "2026-01-01",
            "validUntil": "2026-03-31",
            "summary": "A",
        },
        {
            "cardCode": "ESUN_WORLD",
            "title": "玉山世界卡 海外消費",
            "category": "OVERSEAS",
            "channel": "ONLINE",
            "cashbackType": "PERCENT",
            "cashbackValue": 10.0,
            "minAmount": 0,
            "maxCashback": 500,
            "validFrom": "2026-01-01",
            "validUntil": "2026-03-31",
            "summary": "A",
        },
    ]

    deduped = _dedupe_promotions(promotions)

    assert len(deduped) == 1


def test_infer_channel_prefers_online_for_digital_payment_offer():
    channel = _infer_channel(
        "行動支付一般消費加碼",
        "綁定 LINE Pay 或玉山 Wallet 享加碼回饋。",
    )

    assert channel == "ONLINE"


def test_unicard_online_offer_can_infer_plan_and_subcategory_hint():
    from extractor.benefit_plans import apply_plan_subcategory_hint, infer_plan_id

    plan_id = infer_plan_id(
        "ESUN_UNICARD",
        "ONLINE",
        title="LINE Pay 任意選 3%",
        subcategory="GENERAL",
    )
    category, subcategory = apply_plan_subcategory_hint(
        plan_id,
        "ONLINE",
        "GENERAL",
        title="LINE Pay 行動支付 3%",
    )

    assert plan_id == "ESUN_UNICARD_FLEXIBLE"
    assert category == "ONLINE"
    assert subcategory == "MOBILE_PAY"


def test_unicard_plan_hint_keeps_general_without_matching_subcategory_signal():
    from extractor.benefit_plans import apply_plan_subcategory_hint

    category, subcategory = apply_plan_subcategory_hint(
        "ESUN_UNICARD_SIMPLE",
        "GROCERY",
        "GENERAL",
        title="生鮮採買 3%",
        body="一般消費加碼 3%",
    )

    assert category == "GROCERY"
    assert subcategory == "GENERAL"


def test_unicard_plan_hint_appends_merchant_conditions_for_mobile_pay():
    from extractor.esun_real import _append_unicard_plan_conditions

    conditions = _append_unicard_plan_conditions("ESUN_UNICARD_FLEXIBLE", "MOBILE_PAY", [])

    assert any(
        condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "LINE_PAY"
        for condition in conditions
    )
    assert any(
        condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "ESUN_WALLET"
        for condition in conditions
    )


def test_mobile_pay_subcategory_is_canonicalized_after_payment_conditions_are_added():
    from extractor.promotion_rules import append_inferred_payment_method_conditions, canonicalize_subcategory

    conditions = append_inferred_payment_method_conditions("ONLINE", "MOBILE_PAY", [])

    assert canonicalize_subcategory("ONLINE", "MOBILE_PAY", conditions) == "GENERAL"
    assert any(
        condition["type"] == "PAYMENT_METHOD" and condition["value"] == "MOBILE_PAY"
        for condition in conditions
    )


def test_unicard_plan_hint_appends_streaming_merchants_after_subcategory_resolution():
    from extractor.esun_real import _append_unicard_plan_conditions

    conditions = _append_unicard_plan_conditions("ESUN_UNICARD_FLEXIBLE", "STREAMING", [])

    assert any(condition["type"] == "MERCHANT" and condition["value"] == "NETFLIX" for condition in conditions)
    assert any(
        condition["type"] == "MERCHANT" and condition["value"] == "YOUTUBE_PREMIUM"
        for condition in conditions
    )


def test_unicard_theme_park_offer_infers_entertainment_theme_park():
    from extractor.esun_real import _infer_category

    title = "主題樂園 3%"
    body = "玉山 Unicard 指定六福村主題樂園通路享 3% 玉山 e point 回饋。"

    category = _infer_category(title, body)
    subcategory = infer_subcategory(title, body, category, SUBCATEGORY_SIGNALS)

    assert category == "ENTERTAINMENT"
    assert subcategory == "THEME_PARK"


def test_clean_card_name_trims_unicard_page_selling_points():
    assert clean_card_name("玉山Unicard LINE Pay 最高回饋") == "玉山Unicard"
