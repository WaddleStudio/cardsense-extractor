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
        "DRUGSTORE":    [("康是美", 5), ("屈臣氏", 5), ("藥妝", 4), ("美妝", 3)],
        "SPORTING_GOODS": [("迪卡儂", 5), ("運動用品", 4), ("體育用品", 4)],
        "APPAREL":      [("UNIQLO", 5), ("NET", 5), ("服飾", 4), ("成衣", 4)],
    },
    "ONLINE": {
        "ECOMMERCE":    [("蝦皮", 5), ("momo", 5), ("PChome", 5), ("博客來", 4), ("Yahoo", 3), ("樂天", 4)],
        "MOBILE_PAY":   [("Line Pay", 5), ("街口", 5), ("全盈", 4), ("台灣Pay", 4), ("悠遊付", 4)],
        "SUBSCRIPTION": [("訂閱", 4), ("月費", 3), ("年費", 3), ("自動扣繳", 3)],
        "AI_TOOL":      [("ChatGPT", 5), ("Claude", 5), ("Cursor", 5), ("Gemini", 4), ("Perplexity", 4), ("Notion", 4), ("Canva", 4), ("Gamma", 4), ("Duolingo", 3), ("Speak", 3), ("AI工具", 5)],
        "TRAVEL_PLATFORM": [("Hotels.com", 5), ("Agoda", 5), ("Booking", 5), ("Trip.com", 5), ("AsiaYo", 4), ("Klook", 4), ("KKday", 4), ("AIRSIM", 4)],
        "INTERNATIONAL_ECOMMERCE": [("Coupang", 5), ("酷澎", 5), ("淘寶", 5), ("天貓", 5), ("國際電商", 4)],
    },
    "TRANSPORT": {
        "RIDESHARE":    [("Uber", 5), ("Grab", 5), ("yoxi", 5), ("台灣大車隊", 5), ("iRent", 4), ("和運租車", 4), ("格上租車", 4), ("GoShare", 5), ("WeMo", 5)],
        "PUBLIC_TRANSIT": [("台鐵", 5), ("高鐵", 5), ("臺鐵", 5), ("Taiwan Railway", 4), ("THSR", 4)],
        "EV_CHARGING":  [("U-POWER", 5), ("EVOASIS", 5), ("AmpGO", 5), ("EVALUE", 5), ("USPACE", 4), ("Autopass", 4), ("車麻吉", 4)],
        "GAS_STATION":  [("台灣中油", 5), ("中油", 4), ("全國加油", 5), ("台塑石油", 5), ("台亞", 5), ("福懋", 5), ("加油", 4)],
        "AIRLINE":      [("航空", 4), ("華航", 5), ("長榮航空", 5), ("星宇航空", 5), ("虎航", 4), ("國泰航空", 5), ("樂桃", 4), ("阿聯酋", 4), ("酷航", 4), ("捷星", 4), ("ANA", 4), ("全日空", 4), ("日本航空", 4), ("亞洲航空", 4), ("聯合航空", 4), ("新加坡航空", 4), ("越捷航空", 4), ("大韓航空", 4), ("達美航空", 4), ("土耳其航空", 4), ("卡達航空", 4), ("法國航空", 4)],
    },
    "OVERSEAS": {
        "OVERSEAS_IN_STORE": [("海外實體", 5), ("海外實體消費", 6), ("國外餐飲", 4), ("飯店到店付款", 4)],
        "HOTEL": [("飯店住宿", 5), ("住宿", 4), ("東橫INN", 5), ("星野", 4), ("迪士尼飯店", 4)],
        "TRAVEL_PLATFORM": [("Agoda", 5), ("Airbnb", 5), ("Booking.com", 5), ("Trip.com", 5), ("Klook", 5), ("KKday", 5), ("易遊網", 4)],
        "TRAVEL_AGENCY": [("雄獅", 5), ("可樂旅遊", 5), ("東南旅遊", 5), ("五福旅遊", 5), ("燦星旅遊", 5), ("山富旅遊", 5), ("長汎假期", 4), ("鳳凰旅行社", 4), ("Ezfly", 4), ("旅行社", 4)],
    },
    "GROCERY": {
        "SUPERMARKET": [("家樂福", 5), ("全聯", 5), ("LOPIA", 5), ("量販", 4), ("超市", 4)],
        "CONVENIENCE_STORE": [("7-ELEVEN", 5), ("7-11", 5), ("全家便利商店", 5), ("便利商店", 4), ("超商", 4)],
    },
    "OTHER": {
        "EV_CHARGING":  [("U-POWER", 5), ("EVOASIS", 5), ("EVALUE", 5), ("TAIL", 4), ("iCharging", 5), ("充電站", 4), ("充電", 4)],
        "PARKING":      [("車麻吉", 5), ("uTagGo", 5), ("停車", 4), ("停車費", 4)],
        "HOME_LIVING":  [("IKEA", 5), ("宜家家居", 5), ("生活家居", 4)],
        "CHARITY_DONATION": [("捐款", 5), ("公益", 5), ("愛心捐款", 5), ("定期定額", 4)],
        "GAS_STATION":  [("台灣中油", 5), ("中油", 4), ("加油", 4)],
    },
}

