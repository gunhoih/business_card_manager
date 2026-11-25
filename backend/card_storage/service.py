"""전화번호 또는 이메일이 일치하는 연락처를 찾아 등록·갱신한다.

자동 저장에서 빈 값은 기존 정보를 지우지 않는다. 식별 정보가 없거나
서로 다른 연락처가 동시에 일치하면 목록에 저장하지 않고 검토 대상으로 남긴다.
Streamlit 세션이나 파일 시스템에 의존하지 않는다.
"""

from collections import defaultdict
from datetime import datetime
import re
import unicodedata
from uuid import uuid4

from backend.card_storage.schema import CONTACT_FIELDS, MAX_CONTACTS


def normalize_phone(value):
    """구분 기호를 제거하고 한국 국제번호를 국내 번호와 동일하게 비교한다."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if text.startswith("'+"):
        text = text[1:]
    if not re.fullmatch(r"\+?[0-9().\s-]+", text):
        return ""
    digits = re.sub(r"[^0-9]", "", text)
    international = text.startswith("+") or digits.startswith("00")
    if digits.startswith("00") and not text.startswith("+"):
        digits = digits[2:]
    if not 7 <= len(digits) <= 15:
        return ""
    if international:
        if digits.startswith("82"):
            local = "0" + digits[2:].lstrip("0")
            return local if 7 <= len(local) <= 15 else ""
        return "+" + digits
    return digits


def normalize_email(value):
    """공백과 대소문자 차이는 무시하되 이메일 형식이 아니면 식별에 쓰지 않는다."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    if re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>.]+(?:\.[^\s@,;<>.]+)+", text):
        return text
    return ""


def clean_fields(values):
    return {field: str(values.get(field) or "").strip() for field in CONTACT_FIELDS}


def identity_keys(values):
    """이름, 회사, 이미지 파일명, 팩스는 연락처 일치 판정에 쓰지 않는다."""
    keys = set()
    phone = normalize_phone(values.get("phone"))
    email = normalize_email(values.get("email"))
    if phone:
        keys.add(("phone", phone))
    if email:
        keys.add(("email", email))
    return keys


def invalid_identity_fields(values):
    invalid = []
    if values.get("phone") and not normalize_phone(values["phone"]):
        invalid.append("전화번호")
    if values.get("email") and not normalize_email(values["email"]):
        invalid.append("이메일")
    return invalid


def _make_index(contacts):
    index = defaultdict(set)
    for row_index, contact in enumerate(contacts):
        for key in identity_keys(contact):
            index[key].add(row_index)
    return index


def _matches(index, keys):
    matched = set()
    for key in keys:
        matched.update(index.get(key, ()))
    return matched


def _save_one(contacts, incoming, index, max_contacts):
    fields = clean_fields(incoming)
    if not any(fields.values()):
        return "empty", None, "저장할 내용이 없습니다."

    invalid = invalid_identity_fields(fields)
    if invalid:
        return "invalid_identity", None, "형식을 확인하세요: " + ", ".join(invalid)

    keys = identity_keys(fields)
    if not keys:
        return "missing_identity", None, "전화번호 또는 이메일이 필요합니다."

    matched = _matches(index, keys)
    if len(matched) > 1:
        return "conflicts", None, "전화번호·이메일이 여러 기존 연락처와 일치합니다."

    if not matched:
        if len(contacts) >= max_contacts:
            return "full", None, "연락처 목록 한도를 초과했습니다."
        contact = dict(fields)
        contact["id"] = str(uuid4())
        contact["created_at"] = str(incoming.get("created_at") or datetime.now().isoformat(timespec="seconds"))
        row_index = len(contacts)
        contacts.append(contact)
        for key in keys:
            index[key].add(row_index)
        return "added", contact, ""

    row_index = next(iter(matched))
    contact = contacts[row_index]
    old_keys = identity_keys(contact)
    updated = clean_fields(contact)
    for field, value in fields.items():
        if not value:
            continue
        # 식별자는 표기만 다른 경우 기존 저장값을 유지한다.
        if field == "phone" and normalize_phone(value) == normalize_phone(updated[field]):
            continue
        if field == "email" and normalize_email(value) == normalize_email(updated[field]):
            continue
        updated[field] = value

    if updated == clean_fields(contact):
        return "unchanged", contact, ""

    contact.update(updated)
    for key in old_keys:
        index[key].discard(row_index)
    for key in identity_keys(contact):
        index[key].add(row_index)
    return "updated", contact, ""


def save_contact(contacts, incoming, max_contacts=MAX_CONTACTS):
    """한 명함을 등록하거나 갱신하고 (상태, 연락처, 사유)를 반환한다."""
    return _save_one(contacts, incoming, _make_index(contacts), max_contacts)


def save_contacts(contacts, incoming_rows, max_contacts=MAX_CONTACTS):
    """일괄 스캔, 개별 스캔, CSV 가져오기가 모두 사용하는 저장 진입점."""
    result = {key: 0 for key in (
        "added", "updated", "unchanged", "conflicts", "missing_identity",
        "invalid_identity", "empty", "full",
    )}
    result["issues"] = []
    index = _make_index(contacts)
    for row_number, incoming in enumerate(incoming_rows, start=1):
        status, _, reason = _save_one(contacts, incoming, index, max_contacts)
        result[status] += 1
        if reason:
            result["issues"].append({
                "row": row_number,
                "source": str(incoming.get("source_file") or ""),
                "reason": reason,
            })
    return result


def replace_contact(contacts, contact_id, values):
    """사용자가 목록에서 직접 선택한 연락처를 수정한다. 명시적 빈 값은 허용한다."""
    selected = next((item for item in contacts if item.get("id") == contact_id), None)
    if selected is None:
        return False
    fields = clean_fields(values)
    if not any(fields.values()):
        raise ValueError("모든 연락처 정보를 비울 수는 없습니다.")
    invalid = invalid_identity_fields(fields)
    if invalid:
        raise ValueError("형식을 확인하세요: " + ", ".join(invalid))

    # 이미 등록된 공유 번호 때문에 다른 항목의 직접 수정까지 막지 않는다.
    new_keys = identity_keys(fields) - identity_keys(selected)
    if any(new_keys & identity_keys(item) for item in contacts if item is not selected):
        raise ValueError("변경한 전화번호 또는 이메일이 다른 연락처에 등록되어 있습니다.")
    selected.update(fields)
    return True


def delete_contact(contacts, contact_id):
    """목록에서 지정한 연락처만 삭제한다."""
    for index, contact in enumerate(contacts):
        if contact.get("id") == contact_id:
            del contacts[index]
            return True
    return False


def filter_new_contacts(imported_contacts, current_contacts):
    """기존 호출부 호환용. 신규 추가만 필요한 경우에도 같은 식별 기준을 사용한다."""
    contacts = [dict(item) for item in current_contacts]
    index = _make_index(contacts)
    new_contacts = []
    for row in imported_contacts:
        fields = clean_fields(row)
        keys = identity_keys(fields)
        if not keys or invalid_identity_fields(fields) or _matches(index, keys):
            continue
        new_contacts.append(row)
        row_index = len(contacts)
        contacts.append(dict(row))
        for key in keys:
            index[key].add(row_index)
    return new_contacts, len(imported_contacts) - len(new_contacts)
