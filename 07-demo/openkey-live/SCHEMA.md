# OpenKey Live 기록 형식과 API 계약 (v1)

작성: 2026-11-12 / claude-20261112-01 (PM). 상태: **AI 제안 초안**. 실제 휴대폰·실제 사용자 기록으로 검증한 형식이 아니다.
소유: PM. 바꿔야 하면 PM에게 요청한다(A·B·C·D는 이 파일을 읽기만 한다).

이 기록의 목적은 **안내가 사용자를 끝까지 데려갔는지 확인하고, 막힌 곳을 고치는 것**이다. 사람을 식별하거나 지켜보기 위한 기록이 아니다.

## 1. 원칙

1. **영상·사진·음성 원본을 저장하지 않는다.** 서버는 최신 카메라 프레임 1장만 메모리에 두고 디스크에 쓰지 않는다. 기록은 좌표·시간·화면 상태·안내 문구뿐이다.
2. 사람 이름·연락처를 넣지 않는다. 참가자는 `P01` 같은 임의 코드로만 적는다.
3. 좌표는 **키오스크 화면 정규 좌표**다. 화면 왼쪽 위가 `(0,0)`, 오른쪽 아래가 `(1,1)`. 손끝이 화면 밖이면 범위를 벗어난 값이 그대로 남는다. 영역은 `[left, top, right, bottom]`.
4. 모든 기록에 `data_source`가 따라간다(시도 시작 기록에 한 번 적는다): `synthetic`(합성 입력 자동 시험) / `rehearsal`(팀원 연습) / `field`(실제 사용자). 분석 화면은 이 값을 반드시 표시한다.
5. 버튼 위치의 출처를 적는다: `button_source = kiosk_ground_truth`(모의 키오스크가 알려 준 시연용 정답 좌표) 또는 `ocr`.
6. 3~5단계(분석·교육·매장) 중 어디에 중점을 두든 같은 기록을 쓴다. 쓸지 모르는 항목은 넉넉히 남기되, 측정하지 못한 값은 `null`로 둔다(추정해서 채우지 않는다).

## 2. 파일

- 위치: `07-demo/openkey-live/runs/<attempt_id>.jsonl` (UTF-8, 한 줄에 기록 하나).
- `attempt_id`: `YYYYMMDD-HHMMSS-xxxx`(xxxx는 임의 4자리).
- 첫 줄은 `attempt_start`, 마지막 줄은 `attempt_end`. 서버가 중간에 꺼지면 `attempt_end`가 없을 수 있다(분석은 "미완료·종료 기록 없음"으로 처리).
- 시도 밖(대기 중)에서 생긴 기록은 파일에 쓰지 않는다.
- 자동 시험이 만든 예시 기록은 `runs/examples/`에 둔다(저장소에 포함 가능). 연습·실제 기록(`rehearsal`, `field`)을 저장소에 올릴지는 팀 결정이다.

## 3. 공통 필드

| 필드 | 형식 | 뜻 |
| --- | --- | --- |
| `v` | 1 | 형식 버전 |
| `attempt` | 문자열 | 시도 ID |
| `seq` | 정수 | 시도 안에서 1부터 증가 |
| `t` | ISO 8601(밀리초, 시간대 포함) | 서버 시각 |
| `ms` | 정수 | 시도 시작부터 지난 시간 |
| `kind` | 문자열 | 아래 종류 |

## 4. 기록 종류

