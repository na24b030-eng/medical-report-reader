import time
import uuid
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse

from app.config import settings
from app.api.routes import router
from app.services.guardrail_service import HallucinationDetectedException

logger = logging.getLogger("app.api")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A robust backend service for OCR, test normalization, anti-hallucination guardrails, and plain-language patient explanations."
)

# CORS Middleware to support web clients (standards-compliant: allow_credentials=False for wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_process_time_and_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = str(duration_ms)
    logger.info("[%s] %s %s completed in %sms with status %s", request_id, request.method, request.url.path, duration_ms, response.status_code)
    return response

# Mount API routes
app.include_router(router)

# Custom exception handler for hallucination detection
@app.exception_handler(HallucinationDetectedException)
async def hallucination_exception_handler(request: Request, exc: HallucinationDetectedException):
    return JSONResponse(status_code=200, content={"status": "unprocessed", "reason": exc.reason})

# Mount static demo page
DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"
if DEMO_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(DEMO_DIR)), name="static")

@app.get("/demo", include_in_schema=False)
async def get_demo():
    index_path = DEMO_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Demo file not found."}

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/demo")
