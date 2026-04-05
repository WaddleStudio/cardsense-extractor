import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.promotion_rules import append_inferred_payment_method_conditions, append_inferred_subcategory_conditions


def test_append_inferred_subcategory_conditions_adds_ecommerce_platform_condition():
    conditions = append_inferred_subcategory_conditions(
        "PChome加碼3.8%",
        "使用玉山Unicard至PChome消費，享加碼 3.8% 回饋。",
        "ONLINE",
        "ECOMMERCE",
        [],
    )

    assert any(
        condition["type"] == "ECOMMERCE_PLATFORM" and condition["value"] == "PCHOME_24H"
        for condition in conditions
    )


def test_append_inferred_subcategory_conditions_adds_mobile_pay_platform_condition():
    conditions = append_inferred_subcategory_conditions(
        "LINE Pay一般消費加碼",
        "綁定LINE Pay交易享加碼回饋。",
        "ONLINE",
        "MOBILE_PAY",
        [],
    )

    assert any(
        condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "LINE_PAY"
        for condition in conditions
    )


def test_append_inferred_payment_method_conditions_adds_mobile_pay_group_condition():
    conditions = append_inferred_payment_method_conditions(
        "ONLINE",
        "MOBILE_PAY",
        [],
    )

    assert conditions == [
        {"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": "行動支付"},
    ]
