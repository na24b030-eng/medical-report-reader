import pytest
from app.models.schemas import NormalizedTest, RefRange
from app.services.fallback_service import generate_fallback_explanation
from app.services.extractor_service import load_catalog

def test_fallback_generates_exact_sample_summary_and_explanations():
    """Verify fallback outputs match the PDF sample Step 3 output."""
    catalog = load_catalog()
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

    result = generate_fallback_explanation(tests, catalog)

    assert result.summary == "Low hemoglobin and high white blood cell count."
    assert "Low hemoglobin may relate to anemia." in result.explanations
    assert "High WBC can occur with infections." in result.explanations

def test_fallback_all_normal_findings():
    """Verify fallback response when all tests are normal."""
    catalog = load_catalog()
    tests = [
        NormalizedTest(
            name="Hemoglobin",
            value=14.0,
            unit="g/dL",
            status="normal",
            ref_range=RefRange(low=12.0, high=15.0)
        ),
        NormalizedTest(
            name="WBC",
            value=7000,
            unit="/uL",
            status="normal",
            ref_range=RefRange(low=4000.0, high=11000.0)
        )
    ]
    result = generate_fallback_explanation(tests, catalog)
    assert "standard reference ranges" in result.summary.lower()
    assert len(result.explanations) > 0
