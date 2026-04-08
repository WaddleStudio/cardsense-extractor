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

    # 3 clusters × 3 plans = 9 promos
    assert len(promotions) == 9

    # Check plan expansion for mobile pay cluster
    mobile_pay_promos = [p for p in promotions if "行動支付" in p["title"]]
    assert len(mobile_pay_promos) == 3
    simple = next(p for p in mobile_pay_promos if p["planId"] == "ESUN_UNICARD_SIMPLE")
    flexible = next(p for p in mobile_pay_promos if p["planId"] == "ESUN_UNICARD_FLEXIBLE")
    up = next(p for p in mobile_pay_promos if p["planId"] == "ESUN_UNICARD_UP")

    assert simple["cashbackValue"] == 3.0
    assert flexible["cashbackValue"] == 3.5
    assert up["cashbackValue"] == 4.5
    assert simple["maxCashback"] == 1000
    assert up["maxCashback"] == 5000
    assert all(p["recommendationScope"] == "RECOMMENDABLE" for p in mobile_pay_promos)
    assert all(p["subcategory"] == "GENERAL" for p in mobile_pay_promos)
    assert any(
        condition["type"] == "PAYMENT" and condition["value"] == "MOBILE_PAY"
        for condition in simple["conditions"]
    )
    assert any(condition["value"] == "LINE_PAY" for condition in simple["conditions"])

    # Check ecommerce cluster
    ecommerce_promos = [p for p in promotions if "電商平台" in p["title"]]
    assert len(ecommerce_promos) == 3
    assert all(p["subcategory"] == "ECOMMERCE" for p in ecommerce_promos)
    assert any(condition["value"] == "COUPANG酷澎" for condition in ecommerce_promos[0]["conditions"])

    # Check overseas cluster
    overseas_promos = [p for p in promotions if "國外實體" in p["title"]]
    assert len(overseas_promos) == 3
    assert any(condition["type"] == "LOCATION_ONLY" and condition["value"] == "日本" for condition in overseas_promos[0]["conditions"])
