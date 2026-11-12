# OpenKey Live 실행 방법

작성: 2026-11-12 / A(안내 실행부). PC 합성 시험까지만 확인했다. **실제 휴대폰·실제 사용자는 미시험**(아침에 [PHONE-TEST.md](PHONE-TEST.md) 순서로).

## 무엇이 어디서 도는가

| 기기 | 주소 | 하는 일 |
| --- | --- | --- |
| 노트북 화면(키오스크) | `https://localhost:8460/kiosk-host` | MORU 모의 키오스크 + 검은 마커 4개. 손끝 인식(MediaPipe)도 이 탭에서 돈다. **이 탭은 닫지 않는다** |
| 휴대폰(사용자 기기) | `https://<노트북 IP>:8460/phone` | 후면 카메라 전송, 안내 음성(폰 스피커·이어폰), 큰 버튼 3개(시작/다시 듣기/멈춤), 음성 명령 |
| 노트북 다른 창(운영자) | `https://localhost:8460/admin/` | 관리자 콘솔(B 담당). 닫아도 안내는 계속된다 |
| 서버 | `server.py` | 프레임 중계·마커 위치 맞춤·**안내 판단(engine/)**·기록(`runs/*.jsonl`) |

누르는 것은 사용자 본인이다. 노트북이 터치스크린이 아니면 시연을 위해 "자동 누름(시연 보조)"이 켜진다(아래).

## 1. 서버 켜기

프로젝트 루트(PowerShell)에서:

```powershell
.\.venv\Scripts\python.exe 07-demo\openkey-live\server.py
```

시작하면 노트북·휴대폰 주소가 찍힌다(`[live] 휴대폰: https://192.168.x.x:8460/phone`).

| 옵션 | 기본 | 뜻 |
| --- | --- | --- |
| `--port` | 8460 | 8460~8469만 쓴다. 8443·8444는 사용자 기존 서버 |
| `--auto-click auto\|on\|off` | auto | 자동 누름(시연 보조). auto = 키오스크 탭이 터치스크린이 아니면 켬 |
| `--data-source rehearsal\|field\|synthetic` | rehearsal | 휴대폰 '시작'으로 연 시도의 기록 구분. 실제 사용자 시험이면 `field` |
| `--runs-dir` | `07-demo/openkey-live/runs` | 기록 폴더 |
| `--cert` | `work/live-capture-cert` | `cert.pem`, `key.pem`(읽기만, 저장소로 복사 금지) |
| `--allow-synthetic` | 꺼짐 | 자동 시험용 합성 손끝 입력 허용. **시연·실험 때는 켜지 않는다** |

코드를 바꾸면 **서버를 껐다 다시 켠다**(Ctrl+C). 페이지 새로고침만으로는 서버 쪽이 바뀌지 않는다.

## 2. 노트북

1. Edge/Chrome으로 `https://localhost:8460/kiosk-host`를 연다. 인증서 경고 → "고급 → 계속".
2. F11 전체 화면. 키오스크 양옆에 검은 사각형(마커) 4개, 왼쪽에 작은 상태 칸(연결·손 인식·자동 누름)이 보인다.
   - 배치: `?layout=A` 또는 `B`(기본 B). 시도를 시작하면 서버가 키오스크를 그 시도의 배치 첫 화면(매장/포장)으로 되돌린다.
   - 키오스크는 `fixed=1`(타이머 멈춤, 주문 번호 27 고정)로 띄운다. 안내를 따라 천천히 주문하는 동안 "시간 초과" 창이 뜨지 않게 하려는 것이다. `fixed=1`에서는 카드 투입 화면이 자동 승인되지 않으므로 **결제 목표는 간편결제(모의)** 다. 실제처럼 타이머를 켜려면 `?timers=1`(이때 카드 결제 4초 자동 승인, 완료 10초 뒤 첫 화면).
3. 휴대폰이 없을 때만 노트북 스피커로 안내를 들으려면 상태 칸의 **"노트북 예비 음성"** 을 한 번 누른다(브라우저는 클릭 전에는 소리를 막는다). 기본은 휴대폰이 연결돼 있으면 노트북은 말하지 않는다(`laptop_voice=auto`).
4. 관리자 콘솔은 다른 창으로 `https://localhost:8460/admin/`.

