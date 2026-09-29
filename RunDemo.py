import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import os

from google import genai

GEMINI_API_KEY = "GEmini_Key_here"
client = genai.Client(api_key=GEMINI_API_KEY)

AUDIT_LOG_PATH = "audit_log.json"
XS_NS = "{http://www.w3.org/2001/XMLSchema}"


# ---------- STAGE 1: DETECT ----------
def extract_fields(xsd_path):
    tree = ET.parse(xsd_path)
    root = tree.getroot()
    fields = {}
    for elem in root.iter(f"{XS_NS}element"):
        name = elem.get("name")
        if name is None or name == "Customer":
            continue
        fields[name] = {"type": elem.get("type", "unspecified")}
    return fields


def diff_schemas(baseline_path, current_path):
    baseline = extract_fields(baseline_path)
    current = extract_fields(current_path)
    baseline_names = set(baseline.keys())
    current_names = set(current.keys())
    removed = baseline_names - current_names
    added = current_names - baseline_names

    changes = []
    for name in removed:
        changes.append({
            "change_type": "field_removed",
            "field": name,
            "possible_rename_candidates": list(added)
        })
    for name in added:
        changes.append({"change_type": "field_added", "field": name})
    return changes


import time
from google.genai import errors

# ---------- STAGE 2: UNDERSTAND ----------
def semantic_match(removed_field, candidate_fields, sibling_fields, max_retries=3):
    prompt = f"""You are analyzing a schema change in an enterprise integration.

A field was removed from a schema: "{removed_field}"
Sibling fields in the same schema (for context): {sibling_fields}
Candidate fields that appeared in the new schema version: {candidate_fields}

Determine if any candidate field represents the SAME business concept as the removed field.

Respond ONLY with valid JSON, no other text, in this exact shape:
{{
  "match_type": "exact" | "strong" | "weak" | "ambiguous" | "no_match",
  "matched_field": "<candidate field name or null>",
  "confidence": <integer 0-100>,
  "reasoning": "<one short sentence>"
}}
"""
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model="gemini-3.8-flash", contents=prompt)
            raw = response.text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except errors.ServerError:
            if attempt < max_retries - 1:
                print(f"   (model busy, retrying in 5s... attempt {attempt + 1})")
                time.sleep(5)
            else:
                raise

# ---------- STAGE 3: HEAL ----------
def generate_repair(match_result, current_mapping, old_source_field):
    if match_result["match_type"] not in ("exact", "strong"):
        return {"action": "no_repair_generated", "reason": f"match_type '{match_result['match_type']}' not confident enough"}
    target_field = current_mapping.get(old_source_field)
    return {
        "action": "repair_generated",
        "before": {"source_field": old_source_field, "target_field": target_field},
        "after": {"source_field": match_result["matched_field"], "target_field": target_field}
    }


# ---------- STAGE 4: VALIDATE ----------
def validate_repair(drifted_xml_path, repair):
    if repair["action"] != "repair_generated":
        return {"validation_result": "skipped"}
    tree = ET.parse(drifted_xml_path)
    root = tree.getroot()
    src_field = repair["after"]["source_field"]
    tgt_field = repair["after"]["target_field"]
    src_elem = root.find(src_field)
    amount_elem = root.find("Amount")
    if src_elem is None:
        return {"validation_result": "fail", "reason": f"'{src_field}' not found"}
    target_xml = f"<Customer><{tgt_field}>{src_elem.text}</{tgt_field}><Amount>{amount_elem.text}</Amount></Customer>"
    return {"validation_result": "pass", "generated_target_payload": target_xml}


# ---------- STAGE 5: DECIDE ----------
def confidence_gate(match_result, validation_result):
    if validation_result["validation_result"] != "pass":
        return {"decision": "REJECT", "reason": "Validation failed"}
    confidence = match_result["confidence"]
    match_type = match_result["match_type"]
    if confidence >= 90 and match_type in ("exact", "strong"):
        return {"decision": "AUTO_RELEASE", "reason": f"High confidence ({confidence}) {match_type} match"}
    elif confidence >= 50:
        return {"decision": "NEEDS_APPROVAL", "reason": f"Moderate confidence ({confidence})"}
    else:
        return {"decision": "REJECT", "reason": f"Low confidence ({confidence})"}


