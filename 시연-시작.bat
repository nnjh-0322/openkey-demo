@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp007-demo\openkey-live\start-demo.ps1" %*
echo.
pause
