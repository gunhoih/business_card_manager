"""기존 스캔 결과를 Tesseract로 읽어 기존 연락처 입력 폼에 연결한다."""

import hashlib
import io

from PIL import Image, ImageDraw
import streamlit as st

from backend.contact.field_parser import extract_contact_candidates
from backend.contact.csv_service import CONTACT_FIELDS
from backend.ocr.service import available_languages, recognize_text
from frontend.state import set_extraction_result


LANGUAGE_OPTIONS = {
    "한국어 + 영어": "kor+eng",
    "한국어 + 영어 + 한자(번체 모델)": "kor+eng+chi_tra",
}


def show_ocr_page():
    st.title("OCR 텍스트 인식")
    st.write("Tesseract를 사용해 명함 글자를 로컬에서 인식합니다. 이 단계에서는 AI API를 호출하지 않습니다.")

    image_bytes = st.session_state.scan_result_bytes or st.session_state.scan_image_bytes
    if not image_bytes:
        st.info("먼저 왼쪽의 '명함 인식' 메뉴에서 명함을 업로드하거나 스캔해 주세요.")
        return

    source_id = hashlib.sha256(image_bytes).hexdigest()
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGB")

    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.image(image, caption="OCR 대상: 보정한 명함을 우선 사용", width="stretch")

    with right:
        language_label = st.radio("인식할 언어", list(LANGUAGE_OPTIONS), horizontal=False)
        psm_label = st.selectbox("글자 배치", ["흩어진 텍스트(명함 권장)", "하나의 텍스트 블록", "자동 페이지 분석"])
        psm = {"흩어진 텍스트(명함 권장)": 11, "하나의 텍스트 블록": 6, "자동 페이지 분석": 3}[psm_label]
        with st.expander("OCR 엔진 설치 상태"):
            try:
                languages = available_languages()
                st.success("Tesseract 실행 가능")
                st.caption("설치된 언어: " + ", ".join(code for code in ("kor", "eng", "chi_tra", "chi_sim") if code in languages))
            except RuntimeError as error:
                st.warning(str(error))

        if st.button("Tesseract로 문자 인식", type="primary", width="stretch"):
            try:
                with st.spinner("이미지에서 글자를 읽고 있습니다..."):
                    result = recognize_text(image, languages=LANGUAGE_OPTIONS[language_label], psm=psm)
            except (RuntimeError, ValueError) as error:
                st.error(str(error))
            else:
                fields = extract_contact_candidates(result.text)
                # 이미 수동으로 적은 값은 OCR이 찾지 못한 경우 유지한다.
                for field in CONTACT_FIELDS:
                    if not fields[field]:
                        fields[field] = st.session_state.get(f"scan_{field}", "")
                set_extraction_result(result.text, fields)
                st.session_state["ocr_preview"] = {
                    "image_id": source_id,
                    "lines": [line.__dict__ for line in result.lines],
                    "languages": result.languages,
                }
                st.success(f"{len(result.lines)}개 텍스트 줄을 인식했습니다. 이메일·전화번호·웹사이트 후보를 기존 입력 폼에도 반영했습니다.")

    preview = st.session_state.get("ocr_preview")
    if not preview or preview.get("image_id") != source_id:
        st.caption("OCR을 실행하면 추출된 글자와 줄별 인식 위치가 표시됩니다.")
        return

    st.subheader("인식된 텍스트")
    st.text_area("OCR 원문 · 필요하면 수정하세요", key="scan_raw_text", height=220)

    if st.button("수정한 원문에서 연락처 패턴 다시 추출"):
        text = st.session_state.scan_raw_text
        fields = extract_contact_candidates(text)
        # 수동으로 입력한 이름·회사·직책은 유지한다.
        for field in ("name", "company", "department", "position", "fax", "address", "memo"):
            fields[field] = st.session_state.get(f"scan_{field}", "")
        # scan_raw_text 위젯이 생성된 뒤 같은 키를 다시 대입하지 않는다.
        for field in CONTACT_FIELDS:
            st.session_state[f"scan_{field}"] = str(fields.get(field) or "")
        st.success("연락처 패턴을 다시 추출했습니다.")

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
            st.image(image_with_boxes, caption="Tesseract의 줄별 인식 영역", width="stretch")
        else:
            st.info("글자를 인식하지 못했습니다. 스캔 상태와 언어 설정을 확인해 주세요.")
