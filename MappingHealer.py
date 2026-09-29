import json

def generate_repair(match_result, current_mapping, old_source_field):
    if match_result["match_type"] not in ("exact", "strong"):
        return {
            "action": "no_repair_generated",
            "reason": f"match_type is '{match_result['match_type']}', not confident enough to auto-generate a repair"
        }

    target_field = current_mapping.get(old_source_field)
    new_source_field = match_result["matched_field"]

    return {
        "action": "repair_generated",
        "before": {"source_field": old_source_field, "target_field": target_field},
        "after": {"source_field": new_source_field, "target_field": target_field},
        "confidence": match_result["confidence"],
        "reasoning": match_result["reasoning"]
    }


if __name__ == "__main__":
    match_result = {
        "match_type": "strong",
        "matched_field": "customerName",
        "confidence": 98,
        "reasoning": "customerName is an unabbreviated form of custName representing the same business concept."
    }

    current_mapping = {
        "custName": "CustomerName",
        "Amount": "Amount"
    }

    repair = generate_repair(match_result, current_mapping, old_source_field="custName")
    print(json.dumps(repair, indent=2))