## 3. 휴대폰

1. 노트북과 **같은 Wi-Fi**. 노트북 IP는 서버 시작 줄 또는 PowerShell `ipconfig`의 Wi-Fi IPv4.
2. 휴대폰 브라우저(안드로이드 Chrome 권장)로 `https://<노트북 IP>:8460/phone`. 인증서 경고 → "고급 → 계속(안전하지 않음)". 카메라는 https에서만 켜진다.
3. **화면을 한 번 누른다.** 휴대폰은 첫 터치가 있어야 소리가 난다. 이때 소리·카메라·화면 꺼짐 방지가 켜지고 "오픈키 준비됐어요…"가 들린다. 카메라 권한을 허용한다.
4. 휴대폰을 거치대에 고정하고, 키오스크와 마커 4개가 모두 화면에 들어오게 맞춘다. 상단 작은 글씨에 `마커 4/4`가 보이면 된다.
5. 큰 버튼: 위 **시작**(주문 안내 시작·멈춘 뒤 이어 가기) / 가운데 **다시 듣기** / 아래 **멈춤**. 진동·효과음으로 연결·시작·멈춤·"누르세요" 등을 알린다.
6. **말로 명령**(오른쪽 위): "시작", "다시", "멈춰", "라떼"/"콜드브루"/"아메리카노"(목표 바꾸기). 문장 원문은 서버에 보내지 않는다. 지원하지 않는 브라우저면 버튼이 "음성 명령 없음"으로 바뀐다.
7. 이어폰을 쓰면 휴대폰 주소 뒤에 `?out=earphone`을 붙이면 기록 `device.audio_out`에 남는다(선택).

## 4. 시도 시작·끝

- 휴대폰 **시작** 버튼 → 시도가 열리고(`runs/<시도 ID>.jsonl`) 키오스크가 첫 화면으로 돌아간 뒤 안내가 시작된다. 목표 기본값은 "아이스 아메리카노 한 잔".
- 관리자 콘솔에서 조건(배치·안내 유무·안대·메모)과 목표를 정해 시작할 수도 있다(`POST /api/attempt/start`).
- 주문 번호 화면에 도착하면 "주문이 끝났어요. 주문 번호는 27번입니다."를 말하고 시도가 자동으로 끝난다(`attempt_end.completed=true`).

## 5. 자동 누름(시연 보조)

- 노트북 화면이 터치스크린이 아니면 사용자가 실제로 누를 수 없으므로, "누르세요" 뒤 0.5초 더 버튼 위에 머물면 키오스크가 그 손끝 위치를 대신 누른다.
- 켜져 있으면 키오스크 탭 왼쪽에 주황 칸 **"자동 누름 켬 — 시연 보조"** 가 뜨고, 기록에 `press.source="auto_click"`으로 남는다. 시연에서는 "원래는 사용자가 직접 누른다"고 설명한다.
- 끄기/켜기: 서버 `--auto-click off|on`, 또는 `POST /api/control {"action":"auto_click_off"}`, 또는 관리자 콘솔.

## 6. 방화벽·인증서

- Windows 방화벽이 Python 허용을 물으면 **개인 네트워크만** 허용한다. 공용 Wi-Fi(학교·행사장)에서는 휴대폰이 노트북에 못 붙을 수 있다 → 휴대폰 핫스팟에 노트북을 붙이는 방법이 가장 확실하다.
- 인증서는 자체 서명이다. 노트북·휴대폰 모두 처음에 경고가 뜬다. 인증서 파일은 `work/live-capture-cert/`에만 있고 저장소에 넣지 않는다.

