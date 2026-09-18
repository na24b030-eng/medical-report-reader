from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["low", "normal", "high", "unknown"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class TextRequest(StrictModel):
    text: str = Field(min_length=1, max_length=20000)
    use_gemini: bool = False


class ReferenceRange(StrictModel):
    low: float
    high: float


class NormalizedTest(StrictModel):
    name: str
    value: float
    unit: str
    status: Status
    ref_range: ReferenceRange | None


class Evidence(StrictModel):
    test_id: str
    source_text: str
    source_start: int
    source_end: int
    raw_name: str
    raw_value: str
    raw_unit: str
    conversion_factor: str
    status_basis: Literal["report_range", "report_flag", "unavailable"]
    corrections: list[str]


class Extraction(StrictModel):
    tests_raw: list[str]
    confidence: float = Field(ge=0, le=1)
    confidence_basis: str


class Normalization(StrictModel):
    normalization_confidence: float = Field(ge=0, le=1)
    confidence_basis: str
    evidence: list[Evidence]


class Metadata(StrictModel):
    request_id: str
    input_type: Literal["text", "image", "assignment_demo"]
    source_text: str
    language_provider: Literal["templates", "gemini"]
    language_status: Literal["not_requested", "applied", "fallback"]
    warnings: list[str]
    duration_ms: int
    ocr_engine: str | None = None


class ReportResponse(StrictModel):
    status: Literal["ok"] = "ok"
    tests: list[NormalizedTest]
    summary: str
    explanations: list[str]
    extraction: Extraction
    normalization: Normalization
    metadata: Metadata


class ErrorResponse(StrictModel):
    status: Literal["error", "unprocessed"]
    reason: str
    request_id: str


class LanguageItem(StrictModel):
    test_id: str
    definition: str = Field(max_length=500)
    assessment: str = Field(max_length=500)


class LanguagePlan(StrictModel):
    items: list[LanguageItem] = Field(min_length=1, max_length=50)


class Unprocessed(Exception):
    """The source cannot support a reliable result; never return partial tests."""


class Busy(Exception):
    pass
