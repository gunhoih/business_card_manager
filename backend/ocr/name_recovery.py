"""분리된 한글 이름 영역 복구와 제한적인 이름 재인식."""

from dataclasses import replace
from time import monotonic
import re

from PIL import Image

from backend.classifier.korean_names import COMPOUND_SURNAMES, common_surname, normalize_name
from backend.ocr.english_review import expected_fields


MAX_NAME_CROPS = 3


def _fragment(line):
    text = re.sub(r"\s+", "", line.text)
    if not re.fullmatch(r"[가-힣]{1,3}", text) or line.confidence < 25:
        return ""
    if len(text) > 1 and not normalize_name(text):
        return ""
    return text


def _adjacent(left, right):
    """크기와 기준선이 비슷한 바로 옆 한글 영역만 결합한다."""
    small = min(left.height, right.height)
    large = max(left.height, right.height)
    if small <= 0 or small / large < 0.65:
        return False
    center_gap = abs(left.top + left.height / 2 - right.top - right.height / 2)
    gap = right.left - (left.left + left.width)
    return center_gap <= large * 0.30 and -small * 0.12 <= gap <= small * 0.65


def join_name_fragments(lines):
    """한 음절 이상이 별도 박스로 검출된 경우만 실제 인접 영역을 묶는다.

    최대 네 음절, 성씨 힌트, 위치 조건을 충족해야 한다. 원문 글자는 변경하지 않는다.
    """
    lines = sorted(lines, key=lambda line: (line.top, line.left))
    # 좌표 정렬은 y가 조금씩 다를 수 있으므로 x 기준으로 이웃을 찾는다.
    indexed = sorted(enumerate(lines), key=lambda item: (item[1].left, item[1].top))
    used = set()
    joined = []
    for index, line in indexed:
        first = _fragment(line)
        if index in used or not first or not common_surname(first):
            continue
        group = [(index, line, first)]
        current = line
        while True:
            nearby = [(i, other, _fragment(other)) for i, other in indexed
                      if i not in used and i not in {item[0] for item in group}
                      and other.left > current.left and _adjacent(current, other)]
            if not nearby:
                break
            i, other, text = min(nearby, key=lambda item: item[1].left)
            if not text:
                break
            # 이미 완성된 3음절 일반 이름에 옆의 한 글자를 붙이지 않는다.
            current_text = "".join(item[2] for item in group)
            if len(current_text) >= 2 and text in ("님", "씨"):
                break
            if len(group) == 1 and len(first) == 3:
                if not first.startswith(COMPOUND_SURNAMES):
                    break
            group.append((i, other, text))
            current = other
            if sum(len(item[2]) for item in group) > 4:
                break
        text = "".join(item[2] for item in group)
        if len(group) < 2 or not any(len(item[2]) == 1 for item in group):
            continue
        if not normalize_name(text) or not common_surname(text):
            continue
        # 완전한 이름 두 개의 결합은 피하고, 단일 음절 조각에 초점을 맞춘다.
        if sum(len(item[2]) > 1 for item in group) > 1:
            continue
        boxes = [item[1] for item in group]
        left = min(box.left for box in boxes)
        top = min(box.top for box in boxes)
        right = max(box.left + box.width for box in boxes)
        bottom = max(box.top + box.height for box in boxes)
        joined.append(replace(line, text=text, left=left, top=top, width=right-left,
                              height=bottom-top, confidence=min(box.confidence for box in boxes)))
        used.update(item[0] for item in group)
    return sorted([line for i, line in enumerate(lines) if i not in used] + joined,
                  key=lambda line: (line.top, line.left))


def _crop(image, line):
    pad = max(2, min(10, round(line.height * .10)))
    box = (max(0, line.left-pad), max(0, line.top-pad),
           min(image.width, line.left+line.width+pad), min(image.height, line.top+line.height+pad))
    crop = image.crop(box)
    if crop.width <= 1 or crop.height <= 1:
        return None
    if crop.height > crop.width * 1.5:
        crop = crop.rotate(90, expand=True)
    scale = min(3.0, 1200 / max(crop.size))
    if scale > 1:
        crop = crop.resize(tuple(round(n * scale) for n in crop.size), Image.Resampling.LANCZOS)
    return crop


def review_names(image, lines, rows, recognize, deadline):
    """확정이 어려운 이름/깨진 짧은 한글 줄만 최대 세 곳 재인식한다.

    서로 다른 정상 이름이 나오면 기존 원문을 유지하고 차이를 알려 준다.
    """
    selected = [row for row in rows if row.get("selected_type") == "name"]
    if selected and selected[0].get("name_status") == "strong" and (selected[0].get("ocr_confidence") or 0) >= 85:
        return list(lines), [], []
    ranked = sorted((row for row in rows if row.get("name_rank")), key=lambda row: row["name_rank"])
    indexes = []
    for row in ranked:
        index = row.get("source_line")
        if not isinstance(index, int) or not 0 <= index < len(lines):
            continue
        old = lines[index]
        # 한 줄 전체에 이름 외 정보가 있으면 줄 단위 교체하지 않는다.
        if not normalize_name(old.text) or expected_fields(old.text):
            continue
        if index not in indexes and old.confidence < 90:
            indexes.append(index)
    # 후보가 없더라도 짧고 깨진 한글 문자열은 원문 영역을 다시 읽는다.
    for index, line in enumerate(lines):
        if index in indexes or len(indexes) >= MAX_NAME_CROPS:
            continue
        text = re.sub(r"\s+", "", line.text)
        if not (2 <= len(text) <= 6 and re.search(r"[가-힣]", text) and not normalize_name(text)):
            continue
        if line.confidence >= 80 or expected_fields(line.text):
            continue
        related = [row for row in rows if row.get("source_line") == index]
        if not related or any(row.get("predicted_type") not in ("unknown", "name") for row in related):
            continue
        if line.width / max(1, line.height) > 8:
            continue
        indexes.append(index)
    updated, checks, errors = list(lines), [], []
    for index in indexes[:MAX_NAME_CROPS]:
        remaining = deadline - monotonic()
        if remaining < 1.5:
            break
        old = updated[index]
        crop = _crop(image, old)
        if crop is None:
            continue
        try:
            result = recognize(crop, timeout=remaining, line_only=True)
        except (RuntimeError, ValueError) as error:
            errors.append(str(error))
            break
        if len(result.lines) != 1:
            continue
        new = result.lines[0]
        name = normalize_name(new.text)
        if not name or new.confidence < 65:
            continue
        previous = normalize_name(old.text)
        status = "review"
        if previous == name:
            if new.confidence > old.confidence:
                updated[index] = replace(old, confidence=new.confidence)
            status = "agreed"
        elif not previous and common_surname(name) and new.confidence >= max(80, old.confidence + 12):
            updated[index] = replace(old, text=name, confidence=new.confidence)
            status = "recovered"
        checks.append({"line_index": index, "original": old.text, "alternate": name,
                       "status": status, "original_confidence": old.confidence,
                       "alternate_confidence": new.confidence})
    return updated, checks, errors
