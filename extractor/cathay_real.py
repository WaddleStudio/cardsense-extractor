from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List
from urllib.parse import urljoin

from extractor import ingest
from extractor.html_utils import collapse_text, html_to_lines
from extractor.promotion_rules import (
    build_conditions,
    build_summary,
    classify_recommendation_scope,
    dedupe_promotions,
    extract_cap,
    extract_date_range,
    extract_frequency_limit,
    extract_min_amount,
    extract_reward,
    infer_category,
    infer_channel,
    normalize_promotion_title,
)


CARD_LIST_URL = "https://www.cathay-cube.com.tw/cathaybk/personal/product/credit-card/cards"
CARD_LIST_MODEL_URL = f"{CARD_LIST_URL}.model.json"
BANK_CODE = "CATHAY"
BANK_NAME = "國泰世華"

CATEGORY_SIGNALS = {
    "OVERSEAS": [("海外", 4), ("外幣", 3), ("旅遊", 3), ("航空", 3), ("住宿", 3), ("日本", 2)],
    "ONLINE": [("網購", 4), ("APP", 2), ("LINE Pay", 3), ("行動支付", 4), ("平台", 2)],
    "DINING": [("餐飲", 4), ("餐廳", 3), ("咖啡", 2)],
    "TRANSPORT": [("高鐵", 4), ("台鐵", 4), ("捷運", 4), ("交通", 3), ("加油", 2)],
    "SHOPPING": [("百貨", 3), ("購物", 3), ("商場", 2)],
    "GROCERY": [("超市", 4), ("量販", 3), ("全聯", 3), ("家樂福", 3)],
    "ENTERTAINMENT": [("電影", 3), ("影城", 3), ("串流", 3)],
}

CHANNEL_SIGNALS = {
    "ONLINE": [("APP", 3), ("網站", 3), ("網路", 3), ("網購", 4), ("LINE Pay", 3), ("行動支付", 4)],
    "OFFLINE": [("門市", 3), ("實體", 4), ("店面", 3), ("百貨", 2), ("餐廳", 2)],
    "ALL": [("一般消費", 4), ("國內外一般消費", 5), ("不限通路", 4)],
}

SUMMARY_NOISE_TOKENS = ("活動詳情", "注意事項", "立即登錄", "了解更多", "詳情請參閱")
GENERIC_TITLE_TOKENS = {"優惠", "回饋", "活動", "加碼"}
PROMOTION_SIGNAL_PATTERN = re.compile(r"\d+(?:\.\d+)?%|[\d,]+\s*(?:元|點|日圓)|回饋|折扣|現折|優惠|加碼|里程|哩程|點數")
DATE_PATTERN = re.compile(r"\d{4}/\d{1,2}/\d{1,2}\s*[~～-]\s*\d{4}/\d{1,2}/\d{1,2}")

CUBE_LIST_URL = "https://www.cathay-cube.com.tw/cathaybk/personal/product/credit-card/cards/cube-list"

# Plan name → (planId, default_cashback_rate, primary category)
# Used for plans whose rate isn't embedded in the JSON model data.
CUBE_PLAN_CONFIG: dict[str, tuple[str, str, str]] = {
    "玩數位": ("CATHAY_CUBE_DIGITAL", "3", "ONLINE"),
    "樂饗購": ("CATHAY_CUBE_SHOPPING", "3", "SHOPPING"),
    "趣旅行": ("CATHAY_CUBE_TRAVEL", "3", "OVERSEAS"),
    "集精選": ("CATHAY_CUBE_ESSENTIALS", "2", "OTHER"),
    "慶生月": ("CATHAY_CUBE_BIRTHDAY", "3.5", "DINING"),
    "童樂匯": ("CATHAY_CUBE_KIDS", "5", "OTHER"),
    "日本賞": ("CATHAY_CUBE_JAPAN", "3.5", "OVERSEAS"),
}


