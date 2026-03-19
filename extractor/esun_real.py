from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Dict, Iterable, List
from urllib.parse import urljoin, urlparse

from extractor import ingest


CARD_LIST_URL = "https://www.esunbank.com/zh-tw/personal/credit-card/intro"
BANK_CODE = "ESUN"
BANK_NAME = "玉山銀行"

CATEGORY_SIGNALS = {
    "OVERSEAS": [("日本", 4), ("韓國", 4), ("海外", 4), ("外幣", 3), ("航空", 3), ("旅遊", 3), ("旅行", 3), ("飯店", 3), ("住宿", 3), ("機場", 2), ("日圓", 2), ("韓圓", 2)],
    "ONLINE": [("Booking", 3), ("Agoda", 3), ("Hotels.com", 3), ("Expedia", 3), ("Klook", 3), ("KKday", 3), ("PChome", 4), ("蝦皮", 4), ("網購", 4), ("LINE Pay", 3), ("Uber Eats", 3), ("網頁", 2), ("網站", 2), ("平台", 1), ("APP", 1)],
    "DINING": [("餐飲", 4), ("餐廳", 3), ("咖啡", 2), ("壽司", 2), ("爭鮮", 3), ("星巴克", 2), ("熟成紅茶", 2)],
    "TRANSPORT": [("交通", 4), ("乘車", 4), ("高鐵", 4), ("台鐵", 4), ("捷運", 4), ("巴士", 3), ("TAXI", 4), ("機場接送", 4), ("大眾交通", 4), ("Suica", 4), ("加油", 2), ("中油", 2)],
    "SHOPPING": [("百貨", 3), ("新光三越", 5), ("購物", 3), ("購物園區", 4), ("免稅", 2), ("商圈", 2), ("OUTLET", 2)],
    "GROCERY": [("家樂福", 5), ("全聯", 5), ("超市", 4), ("量販", 3)],
    "ENTERTAINMENT": [("影城", 4), ("電影", 4), ("串流", 4), ("購票", 2), ("演唱會", 4), ("轉播", 2), ("健身房", 2), ("學習平台", 2)],
}

CHANNEL_SIGNALS = {
    "ONLINE": [("APP", 3), ("網站", 3), ("網頁", 3), ("網購", 4), ("Booking", 4), ("Agoda", 4), ("Hotels.com", 4), ("Expedia", 4), ("Klook", 4), ("KKday", 4), ("PChome", 4), ("蝦皮", 4), ("LINE Pay", 3), ("玉山Wallet", 3), ("電子支付", 3), ("乘車碼", 2)],
    "OFFLINE": [("實體門市", 4), ("實體店面", 4), ("實體商店", 4), ("店面", 3), ("門市", 3), ("店家", 3), ("商圈", 3), ("商店", 2), ("百貨", 2), ("餐廳", 2), ("加油站", 3), ("直營站", 3), ("搭乘", 2), ("掃碼付", 2), ("TWQR", 2)],
    "ALL": [("一般消費", 4), ("國內外一般消費", 5), ("不限通路", 4), ("國內外", 2)],
}

SUMMARY_NOISE_TOKENS = ("活動詳情", "注意事項", "立即登錄", "了解更多", "專屬網頁", "詳情請參閱")
GENERIC_TITLE_TOKENS = {"【活動一】", "【活動二】", "【活動三】", "活動一", "活動二", "活動三", "優惠", "回饋", "滿額活動"}

SECTION_HEADINGS = {
    "卡片介紹",
    "卡片特色",
    "專屬優惠",
    "Pi拍錢包加碼",
    "卡友禮遇服務",
    "卡片須知",
    "行動支付新體驗",
    "玉山Wallet 卡友必備APP",
    "常見問題",
    "聯繫客服",
    "Additional Links",
}

