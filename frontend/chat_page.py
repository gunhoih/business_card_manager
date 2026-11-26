"""저장된 명함 전체를 자연어로 조회하는 챗봇 화면."""

import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from backend.agent.service import ask_contacts, MAX_HISTORY
from backend.card_storage.schema import CONTACT_FIELDS

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def get_setting(name, default=""):
    try:
        value = st.secrets.get(name)
        if value is not None:
            return str(value).strip()
    except (FileNotFoundError, OSError, KeyError):
        pass
    return os.getenv(name, default).strip()


def _chat_source():
    saved = st.session_state.get("contacts", [])
    current = {field: st.session_state.get(f"scan_{field}", "") for field in CONTACT_FIELDS}
    options = ["저장된 연락처 전체"]
    if any(str(value or "").strip() for value in current.values()):
        options.append("현재 개별 스캔 명함")
    source = st.radio("조회 대상", options, horizontal=True, key="agent_source")
    if source == "현재 개별 스캔 명함":
        current["id"] = "current-scan"
        return source, [current]
    return source, saved


def _source_key(source, contacts):
    records = [{key: str(row.get(key) or "") for key in ["id", *CONTACT_FIELDS]}
               for row in contacts]
    content = json.dumps(records, ensure_ascii=False, sort_keys=True)
    return source + ":" + hashlib.sha256(content.encode("utf-8")).hexdigest()


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


def show_chat_page():
    st.title("명함 챗봇")
    st.caption("저장된 연락처를 자연어로 검색하고 상세 정보와 통계를 확인할 수 있습니다.")
    source, contacts = _chat_source()
    st.caption(f"조회 가능한 명함 {len(contacts)}개 · 조회 전용")

    source_key = _source_key(source, contacts)
    if st.session_state.get("contact_agent_source_key") != source_key:
        st.session_state.contact_agent_source_key = source_key
        st.session_state.contact_agent_messages = []

    api_key = get_setting("OPENAI_API_KEY")
    model = get_setting("OPENAI_LLM_MODEL") or get_setting("OPENAI_MODEL") or "gpt-4o-mini"
    ready = bool(api_key and api_key not in ("...", "YOUR_OPENAI_API_KEY_HERE", "sk-...") and contacts)
    if not api_key or api_key in ("...", "YOUR_OPENAI_API_KEY_HERE", "sk-..."):
        st.info(".env 또는 Streamlit Secrets에 OPENAI_API_KEY를 설정하세요. OCR은 API 키 없이 사용할 수 있습니다.")
    elif not contacts:
        st.info("명함 데이터 추출 화면에서 연락처 목록에 먼저 저장하거나 CSV를 가져오세요.")
    else:
        st.caption(f"사용 모델: {model}")

    # 명함에는 개인정보가 있을 수 있으므로 API 전송을 명시적으로 알린다.
    consent = st.checkbox("질문과 필요한 조회 결과를 OpenAI API로 전송하는 데 동의합니다.", key="contact_agent_consent")
    st.caption("동의를 받은 명함만 사용하세요. 최근 대화와 조회 결과가 전송되며, 원본 이미지와 OCR 원문은 전송하지 않습니다.")

    history = st.session_state.get("contact_agent_messages", [])
    if st.button("대화 초기화", disabled=not history, key="agent_clear_history"):
        st.session_state.contact_agent_messages = []
        st.rerun()

    for item in history:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
    if not history:
        st.caption("예: 삼성전자 소속 연락처 찾아줘 / 홍길동의 이메일은? / 회사별 등록 건수 알려줘")

    question = st.chat_input("저장된 명함에 대해 질문하세요.", disabled=not ready or not consent,
                             max_chars=2000, key="contact_agent_question")
    if not question or not ready or not consent:
        return
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("연락처를 조회하고 있습니다..."):
                answer = ask_contacts(question, contacts, history, api_key=api_key, model=model)
        except Exception as error:
            # API 오류에는 요청 내용이 포함될 수 있어 원문을 웹 화면에 노출하지 않는다.
            st.error(_api_error_message(error))
            return
        st.markdown(answer)
    st.session_state.contact_agent_messages = (
        history + [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    )[-MAX_HISTORY:]
