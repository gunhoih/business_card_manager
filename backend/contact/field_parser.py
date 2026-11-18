"""기존 연락처 패턴 추출 함수. 정규식은 classifier와 공유한다."""

from backend.classifier.patterns import EMAIL, PHONE, WEBSITE
from backend.contact.csv_service import CONTACT_FIELDS


def extract_contact_candidates(raw_text):
    """기존 OCR 페이지에서 쓰는 간단한 이메일·전화·URL 추출 API."""
    text = str(raw_text or "")
    fields = {key: "" for key in CONTACT_FIELDS}

    email = EMAIL.search(text)
    phone = PHONE.search(text)
    website = WEBSITE.search(text)
    if email:
        fields["email"] = email.group(1).rstrip(". ,;:)")
    if phone:
        fields["phone"] = phone.group(1).strip()
    if website:
        fields["website"] = website.group(1).rstrip(". ,;:)")
    return fields