| `kind` | 추가 필드 | 남기는 때 |
| --- | --- | --- |
| `attempt_start` | `data_source`, `button_source`, `conditions{layout:"A"\|"B", guidance:"on"\|"off", blindfold:"yes"\|"no"\|"unknown", lighting_note, participant_code, operator_note}`, `goal{id, label, steps[{step, screen, target_label, required}]}`, `device{cam_w, cam_h, phone_ua_short, audio_out:"phone"\|"earphone"\|"laptop"\|"unknown"}`, `settings{dwell_ms, zoom, det_threshold, sample_hz}` | 시도 시작 |
| `screen` | `screen`, `screen_version`, `from`, `cause:"press"\|"timer"\|"operator"\|"unknown"` | 키오스크 화면이 바뀜 |
| `target` | `step`, `screen`, `screen_version`, `target_id`, `label`, `bbox`, `reason:"plan"\|"replan"\|"cleared"` | 목표 버튼을 정하거나 버림 |
| `finger` | `x`, `y`, `tracked`, `over`(손끝 아래 버튼 ID 또는 null), `dist`(목표 중심까지 거리, 목표 없으면 null) | 손끝 표본. 기본 10Hz 이하, 손을 못 찾은 동안은 남기지 않음 |
| `guide` | `code`, `text`, `target_id`, `channel:"phone"\|"laptop"`, `suppressed`(같은 말 반복 억제로 말하지 않았으면 true) | 안내 문구를 냄 |
| `hesitation` | `region_id`, `on_target`, `dwell_ms`, `ended_by:"moved_away"\|"hand_lost"\|"screen_change"` | 버튼 위에 `hesitation_min_ms`(기본 700) 이상 머물다 누르지 않고 떠남 |
| `press` | `x`, `y`, `hit_id`, `target_id`, `result:"correct"\|"wrong"\|"no_button"\|"no_target"`, `source:"direct"\|"auto_click"`, `screen`, `next_screen` | 키오스크 실제 입력(터치 기록) 확인 |
| `revert` | `from_screen`, `to_screen`, `reason:"wrong_press"\|"user"\|"operator"` | 잘못 눌러 이전 화면으로 돌아감 |
| `hand_lost` | `cause:"occluded"\|"out_of_frame"\|"unknown"` | 손을 놓침 |
| `hand_found` | `lost_ms` | 손을 다시 찾음 |
| `hand_down_request` | `reason:"new_screen_unreadable"\|"payment_check"`, `waited_ms` | 손을 내려 달라고 요청(정책은 지시문 2절) |
| `hand_down_done` | `took_ms` | 손이 내려간 것을 확인 |
| `marker` | `count`, `aligned`, `align_age_s` | 마커 수·위치 맞춤 상태가 바뀜 |
| `perf` | `hand_rate`(최근 60장 중 손 검출 비율), `model_ms`, `input_w`, `input_h`, `zoom`, `det_threshold`, `frame_age_ms`, `fps` | 약 2초마다. 인식 문제를 영상 없이 진단하는 용도 |
| `voice_cmd` | `command:"start"\|"repeat"\|"stop"\|"goal"`, `goal_id`, `via:"speech"\|"button"` | 사용자의 짧은 명령. 인식된 문장 원문·음성은 저장하지 않음 |
| `operator` | `action`, `detail` | 콘솔 조작(목표 변경, 조건 수정, 강제 종료 등) |
| `step_done` | `step`, `name:"menu"\|"option"\|"confirm"\|"pay"\|"done"`, `duration_ms`, `presses`, `wrong_presses`, `hesitations`, `guides` | 한 단계가 끝남 |
| `attempt_end` | `completed`, `end_reason:"done"\|"aborted"\|"timeout"\|"error"`, `order_no`, `total_ms`, `counts{presses, wrong_presses, reverts, hesitations, hand_lost, hand_down_requests, guides}` | 시도 종료 |

### 안내 코드(`guide.code`)

`LEFT` `RIGHT` `UP` `DOWN`(각각 `_SMALL` 붙으면 "조금") · `HOLD`(멈추세요) · `PRESS`(누르세요) · `PRESS_OK`(맞게 눌렀어요) · `PRESS_WRONG`(다른 버튼이 눌렸어요, 이전으로 돌아갈게요) · `HAND_LOST`(손이 보이지 않아요) · `HAND_DOWN`(손을 잠시 내려 주세요) · `SCREEN`(새 화면 안내, 예: "옵션 화면입니다") · `PAY_CHECK`(금액 확인) · `DONE`(주문 번호 안내) · `INFO`(그 밖). 문구는 A가 정하되 코드와 함께 남긴다.

**안전 규칙(기록으로 검증 가능해야 함)**: `PRESS`는 손을 추적 중이고(`hand_lost` 상태가 아님), 위치 맞춤이 유효하고, 목표의 `screen_version`이 현재 화면과 같을 때만 낼 수 있다.

## 5. 실시간 API (A가 구현, B가 사용)

기본 포트 8460(HTTPS, 자체 서명). 관리자 콘솔은 **보기·조작 전용**이며, 콘솔을 닫아도 안내는 계속 동작해야 한다.

