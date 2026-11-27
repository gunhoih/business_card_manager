"""한국 명함의 이름 후보를 원문, 글자 크기, 실제 위치 및 직책으로 비교한다.
점수는 경험적 우선순위이며 인식 정확도 확률이 아니다.
"""

import re
from statistics import median
from unicodedata import normalize

# 성씨 목록은 힌트일 뿐, 목록 밖 이름을 임의로 교정하거나 생성하지 않는다.
SURNAMES = set("김이박최정강조윤장임한오서신권황안송전홍유고문양손배백허남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용봉경피사부가복태목형팽갈제빈단종점독호상좌승간감견동온빙범춘야")
COMPOUND_SURNAMES = ("남궁", "황보", "제갈", "선우", "사공", "서문", "독고", "동방", "어금", "망절")
ROLE = re.compile(r"(?:대표\s*이사|이사장|부회장|회장|위원장|원장|소장|부사장|사장|대표|전무|상무|이사|본부장|부문장|실장|팀장|파트장|센터장|지점장|과장|차장|부장|대리|사원|인턴|수석\s*연구원|책임\s*연구원|선임\s*연구원|연구원|연구위원|교수|변호사|건축사|기술사|회계사|세무사|매니저|책임|선임|수석|주임|CEO|CTO|CFO|COO|Director|Manager|Engineer|Lead)", re.I)
# 짧은 회사명/상호는 이름과 특히 혼동하기 쉬우므로 자동 확정을 피한다.
NOT_NAMES = {"삼성", "현대", "한화", "신한", "하나", "우리", "국민", "롯데", "두산", "한진", "한솔", "한빛", "대상", "동아", "포스코", "서울", "인천", "경기", "한국", "대한", "코리아", "명함", "연락처", "전화", "메일", "주소", "회사", "대표", "이름", "성명", "영업", "기술", "설계", "개발", "연구", "사업", "경영", "관리", "총무", "마케팅", "고객", "팩스"}
ORG_WORDS = re.compile(r"㈜|\(주\)|주식회사|유한회사|대학교|대학원|병원|연구소|엔지니어링|솔루션|시스템|전자|건설|산업|테크|센터|사업부|연구실|본부|제약|약품|증권|보험|은행|금융|물산|컨설팅|항공|유통|무역|(?:팀|부서)$")
HANGUL = re.compile(r"[가-힣]{2,4}")


# 직책 접미사만으로 사람 이름을 직책으로 판단하지 않는다.
DEPARTMENT_END = re.compile(r"(?:팀|사업부|본부|연구실|센터|부서|부|실|그룹|파트)$")
ROLE_PREFIX = re.compile(r"(?:영업|개발|설계|기술|건축|연구|인사|재무|기획|경영|관리|사업|전략|마케팅|생산|품질|지원|운영|고객|총무|디자인|안전|전산|전문|수석|선임|책임)")
ENGLISH_NAME = re.compile(r"[A-Za-z][A-Za-z'-]{0,24}(?:[ .-]+[A-Za-z][A-Za-z'-]{0,24}){1,4}")
ENGLISH_ORG = re.compile(r"\b(?:inc|ltd|corp|company|corporation|group|team|engineering|engineer|construction|design|solutions?|systems?|technology|technologies|university|bank|center|centre|studio|office|service|services|marketing|management|director|manager|lead|chief|officer|sales|tel|fax|mobile|email|address|road|street|floor|www|http|co)\b", re.I)
NAME_LABEL = re.compile(r"^(?:성명|이름|name)(?:\s*[:：=]\s*|\s+)(.+)$", re.I)
OTHER_LABEL = re.compile(r"^(?:회사|소속|company|organization|부서|department|dept|직책|직급|title|position|주소|address|addr)\s*[:：]", re.I)
AMBIGUOUS_SUFFIXES = ("주임", "선임", "수석", "책임", "대리", "이사")


