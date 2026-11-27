"""형태가 분명한 정보부터 인식한다. 외부 API/모델 의존성 없음."""

import re

# E-mail / 전화번호 / 웹사이트는 형태 자체로 비교적 정확하게 찾을 수 있다.
EMAIL = re.compile(
    r"(?<![\w.@])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w.@])"
)
PHONE = re.compile(
    r"(?<!\d)((?:\+82[\s.-]?(?:0)?|0)"
    r"(?:1[016789]|2|[3-6][1-5]|70|80|50)"
    r"[\s.-]?\d{3,4}[\s.-]?\d{4}|1[568]\d{2}[\s.-]?\d{4})(?!\d)"
)
WEBSITE = re.compile(
    r"(?<!\w)(https?://[^\s,;<>|]+|www\.[\w.-]+\.[A-Za-z]{2,}(?:/[^\s,;<>|]*)?)",
    re.IGNORECASE,
)
# http/www 없이 쓰인 회사 도메인도 지원. 확장자는 제한해 과잉 검출을 줄인다.
BARE_DOMAIN = re.compile(
    r"(?<![\w@])((?:[A-Za-z0-9-]+\.)+(?:co\.kr|go\.kr|ac\.kr|or\.kr|com|net|org|kr|io|ai|dev|biz|info|edu))(?![\w.-])",
    re.IGNORECASE,
)

EMAIL_HINT = re.compile(r"e[\s-]?mail|메일", re.IGNORECASE)
FAX_HINT = re.compile(r"fax|facsimile|팩스|\bF\s*[:.]", re.IGNORECASE)
PHONE_HINT = re.compile(r"tel(?:ephone)?|mobile|cell|phone|전화|휴대폰|핸드폰|\b[MT]\s*[:.]", re.IGNORECASE)

# 한 줄에 두 개의 필드가 쓰인 경우만 구분자로 나눈다.
# URL의 / 또는 e-mail의 . 은 보존해야 하므로 무조건 split('/') 하지 않는다.
FIELD_SEPARATOR = re.compile(r"\s*[|│•·]\s*|\s+[/]\s+")

# 값 추출 후 앞에 남는 'E-mail:', 'Tel:' 등의 라벨을 제거한다.
PURE_LABEL = re.compile(
    r"^(?:e[\s-]?mail|mail|메일|fax|팩스|tel|telephone|mobile|cell|phone|전화|휴대폰|핸드폰|web(?:site)?|url|홈페이지)\s*[:：-]?\s*$",
    re.IGNORECASE,
)


def is_email_hint(text: str) -> bool:
    """'@' 또는 'mail'이 있으면 이메일 후보. 실제 주소의 유효성과는 별개."""
    return "@" in text or "mail" in text.casefold() or bool(EMAIL_HINT.search(text))


def is_fax_number(full_line: str, phone_start: int) -> bool:
    """숫자 바로 앞의 가장 최근 라벨로 전화/FAX를 구분한다."""
    preceding = full_line[:phone_start]
    fax = list(FAX_HINT.finditer(preceding))
    phone = list(PHONE_HINT.finditer(preceding))
    if not fax:
        return False
    if not phone:
        return True
    return fax[-1].start() > phone[-1].start()
