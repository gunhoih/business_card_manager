"""원본 이미지를 보존하며 OCR 전처리 후보를 생성한다."""

from dataclasses import dataclass
from math import sqrt

import cv2
import numpy as np
from PIL import Image, ImageOps


MAX_ENHANCED_LONG_SIDE = 2200
MAX_ENHANCED_PIXELS = 8_000_000


@dataclass(frozen=True)
class PreScanCandidate:
    name: str
    image: Image.Image
    scale: float


def _scale_for_ocr(width: int, height: int) -> float:
    return min(2.0, MAX_ENHANCED_LONG_SIDE / max(width, height),
               sqrt(MAX_ENHANCED_PIXELS / (width * height)))


def _resize(image: np.ndarray, scale: float, binary: bool = False) -> np.ndarray:
    if scale == 1.0:
        return image
    height, width = image.shape[:2]
    interpolation = (cv2.INTER_AREA if scale < 1 else
                     cv2.INTER_NEAREST if binary else cv2.INTER_CUBIC)
    if binary:
        interpolation = cv2.INTER_NEAREST
    return cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))),
                      interpolation=interpolation)


def prepare_pre_scan_images(image: Image.Image) -> tuple[PreScanCandidate, ...]:
    """Produce original, contrast-enhanced and black/white OCR candidates.

    The source image is never mutated. Only scale changes image coordinates.
    """
    if not isinstance(image, Image.Image):
        raise ValueError("A Pillow image is required.")
    if image.width < 2 or image.height < 2:
        raise ValueError("Image dimensions must be at least 2x2.")

    original = ImageOps.exif_transpose(image).convert("RGB")
    scale = _scale_for_ocr(original.width, original.height)
    original_scale = min(1.0, scale)
    if original_scale < 1.0:
        original = original.resize((max(1, round(original.width * original_scale)),
                                    max(1, round(original.height * original_scale))),
                                   Image.Resampling.LANCZOS)
    pixels = np.asarray(original)
    gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)
    _, binary = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    extra_scale = scale / original_scale
    return (
        PreScanCandidate("original", original, original_scale),
        PreScanCandidate("contrast", Image.fromarray(_resize(contrast, extra_scale)), scale),
        PreScanCandidate("binary", Image.fromarray(_resize(binary, extra_scale, binary=True)), scale),
    )
