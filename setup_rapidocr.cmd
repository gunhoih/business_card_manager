@echo off
setlocal
pushd "%~dp0" || exit /b 1
where uv >nul 2>&1
if errorlevel 1 (
  echo [FAILED] uv not found. Install uv first.
  popd
  exit /b 1
)
uv sync --python 3.12
if errorlevel 1 goto failed
uv run --no-sync python scripts/setup_rapidocr.py --smoke-test
if errorlevel 1 goto failed
uv lock --check
if errorlevel 1 goto failed
uv run --no-sync python scripts/check_install.py
if errorlevel 1 goto failed
echo [OK] RapidOCR setup completed. Commit models/ocr and uv.lock before deploying.
popd
exit /b 0
:failed
echo [FAILED] Setup stopped. Review the error above.
popd
exit /b 1
