from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from extractor.html_utils import collapse_text


THRESHOLD_LEFT_PATTERN = re.compile(
    r"(?:"
    r"滿|達|達到|累積滿|累積新增|新增一般消費滿|"
    r"單筆消費滿|消費滿|"
    r"符合|符合條件|符合消費門檻|活動門檻|消費門檻|門檻|條件|"
    r"支付|刷卡支付|票款|票款或|團費|團費或|旅遊團費|機票|"
    r"金額|金額合計達|消費金額|消費額|費用"
    r")\s*$"
)

THRESHOLD_RIGHT_PATTERN = re.compile(
    r"^\s*(?:"
    r"以上|以上之|\(\s*含\s*\)\s*以上|即可|即享|可享|享有|享|"
    r"贈|送|現折|折抵|回饋|加碼|始符合|方可|才可|即符合"
    r")"
)

NON_REWARD_PROMOTION_TOKENS = (
    "抽獎",
    "贈品價值",
    "活動總數量",
    "總數量",
    "名額",
    "抽",
    "機會",
    "乙組",
    "乙次抽獎",
    "發票",
    "載具",
    "三聯",
    "統編",
    "分期零利率"
)

CAP_VALUE_TOKENS = (
    "上限",
    "回饋上限",
    "每月回饋上限",
    "每卡每月回饋上限",
    "累計上限",
    "最高回饋",
)


@dataclass
class RewardCandidate:
    reward_type: str
    value: float
    label: str
    score: int


def clean_title(value: str) -> str:
    return collapse_text(value).strip("-:：|；; ")


def normalize_promotion_title(
    card_name: str,
    raw_title: str,
    raw_body: str,
    *,
    generic_title_tokens: Iterable[str],
    summary_noise_tokens: Sequence[str],
    bank_suffixes: Iterable[str] = (),
) -> str:
    title = clean_title(raw_title)
    for suffix in bank_suffixes:
        title = re.sub(rf"\s*[-|]\s*{re.escape(suffix)}$", "", title)
    title = re.sub(r"\s*※.*$", "", title)
    title = collapse_text(title)

    if title.startswith(card_name):
        title = title[len(card_name):].strip(" -|：:；;")

    if not title or title in set(generic_title_tokens) or any(token in title for token in summary_noise_tokens):
        fallback = derive_title_from_body(raw_body, summary_noise_tokens)
        if fallback:
            return fallback

    if len(title) > 50:
        fallback = derive_title_from_body(raw_body, summary_noise_tokens)
        if fallback:
            return fallback

    return title or "優惠活動"


def derive_title_from_body(raw_body: str, summary_noise_tokens: Sequence[str]) -> str:
    for fragment in extract_bullets(raw_body):
        candidate = clean_summary_fragment(fragment, summary_noise_tokens)
        if not candidate:
            continue
        if candidate.startswith("※") or any(token in candidate for token in ["請參閱", "詳見", "說明"]):
            continue
        if has_reward_signal(candidate):
            return candidate[:40].rstrip("；;。")

    cleaned = clean_summary_fragment(raw_body, summary_noise_tokens)
    if cleaned and has_reward_signal(cleaned):
        return cleaned[:40].rstrip("；;。")
    return ""


def dedupe_promotions(promotions: List[Dict[str, object]]) -> List[Dict[str, object]]:
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


def clean_offer_text(value: str) -> str:
    cleaned = collapse_text(value.replace("\u3000", " "))
    cleaned = re.sub(r"(\d+)\.\s*[；;:：]?\s*(\d+)%", r"\1.\2%", cleaned)
    cleaned = re.sub(r"(\d+)\.\s*[；;:：]?\s*(\d+)元", r"\1.\2元", cleaned)
    cleaned = re.sub(r"\s*[※]+\s*", " ※", cleaned)
    cleaned = re.sub(r"[；;]{2,}", "；", cleaned)
    return cleaned.strip("；; ")


def extract_reward(title: str, text: str) -> Dict[str, object] | None:
    title_candidates = extract_reward_candidates(title, title_weight=50)
    if title_candidates:
        selected = max(title_candidates, key=lambda candidate: (candidate.score, candidate.value))
        return {"type": selected.reward_type, "value": round(selected.value, 2)}

    body_candidates = extract_reward_candidates(text, title_weight=0)
    if not body_candidates:
        return None

    selected = max(body_candidates, key=lambda candidate: (candidate.score, candidate.value))
    return {"type": selected.reward_type, "value": round(selected.value, 2)}


