import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(project_root)

sys.path.append(os.path.join(project_root, "cardsense-extractor"))

from extractor import ingest, parse_rules, normalize, validate, versioning, load
from pydantic import ValidationError

def run_job():
    print(">>> Starting Extraction Job...")
    
    # 1. Ingest
    raw_promotions = ingest.get_raw_promotions("mock")
    print(f">>> Ingested {len(raw_promotions)} raw items.")
    
    for i, raw_text in enumerate(raw_promotions):
        print(f"\n--- Processing Item {i+1} ---")
        print(f"Raw Text snippet: {raw_text.strip().splitlines()[0]}...")
        
        try:
            parsed = parse_rules.parse_promotion(raw_text)
            print(f"Parsed: {parsed}")
            
            normalized = normalize.normalize_data(parsed)
            print(f"Normalized: {normalized}")
            
            payload_with_versions = versioning.assign_version_ids(normalized, raw_text)
            print(f"DEBUG PAYLOAD: {payload_with_versions}")
            
            promo_obj = validate.validate_promotion(payload_with_versions)
            print(">>> Validation: PASSED")
            
            load.load_promotion(promo_obj)
            
        except ValidationError as e:
            print(">>> Validation: FAILED")
            print(f"Errors: {e}")
        except Exception as e:
            print(f">>> Unexpected Error: {e}")

if __name__ == "__main__":
    run_job()
