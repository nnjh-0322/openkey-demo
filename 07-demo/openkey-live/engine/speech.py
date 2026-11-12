"""말하기 관리(순수 로직).

- 문구는 짧게. 같은 코드·같은 문구를 repeat_gap 안에 다시 내지 않는다(억제).
- 우선순위: 0 안전(손 놓침·잘못 누름) > 1 누름 결과·손 내림 요청 > 2 화면·금액·완료·기타 안내 > 3 멈추세요·누르세요 > 4 방향.
- 말하는 중(예상 길이)에는 더 중요한 말만 끊고 들어간다. 방향은 기다리지 않고 버린다(곧 다시 계산됨).
  같은 우선순위의 다른 방향·다른 3순위 말은 끊고 들어간다(낡은 방향을 끝까지 듣지 않게).
- 0~2순위끼리는 줄을 세운다(예: '맞게 눌렀어요' 다음 '옵션 화면입니다').
- 휴대폰은 받은 순서대로 말하되 interrupt=true면 지금 말을 끊고, ttl이 지난 말은 버린다.
"""
from __future__ import annotations

from collections import deque

PRIO = {"HAND_LOST": 0, "PRESS_WRONG": 0, "PRESS_OK": 1, "HAND_DOWN": 1, "SCREEN": 2, "PAY_CHECK": 2, "DONE": 2, "INFO": 2,
        "PRESS": 3, "HOLD": 3}
DIRECTION_PRIO = 4
REPEAT_GAP = {"PRESS": 4.0, "HOLD": 3.0, "HAND_LOST": 4.0, "HAND_DOWN": 5.0}
DEFAULT_GAP = 2.5
DIRECTION_GAP = 3.0
TTL = {4: 1.5, 3: 2.5}
DEFAULT_TTL = 8.0


def prio_of(code: str) -> int:
    return PRIO.get(code, DIRECTION_PRIO)


def estimate_s(text: str) -> float:
    """한국어 음성 길이 추정(rate 1.1 기준 대략값). 실제 기기 음성 속도는 측정하지 않았다."""
    n = sum(1 for c in text if not c.isspace())
    return 0.3 + 0.10 * n  # rate 1.3 기준 대략값


class Speaker:
    def __init__(self, on_emit=None, max_items=80):
        self.items = deque(maxlen=max_items)
        self.n = 0
        self.cur = None
        self.busy_until = 0.0
        self.pending = deque()
        self.last = None
        self.on_emit = on_emit

    def busy(self, now) -> bool:
        return self.cur is not None and now < self.busy_until

    def offer(self, code: str, text: str, now: float, prio: int | None = None, target_id=None, gap: float | None = None,
              force=False) -> tuple[str, dict | None]:
        """반환: ('emitted', item) | ('suppressed', None) | ('dropped', None) | ('queued', None)"""
        p = prio_of(code) if prio is None else prio
        if gap is None:
            gap = DIRECTION_GAP if p == DIRECTION_PRIO else REPEAT_GAP.get(code, DEFAULT_GAP)
        if not force and self.last and self.last["code"] == code and self.last["text"] == text and now - self.last["t"] < gap:
            return "suppressed", None
        if not force and any(q["code"] == code and q["text"] == text for q in self.pending):
            return "suppressed", None
        if self.busy(now):
            c = self.cur
            if p < c["prio"] or (p == c["prio"] and p >= 3 and code != c["code"]):
                return "emitted", self._emit(code, text, now, p, target_id, interrupt=True)
            if p >= 3:
                return "dropped", None
            self.pending.append({"code": code, "text": text, "prio": p, "target_id": target_id, "t": now})
            return "queued", None
        return "emitted", self._emit(code, text, now, p, target_id, interrupt=False)

    def _emit(self, code, text, now, p, target_id, interrupt):
        self.n += 1
        it = {"n": self.n, "code": code, "text": text, "prio": p, "interrupt": interrupt, "t": now,
              "ttl_s": TTL.get(p, DEFAULT_TTL), "target_id": target_id, "est_s": round(estimate_s(text), 2)}
        self.items.append(it)
        self.cur, self.busy_until, self.last = it, now + it["est_s"], it
        if self.on_emit:
            self.on_emit(it)
        return it

    def flush(self, now: float):
        """말이 끝났으면 대기 중인 말을 낸다(8초 넘게 기다린 말은 버린다)."""
        out = []
        while self.pending and not self.busy(now):
            q = self.pending.popleft()
            if now - q["t"] > 8.0:
                continue
            out.append(self._emit(q["code"], q["text"], now, q["prio"], q["target_id"], interrupt=False))
        return out

    def drop_pending(self, code):
        self.pending = deque(q for q in self.pending if q["code"] != code)

    def clear_pending(self):
        """화면이 바뀌면 이전 화면의 대기 말은 낡은 것이므로 버린다."""
        self.pending.clear()

    def cancel(self, now: float, reason=""):
        """지금 말과 대기 말을 모두 끊는다(휴대폰에 CANCEL 전달). guide 기록은 남기지 않는다."""
        self.pending.clear()
        self.n += 1
        it = {"n": self.n, "code": "CANCEL", "text": "", "prio": 0, "interrupt": True, "t": now, "ttl_s": 2.0,
              "target_id": None, "est_s": 0, "reason": reason}
        self.items.append(it)
        self.cur, self.busy_until = None, now
        return it

    def after(self, n: int) -> list:
        return [i for i in self.items if i["n"] > n]
