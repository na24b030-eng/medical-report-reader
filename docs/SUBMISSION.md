# Submission checklist

## Deliverables

| Requirement | Prepared artifact | Final verification |
| --- | --- | --- |
| Working backend demo | FastAPI service, Dockerfile, Swagger UI (/docs) | Supply a hosted HTTPS URL or keep a local tunnel running |
| GitHub repository | Isolated local Git repository | Push to the intended GitHub repository |
| Setup, architecture, API examples | README.md | Run `uvicorn app.main:app` and `pytest tests/` from a fresh checkout |
| curl/Postman requests | README.md, docs/Plum.postman_collection.json | Import the collection or run documented cURL commands |
| JSON schemas | docs/openapi.json | Inspect successful and unprocessed responses |
| Sample typed/scanned input | samples/report.txt, samples/sample_report.png | Run `pytest tests/` with automated OCR & text fixtures |
| Screen recording | Interactive Swagger UI at `/docs` or terminal | Screen recording demonstrating text parsing, image OCR, and guardrail |

## Local verification

```sh
# Setup virtual environment and dependencies
python -m venv .venv
# On Windows: .venv\Scripts\activate
# On Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# Run automated test suite
python -m pytest tests/ -v

# Start FastAPI backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Live verification & Gemini Configuration

Create a `.env` file at project root with:
```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.6-flash
```
Local OCR and deterministic normalizers run completely offline without an API key. When Gemini is unavailable or rate-limited, the system seamlessly applies the clinical fallback engine.

## Hosting & Docker

The service runs on any Python 3.10+ host or Docker environment on port 8000. No external database is required.

- Health route: `/api/v1/health`
- Interactive OpenAPI Documentation: `/docs` and `/redoc`
- Public Catalog: `/api/v1/catalog`

Docker commands:

```sh
docker build -t plum-medical-simplifier .
docker run --rm -p 8000:8000 -e GEMINI_API_KEY=your_key_here plum-medical-simplifier
```

For the brief's allowed local demo, start the app then run `ngrok http 8000` with a configured ngrok installation. Keep both processes running during review.


## Recording outline

1. Open Swagger UI at `/docs` or terminal and run the standard text sample.
2. Show the tests, reference ranges, source evidence, and combined JSON.
3. Process the synthetic text through Gemini using a masked key.
4. Upload samples/report.png and show the OCR results.
5. Submit samples/report-conflict.txt and show the unprocessed response.
6. Clear the key and state the boundaries: supported test set, source-only ranges, and OCR needing human comparison.

## Scope decisions to explain to reviewers

- Code extracts and validates names, values, units and statuses. Gemini cannot create or modify results.
- Reference ranges are never invented. The assignment's original input omits them, so that case returns null ranges; the demo fixture explicitly supplies its example ranges.
- Explanations use approved alternatives. Local Tesseract handles OCR; Gemini only selects plain-language wording.
- Clinical confidence is null because it is not calibrated. Low Tesseract OCR confidence triggers rejection and is reported separately.
- Image output is verified against OCR text, not independently against pixels. Consistent OCR errors remain possible.
- Supported result formats are intentionally constrained and documented. Unknown, unreadable, or extra content is rejected, not silently ignored.

## Submission message template

Repository: https://github.com/na24b030-eng/medical-report-reader

Working backend demo: [insert the verified HTTPS URL or ngrok URL]

Setup and API documentation are in README.md. A Postman collection, OpenAPI schema, synthetic text/image fixtures, and automated backend tests are included. Text processing and local image OCR work without a key. Optional Gemini wording uses each reviewer's own key.
