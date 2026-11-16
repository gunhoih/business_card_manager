import streamlit as st

from frontend.contacts import show_contacts
from frontend.scanner import show_scanner
from frontend.state import init_state


def main():
    st.set_page_config(
        page_title="Business Card Manager",
        page_icon="📇",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    init_state()

    st.sidebar.title("Business Card Manager")
    st.sidebar.caption("명함 스캔 · 정보 추출 · 연락처 관리")

    pages = [
        st.Page(show_scanner, title="명함 인식", icon="📷", url_path="scanner", default=True),
        st.Page(show_contacts, title="연락처 관리", icon="📇", url_path="contacts"),
    ]

    page = st.navigation(pages)

    st.sidebar.divider()
    st.sidebar.metric("임시 저장된 연락처", len(st.session_state.contacts))
    st.sidebar.caption("OpenCV 이미지 보정 · CSV 관리 사용 가능")
    st.sidebar.caption("연락처는 브라우저 세션에만 보관됩니다. CSV로 내려받아 보관하세요.")

    page.run()


if __name__ == "__main__":
    main()