SUBSECTION_SKIP = SECTION_HEADINGS | {
    "注意事項",
    "活動詳情",
    "立即登錄",
    "了解更多",
    "專屬網頁",
    "申辦",
    "申請",
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


@dataclass
class RewardCandidate:
    reward_type: str
    value: float
    label: str
    score: int


class _AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[Dict[str, str]] = []
        self._current_href: str | None = None
        self._text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self._current_href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        text = _collapse_text(" ".join(self._text_parts))
        self.links.append({"href": self._current_href, "text": text})
        self._current_href = None
        self._text_parts = []


def list_esun_cards() -> List[CardRecord]:
    html = ingest.fetch_real_page(CARD_LIST_URL)
    links = _collect_links(html, CARD_LIST_URL)

    seen: set[str] = set()
    cards: List[CardRecord] = []
    for link in links:
        href = link["href"]
        if "/personal/credit-card/intro/" not in href:
            continue
        if "#" in href:
            href = href.split("#", 1)[0]
        if href in seen:
            continue
        seen.add(href)

        text = link["text"]
        if not text:
            continue
        card_name = _extract_card_name_from_link_text(text)
        if not card_name:
            continue

        cards.append(
            CardRecord(
                card_code=_build_card_code(href),
                card_name=card_name,
                detail_url=href,
                apply_url=None,
                annual_fee_summary=None,
                application_requirements=[],
                sections=[],
            )
        )

    return cards


def extract_card_promotions(card: CardRecord) -> tuple[CardRecord, List[Dict[str, object]]]:
    html = ingest.fetch_real_page(card.detail_url)
    links = _collect_links(html, card.detail_url)
    lines = _html_to_lines(html)

    enriched_card = CardRecord(
        card_code=card.card_code,
        card_name=_extract_card_title(lines) or card.card_name,
        detail_url=card.detail_url,
        apply_url=_extract_apply_url(links),
        annual_fee_summary=_extract_annual_fee_summary(lines),
        application_requirements=_extract_application_requirements(lines),
        sections=_extract_sections(lines),
    )

    promotions: List[Dict[str, object]] = []
    for block in _extract_offer_blocks(lines):
        clean_title = _normalize_promotion_title(enriched_card.card_name, block["title"], block["body"])  # type: ignore[arg-type]
        clean_body = _clean_offer_text(block["body"])  # type: ignore[arg-type]

        reward = _extract_reward(clean_title, clean_body)
        if reward is None:
            continue

        valid_from, valid_until = _extract_date_range(clean_body)
        if not valid_from or not valid_until:
            continue

        min_amount = _extract_min_amount(clean_body)
        max_cashback = _extract_cap(clean_body)
        requires_registration = "登錄" in clean_body
        frequency_limit = _extract_frequency_limit(clean_body)
        summary = _build_summary(clean_title, clean_body, valid_from, valid_until, min_amount, max_cashback, requires_registration)
        category = _infer_category(clean_title, clean_body, enriched_card.card_name)
        conditions = _build_conditions(clean_body, enriched_card.application_requirements, requires_registration)

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
                "channel": _infer_channel(clean_title, clean_body),
                "cashbackType": reward["type"],
                "cashbackValue": reward["value"],
                "minAmount": min_amount,
                "maxCashback": max_cashback,
                "frequencyLimit": frequency_limit,
                "requiresRegistration": requires_registration,
                "validFrom": valid_from,
                "validUntil": valid_until,
                "conditions": conditions,
                "excludedConditions": [],
                "sourceUrl": enriched_card.detail_url,
                "summary": summary,
                "status": "ACTIVE",
            }
        )

    return enriched_card, _dedupe_promotions(promotions)


def _collect_links(html: str, base_url: str) -> List[Dict[str, str]]:
    parser = _AnchorCollector()
    parser.feed(html)
    results: List[Dict[str, str]] = []
    for link in parser.links:
        href = urljoin(base_url, link["href"])
        if urlparse(href).scheme not in {"http", "https"}:
            continue
        results.append({"href": href, "text": link["text"]})
    return results


def _extract_card_name_from_link_text(text: str) -> str:
    cleaned = _collapse_text(text)
    if not cleaned:
        return ""
    if "了解更多" in cleaned:
        cleaned = cleaned.split("了解更多", 1)[0].strip()
    for splitter in ["  ", "最高", "國內", "日本", "不限", "公司戶"]:
        if splitter in cleaned:
            candidate = cleaned.split(splitter, 1)[0].strip()
            if 2 <= len(candidate) <= 30:
                return candidate
    return cleaned[:30].strip()


