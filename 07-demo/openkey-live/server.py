"""OpenKey Live 서버: 휴대폰 카메라 → 마커 위치 맞춤 → 손끝 → 안내 판단(파이썬 엔진) → 휴대폰 음성.

실행(프로젝트 루트):
    .venv\\Scripts\\python.exe 07-demo\\openkey-live\\server.py            # 기본 포트 8460(HTTPS)
노트북(키오스크):  https://localhost:8460/kiosk-host
휴대폰(사용자):    https://<노트북 IP>:8460/phone
관리자 콘솔:       https://localhost:8460/admin/   (B 담당 폴더가 있으면 제공)

- 05-data/tools/finger-demo/server.py 를 복사해 확장했다(원본은 수정하지 않음).
- 영상·사진·음성은 저장하지 않는다. 서버는 최신 카메라 프레임 1장만 메모리에 둔다.
  기록은 좌표·시간·화면 상태·안내 문구뿐이며 runs/<attempt>.jsonl 에 쓴다(SCHEMA.md v1).
- 안내 판단은 이 서버(engine/)에서 한다. 관리자 콘솔을 닫아도 안내는 계속된다.
- 버튼 위치는 모의 키오스크가 알려 주는 시연용 정답 좌표(button_source=kiosk_ground_truth)다.
"""
import argparse
import csv
import io
import json
import mimetypes
import pathlib
import socket
import ssl
import sys
import threading
import time
from collections import OrderedDict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

import cv2
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from engine import Config, LiveEngine, goals_list  # noqa: E402
from engine.recorder import iso  # noqa: E402

STATIC = {"/kiosk/": ROOT / "04-practice-kiosk", "/sw/": ROOT / "03-software", "/static/": HERE / "static"}
OPTIONAL = {"/admin/": HERE / "admin", "/analytics/": HERE / "analytics", "/training/": HERE / "training", "/store/": HERE / "store"}
PAGES = {"/kiosk-host": "kiosk-host.html", "/kiosk-host.html": "kiosk-host.html", "/phone": "phone.html", "/phone.html": "phone.html"}
TYPES = {".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm", ".task": "application/octet-stream",
         ".json": "application/json", ".jsonl": "application/x-ndjson", ".css": "text/css", ".html": "text/html", ".png": "image/png",
         ".svg": "image/svg+xml", ".md": "text/markdown", ".csv": "text/csv"}
DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
MARKER_PX, MARKER_PAD = 200, 40   # 검은 마커 200px + 흰 여백 40px(각 변). kiosk-host.html 의 PAD와 같아야 함


def apply_h(H, x, y):
    w = H[2][0] * x + H[2][1] * y + H[2][2]
    return ((H[0][0] * x + H[0][1] * y + H[0][2]) / w, (H[1][0] * x + H[1][1] * y + H[1][2]) / w)


def lan_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


