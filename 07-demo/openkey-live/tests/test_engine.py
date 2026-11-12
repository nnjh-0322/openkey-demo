"""엔진 단위 시험(브라우저·카메라 없음, 시간 주입). 실행: .venv\\Scripts\\python.exe -m pytest 07-demo/openkey-live/tests -q"""
import datetime
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import pytest  # noqa: E402

from engine import GOALS, Config, DirectionGuide, LiveEngine, Speaker, plan_target  # noqa: E402
from engine.checks import guide_sequence, press_safety_violations, schema_errors  # noqa: E402
from sim import FakeKiosk, SimUser  # noqa: E402

WALL = datetime.datetime(2026, 11, 12, 23, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))


def make_engine(tmp_path=None, **cfg):
    return LiveEngine(Config(**cfg), runs_dir=tmp_path, wall=lambda: WALL, rng=random.Random(7), default_data_source="synthetic")


def hand(x, y, aligned=True, tracked=True):
    return {"tracked": tracked, "x": x, "y": y, "count": 1, "aligned": aligned, "source": "synthetic", "frame_age_ms": 0}


def tk(e, k, t):
    e.on_kiosk(t, k.state())
    e.tick(t)


def records(e):
    return e.attempt["rec"].records if e.attempt else e._last_records


class Runner:
    """엔진 + 가짜 키오스크 + 합성 사용자를 가짜 시계로 돌린다."""

    def __init__(self, e, k, u, t=100.0, dt=0.05):
        self.e, self.k, self.u, self.t, self.dt = e, k, u, t, dt
        self.seen = 0
        self.cmd_seen = 0
        self.recs = None
        self.hooks = []

    def step(self):
        e, k, u = self.e, self.k, self.u
        self.t += self.dt
        now = self.t
        e.phone_poll_at = now
        for it in e.speaker.after(self.seen):
            u.hear(now, it)
            self.seen = it["n"]
        u.update(now, self.dt)
        if e.attempt:
            self.recs = e.attempt["rec"].records
        for h in self.hooks:
            h(self, now)
        e.on_hand(now, hand(u.p[0], u.p[1]) if u.visible(now) else hand(None, None, tracked=False))
        touches = []
        if u.take_press():
            touches.append(k.touch(u.p[0], u.p[1]))
        for c in [c for c in e.cmds if c["n"] > self.cmd_seen]:
            self.cmd_seen = c["n"]
            if c["type"] == "click":
                touches.append(k.touch(c["x"], c["y"], source="auto_click"))
        e.on_kiosk(now, k.state(), touches)
        e.tick(now)

    def run(self, max_s=120):
        end = self.t + max_s
        while self.t < end and self.e.attempt:
            self.step()
        return self.recs


# ---------------------------------------------------------------------------- 방향 안내
def test_direction_axes_and_small():
    g = DirectionGuide(dwell_ms=650, inset=0.08)
    b = [0.4, 0.4, 0.6, 0.5]
    assert g.update((0.1, 0.45), b, 0)["code"] == "RIGHT"
    g.reset()
    assert g.update((0.9, 0.45), b, 0)["code"] == "LEFT"
    g.reset()
    assert g.update((0.5, 0.1), b, 0)["code"] == "DOWN"
    g.reset()
    assert g.update((0.5, 0.9), b, 0)["code"] == "UP"
    g.reset()
    assert g.update((0.40, 0.45), b, 0)["code"] == "RIGHT_SMALL"


def test_hold_then_press_after_dwell():
    g = DirectionGuide(dwell_ms=650)
    b = [0.4, 0.4, 0.6, 0.5]
    assert g.update((0.5, 0.45), b, 10.0)["state"] == "hold"
    assert g.update((0.5, 0.45), b, 10.5)["state"] == "hold"
    assert g.update((0.5, 0.45), b, 10.66)["state"] == "press"
    # 가장자리(바깥 테두리 안, 안쪽 여유 밖)에서는 이미 들어온 상태 유지
    assert g.update((0.405, 0.45), b, 10.7)["state"] == "press"
    assert g.update((0.39, 0.45), b, 10.8)["state"] == "guiding"


