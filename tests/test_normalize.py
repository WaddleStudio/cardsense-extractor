import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.normalize import normalize_data


def test_normalize_infers_plan_id_for_benefit_plan_cards():
    normalized = normalize_data(
        {
            "bank": "ESUN",
            "bank_name": "玉山銀行",
            "card_code": "ESUN_UNICARD",
            "card_name": "玉山Unicard",
            "promotion": "指定通路加碼",
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


def test_normalize_infers_richart_plan_id_when_missing():
    normalized = normalize_data(
        {
            "bank": "TAISHIN",
            "bank_name": "台新銀行",
            "card_code": "TAISHIN_RICHART",
            "card_name": "台新Richart卡",
            "promotion": "指定影音加碼",
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


def test_normalize_preserves_explicit_plan_id():
    normalized = normalize_data(
        {
            "bank": "CATHAY",
            "bank_name": "國泰世華",
            "card_code": "CATHAY_CUBE",
            "card_name": "國泰 CUBE 卡",
            "promotion": "日本賞加碼",
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