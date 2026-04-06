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


def test_cash_rebate_signature_extracts_base_general_rewards_from_colorbanner(monkeypatch):
    card = cathay_real.CardRecord(
        card_code="CATHAY_CASH_REBATE_SIGNATURE",
        card_name="現金回饋御璽卡",
        detail_url="https://www.cathay-cube.com.tw/cathaybk/personal/product/credit-card/cards/cash-rebate-signature/",
        apply_url="https://apply.example/cash-rebate-signature",
        annual_fee_summary="免年費條件",
        application_requirements=[],
        sections=[],
    )

    detail_payload = {
        ":items": {
            "applyInfo": {
                ":type": "cathay/components/content/creditcardapplyinfo",
                "mainBtnLink": "https://apply.example/cash-rebate-signature",
                "information": ["<p>成年人可申請正卡。</p>"],
            },
            "baseBenefit": {
                ":type": "cub-aem-cs/components/cub-content/cub-colorbanner/v1/cub-colorbanner",
                "title": "不限通路．最高2%現金回饋",
                "description": "<p>國外消費享2%現金回饋、國內消費享0.5%現金回饋，無通路限制、無回饋上限。</p>",
                "noticeGroup": {
                    "notice1": {
                        "noticeContent": (
                            "<p>2026/12/31前，無通路限制、無級距門檻、無回饋上限。</p>"
                            "<ul>"
                            "<li>國外刷一般消費享2%現金回饋</li>"
                            "<li>國內刷一般消費享0.5%現金回饋</li>"
                            "</ul>"
                        )
                    }
                },
            },
        }
    }

    def fake_fetch_json(url: str):
        if url.endswith("/cash-rebate-signature.model.json"):
            return detail_payload
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(cathay_real, "_fetch_json", fake_fetch_json)

    enriched_card, promotions = cathay_real.extract_card_promotions(card)
    base_rows = [promotion for promotion in promotions if "不限通路" in promotion["title"]]

    assert enriched_card.apply_url == "https://apply.example/cash-rebate-signature"
    assert any(promotion["category"] == "OVERSEAS" and promotion["cashbackValue"] == 2.0 for promotion in base_rows)
    assert any(promotion["category"] == "ONLINE" and promotion["cashbackValue"] == 0.5 for promotion in base_rows)
    assert any(promotion["category"] == "DINING" and promotion["cashbackValue"] == 0.5 for promotion in base_rows)
    assert all(promotion["validFrom"] == "2026-01-01" for promotion in base_rows)
    assert all(promotion["validUntil"] == "2026-12-31" for promotion in base_rows)


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


def test_formosa_gas_promos_remove_payment_and_add_gas_station_conditions():
    category, subcategory, channel, scope, conditions = cathay_real._apply_card_specific_overrides(
        "CATHAY_FORMOSA",
        "加油降價天天享",
        "於台亞/福懋/速邁樂加油中心及其他標有動能精靈之加油站加油享優惠。行動支付APP內顯示之交易記錄為預授權金額。",
        "ONLINE",
        "GENERAL",
        "ONLINE",
        "RECOMMENDABLE",
        [{"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": "行動支付"}],
    )

    assert category == "TRANSPORT"
    assert subcategory == "GAS_STATION"
    assert channel == "OFFLINE"
    assert scope == "CATALOG_ONLY"
    assert all(condition["type"] != "PAYMENT_METHOD" for condition in conditions)
    assert any(condition["type"] == "RETAIL_CHAIN" and condition["value"] == "TAIA" for condition in conditions)
    assert any(condition["type"] == "RETAIL_CHAIN" and condition["value"] == "FORMOZA" for condition in conditions)
    assert any(condition["type"] == "RETAIL_CHAIN" and condition["value"] == "FORMOSA_PETROCHEMICAL" for condition in conditions)


def test_cash_rebate_new_user_tasks_drop_false_merchant_structure():
    category, subcategory, channel, scope, conditions = cathay_real._apply_card_specific_overrides(
        "CATHAY_CASH_REBATE_SIGNATURE",
        "【本活動已結束】新戶首刷完成任務享權益加碼 新戶權益加碼2%！享最高1,200元刷卡金",
        "新戶完成任務一之次月起，Apple Pay綁定現金回饋御璽卡消費。",
        "SHOPPING",
        "DEPARTMENT",
        "ONLINE",
        "FUTURE_SCOPE",
        [{"type": "RETAIL_CHAIN", "value": "SOGO", "label": "SOGO"}],
    )

    assert category == "OTHER"
    assert subcategory == "GENERAL"
    assert channel == "ALL"
    assert scope == "FUTURE_SCOPE"
    assert conditions == []


