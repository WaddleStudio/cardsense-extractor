import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.promotion_rules import append_inferred_payment_method_conditions, append_inferred_subcategory_conditions


def test_append_inferred_subcategory_conditions_adds_ecommerce_platform_condition():
    conditions = append_inferred_subcategory_conditions(
        "PChome 3.8%",
        "Unicard 於 PChome 消費享 3.8% 回饋",
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
        "LINE Pay 指定通路回饋",
        "使用 LINE Pay 消費可享加碼回饋",
        "ONLINE",
        "MOBILE_PAY",
        [],
    )

    assert any(
        condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "LINE_PAY"
        for condition in conditions
    )


def test_append_inferred_subcategory_conditions_adds_travel_platform_merchant_condition():
    conditions = append_inferred_subcategory_conditions(
        "Agoda 訂房最高 8%",
        "Trip.com、Klook、KKday 與 Agoda 指定通路消費回饋",
        "ONLINE",
        "TRAVEL_PLATFORM",
        [],
    )

    assert any(
        condition["type"] == "MERCHANT" and condition["value"] == "AGODA"
        for condition in conditions
    )
    assert any(
        condition["type"] == "MERCHANT" and condition["value"] == "TRIP_COM"
        for condition in conditions
    )


def test_append_inferred_payment_method_conditions_adds_mobile_pay_group_condition():
    conditions = append_inferred_payment_method_conditions(
        "ONLINE",
        "MOBILE_PAY",
        [],
    )

    assert conditions == [
        {"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": conditions[0]["label"]},
    ]
