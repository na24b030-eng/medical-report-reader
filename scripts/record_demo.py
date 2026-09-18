"""Record real Swagger endpoint executions. Use --live to include Gemini NLP."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from app.config import settings
from app.pipeline import ASSIGNMENT_DEMO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    key = settings.gemini_api_key.get_secret_value() if args.live else ""
    if args.live and not key:
        raise SystemExit("Live recording needs GEMINI_API_KEY in .env.")
    Path("artifacts").mkdir(exist_ok=True)
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--no-access-log",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    base = "http://127.0.0.1:8765"
    try:
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError("Recording server could not start; check port 8765.")
            try:
                if httpx.get(base + "/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)
        else:
            raise RuntimeError("Recording server did not become ready.")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, channel="msedge" if os.name == "nt" else None
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                record_video_dir="tmp/video",
                record_video_size={"width": 1440, "height": 1000},
                extra_http_headers={"X-Gemini-API-Key": key} if key else {},
            )
            page = context.new_page()
            page.goto(base + "/docs")
            expect(page.get_by_text("Medical Report Reader", exact=False).first).to_be_visible()
            page.wait_for_timeout(1500)
            operation = page.locator(".opblock").filter(
                has=page.locator('[data-path="/reports/simplify/text"]')
            )
            operation.locator(".opblock-summary").click()
            operation.get_by_role("button", name="Try it out").click()
            operation.locator("textarea").fill(
                json.dumps({"text": ASSIGNMENT_DEMO, "use_gemini": args.live}, indent=2)
            )
            page.screenshot(path="artifacts/demo-request.png", full_page=True)
            with page.expect_response(
                lambda r: r.url.endswith("/reports/simplify/text") and r.request.method == "POST",
                timeout=60000,
            ) as response:
                operation.get_by_role("button", name="Execute", exact=True).click()
            data = response.value.json()
            if response.value.status != 200 or [t["value"] for t in data["tests"]] != [10.2, 11200]:
                raise RuntimeError("Text demo did not return expected results.")
            if args.live and data["metadata"]["language_provider"] != "gemini":
                raise RuntimeError("Text demo used fallback; live verification is not complete.")
            operation.locator(".live-responses-table").scroll_into_view_if_needed()
            page.wait_for_timeout(2200)
            page.screenshot(path="artifacts/demo-text-result.png", full_page=True)
            operation.locator(".opblock-summary").click()
            image_op = page.locator(".opblock").filter(
                has=page.locator('[data-path="/reports/simplify/image"]')
            )
            image_op.locator(".opblock-summary").click()
            image_op.get_by_role("button", name="Try it out").click()
            image_op.locator('input[type="file"]').set_input_files("samples/report.png")
            if args.live:
                image_op.locator("select").filter(
                    has=page.locator('option[value="true"]')
                ).select_option("true")
            with page.expect_response(
                lambda r: r.url.endswith("/reports/simplify/image") and r.request.method == "POST",
                timeout=90000,
            ) as response:
                image_op.get_by_role("button", name="Execute", exact=True).click()
            data = response.value.json()
            if response.value.status != 200 or [t["value"] for t in data["tests"]] != [10.2, 11200]:
                raise RuntimeError("Image demo did not return expected OCR results.")
            if args.live and data["metadata"]["language_provider"] != "gemini":
                raise RuntimeError("Image demo used fallback; live verification is not complete.")
            image_op.locator(".live-responses-table").scroll_into_view_if_needed()
            page.wait_for_timeout(2500)
            page.screenshot(path="artifacts/demo-image-result.png", full_page=True)
            image_op.locator(".opblock-summary").click()
            operation.locator(".opblock-summary").click()
            operation.locator("textarea").fill(
                json.dumps(
                    {"text": "Hemoglobin 10.2 g/dL (High) Reference: 12-15", "use_gemini": False},
                    indent=2,
                )
            )
            with page.expect_response(
                lambda r: r.url.endswith("/reports/simplify/text") and r.request.method == "POST"
            ) as response:
                operation.get_by_role("button", name="Execute", exact=True).click()
            if response.value.status != 422:
                raise RuntimeError("Conflict guardrail did not reject input.")
            operation.locator(".live-responses-table").scroll_into_view_if_needed()
            page.wait_for_timeout(2200)
            page.screenshot(path="artifacts/demo-guardrail.png", full_page=True)
            video = page.video
            context.close()
            output = Path("artifacts") / ("live-demo.webm" if args.live else "backend-demo.webm")
            video.save_as(str(output))
            browser.close()
        Path("artifacts/recording.json").write_text(
            json.dumps(
                {
                    "file": str(output),
                    "actual_endpoint_calls": True,
                    "local_ocr": True,
                    "gemini_live": args.live,
                    "checks": ["text:200", "image:200", "conflict:422"],
                },
                indent=2,
            )
            + "\n"
        )
        print(f"Saved {output}; actual text, image and guardrail requests verified.")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
