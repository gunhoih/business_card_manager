"""명함을 일괄 인식하고 이미지 옆에서 추출 데이터를 바로 확인·수정한다."""

import math

import pandas as pd
import streamlit as st
from PIL import ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

from backend.card_storage.schema import CONTACT_FIELDS, FIELD_LABELS, MAX_CONTACTS
from backend.card_storage.service import save_contacts
from backend.card_storage.csv_service import export_dataset_csv
from frontend.storage_ui import show_save_result
from backend.image.pre_scan.batch import (
    apply_manual_scan,
    apply_ocr_result,
    ensure_record_fields,
    image_from_bytes,
    input_signature,
    process_folder,
    status_counts,
    update_record_fields,
)
from backend.ocr.pipeline import run_ocr_pipeline
from backend.ocr.service import available_languages


PAGE_SIZE = 6
STATUS_LABELS = {
    "auto": "자동 스캔",
    "manual": "수동 보정",
    "needs_manual": "수동 보정 필요",
    "error": "파일 오류",
}


def _clear_editor_keys():
    """다른 폴더를 불러올 때 이전 표의 수정값이 새 결과로 섞이지 않게 한다."""
    prefixes = ("batch_dataset_", "batch_reviewed_", "batch_page_")
    for key in list(st.session_state):
        if key.startswith(prefixes):
            st.session_state.pop(key, None)


def _clear_batch():
    """불러온 명함만 초기화하며 기존 연락처는 유지한다."""
    for key in ("batch_records", "batch_signature"):
        st.session_state.pop(key, None)
    _clear_editor_keys()
    st.session_state["batch_picker_version"] = st.session_state.get("batch_picker_version", 0) + 1



def _save_records_to_contacts(records):
    """최종 수정값을 공통 저장 모듈에 넘긴다."""
    rows = []
    for record in records:
        ensure_record_fields(record)
        rows.append({**record["fields"], "source_file": record.get("name", "")})
    contacts = st.session_state.setdefault("contacts", [])
    return save_contacts(contacts, rows, max_contacts=MAX_CONTACTS)


def _run_ocr_one(record):
    """명함 하나만 인식하고 수동 수정한 필드는 유지한다."""
    if not record.get("scanned_bytes"):
        return

    try:
        result = run_ocr_pipeline(record["scanned_bytes"], languages="kor+eng", psm=11)
    except (RuntimeError, ValueError, OSError) as error:
        record["ocr_error"] = str(error)
        return

    apply_ocr_result(record, result)


def _run_ocr_batch(records, progress=None):
    """명함마다 독립적으로 OCR을 실행한다. 엔진 부재 시 반복 실행하지 않는다."""
    targets = [record for record in records if record.get("scanned_bytes")]
    if not targets:
        return

    try:
        languages = set(available_languages())
        missing = {"kor", "eng"} - languages
        if missing:
            raise RuntimeError("OCR 언어 모델이 없습니다: " + ", ".join(sorted(missing)))
    except (RuntimeError, OSError) as error:
        for record in targets:
            record["ocr_error"] = str(error)
        return

    for index, record in enumerate(targets, start=1):
        _run_ocr_one(record)
        if progress:
            progress(index, len(targets), record["name"])


def _load_folder(files):
    """업로드가 변경되면 자동 스캔한 뒤 곧바로 OCR까지 수행한다."""
    images = [(file.name, file.getvalue()) for file in files]
    signature = input_signature(images)
    if signature == st.session_state.get("batch_signature"):
        return

    progress = st.progress(0.0, text="명함을 자동으로 스캔하는 중입니다.")
    try:
        def report_scan(done, total, name):
            progress.progress(done / max(1, total), text=f"스캔 {done}/{total}: {name}")

        records = process_folder(images, on_progress=report_scan)

        def report_ocr(done, total, name):
            progress.progress(done / max(1, total), text=f"글자 인식 {done}/{total}: {name}")

        _run_ocr_batch(records, progress=report_ocr)
    except ValueError as error:
        st.error(str(error))
        return
    finally:
        progress.empty()

    _clear_editor_keys()
    st.session_state["batch_records"] = records
    st.session_state["batch_signature"] = signature


