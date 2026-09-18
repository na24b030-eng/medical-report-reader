"""Generate reproducible sample inputs and submission artifacts."""

import asyncio
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.main import app
from app.pipeline import ASSIGNMENT_DEMO, ASSIGNMENT_INPUT

ROOT = Path(__file__).resolve().parents[1]


def save_json(path: str, value):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def image_fixture():
    fonts = ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    font = next(
        (ImageFont.truetype(p, 32) for p in fonts if Path(p).exists()),
        ImageFont.load_default(size=32),
    )
    image = Image.new("RGB", (1400, 360), "white")
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(ASSIGNMENT_DEMO.splitlines()):
        draw.text((45, 35 + index * 95), line, fill="black", font=font)
    image.save(ROOT / "samples/report.png")


async def main():
    (ROOT / "samples").mkdir(exist_ok=True)
    fixtures = {
        "report.txt": ASSIGNMENT_DEMO,
        "report-original.txt": ASSIGNMENT_INPUT,
        "report-ocr-typos.txt": "CBC: Hemglobin 10.2 g/dL (Low)\nWBC 11200 /uL (Hgh)",
        "report-conflict.txt": "Hemoglobin 10.2 g/dL (High) Reference: 12-15",
        "report-units.txt": "Hemoglobin 102 g/L (Low) Reference: 120-150\nWBC 11.2 10^9/L (High) Reference: 4-11",
    }
    for filename, text in fixtures.items():
        (ROOT / "samples" / filename).write_text(text + "\n", encoding="utf-8")
    image_fixture()
    example = await app.state.pipeline.run(ASSIGNMENT_DEMO, "sample-request", "assignment_demo")
    example.metadata.duration_ms = 0
    save_json("samples/expected-response.json", example.model_dump())
    save_json("docs/openapi.json", app.openapi())
    items = []

    def add(name, method, endpoint, body=None, expected=200, key=False):
        request = {"method": method, "url": "{{base_url}}" + endpoint, "header": []}
        if key:
            request["header"].append({"key": "X-Gemini-API-Key", "value": "{{gemini_api_key}}"})
        if body is not None:
            request["body"] = body
        items.append(
            {
                "name": name,
                "request": request,
                "event": [
                    {
                        "listen": "test",
                        "script": {
                            "type": "text/javascript",
                            "exec": [
                                f"pm.test('Expected HTTP status', () => pm.response.to.have.status({expected}));",
                                "pm.test('JSON response', () => pm.expect(pm.response.json()).to.have.property('status'));",
                            ],
                        },
                    }
                ],
            }
        )

    def raw(text, use_gemini=False):
        return {
            "mode": "raw",
            "raw": json.dumps({"text": text, "use_gemini": use_gemini}),
            "options": {"raw": {"language": "json"}},
        }

    add("Health", "GET", "/health")
    add("Assignment demo", "GET", "/demo")
    add("Text without LLM", "POST", "/reports/simplify/text", raw(ASSIGNMENT_DEMO))
    add(
        "Text with Gemini language",
        "POST",
        "/reports/simplify/text",
        raw(ASSIGNMENT_DEMO, True),
        key=True,
    )
    add(
        "Local image OCR",
        "POST",
        "/reports/simplify/image",
        {
            "mode": "formdata",
            "formdata": [{"key": "image", "type": "file", "src": "../samples/report.png"}],
        },
    )
    add(
        "Conflicting flag is rejected",
        "POST",
        "/reports/simplify/text",
        raw(fixtures["report-conflict.txt"]),
        expected=422,
    )
    add(
        "Gemini key required only when enabled",
        "POST",
        "/reports/simplify/text",
        raw(ASSIGNMENT_DEMO, True),
        expected=401,
    )
    save_json(
        "docs/Plum.postman_collection.json",
        {
            "info": {
                "name": "Medical Report Reader",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "variable": [
                {"key": "base_url", "value": "http://127.0.0.1:8000"},
                {"key": "gemini_api_key", "value": ""},
            ],
            "item": items,
        },
    )
    print("Generated synthetic fixtures, expected response, OpenAPI and Postman collection.")


if __name__ == "__main__":
    asyncio.run(main())
