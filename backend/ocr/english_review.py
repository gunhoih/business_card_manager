"""검출된 명함 줄 중 영문 연락처를 선별해 보조 인식하고 안전하게 비교한다."""

from dataclasses import replace
import re
from time import monotonic

from backend.classifier.patterns import BARE_DOMAIN, EMAIL, PHONE, WEBSITE, is_fax_number

MAX_ENGLISH_CROPS = 6
HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
EMAIL_HINT = re.compile(r"@|\be[\s.-]?mail\b|이메일|메일|\bE\s*[:.]", re.I)
PHONE_HINT = re.compile(r"\b(?:tel(?:ephone)?|mobile|phone|cell|fax)\b|전화|휴대폰|팩스|\b[MTF]\s*[:.]", re.I)
WEB_HINT = re.compile(r"https?\s*[:/]|\bwww\b|\b(?:website|web|url)\s*[:.]|홈페이지", re.I)


def contact_values(text):
    """정규식에 맞는 값만 모은다. 형식이 맞아도 실제 값이 정확하다는 뜻은 아니다."""
    found = {}
    occupied = []
    for pattern, field in ((EMAIL, "email"), (WEBSITE, "website"),
                           (PHONE, "phone"), (BARE_DOMAIN, "website")):
        for match in pattern.finditer(text):
            start, end = match.span(1)
            if any(start < b and end > a for a, b in occupied):
                continue
            value = match.group(1).rstrip(".,;:)")
            kind = "fax" if field == "phone" and is_fax_number(text, start) else field
            if kind in ("phone", "fax"):
                value = re.sub(r"[^0-9+]", "", value)
            # Email local parts may be case-sensitive; don't collapse genuine differences.
            found.setdefault(kind, set()).add(value)
            occupied.append((start, end))
    return found


def expected_fields(text):
    expected = set(contact_values(text))
    if EMAIL_HINT.search(text):
        expected.add("email")
    if PHONE_HINT.search(text) or ("@" not in text and not HANGUL.search(text) and len(re.findall(r"[0-9]", text)) >= 7):
        if re.search(r"\bfax\b|팩스|\bF\s*[:.]", text, re.I):
            expected.add("fax")
        else:
            expected.add("phone")
    if WEB_HINT.search(text):
        expected.add("website")
    return expected


def _missing_fields(text):
    return expected_fields(text) - set(contact_values(text))


def _priority(line):
    values = contact_values(line.text)
    expected = expected_fields(line.text)
    if not expected:
        return 0
    # 독립된 'E-mail' 라벨만 영어로 다시 읽어도 값이 생길 수 없다.
    if not values and not re.search(r"[0-9@.]|[A-Za-z]{5,}", line.text):
        return 0
    if expected - set(values):
        return 300
    if line.confidence < 88:
        return 200
    # 이메일/URL은 한 글자 오류도 문제가 된다. 특히 혼동 문자가 있는 경우를 재검사.
    if any(re.search(r"[01OIl|]", value.split("@")[0])
           for value in values.get("email", set())):
        return 150
    if ("email" in values or "website" in values) and line.confidence < 96:
        return 100
    if line.confidence < 93 and ("phone" in values or "fax" in values):
        return 80
    return 0


def _has_unrelated_text(text, *, allow_malformed=False):
    """이메일/전화/URL과 명시 라벨 외에 남은 글자가 있으면 줄 전체 교체를 보류한다."""
    remaining = text
    for pattern in (EMAIL, WEBSITE, PHONE, BARE_DOMAIN):
        remaining = pattern.sub(" ", remaining)
    remaining = re.sub(r"(?i)\b(?:e[\s.-]?mail|mail|tel(?:ephone)?|mobile|phone|cell|fax|website|web|url)\b", " ", remaining)
    remaining = re.sub(r"(?i)\b[EMTFW]\s*[:.]", " ", remaining)
    if allow_malformed:
        # 실제 OCR에 있었던, 형식이 깨진 연락처 토큰만 제거한다. 이름/회사명은 보존한다.
        remaining = re.sub(r"[A-Za-z0-9._%+|-]+@[^\s;]+", " ", remaining)
        remaining = re.sub(r"(?i)(?:https?[:/]+|www[.,])[^\s;]+", " ", remaining)
        remaining = re.sub(r"(?<![A-Za-z0-9])\+?[0-9][0-9OIl|(). -]{5,}[0-9](?![A-Za-z0-9])", " ", remaining)
    return bool(re.search(r"[A-Za-z가-힣0-9]", remaining))


