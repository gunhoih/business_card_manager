"""각 저장 화면에서 공통으로 사용하는 간단한 결과 표시."""

import streamlit as st

from backend.card_storage.schema import MAX_CONTACTS
from backend.card_storage.service import save_contacts


def show_save_result(result, ui=None):
    ui = st if ui is None else ui
    ui.success(f"신규 {result['added']}개 · 갱신 {result['updated']}개 · 유지 {result['unchanged']}개")
    skipped = sum(result[key] for key in ("missing_identity", "invalid_identity", "conflicts", "empty", "full"))
    if skipped:
        ui.warning(
            f"저장 보류 {skipped}개: 식별 정보 없음 {result['missing_identity']} · "
            f"형식 오류 {result['invalid_identity']} · 중복 충돌 {result['conflicts']} · "
            f"빈 항목 {result['empty']} · 한도 초과 {result['full']}"
        )
        for issue in result["issues"][:10]:
            source = issue["source"] or f"{issue['row']}번째 연락처"
            ui.caption(f"{source}: {issue['reason']}")
        if len(result["issues"]) > 10:
            ui.caption(f"외 {len(result['issues']) - 10}개. 표에서 값을 수정한 뒤 다시 저장하세요.")


def save_and_report(rows):
    contacts = st.session_state.setdefault("contacts", [])
    result = save_contacts(contacts, rows, max_contacts=MAX_CONTACTS)
    show_save_result(result)
    return result
