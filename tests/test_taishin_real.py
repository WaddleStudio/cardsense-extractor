from __future__ import annotations

import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Card listing
# ---------------------------------------------------------------------------

def test_list_taishin_cards_discovers_cards_from_listing_fixture():
    from extractor.taishin_real import list_taishin_cards

    html = _load_fixture("taishin_listing.html")

    with patch("extractor.ingest.fetch_with_playwright", return_value=html):
        cards = list_taishin_cards()

    assert len(cards) >= 10, f"Expected >= 10 cards, got {len(cards)}"
    for card in cards:
        assert card.card_code.startswith("TAISHIN_"), f"card_code should start with TAISHIN_: {card.card_code}"
        assert card.detail_url.startswith("https://www.taishinbank.com.tw"), f"detail_url bad: {card.detail_url}"

    # Verify known card mapping produces semantic card_codes
    richart = next((c for c in cards if "Richart" in c.card_name), None)
    assert richart is not None, "Should find Richart card"
    assert richart.card_code == "TAISHIN_RICHART", f"Richart card_code should be TAISHIN_RICHART, got {richart.card_code}"


# ---------------------------------------------------------------------------
# Promotion extraction
# ---------------------------------------------------------------------------

def test_extract_card_promotions_from_detail_fixture():
    from extractor.taishin_real import CardRecord, extract_card_promotions

    html = _load_fixture("taishin_card_cg003.html")

    card = CardRecord(
        card_code="TAISHIN_CATHAY_PACIFIC",
        card_name="國泰航空翱翔鈦金卡/鈦金卡",
        detail_url="https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg003/card001/",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    with patch("extractor.ingest.fetch_with_playwright", return_value=html):
        enriched, promotions = extract_card_promotions(card)

    assert len(promotions) >= 1, f"Expected >= 1 promotion, got {len(promotions)}"

    for promo in promotions:
        assert promo["bankCode"] == "TAISHIN"
        assert promo["cardCode"] == "TAISHIN_CATHAY_PACIFIC"
        assert promo["cashbackValue"] > 0, f"cashbackValue should be > 0: {promo}"
        assert promo["validFrom"], f"validFrom missing: {promo}"
        assert promo["validUntil"], f"validUntil missing: {promo}"
        assert promo["category"], f"category missing: {promo}"
        assert promo["channel"], f"channel missing: {promo}"


def test_extract_card_promotions_pulls_extra_richart_marketing_pages():
    from extractor.taishin_real import CardRecord, extract_card_promotions

    detail_html = """
    <html>
      <body>
        <h2>優惠活動</h2>
        <h3>Hotels.com回饋最高8.3%，玩旅刷Richart卡</h3>
        <p>2026/1/1~2026/6/30 於Hotels.com預訂指定飯店，刷台新Richart卡，切換「玩旅刷」最高8.3%台新Point(信用卡)回饋。</p>
      </body>
    </html>
    """
    guide_html = """
    <html>
      <body>
        <a href="https://mkp.taishinbank.com.tw/tscccms/promotion/detail/WM_DAILY">天天刷活動</a>
        <a href="https://mkp.taishinbank.com.tw/TsCms/marketing/expose/WM_DIGITAL/index.html">數趣刷活動</a>
      </body>
    </html>
    """
    daily_html = """
    <html>
      <body>
        <h1>高鐵臺鐵 享最高3.3%，天天刷Richart卡！</h1>
        <p>活動期間 2026/1/1~2026/6/30</p>
        <p>刷台新Richart卡，於高鐵、臺鐵購票，切換「天天刷」方案，享最高3.3%台新Point(信用卡)回饋！</p>
      </body>
    </html>
    """
    digital_html = """
    <html>
      <body>
        <h1>指定影音平台最高4.8%，數趣刷Richart卡！</h1>
        <p>活動期間 2026/1/1~2026/6/30</p>
        <p>刷台新Richart卡訂閱指定影音平台，切換「數趣刷」方案，享最高4.8%台新Point(信用卡)回饋。</p>
      </body>
    </html>
    """

    card = CardRecord(
        card_code="TAISHIN_RICHART",
        card_name="台新Richart卡",
        detail_url="https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg047/card001/",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    html_by_url = {
        card.detail_url: detail_html,
        "https://www.taishinbank.com.tw/TSB/personal/credit/discount/life/": guide_html,
        "https://www.taishinbank.com.tw/TSB/personal/digital/E-Payment/Electronic-Payment/introduction/": "<html><body></body></html>",
        "https://mkp.taishinbank.com.tw/tscccms/promotion/detail/WM_DAILY": daily_html,
        "https://mkp.taishinbank.com.tw/TsCms/marketing/expose/WM_DIGITAL/index.html": digital_html,
    }

    def _mock_fetch(url: str) -> str:
        return html_by_url[url]

    with patch("extractor.ingest.fetch_with_playwright", side_effect=_mock_fetch):
        enriched, promotions = extract_card_promotions(card)

    assert enriched.card_code == "TAISHIN_RICHART"
    assert len(promotions) >= 2
    assert any(promo["sourceUrl"].endswith("WM_DAILY") for promo in promotions)
    assert any("天天刷" in promo["title"] for promo in promotions)
    assert any("數趣刷" in promo["title"] for promo in promotions)
    assert all(promo["cardCode"] == "TAISHIN_RICHART" for promo in promotions)
    assert any(promo.get("planId") == "TAISHIN_RICHART_DAILY" for promo in promotions)
    assert any(promo.get("planId") == "TAISHIN_RICHART_DIGITAL" for promo in promotions)


def test_extract_card_promotions_skips_richart_marketing_without_plan_signal():
    from extractor.taishin_real import CardRecord, extract_card_promotions

    detail_html = """
    <html>
      <body>
        <h2>優惠活動</h2>
      </body>
    </html>
    """
    guide_html = """
    <html>
      <body>
        <a href="https://mkp.taishinbank.com.tw/tscccms/promotion/detail/WM_GENERIC">一般活動</a>
      </body>
    </html>
    """
    generic_html = """
    <html>
      <body>
        <h1>台新Richart卡 春季滿額抽獎</h1>
        <p>活動期間 2026/1/1~2026/6/30</p>
        <p>刷台新Richart卡享抽獎資格。</p>
      </body>
    </html>
    """

    card = CardRecord(
        card_code="TAISHIN_RICHART",
        card_name="台新Richart卡",
        detail_url="https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg047/card001/",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    html_by_url = {
        card.detail_url: detail_html,
        "https://www.taishinbank.com.tw/TSB/personal/credit/discount/life/": guide_html,
        "https://www.taishinbank.com.tw/TSB/personal/digital/E-Payment/Electronic-Payment/introduction/": "<html><body></body></html>",
        "https://mkp.taishinbank.com.tw/tscccms/promotion/detail/WM_GENERIC": generic_html,
    }

    def _mock_fetch(url: str) -> str:
        return html_by_url[url]

    with patch("extractor.ingest.fetch_with_playwright", side_effect=_mock_fetch):
        _, promotions = extract_card_promotions(card)

    assert promotions == []


def test_resolve_richart_plan_id_prefers_body_signal_over_category_fallback():
    from extractor.taishin_real import _resolve_richart_plan_id

    plan_id = _resolve_richart_plan_id(
        "TAISHIN_RICHART",
        "ONLINE",
        "回饋方式",
        "台新Richart卡切換「玩旅刷」最高3.3%回饋於正附卡消費入帳後回饋。",
    )

    assert plan_id == "TAISHIN_RICHART_TRAVEL"


def test_resolve_richart_plan_id_prefers_travel_signal_over_generic_payment_terms():
    from extractor.taishin_real import _resolve_richart_plan_id

    plan_id = _resolve_richart_plan_id(
        "TAISHIN_RICHART",
        "ONLINE",
        "八大訂房網最高現折18%",
        "Richart卡享最高3.3%回饋，指定訂房平台 Hotels.com、Agoda、Booking.com 適用，並提及台新Pay綁卡付款。",
    )

    assert plan_id == "TAISHIN_RICHART_TRAVEL"


def test_extract_card_promotions_applies_plan_subcategory_hints_for_richart_marketing():
    from extractor.taishin_real import CardRecord, _extract_marketing_promotion

    html = """
    <html>
      <body>
        <h1>Richart LINE Pay up to 3.8%</h1>
        <p>2026/1/1~2026/6/30</p>
        <p>LINE Pay payment reward 3.8% with Richart Pay plan.</p>
      </body>
    </html>
    """

    card = CardRecord(
        card_code="TAISHIN_RICHART",
        card_name="Richart Card",
        detail_url="https://example.com/richart",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    promotion = _extract_marketing_promotion(card, html, "https://example.com/promo")

    assert promotion is not None
    assert promotion["planId"] == "TAISHIN_RICHART_PAY"
    assert promotion["subcategory"] == "GENERAL"
    assert any(
        condition["type"] == "PAYMENT_METHOD" and condition["value"] == "MOBILE_PAY"
        for condition in promotion["conditions"]
    )
    assert any(
        condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "LINE_PAY"
        for condition in promotion["conditions"]
    )
    assert any(
        condition["type"] == "TEXT" and condition["value"] == "RICHART_BENEFIT_TIER_REQUIRED"
        for condition in promotion["conditions"]
    )


def test_richart_plan_hint_appends_travel_platform_merchants():
    from extractor.taishin_real import _append_richart_plan_conditions

    conditions = _append_richart_plan_conditions("TAISHIN_RICHART_TRAVEL", "TRAVEL_PLATFORM", [])

    assert any(condition["type"] == "MERCHANT" and condition["value"] == "AGODA" for condition in conditions)
    assert any(condition["type"] == "MERCHANT" and condition["value"] == "TRIP_COM" for condition in conditions)


def test_richart_plan_hint_appends_streaming_merchants():
    from extractor.taishin_real import _append_richart_plan_conditions

    conditions = _append_richart_plan_conditions("TAISHIN_RICHART_DIGITAL", "STREAMING", [])

    assert any(condition["type"] == "MERCHANT" and condition["value"] == "NETFLIX" for condition in conditions)
    assert any(
        condition["type"] == "MERCHANT" and condition["value"] == "DISNEY_PLUS"
        for condition in conditions
    )


def test_richart_tier_hint_appends_level_marker_for_standard_plan_rate():
    from extractor.taishin_real import _append_richart_tier_conditions

    conditions = _append_richart_tier_conditions("TAISHIN_RICHART_DIGITAL", 3.3, [])

    assert any(
        condition["type"] == "TEXT" and condition["value"] == "RICHART_BENEFIT_TIER_REQUIRED"
        for condition in conditions
    )


def test_richart_tier_hint_skips_non_standard_bonus_rate():
    from extractor.taishin_real import _append_richart_tier_conditions

    conditions = _append_richart_tier_conditions("TAISHIN_RICHART_DIGITAL", 4.8, [])

    assert conditions == []


def test_resolve_richart_plan_id_does_not_affect_other_cards():
    from extractor.taishin_real import _resolve_richart_plan_id

    plan_id = _resolve_richart_plan_id(
        "TAISHIN_GOGORO",
        "ONLINE",
        "LINE Pay 最高 3%",
        "一般活動內容",
    )

    assert plan_id is None


def test_postprocess_taishin_promotions_downgrades_installment_offers():
    from extractor.taishin_real import CardRecord, _postprocess_taishin_promotions

    card = CardRecord(
        card_code="TAISHIN_JKOPAY",
        card_name="街口聯名卡",
        detail_url="https://example.com/jko",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    promotions = _postprocess_taishin_promotions(
        card,
        [
            {
                "title": "街口聯名卡 新卡專屬 單筆分期享 1.88% 限時優利",
                "summary": "活動期間內單筆分期 1.88% 優惠利率",
                "category": "OTHER",
                "subcategory": "GENERAL",
                "channel": "ALL",
                "recommendationScope": "RECOMMENDABLE",
            }
        ],
    )

    assert promotions[0]["recommendationScope"] == "CATALOG_ONLY"
    assert promotions[0]["channel"] == "ALL"


def test_postprocess_taishin_promotions_downgrades_rose_plan_rows_to_catalog_only():
    from extractor.taishin_real import CardRecord, _postprocess_taishin_promotions

    card = CardRecord(
        card_code="TAISHIN_ROSE",
        card_name="玫瑰卡",
        detail_url="https://example.com/rose",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    promotions = _postprocess_taishin_promotions(
        card,
        [
            {
                "title": "玫瑰卡 NEW！指定套餐方案",
                "summary": "百貨｜餐廳｜電信｜保費最高 1.2%",
                "category": "DINING",
                "subcategory": "RESTAURANT",
                "channel": "OFFLINE",
                "recommendationScope": "FUTURE_SCOPE",
            }
        ],
    )

    assert promotions[0]["recommendationScope"] == "CATALOG_ONLY"
    assert promotions[0]["category"] == "OTHER"
    assert promotions[0]["subcategory"] == "GENERAL"


def test_extract_px_mart_feature_promotions_adds_store_and_full_pay_rows():
    from extractor.taishin_real import CardRecord, _extract_px_mart_feature_promotions

    card = CardRecord(
        card_code="TAISHIN_PX_MART",
        card_name="大全聯信用卡",
        detail_url="https://example.com/px",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    lines = [
        "大全聯JCB卡最高8.5% 福利點限時送",
        "2026/4/1-6/30 大全聯JCB卡限時加碼活動又來囉！不限新舊戶，申辦亦可享福利點加碼送！",
        "【大全聯限定】 搭配卡友日抵用券 最高 8.5 %",
        "大全聯店內最高回饋8.5%",
        "【全支付店外】最高1.5%，一般吃喝玩買真好用",
        "*大全聯信用卡福利卡號於開卡後3個日曆日生效，生效後須連結 綁定 PX Pay 方享回饋資格，未綁定則無回饋",
        "卡片分期享 0.88%限時優利",
    ]

    promotions = _extract_px_mart_feature_promotions(card, lines)

    assert len(promotions) == 2
    store_promo = next(promo for promo in promotions if "大全聯店內消費" in promo["title"])
    full_pay_promo = next(promo for promo in promotions if "全支付店外消費" in promo["title"])

    assert store_promo["subcategory"] == "SUPERMARKET"
    assert any(condition["type"] == "RETAIL_CHAIN" and condition["value"] == "PXMART" for condition in store_promo["conditions"])
    assert any(condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "全支付" for condition in full_pay_promo["conditions"])


def test_extract_jkopay_feature_promotions_does_not_force_payment_for_generic_app_copy():
    from extractor.taishin_real import CardRecord, _extract_jkopay_feature_promotions

    card = CardRecord(
        card_code="TAISHIN_JKOPAY",
        card_name="街口聯名卡",
        detail_url="https://example.com/jko",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )

    lines = [
        "街口豬富卡2026年權益 : 精選通路最高3.5%街口幣",
        "精選通路，不限交易形式(實體卡(含線上輸入卡號)、於街口支付/LINE Pay/Apple pay綁定等皆適用)，享最高 3.5 %!",
        "【活動已結束】旅遊/娛樂/交通/百貨/藥妝/外送/餐飲最高3.5%",
        "【街口APP繳費 最高 2.15 %】",
        "基本回饋：街口APP繳費享基本 0.15 %回饋無上限",
        "滿額升級：當月街口APP繳費交易滿NT$1,000，升級再享2%回饋",
        "【一般消費享 1 %街口幣 無上限】",
        "一般消費，不限交易形式(實體卡(含線上輸入卡號)、於街口支付/LINE Pay/Apple pay綁定等皆適用)，享 1 %街口幣無上限",
        "(1)精選通路最高3.5%優惠說明如下，其中精選加碼合計每月上限10,000元街口幣",
    ]

    promotions = _extract_jkopay_feature_promotions(card, lines)

    bill_pay = next(promo for promo in promotions if "街口APP繳費" in promo["title"])
    selected = next(promo for promo in promotions if "精選通路最高3.5%" in promo["title"])

    assert not any(condition["type"] == "PAYMENT_PLATFORM" for condition in bill_pay["conditions"])
    assert not any(condition["type"] == "PAYMENT_PLATFORM" for condition in selected["conditions"])