EXTRA_SUBCATEGORY_SIGNALS: Dict[str, Dict[str, List[tuple[str, int]]]] = {
    "ENTERTAINMENT": {
        "STREAMING": [("串流", 5), ("影音平台", 4), ("YouTube Premium", 4), ("friDay影音", 4), ("MyVideo", 4), ("愛奇藝", 4)],
    },
    "DINING": {
        "DELIVERY": [("外送", 5), ("外送平台", 5)],
        "RESTAURANT": [("餐廳", 5), ("饗宴", 4), ("鐵板燒", 4), ("粵菜", 4), ("料理", 3)],
        "CAFE": [("咖啡", 5), ("星巴克", 5), ("路易莎", 4), ("cama", 4), ("85度C", 4)],
        "HOTEL_DINING": [("飯店", 5), ("酒店", 5), ("大飯店", 5), ("萬豪", 4), ("喜來登", 4), ("香格里拉", 4), ("國賓", 4), ("自助餐", 4)],
    },
    "SHOPPING": {
        "DEPARTMENT": [("百貨", 5), ("新光三越", 5), ("遠東SOGO", 5), ("遠百", 4), ("微風", 4), ("漢神", 4), ("夢時代", 4), ("統一時代", 4)],
        "DRUGSTORE": [("康是美", 5), ("屈臣氏", 5), ("藥妝", 4), ("美妝", 3)],
        "SPORTING_GOODS": [("迪卡儂", 5), ("運動用品", 4), ("體育用品", 4)],
        "APPAREL": [("UNIQLO", 5), ("NET", 5), ("服飾", 4), ("成衣", 4)],
    },
    "ONLINE": {
        "ECOMMERCE": [("網購", 5), ("線上購物", 5), ("蝦皮", 5), ("博客來", 4), ("東森購物", 4), ("Yahoo購物", 4), ("Yahoo奇摩購物", 4)],
        "MOBILE_PAY": [("LINE Pay", 5), ("街口", 5), ("街口支付", 5), ("行動支付", 5), ("電子支付", 5), ("Apple Pay", 5), ("Google Pay", 5), ("Samsung Pay", 5), ("全支付", 5), ("全盈", 4), ("Pi 拍錢包", 5), ("Pi拍錢包", 5), ("玉山WALLET電子支付", 5), ("玉山 Wallet電子支付", 5), ("台灣Pay", 5), ("悠遊付", 4), ("icash Pay", 4), ("TWQR", 4)],
        "SUBSCRIPTION": [("訂閱", 5), ("串流", 5), ("Netflix", 5), ("Disney+", 5), ("Spotify", 5), ("KKBOX", 5), ("YouTube Premium", 5), ("friDay影音", 4), ("MyVideo", 4), ("愛奇藝", 4)],
        "AI_TOOL": [("ChatGPT", 5), ("Claude", 5), ("Cursor", 5), ("Gemini", 4), ("Perplexity", 4), ("Notion", 4), ("Canva", 4), ("Gamma", 4), ("Duolingo", 3), ("Speak", 3), ("AI工具", 5)],
        "TRAVEL_PLATFORM": [("Hotels.com", 5), ("Agoda", 5), ("Booking", 5), ("Trip.com", 5), ("AsiaYo", 4), ("Klook", 4), ("KKday", 4), ("AIRSIM", 4)],
        "INTERNATIONAL_ECOMMERCE": [("Coupang", 5), ("酷澎", 5), ("淘寶", 5), ("天貓", 5), ("國際電商", 4)],
    },
    "TRANSPORT": {
        "RIDESHARE": [("Uber", 5), ("Grab", 5), ("yoxi", 5), ("台灣大車隊", 5), ("iRent", 4), ("和運租車", 4), ("格上租車", 4), ("GoShare", 5), ("WeMo", 5)],
        "PUBLIC_TRANSIT": [("台鐵", 5), ("高鐵", 5), ("臺鐵", 5), ("Taiwan Railway", 4), ("THSR", 4)],
        "EV_CHARGING": [("U-POWER", 5), ("EVOASIS", 5), ("AmpGO", 5), ("EVALUE", 5), ("USPACE", 4), ("Autopass", 4), ("車麻吉", 4)],
        "GAS_STATION": [("台灣中油", 5), ("中油", 4), ("全國加油", 5), ("台塑石油", 5), ("台亞", 5), ("福懋", 5), ("加油", 4)],
        "AIRLINE": [("航空", 4), ("華航", 5), ("長榮航空", 5), ("星宇航空", 5), ("虎航", 4), ("國泰航空", 5), ("樂桃", 4), ("阿聯酋", 4), ("酷航", 4), ("捷星", 4), ("ANA", 4), ("全日空", 4), ("日本航空", 4), ("亞洲航空", 4), ("聯合航空", 4), ("新加坡航空", 4), ("越捷航空", 4), ("大韓航空", 4), ("達美航空", 4), ("土耳其航空", 4), ("卡達航空", 4), ("法國航空", 4)],
    },
    "OVERSEAS": {
        "OVERSEAS_IN_STORE": [("海外實體", 5), ("海外實體消費", 6), ("國外餐飲", 4), ("飯店到店付款", 4)],
        "HOTEL": [("飯店住宿", 5), ("住宿", 4), ("東橫INN", 5), ("星野", 4), ("迪士尼飯店", 4)],
        "TRAVEL_PLATFORM": [("Agoda", 5), ("Airbnb", 5), ("Booking.com", 5), ("Trip.com", 5), ("Klook", 5), ("KKday", 5), ("易遊網", 4)],
        "TRAVEL_AGENCY": [("雄獅", 5), ("可樂旅遊", 5), ("東南旅遊", 5), ("五福旅遊", 5), ("燦星旅遊", 5), ("山富旅遊", 5), ("長汎假期", 4), ("鳳凰旅行社", 4), ("Ezfly", 4), ("旅行社", 4)],
    },
    "GROCERY": {
        "SUPERMARKET": [("家樂福", 5), ("全聯", 5), ("LOPIA", 5), ("量販", 4), ("超市", 4)],
        "CONVENIENCE_STORE": [("7-ELEVEN", 5), ("7-11", 5), ("全家便利商店", 5), ("便利商店", 4), ("超商", 4)],
    },
    "OTHER": {
        "EV_CHARGING": [("U-POWER", 5), ("EVOASIS", 5), ("EVALUE", 5), ("TAIL", 4), ("iCharging", 5), ("充電站", 4), ("充電", 4)],
        "PARKING": [("車麻吉", 5), ("uTagGo", 5), ("停車", 4), ("停車費", 4)],
        "HOME_LIVING": [("IKEA", 5), ("宜家家居", 5), ("生活家居", 4)],
        "CHARITY_DONATION": [("捐款", 5), ("公益", 5), ("愛心捐款", 5), ("定期定額", 4)],
        "GAS_STATION": [("台灣中油", 5), ("中油", 4), ("加油", 4)],
    },
}

