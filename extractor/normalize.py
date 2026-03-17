from typing import Dict, Any, List
from datetime import datetime

def normalize_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes extracted data before validation.
    """
    normalized = data.copy()
    
    # 1. Normalize Categories (Example: lowercase, de-duplicate)
    if "categories" in normalized and isinstance(normalized["categories"], list):
        normalized["categories"] = list(set([c.lower().strip() for c in normalized["categories"]]))

    # 2. Normalize Dates
    # (Already extracted as YYYY-MM-DD strings by parser, but could force format here)
    
    # 3. Normalize Channel
    if "channel" in normalized:
        normalized["channel"] = normalized["channel"].lower()

    # 4. Ensure Reward Type is lower case
    if "reward_type" in normalized:
        normalized["reward_type"] = normalized["reward_type"].lower()
        
    return normalized
