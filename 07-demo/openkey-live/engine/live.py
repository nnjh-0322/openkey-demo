"""OpenKey 안내 판단 엔진(순수 로직, 시간 주입).

입력: 키오스크 화면 지도·터치(on_kiosk), 손끝 관측(on_hand), 마커 위치 맞춤(on_markers),
      사용자 명령(on_voice), 운영 조작(control/set_goal/start_attempt/end_attempt), 시간 경과(tick).
출력: 말하기 큐(speaker.after), 키오스크 명령(cmds), 실시간 상태(live), 기록(JSONL, SCHEMA v1).

안전 규칙(기록으로 검증 가능):
  PRESS(누르세요)는 손을 추적 중이고(손 놓침 아님, 관측이 stale_s 이내), 위치 맞춤이 유효하고,
  목표의 screen_version이 지금 키오스크 화면과 같고, 손 내림 확인 절차가 끝났을 때만 낸다.
"""
from __future__ import annotations

import datetime
import math
import pathlib
import random
import time
from collections import deque
from dataclasses import asdict, dataclass

from .goals import DEFAULT_GOAL, GOALS, STEP_NAME, STEPS, goal_public, hit_regions, plan_target
from .guidance import DIR_TEXT, DirectionGuide, direction_vector, inside
from .recorder import Recorder, iso, new_attempt_id
from .speech import Speaker, estimate_s

TIMER_REASONS = {"idle", "timeout", "done-auto", "paid"}


@dataclass
class Config:
    dwell_ms: int = 650            # 목표 안쪽에 머문 뒤 '누르세요'까지
    inset: float = 0.08            # 목표 안쪽 여유 비율
    stale_s: float = 0.6           # 손끝 관측이 이보다 오래되면 '추적 중 아님'
    lost_grace_s: float = 0.5      # 이만큼 손이 안 보이면 hand_lost 기록
    lost_say_s: float = 1.2        # 이만큼 안 보이면 '손이 보이지 않아요'
    align_max_age_s: float = 2.0   # 위치 맞춤(호모그래피)이 이보다 낡으면 무효
    hand_down_clear_s: float = 0.6 # 손이 이만큼 안 보이면 '내려갔다'
    unreadable_wait_s: float = 1.0 # 새 화면을 못 읽을 때 손 내림 요청 전 대기
    hesitation_min_ms: int = 700
    sample_hz: float = 10.0        # finger 기록 상한
    perf_every_s: float = 2.0
    auto_click: bool | None = None # None이면 키오스크 터치 지원 여부로 결정(터치 지원이면 끔)
    auto_click_after_s: float = 0.5
    smooth: float = 0.55           # 새 관측 가중치(지수 평활)
    min_dir_gap_s: float = 0.5
    press_repeat_s: float = 4.0
    raise_hint_s: float = 3.0
    raise_again_s: float = 8.0     # 금액 안내 뒤 손이 이만큼 안 돌아오면 한 번 더 '손을 다시 올려 주세요'
    max_attempt_s: float = 900.0
    zoom: bool | None = None
    det_threshold: float | None = None


def _round(v, n=4):
    return None if v is None else round(float(v), n)


