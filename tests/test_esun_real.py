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

    conditions = append_inferred_payment_method_conditions(
        "ONLINE",
        "MOBILE_PAY",
        [],
        "LINE Pay 3%",
        "LINE Pay 行動支付 3%",
    )

    assert canonicalize_subcategory("ONLINE", "MOBILE_PAY", conditions) == "GENERAL"
    assert any(
        condition["type"] == "PAYMENT_METHOD" and condition["value"] == "MOBILE_PAY"
        for condition in conditions
    )


def test_unicard_hundred_store_department_cluster_is_not_general():
    from extractor.esun_real import UNICARD_HUNDRED_STORE_CLUSTER_META

    assert UNICARD_HUNDRED_STORE_CLUSTER_META["國內百貨"]["subcategory"] == "DEPARTMENT"


def test_unicard_hundred_store_variant_filters_split_mixed_clusters():
    from extractor.esun_real import _filter_unicard_variant_labels

    transport_labels = ["台灣中油(直營店)", "台鐵", "高鐵", "Uber", "yoxi", "55688(台灣大車隊、機場接送)"]
    travel_labels = ["中華航空", "長榮航空", "Trip.com", "Booking.com", "Klook", "Agoda"]

    gas_labels = _filter_unicard_variant_labels(transport_labels, match_tokens=("台灣中油", "中油", "全國加油"))
    transit_labels = _filter_unicard_variant_labels(transport_labels, match_tokens=("台鐵", "高鐵"))
    rideshare_labels = _filter_unicard_variant_labels(transport_labels, match_tokens=("UBER", "YOXI", "55688"))
    airline_labels = _filter_unicard_variant_labels(travel_labels, match_tokens=("中華航空", "長榮航空"))
    platform_labels = _filter_unicard_variant_labels(
        travel_labels,
        exclude_tokens=("中華航空", "長榮航空", "日本航空", "台灣虎航", "樂桃航空", "酷航"),
    )

    assert gas_labels == ["台灣中油(直營店)"]
    assert transit_labels == ["台鐵", "高鐵"]
    assert rideshare_labels == ["Uber", "yoxi", "55688(台灣大車隊、機場接送)"]
    assert airline_labels == ["中華航空", "長榮航空"]
    assert platform_labels == ["Trip.com", "Booking.com", "Klook", "Agoda"]


def test_unicard_hundred_store_variant_filters_split_remaining_general_clusters():
    from extractor.esun_real import _filter_unicard_variant_labels

    selected_labels = ["Apple直營店", "小米台灣", "全國電子", "燦坤", "迪卡儂"]
    grocery_labels = ["家樂福", "屈臣氏", "康是美", "特力屋", "HOLA", "hoi好好生活", "UNIQLO", "NET", "大樹藥局", "丁丁藥妝"]
    esg_labels = ["玉山Wallet愛心捐款-單筆捐款", "玉山Wallet愛心捐款-定期定額", "特斯拉", "Gogoro電池資費", "YouBike 2.0"]

    electronics = _filter_unicard_variant_labels(selected_labels, match_tokens=("APPLE", "小米", "全國電子", "燦坤"))
    sporting = _filter_unicard_variant_labels(selected_labels, match_tokens=("迪卡儂",))
    drugstore = _filter_unicard_variant_labels(grocery_labels, match_tokens=("屈臣氏", "康是美", "大樹藥局", "丁丁藥妝"))
    home_living = _filter_unicard_variant_labels(grocery_labels, match_tokens=("特力屋", "HOLA", "HOI"))
    apparel = _filter_unicard_variant_labels(grocery_labels, match_tokens=("UNIQLO", "NET"))
    charging = _filter_unicard_variant_labels(esg_labels, match_tokens=("特斯拉", "GOGORO"))
    transit = _filter_unicard_variant_labels(esg_labels, match_tokens=("YOUBIKE",))
    donation = _filter_unicard_variant_labels(esg_labels, match_tokens=("愛心捐款",))

    assert electronics == ["Apple直營店", "小米台灣", "全國電子", "燦坤"]
    assert sporting == ["迪卡儂"]
    assert drugstore == ["屈臣氏", "康是美", "大樹藥局", "丁丁藥妝"]
    assert home_living == ["特力屋", "HOLA", "hoi好好生活"]
    assert apparel == ["UNIQLO", "NET"]
    assert charging == ["特斯拉", "Gogoro電池資費"]
    assert transit == ["YouBike 2.0"]
    assert donation == ["玉山Wallet愛心捐款-單筆捐款", "玉山Wallet愛心捐款-定期定額"]


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


def test_herbalife_general_reward_recategorized_for_expansion():
    from extractor.esun_real import _expand_card_specific_promotions

    promotion = {
        "title": "賀寶芙悠遊聯名卡 累積玉山e point",
        "category": "ONLINE",
        "subcategory": "SUBSCRIPTION",
        "channel": "ONLINE",
        "cashbackType": "POINTS",
        "cashbackValue": "0.20",
        "conditions": [],
    }

    result = _expand_card_specific_promotions(
        "ESUN_HERBALIFE_CARD",
        "累積玉山e point",
        "新增一般消費享0.2% 玉山e point回饋。",
        promotion,
    )

    assert len(result) == 1
    assert result[0]["category"] == "OTHER"
    assert result[0]["subcategory"] == "GENERAL"
    assert result[0]["channel"] == "ALL"
