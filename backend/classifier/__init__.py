"""OCR 텍스트를 명함의 연락처 필드로 분류하는 로컬 규칙 엔진."""

from .service import classify_lines, classify_text, build_contact_fields

__all__ = ["classify_lines", "classify_text", "build_contact_fields"]