for _category, _subcategory_map in EXTRA_SUBCATEGORY_SIGNALS.items():
    SUBCATEGORY_SIGNALS.setdefault(_category, {})
    for _subcategory, _signals in _subcategory_map.items():
        SUBCATEGORY_SIGNALS[_category].setdefault(_subcategory, [])
        SUBCATEGORY_SIGNALS[_category][_subcategory].extend(_signals)


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


STRUCTURED_SUBCATEGORY_CONDITION_SIGNALS: Dict[tuple[str, str], List[Dict[str, str]]] = {
    ("ONLINE", "ECOMMERCE"): [
        {"token": "PChome 24h", "type": "ECOMMERCE_PLATFORM", "value": "PCHOME_24H", "label": "PChome 24h"},
        {"token": "PChome", "type": "ECOMMERCE_PLATFORM", "value": "PCHOME_24H", "label": "PChome 24h"},
        {"token": "momo", "type": "ECOMMERCE_PLATFORM", "value": "MOMO", "label": "momo"},
        {"token": "蝦皮", "type": "ECOMMERCE_PLATFORM", "value": "SHOPEE", "label": "蝦皮"},
        {"token": "Yahoo", "type": "ECOMMERCE_PLATFORM", "value": "YAHOO", "label": "Yahoo"},
        {"token": "Coupang", "type": "ECOMMERCE_PLATFORM", "value": "COUPANG", "label": "Coupang"},
        {"token": "淘寶", "type": "ECOMMERCE_PLATFORM", "value": "TAOBAO", "label": "淘寶"},
        {"token": "天貓", "type": "ECOMMERCE_PLATFORM", "value": "TMALL", "label": "天貓"},
    ],
    ("ONLINE", "MOBILE_PAY"): [
        {"token": "LINE Pay", "type": "PAYMENT_PLATFORM", "value": "LINE_PAY", "label": "LINE Pay"},
        {"token": "Apple Pay", "type": "PAYMENT_PLATFORM", "value": "APPLE_PAY", "label": "Apple Pay"},
        {"token": "Google Pay", "type": "PAYMENT_PLATFORM", "value": "GOOGLE_PAY", "label": "Google Pay"},
        {"token": "Samsung Pay", "type": "PAYMENT_PLATFORM", "value": "SAMSUNG_PAY", "label": "Samsung Pay"},
        {"token": "街口", "type": "PAYMENT_PLATFORM", "value": "JKOPAY", "label": "JKOPay"},
        {"token": "玉山WALLET電子支付", "type": "PAYMENT_PLATFORM", "value": "ESUN_WALLET", "label": "玉山 Wallet"},
        {"token": "玉山 Wallet電子支付", "type": "PAYMENT_PLATFORM", "value": "ESUN_WALLET", "label": "玉山 Wallet"},
        {"token": "全支付", "type": "PAYMENT_PLATFORM", "value": "全支付", "label": "全支付"},
        {"token": "街口支付", "type": "PAYMENT_PLATFORM", "value": "街口支付", "label": "街口支付"},
        {"token": "悠遊付", "type": "PAYMENT_PLATFORM", "value": "悠遊付", "label": "悠遊付"},
        {"token": "全盈+PAY", "type": "PAYMENT_PLATFORM", "value": "全盈_PAY", "label": "全盈+PAY"},
        {"token": "iPASS MONEY", "type": "PAYMENT_PLATFORM", "value": "IPASS_MONEY", "label": "iPASS MONEY"},
        {"token": "icash Pay", "type": "PAYMENT_PLATFORM", "value": "ICASH_PAY", "label": "icash Pay"},
    ],
    ("ONLINE", "AI_TOOL"): [
        {"token": "ChatGPT", "type": "MERCHANT", "value": "CHATGPT", "label": "ChatGPT"},
        {"token": "Claude", "type": "MERCHANT", "value": "CLAUDE", "label": "Claude"},
        {"token": "Cursor", "type": "MERCHANT", "value": "CURSOR", "label": "Cursor"},
        {"token": "Gemini", "type": "MERCHANT", "value": "GEMINI", "label": "Gemini"},
        {"token": "Perplexity", "type": "MERCHANT", "value": "PERPLEXITY", "label": "Perplexity"},
        {"token": "Notion", "type": "MERCHANT", "value": "NOTION", "label": "Notion"},
        {"token": "Canva", "type": "MERCHANT", "value": "CANVA", "label": "Canva"},
        {"token": "Gamma", "type": "MERCHANT", "value": "GAMMA", "label": "Gamma"},
    ],
    ("ONLINE", "TRAVEL_PLATFORM"): [
        {"token": "Hotels.com", "type": "MERCHANT", "value": "HOTELS_COM", "label": "Hotels.com"},
        {"token": "Agoda", "type": "MERCHANT", "value": "AGODA", "label": "Agoda"},
        {"token": "Booking.com", "type": "MERCHANT", "value": "BOOKING", "label": "Booking.com"},
        {"token": "Booking", "type": "MERCHANT", "value": "BOOKING", "label": "Booking.com"},
        {"token": "Trip.com", "type": "MERCHANT", "value": "TRIP_COM", "label": "Trip.com"},
        {"token": "AsiaYo", "type": "MERCHANT", "value": "ASIAYO", "label": "AsiaYo"},
        {"token": "Klook", "type": "MERCHANT", "value": "KLOOK", "label": "Klook"},
        {"token": "KKday", "type": "MERCHANT", "value": "KKDAY", "label": "KKday"},
        {"token": "AIRSIM", "type": "MERCHANT", "value": "AIRSIM", "label": "AIRSIM"},
    ],
    ("ENTERTAINMENT", "STREAMING"): [
        {"token": "Netflix", "type": "MERCHANT", "value": "NETFLIX", "label": "Netflix"},
        {"token": "Spotify", "type": "MERCHANT", "value": "SPOTIFY", "label": "Spotify"},
        {"token": "Disney+", "type": "MERCHANT", "value": "DISNEY_PLUS", "label": "Disney+"},
        {"token": "YouTube Premium", "type": "MERCHANT", "value": "YOUTUBE_PREMIUM", "label": "YouTube Premium"},
        {"token": "friDay", "type": "MERCHANT", "value": "FRIDAY_VIDEO", "label": "friDay Video"},
        {"token": "MyVideo", "type": "MERCHANT", "value": "MYVIDEO", "label": "MyVideo"},
    ],
    ("DINING", "DELIVERY"): [
        {"token": "Uber Eats", "type": "MERCHANT", "value": "UBER_EATS", "label": "Uber Eats"},
        {"token": "foodpanda", "type": "MERCHANT", "value": "FOODPANDA", "label": "foodpanda"},
    ],
    ("TRANSPORT", "RIDESHARE"): [
        {"token": "Uber", "type": "MERCHANT", "value": "UBER", "label": "Uber"},
        {"token": "Grab", "type": "MERCHANT", "value": "GRAB", "label": "Grab"},
        {"token": "yoxi", "type": "MERCHANT", "value": "YOXI", "label": "yoxi"},
        {"token": "GoShare", "type": "MERCHANT", "value": "GOSHARE", "label": "GoShare"},
        {"token": "WeMo", "type": "MERCHANT", "value": "WEMO", "label": "WeMo"},
    ],
    ("TRANSPORT", "PUBLIC_TRANSIT"): [
        {"token": "台鐵", "type": "MERCHANT", "value": "TRA", "label": "台鐵"},
        {"token": "臺鐵", "type": "MERCHANT", "value": "TRA", "label": "台鐵"},
        {"token": "高鐵", "type": "MERCHANT", "value": "THSR", "label": "高鐵"},
        {"token": "THSR", "type": "MERCHANT", "value": "THSR", "label": "高鐵"},
    ],
    ("TRANSPORT", "AIRLINE"): [
        {"token": "華航", "type": "MERCHANT", "value": "CHINA_AIRLINES", "label": "華航"},
        {"token": "長榮航空", "type": "MERCHANT", "value": "EVA_AIR", "label": "長榮航空"},
        {"token": "星宇航空", "type": "MERCHANT", "value": "STARLUX", "label": "星宇航空"},
        {"token": "國泰航空", "type": "MERCHANT", "value": "CATHAY_PACIFIC", "label": "國泰航空"},
        {"token": "ANA", "type": "MERCHANT", "value": "ANA", "label": "ANA"},
    ],
    ("GROCERY", "SUPERMARKET"): [
        {"token": "全聯", "type": "RETAIL_CHAIN", "value": "PXMART", "label": "全聯"},
        {"token": "家樂福", "type": "RETAIL_CHAIN", "value": "CARREFOUR", "label": "家樂福"},
        {"token": "LOPIA", "type": "RETAIL_CHAIN", "value": "LOPIA", "label": "LOPIA"},
        {"token": "RT-Mart", "type": "RETAIL_CHAIN", "value": "RT_MART", "label": "RT-Mart"},
    ],
    ("SHOPPING", "DEPARTMENT"): [
        {"token": "SOGO", "type": "RETAIL_CHAIN", "value": "SOGO", "label": "SOGO"},
        {"token": "新光三越", "type": "RETAIL_CHAIN", "value": "SHIN_KONG_MITSUKOSHI", "label": "新光三越"},
        {"token": "遠東百貨", "type": "RETAIL_CHAIN", "value": "FAR_EAST_DEPARTMENT_STORE", "label": "遠東百貨"},
        {"token": "微風", "type": "RETAIL_CHAIN", "value": "BREEZE", "label": "微風"},
        {"token": "台北101", "type": "RETAIL_CHAIN", "value": "TAIPEI_101", "label": "台北101"},
    ],
    ("SHOPPING", "DRUGSTORE"): [
        {"token": "康是美", "type": "RETAIL_CHAIN", "value": "COSMED", "label": "康是美"},
        {"token": "屈臣氏", "type": "RETAIL_CHAIN", "value": "WATSONS", "label": "屈臣氏"},
    ],
    ("OTHER", "EV_CHARGING"): [
        {"token": "U-POWER", "type": "MERCHANT", "value": "U_POWER", "label": "U-POWER"},
        {"token": "EVOASIS", "type": "MERCHANT", "value": "EVOASIS", "label": "EVOASIS"},
        {"token": "AmpGO", "type": "MERCHANT", "value": "AMPGO", "label": "AmpGO"},
        {"token": "iCharging", "type": "MERCHANT", "value": "ICHARGING", "label": "iCharging"},
    ],
    ("TRANSPORT", "GAS_STATION"): [
        {"token": "台灣中油", "type": "RETAIL_CHAIN", "value": "CPC", "label": "台灣中油"},
        {"token": "全國加油", "type": "RETAIL_CHAIN", "value": "NATIONWIDE_GAS", "label": "全國加油"},
        {"token": "台塑石油", "type": "RETAIL_CHAIN", "value": "FORMOSA_PETROCHEMICAL", "label": "台塑石油"},
        {"token": "台亞", "type": "RETAIL_CHAIN", "value": "TAIA", "label": "台亞"},
        {"token": "福懋", "type": "RETAIL_CHAIN", "value": "FORMOZA", "label": "福懋"},
    ],
}

