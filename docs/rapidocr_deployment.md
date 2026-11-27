# RapidOCR PP-OCRv5 한국어·영어 이중 인식 및 Streamlit 배포

## 1. 실행 구조

```text
OpenCV 보정 이미지
  -> 공통 Mobile Detection + Orientation
  -> Korean Mobile (한글·영문·숫자)
  -> 연락처 분류 / 누락·불확실성 검사
     -> 필요 시 대비 개선본으로 전체 검출 1회 추가
     -> 이름이 불확실하면 후보 영역 1개만 재인식
     -> 영문·숫자 연락처가 불확실하면 최대 6개 영역만 English Mobile로 재인식
  -> 유효값 보존 / 판독 불일치 경고 / 한국어 이름 후보 비교
  -> 기존 연락처 수정·검토·CSV·저장
```

평상시 검출은 한 번이다. 이름/연락처가 누락되거나 인식 줄이 부족할 때만 대비 개선본으로 전체 검출을 추가한다. 영어 보조 모델은 검출을 수행하지 않으며, 기존 방향 모델을 재사용한다. 모든 모델은 CPU 전용이고, 프로세스당 한국어/영어 엔진을 각각 최대 한 개씩 지연 로딩한다. OCR 동시 실행은 잠금으로 한 건만 허용하고 ONNX 스레드는 각 1개로 설정한다. 이미지 긴 변 1,800px, 검출 긴 변 1,600px, 인식 배치 2, 방향 배치 4, 보조 영역 최대 6개. 시간 예산은 잠금 대기와 추가 호출을 제한하지만, 진행 중인 ONNX 추론을 강제 취소하지는 않는다.

- Korean Mobile은 영어·숫자도 읽는다. 영어 모델은 필수 연락수단의 저신뢰/형식 오류/혼동 가능 문자를 중심으로 사용한다. 문자 점수는 경험적 판단용이며 두 모델의 보정된 정확도 확률이 아니다.
- 영어 재인식으로 확인된 형식 오류는 조건부 복구한다. 서로 다른 유효값이 나오면 원값을 보존하고 두 판독을 검토 대상으로 표시한다. 한글/회사명 등의 다른 문맥이 포함된 줄은 무단 교체하지 않는다. 기존 OCR이 검출하지 못한 글자까지 영어 모델이 반드시 복구할 수 있는 것은 아니다.
- 한국어 이름은 글자 사이 공백, 이름·직책 앞뒤 배치, 상대 글자 크기, 성씨 힌트, 주변 직책의 실제 좌표를 사용한다. 최대 3개 상위 후보를 표시하고 불확실하면 자동 확정하지 않는다. 기존 사용자 수정값 보존 로직은 변경하지 않는다.
- 기존 Tesseract를 `backend/ocr/tesseract_pipeline.py`에 보존한다. `OCR_ENGINE=tesseract` 또는 한자 요청으로 사용한다. 기본 모델 초기화 오류는 명시적으로 표시하고 조용히 다른 엔진으로 바꾸지 않는다.

## 2. 설치 및 실행

ZIP의 내부 파일을 기존 프로젝트 루트(app.py가 있는 폴더)에 그대로 덮어쓴 뒤 실행한다. 적용 스크립트는 필요하지 않다. 기존 setup.cmd가 RapidOCR 설치로 연결된다.

```powershell
.\setup.cmd
uv run --no-sync python -m pytest -q tests/test_rapidocr_upgrade.py tests/test_english_review.py
.\run.cmd
```

설치 스크립트는 아래를 순서대로 수행한다.

1. `uv sync --python 3.12`: 기존 의존성과 RapidOCR 3.10.0, CPU ONNX Runtime 설치 및 `uv.lock` 갱신.
2. `scripts/setup_rapidocr.py --smoke-test`: 네 모델을 다운로드한다. 공식 SHA-256을 확인하고, 파일당 25 MiB 이하만 허용하며, 임시 파일에 받은 뒤 정상 파일로 이동한다. 재실행 시 검증된 모델은 재다운로드하지 않는다.
3. 실제 CPU 검출/혼합 인식, 영어 이메일 줄 인식, 시스템 한글 폰트가 있으면 한글 이름 인식 테스트를 실행한다.
4. `uv lock --check` 및 기존 소스/앱 import 검사.

실제 모델 확인만 하려면:

```powershell
uv run --no-sync python scripts/setup_rapidocr.py --check-only --smoke-test
```

Linux 로컬/자체 서버 준비는 `bash scripts/setup_rapidocr_linux.sh`. 기존 한자/Tesseract 사용 시 Windows에서는 `setup.cmd -Tesseract`, Linux에서는 기존 `scripts/setup_linux.sh`를 별도 이용한다. Community Cloud에서는 이 설치 스크립트를 실행하지 않으므로 Git에 모델 파일을 함께 올려야 한다.