def extract_reward_candidates(text: str, title_weight: int) -> List[RewardCandidate]:
    candidates: List[RewardCandidate] = []
    fragments = [fragment for fragment in extract_bullets(text) if fragment]
    if not fragments:
        fragments = [collapse_text(text)]

    for index, fragment in enumerate(fragments):
        order_bonus = max(0, 5 - index)
        for match in re.finditer(r"(\d+(?:\.\d+)?)%", fragment):
            value = float(match.group(1))
            context = match_context(fragment, match.start(), match.end())
            left_context, right_context = match_local_context(fragment, match.start(), match.end())
            if is_non_reward_promotion_context(context):
                continue
            if is_cap_value_context(left_context, right_context):
                continue
            # Skip condition-threshold patterns like "團費80%以上"
            if re.search(r"\d+(?:\.\d+)?%\s*以上", context) and not any(token in context for token in ["回饋", "現折", "折扣", "加碼"]):
                continue
            if looks_like_threshold_value(left_context, right_context):
                continue
            # Skip redemption-ratio patterns: "100%折抵" means currency offsets 100%, not cashback
            if re.match(r"\s*折抵", right_context) and not any(token in context for token in ["回饋", "加碼"]):
                continue
            reward_type = "POINTS" if any(token in context for token in ["P幣", "e point", "點數", "里程", "哩"]) else "PERCENT"
            score = score_reward_candidate(fragment, context, reward_type, title_weight, order_bonus)
            # Penalize unrealistically high cashback percentages (real card rewards rarely exceed 20%)
            if value >= 50:
                score -= 20
            elif value >= 20:
                score -= 10
            candidates.append(RewardCandidate(reward_type=reward_type, value=value, label=fragment, score=score))

        for match in re.finditer(r"([\d,]+)\s*(元|點|日圓)", fragment):
            value = float(match.group(1).replace(",", ""))
            unit = match.group(2)
            context = match_context(fragment, match.start(), match.end())
            left_context, right_context = match_local_context(fragment, match.start(), match.end())
            if is_non_reward_promotion_context(context):
                continue
            if is_cap_value_context(left_context, right_context):
                continue
            if looks_like_threshold_value(left_context, right_context):
                continue
            if not is_reward_like_fixed_context(context):
                continue
            reward_type = classify_fixed_reward_type(unit, context)
            score = score_reward_candidate(fragment, context, reward_type, title_weight, order_bonus)
            if any(token in context for token in ["上限", "單筆交易回饋上限", "每歸戶回饋上限"]):
                score -= 8
            # Penalize suspiciously large fixed/points values — likely cap descriptions, not actual rewards
            if value >= 5000:
                score -= 15
            elif value >= 1000:
                score -= 5
            # "最高" with large values is almost always a cap description, not reward
            if value >= 1000 and any(token in context for token in ["最高", "最多", "累計最高"]):
                score -= 10
            # Guardrail: Heavy penalty for prices disguised as fixed rewards (e.g., 優惠價 3150 元)
            if any(token in context for token in ["優惠價", "原價", "特價", "起"]):
                continue
            # Guardrail: Skip per-unit rewards (e.g., "每公升折抵2元") — not flat fixed cashback
            if any(token in context for token in ["每公升", "每次", "每筆", "每件", "每位", "每人", "每杯", "每組"]):
                continue
            candidates.append(RewardCandidate(reward_type=reward_type, value=value, label=fragment, score=score))

    return candidates


def match_context(fragment: str, start: int, end: int) -> str:
    left = max(0, start - 24)
    right = min(len(fragment), end + 24)
    return fragment[left:right]


def match_local_context(fragment: str, start: int, end: int, *, window: int = 18) -> tuple[str, str]:
    left = collapse_text(fragment[max(0, start - window):start]).rstrip(" ，,、:：;；")
    right = collapse_text(fragment[end:min(len(fragment), end + window)]).lstrip(" ，,、:：;；")
    return left, right


def looks_like_threshold_value(left_context: str, right_context: str) -> bool:
    normalized_right = right_context.replace(" ", "")
    if "門檻" in left_context or "條件" in left_context:
        return True
    if THRESHOLD_LEFT_PATTERN.search(left_context) and THRESHOLD_RIGHT_PATTERN.match(normalized_right):
        return True
    if THRESHOLD_LEFT_PATTERN.search(left_context) and any(
        token in normalized_right for token in ("贈", "送", "現折", "折抵", "回饋", "加碼", "折")
    ):
        return True
    return False