PAYMENT_METHOD_SUBCATEGORY_CONDITIONS: Dict[tuple[str, str], Dict[str, str]] = {
    ("ONLINE", "MOBILE_PAY"): {
        "type": "PAYMENT_METHOD",
        "value": "MOBILE_PAY",
        "label": "行動支付",
    },
}


PAYMENT_PLATFORM_VALUE_ALIASES: Dict[str, tuple[str, str]] = {
    "LINE_PAY": ("LINE_PAY", "LINE Pay"),
    "APPLE_PAY": ("APPLE_PAY", "Apple Pay"),
    "GOOGLE_PAY": ("GOOGLE_PAY", "Google Pay"),
    "SAMSUNG_PAY": ("SAMSUNG_PAY", "Samsung Pay"),
    "JKOPAY": ("JKOPAY", "街口支付"),
    "街口支付": ("JKOPAY", "街口支付"),
    "ESUN_WALLET": ("ESUN_WALLET", "玉山 Wallet"),
    "玉山WALLET電子支付": ("ESUN_WALLET", "玉山 Wallet"),
    "玉山 Wallet電子支付": ("ESUN_WALLET", "玉山 Wallet"),
    "全支付": ("全支付", "全支付"),
    "悠遊付": ("悠遊付", "悠遊付"),
    "全盈_PAY": ("全盈_PAY", "全盈+PAY"),
    "IPASS_MONEY": ("IPASS_MONEY", "iPASS MONEY"),
    "ICASH_PAY": ("ICASH_PAY", "icash Pay"),
    "TWQR": ("TWQR", "TWQR"),
    "HAPPY_GO_PAY": ("HAPPY_GO_PAY", "HAPPY GO Pay"),
    "HAMI_PAY": ("HAMI_PAY", "Hami Pay"),
}

