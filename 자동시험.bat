@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] 안내 엔진 + 통합 시험(실제 서버, 화면 없는 Edge, 진짜 모의 키오스크, 합성 손끝). 약 7분
".venv\Scripts\python.exe" -m pytest 07-demo\openkey-live\tests -q -p no:cacheprovider
echo.
echo [2/2] 관리자 콘솔 시험(모의 서버). 약 30초
".venv\Scripts\python.exe" -m pytest 07-demo\openkey-live\admin\dev\test_admin.py -q -p no:cacheprovider
echo.
echo 모두 PC 가상 시험입니다. 실제 휴대폰 시험은 07-demo\openkey-live\PHONE-TEST.md
pause
