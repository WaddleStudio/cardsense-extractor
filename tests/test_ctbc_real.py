import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.ctbc_real import _refine_ctbc_promotion


def test_ctbc_sogo_store_promo_keeps_only_positive_payment_platforms_and_store_shape():
    category, subcategory, channel, scope, conditions = _refine_ctbc_promotion(
        card_code="CTBC_C_CS",
        title="店內消費最高3%",
        body=(
            "店內消費最高3%活動限以實體卡刷卡，或透過Apple Pay、Google Pay、LINE Pay、"
            "HAPPY GO PAY成功綁定支付，方得享有回饋資格。"
            "國外實體商店消費定義：包括以實體卡、Apple Pay、Google Pay、Samsung Pay於實體商店支付。"
        ),
        category="ONLINE",
        subcategory="GENERAL",
        channel="ALL",
        recommendation_scope="RECOMMENDABLE",
        requires_registration=False,
        conditions=[
            {"type": "PAYMENT_PLATFORM", "value": "LINE_PAY", "label": "LINE Pay"},
            {"type": "PAYMENT_PLATFORM", "value": "APPLE_PAY", "label": "Apple Pay"},
            {"type": "PAYMENT_PLATFORM", "value": "GOOGLE_PAY", "label": "Google Pay"},
            {"type": "PAYMENT_PLATFORM", "value": "SAMSUNG_PAY", "label": "Samsung Pay"},
            {"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": "行動支付"},
        ],
    )

    assert category == "SHOPPING"
    assert subcategory == "DEPARTMENT"
    assert channel == "OFFLINE"
    assert scope == "RECOMMENDABLE"
    assert any(condition["type"] == "RETAIL_CHAIN" and condition["value"] == "SOGO" for condition in conditions)
    assert any(condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "HAPPY_GO_PAY" for condition in conditions)
    assert any(condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "LINE_PAY" for condition in conditions)
    assert not any(condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "SAMSUNG_PAY" for condition in conditions)
    assert not any(condition["type"] == "PAYMENT_METHOD" for condition in conditions)


def test_ctbc_sogo_welcome_gift_promo_drops_false_positive_payment_conditions():
    _, _, _, scope, conditions = _refine_ctbc_promotion(
        card_code="CTBC_C_CS",
        title="核卡後 30天內於【遠東SOGO百貨即享券專區】任刷一筆，加贈",
        body=(
            "SOGO即享券200元。"
            "新戶或新卡於核卡30日內刷卡達檻即可獲得回饋。"
            "卡種排序原則為【財管鼎鑽>遠東SOGO>LINE Pay>中油>和泰】。"
        ),
        category="ONLINE",
        subcategory="GENERAL",
        channel="ONLINE",
        recommendation_scope="FUTURE_SCOPE",
        requires_registration=False,
        conditions=[
            {"type": "PAYMENT_PLATFORM", "value": "LINE_PAY", "label": "LINE Pay"},
            {"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": "行動支付"},
        ],
    )

    assert scope == "FUTURE_SCOPE"
    assert not any(condition["type"].startswith("PAYMENT_") for condition in conditions)


