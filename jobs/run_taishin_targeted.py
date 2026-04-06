"""Run Taishin extraction for a specific set of cards with additional promo URLs.

Usage:
    uv run python jobs/run_taishin_targeted.py
"""
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from extractor.taishin_real import CardRecord, extract_card_promotions, list_taishin_cards, KNOWN_CARDS

# Target cards: (cg_path, extra_promo_urls)
TARGET_CARDS: dict[str, list[str]] = {
    "cg010/card001": [  # 大全聯信用卡
        "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/future/de8a9d22-8f7f-11f0-b50f-0050568c09e3",
    ],
    "cg047/card001": [  # 台新Richart卡
        "https://mkp.taishinbank.com.tw/s/2025/RichartCard_2025/index.html",
    ],
    "cg019/card001": [  # 遠傳friDay聯名卡
        "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/future/c73ec5a2-a239-11ef-b432-0050568c09e3",
    ],
    "cg038/card001": [  # 街口聯名卡
        "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/future/24e1ad87-2cad-11f1-b50f-0050568c09e3",
    ],
    "cg023/card002": [],  # 燦坤聯名卡
    "cg042/card001": [  # Gogoro Rewards 聯名卡
        "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/future/27297fce-4f5c-11ed-80cd-0050568c09e3",
    ],
    "cg012/card0001": [],  # 太陽卡
    "cg013/card0001": [],  # 玫瑰卡
    "cg039/card001": [  # 台新雙幣卡
        "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/future/9847a330-2706-11ea-b038-0050568c09e3",
    ],
    "cg045/card001": [  # 卓富無限卡
        "https://mkp.taishinbank.com.tw/s/2023/wealthcard/index.html",
    ],
    "cg008/card001": [],  # 新光三越御璽/鈦金/白金卡
    "cg014/card0001": [],  # 新光三越無限/世界卡
}


def list_targeted_cards() -> list[CardRecord]:
    """Return only cards matching TARGET_CARDS keys."""
    all_cards = list_taishin_cards()
    target_keys = set(TARGET_CARDS.keys())
    targeted = []
    for card in all_cards:
        # Match by checking if the card's detail_url contains any target cg path
        for key in target_keys:
            if key in card.detail_url:
                targeted.append(card)
                break
    return targeted


if __name__ == "__main__":
    from jobs.run_real_bank_job import run_real_bank_job

    code = run_real_bank_job(
        bank_label="TAISHIN-targeted",
        output_prefix="taishin-targeted",
        list_cards=list_targeted_cards,
        extract_card_promotions=extract_card_promotions,
    )
    raise SystemExit(code)
