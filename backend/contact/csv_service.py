"""연락처 CSV 가져오기와 내보내기."""

import csv
import io

CONTACT_FIELDS = [
    "name",
    "company",
    "department",
    "position",
    "phone",
    "email",
    "website",
    "memo",
]

CSV_FIELDS = CONTACT_FIELDS + ["created_at"]

FIELD_LABELS = {
    "name": "이름",
    "company": "회사·소속",
    "department": "부서",
    "position": "직책",
    "phone": "전화번호",
    "email": "이메일",
    "website": "웹사이트",
    "memo": "메모",
}

MAX_CSV_SIZE = 2 * 1024 * 1024
MAX_CONTACTS = 2000


def safe_csv_value(value):
    """CSV 셀을 Excel에서 수식으로 실행하지 않도록 처리."""
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def export_contacts_csv(contacts):
    """연락처 목록을 Excel에서 열 수 있는 UTF-8 BOM CSV로 반환."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()

    for contact in contacts:
        row = {field: safe_csv_value(contact.get(field, "")) for field in CSV_FIELDS}
        writer.writerow(row)

    return output.getvalue().encode("utf-8-sig")


def import_contacts_csv(file_bytes):
    """CSV 내용을 읽어 연락처 딕셔너리 리스트로 반환."""
    if not isinstance(file_bytes, bytes):
        raise ValueError("CSV 파일을 다시 선택해 주세요.")
    if len(file_bytes) > MAX_CSV_SIZE:
        raise ValueError("CSV 파일은 2MB 이하만 가져올 수 있습니다.")

    try:
        content = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV 파일을 UTF-8 형식으로 저장해 주세요.") from error

    try:
        reader = csv.DictReader(io.StringIO(content, newline=""))
        headers = reader.fieldnames

        if not headers or not set(CONTACT_FIELDS).intersection(headers):
            raise ValueError("연락처 CSV 형식이 아닙니다. 앱에서 받은 CSV 양식을 사용해 주세요.")
        if len(headers) != len(set(headers)):
            raise ValueError("CSV 헤더에 중복된 열 이름이 있습니다.")

        contacts = []
        for row in reader:
            if None in row:
                raise ValueError("CSV 열 개수가 헤더와 일치하지 않습니다.")

            contact = {field: (row.get(field) or "").strip() for field in CSV_FIELDS}
            if not any(contact[field] for field in CONTACT_FIELDS):
                continue

            contacts.append(contact)
            if len(contacts) > MAX_CONTACTS:
                raise ValueError("한 번에 최대 2,000개의 연락처만 가져올 수 있습니다.")

        return contacts
    except csv.Error as error:
        raise ValueError("CSV 내용을 읽지 못했습니다. 파일 형식을 확인해 주세요.") from error


def filter_new_contacts(imported_contacts, current_contacts):
    """이미 저장된 연락처와 내용이 완전히 같은 행만 제외."""
    def get_key(contact):
        return tuple(str(contact.get(field) or "").strip() for field in CONTACT_FIELDS)

    existing = {get_key(contact) for contact in current_contacts}
    new_contacts = []
    skipped_count = 0

    for contact in imported_contacts:
        key = get_key(contact)
        if key in existing:
            skipped_count += 1
        else:
            new_contacts.append(contact)
            existing.add(key)

    return new_contacts, skipped_count
