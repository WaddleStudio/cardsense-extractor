from typing import List


def get_raw_promotions(source: str = "mock") -> List[str]:
    """Return mock raw promotion text until real bank ingestion is implemented."""
    if source != "mock":
        return []

    return [
        """
        Bank: CTBC
        Bank Name: 中國信託
        Card Code: CTBC_DEMO_ONLINE
        Card Name: 中國信託 示例網購卡
        Promotion: 春季線上訂票回饋
        Category: ONLINE
        Cashback Type: PERCENT
        Cashback Value: 3.0
        Min Amount: 500
        Max Cashback: 300
        Frequency Limit: MONTHLY
        Requires Registration: true
        Valid From: 2026-03-01
        Valid Until: 2026-06-30
        Conditions: 需登錄活動; LOCATION_ONLY:TAIPEI; trip.com 線上訂票適用
        Excluded Conditions: LOCATION:KAOHSIUNG
        Source URL: https://example.com/promotions/ctbc-online-spring
        Apply URL: https://example.com/cards/ctbc-demo-online
        Annual Fee: 1800
        Status: ACTIVE
        """,
        """
        Bank: CATHAY
        Bank Name: 國泰世華
        Card Code: CATHAY_DEMO_LIFESTYLE
        Card Name: 國泰世華 示例生活卡
        Promotion: 海外平台旅遊刷卡回饋
        Category: OVERSEAS
        Cashback Type: PERCENT
        Cashback Value: 2.5
        Min Amount: 1
        Max Cashback: 500
        Frequency Limit: MONTHLY
        Requires Registration: false
        Valid From: 2026-01-01
        Valid Until: 2026-08-31
        Conditions: 海外一般消費適用; 以外幣結帳回饋優先
        Excluded Conditions:
        Source URL: https://example.com/promotions/cathay-overseas
        Apply URL: https://example.com/cards/cathay-demo-lifestyle
        Annual Fee: 1800
        Status: ACTIVE
        """,
        """
        Mega Sale! 50% off everything!
        Come visit us today.
        """,
    ]
