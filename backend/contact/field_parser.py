"""AI 없이 OCR 원문에서 명확한 연락처 패턴만 추출한다."""

import re

from backend.contact.csv_service import CONTACT_FIELDS

EMAIL = re.compile(r"(?<![\w.@])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.@])")
PHONE = re.compile(r"(?<!\d)((?:\+82[\s.-]?(?:0)?|0)(?:1[016789]|2|[3-6][1-5])[\s.-]?\d{3,4}[\s.-]?\d{4})(?!\d)")
WEBSITE = re.compile(r"(?<!\w)(https?://[^\s,;<>]+|www\.[\w.-]+\.[A-Za-z]{2,}(?:/[^\s,;<>]*)?)", re.IGNORECASE)


def extract_contact_candidates(raw_text):
    """이름·직책·회사명은 추측하지 않고 사용자가 입력하도록 남겨둔다."""
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
