@echo off
REM Double-click to remove what BloombergBridge added (startup entry, etc.).
REM No admin needed. Add  -RemoveCert  to also remove a self-signed trust.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
echo.
pause
