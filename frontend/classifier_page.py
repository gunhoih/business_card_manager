"""OCR 다음 단계: 텍스트를 자동 분류하거나 각 후보를 수동으로 분류한다."""

import hashlib

import streamlit as st

from backend.classifier.service import FIELD_NAMES, build_contact_fields, classify_lines, classify_text
from backend.contact.csv_service import CONTACT_FIELDS
from frontend.state import set_extraction_result


def _current_ocr_preview():
    """새 이미지를 열었을 때 이전 명함의 OCR 정보를 잘못 사용하지 않는다."""
    preview = st.session_state.get("ocr_preview")
    image = st.session_state.scan_result_bytes or st.session_state.scan_image_bytes
    if not preview or not image:
        return None
    if preview.get("image_id") != hashlib.sha256(image).hexdigest():
        return None
    return preview


def _initialize_input():
    """OCR 실행/이미지 변경 시 입력을 갱신하고, 사용자의 편집은 유지한다."""
    preview = _current_ocr_preview()
    image_id = st.session_state.get("scan_image_id", "")
    preview_id = preview["image_id"] if preview else "no_ocr"
    source_key = f"{image_id}:{preview_id}"

    if st.session_state.get("classifier_source_key") != source_key:
        st.session_state["classifier_source_key"] = source_key
        st.session_state["classifier_input"] = st.session_state.get("scan_raw_text", "")
        st.session_state["classifier_rows"] = []
        st.session_state["classifier_analyzed_text"] = ""
        st.session_state["classifier_revision"] = st.session_state.get("classifier_revision", 0) + 1
        st.session_state.pop("classifier_last_result", None)
    return preview


def _analyze(mode, preview):
    text = st.session_state.get("classifier_input", "")
    if not text.strip():
        st.warning("먼저 OCR을 실행하거나 분석할 텍스트를 입력해 주세요.")
        return

    original_text = "\n".join(line.get("text", "") for line in preview["lines"]) if preview else ""
    # 사용자가 OCR 결과를 직접 수정한 경우 원래의 좌표·신뢰도를 재사용하지 않는다.
    if preview and text.strip() == original_text.strip():
        rows = classify_lines(preview["lines"])
        st.session_state["classifier_used_ocr_geometry"] = True
    else:
        rows = classify_text(text)
        st.session_state["classifier_used_ocr_geometry"] = False

    st.session_state["classifier_mode"] = mode
    if mode == "manual":
        for row in rows:
            row["selected_type"] = "unknown"

    st.session_state["classifier_rows"] = rows
    st.session_state["classifier_analyzed_text"] = text
    st.session_state["classifier_revision"] += 1
    st.session_state.pop("classifier_last_result", None)


def _classification_form():
    rows = st.session_state.get("classifier_rows", [])
    if not rows:
        return

    st.subheader("분류 결과 확인·수정")
    st.caption("분류 점수는 휴리스틱 점수이며 정확도(%)나 AI 확률이 아닙니다. 유형과 값은 직접 고칠 수 있습니다.")
    if st.session_state.get("classifier_analyzed_text") != st.session_state.get("classifier_input"):
        st.warning("분석 이후 원문을 바꿨습니다. '자동 분류' 또는 '수동 분류 시작'을 다시 눌러 주세요.")
        return

    revision = st.session_state["classifier_revision"]
    form_values = []
    with st.form(f"classifier_edit_form_{revision}"):
        for index, row in enumerate(rows):
            st.markdown(f"**{index + 1}. {row['source_text']}**")
            c1, c2, c3 = st.columns([1.2, 1, 2])
            with c1:
                selected = st.selectbox(
                    "분류 유형", options=list(FIELD_NAMES),
                    index=list(FIELD_NAMES).index(row["selected_type"]),
                    format_func=lambda name: FIELD_NAMES[name],
                    key=f"classifier_type_{revision}_{index}",
                )
            with c2:
                st.caption(f"자동 추천: {FIELD_NAMES[row['predicted_type']]}")
                st.caption(f"규칙 점수: {row['score']}/100")
                if row["ocr_confidence"] is not None:
                    st.caption(f"OCR 문자 신뢰도: {row['ocr_confidence']}%")
            with c3:
                value = st.text_input(
                    "저장할 값", value=row["value"], key=f"classifier_value_{revision}_{index}"
                )
                st.caption("근거: " + "; ".join(row["reasons"]))
            form_values.append((selected, value))
            st.divider()

        submitted = st.form_submit_button("수정 결과를 연락처 입력 폼에 반영", type="primary", width="stretch")

    if submitted:
        updated = []
        for old, (selected, value) in zip(rows, form_values):
            new = old.copy()
            new["selected_type"] = selected
            new["value"] = value.strip()
            new["manual"] = (
                bool(old.get("manual")) or selected != old["predicted_type"]
                or value.strip() != old["value"]
                or (st.session_state.get("classifier_mode") == "manual" and selected != "unknown")
            )
            updated.append(new)

        found, warnings = build_contact_fields(updated)
        # 분류되지 않은 필드는 기존 수동 입력값을 지우지 않는다.
        merged = {field: st.session_state.get(f"scan_{field}", "") for field in CONTACT_FIELDS}
        for field, value in found.items():
            if value:
                merged[field] = value

        raw_text = st.session_state["classifier_input"]
        set_extraction_result(raw_text, merged)
        st.session_state["classifier_rows"] = updated
        st.session_state["classifier_last_result"] = {"found": found, "warnings": warnings}
        st.success("분류 결과를 '명함 인식 → 텍스트 추출 및 정보 확인' 입력 폼에 반영했습니다.")

    result = st.session_state.get("classifier_last_result")
    if result:
        st.markdown("**이번에 반영한 필드**")
        if result["found"]:
            st.json({FIELD_NAMES[key]: value for key, value in result["found"].items()}, expanded=False)
        else:
            st.info("저장 가능한 후보가 없습니다. 분류 유형과 값을 확인해 주세요.")
        for warning in result["warnings"]:
            st.warning(warning)


