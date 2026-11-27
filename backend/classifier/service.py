"""OCR 줄 → 패턴 추출 → 문맥 분류 → 수동 검토용 후보.

간단한 사용법:
    rows = classify_text('홍길동\n팀장\nhong@example.com')
    for row in rows:
        print(row['text'], row['predicted_type'], row['reasons'])

외부 LLM이나 네트워크 호출 없이 실행한다.
"""

from dataclasses import asdict, dataclass
from statistics import median
import re

from .context_rules import classify_context, looks_like_position
from .korean_names import refine_name_candidates, split_name_context
from .patterns import (
    BARE_DOMAIN, EMAIL, FIELD_SEPARATOR, PHONE, PURE_LABEL, WEBSITE,
    is_email_hint, is_fax_number,
)

# 기존 연락처 저장 필드와 일치한다. unknown은 저장하지 않는다.
FIELD_NAMES = {
    "unknown": "미분류",
    "name": "이름",
    "company": "회사·소속",
    "department": "부서",
    "position": "직책",
    "phone": "전화번호",
    "fax": "팩스",
    "email": "이메일",
    "website": "웹사이트",
    "address": "주소",
    "memo": "기타(메모)",
}

# 접두어가 있는 값은 내용만 추출해 확실하게 분류할 수 있다.
EXPLICIT_LABELS = [
    (re.compile(r"^(?:성명|이름|name)\s*[:：]\s*(.+)$", re.IGNORECASE), "name"),
    (re.compile(r"^(?:회사|소속|company|organization)\s*[:：]\s*(.+)$", re.IGNORECASE), "company"),
    (re.compile(r"^(?:부서|department|dept)\s*[:：]\s*(.+)$", re.IGNORECASE), "department"),
    (re.compile(r"^(?:직책|직급|title|position)\s*[:：]\s*(.+)$", re.IGNORECASE), "position"),
    (re.compile(r"^(?:주소|address|addr)\s*[:：]\s*(.+)$", re.IGNORECASE), "address"),
]
# 이름과 직책의 분리는 korean_names에서 처리한다.


@dataclass
class Candidate:
    """화면에 보여 줄 하나의 분류 후보. score는 분류 규칙 점수다."""
    id: str
    source_line: int
    source_text: str
    text: str
    value: str
    predicted_type: str
    selected_type: str
    score: int
    reasons: list[str]
    ocr_confidence: float | None
    left: int | None
    top: int | None
    width: int | None
    height: int | None
    manual: bool = False


def _read_line(line):
    """Tesseract OCRLine, dict, 일반 문자열 모두 사용 가능."""
    if isinstance(line, str):
        return {"text": line, "confidence": None, "left": None, "top": None, "width": None, "height": None}
    if isinstance(line, dict):
        get = line.get
    else:
        get = lambda field, default=None: getattr(line, field, default)
    return {field: get(field) for field in ("text", "confidence", "left", "top", "width", "height")}


def _split_line(text):
    """필드 구분 기호 및 '홍길동 대표'처럼 확실한 짧은 결합 형태를 분리."""
    # 글자 사이에 점/가운뎃점이 인쇄된 짧은 이름만 연결한다.
    if re.fullmatch(r"[가-힣](?:\s*[·ㆍ.]\s*[가-힣]){1,3}", text.strip()):
        yield re.sub(r"[\s·ㆍ.]", "", text)
        return
    for part in FIELD_SEPARATOR.split(text):
        part = part.strip()
        if not part:
            continue
        yield from split_name_context(part)


def _find_patterns(part):
    """하나의 줄에 전화·이메일이 섞여 있어도 각각 따로 추출한다."""
    found = []
    occupied = []
    rules = (
        (EMAIL, "email", 99, "정확한 이메일 주소 패턴"),
        (WEBSITE, "website", 98, "http(s) 또는 www 웹사이트 패턴"),
        (PHONE, "phone", 98, "전화번호 숫자 패턴"),
        (BARE_DOMAIN, "website", 88, "도메인 주소 패턴"),
    )
    for pattern, kind, score, reason in rules:
        for match in pattern.finditer(part):
            start, end = match.span(1)
            if any(start < old_end and end > old_start for old_start, old_end in occupied):
                continue
            value = match.group(1).rstrip(".,;:)")
            field = "fax" if kind == "phone" and is_fax_number(part, start) else kind
            item_reason = reason + (" + Fax 라벨" if field == "fax" else "")
            found.append((start, end, value, field, score, item_reason))
            occupied.append((start, end))
    found.sort(key=lambda item: item[0])
    return found


def _remove_found_text(part, patterns):
    """정규식으로 잘라낸 값은 빈칸 처리하여 나머지 일반 문구를 분류한다."""
    letters = list(part)
    for start, end, *_ in patterns:
        for index in range(start, end):
            letters[index] = " "
    remaining = " ".join("".join(letters).split())
    # 'E-mail: abc@x.com'에선 E-mail 라벨 자체를 별도 후보로 만들지 않는다.
    # 'Tel: ... Fax: ...'처럼 값만 빼고 라벨이 여러 개 남을 수 있다.
    remaining_labels = re.sub(r"(?i)\b[EMTFW]\s*[:.]", "", remaining)
    labels_only = re.sub(
        r"(?i)\b(?:e[\s-]?mail|mail|fax|tel|telephone|mobile|cell|phone|web|website|url)\b|"
        r"메일|팩스|전화|휴대폰|핸드폰|홈페이지|[:：-]", "", remaining_labels
    ).strip()
    if PURE_LABEL.fullmatch(remaining) or not labels_only or remaining in (":", "/", "-"):
        return ""
    if patterns:
        # 값과 같은 줄에 남은 연락처 라벨만 제거한다. 다른 필드의 라벨은 건드리지 않는다.
        remaining = re.sub(r"(?i)\b(?:e[\s-]?mail|mail|fax|tel|telephone|mobile|cell|phone|web|website|url)\s*[:：.-]?\s*", " ", remaining)
        remaining = re.sub(r"(?i)\b[EMTFW]\s*[:.]", " ", remaining)
        remaining = re.sub(r"(?:이메일|메일|팩스|전화|휴대폰|핸드폰|홈페이지)\s*[:：-]?", " ", remaining)
        remaining = " ".join(remaining.split()).strip(" ,;:：")
    return remaining


