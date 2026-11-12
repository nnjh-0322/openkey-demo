"""손 인식 안정화 비교(합성 시험, 실제 휴대폰 측정 아님).

공개 손 사진(Wikimedia Commons, work/openkey-live/hands/ — 저장소 밖)을 kiosk-host 화면 캡처 위에 합성 →
원근 왜곡으로 '휴대폰이 찍은 것 같은' 프레임을 만들어 실제 경로로 넣는다:
  POST /api/frame(서버 마커 검출·호모그래피) → kiosk-host(MediaPipe 워커, 확대 인식) → POST /api/hand(서버가 키오스크 좌표로 변환)
결과는 /api/hand/recent 에서 읽는다(좌표만). 이미지는 메모리에서만 만들고 저장하지 않는다(--save-samples 때만 work/ 아래 몇 장).

실행(프로젝트 루트): .venv\\Scripts\\python.exe 07-demo\\openkey-live\\tests\\hand-eval\\eval_hands.py
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import pathlib
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote

import cv2
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
TESTS = HERE.parent
LIVE = TESTS.parent
ROOT = LIVE.parents[1]
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(LIVE))
from integration import Api, start_server, wait_kiosk  # noqa: E402

HANDS = ROOT / "work" / "openkey-live" / "hands"
# 사진별: 배경 종류, 손끝 방향(이미지 좌표 단위 벡터, 손끝이 가장 멀리 있는 방향)
PHOTOS = {
    "Index_finger_2.JPG": {"bg": "dark", "dir": (-0.85, -0.5)},
    "Index_finger___attention.JPG": {"bg": "white", "dir": (0, -1)},
    "Index_finger_down.JPG": {"bg": "white", "dir": (0.2, 1)},
    "Index_finger_front.JPG": {"bg": "white", "dir": (1, -0.1)},
    "Index_finger_open.JPG": {"bg": "white", "dir": (0.7, -0.6)},
    "Wijsvinger.jpg": {"bg": "dark", "dir": (0.45, -0.9)},
}
TARGETS = ["item-americano", "item-coldbrew", "checkout"]


def cutout(path, bg, direction):
    im = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)  # 한글 경로에서 cv2.imread 실패
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    if bg == "white":
        mask = ~((hsv[..., 2] > 215) & (hsv[..., 1] < 40))
    else:
        mask = hsv[..., 2] > 70
    mask = mask.astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = np.where(lab == k, 255, 0).astype(np.uint8)
    ys, xs = np.nonzero(mask)
    cx, cy = xs.mean(), ys.mean()
    d = np.array(direction, float)
    d /= np.linalg.norm(d)
    proj = (xs - cx) * d[0] + (ys - cy) * d[1]
    i = int(np.argmax(proj))
    tip = (float(xs[i]), float(ys[i]))
    return im, mask, (cx, cy), tip


def place_hand(screen, hand, scale_px, tip_xy, angle_jitter=0.0):
    """손을 회전(손끝이 위로)·축소해 손끝이 tip_xy에 오게 화면 캡처 위에 합성한다."""
    im, mask, c, tip = hand
    v = (tip[0] - c[0], tip[1] - c[1])
    ang = math.degrees(math.atan2(v[1], v[0])) + 90 + angle_jitter  # 손끝 → 위쪽
    L = math.hypot(*v)
    s = scale_px / L
    M = cv2.getRotationMatrix2D(tip, ang, s)
    M[0, 2] += tip_xy[0] - tip[0]
    M[1, 2] += tip_xy[1] - tip[1]
    H, W = screen.shape[:2]
    warped = cv2.warpAffine(im, M, (W, H), flags=cv2.INTER_AREA)
    wm = cv2.warpAffine(mask, M, (W, H), flags=cv2.INTER_LINEAR)
    wm = cv2.GaussianBlur(wm, (5, 5), 0).astype(np.float32)[..., None] / 255.0
    out = screen.astype(np.float32) * (1 - wm) + warped.astype(np.float32) * wm
    return out.astype(np.uint8)


def to_camera(screen, cam_w, cam_h, frac, tilt, rng):
    """노트북 화면 캡처를 휴대폰이 비스듬히 찍은 것처럼 카메라 프레임에 넣는다."""
    H, W = screen.shape[:2]
    sw = cam_w * frac
    sh = sw * H / W
    cx, cy = cam_w / 2 + rng.uniform(-0.04, 0.04) * cam_w, cam_h / 2 + rng.uniform(-0.03, 0.03) * cam_h
    top = sw * (1 - tilt)
    dst = np.float32([[cx - top / 2, cy - sh / 2], [cx + top / 2, cy - sh / 2], [cx + sw / 2, cy + sh / 2], [cx - sw / 2, cy + sh / 2]])
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    M = cv2.getPerspectiveTransform(src, dst)
    bg = np.full((cam_h, cam_w, 3), 70, np.uint8)
    bg = cv2.add(bg, rng.integers(0, 25, (cam_h, cam_w, 3), dtype=np.uint8))
    out = cv2.warpPerspective(screen, M, (cam_w, cam_h), dst=bg, borderMode=cv2.BORDER_TRANSPARENT)
    out = cv2.GaussianBlur(out, (3, 3), 0)
    out = cv2.convertScaleAbs(out, alpha=rng.uniform(0.85, 1.05), beta=rng.uniform(-10, 10))
    return out


def post_frame(api, img):
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    c = api._conn()
    c.request("POST", "/api/frame", body=jpg.tobytes(), headers={"Content-Type": "image/jpeg", "X-Meta": quote(json.dumps({"source": "synthetic-eval"}))})
    r = c.getresponse()
    return json.loads(r.read())


def result_for(api, seq, timeout=4.0):
    end = time.time() + timeout
    while time.time() < end:
        items = api.get(f"/api/hand/recent?after_seq={seq - 1}")["items"]
        for it in items:
            if it["seq"] == seq:
                return it
        time.sleep(0.03)
    return None


def set_cfg(api, cfg, det_changed):
    api.post("/api/settings", {"hand": cfg})
    time.sleep(6.0 if det_changed else 0.5)  # 기준값이 바뀌면 워커를 다시 만든다(모델 다시 읽음)


def run_config(api, name, cfg, frames, last_det):
    set_cfg(api, cfg, cfg["det"] != last_det)
    # 워커 준비 확인용 빈 프레임
    for _ in range(3):
        j = post_frame(api, frames[0]["blank"])
        result_for(api, j["seq"], 8.0)
    rows = []
    for fr in frames:
        for _ in range(2):  # 손 없는 프레임 2장: 앞 그림의 추적 상태를 끊는다(처음 찾기 시험)
            j = post_frame(api, fr["blank"])
            result_for(api, j["seq"])
        res = []
        for k in range(3):
            j = post_frame(api, fr["img"])
            r = result_for(api, j["seq"])
            res.append((j, r))
        first, third = res[0][1], res[2][1]

        def err(r):
            if not r or not r["tracked"]:
                return None
            return math.hypot(r["x"] - fr["gt"][0], r["y"] - fr["gt"][1])
        rows.append({"photo": fr["photo"], "dist": fr["dist"], "target": fr["target"], "markers": res[0][0].get("known_markers"),
                     "aligned": res[0][0].get("aligned"), "first": bool(first and first["tracked"]), "third": bool(third and third["tracked"]),
                     "err_first": err(first), "err_third": err(third), "model_ms": [r["model_ms"] for _, r in res if r],
                     "input": [(r["input_w"], r["input_h"]) for _, r in res if r][:1], "zoom": [r["zoom"] for _, r in res if r][:1],
                     "noresult": sum(1 for _, r in res if r is None)})
    return rows


def summarize(name, cfg, rows, cam):
    n = len(rows)
    f1 = sum(r["first"] for r in rows)
    f3 = sum(r["third"] for r in rows)
    errs = [r["err_third"] for r in rows if r["err_third"] is not None]
    hit = sum(1 for r in rows if r["err_third"] is not None and r["err_third"] < 0.03)
    ms = [m for r in rows for m in r["model_ms"]]
    inp = [r["input"][0] for r in rows if r["input"]]
    by = {}
    for d in ("near", "far"):
        rr = [r for r in rows if r["dist"] == d]
        by[d] = (sum(r["first"] for r in rr), sum(r["third"] for r in rr), len(rr))
    return {"name": name, "cfg": cfg, "cam": cam, "n": n, "first": f1, "third": f3, "near": by["near"], "far": by["far"],
            "err_med": float(np.median(errs)) if errs else None, "err_max": max(errs) if errs else None, "hit3": hit,
            "model_ms_med": float(np.median(ms)) if ms else None,
            "input_med": f"{int(np.median([a for a, b in inp]))}×{int(np.median([b for a, b in inp]))}" if inp else "-",
            "markers_min": min(r["markers"] or 0 for r in rows), "noresult": sum(r["noresult"] for r in rows)}


def build_frames(screen, stage, regions, cam_w, cam_h, seed, scale_frac=0.30, angle=0.0, dists=("near", "far")):
    rng = np.random.default_rng(seed)
    regs = {r["id"]: r for r in regions}
    frames = []
    H = screen.shape[0]
    for photo, spec in PHOTOS.items():
        hand = cutout(HANDS / photo, spec["bg"], spec["dir"])
        for dist in dists:
            frac = 0.78 if dist == "near" else 0.45
            for t in TARGETS:
                b = regs[t]["bbox"]
                gt = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
                tip_xy = (stage["x"] + gt[0] * stage["w"], stage["y"] + gt[1] * stage["h"])
                comp = place_hand(screen, hand, scale_frac * H, tip_xy, angle_jitter=rng.uniform(-15, 15) + angle)
                st = rng.integers(0, 10 ** 6)
                img = to_camera(comp, cam_w, cam_h, frac, 0.10, np.random.default_rng(st))
                blank = to_camera(screen, cam_w, cam_h, frac, 0.10, np.random.default_rng(st))
                frames.append({"photo": photo, "dist": dist, "target": t, "gt": gt, "img": img, "blank": blank})
    return frames


def rescan_test(api, screen, stage, regions, cam_w, cam_h, rescan):
    """손이 크게 찍혀(휴대폰 가까이) 손바닥 대부분이 확대 영역 밖에 있는 경우: 12장 연속에서 찾는지."""
    api.post("/api/settings", {"hand": {"zoom": True, "det": 0.35, "rescan": rescan, "max_side": 0}})
    time.sleep(0.5)
    regs = {r["id"]: r for r in regions}
    out = []
    for photo in ("Wijsvinger.jpg", "Index_finger_open.JPG", "Index_finger___attention.JPG"):
        spec = PHOTOS[photo]
        hand = cutout(HANDS / photo, spec["bg"], spec["dir"])
        b = regs["checkout"]["bbox"]
        gt = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        tip_xy = (stage["x"] + gt[0] * stage["w"], stage["y"] + gt[1] * stage["h"])
        comp = place_hand(screen, hand, 1.1 * screen.shape[0], tip_xy)
        rng = np.random.default_rng(5)
        img = to_camera(comp, cam_w, cam_h, 0.45, 0.10, rng)
        blank = to_camera(screen, cam_w, cam_h, 0.45, 0.10, np.random.default_rng(5))
        for _ in range(2):
            j = post_frame(api, blank)
            result_for(api, j["seq"])
        found_at = None
        zooms = []
        for k in range(12):
            j = post_frame(api, img)
            r = result_for(api, j["seq"])
            zooms.append("R" if r and r["rescan"] else ("Z" if r and r["zoom"] else "F"))
            if r and r["tracked"] and found_at is None:
                found_at = k + 1
        out.append({"photo": photo, "found_at": found_at, "pattern": "".join(zooms)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8464)
    ap.add_argument("--save-samples", action="store_true")
    a = ap.parse_args()
    import pw_driver
    pw_driver.patch()
    from playwright.sync_api import sync_playwright
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="openkey-hand-"))
    proc, api = start_server(a.port, tmp / "runs", tmp / "server.log")
    results, rescan = [], {}
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(channel="msedge", headless=True, args=["--ignore-certificate-errors"])
            page = br.new_context(viewport={"width": 1600, "height": 900}, ignore_https_errors=True).new_page()
            page.goto(f"https://localhost:{a.port}/kiosk-host?layout=B&screen=menu&voice=0")
            live = wait_kiosk(api, screen="menu")
            time.sleep(4)  # 모델 준비
            page.evaluate("document.getElementById('side').style.display='none'")
            png = page.screenshot()
            screen = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
            stage = page.evaluate("""() => { const f = document.getElementById('k'); const s = f.contentDocument.getElementById('stage').getBoundingClientRect(); return {x: s.left, y: s.top, w: s.width, h: s.height}; }""")
            regions = live["kiosk"]["regions"]
            fr1280 = build_frames(screen, stage, regions, 1280, 720, seed=11)
            fr720 = build_frames(screen, stage, regions, 720, 405, seed=11)
            if a.save_samples:
                sd = ROOT / "work" / "openkey-live" / "hand-eval-samples"
                sd.mkdir(parents=True, exist_ok=True)
                for i in (0, 3, 9, 15):
                    cv2.imencode(".jpg", fr1280[i]["img"])[1].tofile(str(sd / f"sample-{i}.jpg"))
            configs = [
                ("C1 기본(확대 켬·기준 0.35·재탐색)", {"zoom": True, "det": 0.35, "rescan": True, "max_side": 0}, fr1280, "1280×720"),
                ("C2 확대 끔·기준 0.35", {"zoom": False, "det": 0.35, "rescan": True, "max_side": 0}, fr1280, "1280×720"),
                ("C3 확대 켬·기준 0.6", {"zoom": True, "det": 0.6, "rescan": True, "max_side": 0}, fr1280, "1280×720"),
                ("C4 확대 끔·기준 0.6(03-software 원래 값)", {"zoom": False, "det": 0.6, "rescan": True, "max_side": 0}, fr1280, "1280×720"),
                ("C5 확대 켬·기준 0.35·카메라 720", {"zoom": True, "det": 0.35, "rescan": True, "max_side": 0}, fr720, "720×405"),
                ("C6 확대 끔·기준 0.35·카메라 720", {"zoom": False, "det": 0.35, "rescan": True, "max_side": 0}, fr720, "720×405"),
                ("C7 확대 켬·기준 0.25", {"zoom": True, "det": 0.25, "rescan": True, "max_side": 0}, fr1280, "1280×720"),
            ]
            last_det = 0.35
            for name, cfg, frames, cam in configs:
                t0 = time.time()
                rows = run_config(api, name, cfg, frames, last_det)
                last_det = cfg["det"]
                s = summarize(name, cfg, rows, cam)
                s["wall_s"] = round(time.time() - t0, 1)
                s["rows"] = rows
                results.append(s)
                print(f"{name}: 첫 장 {s['first']}/{s['n']} 셋째 장 {s['third']}/{s['n']} 오차중앙 {s['err_med']} 모델 {s['model_ms_med']}ms 입력 {s['input_med']}", flush=True)
            api.post("/api/settings", {"hand": {"det": 0.35}})
            time.sleep(6)
            rescan["on"] = rescan_test(api, screen, stage, regions, 1280, 720, True)
            rescan["off"] = rescan_test(api, screen, stage, regions, 1280, 720, False)
            print("rescan", rescan, flush=True)
            br.close()
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
    (ROOT / "work" / "openkey-live").mkdir(parents=True, exist_ok=True)
    (ROOT / "work" / "openkey-live" / "hand-eval-raw.json").write_text(json.dumps({"results": results, "rescan": rescan}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    write_report(results, rescan)


def write_report(results, rescan):
    L = ["# 손 인식 안정화 비교 (합성 시험)", "",
         f"실행: {datetime.datetime.now().astimezone():%Y-%m-%d %H:%M} / A. 명령: `.venv\\Scripts\\python.exe 07-demo\\openkey-live\\tests\\hand-eval\\eval_hands.py`", "",
         "**합성 시험이며 실제 휴대폰 측정이 아니다.** 공개 손 사진 6장([SOURCES.md](SOURCES.md))을 잘라 kiosk-host 화면 캡처(배치 B 메뉴, 1600×900, 마커 포함) 위에 합성하고,",
         "원근 왜곡(위쪽 10% 좁힘)·흐림·밝기 변화를 줘서 '휴대폰 카메라 프레임'처럼 만들었다. 실제 경로 그대로 넣었다: `POST /api/frame`(서버 ArUco·호모그래피) → kiosk-host MediaPipe 워커(확대 인식) → `POST /api/hand`(서버가 키오스크 좌표로 변환).",
         "사진 속 손은 평면에 붙인 것이라 실제 손의 그림자·시차·움직임 흐림·화면 반사·모아레가 없다. 손 크기는 손끝~손 중심 거리 = 화면 캡처 높이의 30%로 고정.",
         "", "조건: 사진 6장 × 거리 2(near: 화면이 카메라 폭의 78% / far: 45%) × 목표 3곳(아메리카노·콜드브루·결제하기) = 36장. 각 장 앞에 손 없는 프레임 2장을 넣어 추적을 끊고(처음 찾기), 같은 장을 3번 보냈다(첫 장 = 처음 찾기, 셋째 장 = 추적 포함).",
         "정답 손끝 = 목표 버튼 중심(합성 때 손끝을 그 점에 둠). 오차 = 키오스크 정규 좌표 거리(화면 폭·높이 비율). '버튼 안'은 오차 < 0.03.", "",
         "| 조건 | 카메라 | 첫 장 검출 | 셋째 장 검출 | near(첫/셋째) | far(첫/셋째) | 손끝 오차 중앙값 | 최대 | 오차<0.03 | 모델 시간 중앙값 | 손 인식 입력(중앙값) | 결과 없음 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for s in results:
        em = "-" if s["err_med"] is None else f"{s['err_med']:.4f}"
        ex = "-" if s["err_max"] is None else f"{s['err_max']:.3f}"
        mm = "-" if s["model_ms_med"] is None else f"{round(s['model_ms_med'])}ms"
        L.append(f"| {s['name']} | {s['cam']} | {s['first']}/{s['n']} | {s['third']}/{s['n']} | {s['near'][0]}/{s['near'][1]} of {s['near'][2]} | "
                 f"{s['far'][0]}/{s['far'][1]} of {s['far'][2]} | {em} | {ex} | {s['hit3']}/{s['n']} | {mm} | {s['input_med']} | {s['noresult']} |")
    L += ["", "사진별 검출(셋째 장, C1 기본 / C2 확대 끔):", "", "| 사진 | C1 | C2 |", "| --- | --- | --- |"]
    if len(results) >= 2:
        for ph in PHOTOS:
            a = sum(r["third"] for r in results[0]["rows"] if r["photo"] == ph)
            b = sum(r["third"] for r in results[1]["rows"] if r["photo"] == ph)
            L.append(f"| {ph} | {a}/6 | {b}/6 |")
    L += ["", "## 손 놓친 뒤 전체 화면 재탐색", "",
          "손을 매우 크게 합성해(휴대폰에 가까운 손, 손끝~중심 = 화면 높이의 110%) 손바닥 대부분이 확대 영역 밖에 있게 했다. 12장 연속에서 처음 찾은 장 번호. 패턴: Z=확대 입력, R=전체 화면 재탐색, F=전체 화면.", "",
          "| 사진 | 재탐색 켬 | 패턴 | 재탐색 끔 | 패턴 |", "| --- | --- | --- | --- | --- |"]
    for on, off in zip(rescan.get("on", []), rescan.get("off", [])):
        L.append(f"| {on['photo']} | {on['found_at'] or '못 찾음'} | `{on['pattern']}` | {off['found_at'] or '못 찾음'} | `{off['pattern']}` |")
    L += ["", "## 해석(AI 판단, 합성 시험 한계 안에서)", "", "_아래는 표를 보고 쓴 것이다. 실제 휴대폰 시험([PHONE-TEST.md](../../PHONE-TEST.md) 2절)에서 `perf` 기록으로 다시 확인해야 한다._", ""]
    (HERE / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
