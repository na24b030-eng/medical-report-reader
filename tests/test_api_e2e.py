import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_simplify_report_text_sample():
    """E2E test: Text input producing exact Step 4 output from PDF."""
    payload = {
        "text": "CBC: Hemoglobin 10.2 g/dL (Low) , WBC 11,200 /uL (High)"
    }
    response = client.post("/api/v1/simplify-report", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert "summary" in data
    assert len(data["tests"]) == 2

    # Hemoglobin test verification
    hgb = next(t for t in data["tests"] if t["name"] == "Hemoglobin")
    assert hgb["value"] == 10.2
    assert hgb["unit"] == "g/dL"
    assert hgb["status"] == "low"
    assert hgb["ref_range"] == {"low": 12.0, "high": 15.0}

    # WBC test verification
    wbc = next(t for t in data["tests"] if t["name"] == "WBC")
    assert wbc["value"] == 11200
    assert wbc["unit"] == "/uL"
    assert wbc["status"] == "high"
    assert wbc["ref_range"] == {"low": 4000.0, "high": 11000.0}

def test_simplify_report_with_image_upload():
    """E2E test: Uploading generated sample lab report image."""
    image_path = Path("samples/sample_report.png")
    if not image_path.exists():
        pytest.skip("sample_report.png not generated")

    with open(image_path, "rb") as f:
        response = client.post(
            "/api/v1/simplify-report",
            files={"file": ("sample_report.png", f, "image/png")}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert len(data["tests"]) >= 2

def test_guardrail_unprocessed_exit():
    """E2E test: Guardrail triggers 'unprocessed' JSON on hallucinated test."""
    payload = {
        "text": "CBC: Hemoglobin 10.2 g/dL (Low) , WBC 11,200 /uL (High)",
        "simulate_hallucination": True
    }
    response = client.post("/api/v1/simplify-report", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "unprocessed"
    assert data["reason"] == "hallucinated tests not present in input"

def test_step_endpoints_isolated():
    """Test Step 1, Step 2, and Step 3 isolated endpoints."""
    # Step 1
    r1 = client.post("/api/v1/extract-text", json={"text": "CBC: Hemglobin 10.2 g/dL (Low)\nWBC 11200 /uL (Hgh)"})
    assert r1.status_code == 200
    s1 = r1.json()
    assert "tests_raw" in s1

    # Step 2
    r2 = client.post("/api/v1/normalize-tests", json=s1)
    assert r2.status_code == 200
    s2 = r2.json()
    assert "tests" in s2
    assert s2["normalization_confidence"] == 0.84

    # Step 3 with list
    r3 = client.post("/api/v1/summarize", json=s2["tests"])
    assert r3.status_code == 200
    s3 = r3.json()
    assert "summary" in s3
    assert "explanations" in s3

    # Step 3 with full Step 2 output dict (piping)
    r3_pipe = client.post("/api/v1/summarize", json=s2)
    assert r3_pipe.status_code == 200
    assert "summary" in r3_pipe.json()

def test_empty_request_returns_422():
    """Verify that completely empty payload returns HTTP 422."""
    response = client.post("/api/v1/simplify-report", json={})
    assert response.status_code == 422

def test_corrupt_image_upload_handled_gracefully():
    """Verify that corrupt or invalid image bytes return unprocessed guardrail response without 500 crash."""
    corrupt_bytes = b"not_a_valid_image_file_data_corrupt_stream"
    response = client.post(
        "/api/v1/simplify-report",
        files={"file": ("corrupt.png", corrupt_bytes, "image/png")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unprocessed"

def test_trace_mode_returns_all_step_objects():
    """Verify that trace: true returns PipelineStepTrace containing all intermediate steps."""
    payload = {
        "text": "CBC: Hemoglobin 10.2 g/dL (Low)",
        "trace": True
    }
    response = client.post("/api/v1/simplify-report", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "step1_extraction" in data
    assert "step2_normalization" in data
    assert "step3_explanation" in data
    assert "final_output" in data
    assert data["final_output"]["status"] == "ok"

def test_oversized_image_returns_413():
    """Verify that an image exceeding the size limit returns HTTP 413."""
    from unittest.mock import patch
    with patch("app.config.settings.MAX_IMAGE_SIZE_MB", 0.001): # ~1KB limit
        huge_bytes = b"X" * 2048 # 2KB
        response = client.post(
            "/api/v1/simplify-report",
            files={"file": ("large.png", huge_bytes, "image/png")}
        )
        assert response.status_code == 413

def test_catalog_endpoint():
    """Verify that /api/v1/catalog returns supported medical tests."""
    response = client.get("/api/v1/catalog")
    assert response.status_code == 200
    data = response.json()
    assert data["total_tests"] >= 35
    assert len(data["tests"]) == data["total_tests"]
    hgb = next(t for t in data["tests"] if t["canonical_name"] == "Hemoglobin")
    assert hgb["canonical_unit"] == "g/dL"

def test_request_timing_and_id_headers():
    """Verify that every response includes X-Request-ID and X-Process-Time-Ms headers."""
    response = client.get("/api/v1/health")
    assert "X-Request-ID" in response.headers
    assert "X-Process-Time-Ms" in response.headers
    assert float(response.headers["X-Process-Time-Ms"]) >= 0.0

def test_custom_gemini_api_key_handling():
    """Verify that external client-supplied API key is accepted and falls back gracefully on error."""
    # 1. Custom key via header
    payload = {"text": "CBC: Hemoglobin 10.2 g/dL (Low)", "trace": True}
    response = client.post(
        "/api/v1/simplify-report",
        json=payload,
        headers={"X-Gemini-API-Key": "non-existent-or-invalid-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["final_output"]["status"] == "ok"
    assert data["explanation_source"] == "fallback"

    # 2. Custom key via JSON body
    payload2 = {
        "text": "CBC: Hemoglobin 10.2 g/dL (Low)",
        "trace": True,
        "gemini_api_key": "another-custom-key"
    }
    response2 = client.post("/api/v1/simplify-report", json=payload2)
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["final_output"]["status"] == "ok"
    assert data2["explanation_source"] == "fallback"