def normalize_name(text):
    """원문에 있는 2~4음절만 결합한다. 한글 철자를 추측해서 교정하지 않는다."""
    compact = re.sub(r"\s+", "", normalize("NFC", str(text or "")).strip(" \t()[]·,，."))
    if not HANGUL.fullmatch(compact) or compact in NOT_NAMES or ORG_WORDS.search(compact):
        return ""
    if ROLE.fullmatch(compact):
        return ""
    return compact


def common_surname(name):
    return bool(name) and (name[0] in SURNAMES or name.startswith(COMPOUND_SURNAMES))


def is_role(text):
    value = str(text or "").strip()
    if ROLE.fullmatch(value):
        return True
    # '김주임'이나 '김진수석' 같은 이름의 일부를 직책으로 단정하지 않는다.
    for index in range(1, len(value)):
        prefix, suffix = value[:index].strip(), value[index:].strip()
        if not ROLE.fullmatch(suffix):
            continue
        if DEPARTMENT_END.search(prefix) or ROLE_PREFIX.search(prefix):
            return True
        if value[index-1:index].isspace() and re.fullmatch(r"[A-Za-z]+(?:[ &/-]+[A-Za-z]+)*", prefix):
            return True
        if value[index-1:index].isspace() and len(prefix) >= 5:
            return True
    return False


def _department(text):
    value = text.strip()
    return bool(value and (DEPARTMENT_END.search(value) or ROLE_PREFIX.fullmatch(value))
                and not ROLE.fullmatch(value))


def _english_name(text):
    return bool(ENGLISH_NAME.fullmatch(text.strip()) and not ENGLISH_ORG.search(text))


def split_name_role(text):
    """명확한 직책/이름 조합을 분리한다. 붙여 쓴 애매한 짧은 이름은 보존한다."""
    text = str(text or "").strip()
    # 띄어쓰기 없는 '김진수석'이나 '김주임'은 이름일 수도 있으므로 자르지 않는다.
    whole = normalize_name(text)
    if whole and not re.search(r"\s", text) and whole.endswith(AMBIGUOUS_SUFFIXES):
        return None
    if ROLE.fullmatch(text) or (is_role(text) and not re.search(r"\s", text)):
        return None
    possible = []
    for index in range(1, len(text)):
        left, right = text[:index].strip(" ,，:：()[]"), text[index:].strip(" ,，:：()[]")
        if not left or not right:
            continue
        boundary = bool(re.search(r"[\s,，:：()\[\]]", text[index-1:index+1]))
        for name_raw, role, reverse in ((left, right, False), (right, left, True)):
            name = normalize_name(name_raw)
            if not name or not common_surname(name):
                continue
            if not ROLE.fullmatch(role) and not (boundary and is_role(role)):
                continue
            score = (20 if boundary else 0) + (10 if ROLE.fullmatch(role) else 0)
            score += 4 if len(name) == 3 else 0
            pair = (role, name) if reverse else (name, role)
            possible.append((score, pair))
    if not possible:
        return None
    possible.sort(key=lambda item: item[0], reverse=True)
    best_score, best = possible[0]
    if any(score == best_score and pair != best for score, pair in possible):
        return None
    return best