@dataclass
class CardRecord:
    card_code: str
    card_name: str
    detail_url: str
    apply_url: str | None
    annual_fee_summary: str | None
    application_requirements: List[str]
    sections: List[str]


def list_cathay_cards() -> List[CardRecord]:
    model = _fetch_json(CARD_LIST_MODEL_URL)
    seen: set[tuple[str, str]] = set()
    cards: List[CardRecord] = []
    for component in _iter_components(model):
        credit_cards = component.get("creditCards")
        if not isinstance(credit_cards, list):
            continue
        for entry in credit_cards:
            if not isinstance(entry, dict):
                continue
            detail_url = _normalize_url(entry.get("ctaLink") or entry.get("cardLink") or entry.get("cardBtnLink"), CARD_LIST_URL)
            if not detail_url or "/credit-card/cards/" not in detail_url:
                continue
            card_name = collapse_text(str(entry.get("cardName") or entry.get("itemName") or entry.get("title") or ""))
            if not card_name:
                continue
            dedupe_key = (card_name, detail_url)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            sections = _collect_text_list(entry.get("features"))
            cards.append(
                CardRecord(
                    card_code=_build_card_code(detail_url),
                    card_name=card_name,
                    detail_url=detail_url,
                    apply_url=_normalize_url(entry.get("cardBtnLink"), CARD_LIST_URL),
                    annual_fee_summary=None,
                    application_requirements=[],
                    sections=sections,
                )
            )

    return cards


def extract_card_promotions(card: CardRecord) -> tuple[CardRecord, List[Dict[str, object]]]:
    detail_model_url = _model_url(card.detail_url)
    model = _fetch_json(detail_model_url)
    components = list(_iter_components(model))

    detail_card_name = _extract_detail_card_name(components) or card.card_name
    apply_url = card.apply_url
    annual_fee_summary = card.annual_fee_summary
    application_requirements = list(card.application_requirements)

    for component in components:
        component_type = _component_type(component)
        if "creditcardapplyinfo" not in component_type:
            continue
        apply_url = _normalize_url(component.get("mainBtnLink") or component.get("subBtnLink"), card.detail_url) or apply_url
        information_lines = _collect_text_list(component.get("information"))
        if not annual_fee_summary:
            annual_fee_summary = _pick_annual_fee_summary(information_lines)
        application_requirements.extend(_extract_application_requirements(information_lines))

    enriched_card = CardRecord(
        card_code=card.card_code,
        card_name=detail_card_name,
        detail_url=card.detail_url,
        apply_url=apply_url,
        annual_fee_summary=annual_fee_summary,
        application_requirements=list(dict.fromkeys(application_requirements)),
        sections=card.sections,
    )

    promotions: List[Dict[str, object]] = []
    for component in components:
        component_type = _component_type(component)
        if not any(
            token in component_type
            for token in ("horgraphictab", "simplegraphictab", "discountcard", "campaignpromotioncard", "treepointscardcf")
        ):
            continue

        for candidate in _extract_component_candidates(component):
            clean_title = normalize_promotion_title(
                enriched_card.card_name,
                candidate["title"],
                candidate["body"],
                generic_title_tokens=GENERIC_TITLE_TOKENS,
                summary_noise_tokens=SUMMARY_NOISE_TOKENS,
                bank_suffixes=(BANK_NAME, "國泰世華銀行"),
            )
            if not clean_title:
                continue

            reward = extract_reward(clean_title, candidate["body"])
            if reward is None:
                continue

            valid_from, valid_until = extract_date_range(candidate["body"])
            if not valid_from or not valid_until:
                continue

            requires_registration = "登錄" in candidate["body"]
            min_amount = extract_min_amount(candidate["body"])
            max_cashback = extract_cap(candidate["body"])
            category = infer_category(clean_title, candidate["body"], CATEGORY_SIGNALS, overseas_category="OVERSEAS")
            recommendation_scope = classify_recommendation_scope(clean_title, candidate["body"], category)
            promotions.append(
                {
                    "title": f"{enriched_card.card_name} {clean_title}",
                    "cardCode": enriched_card.card_code,
                    "cardName": enriched_card.card_name,
                    "cardStatus": "ACTIVE",
                    "annualFee": _extract_annual_fee_amount(enriched_card.annual_fee_summary),
                    "applyUrl": enriched_card.apply_url,
                    "bankCode": BANK_CODE,
                    "bankName": BANK_NAME,
                    "category": category,
                    "channel": infer_channel(clean_title, candidate["body"], CHANNEL_SIGNALS),
                    "cashbackType": reward["type"],
                    "cashbackValue": reward["value"],
                    "minAmount": min_amount,
                    "maxCashback": max_cashback,
                    "frequencyLimit": extract_frequency_limit(candidate["body"]),
                    "requiresRegistration": requires_registration,
                    "recommendationScope": recommendation_scope,
                    "validFrom": valid_from,
                    "validUntil": valid_until,
                    "conditions": build_conditions(candidate["body"], enriched_card.application_requirements, requires_registration),
                    "excludedConditions": [],
                    "sourceUrl": enriched_card.detail_url,
                    "summary": build_summary(
                        clean_title,
                        candidate["body"],
                        valid_from,
                        valid_until,
                        min_amount,
                        max_cashback,
                        requires_registration,
                        summary_noise_tokens=SUMMARY_NOISE_TOKENS,
                    ),
                    "status": "ACTIVE",
                }
            )

    plan_promotions = _extract_plan_promotions(enriched_card)
    promotions.extend(plan_promotions)

    return enriched_card, dedupe_promotions(promotions)


