"""연락처 목록과 CSV에서 공통으로 사용하는 필드와 제한."""

CONTACT_FIELDS = [
    "name", "company", "department", "position", "phone", "fax",
    "email", "website", "address", "memo",
]
CSV_FIELDS = CONTACT_FIELDS + ["created_at"]
FIELD_LABELS = {
    "name": "이름", "company": "회사·소속", "department": "부서",
    "position": "직책", "phone": "전화번호", "fax": "팩스",
    "email": "이메일", "website": "웹사이트", "address": "주소", "memo": "메모",
}
MAX_CSV_SIZE = 2 * 1024 * 1024
MAX_CONTACTS = 2000