class State:
    def __init__(self, engine: LiveEngine, runs_dir: pathlib.Path, allow_synthetic: bool):
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.engine = engine
        self.runs_dir = runs_dir
        self.allow_synthetic = allow_synthetic
        self.layout_markers = None     # kiosk-host가 보낸 마커 위치(키오스크 정규 좌표)
        self.frame = None
        self.seq = 0
        self.frame_meta = OrderedDict()  # seq → {H, t, aligned}
        self.H = None
        self.H_at = 0.0
        self.H_markers = 0
        self.cam = {}
        self.laptop_voice = "auto"     # auto(휴대폰 없을 때만) | on | off
        self.hand_cfg = {"zoom": True, "det": 0.35, "rescan": True, "max_side": 0}
        self.hand_log = deque(maxlen=400)   # 최근 손 인식 결과(좌표·시간만, 진단용)
        self.det = cv2.aruco.ArucoDetector(DICT, cv2.aruco.DetectorParameters())
        self.det_lock = threading.Lock()
        self.started = time.time()

    # ---------------------------------------------------------------- 마커·위치 맞춤
    def detect(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        with self.det_lock:
            corners, ids, _ = self.det.detectMarkers(gray)
        found = []
        if ids is not None:
            for c, i in zip(corners, ids.flatten()):
                found.append({"id": int(i), "corners": [[round(float(x), 1), round(float(y), 1)] for x, y in c.reshape(4, 2)]})
        return found

    def update_h(self, found, now):
        if not self.layout_markers:
            return 0, "키오스크 화면(/kiosk-host)이 아직 연결되지 않음"
        known = {m["id"]: m["corners"] for m in self.layout_markers}
        src, dst = [], []
        for m in found:
            if m["id"] in known:
                src += m["corners"]
                dst += known[m["id"]]
        n = len(src) // 4
        if n >= 2 or (n == 1 and self.H is None):
            H, _ = cv2.findHomography(np.array(src, np.float64), np.array(dst, np.float64), 0)
            if H is not None:
                self.H, self.H_at, self.H_markers = H, now, n
                return n, None
        return n, None if self.H is not None else "마커를 2개 이상 찾지 못함"

    def aligned(self, now):
        return self.H is not None and now - self.H_at <= self.engine.cfg.align_max_age_s


def frame_post(st: State, jpeg: bytes, meta: dict):
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return 400, {"error": "bad jpeg"}
    found = st.detect(img)
    now = time.monotonic()
    with st.cond:
        n, warn = st.update_h(found, now)
        aligned = st.aligned(now)
        st.seq += 1
        st.cam = {"last": iso_now(), "w": img.shape[1], "h": img.shape[0], "fps": meta.get("fps"), "ua": str(meta.get("ua", ""))[:60],
                  "source": meta.get("source", "phone")}
        H = st.H.tolist() if st.H is not None else None
        st.frame = {"seq": st.seq, "jpeg": jpeg, "w": img.shape[1], "h": img.shape[0], "markers": found, "t": now, "recv": iso_now(), "warn": warn,
                    "H": H, "aligned": aligned}
        st.frame_meta[st.seq] = {"H": H, "t": now, "aligned": aligned, "w": img.shape[1], "h": img.shape[0]}
        while len(st.frame_meta) > 60:
            st.frame_meta.popitem(last=False)
        st.engine.phone.update({"cam_w": img.shape[1], "cam_h": img.shape[0]})
        st.engine.on_markers(now, n, aligned, round(now - st.H_at, 2) if st.H is not None else None, "camera")
        st.cond.notify_all()
        if st.seq == 1:
            print(f"[live] 첫 카메라 프레임 {img.shape[1]}x{img.shape[0]}", flush=True)
    return 200, {"seq": st.seq, "markers": len(found), "known_markers": n, "aligned": aligned, "warn": warn}


def iso_now():
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def hand_post(st: State, m: dict):
    now = time.monotonic()
    with st.cond:
        e = st.engine
        if m.get("source") == "synthetic":
            if not st.allow_synthetic:
                return 403, {"error": "합성 입력은 --allow-synthetic 으로 켠 서버에서만 받는다"}
            rep = {k: m.get(k) for k in ("tracked", "x", "y", "count", "model_ms", "input_w", "input_h", "zoom", "det_threshold", "fps")}
            rep.update(source="synthetic", aligned=bool(m.get("aligned", True)), frame_age_ms=m.get("frame_age_ms", 0), markers=m.get("markers", 4))
            e.on_hand(now, rep)
            st.cond.notify_all()
            return 200, {"ok": True}
        fm = st.frame_meta.get(int(m.get("seq") or 0))
        hands = m.get("hands") or []
        rep = {"model_ms": m.get("model_ms"), "input_w": m.get("input_w"), "input_h": m.get("input_h"), "zoom": m.get("zoom"),
               "det_threshold": m.get("det_threshold"), "fps": m.get("fps"), "source": "camera", "rescan": m.get("rescan")}
        if not fm:
            rep.update(tracked=False, frame_age_ms=None)
            e.on_hand(now, rep)
            return 200, {"ok": True, "note": "frame meta missing"}
        rep["frame_age_ms"] = int((now - fm["t"]) * 1000)
        rep["aligned"] = bool(fm["aligned"])
        best, inside_n = None, 0
        if fm["H"] is not None:
            prev = e.hand["p"] if e.hand and e.hand.get("tracked") else None
            for h in hands:
                px, py = h["tip"]
                k = apply_h(fm["H"], px, py)
                ins = -0.02 <= k[0] <= 1.02 and -0.02 <= k[1] <= 1.02
                inside_n += 1 if ins else 0
                score = (0 if ins else 1, ((k[0] - prev[0]) ** 2 + (k[1] - prev[1]) ** 2) if prev else 0)
                if best is None or score < best[0]:
                    best = (score, k)
        if best:
            rep.update(tracked=True, x=best[1][0], y=best[1][1], count=max(1, inside_n))
        else:
            rep.update(tracked=False)
        st.hand_log.append({"seq": int(m.get("seq") or 0), "tracked": bool(best), "x": rep.get("x"), "y": rep.get("y"), "hands": len(hands),
                            "model_ms": m.get("model_ms"), "input_w": m.get("input_w"), "input_h": m.get("input_h"), "zoom": m.get("zoom"),
                            "rescan": m.get("rescan"), "det": m.get("det_threshold"), "frame_age_ms": rep.get("frame_age_ms")})
        e.on_hand(now, rep)
        st.cond.notify_all()
    return 200, {"ok": True, "tracked": bool(best), "x": best[1][0] if best else None, "y": best[1][1] if best else None}


def list_attempts(st: State):
    out = []
    for folder in (st.runs_dir, st.runs_dir / "examples"):
        if not folder.is_dir():
            continue
        for f in sorted(folder.glob("*.jsonl"), reverse=True):
            first = last = None
            n = 0
            try:
                with open(f, encoding="utf-8") as fh:
                    for line in fh:
                        if not line.strip():
                            continue
                        r = json.loads(line)
                        n += 1
                        if first is None:
                            first = r
                        last = r
            except (OSError, ValueError):
                continue
            if not first:
                continue
            end = last if last and last.get("kind") == "attempt_end" else None
            out.append({"id": f.stem, "folder": "examples" if folder.name == "examples" else "runs", "records": n,
                        "started": first.get("t"), "data_source": first.get("data_source"),
                        "layout": (first.get("conditions") or {}).get("layout"), "guidance": (first.get("conditions") or {}).get("guidance"),
                        "goal": (first.get("goal") or {}).get("id"), "completed": end.get("completed") if end else None,
                        "end_reason": end.get("end_reason") if end else None, "total_ms": end.get("total_ms") if end else None,
                        "url_jsonl": f"/api/attempts/{f.stem}.jsonl", "url_csv": f"/api/attempts/{f.stem}.csv"})
    return out


def find_attempt(st: State, aid: str):
    if not aid.replace("-", "").isalnum():
        return None
    for folder in (st.runs_dir, st.runs_dir / "examples"):
        f = folder / f"{aid}.jsonl"
        if f.is_file():
            return f
    return None


def to_csv(path: pathlib.Path) -> bytes:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cols = ["v", "attempt", "seq", "t", "ms", "kind"]
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([json.dumps(r[c], ensure_ascii=False) if isinstance(r.get(c), (dict, list)) else ("" if r.get(c) is None else r.get(c)) for c in cols])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def make_handler(st: State):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def send(self, code, body=b"", ctype="application/json; charset=utf-8", headers=None):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def body(self):
            return self.rfile.read(int(self.headers.get("Content-Length", 0)))

        def jbody(self):
            raw = self.body()
            return json.loads(raw) if raw else {}

        def serve_file(self, base: pathlib.Path, rel: str):
            f = (base / rel).resolve()
            if f.is_dir():
                f = f / "index.html"
            if base.resolve() not in f.parents and f != base.resolve() or not f.is_file():
                return self.send(404, {"error": "not found"})
            ct = TYPES.get(f.suffix.lower()) or mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            return self.send(200, f.read_bytes(), ct + ("; charset=utf-8" if ct.startswith("text") or ct.endswith("json") else ""))

        def do_HEAD(self):
            return self.do_GET()

        def do_GET(self):
            u = urlparse(self.path)
            p, q = unquote(u.path), parse_qs(u.query)
            arg = lambda k, d=None: q.get(k, [d])[0]  # noqa: E731
            e = st.engine
            if p in ("/", "/index.html"):
                links = "".join(f"<li><a href='{h}'>{t}</a></li>" for h, t in [("/kiosk-host", "kiosk-host(노트북 키오스크)"), ("/phone", "phone(휴대폰, 사용자 기기)"),
                                                                              ("/admin/", "admin(관리자 콘솔, 있으면)"), ("/api/live", "api/live")])
                return self.send(200, f"<!doctype html><meta charset=utf-8><title>OpenKey Live</title><h1>OpenKey Live</h1><ul>{links}</ul>".encode(),
                                 "text/html; charset=utf-8")
            if p in PAGES:
                return self.send(200, (HERE / PAGES[p]).read_bytes(), "text/html; charset=utf-8")
            for prefix, base in STATIC.items():
                if p.startswith(prefix):
                    return self.serve_file(base, p[len(prefix):])
            for prefix, base in OPTIONAL.items():
                if p == prefix.rstrip("/"):
                    return self.send(302, b"", headers={"Location": prefix})
                if p.startswith(prefix):
                    if not base.is_dir():
                        return self.send(404, {"error": f"{prefix} 폴더가 아직 없음"})
                    return self.serve_file(base, p[len(prefix):])
            if p.startswith("/runs/"):
                rel = p[len("/runs/"):]
                base = st.runs_dir
                if rel in ("", "examples", "examples/"):
                    return self.send(200, {"attempts": list_attempts(st)})
                return self.serve_file(base, rel)
            if p.startswith("/api/marker/"):
                i = int(p.split("/")[-1].split(".")[0])
                mk = cv2.aruco.generateImageMarker(DICT, i, MARKER_PX)
                mk = cv2.copyMakeBorder(mk, MARKER_PAD, MARKER_PAD, MARKER_PAD, MARKER_PAD, cv2.BORDER_CONSTANT, value=255)
                return self.send(200, cv2.imencode(".png", mk)[1].tobytes(), "image/png", {"Cache-Control": "max-age=3600"})
            if p == "/api/live":
                now = time.monotonic()
                with st.lock:
                    e.tick(now)
                    live = e.live(now)
                    live["server"] = {"frames": st.seq, "cam": st.cam, "markers_layout": bool(st.layout_markers), "laptop_voice": st.laptop_voice,
                                      "hand_cfg": st.hand_cfg, "lan": [f"https://{ip}:{st.port}/phone" for ip in lan_ips()],
                                      "allow_synthetic": st.allow_synthetic}
                return self.send(200, live)
            if p == "/api/hand/recent":
                after = int(arg("after_seq", "0") or 0)
                with st.lock:
                    return self.send(200, {"items": [h for h in st.hand_log if h["seq"] > after]})
            if p == "/api/health":
                return self.send(200, {"ok": True, "uptime_s": round(time.time() - st.started, 1)})
            if p == "/api/goals":
                with st.lock:
                    return self.send(200, {"goals": goals_list(), "current": e.goal["id"]})
            if p == "/api/events":
                after = int(arg("after", "0") or 0)
                deadline = time.monotonic() + 1.5
                with st.cond:
                    while True:
                        a = e.attempt
                        recs = a["rec"].after(after) if a else []
                        if recs or time.monotonic() >= deadline:
                            break
                        st.cond.wait(timeout=max(0.01, deadline - time.monotonic()))
                    return self.send(200, {"attempt": a["id"] if a else None, "events": recs,
                                           "last_seq": recs[-1]["seq"] if recs else after})
            if p == "/api/frame/latest":
                after = int(arg("after", "0") or 0)
                with st.cond:
                    st.cond.wait_for(lambda: st.seq > after, timeout=1.5)
                    fr = st.frame
                    if not fr or fr["seq"] <= after:
                        return self.send(204)
                    now = time.monotonic()
                    info = {k: fr[k] for k in ("seq", "w", "h", "markers", "recv", "warn", "H", "aligned")}
                    info["age_ms"] = round((now - fr["t"]) * 1000)
                    info["H_age_s"] = round(now - st.H_at, 1) if st.H is not None else None
                    info["H_markers"] = st.H_markers
                    info["cam"] = st.cam
                    jpeg = fr["jpeg"]
                return self.send(200, jpeg, "image/jpeg", {"X-Info": quote(json.dumps(info, ensure_ascii=False))})
            if p == "/api/say":
                after = int(arg("after", "0") or 0)
                ch = arg("ch", "phone")
                deadline = time.monotonic() + float(arg("wait", "1.0") or 1.0)
                with st.cond:
                    while True:
                        now = time.monotonic()
                        if ch == "phone":
                            e.phone_poll_at = now
                        elif ch == "laptop":
                            e.laptop_poll_at = now
                        items = e.speaker.after(after)
                        if items or now >= deadline:
                            break
                        st.cond.wait(timeout=max(0.01, deadline - now))
                    now = time.monotonic()
                    phone_on = e.phone_poll_at is not None and now - e.phone_poll_at < 3.0
                    speak = True if ch != "laptop" else (st.laptop_voice == "on" or (st.laptop_voice == "auto" and not phone_on))
                    out = [{"n": i["n"], "code": i["code"], "text": i["text"], "prio": i["prio"], "interrupt": i["interrupt"],
                            "age_ms": int((now - i["t"]) * 1000), "ttl_ms": int(i["ttl_s"] * 1000),
                            "reason": i.get("reason")} for i in items]
                    return self.send(200, {"items": out, "n": e.speaker.n, "speak": speak, "paused": e.paused,
                                           "attempt": e.attempt["id"] if e.attempt else None})
            if p == "/api/cmd":
                after = int(arg("after", "0") or 0)
                with st.lock:
                    return self.send(200, {"cmds": [c for c in e.cmds if c["n"] > after], "hand_cfg": st.hand_cfg,
                                           "auto_click": e.auto_click, "laptop_voice": st.laptop_voice})
            if p == "/api/attempts":
                return self.send(200, {"attempts": list_attempts(st)})
            if p.startswith("/api/attempts/"):
                name = p[len("/api/attempts/"):]
                aid, _, ext = name.rpartition(".")
                f = find_attempt(st, aid)
                if not f or ext not in ("jsonl", "csv"):
                    return self.send(404, {"error": "not found"})
                if ext == "jsonl":
                    return self.send(200, f.read_bytes(), "application/x-ndjson; charset=utf-8",
                                     {"Content-Disposition": f'attachment; filename="{aid}.jsonl"'})
                return self.send(200, to_csv(f), "text/csv; charset=utf-8", {"Content-Disposition": f'attachment; filename="{aid}.csv"'})
            return self.send(404, {"error": "not found"})

        def do_POST(self):
            p = urlparse(self.path).path
            e = st.engine
            try:
                if p == "/api/frame":
                    meta = json.loads(unquote(self.headers.get("X-Meta", "%7B%7D")))
                    code, body = frame_post(st, self.body(), meta)
                    return self.send(code, body)
                m = self.jbody()
                now = time.monotonic()
                if p == "/api/hand":
                    code, body = hand_post(st, m)
                    return self.send(code, body)
                if p == "/api/kiosk":
                    with st.cond:
                        if m.get("markers"):
                            st.layout_markers = m["markers"]
                        state = m.get("state")
                        if state:
                            state["autoDefault"] = m.get("autoDefault", state.get("autoDefault"))
                            e.on_kiosk(now, state, m.get("touches") or [], m.get("screen_events") or [])
                        st.cond.notify_all()
                        return self.send(200, {"ok": True, "attempt": e.attempt["id"] if e.attempt else None})
                if p == "/api/attempt/start":
                    with st.cond:
                        dev = {"cam_w": st.cam.get("w"), "cam_h": st.cam.get("h"), "phone_ua_short": st.cam.get("ua") or None,
                               "audio_out": e.phone.get("audio_out", "unknown")}
                        ds = m.get("data_source") or e.default_data_source
                        if ds not in ("synthetic", "rehearsal", "field"):
                            return self.send(400, {"error": "data_source는 synthetic|rehearsal|field"})
                        aid = e.start_attempt(now, conditions=m.get("conditions"), goal_id=m.get("goal_id"), data_source=ds, device=dev,
                                              reset_kiosk=m.get("reset_kiosk", True))
                        st.cond.notify_all()
                        return self.send(200, {"attempt": aid})
                if p == "/api/attempt/end":
                    with st.cond:
                        reason = m.get("reason") or "aborted"
                        if reason not in ("done", "aborted", "timeout", "error"):
                            reason = "aborted"
                        if e.attempt:
                            e._rec("operator", now, action="end", detail=reason)
                        s = e.end_attempt(now, reason)
                        st.cond.notify_all()
                        return self.send(200, {"ended": s})
                if p == "/api/goal":
                    with st.cond:
                        e.set_goal(now, m.get("goal_id"))
                        st.cond.notify_all()
                        return self.send(200, {"goal": e.goal["id"]})
                if p == "/api/control":
                    with st.cond:
                        act = m.get("action")
                        if act not in ("repeat", "stop", "resume", "auto_click_on", "auto_click_off"):
                            return self.send(400, {"error": "action은 repeat|stop|resume|auto_click_on|auto_click_off"})
                        e.control(now, act)
                        st.cond.notify_all()
                        return self.send(200, {"ok": True, "paused": e.paused, "auto_click": e.auto_click})
                if p == "/api/voice":
                    with st.cond:
                        cmd = m.get("command")
                        if cmd not in ("start", "repeat", "stop", "goal"):
                            return self.send(400, {"error": "command는 start|repeat|stop|goal"})
                        via = "speech" if m.get("via") == "speech" else "button"
                        e.on_voice(now, cmd, via=via, goal_id=m.get("goal_id"))
                        st.cond.notify_all()
                        return self.send(200, {"ok": True, "attempt": e.attempt["id"] if e.attempt else None, "paused": e.paused})
                if p == "/api/phone":
                    with st.lock:
                        e.phone.update({k: m[k] for k in ("audio_unlocked", "audio_out", "speech_supported", "recognition_supported", "wake_lock") if k in m})
                        return self.send(200, {"ok": True})
                if p == "/api/settings":
                    with st.lock:
                        if "laptop_voice" in m and m["laptop_voice"] in ("auto", "on", "off"):
                            st.laptop_voice = m["laptop_voice"]
                        if "auto_click" in m:
                            e.control(now, "auto_click_on" if m["auto_click"] else "auto_click_off")
                        for k in ("zoom", "det", "rescan", "max_side"):
                            if k in (m.get("hand") or {}):
                                st.hand_cfg[k] = m["hand"][k]
                        return self.send(200, {"laptop_voice": st.laptop_voice, "auto_click": e.auto_click, "hand_cfg": st.hand_cfg})
            except (ValueError, KeyError, TypeError) as err:
                return self.send(400, {"error": str(err)})
            return self.send(404, {"error": "not found"})
    return H


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        err = sys.exc_info()[1]
        if isinstance(err, (ConnectionError, ssl.SSLError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def ticker(st: State, stop: threading.Event):
    while not stop.is_set():
        with st.cond:
            n0 = st.engine.speaker.n
            st.engine.tick(time.monotonic())
            if st.engine.speaker.n != n0:
                st.cond.notify_all()
        stop.wait(0.05)


def build(port=8460, runs_dir=None, allow_synthetic=False, auto_click=None, data_source="rehearsal", cfg_overrides=None):
    cfg = Config(auto_click=auto_click, **(cfg_overrides or {}))
    rd = pathlib.Path(runs_dir) if runs_dir else HERE / "runs"
    rd.mkdir(parents=True, exist_ok=True)
    eng = LiveEngine(cfg, runs_dir=rd, default_data_source=data_source)
    st = State(eng, rd, allow_synthetic)
    st.port = port
    return st


def main():
    ap = argparse.ArgumentParser(description="OpenKey Live 서버")
    ap.add_argument("--port", type=int, default=8460, help="8460~8469 권장(8443·8444는 사용자 서버)")
    ap.add_argument("--cert", default=str(ROOT / "work" / "live-capture-cert"), help="cert.pem·key.pem 폴더(읽기만 함)")
    ap.add_argument("--runs-dir", default=None, help="기록 폴더(기본 07-demo/openkey-live/runs)")
    ap.add_argument("--allow-synthetic", action="store_true", help="자동 시험용 합성 손끝 입력(/api/hand source=synthetic) 허용")
    ap.add_argument("--auto-click", choices=["auto", "on", "off"], default="auto", help="시연 보조 자동 누름(auto: 터치스크린이 아니면 켬)")
    ap.add_argument("--data-source", choices=["rehearsal", "field", "synthetic"], default="rehearsal", help="휴대폰 '시작'으로 연 시도의 기본 data_source")
    ap.add_argument("--http", action="store_true", help="인증서 없이 HTTP(시험용, 휴대폰 카메라는 안 켜짐)")
    a = ap.parse_args()
    ac = {"auto": None, "on": True, "off": False}[a.auto_click]
    st = build(a.port, a.runs_dir, a.allow_synthetic, ac, a.data_source)
    srv = Server(("0.0.0.0", a.port), make_handler(st))
    scheme = "http"
    if not a.http:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(pathlib.Path(a.cert) / "cert.pem", pathlib.Path(a.cert) / "key.pem")
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        scheme = "https"
    stop = threading.Event()
    threading.Thread(target=ticker, args=(st, stop), daemon=True).start()
    print(f"[live] 노트북 키오스크: {scheme}://localhost:{a.port}/kiosk-host", flush=True)
    for ip in lan_ips() or ["<노트북 IP>"]:
        print(f"[live] 휴대폰:          {scheme}://{ip}:{a.port}/phone", flush=True)
    print(f"[live] 관리자 콘솔:     {scheme}://localhost:{a.port}/admin/  |  상태: /api/live", flush=True)
    print(f"[live] 기록 폴더: {st.runs_dir}  (영상·사진·음성은 저장하지 않음)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        with st.lock:
            if st.engine.attempt:
                st.engine.end_attempt(time.monotonic(), "aborted")


if __name__ == "__main__":
    main()