def _extract_plan_promotions(card: CardRecord) -> List[Dict[str, object]]:
    """Extract CUBE plan-based promotions from treepointscardcf and cube-list page."""
    # Step 1: Get date ranges from cube-list page cubelisttitle components
    plan_dates: dict[str, tuple[str, str]] = {}
    try:
        cubelist_model = _fetch_json(_model_url(CUBE_LIST_URL))
        current_plan_name: str | None = None
        for comp in _iter_components(cubelist_model):
            ct = _component_type(comp)
            if "cubelisttitle" in ct:
                title_html = comp.get("mainTitle", "")
                plan_match = re.search(r">([^<]+?)(?:&nbsp;|\s*<)", title_html)
                if plan_match:
                    current_plan_name = plan_match.group(1).strip()
                date_match = re.search(
                    r"適用期間[：:](\d{4}/\d{1,2}/\d{1,2})\s*[~～]\s*(\d{4}/\d{1,2}/\d{1,2})",
                    title_html,
                )
                if date_match and current_plan_name:
                    vf = _normalize_date(date_match.group(1))
                    vu = _normalize_date(date_match.group(2))
                    if vf and vu:
                        plan_dates[current_plan_name] = (vf, vu)
    except Exception:
        pass  # cube-list page may be unavailable; proceed with what we have

    # Step 2: Extract structured rates from treepointscardcf on the main card page
    plan_rates: dict[str, list[dict[str, str]]] = {}
    try:
        detail_model = _fetch_json(_model_url(card.detail_url))
        for comp in _iter_components(detail_model):
            ct = _component_type(comp)
            if "treepointscard" not in ct:
                continue
            for tree in comp.get("contentTrees", []):
                tab_text = (tree.get("contentTreeItem") or {}).get("tabText", "")
                if not tab_text:
                    continue
                tiers: list[dict[str, str]] = []
                for card_item in tree.get("cardList", []):
                    rate = card_item.get("rate")
                    title = card_item.get("title", "")
                    content = collapse_text(card_item.get("content", ""))
                    content_clean = re.sub(r"<[^>]+>", "", content)
                    if rate and title and title != "一般消費":
                        tiers.append({"rate": rate, "title": title, "merchants": content_clean})
                if tiers:
                    plan_rates[tab_text] = tiers
    except Exception:
        pass

    # Step 3: Build promotions for each plan
    promotions: List[Dict[str, object]] = []
    seen_plans: set[str] = set()

    # 3a: Plans with structured rate data from treepointscardcf
    for plan_name, tiers in plan_rates.items():
        seen_plans.add(plan_name)
        config = CUBE_PLAN_CONFIG.get(plan_name)
        plan_id = config[0] if config else None
        dates = plan_dates.get(plan_name)

        for tier in tiers:
            rate = tier["rate"]
            tier_title = tier["title"]
            merchants = tier["merchants"]
            category = infer_category(tier_title, merchants, CATEGORY_SIGNALS, overseas_category="OVERSEAS")
            channel = infer_channel(tier_title, merchants, CHANNEL_SIGNALS)
            title = f"{card.card_name} {plan_name} {tier_title}"
            body = f"{tier_title} 享{rate}%小樹點回饋 {merchants}"
            valid_from = dates[0] if dates else None
            valid_until = dates[1] if dates else None

            if not valid_from or not valid_until:
                continue

            promo = _build_plan_promotion(
                card=card,
                title=title,
                body=body,
                rate=rate,
                category=category,
                channel=channel,
                valid_from=valid_from,
                valid_until=valid_until,
                plan_id=plan_id,
                plan_name=plan_name,
            )
            promotions.append(promo)

    # 3b: Plans without treepointscardcf data — use config fallback rates
    for plan_name, (plan_id, default_rate, default_category) in CUBE_PLAN_CONFIG.items():
        if plan_name in seen_plans:
            continue
        dates = plan_dates.get(plan_name)
        if not dates:
            continue

        valid_from, valid_until = dates
        title = f"{card.card_name} {plan_name} 指定通路回饋"
        body = f"{plan_name}方案 指定通路享{default_rate}%小樹點回饋"
        channel = "ONLINE" if default_category == "ONLINE" else "ALL"

        promo = _build_plan_promotion(
            card=card,
            title=title,
            body=body,
            rate=default_rate,
            category=default_category,
            channel=channel,
            valid_from=valid_from,
            valid_until=valid_until,
            plan_id=plan_id,
            plan_name=plan_name,
        )
        promotions.append(promo)

    return promotions


