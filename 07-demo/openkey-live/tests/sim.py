"""시험 도구: 가짜 키오스크(엔진 단위 시험용)와 '안내만 듣고 움직이는' 합성 사용자.

합성 사용자는 목표 버튼 좌표를 모른다. 휴대폰이 받는 말하기 큐의 안내 코드만 듣고 손끝을 움직인다.
실제 사람의 손 움직임을 흉내 낸 모델이 아니다(속도·반응 지연은 임의 값).
"""
from __future__ import annotations

import math
import random

DIRS = {"LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1), "DOWN": (0, 1)}


class SimUser:
    def __init__(self, start=(0.5, 0.75), speed=0.30, small_speed=0.07, react_s=0.15, seed=1, jitter=0.0015, aspect=1080 / 1920):
        self.p = list(start)
        self.vel = (0.0, 0.0)
        self.speed, self.small_speed, self.react_s = speed, small_speed, react_s
        self.aspect = aspect
        self.rng = random.Random(seed)
        self.jitter = jitter
        self.want_press = False
        self.hand_down_until = None
        self.hand_up = True
        self.queue = []  # (적용 시각, 코드)
        self.heard = []
        self.wrong_press_plan = None  # {"on_code": "SCREEN", "point": (x,y)} 등 시험용
        self.hide_until = None

    def hear(self, now, item):
        if item["code"] == "CANCEL":
            return
        self.heard.append((round(now, 2), item["code"], item["text"]))
        self.queue.append((now + self.react_s, item["code"]))

    def update(self, now, dt):
        due = [c for t, c in self.queue if t <= now]
        self.queue = [(t, c) for t, c in self.queue if t > now]
        for code in due:
            base = code.replace("_SMALL", "")
            if base in DIRS:
                sp = self.small_speed if code.endswith("_SMALL") else self.speed
                dx, dy = DIRS[base]
                # 화면 세로가 더 길어서 같은 '속도'라도 정규 좌표 기준 x를 크게 움직인다
                self.vel = (dx * sp / (self.aspect * 1.6) if dx else 0.0, dy * sp * 0.6 if dy else 0.0)
            elif code == "HOLD":
                self.vel = (0.0, 0.0)
            elif code == "PRESS":
                self.vel = (0.0, 0.0)
                self.want_press = True
            elif code == "HAND_DOWN":
                self.vel = (0.0, 0.0)
                self.hand_up = False
                self.hand_down_until = now + 1.2
            elif code in ("SCREEN", "PRESS_OK", "PRESS_WRONG", "PAY_CHECK", "INFO"):
                self.vel = (0.0, 0.0)
        if self.hand_down_until is not None and now >= self.hand_down_until:
            self.hand_down_until = None
            self.hand_up = True
        self.p[0] += self.vel[0] * dt + self.rng.uniform(-self.jitter, self.jitter)
        self.p[1] += self.vel[1] * dt + self.rng.uniform(-self.jitter, self.jitter)
        self.p[0] = min(1.05, max(-0.05, self.p[0]))
        self.p[1] = min(1.05, max(-0.05, self.p[1]))

    def visible(self, now):
        if self.hide_until is not None and now < self.hide_until:
            return False
        return self.hand_up

    def take_press(self):
        if self.want_press:
            self.want_press = False
            return True
        return False


# ---------------------------------------------------------------------------- 가짜 키오스크(엔진 단위 시험용)
SCREENS = {
    "start": [("dine-store", "매장", [0.08, 0.45, 0.48, 0.62]), ("dine-takeout", "포장", [0.52, 0.45, 0.92, 0.62]),
              ("practice", "연습하기", [0.35, 0.85, 0.65, 0.9])],
    "menu": [("home", "처음으로", [0.02, 0.01, 0.2, 0.05]), ("cat-all", "전체 메뉴", [0.02, 0.07, 0.2, 0.11]),
             ("cat-coffee", "커피", [0.21, 0.07, 0.39, 0.11]),
             ("item-americano", "아메리카노 2,000원", [0.03, 0.30, 0.33, 0.45]), ("item-latte", "카페라떼 3,200원", [0.35, 0.30, 0.65, 0.45]),
             ("item-vanilla", "바닐라라떼 3,700원", [0.67, 0.30, 0.97, 0.45]), ("item-coldbrew", "콜드브루 3,500원", [0.67, 0.47, 0.97, 0.62]),
             ("clear", "전체삭제", [0.7, 0.75, 0.95, 0.79]), ("checkout", "결제하기", [0.05, 0.88, 0.95, 0.97])],
    "menu+option": [("opt-temp-ICE", "ICE", [0.52, 0.30, 0.72, 0.36]), ("opt-temp-HOT", "HOT", [0.75, 0.30, 0.95, 0.36]),
                    ("opt-size-R", "레귤러", [0.52, 0.40, 0.72, 0.46]), ("opt-size-L", "라지 +500", [0.75, 0.40, 0.95, 0.46]),
                    ("draft-minus", "−", [0.05, 0.8, 0.1, 0.84]), ("draft-plus", "+", [0.18, 0.8, 0.23, 0.84]),
                    ("opt-cancel", "취소", [0.3, 0.8, 0.48, 0.86]), ("opt-add", "담기", [0.52, 0.8, 0.95, 0.86])],
    "menu+confirm": [("cf-back", "이전", [0.1, 0.7, 0.45, 0.78]), ("cf-pay", "결제하기", [0.55, 0.7, 0.9, 0.78])],
    "pay": [("home", "처음으로", [0.02, 0.01, 0.2, 0.05]), ("pay-card", "신용·체크카드", [0.1, 0.4, 0.45, 0.6]),
            ("pay-simple", "간편결제", [0.55, 0.4, 0.9, 0.6]), ("pay-back", "이전", [0.35, 0.85, 0.65, 0.9])],
    "card": [("card-cancel", "결제 취소", [0.35, 0.85, 0.65, 0.9])],
    "done": [("receipt-yes", "출력", [0.1, 0.8, 0.45, 0.86]), ("receipt-no", "출력 안 함", [0.55, 0.8, 0.9, 0.86])],
    "practice_lr": [("home", "처음으로", [0.02, 0.01, 0.2, 0.05])],
}
PRICES = {"americano": 2000, "latte": 3200, "vanilla": 3700, "coldbrew": 3500}


class FakeKiosk:
    def __init__(self, layout="B"):
        self.layout = layout
        self.screen, self.modal = "start", None
        self.cart, self.draft, self.dine = [], None, None
        self.version = 1
        self.order_no = 27
        self.log = []

    def sid(self):
        return self.screen + ("+" + self.modal if self.modal else "")

    def regions(self):
        sid = self.sid()
        out = []
        if self.modal:
            for rid, lab, b in SCREENS["menu"]:
                out.append({"id": rid, "label": lab, "bbox": b, "hit": True, "enabled": True, "dimmed": True, "category": "button"})
        for rid, lab, b in SCREENS.get(sid, []):
            en = not (rid == "checkout" and not self.cart)
            out.append({"id": rid, "label": lab, "bbox": b, "hit": True, "enabled": en, "dimmed": False, "category": "button"})
        return out

    def state(self):
        total = sum(PRICES[i["menu"]] * i["qty"] for i in self.cart)
        return {"screen": self.sid(), "screenVersion": self.version, "layout": self.layout, "regions": self.regions(),
                "order": {"dine": self.dine, "cart": [dict(i) for i in self.cart], "draft": dict(self.draft) if self.draft else None,
                          "cartTotal": total, "orderNo": self.order_no, "category": "all", "page": 0}}

    def hit(self, x, y):
        best, area = None, 9
        for r in self.regions():
            if r["dimmed"]:
                continue
            b = r["bbox"]
            if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
                a = (b[2] - b[0]) * (b[3] - b[1])
                if a < area:
                    best, area = r, a
        return best

    def touch(self, x, y, source="direct"):
        r = self.hit(x, y)
        t = {"x": x, "y": y, "id": r["id"] if r else None, "screen": self.sid(), "screenVersion": self.version, "source": source}
        self.log.append(t)
        if r and r["enabled"]:
            self.act(r["id"])
        return t

    def go(self, screen, modal=None):
        self.screen, self.modal = screen, modal
        self.version += 1

    def act(self, rid):
        if rid.startswith("dine-"):
            self.dine = "매장" if rid == "dine-store" else "포장"
            self.go("menu")
        elif rid.startswith("item-"):
            m = rid[5:]
            self.draft = {"menu": m, "temp": "ICE" if m == "coldbrew" else None, "size": "R", "shot": 0, "qty": 1}
            self.go("menu", "option")
        elif rid.startswith("opt-temp-"):
            self.draft["temp"] = rid[9:]
            self.version += 1
        elif rid == "opt-add":
            if self.draft["temp"] is None:
                self.version += 1
                return
            self.cart.append(self.draft)
            self.draft = None
            self.go("menu")
        elif rid == "opt-cancel":
            self.draft = None
            self.go("menu")
        elif rid == "checkout":
            self.go("menu", "confirm")
        elif rid == "cf-back":
            self.go("menu")
        elif rid == "cf-pay":
            self.go("pay")
        elif rid == "pay-simple":
            self.go("done")
        elif rid == "pay-card":
            self.go("card")
        elif rid in ("card-cancel", "pay-back"):
            self.go("menu", "confirm")
        elif rid == "clear":
            self.cart = []
            self.version += 1
        elif rid == "home":
            self.cart, self.draft = [], None
            self.go("start")
        elif rid == "practice":
            self.go("practice_lr")


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])
