@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo OpenKey 시연 환경 설치 (처음 한 번만)
echo.
rem Python 3.13, 3.12, 그 밖의 3.x 순서로 고른다(시험용 패키지가 3.14용 설치 파일이 없음)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 파이썬 가상환경 .venv 만들기
  py -3.13 -m venv .venv 2>nul || py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo [!] 파이썬을 찾지 못했습니다. python.org에서 Python 3.13을 설치하고 다시 실행하세요.
    pause
    exit /b 1
  )
) else (
  echo [1/3] .venv 이미 있음
)
".venv\Scripts\python.exe" --version
echo [2/3] 패키지 설치 - 시연용
".venv\Scripts\python.exe" -m pip install -q -r 07-demo\openkey-live\requirements.txt
if errorlevel 1 (
  echo [!] 시연용 패키지 설치에 실패했습니다. 인터넷 연결을 확인하세요.
  pause
  exit /b 1
)
echo [2/3] 패키지 설치 - 자동 시험용
".venv\Scripts\python.exe" -m pip install -q -r 07-demo\openkey-live\requirements-test.txt
if errorlevel 1 echo [!] 시험용 패키지 설치 실패. 시연은 되지만 자동시험.bat은 안 됩니다. .venv를 지우고 Python 3.13으로 다시 만드세요.
echo [3/3] 시연용 인증서(work\live-capture-cert)
".venv\Scripts\python.exe" 07-demo\openkey-live\make_cert.py
echo.
echo 끝났습니다. 시연-시작.bat 으로 켜고, 자동시험.bat 으로 PC 시험을 돌릴 수 있습니다.
pause
