from models.promotion import PromotionNormalized


def load_promotion(promotion: PromotionNormalized):
    """Mock persistence for the normalized promotion model."""
    print(f"[{promotion.extractedAt}] LOADING PROMOTION: {promotion.promoId} (Version: {promotion.promoVersionId})")
    print(f"  Bank: {promotion.bankCode} / {promotion.bankName}")
    print(f"  Card: {promotion.cardCode} / {promotion.cardName}")
    print(f"  Summary: {promotion.summary}")
    print(f"  Confidence: {promotion.confidence}")
    print("  STATUS: SUCCESS (Mock DB Insert)")