def _build_plan_promotion(
    *,
    card: CardRecord,
    title: str,
    body: str,
    rate: str,
    category: str,
    channel: str,
    valid_from: str,
    valid_until: str,
    plan_id: str | None,
    plan_name: str,
) -> Dict[str, object]:
    return {
        "title": title,
        "cardCode": card.card_code,
        "cardName": card.card_name,
        "cardStatus": "ACTIVE",
        "annualFee": _extract_annual_fee_amount(card.annual_fee_summary),
        "applyUrl": card.apply_url,
        "bankCode": BANK_CODE,
        "bankName": BANK_NAME,
        "category": category,
        "channel": channel,
        "cashbackType": "PERCENT",
        "cashbackValue": rate,
        "minAmount": 0,
        "maxCashback": None,
        "frequencyLimit": "NONE",
        "requiresRegistration": False,
        "recommendationScope": "RECOMMENDABLE",
        "validFrom": valid_from,
        "validUntil": valid_until,
        "conditions": [{"type": "TEXT", "value": f"需切換至「{plan_name}」方案", "label": f"需切換至「{plan_name}」方案"}],
        "excludedConditions": [],
        "sourceUrl": card.detail_url,
        "summary": f"{title}；享{rate}%小樹點回饋；期間 {valid_from}~{valid_until}",
        "status": "ACTIVE",
        "planId": plan_id,
    }


def _normalize_date(date_str: str) -> str | None:
    """Convert '2026/1/1' to '2026-01-01'."""
    match = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", date_str)
    if not match:
        return None
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _fetch_json(url: str) -> Dict[str, Any]:
    return json.loads(ingest.fetch_real_page(url))