def _prepare_parts(lines):
    pieces = []
    for line_index, raw in enumerate(lines):
        original = _read_line(raw)
        text = str(original.get("text") or "").strip()
        if not text:
            continue
        for part in _split_line(text):
            patterns = _find_patterns(part)
            for _, _, value, kind, score, reason in patterns:
                pieces.append({"line_index": line_index, "source": text, "part": value,
                               "fixed_type": kind, "score": score, "reason": reason, "ocr": original})
            remaining = _remove_found_text(part, patterns)
            if remaining:
                # 연락처 값 제거 후 이름/직책이 남아 있다면 한 번 더 분리한다.
                for value in split_name_context(remaining):
                    pieces.append({"line_index": line_index, "source": text, "part": value,
                                   "fixed_type": None, "score": 0, "reason": "", "ocr": original})
    return pieces


def classify_lines(lines):
    """OCR 줄의 목록을 분류한다. 반환값은 Streamlit 세션에 저장 가능한 dict 목록."""
    if isinstance(lines, str):
        lines = lines.splitlines()
    pieces = _prepare_parts(lines)
    heights = [float(p["ocr"]["height"]) for p in pieces if p["ocr"].get("height")]
    regular_height = median(heights) if heights else None
    role_lines = {p["line_index"] for p in pieces if looks_like_position(p["part"])}

    rows = []
    for index, piece in enumerate(pieces):
        value = piece["part"].strip()
        kind = piece["fixed_type"]
        if kind:
            score, reasons = piece["score"], [piece["reason"]]
        else:
            # 'Name: 홍길동', 'Company: NextLab' 같은 명시적 라벨을 먼저 처리.
            for label_pattern, label_type in EXPLICIT_LABELS:
                matched = label_pattern.match(value)
                if matched:
                    value = matched.group(1).strip()
                    kind, score, reasons = label_type, 96, ["필드 이름이 직접 명시됨"]
                    break

            if not kind:
                if is_email_hint(value):
                    kind, score = "email", 40
                    reasons = ["@ 또는 mail 포함 → 이메일 후보 (정확한 주소 형식 미확인)"]
                else:
                    current_line = piece["line_index"]
                    near_role = any(abs(current_line - other) <= 2 for other in role_lines)
                    height = piece["ocr"].get("height")
                    large = bool(regular_height and height and float(height) >= regular_height * 1.35)
                    kind, score, reasons = classify_context(value, near_role, large)

        ocr = piece["ocr"]
        candidate = Candidate(
            id=f"row_{index}", source_line=piece["line_index"], source_text=piece["source"],
            text=piece["part"], value=value,
            predicted_type=kind, selected_type=kind, score=score, reasons=reasons,
            ocr_confidence=ocr.get("confidence"), left=ocr.get("left"), top=ocr.get("top"),
            width=ocr.get("width"), height=ocr.get("height"),
        )
        rows.append(asdict(candidate))
    return refine_name_candidates(rows)


def classify_text(text):
    """좌표가 없는 일반 텍스트에서도 같은 알고리즘을 사용한다."""
    return classify_lines(str(text or "").splitlines())


def build_contact_fields(rows):
    """수정된 후보를 연락처 필드에 정리한다. 중복/잘못된 후보는 경고로 반환."""
    chosen = {}
    warnings = []
    for row in rows:
        kind = row.get("selected_type", "unknown")
        value = str(row.get("value") or "").strip()
        if not value or kind == "unknown":
            continue
        if kind == "email" and not EMAIL.fullmatch(value):
            warnings.append(f"'{value}': 이메일 유형이지만 유효한 주소 형식이 아니어서 제외")
            continue
        if kind not in FIELD_NAMES:
            continue
        if kind in chosen:
            # 사용자가 수동으로 수정한 값이 자동 후보보다 우선한다.
            earlier = chosen[kind]
            older_rank = (bool(earlier.get("manual")), int(earlier.get("score", 0)))
            new_rank = (bool(row.get("manual")), int(row.get("score", 0)))
            if new_rank > older_rank:
                warnings.append(f"{FIELD_NAMES[kind]} 중복: 기존 후보 대신 수정 후보를 선택")
                chosen[kind] = row
            else:
                warnings.append(f"{FIELD_NAMES[kind]} 중복: '{value}' 후보는 저장하지 않음")
        else:
            chosen[kind] = row

    fields = {}
    for kind, row in chosen.items():
        fields[kind] = str(row["value"]).strip()
        if kind == "name" and row.get("name_status") == "suggested" and not row.get("manual"):
            warnings.append("이름 자동 제안: " + fields[kind] + " · 원본에서 확인해 주세요.")
    return fields, warnings
