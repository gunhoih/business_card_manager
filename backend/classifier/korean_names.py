"""한국 명함의 이름 후보를 원문, 글자 크기, 실제 위치 및 직책으로 비교한다.
점수는 경험적 우선순위이며 인식 정확도 확률이 아니다.
"""

import re
from statistics import median

# 성씨 목록은 힌트일 뿐, 목록 밖 이름을 임의로 교정하거나 생성하지 않는다.
SURNAMES = set("김이박최정강조윤장임한오서신권황안송전홍유고문양손배백허남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용봉경피사부가복태목형팽갈제빈단종점독호상좌승간감견동온빙범춘야")
COMPOUND_SURNAMES = ("남궁", "황보", "제갈", "선우", "사공", "서문", "독고", "동방", "어금", "망절")
ROLE = re.compile(r"(?:대표\s*이사|이사장|부회장|회장|위원장|원장|소장|부사장|사장|대표|전무|상무|이사|본부장|부문장|실장|팀장|파트장|센터장|지점장|과장|차장|부장|대리|사원|인턴|수석\s*연구원|책임\s*연구원|선임\s*연구원|연구원|연구위원|교수|변호사|건축사|기술사|회계사|세무사|매니저|책임|선임|수석|주임|CEO|CTO|CFO|COO|Director|Manager|Engineer|Lead)", re.I)
# 짧은 회사명/상호는 이름과 특히 혼동하기 쉬우므로 자동 확정을 피한다.
NOT_NAMES = {"삼성", "현대", "한화", "신한", "하나", "우리", "국민", "롯데", "두산", "한진", "한솔", "한빛", "대상", "동아", "포스코", "서울", "인천", "경기", "한국", "대한", "코리아", "명함", "연락처", "전화", "메일", "주소", "회사", "대표", "이름", "성명", "영업", "기술", "설계", "개발", "연구", "사업", "경영", "관리", "총무", "마케팅", "고객", "팩스"}
ORG_WORDS = re.compile(r"㈜|\(주\)|주식회사|유한회사|대학교|대학원|병원|연구소|엔지니어링|솔루션|시스템|전자|건설|산업|테크|센터|사업부|연구실|본부|(?:팀|부서)$")
HANGUL = re.compile(r"[가-힣]{2,4}")


def normalize_name(text):
    """'김 민 수' → '김민수'. 한글 외 문자 또는 다섯 글자 이상은 자동 후보 제외."""
    compact = re.sub(r"\s+", "", str(text or "").strip())
    if not HANGUL.fullmatch(compact) or compact in NOT_NAMES or ORG_WORDS.search(compact):
        return ""
    if ROLE.fullmatch(compact):
        return ""
    return compact


def common_surname(name):
    return bool(name) and (name[0] in SURNAMES or name.startswith(COMPOUND_SURNAMES))


def is_role(text):
    value = str(text or "").strip()
    match = ROLE.search(value)
    if not match:
        return False
    # 정확한 직책 또는 '기술팀장', '영업부 부장' 등 직책이 끝에 오는 표현.
    return bool(re.fullmatch(r"[가-힣A-Za-z0-9·& /-]{0,20}" + ROLE.pattern, value, re.I))


def split_name_role(text):
    """직책 전체 일치를 우선하고, 공백으로 분리된 부서+직책은 그 다음에 판단한다."""
    text = str(text or "").strip()
    qualified = []
    for index in range(1, len(text)):
        left, right = text[:index].strip(), text[index:].strip()
        if not left or not right:
            continue
        boundary = text[index-1:index].isspace() or text[index:index+1].isspace()
        name = normalize_name(left)
        if name and common_surname(name):
            if ROLE.fullmatch(right):
                return name, right
            if boundary and is_role(right):
                qualified.append((name, right))
        name = normalize_name(right)
        if name and common_surname(name):
            if ROLE.fullmatch(left):
                return left, name
            if boundary and is_role(left):
                qualified.append((left, name))
    # 이름 3음절을 우선하고, 여전히 여러 후보라면 임의로 분리하지 않는다.
    if qualified:
        unique = list(dict.fromkeys(qualified))
        if len(unique) == 1:
            return unique[0]
        typical = [pair for pair in unique if any(len(item) == 3 and normalize_name(item) == item for item in pair)]
        if len(typical) == 1:
            return typical[0]
    return None


def _geometry(row):
    values = [row.get(key) for key in ("left", "top", "width", "height")]
    if any(value is None for value in values):
        return None
    x, y, w, h = values
    return (float(x), float(y), float(w), float(h)) if w > 0 and h > 0 else None


