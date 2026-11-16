# Business Card Manager

**OpenCV와 LLM을 활용한 명함 인식 및 연락처 관리 웹 애플리케이션**

명함을 이미지로 입력받아 원근 보정하고, Vision LLM으로 이름·회사·직책·전화번호·이메일을 구조화하여 연락처로 관리하는 것을 목표로 합니다.

## 개발 목표

| 단계 | 주요 기능 | 성취 목표 |
|---|---|---|
| 0. 프런트엔드 | Streamlit 두 페이지, 파일/카메라 입력, 연락처 편집 및 CSV | 백엔드 없이 화면·데이터 흐름 테스트 |
| 1. 수동 스캔 | 4개 꼭짓점 지정 및 OpenCV 호모그래피 | 기울어진 명함 이미지 보정 |
| 2. AI 정보 추출 | OpenAI Vision + Structured Outputs | 이미지에서 연락처 정보 구조화 |
| 3. 자동 스캔 | 윤곽선·사각형 검출 | 명함 영역 자동 탐지 |
| 4. 정보 검증 | 전화번호·이메일 확인, 직접 수정 | 불확실한 결과를 사용자 확인 후 저장 |
| 5. 연락처 관리 | 검색, 중복 검사 및 CSV 내보내기 | 실제 연락처 목록 관리 |

## 화면 구성

- **명함 인식:** 이미지 업로드·카메라 촬영, 수동 좌표 선택, 자동 감지 자리, 스캔 결과, OCR·정보 구조화 편집 폼
- **연락처 관리:** 세션 연락처 목록, 검색, 수정, 삭제, CSV 가져오기·내보내기

> **현재 구현 상태:** 프런트엔드 화면과 세션 기반 CSV 관리 기능을 구현했습니다. 수동 꼭짓점 선택은 작동하지만 OpenCV 변환과 AI 인식은 아직 연결되지 않아 버튼이 비활성화되어 있습니다. 가짜 OCR 결과를 생성하지 않습니다.

## 폴더 구조

```text
BusinessCardManager/
├── app.py                         # Streamlit 실행
├── frontend/
│   ├── scanner.py                 # 명함 스캔 및 AI 추출 UI
│   ├── contacts.py                # 연락처 관리 및 CSV UI
│   ├── state.py                   # 세션 상태 관리
│   └── csv_utils.py               # CSV 입출력
├── backend/
│   └── image/                     # 호모그래피 및 자동 감지 (추후 구현)
├── tests/
├── .streamlit/
├── pyproject.toml
├── requirements.txt
└── README.md
```

## 실행

```powershell
uv sync
uv run streamlit run app.py
```

연락처는 `st.session_state`에 임시 저장됩니다. Streamlit 서버를 다시 시작하거나 세션이 만료되면 사라질 수 있으므로 CSV를 내려받아 보관해야 합니다. 다음 접속 시 저장한 CSV를 다시 업로드할 수 있습니다.

OpenAI API 키는 나중에 백엔드를 연결할 때 `.streamlit/secrets.toml` 또는 Streamlit Cloud Secrets에 설정합니다. 실제 명함의 개인정보는 공개 저장소나 시연 화면에 노출하지 않습니다.

## 현재 실행 가능한 기능

- 명함 이미지 업로드 또는 카메라 촬영
- 수동 네 꼭짓점 선택 후 OpenCV 호모그래피 보정
- OpenCV Contour 기반 명함 영역 자동 감지 및 원근 보정
- 보정된 명함 PNG 다운로드
- 명함 정보를 직접 입력해 임시 연락처 목록에 추가
- 연락처 검색, 수정, 삭제 및 CSV 업로드·미리보기·다운로드

> 아직 OpenAI API를 호출하지 않습니다. 명함의 텍스트 인식 및 필드 자동 추출은 다음 단계에서 구현합니다. 연락처는 세션 종료 시 사라지므로 CSV로 내려받아 보관해야 합니다.
