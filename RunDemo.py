import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

# Load project-level .env if present.
load_dotenv(PROJECT_ROOT / ".env")

# Load the existing Gemini proxy .env as fallback.
load_dotenv(PROJECT_ROOT / "gemini-proxy-server" / ".env")


# We intentionally do not print or expose the API key.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not configured. "
        "Set it in .env or gemini-proxy-server/.env."
    )


# Import semantic matcher only after environment configuration.
from SymanticMatcher import semantic_match


# ============================================================
# CONFIGURATION
# ============================================================

AUDIT_LOG_PATH = PROJECT_ROOT / "audit_log.json"

XS_NS = "{http://www.w3.org/2001/XMLSchema}"


# ============================================================
# STAGE 1 — DETECT
# ============================================================

def extract_fields(xsd_path):
    """
    Extract fields from an XSD while excluding the top-level
    root element.

    This is intentionally generic and does not depend on the
    root being named Customer or Employee.
    """

    xsd_path = Path(xsd_path)

    tree = ET.parse(xsd_path)
    root = tree.getroot()

    fields = {}

    # Identify top-level XSD elements.
    top_level_elements = [
        elem
        for elem in root.findall(f"{XS_NS}element")
    ]

    root_element_names = {
        elem.get("name")
        for elem in top_level_elements
        if elem.get("name")
    }

    for elem in root.iter(f"{XS_NS}element"):

        name = elem.get("name")

        if not name:
            continue

        # Skip the schema's root wrapper.
        if name in root_element_names:
            continue

        fields[name] = {
            "type": elem.get("type", "unspecified")
        }

    return fields


def diff_schemas(baseline_path, current_path):
    """
    Compare two XSD files.

    Detects:
        - field_removed
        - field_added
        - type_changed
    """

    baseline = extract_fields(baseline_path)
    current = extract_fields(current_path)

    baseline_names = set(baseline.keys())
    current_names = set(current.keys())

    removed = baseline_names - current_names
    added = current_names - baseline_names
    common = baseline_names & current_names

    changes = []

    # --------------------------------------------------------
    # Removed fields
    # --------------------------------------------------------

    for name in sorted(removed):

        changes.append({
            "change_type": "field_removed",
            "field": name,
            "possible_rename_candidates": sorted(added)
        })

    # --------------------------------------------------------
    # Added fields
    # --------------------------------------------------------

    for name in sorted(added):

        changes.append({
            "change_type": "field_added",
            "field": name
        })

    # --------------------------------------------------------
    # Datatype changes
    # --------------------------------------------------------

    for name in sorted(common):

        baseline_type = baseline[name]["type"]
        current_type = current[name]["type"]

        if baseline_type != current_type:

            changes.append({
                "change_type": "type_changed",
                "field": name,
                "old_type": baseline_type,
                "new_type": current_type
            })

    return changes


# ============================================================
# STAGE 3 — HEAL
# ============================================================

def generate_repair(
    match_result,
    current_mapping,
    old_source_field
):
    """
    Generate a mapping repair from a semantic match.

    Only exact and strong matches are eligible for repair.
    """

    match_type = match_result.get("match_type")

    if match_type not in ("exact", "strong"):

        return {
            "action": "no_repair_generated",
            "reason": (
                f"match_type '{match_type}' "
                "is not confident enough"
            )
        }

    target_field = current_mapping.get(old_source_field)

    if target_field is None:

        return {
            "action": "no_repair_generated",
            "reason": (
                f"Source field '{old_source_field}' "
                "does not exist in the existing mapping."
            )
        }

    matched_field = match_result.get("matched_field")

    if not matched_field:

        return {
            "action": "no_repair_generated",
            "reason": "No matched field was returned by semantic analysis."
        }

    return {
        "action": "repair_generated",

        "confidence": match_result.get("confidence"),

        "before": {
            "source_field": old_source_field,
            "target_field": target_field
        },

        "after": {
            "source_field": matched_field,
            "target_field": target_field
        }
    }


# ============================================================
# STAGE 4 — VALIDATE
# ============================================================

