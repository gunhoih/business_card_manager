@echo off
setlocal
REM Only this child PowerShell process uses ExecutionPolicy Bypass.
REM This does not change the user or machine execution policy.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
exit /b %ERRORLEVEL%