## 7. 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| 휴대폰에서 페이지가 안 열림 | 같은 Wi-Fi인가, IP가 맞나, 방화벽 '개인' 허용, 포트 8460. 학교 Wi-Fi는 기기 간 통신을 막기도 함 → 핫스팟 |
| 휴대폰 카메라 오류 | 주소가 `https://`인가, 카메라 권한, 다른 앱이 카메라를 쓰는 중인가 |
| 소리가 안 남 | 휴대폰 화면을 한 번 눌렀나(첫 터치), 무음/진동 모드, 볼륨, 이어폰 연결. 한국어 음성이 없는 기기는 영어 음성으로 읽을 수 있음 |
| `마커 0/4` 또는 2개 미만 | 키오스크 탭이 F11 전체 화면인가, 휴대폰이 너무 멀거나 비스듬한가, 화면 반사, 노트북 밝기 |
| 마커는 4/4인데 손을 못 찾음 | 키오스크 탭 상태 칸의 "인식률"·입력 크기 확인. 손등·손가락이 보이게, 휴대폰을 더 가까이. `/api/settings {"hand":{"det":0.3}}`로 기준값 낮추기 |
| 안내가 "누르세요"를 안 함 | `/api/live`의 `safety.reason`: `hand_lost`(손 놓침), `not_aligned`(마커), `hand_down_check`(결제 화면에서 손을 내려야 함), `dwell`(버튼 안에 0.65초 머물러야 함) |
| 키오스크가 안 넘어감 | 자동 누름이 꺼져 있고 노트북이 터치스크린이 아님 → 자동 누름 켬 |
| 화면이 옛날 그대로 | 서버를 껐다 켜고 탭을 새로고침 |

## 8. 시험 다시 돌리기

```powershell
# 엔진 단위 시험 + 통합 시험(실제 서버·headless Edge·진짜 키오스크·합성 손끝, 약 7분)
.\.venv\Scripts\python.exe -m pytest 07-demo\openkey-live\tests -q
# 통합 시험 결과 문서·예시 기록 갱신(tests/INTEGRATION-RESULT.md, runs/examples/)
.\.venv\Scripts\python.exe 07-demo\openkey-live\tests\integration.py --write-examples
# 합성 카메라 프레임 경로 1건(손 사진 합성 → 마커·MediaPipe → 안내 → 자동 누름 → 화면 전환). 손 사진 필요(아래)
.\.venv\Scripts\python.exe 07-demo\openkey-live\tests\frame_path.py
# 손 인식 비교(tests/hand-eval/REPORT.md 갱신, 약 8분), 선택 과제 OCR 비교(tests/ocr-eval/REPORT.md)
.\.venv\Scripts\python.exe 07-demo\openkey-live\tests\hand-eval\eval_hands.py
.\.venv\Scripts\python.exe 07-demo\openkey-live\tests\ocr-eval\ocr_buttons.py
```

- 손 사진 합성 시험은 `work/openkey-live/hands/`에 사진이 있어야 한다(저장소 밖, 출처는 `tests/hand-eval/SOURCES.md`). 없으면 SOURCES.md의 Commons 파일 페이지에서 900px 미리보기를 같은 파일 이름(공백·특수문자 → `_`)으로 받는다.
- 엔진 단위 시험만: `$env:OPENKEY_SKIP_INTEGRATION='1'; .\.venv\Scripts\python.exe -m pytest 07-demo\openkey-live\tests -q`

- 통합 시험은 포트 8462에 서버를 따로 띄웠다가 끈다. 사용 중인 서버(8460)와 겹치지 않는다.
- Playwright 드라이버(Node)가 한글·공백 경로에서 바로 죽는 문제가 있어 시험 코드가 드라이버를 `%TEMP%\openkey-pwdriver-1.49.1`로 복사해 쓴다(`tests/pw_driver.py`). 저장소에는 쓰지 않는다.

## 9. 기록·개인정보

- 영상·사진·음성은 저장하지 않는다. 서버는 최신 프레임 1장만 메모리에 둔다.
- 기록은 `runs/<시도 ID>.jsonl`(SCHEMA.md v1): 좌표·시간·화면 상태·안내 문구. 참가자는 `P01` 같은 코드만.
- 자동 시험 기록 예시는 `runs/examples/`(`data_source="synthetic"`). 연습·실제 기록을 저장소에 올릴지는 팀 결정.
