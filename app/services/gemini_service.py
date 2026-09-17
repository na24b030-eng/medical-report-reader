import re
import json
import logging
from typing import List, Dict, Any
from app.config import settings
from app.models.schemas import NormalizedTest, ExplanationResult
from app.services.guardrail_service import validate_explanation_text

logger = logging.getLogger(__name__)

GEMINI_SYSTEM_INSTRUCTION = """You are an empathetic, clinical report communicator assisting patients.
Your ONLY role is to provide plain-language explanations of already-validated lab test results.
CRITICAL RULES:
1. You MUST NOT decide, recalculate, or alter test values, units, or medical statuses. Those are already verified.
2. You MUST NOT introduce or mention any medical test that is not in the provided validated findings.
3. You MUST NOT provide a medical diagnosis (e.g. do not say "You have leukemia" or "Diagnosed with anemia"). Use non-diagnostic phrasing such as "may relate to anemia" or "can occur with infections".
4. Produce a concise 1-sentence summary covering abnormal findings.
5. Provide a 1-sentence explanation for each abnormal finding.
6. Return your answer strictly in JSON format with keys "summary" and "explanations".
"""

_cached_client = None

def get_gemini_client(api_key: Optional[str] = None):
    """Lazily instantiate and cache default Gemini client, or return client with custom API key."""
    global _cached_client
    from google import genai
    from google.genai import types

    target_key = (api_key or "").strip() or settings.GEMINI_API_KEY.strip()
    if not target_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    http_opts = types.HttpOptions(timeout=int(settings.GEMINI_TIMEOUT_SECONDS * 1000)) if hasattr(types, "HttpOptions") else None

    # If a custom key is provided that differs from server settings, create on-demand client
    if target_key != settings.GEMINI_API_KEY.strip():
        return genai.Client(api_key=target_key, http_options=http_opts) if http_opts else genai.Client(api_key=target_key)

    if _cached_client is None:
        _cached_client = genai.Client(api_key=target_key, http_options=http_opts) if http_opts else genai.Client(api_key=target_key)
    return _cached_client

def generate_explanation_with_gemini(
    tests: List[NormalizedTest],
    catalog: Dict[str, Any],
    api_key: Optional[str] = None
) -> ExplanationResult:
    """
    Calls Google Gemini using the official google-genai SDK to generate patient-friendly explanations.
    Supports either a caller-provided custom API key or the default server demo key.
    Validates output against hallucination guards.
    Raises an exception if unconfigured, timed out, or validation fails.
    """
    effective_key = (api_key or "").strip() or settings.GEMINI_API_KEY.strip()
    if not effective_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    from google.genai import types

    # Prepare strictly sanitized input summary for Gemini
    findings_list = []
    for t in tests:
        findings_list.append({
            "test_name": t.name,
            "value": t.value,
            "unit": t.unit,
            "status": t.status,
            "reference_range": f"{t.ref_range.low} - {t.ref_range.high}"
        })

    prompt = (
        f"Validated Lab Findings:\n"
        f"{json.dumps(findings_list, indent=2)}\n\n"
        f"Please explain these findings in plain language for the patient following the system instructions."
    )

    client = get_gemini_client(api_key=effective_key)

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=GEMINI_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=ExplanationResult,
                temperature=0.2,
            )
        )

        if not response or not response.text:
            raise ValueError("Empty response from Gemini")

        # Strip any markdown code fences if present
        raw_output = response.text.strip()
        if raw_output.startswith("```"):
            raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output)
            raw_output = re.sub(r"\s*```$", "", raw_output)

        parsed_data = json.loads(raw_output)
        result = ExplanationResult(**parsed_data)

        # Post-validation: ensure Gemini didn't hallucinate extra test names
        allowed_names = [t.name for t in tests]
        if not validate_explanation_text(result, allowed_names, catalog):
            logger.warning("Gemini explanation failed anti-hallucination validation.")
            raise ValueError("Gemini explanation mentioned ungrounded tests")

        return result

    except Exception as e:
        logger.warning("Gemini explanation generation failed: %s", e)
        raise
