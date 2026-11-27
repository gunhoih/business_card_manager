"""명함을 일괄 인식하고 이미지 옆에서 추출 데이터를 바로 확인·수정한다."""

import math
from time import monotonic

import pandas as pd
import streamlit as st
from PIL import ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

from backend.card_storage.schema import CONTACT_FIELDS, FIELD_LABELS, MAX_CONTACTS
from backend.card_storage.service import save_contacts
from backend.card_storage.csv_service import export_dataset_csv
from frontend.storage_ui import show_save_result
from backend.image.pre_scan.batch import (
    MAX_FILES, MAX_TOTAL_BYTES,
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
from backend.ocr.engine import check_ocr_ready


PAGE_SIZE = 6
# 자동 OCR을 먼저 시작하고 큰 배치는 중간 결과를 보존한 채 이어서 처리한다.
OCR_RUN_SECONDS = 45
OCR_RUN_CARDS = 12
OCR_CARD_SECONDS = 30
STATUS_LABELS = {
    "auto": "자동 스캔",
    "manual": "수동 보정",
    "needs_manual": "수동 보정 필요",
    "error": "파일 오류",
}


def _clear_editor_keys():
    """다른 폴더를 불러올 때 이전 표의 수정값이 새 결과로 섞이지 않게 한다."""
    prefixes = ("batch_dataset_", "batch_reviewed_", "batch_page_", "batch_points_",
                "batch_manual_", "batch_cancel_", "batch_retry_", "batch_name_")
    for key in list(st.session_state):
        if key.startswith(prefixes):
            st.session_state.pop(key, None)


def _clear_batch():
    """불러온 명함만 초기화하며 기존 연락처는 유지한다."""
    for key in ("batch_records", "batch_signature", "batch_rejected_signature", "batch_load_error"):
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


def _run_ocr_one(record, timeout=OCR_CARD_SECONDS):
    """명함 하나만 인식하고 수동 수정한 필드는 유지한다."""
    if not record.get("scanned_bytes"):
        return

    try:
        result = run_ocr_pipeline(record["scanned_bytes"], languages="kor+eng", psm=11,
                                  timeout=timeout)
        apply_ocr_result(record, result)
    except Exception as error:
        # 파일 한 장의 엔진/전처리 오류로 전체 배치를 중단하지 않는다.
        record["ocr_error"] = (str(error) if isinstance(error, (RuntimeError, ValueError))
                               else f"글자 인식 실패 ({type(error).__name__})")


def _pending_records(records):
    return [record for record in records if record.get("scanned_bytes")
            and not record.get("ocr") and not record.get("ocr_error")]


def _run_ocr_batch(records, progress=None):
    """한 번에 제한된 시간/건수만 처리한다. 미처리 명함은 다음 실행에 남긴다."""
    targets = [record for record in records if record.get("scanned_bytes")]
    if not targets:
        return 0

    try:
        with st.spinner("OCR 모델 확인 중 · 최초 실행 시 자동 다운로드합니다."):
            check_ocr_ready("kor+eng")
    except (RuntimeError, OSError, ValueError) as error:
        for record in targets:
            record["ocr_error"] = str(error)
        return 0

    deadline = monotonic() + OCR_RUN_SECONDS
    done = 0
    for record in targets:
        remaining = deadline - monotonic()
        if remaining < 5 or done >= OCR_RUN_CARDS:
            break
        _run_ocr_one(record, timeout=min(OCR_CARD_SECONDS, remaining))
        done += 1
        if progress:
            progress(done, len(targets), record["name"])
    return done


def _load_folder(files):
    """새 파일만 스캔하고 OCR 전에도 결과를 세션에 기록한다."""
    if len(files) > MAX_FILES:
        st.error(f"한 번에 최대 {MAX_FILES}장의 이미지를 처리할 수 있습니다.")
        return
    # UploadedFile.size를 먼저 확인하여 불필요한 대용량 복사를 줄인다.
    sizes = [getattr(file, "size", None) for file in files]
    if all(isinstance(size, int) for size in sizes) and sum(sizes) > MAX_TOTAL_BYTES:
        st.error("폴더 전체 용량은 120MB 이하로 제한됩니다.")
        return
    images = [(file.name, file.getvalue()) for file in files]
    signature = input_signature(images)
    if signature == st.session_state.get("batch_signature"):
        return
    if signature == st.session_state.get("batch_rejected_signature"):
        st.error(st.session_state.get("batch_load_error", "업로드 파일을 확인하세요."))
        return

    progress = st.progress(0.0, text="명함을 자동으로 스캔하는 중입니다.")
    try:
        def report_scan(done, total, name):
            progress.progress(done / max(1, total), text=f"스캔 {done}/{total}: {name}")

        records = process_folder(images, on_progress=report_scan,
                                 previous_records=st.session_state.get("batch_records", []))
        if not records:
            raise ValueError("지원하는 명함 이미지가 없습니다.")
        # 스캔이 완료된 시점에 저장하여 OCR 중단 시에도 작업을 복구할 수 있다.
        _clear_editor_keys()
        st.session_state["batch_records"] = records
        st.session_state["batch_signature"] = signature
        st.session_state.pop("batch_rejected_signature", None)
        st.session_state.pop("batch_load_error", None)

        def report_ocr(done, total, name):
            progress.progress(done / max(1, total), text=f"글자 인식 {done}/{total}: {name}")

        _run_ocr_batch(_pending_records(records), progress=report_ocr)
    except ValueError as error:
        st.session_state["batch_rejected_signature"] = signature
        st.session_state["batch_load_error"] = str(error)
        st.error(str(error))
        if st.session_state.get("batch_records"):
            st.caption("새 업로드를 처리하지 못해 이전 작업을 그대로 유지합니다.")
    finally:
        progress.empty()


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


def _apply_editor_changes(record, editor_key):
    """위젯의 셀 변경을 화면 재실행 전에 해당 명함에 반영한다."""
    state = st.session_state.get(editor_key) or {}
    if not isinstance(state, dict) or record.get("editor_key") != editor_key:
        return
    base = record.get("editor_base") or record.get("fields") or {}
    edits = state.get("edited_rows", {})
    if not isinstance(edits, dict):
        return
    # edited_rows는 현재 기준 표에 대한 전체 변경분이다. 기준 표를 고정해야 한다.
    values = {field: str(base.get(field) or "") for field in CONTACT_FIELDS}
    for index, changes in edits.items():
        try:
            index = int(index)
            if 0 <= index < len(CONTACT_FIELDS) and isinstance(changes, dict) and "추출값" in changes:
                value = changes["추출값"]
                values[CONTACT_FIELDS[index]] = "" if value is None else str(value)
        except (TypeError, ValueError):
            continue
    if update_record_fields(record, values):
        st.session_state[f"batch_reviewed_{record['id']}"] = False


def _apply_review_change(record, key):
    record["reviewed"] = bool(st.session_state.get(key, False))


def _show_dataset(record):
    """수정 표의 기준값을 고정하고, 위젯이 사라진 후에는 최종 저장값으로 복원한다."""
    revision = record.get("field_revision", 0)
    editor_key = f"batch_dataset_{record['id']}_{revision}"
    fields = record.get("fields") or {}
    if editor_key not in st.session_state or record.get("editor_key") != editor_key:
        record["editor_key"] = editor_key
        record["editor_base"] = dict(fields)
    base = record["editor_base"]
    rows = pd.DataFrame([
        {"항목": FIELD_LABELS[field], "추출값": str(base.get(field) or "")}
        for field in CONTACT_FIELDS
    ])
    edited = st.data_editor(
        rows,
        key=editor_key,
        hide_index=True,
        disabled=["항목"],
        num_rows="fixed",
        width="stretch",
        height=390,
        column_config={
            "항목": st.column_config.TextColumn("항목", width="small"),
            "추출값": st.column_config.TextColumn("추출값", width="large"),
        },
        on_change=_apply_editor_changes,
        args=(record, editor_key),
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
    else:
        report = record["ocr"]
        warnings = report.get("warnings", [])
        if warnings and not record.get("reviewed"):
            with st.expander(f"인식 확인 필요 ({len(warnings)}건)"):
                for warning in warnings:
                    st.warning(warning)
        # 불확실한 이름은 표를 직접 고치거나 실제 OCR 후보 중 하나를 선택한다.
        name_rows = sorted((row for row in report.get("candidates", []) if row.get("name_rank")),
                           key=lambda row: row["name_rank"])
        chosen = next((row for row in name_rows if row.get("selected_type") == "name"), None)
        names = [row.get("name_candidate") for row in name_rows if row.get("name_candidate")]
        names += [item["alternate"] for item in report.get("name_checks", [])
                  if item.get("status") == "review" and item.get("alternate")]
        names = list(dict.fromkeys(names))[:3]
        needs_name = (not record.get("fields", {}).get("name") or
                      (chosen and chosen.get("name_status") == "suggested") or
                      any(item.get("status") == "review" for item in report.get("name_checks", [])))
        if names and needs_name and not record.get("reviewed") and "name" not in record.get("manual_fields", []):
            st.caption("이름 확인 필요 · 원본에서 판독한 후보")
            options = ["선택하지 않음", *names]
            name = st.selectbox("이름 후보", options,
                                key=f"batch_name_choice_{record['id']}_{revision}")
            if st.button("선택한 이름 반영", disabled=name == options[0],
                         key=f"batch_name_apply_{record['id']}_{revision}"):
                values = dict(record.get("fields", {}))
                values["name"] = name
                update_record_fields(record, values)
                # 같은 자동 제안값을 승인해도 수동 확인값으로 기록한다.
                record["manual_fields"] = sorted(set(record.get("manual_fields", [])) | {"name"})
                record["field_revision"] = revision + 1
                record["reviewed"] = False
                st.session_state[f"batch_reviewed_{record['id']}"] = False
                st.rerun()
        checks = report.get("english_checks", [])
        if checks:
            st.caption(f"영문·숫자 영역 {len(checks)}개 보조 인식 완료")
        if needs_name and record.get("scanned_bytes") and "name" not in record.get("manual_fields", []):
            if st.button("이 명함 다시 인식", key=f"batch_retry_name_{record['id']}"):
                _run_ocr_one(record)
                st.session_state[f"batch_reviewed_{record['id']}"] = False
                st.rerun()

    review_key = f"batch_reviewed_{record['id']}"
    st.session_state.setdefault(review_key, record.get("reviewed", False))
    confirmed = st.checkbox("이 명함의 추출값 확인 완료", key=review_key,
                            on_change=_apply_review_change, args=(record, review_key))
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
    # 다른 페이지로 이동하면 업로더 위젯이 초기화될 수 있다.
    # 실제 작업 데이터는 명시적인 '목록 비우기' 전까지 유지한다.
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

    pending = _pending_records(records)
    if pending:
        st.caption(f"아직 글자를 인식하지 않은 보정 완료 명함 {len(pending)}장 · 현재까지의 결과는 유지됩니다.")
        if st.button(f"남은 {len(pending)}장 이어서 추출", key="batch_continue", type="primary"):
            progress = st.progress(0.0, text="남은 명함을 인식하는 중입니다.")
            try:
                _run_ocr_batch(pending, progress=lambda done, total, name:
                               progress.progress(done / max(1, total), text=f"글자 인식 {done}/{total}: {name}"))
            finally:
                progress.empty()
            st.rerun()

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
    if pending:
        st.caption("아직 인식하지 않은 명함은 현재 입력된 값만 저장·다운로드됩니다.")
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
