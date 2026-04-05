import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.esun_real import _dedupe_promotions, _extract_reward, _infer_channel, _normalize_promotion_title
from extractor.normalize import clean_card_name


def test_extract_reward_prefers_fixed_when_title_is_fixed_offer():
    reward = _extract_reward(
        "滿額再享現折40元",
        "活動期間內使用玉山Unicard於爭鮮餐飲消費，單筆滿500元即可現折40元並同享最高4.5%回饋。",
    )

    assert reward == {"type": "FIXED", "value": 40.0}


def test_extract_reward_prefers_percent_when_title_is_percent_offer():
    reward = _extract_reward(
        "最高享14.5%回饋",
        "活動期間內首次申辦玉山Unicard，核卡後45天內新增一般消費滿5,000元贈500點玉山e point，加上原卡片權益回饋最高享14.5%。",
    )

    assert reward == {"type": "PERCENT", "value": 14.5}


def test_extract_reward_prefers_points_over_voucher_in_generic_title():
    reward = _extract_reward(
        "滿額活動",
        "登錄並使用玉山熊本熊卡，於指定旅遊通路刷卡最高享2,000點玉山e point回饋與2,000元好禮即享券。",
    )

    assert reward == {"type": "POINTS", "value": 2000.0}


def test_extract_reward_ignores_lottery_prize_value_campaign():
    reward = _extract_reward(
        "活動期間持玉山Unicard購買KKday行程享抽獎機會",
        "活動期間持玉山Unicard購買KKday任一不限金額商品，即可累積1次抽獎機會，抽獎贈品價值18,000元，活動總數量共1組。",
    )

    assert reward is None


def test_normalize_promotion_title_drops_note_noise_and_uses_body_fallback():
    title = _normalize_promotion_title(
        "玉山愛心卡 - 玉山銀行",
        "玉山愛心卡 - 玉山銀行 ※玉山e point更多介紹詳見 玉山e point網頁 說明。",
        "活動期間內一般消費享1%玉山e point回饋，最高回饋50點。",
    )

    assert title == "活動期間內一般消費享1%玉山e point回饋，最高回饋50點"


def test_dedupe_promotions_removes_exact_duplicate_rows():
    promotions = [
        {
            "cardCode": "ESUN_WORLD",
            "title": "玉山世界卡 【活動一】",
            "category": "OVERSEAS",
            "channel": "ONLINE",
            "cashbackType": "PERCENT",
            "cashbackValue": 10.0,
            "minAmount": 0,
            "maxCashback": 500,
            "validFrom": "2026-01-01",
            "validUntil": "2026-03-31",
            "summary": "A",
        },
        {
            "cardCode": "ESUN_WORLD",
            "title": "玉山世界卡 【活動一】",
            "category": "OVERSEAS",
            "channel": "ONLINE",
            "cashbackType": "PERCENT",
            "cashbackValue": 10.0,
            "minAmount": 0,
            "maxCashback": 500,
            "validFrom": "2026-01-01",
            "validUntil": "2026-03-31",
            "summary": "A",
        },
    ]

    deduped = _dedupe_promotions(promotions)

    assert len(deduped) == 1


def test_infer_channel_prefers_online_for_digital_payment_offer():
    channel = _infer_channel(
        "行動支付、網路消費 基本回饋",
        "國內外一般消費最高享1%現金回饋，行動支付與網路消費加碼。",
    )

    assert channel == "ONLINE"


def test_unicard_online_offer_can_infer_plan_and_subcategory_hint():
    from extractor.benefit_plans import apply_plan_subcategory_hint, infer_plan_id

    plan_id = infer_plan_id(
        "ESUN_UNICARD",
        "ONLINE",
        title="LINE Pay 加碼 3%",
        subcategory="GENERAL",
    )
    category, subcategory = apply_plan_subcategory_hint(plan_id, "ONLINE", "GENERAL")

    assert plan_id == "ESUN_UNICARD_FLEXIBLE"
    assert category == "ONLINE"
    assert subcategory == "MOBILE_PAY"


def test_clean_card_name_trims_unicard_page_selling_points():
    assert clean_card_name("玉山Unicard LINE Pay、韓國、新光三越、蝦皮購") == "玉山Unicard"
