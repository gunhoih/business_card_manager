# Business Card Manager

**OpenCV, Tesseract OCR, 선택적 OpenAI 챗봇을 활용한 명함 인식 및 연락처 관리 웹 애플리케이션**

명함을 이미지로 입력받아 원근 보정하고, 한국어·영어(선택적으로 한자) 텍스트를 OCR로 인식한 뒤 직접 확인·수정해 연락처로 관리합니다. 필요한 경우 추출한 정보를 OpenAI 기반 챗봇에서 참고하도록 할 수 있습니다.

## 개발 목표 및 상태

| 단계 | 주요 기능 | 현재 상태 |
|---|---|---|
| 0. 프런트엔드 | Streamlit 다중 페이지, 파일/카메라 입력, 연락처 편집 및 CSV | 구현 |
| 1. 수동 스캔 | 4개 꼭짓점 지정 및 OpenCV 호모그래피 | 구현 |
| 2. 텍스트 인식 | Tesseract OCR, 한국어·영어·한자, 기본 줄 그룹화 | 구현 (별도 OCR 페이지) |
| 3. 자동 스캔 | 윤곽선·사각형 검출 | 구현 |
| 4. 정보 검증 | 이메일·전화번호·웹사이트 후보 추출, 사용자 수정 | 부분 구현 |
| 5. 연락처 관리 | 목록, 검색, 편집, 삭제 및 CSV 입출력 | 구현 |
| 6. 챗봇 | OpenAI SDK로 현재 명함/선택 연락처에 질문 | 선택 기능 구현 (API 키 필요) |

> **주의:** 기존 **AI 텍스트 인식 및 구조화** 버튼은 아직 연결하지 않았습니다. 대신 새 **OCR 텍스트 인식** 메뉴에서 Tesseract를 실행합니다. 이름·회사·직책은 OCR만으로 안정적인 의미 분류가 어려우므로 수동으로 확인·수정해야 합니다.

## 화면 구성

- **명함 인식**: 이미지 업로드·카메라 촬영, 수동 네 꼭짓점 선택 및 자동 카드 영역 탐지, 원근 보정, 연락처 수정 폼
- **OCR 텍스트 인식**: 언어 및 배치 모드 선택, 텍스트·줄 그룹·신뢰도·좌표 확인, 연락처 패턴 추출
- **연락처 관리**: 세션 연락처 목록, 검색·수정·삭제, CSV 가져오기·내보내기
- **명함 챗봇**: 현재 명함 또는 선택한 연락처 한 명에 대해 질문 (OpenAI API 키 필요)

## 실행

Windows PowerShell에서는 다음을 실행합니다.

```powershell
.\setup.ps1
uv run streamlit run app.py
```

`setup.ps1`은 `uv sync`, Tesseract 실행 엔진 설치/확인, `eng`·`kor`·`chi_tra` OCR 언어 모델 다운로드/확인을 진행합니다. Tesseract는 `uv`로 설치하는 Python 패키지가 아닌 시스템 프로그램입니다. 자세한 설치·Cloud 배포 가이드는 **[README_OCR_CHAT.md](README_OCR_CHAT.md)** 를 확인하세요.

Streamlit Community Cloud에서는 루트의 `packages.txt`로 OCR 엔진과 언어 데이터를 자동 설치합니다. Python 의존성은 `pyproject.toml`, `requirements.txt`에 적혀 있습니다. `uv.lock`을 추가했다면 새 의존성과 일치하도록 갱신해 커밋하세요.

## 주요 구조

```text
BusinessCardManager/
├── app.py
├── frontend/
│   ├── scanner.py              # 기존 수동/자동 스캔 UI
│   ├── ocr_page.py             # Tesseract OCR 페이지
│   ├── chat_page.py            # 선택적 명함 챗봇 UI
│   ├── contacts.py             # 연락처 관리
│   └── state.py                # 세션 상태
├── backend/
│   ├── image/                  # 기존 OpenCV 호모그래피
│   ├── ocr/service.py          # OCR + 줄/좌표 추출
│   ├── contact/field_parser.py # 이메일/전화/URL 후보
│   ├── contact/csv_service.py  # CSV 입출력
│   └── chat/service.py         # OpenAI 기반 응답
├── scripts/setup_ocr.py       # 공식 언어 모델 다운로드
├── packages.txt               # Streamlit Cloud 시스템 패키지
├── setup.ps1                  # Windows 로컬 초기화
└── README_OCR_CHAT.md          # OCR 및 챗봇 설정 설명
```

## 데이터 및 개인정보

- OCR 인식은 로컬 Tesseract로 처리하며 외부 AI API를 호출하지 않습니다.
- 챗봇은 질문할 때만 선택한 명함의 정보가 OpenAI API로 전송됩니다. 실제 명함은 개인정보 보호에 주의하세요.
- 연락처는 Streamlit 세션에만 임시 저장됩니다. 종료 전에 CSV 파일로 내려받아야 합니다.
- `data/ocr/` 모델 파일과 `.env`, `.streamlit/secrets.toml`은 Git에 올리지 않습니다.
