from extractor.promotion_rules import build_conditions, classify_recommendation_scope, extract_reward, infer_channel


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