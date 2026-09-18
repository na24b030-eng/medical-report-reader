import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.language import GeminiLanguage
from app.main import create_app
from app.pipeline import ASSIGNMENT_DEMO, Pipeline


@pytest.fixture
def client():
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def test_health_demo_and_schema(client):
    assert client.get("/health").status_code == 200
    demo = client.get("/demo")
    assert demo.status_code == 200
    assert demo.json()["summary"] == "Low hemoglobin and high white blood cell count."
    assert "/reports/simplify/image" in client.get("/openapi.json").json()["paths"]


def test_text_without_key(client):
    response = client.post("/reports/simplify/text", json={"text": ASSIGNMENT_DEMO})
    assert response.status_code == 200
    assert response.json()["metadata"]["language_status"] == "not_requested"
    assert response.headers["x-request-id"] == response.json()["metadata"]["request_id"]


def test_invalid_json_and_body_do_not_echo_sensitive_content(client):
    response = client.post("/reports/simplify/text", json={"text": 12, "key": "secret-sentinel"})
    assert response.status_code == 400
    assert "secret-sentinel" not in response.text
    assert (
        client.post(
            "/reports/simplify/text", content="{", headers={"Content-Type": "application/json"}
        ).status_code
        == 400
    )


def test_empty_and_oversized_inputs(client):
    assert client.post("/reports/simplify/text", json={"text": ""}).status_code == 400
    assert client.post("/reports/simplify/text", json={"text": "x" * 20001}).status_code == 400
    assert client.post("/reports/simplify/text", content=b"x" * 110000).status_code == 413


def test_conflict_is_unprocessed(client):
    result = client.post(
        "/reports/simplify/text", json={"text": "Hemoglobin 10.2 g/dL (High) Reference: 12-15"}
    )
    assert result.status_code == 422
    assert result.json()["status"] == "unprocessed"
    assert "tests" not in result.json()


def test_key_required_only_for_requested_nlp(client):
    response = client.post(
        "/reports/simplify/text", json={"text": ASSIGNMENT_DEMO, "use_gemini": True}
    )
    assert response.status_code == 401


def test_real_local_ocr(client):
    with open("samples/report.png", "rb") as image:
        response = client.post(
            "/reports/simplify/image", files={"image": ("report.png", image, "image/png")}
        )
    assert response.status_code == 200, response.text
    assert [test["value"] for test in response.json()["tests"]] == [10.2, 11200]
    assert response.json()["metadata"]["ocr_engine"].startswith("RapidOCR")


def test_corrupt_and_blank_images(client):
    assert (
        client.post(
            "/reports/simplify/image", files={"image": ("bad.png", b"fake", "image/png")}
        ).status_code
        == 422
    )
    stream = io.BytesIO()
    Image.new("RGB", (300, 300), "white").save(stream, format="PNG")
    assert (
        client.post(
            "/reports/simplify/image",
            files={"image": ("blank.png", stream.getvalue(), "image/png")},
        ).status_code
        == 422
    )


def provider_client(handler):
    language = GeminiLanguage("test-model", transport=httpx.MockTransport(handler))
    return TestClient(create_app(pipeline=Pipeline(language)), raise_server_exceptions=False)


def test_nlp_receives_no_raw_measurements_and_keys_remain_request_scoped():
    seen = []

    def handler(request):
        seen.append(request.headers["x-goog-api-key"])
        data = json.loads(request.content)
        facts = json.loads(data["contents"][0]["parts"][0]["text"])
        assert "10.2" not in json.dumps(facts) and "11200" not in json.dumps(facts)
        items = [
            {
                "test_id": f["test_id"],
                "definition": f["definitions"][1],
                "assessment": f["assessments"][1],
            }
            for f in facts
        ]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps({"items": items})}]},
                    }
                ]
            },
        )

    with provider_client(handler) as client:
        for key in ("first-request-key-123456", "second-request-key-123456"):
            result = client.post(
                "/reports/simplify/text",
                json={"text": ASSIGNMENT_DEMO, "use_gemini": True},
                headers={"X-Gemini-API-Key": key},
            )
            assert result.status_code == 200
            assert result.json()["metadata"]["language_provider"] == "gemini"
            assert key not in result.text
    assert seen == ["first-request-key-123456", "second-request-key-123456"]


def test_provider_outage_is_explicit_fallback():
    with provider_client(lambda _: httpx.Response(429)) as client:
        result = client.post(
            "/reports/simplify/text",
            json={"text": ASSIGNMENT_DEMO, "use_gemini": True},
            headers={"X-Gemini-API-Key": "test-key-123456789012345"},
        )
    assert result.status_code == 200
    assert result.json()["metadata"]["language_status"] == "fallback"
    assert [t["value"] for t in result.json()["tests"]] == [10.2, 11200]


def test_hallucinated_nlp_content_exits_unprocessed():
    payload = {
        "items": [
            {
                "test_id": "invented",
                "definition": "You have a disease.",
                "assessment": "Start treatment.",
            }
        ]
    }
    with provider_client(
        lambda _: httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}
                ]
            },
        )
    ) as client:
        result = client.post(
            "/reports/simplify/text",
            json={"text": ASSIGNMENT_DEMO, "use_gemini": True},
            headers={"X-Gemini-API-Key": "test-key-123456789012345"},
        )
    assert result.status_code == 422
    assert result.json()["status"] == "unprocessed"