def test_ctbc_ep_titanium_online_offer_keeps_positive_wallets_and_adds_ecommerce_shape():
    category, subcategory, channel, scope, conditions = _refine_ctbc_promotion(
        card_code="CTBC_B_EP_TITANIUM",
        title="指定網購平台最高5%回饋",
        body=(
            "蝦皮購物、momo購物網、Coupang酷澎、淘寶網消費最高5%現金回饋。"
            "需登錄，每戶加碼上限300元/月，每月限量3,000名。"
            "限使用商旅鈦金實體卡(含綁定Apple Pay、Google Pay、Samsung Pay)支付，"
            "若透過第三方支付及電子支付錢包(例如：LINE Pay、街口支付、悠遊付、全支付等)將不認列為該特店之交易。"
        ),
        category="ONLINE",
        subcategory="GENERAL",
        channel="ONLINE",
        recommendation_scope="RECOMMENDABLE",
        requires_registration=True,
        conditions=[
            {"type": "REGISTRATION_REQUIRED", "value": "true", "label": "需登錄活動"},
            {"type": "PAYMENT_PLATFORM", "value": "LINE_PAY", "label": "LINE Pay"},
            {"type": "PAYMENT_PLATFORM", "value": "APPLE_PAY", "label": "Apple Pay"},
            {"type": "PAYMENT_PLATFORM", "value": "GOOGLE_PAY", "label": "Google Pay"},
            {"type": "PAYMENT_PLATFORM", "value": "SAMSUNG_PAY", "label": "Samsung Pay"},
            {"type": "PAYMENT_PLATFORM", "value": "JKOPAY", "label": "街口支付"},
            {"type": "PAYMENT_PLATFORM", "value": "全支付", "label": "全支付"},
            {"type": "PAYMENT_PLATFORM", "value": "悠遊付", "label": "悠遊付"},
            {"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": "行動支付"},
        ],
    )

    assert category == "ONLINE"
    assert subcategory == "ECOMMERCE"
    assert channel == "ONLINE"
    assert scope == "CATALOG_ONLY"
    assert any(condition["type"] == "ECOMMERCE_PLATFORM" and condition["value"] == "SHOPEE" for condition in conditions)
    assert any(condition["type"] == "ECOMMERCE_PLATFORM" and condition["value"] == "MOMO" for condition in conditions)
    assert any(condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "APPLE_PAY" for condition in conditions)
    assert any(condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "SAMSUNG_PAY" for condition in conditions)
    assert not any(condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "LINE_PAY" for condition in conditions)
    assert not any(condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "JKOPAY" for condition in conditions)
    assert not any(condition["type"] == "PAYMENT_METHOD" for condition in conditions)


def test_ctbc_hami_pay_offer_keeps_required_payment_platform():
    _, _, _, scope, conditions = _refine_ctbc_promotion(
        card_code="CTBC_C_CHT",
        title="Hami Pay掃碼支付回饋Hami Point最高3%",
        body="活動需以Hami Pay掃碼支付消費始符合回饋資格，其中2%為限時活動加碼。",
        category="OTHER",
        subcategory="GENERAL",
        channel="ALL",
        recommendation_scope="CATALOG_ONLY",
        requires_registration=False,
        conditions=[],
    )

    assert scope == "CATALOG_ONLY"
    assert any(condition["type"] == "PAYMENT_PLATFORM" and condition["value"] == "HAMI_PAY" for condition in conditions)


def test_ctbc_registration_heavy_campaigns_downgrade_to_catalog_only():
    _, _, _, scope, _ = _refine_ctbc_promotion(
        card_code="CTBC_C_DAYEHTAKASHIMAYA",
        title="限時加碼",
        body="持大葉髙島屋百貨JCB聯名卡綁定Apple Pay，儲值日本Suica最高10%刷卡金回饋(需完成登錄)，每人限回饋一次。",
        category="OVERSEAS",
        subcategory="GENERAL",
        channel="ALL",
        recommendation_scope="RECOMMENDABLE",
        requires_registration=True,
        conditions=[{"type": "REGISTRATION_REQUIRED", "value": "true", "label": "需登錄活動"}],
    )

    assert scope == "CATALOG_ONLY"


def test_ctbc_registration_heavy_cash_credit_campaign_downgrades_to_catalog_only():
    _, _, _, scope, _ = _refine_ctbc_promotion(
        card_code="CTBC_C_DAYEHTAKASHIMAYA",
        title="活動內容：持大葉髙島屋百貨JCB聯名卡刷日本大葉高島屋百貨，最高10%刷卡金回饋",
        body="持大葉髙島屋百貨JCB聯名卡刷日本大葉高島屋百貨，最高10%刷卡金回饋(需完成登錄)。",
        category="OVERSEAS",
        subcategory="GENERAL",
        channel="OFFLINE",
        recommendation_scope="RECOMMENDABLE",
        requires_registration=True,
        conditions=[{"type": "REGISTRATION_REQUIRED", "value": "true", "label": "需登錄活動"}],
    )

    assert scope == "CATALOG_ONLY"
