import pytest
from app.models.schemas import ExtractionResult
from app.services.normalizer_service import normalize_extracted_tests

def test_normalize_tests_sample():
    """Test Step 2 normalization matching PDF expected JSON."""
    raw_extraction = ExtractionResult(
        tests_raw=[
            "Hemoglobin 10.2 g/dL (Low)",
            "WBC 11200 /uL (High)"
        ],
        confidence=0.80
    )

    result = normalize_extracted_tests(raw_extraction, base_confidence=0.84)

    assert result.normalization_confidence == 0.84
    assert len(result.tests) == 2

    # Hemoglobin check
    hgb = next(t for t in result.tests if t.name == "Hemoglobin")
    assert hgb.value == 10.2
    assert hgb.unit == "g/dL"
    assert hgb.status == "low"
    assert hgb.ref_range.low == 12.0
    assert hgb.ref_range.high == 15.0

    # WBC check
    wbc = next(t for t in result.tests if t.name == "WBC")
    assert wbc.value == 11200
    assert wbc.unit == "/uL"
    assert wbc.status == "high"
    assert wbc.ref_range.low == 4000.0
    assert wbc.ref_range.high == 11000.0

def test_normalize_comma_separated_numbers():
    """Verify that comma-formatted numbers like '11,200' parse correctly in Step 2."""
    raw_extraction = ExtractionResult(
        tests_raw=["WBC 11,200 /uL (High)"],
        confidence=0.80
    )
    result = normalize_extracted_tests(raw_extraction)
    assert len(result.tests) == 1
    item = result.tests[0]
    assert item.value == 11200
    assert item.unit == "/uL"
    assert item.status == "high"

def test_normalize_expanded_catalog_items():
    """Verify newly added catalog tests (Glucose, Platelets, TSH) normalize properly."""
    raw_extraction = ExtractionResult(
        tests_raw=[
            "Glucose 145 mg/dL (High)",
            "Platelets 250000 /uL (Normal)",
            "TSH 0.2 uIU/mL (Low)"
        ],
        confidence=0.85
    )
    result = normalize_extracted_tests(raw_extraction)
    assert len(result.tests) == 3
    glu = next(t for t in result.tests if t.name == "Glucose")
    assert glu.value == 145
    assert glu.status == "high"
    assert glu.ref_range.low == 70.0
    assert glu.ref_range.high == 99.0

def test_normalize_rejects_nameless_number_line():
    """Verify that an orphaned line without a test name is rejected and does NOT match Hemoglobin."""
    raw_extraction = ExtractionResult(
        tests_raw=["10.2 g/dL (Low)"],
        confidence=0.80
    )
    result = normalize_extracted_tests(raw_extraction)
    assert len(result.tests) == 0

def test_normalize_rejects_uncataloged_test_without_status_flag():
    """Verify that an unknown test with no reference range and no flag is rejected rather than marked normal."""
    raw_extraction = ExtractionResult(
        tests_raw=["UncatalogedBiomarker 99.5 ng/mL"],
        confidence=0.80
    )
    result = normalize_extracted_tests(raw_extraction)
    assert len(result.tests) == 0

def test_normalize_preserves_explicit_flag_on_uncataloged_test():
    """Verify that an unknown test with an explicit flag (High/Low) is retained with that flag."""
    raw_extraction = ExtractionResult(
        tests_raw=["UncatalogedBiomarker 99.5 ng/mL (High)"],
        confidence=0.80
    )
    result = normalize_extracted_tests(raw_extraction)
    assert len(result.tests) == 1
    assert result.tests[0].name == "Uncatalogedbiomarker"
    assert result.tests[0].status == "high"

def test_normalize_scales_unit_multipliers_correctly():
    """Verify that WBC 11.2 K/uL scales to 11200 /uL (High) and Platelets 2.5 lakhs/cumm scales to 250000 /uL (Normal)."""
    raw_extraction = ExtractionResult(
        tests_raw=[
            "WBC 11.2 K/uL",
            "Platelets 2.5 lakhs/cumm"
        ],
        confidence=0.85
    )
    result = normalize_extracted_tests(raw_extraction)
    assert len(result.tests) == 2
    
    wbc = next(t for t in result.tests if t.name == "WBC")
    assert wbc.value == 11200
    assert wbc.unit == "/uL"
    assert wbc.status == "high"
    
    plt = next(t for t in result.tests if t.name == "Platelets")
    assert plt.value == 250000
    assert plt.unit == "/uL"
    assert plt.status == "normal"