def test_axis_hysteresis():
    g = DirectionGuide()
    b = [0.4, 0.4, 0.6, 0.5]
    assert g.update((0.0, 0.2), b, 0)["code"].startswith("RIGHT")
    # y 오차가 조금 더 커져도 축을 바로 바꾸지 않는다
    assert g.update((0.2, 0.25), b, 0.1)["code"].startswith("RIGHT")
    # 훨씬 커지면 바꾼다
    assert g.update((0.35, 0.05), b, 0.2)["code"].startswith("DOWN")


# ---------------------------------------------------------------------------- 말하기
def test_speaker_suppresses_repeat_and_prioritizes():
    s = Speaker()
    assert s.offer("RIGHT", "오른쪽으로", 0)[0] == "emitted"
    assert s.offer("RIGHT", "오른쪽으로", 0.5)[0] == "suppressed"
    st, it = s.offer("HOLD", "멈추세요.", 0.6)
    assert st == "emitted" and it["interrupt"]
    assert s.offer("LEFT", "왼쪽으로", 0.7)[0] == "dropped"  # 더 중요한 말을 하는 중이면 방향은 버림
    assert s.offer("HAND_LOST", "손이 보이지 않아요.", 0.8)[1]["interrupt"]


def test_speaker_queues_announcements():
    s = Speaker()
    s.offer("PRESS_OK", "맞게 눌렀어요.", 0)
    assert s.offer("SCREEN", "옵션 화면입니다.", 0.1)[0] == "queued"
    assert s.flush(0.2) == []
    out = s.flush(2.0)
    assert [o["code"] for o in out] == ["SCREEN"]


# ---------------------------------------------------------------------------- 계획
def test_plan_each_screen():
    g = GOALS["iced-americano-1"]
    k = FakeKiosk()
    assert plan_target(g, k.state()).target_id == "dine-store"
    k.act("dine-store")
    p = plan_target(g, k.state())
    assert p.target_id == "item-americano" and "아메리카노" in p.announce
    k.act("item-americano")
    p = plan_target(g, k.state())
    assert p.target_id == "opt-temp-ICE" and p.step == 2
    k.act("opt-temp-ICE")
    assert plan_target(g, k.state()).target_id == "opt-add"
    k.act("opt-add")
    p = plan_target(g, k.state())
    assert p.target_id == "checkout" and p.step == 3
    k.act("checkout")
    p = plan_target(g, k.state())
    assert p.target_id == "cf-pay" and p.payment and "2,000원" in p.pay_check
    k.act("cf-pay")
    p = plan_target(g, k.state())
    assert p.target_id == "pay-simple" and p.payment
    k.act("pay-simple")
    p = plan_target(g, k.state())
    assert p.done and "27번" in p.announce


def test_plan_wrong_item_reverts():
    g = GOALS["iced-americano-1"]
    k = FakeKiosk()
    k.act("dine-store")
    k.act("item-latte")
    p = plan_target(g, k.state())
    assert p.target_id == "opt-cancel" and p.kind == "revert"


def test_plan_takeout_goal_and_josa():
    g = GOALS["hot-latte-1"]
    k = FakeKiosk()
    k.act("dine-store")
    k.act("item-latte")
    p = plan_target(g, k.state())
    assert p.target_id == "opt-temp-HOT" and "핫" in p.announce
    assert plan_target(GOALS["coldbrew-1"], FakeKiosk().state()).target_id == "dine-takeout"


# ---------------------------------------------------------------------------- 엔진 전체 흐름
def finish(e, r):
    recs = r.recs
    return recs


