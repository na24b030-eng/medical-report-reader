import pytest
from app.services.extractor_service import extract_raw_tests

def test_extract_typed_text_sample():
    """Test Step 1 with typed input from PDF."""
    input_text = "CBC: Hemoglobin 10.2 g/dL (Low) , WBC 11,200 /uL (High)"
    result = extract_raw_tests(input_text, base_confidence=0.80)

    assert len(result.tests_raw) == 2
    assert "Hemoglobin 10.2 g/dL (Low)" in result.tests_raw
    assert "WBC 11200 /uL (High)" in result.tests_raw
    assert result.confidence == 0.80

def test_extract_ocr_sample_with_typos():
    """Test Step 1 fixing typos from OCR input: Hemglobin -> Hemoglobin, Hgh -> High."""
    input_text = "CBC: Hemglobin 10.2 g/dL (Low)\nWBC 11200 /uL (Hgh)"
    result = extract_raw_tests(input_text, base_confidence=0.80)

    assert len(result.tests_raw) == 2
    assert "Hemoglobin 10.2 g/dL (Low)" in result.tests_raw
    assert "WBC 11200 /uL (High)" in result.tests_raw
    assert result.confidence == 0.80

def test_extract_empty_input():
    result = extract_raw_tests("")
    assert result.tests_raw == []
    assert result.confidence == 0.0

def test_extract_uppercase_test_names_with_colons():
    """Test that uppercase test names followed by colons are preserved."""
    input_text = "WBC: 11200 /uL (High)\nHEMOGLOBIN: 10.2 g/dL (Low)"
    result = extract_raw_tests(input_text, base_confidence=0.80)

    assert len(result.tests_raw) == 2
    assert "WBC 11200 /uL (High)" in result.tests_raw
    assert "Hemoglobin 10.2 g/dL (Low)" in result.tests_raw

def test_extract_panel_header_with_colon_preservation():
    """Test that panel header like CBC: is stripped, but test: is parsed."""
    input_text = "CBC: Hemoglobin: 12.5 g/dL (Normal); WBC: 6000 /uL (Normal)"
    result = extract_raw_tests(input_text, base_confidence=0.80)

    assert len(result.tests_raw) == 2
    assert any("Hemoglobin 12.5 g/dL" in t for t in result.tests_raw)
    assert any("WBC 6000 /uL" in t for t in result.tests_raw)
