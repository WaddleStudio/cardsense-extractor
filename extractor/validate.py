from typing import Any, Dict

from models.promotion import PromotionNormalized


def validate_promotion(data: Dict[str, Any]) -> PromotionNormalized:
    """Validate a normalized promotion against the current CardSense model."""
    return PromotionNormalized.model_validate(data)
