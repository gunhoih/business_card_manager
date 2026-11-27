"""연락처 목록, 수정, CSV 관리와 AI 조회 패널을 한 화면에 배치한다."""

import streamlit as st

from backend.card_storage.schema import CONTACT_FIELDS, FIELD_LABELS
from backend.card_storage.csv_service import export_contacts_csv, import_contacts_csv
from backend.card_storage.service import save_contacts
from frontend.chat_page import show_chat_panel
from frontend.state import delete_contact, update_contact
from frontend.storage_ui import show_save_result


def show_csv_tools():
    st.subheader("CSV 저장 및 가져오기")
    left, right = st.columns(2, gap="large")

    with left:
        with st.container(border=True):
            st.markdown("**CSV로 내보내기**")
            st.caption("현재 연락처 목록을 UTF-8(BOM) CSV로 다운로드합니다.")
            st.download_button(
                "CSV 다운로드",
                data=export_contacts_csv(st.session_state.contacts),
                file_name="business_card_contacts.csv",
                mime="text/csv",
                disabled=not st.session_state.contacts,
                type="primary",
                width="stretch",
                on_click="ignore",
            )

    with right:
        with st.container(border=True):
            st.markdown("**CSV에서 가져오기**")
            uploaded = st.file_uploader("연락처 CSV 선택", type=["csv"], key="contacts_csv")
            st.caption("UTF-8 CSV · 최대 2MB / 2,000개 연락처")
            st.caption("전화번호 또는 이메일이 일치하면 갱신하고, 일치하는 연락처가 없으면 신규 등록합니다. 식별 정보가 없으면 저장을 보류합니다.")

            if uploaded is not None:
                try:
                    rows = import_contacts_csv(uploaded.getvalue())
                except ValueError as error:
                    st.error(str(error))
                else:
                    st.caption(f"가져올 연락처 {len(rows)}개 · 아래는 최대 10개 미리보기")
                    if rows:
                        preview = [
                            {FIELD_LABELS[field]: item.get(field, "") for field in CONTACT_FIELDS}
                            for item in rows[:10]
                        ]
                        st.dataframe(preview, hide_index=True, width="stretch")

                    if st.button("CSV 연락처 저장", disabled=not rows, type="primary", width="stretch"):
                        result = save_contacts(st.session_state.contacts, rows)
                        # 이전 목록으로 생성된 다운로드 버튼을 새 목록으로 갱신한다.
                        st.session_state["contacts_save_result"] = result
                        st.rerun()


