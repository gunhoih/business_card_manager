# Windows PowerShell 5.1 compatible.
# Recommended entrypoint: .\setup.cmd (process-scoped execution policy).
# This installer does not modify Git files or delete existing local work.
param(
    [switch]$SkipOcr
)

$ErrorActionPreference = 'Continue'
Push-Location -Path $PSScriptRoot -ErrorAction Stop

function Get-OcrEngine {
    # Capture only the executable path, not uv's progress messages.
    $output = @(& uv run --quiet --no-sync python scripts/setup_ocr.py --locate-engine 2>$null)
    $exitCode = $LASTEXITCODE
    $path = if ($exitCode -eq 0 -and $output.Count -gt 0) {
        [string]($output | Select-Object -Last 1)
    } else {
        ''
    }
    return [PSCustomObject]@{ ExitCode = $exitCode; Path = $path.Trim() }
}

try {
    Write-Host '[1/4] Checking project sources and Git conflicts'
    foreach ($relativePath in @(
        'app.py',
        'pyproject.toml',
        'frontend/ocr_page.py',
        'frontend/classifier_page.py',
        'backend/classifier/service.py',
        'scripts/check_install.py',
        'scripts/setup_ocr.py'
    )) {
        if (-not (Test-Path -LiteralPath $relativePath -PathType Leaf)) {
            throw "Missing project source: $relativePath. Check your Git checkout before installing."
        }
    }

    if (Get-Command git -ErrorAction SilentlyContinue) {
        $conflicts = @(& git diff --name-only --diff-filter=U 2>$null)
        if ($LASTEXITCODE -eq 0 -and $conflicts.Count -gt 0) {
            throw ('Unresolved Git conflicts: ' + ($conflicts -join ', ') + '. Finish or abort the merge/rebase first.')
        }
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv is missing. Install it with: winget install --id astral-sh.uv --exact, then restart the terminal.'
    }

    Write-Host '[2/4] Installing and synchronizing Python dependencies'
    & uv sync
    if ($LASTEXITCODE -ne 0) {
        throw 'uv sync failed. Check network access, Python 3.12 and dependency errors above.'
    }

    Write-Host '[3/4] Checking Python syntax and app imports'
    & uv run --no-sync python scripts/check_install.py
    if ($LASTEXITCODE -ne 0) {
        throw 'App validation failed. Source version mismatches cannot be fixed by reinstalling packages.'
    }

    if ($SkipOcr) {
        Write-Host '[4/4] OCR setup skipped by request' -ForegroundColor Yellow
        Write-Host 'NOTE: OCR pages will not work until full setup is run.' -ForegroundColor Yellow
    } else {
        Write-Host '[4/4] Checking and installing Tesseract OCR'
        $engine = Get-OcrEngine
        if ($engine.ExitCode -eq 2) {
            & uv run --no-sync python scripts/setup_ocr.py --locate-engine
            throw 'OCR_TESSERACT_CMD is invalid. Correct the environment variable and retry.'
        }

        if ($engine.ExitCode -ne 0) {
            if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
                throw 'Tesseract is missing and winget is unavailable. Install Tesseract OCR manually and run setup.cmd again.'
            }
            Write-Host 'Tesseract not found. Trying Windows Package Manager (winget).'
            & winget install --id UB-Mannheim.TesseractOCR --exact --accept-package-agreements --accept-source-agreements
            $wingetExitCode = $LASTEXITCODE
            if ($wingetExitCode -ne 0) {
                Write-Host "winget returned $wingetExitCode. Rechecking installed programs." -ForegroundColor Yellow
            }
            # Detection checks registry paths and common install directories.
            $engine = Get-OcrEngine
        }

        if ($engine.ExitCode -ne 0 -or -not $engine.Path) {
            throw 'Tesseract is not usable. Check: winget list --id UB-Mannheim.TesseractOCR -e; or set OCR_TESSERACT_CMD to tesseract.exe.'
        }

        $env:OCR_TESSERACT_CMD = $engine.Path
        Write-Host "Tesseract found: $($engine.Path)" -ForegroundColor Green
        & $engine.Path --version
        if ($LASTEXITCODE -ne 0) {
            throw 'Tesseract --version failed.'
        }

        & uv run --no-sync python scripts/setup_ocr.py --languages eng kor chi_tra
        if ($LASTEXITCODE -ne 0) {
            throw 'OCR language model installation or smoke test failed. Review the error above.'
        }
    }

    Write-Host ''
    Write-Host '[SUCCESS] Installation checks completed.' -ForegroundColor Green
    Write-Host 'Run the app: .\run.cmd'
}
catch {
    Write-Host ''
    Write-Host "[FAILED] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Source conflict? Run: git status' -ForegroundColor Yellow
    exit 1
}
finally {
    Pop-Location
}
