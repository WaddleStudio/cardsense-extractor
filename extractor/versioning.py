import hashlib
import uuid
from typing import Dict, Any
from datetime import datetime

def assign_version_ids(data: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    """
    Assigns:
    - raw_text_hash
    - promo_id (if not present, generate predictable ID from bank+card or similar)
    - promo_version_id (hash of data + version)
    - extractor_version
    - extracted_at
    - confidence (mock)
    """
    versioned = data.copy()
    
    # 1. Raw Text Hash
    raw_hash = hashlib.sha256(raw_text.encode('utf-8')).hexdigest()
    versioned["raw_text_hash"] = raw_hash
    
    # 2. Promo Logic ID (Should be stable across versions of the "same" promo)
    # For now, let's use bank + card + start_date as a composite key if available, else random
    # In reality this is complex entity resolution.
    # Simple Mock: 
    unique_string = f"{versioned.get('bank')}-{versioned.get('card_id')}-{versioned.get('start_date')}"
    # Use MD5 for a shorter ID
    versioned["promo_id"] = hashlib.md5(unique_string.encode('utf-8')).hexdigest()
    
    # 3. Extractor Metadata
    versioned["extractor_version"] = "1.0.0"
    versioned["extracted_at"] = datetime.now()
    versioned["confidence"] = 0.95 # Mock confidence

    # 4. Promo Version ID (Changes if ANY field in the normalized data changes)
    # We serialize the data (excluding itself) to get a hash
    # For simplicity, we just hash the current state + raw_hash
    # In a real system, we'd check DB for previous version.
    # Here we just generate a deterministic hash of the content.
    content_string = str(sorted(versioned.items())) 
    versioned["promo_version_id"] = hashlib.sha256(content_string.encode('utf-8')).hexdigest()

    return versioned
