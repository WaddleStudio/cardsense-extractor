import re
from typing import Dict, Any

def parse_promotion(raw_text: str) -> Dict[str, Any]:
    """
    Parses raw promotion text using rules/regex.
    Returns a dictionary of potential fields.
    """
    extracted = {}
    
    # 1. Bank Extraction (Simple heuristic)
    if "Bank A" in raw_text:
        extracted["bank"] = "Bank A"
    elif "Bank B" in raw_text:
        extracted["bank"] = "Bank B"
        
    # 2. Card Intent (Mock logic)
    if "Rewards Card" in raw_text:
        extracted["card_id"] = "card_001"
    else:
        # Try to infer or leave empty to fail validation if strict
        extracted["card_id"] = "unknown_card"

    # 3. Reward Rate
    # Look for "X% cashback"
    rate_match = re.search(r"(\d+)%\s+cashback", raw_text, re.IGNORECASE)
    if rate_match:
        extracted["reward_type"] = "cashback"
        extracted["reward_rate"] = float(rate_match.group(1)) / 100.0

    # 4. Dates
    # Look for YYYY-MM-DD
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", raw_text)
    if len(dates) >= 1:
        extracted["start_date"] = dates[0]
    if len(dates) >= 2:
        extracted["end_date"] = dates[1]

    # 5. Min Spend / Cap
    # "Min spend: 500"
    min_match = re.search(r"Min spend:\s*(\d+)", raw_text, re.IGNORECASE)
    if min_match:
        extracted["min_amount"] = int(min_match.group(1))
        
    # "Max cap: 1000"
    cap_match = re.search(r"Max cap:\s*(\d+)", raw_text, re.IGNORECASE)
    if cap_match:
        extracted["reward_cap"] = int(cap_match.group(1))

    # 6. Categories (Keyword matching)
    extracted["categories"] = []
    lower_text = raw_text.lower()
    if "dining" in lower_text:
        extracted["categories"].append("dining")
    if "travel" in lower_text:
        extracted["categories"].append("travel")
        
    # 7. Channel
    # Default to 'all' or infer
    extracted["channel"] = "all"
    
    # 8. Summary
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    if lines:
        extracted["summary"] = lines[0] # Use first line as title/summary

    return extracted