def _build_card_code(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").upper()
    return f"ESUN_{normalized}"


def _html_to_lines(html: str) -> List[str]:
    text = re.sub(r"<(?:br|/p|/div|/li|/tr|/h1|/h2|/h3|/h4|/h5|/h6|/section|/article|/ul|/ol)[^>]*>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.IGNORECASE)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    lines = [_collapse_text(line) for line in text.splitlines()]
    return [line for line in lines if line]


def _collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_title(value: str) -> str:
    return _collapse_text(value).strip("-:：|；; ")


def _normalize_promotion_title(card_name: str, raw_title: str, raw_body: str) -> str:
    title = _clean_title(raw_title)
    title = re.sub(r"\s*-\s*玉山銀行$", "", title)
    title = re.sub(r"\s*\|\s*玉山銀行$", "", title)
    title = re.sub(r"\s*※.*$", "", title)
    title = _collapse_text(title)

    if title.startswith(card_name):
        title = title[len(card_name):].strip(" -|：:；;")

    if not title or title in GENERIC_TITLE_TOKENS or any(token in title for token in SUMMARY_NOISE_TOKENS):
        fallback = _derive_title_from_body(raw_body)
        if fallback:
            return fallback

    if len(title) > 50:
        fallback = _derive_title_from_body(raw_body)
        if fallback:
            return fallback

    return title or "優惠活動"


def _derive_title_from_body(raw_body: str) -> str:
    for fragment in _extract_bullets(raw_body):
        candidate = _clean_summary_fragment(fragment)
        if not candidate:
            continue
        if candidate.startswith("※") or any(token in candidate for token in ["請參閱", "詳見", "說明"]):
            continue
        if _has_reward_signal(candidate):
            return candidate[:40].rstrip("；;。")

    cleaned = _clean_summary_fragment(raw_body)
    if cleaned and _has_reward_signal(cleaned):
        return cleaned[:40].rstrip("；;。")
    return ""


def _dedupe_promotions(promotions: List[Dict[str, object]]) -> List[Dict[str, object]]:
    deduped: List[Dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for promotion in promotions:
        dedupe_key = (
            promotion.get("cardCode"),
            promotion.get("title"),
            promotion.get("category"),
            promotion.get("channel"),
            promotion.get("cashbackType"),
            promotion.get("cashbackValue"),
            promotion.get("minAmount"),
            promotion.get("maxCashback"),
            promotion.get("validFrom"),
            promotion.get("validUntil"),
            promotion.get("summary"),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(promotion)
    return deduped


def _clean_offer_text(value: str) -> str:
    cleaned = _collapse_text(value.replace("\u3000", " "))
    cleaned = re.sub(r"(\d+)\.\s*[；;:：]?\s*(\d+)%", r"\1.\2%", cleaned)
    cleaned = re.sub(r"(\d+)\.\s*[；;:：]?\s*(\d+)元", r"\1.\2元", cleaned)
    cleaned = re.sub(r"\s*[※]+\s*", " ※", cleaned)
    cleaned = re.sub(r"[；;]{2,}", "；", cleaned)
    return cleaned.strip("；; ")


def _extract_card_title(lines: List[str]) -> str | None:
    for line in lines[:80]:
        if line.startswith("玉山") and "卡" in line and len(line) <= 30:
            return line
    return None


def _extract_apply_url(links: List[Dict[str, str]]) -> str | None:
    for link in links:
        if re.search(r"申辦|申請", link["text"]):
            return link["href"]
    return None


def _extract_sections(lines: List[str]) -> List[str]:
    return [line for line in lines if line in SECTION_HEADINGS]


def _extract_annual_fee_summary(lines: List[str]) -> str | None:
    for index, line in enumerate(lines):
        if line == "年費":
            return _collapse_text(" ".join(lines[index + 1:index + 6]))
    for line in lines:
        if "首年免年費" in line or line.startswith("•玉山") and "年費" in line:
            return line
    return None


def _extract_annual_fee_amount(summary: str | None) -> int:
    if not summary:
        return 0
    match = re.search(r"正卡\s*([\d,]+)元", summary)
    if match:
        return int(match.group(1).replace(",", ""))
    match = re.search(r"年費\s*([\d,]+)元", summary)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


def _extract_application_requirements(lines: List[str]) -> List[str]:
    requirements: List[str] = []
    for line in lines:
        if any(token in line for token in ["年滿18歲", "年滿15歲", "財力證明", "申辦雙幣卡須", "臺外幣帳戶", "同一持卡人"]):
            requirements.append(line)
    return list(dict.fromkeys(requirements))[:6]


def _extract_offer_blocks(lines: List[str]) -> List[Dict[str, str]]:
    blocks: List[Dict[str, str]] = []
    current_section = ""
    current_title = ""
    current_body: List[str] = []

    def flush() -> None:
        nonlocal current_title, current_body
        if not current_title:
            return
        body = _collapse_text(" ".join(current_body))
        if _is_real_offer_block(current_title, body):
            blocks.append({"section": current_section, "title": current_title, "body": body})
        current_title = ""
        current_body = []

    for line in lines:
        if line in SECTION_HEADINGS:
            flush()
            current_section = line
            continue

        if current_section not in {"卡片特色", "專屬優惠", "Pi拍錢包加碼", "卡友禮遇服務"}:
            continue

        if _is_subsection_title(line):
            flush()
            current_title = line
            continue

        if current_title:
            current_body.append(line)

    flush()
    return blocks


def _is_subsection_title(line: str) -> bool:
    if line in SUBSECTION_SKIP:
        return False
    if len(line) < 2 or len(line) > 40:
        return False
    if line.startswith("•"):
        return False
    if re.search(r"\d{4}/\d{1,2}/\d{1,2}", line):
        return False
    if any(token in line for token in ["http", "https", "活動詳情", "立即登錄", "了解更多"]):
        return False
    return True


def _is_real_offer_block(title: str, body: str) -> bool:
    if len(body) < 40:
        return False
    has_value = bool(re.search(r"\d+(?:\.\d+)?%|[\d,]+元|[\d,]+P幣|[\d,]+點", body))
    has_period = bool(re.search(r"\d{4}/\d{1,2}/\d{1,2}\s*[~～-]\s*\d{4}/\d{1,2}/\d{1,2}", body))
    return has_value and has_period and title not in SUBSECTION_SKIP


def _extract_reward(title: str, text: str) -> Dict[str, object] | None:
    title_candidates = _extract_reward_candidates(title, title_weight=50)
    if title_candidates:
        selected = max(title_candidates, key=lambda candidate: (candidate.score, candidate.value))
        return {"type": selected.reward_type, "value": round(selected.value, 2)}

    body_candidates = _extract_reward_candidates(text, title_weight=0)
    if not body_candidates:
        return None

    selected = max(body_candidates, key=lambda candidate: (candidate.score, candidate.value))
    return {"type": selected.reward_type, "value": round(selected.value, 2)}


def _extract_reward_candidates(text: str, title_weight: int) -> List[RewardCandidate]:
    candidates: List[RewardCandidate] = []
    fragments = [fragment for fragment in _extract_bullets(text) if fragment]
    if not fragments:
        fragments = [_collapse_text(text)]

    for index, fragment in enumerate(fragments):
        order_bonus = max(0, 5 - index)
        for match in re.finditer(r"(\d+(?:\.\d+)?)%", fragment):
            value = float(match.group(1))
            context = _match_context(fragment, match.start(), match.end())
            reward_type = "POINTS" if any(token in context for token in ["P幣", "e point", "點數", "里程", "哩"]) else "PERCENT"
            score = _score_reward_candidate(fragment, context, reward_type, title_weight, order_bonus)
            candidates.append(RewardCandidate(reward_type=reward_type, value=value, label=fragment, score=score))

        for match in re.finditer(r"([\d,]+)\s*(元|點|日圓)", fragment):
            value = float(match.group(1).replace(",", ""))
            unit = match.group(2)
            context = _match_context(fragment, match.start(), match.end())
            if not _is_reward_like_fixed_context(context):
                continue
            reward_type = _classify_fixed_reward_type(unit, context)
            score = _score_reward_candidate(fragment, context, reward_type, title_weight, order_bonus)
            if any(token in context for token in ["上限", "單筆交易回饋上限", "每歸戶回饋上限"]):
                score -= 8
            candidates.append(RewardCandidate(reward_type=reward_type, value=value, label=fragment, score=score))

    return candidates


def _match_context(fragment: str, start: int, end: int) -> str:
    left = max(0, start - 24)
    right = min(len(fragment), end + 24)
    return fragment[left:right]


def _is_reward_like_fixed_context(context: str) -> bool:
    return any(token in context for token in ["回饋", "現折", "折扣", "優惠", "即享券", "折抵", "贈", "刷卡金", "點"])


def _classify_fixed_reward_type(unit: str, context: str) -> str:
    if unit == "點" or any(token in context for token in ["e point", "點數", "里程", "哩"]):
        return "POINTS"
    return "FIXED"


def _score_reward_candidate(fragment: str, context: str, reward_type: str, title_weight: int, order_bonus: int) -> int:
    score = title_weight + order_bonus

    positive_signals = ["最高享", "最高", "回饋", "加碼", "現折", "折扣", "優惠", "贈", "刷卡金", "折抵"]
    negative_signals = ["上限", "門檻", "滿額", "累積滿", "單筆滿", "限量", "活動期間", "旅遊期限", "入住期間", "預訂期限"]

    score += sum(6 for token in positive_signals if token in context)
    score -= sum(4 for token in negative_signals if token in context)

    if reward_type == "POINTS" and any(token in context for token in ["回饋", "加碼", "e point", "點數"]):
        score += 5
    if reward_type == "FIXED" and any(token in context for token in ["現折", "折抵", "刷卡金"]):
        score += 5
    if reward_type == "FIXED" and any(token in context for token in ["即享券", "優惠券", "購物券"]):
        score += 2
    if reward_type == "PERCENT" and any(token in context for token in ["最高享", "回饋", "加碼"]):
        score += 5

    if "並同享" in fragment and reward_type == "PERCENT":
        score -= 3
    if "再享" in fragment and reward_type == "FIXED":
        score += 3
    if fragment.startswith(("最高享", "享最高", "滿額再享", "現折", "加碼", "回饋")):
        score += 4

    return score


def _extract_date_range(text: str) -> tuple[str | None, str | None]:
    match = re.search(r"(\d{4}/\d{1,2}/\d{1,2})\s*[~～-]\s*(\d{4}/\d{1,2}/\d{1,2})", text)
    if not match:
        return None, None
    return _normalize_date(match.group(1)), _normalize_date(match.group(2))


def _normalize_date(value: str) -> str:
    year, month, day = value.split("/")
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _extract_min_amount(text: str) -> int:
    matches = re.findall(r"滿\s*([\d,]+)\s*元", text)
    if not matches:
        return 0
    return min(int(match.replace(",", "")) for match in matches)


def _extract_cap(text: str) -> int | None:
    matches = re.findall(r"上限\s*([\d,]+)\s*(?:P幣|元|點|日圓)", text)
    if not matches:
        return None
    return max(int(match.replace(",", "")) for match in matches)


def _extract_frequency_limit(text: str) -> str:
    if "每月" in text:
        return "MONTHLY"
    if "每季" in text:
        return "QUARTERLY"
    if "每年" in text:
        return "YEARLY"
    if "限領1次" in text or "限參加登錄1次" in text or "僅限兌換1次" in text:
        return "ONCE"
    return "NONE"


def _infer_category(title: str, body: str, card_name: str) -> str:
    text = f"{title} {body}"
    scores = {category: _score_signals(text, signals) for category, signals in CATEGORY_SIGNALS.items()}
    if scores["OVERSEAS"] >= 3 and scores["OVERSEAS"] >= scores["ONLINE"]:
        return "OVERSEAS"
    best_category = max(scores, key=scores.get)
    return best_category if scores[best_category] > 0 else "OTHER"


def _infer_channel(title: str, body: str) -> str:
    text = f"{title} {body}"
    scores = {channel: _score_signals(text, signals) for channel, signals in CHANNEL_SIGNALS.items()}
    if scores["ALL"] > 0:
        return "ALL"
    if scores["ONLINE"] > 0 and scores["OFFLINE"] > 0 and abs(scores["ONLINE"] - scores["OFFLINE"]) <= 1:
        return "ALL"
    if scores["ONLINE"] > scores["OFFLINE"]:
        return "ONLINE"
    if scores["OFFLINE"] > 0:
        return "OFFLINE"
    return "ALL"


def _build_summary(title: str, body: str, valid_from: str, valid_until: str, min_amount: int, max_cashback: int | None, requires_registration: bool) -> str:
    bullets = _extract_bullets(body)
    summary_parts = [title]

    reward_fragment = _pick_summary_fragment(bullets, prefer_reward=True)
    qualifier_fragment = _pick_summary_fragment(bullets, prefer_reward=False)
    for fragment in (reward_fragment, qualifier_fragment):
        if fragment and fragment not in summary_parts:
            summary_parts.append(fragment)

    fallback_bits: List[str] = []
    if min_amount > 0:
        fallback_bits.append(f"滿{min_amount:,}元")
    if max_cashback is not None:
        fallback_bits.append(f"上限{max_cashback:,}")
    if requires_registration:
        fallback_bits.append("需登錄")
    if fallback_bits:
        summary_parts.append(" / ".join(fallback_bits))

    summary_parts.append(f"期間 {valid_from}~{valid_until}")
    return _collapse_text("；".join(summary_parts))[:300]


def _extract_bullets(text: str) -> List[str]:
    bullet_matches = re.findall(r"•\s*([^•]+?)(?=(?:•|$))", text)
    if bullet_matches:
        return [_clean_summary_fragment(match) for match in bullet_matches if _clean_summary_fragment(match)]
    normalized = text.replace("；", "。")
    chunks = re.split(r"(?<=[。！？])|(?<!\d)\.(?!\d)", normalized)
    return [_clean_summary_fragment(chunk) for chunk in chunks if _clean_summary_fragment(chunk)]


def _pick_summary_fragment(fragments: List[str], prefer_reward: bool) -> str | None:
    for fragment in fragments:
        if prefer_reward and _has_reward_signal(fragment):
            return fragment
        if not prefer_reward and _has_qualifier_signal(fragment):
            return fragment
    return None


def _clean_summary_fragment(value: str) -> str:
    cleaned = _clean_offer_text(value)
    cleaned = re.sub(r"(?:活動詳情|注意事項|了解更多|專屬網頁)", "", cleaned)
    cleaned = re.sub(r"\s*※.*$", "", cleaned)
    cleaned = _collapse_text(cleaned).strip("；; ")
    if len(cleaned) < 4:
        return ""
    if cleaned.startswith(("、", "及", ",", "，")):
        return ""
    if any(token in cleaned for token in ["請參閱活動網頁", "請參閱活動", "詳情請參閱"]):
        return ""
    if any(token in cleaned for token in SUMMARY_NOISE_TOKENS) and not _has_reward_signal(cleaned):
        return ""
    return cleaned[:120]


def _has_reward_signal(value: str) -> bool:
    return bool(re.search(r"\d+(?:\.\d+)?%|[\d,]+元|[\d,]+點|[\d,]+日圓|回饋|折扣|現折|優惠", value))


def _has_qualifier_signal(value: str) -> bool:
    return any(token in value for token in ["滿", "上限", "登錄", "指定", "一般消費", "實體", "通路", "綁定", "國內", "日本", "海外"])


def _score_signals(text: str, signals: List[tuple[str, int]]) -> int:
    return sum(weight for keyword, weight in signals if keyword in text)


def _build_conditions(text: str, application_requirements: Iterable[str], requires_registration: bool) -> List[Dict[str, str]]:
    conditions: List[Dict[str, str]] = []

    if requires_registration:
        conditions.append({"type": "REGISTRATION_REQUIRED", "value": "true", "label": "需登錄活動"})

    for requirement in list(dict.fromkeys(application_requirements))[:3]:
        conditions.append({"type": "TEXT", "value": _to_condition_value(requirement), "label": requirement[:120]})

    for bullet in _extract_bullets(text)[:3]:
        if any(token in bullet for token in ["活動詳情", "立即登錄", "注意事項"]):
            continue
        conditions.append({"type": "TEXT", "value": _to_condition_value(bullet), "label": bullet[:120]})

    deduped: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for condition in conditions:
        key = (condition["type"], condition["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(condition)
    return deduped


def _to_condition_value(text: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", text).strip("_")
    return normalized[:80].upper() or "TEXT"