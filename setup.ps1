# Windows: 이 스크립트 한 번으로 Python 의존성, Tesseract 엔진, OCR 언어 모델을 준비합니다.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv 명령이 없습니다. 먼저 https://docs.astral.sh/uv/ 에서 uv를 설치해 주세요."
}

Write-Host "[1/3] Python 의존성 설치 (uv sync)"
& uv sync
if ($LASTEXITCODE -ne 0) { throw "uv sync 실패: Python 3.12 및 네트워크를 확인하세요." }

Write-Host "[2/3] Tesseract 실행 엔진 확인"
$engine = Get-Command tesseract -ErrorAction SilentlyContinue
$commonPath = Join-Path $env:ProgramFiles "Tesseract-OCR\tesseract.exe"
if (-not $engine -and -not (Test-Path $commonPath) -and -not $env:OCR_TESSERACT_CMD) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Tesseract가 없고 winget도 없습니다. UB Mannheim Tesseract OCR을 설치한 후 다시 실행하세요."
    }
    Write-Host "Tesseract 엔진이 없어 winget으로 설치합니다. Windows 승인이 필요할 수 있습니다."
    & winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Tesseract 엔진 설치가 완료되지 않았습니다." }
}

Write-Host "[3/3] 한국어, 영어, 한자 OCR 모델 다운로드 및 검사"
& uv run python scripts/setup_ocr.py --languages eng kor chi_tra
if ($LASTEXITCODE -ne 0) {
    throw "언어 모델 준비/검사에 실패했습니다. Tesseract 설치 경로와 인터넷 연결을 확인하세요."
}

Write-Host "준비 완료: uv run streamlit run app.py"
