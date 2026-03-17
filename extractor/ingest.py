from typing import List

def get_raw_promotions(source: str = "mock") -> List[str]:
    """
    Ingests raw promotion text.
    For this sample, we return hardcoded strings if source == 'mock'.
    """
    if source == "mock":
        return [
            # Valid Sample
            """
            [Bank A] Rewards Card Special
            Get 5% cashback on all dining spend!
            Min spend: 500. Max cap: 1000.
            Valid from 2023-10-01 to 2023-12-31.
            """,
            # Invalid Sample (Missing required fields like Bank, Card)
            """
            Mega Sale! 50% off everything!
            Come visit us today.
            """
        ]
    # In a real scenario, this would read from a file or API
    return []
