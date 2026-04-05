import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.normalize import clean_card_name, infer_eligibility_type, normalize_data


def test_normalize_infers_plan_id_for_benefit_plan_cards():
    normalized = normalize_data(
        {
            "bank": "ESUN",
            "bank_name": "玉山銀行",
            "card_code": "ESUN_UNICARD",
            "card_name": "玉山Unicard",
            "promotion": "任意選 LINE Pay 3%",
            "category": "ONLINE",
            "cashback_type": "PERCENT",
            "cashback_value": "3.5",
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
            "source_url": "https://example.com/unicard",
            "annual_fee": "0",
        }
    )

    assert normalized["planId"] == "ESUN_UNICARD_FLEXIBLE"
    assert normalized["subcategory"] == "MOBILE_PAY"


def test_normalize_infers_richart_plan_id_when_missing():
    normalized = normalize_data(
        {
            "bank": "TAISHIN",
            "bank_name": "台新銀行",
            "card_code": "TAISHIN_RICHART",
            "card_name": "台新Richart卡",
            "promotion": "數位影音 3%",
            "category": "ENTERTAINMENT",
            "cashback_type": "PERCENT",
            "cashback_value": "3",
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
            "source_url": "https://example.com/richart",
            "annual_fee": "0",
        }
    )

    assert normalized["planId"] == "TAISHIN_RICHART_DIGITAL"
    assert normalized["subcategory"] == "STREAMING"


def test_normalize_preserves_explicit_plan_id():
    normalized = normalize_data(
        {
            "bank": "CATHAY",
            "bank_name": "國泰世華",
            "card_code": "CATHAY_CUBE",
            "card_name": "CUBE信用卡",
            "promotion": "日本賞 8%",
            "category": "OVERSEAS",
            "cashback_type": "PERCENT",
            "cashback_value": "8",
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
            "source_url": "https://example.com/cube",
            "annual_fee": "0",
            "plan_id": "CATHAY_CUBE_JAPAN",
        }
    )

    assert normalized["planId"] == "CATHAY_CUBE_JAPAN"


def test_normalize_preserves_existing_subcategory_when_present():
    normalized = normalize_data(
        {
            "bank": "TAISHIN",
            "bank_name": "Taishin",
            "card_code": "TAISHIN_RICHART",
            "card_name": "Richart Card",
            "promotion": "LINE Pay up to 3.8%",
            "category": "ONLINE",
            "subcategory": "MOBILE_PAY",
            "cashback_type": "PERCENT",
            "cashback_value": "3.8",
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
            "annual_fee": "0",
        }
    )

    assert normalized["planId"] == "TAISHIN_RICHART_PAY"
    assert normalized["subcategory"] == "MOBILE_PAY"


def test_normalize_applies_category_specific_cube_shopping_hint():
    normalized = normalize_data(
        {
            "bank": "CATHAY",
            "bank_name": "Cathay",
            "card_code": "CATHAY_CUBE",
            "card_name": "CUBE Credit Card",
            "promotion": "來享購 百貨 3%",
            "category": "SHOPPING",
            "cashback_type": "PERCENT",
            "cashback_value": "3",
            "valid_from": "2026-01-01",
            "valid_until": "2026-12-31",
            "annual_fee": "0",
        }
    )

    assert normalized["planId"] == "CATHAY_CUBE_SHOPPING"
    assert normalized["subcategory"] == "DEPARTMENT"


def test_normalize_maps_cube_dining_to_shopping_plan():
    normalized = normalize_data(
        {
            "bank": "CATHAY",
            "bank_name": "Cathay",
            "card_code": "CATHAY_CUBE",
            "card_name": "CUBE Credit Card",
            "promotion": "來享購 餐飲 3%",
            "category": "DINING",
            "cashback_type": "PERCENT",
            "cashback_value": "3",
            "valid_from": "2026-01-01",
            "valid_until": "2026-06-30",
            "annual_fee": "0",
            "source_url": "https://example.com/cube-dining",
        }
    )

    assert normalized["planId"] == "CATHAY_CUBE_SHOPPING"
    assert normalized["subcategory"] == "RESTAURANT"


def test_normalize_maps_cube_grocery_to_essentials_plan():
    normalized = normalize_data(
        {
            "bank": "CATHAY",
            "bank_name": "Cathay",
            "card_code": "CATHAY_CUBE",
            "card_name": "CUBE Credit Card",
            "promotion": "集精選 超市 2%",
            "category": "GROCERY",
            "cashback_type": "PERCENT",
            "cashback_value": "2",
            "valid_from": "2026-01-01",
            "valid_until": "2026-06-30",
            "annual_fee": "0",
            "source_url": "https://example.com/cube-grocery",
        }
    )

    assert normalized["planId"] == "CATHAY_CUBE_ESSENTIALS"
    assert normalized["subcategory"] == "SUPERMARKET"


def test_infer_eligibility_type_detects_business_card_names():
    assert infer_eligibility_type("玉山商務御璽卡 - 玉山銀行") == "BUSINESS"


def test_infer_eligibility_type_detects_profession_specific_card_names():
    assert infer_eligibility_type("中信教師認同卡") == "PROFESSION_SPECIFIC"


def test_clean_card_name_trims_marketing_suffixes_from_listing_titles():
    assert clean_card_name("玉山ＵBear信用卡 行動支付、網路消費") == "玉山ＵBear信用卡"
    assert clean_card_name("玉山 Pi 拍錢包信用卡 國內外一般消費") == "玉山 Pi 拍錢包信用卡"
    assert clean_card_name("寶雅悠遊聯名卡 每週末實體門市、寶雅線上買享13%現金回饋") == "寶雅悠遊聯名卡"


def test_clean_card_name_trims_status_suffixes():
    assert clean_card_name("玉山商務御璽卡 《2025/10/15起停止申辦》") == "玉山商務御璽卡"
    assert clean_card_name("KOKO COMBO icash聯名卡，已停發") == "KOKO COMBO icash聯名卡"
    assert clean_card_name("Taiwan Money 卡 (停發)") == "Taiwan Money 卡"
