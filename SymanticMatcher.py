import json
import time
from google import genai
from google.genai import errors
print(f"==>> type(google.genai):  {type(google.genai)}")

client = genai.Client(api_key="gemini_api_key")

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

Guidelines:
- "exact": identical meaning, just different casing/formatting
- "strong": clearly the same business concept (e.g. custName -> customerName)
- "weak": plausible but not clearly the same concept
- "ambiguous": could mean different things (e.g. a name vs an identifier)
- "no_match": no candidate represents the same concept
"""

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            raw_text = response.text.strip()
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            return json.loads(raw_text)
        except errors.ServerError:
            if attempt < max_retries - 1:
                print(f"Model busy, retrying in 5 seconds... (attempt {attempt + 1})")
                time.sleep(5)
            else:
                raise

if __name__ == "__main__":
    result = semantic_match(
        removed_field="custName",
        candidate_fields=["customerName"],
        sibling_fields=["Amount"]
    )
    print(json.dumps(result, indent=2))

    print("\n--- Ambiguous case ---")
    ambiguous_result = semantic_match(
        removed_field="custName",
        candidate_fields=["customerIdentifier"],
        sibling_fields=["Amount"]
    )
    print(json.dumps(ambiguous_result, indent=2))