def _manual_preview(image, record):
    """원본 위에 선택한 네 모서리를 표시한다."""
    preview = image.copy()
    preview.thumbnail((520, 650))
    draw = ImageDraw.Draw(preview)
    scale_x = preview.width / image.width
    scale_y = preview.height / image.height
    points = [(round(x * scale_x), round(y * scale_y)) for x, y in record["manual_points"]]

    if len(points) >= 2:
        draw.line(points, fill="#f97316", width=3)
    if len(points) == 4:
        draw.line([points[-1], points[0]], fill="#f97316", width=3)

    for index, (x, y) in enumerate(points, start=1):
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="#f97316", outline="white", width=2)
        draw.text((x + 8, y - 8), str(index), fill="#f97316")
    return preview


def _show_manual_scan(record):
    """자동 보정 실패 항목에서만 수동 좌표 선택기를 펼친다."""
    source = image_from_bytes(record["original_bytes"])
    preview = _manual_preview(source, record)
    st.caption("명함의 네 모서리를 차례로 클릭하세요.")
    widget_key = f"batch_points_{record['id']}_{record['click_version']}"
    clicked = streamlit_image_coordinates(preview, key=widget_key)

    if clicked and len(record["manual_points"]) < 4:
        click_id = clicked.get("unix_time", (clicked["x"], clicked["y"]))
        if click_id != record["last_click"]:
            x = round(clicked["x"] * source.width / preview.width)
            y = round(clicked["y"] * source.height / preview.height)
            record["manual_points"].append((max(0, min(x, source.width - 1)),
                                            max(0, min(y, source.height - 1))))
            record["last_click"] = click_id
            st.rerun()

    count = len(record["manual_points"])
    st.caption(f"모서리 선택: {count}/4")
    left, right = st.columns(2)
    if left.button("다시 선택", key=f"batch_points_reset_{record['id']}", disabled=count == 0):
        record["manual_points"] = []
        record["last_click"] = None
        record["click_version"] += 1
        st.rerun()

    if right.button("마지막 점 취소", key=f"batch_points_undo_{record['id']}", disabled=count == 0):
        record["manual_points"].pop()
        record["last_click"] = None
        record["click_version"] += 1
        st.rerun()

    if st.button("보정하고 글자 추출", type="primary", disabled=count != 4,
                 key=f"batch_points_apply_{record['id']}", width="stretch"):
        try:
            apply_manual_scan(record, record["manual_points"])
        except ValueError as error:
            st.error(str(error))
        else:
            _run_ocr_one(record)
            st.session_state[f"batch_reviewed_{record['id']}"] = False
            st.rerun()


def _show_image(record):
    """자동·수동 보정에 성공했으면 보정본, 실패했으면 원본을 표시한다."""
    if record["status"] == "error":
        st.error(record["message"])
        return

    # 네 모서리를 고르는 동안에는 원본을 클릭할 수 있는 이미지로 표시한다.
    # 일반 미리보기와 겹쳐 보이지 않도록 편집 화면에서는 한 장만 표시한다.
    if record.get("manual_mode"):
        _show_manual_scan(record)
        if st.button("수동 보정 취소", key=f"batch_cancel_{record['id']}"):
            record["manual_mode"] = False
            record["manual_points"] = []
            record["last_click"] = None
            record["click_version"] += 1
            st.rerun()
        return

    # 탐지에 실패한 명함도 이미지 영역은 비워 두지 않는다.
    # 수동 보정을 완료하면 scanned_bytes가 생성되어 같은 위치에 보정본이 보인다.
    scanned = record.get("scanned_bytes") if record.get("status") in ("auto", "manual") else None
    st.image(scanned or record["original_bytes"], width="stretch")

    if not scanned:
        st.caption("자동 보정 실패 · 원본 이미지 표시 중")
        if st.button("이 명함 수동 보정", key=f"batch_manual_{record['id']}"):
            record["manual_mode"] = True
            record["manual_points"] = []
            record["last_click"] = None
            record["click_version"] += 1
            st.rerun()
        return

    with st.expander("원본 보기 · 스캔 다시 조정"):
        st.image(record["original_bytes"], caption="원본 이미지", width="stretch")
        if st.button("네 모서리 직접 선택", key=f"batch_manual_{record['id']}"):
            record["manual_mode"] = True
            record["manual_points"] = []
            record["last_click"] = None
            record["click_version"] += 1
            st.rerun()


