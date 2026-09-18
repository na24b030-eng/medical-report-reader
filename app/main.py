import asyncio
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.language import GeminiLanguage
from app.ocr import MAX_IMAGE_BYTES, LocalOCR
from app.pipeline import ASSIGNMENT_DEMO, Pipeline
from app.schemas import Busy, ErrorResponse, ReportResponse, TextRequest, Unprocessed

key_header = APIKeyHeader(
    name="X-Gemini-API-Key",
    auto_error=False,
    description="Optional per-request key. Used only when use_gemini=true; never saved.",
)


class BodyLimitMiddleware:
    """Enforce the actual body size, including chunked requests, before parsing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        limit = 6 * 1024 * 1024 if scope["path"].endswith("/image") else 100 * 1024
        body = bytearray()
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=15)
            except TimeoutError:
                response = JSONResponse(
                    {
                        "status": "error",
                        "reason": "Request upload timed out.",
                        "request_id": str(uuid.uuid4()),
                    },
                    status_code=408,
                )
                return await response(scope, receive, send)
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                response = JSONResponse(
                    {
                        "status": "error",
                        "reason": "Request body is too large.",
                        "request_id": str(uuid.uuid4()),
                    },
                    status_code=413,
                )
                return await response(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(pipeline: Pipeline | None = None, ocr: LocalOCR | None = None) -> FastAPI:
    app = FastAPI(
        title="Medical Report Reader",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        description="Local OCR, deterministic extraction and normalization, grounded explanations. Gemini is restricted to optional NLP. No diagnosis or treatment advice.",
    )
    app.add_middleware(BodyLimitMiddleware)
    app.mount(
        "/docs-assets",
        StaticFiles(directory=Path(__file__).parent / "static" / "swagger"),
        name="docs-assets",
    )

    @app.get("/docs", include_in_schema=False)
    async def docs():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="Medical Report Reader - API",
            swagger_js_url="/docs-assets/swagger-ui-bundle.js",
            swagger_css_url="/docs-assets/swagger-ui.css",
            swagger_favicon_url="/docs-assets/favicon-32x32.png",
            swagger_ui_parameters={
                "docExpansion": "none",
                "defaultModelsExpandDepth": -1,
                "persistAuthorization": False,
            },
        )

    app.state.pipeline = pipeline or Pipeline(GeminiLanguage(settings.gemini_model))
    app.state.ocr = ocr or LocalOCR(settings.ocr_min_confidence)
    slots = threading.BoundedSemaphore(3)

    @asynccontextmanager
    async def capacity():
        if not slots.acquire(blocking=False):
            raise Busy("Processing capacity reached. Please retry shortly.")
        try:
            yield
        finally:
            slots.release()

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def error(request: Request, reason: str, status_code: int, kind: str = "error"):
        return JSONResponse(
            ErrorResponse(
                status=kind, reason=reason, request_id=request.state.request_id
            ).model_dump(),
            status_code=status_code,
        )

    @app.exception_handler(Unprocessed)
    async def unprocessed(request, exc):
        return error(request, str(exc), 422, "unprocessed")

    @app.exception_handler(Busy)
    async def busy(request, exc):
        return error(request, str(exc), 429)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        # FastAPI's default errors may echo submitted input. Never echo payloads or credentials.
        return error(
            request,
            "Invalid request. Check field types, required fields and size limits in /docs.",
            400,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request, str(exc.detail), exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected(request, _exc):
        return error(
            request, "Unexpected processing failure. Please retry or provide clearer input.", 500
        )

    def resolve_key(enabled: bool, key: str | None) -> str | None:
        if not enabled:
            return None
        value = key or (
            settings.gemini_api_key.get_secret_value() if settings.allow_server_key else ""
        )
        if not value:
            raise HTTPException(
                401,
                "Supply X-Gemini-API-Key for use_gemini=true, or disable optional Gemini wording.",
            )
        if not 20 <= len(value) <= 500 or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise HTTPException(400, "Invalid Gemini API-key format.")
        return value

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/docs")

    @app.get("/health", tags=["Operations"])
    async def health():
        return {"status": "ok", "ocr": "local_rapidocr", "gemini_role": "optional_language_only"}

    errors = {code: {"model": ErrorResponse} for code in (400, 401, 408, 413, 422, 429, 500)}

    @app.post(
        "/reports/simplify/text", response_model=ReportResponse, responses=errors, tags=["Reports"]
    )
    async def simplify_text(
        body: TextRequest, request: Request, key: Annotated[str | None, Depends(key_header)]
    ):
        credential = resolve_key(body.use_gemini, key)
        async with capacity():
            return await app.state.pipeline.run(body.text, request.state.request_id, key=credential)

    @app.post(
        "/reports/simplify/image", response_model=ReportResponse, responses=errors, tags=["Reports"]
    )
    async def simplify_image(
        request: Request,
        image: Annotated[
            UploadFile,
            File(description="PNG, JPEG or WebP; max 5 MB, 16 megapixels; crop to result lines"),
        ],
        key: Annotated[str | None, Depends(key_header)],
        use_gemini: Annotated[bool, Form()] = False,
    ):
        credential = resolve_key(use_gemini, key)
        try:
            content = await image.read(MAX_IMAGE_BYTES + 1)
        finally:
            await image.close()
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image exceeds the 5 MB limit.")
        async with capacity():
            recognized = await run_in_threadpool(app.state.ocr.read, content)
            return await app.state.pipeline.run(
                recognized.text,
                request.state.request_id,
                "image",
                credential,
                recognized.confidence,
            )

    @app.get(
        "/demo",
        response_model=ReportResponse,
        tags=["Demo"],
        summary="Assignment example with explicitly supplied fixture ranges; no Gemini calls",
    )
    async def demo(request: Request):
        result = await app.state.pipeline.run(
            ASSIGNMENT_DEMO, request.state.request_id, "assignment_demo"
        )
        result.metadata.warnings.append(
            "Synthetic assignment fixture: its source text explicitly includes example ranges. These are not patient defaults."
        )
        return result

    return app


app = create_app()
