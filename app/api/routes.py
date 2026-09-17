import logging
from typing import Optional, Union, List
from fastapi import APIRouter, UploadFile, File, Form, Request, HTTPException, status

from app.models.schemas import (
    FinalSuccessResult,
    GuardrailExitResult,
    ExtractionResult,
    Step1Request,
    NormalizationResult,
    ExplanationResult,
    PipelineStepTrace,
    NormalizedTest
)
from app.services.pipeline import run_pipeline
from app.services.catalog_service import load_catalog
from app.services.extractor_service import extract_raw_tests
from app.services.normalizer_service import normalize_extracted_tests
from app.services.gemini_service import generate_explanation_with_gemini
from app.services.fallback_service import generate_fallback_explanation
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Medical Report Simplifier"])

@router.get("/health")
def health_check():
    """Health check endpoint providing status of dependencies."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "gemini_configured": bool(settings.GEMINI_API_KEY),
        "tesseract_detected": bool(settings.TESSERACT_CMD)
    }

@router.get("/catalog", summary="Get supported medical tests catalog")
def get_catalog():
    """Returns the verified clinical reference ranges, units, and synonyms for all supported tests."""
    catalog = load_catalog()
    return {
        "total_tests": len(catalog),
        "tests": [
            {
                "canonical_name": k,
                "canonical_unit": v.get("canonical_unit", ""),
                "ref_range": v.get("ref_range", {}),
                "synonyms": v.get("synonyms", [])
            }
            for k, v in catalog.items()
        ]
    }

@router.post(
    "/simplify-report",
    response_model=Union[FinalSuccessResult, GuardrailExitResult, PipelineStepTrace],
    summary="Main unified endpoint for medical report simplification"
)
async def simplify_report(
    request: Request,
    trace: bool = False,
    simulate_hallucination: bool = False
):
    """
    Accepts either:
    1. application/json with {"text": "CBC: Hemoglobin 10.2 g/dL (Low)..."}
    2. multipart/form-data with an image file
    Executes the 4-step pipeline and returns the normalized tests, summary, and status.
    """
    content_type = request.headers.get("content-type", "").lower()
    text_input: Optional[str] = None
    image_bytes: Optional[bytes] = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        file_obj = form.get("file")
        if file_obj and hasattr(file_obj, "read"):
            image_bytes = await file_obj.read()
            max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
            if len(image_bytes) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Image file size exceeds maximum limit of {settings.MAX_IMAGE_SIZE_MB}MB."
                )
        if not image_bytes and "text" in form:
            text_input = str(form.get("text"))
        if "simulate_hallucination" in form:
            simulate_hallucination = str(form.get("simulate_hallucination")).lower() in ("true", "1")
        if "trace" in form:
            trace = str(form.get("trace")).lower() in ("true", "1")
    elif "application/json" in content_type:
        try:
            body = await request.json()
            text_input = body.get("text")
            if body.get("simulate_hallucination"):
                simulate_hallucination = True
            if body.get("trace"):
                trace = True
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload."
            )
    else:
        # Try reading raw body as text
        raw_body = await request.body()
        if raw_body:
            text_input = raw_body.decode("utf-8", errors="ignore")

    if not text_input and not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Must provide either text payload or an uploaded image file."
        )

    result = run_pipeline(
        text=text_input,
        image_bytes=image_bytes,
        simulate_hallucination=simulate_hallucination,
        return_trace=trace
    )
    return result

# --- Step-by-Step Explicit Endpoints ---

@router.post(
    "/extract-text",
    response_model=ExtractionResult,
    summary="Step 1: Extract test names, values, units; fix minor typos"
)
async def step1_extract(payload: Step1Request):
    """Executes Step 1: Extracts tests_raw and confidence."""
    return extract_raw_tests(payload.text)

@router.post(
    "/normalize-tests",
    response_model=NormalizationResult,
    summary="Step 2: Standardize names, units, ranges, and statuses"
)
async def step2_normalize(extraction: ExtractionResult):
    """Executes Step 2: Converts tests_raw into NormalizedTest objects with ranges."""
    return normalize_extracted_tests(extraction)

@router.post(
    "/summarize",
    response_model=ExplanationResult,
    summary="Step 3: Patient-friendly explanation generation"
)
async def step3_summarize(payload: Union[List[NormalizedTest], NormalizationResult]):
    """
    Executes Step 3: Generates plain-language explanation without medical diagnosis.
    Accepts either a list of NormalizedTest or a NormalizationResult object.
    """
    tests = payload.tests if isinstance(payload, NormalizationResult) else payload
    catalog = load_catalog()
    try:
        return generate_explanation_with_gemini(tests, catalog)
    except Exception:
        return generate_fallback_explanation(tests, catalog)