def split_name_context(text):
    """부서/직책/영문 병기를 포함한 한 줄을 원문 기반으로 나눈다.

    이름처럼 보이는 임의의 부분 문자열을 만들지 않고 명확한 경계가 있는 경우만 분리한다.
    """
    text = str(text or "").strip()
    if OTHER_LABEL.match(text):
        return [text]
    label = NAME_LABEL.fullmatch(text)
    if label:
        value = label.group(1).strip()
        # 명시 라벨도 회사·영문 병기와 함께 나올 수 있다.
        if normalize_name(value) or _english_name(value):
            return ["이름: " + value]
        pieces = split_name_context(value)
        if len(pieces) > 1:
            for index, part in enumerate(pieces):
                if normalize_name(part) or _english_name(part):
                    pieces[index] = "이름: " + part
                    return pieces
        return ["이름: " + value]
    role_pair = split_name_role(text)
    if role_pair:
        return list(role_pair)
    # 괄호/쉼표/공백을 경계로 하되 나머지가 직책, 부서 또는 영문 이름일 때만 분리.
    parts = []
    for match in re.finditer(r"[\s,，()\[\]：:]+", text):
        left = text[:match.start()].strip(" ,，()[]：:")
        right = text[match.end():].strip(" ,，()[]：:")
        for name_raw, other, reverse in ((left, right, False), (right, left, True)):
            name = normalize_name(name_raw)
            if not name or not common_surname(name) or not other:
                continue
            # 회사명 뒤에 사람 이름이 별도로 붙은 경우도 분리한다.
            # '김민수 건축사사무소'처럼 사람 이름을 포함한 상호는 함부로 자르지 않는다.
            organization = reverse and len(other) >= 4 and bool(ORG_WORDS.search(other))
            if _department(other) or is_role(other) or _english_name(other) or organization:
                pair = [other, name] if reverse else [name, other]
                # 이름과 부서의 구분이 불명확할 때는 3음절 및 확실한 직책을 우선한다.
                strength = (8 if len(name) == 3 else 0) + (5 if is_role(other) else 0)
                parts.append((strength, pair))
    if parts:
        parts.sort(key=lambda item: item[0], reverse=True)
        strength, best = parts[0]
        if not any(score == strength and pair != best for score, pair in parts):
            return best
    # 영문과 한글 사이 공백이 없는 OCR 결과도 언어 전환 경계를 이용한다.
    match = re.fullmatch(r"([가-힣]{2,4})([A-Za-z][A-Za-z .'-]+)", text)
    if match and normalize_name(match[1]) and _english_name(match[2]):
        return [match[1], match[2].strip()]
    return [text]


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


# 로마자 표기 비교는 관측된 영문/이메일이 있는 경우에만 점수를 보강한다.
# 일치하지 않는다고 이름을 감점하거나 이메일에서 새 이름을 생성하지 않는다.
_SURNAME_ROMAN = {
    "김": ("kim", "gim"), "이": ("lee", "yi", "i", "rhee"),
    "박": ("park", "bak", "pak"), "최": ("choi", "choe"),
    "정": ("jung", "jeong", "chung"), "조": ("cho", "jo"),
    "강": ("kang", "gang"), "윤": ("yoon", "yun"),
    "임": ("lim", "im"), "유": ("yu", "yoo", "ryu"),
    "오": ("oh", "o"), "신": ("shin", "sin"), "한": ("han",),
    "장": ("jang", "chang"), "권": ("kwon", "gwon"),
    "홍": ("hong",), "배": ("bae", "pae"), "서": ("seo", "suh"),
    "우": ("woo", "u"), "송": ("song",), "문": ("moon", "mun"),
    "안": ("ahn", "an"), "심": ("shim", "sim"), "황": ("hwang",),
    "남궁": ("namgung", "namkoong"), "선우": ("seonwoo", "sunwoo"),
    "황보": ("hwangbo",), "제갈": ("jegal",),
}
_GIVEN_ROMAN = {"수": ("su", "soo"), "준": ("jun", "joon"), "영": ("yeong", "young"),
                "현": ("hyeon", "hyun"), "석": ("seok", "suk"), "희": ("hui", "hee"),
                "우": ("u", "woo"), "경": ("gyeong", "kyung"), "정": ("jeong", "jung"),
                "성": ("seong", "sung"), "지": ("ji", "jee"), "혁": ("hyeok", "hyuk"),
                "진": ("jin", "jean"), "연": ("yeon", "yun")}
