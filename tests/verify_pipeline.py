import sys
import os
import traceback

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor import ingest, parse_rules, normalize, validate, versioning
from pydantic import ValidationError

def verify():
    print("Running verification...")
    
    # CASE 1: Valid Item
    try:
        raw_text_1 = """
            [Bank A] Rewards Card Special
            Get 5% cashback on all dining spend!
            Min spend: 500. Max cap: 1000.
            Valid from 2023-10-01 to 2023-12-31.
        """
        parsed = parse_rules.parse_promotion(raw_text_1)
        normalized = normalize.normalize_data(parsed)
        payload = versioning.assign_version_ids(normalized, raw_text_1)
        obj = validate.validate_promotion(payload)
        
        # Additional checks
        if obj.bank != "Bank A": raise ValueError(f"Wrong bank: {obj.bank}")
        if obj.reward_rate != 0.05: raise ValueError(f"Wrong rate: {obj.reward_rate}")
        
    except Exception:
        with open("verification_failure.log", "w") as f:
            f.write(f"ITEM 1 FAILED:\n{traceback.format_exc()}")
        print("FINAL STATUS: FAILURE")
        return

    # CASE 2: Invalid Item
    try:
        raw_text_2 = "Invalid Promo Text"
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
