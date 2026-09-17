# AI-Powered Medical Report Simplifier

A production-grade, deterministic-first backend service that parses medical lab reports (both typed text and scanned images), normalizes lab tests against standard reference catalogs, enforces strict source-evidence guardrails to prevent hallucinations, and generates patient-friendly explanations with Google Gemini and an offline-resilient fallback engine.

- **Live Web Application (GitHub Pages)**: [https://na24b030-eng.github.io/medical-report-reader/](https://na24b030-eng.github.io/medical-report-reader/)
---

## Architectural Overview and Core Principles

```
                  ┌──────────────────────────────────────────────┐
                  │          Input: Image or Typed Text          │
                  └──────────────────────┬───────────────────────┘
                                         │
        ┌────────────────────────────────┴────────────────────────────────┐
        │                                                                 │
  [Image Upload]                                                     [Raw Text]
        │                                                                 │
        ▼                                                                 ▼
┌───────────────────────────────┐                             ┌───────────────────────┐
│ Dedicated Local OCR Engine    │                             │ Standard Text Buffer  │
│ (RapidOCR ONNX / Tesseract)   │                             └───────────┬───────────┘
└───────────────┬───────────────┘                                         │
                │                                                         │
                └────────────────────────┬────────────────────────────────┘
                                         │
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │ Step 1: Extractor & Typo-Correction Service   │
                 │ - Strips formatting commas (11,200 -> 11200) │
                 │ - Corrects OCR typos (Hemglobin -> Hemoglobin)│
                 │ Output: tests_raw + confidence                │
                 └───────────────────────┬───────────────────────┘
                                         │
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │ Step 2: Normalizer & Reference Engine         │
                 │ - Deterministic value parsing                 │
                 │ - Standard reference range lookup             │
                 │ - Clinical status calculation (low/high/norm) │
                 │ Output: tests + normalization_confidence      │
                 └───────────────────────┬───────────────────────┘
                                         │
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │ Strict Guardrail: Source Evidence Check       │
                 │ Checks that EVERY test is grounded in input   │
                 └───────┬───────────────────────────────┬───────┘
                         │                               │
                [Ungrounded Test]               [All Tests Grounded]
                         │                               │
                         ▼                               ▼
        ┌────────────────────────────────┐  ┌────────────────────────────────┐
        │ Exit Condition Response        │  │ Step 3: Explanation Engine     │
        │ status: "unprocessed"          │  │ Gemini 3.6 / Flash             │
        │ reason: "hallucinated tests..."│  │ (or Curated Clinical Fallback) │
        └────────────────────────────────┘  └────────────────┬───────────────┘
                                                             │
                                                             ▼
                                            ┌────────────────────────────────┐
                                            │ Step 4: Final Output Assembly  │
                                            │ status: "ok" + tests + summary │
                                            └────────────────────────────────┘
```

### Key Architectural Decisions:
1. **Dedicated OCR Engine for Images**: Images are read using dedicated local OCR (`rapidocr-onnxruntime` and `pytesseract`) rather than passing raw images to an LLM. This prevents extraction-phase hallucinations.
2. **Backend Code Owns Values & Statuses**: Parsing values, formatting numbers, standardizing units, and calculating clinical statuses (`low`, `high`, `normal`) against standard reference ranges are performed **100% deterministically in Python**—not by an LLM.
3. **Strict Source-Evidence Guardrails**: Before generating explanations, every test in the normalized results is cross-referenced against the raw input tokens. If an ungrounded test is detected, the pipeline immediately halts and returns:
   ```json
   {
     "status": "unprocessed",
     "reason": "hallucinated tests not present in input"
   }
   ```
4. **Restricted Gemini Role**: Gemini is strictly constrained to translating verified findings into clear, empathetic, non-diagnostic explanations. It is barred from altering numbers or deciding medical status.
5. **Resilient Offline Fallback**: If the Gemini API is unconfigured, rate-limited, or fails validation, the system automatically uses a curated clinical knowledge dictionary. The API never crashes or fails to respond.

---

## Setup and Quickstart

### Prerequisites
- Python 3.10+ (tested on Python 3.14)
- `uv` or standard Python `venv`

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/na24b030-eng/medical-report-reader.git
   cd medical-report-reader
   ```

2. **Create virtual environment & install dependencies**:
   ```bash
   # Using uv (recommended, ultra-fast)
   uv venv .venv
   .venv\Scripts\activate     # On Windows
   # source .venv/bin/activate # On Linux/macOS
   uv pip install -r requirements.txt

   # OR using standard pip
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables (Optional)**:
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Add your Gemini API key:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
   *(Note: The system works completely out of the box even without an API key using the built-in clinical fallback engine! External users can also supply their own key directly in the web UI or via the `X-Gemini-API-Key` header).*

4. **Start the Backend Server**:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Open the Interactive Web UI**:
   - **Hosted Frontend (GitHub Pages)**: [https://na24b030-eng.github.io/medical-report-reader/](https://na24b030-eng.github.io/medical-report-reader/)
   - **Local Web UI**: [http://localhost:8000/demo](http://localhost:8000/demo)

   *In the Web UI, visitors can enter their own Gemini API key for live AI explanations or leave the field empty to use the server demo key or built-in clinical fallback engine.*

---

## API Usage and Sample Requests

### 1. Main Unified Endpoint: `/api/v1/simplify-report`

#### A. Text Input (Sample from PDF)
```bash
curl -X POST http://localhost:8000/api/v1/simplify-report \
  -H "Content-Type: application/json" \
  -d '{
    "text": "CBC: Hemoglobin 10.2 g/dL (Low) , WBC 11,200 /uL (High)"
  }'
```

**Expected Response (Step 4 Schema):**
```json
{
  "tests": [
    {
      "name": "Hemoglobin",
      "value": 10.2,
      "unit": "g/dL",
      "status": "low",
      "ref_range": {
        "low": 12.0,
        "high": 15.0
      }
    },
    {
      "name": "WBC",
      "value": 11200,
      "unit": "/uL",
      "status": "high",
      "ref_range": {
        "low": 4000.0,
        "high": 11000.0
      }
    }
  ],
  "summary": "Low hemoglobin and high white blood cell count.",
  "status": "ok"
}
```

#### B. Text Input with OCR Typos (Sample from PDF)
```bash
curl -X POST http://localhost:8000/api/v1/simplify-report \
  -H "Content-Type: application/json" \
  -d '{
    "text": "CBC: Hemglobin 10.2 g/dL (Low)\nWBC 11200 /uL (Hgh)"
  }'
```

#### C. Image Upload (Dedicated OCR)
```bash
curl -X POST http://localhost:8000/api/v1/simplify-report \
  -F "file=@samples/sample_report.png"
```

#### D. Guardrail Exit Condition Trigger
```bash
curl -X POST http://localhost:8000/api/v1/simplify-report \
  -H "Content-Type: application/json" \
  -d '{
    "text": "CBC: Hemoglobin 10.2 g/dL (Low)",
    "simulate_hallucination": true
  }'
```

**Exit Response:**
```json
{
  "status": "unprocessed",
  "reason": "hallucinated tests not present in input"
}
```

---

### 2. Isolated Step Endpoints

- **Step 1 (`POST /api/v1/extract-text`)**:
  ```bash
  curl -X POST http://localhost:8000/api/v1/extract-text \
    -H "Content-Type: application/json" \
    -d '{"text": "CBC: Hemglobin 10.2 g/dL (Low)\nWBC 11200 /uL (Hgh)"}'
  ```
  Returns:
  ```json
  {
    "tests_raw": [
      "Hemoglobin 10.2 g/dL (Low)",
      "WBC 11200 /uL (High)"
    ],
    "confidence": 0.8
  }
  ```

- **Step 2 (`POST /api/v1/normalize-tests`)**:
  ```bash
  curl -X POST http://localhost:8000/api/v1/normalize-tests \
    -H "Content-Type: application/json" \
    -d '{
      "tests_raw": [
        "Hemoglobin 10.2 g/dL (Low)",
        "WBC 11200 /uL (High)"
      ],
      "confidence": 0.8
    }'
  ```

- **Step 3 (`POST /api/v1/summarize`)**:
  Accepts normalized test array and returns plain-language summary and explanations without medical diagnosis.

---

## Running Automated Tests

Run the complete test suite covering all four steps, OCR, normalizer, guardrails, and API integration:

```bash
.venv\Scripts\pytest tests\ -v
```

---

## Frontend Web Application and Live Demo Access

### 1. Hosted Web Application (GitHub Pages)
The client-side demo interface is hosted on GitHub Pages:
- **Live URL**: [https://na24b030-eng.github.io/medical-report-reader/](https://na24b030-eng.github.io/medical-report-reader/)

### 2. Local Interactive Web UI
When running the FastAPI server locally:
- **Local URL**: [http://localhost:8000/demo](http://localhost:8000/demo)

### 3. Exposing Local Backend for Remote Access (ngrok)
To share your live local backend instance with external reviewers:

1. Start your local server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
2. In a separate terminal, launch ngrok:
   ```bash
   ngrok http 8000
   ```
3. Copy the generated public URL (e.g. `https://xyz.ngrok-free.app`) and append `/demo` to view the interactive web UI, or send requests directly to `/api/v1/simplify-report`.