def is_non_reward_promotion_context(context: str) -> bool:
    return any(token in context for token in NON_REWARD_PROMOTION_TOKENS)


def is_cap_value_context(left_context: str, right_context: str) -> bool:
    return any(token in left_context for token in CAP_VALUE_TOKENS) or any(
        right_context.startswith(token) for token in CAP_VALUE_TOKENS
    )


def is_reward_like_fixed_context(context: str) -> bool:
    return any(token in context for token in ["回饋", "現折", "折扣", "優惠", "即享券", "折抵", "贈", "刷卡金", "點"])


def classify_fixed_reward_type(unit: str, context: str) -> str:
    if unit == "點" or any(token in context for token in ["e point", "點數", "里程", "哩"]):
        return "POINTS"
    return "FIXED"


def score_reward_candidate(fragment: str, context: str, reward_type: str, title_weight: int, order_bonus: int) -> int:
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


def extract_date_range(text: str) -> tuple[str | None, str | None]:
    # Full format: 2026/1/1~2026/3/31 or ROC 115/1/1~115/6/30
    match = re.search(r"(\d{3,4}/\d{1,2}/\d{1,2})\s*[~～-]\s*(\d{3,4}/\d{1,2}/\d{1,2})", text)
    if match:
        return normalize_date(match.group(1)), normalize_date(match.group(2))
    # Short format: 2026/1/1-3/31 or 115/1/1-6/30 (end date missing year, infer from start)
    match = re.search(r"(\d{3,4})/(\d{1,2}/\d{1,2})\s*[~～-]\s*(\d{1,2}/\d{1,2})", text)
    if match:
        year = match.group(1)
        start = f"{year}/{match.group(2)}"
        end = f"{year}/{match.group(3)}"
        return normalize_date(start), normalize_date(end)
    return None, None


def normalize_date(value: str) -> str:
    year, month, day = value.split("/")
    year_int = int(year)
    # Convert ROC calendar (3-digit, e.g. 115) to Gregorian
    if year_int < 1000:
        year_int += 1911
    return f"{year_int:04d}-{int(month):02d}-{int(day):02d}"


def extract_min_amount(text: str) -> int:
    matches = re.findall(r"滿\s*([\d,]+)\s*元", text)
    if not matches:
        return 0
    return min(int(match.replace(",", "")) for match in matches)


def extract_cap(text: str) -> int | None:
    cap_patterns = [
        r"上限\s*([\d,]+)\s*(?:P幣|元|點|日圓)",
        r"(?:每月|每季|每年|每歸戶|每戶|每卡)(?:最高|回饋上限|累計上限)?\s*(?:回饋)?\s*([\d,]+)\s*(?:P幣|元|點|日圓)",
        r"最高(?:回饋|可得|可享)?\s*([\d,]+)\s*(?:P幣|元|點|日圓)",
        r"回饋上限\s*([\d,]+)\s*(?:P幣|元|點|日圓)",
        r"(?:封頂|回饋金額上限)\s*([\d,]+)\s*(?:P幣|元|點|日圓)",
    ]
    all_matches: list[int] = []
    for pattern in cap_patterns:
        for match in re.findall(pattern, text):
            all_matches.append(int(match.replace(",", "")))
    if not all_matches:
        return None
    return max(all_matches)


def extract_frequency_limit(text: str) -> str:
    if "每月" in text:
        return "MONTHLY"
    if "每季" in text:
        return "QUARTERLY"
    if "每年" in text:
        return "YEARLY"
    if "限領1次" in text or "限參加登錄1次" in text or "僅限兌換1次" in text:
        return "ONCE"
    return "NONE"


