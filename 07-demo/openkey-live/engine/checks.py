"""기록 검사: SCHEMA.md v1 필드와 안전 규칙을 기록만 보고 확인한다(시험·분석 공용)."""
from __future__ import annotations

COMMON = ("v", "attempt", "seq", "t", "ms", "kind")
REQUIRED = {
    "attempt_start": ("data_source", "button_source", "conditions", "goal", "device", "settings"),
    "screen": ("screen", "screen_version", "from", "cause"),
    "target": ("step", "screen", "screen_version", "target_id", "label", "bbox", "reason"),
    "finger": ("x", "y", "tracked", "over", "dist"),
    "guide": ("code", "text", "target_id", "channel", "suppressed"),
    "hesitation": ("region_id", "on_target", "dwell_ms", "ended_by"),
    "press": ("x", "y", "hit_id", "target_id", "result", "source", "screen", "next_screen"),
    "revert": ("from_screen", "to_screen", "reason"),
    "hand_lost": ("cause",),
    "hand_found": ("lost_ms",),
    "hand_down_request": ("reason", "waited_ms"),
    "hand_down_done": ("took_ms",),
    "marker": ("count", "aligned", "align_age_s"),
    "perf": ("hand_rate", "model_ms", "input_w", "input_h", "zoom", "det_threshold", "frame_age_ms", "fps"),
    "voice_cmd": ("command", "goal_id", "via"),
    "operator": ("action", "detail"),
    "step_done": ("step", "name", "duration_ms", "presses", "wrong_presses", "hesitations", "guides"),
    "attempt_end": ("completed", "end_reason", "order_no", "total_ms", "counts"),
}
ENUMS = {
    ("screen", "cause"): {"press", "timer", "operator", "unknown"},
    ("target", "reason"): {"plan", "replan", "cleared"},
    ("guide", "channel"): {"phone", "laptop"},
    ("hesitation", "ended_by"): {"moved_away", "hand_lost", "screen_change"},
    ("press", "result"): {"correct", "wrong", "no_button", "no_target"},
    ("press", "source"): {"direct", "auto_click"},
    ("revert", "reason"): {"wrong_press", "user", "operator"},
    ("hand_lost", "cause"): {"occluded", "out_of_frame", "unknown"},
    ("hand_down_request", "reason"): {"new_screen_unreadable", "payment_check"},
    ("voice_cmd", "command"): {"start", "repeat", "stop", "goal"},
    ("voice_cmd", "via"): {"speech", "button"},
    ("step_done", "name"): {"menu", "option", "confirm", "pay", "done"},
    ("attempt_end", "end_reason"): {"done", "aborted", "timeout", "error"},
}
GUIDE_CODES = {"LEFT", "RIGHT", "UP", "DOWN", "LEFT_SMALL", "RIGHT_SMALL", "UP_SMALL", "DOWN_SMALL", "HOLD", "PRESS", "PRESS_OK",
               "PRESS_WRONG", "HAND_LOST", "HAND_DOWN", "SCREEN", "PAY_CHECK", "DONE", "INFO"}
FORBIDDEN_KEYS = {"jpeg", "image", "frame", "audio", "transcript", "snapshot", "data_url"}


def schema_errors(records: list) -> list:
    errs = []
    if not records:
        return ["기록 없음"]
    if records[0].get("kind") != "attempt_start":
        errs.append("첫 줄이 attempt_start가 아님")
    seqs = [r.get("seq") for r in records]
    if seqs != list(range(1, len(records) + 1)):
        errs.append("seq가 1부터 연속이 아님")
    for r in records:
        k = r.get("kind")
        for f in COMMON:
            if f not in r:
                errs.append(f"seq {r.get('seq')}: 공통 필드 {f} 없음")
        if k not in REQUIRED:
            errs.append(f"seq {r.get('seq')}: 모르는 kind {k}")
            continue
        for f in REQUIRED[k]:
            if f not in r:
                errs.append(f"seq {r.get('seq')} {k}: 필드 {f} 없음")
        for (kk, f), allowed in ENUMS.items():
            if kk == k and r.get(f) not in allowed:
                errs.append(f"seq {r.get('seq')} {k}.{f}={r.get(f)!r} 허용값 아님")
        if k == "guide" and r.get("code") not in GUIDE_CODES:
            errs.append(f"seq {r.get('seq')} guide.code={r.get('code')} 모르는 코드")
        bad = FORBIDDEN_KEYS & set(r)
        if bad:
            errs.append(f"seq {r.get('seq')}: 원본 매체로 보이는 필드 {bad}")
    return errs


def press_safety_violations(records: list) -> list:
    """PRESS 안내가 손 놓침 중·위치 맞춤 무효·목표 화면 버전 불일치 상태에서 나왔는지 기록으로 검사한다."""
    out = []
    lost = False
    aligned = None
    screen_version = None
    target = None
    for r in records:
        k = r["kind"]
        if k == "hand_lost":
            lost = True
        elif k == "hand_found":
            lost = False
        elif k == "marker":
            aligned = r["aligned"]
        elif k == "screen":
            screen_version = r["screen_version"]
            target = None
        elif k == "target":
            target = r if r.get("target_id") else None
            screen_version = r["screen_version"] if screen_version is None or r["screen_version"] > screen_version else screen_version
        elif k == "guide" and r["code"] == "PRESS" and not r.get("suppressed"):
            if lost:
                out.append(f"seq {r['seq']}: 손 놓침 중 PRESS")
            if aligned is False:
                out.append(f"seq {r['seq']}: 위치 맞춤 무효 중 PRESS")
            if target is None or target["target_id"] != r.get("target_id"):
                out.append(f"seq {r['seq']}: 현재 목표가 아닌 PRESS")
            elif target["screen_version"] != screen_version:
                out.append(f"seq {r['seq']}: 화면 버전 불일치 PRESS")
    return out


def guide_sequence(records: list, with_text=False) -> list:
    return [(r["code"], r["text"]) if with_text else r["code"] for r in records if r["kind"] == "guide" and not r.get("suppressed")]
