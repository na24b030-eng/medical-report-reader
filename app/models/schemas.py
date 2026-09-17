from typing import Literal, Optional, List, Union
from pydantic import BaseModel, Field

class RefRange(BaseModel):
    low: float = Field(..., description="Lower bound of reference range")
    high: float = Field(..., description="Upper bound of reference range")

class NormalizedTest(BaseModel):
    name: str = Field(..., description="Standardized test name")
    value: Union[int, float] = Field(..., description="Numeric test value")
    unit: str = Field(..., description="Standardized unit of measurement")
    status: Literal["low", "high", "normal"] = Field(..., description="Clinical status relative to reference range")
    ref_range: RefRange = Field(..., description="Reference range for standard adult")

# --- Step 1: OCR / Text Extraction Output ---
class ExtractionResult(BaseModel):
    tests_raw: List[str] = Field(..., description="List of raw test lines extracted from text/image with typos corrected")
    confidence: float = Field(default=0.80, ge=0.0, le=1.0, description="Confidence score for the extraction step")

class Step1Request(BaseModel):
    text: str = Field(default="", description="Raw report text")

# --- Step 2: Normalized Tests Output ---
class NormalizationResult(BaseModel):
    tests: List[NormalizedTest] = Field(..., description="List of standardized, validated medical test items")
    normalization_confidence: float = Field(default=0.84, ge=0.0, le=1.0, description="Confidence score for the normalization step")

# --- Step 3: Patient-Friendly Summary Output ---
class ExplanationResult(BaseModel):
    summary: str = Field(..., description="One-sentence plain-language overview of abnormal findings")
    explanations: List[str] = Field(..., description="Plain-language, non-diagnostic explanations for abnormal findings")

# --- Guardrail / Exit Condition Output ---
class GuardrailExitResult(BaseModel):
    status: Literal["unprocessed"] = "unprocessed"
    reason: str = Field(default="hallucinated tests not present in input", description="Reason the processing was stopped")

# --- Step 4: Final Output ---
class FinalSuccessResult(BaseModel):
    tests: List[NormalizedTest] = Field(..., description="Normalized lab test results")
    summary: str = Field(..., description="Patient-friendly summary")
    status: Literal["ok"] = "ok"

# Request DTO
class AnalyzeReportRequest(BaseModel):
    text: Optional[str] = Field(None, description="Raw medical report text input")
    simulate_hallucination: Optional[bool] = Field(False, description="Testing flag to simulate ungrounded hallucination for guardrail validation")
    trace: Optional[bool] = Field(False, description="Flag to return detailed execution trace of all 4 steps")
    gemini_api_key: Optional[str] = Field(None, description="Optional custom Gemini API key provided by external client")

# Detailed trace for UI demo
class PipelineStepTrace(BaseModel):
    raw_ocr_or_text: str
    step1_extraction: ExtractionResult
    step2_normalization: NormalizationResult
    step3_explanation: ExplanationResult
    final_output: FinalSuccessResult
    explanation_source: str = Field(..., description="Source of explanations: gemini, gemini (client key), gemini (demo key), or fallback")
