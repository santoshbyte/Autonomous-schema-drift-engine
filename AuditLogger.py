import json
import os
from datetime import datetime, timezone

AUDIT_LOG_PATH = "audit_log.json"

def write_audit_entry(change_report, match_result, repair, validation_result, gate_decision):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "detected_change": change_report,
        "semantic_match": match_result,
        "proposed_repair": repair,
        "validation_result": validation_result,
        "gate_decision": gate_decision,
        "rollback_reference": {
            "original_mapping": repair.get("before") if repair.get("action") == "repair_generated" else None
        }
    }

    if os.path.exists(AUDIT_LOG_PATH):
        with open(AUDIT_LOG_PATH, "r") as f:
            log = json.load(f)
    else:
        log = []

    log.append(entry)

    with open(AUDIT_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)

    return entry


if __name__ == "__main__":
    change_report = {
        "change_type": "field_removed",
        "field": "custName",
        "possible_rename_candidates": ["customerName"]
    }
    match_result = {
        "match_type": "strong",
        "matched_field": "customerName",
        "confidence": 98,
        "reasoning": "customerName is an unabbreviated form of custName representing the same business concept."
    }
    repair = {
        "action": "repair_generated",
        "before": {"source_field": "custName", "target_field": "CustomerName"},
        "after": {"source_field": "customerName", "target_field": "CustomerName"}
    }
    validation_result = {"validation_result": "pass"}
    gate_decision = {"decision": "AUTO_RELEASE", "reason": "High confidence (98) strong match, validation passed"}

    entry = write_audit_entry(change_report, match_result, repair, validation_result, gate_decision)
    print(json.dumps(entry, indent=2))