PAYMENT_SIGNAL_TOKENS: Dict[str, tuple[str, ...]] = {
    "MOBILE_PAY": (
        "行動支付",
        "電子支付",
        "LINE Pay",
        "Apple Pay",
        "Google Pay",
        "Samsung Pay",
        "街口支付",
        "JKOPay",
        "玉山WALLET電子支付",
        "玉山 Wallet電子支付",
        "全支付",
        "悠遊付",
        "全盈+PAY",
        "iPASS MONEY",
        "icash Pay",
        "TWQR",
        "HAPPY GO Pay",
        "Hami Pay",
    ),
    "LINE_PAY": ("LINE Pay",),
    "APPLE_PAY": ("Apple Pay",),
    "GOOGLE_PAY": ("Google Pay",),
    "SAMSUNG_PAY": ("Samsung Pay",),
    "JKOPAY": ("JKOPay", "街口支付"),
    "ESUN_WALLET": ("玉山WALLET電子支付", "玉山 Wallet電子支付"),
    "全支付": ("全支付",),
    "悠遊付": ("悠遊付",),
    "全盈_PAY": ("全盈+PAY",),
    "IPASS_MONEY": ("iPASS MONEY",),
    "ICASH_PAY": ("icash Pay",),
    "TWQR": ("TWQR",),
    "HAPPY_GO_PAY": ("HAPPY GO Pay", "HAPPY GO PAY"),
    "HAMI_PAY": ("Hami Pay",),
}

