import logging
from typing import Optional, Union
from app.models.schemas import (
    ExtractionResult,
    NormalizationResult,
    ExplanationResult,
    GuardrailExitResult,
    FinalSuccessResult,
    PipelineStepTrace,
    RefRange,
    NormalizedTest
)
from app.services.ocr_service import extract_text_from_image
from app.services.extractor_service import extract_raw_tests, load_catalog
from app.services.normalizer_service import normalize_extracted_tests
from app.services.guardrail_service import verify_source_evidence
from app.services.gemini_service import generate_explanation_with_gemini
from app.services.fallback_service import generate_fallback_explanation

logger = logging.getLogger(__name__)

def run_pipeline(
    text: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    simulate_hallucination: bool = False,
    return_trace: bool = False,
    gemini_api_key: Optional[str] = None
) -> Union[FinalSuccessResult, GuardrailExitResult, PipelineStepTrace]:
    """
    Executes the end-to-end 4-step pipeline:
    1. Dedicated OCR / Text extraction (fixes typos, outputs tests_raw)
    2. Deterministic normalization (computes status, looks up ref ranges)
    3. Strict Guardrails & Source Evidence Verification
    4. Gemini plain-language explanation with controlled fallback
    5. Final output assembly: {"tests": [...], "summary": "...", "status": "ok"}
    """
    catalog = load_catalog()

    # Step 0: Ingestion & OCR
    raw_source_text = ""
    ocr_confidence = 0.80

    if image_bytes:
        try:
            extracted_text, conf = extract_text_from_image(image_bytes)
            raw_source_text = extracted_text
            ocr_confidence = conf
        except ValueError as e:
            logger.warning("Corrupted or unreadable image uploaded: %s", e)
            return GuardrailExitResult(
                status="unprocessed",
                reason="unable to extract readable text from input"
            )
    elif text:
        raw_source_text = text.strip()
        ocr_confidence = 0.80

    if not raw_source_text:
        # If no readable text was obtained
        return GuardrailExitResult(
            status="unprocessed",
            reason="unable to extract readable text from input"
        )

    # Step 1: OCR / Text Extraction & Typo Correction
    step1_result: ExtractionResult = extract_raw_tests(raw_source_text, base_confidence=ocr_confidence)
    if not step1_result.tests_raw:
        return GuardrailExitResult(
            status="unprocessed",
            reason="no medical tests detected in input"
        )

    # Step 2: Normalization & Medical Reference Engine
    step2_result: NormalizationResult = normalize_extracted_tests(step1_result)
    if not step2_result.tests:
        return GuardrailExitResult(
            status="unprocessed",
            reason="no medical tests detected in input"
        )

    # For testing / verification: simulate an ungrounded hallucination if requested
    if simulate_hallucination:
        # Injects an ungrounded test that does NOT exist in raw_source_text
        step2_result.tests.append(
            NormalizedTest(
                name="HallucinatedMarker",
                value=999.0,
                unit="mg/dL",
                status="high",
                ref_range=RefRange(low=10.0, high=50.0)
            )
        )

    # Guardrail: Source Evidence Check (Anti-Hallucination)
    hallucinated_tests = verify_source_evidence(step2_result.tests, raw_source_text, catalog)
    if hallucinated_tests:
        logger.warning("Guardrail triggered: Hallucinated tests detected: %s", hallucinated_tests)
        return GuardrailExitResult(
            status="unprocessed",
            reason="hallucinated tests not present in input"
        )

    # Step 3: Patient-Friendly Summary (Gemini with controlled Fallback)
    has_custom_key = bool(gemini_api_key and gemini_api_key.strip())
    explanation_source = "gemini (custom key)" if has_custom_key else "gemini"
    try:
        step3_result: ExplanationResult = generate_explanation_with_gemini(
            step2_result.tests, catalog, api_key=gemini_api_key
        )
    except Exception as e:
        logger.info("Using controlled fallback explanation engine (reason: %s)", e)
        step3_result = generate_fallback_explanation(step2_result.tests, catalog)
        explanation_source = "fallback"

    # Step 4: Final Output Assembly
    final_output = FinalSuccessResult(
        tests=step2_result.tests,
        summary=step3_result.summary,
        status="ok"
    )

    if return_trace:
        return PipelineStepTrace(
            raw_ocr_or_text=raw_source_text,
            step1_extraction=step1_result,
            step2_normalization=step2_result,
            step3_explanation=step3_result,
            final_output=final_output,
            explanation_source=explanation_source
        )

    return final_output
