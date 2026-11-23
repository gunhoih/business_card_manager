"""여러 명함을 자동 호모그래피로 스캔하고 실패한 항목만 수동 보정하는 화면."""

import hashlib

import streamlit as st
from PIL import ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

from backend.image.pre_scan.batch import (
    apply_manual_scan,
    export_scans_zip,
    image_from_bytes,
    input_signature,
    process_folder,
    status_counts,
)
from backend.ocr.pipeline import run_ocr_pipeline
from frontend.state import (
    apply_auto_fields,
    next_ocr_revision,
    set_scan_image,
    set_scan_result,
)


STATUS_LABELS = {
    "auto": "자동 완료",
    "manual": "수동 완료",
    "needs_manual": "수동 필요",
    "error": "파일 오류",
}


def _clear_batch():
    """이미지 목록만 비우며 기존 연락처와 단일 스캔은 보존한다."""
    for key in ("batch_records", "batch_signature", "batch_selected", "batch_zip"):
        st.session_state.pop(key, None)
    st.session_state["batch_picker_version"] = st.session_state.get("batch_picker_version", 0) + 1


def _load_folder(uploaded_files):
    """업로드 목록이 달라졌을 때에만 자동 호모그래피를 다시 실행한다."""
    images = [(file.name, file.getvalue()) for file in uploaded_files]
    signature = input_signature(images)
    if signature == st.session_state.get("batch_signature"):
        return

    progress = st.progress(0.0, text="명함 영역을 자동으로 확인하고 있습니다.")

    def report(done, total, name):
        progress.progress(done / max(1, total), text=f"자동 스캔 {done}/{total}: {name}")

    try:
        records = process_folder(images, on_progress=report)
    except ValueError as error:
        st.error(str(error))
        return
    finally:
        progress.empty()

    st.session_state["batch_records"] = records
    st.session_state.pop("batch_zip", None)
    st.session_state["batch_signature"] = signature
    st.session_state["batch_selected"] = records[0]["id"] if records else None


def _manual_preview(image, record):
    """모서리 선택 과정과 선택된 점을 원본 이미지 위에 표시한다."""
    preview = image.copy()
    preview.thumbnail((540, 650))
    draw = ImageDraw.Draw(preview)
    sx = preview.width / image.width
    sy = preview.height / image.height
    points = [(round(x * sx), round(y * sy)) for x, y in record["manual_points"]]
    if len(points) >= 2:
        draw.line(points, fill="#f97316", width=3)
    if len(points) == 4:
        draw.line([points[-1], points[0]], fill="#f97316", width=3)
    for number, (x, y) in enumerate(points, start=1):
        draw.ellipse([x - 6, y - 6, x + 6, y + 6], fill="#f97316", outline="white", width=2)
        draw.text((x + 8, y - 8), str(number), fill="#f97316")
    return preview


def _manual_controls(record, source_image):
    st.caption("명함의 모서리 네 곳을 순서대로 클릭해 주세요. 자동 보정이 실패한 명함만 작업하면 됩니다.")
    preview = _manual_preview(source_image, record)
    key = f"batch_coordinate_{record['id']}_{record['click_version']}"
    clicked = streamlit_image_coordinates(preview, key=key)

    if clicked and len(record["manual_points"]) < 4:
        click_id = clicked.get("unix_time", (clicked["x"], clicked["y"]))
        if record["last_click"] != click_id:
            x = round(clicked["x"] * source_image.width / preview.width)
            y = round(clicked["y"] * source_image.height / preview.height)
            x = min(source_image.width - 1, max(0, x))
            y = min(source_image.height - 1, max(0, y))
            record["manual_points"].append((x, y))
            record["last_click"] = click_id
            st.rerun()

    count = len(record["manual_points"])
    st.progress(count / 4, text=f"선택한 모서리: {count}/4")
    left, right = st.columns(2)
    if left.button("다시 선택", disabled=count == 0, key=f"batch_reset_{record['id']}", width="stretch"):
        record["manual_points"] = []
        record["last_click"] = None
        record["click_version"] += 1
        st.rerun()
    if right.button("마지막 점 취소", disabled=count == 0, key=f"batch_undo_{record['id']}", width="stretch"):
        record["manual_points"].pop()
        record["last_click"] = None
        record["click_version"] += 1
        st.rerun()
    if st.button("선택한 네 모서리로 수동 보정", type="primary", disabled=count != 4,
                 key=f"batch_manual_apply_{record['id']}", width="stretch"):
        try:
            apply_manual_scan(record, record["manual_points"])
            st.session_state.pop("batch_zip", None)
        except ValueError as error:
            st.error(str(error))
        else:
            st.rerun()