def _near_role(row, role):
    if row.get("source_line") == role.get("source_line"):
        return True
    a, b = _geometry(row), _geometry(role)
    if not a or not b:
        return abs(row.get("source_line", 0) - role.get("source_line", 0)) <= 1
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    h = max(ah, bh, 1)
    horizontal_gap = max(0, bx - ax - aw, ax - bx - bw)
    vertical_gap = max(0, by - ay - ah, ay - by - bh)
    return horizontal_gap <= 5 * h and vertical_gap <= 2.5 * h


def refine_name_candidates(rows):
    """모든 줄을 비교해 최대 한 개만 자동 선택한다. 다른 후보는 검토 가능한 미분류로 남긴다."""
    if not rows:
        return rows
    # 명시적인 Name:/성명:은 기존 우선순위를 유지한다.
    explicit = [row for row in rows if row.get("predicted_type") == "name" and row.get("score") == 96]
    roles = [row for row in rows if row.get("predicted_type") == "position" and is_role(row.get("value"))]
    heights = [float(row["height"]) for row in rows if row.get("height") and row.get("predicted_type") not in ("name", "unknown")]
    if not heights:
        heights = [float(row["height"]) for row in rows if row.get("height")]
    typical = median(heights) if heights else None
    has_contact = any(row.get("predicted_type") in ("phone", "email") for row in rows)
    has_company = any(row.get("predicted_type") == "company" for row in rows)
    candidates = []
    for row in rows:
        kind = row.get("predicted_type")
        if row in explicit or kind in ("company", "address", "phone", "fax", "email", "website"):
            continue
        original = str(row.get("value") or "")
        name = normalize_name(original)
        if not name or (kind == "position" and is_role(original)):
            # 기존 단순 규칙에서 짧은 상호를 이름으로 잡았어도 자동 확정하지 않는다.
            if kind == "name" and HANGUL.fullmatch(re.sub(r"\s+", "", original)):
                row["predicted_type"] = "unknown"
                row["selected_type"] = "unknown"
                row["reasons"].append("이름과 혼동하기 쉬운 상호/직책: 검토 필요")
            continue
        if kind == "department" and not common_surname(name):
            continue
        confidence = row.get("ocr_confidence")
        score = 42 if common_surname(name) else 24
        reasons = ["한글 이름 형태" + (" 및 성씨 힌트" if common_surname(name) else " (성씨 근거 부족)")]
        if len(name) == 3:
            score += 10
        elif len(name) == 4:
            score += 6
        else:
            score -= 8
        near = any(_near_role(row, role) for role in roles if role is not row)
        if near:
            score += 28
            reasons.append("인접한 직책")
        height = row.get("height")
        large = bool(typical and height and height >= typical * 1.3)
        if large:
            score += 23
            reasons.append("상대적으로 큰 글자")
        if has_contact:
            score += 6
        if has_company:
            score += 7
        if confidence is not None:
            if confidence >= 85:
                score += 5
            elif confidence < 45:
                score -= 25
                reasons.append("OCR 신뢰도 낮음")
        # 이름만 읽힌 경우에는 성씨 형태만으로 확정하지 않는다.
        # 두 글자 이름은 직책과 크기 모두 또는 명시 라벨을 요구한다.
        eligible = (score >= 68 and (near or large or (has_contact and has_company))
                    and (len(name) != 2 or (near and large))
                    and (confidence is None or confidence >= 45))
        row["name_score"] = min(100, max(0, score))
        row["name_candidate"] = name
        row["reasons"] = list(row.get("reasons") or []) + reasons
        if kind in ("unknown", "name", "position"):
            row["predicted_type"] = "unknown"
            row["selected_type"] = "unknown"
        candidates.append((score, eligible, row, name))

    candidates.sort(key=lambda item: item[0], reverse=True)
    for rank, (_, _, row, _) in enumerate(candidates[:3], start=1):
        row["name_rank"] = rank
        row["reasons"].append(f"이름 후보 {rank}순위 · 자동 판단 점수 {row['name_score']}")
    if not explicit and candidates:
        score, eligible, row, name = candidates[0]
        competing = next((item for item in candidates[1:] if item[3] != name), None)
        if eligible and (not competing or score - competing[0] >= 9):
            row.update(value=name, predicted_type="name", selected_type="name", score=min(score, 95))
            row["reasons"].append("명함 전체의 이름 후보 비교에서 선택")
        else:
            row["reasons"].append("이름 확정 보류: 후보 충돌 또는 근거 부족")
    # 낮은 문자 신뢰도는 원문과 후보에 남기되 자동 저장 대상으로 사용하지 않는다.
    for row in rows:
        confidence = row.get("ocr_confidence")
        if confidence is not None and confidence < 35 and row.get("selected_type") != "unknown":
            row["selected_type"] = "unknown"
            row["reasons"].append("낮은 OCR 신뢰도: 수동 검토 필요")
    return rows