class LiveEngine:
    def __init__(self, cfg: Config | None = None, runs_dir: pathlib.Path | None = None, wall=None, rng=None,
                 default_data_source="rehearsal"):
        self.cfg = cfg or Config()
        self.runs_dir = runs_dir
        self.wall = wall or (lambda: datetime.datetime.now().astimezone())
        self.rng = rng or random.Random()
        self.default_data_source = default_data_source
        self.speaker = Speaker(on_emit=self._on_emit)
        self.kiosk = None
        self.kiosk_at = None
        self.kiosk_screen_events = deque(maxlen=20)
        self.goal = GOALS[DEFAULT_GOAL]
        self.attempt = None
        self.last_summary = None
        self.align = {"count": 0, "aligned": False, "age_s": None, "at": None, "source": None}
        self.hand = None
        self.last_seen = None
        self.rate = deque(maxlen=60)
        self.perf = {}
        self.perf_at = None
        self.cmds = deque(maxlen=200)
        self.cmd_n = 0
        self.phone_poll_at = None
        self.laptop_poll_at = None
        self.phone = {}
        self.auto_click = self.cfg.auto_click
        self.auto_click_decided = self.cfg.auto_click is not None
        self.paused = False
        self.operator_at = -1e9
        self._reset_attempt_state()

    # ------------------------------------------------------------------ 상태 초기화
    def _reset_attempt_state(self):
        self.plan = None
        self.plan_version = None
        self.cur_screen = None
        self.target = None
        self.target_set_at = None
        self.guide = DirectionGuide(dwell_ms=self.cfg.dwell_ms, inset=self.cfg.inset)
        self.gate = None
        self.pending_press = None
        self.last_wrong = None
        self.active_step = None
        self.max_step = None
        self.step_start = None
        self.step_counts = self._zero_step()
        self.dwell = None
        self.last_dir = None
        self.hold_said = False
        self.press_at = None
        self.auto_clicked = False
        self.said_raise = False
        self.lost = False
        self.lost_at = None
        self.lost_said = False
        self.lost_quiet = False      # 손 내림을 요청해서 사라진 손은 '손 놓침'으로 세지 않는다
        self.hand_down_quiet = False
        self.last_press = None
        self.last_guide = None
        self.finger_at = None
        self.marker_logged = None
        self.marker_logged_at = None
        self.finish_at = None
        self.done_emitted = False
        self.await_reset = None
        self.safety = {"press_allowed": False, "reason": "no_attempt"}
        self.counts = {"presses": 0, "wrong_presses": 0, "reverts": 0, "hesitations": 0, "hand_lost": 0,
                       "hand_down_requests": 0, "guides": 0}

    @staticmethod
    def _zero_step():
        return {"presses": 0, "wrong_presses": 0, "hesitations": 0, "guides": 0}

    # ------------------------------------------------------------------ 기록·말하기
    def _rec(self, kind, now, **f):
        if self.attempt:
            return self.attempt["rec"].write(kind, now, **f)
        return None

    def _channel(self, now):
        return "phone" if self.phone_poll_at is not None and now - self.phone_poll_at < 3.0 else "laptop"

    def _on_emit(self, it):
        now = it["t"]
        if not self.attempt:
            return
        self._rec("guide", now, code=it["code"], text=it["text"], target_id=it["target_id"], channel=self._channel(now), suppressed=False)
        self.counts["guides"] += 1
        self.step_counts["guides"] += 1
        self.last_guide = {"code": it["code"], "text": it["text"], "ms": self.attempt["rec"].ms(now),
                           "direction": direction_vector(it["code"]), "n": it["n"]}
        if it["code"] == "DONE":
            self.done_emitted = True

    def _say(self, code, text, now, prio=None, force=False, allow_paused=False):
        if not self.attempt or not text:
            return "off", None
        if self.attempt["conditions"].get("guidance") == "off":
            return "off", None
        if self.paused and not allow_paused:
            return "paused", None
        tid = self.target["id"] if self.target else None
        st, it = self.speaker.offer(code, text, now, prio=prio, target_id=tid, force=force)
        if st == "suppressed":
            # 억제된 말도 남긴다: 같은 말을 1초 이상 지나 다시 내려 했을 때, 코드별 5초에 한 번.
            # ('같은 말 연달아 반복 안 함'을 기록으로 확인하는 용도. 같은 계산 주기의 중복은 남기지 않는다.)
            key = (code, text)
            last = self.attempt.setdefault("supp", {})
            lt = self.speaker.last["t"] if self.speaker.last else now
            if now - lt >= 1.0 and now - last.get(key, -1e9) >= 5.0:
                last[key] = now
                self._rec("guide", now, code=code, text=text, target_id=tid, channel=self._channel(now), suppressed=True)
        return st, it

    # ------------------------------------------------------------------ 시도
    def start_attempt(self, now, conditions=None, goal_id=None, data_source=None, device=None, reset_kiosk=True):
        if self.attempt:
            self.end_attempt(now, "aborted")
        if goal_id:
            if goal_id not in GOALS:
                raise ValueError(f"알 수 없는 목표: {goal_id}")
            self.goal = GOALS[goal_id]
        wall = self.wall()
        aid = new_attempt_id(wall, self.rng)
        cond = {"layout": None, "guidance": "on", "blindfold": "unknown", "lighting_note": "", "participant_code": "", "operator_note": ""}
        cond.update({k: v for k, v in (conditions or {}).items() if k in cond})
        if cond["layout"] is None and self.kiosk:
            cond["layout"] = self.kiosk.get("layout")
        ds = data_source or self.default_data_source
        path = (self.runs_dir / f"{aid}.jsonl") if self.runs_dir else None
        rec = Recorder(aid, now, wall, path)
        self._reset_attempt_state()
        self.paused = False
        self.attempt = {"id": aid, "t0": now, "started": iso(wall), "data_source": ds, "conditions": cond, "rec": rec, "path": path}
        dev = {"cam_w": None, "cam_h": None, "phone_ua_short": None, "audio_out": "unknown"}
        dev.update({k: v for k, v in (device or {}).items() if k in dev})
        settings = {"dwell_ms": self.cfg.dwell_ms, "zoom": self.cfg.zoom, "det_threshold": self.cfg.det_threshold,
                    "sample_hz": self.cfg.sample_hz, "auto_click": self.auto_click, "inset": self.cfg.inset,
                    "stale_ms": int(self.cfg.stale_s * 1000), "hesitation_min_ms": self.cfg.hesitation_min_ms}
        rec.write("attempt_start", now, data_source=ds, button_source="kiosk_ground_truth", conditions=cond,
                  goal=goal_public(self.goal), device=dev, settings=settings)
        if reset_kiosk and self.kiosk is not None:
            self.queue_cmd({"type": "reset", "layout": cond["layout"] or self.kiosk.get("layout") or "B", "screen": "start"})
            self.await_reset = {"since": now, "version": self.kiosk.get("screenVersion")}
            self.operator_at = now
        self._say("INFO", f"{self.goal['say']} 주문.", now)
        self._step(now)
        return aid

    def end_attempt(self, now, reason="aborted"):
        a = self.attempt
        if not a:
            return None
        if self.pending_press:
            self._finalize_press(now, self.kiosk.get("screen") if self.kiosk else None)
        self._hes_end(now, "screen_change")
        completed = reason == "done"
        if completed and self.max_step is not None:
            self._rec("step_done", now, step=self.max_step, name=STEP_NAME.get(self.max_step), duration_ms=int((now - self.step_start) * 1000),
                      **self.step_counts)
        order_no = None
        if completed and self.kiosk:
            order_no = (self.kiosk.get("order") or {}).get("orderNo")
        rec = a["rec"].write("attempt_end", now, completed=completed, end_reason=reason, order_no=order_no,
                             total_ms=a["rec"].ms(now), counts=dict(self.counts))
        a["rec"].close()
        self.last_summary = {"id": a["id"], "completed": completed, "end_reason": reason, "order_no": order_no,
                             "total_ms": rec["ms"], "path": str(a["path"]) if a["path"] else None}
        self.attempt = None
        self.safety = {"press_allowed": False, "reason": "no_attempt"}
        return self.last_summary

    def set_goal(self, now, goal_id, by="operator"):
        if goal_id not in GOALS:
            raise ValueError(f"알 수 없는 목표: {goal_id}")
        self.goal = GOALS[goal_id]
        if self.attempt:
            if by == "operator":
                self._rec("operator", now, action="goal", detail=goal_id)
            self.plan_version = None  # 다음 단계에서 다시 계획
            self._say("INFO", f"목표를 바꿨어요. {self.goal['say']}입니다.", now)
            self._step(now)

    def control(self, now, action, by="operator"):
        if by == "operator":
            self.operator_at = now
            self._rec("operator", now, action=action, detail="")
        if action == "stop":
            self.paused = True
            self.speaker.cancel(now, "stop")
            self._say("INFO", "안내를 멈췄어요. 다시 하려면 시작을 누르세요.", now, prio=0, allow_paused=True)
        elif action in ("resume", "start"):
            if self.paused:
                self.paused = False
                self.guide.reset()
                self.press_at = None
                self._say("INFO", "다시 안내할게요. " + self._where_text(), now, force=True)
        elif action == "repeat":
            self._say("INFO", self._where_text(), now, force=True, prio=1)
        elif action == "auto_click_on":
            self.auto_click, self.auto_click_decided = True, True
        elif action == "auto_click_off":
            self.auto_click, self.auto_click_decided = False, True
        self._step(now)

    def _where_text(self):
        if self.plan and self.plan.done:
            return self.plan.announce or "주문이 끝났어요."
        if self.gate and self.gate.get("phase") == "waiting_down":
            return "손을 잠시 내려 주세요."
        if self.target and self.plan:
            t = f"지금은 {self.plan.screen_name}입니다. {self.target['label']} 버튼을 찾고 있어요."
            if self.last_dir:
                t += " " + DIR_TEXT.get(self.last_dir["code"], "")
            return t.strip()
        return f"{self.goal['say']} 주문 중입니다."

    def on_voice(self, now, command, via="button", goal_id=None):
        if command == "start" and not self.attempt:
            self.start_attempt(now, goal_id=goal_id)
            self._rec("voice_cmd", now, command=command, goal_id=goal_id, via=via)
            return
        self._rec("voice_cmd", now, command=command, goal_id=goal_id, via=via)
        if command == "goal" and goal_id:
            if self.attempt:
                self.set_goal(now, goal_id, by="user")
            else:
                self.goal = GOALS.get(goal_id, self.goal)
        elif command in ("stop", "repeat", "start"):
            self.control(now, command, by="user")

    def queue_cmd(self, cmd):
        self.cmd_n += 1
        cmd = dict(cmd, n=self.cmd_n)
        self.cmds.append(cmd)
        return cmd

    # ------------------------------------------------------------------ 입력
    def on_kiosk(self, now, state: dict, touches=None, screen_events=None):
        for ev in screen_events or []:
            self.kiosk_screen_events.append(ev)
        for t in touches or []:
            self._on_touch(now, t)
        self.kiosk = state
        self.kiosk_at = now
        if not self.auto_click_decided and "autoDefault" in state:
            self.auto_click = bool(state["autoDefault"])
            self.auto_click_decided = True
        self._step(now)

    def on_markers(self, now, count, aligned, age_s, source="camera"):
        self.align = {"count": int(count), "aligned": bool(aligned), "age_s": age_s, "at": now, "source": source}
        if self.attempt:
            key = (int(count), bool(aligned))
            if self.marker_logged is None or (key[1] != self.marker_logged[1]) or (key != self.marker_logged and now - self.marker_logged_at >= 1.0):
                self.marker_logged, self.marker_logged_at = key, now
                self._rec("marker", now, count=int(count), aligned=bool(aligned), align_age_s=_round(age_s, 2))

    def _aligned_now(self, now):
        a = self.align
        return bool(a["aligned"]) and a["at"] is not None and now - a["at"] <= self.cfg.align_max_age_s

    def on_hand(self, now, rep: dict):
        """rep: {tracked, x, y(키오스크 정규), count, aligned, frame_age_ms, model_ms, input_w, input_h, zoom, det_threshold, fps, source}"""
        age = float(rep.get("frame_age_ms") or 0) / 1000.0
        obs_at = now - age
        x, y = rep.get("x"), rep.get("y")
        tracked = bool(rep.get("tracked")) and x is not None and y is not None and math.isfinite(x) and math.isfinite(y)
        self.rate.append(1 if tracked else 0)
        self.perf = {"model_ms": rep.get("model_ms"), "input_w": rep.get("input_w"), "input_h": rep.get("input_h"),
                     "zoom": rep.get("zoom"), "det_threshold": rep.get("det_threshold"), "frame_age_ms": rep.get("frame_age_ms"),
                     "fps": rep.get("fps"), "at": now, "source": rep.get("source", "camera"), "rescan": rep.get("rescan")}
        if rep.get("source") == "synthetic" and "aligned" in rep:
            self.on_markers(now, rep.get("markers", 4 if rep["aligned"] else 0), rep["aligned"], 0.0 if rep["aligned"] else None, "synthetic")
        aligned = bool(rep["aligned"]) if "aligned" in rep else self._aligned_now(now)
        if tracked:
            raw = (float(x), float(y))
            prev = self.hand
            if prev and prev.get("tracked") and obs_at - prev["at"] < 0.4 and self.cfg.smooth < 1:
                a = self.cfg.smooth
                p = (prev["p"][0] * (1 - a) + raw[0] * a, prev["p"][1] * (1 - a) + raw[1] * a)
            else:
                p = raw
            over = self._hit(p)
            if self.lost:
                if not self.lost_quiet:
                    self._rec("hand_found", now, lost_ms=int((obs_at - self.lost_at) * 1000) if self.lost_at else None)
                self.lost, self.lost_said, self.lost_quiet = False, False, False
            self.hand_down_quiet = False
            self.last_seen = obs_at
            self.hand = {"tracked": True, "p": p, "raw": raw, "count": int(rep.get("count") or 1), "at": obs_at, "aligned": aligned, "over": over}
            if self.attempt and (self.finger_at is None or now - self.finger_at >= 1.0 / self.cfg.sample_hz):
                self.finger_at = now
                self._rec("finger", now, x=_round(p[0]), y=_round(p[1]), tracked=True, over=over, dist=self._dist(p))
            self._hes_update(now, over)
        else:
            if self.hand:
                self.hand = dict(self.hand, tracked=False)
        self._step(now)

    def _hit(self, p):
        if not self.kiosk:
            return None
        best, area = None, 9.0
        for r in hit_regions(self.kiosk).values():
            if not r.get("enabled", True):
                continue
            b = r["bbox"]
            if inside(p, b):
                a = (b[2] - b[0]) * (b[3] - b[1])
                if a < area:
                    best, area = r["id"], a
        return best

    def _dist(self, p):
        if not self.target or p is None:
            return None
        b = self.target["bbox"]
        return _round(math.hypot(p[0] - (b[0] + b[2]) / 2, p[1] - (b[1] + b[3]) / 2))

    def _hand_fresh(self, now):
        h = self.hand
        return bool(h and h.get("tracked") and not self.lost and 0 <= now - h["at"] <= self.cfg.stale_s)

    # ------------------------------------------------------------------ 누름
    def _on_touch(self, now, t):
        if not self.attempt:
            return
        if self.pending_press:
            self._finalize_press(now, self.kiosk.get("screen") if self.kiosk else None)
        hit = t.get("id")
        sv = t.get("screenVersion")
        tgt = self.target if (self.target and (sv is None or self.target["screen_version"] == sv)) else None
        if not hit:
            result = "no_button"
        elif not tgt:
            result = "no_target"
        elif hit == tgt["id"]:
            result = "correct"
        else:
            result = "wrong"
        src = "auto_click" if t.get("source") in ("auto_click", "camera") else "direct"
        self.pending_press = {"x": _round(t.get("x")), "y": _round(t.get("y")), "hit": hit, "target_id": tgt["id"] if tgt else None,
                              "result": result, "source": src, "screen": t.get("screen") or self.cur_screen, "sv": sv,
                              "at": now, "kind": tgt["kind"] if tgt else None}
        if self.dwell and self.dwell["id"] == hit:
            self.dwell["pressed"] = True

    def _finalize_press(self, now, next_screen):
        pp, self.pending_press = self.pending_press, None
        self._rec("press", now, x=pp["x"], y=pp["y"], hit_id=pp["hit"], target_id=pp["target_id"], result=pp["result"],
                  source=pp["source"], screen=pp["screen"], next_screen=next_screen)
        self.counts["presses"] += 1
        self.step_counts["presses"] += 1
        if pp["result"] == "wrong":
            self.counts["wrong_presses"] += 1
            self.step_counts["wrong_presses"] += 1
            self.last_wrong = {"from": pp["screen"], "at": now}
        self.last_press = {"hit_id": pp["hit"], "result": pp["result"], "ms": self.attempt["rec"].ms(now) if self.attempt else None,
                           "source": pp["source"]}
        if pp["result"] == "correct" and pp["kind"] == "revert" and next_screen != pp["screen"]:
            self._rec("revert", now, from_screen=pp["screen"], to_screen=next_screen, reason="wrong_press" if self.last_wrong else "user")
            self.counts["reverts"] += 1
            self.last_wrong = None
        return pp

    # ------------------------------------------------------------------ 망설임
    def _hes_update(self, now, over):
        d = self.dwell
        if d and d["id"] == over:
            return
        if d:
            self._hes_end(now, "moved_away")
        self.dwell = {"id": over, "start": now, "pressed": False} if over else None

    def _hes_end(self, now, by):
        d, self.dwell = self.dwell, None
        if d and not d["pressed"] and (now - d["start"]) * 1000 >= self.cfg.hesitation_min_ms and self.attempt:
            self._rec("hesitation", now, region_id=d["id"], on_target=bool(self.target and self.target["id"] == d["id"]),
                      dwell_ms=int((now - d["start"]) * 1000), ended_by=by)
            self.counts["hesitations"] += 1
            self.step_counts["hesitations"] += 1

    # ------------------------------------------------------------------ 주기 처리
    def tick(self, now):
        self._step(now)

    def _step(self, now):
        self.speaker.flush(now)
        if not self.attempt:
            return
        self._lost_check(now)
        self._perf(now)
        if self.finish_at is not None:
            if self.done_emitted or now - self.finish_at > 6.0 or self.attempt["conditions"].get("guidance") == "off":
                self.end_attempt(now, "done")
            return
        if now - self.attempt["t0"] > self.cfg.max_attempt_s:
            self.end_attempt(now, "timeout")
            return
        if self.await_reset:
            k = self.kiosk
            if (k and k.get("screenVersion") != self.await_reset["version"]) or now - self.await_reset["since"] > 3.0:
                self.await_reset = None
            else:
                return
        self._plan_step(now)
        self._guide(now)

    def _lost_check(self, now):
        if self.last_seen is None:
            return
        fresh = self.hand and self.hand.get("tracked") and now - self.hand["at"] <= self.cfg.lost_grace_s
        if not self.lost and not fresh and now - self.last_seen > self.cfg.lost_grace_s:
            self.lost, self.lost_at, self.lost_said = True, self.last_seen, False
            # 손 내림을 요청한 뒤(내려가는 중·금액 읽는 중·다시 올리기를 기다리는 중) 손이 안 보이는 것은 정상이다.
            self.lost_quiet = self.hand_down_quiet or bool(self.gate and self.gate.get("phase") != "start")
            p = self.hand["p"] if self.hand else None
            cause = "out_of_frame" if p and not (-0.05 <= p[0] <= 1.05 and -0.05 <= p[1] <= 1.05) else "unknown"
            if not self.lost_quiet:
                self._rec("hand_lost", now, cause=cause)
                self.counts["hand_lost"] += 1
            self._hes_end(now, "hand_lost")
            self.guide.reset()
            self.press_at = None
            cur = self.speaker.cur
            if cur and self.speaker.busy(now) and cur["code"] not in ("SCREEN", "PAY_CHECK", "DONE", "PRESS_OK", "INFO", "HAND_DOWN", "PRESS_WRONG"):
                self.speaker.cancel(now, "hand_lost")
        cur = self.speaker.cur
        informing = cur is not None and self.speaker.busy(now) and cur["code"] in ("SCREEN", "PAY_CHECK", "DONE", "HAND_DOWN", "PRESS_WRONG")
        if self.lost and not self.lost_said and not self.lost_quiet and self.target and not self.gate and not informing \
                and now - self.lost_at >= self.cfg.lost_say_s:
            # 화면·금액 안내를 끊고 '손이 보이지 않아요'를 내지 않는다(안내가 끝난 뒤 다시 확인).
            st, _ = self._say("HAND_LOST", "손이 안 보여요.", now)
            if st in ("emitted", "queued", "suppressed", "off"):
                self.lost_said = True

    def _perf(self, now):
        if self.perf_at is not None and now - self.perf_at < self.cfg.perf_every_s:
            return
        self.perf_at = now
        p = self.perf
        if not p or now - p.get("at", -1e9) > 3.0:
            return
        self._rec("perf", now, hand_rate=_round(sum(self.rate) / len(self.rate), 3) if self.rate else None,
                  model_ms=_round(p.get("model_ms"), 1), input_w=p.get("input_w"), input_h=p.get("input_h"), zoom=p.get("zoom"),
                  det_threshold=p.get("det_threshold"), frame_age_ms=p.get("frame_age_ms"), fps=_round(p.get("fps"), 1))

    # ------------------------------------------------------------------ 계획
    def _plan_step(self, now):
        k = self.kiosk
        if k is None:
            return
        v = k.get("screenVersion")
        if v != self.plan_version:
            pp = self._finalize_press(now, k.get("screen")) if self.pending_press else None
            self._replan(now, pp)
        elif self.pending_press and now - self.pending_press["at"] > 1.0:
            pp = self._finalize_press(now, k.get("screen"))
            self.guide.reset()
            self.press_at = None
            self.auto_clicked = False
            if pp["result"] == "wrong":
                self._say("PRESS_WRONG", "다른 버튼이 눌렸어요.", now)
            elif pp["result"] == "no_button":
                self._say("INFO", "버튼 밖이 눌렸어요.", now)

    def _screen_cause(self, now, pp):
        if pp:
            return "press"
        if now - self.operator_at < 3.0:
            return "operator"
        ev = self.kiosk_screen_events[-1] if self.kiosk_screen_events else None
        if ev and ev.get("to") == (self.kiosk or {}).get("screen") and ev.get("reason") in TIMER_REASONS:
            return "timer"
        return "unknown"

    def _replan(self, now, pp):
        k = self.kiosk
        v, scr = k.get("screenVersion"), k.get("screen")
        prev = self.cur_screen
        plan = plan_target(self.goal, k)
        changed = scr != prev
        if changed:
            self.speaker.clear_pending()  # 이전 화면의 대기 말은 버린다
            self._rec("screen", now, screen=scr, screen_version=v, **{"from": prev}, cause=self._screen_cause(now, pp))
            self._hes_end(now, "screen_change")
        old = self.target
        self.target = None  # 화면이 바뀌면 이전 목표는 즉시 버린다
        self.guide.reset()
        self.hold_said, self.press_at, self.auto_clicked, self.last_dir = False, None, False, None
        self.plan, self.plan_version, self.cur_screen = plan, v, scr
        if plan.target_id:
            r = hit_regions(k)[plan.target_id]
            self.target = {"id": plan.target_id, "label": plan.label, "bbox": [float(c) for c in r["bbox"]], "screen_version": v,
                           "kind": plan.kind, "step": plan.step, "screen": scr}
            self.target_set_at = now
            reason = "replan" if (pp and pp["result"] in ("wrong", "no_button")) or plan.kind in ("revert", "fix") or (old and old["id"] == plan.target_id) else "plan"
            self._rec("target", now, step=plan.step, screen=scr, screen_version=v, target_id=plan.target_id, label=plan.label,
                      bbox=[_round(c, 5) for c in r["bbox"]], reason=reason)
        elif old is not None:
            self._rec("target", now, step=plan.step, screen=scr, screen_version=v, target_id=None, label=None, bbox=None, reason="cleared")
        self._step_progress(now, plan.step)
        # ---- 말
        announced = False
        if pp:
            if pp["result"] == "correct":
                if changed or not self.target or (old and old["id"] == self.target["id"]):
                    self._say("PRESS_OK", "맞아요.", now)
                else:
                    self._say("PRESS_OK", f"맞아요. 다음 {self.target['label']}.", now)
            elif pp["result"] == "wrong":
                if plan.kind == "revert" and self.target:
                    self._say("PRESS_WRONG", f"다른 버튼이 눌렸어요. {self.target['label']} 버튼으로 돌아가요.", now)
                    announced = True
                else:
                    self._say("PRESS_WRONG", "다른 버튼이 눌렸어요.", now)
            elif pp["result"] == "no_button":
                self._say("INFO", "버튼 밖이 눌렸어요.", now)
        hand_down_now = changed and plan.payment and self._hand_present(now)
        if changed and plan.announce and not announced and not hand_down_now:
            self._say(plan.announce_code, plan.announce, now)
        elif not changed and not pp and self.target and (old is None or old["id"] != self.target["id"]):
            self._say("INFO", f"다음 {self.target['label']}.", now)
        # ---- 손 내림 정책
        if changed:
            self.gate = None
            if plan.payment:
                self.gate = {"kind": "payment", "phase": "start", "since": now, "text": plan.pay_check,
                             "hd_text": f"{plan.announce or ''} 손을 내려 주세요.".strip()}
            elif self.target and self.align["at"] is not None and not self._aligned_now(now):
                self.gate = {"kind": "unreadable", "phase": "wait", "since": now}
        if plan.done:
            self.finish_at = now
            if plan.announce_code != "DONE" or not plan.announce:
                self.done_emitted = True

    def _step_progress(self, now, step):
        self.active_step = step
        if self.max_step is None:
            self.max_step, self.step_start = step, now
            return
        if step > self.max_step:
            for s in range(self.max_step, step):
                c = self.step_counts if s == self.max_step else self._zero_step()
                self._rec("step_done", now, step=s, name=STEP_NAME.get(s), duration_ms=int((now - self.step_start) * 1000) if s == self.max_step else 0, **c)
            self.max_step, self.step_start = step, now
            self.step_counts = self._zero_step()

    # ------------------------------------------------------------------ 손 내림·안내
    def _hand_present(self, now):
        h = self.hand
        if not h or not h.get("tracked") or now - h["at"] > self.cfg.hand_down_clear_s:
            return False
        p = h["p"]
        return -0.15 <= p[0] <= 1.15 and -0.15 <= p[1] <= 1.15

    def _run_gate(self, now) -> bool:
        g = self.gate
        if g["kind"] == "payment":
            if g["phase"] == "start":
                if self._hand_present(now):
                    self._rec("hand_down_request", now, reason="payment_check", waited_ms=0)
                    self.counts["hand_down_requests"] += 1
                    self._say("HAND_DOWN", g.get("hd_text") or "손을 내려 주세요.", now)
                    g.update(phase="waiting_down", req_at=now, said_at=now)
                else:
                    g["phase"] = "read"
            if g["phase"] == "waiting_down":
                if not self._hand_present(now):
                    self._rec("hand_down_done", now, took_ms=int((now - g["req_at"]) * 1000))
                    self.hand_down_quiet = True
                    self.speaker.drop_pending("HAND_DOWN")  # 이미 내렸으면 아직 못 한 요청은 말하지 않는다
                    g["phase"] = "read"
                elif now - g["said_at"] >= 6.0:
                    g["said_at"] = now
                    self._say("HAND_DOWN", "손을 떼 주세요.", now)
            if g["phase"] == "read":
                # 금액을 다 읽을 때까지(예상 길이) 게이트를 유지한다. 그동안 손이 안 보이는 것은 정상이다.
                text = g.get("text") or "금액을 확인했어요."
                start = max(now, self.speaker.busy_until) if self.speaker.busy(now) else now
                self._say("PAY_CHECK", text, now)
                g.update(phase="reading", read_until=start + estimate_s(text) + 0.3)
                return False
            if g["phase"] == "reading":
                if now < g["read_until"]:
                    return False
                g.update(phase="raise", raise_at=now, said_at=now)
            if g["phase"] == "raise":
                # 금액 안내 끝에 '손을 다시 올려 주세요'를 이미 말했다. 손이 돌아오면 안내를 이어 간다.
                if self._hand_present(now):
                    self.gate = None
                    return True
                if now - g["said_at"] >= self.cfg.raise_again_s:
                    g["said_at"] = now
                    self._say("INFO", "손을 화면에 올려 주세요.", now)
                return False
            return False
        if g["kind"] == "unreadable":
            if self._aligned_now(now):
                if g["phase"] == "waiting_down":
                    self._rec("hand_down_done", now, took_ms=int((now - g["req_at"]) * 1000))
                    self.hand_down_quiet = True
                    self._say("INFO", "손을 다시 올려 주세요.", now)
                self.gate = None
                return True
            if g["phase"] == "wait" and now - g["since"] >= self.cfg.unreadable_wait_s:
                self._rec("hand_down_request", now, reason="new_screen_unreadable", waited_ms=int((now - g["since"]) * 1000))
                self.counts["hand_down_requests"] += 1
                self._say("HAND_DOWN", "화면 확인. 손을 내려 주세요.", now)
                g.update(phase="waiting_down", req_at=now)
            return False
        return True

    def press_safety(self, now):
        if not self.attempt:
            return False, "no_attempt"
        if self.paused:
            return False, "paused"
        if not self.target:
            return False, "no_target"
        if self.gate:
            return False, "hand_down_check" if self.gate["kind"] == "payment" else "screen_unreadable"
        if self.kiosk_at is None or now - self.kiosk_at > 3.0:
            return False, "kiosk_lost"
        if not self._hand_fresh(now):
            return False, "hand_lost" if self.lost or self.last_seen is not None else "no_hand"
        if not self.hand.get("aligned") or not self._aligned_now(now):
            return False, "not_aligned"
        if self.target["screen_version"] != self.kiosk.get("screenVersion"):
            return False, "screen_changed"
        if self.hand.get("count", 1) > 1:
            return False, "multiple_hands"
        if not inside(self.hand["p"], self.target["bbox"]):
            return False, "not_on_target"
        if not self.guide.entered or self.guide.since is None or (now - self.guide.since) * 1000 < self.cfg.dwell_ms:
            return False, "dwell"
        return True, "ok"

    def _guide(self, now):
        ok, reason = self.press_safety(now)
        self.safety = {"press_allowed": ok, "reason": reason}
        if self.paused or self.finish_at is not None:
            return
        if self.gate and not self._run_gate(now):
            self.safety = {"press_allowed": False, "reason": "hand_down_check" if self.gate and self.gate["kind"] == "payment" else "screen_unreadable"}
            return
        t = self.target
        if not t or self.kiosk_at is None or now - self.kiosk_at > 3.0:
            return
        if not self._hand_fresh(now):
            self.guide.reset()
            if self.target_set_at is not None and (self.last_seen is None or self.last_seen < self.target_set_at) \
                    and now - self.target_set_at > self.cfg.raise_hint_s and not self.said_raise:
                self.said_raise = True
                self._say("INFO", "손을 화면에 올려 주세요.", now)
            return
        if not self.hand.get("aligned") or not self._aligned_now(now):
            self.guide.reset()
            return
        if t["screen_version"] != self.kiosk.get("screenVersion"):
            return
        res = self.guide.update(self.hand["p"], t["bbox"], now)
        if res["state"] == "guiding":
            self.hold_said, self.press_at, self.auto_clicked = False, None, False
            code = res["code"]
            if self.last_dir and self.last_dir["code"] != code and now - self.last_dir["at"] < self.cfg.min_dir_gap_s:
                return
            st, _ = self._say(code, DIR_TEXT[code], now)
            if st == "emitted":
                self.last_dir = {"code": code, "at": now}
            return
        if res["state"] == "hold":
            if not self.hold_said:
                st, _ = self._say("HOLD", "멈추세요.", now)
                self.hold_said = st != "dropped"
            return
        # press
        ok, reason = self.press_safety(now)
        self.safety = {"press_allowed": ok, "reason": reason}
        if not ok:
            return
        if self.press_at is None or now - self.press_at >= self.cfg.press_repeat_s:
            st, _ = self._say("PRESS", "누르세요.", now)
            if st in ("emitted", "off"):
                self.press_at = now
            elif st == "suppressed" and self.press_at is None:
                self.press_at = now
        if self.auto_click and self.press_at is not None and not self.auto_clicked and now - self.press_at >= self.cfg.auto_click_after_s:
            self.auto_clicked = True
            p = self.hand["p"]
            self.queue_cmd({"type": "click", "x": _round(p[0], 5), "y": _round(p[1], 5), "target_id": t["id"], "screen_version": t["screen_version"]})

    # ------------------------------------------------------------------ 실시간 상태
    def live(self, now) -> dict:
        a = self.attempt
        k = self.kiosk
        steps = []
        cur = self.active_step
        for s in STEPS:
            if a is None or cur is None:
                stt = "todo"
            elif self.plan and self.plan.done:
                stt = "done"
            elif s["step"] < cur:
                stt = "done"
            elif s["step"] == cur:
                stt = "active"
            else:
                stt = "todo"
            steps.append(dict(s, status=stt))
        h = self.hand
        finger = {"tracked": self._hand_fresh(now), "x": _round(h["p"][0]) if h else None, "y": _round(h["p"][1]) if h else None,
                  "over": h.get("over") if h else None, "age_ms": int((now - h["at"]) * 1000) if h else None,
                  "count": h.get("count") if h else None}
        p = self.perf
        status = {"camera": bool(p and now - p.get("at", -1e9) < 2.0) or (self.align["at"] is not None and now - self.align["at"] < 2.0),
                  "markers": self.align["count"], "aligned": self._aligned_now(now), "align_age_s": self.align["age_s"],
                  "hand_rate": _round(sum(self.rate) / len(self.rate), 3) if self.rate else None,
                  "model_ms": _round(p.get("model_ms"), 1) if p else None, "frame_age_ms": p.get("frame_age_ms") if p else None,
                  "fps": _round(p.get("fps"), 1) if p else None, "cam_w": self.phone.get("cam_w"), "cam_h": self.phone.get("cam_h"),
                  "input": (p.get("source") if p else None), "zoom": p.get("zoom") if p else None,
                  "input_w": p.get("input_w") if p else None, "input_h": p.get("input_h") if p else None}
        return {
            "server_time": iso(self.wall()),
            "attempt": None if a is None else {"id": a["id"], "started": a["started"], "ms": a["rec"].ms(now), "data_source": a["data_source"],
                                               "conditions": a["conditions"]},
            "button_source": "kiosk_ground_truth",
            "button_source_label": "시연용 정답 좌표(모의 키오스크가 알려 준 버튼 위치)",
            "goal": {"id": self.goal["id"], "label": self.goal["label"]},
            "steps": steps,
            "kiosk": None if k is None else {"connected": self.kiosk_at is not None and now - self.kiosk_at < 3.0, "screen": k.get("screen"),
                                             "screen_version": k.get("screenVersion"), "layout": k.get("layout"),
                                             "regions": [{"id": r["id"], "label": r.get("label"), "bbox": r["bbox"], "hit": True,
                                                          "enabled": r.get("enabled", True)} for r in hit_regions(k).values()]},
            "target": None if not self.target else {k2: self.target[k2] for k2 in ("id", "label", "bbox", "screen_version", "kind", "step")},
            "finger": finger,
            "guide": self.last_guide,
            "safety": self.safety,
            "status": status,
            "last_press": self.last_press,
            "counts": self.counts if a else None,
            "paused": self.paused,
            "auto_click": self.auto_click,
            "hand_down": None if not self.gate else {"kind": self.gate["kind"], "phase": self.gate["phase"]},
            "phone": {"connected": self.phone_poll_at is not None and now - self.phone_poll_at < 3.0,
                      "audio_unlocked": self.phone.get("audio_unlocked"), "last_poll_age_s": _round(now - self.phone_poll_at, 1) if self.phone_poll_at else None},
            "speech_n": self.speaker.n,
            "last_attempt": self.last_summary,
            "settings": asdict(self.cfg),
        }