@pytest.mark.parametrize("auto", [False, True])
def test_full_order_with_sim_user(tmp_path, auto):
    e = make_engine(tmp_path, auto_click=auto)
    k = FakeKiosk()
    u = SimUser(start=(0.5, 0.75))
    e.on_kiosk(100.0, k.state())
    if auto:
        u.take_press = lambda: False  # 사용자가 직접 누르지 않음 → 자동 누름 경로
    e.start_attempt(100.0, conditions={"layout": "B"}, goal_id="iced-americano-1", data_source="synthetic", reset_kiosk=False)
    r = Runner(e, k, u)
    recs = r.run(150)
    assert e.attempt is None, "시간 안에 끝나지 않음"
    end = recs[-1]
    assert end["kind"] == "attempt_end" and end["completed"] and end["order_no"] == 27
    assert schema_errors(recs) == []
    assert press_safety_violations(recs) == []
    seq = guide_sequence(recs)
    for code in ("SCREEN", "PRESS", "PRESS_OK", "HAND_DOWN", "PAY_CHECK", "DONE"):
        assert code in seq, code
    presses = [x for x in recs if x["kind"] == "press"]
    assert all(p["result"] == "correct" for p in presses)
    assert {p["source"] for p in presses} == ({"auto_click"} if auto else {"direct"})
    steps = [x["name"] for x in recs if x["kind"] == "step_done"]
    assert steps == ["menu", "option", "confirm", "pay", "done"]
    # 파일에도 같은 내용
    lines = (tmp_path / f"{recs[0]['attempt']}.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(recs)


def test_no_press_while_hand_lost(tmp_path):
    """손이 목표 안에서 사라지면 PRESS가 나오지 않고, 다시 보여도 머묾을 새로 채운 뒤에만 나온다."""
    e = make_engine(tmp_path)
    k = FakeKiosk()
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, data_source="synthetic", reset_kiosk=False)
    b = [0.08, 0.45, 0.48, 0.62]  # dine-store
    c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    t = 0.0
    while t < 3.0:  # 처음 안내가 끝날 때까지 손은 버튼 밖
        t += 0.05
        e.on_hand(t, hand(0.5, 0.9))
        tk(e, k, t)
    for i in range(6):  # 0.3초 동안 목표 안 → 아직 PRESS 아님
        t += 0.05
        e.on_hand(t, hand(*c))
        tk(e, k, t)
    for i in range(60):  # 3초 동안 손 놓침(관측 없음)
        t += 0.05
        tk(e, k, t)
        assert e.press_safety(t)[0] is False
    recs = e.attempt["rec"].records
    assert "PRESS" not in guide_sequence(recs)
    assert any(r["kind"] == "hand_lost" for r in recs)
    assert "HAND_LOST" in guide_sequence(recs)
    # 다시 보이면: 바로 PRESS가 아니라 머묾을 다시 채운 뒤
    t += 0.05
    e.on_hand(t, hand(*c))
    e.tick(t)
    assert "PRESS" not in guide_sequence(recs)
    for i in range(16):
        t += 0.05
        e.on_hand(t, hand(*c))
        tk(e, k, t)
    assert "PRESS" in guide_sequence(recs)
    assert press_safety_violations(recs) == []
    assert any(r["kind"] == "hand_found" for r in recs)


def test_stale_observation_blocks_press(tmp_path):
    e = make_engine(tmp_path)
    k = FakeKiosk()
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, data_source="synthetic", reset_kiosk=False)
    t = 4.0
    for i in range(30):
        t += 0.05
        rep = hand(0.28, 0.53)
        rep["frame_age_ms"] = 900  # 오래된 프레임
        e.on_hand(t, rep)
        tk(e, k, t)
    assert "PRESS" not in guide_sequence(e.attempt["rec"].records)


def test_no_press_when_not_aligned(tmp_path):
    e = make_engine(tmp_path)
    k = FakeKiosk()
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, data_source="synthetic", reset_kiosk=False)
    t = 4.0
    for i in range(40):
        t += 0.05
        e.on_hand(t, hand(0.28, 0.53, aligned=False))
        tk(e, k, t)
    recs = e.attempt["rec"].records
    assert "PRESS" not in guide_sequence(recs)
    assert e.safety["reason"] == "not_aligned"
    assert any(r["kind"] == "marker" and r["aligned"] is False for r in recs)