def _iter_components(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        if ":type" in value:
            yield value
        for child in value.values():
            yield from _iter_components(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from _iter_components(child)


def _component_type(component: Dict[str, Any]) -> str:
    return str(component.get(":type") or "").lower()


def _extract_detail_card_name(components: Iterable[Dict[str, Any]]) -> str:
    for component in components:
        for key in ("creditCardName", "cardName", "mainTitle"):
            value = collapse_text(str(component.get(key) or ""))
            if value and ("信用卡" in value or value.endswith("卡")):
                return value
    return ""


def _pick_annual_fee_summary(lines: Iterable[str]) -> str | None:
    for line in lines:
        if "年費" in line or "首年免年費" in line:
            return line[:200]
    return None


def _extract_application_requirements(lines: Iterable[str]) -> List[str]:
    tokens = ("年滿", "財力證明", "正卡", "附卡", "申辦", "限申請")
    results: List[str] = []
    for line in lines:
        if any(token in line for token in tokens):
            results.append(line[:120])
    return list(dict.fromkeys(results))


def _extract_component_candidates(component: Dict[str, Any]) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def walk(value: Any, title_stack: List[str]) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item, title_stack)
            return

        if not isinstance(value, dict):
            return

        current_title = _primary_title(value)
        next_titles = title_stack
        if current_title and (not title_stack or current_title != title_stack[-1]):
            next_titles = [*title_stack, current_title]

        body = _compose_body(value)
        if current_title and body and _looks_like_promotion(current_title, body):
            title = current_title if len(next_titles) == 1 else " ".join(next_titles[-2:])
            dedupe_key = (title, body)
            if dedupe_key not in seen:
                seen.add(dedupe_key)
                candidates.append({"title": title, "body": body})

        for child_key, child_value in value.items():
            if child_key.startswith(":") or child_key in {
                "title",
                "mainTitle",
                "cardName",
                "creditCardName",
                "tabText",
                "content",
                "description",
                "rate",
                "noticeText",
                "noticeContent",
                "noticeContent1",
                "noticeContent2",
                "subTitle",
            }:
                continue
            walk(child_value, next_titles)

    walk(component, [])
    return candidates


def _primary_title(value: Dict[str, Any]) -> str:
    for key in ("title", "tabText", "mainTitle", "itemName", "cardName"):
        title = collapse_text(str(value.get(key) or ""))
        if title and title not in {"立即申辦", "注意事項", "了解更多"}:
            return title
    return ""


def _compose_body(value: Dict[str, Any]) -> str:
    body_parts: List[str] = []
    for key in ("subTitle", "content", "description", "rate", "noticeText", "noticeContent", "noticeContent1", "noticeContent2"):
        body_parts.extend(_collect_text_list(value.get(key)))
    return collapse_text(" • ".join(part for part in body_parts if part))


def _collect_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        results: List[str] = []
        for item in value:
            results.extend(_collect_text_list(item))
        return [item for item in results if item]
    if isinstance(value, dict):
        results: List[str] = []
        for key in ("text", "description", "content", "title", "noticeContent", "noticeText", "value"):
            results.extend(_collect_text_list(value.get(key)))
        return [item for item in results if item]

    text = str(value)
    if "<" in text and ">" in text:
        return html_to_lines(text)
    collapsed = collapse_text(text)
    return [collapsed] if collapsed else []


def _looks_like_promotion(title: str, body: str) -> bool:
    text = f"{title} {body}"
    if not DATE_PATTERN.search(text):
        return False
    return bool(PROMOTION_SIGNAL_PATTERN.search(text))


def _normalize_url(url: Any, base_url: str) -> str | None:
    if not url:
        return None
    normalized = urljoin(base_url, str(url).strip())
    return normalized.split("#", 1)[0]


def _model_url(detail_url: str) -> str:
    return f"{detail_url.rstrip('/')}.model.json"


def _build_card_code(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").upper()
    return f"CATHAY_{normalized}"


def _extract_annual_fee_amount(summary: str | None) -> int:
    if not summary:
        return 0
    match = re.search(r"年費\s*([\d,]+)元", summary)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0