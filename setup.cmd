@echo off
setlocal
REM Default: prepare the dual Korean/English RapidOCR environment.
if /I "%~1"=="-Tesseract" goto tesseract
if /I "%~1"=="-SkipOcr" goto skipocr
if not "%~1"=="" (
  echo Usage: setup.cmd [-Tesseract ^| -SkipOcr]
  exit /b 2
)
call "%~dp0setup_rapidocr.cmd"
exit /b %ERRORLEVEL%

:tesseract
REM Optional: retain the original Windows Tesseract installer.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
exit /b %ERRORLEVEL%

:skipocr
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -SkipOcr
exit /b %ERRORLEVEL%