def _run_ocr_one(record):
    if not record.get("scanned_bytes"):
        return
    st.session_state.pop("batch_zip", None)
    try:
        record["ocr"] = run_ocr_pipeline(record["scanned_bytes"], languages="kor+eng", psm=11)
        record["ocr_error"] = None
    except (ValueError, RuntimeError) as error:
        record["ocr"] = None
        record["ocr_error"] = str(error)


def _connect_to_editor(record):
    """선택한 명함을 기존 단일 OCR/텍스트 분류/연락처 수정 화면에 전달한다."""
    source = record["original_bytes"]
    scanned = record["scanned_bytes"]
    set_scan_image(source, record["name"], hashlib.sha256(source).hexdigest())
    set_scan_result(scanned, "폴더 일괄 스캔 · " + STATUS_LABELS[record["status"]])

    report = record.get("ocr")
    if report:
        apply_auto_fields(report["fields"])
        st.session_state["scan_raw_text"] = report["text"]
        st.session_state["ocr_preview"] = {
            "image_id": hashlib.sha256(scanned).hexdigest(),
            "lines": report["lines"],
            "languages": report["languages"],
            "psm": report["psm"],
            "source_text": report["text"],
            "revision": next_ocr_revision(),
        }


def _render_selected(record):
    st.write("**선택한 명함:**", record["name"])
    st.caption(record["message"])
    if record["manual_mode"] and record.get("scanned_bytes"):
        if st.button("수동 보정 취소 · 기존 스캔 유지", key=f"batch_manual_cancel_{record['id']}"):
            record["manual_mode"] = False
            record["manual_points"] = []
            st.rerun()

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**원본 이미지**")
        if record["status"] == "error":
            st.warning("이미지를 열 수 없습니다. 다른 이미지 파일로 다시 업로드해 주세요.")
        else:
            source_image = image_from_bytes(record["original_bytes"])
            if record["status"] == "needs_manual" or record["manual_mode"]:
                _manual_controls(record, source_image)
            else:
                st.image(source_image, caption="원본 촬영 이미지", width="stretch")
                if st.button("수동으로 다시 보정", key=f"batch_override_{record['id']}"):
                    record["manual_mode"] = True
                    record["manual_points"] = []
                    record["last_click"] = None
                    record["click_version"] += 1
                    st.rerun()
    with right:
        st.markdown("**호모그래피 스캔 결과**")
        if record.get("scanned_bytes"):
            st.image(record["scanned_bytes"], caption=STATUS_LABELS[record["status"]], width="stretch")
            st.download_button("현재 스캔 이미지 저장", record["scanned_bytes"],
                               file_name="scanned_card.png", mime="image/png", on_click="ignore")
            if st.button("이 명함을 기존 OCR·연락처 편집에 연결", key=f"batch_select_{record['id']}",
                         width="stretch"):
                _connect_to_editor(record)
                st.success("연결했습니다. 왼쪽의 'OCR 텍스트 인식' 또는 '명함 인식' 메뉴에서 확인하세요.")
            if st.button("이 명함 OCR 실행", key=f"batch_ocr_one_{record['id']}", width="stretch"):
                with st.spinner("선택한 명함에서 텍스트를 인식하고 있습니다."):
                    _run_ocr_one(record)
                st.rerun()
            if record.get("ocr"):
                with st.expander("OCR 추출 결과", expanded=True):
                    st.text_area("인식된 원문", value=record["ocr"]["text"], height=150,
                                 key=f"batch_ocr_text_{record['id']}", disabled=True)
                    st.json(record["ocr"]["fields"])
            elif record.get("ocr_error"):
                st.warning(f"OCR 실패: {record['ocr_error']}")
        else:
            st.info("자동 스캔이 실패했습니다. 왼쪽의 원본 이미지에서 네 모서리를 지정하면 이 위치에 스캔본이 바로 나타납니다.")


