import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.promotion_rules import (
    append_inferred_payment_method_conditions,
    append_inferred_subcategory_conditions,
    sanitize_payment_conditions,
)


def test_append_inferred_subcategory_conditions_adds_ecommerce_platform_condition():
    conditions = append_inferred_subcategory_conditions(
        "PChome 3.8%",
        "Unicard 於 PChome 消費享 3.8% 回饋",
        "ONLINE",
        "ECOMMERCE",
        [],
    )

    assert any(
        condition["type"] == "VENUE" and condition["value"] == "PCHOME_24H"
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
        condition["type"] == "PAYMENT" and condition["value"] == "LINE_PAY"
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
        condition["type"] == "VENUE" and condition["value"] == "AGODA"
        for condition in conditions
    )
    assert any(
        condition["type"] == "VENUE" and condition["value"] == "TRIP_COM"
        for condition in conditions
    )


def test_append_inferred_subcategory_conditions_adds_poya_drugstore_condition():
    conditions = append_inferred_subcategory_conditions(
        "寶雅指定通路 5%",
        "於 POYA 寶雅門市消費享加碼回饋。",
        "SHOPPING",
        "DRUGSTORE",
        [],
    )

    assert any(
        condition["type"] == "VENUE" and condition["value"] == "POYA"
        for condition in conditions
    )


def test_append_inferred_subcategory_conditions_adds_high_frequency_ecommerce_conditions():
    conditions = append_inferred_subcategory_conditions(
        "momo PChome 樂天 最高 5%",
        "指定平台含蝦皮、博客來、東森購物與 Amazon。",
        "ONLINE",
        "ECOMMERCE",
        [],
    )

    values = {condition["value"] for condition in conditions}
    assert {"MOMO", "SHOPEE", "BOOKS_COM_TW", "RAKUTEN", "ETMALL", "AMAZON"}.issubset(values)


def test_append_inferred_subcategory_conditions_adds_dining_merchant_conditions():
    restaurant_conditions = append_inferred_subcategory_conditions(
        "速食與集團餐飲加碼",
        "麥當勞、肯德基、摩斯、王品與瓦城適用。",
        "DINING",
        "RESTAURANT",
        [],
    )
    cafe_conditions = append_inferred_subcategory_conditions(
        "咖啡通路加碼",
        "星巴克、路易莎與 cama 適用。",
        "DINING",
        "CAFE",
        [],
    )

    restaurant_values = {condition["value"] for condition in restaurant_conditions}
    cafe_values = {condition["value"] for condition in cafe_conditions}
    assert {"MCDONALD", "KFC", "MOS_BURGER", "WOWPRIME", "THAI_TOWN"}.issubset(restaurant_values)
    assert {"STARBUCKS", "LOUISA", "CAMA"}.issubset(cafe_values)


def test_append_inferred_subcategory_conditions_adds_grocery_and_shopping_conditions():
    grocery_conditions = append_inferred_subcategory_conditions(
        "超市量販通路",
        "全聯、大全聯、家樂福、大潤發、Costco 與 LOPIA 適用。",
        "GROCERY",
        "SUPERMARKET",
        [],
    )
    convenience_conditions = append_inferred_subcategory_conditions(
        "四大超商加碼",
        "7-ELEVEN、全家、萊爾富與 OK mart 適用。",
        "GROCERY",
        "CONVENIENCE_STORE",
        [],
    )
    apparel_conditions = append_inferred_subcategory_conditions(
        "服飾與運動通路",
        "UNIQLO、NET、GU 與迪卡儂適用。",
        "SHOPPING",
        "APPAREL",
        [],
    )
    sporting_conditions = append_inferred_subcategory_conditions(
        "運動用品通路",
        "迪卡儂 Decathlon 適用。",
        "SHOPPING",
        "SPORTING_GOODS",
        [],
    )

    grocery_values = {condition["value"] for condition in grocery_conditions}
    convenience_values = {condition["value"] for condition in convenience_conditions}
    apparel_values = {condition["value"] for condition in apparel_conditions}
    sporting_values = {condition["value"] for condition in sporting_conditions}
    assert {"PXMART", "CARREFOUR", "RT_MART", "COSTCO", "LOPIA"}.issubset(grocery_values)
    assert {"7_ELEVEN", "FAMILYMART", "HI_LIFE", "OK_MART"}.issubset(convenience_values)
    assert {"UNIQLO", "NET", "GU"}.issubset(apparel_values)
    assert "DECATHLON" in sporting_values

def test_append_inferred_payment_method_conditions_adds_mobile_pay_group_condition():
    conditions = append_inferred_payment_method_conditions(
        "ONLINE",
        "MOBILE_PAY",
        [],
        "LINE Pay 3%",
        "使用 LINE Pay 付款享 3% 回饋",
    )

    assert conditions == [
        {"type": "PAYMENT", "value": "MOBILE_PAY", "label": conditions[0]["label"]},
    ]


def test_append_inferred_subcategory_conditions_skips_negated_payment_platforms():
    conditions = append_inferred_subcategory_conditions(
        "旅遊平台回饋",
        "Apple Pay、Google Pay、LINE Pay 等綁定行動支付不適用本活動。",
        "ONLINE",
        "MOBILE_PAY",
        [],
    )

    assert conditions == []


def test_sanitize_payment_conditions_canonicalizes_aliases():
    conditions = sanitize_payment_conditions(
        "行動支付加碼",
        "玉山WALLET電子支付、街口支付享加碼回饋",
        [
            {"type": "PAYMENT", "value": "玉山WALLET電子支付", "label": "玉山WALLET電子支付"},
            {"type": "PAYMENT", "value": "街口支付", "label": "街口支付"},
            {"type": "PAYMENT", "value": "MOBILE_PAY", "label": "行動支付"},
        ],
    )

    assert any(condition["type"] == "PAYMENT" and condition["value"] == "ESUN_WALLET" for condition in conditions)
    assert any(condition["type"] == "PAYMENT" and condition["value"] == "JKOPAY" for condition in conditions)


def test_sanitize_payment_conditions_removes_negated_positive_payment_conditions():
    conditions = sanitize_payment_conditions(
        "易遊網折扣碼",
        "若以 Apple Pay、Google Pay、LINE Pay 等相關綁定行動載具支付恕無法參加。",
        [
            {"type": "PAYMENT", "value": "LINE_PAY", "label": "LINE Pay"},
            {"type": "PAYMENT", "value": "APPLE_PAY", "label": "Apple Pay"},
            {"type": "PAYMENT", "value": "MOBILE_PAY", "label": "行動支付"},
        ],
    )

    assert conditions == []
