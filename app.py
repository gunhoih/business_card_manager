import streamlit as st

from frontend.chat_page import show_chat_page
from frontend.contacts import show_contacts
from frontend.ocr_page import show_ocr_page
from frontend.scanner import show_scanner
from frontend.state import init_state


def keep_scan_data_between_pages():
    """Streamlit 페이지 변경 시 기존 입력 위젯 키가 정리되지 않도록 유지."""
    keys = [
        "scan_raw_text", "scan_name", "scan_company", "scan_department",
        "scan_position", "scan_phone", "scan_email", "scan_website", "scan_memo",
    ]
    for key in keys:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def main():
    st.set_page_config(
        page_title="Business Card Manager",
        page_icon="📇",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    keep_scan_data_between_pages()
    init_state()

    st.sidebar.title("Business Card Manager")
    st.sidebar.caption("명함 스캔 · OCR · 연락처 · 챗봇")

    pages = [
        st.Page(show_scanner, title="명함 인식", icon="📷", url_path="scanner", default=True),
        st.Page(show_ocr_page, title="OCR 텍스트 인식", icon="🔤", url_path="ocr"),
        st.Page(show_contacts, title="연락처 관리", icon="📇", url_path="contacts"),
        st.Page(show_chat_page, title="명함 챗봇", icon="💬", url_path="chat"),
    ]

    page = st.navigation(pages)

    st.sidebar.divider()
    st.sidebar.metric("임시 저장된 연락처", len(st.session_state.contacts))
    st.sidebar.caption("OpenCV 원근 보정 · Tesseract OCR · CSV 관리")
    st.sidebar.caption("챗봇만 OpenAI API 키가 필요합니다.")
    st.sidebar.caption("연락처는 브라우저 세션에만 보관됩니다. CSV로 내려받아 보관하세요.")

    page.run()


if __name__ == "__main__":
    main()