| 메서드·경로 | 내용 |
| --- | --- |
| `GET /api/live` | 현재 상태 한 장(JSON). 콘솔이 초당 5~10회 조회 |
| `GET /api/events?after=<seq>` | 현재 시도의 기록 중 `seq`가 큰 것(최대 1.5초 대기). 시도가 없으면 빈 목록 |
| `GET /api/frame/latest?after=<n>` | 최신 카메라 프레임 JPEG + `X-Info` 머리글(finger-demo와 같은 방식). 저장하지 않음 |
| `GET /api/goals` | 고를 수 있는 주문 목표 목록 |
| `POST /api/attempt/start` | `{conditions, goal_id, data_source}` → `{attempt}` |
| `POST /api/attempt/end` | `{reason}` |
| `POST /api/goal` | `{goal_id}` (시도 전·중 목표 변경) |
| `POST /api/control` | `{action:"repeat"\|"stop"\|"resume"}` |
| `GET /api/attempts` | 저장된 시도 목록(요약) |
| `GET /api/attempts/<id>.jsonl`, `.csv` | 기록 내보내기 |
| `GET /admin/…` `/analytics/…` `/training/…` `/store/…` | 각 폴더의 정적 파일 |

`GET /api/live` 응답(없는 값은 `null`):

```json
{
  "server_time": "2026-11-12T23:10:05.120+09:00",
  "attempt": {"id": "20261112-231000-a1b2", "started": "…", "ms": 5120, "data_source": "rehearsal",
              "conditions": {"layout": "B", "guidance": "on", "blindfold": "yes", "lighting_note": "", "participant_code": "P01", "operator_note": ""}},
  "button_source": "kiosk_ground_truth",
  "goal": {"id": "iced-americano-1", "label": "아이스 아메리카노 한 잔"},
  "steps": [{"step": 1, "name": "menu", "label": "메뉴 고르기", "status": "done"},
            {"step": 2, "name": "option", "label": "옵션", "status": "active"},
            {"step": 3, "name": "confirm", "label": "확인", "status": "todo"},
            {"step": 4, "name": "pay", "label": "결제", "status": "todo"},
            {"step": 5, "name": "done", "label": "주문 번호", "status": "todo"}],
  "kiosk": {"connected": true, "screen": "option", "screen_version": 7, "layout": "B",
            "regions": [{"id": "temp-ice", "label": "ICE", "bbox": [0.1, 0.4, 0.45, 0.5], "hit": true, "enabled": true}]},
  "target": {"id": "temp-ice", "label": "ICE", "bbox": [0.1, 0.4, 0.45, 0.5], "screen_version": 7},
  "finger": {"tracked": true, "x": 0.52, "y": 0.47, "over": null, "age_ms": 80},
  "guide": {"code": "LEFT_SMALL", "text": "왼쪽으로 조금", "ms": 4980, "direction": [-1, 0]},
  "safety": {"press_allowed": false, "reason": "not_on_target"},
  "status": {"camera": true, "markers": 4, "aligned": true, "align_age_s": 0.1, "hand_rate": 0.92, "model_ms": 24, "frame_age_ms": 90, "fps": 12, "cam_w": 1280, "cam_h": 720},
  "last_press": {"hit_id": "menu-americano", "result": "correct", "ms": 2100},
  "counts": {"presses": 1, "wrong_presses": 0, "reverts": 0, "hesitations": 0, "hand_lost": 0, "hand_down_requests": 0, "guides": 6}
}
```

필드 이름은 이 문서가 기준이다. A가 구현하면서 더 필요한 필드는 **추가**할 수 있지만(추가분은 `API.md`에 적는다) 위 이름을 바꾸거나 빼려면 PM에게 요청한다.

## 6. 지표 정의(C가 사용, 초안)

| 지표 | 계산 |
| --- | --- |
| 단계별 소요 시간 | `step_done.duration_ms` |
| 망설임 횟수·시간 | `hesitation` 수와 `dwell_ms` 합. 목표 위(`on_target`)와 다른 버튼 위를 구분 |
| 잘못 누름·되돌림 | `press.result="wrong"` 수, `revert` 수 |
| 손 경로 길이 | 연속한 `finger` 표본 사이 거리의 합(화면 폭·높이 정규 단위). 목표까지 직선 거리와의 비율도 함께 |
| 머문 곳(히트맵) | `finger` 표본을 화면별 격자로 집계 |
| 완료율 | `attempt_end.completed` 비율. 조건(`layout`, `guidance`, `blindfold`)별로 나눔 |
| 손 놓침·손 내림 요청 | `hand_lost`, `hand_down_request` 수 |

지표는 "누가 얼마나 느린가"가 아니라 **"어느 화면·어느 버튼에서 막히는가"**를 보려는 것이다. 결론은 화면 배치·안내 문구·교육 과제를 고치는 제안으로 끝낸다.
