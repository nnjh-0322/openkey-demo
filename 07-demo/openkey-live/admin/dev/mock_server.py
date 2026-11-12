"""OpenKey 관리자 콘솔 개발용 모의 서버 (예시 데이터 전용).

SCHEMA.md 5절의 실시간 API 계약을 흉내 낸다. 실제 안내 엔진·카메라·손 인식은 없다.
- 모든 값은 합성이며 `data_source: "synthetic"`을 준다.
- 기록은 메모리에만 두고 디스크에 쓰지 않는다. 영상도 합성 그림이다.
- 캡처·시험용으로 `POST /dev/scenario {"name": ...}`로 상태를 고정할 수 있다(계약 밖, 모의 서버 전용).

실행: .\\.venv\\Scripts\\python.exe 07-demo/openkey-live/admin/dev/mock_server.py --port 8470
열기: http://localhost:8470/admin/
"""
import argparse
import csv
import io
import json
import math
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ADMIN = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
KW, KH = 540, 960  # 키오스크 그림 크기(논리 1080x1920의 절반, 세로 9:16)
CAM_W, CAM_H = 1280, 720

STEP_NAMES = [("menu", "메뉴 고르기"), ("option", "옵션"), ("confirm", "확인"), ("pay", "결제"), ("done", "주문 번호")]
SCREEN_KO = {"menu": "메뉴", "option": "옵션", "confirm": "주문 확인", "pay": "결제", "done": "주문 번호"}

GOALS = {
    "iced-americano-1": {"label": "아이스 아메리카노 한 잔", "menu": "menu-americano", "temp": "temp-ice", "name": "아메리카노", "price": 4500},
    "hot-latte-1": {"label": "따뜻한 카페라테 한 잔", "menu": "menu-latte", "temp": "temp-hot", "name": "카페라테", "price": 5000},
    "iced-vanilla-1": {"label": "아이스 바닐라라테 한 잔", "menu": "menu-vanilla", "temp": "temp-ice", "name": "바닐라라테", "price": 5500},
}
MENU = [("menu-americano", "아메리카노", 4500), ("menu-latte", "카페라테", 5000), ("menu-vanilla", "바닐라라테", 5500),
        ("menu-cappuccino", "카푸치노", 5000), ("menu-greentea", "녹차라테", 5500), ("menu-lemonade", "레몬에이드", 5000)]
MENU_ORDER = {"A": [0, 1, 2, 3, 4, 5], "B": [1, 3, 4, 2, 5, 0]}


def won(n):
    return f"{n:,}원"


def regions_for(screen, layout, goal_id):
    """화면별 버튼 영역(키오스크 정규 좌표 [l, t, r, b])."""
    g = GOALS[goal_id]
    R = []
    if screen == "menu":
        for i, (cid, lab) in enumerate([("cat-coffee", "커피"), ("cat-drink", "음료"), ("cat-dessert", "디저트")]):
            R.append({"id": cid, "label": lab, "bbox": [0.03, 0.12 + i * 0.08, 0.23, 0.18 + i * 0.08], "hit": True, "enabled": True})
        for slot, mi in enumerate(MENU_ORDER[layout]):
            mid, name, price = MENU[mi]
            c, r = slot % 2, slot // 2
            l, t = 0.27 + c * 0.36, 0.12 + r * 0.22
            R.append({"id": mid, "label": name, "bbox": [round(l, 3), round(t, 3), round(l + 0.33, 3), round(t + 0.2, 3)], "hit": True, "enabled": True, "price": price})
        R.append({"id": "cart-clear", "label": "전체 삭제", "bbox": [0.05, 0.86, 0.38, 0.94], "hit": True, "enabled": True})
        R.append({"id": "cart-pay", "label": "결제하기", "bbox": [0.55, 0.86, 0.95, 0.94], "hit": True, "enabled": False})
    elif screen == "option":
        hot, ice = [0.1, 0.36, 0.47, 0.5], [0.53, 0.36, 0.9, 0.5]
        if layout == "B":
            hot, ice = ice, hot
        R.append({"id": "temp-hot", "label": "HOT", "bbox": hot, "hit": True, "enabled": True})
        R.append({"id": "temp-ice", "label": "ICE", "bbox": ice, "hit": True, "enabled": True})
        R.append({"id": "size-regular", "label": "레귤러", "bbox": [0.1, 0.56, 0.47, 0.64], "hit": True, "enabled": True})
        R.append({"id": "size-large", "label": "라지 +500원", "bbox": [0.53, 0.56, 0.9, 0.64], "hit": True, "enabled": True})
        R.append({"id": "option-cancel", "label": "취소", "bbox": [0.1, 0.74, 0.4, 0.82], "hit": True, "enabled": True})
        R.append({"id": "option-add", "label": "담기", "bbox": [0.45, 0.74, 0.9, 0.82], "hit": True, "enabled": True})
    elif screen == "confirm":
        R.append({"id": "confirm-back", "label": "이전", "bbox": [0.06, 0.82, 0.4, 0.92], "hit": True, "enabled": True})
        R.append({"id": "confirm-pay", "label": "결제하기", "bbox": [0.45, 0.82, 0.94, 0.92], "hit": True, "enabled": True})
    elif screen == "pay":
        R.append({"id": "pay-card", "label": "카드 결제", "bbox": [0.1, 0.42, 0.9, 0.54], "hit": True, "enabled": True})
        R.append({"id": "pay-easy", "label": "간편 결제", "bbox": [0.1, 0.58, 0.9, 0.7], "hit": True, "enabled": True})
        R.append({"id": "pay-cancel", "label": "취소", "bbox": [0.1, 0.8, 0.9, 0.88], "hit": True, "enabled": True})
    elif screen == "done":
        R.append({"id": "done-home", "label": "처음으로", "bbox": [0.25, 0.8, 0.75, 0.88], "hit": True, "enabled": True})
    return R


