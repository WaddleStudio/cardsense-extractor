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
    assert all(not promotion.get("planId") for promotion in promotions)


def test_extract_plan_promotions_emits_curated_cube_variants(monkeypatch):
    card = cathay_real.CardRecord(
        card_code="CATHAY_CUBE",
        card_name="CUBE信用卡",
        detail_url="https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/cube/",
        apply_url="https://apply.example/cube",
        annual_fee_summary="首年免年費",
        application_requirements=[],
        sections=[],
    )

    cube_list_payload = {
        ":items": {
            "title1": {
                ":type": "cathay/components/content/cubelisttitle",
                "mainTitle": "<p>玩數位&nbsp;<span>適用期間：2026/1/1~2026/6/30</span></p>",
            },
            "title2": {
                ":type": "cathay/components/content/cubelisttitle",
                "mainTitle": "<p>樂饗購&nbsp;<span>適用期間：2026/1/1~2026/6/30</span></p>",
            },
            "title3": {
                ":type": "cathay/components/content/cubelisttitle",
                "mainTitle": "<p>趣旅行&nbsp;<span>適用期間：2026/1/1~2026/6/30</span></p>",
            },
            "title4": {
                ":type": "cathay/components/content/cubelisttitle",
                "mainTitle": "<p>集精選&nbsp;<span>適用期間：2026/1/1~2026/6/30</span></p>",
            },
        }
    }
    detail_payload = {
        ":items": {
            "tree": {
                ":type": "cathay/components/content/treepointscardcf",
                "contentTrees": [
                    {
                        "contentTreeItem": {"tabText": "玩數位"},
                        "cardList": [{"rate": "3", "title": "指定通路回饋", "content": "網購與數位訂閱"}],
                    },
                    {
                        "contentTreeItem": {"tabText": "樂饗購"},
                        "cardList": [{"rate": "3", "title": "指定通路回饋", "content": "百貨與餐飲"}],
                    },
                    {
                        "contentTreeItem": {"tabText": "趣旅行"},
                        "cardList": [{"rate": "3", "title": "指定通路回饋", "content": "海外與旅遊"}],
                    },
                    {
                        "contentTreeItem": {"tabText": "集精選"},
                        "cardList": [{"rate": "2", "title": "指定通路回饋", "content": "超市與充電停車"}],
                    },
                ],
            }
        }
    }

    def fake_fetch_json(url: str):
        if "cube-list" in url:
            return cube_list_payload
        if url.endswith("/cube.model.json"):
            return detail_payload
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(cathay_real, "_fetch_json", fake_fetch_json)

    promotions = cathay_real._extract_plan_promotions(card)
    titles = {promotion["title"] for promotion in promotions}
    keyed = {(promotion["planId"], promotion["subcategory"]) for promotion in promotions}

    assert "CUBE信用卡 玩數位 AI工具訂閱" in titles
    assert "CUBE信用卡 樂饗購 外送平台" in titles
    assert "CUBE信用卡 樂饗購 藥妝通路" in titles
    assert "CUBE信用卡 趣旅行 指定航空公司" in titles
    assert "CUBE信用卡 集精選 充電通路" in titles
    assert ("CATHAY_CUBE_DIGITAL", "AI_TOOL") in keyed
    assert ("CATHAY_CUBE_SHOPPING", "DELIVERY") in keyed
    assert ("CATHAY_CUBE_SHOPPING", "DRUGSTORE") in keyed
    assert ("CATHAY_CUBE_TRAVEL", "AIRLINE") in keyed
    assert ("CATHAY_CUBE_ESSENTIALS", "PARKING") in keyed

    ai_tool = next(p for p in promotions if p["planId"] == "CATHAY_CUBE_DIGITAL" and p["subcategory"] == "AI_TOOL")
    supermarket = next(p for p in promotions if p["planId"] == "CATHAY_CUBE_ESSENTIALS" and p["subcategory"] == "SUPERMARKET")
    airline = next(p for p in promotions if p["planId"] == "CATHAY_CUBE_TRAVEL" and p["subcategory"] == "AIRLINE")

    assert any(condition["type"] == "MERCHANT" and condition["value"] == "CHATGPT" for condition in ai_tool["conditions"])
    assert any(condition["type"] == "RETAIL_CHAIN" and condition["value"] == "PXMART" for condition in supermarket["conditions"])
    assert any(condition["type"] == "MERCHANT" and condition["value"] == "CHINA_AIRLINES" for condition in airline["conditions"])
