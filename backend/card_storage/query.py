"""저장된 연락처의 검색, 상세 조회, 집계를 담당한다. 읽기 전용 함수이다."""

from collections import Counter
import unicodedata

from backend.card_storage.schema import CONTACT_FIELDS
from backend.card_storage.service import normalize_email, normalize_phone

DEFAULT_FIELDS = ("name", "company", "department", "position")
GROUP_FIELDS = ("company", "department", "position")
MAX_RESULTS = 20
MAX_FILTERS = 10
OPERATORS = ("contains", "equals", "missing", "present")


def _text(value):
    return str(value or "").strip()


def _normalized(value):
    return unicodedata.normalize("NFKC", _text(value)).casefold()


def _check_fields(fields):
    if fields is None or fields == []:
        return DEFAULT_FIELDS
    if not isinstance(fields, (list, tuple)) or any(
        not isinstance(field, str) or field not in CONTACT_FIELDS for field in fields
    ):
        raise ValueError("지원하지 않는 조회 필드입니다.")
    return tuple(dict.fromkeys(fields))


def _check_filters(filters):
    if filters is None:
        return []
    if not isinstance(filters, list) or len(filters) > MAX_FILTERS:
        raise ValueError("검색 조건은 최대 10개까지 사용할 수 있습니다.")
    checked = []
    for condition in filters:
        if not isinstance(condition, dict) or set(condition) - {"field", "operator", "value"}:
            raise ValueError("검색 조건 형식이 올바르지 않습니다.")
        field = condition.get("field")
        operator = condition.get("operator")
        value = condition.get("value")
        if field not in CONTACT_FIELDS or operator not in OPERATORS:
            raise ValueError("지원하지 않는 검색 필드 또는 조건입니다.")
        if operator in ("missing", "present"):
            if value not in (None, ""):
                raise ValueError("누락/존재 조건에는 값을 지정하지 않습니다.")
            value = None
        elif not isinstance(value, str) or not value.strip() or len(value) > 300:
            raise ValueError("검색어를 1~300자로 지정하세요.")
        elif operator == "equals" and field in ("phone", "email"):
            normalizer = normalize_phone if field == "phone" else normalize_email
            if not normalizer(value):
                raise ValueError("전화번호 또는 이메일의 형식을 확인하세요.")
        checked.append((field, operator, value))
    return checked


def _match(contact, field, operator, value):
    saved = _text(contact.get(field))
    if operator == "missing":
        return not saved
    if operator == "present":
        return bool(saved)
    if field == "phone":
        left = normalize_phone(saved)
        right = normalize_phone(value)
        if operator == "equals":
            return bool(left and right and left == right)
        # 전화번호 부분 검색은 숫자와 국제번호 표기 차이를 정리한다.
        left = "".join(char for char in left if char.isascii() and char.isdigit())
        right = right or _normalized(value)
        if not all(char in "0123456789+(). -" for char in right):
            return False
        right = "".join(char for char in right if char.isascii() and char.isdigit())
        return bool(right and right in left)
    if field == "email" and operator == "equals":
        left, right = normalize_email(saved), normalize_email(value)
        return bool(left and right and left == right)
    left, right = _normalized(saved), _normalized(value)
    if operator == "equals":
        return left == right
    return right in left


def _select(contacts, filters):
    conditions = _check_filters(filters)
    return [contact for contact in contacts if all(
        _match(contact, field, operator, value)
        for field, operator, value in conditions
    )]


def _page(limit, offset):
    if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise ValueError("조회 건수는 1~20개로 지정하세요.")
    if type(offset) is not int or offset < 0:
        raise ValueError("시작 위치는 0 이상의 정수여야 합니다.")
    return limit, offset


def _project(contact, fields):
    result = {"id": _text(contact.get("id"))}
    for field in fields:
        value = _text(contact.get(field))
        # 비정상적으로 긴 값으로 API 입력이 커지는 것을 방지한다.
        result[field] = value if len(value) <= 500 else value[:500] + "…[생략]"
    return result


def search_contacts(contacts, filters=None, fields=None, limit=20, offset=0):
    """모든 검색 조건(AND)에 맞는 연락처와 전체 일치 건수를 반환한다."""
    limit, offset = _page(limit, offset)
    fields = _check_fields(fields)
    matched = _select(contacts, filters)
    page = matched[offset:offset + limit]
    return {
        "total": len(matched),
        "contacts": [_project(contact, fields) for contact in page],
        "offset": offset,
        "returned": len(page),
        "has_more": offset + len(page) < len(matched),
    }


def get_contact(contacts, contact_id, fields=None):
    """고유 ID로 지정한 연락처 한 건을 조회한다."""
    fields = _check_fields(fields)
    if not isinstance(contact_id, str) or not contact_id.strip() or len(contact_id) > 200:
        raise ValueError("검색 결과의 연락처 ID를 지정하세요.")
    for contact in contacts:
        if contact.get("id") == contact_id:
            return {"found": True, "contact": _project(contact, fields)}
    return {"found": False, "contact": None}


def count_contacts(contacts, filters=None, group_by=None, limit=20, offset=0):
    """전체/조건별 건수와 회사, 부서, 직책별 집계를 계산한다."""
    limit, offset = _page(limit, offset)
    if group_by is not None and group_by not in GROUP_FIELDS:
        raise ValueError("회사, 부서, 직책으로만 그룹 집계를 할 수 있습니다.")
    matched = _select(contacts, filters)
    result = {"total": len(matched)}
    if group_by is None:
        return result

    # 표기상의 대소문자 차이만 합산하고, 다른 회사명을 임의로 합치지 않는다.
    counts = Counter()
    labels = {}
    for contact in matched:
        label = _text(contact.get(group_by))
        key = _normalized(label)
        counts[key] += 1
        labels.setdefault(key, label)
    ordered = sorted(counts, key=lambda key: (-counts[key], key))
    page = ordered[offset:offset + limit]
    result.update({
        "group_by": group_by,
        "group_count": len(ordered),
        "groups": [{"value": labels[key][:500], "count": counts[key]} for key in page],
        "offset": offset,
        "has_more": offset + len(page) < len(ordered),
    })
    return result