def classify_recommendation_scope(title: str, body: str, category: str | None = None) -> str:
    text = f"{title} {body}"

    future_scope_tokens = (
        "新戶",
        "首刷",
        "首次申辦",
        "核卡後",
        "保費",
        "壽險",
        "保險",
        "財富管理會員",
        "公會會員",
        "附卡首刷",
        "新卡友",
    )
    catalog_only_tokens = (
        "道路救援",
        "機場接送",
        "旅遊保障",
        "白金會員",
        "會員禮遇",
        "通道服務",
        "貴賓室",
        "停車",
        "專屬禮遇",
        "禮遇",
        "服務",
        "借電券",
        "折扣券",
        "抵用券",
        "優惠券",
        "充電券",
        "兌換碼",
        "抽獎",
        "贈品價值",
        "活動總數量",
        "名額",
    )

    if any(token in text for token in future_scope_tokens):
        return "FUTURE_SCOPE"
    if any(token in text for token in catalog_only_tokens):
        return "CATALOG_ONLY"
    if category == "OTHER" and any(token in text for token in ("會員", "服務", "優惠券", "購票優惠")):
        return "CATALOG_ONLY"
    return "RECOMMENDABLE"


def infer_category(
    title: str,
    body: str,
    category_signals: Dict[str, List[tuple[str, int]]],
    *,
    overseas_category: str | None = None,
) -> str:
    text = f"{title} {body}"
    scores = {category: score_signals(text, signals) for category, signals in category_signals.items()}
    if overseas_category and scores.get(overseas_category, 0) >= 3 and scores.get(overseas_category, 0) >= scores.get("ONLINE", 0):
        return overseas_category
    best_category = max(scores, key=scores.get)
    return best_category if scores[best_category] > 0 else "OTHER"


def infer_channel(title: str, body: str, channel_signals: Dict[str, List[tuple[str, int]]]) -> str:
    text = f"{title} {body}"
    scores = {channel: score_signals(text, signals) for channel, signals in channel_signals.items()}
    online_score = scores.get("ONLINE", 0)
    offline_score = scores.get("OFFLINE", 0)
    all_score = scores.get("ALL", 0)

    if online_score == 0 and offline_score == 0:
        return "ALL"
    if online_score > 0 and offline_score == 0:
        return "ONLINE"
    if offline_score > 0 and online_score == 0:
        return "OFFLINE" if offline_score >= all_score else "ALL"
    if abs(online_score - offline_score) <= 1:
        return "ALL"
    return "ONLINE" if online_score > offline_score else "OFFLINE"


def build_summary(
    title: str,
    body: str,
    valid_from: str,
    valid_until: str,
    min_amount: int,
    max_cashback: int | None,
    requires_registration: bool,
    *,
    summary_noise_tokens: Sequence[str],
) -> str:
    bullets = extract_bullets(body)
    summary_parts = [title]

    reward_fragment = pick_summary_fragment(bullets, prefer_reward=True)
    qualifier_fragment = pick_summary_fragment(bullets, prefer_reward=False)
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
    summary = collapse_text("；".join(summary_parts))[:300]
    return clean_summary_fragment(summary, summary_noise_tokens) or summary


def extract_bullets(text: str) -> List[str]:
    bullet_matches = re.findall(r"•\s*([^•]+?)(?=(?:•|$))", text)
    if bullet_matches:
        return [clean_summary_fragment(match, ()) for match in bullet_matches if clean_summary_fragment(match, ())]
    normalized = text.replace("；", "。")
    chunks = re.split(r"(?<=[。！？])|(?<!\d)\.(?!\d)", normalized)
    return [clean_summary_fragment(chunk, ()) for chunk in chunks if clean_summary_fragment(chunk, ())]


def pick_summary_fragment(fragments: List[str], prefer_reward: bool) -> str | None:
    for fragment in fragments:
        if prefer_reward and has_reward_signal(fragment):
            return fragment
        if not prefer_reward and has_qualifier_signal(fragment):
            return fragment
    return None


def clean_summary_fragment(value: str, summary_noise_tokens: Sequence[str]) -> str:
    cleaned = clean_offer_text(value)
    cleaned = re.sub(r"(?:活動詳情|注意事項|了解更多|專屬網頁)", "", cleaned)
    cleaned = re.sub(r"\s*※.*$", "", cleaned)
    cleaned = collapse_text(cleaned).strip("；; ")
    if len(cleaned) < 4:
        return ""
    if cleaned.startswith(("、", "及", ",", "，")):
        return ""
    if any(token in cleaned for token in ["請參閱活動網頁", "請參閱活動", "詳情請參閱"]):
        return ""
    if any(token in cleaned for token in summary_noise_tokens) and not has_reward_signal(cleaned):
        return ""
    return cleaned[:120]


def has_reward_signal(value: str) -> bool:
    return bool(re.search(r"\d+(?:\.\d+)?%|[\d,]+元|[\d,]+點|[\d,]+日圓|回饋|折扣|現折|優惠", value))


