import xml.etree.ElementTree as ET
import json

def apply_repair_and_validate(drifted_xml_path, repair):
    if repair["action"] != "repair_generated":
        return {
            "validation_result": "skipped",
            "reason": "no repair to validate"
        }

    tree = ET.parse(drifted_xml_path)
    root = tree.getroot()

    new_source_field = repair["after"]["source_field"]
    target_field = repair["after"]["target_field"]

    source_element = root.find(new_source_field)
    amount_element = root.find("Amount")

    if source_element is None:
        return {
            "validation_result": "fail",
            "reason": f"Expected source field '{new_source_field}' not found in drifted payload"
        }

    target_xml = f"<Customer><{target_field}>{source_element.text}</{target_field}><Amount>{amount_element.text}</Amount></Customer>"

    return {
        "validation_result": "pass",
        "generated_target_payload": target_xml
    }


if __name__ == "__main__":
    repair = {
        "action": "repair_generated",
        "before": {"source_field": "custName", "target_field": "CustomerName"},
        "after": {"source_field": "customerName", "target_field": "CustomerName"},
        "confidence": 98,
        "reasoning": "customerName is an unabbreviated form of custName representing the same business concept."
    }

    result = apply_repair_and_validate("drifted_customer.xml", repair)
    print(json.dumps(result, indent=2))