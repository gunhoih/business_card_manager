"""OpenAI 도구 명세와 실제 연락처 조회 함수의 연결."""

from backend.card_storage.query import (
    GROUP_FIELDS, MAX_RESULTS, OPERATORS, count_contacts, get_contact, search_contacts,
)
from backend.card_storage.schema import CONTACT_FIELDS

FILTERS = {
    "type": "array",
    "description": "AND 검색 조건. 전체 조회/집계이면 빈 배열을 사용한다.",
    "items": {
        "type": "object",
        "properties": {
            "field": {"type": "string", "enum": CONTACT_FIELDS},
            "operator": {"type": "string", "enum": list(OPERATORS)},
            "value": {"type": ["string", "null"], "description": "검색어. missing/present는 null."},
        },
        "required": ["field", "operator", "value"],
        "additionalProperties": False,
    },
}
FIELDS = {
    "type": "array",
    "description": "답변에 필요한 필드만 선택. 빈 배열은 이름·회사·부서·직책.",
    "items": {"type": "string", "enum": CONTACT_FIELDS},
}
LIMIT = {"type": "integer", "description": f"한 번에 반환할 최대 건수(1~{MAX_RESULTS})."}
OFFSET = {"type": "integer", "description": "페이지 시작 위치. 첫 페이지는 0."}


def _tool(name, description, properties):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "strict": True,
            "parameters": {
                "type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False,
            },
        },
    }


TOOLS = [
    _tool("search_contacts", "조건에 맞는 저장 연락처를 검색하고 전체 일치 건수를 반환한다.", {
        "filters": FILTERS, "fields": FIELDS, "limit": LIMIT, "offset": OFFSET,
    }),
    _tool("get_contact", "검색에서 확인한 ID로 연락처 한 건의 필요한 필드를 조회한다.", {
        "contact_id": {"type": "string", "description": "search_contacts가 반환한 ID"},
        "fields": FIELDS,
    }),
    _tool("count_contacts", "조건별 건수 또는 회사·부서·직책별 집계를 반환한다.", {
        "filters": FILTERS,
        "group_by": {"type": ["string", "null"], "enum": [*GROUP_FIELDS, None],
                     "description": "전체 건수만 필요하면 null."},
        "limit": LIMIT, "offset": OFFSET,
    }),
]

_HANDLERS = {
    "search_contacts": search_contacts,
    "get_contact": get_contact,
    "count_contacts": count_contacts,
}


def run_tool(name, arguments, contacts):
    """허용된 세 조회 함수만 실행한다. 모델의 잘못된 인자는 오류로 반환한다."""
    if not isinstance(name, str) or name not in _HANDLERS:
        return {"ok": False, "error": "허용되지 않은 도구입니다."}
    if not isinstance(arguments, dict):
        return {"ok": False, "error": "도구 인자는 JSON 객체여야 합니다."}
    expected = next(tool["function"]["parameters"]["properties"] for tool in TOOLS
                    if tool["function"]["name"] == name)
    if set(arguments) != set(expected):
        return {"ok": False, "error": "도구의 필수 인자를 정확하게 지정하세요."}
    # 런타임 검증은 strict 모드와 별도로 유지한다.
    try:
        for field, specification in expected.items():
            value = arguments[field]
            kinds = specification["type"]
            kinds = [kinds] if isinstance(kinds, str) else kinds
            valid = any((kind == "array" and isinstance(value, list)) or
                        (kind == "integer" and type(value) is int) or
                        (kind == "string" and isinstance(value, str)) or
                        (kind == "null" and value is None) for kind in kinds)
            if not valid:
                raise ValueError("도구 인자의 자료형을 확인하세요.")
        data = _HANDLERS[name](contacts, **arguments)
    except (TypeError, ValueError):
        return {"ok": False, "error": "검색 조건, 조회 필드 또는 페이지 범위를 확인하세요."}
    return {"ok": True, **data}