def test_eva_mileage_offer_is_downgraded_to_catalog_only_general():
    category, subcategory, channel, scope, conditions = cathay_real._apply_card_specific_overrides(
        "CATHAY_EVA",
        "倍速哩遇消費最優10元1哩",
        "長榮航空官網購票與海外指定消費，登錄成功後享回饋。",
        "OVERSEAS",
        "TRAVEL_PLATFORM",
        "ONLINE",
        "FUTURE_SCOPE",
        [{"type": "REGISTRATION_REQUIRED", "value": "true", "label": "需登錄活動"}],
    )

    assert category == "OVERSEAS"
    assert subcategory == "GENERAL"
    assert channel == "ALL"
    assert scope == "CATALOG_ONLY"
    assert conditions == [{"type": "REGISTRATION_REQUIRED", "value": "true", "label": "需登錄活動"}]


def test_formosa_page_extracts_four_major_promotions(monkeypatch):
    list_payload = {
        ":items": {
            "cardList": {
                ":type": "cathay/components/content/creditcardlist",
                "creditCards": [
                    {
                        "cardName": "台塑聯名卡",
                        "ctaLink": "/cathaybk/personal/product/credit-card/cards/formosa/",
                    }
                ],
            }
        }
    }
    detail_payload = {
        ":items": {
            "applyInfo": {
                ":type": "cathay/components/content/creditcardapplyinfo",
                "information": ["<p>免年費條件</p>"],
            },
            "promoGroup": {
                ":type": "cub-aem-cs/components/cub-content/cub-horgraphictab/v1/cub-horgraphictab",
                "items": [
                    {
                        "title": "加油降價天天享",
                        "description": "2026/1/1~2026/3/31，於台亞/福懋/速邁樂加油中心及其他標有動能精靈之加油站加油享優惠。",
                    },
                    {
                        "title": "加油金再折抵",
                        "description": "2026/1/1~2026/7/31，以加油金折抵消費，每公升可折抵2元加油金。",
                    },
                    {
                        "title": "週三加油日",
                        "description": "2026/1/1~2026/3/31，週三站內汽油加滿25公升(含)以上，再享現折NT$15。限台亞/福懋/速邁樂加油中心。",
                    },
                    {
                        "title": "站外高回饋 最高回饋1%加油金",
                        "description": "站外一般消費NT$200＝1元加油金；指定台塑關係企業消費NT$200＝2元加油金。活動期間：2026/1/1~2026/7/31。",
                    },
                ],
            },
        }
    }

    def fake_fetch(url: str, timeout: int = 20) -> str:
        if url == cathay_real.CARD_LIST_MODEL_URL:
            return json.dumps(list_payload, ensure_ascii=False)
        if url.endswith("/formosa.model.json"):
            return json.dumps(detail_payload, ensure_ascii=False)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(cathay_real.ingest, "fetch_real_page", fake_fetch)

    card = cathay_real.list_cathay_cards()[0]
    _, promotions = cathay_real.extract_card_promotions(card)

    titles = {promotion["title"] for promotion in promotions}
    assert "台塑聯名卡 加油降價天天享" in titles
    assert "台塑聯名卡 加油金再折抵" in titles
    assert "台塑聯名卡 週三加油日" in titles
    assert "台塑聯名卡 站外高回饋 最高回饋1%加油金" in titles

    by_title = {promotion["title"]: promotion for promotion in promotions}
    assert by_title["台塑聯名卡 加油降價天天享"]["cashbackType"] == "FIXED"
    assert by_title["台塑聯名卡 加油降價天天享"]["cashbackValue"] == 1.2
    assert by_title["台塑聯名卡 加油金再折抵"]["cashbackValue"] == 2.0
    assert by_title["台塑聯名卡 週三加油日"]["cashbackValue"] == 15.0
    assert by_title["台塑聯名卡 週三加油日"]["recommendationScope"] == "CATALOG_ONLY"
    assert by_title["台塑聯名卡 站外高回饋 最高回饋1%加油金"]["validFrom"] == "2026-01-01"
    assert by_title["台塑聯名卡 站外高回饋 最高回饋1%加油金"]["validUntil"] == "2026-07-31"
    assert any(
        condition["type"] == "MERCHANT" and condition["value"] == "FORMOSA_BIOMEDICAL"
        for condition in by_title["台塑聯名卡 站外高回饋 最高回饋1%加油金"]["conditions"]
    )
