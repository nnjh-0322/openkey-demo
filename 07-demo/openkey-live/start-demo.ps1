# OpenKey 시연 시작: 이 창에서 서버(8460)를 켜고, 서버가 준비되면 노트북 키오스크·관리자 콘솔을 연다.
# 루트의 "시연-시작.bat"이 이 파일을 부른다. 끌 때는 이 창에서 Ctrl+C.
# 사용자가 켠 다른 서버(8443·8444)는 건드리지 않는다.
param([int]$Port = 8460, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$py = Join-Path $root '.venv\Scripts\python.exe'
$server = Join-Path $root '07-demo\openkey-live\server.py'
$cert = Join-Path $root 'work\live-capture-cert\cert.pem'

if (-not (Test-Path $py)) { Write-Host "[!] .venv가 없습니다. 루트의 환경-설치.bat을 먼저 실행하세요." -ForegroundColor Yellow; exit 1 }
if (-not (Test-Path $cert)) {
    Write-Host "인증서가 없어 새로 만듭니다(work\live-capture-cert, 저장소에는 올리지 않음)..."
    & $py (Join-Path $root '07-demo\openkey-live\make_cert.py')
    if (-not (Test-Path $cert)) { Write-Host "[!] 인증서를 만들지 못했습니다. 위 메시지를 확인하세요." -ForegroundColor Yellow; exit 1 }
}

$urls = @("https://localhost:$Port/kiosk-host", "https://localhost:$Port/admin/")
$busy = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($busy) {
    Write-Host "포트 $Port 에 이미 서버가 켜져 있습니다. 새로 켜지 않고 화면만 엽니다."
    if (-not $NoBrowser) { foreach ($u in $urls) { Start-Process $u; Start-Sleep -Milliseconds 800 } }
    exit 0
}

Write-Host "노트북 키오스크 : $($urls[0])   (F11 전체 화면, 이 탭은 닫지 않기)"
Write-Host "관리자 콘솔     : $($urls[1])"
Write-Host "휴대폰 주소는 아래 서버 첫 줄들에 찍힙니다(같은 Wi-Fi). 처음에는 인증서 경고 -> '고급' -> '계속'."
Write-Host "휴대폰은 화면을 한 번 눌러야 소리가 납니다. 순서: 지금-테스트하기.md"
Write-Host "끌 때는 이 창에서 Ctrl+C"
Write-Host ""

if (-not $NoBrowser) {
    # 서버가 포트를 열면 브라우저를 연다(최대 30초 기다림).
    Start-Job -ArgumentList $Port, $urls -ScriptBlock {
        param($Port, $urls)
        for ($i = 0; $i -lt 60; $i++) {
            if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
                foreach ($u in $urls) { Start-Process $u; Start-Sleep -Milliseconds 800 }
                return
            }
            Start-Sleep -Milliseconds 500
        }
    } | Out-Null
}

Set-Location $root
& $py $server --port $Port