# ---------- STAGE 6: AUDIT ----------
def write_audit_entry(change, match_result, repair, validation_result, gate_decision):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "detected_change": change,
        "semantic_match": match_result,
        "proposed_repair": repair,
        "validation_result": validation_result,
        "gate_decision": gate_decision,
        "rollback_reference": {"original_mapping": repair.get("before")}
    }
    log = json.load(open(AUDIT_LOG_PATH)) if os.path.exists(AUDIT_LOG_PATH) else []
    log.append(entry)
    json.dump(log, open(AUDIT_LOG_PATH, "w"), indent=2)
    return entry


# ---------- ORCHESTRATION ----------
def run_pipeline(scenario_name, baseline_xsd, current_xsd, drifted_xml, current_mapping):
    print(f"\n{'='*60}\nSCENARIO: {scenario_name}\n{'='*60}")

    changes = diff_schemas(baseline_xsd, current_xsd)
    removed = next((c for c in changes if c["change_type"] == "field_removed"), None)
    print("1. DETECT:", json.dumps(changes, indent=2))

    if not removed:
        print("No drift detected. Nothing to do.")
        return

    match_result = semantic_match(removed["field"], removed["possible_rename_candidates"], ["Amount"])
    print("\n2. UNDERSTAND:", json.dumps(match_result, indent=2))

    repair = generate_repair(match_result, current_mapping, removed["field"])
    print("\n3. HEAL:", json.dumps(repair, indent=2))

    validation = validate_repair(drifted_xml, repair)
    print("\n4. VALIDATE:", json.dumps(validation, indent=2))

    decision = confidence_gate(match_result, validation)
    print("\n5. DECIDE:", json.dumps(decision, indent=2))

    entry = write_audit_entry(changes, match_result, repair, validation, decision)
    print("\n6. AUDIT: entry written at", entry["timestamp"])
    print(f"\nFINAL OUTCOME: {decision['decision']}")


if __name__ == "__main__":
    current_mapping = {"custName": "CustomerName", "Amount": "Amount"}

    # Scenario B - Safe Drift
    run_pipeline(
        "B - Safe Drift (custName -> customerName)",
        "baseline_customer.xsd", "current_customer.xsd", "drifted_customer.xml",
        current_mapping
    )

    # Scenario C - Ambiguous Drift
    print(f"\n{'='*60}\nSCENARIO: C - Ambiguous Drift (custName -> customerIdentifier)\n{'='*60}")
    removed_c = {"field": "custName", "possible_rename_candidates": ["customerIdentifier"]}
    match_c = semantic_match(removed_c["field"], removed_c["possible_rename_candidates"], ["Amount"])
    print("\n2. UNDERSTAND:", json.dumps(match_c, indent=2))
    repair_c = generate_repair(match_c, current_mapping, removed_c["field"])
    print("\n3. HEAL:", json.dumps(repair_c, indent=2))
    validation_c = {"validation_result": "skipped", "reason": "repair not generated - confidence too low"} if repair_c["action"] != "repair_generated" else validate_repair("drifted_customer.xml", repair_c)
    print("\n4. VALIDATE:", json.dumps(validation_c, indent=2))
    decision_c = confidence_gate(match_c, validation_c) if validation_c["validation_result"] != "skipped" else {"decision": "NEEDS_APPROVAL" if match_c["confidence"] >= 50 else "REJECT", "reason": "No repair generated - manual review required"}
    print("\n5. DECIDE:", json.dumps(decision_c, indent=2))
    write_audit_entry([removed_c], match_c, repair_c, validation_c, decision_c)
    print(f"\nFINAL OUTCOME: {decision_c['decision']}")

    # Scenario D - Invalid Repair
    print(f"\n{'='*60}\nSCENARIO: D - Invalid Repair (forced validation failure)\n{'='*60}")
    match_d = {"match_type": "strong", "matched_field": "nonExistentField", "confidence": 92, "reasoning": "Forced test case for invalid repair"}
    repair_d = generate_repair(match_d, current_mapping, "custName")
    print("\n3. HEAL:", json.dumps(repair_d, indent=2))
    validation_d = validate_repair("drifted_customer.xml", repair_d)
    print("\n4. VALIDATE:", json.dumps(validation_d, indent=2))
    decision_d = confidence_gate(match_d, validation_d)
    print("\n5. DECIDE:", json.dumps(decision_d, indent=2))
    write_audit_entry([{"field": "custName"}], match_d, repair_d, validation_d, decision_d)
    print(f"\nFINAL OUTCOME: {decision_d['decision']}")