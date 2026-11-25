"""연락처 목록과 명함 추출 데이터의 CSV 입출력을 담당한다."""

import csv
import io

from backend.card_storage.schema import CONTACT_FIELDS, CSV_FIELDS, FIELD_LABELS, MAX_CSV_SIZE, MAX_CONTACTS
from backend.card_storage.service import filter_new_contacts


def safe_csv_value(value):
    """스프레드시트에서 수식으로 실행될 수 있는 값의 앞을 보호한다."""
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith("'"):
        return "'" + text
    return text


def _restore_csv_value(value):
    """내보낼 때 추가한 보호용 따옴표를 복원한다. 재내보내기 시 중복되지 않는다."""
    text = str(value or "").strip()
    if text.startswith("''") or (text.startswith("'") and text[1:].lstrip().startswith(("=", "+", "-", "@"))):
        return text[1:]
    return text


def _write_csv(columns, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: safe_csv_value(row.get(field, "")) for field in columns})
    return output.getvalue().encode("utf-8-sig")


def export_contacts_csv(contacts):
    return _write_csv(CSV_FIELDS, contacts)


def export_dataset_csv(records):
    """명함 한 장당 한 행을 저장한다. 식별자가 없는 명함도 원문 데이터로 내보낸다."""
    columns = ["source_file", "scan_status", "ocr_status", "reviewed", *CONTACT_FIELDS]
    rows = []
    for record in records:
        values = record.get("fields") or (record.get("ocr") or {}).get("fields") or {}
        ocr_status = "done" if record.get("ocr") else "error" if record.get("ocr_error") else "not_run"
        rows.append({
            "source_file": record.get("name", ""),
            "scan_status": record.get("status", ""),
            "ocr_status": ocr_status,
            "reviewed": "yes" if record.get("reviewed") else "no",
            **{field: values.get(field, "") for field in CONTACT_FIELDS},
        })
    return _write_csv(columns, rows)


def import_contacts_csv(file_bytes):
    """연락처 목록 CSV와 일괄 명함 추출 CSV를 읽는다."""
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
            contact = {field: _restore_csv_value(row.get(field)) for field in CSV_FIELDS}
            if not any(contact[field] for field in CONTACT_FIELDS):
                continue
            contacts.append(contact)
            if len(contacts) > MAX_CONTACTS:
                raise ValueError("한 번에 최대 2,000개의 연락처만 가져올 수 있습니다.")
        return contacts
    except csv.Error as error:
        raise ValueError("CSV 내용을 읽지 못했습니다. 파일 형식을 확인해 주세요.") from error