def _reload_ocr_text():
    """버튼 콜백은 텍스트 입력 위젯을 만들기 전에 실행된다."""
    st.session_state["classifier_input"] = st.session_state.get("scan_raw_text", "")
    st.session_state["classifier_rows"] = []
    st.session_state["classifier_analyzed_text"] = ""
    st.session_state.pop("classifier_last_result", None)


def show_classifier_page():
    st.title("텍스트 분류")
    st.write("OCR에서 묶은 글자를 이름·회사·직책·이메일 등으로 자동 추천하고, 틀린 결과를 직접 수정합니다.")
    st.caption("로컬 규칙 엔진만 사용합니다. OpenAI API나 추가 AI 모델을 호출하지 않습니다.")

    preview = _initialize_input()
    if preview:
        st.info(f"현재 명함의 OCR 결과 {len(preview['lines'])}줄을 사용할 수 있습니다.")
    else:
        st.info("OCR 결과가 없어도 아래에 텍스트를 직접 입력해 실험할 수 있습니다.")

    st.text_area(
        "분석할 글자 (줄 단위, 자유롭게 수정 가능)",
        height=180, key="classifier_input",
        placeholder="(주)넥스트랩\n홍길동\nAI개발팀\n팀장\nE-mail: hong@example.com\nTel: 010-1234-5678",
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("자동 분류", type="primary", width="stretch"):
            _analyze("auto", preview)
    with c2:
        if st.button("수동 분류 시작", width="stretch"):
            _analyze("manual", preview)
    with c3:
        st.button("OCR 원문 다시 불러오기", width="stretch", on_click=_reload_ocr_text)

    if st.session_state.get("classifier_rows"):
        st.caption(
            "OCR 좌표·문자 신뢰도 사용" if st.session_state.get("classifier_used_ocr_geometry")
            else "수정된 텍스트 사용: 원본 OCR 좌표는 적용하지 않음"
        )
        _classification_form()
    else:
        st.caption("'자동 분류'는 규칙이 추천한 유형으로 시작하고, '수동 분류 시작'은 모두 미분류로 시작합니다.")

    with st.expander("분류 원리: 실제 코드에서 어떤 순서로 판단하나요?"):
        st.code(
            'if EMAIL.search(text):\n'
            '    field = "email"\n'
            'elif PHONE.search(text):\n'
            '    field = "phone"\n'
            'elif "@" in text or "mail" in text.lower():\n'
            '    field = "email"  # 형식이 틀리면 저장하지 않음\n'
            'elif "팀장" in text or "대표" in text:\n'
            '    field = "position"\n'
            'else:\n'
            '    field = "unknown"  # 주변 줄을 분석해 추가 판단',
            language="python",
        )
        st.caption("위는 이해를 위한 축약 코드입니다. 실제 전체 규칙은 backend/classifier/에 있습니다.")
