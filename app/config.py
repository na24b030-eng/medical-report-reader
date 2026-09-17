import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    PROJECT_NAME: str = "AI-Powered Medical Report Simplifier"
    VERSION: str = "1.0.0"
    
    # Gemini Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    GEMINI_TIMEOUT_SECONDS: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "10.0"))
    
    # OCR Configuration
    # Automatically search standard locations if not explicitly set
    _configured_tesseract = os.getenv("TESSERACT_CMD", "")
    if _configured_tesseract and Path(_configured_tesseract).exists():
        TESSERACT_CMD: str = _configured_tesseract
    elif shutil.which("tesseract"):
        TESSERACT_CMD: str = shutil.which("tesseract") or ""
    elif Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe").exists():
        TESSERACT_CMD: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    elif Path(os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe")).exists():
        TESSERACT_CMD: str = os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe")
    else:
        TESSERACT_CMD: str = ""
        
    MAX_IMAGE_SIZE_MB: int = int(os.getenv("MAX_IMAGE_SIZE_MB", "15"))
    MEDICAL_CATALOG_PATH: Path = BASE_DIR / "app" / "data" / "medical_catalog.json"

settings = Settings()
