"""기본 OCR 엔진 선택. 한자 전용 요청은 기존 Tesseract로 처리한다."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


def select_engine(languages="kor+eng"):
    mode = os.getenv("OCR_ENGINE", "rapidocr").strip().lower()
    if mode not in ("rapidocr", "tesseract"):
        raise ValueError("OCR_ENGINE은 rapidocr 또는 tesseract로 지정하세요.")
    selected = set(languages.split("+"))
    if not selected or not selected <= {"kor", "eng", "chi_tra", "chi_sim"}:
        raise ValueError("지원하지 않는 OCR 언어입니다.")
    # 한국어 모델이 모든 한자를 지원하는 것은 아니므로 기존 한자 선택 기능을 보존한다.
    if selected & {"chi_tra", "chi_sim"} or mode == "tesseract":
        return "tesseract"
    return "rapidocr"


def engine_label(languages="kor+eng"):
    return "RapidOCR · PP-OCRv5 Korean + English" if select_engine(languages) == "rapidocr" else "Tesseract"


def check_ocr_ready(languages="kor+eng"):
    if select_engine(languages) == "rapidocr":
        from backend.ocr.rapid_service import check_rapidocr
        return check_rapidocr()
    from backend.ocr.service import available_languages
    missing = set(languages.split("+")) - set(available_languages())
    if missing:
        raise RuntimeError("Tesseract 언어 모델이 없습니다: " + ", ".join(sorted(missing)))
    return "Tesseract · " + languages
