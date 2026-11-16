# Business Card Manager

**OpenCV와 LLM을 활용한 명함 스캔 및 연락처 관리 웹 애플리케이션**

## 프로젝트 소개

Business Card Manager는 사진으로 촬영한 명함을 **OpenCV로 스캔한 것처럼 보정**하고, **OpenAI Vision API로 이름·회사·직책·전화번호·이메일 등을 구조화**하여 연락처로 정리하는 Streamlit 웹 애플리케이션입니다.

단순히 AI 결과를 출력하는 데 그치지 않고, **이미지 보정 → 정보 추출 → 형식 검증 → 사용자 확인 → 연락처 관리** 과정을 구현하는 것이 목표입니다.

- **개발 목적:** 소프트웨어 실습 최종과제 및 취업 포트폴리오
- **주요 기술:** Python, Streamlit, OpenCV, NumPy, OpenAI API, Pydantic
- **개발 원칙:** 기능별 모듈 분리, 단계별 완성, 실제 결과 검증
- **배포 목표:** Streamlit Community Cloud

## 단계별 구현 목표

| 단계 | 구현 계획 | 성취 목표 |
|---|---|---|
| **0. 개발 환경 구성** | Streamlit 화면, 프로젝트 폴더 및 `uv` 의존성 설정 | 이미지를 업로드하고 화면에 표시한다. |
| **1. 수동 명함 스캔** | 명함의 네 꼭짓점을 직접 선택하고 OpenCV 호모그래피 적용 | 비스듬히 촬영한 명함을 정면 이미지로 보정한다. |
| **2. LLM 정보 추출** | OpenAI Vision API와 구조화된 응답 사용 | 이름·소속·직책·전화번호·이메일을 구분해 표시한다. |
| **3. 자동 명함 감지** | 윤곽선·사각형 탐지로 명함 영역 자동 검출 | 수동 선택 없이 명함을 보정하고, 실패하면 수동 모드로 전환한다. |
| **4. 정보 검증 및 수정** | 이메일·전화번호 형식 검사, 누락 정보 표시, 직접 수정 | 부정확한 인식 결과를 사용자가 확인하고 보정할 수 있다. |
| **5. 연락처 관리** | 연락처 목록·검색, 중복 탐지, CSV·vCard 내보내기 | 추출한 정보를 실제로 관리하고 파일로 저장한다. |

## 전체 처리 흐름

**명함 이미지 업로드 → OpenCV 보정 → LLM 정보 추출 → 형식 검증 및 사용자 수정 → 연락처 목록 → 파일 다운로드**

## 프로젝트 구조 (예정)

개발 단계별 폴더가 아니라 **기능별로 구분**하고, 각 단계의 진행 내용은 `docs/`에 기록합니다.

```text
BusinessCardManager/
├── app.py                     # Streamlit 실행 진입점
├── frontend/                  # 화면 및 사용자 입력
│   ├── scanner.py             # 명함 스캔 화면
│   └── contacts.py            # 연락처 관리 화면
├── backend/
│   ├── image/                 # 호모그래피, 자동 명함 탐지
│   ├── ai/                    # LLM 추출 및 응답 스키마
│   └── contact/               # 정보 검증, 중복 검사, 내보내기
├── tests/                     # 핵심 기능 테스트
├── docs/                      # 단계별 기록 및 결과
├── pyproject.toml             # uv 프로젝트 의존성
├── requirements.txt           # Streamlit 배포용 의존성
└── README.md
```

> 위 구조는 목표 구성입니다. 처음에는 1단계에 필요한 파일부터 만들고 기능을 추가하며 확장합니다.

## 실행 환경

- **Python:** 3.12
- **패키지 관리:** `uv` (`pyproject.toml`, 추후 생성할 `uv.lock`)
- **주요 패키지:** `streamlit`, `opencv-python-headless`, `numpy`, `Pillow`, `openai`, `pydantic`, `streamlit-image-coordinates`

```powershell
uv sync
# app.py 작성 후 실행
uv run streamlit run app.py
```

OpenAI API 키는 로컬의 `.streamlit/secrets.toml` 또는 배포 환경의 Streamlit Secrets에 설정하고, GitHub에 공개하지 않습니다.

## 개발 및 배포 시 고려 사항

- **OpenCV 영역은 직접 구현**하고, LLM은 문자 인식과 정보 구조화에 사용합니다.
- 명함에 없는 정보는 추측해서 채우지 않고, 사용자 확인·수정을 거쳐 저장합니다.
- Streamlit Community Cloud의 임시 저장 특성을 고려하여 우선 **세션 내 연락처 관리와 CSV·vCard 다운로드**를 구현합니다.
- 실제 명함에는 개인정보가 있으므로 공개 시연에는 **가상 명함**을 사용합니다.
- 각 단계에서 보정 전후 이미지, 추출 결과와 오류 사례를 기록해 포트폴리오에 반영합니다.

> **현재 상태:** 프로젝트 범위 및 개발 계획 확정. 실제 기능은 단계별로 구현 예정입니다.