## 3. 배포 모델 파일

```text
models/ocr/
  detection.onnx
  korean_recognition.onnx
  english_recognition.onnx
  orientation.onnx
  NOTICE.md
  LICENSE-APACHE-2.0.txt
```

ONNX 파일 4개는 GitHub 일반 파일로 관리한다. 실제 합계는 설치 로그에 표시되며 모델의 원본 Paddle 형식 용량과 동일하다고 보장하지 않는다. Git LFS 포인터나 손상된 파일은 SHA-256 검사에서 거부된다. RapidOCR는 절대 경로를 지정해 위 파일만 사용하고, 앱에서는 모델 파일을 다운로드하지 않는다. 두 인식 모델에 내장된 문자 사전을 로드 전에 확인한다. 외부 OCR API는 호출하지 않는다.

## 4. GitHub에 올리기 (PowerShell)

기존 작업의 변경분을 확인하고 필요한 파일만 stage한다. 이 업데이트는 이미 챗봇이 통합된 GitHub 원본을 기준으로 한다. 연락처·챗봇 모듈은 교체하지 않으며, app.py는 해당 원본의 OCR 안내 문구만 변경한다.

```powershell
uv lock --check
uv run --no-sync python scripts/setup_rapidocr.py --check-only --smoke-test
git status --short
git check-attr filter -- models/ocr/*.onnx
git add app.py README_OCR_UPDATE.md backend/ocr backend/classifier frontend/batch_scanner.py frontend/scanner.py frontend/ocr_page.py frontend/ocr_flow.py scripts/setup_rapidocr.py scripts/setup_rapidocr_linux.sh setup.cmd setup_rapidocr.cmd models/ocr docs/rapidocr_deployment.md tests/test_rapidocr_upgrade.py tests/test_english_review.py pyproject.toml requirements.txt uv.lock .gitignore .env.example
git diff --cached --stat
git commit -m "Use dual Korean English RapidOCR ONNX"
git push
```

`git check-attr`의 filter 값이 `lfs`인 경우 모델 파일이 일반 Git 파일로 실제 업로드되는지 확인한다. `.env`, `.streamlit/secrets.toml`, `.venv`, 개인 명함, ZIP 및 이전 버전의 `rapidocr_update/` 폴더는 Git에 올리지 않는다. `packages.txt`의 Tesseract 패키지는 예비 엔진/한자 기능 때문에 유지한다.

## 5. Streamlit Community Cloud

- 저장소 및 배포 브랜치: 기존 설정 유지.
- Entry point: `app.py`.
- Python: 3.12 (기존 `pyproject.toml`은 >=3.12,<3.13).
- Secrets: OCR에는 불필요. 챗봇의 기존 `OPENAI_API_KEY`만 유지한다. `OCR_ENGINE`은 생략하면 rapidocr이며 필요한 경우 최상위 Secrets에 `OCR_ENGINE = "rapidocr"`로 명시한다.
- Cloud의 의존성 탐색에서 `uv.lock`이 `requirements.txt`보다 우선하므로 갱신된 lock 파일을 반드시 push한다. 설치 실패 시 배포 로그 확인 후 수정/재배포한다.
- 앱에서 명함 1장 → 5장 → 20장을 순서대로 테스트한다. 모델 초기화 시간, 1장 처리시간, 누락 필드/충돌 경고, RAM/CPU 리소스 오류를 점검한다. 다중 세션의 배치 이미지 메모리는 모델 외 별도 비용이다. 메모리 초과 시 이미지/업로드 배치 제한을 조정한다.

## 6. 검증 범위와 제한

- 모델 레지스트리: https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/default_models.yaml
- RapidOCR: https://pypi.org/project/rapidocr/3.10.0/
- ONNX Runtime: https://pypi.org/project/onnxruntime/1.23.2/
- Streamlit 의존성: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
- 모델 라이선스 및 출처: `models/ocr/NOTICE.md`.

제작 환경은 외부 모델 바이너리 다운로드 및 PyPI 설치가 불가능하여 ZIP에 실제 ONNX 파일과 새 `uv.lock`을 넣지 못했다. 교체 대상 GitHub 원본 파일의 Git blob 해시를 대조한 뒤 실제 교체 파일을 생성했고, 해당 분류 코드와 모의 OCR 입력을 사용한 회귀 테스트 28개가 통과했다. 테스트 환경은 기존 OCRLine/OCRResult 규격과 전처리 모듈을 재현해 사용했다. 실제 추론/브라우저 배포는 실행하지 못했으므로, 위 설치 스크립트의 실제 추론 검사까지 성공한 뒤 배포한다. 대표 한국어·영문 혼합 명함 20~50장의 이름/이메일/전화번호 완전 일치율과 처리시간으로 개선 효과를 비교하는 것을 권장한다.
