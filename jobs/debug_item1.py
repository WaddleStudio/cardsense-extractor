import sys
import os
from pprint import pprint
import traceback

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(project_root, "cardsense-extractor"))

from extractor import ingest, parse_rules, normalize, validate, versioning
from pydantic import ValidationError

def run_debug():
    print("DEBUG: Starting Single Item Test")
    raw_text = """
            [Bank A] Rewards Card Special
            Get 5% cashback on all dining spend!
            Min spend: 500. Max cap: 1000.
            Valid from 2023-10-01 to 2023-12-31.
            """
    
    try:
        parsed = parse_rules.parse_promotion(raw_text)
        print("Parsed:")
        pprint(parsed)
        
        normalized = normalize.normalize_data(parsed)
        print("Normalized:")
        pprint(normalized)
        
        payload = versioning.assign_version_ids(normalized, raw_text)
        print("Payload:")
        pprint(payload)
        
        obj = validate.validate_promotion(payload)
        print("VALIDATION SUCCESS")
        print(obj.model_dump_json(indent=2))
        
    except ValidationError as e:
        print("VALIDATION FAILED")
        print(e.json(indent=2))
    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    run_debug()
