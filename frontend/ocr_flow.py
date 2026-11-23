"""OCR 파이프라인 결과를 Streamlit 세션과 안전하게 연결한다.

새 OCR 결과는 자동 항목만 갱신하고, 사람이 편집한 항목은 보존한다.
"""

import streamlit as st

from backend.ocr.pipeline import run_ocr_pipeline
from frontend.state import apply_auto_fields, next_ocr_revision


def recognize_and_apply(image_bytes: bytes, languages: str = "kor+eng", psm: int = 11) -> dict:
    """OCR 인식 성공 후에만 연락처 필드·OCR 미리보기 정보를 변경한다."""
    result = run_ocr_pipeline(image_bytes, languages=languages, psm=psm)

    # 바로 이전에 OCR로 채운 필드는 새 결과로 교체 가능하다.
    # 사용자가 직접 수정(빈 값으로 수정 포함)한 필드는 보호한다.
    apply_auto_fields(result["fields"])
    st.session_state["scan_raw_text"] = result["text"]

    st.session_state["ocr_preview"] = {
        "image_id": result["image_id"],
        "lines": result["lines"],
        "languages": result["languages"],
        "psm": result["psm"],
        "source_text": result["text"],
        "revision": next_ocr_revision(),
    }
    return result
