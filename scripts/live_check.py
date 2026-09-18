"""Three real Gemini language calls on synthetic fixtures. Never prints credentials."""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app


def main():
    key = settings.gemini_api_key.get_secret_value()
    if not key:
        raise SystemExit("Set GEMINI_API_KEY in the ignored .env file first.")
    results = []
    with TestClient(create_app()) as client:
        for fixture in ("report.txt", "report-ocr-typos.txt"):
            response = client.post(
                "/reports/simplify/text",
                json={"text": Path("samples", fixture).read_text(), "use_gemini": True},
                headers={"X-Gemini-API-Key": key},
            )
            check(response, fixture)
            results.append({"case": fixture, "status": "passed", "provider": "gemini"})
        with Path("samples/report.png").open("rb") as image:
            response = client.post(
                "/reports/simplify/image",
                files={"image": ("report.png", image, "image/png")},
                data={"use_gemini": "true"},
                headers={"X-Gemini-API-Key": key},
            )
        check(response, "image")
        results.append(
            {"case": "local_ocr_plus_gemini_language", "status": "passed", "provider": "gemini"}
        )
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/live-verification.json").write_text(
        json.dumps(
            {
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "model": settings.gemini_model,
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    print("All three live Gemini cases passed. No fallback was accepted as success.")


def check(response, name):
    if response.status_code != 200:
        raise SystemExit(
            f"{name}: failed with HTTP {response.status_code}; inspect the API using synthetic input."
        )
    result = response.json()
    if result["metadata"]["language_provider"] != "gemini":
        raise SystemExit(
            f"{name}: provider fallback occurred. Check key access, quota and model configuration."
        )
    if [test["value"] for test in result["tests"]] != [10.2, 11200]:
        raise SystemExit(f"{name}: unexpected numeric results.")
    print(f"{name}: passed")


if __name__ == "__main__":
    main()