def show_contact_table():
    st.subheader("연락처 목록")
    search = st.text_input(
        "연락처 검색", placeholder="이름, 회사, 전화번호, 이메일로 검색",
        key="contacts_search",
    )
    keyword = search.strip().casefold()
    contacts = st.session_state.contacts

    if keyword:
        contacts = [
            item for item in contacts
            if any(keyword in str(item.get(field, "")).casefold() for field in CONTACT_FIELDS)
        ]

    if not contacts:
        st.info("일치하는 연락처가 없습니다. '명함 데이터 추출'에서 저장하거나 CSV 파일을 가져오세요.")
        return []

    visible_fields = ["name", "company", "department", "position", "phone", "email"]
    rows = [
        {FIELD_LABELS[field]: item.get(field, "") for field in visible_fields}
        for item in contacts
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption(f"검색 결과 {len(contacts)}개 / 전체 {len(st.session_state.contacts)}개")
    return contacts


def show_contact_editor(contacts):
    """선택된 연락처 ID를 챗봇에 전달한다. 기존 저장 및 삭제 로직은 유지한다."""
    if not contacts:
        return None

    st.subheader("선택한 연락처 수정")
    contact_ids = [item["id"] for item in contacts]
    contact_map = {item["id"]: item for item in contacts}

    def contact_label(contact_id):
        item = contact_map[contact_id]
        name = item.get("name") or "이름 없음"
        company = item.get("company") or "소속 없음"
        return f"{name} · {company}"

    selection_key = "contacts_editor_selected"
    # 기존 선택이 검색/삭제로 사라진 경우 유효한 항목으로 바꾼다.
    if st.session_state.get(selection_key) not in contact_ids:
        st.session_state[selection_key] = contact_ids[0]
    selected_id = st.selectbox(
        "연락처 선택", contact_ids, format_func=contact_label, key=selection_key,
    )
    if selected_id not in contact_map:
        return None
    selected = contact_map[selected_id]

    with st.form(f"edit_contact_{selected_id}"):
        name = st.text_input("이름", value=selected.get("name", ""))
        company = st.text_input("회사·소속", value=selected.get("company", ""))
        c1, c2 = st.columns(2)
        with c1:
            department = st.text_input("부서", value=selected.get("department", ""))
        with c2:
            position = st.text_input("직책", value=selected.get("position", ""))
        phone = st.text_input("전화번호", value=selected.get("phone", ""))
        email = st.text_input("이메일", value=selected.get("email", ""))
        website = st.text_input("웹사이트", value=selected.get("website", ""))
        fax = st.text_input("팩스", value=selected.get("fax", ""))
        address = st.text_input("주소", value=selected.get("address", ""))
        memo = st.text_area("메모", value=selected.get("memo", ""))
        saved = st.form_submit_button("변경 사항 저장", type="primary")

    if saved:
        updated = {
            "name": name,
            "company": company,
            "department": department,
            "position": position,
            "phone": phone,
            "email": email,
            "website": website,
            "fax": fax,
            "address": address,
            "memo": memo,
        }
        try:
            if not update_contact(selected_id, updated):
                st.warning("연락처를 찾을 수 없습니다.")
            else:
                st.session_state["contacts_notice"] = "수정된 정보가 목록에 반영됐습니다."
                st.rerun()
        except ValueError as error:
            st.warning(str(error))

    with st.expander("연락처 삭제"):
        confirmed = st.checkbox("선택한 연락처를 삭제하겠습니다.", key=f"confirm_delete_{selected_id}")
        if st.button("선택한 연락처 삭제", disabled=not confirmed, key=f"delete_{selected_id}"):
            delete_contact(selected_id)
            st.rerun()
    return selected_id


def _show_contact_workspace():
    """목록, 편집 및 CSV 기능을 표시하고 현재 조회 맥락을 반환한다."""
    result = st.session_state.pop("contacts_save_result", None)
    if result is not None:
        show_save_result(result, ui=st)
    notice = st.session_state.pop("contacts_notice", None)
    if notice:
        st.success(notice)

    total = len(st.session_state.contacts)
    with_email = sum(bool(item.get("email")) for item in st.session_state.contacts)
    companies = {item["company"].strip() for item in st.session_state.contacts if item.get("company", "").strip()}
    col1, col2, col3 = st.columns(3)
    col1.metric("전체 연락처", total)
    col2.metric("이메일이 있는 연락처", with_email)
    col3.metric("회사·소속", len(companies))

    contacts = show_contact_table()
    selected_id = show_contact_editor(contacts)
    with st.expander("CSV 저장 및 가져오기", expanded=not total):
        show_csv_tools()
    return contacts, selected_id


def _toggle_chat():
    st.session_state.contacts_chat_open = not st.session_state.get("contacts_chat_open", False)


def show_contacts():
    if "contacts_chat_open" not in st.session_state:
        st.session_state.contacts_chat_open = False
    chat_open = st.session_state.contacts_chat_open

    title_col, button_col = st.columns([3, 1], vertical_alignment="center")
    with title_col:
        st.title("연락처 관리")
    with button_col:
        label = "AI 도우미 닫기" if chat_open else "AI 도우미 열기"
        st.button(
            label, key="contacts_chat_toggle", on_click=_toggle_chat,
            type="secondary" if chat_open else "primary", width="stretch",
            icon=":material/chat:",
        )

    st.caption("인식하거나 직접 입력한 명함을 관리하고, AI 도우미에게 현재 연락처를 질문할 수 있습니다.")
    st.warning("연락처는 현재 웹 세션에만 보관됩니다. 종료 전에 CSV 파일을 다운로드하세요.", icon="⚠️")

    if chat_open:
        left, right = st.columns([65, 35], gap="large")
        with left:
            visible_contacts, selected_id = _show_contact_workspace()
        with right:
            show_chat_panel(visible_contacts, selected_id)
    else:
        _show_contact_workspace()
