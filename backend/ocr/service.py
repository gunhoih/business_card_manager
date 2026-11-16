"""Tesseract로 명함 텍스트와 줄/좌표 정보를 추출한다."""

from collections import defaultdict
from dataclasses import dataclass
import os
from pathlib import Path
import shutil

import pytesseract
from PIL import Image
from pytesseract import Output, TesseractError, TesseractNotFoundError


ROOT = Path(__file__).resolve().parents[2]
LOCAL_TESSDATA = ROOT / "data" / "ocr" / "tessdata"
SUPPORTED_LANGUAGES = {"eng", "kor", "chi_tra", "chi_sim"}


@dataclass(frozen=True)
class OCRLine:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float


@dataclass(frozen=True)
class OCRResult:
    text: str
    lines: list[OCRLine]
    languages: str


def resolve_tesseract_cmd():
    """PATH 또는 Windows 기본 경로에서 Tesseract 실행 파일을 찾는다."""
    custom = os.getenv("OCR_TESSERACT_CMD", "").strip()
    if custom:
        return custom

    found = shutil.which("tesseract")
    if found:
        return found

    if os.name == "nt":
        candidates = [
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR" / "tesseract.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Tesseract-OCR" / "tesseract.exe",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


def resolve_tessdata_dir():
    """프로젝트에 다운로드한 모델을 우선하고, 없으면 OS 기본 모델을 사용한다."""
    custom = os.getenv("OCR_TESSDATA_DIR", "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    if LOCAL_TESSDATA.is_dir() and any(LOCAL_TESSDATA.glob("*.traineddata")):
        return LOCAL_TESSDATA
    return None


def _configure_engine():
    command = resolve_tesseract_cmd()
    if not command:
        raise RuntimeError(
            "Tesseract 실행 프로그램이 없습니다. Windows에서는 ./setup.ps1을 실행하거나 "
            "winget install --id UB-Mannheim.TesseractOCR -e 명령으로 설치하세요."
        )
    pytesseract.pytesseract.tesseract_cmd = command
    tessdata = resolve_tessdata_dir()
    if tessdata:
        if not tessdata.is_dir():
            raise RuntimeError(f"OCR 언어 데이터 폴더가 없습니다: {tessdata}")
        return f'--tessdata-dir "{tessdata}"'
    return ""


def available_languages():
    """현재 Tesseract 엔진에 로드 가능한 언어 목록을 반환한다."""
    config = _configure_engine()
    try:
        return sorted(pytesseract.get_languages(config=config))
    except (TesseractNotFoundError, TesseractError, OSError) as error:
        raise RuntimeError("OCR 엔진 또는 언어 데이터 목록을 읽지 못했습니다.") from error


def group_ocr_lines(data):
    """Tesseract block/par/line 번호와 단어 좌표로 행을 구성한다."""
    groups = defaultdict(list)
    count = len(data.get("text", []))

    for i in range(count):
        word = str(data["text"][i] or "").strip()
        if not word:
            continue
        try:
            left = int(data["left"][i])
            top = int(data["top"][i])
            width = int(data["width"][i])
            height = int(data["height"][i])
            confidence = float(data["conf"][i])
            key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
        except (ValueError, TypeError, IndexError, KeyError):
            continue
        if width <= 0 or height <= 0 or confidence < 0:
            continue
        groups[key].append((left, top, width, height, confidence, word))

    lines = []
    for words in groups.values():
        words.sort(key=lambda word: word[0])
        left = min(word[0] for word in words)
        top = min(word[1] for word in words)
        right = max(word[0] + word[2] for word in words)
        bottom = max(word[1] + word[3] for word in words)
        confidence = round(sum(word[4] for word in words) / len(words), 1)
        lines.append(OCRLine(" ".join(word[5] for word in words), left, top, right - left, bottom - top, confidence))

    # 흩어진 블록(PSM 11)은 기존 번호보다 이미지 위치순으로 보여준다.
    lines.sort(key=lambda line: (line.top, line.left))
    return lines


def recognize_text(image: Image.Image, languages="kor+eng", psm=11, timeout=45):
    """Pillow 이미지에서 OCR 결과를 반환한다. 외부 AI API는 사용하지 않는다."""
    if not isinstance(image, Image.Image):
        raise ValueError("Pillow 이미지가 필요합니다.")

    selected = languages.split("+")
    if not selected or any(language not in SUPPORTED_LANGUAGES for language in selected):
        raise ValueError("지원하지 않는 OCR 언어입니다.")
    if psm not in (3, 6, 11):
        raise ValueError("지원하지 않는 페이지 분석 모드입니다.")

    config = _configure_engine()
    try:
        installed = set(pytesseract.get_languages(config=config))
        missing = set(selected) - installed
        if missing:
            raise RuntimeError(
                f"OCR 언어 데이터가 부족합니다: {', '.join(sorted(missing))}. "
                "로컬에서 ./setup.ps1 또는 uv run python scripts/setup_ocr.py를 실행하세요."
            )
        data = pytesseract.image_to_data(
            image.convert("RGB"),
            lang=languages,
            config=f"--oem 1 --psm {psm} {config}".strip(),
            output_type=Output.DICT,
            timeout=timeout,
        )
    except (TesseractNotFoundError, TesseractError, RuntimeError, OSError) as error:
        if isinstance(error, RuntimeError):
            raise
        raise RuntimeError("Tesseract OCR 실행에 실패했습니다. 설치 상태와 이미지를 확인하세요.") from error

    lines = group_ocr_lines(data)
    return OCRResult("\n".join(line.text for line in lines), lines, languages)
