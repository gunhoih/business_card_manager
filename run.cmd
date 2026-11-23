@echo off
setlocal
pushd "%~dp0" || exit /b 1
where uv >nul 2>&1
if errorlevel 1 (
  echo [FAILED] uv not found. Run setup.cmd after installing uv.
  popd
  exit /b 1
)
uv run --no-sync python scripts/check_install.py
if errorlevel 1 (
  echo [FAILED] App source check failed. Run setup.cmd or inspect git status.
  popd
  exit /b 1
)
uv run --no-sync streamlit run app.py
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
