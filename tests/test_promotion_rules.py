from extractor.promotion_rules import build_conditions, infer_channel


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