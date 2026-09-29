import xml.etree.ElementTree as ET
import json

XS_NS = "{http://www.w3.org/2001/XMLSchema}"

def extract_fields(xsd_path):
    """Returns dict of {field_name: {'type': ..., 'min_occurs': ...}}"""
    tree = ET.parse(xsd_path)
    root = tree.getroot()
    fields = {}
    for elem in root.iter(f"{XS_NS}element"):
        name = elem.get("name")
        if name is None or name == "Customer":
            continue
        fields[name] = {
            "type": elem.get("type", "unspecified"),
            "min_occurs": elem.get("minOccurs", "1")
        }
    return fields

def diff_schemas(baseline_path, current_path):
    baseline = extract_fields(baseline_path)
    current = extract_fields(current_path)

    baseline_names = set(baseline.keys())
    current_names = set(current.keys())

    removed = baseline_names - current_names
    added = current_names - baseline_names
    common = baseline_names & current_names

    changes = []

    for name in common:
        if baseline[name]["type"] != current[name]["type"]:
            changes.append({
                "change_type": "type_changed",
                "field": name,
                "old_type": baseline[name]["type"],
                "new_type": current[name]["type"]
            })

    for name in removed:
        changes.append({
            "change_type": "field_removed",
            "field": name,
            "old_type": baseline[name]["type"],
            "possible_rename_candidates": list(added)
        })

    for name in added:
        
        changes.append({
            "change_type": "field_added",
            "field": name,
            "new_type": current[name]["type"]
        })

    return {
        "baseline_field_count": len(baseline_names),
        "current_field_count": len(current_names),
        "changes": changes
    }

if __name__ == "__main__":
    report = diff_schemas("baseline_customer.xsd", "current_customer.xsd")
    print(json.dumps(report, indent=2))