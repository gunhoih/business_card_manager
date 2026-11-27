"""공통 OCR 파이프라인: 한국어 RapidOCR 우선, 명시적 Tesseract 선택도 유지한다."""

from dataclasses import asdict, replace
import hashlib
import io
from time import monotonic

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.classifier.service import build_contact_fields, classify_lines
from backend.image.pre_scan import prepare_pre_scan_images
from backend.ocr.engine import select_engine
from backend.ocr.english_review import review_english, review_warnings, _missing_fields
from backend.ocr.rapid_service import recognize_rapid

MAX_IMAGE_PIXELS = 12_000_000
MAX_IMAGE_BYTES = 12 * 1024 * 1024
DEFAULT_OCR_TIMEOUT = 60.0


def _open_image(image_bytes):
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("OCR을 실행할 명함 이미지가 없습니다.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("명함 이미지는 12MB 이하만 인식할 수 있습니다.")
    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("이미지는 1,200만 픽셀 이하만 인식할 수 있습니다.")
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError("이미지를 읽을 수 없습니다.") from error
    if min(image.size) < 2:
        raise ValueError("이미지 크기가 너무 작습니다.")
    return image


def _restore(line, source_size, processed_size):
    sx = source_size[0] / processed_size[0]
    sy = source_size[1] / processed_size[1]
    x = max(0, min(source_size[0] - 1, round(line.left * sx)))
    y = max(0, min(source_size[1] - 1, round(line.top * sy)))
    right = max(x + 1, min(source_size[0], round((line.left + line.width) * sx)))
    bottom = max(y + 1, min(source_size[1], round((line.top + line.height) * sy)))
    return replace(line, left=x, top=y, width=right - x, height=bottom - y)


def _readable(line):
    chars = [char for char in line.text if not char.isspace()]
    return (line.confidence >= 25 and sum(char.isalnum() for char in chars) >= 2
            and sum(char.isalnum() for char in chars) / max(1, len(chars)) >= 0.45)


def _intersection(first, second):
    w = max(0, min(first.left + first.width, second.left + second.width) - max(first.left, second.left))
    h = max(0, min(first.top + first.height, second.top + second.height) - max(first.top, second.top))
    return w * h


def _merge_lines(original, additional):
    """원본의 확실한 줄을 유지한다. 겹친 여러 줄을 한 줄로 덮어쓰지 않는다."""
    combined = [line for line in original if _readable(line)]
    for line in additional:
        if not _readable(line):
            continue
        area = line.width * line.height
        overlaps = [i for i, old in enumerate(combined)
                    if _intersection(old, line) >= 0.45 * min(area, old.width * old.height)]
        if not overlaps:
            combined.append(line)
        elif len(overlaps) == 1:
            i = overlaps[0]
            old = combined[i]
            union = area + old.width * old.height - _intersection(old, line)
            similar_box = union > 0 and _intersection(old, line) / union >= 0.45
            if similar_box and line.confidence >= old.confidence + 12:
                # 짧아진 재인식 결과가 원래의 긴 이름/이메일 등을 잘라먹지 않게 한다.
                if len(line.text.replace(" ", "")) >= 0.8 * len(old.text.replace(" ", "")):
                    combined[i] = line
    return sorted(combined, key=lambda line: (line.top, line.left))


def _classify(lines):
    rows = classify_lines(lines)
    fields, warnings = build_contact_fields(rows)
    if not fields.get("name"):
        candidates = sorted((row for row in rows if row.get("name_rank")), key=lambda row: row["name_rank"])
        if candidates:
            warnings.append("이름 확인 필요: " + ", ".join(row["name_candidate"] for row in candidates[:3]))
        else:
            warnings.append("이름을 자동으로 찾지 못했습니다. 명함 원본을 확인하세요.")
    return rows, fields, warnings


def _primary_image(image):
    long_side = max(image.size)
    scale = min(1.7, 1800 / long_side)
    if 0.99 <= scale <= 1.01:
        return image
    return image.resize(tuple(max(1, round(x * scale)) for x in image.size), Image.Resampling.LANCZOS)


def _run_rapid_pipeline(image_bytes, languages, psm, timeout):
    deadline = monotonic() + timeout
    image = _open_image(image_bytes)
    attempted, errors = [], []

    def read_variant(variant, label):
        remaining = deadline - monotonic()
        if remaining < 0.5:
            raise RuntimeError("OCR 추가 인식 시간 예산을 소진했습니다.")
        attempted.append(label)
        result = recognize_rapid(variant, timeout=remaining)
        return [_restore(line, image.size, variant.size) for line in result.lines if _readable(line)]

    # 1차: 색상 원본을 사용하고 작은 명함은 제한적으로 확대한다.
    lines = _merge_lines([], read_variant(_primary_image(image), "rapid_original"))
    rows, fields, warnings = _classify(lines)
    # 2차: 이름 또는 연락수단이 누락된 경우에만 대비 개선 이미지로 재검출한다.
    if (not fields.get("name") or not (fields.get("phone") or fields.get("email"))
            or len(lines) < 3 or any(_missing_fields(line.text) for line in lines)) and deadline - monotonic() >= 2:
        try:
            contrast = prepare_pre_scan_images(image)[1].image
            lines = _merge_lines(lines, read_variant(_primary_image(contrast), "rapid_contrast"))
            rows, fields, warnings = _classify(lines)
        except RuntimeError as error:
            errors.append(str(error))

    # 3차: 판별이 애매한 이름 후보 한 곳만 확대해 문자 인식을 다시 실행한다.
    # 이름 후보가 전혀 없으면 추측 영역을 만들지 않는다.
    ranked = sorted((row for row in rows if row.get("name_rank") and row.get("ocr_confidence") is not None),
                    key=lambda row: row["name_rank"])
    if not fields.get("name") and ranked and deadline - monotonic() >= 2:
        row = ranked[0]
        line_index = row.get("source_line")
        if isinstance(line_index, int) and 0 <= line_index < len(lines):
            old = lines[line_index]
            # 줄에 다른 직책/정보가 같이 있는 경우 강제 단일줄 교체를 하지 않는다.
            if old.text.strip() == row.get("text", "").strip():
                try:
                    pad = max(3, round(old.height * 0.12))
                    box = (max(0, old.left - pad), max(0, old.top - pad),
                           min(image.width, old.left + old.width + pad), min(image.height, old.top + old.height + pad))
                    crop = image.crop(box)
                    crop = _primary_image(crop)
                    attempted.append("rapid_name_crop")
                    result = recognize_rapid(crop, timeout=max(0.1, deadline - monotonic()), line_only=True)
                    if len(result.lines) == 1:
                        new = result.lines[0]
                        if new.confidence >= max(55, old.confidence + 10) and _readable(new):
                            from backend.classifier.korean_names import normalize_name
                            if normalize_name(new.text):
                                lines[line_index] = replace(old, text=new.text, confidence=new.confidence)
                                rows, fields, warnings = _classify(lines)
                except RuntimeError as error:
                    errors.append(str(error))
    if not lines:
        raise RuntimeError("글자를 인식하지 못했습니다. 명함의 보정 영역과 화질을 확인하세요.")
    # 한글/영문 기본 인식이 끝난 뒤 필요한 영문·숫자 줄만 보조 모델로 검사한다.
    # 이름/주소 등 한국어 문맥은 그대로 보호한다.
    lines, english_checks, english_errors = review_english(image, lines, recognize_rapid, deadline)
    if english_checks or english_errors:
        attempted.append("rapid_english_crops")
    errors.extend(english_errors)
    rows, fields, warnings = _classify(lines)
    warnings.extend(review_warnings(english_checks))
    if english_errors:
        warnings.append("영문 보조 인식을 일부 완료하지 못했습니다. 기본 인식 결과를 확인하세요.")
    return {
        "image_id": hashlib.sha256(image_bytes).hexdigest(),
        "text": "\n".join(line.text for line in lines),
        "lines": [asdict(line) for line in lines],
        "languages": languages,
        "psm": psm,
        "engine": "rapidocr",
        "english_checks": english_checks,
        "candidates": rows,
        "fields": fields,
        "warnings": warnings,
        "pre_scan": {"attempted": attempted, "secondary_errors": errors},
    }


def run_ocr_pipeline(image_bytes, languages="kor+eng", psm=11, *, timeout=DEFAULT_OCR_TIMEOUT):
    if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 180:
        raise ValueError("OCR 처리 제한 시간은 1~180초로 지정하세요.")
    if psm not in (3, 6, 11):
        raise ValueError("지원하지 않는 페이지 분석 모드입니다.")
    if select_engine(languages) == "tesseract":
        from backend.ocr.tesseract_pipeline import run_ocr_pipeline as run_tesseract
        report = run_tesseract(image_bytes, languages=languages, psm=psm, timeout=timeout)
        report["engine"] = "tesseract"
        return report
    return _run_rapid_pipeline(image_bytes, languages, psm, timeout)
