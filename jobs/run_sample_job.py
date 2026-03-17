import sys
import os
from pprint import pprint

# Add the project root to sys.path so we can import from cardsense_extractor
# Assuming this script is in cardsense-extractor/jobs/
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(project_root)

# Correct import paths based on the actual folder structure
# The folder is "cardsense-extractor", and inside it has "extractor" package and "models" package.
# However, python usually expects the package name to be a valid identifier. "cardsense-extractor" has a dash.
# We might need to rename the package folders or use importlib. 
# BUT, looking at the user request: "cardsense-extractor/extractor/ingest.py".
# So the root of the repo is "cardsense-extractor".
# If I add "d:/Projects/cardsense-workspace" to sys.path, then I can do:
# from cardsense_extractor.extractor import ingest
# WAIT. The folder name is "cardsense-extractor" (dash). Python modules can't have dashes.
# I should probably rename the internal folders to snake_case equivalent or just add "cardsense-extractor" to path
# and import "extractor.ingest".
# Let's try adding "d:/Projects/cardsense-workspace/cardsense-extractor" to sys.path.
# Then "import extractor.ingest" works.
# AND "import models.promotion" works.

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
            # 2. Parse
            parsed = parse_rules.parse_promotion(raw_text)
            print(f"Parsed: {parsed}")
            
            # 3. Normalize
            normalized = normalize.normalize_data(parsed)
            # print(f"Normalized: {normalized}")
            
            # 4. Versioning (must happen before validation as it adds required fields like IDs)
            # Note: This is a slight deviation from the plan order, but necessary because Validation needs the IDs.
            # Or Validate checks the "business payload" and Versioning adds the IDs later?
            # The Requirement says "Every normalized record MUST include promo_version_id".
            # So we must add it before we call the final validation against PromotionNormalized schema.
            
            payload_with_versions = versioning.assign_version_ids(normalized, raw_text)
            print(f"DEBUG PAYLOAD: {payload_with_versions}")
            
            # 5. Validate
            # This returns a Pydantic model
            promo_obj = validate.validate_promotion(payload_with_versions)
            print(">>> Validation: PASSED")
            
            # 6. Load
            load.load_promotion(promo_obj)
            
        except ValidationError as e:
            print(">>> Validation: FAILED")
            print(f"Errors: {e}")
        except Exception as e:
            print(f">>> Unexpected Error: {e}")

if __name__ == "__main__":
    run_job()
