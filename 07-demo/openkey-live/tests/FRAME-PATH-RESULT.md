# 합성 카메라 프레임 경로 종단 시험 (가상 시험)

실행: 2026-11-12 18:55 / A. 명령: `.venv\Scripts\python.exe 07-demo\openkey-live\tests\frame_path.py Wijsvinger.jpg` (같은 결과 2회).

좌표 주입 없이 실제 카메라 경로만 썼다: 손 사진(`Wijsvinger.jpg`, CC BY-SA 3.0, [hand-eval/SOURCES.md](hand-eval/SOURCES.md))을 kiosk-host 첫 화면 캡처의 '매장' 버튼 위에 합성 → 원근 왜곡 1280×720 프레임 약 8장/초
→ `POST /api/frame`(서버 ArUco 4/4, 호모그래피) → kiosk-host MediaPipe 워커(확대 인식) → `POST /api/hand`(서버가 키오스크 좌표로 변환) → 엔진 → 자동 누름 명령 → MORU 키오스크가 메뉴 화면으로.
실제 휴대폰·실제 손이 아니다(정지한 사진 손, 매 장 잡음·밝기만 바꿈).

| 항목 | 값 |
| --- | --- |
| 결과 | **통과**: `press` 1건 `dine-store / correct / auto_click`, `start → menu` |
| 보낸 프레임 | 49장, 5.9초 |
| 안내 순서 | `INFO` 주문 시작 → `SCREEN` 주문 시작 화면입니다. 매장 버튼을 찾을게요. → `PRESS` 누르세요. → `PRESS_OK` 맞게 눌렀어요. |
| 손끝 표본 | 46개, 정답(버튼 중심)과의 거리 중앙값 0.024 |
| perf | hand_rate 1.0, model_ms 37, 입력 822×720(확대), frame_age_ms 44, fps 8.5 |
| 형식·안전 검사 | schema_errors 0, press_safety_violations 0 |

- `HOLD`(멈추세요)가 없는 것은 손이 처음부터 버튼 위에 있었고 그동안 화면 안내(`SCREEN`)를 말하는 중이라 낮은 우선순위의 '멈추세요'를 버렸기 때문이다(설계대로). 머묾 650ms는 채운 뒤 `PRESS`가 나왔다.
- 한 화면(첫 화면 → 메뉴)만 확인했다. 카메라 경로로 주문 전체를 끝내는 시험은 하지 않았다(화면마다 새 캡처·합성이 필요).