def validate_repair(
    drifted_xml_path,
    repair
):
    """
    Validate that the proposed repaired source field exists
    in the drifted source XML.

    This demo validator also generates a simple target payload
    for the Customer example.
    """

    if repair.get("action") != "repair_generated":

        return {
            "validation_result": "skipped",
            "reason": "No repair was generated."
        }

    drifted_xml_path = Path(drifted_xml_path)

    tree = ET.parse(drifted_xml_path)
    root = tree.getroot()

    src_field = repair["after"]["source_field"]
    tgt_field = repair["after"]["target_field"]

    src_elem = root.find(src_field)

    if src_elem is None:

        return {
            "validation_result": "fail",
            "reason": (
                f"Source field '{src_field}' "
                "was not found in the current payload."
            )
        }

    # Customer demo payload support.
    amount_elem = root.find("Amount")

    if amount_elem is not None:

        target_xml = (
            f"<Customer>"
            f"<{tgt_field}>{src_elem.text or ''}</{tgt_field}>"
            f"<Amount>{amount_elem.text or ''}</Amount>"
            f"</Customer>"
        )

    else:

        target_xml = (
            f"<Customer>"
            f"<{tgt_field}>{src_elem.text or ''}</{tgt_field}>"
            f"</Customer>"
        )

    return {
        "validation_result": "pass",
        "generated_target_payload": target_xml
    }


# ============================================================
# STAGE 5 — DECIDE
# ============================================================

def confidence_gate(
    match_result,
    validation_result
):
    """
    Determine whether the proposed repair can be released.
    """

    if validation_result.get("validation_result") != "pass":

        return {
            "decision": "REJECT",
            "reason": "Validation failed."
        }

    confidence = int(match_result.get("confidence", 0))
    match_type = match_result.get("match_type")

    if (
        confidence >= 90
        and match_type in ("exact", "strong")
    ):

        return {
            "decision": "AUTO_RELEASE",
            "reason": (
                f"High confidence ({confidence}%) "
                f"{match_type} match and validation passed."
            )
        }

    if confidence >= 50:

        return {
            "decision": "NEEDS_APPROVAL",
            "reason": (
                f"Moderate confidence ({confidence}%). "
                "Manual approval required."
            )
        }

    return {
        "decision": "REJECT",
        "reason": (
            f"Low confidence ({confidence}%) "
            f"{match_type} match."
        )
    }


# ============================================================
# STAGE 6 — AUDIT
# ============================================================

def write_audit_entry(
    change,
    match_result,
    repair,
    validation_result,
    gate_decision
):
    """
    Append a complete pipeline execution to audit_log.json.
    """

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),

        "detected_change": change,

        "semantic_match": match_result,

        "proposed_repair": repair,

        "validation_result": validation_result,

        "gate_decision": gate_decision,

        "rollback_reference": {
            "original_mapping": repair.get("before")
        }
    }

    if AUDIT_LOG_PATH.exists():

        try:
            with open(
                AUDIT_LOG_PATH,
                "r",
                encoding="utf-8"
            ) as file:

                log = json.load(file)

                if not isinstance(log, list):
                    log = []

        except (json.JSONDecodeError, OSError):

            log = []

    else:

        log = []

    log.append(entry)

    with open(
        AUDIT_LOG_PATH,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            log,
            file,
            indent=2
        )

    return entry


# ============================================================
# COMPLETE PIPELINE
# ============================================================

def run_pipeline(
    scenario_name,
    baseline_xsd,
    current_xsd,
    drifted_xml,
    current_mapping
):

    print("\n" + "=" * 60)
    print(f"SCENARIO: {scenario_name}")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. DETECT
    # --------------------------------------------------------

    changes = diff_schemas(
        baseline_xsd,
        current_xsd
    )

    print(
        "\n1. DETECT:"
    )

    print(
        json.dumps(
            changes,
            indent=2
        )
    )

    removed = next(
        (
            change
            for change in changes
            if change["change_type"] == "field_removed"
        ),
        None
    )

    if not removed:

        print(
            "\nNo removed field detected. "
            "Nothing to repair."
        )

        return

    # --------------------------------------------------------
    # 2. UNDERSTAND
    # --------------------------------------------------------

    match_result = semantic_match(
        removed["field"],
        removed["possible_rename_candidates"],
        [
            field
            for field in current_mapping.keys()
            if field != removed["field"]
        ]
    )

    print(
        "\n2. UNDERSTAND:"
    )

    print(
        json.dumps(
            match_result,
            indent=2
        )
    )

    # --------------------------------------------------------
    # 3. HEAL
    # --------------------------------------------------------

    repair = generate_repair(
        match_result,
        current_mapping,
        removed["field"]
    )

    print(
        "\n3. HEAL:"
    )

    print(
        json.dumps(
            repair,
            indent=2
        )
    )

    # --------------------------------------------------------
    # 4. VALIDATE
    # --------------------------------------------------------

    validation = validate_repair(
        drifted_xml,
        repair
    )

    print(
        "\n4. VALIDATE:"
    )

    print(
        json.dumps(
            validation,
            indent=2
        )
    )

    # --------------------------------------------------------
    # 5. DECIDE
    # --------------------------------------------------------

    decision = confidence_gate(
        match_result,
        validation
    )

    print(
        "\n5. DECIDE:"
    )

    print(
        json.dumps(
            decision,
            indent=2
        )
    )

    # --------------------------------------------------------
    # 6. AUDIT
    # --------------------------------------------------------

    entry = write_audit_entry(
        changes,
        match_result,
        repair,
        validation,
        decision
    )

    print(
        "\n6. AUDIT:"
    )

    print(
        "Entry written at:",
        entry["timestamp"]
    )

    print(
        f"\nFINAL OUTCOME: {decision['decision']}"
    )


