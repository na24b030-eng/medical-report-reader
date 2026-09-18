# Medical Report Reader

Backend API that extracts biomarker results from medical reports (text or image), normalizes values with unit conversion, applies anti-hallucination guardrails, and generates grounded patient-friendly explanations.

## Architecture

```
Input (text or image)
       |
  [1. OCR]  -- local RapidOCR, CPU-only, image never leaves the server
       |
  [2. Extraction]  -- deterministic regex, no LLM
       |
  [3. Normalization]  -- unit conversion, reference range comparison, flag resolution
       |
  [4. Guardrail]  -- re-parse and diff to reject hallucinated or altered results
       |
  [5. Language]  -- constrained Gemini NLP (optional) or approved local templates
       |
  JSON Response
```

**Design principles**

- All numeric extraction and normalization is deterministic (regex + decimal arithmetic). Gemini is never used for data extraction.
- The optional Gemini step only selects pre-approved sentence fragments for patient-friendly wording. It cannot invent medical claims, values, diagnoses, or treatments.
- A final guardrail re-parses the source text independently and rejects the response if any test was added, removed, or altered downstream.
- Uploaded images are processed locally with RapidOCR. They are never sent to any external API.

## Supported biomarkers

Hemoglobin, WBC, Platelets, RBC, Glucose, Creatinine, TSH, Total cholesterol.

Each biomarker has known aliases (including common OCR typos), canonical units, and conversion factors for alternate units.

## Setup

### Prerequisites

- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/) package manager (recommended) or pip

### Install and run

```bash
# Clone
git clone https://github.com/na24b030-eng/medical-report-reader.git
cd medical-report-reader

# Install dependencies
uv sync

# (Optional) Configure Gemini for NLP wording
cp .env.example .env
# Edit .env: set GEMINI_API_KEY and ALLOW_SERVER_KEY=true

# Start the server
uv run uvicorn app.main:app --reload

# Open Swagger UI
# http://127.0.0.1:8000/docs
```

### With pip (alternative)

```bash
python -m venv .venv
.venv/Scripts/activate    # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Docker

```bash
docker build -t medical-report-reader .
docker run -p 8000:8000 medical-report-reader
```

## Demo video

A screen recording demonstrating the endpoints (`/reports/simplify/text`, `/reports/simplify/image` with local OCR, and the medical conflict guardrail) is included in the repository:

- [View demo recording](docs/demo.webm)

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/demo` | Assignment example with fixture data |
| POST | `/reports/simplify/text` | Analyze text report |
| POST | `/reports/simplify/image` | Analyze image report (local OCR) |
| GET | `/docs` | Swagger UI |

## API usage examples

### 1. Text report (Deterministic - No external AI)

#### cURL
```bash
curl -X POST http://127.0.0.1:8000/reports/simplify/text \
  -H "Content-Type: application/json" \
  -d '{
    "text": "CBC:\nHemoglobin 10.2 g/dL (Low) Reference: 12.0-15.0\nWBC 11,200 /uL (High) Reference: 4000-11000",
    "use_gemini": false
  }'
```

#### Python (requests)
```python
import requests

url = "http://127.0.0.1:8000/reports/simplify/text"
payload = {
    "text": "CBC:\nHemoglobin 10.2 g/dL (Low) Reference: 12.0-15.0\nWBC 11,200 /uL (High) Reference: 4000-11000",
    "use_gemini": False
}
response = requests.post(url, json=payload)
data = response.json()
print("Status:", data["status"])
for test in data["tests"]:
    print(f"- {test['name']}: {test['value']} {test['unit']} ({test['status']})")
print("Summary:", data["summary"])
```

#### JavaScript (fetch / Node.js)
```javascript
const response = await fetch("http://127.0.0.1:8000/reports/simplify/text", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    text: "CBC:\nHemoglobin 10.2 g/dL (Low) Reference: 12.0-15.0\nWBC 11,200 /uL (High) Reference: 4000-11000",
    use_gemini: false
  })
});
const data = await response.json();
console.log(data.summary);
```

### 2. Image report (Local RapidOCR on CPU)

#### cURL
```bash
curl -X POST http://127.0.0.1:8000/reports/simplify/image \
  -F "image=@samples/report.png" \
  -F "use_gemini=false"
```

#### Python (requests)
```python
import requests

url = "http://127.0.0.1:8000/reports/simplify/image"
with open("samples/report.png", "rb") as f:
    files = {"image": ("report.png", f, "image/png")}
    data = {"use_gemini": "false"}
    response = requests.post(url, files=files, data=data)
print(response.json())
```

### 3. Text report with optional Gemini NLP

Pass `use_gemini: true` and provide the `X-Gemini-API-Key` header:

```bash
curl -X POST http://127.0.0.1:8000/reports/simplify/text \
  -H "Content-Type: application/json" \
  -H "X-Gemini-API-Key: YOUR_GEMINI_API_KEY" \
  -d '{
    "text": "CBC:\nHemoglobin 10.2 g/dL (Low) Reference: 12.0-15.0\nWBC 11,200 /uL (High) Reference: 4000-11000",
    "use_gemini": true
  }'
```

