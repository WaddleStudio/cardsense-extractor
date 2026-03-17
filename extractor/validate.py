from typing import Dict, Any, Optional
from pydantic import ValidationError
from models.promotion import PromotionNormalized

def validate_promotion(data: Dict[str, Any]) -> Optional[PromotionNormalized]:
    """
    Validates data against the PromotionNormalized Pydantic model.
    Returns the Pydantic object if valid, else raises ValidationError.
    """
    try:
        # We might need to add missing fields that are required by Pydantic but not part of parsing
        # e.g. promo_version_id, extractor_version, etc. are added in pipeline later?
        # Actually, validation usually happens on the final object.
        # But here we validate the "payload" part or the "full" part.
        # The schema requires promo_version_id, so it must be present.
        # The pipeline orchestrator should add those before validation.
        return PromotionNormalized(**data)
    except ValidationError as e:
        # Re-raise to let the caller handle logging
        raise e
