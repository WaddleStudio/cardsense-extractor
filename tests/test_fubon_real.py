import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor import fubon_real


def test_general_reward_exclusion_copy_drops_false_payment_and_online_bias():
    category, subcategory, channel, scope, conditions = fubon_real._apply_card_specific_overrides(
        "FUBON_ANGEL",
        "刷卡賺紅利 輕鬆享回饋",
        "一般消費定義：不包含指定網路平台交易、便利商店消費(含綁定該便利商店各行動支付，如 icash Pay、全盈+Pay 及 LINE PAY 等)、全聯實業旗下品牌通路(包含 Px pay、全支付 等)。",
        "ONLINE",
        "GENERAL",
        "ONLINE",
        "CATALOG_ONLY",
        [
            {"type": "PAYMENT_PLATFORM", "value": "ICASH_PAY", "label": "icash Pay"},
            {"type": "PAYMENT_PLATFORM", "value": "全支付", "label": "全支付"},
            {"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": "行動支付"},
        ],
    )

    assert category == "OTHER"
    assert subcategory == "GENERAL"
    assert channel == "ALL"
    assert scope == "CATALOG_ONLY"
    assert conditions == []


def test_jcard_apple_pay_suica_keeps_payment_and_adds_transit_structure():
    category, subcategory, channel, scope, conditions = fubon_real._apply_card_specific_overrides(
        "FUBON_OMIYAGE",
        "日本三大交通卡最高 10% 回饋",
        "活動內容：以Apple Pay綁定J卡並刷付日本Suica、PASMO或ICOCA卡儲值金，單筆滿新台幣2,000元，享最高10%回饋。",
        "OVERSEAS",
        "GENERAL",
        "ONLINE",
        "RECOMMENDABLE",
        [],
    )

    assert category == "TRANSPORT"
    assert subcategory == "PUBLIC_TRANSIT"
    assert channel == "ONLINE"
    assert scope == "RECOMMENDABLE"
    assert any(condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "APPLE_PAY" for condition in conditions)
    assert any(condition["type"] == "MERCHANT" and condition["value"] == "SUICA" for condition in conditions)
    assert any(condition["type"] == "MERCHANT" and condition["value"] == "PASMO" for condition in conditions)
    assert any(condition["type"] == "MERCHANT" and condition["value"] == "ICOCA" for condition in conditions)


def test_referral_coupon_copy_drops_false_grocery_merchants():
    category, subcategory, channel, scope, conditions = fubon_real._apply_card_specific_overrides(
        "FUBON_OMIYAGE",
        "4. 分享您的專屬推薦連結給好友",
        "本活動限本國籍自然人參加，成功推薦一位J卡新戶回饋300元即享券。即享券適用通路：全聯、家樂福、大全聯。",
        "GROCERY",
        "SUPERMARKET",
        "ALL",
        "FUTURE_SCOPE",
        [
            {"type": "RETAIL_CHAIN", "value": "PXMART", "label": "全聯"},
            {"type": "RETAIL_CHAIN", "value": "CARREFOUR", "label": "家樂福"},
        ],
    )

    assert category == "OTHER"
    assert subcategory == "GENERAL"
    assert channel == "ALL"
    assert scope == "FUTURE_SCOPE"
    assert conditions == []


def test_momo_public_transit_offer_drops_negated_high_speed_rail_merchants():
    category, subcategory, channel, scope, conditions = fubon_real._apply_card_specific_overrides(
        "FUBON_MOMO",
        "一卡通全台大眾交通2%，回饋無上限",
        "限以富邦momo卡之一卡通功能搭乘全台大眾運輸，始具回饋資格(高鐵除外，且僅限實體卡交易)。",
        "TRANSPORT",
        "PUBLIC_TRANSIT",
        "OFFLINE",
        "RECOMMENDABLE",
        [
            {"type": "MERCHANT", "value": "TRA", "label": "台鐵"},
            {"type": "MERCHANT", "value": "THSR", "label": "高鐵"},
        ],
    )

    assert category == "TRANSPORT"
    assert subcategory == "PUBLIC_TRANSIT"
    assert channel == "OFFLINE"
    assert scope == "RECOMMENDABLE"
    assert conditions == []


def test_momo_cross_border_online_offer_drops_false_momo_platform():
    category, subcategory, channel, scope, conditions = fubon_real._apply_card_specific_overrides(
        "FUBON_MOMO",
        "指定跨境線上 消費滿千最高 回饋6%",
        "活動期間刷momo卡或尊御卡，於跨境線上消費，單筆滿千享最高6%刷卡金回饋。",
        "ONLINE",
        "ECOMMERCE",
        "ALL",
        "RECOMMENDABLE",
        [
            {"type": "ECOMMERCE_PLATFORM", "value": "MOMO", "label": "momo"},
        ],
    )

    assert category == "ONLINE"
    assert subcategory == "GENERAL"
    assert channel == "ONLINE"
    assert scope == "RECOMMENDABLE"
    assert conditions == []


def test_momo_store_threshold_offer_moves_to_catalog_only():
    category, subcategory, channel, scope, conditions = fubon_real._apply_card_specific_overrides(
        "FUBON_MOMO",
        "momo卡店外滿額 店內最高 6% 回饋",
        "本活動以消費日為準，正附卡消費合併計算。使用第三方支付平台如 LINE Pay、街口支付、悠遊付 之交易不列入活動資格。",
        "ONLINE",
        "GENERAL",
        "ALL",
        "FUTURE_SCOPE",
        [
            {"type": "PAYMENT_PLATFORM", "value": "LINE_PAY", "label": "LINE Pay"},
            {"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": "行動支付"},
        ],
    )

    assert category == "ONLINE"
    assert subcategory == "GENERAL"
    assert channel == "ALL"
    assert scope == "CATALOG_ONLY"
    assert conditions == []


def test_insurance_feature_general_reward_expands_with_body_text():
    from extractor.promotion_rules import expand_general_reward_promotions

    card = fubon_real.CardRecord(
        card_code="FUBON_INSURANCE",
        card_name="富邦鑽保卡",
        detail_url="https://example.com/insurance",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    promotions = fubon_real._extract_insurance_feature_promotions(card, "GENERAL")
    general_promo = [p for p in promotions if float(p["cashbackValue"]) == 0.7][0]

    # _body should be preserved for expansion
    assert "_body" in general_promo

    expanded = expand_general_reward_promotions(
        general_promo, general_promo["title"], general_promo["_body"]
    )

    categories = {p["category"] for p in expanded}
    assert "DINING" in categories
    assert "SHOPPING" in categories
    assert "ONLINE" in categories
    assert "OVERSEAS" in categories
    assert len(expanded) >= 7


def test_extract_reward_falls_back_to_body_when_title_parses_zero():
    reward = fubon_real._extract_reward(
        "五大場域任一通路單筆消費達10,000元計算，每季活動期間每戶回饋乙次，上限50",
        "五大場域任一通路單筆消費達10,000元計算，每季活動期間每戶回饋乙次，上限500元刷卡金。",
    )

    assert reward == {"type": "FIXED", "value": 500.0}
