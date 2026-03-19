import sys
import os
import traceback
from decimal import Decimal

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor import ingest, parse_rules, normalize, validate, versioning
from pydantic import ValidationError

def verify():
    print("Running verification...")
    
    # CASE 1: Valid Item
    try:
        raw_text_1 = ingest.get_raw_promotions("mock")[0]
        parsed = parse_rules.parse_promotion(raw_text_1)
        normalized = normalize.normalize_data(parsed)
        payload = versioning.assign_version_ids(normalized, raw_text_1)
        obj = validate.validate_promotion(payload)
        
        # Additional checks
        if obj.bankCode != "CTBC": raise ValueError(f"Wrong bankCode: {obj.bankCode}")
        if obj.cardCode != "CTBC_DEMO_ONLINE": raise ValueError(f"Wrong cardCode: {obj.cardCode}")
        if obj.cashbackValue != Decimal("3.00"): raise ValueError(f"Wrong cashbackValue: {obj.cashbackValue}")
        if obj.frequencyLimit != "MONTHLY": raise ValueError(f"Wrong frequencyLimit: {obj.frequencyLimit}")
        if not obj.requiresRegistration: raise ValueError("Expected requiresRegistration to be true")
        if not obj.promoId or not obj.promoVersionId: raise ValueError("Missing version identifiers")
        
    except Exception:
        with open("verification_failure.log", "w") as f:
            f.write(f"ITEM 1 FAILED:\n{traceback.format_exc()}")
        print("FINAL STATUS: FAILURE")
        return

    # CASE 2: Invalid Item
    try:
        raw_text_2 = ingest.get_raw_promotions("mock")[2]
        parsed = parse_rules.parse_promotion(raw_text_2)
        normalized = normalize.normalize_data(parsed)
        payload = versioning.assign_version_ids(normalized, raw_text_2)
        validate.validate_promotion(payload)
        
        # Should have raised ValidationError
        with open("verification_failure.log", "w") as f:
            f.write("ITEM 2 SHOULD HAVE FAILED BUT PASSED validation.")
        print("FINAL STATUS: FAILURE")
        return
        
    except ValidationError:
        # Expected
        pass
    except Exception:
        with open("verification_failure.log", "w") as f:
            f.write(f"ITEM 2 RAISED UNEXPECTED ERROR:\n{traceback.format_exc()}")
        print("FINAL STATUS: FAILURE")
        return

    print("FINAL STATUS: SUCCESS")

if __name__ == "__main__":
    verify()
