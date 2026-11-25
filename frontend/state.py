"""명함 스캔·OCR·연락처 편집 상태를 한곳에서 관리한다.

중요 원칙:
- OCR이 자동으로 채운 값은 다음 인식에서 갱신할 수 있다.
- 사용자가 직접 수정·확인한 값은 다음 OCR에서 덮어쓰지 않는다.
- 스캔 대상이 바뀌면 이전 OCR 좌표·텍스트·자동 후보를 폐기한다.
"""

import streamlit as st

from backend.card_storage.schema import CONTACT_FIELDS
from backend.card_storage.service import save_contact, replace_contact, delete_contact as remove_contact


OCR_TEMP_KEYS = (
    "ocr_preview", "classifier_source_key", "classifier_input", "classifier_rows",
    "classifier_analyzed_text", "classifier_used_ocr_geometry", "classifier_mode",
    "classifier_last_result",
)


def _current_fields():
    return {
        field: str(st.session_state.get(f"scan_{field}") or "")
        for field in CONTACT_FIELDS
    }


def _manual_fields():
    """직접 수정한 입력값을 직전 프로그램 작성값과 비교해 감지한다.

    수정값이 빈 문자열이라도 수동 입력으로 인정한다.
    저장된 출처 정보가 없는 기존 세션은 기존의 비어 있지 않은 값을 보호한다.
    """
    current = _current_fields()
    previous = st.session_state.get("scan_last_written_fields")
    manual = set(st.session_state.get("scan_manual_fields", []))

    if previous is None:
        for field, value in current.items():
            if value.strip():
                manual.add(field)
    else:
        for field, value in current.items():
            if value != previous.get(field, ""):
                manual.add(field)

    return manual


def mark_field_manual(field):
    """사용자가 연락처 입력 위젯을 직접 편집했을 때 호출한다."""
    if field not in CONTACT_FIELDS:
        return
    manual = _manual_fields()
    manual.add(field)
    st.session_state["scan_manual_fields"] = sorted(manual)


def apply_auto_fields(suggestions):
    """새 OCR 후보를 적용한다. 수동 항목은 보존하고 이전 자동값은 교체한다.

    새 OCR에서 특정 항목이 사라지면 이전 자동 입력도 비운다.
    사용자가 직접 비운 필드 역시 보호한다.
    """
    manual = _manual_fields()
    for field in CONTACT_FIELDS:
        if field not in manual:
            st.session_state[f"scan_{field}"] = str(suggestions.get(field) or "").strip()

    st.session_state["scan_manual_fields"] = sorted(manual)
    st.session_state["scan_last_written_fields"] = _current_fields()


def apply_reviewed_fields(fields):
    """분류 화면의 '연락처에 반영'은 사용자의 명시적 확정으로 취급한다.

    제외된 후보는 기존 자동값에서 삭제하되, 직접 편집한 값은 지우지 않는다.
    """
    manual = _manual_fields()
    for field in CONTACT_FIELDS:
        value = str(fields.get(field) or "").strip()
        if value:
            st.session_state[f"scan_{field}"] = value
            manual.add(field)
        elif field not in manual:
            st.session_state[f"scan_{field}"] = ""

    st.session_state["scan_manual_fields"] = sorted(manual)
    st.session_state["scan_last_written_fields"] = _current_fields()


def invalidate_ocr_context(preserve_manual=True):
    """새 사진·보정영역에서는 옛 OCR 결과를 제거한다.

    보정영역만 달라졌다면 사용자가 직접 입력한 연락처만 유지한다.
    아예 다른 사진을 올리거나 이미지를 지우면 모두 초기화한다.
    """
    manual = _manual_fields() if preserve_manual else set()
    for field in CONTACT_FIELDS:
        if field not in manual:
            st.session_state[f"scan_{field}"] = ""

    st.session_state["scan_raw_text"] = ""
    for key in OCR_TEMP_KEYS:
        st.session_state.pop(key, None)
    st.session_state["scan_manual_fields"] = sorted(manual)
    st.session_state["scan_last_written_fields"] = _current_fields()


def next_ocr_revision():
    """재인식 횟수를 단조 증가시켜 분류 페이지가 새 분석으로 갱신되게 한다."""
    count = int(st.session_state.get("ocr_revision_counter", 0)) + 1
    st.session_state["ocr_revision_counter"] = count
    return count


def init_state():
    if "contacts" not in st.session_state:
        st.session_state.contacts = []

    if "scan_image_bytes" not in st.session_state:
        st.session_state.scan_image_bytes = None
        st.session_state.scan_image_name = ""
        st.session_state.scan_image_id = ""
        st.session_state.scan_points = []
        st.session_state.scan_last_click = None
        st.session_state.scan_widget_version = 0
        st.session_state.scan_upload_version = 0
        st.session_state.scan_result_bytes = None
        st.session_state.scan_result_mode = ""
        st.session_state.scan_raw_text = ""

    if "scan_result_mode" not in st.session_state:
        st.session_state.scan_result_mode = ""

    for field in CONTACT_FIELDS:
        key = f"scan_{field}"
        if key not in st.session_state:
            st.session_state[key] = ""

    if "scan_manual_fields" not in st.session_state:
        st.session_state["scan_manual_fields"] = []
    # 기존 세션의 값이 자동인지 수동인지 확인되지 않을 경우 첫 OCR에서 보호한다.
    # snapshot 자체는 실제 후보 적용 또는 OCR 무효화 때 처음 만든다.


def clear_scan_result():
    invalidate_ocr_context(preserve_manual=True)
    st.session_state.scan_result_bytes = None
    st.session_state.scan_result_mode = ""


def set_scan_result(image_bytes, mode):
    """보정 결과를 교체할 때만 이전 OCR·자동 분류를 무효화한다."""
    if st.session_state.get("scan_result_bytes") != image_bytes:
        invalidate_ocr_context(preserve_manual=True)
    st.session_state.scan_result_bytes = image_bytes
    st.session_state.scan_result_mode = mode


def reset_scan_points():
    st.session_state.scan_points = []
    st.session_state.scan_last_click = None
    st.session_state.scan_widget_version += 1
    clear_scan_result()


def set_scan_image(image_bytes, file_name, image_id):
    if st.session_state.scan_image_id == image_id:
        return

    st.session_state.scan_image_bytes = image_bytes
    st.session_state.scan_image_name = file_name
    st.session_state.scan_image_id = image_id
    reset_scan_points()
    invalidate_ocr_context(preserve_manual=False)


def clear_scan_image():
    st.session_state.scan_image_bytes = None
    st.session_state.scan_image_name = ""
    st.session_state.scan_image_id = ""
    st.session_state.scan_upload_version += 1
    reset_scan_points()
    invalidate_ocr_context(preserve_manual=False)


def set_extraction_result(raw_text, fields):
    """기존 호환용 API: 원문과 자동 후보를 반영한다."""
    st.session_state["scan_raw_text"] = raw_text or ""
    apply_auto_fields(fields)


def add_contact(contact):
    """기존 호출부 호환용. 연락처 저장 기준은 card_storage에서 관리한다."""
    status, item, reason = save_contact(st.session_state.setdefault("contacts", []), contact)
    if item is None:
        raise ValueError(reason)
    return item


def update_contact(contact_id, values):
    return replace_contact(st.session_state.contacts, contact_id, values)


def delete_contact(contact_id):
    return remove_contact(st.session_state.contacts, contact_id)
