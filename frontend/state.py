from datetime import datetime
from uuid import uuid4

import streamlit as st

from backend.contact.csv_service import CONTACT_FIELDS


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


def clear_scan_result():
    st.session_state.scan_result_bytes = None
    st.session_state.scan_result_mode = ""


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
    st.session_state.scan_raw_text = ""

    # 새 명함을 불러오면 이전 카드의 추출 정보를 비운다.
    for field in CONTACT_FIELDS:
        st.session_state[f"scan_{field}"] = ""


def clear_scan_image():
    st.session_state.scan_image_bytes = None
    st.session_state.scan_image_name = ""
    st.session_state.scan_image_id = ""
    st.session_state.scan_upload_version += 1
    reset_scan_points()
    st.session_state.scan_raw_text = ""

    for field in CONTACT_FIELDS:
        st.session_state[f"scan_{field}"] = ""


def set_extraction_result(raw_text, fields):
    """추후 OCR 백엔드가 반환한 결과를 편집 화면에 반영할 때 사용한다."""
    st.session_state.scan_raw_text = raw_text or ""

    for field in CONTACT_FIELDS:
        st.session_state[f"scan_{field}"] = str(fields.get(field) or "")


def add_contact(contact):
    item = {field: str(contact.get(field) or "").strip() for field in CONTACT_FIELDS}
    item["id"] = str(uuid4())
    item["created_at"] = str(contact.get("created_at") or datetime.now().isoformat(timespec="seconds"))
    st.session_state.contacts.append(item)
    return item


def update_contact(contact_id, values):
    for item in st.session_state.contacts:
        if item["id"] == contact_id:
            for field in CONTACT_FIELDS:
                item[field] = str(values.get(field) or "").strip()
            return True
    return False


def delete_contact(contact_id):
    before = len(st.session_state.contacts)
    st.session_state.contacts = [item for item in st.session_state.contacts if item["id"] != contact_id]
    return len(st.session_state.contacts) < before
