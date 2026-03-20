import json
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor import cathay_real


def test_cathay_model_json_parser_extracts_card_and_promotion(monkeypatch):
    list_payload = {
        ":items": {
            "cardList": {
                ":type": "cathay/components/content/creditcardlist",
                "creditCards": [
                    {
                        "cardName": "測試聯名卡",
                        "ctaLink": "/cathaybk/personal/product/credit-card/cards/test-card/",
                        "cardBtnLink": "https://apply.example/test-card",
                        "features": ["指定通路", "行動支付"],
                    }
                ],
            }
        }
    }
    detail_payload = {
        ":items": {
            "applyInfo": {
                ":type": "cathay/components/content/creditcardapplyinfo",
                "mainBtnLink": "https://apply.example/test-card",
                "information": [
                    "<p>首年免年費</p>",
                    "<p>年滿18歲可申辦</p>",
                ],
            },
            "promo": {
                ":type": "cathay/components/content/campaignpromotioncard",
                "title": "指定通路加碼",
                "description": "最高享5%回饋",
                "noticeContent": "活動期間：2026/1/1~2026/3/31 指定通路消費最高享5%回饋，上限300元，需登錄。",
            },
        }
    }

    def fake_fetch(url: str, timeout: int = 20) -> str:
        if url == cathay_real.CARD_LIST_MODEL_URL:
            return json.dumps(list_payload, ensure_ascii=False)
        if url.endswith("/test-card.model.json"):
            return json.dumps(detail_payload, ensure_ascii=False)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(cathay_real.ingest, "fetch_real_page", fake_fetch)

    cards = cathay_real.list_cathay_cards()

    assert len(cards) == 1
    assert cards[0].card_name == "測試聯名卡"
    assert cards[0].detail_url.endswith("/test-card/")

    enriched_card, promotions = cathay_real.extract_card_promotions(cards[0])

    assert enriched_card.apply_url == "https://apply.example/test-card"
    assert enriched_card.application_requirements == ["年滿18歲可申辦"]
    assert len(promotions) == 1
    assert promotions[0]["cardCode"] == "CATHAY_TEST_CARD"
    assert promotions[0]["cashbackType"] == "PERCENT"
    assert promotions[0]["cashbackValue"] == 5.0
    assert promotions[0]["maxCashback"] == 300
    assert promotions[0]["requiresRegistration"] is True
    assert promotions[0]["recommendationScope"] == "RECOMMENDABLE"
    assert promotions[0]["validFrom"] == "2026-01-01"
    assert promotions[0]["validUntil"] == "2026-03-31"