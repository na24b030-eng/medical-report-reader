import io
import logging
from typing import Tuple
from PIL import Image, ImageOps
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Initialize RapidOCR engine once as high-performance local OCR
_rapid_ocr_engine = None
try:
    from rapidocr_onnxruntime import RapidOCR
    _rapid_ocr_engine = RapidOCR()
    logger.info("RapidOCR ONNX engine initialized successfully.")
except Exception as e:
    logger.warning("RapidOCR could not be initialized: %s", e)


def preprocess_image(image_bytes: bytes) -> Tuple[Image.Image, np.ndarray]:
    """Load image from bytes, validate, auto-contrast, and convert to numpy array."""
    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        raise ValueError(f"Invalid image data: {str(e)}")

    # Ensure standard RGB mode
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")

    # Auto-contrast enhancement for scanned papers
    try:
        pil_img = ImageOps.autocontrast(pil_img, cutoff=1)
    except Exception:
        pass

    # Convert to numpy array for OCR engines
    np_img = np.array(pil_img)
    return pil_img, np_img


def extract_text_from_image(image_bytes: bytes) -> Tuple[str, float]:
    """
    Extract raw text and average confidence from an image using dedicated local OCR.
    Prioritizes RapidOCR (PaddleOCR ONNX) and falls back to pytesseract if configured.
    """
    pil_img, np_img = preprocess_image(image_bytes)

    # 1. Try RapidOCR (dedicated local high-performance engine)
    if _rapid_ocr_engine is not None:
        try:
            results, elapse = _rapid_ocr_engine(np_img)
            if results:
                extracted_lines = []
                confidences = []
                for item in results:
                    # item format: [box, text, confidence]
                    text = item[1].strip()
                    conf = float(item[2])
                    if text:
                        extracted_lines.append(text)
                        confidences.append(conf)

                full_text = "\n".join(extracted_lines)
                avg_conf = sum(confidences) / len(confidences) if confidences else 0.80
                return full_text, round(avg_conf, 2)
        except Exception as e:
            logger.warning("RapidOCR extraction encountered error: %s", e)

    # 2. Try pytesseract if Tesseract binary is available
    if settings.TESSERACT_CMD:
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
            data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)
            words = []
            confs = []
            for i in range(len(data["text"])):
                word = data["text"][i].strip()
                conf = float(data["conf"][i])
                if word and conf > 0:
                    words.append(word)
                    confs.append(conf / 100.0)
            text = pytesseract.image_to_string(pil_img)
            avg_conf = sum(confs) / len(confs) if confs else 0.80
            return text.strip(), round(avg_conf, 2)
        except Exception as e:
            logger.warning("pytesseract extraction encountered error: %s", e)

    # 3. Fallback: if no OCR binary worked or text is empty, return empty string
    return "", 0.0
