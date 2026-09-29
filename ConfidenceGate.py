import json

def confidence_gate(match_result, validation_result):
    if validation_result["validation_result"] != "pass":
        return {
            "decision": "REJECT",
            "reason": "Validation failed - repaired mapping did not produce a valid target payload"
        }

    confidence = match_result["confidence"]
    match_type = match_result["match_type"]

    if confidence >= 90 and match_type in ("exact", "strong"):
        return {
            "decision": "AUTO_RELEASE",
            "reason": f"High confidence ({confidence}) {match_type} match, validation passed"
        }
    elif confidence >= 50:
        return {
            "decision": "NEEDS_APPROVAL",
            "reason": f"Moderate confidence ({confidence}), developer review required before release"
        }
    else:
        return {
            "decision": "REJECT",
            "reason": f"Low confidence ({confidence}), match type '{match_type}' - repair not applied"
        }


if __name__ == "__main__":
    # Scenario B: safe drift
    match_b = {"match_type": "strong", "confidence": 98}
    validation_b = {"validation_result": "pass"}
    print("Scenario B:", json.dumps(confidence_gate(match_b, validation_b), indent=2))

    # Scenario C: ambiguous drift
    match_c = {"match_type": "ambiguous", "confidence": 40}
    validation_c = {"validation_result": "pass"}
    print("\nScenario C:", json.dumps(confidence_gate(match_c, validation_c), indent=2))

    # Scenario D: invalid repair
    match_d = {"match_type": "strong", "confidence": 95}
    validation_d = {"validation_result": "fail", "reason": "target field missing"}
    print("\nScenario D:", json.dumps(confidence_gate(match_d, validation_d), indent=2))