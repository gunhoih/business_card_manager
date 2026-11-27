"""이름·회사·직책 등 규칙과 주변 줄로 분류한다.

점수는 분류를 위한 우선순위 점수(0~100)이며, 통계적 정확도/확률이 아니다.
규칙을 이해하고 바꾸기 쉽도록 의도적으로 단순한 if문으로 작성했다.
"""

import re

from .korean_names import is_role

COMPANY = re.compile(
    r"㈜|\(주\)|주식회사|유한회사|(?:\bInc\.?\b)|(?:\bCorp\.?\b)|"
    r"(?:\bLLC\b)|(?:\bLtd\.?\b)|(?:\bCo\.?\s*,?\s*Ltd\.?\b)|"
    r"사단법인|재단법인|대학교|대학원|병원|공사",
    re.IGNORECASE,
)
COMPANY_WEAK = re.compile(
    r"전자|테크|솔루션|시스템|엔지니어링|건설|산업|스튜디오|연구소|"
    r"\b(?:tech|labs?|solutions?|systems?)\b",
    re.IGNORECASE,
)
POSITION = re.compile(
    r"대표이사|대표|사장|부사장|전무|상무|이사|본부장|실장|팀장|"
    r"과장|차장|부장|대리|사원|인턴|연구원|교수|변호사|"
    r"책임연구원|선임연구원|수석연구원|"
    r"\b(?:CEO|CTO|CFO|COO|Director|Manager|Engineer|Lead)\b",
    re.IGNORECASE,
)
DEPARTMENT = re.compile(
    r"(?:팀|사업부|본부|연구실|센터|부서|부|실)$|"
    r"\b(?:team|division|department|dept\.?|group)\b",
    re.IGNORECASE,
)
ADDRESS = re.compile(
    r"특별시|광역시|특별자치시|특별자치도|"
    r"(?:경기|강원|충청|전라|경상|제주)(?:도|북도|남도)|"
    r"[가-힣]{2,}(?:시|군|구)\s+[가-힣\d]|"
    r"[가-힣\d]+(?:대로|로|길)\s*\d+|"
    r"\b(?:street|st\.|road|rd\.|avenue|ave\.|suite|floor)\b",
    re.IGNORECASE,
)
KOREAN_NAME = re.compile(r"[가-힣]{2,4}")
ENGLISH_NAME = re.compile(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}")


def looks_like_position(text: str) -> bool:
    return is_role(text)


def classify_context(text: str, near_position: bool, is_large_text: bool):
    """규칙을 위에서부터 확인하고 (분류, 점수, 판단 근거)를 반환한다."""
    value = text.strip()
    if not value:
        return "unknown", 0, ["비어 있는 텍스트"]

    # 직책을 먼저 확인한다. '개발팀장'은 부서가 아니라 직책이다.
    if is_role(value):
        return "position", 91, ["직책 키워드 발견(예: 대표, 팀장, 연구원, CEO)"]

    if COMPANY.search(value):
        return "company", 94, ["회사·기관 표기 발견(예: (주), Inc., 대학교)"]

    if DEPARTMENT.search(value):
        return "department", 86, ["부서 접미사 발견(예: 팀, 본부, 실)"]

    if ADDRESS.search(value):
        return "address", 89, ["주소 표현 발견(예: 시·구, 도로명, Street)"]

    if COMPANY_WEAK.search(value):
        return "company", 76, ["회사명에 흔한 단어 발견(예: 테크, 시스템, Labs)"]

    if KOREAN_NAME.fullmatch(value) or ENGLISH_NAME.fullmatch(value):
        score = 43
        reasons = ["사람 이름처럼 보이는 글자 형태: +43"]
        if near_position:
            score += 31
            reasons.append("인접 줄에 직책이 있음: +31")
        if is_large_text:
            score += 6
            reasons.append("주변보다 글자가 큼: +6")
        if score >= 65:
            return "name", min(score, 100), reasons
        return "unknown", score, reasons + ["이름 근거가 부족해 자동 확정하지 않음"]

    return "unknown", 0, ["일치한 규칙이 없음 → 사용자가 분류 가능"]
