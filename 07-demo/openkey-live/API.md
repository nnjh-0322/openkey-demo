# OpenKey Live API (A 구현본)

작성: 2026-11-12 / A(안내 실행부). 기준: [SCHEMA.md](SCHEMA.md) 5절(PM). 이 문서는 **실제 구현한 것**과 **SCHEMA에 더한 것**을 적는다.
상태: PC 합성 시험으로만 확인(실제 휴대폰·실제 사용자 미시험).

- 서버: `server.py`, 기본 `https://<노트북>:8460`(자체 서명). 포트는 8460~8469만 쓴다.
- 모든 JSON은 UTF-8. 시간 `t`·`server_time`은 ISO 8601(밀리초, 시간대). `ms`는 시도 시작부터 지난 밀리초.
- 좌표는 키오스크 화면 정규 좌표(왼쪽 위 0,0 / 오른쪽 아래 1,1), 영역은 `[left, top, right, bottom]`.
- 버튼 위치는 **시연용 정답 좌표**(`button_source="kiosk_ground_truth"`). 화면에 그렇게 표시한다.
- 안내 판단은 서버(`engine/`)에서 한다. 관리자 콘솔은 보기·조작 전용이며 닫아도 안내는 계속된다.

## 1. 페이지·정적 경로

| 경로 | 내용 |
| --- | --- |
| `/kiosk-host` | 노트북: MORU 키오스크 + ArUco 마커 4개 + 손끝 인식(MediaPipe 워커) + 키오스크 상태·터치 보고 + 노트북 예비 음성 |
| `/phone` | 휴대폰(사용자 기기): 후면 카메라 전송, 안내 음성, 큰 버튼 3개, 음성 명령 |
| `/admin/` `/analytics/` `/training/` `/store/` | 각 폴더가 있으면 정적 제공(없으면 404 JSON). `/admin` → `/admin/` 302 |
| `/runs/<파일>` | 기록 폴더 읽기 전용. `/runs/` 자체는 시도 목록 JSON |
| `/kiosk/…` | `04-practice-kiosk/` 읽기 전용(키오스크 파일 수정 없음) |
| `/sw/…` | `03-software/` 읽기 전용(MediaPipe vendor) |
| `/static/…` | `07-demo/openkey-live/static/`(손 인식 워커 등) |

## 2. SCHEMA 5절 엔드포인트

### `GET /api/live`
현재 상태 한 장. 콘솔이 초당 5~10회 조회해도 된다. SCHEMA 예시의 필드는 모두 같은 이름으로 있다. **추가 필드**는 `★`.

```json
{
  "server_time": "2026-11-12T23:10:05.120+09:00",
  "attempt": {"id": "20261112-231000-a1b2", "started": "…", "ms": 5120, "data_source": "synthetic",
              "conditions": {"layout": "B", "guidance": "on", "blindfold": "unknown", "lighting_note": "", "participant_code": "", "operator_note": ""}},
  "button_source": "kiosk_ground_truth",
  "button_source_label": "시연용 정답 좌표(모의 키오스크가 알려 준 버튼 위치)",   // ★ 화면 표시용 문구
  "goal": {"id": "iced-americano-1", "label": "아이스 아메리카노 한 잔"},
  "steps": [{"step": 1, "name": "menu", "label": "메뉴 고르기", "status": "done"}, {"step": 2, "name": "option", "label": "옵션", "status": "active"}, "…"],
  "kiosk": {"connected": true, "screen": "menu+option", "screen_version": 7, "layout": "B",
            "regions": [{"id": "opt-temp-ICE", "label": "ICE", "bbox": [0.52, 0.30, 0.72, 0.36], "hit": true, "enabled": true}]},
  "target": {"id": "opt-temp-ICE", "label": "ICE", "bbox": [0.52, 0.30, 0.72, 0.36], "screen_version": 7,
             "kind": "forward", "step": 2},                                     // ★ kind: forward|revert|fix
  "finger": {"tracked": true, "x": 0.52, "y": 0.47, "over": null, "age_ms": 80, "count": 1},  // ★ count: 키오스크 안 손 수
  "guide": {"code": "RIGHT_SMALL", "text": "오른쪽으로 조금", "ms": 4980, "direction": [1, 0], "n": 31},  // ★ n: 말하기 큐 번호
  "safety": {"press_allowed": false, "reason": "not_on_target"},
  "status": {"camera": true, "markers": 4, "aligned": true, "align_age_s": 0.1, "hand_rate": 0.92, "model_ms": 24, "frame_age_ms": 90,
             "fps": 12, "cam_w": 1280, "cam_h": 720,
             "input": "camera", "zoom": true, "input_w": 640, "input_h": 520},   // ★ input: camera|synthetic, 손 인식 입력 크기·확대 여부
  "last_press": {"hit_id": "item-americano", "result": "correct", "ms": 2100, "source": "direct"},  // ★ source
  "counts": {"presses": 1, "wrong_presses": 0, "reverts": 0, "hesitations": 0, "hand_lost": 0, "hand_down_requests": 0, "guides": 6},
  "paused": false,                         // ★ 사용자가 '멈춤'을 눌렀는지
  "auto_click": false,                     // ★ 시연 보조 자동 누름(켜져 있으면 화면에 분명히 표시할 것)
  "hand_down": null,                       // ★ {"kind":"payment"|"unreadable","phase":"start"|"waiting_down"|"read"|"wait"} 손 내림 확인 중
  "phone": {"connected": true, "audio_unlocked": true, "last_poll_age_s": 0.4},  // ★ 휴대폰 연결·소리 풀림
  "speech_n": 31,                          // ★ 말하기 큐 마지막 번호
  "last_attempt": {"id": "…", "completed": true, "end_reason": "done", "order_no": 27, "total_ms": 54850, "path": "…"},  // ★ 직전 시도 요약
  "settings": {"dwell_ms": 650, "inset": 0.08, "stale_s": 0.6, "…": "…"},          // ★ 엔진 설정값(예비값)
  "server": {"frames": 812, "cam": {"w": 1280, "h": 720, "fps": 14.8, "ua": "…", "last": "…"}, "markers_layout": true,
             "laptop_voice": "auto", "hand_cfg": {"zoom": true, "det": 0.35, "rescan": true, "max_side": 0},
             "lan": ["https://192.168.0.12:8460/phone"], "allow_synthetic": false}   // ★ 운영 정보
}
```

