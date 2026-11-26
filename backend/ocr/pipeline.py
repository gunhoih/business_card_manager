"""OCR pipeline with non-destructive pre-scan image enhancement.

The original image remains the primary source. Secondary OCR passes may recover
text absent from the original, while their bounding boxes are mapped back to
original image coordinates for the existing Streamlit preview.
"""

import hashlib
import io
import re
from time import monotonic
from dataclasses import asdict, replace

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.classifier.service import build_contact_fields, classify_lines
from backend.contact.field_parser import extract_contact_candidates
from backend.image.pre_scan import prepare_pre_scan_images
from backend.ocr.service import OCRLine, recognize_text

MAX_IMAGE_PIXELS = 12_000_000
MAX_IMAGE_BYTES = 12 * 1024 * 1024
DEFAULT_OCR_TIMEOUT = 60.0


def _restore_coordinates(line: OCRLine, scale: float) -> OCRLine:
    if scale == 1.0:
        return line
    return replace(
        line,
        left=round(line.left / scale),
        top=round(line.top / scale),
        width=max(1, round(line.width / scale)),
        height=max(1, round(line.height / scale)),
    )


def _has_readable_text(line: OCRLine) -> bool:
    visible = [char for char in line.text if not char.isspace()]
    alnum_count = sum(char.isalnum() for char in visible)
    if alnum_count < 2 or line.confidence < 45:
        return False
    return not (len(visible) >= 5 and alnum_count / len(visible) < 0.55)


def _line_score(line: OCRLine) -> float:
    alnum_count = sum(char.isalnum() for char in line.text)
    korean_count = sum("가" <= char <= "힣" for char in line.text)
    phone = bool(re.search(r"\d{2,4}[\s-]?\d{3,4}[\s-]?\d{4}", line.text))
    return line.confidence + 0.35 * min(alnum_count, 60) + min(korean_count, 10) + (8 if phone else 0)


def _overlaps(first: OCRLine, second: OCRLine) -> bool:
    horizontal = max(0, min(first.left + first.width, second.left + second.width) - max(first.left, second.left))
    vertical = max(0, min(first.top + first.height, second.top + second.height) - max(first.top, second.top))
    smallest_area = min(first.width * first.height, second.width * second.height)
    return smallest_area > 0 and horizontal * vertical / smallest_area >= 0.30


def _merge_lines(original: list[OCRLine], additional: list[OCRLine]) -> list[OCRLine]:
    """Preserve reliable lines and add missing content without duplicating boxes."""
    combined = [line for line in original if _has_readable_text(line)]
    for line in additional:
        if not _has_readable_text(line):
            continue
        overlapping = [index for index, existing in enumerate(combined) if _overlaps(existing, line)]
        if not overlapping:
            combined.append(line)
        elif len(overlapping) == 1:
            index = overlapping[0]
            if _line_score(line) > _line_score(combined[index]) + 8:
                combined[index] = line
    return sorted(combined, key=lambda line: (line.top, line.left))


def _recognize_variant(candidate, languages: str, psm: int, timeout: int) -> list[OCRLine]:
    result = recognize_text(candidate.image, languages=languages, psm=psm, timeout=timeout)
    return [_restore_coordinates(line, candidate.scale) for line in result.lines]


def run_ocr_pipeline(image_bytes: bytes, languages: str = "kor+eng", psm: int = 11, *,
                     timeout: float = DEFAULT_OCR_TIMEOUT) -> dict:
    """Read an image, enhance OCR candidates, then classify contact fields.

    timeout은 이미지 한 장의 전체 OCR 예산이다. 보조 인식이 시간 초과되어도
    이미 얻은 결과는 유지한다.
    """
    if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 180:
        raise ValueError("OCR 처리 제한 시간은 1~180초로 지정하세요.")
    deadline = monotonic() + timeout

    def remaining(max_seconds):
        seconds = min(max_seconds, deadline - monotonic())
        if seconds < 0.5:
            raise RuntimeError("OCR 처리 제한 시간에 도달했습니다.")
        return seconds
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("OCR을 실행할 명함 이미지가 없습니다.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("OCR image must be 12MB or smaller.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("이미지는 1,200만 픽셀 이하만 인식할 수 있습니다.")
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError("이미지를 읽을 수 없습니다. 업로드한 이미지를 확인해 주세요.") from error

    variants = prepare_pre_scan_images(image)
    original, contrast, binary = variants

    # 첫 번째 인식에 전체 예산을 소진하지 않도록 하고, 보조 인식 기회를 남긴다.
    examined = ["original"]
    errors = []
    try:
        lines = _recognize_variant(original, languages, psm, timeout=remaining(min(45, timeout * 0.65)))
    except RuntimeError as error:
        # 설치/언어 모델 오류는 반복할 이유가 없다. 시간 초과인 경우만 보조 시도.
        if not any(word in str(error).casefold() for word in ("timeout", "시간", "timed out")):
            raise
        errors.append(str(error))
        lines = []

    # A single-block pass can recover large titles missed by sparse-text mode.
    try:
        contrast_psm = 6 if psm == 11 else psm
        enhanced_lines = _recognize_variant(contrast, languages, contrast_psm, timeout=remaining(30))
        lines = _merge_lines(lines, enhanced_lines)
        examined.append("contrast")
    except RuntimeError as error:
        errors.append(str(error))
        lines = _merge_lines(lines, [])

    # Thresholding is intentionally a fallback: it may destroy thin strokes.
    if len(lines) < 2:
        try:
            threshold_lines = _recognize_variant(binary, languages, psm, timeout=remaining(30))
            lines = _merge_lines(lines, threshold_lines)
            examined.append("binary")
        except RuntimeError as error:
            errors.append(str(error))

    if not lines:
        raise RuntimeError("글자를 인식하지 못했습니다. 스캔 상태와 언어 설정을 확인해 주세요.")

    text = "\n".join(line.text for line in lines)
    rows = classify_lines(lines)
    fields, warnings = build_contact_fields(rows)
    simple_fields = extract_contact_candidates(text)
    for field in ("email", "website"):
        if not fields.get(field) and simple_fields.get(field):
            fields[field] = simple_fields[field]

    return {
        "image_id": hashlib.sha256(image_bytes).hexdigest(),
        "text": text,
        "lines": [asdict(line) for line in lines],
        "languages": languages,
        "psm": psm,
        "candidates": rows,
        "fields": fields,
        "warnings": warnings,
        "pre_scan": {"attempted": examined, "secondary_errors": errors},
    }
