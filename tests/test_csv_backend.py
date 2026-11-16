import pytest

from backend.contact.csv_service import (
    CONTACT_FIELDS,
    export_contacts_csv,
    filter_new_contacts,
    import_contacts_csv,
)


def test_export_and_import_korean_contact():
    contacts = [{
        "name": "김건호",
        "company": "에이, 비 연구소",
        "phone": "010-1234-5678",
        "email": "user@example.com",
        "memo": "첫 줄\n둘째 줄",
        "created_at": "2026-11-16T12:00:00",
    }]
    content = export_contacts_csv(contacts)
    assert content.startswith(b"\xef\xbb\xbf")
    rows = import_contacts_csv(content)
    assert rows[0]["name"] == "김건호"
    assert rows[0]["company"] == "에이, 비 연구소"
    assert rows[0]["memo"] == "첫 줄\n둘째 줄"
    assert rows[0]["created_at"] == "2026-11-16T12:00:00"
    assert len(rows[0]) == len(CONTACT_FIELDS) + 1


def test_import_empty_and_malformed_csv():
    assert import_contacts_csv(export_contacts_csv([])) == []
    with pytest.raises(ValueError):
        import_contacts_csv(b"random,columns\na,b\n")
    with pytest.raises(ValueError):
        import_contacts_csv(b"name,email\nA,a@example.com,extra\n")
    with pytest.raises(ValueError):
        import_contacts_csv(b"name,name\nA,B\n")


def test_csv_formula_cells_are_escaped():
    content = export_contacts_csv([{"name": " =SUM(1,2)", "email": "@abc"}])
    assert b"' =SUM(1,2)" in content
    assert b"'@abc" in content


def test_duplicate_rows_skipped_without_dropping_different_people():
    existing = [{"name": "홍길동", "email": "hong@example.com"}]
    imported = [
        {"name": "홍길동", "email": "hong@example.com"},
        {"name": "김민수", "email": "minsu@example.com"},
        {"name": "김민수", "email": "minsu@example.com"},
    ]
    new_rows, count = filter_new_contacts(imported, existing)
    assert count == 2
    assert len(new_rows) == 1
    assert new_rows[0]["name"] == "김민수"


def test_too_many_contacts_are_rejected():
    data = ("name\n" + "\n".join("A" for _ in range(2001)) + "\n").encode()
    with pytest.raises(ValueError, match="2,000"):
        import_contacts_csv(data)