def test_screen_change_discards_target(tmp_path):
    e = make_engine(tmp_path)
    k = FakeKiosk()
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, data_source="synthetic", reset_kiosk=False)
    e.tick(0.1)
    assert e.target["id"] == "dine-store"
    # 직원이 화면을 바꿈(누름 아님) → 즉시 목표 폐기·새 목표
    k.act("dine-store")
    e.on_kiosk(0.2, k.state())
    assert e.target["id"] == "item-americano"
    recs = e.attempt["rec"].records
    scr = [r for r in recs if r["kind"] == "screen"]
    assert scr[-1]["screen"] == "menu" and scr[-1]["cause"] in ("unknown", "operator")
    # 이전 화면 목표 위에 손이 있어도 PRESS 없음(새 목표 아님)
    t = 0.2
    for i in range(30):
        t += 0.05
        e.on_hand(t, hand(0.28, 0.53))
        tk(e, k, t)
    assert all(r.get("target_id") != "dine-store" for r in recs if r["kind"] == "guide" and r["code"] == "PRESS")
    assert press_safety_violations(recs) == []


def test_wrong_press_alert_and_revert(tmp_path):
    e = make_engine(tmp_path)
    k = FakeKiosk()
    k.act("dine-store")
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, data_source="synthetic", reset_kiosk=False)
    e.tick(0.1)
    assert e.target["id"] == "item-americano"
    t = 3.0
    touch = k.touch(0.5, 0.37)  # 카페라떼(잘못)
    e.on_kiosk(t, k.state(), [touch])
    assert e.target["id"] == "opt-cancel" and e.target["kind"] == "revert"
    recs = e.attempt["rec"].records
    pr = [r for r in recs if r["kind"] == "press"][-1]
    assert pr["result"] == "wrong" and pr["hit_id"] == "item-latte" and pr["next_screen"] == "menu+option"
    g = [r for r in recs if r["kind"] == "guide" and r["code"] == "PRESS_WRONG"]
    assert g and "돌아가요" in g[-1]["text"]
    touch = k.touch(0.39, 0.83)  # 취소
    e.on_kiosk(t + 2, k.state(), [touch])
    rv = [r for r in recs if r["kind"] == "revert"]
    assert rv and rv[-1]["reason"] == "wrong_press" and rv[-1]["to_screen"] == "menu"
    assert e.target["id"] == "item-americano"
    assert e.counts["wrong_presses"] == 1 and e.counts["reverts"] == 1


def test_payment_requires_hand_down(tmp_path):
    e = make_engine(tmp_path)
    k = FakeKiosk()
    for a in ("dine-store", "item-americano", "opt-temp-ICE", "opt-add"):
        k.act(a)
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, data_source="synthetic", reset_kiosk=False)
    t = 0.0
    for i in range(10):
        t += 0.05
        e.on_hand(t, hand(0.5, 0.92))
        tk(e, k, t)
    touch = k.touch(0.5, 0.92)  # 결제하기 → 확인 화면(금액)
    e.on_kiosk(t, k.state(), [touch])
    recs = e.attempt["rec"].records
    for i in range(90):  # 손이 계속 보임 → 안내·PRESS 없음(요청 말은 앞 안내 뒤에 나옴)
        t += 0.05
        e.on_hand(t, hand(0.72, 0.74))
        tk(e, k, t)
    req = [r for r in recs if r["kind"] == "hand_down_request"]
    assert req and req[0]["reason"] == "payment_check"
    assert e.safety["reason"] == "hand_down_check"
    after = recs[recs.index(req[0]):]
    assert "PRESS" not in guide_sequence(after) and "PAY_CHECK" not in guide_sequence(after)
    for i in range(20):  # 손을 내림
        t += 0.05
        e.on_hand(t, hand(None, None, tracked=False))
        tk(e, k, t)
    assert any(r["kind"] == "hand_down_done" for r in recs)
    seq = guide_sequence(recs)
    assert seq.index("HAND_DOWN") < seq.index("PAY_CHECK")
    assert "2,000원" in [r for r in recs if r["kind"] == "guide" and r["code"] == "PAY_CHECK"][0]["text"]


