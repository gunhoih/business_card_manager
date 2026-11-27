"""연락처 관리 화면에 삽입되는 읽기 전용 AI 연락처 도우미."""

import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from backend.agent.service import ask_contacts, MAX_HISTORY
from backend.card_storage.schema import CONTACT_FIELDS
from frontend.contact_chat_state import (
    ALL_CONTACTS, SELECTED_CONTACT, CURRENT_SCAN, SCOPE_LABELS,
    resolve_source, source_key,
    current_history, append_turn,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def get_setting(name, default=""):
    try:
        value = st.secrets.get(name)
        if value is not None:
            return str(value).strip()
    except (FileNotFoundError, OSError, KeyError):
        pass
    return os.getenv(name, default).strip()


def _remember_widget(widget_key, state_key):
    """패널을 닫거나 페이지를 이동해도 위젯 선택값을 유지한다."""
    st.session_state[state_key] = st.session_state[widget_key]


def _chat_source(visible_contacts, selected_id):
    scope_state = "contact_chat_scope"
    widget_key = "_contact_chat_scope"
    saved_scope = st.session_state.get(scope_state, ALL_CONTACTS)
    if saved_scope not in SCOPE_LABELS:
        saved_scope = ALL_CONTACTS
    if widget_key not in st.session_state:
        st.session_state[widget_key] = saved_scope
    scope = st.selectbox(
        "조회 대상", list(SCOPE_LABELS), format_func=SCOPE_LABELS.__getitem__,
        key=widget_key, on_change=_remember_widget, args=(widget_key, scope_state),
    )
    current = {field: st.session_state.get(f"scan_{field}", "") for field in CONTACT_FIELDS}
    contacts = resolve_source(
        scope, st.session_state.get("contacts", []), visible_contacts, selected_id, current,
    )
    return scope, contacts


def _api_error_message(error):
    """API 키나 연락처 데이터가 담긴 예외 원문은 사용자 화면에 노출하지 않는다."""
    messages = {
        "AuthenticationError": "API 키 인증에 실패했습니다. 키 설정을 확인하세요.",
        "PermissionDeniedError": "API 키의 모델 접근 권한을 확인하세요.",
        "NotFoundError": "설정한 모델 또는 API 경로를 찾지 못했습니다. 모델 이름을 확인하세요.",
        "RateLimitError": "API 요청 한도 또는 잔여 크레딧을 확인한 후 다시 시도하세요.",
        "APITimeoutError": "API 응답 시간이 초과됐습니다. 질문을 좁혀 다시 시도하세요.",
        "APIConnectionError": "API 서버에 연결하지 못했습니다. 인터넷 및 서버 상태를 확인하세요.",
        "BadRequestError": "API 요청이 거부됐습니다. 모델의 Tool Calling 지원 및 설정을 확인하세요.",
        "InternalServerError": "API 서버에 일시적인 문제가 있습니다. 다시 시도하세요.",
    }
    if type(error).__name__ in messages:
        return messages[type(error).__name__]
    if isinstance(error, (ValueError, RuntimeError)):
        return "질문 또는 조회 결과를 처리하지 못했습니다. 질문을 좁혀 다시 시도해 주세요."
    return "API 연결에 실패했습니다. API 키, 모델 이름, 사용 한도 및 네트워크를 확인해 주세요."


def show_chat_panel(visible_contacts, selected_id):
    """현재 연락처 데이터와 편집 화면의 선택값을 받아 챗봇을 표시한다."""
    with st.container(border=True):
        st.subheader("AI 연락처 도우미")
        scope, contacts = _chat_source(visible_contacts, selected_id)
        label = SCOPE_LABELS[scope]
        key = source_key(scope, contacts)
        st.caption(f"{label} · {len(contacts)}개 · 조회 전용")
        if scope == SELECTED_CONTACT and contacts:
            selected = contacts[0]
            st.caption(f"선택: {selected.get('name') or '이름 없음'} · {selected.get('company') or '소속 없음'}")
        elif scope == CURRENT_SCAN:
            st.caption("저장 전 개별 스캔의 입력값입니다. 확정된 연락처와는 다를 수 있습니다.")

        api_key = get_setting("OPENAI_API_KEY")
        model = get_setting("OPENAI_LLM_MODEL") or get_setting("OPENAI_MODEL") or "gpt-4o-mini"
        valid_key = bool(api_key and api_key not in ("...", "YOUR_OPENAI_API_KEY_HERE", "sk-..."))
        if not valid_key:
            st.info(".env 또는 Streamlit Secrets에 OPENAI_API_KEY를 설정하세요.")
        if not contacts:
            st.info("현재 조회 대상에 연락처가 없습니다. 명함을 저장하거나 조회 대상을 변경하세요.")
        if valid_key and contacts:
            st.caption(f"사용 모델: {model}")

        consent_key = "_contact_chat_consent"
        consent_state = "contact_chat_consent"
        if consent_key not in st.session_state:
            st.session_state[consent_key] = st.session_state.get(consent_state, False)
        consent = st.checkbox(
            "질문과 필요한 조회 결과의 OpenAI API 전송에 동의합니다.",
            key=consent_key, on_change=_remember_widget, args=(consent_key, consent_state),
        )
        st.caption("동의를 받은 명함만 사용하세요. 현재 데이터 기준 최근 대화와 조회 결과가 전송되며, 원본 이미지와 OCR 원문은 전송하지 않습니다.")

        history = st.session_state.get("contact_agent_messages", [])
        active_history = current_history(history, key, MAX_HISTORY)
        if len(active_history) != len(history):
            st.info("조회 대상 또는 데이터가 변경되었습니다. 이전 기록은 표시만 하며, 새 질문에는 현재 데이터를 사용합니다.")
        if st.button("대화 초기화", disabled=not history, key="agent_clear_history"):
            st.session_state.contact_agent_messages = []
            st.rerun()

        # 대화 영역만 스크롤하고 입력창은 아래쪽에 둔다.
        messages_box = st.container(height=420, border=False)
        with messages_box:
            if not history:
                st.caption("예: 회사별 등록 건수는? / 김민수의 전화번호는? / 이메일이 없는 연락처는?")
            stale_count = len(history) - len(active_history)
            for index, item in enumerate(history):
                with st.chat_message(item["role"]):
                    if index < stale_count:
                        st.caption(f"이전 조회 기준 · {item.get('source_label', '이전 대화')}")
                    st.markdown(item["content"])

        ready = valid_key and bool(contacts) and consent
        question = st.chat_input(
            "연락처에 대해 질문하세요", disabled=not ready,
            max_chars=2000, key="contact_agent_question",
        )
        if not question or not ready:
            return

        with messages_box:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                try:
                    with st.spinner("연락처를 조회하고 있습니다..."):
                        answer = ask_contacts(question, contacts, active_history, api_key=api_key, model=model)
                except Exception as error:
                    # 예외 원문에는 개인정보가 포함될 수 있다.
                    st.error(_api_error_message(error))
                    return
                st.markdown(answer)

        st.session_state.contact_agent_messages = append_turn(
            history, question, answer, key, label, MAX_HISTORY,
        )
        # 입력 이벤트는 일회성이다. 다시 그리면 초기화 버튼과 대화 상태가 갱신된다.
        st.rerun()
