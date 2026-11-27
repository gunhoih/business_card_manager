"""챗봇 조회 대상과 대화 기록의 최신 데이터 여부를 관리한다.

화면과 API에 의존하지 않으며 연락처를 수정하지 않는다.
"""

import hashlib
import json

from backend.card_storage.schema import CONTACT_FIELDS

ALL_CONTACTS = "all"
VISIBLE_CONTACTS = "visible"
SELECTED_CONTACT = "selected"
CURRENT_SCAN = "scan"

SCOPE_LABELS = {
    ALL_CONTACTS: "저장된 연락처 전체",
    VISIBLE_CONTACTS: "현재 검색 결과",
    SELECTED_CONTACT: "선택한 연락처",
    CURRENT_SCAN: "미저장 개별 스캔 명함",
}


def resolve_source(scope, contacts, visible_contacts, selected_id, scan_fields=None):
    """현재 데이터에서 조회 대상을 결정한다. 빈 선택을 전체 조회로 바꾸지 않는다."""
    if scope == ALL_CONTACTS:
        return contacts
    if scope == VISIBLE_CONTACTS:
        # 화면에 전달된 항목도 현재 저장된 ID를 기준으로 다시 조회한다.
        visible_ids = {row.get("id") for row in visible_contacts if row.get("id")}
        return [row for row in contacts if row.get("id") in visible_ids]
    if scope == SELECTED_CONTACT:
        if not selected_id:
            return []
        return [row for row in contacts if row.get("id") == selected_id][:1]
    if scope == CURRENT_SCAN:
        scan_fields = scan_fields or {}
        current = {field: str(scan_fields.get(field) or "") for field in CONTACT_FIELDS}
        if not any(value.strip() for value in current.values()):
            return []
        current["id"] = "current-scan"
        return [current]
    raise ValueError("지원하지 않는 연락처 조회 대상입니다.")


def source_key(scope, contacts):
    """조회 대상이나 연락처 내용이 달라지면 새 데이터 버전으로 판단한다."""
    records = [
        {field: str(row.get(field) or "") for field in ["id", *CONTACT_FIELDS]}
        for row in contacts
    ]
    content = json.dumps(records, ensure_ascii=False, sort_keys=True)
    return scope + ":" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def current_history(history, key, limit):
    """현재 데이터로 진행한 연속 대화만 API에 전달한다.

    이전 데이터의 답변은 화면에는 남지만 모델에 다시 보내지 않는다.
    이전 버전에서 만든 출처 없는 대화도 제외한다.
    """
    messages = []
    for item in reversed(history):
        if item.get("source_key") != key:
            break
        messages.append({"role": item["role"], "content": item["content"]})
    return list(reversed(messages))[-limit:] if limit > 0 else []


def append_turn(history, question, answer, key, label, limit):
    """완료된 질문과 답변을 함께 추가하고 최근 대화만 보관한다."""
    messages = [
        {"role": "user", "content": question, "source_key": key, "source_label": label},
        {"role": "assistant", "content": answer, "source_key": key, "source_label": label},
    ]
    return (history + messages)[-limit:] if limit > 0 else []