def step_targets(step_idx, goal_id):
    g = GOALS[goal_id]
    return [[g["menu"]], [g["temp"], "option-add"], ["confirm-pay"], ["pay-card"], []][step_idx]


# ---------------------------------------------------------------- 그림
_font_cache = {}


def font(size):
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype(FONT_PATH, size)
        except OSError:
            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def px(b):
    return [b[0] * KW, b[1] * KH, b[2] * KW, b[3] * KH]


def center_text(d, box, text, size, fill):
    f = font(size)
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    d.text(((box[0] + box[2] - (r - l)) / 2, (box[1] + box[3] - (b - t)) / 2 - t), text, font=f, fill=fill)


_kiosk_cache = {}


def render_kiosk(screen, layout, goal_id, order_no):
    key = (screen, layout, goal_id, order_no)
    if key in _kiosk_cache:
        return _kiosk_cache[key]
    g = GOALS[goal_id]
    im = Image.new("RGB", (KW, KH), (243, 244, 246))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, KW, 0.09 * KH], fill=(255, 255, 255))
    d.text((18, 24), "MORU 카페", font=font(26), fill=(40, 40, 40))
    d.text((KW - 150, 30), f"배치 {layout}", font=font(18), fill=(120, 120, 120))
    regs = regions_for(screen, layout, goal_id)
    if screen == "option":
        d.rectangle([0.05 * KW, 0.2 * KH, 0.95 * KW, 0.88 * KH], fill=(255, 255, 255))
        center_text(d, [0, 0.22 * KH, KW, 0.3 * KH], g["name"], 30, (30, 30, 30))
    if screen == "confirm":
        d.rectangle([0.06 * KW, 0.14 * KH, 0.94 * KW, 0.7 * KH], fill=(255, 255, 255))
        d.text((0.1 * KW, 0.17 * KH), "주문 내역", font=font(24), fill=(30, 30, 30))
        temp = "ICE" if g["temp"] == "temp-ice" else "HOT"
        d.text((0.1 * KW, 0.26 * KH), f"{g['name']} ({temp}) 1잔", font=font(22), fill=(50, 50, 50))
        d.text((0.66 * KW, 0.26 * KH), won(g["price"]), font=font(22), fill=(50, 50, 50))
        d.text((0.1 * KW, 0.6 * KH), "합계", font=font(24), fill=(30, 30, 30))
        d.text((0.62 * KW, 0.6 * KH), won(g["price"]), font=font(26), fill=(25, 90, 200))
    if screen == "pay":
        center_text(d, [0, 0.16 * KH, KW, 0.24 * KH], "결제 금액", 24, (60, 60, 60))
        center_text(d, [0, 0.25 * KH, KW, 0.34 * KH], won(g["price"]), 40, (25, 90, 200))
    if screen == "done":
        center_text(d, [0, 0.2 * KH, KW, 0.28 * KH], "주문이 완료되었습니다", 28, (40, 40, 40))
        center_text(d, [0, 0.34 * KH, KW, 0.4 * KH], "주문 번호", 24, (90, 90, 90))
        center_text(d, [0, 0.42 * KH, KW, 0.6 * KH], str(order_no or ""), 96, (25, 90, 200))
    for r in regs:
        b = px(r["bbox"])
        if r["id"].startswith("menu-"):
            d.rounded_rectangle(b, 14, fill=(255, 255, 255))
            d.rounded_rectangle([b[0] + 40, b[1] + 16, b[2] - 40, b[1] + 0.11 * KH], 10, fill=(214, 196, 170))
            center_text(d, [b[0], b[1] + 0.12 * KH, b[2], b[1] + 0.155 * KH], r["label"], 20, (30, 30, 30))
            center_text(d, [b[0], b[1] + 0.155 * KH, b[2], b[3] - 4], won(r["price"]), 18, (90, 90, 90))
        elif r["id"].startswith("cat-"):
            sel = r["id"] == "cat-coffee"
            d.rounded_rectangle(b, 12, fill=(255, 255, 255) if sel else (232, 234, 238))
            center_text(d, b, r["label"], 20, (30, 30, 30))
        else:
            primary = r["id"] in ("cart-pay", "option-add", "confirm-pay", "pay-card")
            fill = (40, 110, 220) if primary else (228, 230, 234)
            if not r["enabled"]:
                fill = (200, 205, 214)
            d.rounded_rectangle(b, 14, fill=fill)
            center_text(d, b, r["label"], 22, (255, 255, 255) if primary else (40, 40, 40))
    arr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    _kiosk_cache[key] = arr
    return arr


ARUCO = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
KIOSK_QUAD = np.float32([[478, 70], [796, 84], [812, 650], [462, 640]])  # 카메라 속 키오스크 네 모서리
MARKER_POS = {0: (400, 40), 1: (840, 50), 2: (850, 610), 3: (396, 600)}
MARKER_PX = 46
_bg = None


def background():
    global _bg
    if _bg is None:
        y = np.linspace(0, 1, CAM_H)[:, None]
        base = np.zeros((CAM_H, CAM_W, 3), np.float32)
        base[:] = (88, 98, 108)
        base *= (0.85 + 0.25 * y)[..., None]
        rng = np.random.default_rng(3)
        base += rng.normal(0, 4, base.shape)
        img = np.clip(base, 0, 255).astype(np.uint8)
        cv2.fillConvexPoly(img, np.int32([[330, 20], [950, 30], [968, 690], [318, 682]]), (34, 34, 38))  # 노트북 화면 테두리
        _bg = img
    return _bg.copy()


