from typing import Any
from models.promotion import PromotionNormalized

def load_promotion(promotion: PromotionNormalized):
    """
    Mocks loading to PostgreSQL.
    """
    print(f"[{promotion.extracted_at}] LOADING PROMOTION: {promotion.promo_id} (Version: {promotion.promo_version_id})")
    print(f"  Bank: {promotion.bank}")
    print(f"  Summary: {promotion.summary}")
    print(f"  Confidence: {promotion.confidence}")
    print("  STATUS: SUCCESS (Mock DB Insert)")