PAYMENT_NEGATION_TOKENS: tuple[str, ...] = (
    "不適用",
    "恕不適用",
    "恕無法參加",
    "無法參加",
    "不列入",
    "不享",
    "不回饋",
    "排除",
    "除外",
)


def _canonicalize_payment_condition(condition: Dict[str, str]) -> Dict[str, str]:
    normalized_type = str(condition.get("type", "")).upper()
    if normalized_type != "PAYMENT_PLATFORM":
        return dict(condition)

    canonical = PAYMENT_PLATFORM_VALUE_ALIASES.get(str(condition.get("value", "")).strip())
    if not canonical:
        return dict(condition)

    return {
        **condition,
        "type": "PAYMENT_PLATFORM",
        "value": canonical[0],
        "label": canonical[1],
    }


def _is_negated_payment_token(text: str, token: str) -> bool:
    for match in re.finditer(re.escape(token), text, flags=re.IGNORECASE):
        sentence_start = max(
            text.rfind("。", 0, match.start()),
            text.rfind("；", 0, match.start()),
            text.rfind("!", 0, match.start()),
            text.rfind("?", 0, match.start()),
        )
        sentence_end_candidates = [
            index for index in (
                text.find("。", match.end()),
                text.find("；", match.end()),
                text.find("!", match.end()),
                text.find("?", match.end()),
            )
            if index != -1
        ]
        left = 0 if sentence_start == -1 else sentence_start + 1
        right = min(sentence_end_candidates) if sentence_end_candidates else len(text)
        context = text[left:right]
        if any(negation in context for negation in PAYMENT_NEGATION_TOKENS):
            return True
    return False


