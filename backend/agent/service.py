"""OpenAI Chat Completions로 조회 도구를 호출하는 단일 에이전트."""

import json
from time import monotonic

from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.tools import TOOLS, run_tool
from backend.card_storage.schema import CONTACT_FIELDS

MAX_TOOL_CALLS = 5
MAX_HISTORY = 8
MAX_AGENT_SECONDS = 60.0
MAX_REQUEST_SECONDS = 25.0
NO_LOOKUP = "조회할 이름이나 회사 등 검색 조건을 알려 주세요. 연락처 등록·수정·삭제는 연락처 관리 화면에서 할 수 있습니다."


def _snapshot(contacts):
    # 현재 세션의 연락처만 사용한다. 이미지, OCR 원문, 내부 메타데이터는 제외한다.
    result = []
    for contact in contacts:
        item = {field: str(contact.get(field) or "") for field in CONTACT_FIELDS}
        item["id"] = str(contact.get("id") or "")
        result.append(item)
    return result


def _messages(question, history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in history[-MAX_HISTORY:]:
        if not isinstance(item, dict):
            continue
        if item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
            messages.append({"role": item["role"], "content": item["content"][:2000]})
    messages.append({"role": "user", "content": question})
    return messages


def _tool_result(name, raw_arguments, contacts):
    try:
        if not isinstance(raw_arguments, str) or len(raw_arguments) > 16000:
            raise ValueError("인자가 너무 큽니다.")
        arguments = json.loads(raw_arguments)
    except (ValueError, TypeError, RecursionError):
        return {"ok": False, "error": "도구 인자를 올바른 JSON으로 지정하세요."}
    return run_tool(name, arguments, contacts)


def ask_contacts(question, contacts, history=None, *, api_key=None, model="gpt-4o-mini", client=None):
    """질문 -> 도구 실행 -> 결과 기반 답변. 한 질문에 도구는 최대 5번 실행한다.

    client 주입은 테스트에서 실제 API 요청 없이 동작을 검증하기 위한 것이다.
    """
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError("질문을 1~2,000자로 입력하세요.")
    if not model or not model.strip():
        raise ValueError("OpenAI 모델을 설정해 주세요.")
    if not contacts:
        return "조회할 연락처가 없습니다. 명함을 먼저 저장해 주세요."
    if client is None:
        if not api_key or not api_key.strip():
            raise ValueError("OpenAI API 키를 설정해 주세요.")
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=MAX_REQUEST_SECONDS, max_retries=0)

    deadline = monotonic() + MAX_AGENT_SECONDS

    def request(**kwargs):
        remaining = deadline - monotonic()
        if remaining < 1:
            raise RuntimeError("연락처 조회 제한 시간에 도달했습니다. 질문을 좁혀 주세요.")
        # 실제 SDK에만 남은 시간에 맞춘 옵션을 적용한다. 모의 클라이언트도 같은 실행 흐름 사용.
        request_client = client
        if callable(getattr(client, "with_options", None)):
            request_client = client.with_options(timeout=min(MAX_REQUEST_SECONDS, remaining), max_retries=0)
        response = request_client.chat.completions.create(**kwargs)
        if not response.choices:
            raise RuntimeError("API가 답변 후보를 반환하지 않았습니다.")
        return response.choices[0]

    contacts = _snapshot(contacts)
    messages = _messages(question.strip(), history or [])
    used = 0
    successful = False

    while used < MAX_TOOL_CALLS:
        choice = request(
            model=model, messages=messages, tools=TOOLS, tool_choice="auto",
            parallel_tool_calls=False, store=False, max_completion_tokens=1200,
        )
        message = choice.message
        calls = message.tool_calls or []
        if not calls:
            if choice.finish_reason != "stop" or not isinstance(message.content, str) or not message.content.strip():
                raise RuntimeError("답변이 중단되었습니다. 질문을 조금 더 좁혀 주세요.")
            if not successful:
                # 근거 없이 연락처 정보를 만들어 답하는 것을 방지한다.
                return NO_LOOKUP
            return message.content.strip()

        assistant_message = {"role": "assistant", "content": message.content, "tool_calls": []}
        for call in calls:
            assistant_message["tool_calls"].append({
                "id": call.id, "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            })
        messages.append(assistant_message)

        # 병렬 호출을 요청하지 않지만 복수 호출이 반환되어도 모두 응답한다.
        for call in calls:
            if used >= MAX_TOOL_CALLS:
                result = {"ok": False, "error": "도구 호출 한도에 도달했습니다."}
            else:
                used += 1
                result = _tool_result(call.function.name, call.function.arguments, contacts)
                successful = successful or result.get("ok", False)
            messages.append({"role": "tool", "tool_call_id": call.id,
                             "content": json.dumps(result, ensure_ascii=False)})

    if not successful:
        return "연락처 조회에 실패했습니다. 검색 조건을 바꾸어 다시 질문해 주세요."

    # 한도 이후에는 추가 도구를 제공하지 않고 이미 조회한 결과만 정리한다.
    messages.append({"role": "system", "content":
                     "도구 호출 한도에 도달했습니다. 지금까지 조회한 결과만으로 답하고, 확인하지 못한 정보는 명시하세요."})
    choice = request(
        model=model, messages=messages, store=False, max_completion_tokens=1200,
    )
    if (choice.finish_reason != "stop" or not isinstance(choice.message.content, str)
            or not choice.message.content.strip()):
        raise RuntimeError("답변이 중단되었습니다. 질문을 조금 더 좁혀 주세요.")
    return choice.message.content.strip()