def _show_dataset(record):
    """필드/값 표를 직접 수정하면 해당 명함의 결과 데이터에 반영한다."""
    fields = record.get("fields") or {}
    rows = pd.DataFrame([
        {"항목": FIELD_LABELS[field], "추출값": str(fields.get(field) or "")}
        for field in CONTACT_FIELDS
    ])
    revision = record.get("field_revision", 0)
    edited = st.data_editor(
        rows,
        key=f"batch_dataset_{record['id']}_{revision}",
        hide_index=True,
        disabled=["항목"],
        num_rows="fixed",
        width="stretch",
        height=390,
        column_config={
            "항목": st.column_config.TextColumn("항목", width="small"),
            "추출값": st.column_config.TextColumn("추출값", width="large"),
        },
    )
    current = {
        field: "" if pd.isna(value) else str(value)
        for field, value in zip(CONTACT_FIELDS, edited["추출값"])
    }
    if update_record_fields(record, current):
        st.session_state[f"batch_reviewed_{record['id']}"] = False

    if record.get("ocr_error"):
        st.warning(f"자동 글자 인식 실패: {record['ocr_error']}")
        if record.get("scanned_bytes") and st.button("글자 인식 다시 실행", key=f"batch_retry_{record['id']}"):
            _run_ocr_one(record)
            st.session_state[f"batch_reviewed_{record['id']}"] = False
            st.rerun()
    elif not record.get("ocr"):
        st.caption("아직 인식된 내용이 없습니다. 직접 입력하거나 스캔을 보정해 주세요.")

    review_key = f"batch_reviewed_{record['id']}"
    st.session_state.setdefault(review_key, record.get("reviewed", False))
    confirmed = st.checkbox("이 명함의 추출값 확인 완료", key=review_key)
    record["reviewed"] = confirmed


def _show_record(record, index):
    """명함 한 장을 이미지 + 구조화된 데이터 한 줄로 표시한다."""
    with st.container(border=True):
        header, status = st.columns([4, 1])
        header.markdown(f"**{index:02d}. {record['name']}**")
        status.caption(STATUS_LABELS[record["status"]])

        left, right = st.columns([1, 1.35], gap="large")
        with left:
            _show_image(record)
        with right:
            _show_dataset(record)


