"""방향 안내(순수 로직). 03-software/guidance/engine.js 의 규칙을 파이썬으로 옮기고 다듬었다.

- 목표 영역 안쪽 여유(inset): 버튼 가장자리에서는 '들어왔다'고 보지 않는다.
- 한 번에 한 축만 안내(목표 크기 대비 오차가 큰 축). 축이 자주 바뀌지 않게 이력(hysteresis)을 둔다.
- 안쪽에 들어오면 '멈추세요'(HOLD), dwell_ms 머물면 '누르세요'(PRESS) 단계.
- 들어온 뒤에는 버튼 바깥 테두리를 벗어날 때까지 안에 있는 것으로 본다(가장자리 떨림 방지).
안전 조건(손 추적·위치 맞춤·화면 버전)은 이 모듈 밖(live.py)에서 검사한다.
값들은 조절 가능한 예비값이며 측정으로 정한 안전 기준이 아니다.
"""
from __future__ import annotations

DIR_TEXT = {
    "LEFT": "왼쪽으로", "RIGHT": "오른쪽으로", "UP": "위로", "DOWN": "아래로",
    "LEFT_SMALL": "왼쪽 조금", "RIGHT_SMALL": "오른쪽 조금", "UP_SMALL": "위로 조금", "DOWN_SMALL": "아래 조금",
}
DIR_VEC = {"LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1), "DOWN": (0, 1)}


def inside(p, b) -> bool:
    return p is not None and b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def inset_box(b, ratio):
    dx, dy = (b[2] - b[0]) * ratio, (b[3] - b[1]) * ratio
    return [b[0] + dx, b[1] + dy, b[2] - dx, b[3] - dy]


def direction_vector(code: str | None):
    if not code:
        return None
    base = code.replace("_SMALL", "")
    v = DIR_VEC.get(base)
    return list(v) if v else None


class DirectionGuide:
    def __init__(self, dwell_ms=650, inset=0.08, small_px=130, aspect=(1080, 1920), axis_keep=1.5):
        if not (100 <= dwell_ms <= 5000) or not (0 <= inset < 0.5):
            raise ValueError("설정 범위를 확인하세요")
        self.dwell_ms, self.inset, self.small_px, self.axis_keep = dwell_ms, inset, small_px, axis_keep
        self.aspect = aspect
        self.reset()

    def reset(self):
        self.entered = False
        self.since = None
        self.axis = None

    def update(self, p, bbox, now: float) -> dict:
        """p: 손끝(키오스크 정규 좌표), bbox: 목표 영역. now: 초.

        반환: {state: guiding|hold|press, code, err:[ex,ey], remaining_ms}
        """
        inner = inset_box(bbox, self.inset)
        if inside(p, inner) or (self.entered and inside(p, bbox)):
            if not self.entered:
                self.entered, self.since = True, now
            held = (now - self.since) * 1000
            if held >= self.dwell_ms:
                return {"state": "press", "code": "PRESS", "err": [0.0, 0.0], "remaining_ms": 0}
            return {"state": "hold", "code": "HOLD", "err": [0.0, 0.0], "remaining_ms": round(self.dwell_ms - held)}
        self.entered, self.since = False, None
        ex = inner[0] - p[0] if p[0] < inner[0] else (inner[2] - p[0] if p[0] > inner[2] else 0.0)
        ey = inner[1] - p[1] if p[1] < inner[1] else (inner[3] - p[1] if p[1] > inner[3] else 0.0)
        bw, bh = max(1e-6, bbox[2] - bbox[0]), max(1e-6, bbox[3] - bbox[1])
        rx, ry = abs(ex) / bw, abs(ey) / bh
        axis = "x" if rx >= ry else "y"
        # 이력: 지금 축에 아직 오차가 있고 다른 축이 훨씬 크지 않으면 축을 유지한다
        if self.axis == "x" and ex != 0 and ry < rx * self.axis_keep + 1e-9:
            axis = "x"
        elif self.axis == "y" and ey != 0 and rx < ry * self.axis_keep + 1e-9:
            axis = "y"
        if axis == "x" and ex == 0:
            axis = "y"
        if axis == "y" and ey == 0:
            axis = "x"
        self.axis = axis
        if axis == "x":
            base = "RIGHT" if ex > 0 else "LEFT"
            small = abs(ex) * self.aspect[0] < self.small_px
        else:
            base = "DOWN" if ey > 0 else "UP"
            small = abs(ey) * self.aspect[1] < self.small_px
        return {"state": "guiding", "code": base + ("_SMALL" if small else ""), "err": [round(ex, 4), round(ey, 4)], "remaining_ms": None}
