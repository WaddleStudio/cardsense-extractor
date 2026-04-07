import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.promotion_rules import append_inferred_cobranded_conditions


def test_cobranded_adds_chungyo_retail_chain():
    conditions = append_inferred_cobranded_conditions(
        "中友百貨悠遊聯名卡 最高再享1.5%回饋",
        "於中友百貨館內消費享最高1.5%回饋",
        [],
    )
    assert any(
        c["type"] == "RETAIL_CHAIN" and c["value"] == "CHUNGYO"
        for c in conditions
    )


def test_cobranded_adds_metrowalk_retail_chain():
    conditions = append_inferred_cobranded_conditions(
        "大江聯名卡 天天饗最高12%回饋",
        "於大江購物中心餐飲消費享最高12%回饋",
        [],
    )
    assert any(
        c["type"] == "RETAIL_CHAIN" and c["value"] == "METROWALK"
        for c in conditions
    )


def test_cobranded_adds_chungyo_from_title():
    """General e-point rewards mention 中友百貨 in title — condition is added."""
    conditions = append_inferred_cobranded_conditions(
        "中友百貨悠遊聯名卡 玉山e point（一般消費）",
        "一般消費享玉山e point回饋",
        [],
    )
    assert any(
        c["type"] == "RETAIL_CHAIN" and c["value"] == "CHUNGYO"
        for c in conditions
    )


def test_cobranded_does_not_duplicate_existing_condition():
    existing = [{"type": "RETAIL_CHAIN", "value": "CHUNGYO", "label": "中友百貨"}]
    conditions = append_inferred_cobranded_conditions(
        "中友百貨悠遊聯名卡 13號卡友日",
        "中友百貨館內消費",
        existing,
    )
    chungyo_count = sum(1 for c in conditions if c["value"] == "CHUNGYO")
    assert chungyo_count == 1


from extractor.promotion_rules import append_inferred_date_conditions


def test_date_day_of_month_13():
    conditions = append_inferred_date_conditions(
        "中友百貨悠遊聯名卡 13號卡友日",
        "每月13號於中友百貨館內累積消費滿3,000元",
        [],
    )
    assert any(
        c["type"] == "DAY_OF_MONTH" and c["value"] == "13"
        for c in conditions
    )


def test_date_day_of_month_pattern_meiyue():
    conditions = append_inferred_date_conditions(
        "每月15號回饋日",
        "每月15號消費享雙倍回饋",
        [],
    )
    assert any(
        c["type"] == "DAY_OF_MONTH" and c["value"] == "15"
        for c in conditions
    )


def test_date_day_of_week_wednesday():
    conditions = append_inferred_date_conditions(
        "每週三加碼回饋",
        "每週三於指定通路消費享加碼",
        [],
    )
    assert any(
        c["type"] == "DAY_OF_WEEK" and c["value"] == "WED"
        for c in conditions
    )


def test_date_day_of_week_weekend():
    conditions = append_inferred_date_conditions(
        "週末限定回饋",
        "週末於百貨消費享加碼回饋",
        [],
    )
    assert any(
        c["type"] == "DAY_OF_WEEK" and c["value"] == "WEEKEND"
        for c in conditions
    )


def test_date_day_of_week_friday_saturday():
    conditions = append_inferred_date_conditions(
        "週五六加碼",
        "每週五、六消費享加碼回饋",
        [],
    )
    assert any(c["type"] == "DAY_OF_WEEK" and c["value"] == "FRI" for c in conditions)
    assert any(c["type"] == "DAY_OF_WEEK" and c["value"] == "SAT" for c in conditions)


def test_date_no_match_returns_unchanged():
    existing = [{"type": "TEXT", "value": "test", "label": "test"}]
    conditions = append_inferred_date_conditions(
        "一般消費回饋",
        "享1%回饋",
        existing,
    )
    assert conditions == existing


def test_date_does_not_duplicate():
    existing = [{"type": "DAY_OF_MONTH", "value": "13", "label": "每月13號"}]
    conditions = append_inferred_date_conditions(
        "13號卡友日",
        "每月13號消費",
        existing,
    )
    dom_count = sum(1 for c in conditions if c["type"] == "DAY_OF_MONTH" and c["value"] == "13")
    assert dom_count == 1
