import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.esun_real import CardRecord, _extract_unicard_hundred_store_promotions


def test_extract_unicard_hundred_store_promotions_parses_official_clusters():
    lines = [
        "百大指定消費列表",
        "2025/10/1~2026/6/30適用百大指定消費列表如下：",
        "類別",
        "指定百大指定消費",
        "行動支付",
        "玉山Wallet電子支付、LINE Pay、全支付、街口支付",
        "電商平台",
        "momo購物網、蝦皮購物、淘寶網、Coupang酷澎",
        "國外實體",
        "日本、韓國、美國",
        "百大指定消費列表注意事項",
    ]
    card = CardRecord(
        card_code="ESUN_UNICARD",
        card_name="玉山Unicard",
        detail_url="https://www.esunbank.com/zh-tw/personal/credit-card/intro/bank-card/unicard",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    promotions = _extract_unicard_hundred_store_promotions(lines, card, "GENERAL")

    assert len(promotions) == 3
    mobile_pay = next(promo for promo in promotions if promo["title"].endswith("行動支付"))
    ecommerce = next(promo for promo in promotions if promo["title"].endswith("電商平台"))
    overseas = next(promo for promo in promotions if promo["title"].endswith("國外實體"))

    assert mobile_pay["subcategory"] == "GENERAL"
    assert mobile_pay["recommendationScope"] == "CATALOG_ONLY"
    assert any(
        condition["type"] == "PAYMENT_METHOD" and condition["value"] == "MOBILE_PAY"
        for condition in mobile_pay["conditions"]
    )
    assert any(condition["value"] == "LINE_PAY" for condition in mobile_pay["conditions"])
    assert ecommerce["subcategory"] == "ECOMMERCE"
    assert any(condition["value"] == "COUPANG酷澎" for condition in ecommerce["conditions"])
    assert any(condition["type"] == "LOCATION_ONLY" and condition["value"] == "日本" for condition in overseas["conditions"])
