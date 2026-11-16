@echo off
setlocal
REM Windows PowerShell execution policy is limited to this setup process.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
exit /b %ERRORLEVEL%
