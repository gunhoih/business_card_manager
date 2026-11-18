import hashlib
import io

import streamlit as st
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from streamlit_image_coordinates import streamlit_image_coordinates

from backend.contact.csv_service import CONTACT_FIELDS
from backend.image.scan_service import scan_auto_image, scan_manual_image
from frontend.state import (
    add_contact,
    clear_scan_image,
    clear_scan_result,
    reset_scan_points,
    set_scan_image,
)


MAX_IMAGE_SIZE = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000


def load_image(image_bytes):
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise ValueError("이미지는 12MB 이하로 업로드해 주세요.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("이미지 해상도가 너무 큽니다. 1,200만 픽셀 이하로 줄여 주세요.")
            image = ImageOps.exif_transpose(image)
            return image.convert("RGB")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError("이미지를 열 수 없습니다. JPG, PNG 등의 파일을 확인해 주세요.") from error


def make_click_image(image, points):
    preview = image.copy()
    preview.thumbnail((500, 600))

    scale_x = preview.width / image.width
    scale_y = preview.height / image.height
    draw = ImageDraw.Draw(preview)

    selected = [(round(x * scale_x), round(y * scale_y)) for x, y in points]

    if len(selected) > 1:
        draw.line(selected, fill="#f97316", width=3)
    if len(selected) == 4:
        draw.line([selected[-1], selected[0]], fill="#f97316", width=3)

    for number, (x, y) in enumerate(selected, start=1):
        radius = 7
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#f97316", outline="white", width=2)
        draw.text((x + 10, y - 10), str(number), fill="#f97316")

    return preview


def show_image_upload():
    mode = st.radio("이미지 가져오기", ["파일 업로드", "카메라 촬영"], horizontal=True)

    if mode == "파일 업로드":
        uploaded = st.file_uploader(
            "명함 이미지 선택",
            type=["jpg", "jpeg", "png", "bmp", "webp"],
            help="JPG, PNG, BMP, WebP · 최대 12MB",
            key=f"scan_upload_{st.session_state.scan_upload_version}",
        )
    else:
        uploaded = st.camera_input("카메라로 명함 촬영", key=f"scan_camera_{st.session_state.scan_upload_version}")

    if uploaded is not None:
        content = uploaded.getvalue()
        try:
            load_image(content)
            image_id = hashlib.sha256(content).hexdigest()
            set_scan_image(content, uploaded.name, image_id)
        except ValueError as error:
            st.error(str(error))

    if st.session_state.scan_image_bytes is not None:
        if st.button("현재 이미지 지우기", key="clear_scan_image"):
            clear_scan_image()
            st.rerun()

    return st.session_state.scan_image_bytes


def show_manual_scan(image):
    st.caption("명함의 네 모서리를 순서대로 클릭해 주세요. 좌표는 원본 이미지 크기로 저장됩니다.")

    preview = make_click_image(image, st.session_state.scan_points)
    widget_key = f"scan_coordinates_{st.session_state.scan_image_id}_{st.session_state.scan_widget_version}"
    clicked = streamlit_image_coordinates(preview, key=widget_key)

    if clicked and len(st.session_state.scan_points) < 4:
        click_id = clicked.get("unix_time", (clicked["x"], clicked["y"]))

        if click_id != st.session_state.scan_last_click:
            x = round(clicked["x"] * image.width / preview.width)
            y = round(clicked["y"] * image.height / preview.height)
            x = max(0, min(x, image.width - 1))
            y = max(0, min(y, image.height - 1))
            st.session_state.scan_points.append((x, y))
            st.session_state.scan_last_click = click_id
            st.rerun()

    count = len(st.session_state.scan_points)
    st.progress(count / 4, text=f"모서리 {count} / 4개 선택")

    left, right = st.columns(2)
    with left:
        if st.button("좌표 초기화", width="stretch", disabled=count == 0):
            reset_scan_points()
            st.rerun()
    with right:
        if st.button("마지막 점 취소", width="stretch", disabled=count == 0):
            st.session_state.scan_points.pop()
            st.session_state.scan_last_click = None
            clear_scan_result()
            st.session_state.scan_widget_version += 1
            st.rerun()

    if count == 4:
        st.success("네 모서리 지정이 완료됐습니다.")
        with st.expander("선택 좌표 확인"):
            for number, (x, y) in enumerate(st.session_state.scan_points, start=1):
                st.write(f"{number}번 점: x={x}, y={y}")

    if st.button("원근 보정 실행", type="primary", width="stretch", disabled=count != 4):
        try:
            result = scan_manual_image(image, st.session_state.scan_points)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state.scan_result_bytes = result
            st.session_state.scan_result_mode = "수동 호모그래피"
            st.success("선택한 영역을 정면 이미지로 보정했습니다.")


def show_auto_scan(image):
    st.image(image, caption="자동 탐지 대상 이미지", width="stretch")
    st.caption("OpenCV에서 명함의 사각형 테두리를 찾아 원근 보정합니다.")

    if st.button("자동 영역 탐지 및 스캔", type="primary", width="stretch"):
        try:
            result, _ = scan_auto_image(image)
        except ValueError as error:
            st.error(str(error))
        else:
            if result is None:
                st.warning("명함 영역을 찾지 못했습니다. '수동 모서리 선택'을 이용해 주세요.")
            else:
                st.session_state.scan_result_bytes = result
                st.session_state.scan_result_mode = "자동 명함 탐지"
                st.success("명함 영역을 자동으로 감지하고 보정했습니다.")


def show_scan_page():
    st.subheader("1. 명함 이미지 스캔")
    image_bytes = show_image_upload()

    if not image_bytes:
        st.info("명함 이미지를 업로드하면 모서리를 지정할 수 있습니다.")
        return

    try:
        image = load_image(image_bytes)
    except ValueError as error:
        st.error(str(error))
        return

    st.caption(f"현재 이미지: {st.session_state.scan_image_name} · {image.width} × {image.height}px")

    left, right = st.columns([1.2, 1], gap="large")
    with left:
        scan_mode = st.radio(
            "스캔 방식", ["수동 모서리 선택", "자동 영역 탐지"],
            horizontal=True, key="scan_mode", on_change=clear_scan_result,
        )
        if scan_mode == "수동 모서리 선택":
            show_manual_scan(image)
        else:
            show_auto_scan(image)

    with right:
        st.markdown("**스캔 결과 미리보기**")
        result = st.session_state.scan_result_bytes
        if result:
            mode = st.session_state.scan_result_mode
            st.image(result, caption=f"보정된 이미지 · {mode}", width="stretch")
            st.download_button(
                "보정 이미지 다운로드",
                result,
                file_name="scanned_business_card.png",
                mime="image/png",
                width="stretch",
                on_click="ignore",
            )
        else:
            with st.container(border=True):
                st.write("아직 보정된 이미지가 없습니다.")
                st.caption("수동 또는 자동 스캔을 실행하면 보정 결과가 표시됩니다.")


def show_extraction_page():
    st.subheader("2. 명함 정보 추출")
    st.caption("OpenAI Vision으로 인식된 값을 이곳에 표시할 예정입니다. 현재는 수동으로 입력해 화면과 CSV 저장 흐름을 테스트할 수 있습니다.")

    left, right = st.columns([1, 1.3], gap="large")

    with left:
        st.markdown("**인식 대상 이미지**")
        image_bytes = st.session_state.scan_result_bytes or st.session_state.scan_image_bytes
        if image_bytes:
            st.image(image_bytes, width="stretch")
        else:
            st.info("스캔 탭에서 명함 이미지를 업로드해 주세요.")

        st.button(
            "AI 텍스트 인식 및 구조화",
            type="primary",
            width="stretch",
            disabled=True,
            help="OpenAI 추출 백엔드 연결 후 활성화됩니다.",
        )
        st.caption("미연결: API 호출은 발생하지 않으며 비용도 청구되지 않습니다.")
        st.text_area("OCR 원문", key="scan_raw_text", height=140, placeholder="추후 OCR 원문을 보여줍니다. 직접 입력해도 됩니다.")

    with right:
        st.markdown("**구조화된 연락처 정보**")
        st.caption("필드를 수정한 뒤 임시 연락처 목록에 추가할 수 있습니다.")

        with st.form("scan_contact_form", clear_on_submit=True):
            name = st.text_input("이름", key="scan_name", placeholder="예: 홍길동")
            company = st.text_input("회사·소속", key="scan_company", placeholder="예: ABC 테크놀로지")
            col1, col2 = st.columns(2)
            with col1:
                department = st.text_input("부서", key="scan_department")
            with col2:
                position = st.text_input("직책", key="scan_position")

            phone = st.text_input("전화번호", key="scan_phone")
            email = st.text_input("이메일", key="scan_email")
            website = st.text_input("웹사이트", key="scan_website")
            fax = st.text_input("팩스", key="scan_fax")
            address = st.text_input("주소", key="scan_address")
            memo = st.text_area("메모", key="scan_memo", height=80)

            submitted = st.form_submit_button("연락처 목록에 추가", type="primary", width="stretch")

        if submitted:
            contact = {
                "name": name,
                "company": company,
                "department": department,
                "position": position,
                "phone": phone,
                "email": email,
                "website": website,
                "fax": fax,
                "address": address,
                "memo": memo,
            }
            if not any(contact[field].strip() for field in CONTACT_FIELDS):
                st.warning("저장할 정보를 하나 이상 입력해 주세요.")
            else:
                add_contact(contact)
                st.success("임시 연락처 목록에 추가했습니다. '연락처 관리' 페이지에서 확인하고 CSV로 내려받을 수 있습니다.")


def show_scanner():
    st.title("명함 인식")
    st.write("명함 이미지를 스캔하고, AI 추출 결과를 확인한 다음 연락처 목록에 저장합니다.")
    st.info("OpenCV 수동·자동 스캔과 CSV 저장을 지원합니다. AI 정보 추출은 다음 단계에서 연결합니다.")

    scan_tab, extraction_tab = st.tabs(["📐 스캔 및 이미지 보정", "📝 텍스트 추출 및 정보 확인"])
    with scan_tab:
        show_scan_page()
    with extraction_tab:
        show_extraction_page()