def has_qualifier_signal(value: str) -> bool:
    return any(token in value for token in ["滿", "上限", "登錄", "指定", "一般消費", "實體", "通路", "綁定", "國內", "日本", "海外"])


def score_signals(text: str, signals: List[tuple[str, int]]) -> int:
    return sum(weight for keyword, weight in signals if keyword in text)


SUBCATEGORY_SIGNALS: Dict[str, Dict[str, List[tuple[str, int]]]] = {
    "ENTERTAINMENT": {
        "MOVIE":      [("電影", 5), ("影城", 5), ("威秀", 4), ("秀泰", 4), ("國賓", 4), ("影廳", 3)],
        "THEME_PARK": [("樂園", 5), ("遊樂", 5), ("麗寶", 4), ("六福村", 4), ("劍湖山", 4), ("門票", 3)],
        "VENUE":      [("KTV", 5), ("好樂迪", 4), ("錢櫃", 4), ("桌遊", 3), ("保齡球", 3)],
        "STREAMING":  [("Netflix", 5), ("Spotify", 4), ("KKBOX", 4), ("串流", 4), ("Disney+", 4), ("訂閱", 2)],
    },
    "DINING": {
        "DELIVERY":     [("外送", 5), ("UberEats", 5), ("foodpanda", 5), ("熊貓", 4), ("Uber Eats", 5)],
        "RESTAURANT":   [("指定餐廳", 5), ("合作餐廳", 5), ("特約餐廳", 4), ("指定門市", 3)],
        "CAFE":         [("星巴克", 5), ("Starbucks", 5), ("咖啡", 3), ("手搖", 4), ("飲料", 2)],
        "HOTEL_DINING": [("飯店", 4), ("酒店", 4), ("自助餐", 3), ("buffet", 4), ("Buffet", 4)],
    },
    "SHOPPING": {
        "DEPARTMENT":   [("百貨", 5), ("SOGO", 5), ("新光三越", 5), ("遠百", 5), ("週年慶", 4), ("統一時代", 4)],
        "WAREHOUSE":    [("Costco", 5), ("好市多", 5), ("家樂福", 5), ("大潤發", 5), ("量販", 4)],
        "ELECTRONICS":  [("3C", 5), ("家電", 4), ("燦坤", 5), ("全國電子", 5), ("Apple Store", 4)],
    },
    "ONLINE": {
        "ECOMMERCE":    [("蝦皮", 5), ("momo", 5), ("PChome", 5), ("博客來", 4), ("Yahoo", 3), ("樂天", 4)],
        "MOBILE_PAY":   [("Line Pay", 5), ("街口", 5), ("全盈", 4), ("台灣Pay", 4), ("悠遊付", 4)],
        "SUBSCRIPTION": [("訂閱", 4), ("月費", 3), ("年費", 3), ("自動扣繳", 3)],
    },
}


def infer_subcategory(
    title: str,
    body: str,
    category: str,
    subcategory_signals: Dict[str, Dict[str, List[tuple[str, int]]]],
) -> str:
    if category not in subcategory_signals:
        return "GENERAL"
    text = f"{title} {body}"
    scores = {
        sub: score_signals(text, signals)
        for sub, signals in subcategory_signals[category].items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] >= 3 else "GENERAL"


def build_conditions(
    text: str,
    application_requirements: Iterable[str],
    requires_registration: bool,
    *,
    skip_tokens: Sequence[str] = ("活動詳情", "立即登錄", "注意事項"),
) -> List[Dict[str, str]]:
    conditions: List[Dict[str, str]] = []

    if requires_registration:
        conditions.append({"type": "REGISTRATION_REQUIRED", "value": "true", "label": "需登錄活動"})

    for requirement in list(dict.fromkeys(application_requirements))[:3]:
        conditions.append({"type": "TEXT", "value": to_condition_value(requirement), "label": requirement[:120]})

    for bullet in extract_bullets(text)[:3]:
        if any(token in bullet for token in skip_tokens):
            continue
        if requires_registration and "登錄" in bullet:
            continue
        conditions.append({"type": "TEXT", "value": to_condition_value(bullet), "label": bullet[:120]})

    deduped: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for condition in conditions:
        key = (condition["type"], condition["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(condition)
    return deduped


def to_condition_value(text: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", text).strip("_")
    return normalized[:80].upper() or "TEXT"