# ============================================================
# DEMO EXECUTION
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Existing demo mapping
    # --------------------------------------------------------

    current_mapping = {
        "custName": "CustomerName",
        "Amount": "Amount"
    }

    # --------------------------------------------------------
    # Scenario B — Safe Drift
    # --------------------------------------------------------

    run_pipeline(
        "B - Safe Drift (custName -> customerName)",

        PROJECT_ROOT / "baseline_customer.xsd",

        PROJECT_ROOT / "current_customer.xsd",

        PROJECT_ROOT / "drifted_customer.xml",

        current_mapping
    )

    # --------------------------------------------------------
    # Scenario C — Ambiguous Drift
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print(
        "SCENARIO: "
        "C - Ambiguous Drift "
        "(custName -> customerIdentifier)"
    )
    print("=" * 60)

    removed_c = {
        "field": "custName",
        "possible_rename_candidates": [
            "customerIdentifier"
        ]
    }

    match_c = semantic_match(
        removed_c["field"],
        removed_c["possible_rename_candidates"],
        ["Amount"]
    )

    print(
        "\n2. UNDERSTAND:"
    )

    print(
        json.dumps(
            match_c,
            indent=2
        )
    )

    repair_c = generate_repair(
        match_c,
        current_mapping,
        removed_c["field"]
    )

    print(
        "\n3. HEAL:"
    )

    print(
        json.dumps(
            repair_c,
            indent=2
        )
    )

    if repair_c["action"] != "repair_generated":

        validation_c = {
            "validation_result": "skipped",
            "reason": (
                "Repair not generated. "
                "Confidence or semantic classification "
                "was insufficient."
            )
        }

    else:

        validation_c = validate_repair(
            PROJECT_ROOT / "drifted_customer.xml",
            repair_c
        )

    print(
        "\n4. VALIDATE:"
    )

    print(
        json.dumps(
            validation_c,
            indent=2
        )
    )

    if validation_c["validation_result"] == "skipped":

        confidence_c = int(
            match_c.get("confidence", 0)
        )

        if confidence_c >= 50:

            decision_c = {
                "decision": "NEEDS_APPROVAL",
                "reason": (
                    "No automatic repair generated. "
                    "Manual review required."
                )
            }

        else:

            decision_c = {
                "decision": "REJECT",
                "reason": (
                    "Semantic confidence is too low."
                )
            }

    else:

        decision_c = confidence_gate(
            match_c,
            validation_c
        )

    print(
        "\n5. DECIDE:"
    )

    print(
        json.dumps(
            decision_c,
            indent=2
        )
    )

    write_audit_entry(
        [removed_c],
        match_c,
        repair_c,
        validation_c,
        decision_c
    )

    print(
        f"\nFINAL OUTCOME: {decision_c['decision']}"
    )

    # --------------------------------------------------------
    # Scenario D — Invalid Repair
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print(
        "SCENARIO: "
        "D - Invalid Repair "
        "(forced validation failure)"
    )
    print("=" * 60)

    match_d = {
        "match_type": "strong",
        "matched_field": "nonExistentField",
        "confidence": 92,
        "reasoning": (
            "Forced test case for invalid repair."
        )
    }

    repair_d = generate_repair(
        match_d,
        current_mapping,
        "custName"
    )

    print(
        "\n3. HEAL:"
    )

    print(
        json.dumps(
            repair_d,
            indent=2
        )
    )

    validation_d = validate_repair(
        PROJECT_ROOT / "drifted_customer.xml",
        repair_d
    )

    print(
        "\n4. VALIDATE:"
    )

    print(
        json.dumps(
            validation_d,
            indent=2
        )
    )

    decision_d = confidence_gate(
        match_d,
        validation_d
    )

    print(
        "\n5. DECIDE:"
    )

    print(
        json.dumps(
            decision_d,
            indent=2
        )
    )

    write_audit_entry(
        [{"field": "custName"}],
        match_d,
        repair_d,
        validation_d,
        decision_d
    )

    print(
        f"\nFINAL OUTCOME: {decision_d['decision']}"
    )