- 시도가 없으면 `attempt`·`counts`는 `null`, `steps`는 모두 `todo`. 키오스크가 연결 전이면 `kiosk`는 `null`.
- `safety.reason` 값: `ok`, `no_attempt`, `paused`, `no_target`, `hand_down_check`(결제·금액 화면 손 내림 확인 중), `screen_unreadable`, `kiosk_lost`, `no_hand`, `hand_lost`, `not_aligned`, `screen_changed`, `multiple_hands`, `not_on_target`, `dwell`(아직 머묾 시간 안 참).
- `steps[].status`: `done` / `active` / `todo`. 주문 완료 화면이면 모두 `done`.

### `GET /api/events?after=<seq>`
현재 시도의 기록 중 `seq > after`(최대 1.5초 기다림). `{"attempt": "…"|null, "events": [기록…], "last_seq": n}`. 기록 형식은 SCHEMA 3·4절 그대로.

### `GET /api/frame/latest?after=<n>`
최신 카메라 프레임 JPEG(없으면 1.5초 기다린 뒤 204). `X-Info` 머리글(URL 인코딩 JSON):
`{seq, w, h, markers:[{id, corners}], recv, warn, H(카메라 px→키오스크 정규 3×3 또는 null), aligned, age_ms, H_age_s, H_markers, cam}`. 저장하지 않는다.

### `GET /api/goals`
```json
{"goals": [{"id": "iced-americano-1", "label": "아이스 아메리카노 한 잔", "default": true},
           {"id": "hot-latte-1", "label": "따뜻한 카페라떼 한 잔", "default": false},
           {"id": "coldbrew-1", "label": "콜드브루 한 잔(포장)", "default": false}], "current": "iced-americano-1"}
```

### `POST /api/attempt/start`
요청 `{"conditions": {...SCHEMA 조건...}, "goal_id": "iced-americano-1", "data_source": "rehearsal", "reset_kiosk": true}` → `{"attempt": "20261112-231000-a1b2"}`
- `data_source`: `synthetic|rehearsal|field`(그 밖은 400). 빠지면 서버 기본값(`--data-source`, 기본 `rehearsal`).
- ★ `reset_kiosk`(기본 true): 키오스크를 `conditions.layout` 배치의 **첫 화면(매장/포장)** 으로 되돌린다(kiosk-host가 `OPENKEY_KIOSK.setState` 실행). 이때 `screen.cause="operator"`.
- 진행 중 시도가 있으면 그 시도를 `aborted`로 끝내고 새로 시작한다.

### `POST /api/attempt/end`
`{"reason": "aborted"}`(`done|aborted|timeout|error`) → `{"ended": {id, completed, end_reason, order_no, total_ms, path}}`. 주문 번호 화면에 도달하면 서버가 스스로 `done`으로 끝낸다.

