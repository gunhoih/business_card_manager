"""로컬 OCR + 텍스트 분류를 한 번에 실행하는 백엔드 파이프라인.

OCR 엔진(Tesseract)과 화면(Streamlit)을 분리한다.

    결과 = run_ocr_pipeline(명함_이미지_바이트)
    print(결과["text"])
    print(결과["fields"])

텍스트를 인식한 다음 이미 묶인 OCR 줄과 좌표를 분류기에 넘긴다.
API 키, 외부 서버, 언어 모델 추론 API는 사용하지 않는다.
"""

import hashlib
import io
from dataclasses import asdict

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.classifier.service import build_contact_fields, classify_lines
from backend.contact.field_parser import extract_contact_candidates
from backend.ocr.service import recognize_text

MAX_IMAGE_PIXELS = 12_000_000
MAX_IMAGE_BYTES = 12 * 1024 * 1024


def run_ocr_pipeline(image_bytes: bytes, languages: str = "kor+eng", psm: int = 11) -> dict:
    """이미지 -> Tesseract OCR -> 줄별 자동 분류 -> 연락처 필드 후보.

    반환되는 fields는 자동 추출 *후보*이므로 최종 저장 전에 UI에서 수정 가능하다.
    분류 점수와 Tesseract 신뢰도는 서로 다른 수치이며 정확도가 아니다.
    """
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

    # 실제 Tesseract 호출. 엔진/언어 모델이 없다면 RuntimeError가 발생한다.
    result = recognize_text(image, languages=languages, psm=psm)
    if not result.text.strip():
        raise RuntimeError("글자를 인식하지 못했습니다. 스캔 상태와 언어 설정을 확인해 주세요.")

    # OCR이 돌려준 줄의 좌표, 높이, 신뢰도를 그대로 전달한다.
    rows = classify_lines(result.lines)
    fields, warnings = build_contact_fields(rows)

    # 분류기가 전화/Fax 라벨까지 이미 판별했으므로, 전화번호를 다시 단순
    # 정규식으로 추출하면 'Fax: 02-...'가 phone에도 복제될 수 있다.
    # 연락처 패턴은 다른 문자열에서만 보완하고 전화번호는 분류기 결과를 신뢰한다.
    simple_fields = extract_contact_candidates(result.text)
    for field in ("email", "website"):
        if not fields.get(field) and simple_fields.get(field):
            fields[field] = simple_fields[field]

    return {
        "image_id": hashlib.sha256(image_bytes).hexdigest(),
        "text": result.text,
        "lines": [asdict(line) for line in result.lines],
        "languages": result.languages,
        "psm": psm,
        "candidates": rows,
        "fields": fields,
        "warnings": warnings,
    }
