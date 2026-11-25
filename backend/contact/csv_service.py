"""기존 import 경로 호환용. 실제 연락처 저장 및 CSV 처리는 card_storage에 있다."""

from backend.card_storage.csv_service import (
    export_contacts_csv, export_dataset_csv, import_contacts_csv, safe_csv_value,
)
from backend.card_storage.schema import (
    CONTACT_FIELDS, CSV_FIELDS, FIELD_LABELS, MAX_CONTACTS, MAX_CSV_SIZE,
)
from backend.card_storage.service import filter_new_contacts

__all__ = [
    "CONTACT_FIELDS", "CSV_FIELDS", "FIELD_LABELS", "MAX_CONTACTS", "MAX_CSV_SIZE",
    "export_contacts_csv", "export_dataset_csv", "import_contacts_csv", "safe_csv_value",
    "filter_new_contacts",
]
