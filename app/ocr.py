"""Local CPU OCR. Uploaded images are never sent to Gemini."""

import io
import threading
import warnings
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.schemas import Busy, Unprocessed

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float


class LocalOCR:
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self._engine = None
        self._lock = threading.Lock()

    def read(self, content: bytes) -> OCRResult:
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise Unprocessed("Upload one nonempty image no larger than 5 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as original:
                    if (
                        original.format not in {"PNG", "JPEG", "WEBP"}
                        or getattr(original, "n_frames", 1) != 1
                    ):
                        raise Unprocessed(
                            "Only single-frame PNG, JPEG and WebP images are supported."
                        )
                    if original.width * original.height > MAX_PIXELS:
                        raise Unprocessed(
                            "Image exceeds 16 megapixels. Crop it to the results table."
                        )
                    oriented = ImageOps.exif_transpose(original).convert("RGBA")
                    image = Image.new("RGBA", oriented.size, "white")
                    image.alpha_composite(oriented)
                    image = image.convert("RGB")
                    image.thumbnail((2400, 2400))
                    pixels = np.asarray(image)
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise Unprocessed("The image is invalid or too large to decode safely.") from exc
        if not self._lock.acquire(blocking=False):
            raise Busy("The OCR worker is busy. Please retry shortly.")
        try:
            if self._engine is None:
                from rapidocr_onnxruntime import RapidOCR

                self._engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
            result, _ = self._engine(pixels)
        finally:
            self._lock.release()
        if not result:
            raise Unprocessed("No readable text was found in the image.")
        if any(float(item[2]) < self.threshold for item in result):
            raise Unprocessed(
                "Low-confidence OCR text requires review. Upload a clearer crop or paste the text."
            )
        # Reconstruct rows from bounding boxes, not the OCR detector's incidental ordering.
        cells = sorted(
            result, key=lambda item: (sum(p[1] for p in item[0]) / 4, min(p[0] for p in item[0]))
        )
        rows: list[list] = []
        centers: list[float] = []
        for item in cells:
            box = item[0]
            y = sum(p[1] for p in box) / 4
            height = max(p[1] for p in box) - min(p[1] for p in box)
            if rows and abs(y - centers[-1]) <= max(4, height * 0.5):
                rows[-1].append(item)
            else:
                rows.append([item])
                centers.append(y)
        lines = [
            " ".join(str(item[1]) for item in sorted(row, key=lambda i: min(p[0] for p in i[0])))
            for row in rows
        ]
        text = "\n".join(lines)
        if len(text) > 20000:
            raise Unprocessed("OCR text is too long. Crop the results table.")
        return OCRResult(text=text, confidence=min(float(item[2]) for item in result))