def _has_positive_payment_signal(text: str, payment_value: str) -> bool:
    for token in PAYMENT_SIGNAL_TOKENS.get(payment_value, (payment_value,)):
        if token not in text:
            continue
        if _is_negated_payment_token(text, token):
            continue
        return True
    return False


def sanitize_payment_conditions(
    title: str,
    body: str,
    conditions: Sequence[Dict[str, str]],
) -> List[Dict[str, str]]:
    text = collapse_text(f"{title} {body}")
    merged: List[Dict[str, str]] = []

    for raw_condition in conditions:
        condition = _canonicalize_payment_condition(raw_condition)
        normalized_type = str(condition.get("type", "")).upper()
        normalized_value = str(condition.get("value", "")).upper()

        if normalized_type == "PAYMENT_PLATFORM" and not _has_positive_payment_signal(text, normalized_value):
            continue
        if normalized_type == "PAYMENT_METHOD" and normalized_value == "MOBILE_PAY":
            has_positive_platform = any(
                str(existing.get("type", "")).upper() == "PAYMENT_PLATFORM"
                for existing in merged
            )
            if not has_positive_platform and not _has_positive_payment_signal(text, "MOBILE_PAY"):
                continue

        merged.append(condition)

    deduped: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for condition in merged:
        key = (
            str(condition.get("type", "")).upper(),
            str(condition.get("value", "")).upper(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(condition)

    return deduped


def append_inferred_subcategory_conditions(
    title: str,
    body: str,
    category: str | None,
    subcategory: str | None,
    conditions: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    if not category or not subcategory or subcategory.upper() == "GENERAL":
        return conditions

    inferred = STRUCTURED_SUBCATEGORY_CONDITION_SIGNALS.get((category.upper(), subcategory.upper()))
    if not inferred:
        return conditions

    text = f"{title} {body}"
    merged = list(conditions)
    seen = {
        (str(condition.get("type", "")).upper(), str(condition.get("value", "")).upper())
        for condition in merged
    }

    for candidate in inferred:
        if candidate["token"] not in text:
            continue
        candidate_condition = _canonicalize_payment_condition(
            {
                "type": candidate["type"],
                "value": candidate["value"],
                "label": candidate["label"],
            }
        )
        if candidate_condition["type"].upper() == "PAYMENT_PLATFORM" and not _has_positive_payment_signal(
            text,
            candidate_condition["value"].upper(),
        ):
            continue
        key = (candidate_condition["type"].upper(), candidate_condition["value"].upper())
        if key in seen:
            continue
        merged.append(candidate_condition)
        seen.add(key)

    return merged


def append_inferred_payment_method_conditions(
    category: str | None,
    subcategory: str | None,
    conditions: List[Dict[str, str]],
    title: str = "",
    body: str = "",
) -> List[Dict[str, str]]:
    if not category or not subcategory:
        return conditions

    inferred = PAYMENT_METHOD_SUBCATEGORY_CONDITIONS.get((category.upper(), subcategory.upper()))
    if not inferred:
        return conditions

    merged = list(conditions)
    key = (inferred["type"].upper(), inferred["value"].upper())
    seen = {
        (str(condition.get("type", "")).upper(), str(condition.get("value", "")).upper())
        for condition in merged
    }
    text = collapse_text(f"{title} {body}")
    has_existing_payment_condition = any(condition_type in {"PAYMENT_METHOD", "PAYMENT_PLATFORM"} for condition_type, _ in seen)
    if key not in seen and (has_existing_payment_condition or _has_positive_payment_signal(text, inferred["value"].upper())):
        merged.append(dict(inferred))
    return merged


def canonicalize_subcategory(
    category: str | None,
    subcategory: str | None,
    conditions: Sequence[Dict[str, str]] | None = None,
) -> str | None:
    if not category or not subcategory:
        return subcategory

    if category.upper() != "ONLINE" or subcategory.upper() != "MOBILE_PAY":
        return subcategory

    normalized_conditions = conditions or []
    has_payment_condition = any(
        str(condition.get("type", "")).upper() in {"PAYMENT_METHOD", "PAYMENT_PLATFORM"}
        for condition in normalized_conditions
    )
    # MOBILE_PAY is only an internal inference bridge for ONLINE promos.
    # It should never survive as a persisted subcategory after normalization.
    return "GENERAL" if has_payment_condition else "GENERAL"


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
