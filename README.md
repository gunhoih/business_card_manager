# Business Card Manager

**OpenCV, Tesseract OCR, 선택적 OpenAI 챗봇을 활용한 명함 인식 및 연락처 관리 웹 애플리케이션**

명함을 이미지로 입력받아 원근 보정하고, 한국어·영어(선택적으로 한자) 텍스트를 OCR로 인식한 뒤 직접 확인·수정해 연락처로 관리합니다. 필요한 경우 연락처 관리 화면의 우측 AI 도우미에서 현재 연락처를 조회할 수 있습니다.

## 개발 목표 및 상태

| 단계 | 주요 기능 | 현재 상태 |
|---|---|---|
| 0. 프런트엔드 | Streamlit 다중 페이지, 파일/카메라 입력, 연락처 편집 및 CSV | 구현 |
| 1. 수동 스캔 | 4개 꼭짓점 지정 및 OpenCV 호모그래피 | 구현 |
| 2. 텍스트 인식 | Tesseract OCR, 한국어·영어·한자, 기본 줄 그룹화 | 구현 (별도 OCR 페이지) |
| 3. 자동 스캔 | 윤곽선·사각형 검출 | 구현 |
| 4. 정보 검증 | 이메일·전화번호·웹사이트 후보 추출, 사용자 수정 | 부분 구현 |
| 5. 연락처 관리 | 목록, 검색, 편집, 삭제 및 CSV 입출력 | 구현 |
| 6. 챗봇 | 연락처 관리 화면에서 자연어 검색, 상세 조회 및 집계 | 선택 기능 구현 (API 키 필요) |

> **주의:** 기존 **AI 텍스트 인식 및 구조화** 버튼은 아직 연결하지 않았습니다. 대신 새 **OCR 텍스트 인식** 메뉴에서 Tesseract를 실행합니다. 이름·회사·직책은 OCR만으로 안정적인 의미 분류가 어려우므로 수동으로 확인·수정해야 합니다.

## 화면 구성

- **명함 데이터 추출**: 일괄 이미지 처리, OCR, 연락처 확인 및 저장
- **개별 명함 스캔**: 이미지 업로드·카메라 촬영, 수동 네 꼭짓점 선택 및 자동 카드 영역 탐지, 원근 보정, 연락처 수정 폼
- **OCR 텍스트 인식**: 언어 및 배치 모드 선택, 텍스트·줄 그룹·신뢰도·좌표 확인, 연락처 패턴 추출
- **연락처 관리**: 세션 연락처 목록, 검색·수정·삭제, CSV 가져오기·내보내기
  - 우측 **AI 연락처 도우미**: 버튼으로 열고 닫는 읽기 전용 챗봇 (OpenAI API 키 필요)
  - 조회 대상: 전체 연락처, 현재 검색 결과, 선택한 연락처, 미저장 개별 스캔 명함
  - 연락처를 저장하거나 수정하면 다음 질문은 최신 데이터를 조회하며 이전 데이터 기준의 대화는 API에 재전송하지 않습니다.

자세한 통합 화면 사용법과 검증 절차는 [연락처 AI 도우미 안내](docs/contact_chat_update.md)를 확인하세요.

## 설치
```powershell
.\setup.cmd
```

## 실행
Windows PowerShell에서는 다음을 실행합니다.

```powershell
.\run.cmd
```

`setup.ps1`은 `uv sync`, Tesseract 실행 엔진 설치/확인, `eng`·`kor`·`chi_tra` OCR 언어 모델 다운로드/확인을 진행합니다. Tesseract는 `uv`로 설치하는 Python 패키지가 아닌 시스템 프로그램입니다.

Streamlit Community Cloud에서는 루트의 `packages.txt`로 OCR 엔진과 언어 데이터를 자동 설치합니다. Python 의존성은 `pyproject.toml`, `requirements.txt`에 적혀 있습니다. `uv.lock`을 추가했다면 새 의존성과 일치하도록 갱신해 커밋하세요.

## 주요 구조

```text
BusinessCardManager/
├── app.py
├── frontend/
│   ├── scanner.py              # 기존 수동/자동 스캔 UI
│   ├── ocr_page.py             # Tesseract OCR 페이지
│   ├── chat_page.py            # 연락처 관리 화면의 AI 도우미 패널
│   ├── contact_chat_state.py   # 조회 범위 및 데이터별 대화 관리
│   ├── contacts.py             # 연락처 관리 및 패널 배치
│   └── state.py                # 세션 상태
├── backend/
│   ├── image/                  # 기존 OpenCV 호모그래피
│   ├── ocr/service.py          # OCR + 줄/좌표 추출
│   ├── contact/field_parser.py # 이메일/전화/URL 후보
│   ├── card_storage/           # 연락처 저장·조회·CSV
│   └── agent/                  # OpenAI 도구 기반 연락처 조회
├── scripts/setup_ocr.py       # 공식 언어 모델 다운로드
├── packages.txt               # Streamlit Cloud 시스템 패키지
└── setup.ps1                  # Windows 로컬 초기화
```

## 데이터 및 개인정보

- OCR 인식은 로컬 Tesseract로 처리하며 외부 AI API를 호출하지 않습니다.
- AI 도우미는 동의 후 질문할 때만 OpenAI API를 호출합니다. 질문, 현재 데이터 기준 최근 대화 및 필요한 조회 결과가 전송되며 명함 이미지와 OCR 원문은 전송하지 않습니다.
- AI 도우미는 읽기 전용이며 연락처를 직접 등록·수정·삭제하지 않습니다.
- 연락처 및 대화는 Streamlit 세션에만 임시 저장됩니다. 종료 전에 연락처를 CSV 파일로 내려받아야 합니다.
- `data/ocr/` 모델 파일과 `.env`, `.streamlit/secrets.toml`은 Git에 올리지 않습니다.
