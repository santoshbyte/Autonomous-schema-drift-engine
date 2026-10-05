import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors


# ============================================================
# ENVIRONMENT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

# Try project root .env first.
load_dotenv(PROJECT_ROOT / ".env")

# Fall back to the existing Gemini proxy .env.
load_dotenv(PROJECT_ROOT / "gemini-proxy-server" / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not configured. "
        "Set it in .env or gemini-proxy-server/.env."
    )


# ============================================================
# GEMINI CLIENT
# ============================================================

client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-3.8-flash"


# ============================================================
# SEMANTIC MATCHING
# ============================================================

def semantic_match(
    removed_field,
    candidate_fields,
    sibling_fields,
    max_retries=3
):
    """
    Analyze whether one of the newly added fields represents
    the same business concept as a removed field.

    Parameters
    ----------
    removed_field : str
        Field removed from the baseline schema.

    candidate_fields : list[str]
        Fields introduced in the current schema.

    sibling_fields : list[str]
        Other fields from the surrounding schema used as context.

    max_retries : int
        Number of retries if Gemini temporarily fails.

    Returns
    -------
    dict
        Structured semantic classification.
    """

    prompt = f"""
You are analyzing a schema change in an enterprise integration.

A field was removed from a schema:

"{removed_field}"

Sibling fields in the same schema for context:

{sibling_fields}

Candidate fields that appeared in the new schema version:

{candidate_fields}

Determine whether any candidate field represents the SAME
business concept as the removed field.

Respond ONLY with valid JSON.
Do not include markdown.
Do not include ```json.
Do not include any explanation outside the JSON.

Use exactly this structure:

{{
  "match_type": "exact" | "strong" | "weak" | "ambiguous" | "no_match",
  "matched_field": "<candidate field name or null>",
  "confidence": <integer 0-100>,
  "reasoning": "<one short sentence>"
}}

Guidelines:

- "exact":
  Identical business meaning with only casing, formatting,
  or naming convention differences.

- "strong":
  Clearly represents the same business concept despite
  different naming.

- "weak":
  Plausibly related but not sufficiently certain.

- "ambiguous":
  Multiple interpretations are possible or the candidate
  may represent a different business concept.

- "no_match":
  None of the candidates represents the same business concept.

Do not invent candidate fields.
Do not change candidate field names.
"""

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )

            raw_text = response.text.strip()

            # Defensive cleanup in case the model still returns
            # a markdown JSON block.
            raw_text = (
                raw_text
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

            result = json.loads(raw_text)

            # Basic structural validation.
            required_keys = {
                "match_type",
                "matched_field",
                "confidence",
                "reasoning"
            }

            missing_keys = required_keys - result.keys()

            if missing_keys:
                raise ValueError(
                    f"Gemini response missing fields: {sorted(missing_keys)}"
                )

            result["confidence"] = int(result["confidence"])

            return result

        except errors.ServerError:
            if attempt < max_retries - 1:
                print(
                    f"Model busy, retrying in 5 seconds... "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(5)
            else:
                raise

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Gemini returned an invalid JSON response."
            ) from exc

        except ValueError:
            raise


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("SEMANTIC MATCHER TEST")
    print("=" * 60)

    result = semantic_match(
        removed_field="custName",
        candidate_fields=["customerName"],
        sibling_fields=["Amount"]
    )

    print("\n--- Safe Case ---")
    print(json.dumps(result, indent=2))

    print("\n--- Ambiguous Case ---")

    ambiguous_result = semantic_match(
        removed_field="custName",
        candidate_fields=["customerIdentifier"],
        sibling_fields=["Amount"]
    )

    print(json.dumps(ambiguous_result, indent=2))