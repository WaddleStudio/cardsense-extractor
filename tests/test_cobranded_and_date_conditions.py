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