def show_batch_scanner():
    """폴더 업로드 → 자동 스캔·OCR → 옆 표에서 수정 → CSV 저장."""
    st.title("명함 데이터 추출")
    st.caption("명함 폴더를 선택하면 자동으로 스캔하고 글자를 추출합니다. 오른쪽 표의 값을 바로 수정하세요.")

    st.session_state.setdefault("batch_picker_version", 0)
    mode = st.radio("이미지 가져오기", ["폴더", "여러 파일"], horizontal=True, key="batch_source_mode")
    uploaded = st.file_uploader(
        "명함 이미지",
        type=["jpg", "jpeg", "png", "bmp", "webp"],
        accept_multiple_files="directory" if mode == "폴더" else True,
        key=f"batch_input_{mode}_{st.session_state.batch_picker_version}",
        help="한 번에 최대 80장, 총 120MB까지 가져옵니다.",
    )

    if uploaded:
        _load_folder(uploaded)
    elif st.session_state.get("batch_records"):
        _clear_batch()
        st.rerun()
    records = st.session_state.get("batch_records") or []
    if not records:
        st.info("폴더를 선택하면 아래에 명함 이미지와 추출 데이터가 나란히 표시됩니다.")
        return

    for record in records:
        ensure_record_fields(record)

    counts = status_counts(records)
    recognized = sum(bool(item.get("ocr")) for item in records)
    reviewed = sum(bool(item.get("reviewed")) for item in records)
    st.caption(
        f"전체 {len(records)}장 · 자동 보정 {counts['auto']}장 · 수동 완료 {counts['manual']}장"
        f" · 수동 필요 {counts['needs_manual']}장 · 글자 추출 {recognized}장 · 확인 완료 {reviewed}장"
    )

    failed_ocr = [item for item in records if item.get("scanned_bytes") and item.get("ocr_error")]
    if failed_ocr and st.button(f"인식 실패 {len(failed_ocr)}장 다시 시도", key="batch_retry_failed"):
        progress = st.progress(0.0, text="글자를 다시 인식하는 중입니다.")
        try:
            _run_ocr_batch(failed_ocr, progress=lambda done, total, name:
                           progress.progress(done / max(1, total), text=f"재인식 {done}/{total}: {name}"))
        finally:
            progress.empty()
        for record in failed_ocr:
            st.session_state[f"batch_reviewed_{record['id']}"] = False
        st.rerun()

    control, reset = st.columns([4, 1])
    with control:
        needs_attention = st.checkbox("확인이 필요한 명함만 보기", key="batch_needs_review")
    with reset:
        if st.button("목록 비우기", key="batch_clear", width="stretch"):
            _clear_batch()
            st.rerun()

    visible = [item for item in records if not item.get("reviewed")] if needs_attention else records
    if not visible:
        st.success("모든 명함의 추출값을 확인했습니다.")
    else:
        total_pages = math.ceil(len(visible) / PAGE_SIZE)
        if total_pages > 1:
            page_key = f"batch_page_{st.session_state['batch_signature']}_{int(needs_attention)}"
            if st.session_state.get(page_key, 0) >= total_pages:
                st.session_state[page_key] = total_pages - 1
            page = st.selectbox(
                "표시할 명함",
                list(range(total_pages)),
                format_func=lambda value: f"{value * PAGE_SIZE + 1}~{min(len(visible), (value + 1) * PAGE_SIZE)}장 / 총 {len(visible)}장",
                key=page_key,
            )
        else:
            page = 0

        start = page * PAGE_SIZE
        indexed_records = {id(item): index for index, item in enumerate(records, start=1)}
        for record in visible[start:start + PAGE_SIZE]:
            _show_record(record, indexed_records[id(record)])

    st.divider()
    st.caption("셀 수정 후 Enter로 확정하세요. 전화번호 또는 이메일이 일치하면 갱신하고, 일치하지 않으면 신규 등록합니다. 식별 정보가 없으면 CSV로만 내보낼 수 있습니다.")
    save_col, csv_col = st.columns(2, gap="medium")
    with save_col:
        if st.button("연락처 목록에 저장", type="primary", width="stretch", key="batch_save_contacts"):
            results = _save_records_to_contacts(records)
            show_save_result(results, ui=st)
    with csv_col:
        st.download_button(
            "추출 데이터 CSV 다운로드",
            data=export_dataset_csv(records),
            file_name="business_cards_dataset.csv",
            mime="text/csv",
            type="secondary",
            width="stretch",
            on_click="ignore",
            key="batch_download_csv",
        )
    st.caption("CSV는 명함 한 장당 한 행이며 파일명·처리 상태·검토 여부·최종 수정값을 포함합니다. "
               "연락처 목록은 현재 웹 세션에만 저장되므로 연락처 관리 화면에서도 CSV를 내려받아 보관하세요.")
