import pytest
from app.models.schemas import NormalizedTest, RefRange
from app.services.guardrail_service import verify_source_evidence
from app.services.extractor_service import load_catalog
from app.services.pipeline import run_pipeline
from app.models.schemas import GuardrailExitResult

def test_guardrail_passes_for_valid_input():
    catalog = load_catalog()
    raw_text = "CBC: Hemglobin 10.2 g/dL (Low)\nWBC 11200 /uL (Hgh)"
    tests = [
        NormalizedTest(
            name="Hemoglobin",
            value=10.2,
            unit="g/dL",
            status="low",
            ref_range=RefRange(low=12.0, high=15.0)
        ),
        NormalizedTest(
            name="WBC",
            value=11200,
            unit="/uL",
            status="high",
            ref_range=RefRange(low=4000.0, high=11000.0)
        )
    ]

    hallucinated = verify_source_evidence(tests, raw_text, catalog)
    assert hallucinated == []

def test_guardrail_catches_hallucinated_test():
    catalog = load_catalog()
    raw_text = "CBC: Hemglobin 10.2 g/dL (Low)\nWBC 11200 /uL (Hgh)"
    tests = [
        NormalizedTest(
            name="Hemoglobin",
            value=10.2,
            unit="g/dL",
            status="low",
            ref_range=RefRange(low=12.0, high=15.0)
        ),
        NormalizedTest(
            name="Platelets",  # NOT in raw_text!
            value=150000,
            unit="/uL",
            status="normal",
            ref_range=RefRange(low=150000.0, high=400000.0)
        )
    ]

    hallucinated = verify_source_evidence(tests, raw_text, catalog)
    assert "Platelets" in hallucinated

def test_pipeline_guardrail_exit_condition():
    """Verify exact JSON return on hallucination condition from PDF."""
    raw_text = "CBC: Hemoglobin 10.2 g/dL (Low), WBC 11,200 /uL (High)"
    result = run_pipeline(text=raw_text, simulate_hallucination=True)

    assert isinstance(result, GuardrailExitResult)
    assert result.status == "unprocessed"
    assert result.reason == "hallucinated tests not present in input"

def test_explanation_validation_catches_ungrounded_abbreviations():
    """Verify that explanation validator catches short abbreviations (like WBC) with punctuation."""
    from app.models.schemas import ExplanationResult
    from app.services.guardrail_service import validate_explanation_text

    catalog = load_catalog()
    # Only Hemoglobin is in validated tests, but explanation mentions 'WBC.'
    allowed_tests = ["Hemoglobin"]
    bad_explanation = ExplanationResult(
        summary="Low hemoglobin levels noted.",
        explanations=["Low hemoglobin may relate to anemia, and also check WBC."]
    )

    is_valid = validate_explanation_text(bad_explanation, allowed_tests, catalog)
    assert is_valid is False

def test_guardrail_prevents_short_synonym_bypass():
    """Ensure hallucinated Potassium ('k') is not falsely grounded by words like 'check' or 'normal'."""
    catalog = load_catalog()
    raw_text = "CBC: Hemoglobin 10.2 g/dL (Low), normal check examination."
    tests = [
        NormalizedTest(
            name="Hemoglobin",
            value=10.2,
            unit="g/dL",
            status="low",
            ref_range=RefRange(low=12.0, high=15.0)
        ),
        NormalizedTest(
            name="Potassium",  # NOT in text, but synonym 'k' is in 'check'/'make'
            value=4.0,
            unit="mEq/L",
            status="normal",
            ref_range=RefRange(low=3.5, high=5.0)
        )
    ]
    hallucinated = verify_source_evidence(tests, raw_text, catalog)
    assert "Potassium" in hallucinated

def test_explanation_validation_permits_cluster_vocabulary():
    """Ensure mentioning 'cholesterol' when LDL is present does not trigger false positive."""
    from app.models.schemas import ExplanationResult
    from app.services.guardrail_service import validate_explanation_text

    catalog = load_catalog()
    allowed_tests = ["LDL"]
    valid_explanation = ExplanationResult(
        summary="High LDL cholesterol levels.",
        explanations=["Elevated bad cholesterol warrants dietary changes."]
    )
    is_valid = validate_explanation_text(valid_explanation, allowed_tests, catalog)
    assert is_valid is True