def homography():
    dst = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])
    return cv2.getPerspectiveTransform(KIOSK_QUAD, dst)


def render_frame(sim_view):
    img = background()
    k = render_kiosk(sim_view["screen"], sim_view["layout"], sim_view["goal_id"], sim_view["order_no"])
    M = cv2.getPerspectiveTransform(np.float32([[0, 0], [KW, 0], [KW, KH], [0, KH]]), KIOSK_QUAD)
    warped = cv2.warpPerspective(k, M, (CAM_W, CAM_H))
    mask = cv2.warpPerspective(np.full((KH, KW), 255, np.uint8), M, (CAM_W, CAM_H))
    img[mask > 0] = (warped[mask > 0] * 0.92 + 10).astype(np.uint8)
    markers = []
    for mid in sim_view["marker_ids"]:
        x, y = MARKER_POS[mid]
        m = cv2.aruco.generateImageMarker(ARUCO, mid, MARKER_PX)
        img[y - 6:y + MARKER_PX + 6, x - 6:x + MARKER_PX + 6] = 255
        img[y:y + MARKER_PX, x:x + MARKER_PX] = m[..., None]
        markers.append({"id": mid, "corners": [[x, y], [x + MARKER_PX, y], [x + MARKER_PX, y + MARKER_PX], [x, y + MARKER_PX]]})
    f = sim_view["finger"]
    if f and f.get("tracked"):
        Hi = np.linalg.inv(homography())
        p = Hi @ np.array([f["x"], f["y"], 1.0])
        tx, ty = p[0] / p[2], p[1] / p[2]
        skin = (138, 168, 214)
        cv2.line(img, (int(tx), int(ty)), (int(tx + 70), CAM_H + 40), skin, 34, cv2.LINE_AA)
        cv2.circle(img, (int(tx), int(ty)), 17, skin, -1, cv2.LINE_AA)
        cv2.ellipse(img, (int(tx + 110), CAM_H + 20), (120, 90), -20, 0, 360, skin, -1, cv2.LINE_AA)
    cv2.putText(img, "SYNTHETIC SAMPLE FRAME (mock server)", (16, CAM_H - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return jpg.tobytes(), markers


# ---------------------------------------------------------------- 상황 흉내
GUIDE_TEXT = {
    "LEFT": "왼쪽으로", "RIGHT": "오른쪽으로", "UP": "위로", "DOWN": "아래로",
    "LEFT_SMALL": "왼쪽으로 조금", "RIGHT_SMALL": "오른쪽으로 조금", "UP_SMALL": "위로 조금", "DOWN_SMALL": "아래로 조금",
    "HOLD": "멈추세요", "PRESS": "누르세요", "PRESS_OK": "맞게 눌렀어요", "PRESS_WRONG": "다른 버튼이 눌렸어요. 이전으로 돌아갈게요",
    "HAND_LOST": "손이 보이지 않아요", "HAND_DOWN": "손을 잠시 내려 주세요. 결제 금액을 확인할게요",
}
DIRS = {"LEFT": [-1, 0], "RIGHT": [1, 0], "UP": [0, -1], "DOWN": [0, 1]}


class Sim:
    def __init__(self, speed=1.0, seed=7):
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.speed = speed
        self.rng = random.Random(seed)
        self.vt = 0.0
        self.wall0 = time.time()
        self.scenario = "live"
        self.frozen = False
        self.layout = "A"
        self.goal_id = "iced-americano-1"
        self.attempt = None
        self.history = []  # 끝난 시도(기록 포함)
        self.paused = False
        self.frame_mode = "camera"  # camera | none(404) | off(카메라 꺼짐)
        self.marker_ids = [0, 1, 2, 3]
        self.attempt_no = 0
        self.frame_seq = 0
        self.frame_at = 0.0
        self.frame_cache = None
        self.reset_idle()

    # --- 시간
    def iso(self):
        return datetime.fromtimestamp(self.wall0 + self.vt, KST).isoformat(timespec="milliseconds")

    def ams(self):
        return int((self.vt - self.attempt["vt0"]) * 1000) if self.attempt else None

    # --- 상태 초기화
    def reset_idle(self):
        self.screen, self.screen_version = "menu", getattr(self, "screen_version", 0) + 1
        self.step_idx, self.sub = 0, 0
        self.finger = {"tracked": False, "x": None, "y": None, "over": None, "seen_vt": None}
        self.guide = None
        self.last_guide_vt = -99
        self.counts = dict(presses=0, wrong_presses=0, reverts=0, hesitations=0, hand_lost=0, hand_down_requests=0, guides=0)
        self.last_press = None
        self.target = None
        self.order_no = None
        self.phase = None  # None | ("hand_lost", until) | ("hand_down", until) | ("wrong", until) | ("screen_wait", until)
        self.hold_vt = None
        self.over_vt = None
        self.over_id = None
        self.hes_done = False
        self.wrong_done = False
        self.lost_done = False
        self.track_win = []
        self.next_finger_vt = 0
        self.next_perf_vt = 0
        self.step_vt0 = self.vt
        self.step_stats = dict(presses=0, wrong_presses=0, hesitations=0, guides=0)
        self.status = dict(camera=True, markers=4, aligned=True, align_age_s=0.1, hand_rate=None, model_ms=23, frame_age_ms=85, fps=12, cam_w=CAM_W, cam_h=CAM_H)

    # --- 기록
    def rec(self, kind, **kw):
        if not self.attempt:
            return
        a = self.attempt
        a["seq"] += 1
        r = {"v": 1, "attempt": a["id"], "seq": a["seq"], "t": self.iso(), "ms": self.ams(), "kind": kind}
        r.update(kw)
        a["records"].append(r)
        with self.cond:
            self.cond.notify_all()
        return r

    def say(self, code, text=None, target_id=None):
        text = text or GUIDE_TEXT.get(code, code)
        same = self.guide and self.guide["code"] == code and self.vt - self.last_guide_vt < 2.0
        if self.paused:
            return
        self.rec("guide", code=code, text=text, target_id=target_id, channel="phone", suppressed=bool(same))
        if same:
            return
        base = code.replace("_SMALL", "")
        self.guide = {"code": code, "text": text, "ms": self.ams() if self.attempt else 0, "direction": DIRS.get(base)}
        self.last_guide_vt = self.vt
        self.counts["guides"] += 1
        self.step_stats["guides"] += 1

    # --- 시도
    def start(self, conditions, goal_id, data_source):
        if self.attempt:
            raise ValueError("이미 진행 중인 시도가 있습니다")
        if goal_id:
            if goal_id not in GOALS:
                raise ValueError("알 수 없는 목표입니다")
            self.goal_id = goal_id
        cond = {"layout": "A", "guidance": "on", "blindfold": "unknown", "lighting_note": "", "participant_code": "", "operator_note": ""}
        cond.update({k: v for k, v in (conditions or {}).items() if k in cond})
        self.layout = cond["layout"] if cond["layout"] in ("A", "B") else "A"
        self.attempt_no += 1
        ts = datetime.fromtimestamp(self.wall0 + self.vt, KST)
        aid = ts.strftime("%Y%m%d-%H%M%S-") + "%04x" % self.rng.randrange(65536)
        self.reset_idle()
        self.attempt = {"id": aid, "started": self.iso(), "vt0": self.vt, "seq": 0, "records": [], "data_source": data_source or "synthetic",
                        "conditions": cond, "goal_id": self.goal_id}
        g = GOALS[self.goal_id]
        self.rec("attempt_start", data_source=self.attempt["data_source"], button_source="kiosk_ground_truth", conditions=cond,
                 goal={"id": self.goal_id, "label": g["label"], "steps": [{"step": i + 1, "screen": n, "target_label": None, "required": True} for i, (n, _) in enumerate(STEP_NAMES)]},
                 device={"cam_w": CAM_W, "cam_h": CAM_H, "phone_ua_short": "mock", "audio_out": "unknown"},
                 settings={"dwell_ms": 800, "zoom": True, "det_threshold": 0.5, "sample_hz": 5})
        self.rec("screen", screen="menu", screen_version=self.screen_version, **{"from": None}, cause="unknown")
        self.finger.update(tracked=False, x=0.55, y=1.08)
        self.phase = ("enter", self.vt + 0.8)
        self.say("SCREEN", f"메뉴 화면입니다. {g['label']}을 찾아 볼게요")
        self.plan()
        return aid

    def end(self, reason):
        if not self.attempt:
            raise ValueError("진행 중인 시도가 없습니다")
        a = self.attempt
        completed = self.screen == "done"
        reason = reason if reason in ("done", "aborted", "timeout", "error") else "aborted"
        self.rec("attempt_end", completed=completed, end_reason=reason, order_no=self.order_no, total_ms=self.ams(), counts=dict(self.counts))
        a["ended"] = self.iso()
        a["completed"], a["end_reason"], a["total_ms"], a["order_no"] = completed, reason, self.ams(), self.order_no
        self.history.append(a)
        self.attempt = None
        self.reset_idle()
        return a["id"]

    def regions(self):
        return regions_for(self.screen, self.layout, self.goal_id)

    def region(self, rid):
        return next((r for r in self.regions() if r["id"] == rid), None)

    def plan(self, reason="plan"):
        t = step_targets(self.step_idx, self.goal_id)
        if self.sub < len(t):
            r = self.region(t[self.sub])
            self.target = {"id": r["id"], "label": r["label"], "bbox": r["bbox"], "screen_version": self.screen_version}
            self.rec("target", step=self.step_idx + 1, screen=self.screen, screen_version=self.screen_version, target_id=r["id"], label=r["label"], bbox=r["bbox"], reason=reason)
        else:
            if self.target:
                self.rec("target", step=self.step_idx + 1, screen=self.screen, screen_version=self.screen_version, target_id=None, label=None, bbox=None, reason="cleared")
            self.target = None

    def set_screen(self, screen, cause="press"):
        prev = self.screen
        self.screen = screen
        self.screen_version += 1
        self.rec("screen", screen=screen, screen_version=self.screen_version, **{"from": prev}, cause=cause)

    def step_done(self):
        name = STEP_NAMES[self.step_idx][0]
        self.rec("step_done", step=self.step_idx + 1, name=name, duration_ms=int((self.vt - self.step_vt0) * 1000), **self.step_stats)
        self.step_idx += 1
        self.sub = 0
        self.step_vt0 = self.vt
        self.step_stats = dict(presses=0, wrong_presses=0, hesitations=0, guides=0)

    def press(self, r):
        f = self.finger
        tid = self.target["id"] if self.target else None
        result = "correct" if r and r["id"] == tid else ("wrong" if r else "no_button")
        self.counts["presses"] += 1
        self.step_stats["presses"] += 1
        nxt = None
        if result == "correct":
            self.sub += 1
            if self.sub >= len(step_targets(self.step_idx, self.goal_id)):
                nxt = STEP_NAMES[self.step_idx + 1][0]
        else:
            nxt = "option" if self.screen == "menu" else self.screen
        self.rec("press", x=round(f["x"], 4), y=round(f["y"], 4), hit_id=r and r["id"], target_id=tid, result=result, source="direct", screen=self.screen, next_screen=nxt or self.screen)
        self.last_press = {"hit_id": r and r["id"], "label": r and r["label"], "result": result, "ms": self.ams()}
        self.hold_vt = None
        if result == "correct":
            self.say("PRESS_OK", target_id=tid)
            if nxt:
                self.step_done()
                self.set_screen(nxt)
                self.target = None
                self.phase = ("screen_wait", self.vt + 0.7)
            else:
                self.plan()
        else:
            self.counts["wrong_presses"] += 1
            self.step_stats["wrong_presses"] += 1
            if nxt != self.screen:
                self.set_screen(nxt)
            self.say("PRESS_WRONG")
            self.phase = ("wrong", self.vt + 1.4)

    def on_screen_ready(self):
        g = GOALS[self.goal_id]
        s = self.screen
        if s == "option":
            self.say("SCREEN", f"옵션 화면입니다. {'아이스를' if g['temp'] == 'temp-ice' else '따뜻한 음료(HOT)를'} 고를게요")
        elif s == "confirm":
            self.say("SCREEN", "주문 확인 화면입니다. 결제하기를 찾아 볼게요")
        elif s == "pay":
            self.counts["hand_down_requests"] += 1
            self.rec("hand_down_request", reason="payment_check", waited_ms=0)
            self.say("HAND_DOWN")
            self.finger.update(tracked=False)
            self.phase = ("hand_down", self.vt + 1.6)
            self.plan()
            return
        elif s == "done":
            self.order_no = 100 + (self.attempt_no * 27) % 900
            self.say("DONE", f"주문이 끝났어요. 주문 번호는 {self.order_no}번입니다")
            self.rec("step_done", step=5, name="done", duration_ms=0, presses=0, wrong_presses=0, hesitations=0, guides=1)
            self.step_idx = 5
            self.target = None
            return
        self.plan()

    def tick(self, dt=0.1):
        self.vt += dt
        st = self.status
        if self.frozen:
            return
        st["model_ms"] = int(22 + self.rng.random() * 6)
        st["frame_age_ms"] = int(70 + self.rng.random() * 40)
        st["fps"] = round(11.5 + self.rng.random(), 1)
        st["align_age_s"] = 0.1
        if not self.attempt:
            self.track_win = (self.track_win + [0])[-60:]
            st["hand_rate"] = round(sum(self.track_win) / len(self.track_win), 2)
            return
        f = self.finger
        ph = self.phase
        if ph and self.vt >= ph[1]:
            kind = ph[0]
            self.phase = None
            if kind == "enter":
                f.update(tracked=True, x=0.6, y=0.98, seen_vt=self.vt)
            elif kind == "screen_wait":
                self.on_screen_ready()
            elif kind == "hand_lost":
                f.update(tracked=True, seen_vt=self.vt)
                self.rec("hand_found", lost_ms=1600)
            elif kind == "hand_down":
                self.rec("hand_down_done", took_ms=1600)
                g = GOALS[self.goal_id]
                self.say("PAY_CHECK", f"결제 금액은 {won(g['price'])}입니다. 카드 결제를 찾아 볼게요")
                f.update(tracked=True, x=0.5, y=0.97, seen_vt=self.vt)
            elif kind == "wrong":
                prev = "menu" if self.screen == "option" and self.step_idx == 0 else self.screen
                self.counts["reverts"] += 1
                self.rec("revert", from_screen=self.screen, to_screen=prev, reason="wrong_press")
                self.set_screen(prev, cause="operator")
                self.plan("replan")
        tracked = bool(f["tracked"]) and self.phase is None
        self.track_win = (self.track_win + [1 if tracked else 0])[-60:]
        st["hand_rate"] = round(sum(self.track_win) / len(self.track_win), 2)
        if self.vt >= self.next_perf_vt:
            self.next_perf_vt = self.vt + 2.0
            self.rec("perf", hand_rate=st["hand_rate"], model_ms=st["model_ms"], input_w=640, input_h=360, zoom=True, det_threshold=0.5, frame_age_ms=st["frame_age_ms"], fps=st["fps"])
        if not tracked or not self.target or self.screen == "done":
            return
        # 확인 화면에서 한 번 손을 놓침(가려짐)
        if self.screen == "confirm" and not self.lost_done and self.vt - self.step_vt0 > 1.2:
            self.lost_done = True
            f["tracked"] = False
            self.counts["hand_lost"] += 1
            self.rec("hand_lost", cause="occluded")
            self.say("HAND_LOST")
            self.phase = ("hand_lost", self.vt + 1.6)
            self.hold_vt = None
            return
        b = self.target["bbox"]
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        dx, dy = cx - f["x"], cy - f["y"]
        dist = math.hypot(dx, dy)
        regs = [r for r in self.regions() if r["hit"] and r["enabled"]]
        over = next((r for r in regs if r["bbox"][0] <= f["x"] <= r["bbox"][2] and r["bbox"][1] <= f["y"] <= r["bbox"][3]), None)
        f["over"] = over and over["id"]
        # 다른 버튼 위에 잠깐 머묾(옵션 화면에서 한 번)
        if over and over["id"] != self.target["id"]:
            if self.over_id != over["id"]:
                self.over_id, self.over_vt = over["id"], self.vt
            linger = self.screen == "option" and not self.hes_done and over["id"].startswith("temp-")
            if linger and self.vt - self.over_vt < 0.9:
                spd = 0.002
            else:
                spd = 0.016
                if linger:
                    self.hes_done = True
                    self.counts["hesitations"] += 1
                    self.step_stats["hesitations"] += 1
                    self.rec("hesitation", region_id=over["id"], on_target=False, dwell_ms=int((self.vt - self.over_vt) * 1000), ended_by="moved_away")
            # 메뉴 화면에서 홀수 번째 시도는 이웃 버튼을 한 번 잘못 누름
            if self.screen == "menu" and not self.wrong_done and self.attempt_no % 2 == 1 and over["id"].startswith("menu-") and self.vt - self.step_vt0 > 1.5:
                self.wrong_done = True
                self.press(over)
                return
        else:
            self.over_id = over and over["id"]
            spd = 0.016
        inside = over is not None and over["id"] == self.target["id"]
        if inside:
            if self.hold_vt is None:
                self.hold_vt = self.vt
                self.say("HOLD", target_id=self.target["id"])
            elif self.vt - self.hold_vt > 0.6 and (not self.guide or self.guide["code"] != "PRESS"):
                self.say("PRESS", target_id=self.target["id"])
            elif self.vt - self.hold_vt > 1.4:
                self.press(over)
                return
            f["x"] += dx * 0.15 + self.rng.gauss(0, 0.002)
            f["y"] += dy * 0.15 + self.rng.gauss(0, 0.002)
        else:
            self.hold_vt = None
            k = min(1.0, spd / max(dist, 1e-6))
            f["x"] += dx * k + self.rng.gauss(0, 0.004)
            f["y"] += dy * k * 0.8 + self.rng.gauss(0, 0.004)
            if self.vt - self.last_guide_vt > 1.1:
                ax, ay = abs(dx), abs(dy)
                base = ("RIGHT" if dx > 0 else "LEFT") if ax >= ay else ("DOWN" if dy > 0 else "UP")
                mag = max(ax, ay)
                self.say(base + ("_SMALL" if mag < 0.12 else ""), target_id=self.target["id"])
        f["seen_vt"] = self.vt
        if self.vt >= self.next_finger_vt:
            self.next_finger_vt = self.vt + 0.2
            self.rec("finger", x=round(f["x"], 4), y=round(f["y"], 4), tracked=True, over=f["over"], dist=round(dist, 4))

    # --- 계약 응답
    def live(self):
        st = dict(self.status)
        a = self.attempt
        f = self.finger
        steps = []
        for i, (n, lab) in enumerate(STEP_NAMES):
            if self.step_idx > i:
                s = "done"
            elif self.step_idx == i and a:
                s = "active"
            else:
                s = "todo"
            steps.append({"step": i + 1, "name": n, "label": lab, "status": s})
        tracked = bool(f["tracked"]) and self.phase is None
        safety_reason = None
        if not tracked:
            safety_reason = "hand_lost"
        elif not st["aligned"]:
            safety_reason = "not_aligned"
        elif not self.target:
            safety_reason = "no_target"
        elif f["over"] != self.target["id"]:
            safety_reason = "not_on_target"
        g = GOALS[self.goal_id]
        return {
            "server_time": self.iso(),
            "data_source": "synthetic",
            "mock": True,
            "attempt": a and {"id": a["id"], "started": a["started"], "ms": self.ams(), "data_source": a["data_source"], "conditions": a["conditions"]},
            "button_source": "kiosk_ground_truth",
            "goal": {"id": self.goal_id, "label": g["label"]},
            "steps": steps,
            "kiosk": {"connected": True, "screen": self.screen, "screen_version": self.screen_version, "layout": self.layout, "regions": self.regions()},
            "target": self.target,
            "finger": {"tracked": tracked, "x": f["x"] if f["x"] is not None else None, "y": f["y"], "over": f["over"] if tracked else None,
                       "age_ms": (80 if self.frozen and tracked else int((self.vt - f["seen_vt"]) * 1000)) if f.get("seen_vt") is not None else None},
            "guide": self.guide,
            "safety": {"press_allowed": safety_reason is None, "reason": safety_reason},
            "status": st,
            "last_press": self.last_press,
            "counts": dict(self.counts),
            "paused": self.paused,
            "order_no": self.order_no,
            # 아래는 A의 API.md에 있는 추가 필드를 흉내 낸 것
            "auto_click": False,
            "hand_down": {"kind": "payment", "phase": "waiting_down"} if self.phase and self.phase[0] == "hand_down" else None,
            "phone": {"connected": True, "audio_unlocked": True, "last_poll_age_s": 0.4},
            "last_attempt": (lambda h: h and {"id": h["id"], "completed": h.get("completed"), "end_reason": h.get("end_reason"),
                                               "order_no": h.get("order_no"), "total_ms": h.get("total_ms")})(self.history[-1] if self.history else None),
        }

    def all_attempts(self):
        out = []
        for a in self.history + ([self.attempt] if self.attempt else []):
            out.append({"id": a["id"], "started": a["started"], "ended": a.get("ended"), "data_source": a["data_source"], "conditions": a["conditions"],
                        "goal": {"id": a["goal_id"], "label": GOALS[a["goal_id"]]["label"]}, "completed": a.get("completed"), "end_reason": a.get("end_reason"),
                        "total_ms": a.get("total_ms"), "order_no": a.get("order_no"), "records": len(a["records"]), "running": a is self.attempt})
        return list(reversed(out))

    def find(self, aid):
        return next((a for a in self.history + ([self.attempt] if self.attempt else []) if a["id"] == aid), None)

    def frame_view(self):
        return {"screen": self.screen, "layout": self.layout, "goal_id": self.goal_id, "order_no": self.order_no, "marker_ids": list(self.marker_ids),
                "finger": {"tracked": bool(self.finger["tracked"]) and self.phase is None, "x": self.finger["x"], "y": self.finger["y"]}}

    # --- 캡처·시험용 고정 상황
    def run_until(self, pred, limit=3000):
        for _ in range(limit):
            if pred():
                return True
            self.tick()
        return False

    def scenario_set(self, name):
        self.frozen = False
        self.paused = False
        self.frame_mode = "camera"
        self.marker_ids = [0, 1, 2, 3]
        self.status.update(camera=True, markers=4, aligned=True)
        if name == "live":
            self.scenario = "live"
            return
        if name == "offline":
            self.scenario = "offline"
            return
        self.scenario = name
        if self.attempt:
            self.attempt = None
            self.reset_idle()
        if name == "idle":
            self.frozen = True
            return
        cond = {"layout": "B", "guidance": "on", "blindfold": "yes", "lighting_note": "창가, 오후", "participant_code": "P03", "operator_note": "캡처용 예시"}
        self.attempt_no = 0  # start()에서 1이 됨(홀수: 메뉴에서 한 번 잘못 누름)
        self.start(cond, "iced-americano-1", "synthetic")
        if name in ("guiding", "markers_low", "schematic", "camera_off"):
            self.run_until(lambda: self.screen == "option" and self.target and self.target["id"] == "temp-ice" and self.guide and self.guide["code"] in DIRS and self.vt - self.step_vt0 > 1.6
                           or (self.screen == "option" and self.guide and self.guide["code"].endswith("_SMALL") and self.finger["tracked"]))
        elif name == "hand_lost":
            self.run_until(lambda: self.phase and self.phase[0] == "hand_lost" and self.phase[1] - self.vt < 1.0)
            self.status["hand_rate"] = 0.41
        elif name == "done":
            self.run_until(lambda: self.screen == "done" and self.order_no)
        if name == "markers_low":
            self.marker_ids = [0, 1]
            self.status.update(markers=2, aligned=True, align_age_s=0.3)
        if name == "schematic":
            self.frame_mode = "none"
        if name == "camera_off":
            self.frame_mode = "off"
            self.status.update(camera=False, markers=0, aligned=False, align_age_s=None, hand_rate=None, model_ms=None, frame_age_ms=None, fps=None)
            self.finger.update(tracked=False)
        self.frozen = True


def seed_history(sim, n):
    samples = [({"layout": "A", "guidance": "on", "blindfold": "no", "lighting_note": "실내 형광등", "participant_code": "P01", "operator_note": "캡처용 예시"}, "iced-americano-1"),
               ({"layout": "B", "guidance": "off", "blindfold": "yes", "lighting_note": "", "participant_code": "P02", "operator_note": "캡처용 예시"}, "hot-latte-1"),
               ({"layout": "A", "guidance": "on", "blindfold": "yes", "lighting_note": "창가", "participant_code": "P02", "operator_note": "캡처용 예시"}, "iced-vanilla-1")]
    for i in range(n):
        cond, gid = samples[i % len(samples)]
        sim.start(cond, gid, "synthetic")
        if i == 1:
            sim.run_until(lambda: sim.screen == "confirm")
            sim.end("aborted")
        else:
            sim.run_until(lambda: sim.screen == "done" and sim.order_no)
            sim.tick()
            sim.end("done")
        sim.vt += 90
    sim.layout, sim.goal_id = "A", "iced-americano-1"


# ---------------------------------------------------------------- HTTP
TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".png": "image/png", ".json": "application/json", ".md": "text/markdown", ".svg": "image/svg+xml"}
CSV_COLS = ["v", "attempt", "seq", "t", "ms", "kind", "x", "y", "tracked", "code", "text", "target_id", "hit_id", "result", "screen", "detail"]


def to_csv(records):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for r in records:
        rest = {k: v for k, v in r.items() if k not in CSV_COLS}
        w.writerow([r.get(c, "") if r.get(c) is not None else "" for c in CSV_COLS[:-1]] + [json.dumps(rest, ensure_ascii=False) if rest else ""])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def make_handler(sim: Sim):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def send(self, code, body=b"", ctype="application/json; charset=utf-8", headers=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return {}

        def offline(self, p):
            return sim.scenario == "offline" and p.startswith("/api/")

        def do_GET(self):
            u = urlparse(self.path)
            p, q = unquote(u.path), parse_qs(u.query)
            if p in ("/", "/admin"):
                return self.send(302, b"", headers={"Location": "/admin/"})
            if p.startswith("/admin/"):
                rel = p[len("/admin/"):] or "index.html"
                f = (ADMIN / rel).resolve()
                if ADMIN.resolve() not in f.parents or not f.is_file():
                    return self.send(404, {"error": "not found"})
                ct = TYPES.get(f.suffix.lower(), "application/octet-stream")
                return self.send(200, f.read_bytes(), ct + ("; charset=utf-8" if ct.startswith("text") else ""))
            if self.offline(p):
                return self.send(503, {"error": "mock offline"})
            if p == "/api/live":
                with sim.lock:
                    return self.send(200, sim.live())
            if p == "/api/events":
                after = int(q.get("after", ["0"])[0] or 0)
                end = time.time() + 1.5
                with sim.cond:
                    while True:
                        a = sim.attempt
                        new = [r for r in a["records"] if r["seq"] > after] if a else []
                        if new or time.time() >= end:
                            new = new[:400]
                            # A의 API.md 형식: {"attempt", "events", "last_seq"}
                            return self.send(200, {"attempt": a and a["id"], "events": new, "last_seq": new[-1]["seq"] if new else (a["seq"] if a else 0)})
                        sim.cond.wait(timeout=max(0.05, end - time.time()))
            if p == "/api/frame/latest":
                if sim.frame_mode == "none":
                    return self.send(404, {"error": "no frame endpoint (mock)"})
                if sim.frame_mode == "off":
                    time.sleep(1.5)
                    return self.send(204)
                wait = sim.frame_at + 0.12 - time.time()
                if wait > 0:
                    time.sleep(wait)
                with sim.lock:
                    view = sim.frame_view()
                    st = dict(sim.status)
                    sim.frame_seq += 1
                    seq = sim.frame_seq
                    sim.frame_at = time.time()
                jpg, markers = render_frame(view)
                info = {"seq": seq, "w": CAM_W, "h": CAM_H, "markers": markers, "recv": sim.iso(), "age_ms": st["frame_age_ms"],
                        "H": homography().tolist() if st["aligned"] else None, "H_age_s": 0.1, "H_markers": len(markers), "warn": None,
                        "cam": {"fps": st["fps"], "w": CAM_W, "h": CAM_H}, "synthetic": True}
                return self.send(200, jpg, "image/jpeg", {"X-Info": quote(json.dumps(info, ensure_ascii=False))})
            if p == "/api/goals":
                return self.send(200, {"goals": [{"id": k, "label": g["label"], "default": k == "iced-americano-1"} for k, g in GOALS.items()], "current": sim.goal_id})
            if p == "/api/attempts":
                with sim.lock:
                    return self.send(200, {"attempts": sim.all_attempts()})
            if p.startswith("/api/attempts/"):
                name = p[len("/api/attempts/"):]
                aid, _, ext = name.rpartition(".")
                with sim.lock:
                    a = sim.find(aid)
                    recs = list(a["records"]) if a else None
                if recs is None or ext not in ("jsonl", "csv"):
                    return self.send(404, {"error": "not found"})
                if ext == "jsonl":
                    body = ("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n").encode("utf-8")
                    return self.send(200, body, "application/x-ndjson; charset=utf-8", {"Content-Disposition": f'attachment; filename="{aid}.jsonl"'})
                return self.send(200, to_csv(recs), "text/csv; charset=utf-8", {"Content-Disposition": f'attachment; filename="{aid}.csv"'})
            return self.send(404, {"error": "not found"})

        def do_POST(self):
            p = urlparse(self.path).path
            b = self.body()
            if p == "/dev/scenario":
                with sim.lock:
                    sim.scenario_set(b.get("name", "live"))
                    return self.send(200, {"ok": True, "scenario": sim.scenario})
            if self.offline(p):
                return self.send(503, {"error": "mock offline"})
            try:
                with sim.lock:
                    if p == "/api/attempt/start":
                        sim.frozen = False
                        sim.scenario = "live"
                        aid = sim.start(b.get("conditions") or {}, b.get("goal_id"), b.get("data_source"))
                        return self.send(200, {"attempt": aid})
                    if p == "/api/attempt/end":
                        aid = sim.end(b.get("reason", "aborted"))
                        return self.send(200, {"ok": True, "attempt": aid})
                    if p == "/api/goal":
                        gid = b.get("goal_id")
                        if gid not in GOALS:
                            return self.send(400, {"error": "알 수 없는 목표입니다"})
                        sim.goal_id = gid
                        sim.rec("operator", action="goal", detail=gid)
                        sim.plan("replan")
                        return self.send(200, {"ok": True})
                    if p == "/api/control":
                        act = b.get("action")
                        if act not in ("repeat", "stop", "resume"):
                            return self.send(400, {"error": "알 수 없는 조작입니다"})
                        sim.rec("operator", action=act, detail=None)
                        if act == "stop":
                            sim.paused = True
                        elif act == "resume":
                            sim.paused = False
                        elif act == "repeat" and sim.guide:
                            sim.rec("guide", code=sim.guide["code"], text=sim.guide["text"], target_id=None, channel="phone", suppressed=False)
                        return self.send(200, {"ok": True, "paused": sim.paused})
            except ValueError as e:
                return self.send(409, {"error": str(e)})
            return self.send(404, {"error": "not found"})

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8470)
    ap.add_argument("--speed", type=float, default=1.0, help="흉내 속도(시험은 3~5)")
    ap.add_argument("--seed-attempts", type=int, default=2, help="시작할 때 만들어 둘 지난 시도 수")
    ap.add_argument("--scenario", default="live")
    a = ap.parse_args()
    if not 8470 <= a.port <= 8475:
        raise SystemExit("포트는 8470~8475만 씁니다")
    sim = Sim(speed=a.speed)
    seed_history(sim, a.seed_attempts)
    sim.scenario_set(a.scenario)

    def loop():
        while True:
            time.sleep(0.1 / sim.speed)
            with sim.lock:
                sim.tick()

    threading.Thread(target=loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(sim))
    srv.daemon_threads = True
    srv.handle_error = lambda request, addr: None  # 페이지를 닫아 끊긴 롱 폴링 연결 오류는 조용히 넘김
    print(f"mock server: http://localhost:{a.port}/admin/  (예시 데이터, speed={a.speed})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