def show_batch_scanner():
    """폴더 전체 자동 보정 → 미검출 명함만 수동 보정 → 선택적 OCR → ZIP 내려받기."""
    st.title("폴더 일괄 명함 스캔")
    st.write("폴더의 모든 명함을 자동으로 스캔하고, 인식되지 않은 명함만 수동으로 보정합니다.")
    st.caption("단일 명함 스캔과 별도로 동작합니다. 원본을 보존하며, 로컬 OCR은 버튼을 누른 경우에만 실행합니다.")

    st.session_state.setdefault("batch_picker_version", 0)
    source_mode = st.radio("가져오기 방식", ["폴더 선택", "여러 파일 선택"], horizontal=True, key="batch_source_mode")
    uploaded = st.file_uploader(
        "명함 사진이 들어 있는 폴더 또는 여러 이미지 선택",
        type=["jpg", "jpeg", "png", "bmp", "webp"],
        accept_multiple_files="directory" if source_mode == "폴더 선택" else True,
        key=f"batch_upload_{source_mode}_{st.session_state.batch_picker_version}",
        help="하위 폴더도 포함됩니다. 최대 80장, 합계 120MB, 파일당 12MB입니다.",
    )
    if uploaded:
        _load_folder(uploaded)

    records = st.session_state.get("batch_records") or []
    if not records:
        st.info("이미지 폴더를 선택하면 자동 호모그래피 결과가 생성됩니다.")
        return

    counts = status_counts(records)
    columns = st.columns(4)
    for col, (label, value) in zip(columns, [
        ("자동 완료", counts["auto"]),
        ("수동 완료", counts["manual"]),
        ("수동 필요", counts["needs_manual"]),
        ("파일 오류", counts["error"]),
    ]):
        col.metric(label, value)

    st.dataframe([{"파일": item["name"], "상태": STATUS_LABELS[item["status"]],
                   "OCR": "완료" if item.get("ocr") else ("오류" if item.get("ocr_error") else "미실행")}
                  for item in records], hide_index=True, width="stretch", height=min(300, 70 + len(records) * 35))

    ids = [record["id"] for record in records]
    if st.session_state.get("batch_selected") not in ids:
        st.session_state["batch_selected"] = ids[0]
    record_by_id = {record["id"]: record for record in records}
    selected_id = st.selectbox(
        "비교·수정할 명함 선택", options=ids,
        format_func=lambda id_: f"[{STATUS_LABELS[record_by_id[id_]['status']]}] {record_by_id[id_]['name']}",
        key="batch_selected",
    )
    _render_selected(record_by_id[selected_id])

    st.divider()
    pending = [item for item in records if item.get("scanned_bytes") and not item.get("ocr")]
    left, right = st.columns([1, 1])
    with left:
        if st.button(f"보정 완료 명함 일괄 OCR ({len(pending)}개)", disabled=not pending, width="stretch"):
            progress = st.progress(0.0, text="일괄 OCR 처리 중")
            for index, item in enumerate(pending, start=1):
                _run_ocr_one(item)
                progress.progress(index / len(pending), text=f"OCR {index}/{len(pending)}: {item['name']}")
            progress.empty()
            st.rerun()
        if st.button("폴더 목록 비우기", width="stretch"):
            _clear_batch()
            st.rerun()
    with right:
        if st.button("보정 이미지·OCR 결과 ZIP 준비", width="stretch"):
            with st.spinner("압축파일을 생성하고 있습니다."):
                st.session_state["batch_zip"] = export_scans_zip(records)
        if st.session_state.get("batch_zip"):
            st.download_button(
                "준비된 ZIP 다운로드",
                data=st.session_state["batch_zip"],
                file_name="business_cards_scanned.zip",
                mime="application/zip",
                width="stretch",
                on_click="ignore",
            )
        st.caption("보정 이미지, 처리 상태 및 실행한 OCR 결과를 저장합니다. 처리 결과가 바뀌면 ZIP을 다시 준비해야 합니다.")

    if counts["needs_manual"]:
        st.warning(f"아직 {counts['needs_manual']}개 명함은 수동 보정이 필요합니다. 선택 목록에서 해당 항목을 진행해 주세요.")