def test_payment_reading_not_interrupted_by_hand_absence(tmp_path):
    """11/12 실사용 피드백: 손을 내려 달라고 한 뒤 금액을 읽는 중에 손이 안 보이자 말을 끊고 손을 올려 달라고 했다.
    손 내림 요청 → (내리다 한 번 잠깐 다시 잡힘) → 손이 계속 안 보임 동안: HAND_LOST·끊기 없음, 금액 안내는 끝까지.
    다 읽은 뒤 손이 돌아오면 안내를 이어 간다."""
    e = make_engine(tmp_path)
    k = FakeKiosk()
    for a in ("dine-store", "item-americano", "opt-temp-ICE", "opt-add"):
        k.act(a)
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, data_source="synthetic", reset_kiosk=False)
    t = 0.0
    for _ in range(10):
        t += 0.05
        e.on_hand(t, hand(0.5, 0.92))
        tk(e, k, t)
    e.on_kiosk(t, k.state(), [k.touch(0.5, 0.92)])  # 결제하기 → 확인 화면(금액)
    recs = e.attempt["rec"].records
    for _ in range(60):  # 손이 보이는 동안 손 내림 요청
        t += 0.05
        e.on_hand(t, hand(0.72, 0.74))
        tk(e, k, t)
    assert e.gate and e.gate["phase"] == "waiting_down"
    n_items = e.speaker.n
    # 손을 내림: 처음 0.5초 안 보임 → 한 프레임 다시 잡힘(내리는 동작) → 그 뒤 25초 동안 계속 안 보임
    seq_hand = [False] * 10 + [True] + [False] * 500
    pay_at = None
    for vis in seq_hand:
        t += 0.05
        e.on_hand(t, hand(0.7, 0.98) if vis else hand(None, None, tracked=False))
        tk(e, k, t)
        if pay_at is None and any(r["kind"] == "guide" and r["code"] == "PAY_CHECK" for r in recs):
            pay_at = t
    new_items = e.speaker.after(n_items)
    codes = [i["code"] for i in new_items]
    assert "PAY_CHECK" in codes
    assert "HAND_LOST" not in codes, codes            # 손을 내린 것은 손 놓침이 아니다
    assert "CANCEL" not in codes, codes               # 금액 안내를 끊지 않는다
    assert not any(r["kind"] == "hand_lost" for r in recs[recs.index(next(r for r in recs if r["kind"] == "hand_down_request")):])
    assert e.gate and e.gate["phase"] == "raise"      # 아직 손이 안 돌아옴 → 기다림
    assert any(i["code"] == "INFO" and "올려" in i["text"] for i in new_items)  # 8초 뒤 한 번 더 부드럽게 요청
    assert e.safety["press_allowed"] is False
    for _ in range(20):  # 손이 돌아옴 → 게이트 해제, 안내 재개
        t += 0.05
        e.on_hand(t, hand(0.3, 0.6))
        tk(e, k, t)
    assert e.gate is None
    assert e.safety["reason"] != "hand_down_check"


def test_new_screen_unreadable_waits_then_asks(tmp_path):
    """새 화면에서 위치 맞춤이 낡았으면(마커가 손에 가려짐 등) 약 1초 기다린 뒤 손 내림 요청."""
    e = make_engine(tmp_path)
    k = FakeKiosk()
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, data_source="synthetic", reset_kiosk=False)
    e.on_hand(0.1, hand(0.28, 0.53))
    e.on_markers(0.15, 1, False, 2.5)  # 마커가 가려져 위치 맞춤이 낡음
    k.act("dine-store")
    e.on_kiosk(0.2, k.state())
    t = 0.2
    e.on_markers(t, 1, False, 3.0)
    for i in range(10):  # 0.5초: 아직 요청 안 함
        t += 0.05
        tk(e, k, t)
    recs = e.attempt["rec"].records
    assert not any(r["kind"] == "hand_down_request" for r in recs)
    for i in range(12):
        t += 0.05
        tk(e, k, t)
    req = [r for r in recs if r["kind"] == "hand_down_request"]
    assert req and req[0]["reason"] == "new_screen_unreadable" and req[0]["waited_ms"] >= 1000
    e.on_markers(t, 4, True, 0.0)
    e.tick(t + 0.05)
    assert any(r["kind"] == "hand_down_done" for r in recs)


