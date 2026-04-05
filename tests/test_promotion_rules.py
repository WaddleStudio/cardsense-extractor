from extractor.promotion_rules import (
    SUBCATEGORY_SIGNALS,
    build_conditions,
    classify_recommendation_scope,
    extract_reward,
    infer_channel,
    infer_subcategory,
)


CHANNEL_SIGNALS = {
    "ONLINE": [("APP", 3), ("網站", 3), ("網購", 4), ("LINE Pay", 3)],
    "OFFLINE": [("門市", 3), ("實體", 4), ("百貨", 2)],
    "ALL": [("一般消費", 4), ("國內外一般消費", 5)],
}


def test_infer_channel_prefers_online_when_specific_signal_exists_with_all_signal():
    channel = infer_channel(
        "綁定 APP 最高 3% 回饋",
        "國內外一般消費綁定 LINE Pay 或 APP 付款享加碼。",
        CHANNEL_SIGNALS,
    )

    assert channel == "ONLINE"


def test_build_conditions_dedupes_registration_and_requirement_fragments():
    conditions = build_conditions(
        "• 需登錄活動 • 單筆滿500元享5%回饋 • 單筆滿500元享5%回饋",
        ["需年滿18歲", "需年滿18歲"],
        requires_registration=True,
    )

    assert conditions == [
        {"type": "REGISTRATION_REQUIRED", "value": "true", "label": "需登錄活動"},
        {"type": "TEXT", "value": "需年滿18歲", "label": "需年滿18歲"},
        {"type": "TEXT", "value": "單筆滿500元享5_回饋", "label": "單筆滿500元享5%回饋"},
    ]


def test_classify_recommendation_scope_marks_insurance_offer_as_future_scope():
    scope = classify_recommendation_scope("壽險保費加碼0.9%玉山e point", "持卡繳壽險保費不限金額，登錄享加碼。", "OTHER")

    assert scope == "FUTURE_SCOPE"


def test_classify_recommendation_scope_marks_service_perk_as_catalog_only():
    scope = classify_recommendation_scope("道路救援", "玉山會員享起拖費1,500元內免費優惠。", "OTHER")

    assert scope == "CATALOG_ONLY"


def test_extract_reward_ignores_threshold_percentage_without_real_reward_value():
    reward = extract_reward(
        "機場接送使用條件",
        "刷卡支付當次旅遊團費80%以上，即可免費使用乙次機場接送服務。",
    )

    assert reward is None


def test_extract_reward_ignores_threshold_amount_without_real_reward_value():
    reward = extract_reward(
        "免費機場停車優惠",
        "使用前六個月內刷卡支付當次旅遊之機票或旅遊團費金額合計達30,000元以上，即可免費使用乙次。",
    )

    assert reward is None


def test_extract_reward_skips_threshold_percentage_and_keeps_actual_reward_percentage():
    reward = extract_reward(
        "海外團費加碼",
        "刷卡支付當次旅遊團費80%以上可享1%回饋。",
    )

    assert reward == {"type": "PERCENT", "value": 1.0}


def test_extract_reward_ignores_cap_points_and_keeps_actual_percent_reward():
    reward = extract_reward(
        "每週末實體門市、寶雅線上買享13%現金回饋 週間精彩刷",
        "活動期間每卡每月回饋上限27,000點寶雅點數，點數贈送皆含原本1倍。",
    )

    assert reward == {"type": "PERCENT", "value": 13.0}


def test_extract_reward_ignores_cap_fixed_amount_and_keeps_actual_percent_reward():
    reward = extract_reward(
        "TWQR優惠專區",
        "指定實體門市消費，單筆消費不限金額，可享10%現金回饋，活動期間每月回饋上限3,000元。",
    )

    assert reward == {"type": "PERCENT", "value": 10.0}


def test_extract_reward_prefers_actual_voucher_value_over_threshold_amount():
    reward = extract_reward(
        "LOPIA超市採買享新鮮",
        "單筆消費滿888元(含)以上，贈【宏匯廣場電子禮券100元】1份。",
    )

    assert reward == {"type": "FIXED", "value": 100.0}


