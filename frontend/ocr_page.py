"""기존 스캔 결과를 로컬 OCR로 읽어 기존 연락처 입력 폼에 연결한다."""

import hashlib
import io

from PIL import Image, ImageDraw, ImageOps
import streamlit as st

from backend.classifier.service import build_contact_fields, classify_text
from backend.ocr.engine import check_ocr_ready, engine_label, select_engine
from frontend.ocr_flow import recognize_and_apply
from frontend.state import apply_auto_fields, next_ocr_revision


LANGUAGE_OPTIONS = {
    "한국어 + 영어": "kor+eng",
    "한국어 + 영어 + 한자(번체 모델)": "kor+eng+chi_tra",
}


def show_ocr_page():
    st.title("OCR 텍스트 인식")
    st.write("RapidOCR를 기본으로 명함 글자를 로컬에서 인식합니다. 이 단계에서는 AI API를 호출하지 않습니다.")

    image_bytes = st.session_state.scan_result_bytes or st.session_state.scan_image_bytes
    if not image_bytes:
        st.info("먼저 왼쪽의 '명함 인식' 메뉴에서 명함을 업로드하거나 스캔해 주세요.")
        return

    source_id = hashlib.sha256(image_bytes).hexdigest()
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")

    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.image(image, caption="OCR 대상: 보정한 명함을 우선 사용", width="stretch")

    with right:
        language_label = st.radio("인식할 언어", list(LANGUAGE_OPTIONS), horizontal=False)
        selected = LANGUAGE_OPTIONS[language_label]
        st.caption("사용 엔진: " + engine_label(selected))
        psm = 11
        if select_engine(selected) == "tesseract":
            psm_label = st.selectbox("글자 배치", ["흩어진 텍스트(명함 권장)", "하나의 텍스트 블록", "자동 페이지 분석"])
            psm = {"흩어진 텍스트(명함 권장)": 11, "하나의 텍스트 블록": 6, "자동 페이지 분석": 3}[psm_label]
        with st.expander("OCR 엔진 설치 상태"):
            try:
                st.success(check_ocr_ready(selected))
            except RuntimeError as error:
                st.warning(str(error))

        if st.button("명함 문자 인식", type="primary", width="stretch"):
            try:
                with st.spinner("이미지에서 글자를 읽고 분류하고 있습니다..."):
                    report = recognize_and_apply(
                        image_bytes, languages=LANGUAGE_OPTIONS[language_label], psm=psm
                    )
            except (RuntimeError, ValueError) as error:
                st.error(str(error))
            else:
                st.success(f"{len(report['lines'])}개 텍스트 줄을 인식해 자동 분류했습니다. '텍스트 분류'에서 직접 수정할 수 있습니다.")
                for warning in report["warnings"]:
                    st.warning(warning)

    preview = st.session_state.get("ocr_preview")
    if not preview or preview.get("image_id") != source_id:
        st.caption("OCR을 실행하면 추출된 글자와 줄별 인식 위치가 표시됩니다.")
        return

    st.subheader("인식된 텍스트")
    st.text_area("OCR 원문 · 필요하면 수정하세요", key="scan_raw_text", height=220)

    if st.button("수정한 원문에서 자동 분류 다시 실행"):
        text = st.session_state.scan_raw_text
        rows = classify_text(text)
        suggestions, warnings = build_contact_fields(rows)
        # 기존 자동 후보는 새 분류 결과로 갱신한다. 수동 입력·빈 값은 보호한다.
        # OCR 원문 위젯은 이미 만들어졌으므로 scan_raw_text는 여기서 변경하지 않는다.
        apply_auto_fields(suggestions)
        preview["revision"] = next_ocr_revision()
        st.success("수정한 원문을 다시 분류했습니다. '텍스트 분류' 메뉴에서 세부 항목을 검토하세요.")
        for warning in warnings:
            st.warning(warning)

    st.caption("이름·회사·직책은 왼쪽 '텍스트 분류' 메뉴에서 자동 추천·수동 수정할 수 있습니다. 결과를 반영한 후 연락처로 저장하세요.")
    with st.expander("텍스트 위치·신뢰도 확인"):
        lines = preview["lines"]
        if lines:
            st.dataframe(
                [{"텍스트": line["text"], "신뢰도(%)": line["confidence"], "x": line["left"], "y": line["top"]} for line in lines],
                hide_index=True, width="stretch",
            )
            image_with_boxes = image.copy()
            draw = ImageDraw.Draw(image_with_boxes)
            for line in lines:
                x, y = line["left"], line["top"]
                draw.rectangle((x, y, x + line["width"], y + line["height"]), outline="#f97316", width=2)
            st.image(image_with_boxes, caption="OCR 줄별 인식 영역", width="stretch")
        else:
            st.info("글자를 인식하지 못했습니다. 스캔 상태와 언어 설정을 확인해 주세요.")