### `POST /api/goal`
`{"goal_id": "hot-latte-1"}` → `{"goal": "hot-latte-1"}`. 시도 중이면 `operator` 기록 + 다시 계획.

### `POST /api/control`
`{"action": "repeat"|"stop"|"resume"|"auto_click_on"|"auto_click_off"}` → `{"ok": true, "paused": false, "auto_click": true}`. ★ `auto_click_on/off`를 더했다.

### `GET /api/attempts`, `GET /api/attempts/<id>.jsonl`, `.csv`
목록: `{"attempts": [{id, folder:"runs"|"examples", records, started, data_source, layout, guidance, goal, completed, end_reason, total_ms, url_jsonl, url_csv}]}`(최근 순, `runs/`와 `runs/examples/` 모두).
CSV는 UTF-8 BOM, 열은 공통 필드 + 등장한 모든 필드, 객체·배열은 JSON 문자열.

## 3. 추가 엔드포인트(★ SCHEMA에 없던 것)

| 메서드·경로 | 누가 | 내용 |
| --- | --- | --- |
| `GET /api/say?after=<n>&ch=phone\|laptop\|test&wait=1.0` | phone / kiosk-host / 시험 | **말하기 큐**(최대 `wait`초 기다림). `ch=phone` 조회가 3초 안에 있으면 "휴대폰 연결됨"으로 본다 |
| `POST /api/frame` | phone | 카메라 JPEG 본문, `X-Meta` 머리글 `{fps, ua, source}` → `{seq, markers, known_markers, aligned, warn}` |
| `POST /api/kiosk` | kiosk-host | `{state, touches, screen_events, markers, stage, autoDefault}` 키오스크 화면 지도·실제 터치·화면 전환 이유 |
| `POST /api/hand` | kiosk-host | 손끝 인식 결과 `{seq, hands:[{tip:[px,py], score}], model_ms, input_w, input_h, zoom, det_threshold, fps, rescan}`(카메라 px; 서버가 그 프레임의 H로 키오스크 좌표로 바꾼다) |
| `POST /api/hand` (source=synthetic) | 자동 시험 | `{source:"synthetic", tracked, x, y, aligned, count}` 키오스크 좌표 직접 주입. **`--allow-synthetic`으로 켠 서버만** 받는다(아니면 403) |
| `GET /api/cmd?after=<n>` | kiosk-host | 키오스크 명령 `{cmds:[{n, type:"click", x, y, target_id}|{n, type:"reset", layout, screen}], hand_cfg, auto_click, laptop_voice}` |
| `POST /api/voice` | phone | `{command:"start"\|"repeat"\|"stop"\|"goal", via:"speech"\|"button", goal_id}`. **인식된 문장 원문은 보내지 않는다** |
| `POST /api/phone` | phone | `{audio_unlocked, audio_out, speech_supported, recognition_supported, wake_lock}` 상태 보고 |
| `POST /api/settings` | 콘솔 | `{laptop_voice:"auto"\|"on"\|"off", auto_click:bool, hand:{zoom, det, rescan, max_side}}` |
| `GET /api/marker/<0-3>.png` | kiosk-host | ArUco DICT_4X4_50 마커(검은 200px + 흰 여백 40px) |
| `GET /api/health` | 누구나 | `{ok, uptime_s}` |
| `GET /api/hand/recent?after_seq=<n>` | 진단·손 인식 시험 | 최근 손 인식 결과 400개 `{items:[{seq, tracked, x, y, hands, model_ms, input_w, input_h, zoom, rescan, det, frame_age_ms}]}`(좌표·시간만) |

### `GET /api/say` 응답
```json
{"items": [{"n": 12, "code": "PRESS", "text": "누르세요.", "prio": 3, "interrupt": true, "age_ms": 40, "ttl_ms": 2500}],
 "n": 12, "speak": true, "paused": false, "attempt": "20261112-231000-a1b2"}
```
- 받는 쪽 규칙: `code="CANCEL"`이면 지금 말을 끊는다(손을 놓쳤을 때 낡은 "누르세요"를 끊음, guide 기록 없음). `interrupt=true`면 끊고 말한다. `age_ms > ttl_ms`인 말은 버린다(낡은 방향).
- `speak`: `ch=laptop`일 때 노트북이 실제로 소리를 낼지(`laptop_voice=auto`면 휴대폰이 연결 안 됐을 때만 true).
- 우선순위 `prio`: 0 손 놓침·잘못 누름 / 1 누름 결과·손 내림 요청 / 2 화면·금액·완료·기타 / 3 멈추세요·누르세요 / 4 방향.

