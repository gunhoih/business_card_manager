"""Tesseract 없이 분류 알고리즘만 실행하는 학습용 예제.

실행: python examples/classify_demo.py
"""

from pathlib import Path
import sys

# ZIP을 압축해제한 상태와 실제 프로젝트에 설치한 상태 모두 실행 가능.
HERE = Path(__file__).resolve().parent.parent
if (HERE / "payload").is_dir():
    sys.path.insert(0, str(HERE / "payload"))
else:
    sys.path.insert(0, str(HERE))

from backend.classifier.service import build_contact_fields, classify_text

sample = """(주)샘플테크
홍길동
AI개발팀
팀장
Tel: 010-1234-5678 Fax: 02-123-4567
E-mail: hong@example.com
www.example.com
서울특별시 강남구 테헤란로 123"""

print("=" * 55)
print("1. OCR에서 읽은 원문")
print(sample)
print("\n2. 규칙으로 자동 분류")
rows = classify_text(sample)
for row in rows:
    print(f"{row['text']:32} => {row['predicted_type']:12} ({row['score']}점)")
    print("    이유:", "; ".join(row["reasons"]))

print("\n3. 수동 변경 예시: 첫 번째 '이름' 후보를 사용자가 수정")
for row in rows:
    if row["selected_type"] == "name":
        row["value"] = "홍길동"
        row["manual"] = True
        break

fields, warnings = build_contact_fields(rows)
print("\n4. 최종 연락처")
for key, value in fields.items():
    print(f"{key:12} : {value}")
for warning in warnings:
    print("주의:", warning)
