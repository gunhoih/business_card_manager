import streamlit as st

from backend.contact.csv_service import (
    CONTACT_FIELDS,
    FIELD_LABELS,
    export_contacts_csv,
    import_contacts_csv,
    filter_new_contacts,
)
from frontend.state import add_contact, delete_contact, update_contact


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

                    if st.button("CSV 연락처 추가", disabled=not rows, type="primary", width="stretch"):
                        new_rows, skipped = filter_new_contacts(rows, st.session_state.contacts)
                        for row in new_rows:
                            add_contact(row)
                        st.success(f"{len(new_rows)}개를 추가했습니다. 중복된 {skipped}개는 건너뛰었습니다.")


def show_contact_table():
    st.subheader("연락처 목록")
    search = st.text_input("연락처 검색", placeholder="이름, 회사, 전화번호, 이메일로 검색")
    keyword = search.strip().casefold()
    contacts = st.session_state.contacts

    if keyword:
        contacts = [
            item for item in contacts
            if any(keyword in str(item.get(field, "")).casefold() for field in CONTACT_FIELDS)
        ]

    if not contacts:
        st.info("일치하는 연락처가 없습니다. '명함 인식'에서 정보를 입력하거나 CSV 파일을 가져오세요.")
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
    if not contacts:
        return

    st.subheader("선택한 연락처 수정")
    contact_ids = [item["id"] for item in contacts]
    contact_map = {item["id"]: item for item in contacts}

    def contact_label(contact_id):
        item = contact_map[contact_id]
        name = item.get("name") or "이름 없음"
        company = item.get("company") or "소속 없음"
        return f"{name} · {company}"

    selected_id = st.selectbox("연락처 선택", contact_ids, format_func=contact_label)
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
        if not any(updated[field].strip() for field in CONTACT_FIELDS):
            st.warning("모든 연락처 정보를 비울 수는 없습니다.")
        else:
            update_contact(selected_id, updated)
            st.success("수정된 정보가 임시 목록에 반영됐습니다.")

    with st.expander("연락처 삭제"):
        confirmed = st.checkbox("선택한 연락처를 삭제하겠습니다.", key=f"confirm_delete_{selected_id}")
        if st.button("선택한 연락처 삭제", disabled=not confirmed, key=f"delete_{selected_id}"):
            delete_contact(selected_id)
            st.rerun()


def show_contacts():
    st.title("연락처 관리")
    st.write("인식하거나 직접 입력한 명함 정보를 확인하고 CSV로 저장할 수 있습니다.")
    st.warning("현재 연락처는 서버에 영구 저장되지 않습니다. 페이지를 떠나기 전에 CSV 파일을 다운로드하세요.", icon="⚠️")

    total = len(st.session_state.contacts)
    with_email = sum(bool(item.get("email")) for item in st.session_state.contacts)
    companies = {item["company"].strip() for item in st.session_state.contacts if item.get("company", "").strip()}
    col1, col2, col3 = st.columns(3)
    col1.metric("전체 연락처", total)
    col2.metric("이메일이 있는 연락처", with_email)
    col3.metric("회사·소속", len(companies))

    show_csv_tools()
    contacts = show_contact_table()
    show_contact_editor(contacts)