## 4. 기록(SCHEMA 4절)과 다르게·더한 점

- 필드 이름·종류는 SCHEMA 그대로. **추가 필드 없음**(기록 쪽). 아래는 값의 해석이다.
- `attempt_start.settings`에 SCHEMA 4개(`dwell_ms, zoom, det_threshold, sample_hz`) 외에 `auto_click, inset, stale_ms, hesitation_min_ms`를 더 넣는다(★).
- 단계(`step`)는 5개: 1 menu(매장/포장 선택 포함) → 2 option → 3 confirm(메뉴 화면의 결제하기 + 주문 확인 창) → 4 pay → 5 done.
- `target.reason`: 정상 진행은 `plan`, 잘못 누름 뒤·되돌리기·수정 버튼(`kind=revert|fix`)·같은 버튼 재지정은 `replan`, 목표 없음(완료 화면 등)은 `cleared`(`target_id=null`).
- 같은 방향 안내는 손이 계속 같은 쪽에 있으면 **3초 간격으로 한 번 다시** 말한다(계속 움직이는 사용자를 위한 되새김. 그 사이 같은 말은 억제). "멈추세요"는 목표에 들어올 때 한 번, "누르세요"는 4초 간격 이상. 이 간격이 "연달아 반복"으로 들리는지는 실제 사용자 시험에서 확인 필요.
- `guide.suppressed=true`는 같은 말을 1초 이상 지나 다시 내려다 억제된 경우만, 코드별 5초에 한 번 남긴다(같은 계산 주기의 중복은 남기지 않음). `counts.guides`는 실제로 낸 말만 센다.
- `hand_lost`/`hand_found`: 손 내림을 요청해서 사라진 손은 **손 놓침으로 세지 않는다**(`hand_down_done`으로 남긴다). 원인은 화면 밖이면 `out_of_frame`, 그 밖은 `unknown`(가려짐인지 구별하지 못한다 → `occluded`는 지금 쓰지 않음).
- `hand_down_request.reason`: 결제·금액 화면(주문 확인 창, 결제 수단 화면)은 손이 보이면 `payment_check`. 손이 이미 내려가 있으면 요청 없이 바로 금액을 읽는다. `new_screen_unreadable`은 **새 화면에서 위치 맞춤(마커)이 낡았을 때** 약 1초 기다린 뒤 낸다. 같은 화면에서 마커가 가려지는 것은 요청하지 않고 목표 영역을 유지한다.
  - 지금은 버튼 위치가 키오스크 정답 좌표라서 "화면 글자를 못 읽음"은 실제로 생기지 않는다. 이 정책은 마커가 가려져 위치 맞춤이 낡았을 때와 앞으로의 OCR 모드를 대비한 것이다.
- `press.source`: kiosk-host가 자동 누름 명령으로 누른 터치는 `auto_click`, 그 밖(실제 포인터·터치)은 `direct`.
- `screen.cause`: 직전에 터치가 있었으면 `press`, 시도 시작·콘솔 조작 3초 안이면 `operator`, 키오스크 자체 타이머(`idle/timeout/done-auto/paid`)면 `timer`, 그 밖 `unknown`.
- `perf`: kiosk-host 손 인식 결과가 3초 안에 있을 때만 약 2초마다. `hand_rate`는 최근 60번 보고 중 손을 찾은 비율.
- `marker`: 위치 맞춤 유효 여부가 바뀌면 바로, 마커 수만 바뀌면 1초에 한 번까지.

## 5. 안전 규칙(엔진에서 강제, 기록으로 검사)

`PRESS`(누르세요)는 다음을 모두 만족할 때만 낸다: 시도 중·멈춤 아님 / 손 내림 확인 절차 끝남 / 키오스크 보고가 3초 안 / 손끝 관측이 0.6초 안이고 손 놓침 상태 아님 / 그 관측의 위치 맞춤 유효 + 서버 위치 맞춤 2초 안 / 목표 `screen_version` = 지금 화면 / 키오스크 안 손 1개 / 목표 안에 650ms 머묾.
검사 함수: `engine/checks.py`의 `press_safety_violations(records)`(기록만 보고 손 놓침 중·위치 맞춤 무효 중·현재 목표 아님 PRESS를 찾는다), `schema_errors(records)`.

## 6. PM 승인 필요·요청

- 이름 변경·삭제 요청 없음. 위 ★ 추가분을 SCHEMA에 반영할지 PM 판단.
- `hand_lost.cause="occluded"`는 지금 구별할 수 없어 쓰지 않는다(값은 SCHEMA에 그대로 둠).
