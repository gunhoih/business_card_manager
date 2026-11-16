"""현재 명함 또는 선택한 저장 연락처에 대한 간단한 LLM 채팅."""

import os
import hashlib

from dotenv import load_dotenv
from openai import OpenAIError
import streamlit as st

from backend.chat.service import FIELD_NAMES, ask_about_card, build_card_context


load_dotenv()


def get_setting(name, default=""):
    try:
        value = st.secrets.get(name)
        if value is not None:
            return str(value).strip()
    except (FileNotFoundError, OSError, KeyError):
        pass
    return os.getenv(name, default).strip()


def show_chat_page():
    st.title("명함 챗봇")
    st.write("추출·수정한 명함 정보를 바탕으로 질문할 수 있습니다. OCR은 API 없이 동작하지만 챗봇은 OpenAI API를 사용합니다.")
    st.warning("명함의 개인정보가 질문과 함께 OpenAI API로 전송됩니다. 본인 또는 제공자의 동의를 받은 명함으로만 사용하세요.")

    current_fields = {key: st.session_state.get(f"scan_{key}", "") for key in FIELD_NAMES}
    raw_text = st.session_state.get("scan_raw_text", "")
    contacts = st.session_state.get("contacts", [])

    source_options = ["현재 스캔 명함"]
    if contacts:
        source_options.append("저장된 연락처 한 명")
    source = st.radio("참고 데이터", source_options, horizontal=True)

    if source == "저장된 연락처 한 명":
        index = st.selectbox(
            "연락처 선택", range(len(contacts)),
            format_func=lambda i: f"{contacts[i].get('name') or '이름 없음'} · {contacts[i].get('company') or '소속 없음'}",
        )
        card = contacts[index]
        source_key = "contact:" + card["id"]
        context = build_card_context(card)
        has_data = any(str(card.get(key, "")).strip() for key in FIELD_NAMES)
    else:
        source_key = "scan:" + st.session_state.get("scan_image_id", "")
        context = build_card_context(current_fields, raw_text)
        has_data = bool(raw_text.strip() or any(str(value).strip() for value in current_fields.values()))

    source_key += ":" + hashlib.sha256(context.encode("utf-8")).hexdigest()
    if st.session_state.get("chat_source_key") != source_key:
        st.session_state.chat_source_key = source_key
        st.session_state.chat_messages = []

    with st.expander("LLM에 전달할 명함 정보 미리보기"):
        st.code(context, language="json")

    api_key = get_setting("OPENAI_API_KEY")
    model = get_setting("OPENAI_LLM_MODEL", "gpt-4o-mini")
    if not api_key or api_key in ("...", "YOUR_OPENAI_API_KEY_HERE"):
        st.info("챗봇 사용 시 .env 또는 .streamlit/secrets.toml에 OPENAI_API_KEY를 설정해 주세요. OCR은 키 없이도 작동합니다.")
    elif not has_data:
        st.info("스캔 명함 정보를 입력하거나 OCR을 실행한 후 질문해 주세요.")
    else:
        st.caption(f"사용 모델: {model} · 질문할 때만 API 호출")

    history = st.session_state.get("chat_messages", [])
    if st.button("대화 내역 초기화", disabled=not history):
        st.session_state.chat_messages = []
        st.rerun()

    for item in history:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    question = st.chat_input("예: 이 명함에 적힌 이메일 주소는?", disabled=not has_data or not api_key or api_key in ("...", "YOUR_OPENAI_API_KEY_HERE"))
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("명함 정보로 답변 중..."):
                try:
                    answer = ask_about_card(question, context, history, api_key=api_key, model=model)
                except (OpenAIError, RuntimeError, ValueError):
                    st.error("LLM 응답을 받지 못했습니다. 모델 이름, API 키, 사용량 및 네트워크를 확인해 주세요.")
                    return
                st.markdown(answer)
        st.session_state.chat_messages = (history + [{"role": "user", "content": question}, {"role": "assistant", "content": answer}])[-12:]
