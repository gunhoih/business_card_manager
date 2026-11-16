# Windows PowerShell 5.1 compatible. Run from the project root with setup.cmd.
# Installs Python dependencies, detects/installs Tesseract, then validates language models.
$ErrorActionPreference = 'Continue'
Push-Location $PSScriptRoot

function Get-OcrEngine {
    # uv's progress output is on stderr; capture only the discovered executable path.
    $output = & uv run --quiet python scripts/setup_ocr.py --locate-engine 2>$null
    $result = $LASTEXITCODE
    $path = if ($result -eq 0) { [string]($output | Select-Object -Last 1) } else { '' }
    return [PSCustomObject]@{ ExitCode = $result; Path = $path.Trim() }
}

try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv가 설치되어 있지 않습니다. https://docs.astral.sh/uv/ 에서 uv를 설치하세요.'
    }

    Write-Host '[1/3] Python 의존성 설치/동기화'
    & uv sync
    if ($LASTEXITCODE -ne 0) {
        throw 'uv sync에 실패했습니다. Python 3.12와 네트워크/패키지 설정을 확인하세요.'
    }

    Write-Host '[2/3] Tesseract 실행 파일 탐색 및 실제 실행 검사'
    $engine = Get-OcrEngine
    if ($engine.ExitCode -eq 2) {
        & uv run python scripts/setup_ocr.py --locate-engine
        throw 'OCR_TESSERACT_CMD 설정이 올바르지 않습니다. 해당 환경 변수를 수정하세요.'
    }

    if ($engine.ExitCode -ne 0) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Tesseract가 없고 winget도 없습니다. https://github.com/UB-Mannheim/tesseract/wiki 에서 엔진을 설치하세요.'
        }
        Write-Host 'Tesseract가 없어 winget 설치를 시도합니다. 설치/관리자 승인 화면을 확인해 주세요.'
        & winget install --id UB-Mannheim.TesseractOCR --exact --accept-package-agreements --accept-source-agreements
        $installExit = $LASTEXITCODE
        if ($installExit -ne 0) {
            Write-Host "[주의] winget 종료 코드: $installExit" -ForegroundColor Yellow
            Write-Host '설치된 엔진이 있는지 다시 탐색합니다.'
        }
        # winget 성공 뒤 PATH가 반영되지 않더라도 레지스트리/사용자별 경로를 다시 확인합니다.
        $engine = Get-OcrEngine
    }

    if ($engine.ExitCode -ne 0 -or -not $engine.Path) {
        Write-Host '[실패] winget의 설치 성공 표시와 별개로, 실행 가능한 tesseract.exe를 찾지 못했습니다.' -ForegroundColor Red
        Write-Host 'winget list --id UB-Mannheim.TesseractOCR -e 로 설치 목록을 확인하세요.'
        Write-Host '비표준 폴더에 설치했다면 실행 파일 전체 경로를 OCR_TESSERACT_CMD에 지정하세요.'
        Write-Host '예: $env:OCR_TESSERACT_CMD = "D:\Programs\Tesseract-OCR\tesseract.exe"'
        Write-Host '실제 설치가 누락되었다면 UB Mannheim 설치 관리자를 다시 실행해야 할 수 있습니다.'
        throw 'Tesseract 실행 파일 검증에 실패했습니다. 언어 모델 문제는 아닙니다.'
    }

    # 이번 PowerShell 세션과 자식 프로세스에서만 사용한다. 영구 PATH/사용자 변수는 변경하지 않는다.
    $env:OCR_TESSERACT_CMD = $engine.Path
    Write-Host "[확인] Tesseract: $($engine.Path)" -ForegroundColor Green
    & $engine.Path --version
    if ($LASTEXITCODE -ne 0) { throw 'Tesseract --version 실행에 실패했습니다.' }

    Write-Host '[3/3] 영어/한국어/한자 모델 다운로드 + 무결성 검사 + OCR 실행 검사'
    & uv run python scripts/setup_ocr.py --languages eng kor chi_tra
    if ($LASTEXITCODE -ne 0) {
        throw 'OCR 모델 설치 또는 실제 실행 검사에 실패했습니다. 위 오류의 원인을 확인하세요.'
    }

    Write-Host ''
    Write-Host '[완료] OCR 설치 검사를 통과했습니다.' -ForegroundColor Green
    Write-Host '앱 실행: uv run streamlit run app.py'
}
catch {
    Write-Host "[설치 중단] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