### 4. Assignment demo endpoint

```bash
curl http://127.0.0.1:8000/demo
```


## Sample response

```json
{
  "status": "ok",
  "tests": [
    {
      "name": "Hemoglobin",
      "value": 10.2,
      "unit": "g/dL",
      "status": "low",
      "ref_range": { "low": 12.0, "high": 15.0 }
    },
    {
      "name": "WBC",
      "value": 11200.0,
      "unit": "/uL",
      "status": "high",
      "ref_range": { "low": 4000.0, "high": 11000.0 }
    }
  ],
  "summary": "Low hemoglobin and high white blood cell count.",
  "explanations": [
    "Hemoglobin carries oxygen in your red blood cells. This result is below the reference range shown in the report.",
    "White blood cells are part of your immune system. This result is above the reference range shown in the report."
  ],
  "extraction": {
    "tests_raw": [
      "Hemoglobin 10.2 g/dL (Low) Reference: 12.0-15.0\n",
      "WBC 11,200 /uL (High) Reference: 4000-11000"
    ],
    "confidence": 1.0,
    "confidence_basis": "Exact deterministic text parsing; not clinical confidence"
  },
  "normalization": {
    "normalization_confidence": 1.0,
    "confidence_basis": "Rule-coverage score: 1.0 for supported exact rules, 0.95 when explicit OCR typo aliases are corrected; not a probability",
    "evidence": [
      {
        "test_id": "test_1",
        "source_text": "Hemoglobin 10.2 g/dL (Low) Reference: 12.0-15.0\n",
        "source_start": 5,
        "source_end": 53,
        "raw_name": "Hemoglobin",
        "raw_value": "10.2",
        "raw_unit": "g/dL",
        "conversion_factor": "1",
        "status_basis": "report_range",
        "corrections": []
      },
      {
        "test_id": "test_2",
        "source_text": "WBC 11,200 /uL (High) Reference: 4000-11000",
        "source_start": 53,
        "source_end": 96,
        "raw_name": "WBC",
        "raw_value": "11,200",
        "raw_unit": "/uL",
        "conversion_factor": "1",
        "status_basis": "report_range",
        "corrections": []
      }
    ]
  },
  "metadata": {
    "request_id": "sample-request",
    "input_type": "assignment_demo",
    "source_text": "CBC:\nHemoglobin 10.2 g/dL (Low) Reference: 12.0-15.0\nWBC 11,200 /uL (High) Reference: 4000-11000",
    "language_provider": "templates",
    "language_status": "not_requested",
    "warnings": [
      "Educational explanation, not a diagnosis. Discuss results with your clinician."
    ],
    "duration_ms": 0,
    "ocr_engine": null
  }
}
```

## Guardrails and error handling

The API rejects unsafe or ambiguous input with HTTP 422 and `status: "unprocessed"`:

- Conflicting flags vs reference ranges (e.g., marked "High" but value is within range)
- Inverted reference ranges (low > high)
- Duplicate test results requiring manual review
- Unsupported units or unsupported biomarker names
- Unparsed leftover content (prevents silent omission of unknown tests)
- Precision loss during unit conversion
- Hallucinated or altered results detected by the final guardrail
- Prompt injection attempts in text input

Additional error codes: 400 (invalid request), 401 (missing API key when Gemini requested), 408 (upload timeout), 413 (body too large), 429 (capacity limit or Gemini quota), 500 (unexpected failure).

## Gemini API key handling

Gemini is optional and used only for natural-language wording, never for data extraction.

- Pass `use_gemini: true` and the `X-Gemini-API-Key` header to enable Gemini NLP.
- Without a key, the API uses approved local template explanations.
- If Gemini is unavailable or returns an error, the API falls back to templates automatically and includes a warning.
- Keys are per-request, never stored, and never echoed in responses.

## Running tests

```bash
uv run pytest -v
```

## Project structure

```
app/
  main.py         -- FastAPI app, routes, middleware, error handlers
  config.py       -- Pydantic settings from .env
  schemas.py      -- All request/response Pydantic models
  engine.py       -- Deterministic extraction, normalization, guardrail
  catalog.py      -- Biomarker definitions, aliases, units, conversion factors
  language.py     -- Constrained Gemini NLP and local template fallback
  pipeline.py     -- Orchestrates engine + language into a response
  ocr.py          -- Local RapidOCR image processing
  static/swagger/ -- Vendored Swagger UI assets
tests/
  test_api.py     -- 11 API integration tests
  test_engine.py  -- 22 engine unit tests (including parametrized)
samples/          -- Sample inputs and expected output
scripts/          -- Submission preparation and demo recording tools
docs/             -- OpenAPI spec and Postman collection
```

## Postman collection

Import `docs/Plum.postman_collection.json` into Postman. Set the `base_url` variable to your server address and optionally set `gemini_api_key`.