def test_extract_reward_prefers_discount_value_over_threshold_amount():
    reward = extract_reward(
        "KKday趣亞太",
        "單筆消費金額滿2,000元(含)，於結帳頁面輸入指定優惠碼，滿額折200元。",
    )

    assert reward == {"type": "FIXED", "value": 200.0}


def test_extract_reward_prefers_voucher_value_over_threshold_amount_without_immediate_reward_token():
    reward = extract_reward(
        "每週三卡友日",
        "每週三持玉山宏匯廣場聯名卡，當日於宏匯廣場館內單筆消費滿1,000元(含)以上，贈【宏匯廣場電子禮券100元】1份。",
    )

    assert reward == {"type": "FIXED", "value": 100.0}


def test_infer_subcategory_matches_mobile_pay_from_chinese_terms():
    subcategory = infer_subcategory(
        "玉山 U Bear 信用卡 行動支付、網路消費",
        "綁定玉山Wallet電子支付消費，同享TWQR及台灣Pay優惠",
        "ONLINE",
        SUBCATEGORY_SIGNALS,
    )

    assert subcategory == "MOBILE_PAY"


def test_infer_subcategory_matches_hotel_dining_from_hotel_terms():
    subcategory = infer_subcategory(
        "世界卡 專屬優惠 台北萬豪酒店",
        "飯店餐廳與自助餐禮遇，持卡享回饋",
        "DINING",
        SUBCATEGORY_SIGNALS,
    )

    assert subcategory == "HOTEL_DINING"


def test_infer_subcategory_matches_department_from_department_store_terms():
    subcategory = infer_subcategory(
        "新光三越百貨刷卡回饋",
        "百貨週年慶指定通路加碼",
        "SHOPPING",
        SUBCATEGORY_SIGNALS,
    )

    assert subcategory == "DEPARTMENT"


def test_infer_subcategory_matches_ecommerce_from_local_platform_terms():
    subcategory = infer_subcategory(
        "momo 網購天天買",
        "PChome、蝦皮、博客來消費回饋",
        "ONLINE",
        SUBCATEGORY_SIGNALS,
    )

    assert subcategory == "ECOMMERCE"


def test_infer_subcategory_matches_travel_platform_from_online_terms():
    subcategory = infer_subcategory(
        "Hotels.com 玩旅刷最高 8.3%",
        "Agoda、Booking、Trip.com、AIRSIM 指定通路消費回饋",
        "ONLINE",
        SUBCATEGORY_SIGNALS,
    )

    assert subcategory == "TRAVEL_PLATFORM"


def test_infer_subcategory_matches_ai_tool_terms():
    subcategory = infer_subcategory(
        "CUBE 玩數位 AI工具訂閱最高 3%",
        "ChatGPT、Claude、Cursor、Gemini、Notion、Perplexity",
        "ONLINE",
        SUBCATEGORY_SIGNALS,
    )

    assert subcategory == "AI_TOOL"


def test_infer_subcategory_matches_ev_charging_terms():
    subcategory = infer_subcategory(
        "CUBE 集精選 充電停車最高 2%",
        "U-POWER、EVOASIS、EVALUE、iCharging、uTagGo",
        "OTHER",
        SUBCATEGORY_SIGNALS,
    )

    assert subcategory == "EV_CHARGING"


def test_infer_subcategory_matches_gas_station_terms_under_transport():
    subcategory = infer_subcategory(
        "玉山Unicard 加油最高 7.5%",
        "台灣中油、全國加油、台塑石油、台亞、福懋消費回饋",
        "TRANSPORT",
        SUBCATEGORY_SIGNALS,
    )

    assert subcategory == "GAS_STATION"


def test_infer_subcategory_matches_rideshare_terms_under_transport():
    subcategory = infer_subcategory(
        "指定交通通路加碼 5%",
        "GoShare、WeMo、Uber、yoxi 消費加碼",
        "TRANSPORT",
        SUBCATEGORY_SIGNALS,
    )

    assert subcategory == "RIDESHARE"