_INITIAL = ("g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h")
_VOWEL = ("a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i")
_FINAL = ("", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t")


def _roman_syllable(char):
    number = ord(char) - ord("가")
    return _INITIAL[number // 588] + _VOWEL[number % 588 // 28] + _FINAL[number % 28]


def _roman_keys(name):
    from itertools import product
    surname = next((part for part in COMPOUND_SURNAMES if name.startswith(part) and len(name) > len(part)), name[0])
    given = name[len(surname):]
    if not given:
        return set()
    surnames = _SURNAME_ROMAN.get(surname, ("".join(_roman_syllable(c) for c in surname),))
    given_parts = [_GIVEN_ROMAN.get(c, (_roman_syllable(c),)) for c in given]
    names = {"".join(parts) for parts in product(*given_parts)}
    return {value for family in surnames for first in names for value in (family + first, first + family)}


def _roman_key(text):
    return re.sub(r"[^a-z]", "", text.casefold())


def _english_evidence(rows):
    english, emails = set(), set()
    for row in rows:
        value = str(row.get("value") or "")
        confidence = row.get("ocr_confidence")
        if confidence is not None and confidence < 55:
            continue
        if row.get("predicted_type") == "email" and "@" in value:
            local = value.split("@", 1)[0]
            if re.fullmatch(r"[A-Za-z._-]+", local):
                emails.add(_roman_key(local))
        elif row.get("predicted_type") in ("name", "unknown") and _english_name(value):
            english.add(_roman_key(value))
    return english, emails


def refine_name_candidates(rows):
    """후보 생성과 최종 이름 선택을 분리한다. 유력한 값은 제안하고 모호한 값은 검토로 남긴다."""
    if not rows:
        return rows
    roles = [row for row in rows if row.get("predicted_type") == "position"]
    heights = [row["height"] for row in rows if row.get("height") and row.get("predicted_type") in
               ("phone", "email", "address", "fax", "website", "position", "department")]
    typical = median(heights) if heights else None
    contact = any(row.get("predicted_type") in ("phone", "email") for row in rows)
    company = any(row.get("predicted_type") == "company" for row in rows)
    english, emails = _english_evidence(rows)
    candidates = []
    for row in rows:
        kind = row.get("predicted_type")
        value = str(row.get("value") or "").strip()
        explicit = kind == "name" and row.get("score") == 96
        # 다른 필드가 명시적으로 지정된 경우 이름 후보로 재분류하지 않는다.
        if row.get("score") == 96 and kind != "name":
            continue
        confidence = row.get("ocr_confidence")
        name = normalize_name(value)
        compact = re.sub(r"\s+", "", value)
        ambiguous_brand = False
        if not name and compact in NOT_NAMES and HANGUL.fullmatch(compact) and common_surname(compact):
            if _roman_keys(compact) & (english | emails):
                name = compact
                ambiguous_brand = True
        # 명시 라벨은 성씨/길이/상호 목록보다 우선한다. 원문은 그대로 유지한다.
        if explicit:
            name = re.sub(r"\s+", "", value) if HANGUL.fullmatch(re.sub(r"\s+", "", value)) else value
        korean = bool(name and HANGUL.fullmatch(name))
        if not name and _english_name(value):
            name = value
        if not explicit and kind in ("company", "address", "phone", "fax", "email", "website", "position"):
            continue
        if not name:
            if kind == "name":
                row.update(predicted_type="unknown", selected_type="unknown")
            continue
        if not korean and not explicit and not _english_name(name):
            continue
        near = any(_near_role(row, role) for role in roles if role is not row)
        large = bool(typical and row.get("height") and row["height"] >= typical * 1.25)
        surname = korean and common_surname(name)
        roman = _roman_keys(name) if korean else {_roman_key(name)}
        english_match = korean and bool(roman & english)
        email_match = bool(roman & emails)
        split = row.get("source_text", "").strip() != row.get("text", "").strip()
        ambiguous_role = korean and name.endswith(AMBIGUOUS_SUFFIXES) and not split
        score = 48 if surname else (33 if korean else 36)
        reasons = ["원문 이름 형태" + (" 및 성씨 힌트" if surname else "")]
        if korean:
            score += {2: -5, 3: 12, 4: 8}[len(name)]
        if near:
            score += 18
            reasons.append("직책과 인접")
        if large:
            score += 14
            reasons.append("상대적으로 큰 글자")
        if split and korean:
            score += 8
            reasons.append("같은 줄의 다른 필드와 분리")
        if contact:
            score += 5
        if company:
            score += 3
        if english_match:
            score += 25
            reasons.append("영문 병기와 로마자 표기 일치")
        if email_match:
            score += 23
            reasons.append("이메일 아이디와 로마자 표기 일치")
        if confidence is not None:
            if confidence >= 85:
                score += 8
            elif confidence < 55:
                score -= 15
                reasons.append("낮은 문자 신뢰도")
        if kind == "department" and not explicit:
            score -= 18
        if ambiguous_role:
            score -= 9
            reasons.append("직책 접미사와 겹치는 이름 형태")
        if explicit:
            score = 110
            reasons.append("이름 라벨 직접 확인")
        # 3~4음절 일반 이름은 높은 문자 신뢰도만으로도 제안 가능.
        # 두 음절/희귀 성씨/영문 이름에는 문맥 근거 하나 이상을 요구한다.
        context = near or large or split or english_match or email_match
        if korean and len(name) == 2 and surname and contact and company:
            context = True
        eligible = score >= 58 and (confidence is None or confidence >= 55)
        if not korean or len(name) == 2 or not surname:
            eligible = eligible and context
        if kind == "department" and not (english_match or email_match):
            eligible = False
        if ambiguous_brand and not explicit:
            # 한솔처럼 상호로도 쓰이는 이름은 근거가 있더라도 후보로만 표시한다.
            eligible = False
            reasons.append("상호와 겹치는 이름: 직접 확인 필요")
        if explicit:
            eligible = confidence is None or confidence >= 35
        strong = explicit or (score >= 82 and context and not ambiguous_role)
        row.update(name_candidate=name, name_score=min(100, max(0, score)), name_status="review")
        row["reasons"] = list(row.get("reasons") or []) + reasons
        if kind in ("unknown", "name"):
            row.update(predicted_type="unknown", selected_type="unknown")
        candidates.append({"score": score, "eligible": eligible, "strong": strong, "row": row,
                           "name": name, "korean": korean, "explicit": explicit})
    # 확정 가능한 후보를 먼저 비교한다. 높은 점수지만 부적격인 후보가 전체를 막지 않는다.
    candidates.sort(key=lambda c: (c["eligible"], c["explicit"], c["korean"], c["score"]), reverse=True)
    unique = []
    seen = set()
    for item in candidates:
        key = re.sub(r"\s+", "", item["name"]).casefold()
        if key not in seen:
            unique.append(item)
            seen.add(key)
    for rank, item in enumerate(unique[:3], start=1):
        item["row"]["name_rank"] = rank
        item["row"]["reasons"].append(f"이름 후보 {rank}순위 · 규칙 점수 {item['row']['name_score']}")
    eligible = [item for item in unique if item["eligible"]]
    explicit = [item for item in eligible if item["explicit"]]
    korean = [item for item in eligible if item["korean"]]
    pool = explicit or korean or eligible
    # 한글 후보가 모호하다고 영문 후보를 대신 저장하지 않는다.
    if pool:
        best = pool[0]
        competing = pool[1] if len(pool) > 1 else None
        if not competing or (not best["explicit"] and best["score"] - competing["score"] >= 7):
            row = best["row"]
            row.update(value=best["name"], predicted_type="name", selected_type="name",
                       score=min(100, best["score"]), name_status="strong" if best["strong"] else "suggested")
            row["reasons"].append("유력한 이름 자동 입력" if best["strong"] else "이름 후보 자동 제안: 확인 필요")
        else:
            best["row"]["reasons"].append("이름 후보 간 근거가 비슷하여 확정 보류")
    for row in rows:
        confidence = row.get("ocr_confidence")
        if confidence is not None and confidence < 35 and row.get("selected_type") != "unknown":
            row["selected_type"] = "unknown"
            row["reasons"].append("낮은 OCR 신뢰도: 수동 검토 필요")
    return rows
