import time

from app.engine import parse, verify
from app.language import (
    GeminiLanguage,
    ProviderUnavailable,
    default_explanations,
    facts_for,
    render_plan,
)
from app.schemas import Extraction, Metadata, Normalization, ReportResponse

ASSIGNMENT_INPUT = "CBC: Hemoglobin 10.2 g/dL (Low), WBC 11,200 /uL (High)"
ASSIGNMENT_DEMO = "CBC:\nHemoglobin 10.2 g/dL (Low) Reference: 12.0-15.0\nWBC 11,200 /uL (High) Reference: 4000-11000"


class Pipeline:
    def __init__(self, language: GeminiLanguage):
        self.language = language

    async def run(
        self,
        text: str,
        request_id: str,
        input_type: str = "text",
        key: str | None = None,
        ocr_confidence: float | None = None,
    ) -> ReportResponse:
        start = time.monotonic()
        tests, evidence, source = parse(text)
        facts = facts_for(tests)
        explanations = default_explanations(facts)
        provider, language_status = "templates", "not_requested"
        warnings = [
            "Educational explanation, not a diagnosis. Discuss results with your clinician."
        ]
        if key:
            try:
                plan = await self.language.explain(facts, key)
                explanations = render_plan(plan, facts)
                provider, language_status = "gemini", "applied"
            except ProviderUnavailable as exc:
                language_status = "fallback"
                warnings.append(str(exc))
        verify(tests, evidence, source)
        if any(test.ref_range is None for test in tests):
            warnings.append(
                "Missing reference ranges were not inferred; flags, when present, are copied from the report."
            )
        if input_type == "image":
            warnings.append(
                "OCR can misread characters even with a high score. Compare source_text with the original image."
            )
        labels = {"WBC": "white blood cell count", "RBC": "red blood cell count"}
        phrases = [
            f"{test.status if test.status != 'unknown' else 'Unclassified'} {labels.get(test.name, test.name.lower())}"
            for test in tests
        ]
        summary = (
            ", ".join(phrases[:-1]) + " and " + phrases[-1] if len(phrases) > 1 else phrases[0]
        ).capitalize() + "."
        raw_lines = []
        for e in evidence:
            corrected = e.source_text
            for correction in e.corrections:
                old, new = correction.split(" -> ")
                import re

                corrected = re.sub(re.escape(old), new, corrected, flags=re.I)
            raw_lines.append(corrected)
        normalization_score = 0.95 if any(e.corrections for e in evidence) else 1.0
        return ReportResponse(
            tests=tests,
            summary=summary,
            explanations=explanations,
            extraction=Extraction(
                tests_raw=raw_lines,
                confidence=ocr_confidence if ocr_confidence is not None else 1,
                confidence_basis="Minimum accepted OCR-region score; not calibrated clinical confidence"
                if ocr_confidence is not None
                else "Exact deterministic text parsing; not clinical confidence",
            ),
            normalization=Normalization(
                normalization_confidence=normalization_score,
                confidence_basis="Rule-coverage score: 1.0 for supported exact rules, 0.95 when explicit OCR typo aliases are corrected; not a probability",
                evidence=evidence,
            ),
            metadata=Metadata(
                request_id=request_id,
                input_type=input_type,
                source_text=source,
                language_provider=provider,
                language_status=language_status,
                warnings=warnings,
                duration_ms=round((time.monotonic() - start) * 1000),
                ocr_engine="RapidOCR / ONNX Runtime (local CPU)" if input_type == "image" else None,
            ),
        )
