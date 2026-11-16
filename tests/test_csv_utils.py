import pytest

from frontend.csv_utils import export_contacts_csv, import_contacts_csv


def test_csv_round_trip_korean_and_comma():
    rows = [{
        "name": "김민수",
        "company": "에이, 비 회사",
        "department": "개발부",
        "position": "대리",
        "phone": "010-1234-5678",
        "email": "minsu@example.com",
        "website": "",
        "memo": "첫 번째 줄\n두 번째 줄",
        "created_at": "2026-11-16T10:00:00",
    }]
    content = export_contacts_csv(rows)
    assert content.startswith(b"\xef\xbb\xbf")
    imported = import_contacts_csv(content)
    assert imported[0]["name"] == "김민수"
    assert imported[0]["company"] == "에이, 비 회사"
    assert imported[0]["memo"] == "첫 번째 줄\n두 번째 줄"
    assert imported[0]["created_at"] == "2026-11-16T10:00:00"


def test_csv_formula_injection_guard():
    content = export_contacts_csv([{"name": "=1+1", "company": "@test"}])
    assert b"'=1+1" in content
    assert b"'@test" in content


def test_empty_csv_only_header():
    imported = import_contacts_csv(export_contacts_csv([]))
    assert imported == []


def test_csv_invalid_header():
    with pytest.raises(ValueError):
        import_contacts_csv("something,else\nhello,world\n".encode("utf-8"))


def test_csv_invalid_encoding():
    with pytest.raises(ValueError):
        import_contacts_csv(b"\xff\xfe\xff")


def test_csv_file_size_limit():
    with pytest.raises(ValueError):
        import_contacts_csv(b"x" * (2 * 1024 * 1024 + 1))


def test_csv_mismatched_columns():
    with pytest.raises(ValueError):
        import_contacts_csv(b"name,email\ntest,example@example.com,extra\n")