def compare_readings(old, new):
    """동일 영역의 두 판독 결과를 비교한다. 서로 다른 유효값은 자동 덮어쓰지 않는다."""
    before = contact_values(old.text)
    after = contact_values(new.text)
    expected = expected_fields(old.text)
    if not after:
        return old, "no_valid_result"
    if before and before == after:
        if old.confidence < 45 <= new.confidence and new.confidence >= 82 and not HANGUL.search(old.text) and not _has_unrelated_text(old.text, allow_malformed=True):
            return replace(old, confidence=new.confidence), "agreed"
        return old, "agreed"
    # 기존 유효값을 잃거나 변경하는 경우에는 자동 교체하지 않는다.
    if before and any(after.get(kind) != values for kind, values in before.items()):
        return old, "conflict"
    # 이름·회사·한국어 라벨 등이 있는 줄을 영어 모델 결과로 통째로 덮어쓰지 않는다.
    if HANGUL.search(old.text):
        return old, "review"
    if new.confidence < 82 or not (set(after) & expected) or set(after) - expected:
        return old, "review"
    if _has_unrelated_text(old.text, allow_malformed=True) or _has_unrelated_text(new.text):
        return old, "review"
    # 보조 인식은 기존 OCR 문자열을 정규식으로 조작하거나 추측해 만든 값이 아니다.
    # 원본이 불완전하고 실제 재인식에서 유효한 값이 나온 경우에만 반영한다.
    return replace(old, text=new.text, confidence=new.confidence), "recovered"


def review_english(image, lines, recognize, deadline):
    """필요한 최대 6개 영역만 확대 인식한다. 검출은 다시 수행하지 않는다."""
    updated = list(lines)
    checks, errors = [], []
    ranked = sorted(((i, _priority(line)) for i, line in enumerate(lines)),
                    key=lambda item: (-item[1], item[0]))
    candidates = [i for i, score in ranked if score > 0]
    selected = candidates[:MAX_ENGLISH_CROPS]
    if len(candidates) > MAX_ENGLISH_CROPS:
        errors.append("영문 보조 인식 건수 제한: 일부 영역은 수동 확인이 필요합니다.")
    for index in selected:
        remaining = deadline - monotonic()
        if remaining < 1:
            errors.append("영문 보조 인식 시간 예산을 소진했습니다.")
            break
        old = updated[index]
        # 재인식 영역은 실제 검출 박스에 가깝게 유지해 이웃 텍스트가 들어오지 않게 한다.
        pad_x = max(2, min(12, round(old.height * .12)))
        pad_y = max(1, min(5, round(old.height * .06)))
        box = (max(0, old.left - pad_x), max(0, old.top - pad_y),
               min(image.width, old.left + old.width + pad_x),
               min(image.height, old.top + old.height + pad_y))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        crop = image.crop(box)
        if crop.height > crop.width * 1.5:
            crop = crop.rotate(90, expand=True)
        if crop.width / crop.height > 45:
            checks.append({"line_index": index, "original": old.text, "alternate": "", "status": "no_valid_result"})
            continue
        try:
            result = recognize(crop, timeout=remaining, line_only=True, model="english")
        except (RuntimeError, ValueError) as error:
            errors.append(str(error))
            break  # 설치 오류 등 동일한 실패를 반복하지 않는다.
        if len(result.lines) != 1:
            checks.append({"line_index": index, "original": old.text, "alternate": "", "status": "no_valid_result"})
            continue
        new = result.lines[0]
        replacement, status = compare_readings(old, new)
        updated[index] = replacement
        checks.append({"line_index": index, "original": old.text, "alternate": new.text,
                       "original_confidence": old.confidence, "alternate_confidence": new.confidence,
                       "status": status})
    return updated, checks, errors


def review_warnings(checks):
    warnings = []
    for item in checks:
        if item["status"] in ("conflict", "review"):
            warnings.append(f"영문 재확인 필요: {item['original']} / 보조 판독: {item['alternate']}")
        elif item["status"] == "no_valid_result":
            warnings.append(f"영문 보조 판독에서 확인하지 못함: {item['original']}")
    return warnings