def test_same_screen_occlusion_does_not_ask(tmp_path):
    e = make_engine(tmp_path)
    k = FakeKiosk()
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, data_source="synthetic", reset_kiosk=False)
    t = 0.0
    e.on_markers(t, 4, True, 0.0)
    for i in range(10):
        t += 0.05
        e.on_markers(t, 4, True, 0.0)
        tk(e, k, t)
    for i in range(40):  # 같은 화면에서 가려짐
        t += 0.05
        e.on_markers(t, 1, False, 2.5)
        tk(e, k, t)
    assert not any(r["kind"] == "hand_down_request" for r in e.attempt["rec"].records)
    assert e.target["id"] == "dine-store"  # 목표 유지


def test_hesitation_recorded(tmp_path):
    e = make_engine(tmp_path)
    k = FakeKiosk()
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, data_source="synthetic", reset_kiosk=False)
    t = 0.0
    for i in range(20):  # 포장 버튼 위 1초
        t += 0.05
        e.on_hand(t, hand(0.7, 0.53))
        tk(e, k, t)
    for i in range(4):
        t += 0.05
        e.on_hand(t, hand(0.5, 0.8))
        tk(e, k, t)
    h = [r for r in e.attempt["rec"].records if r["kind"] == "hesitation"]
    assert h and h[0]["region_id"] == "dine-takeout" and h[0]["on_target"] is False and h[0]["ended_by"] == "moved_away"


def test_guidance_off_records_without_speaking(tmp_path):
    e = make_engine(tmp_path)
    k = FakeKiosk()
    e.on_kiosk(0.0, k.state())
    e.start_attempt(0.0, conditions={"guidance": "off"}, data_source="synthetic", reset_kiosk=False)
    t = 0.0
    for i in range(30):
        t += 0.05
        e.on_hand(t, hand(0.28, 0.53))
        tk(e, k, t)
    recs = e.attempt["rec"].records
    assert guide_sequence(recs) == []
    assert any(r["kind"] == "finger" for r in recs)


def test_voice_commands_stop_repeat(tmp_path):
    e = make_engine(tmp_path)
    k = FakeKiosk()
    e.on_kiosk(0.0, k.state())
    e.on_voice(0.0, "start", via="button")
    assert e.attempt is not None
    e.tick(3.0)
    e.on_voice(3.1, "stop", via="speech")
    assert e.paused
    for i in range(20):
        e.on_hand(3.2 + i * 0.05, hand(0.28, 0.53))
    recs = e.attempt["rec"].records
    assert "PRESS" not in guide_sequence(recs)
    e.on_voice(5.0, "start", via="button")
    assert not e.paused
    e.on_voice(9.0, "repeat", via="button")
    vc = [r for r in recs if r["kind"] == "voice_cmd"]
    assert [v["command"] for v in vc] == ["start", "stop", "start", "repeat"]
    assert any("매장" in r["text"] for r in recs if r["kind"] == "guide" and r["code"] == "INFO" and r["ms"] >= 9000)
    assert all("transcript" not in r for r in recs)


def test_attempt_ids_and_outside_attempt_not_written(tmp_path):
    e = make_engine(tmp_path)
    k = FakeKiosk()
    e.on_kiosk(0.0, k.state())
    e.on_hand(0.1, hand(0.3, 0.5))
    assert list(tmp_path.iterdir()) == []
    aid = e.start_attempt(1.0, data_source="synthetic", reset_kiosk=False)
    assert len(aid) == len("20261112-230000-abcd") and aid.startswith("20261112-230000-")
    e.end_attempt(2.0, "aborted")
    lines = (tmp_path / f"{aid}.jsonl").read_text(encoding="utf-8").splitlines()
    assert '"attempt_end"' in lines[-1] and '"aborted"' in lines[-1]
