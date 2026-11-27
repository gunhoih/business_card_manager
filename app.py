import streamlit as st

from backend.contact.csv_service import CONTACT_FIELDS
from frontend.batch_scanner import show_batch_scanner
from frontend.classifier_page import show_classifier_page
from frontend.contacts import show_contacts
from frontend.ocr_page import show_ocr_page
from frontend.scanner import show_scanner
from frontend.state import init_state


def keep_scan_data_between_pages():
    """Streamlit 페이지 전환 시 편집 중인 값이 지워지지 않도록 유지."""
    keys = ["scan_raw_text", "classifier_input"] + [f"scan_{field}" for field in CONTACT_FIELDS]
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
    st.sidebar.caption("명함 이미지 → 연락처 데이터 추출")

    # 챗봇은 연락처 관리 화면의 우측 패널에서 사용한다.
    pages = {
        "기본": [
            st.Page(show_batch_scanner, title="명함 데이터 추출", icon="📋", url_path="batch-scanner", default=True),
            st.Page(show_contacts, title="연락처 관리", icon="📇", url_path="contacts"),
        ],
        "상세 도구": [
            st.Page(show_scanner, title="개별 명함 스캔", icon="📷", url_path="scanner"),
            st.Page(show_ocr_page, title="OCR 텍스트 인식", icon="🔤", url_path="ocr"),
            st.Page(show_classifier_page, title="텍스트 분류", icon="🏷️", url_path="classifier"),
        ],
    }

    page = st.navigation(pages)

    st.sidebar.divider()
    contact_metric = st.sidebar.empty()
    st.sidebar.caption("OpenCV 보정 · Tesseract OCR · 로컬 규칙 분류 · CSV 관리")
    st.sidebar.caption("AI 연락처 도우미만 OpenAI API 키가 필요합니다.")
    st.sidebar.caption("연락처는 웹 세션에만 보관됩니다. CSV로 내려받아 보관하세요.")

    page.run()
    # 같은 실행 안에서 연락처가 추가/수정돼도 최신 건수를 표시한다.
    contact_metric.metric("임시 저장된 연락처", len(st.session_state.contacts))


if __name__ == "__main__":
    main()
