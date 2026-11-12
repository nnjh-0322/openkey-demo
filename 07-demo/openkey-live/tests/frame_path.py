"""합성 '카메라 프레임' 경로 종단 시험 1건(가상 시험).

좌표 주입 없이 실제 카메라 경로만 쓴다: 손 사진을 합성한 프레임 → POST /api/frame(서버 ArUco·호모그래피)
→ kiosk-host MediaPipe 워커 → POST /api/hand → 엔진(방향·머묾·PRESS) → 자동 누름 명령 → MORU 키오스크 화면 전환.
서버는 --allow-synthetic 으로 켜지만 이 시험은 합성 좌표(/api/hand source=synthetic)를 보내지 않는다.
손 사진은 work/openkey-live/hands/(저장소 밖). 실제 휴대폰·실제 손이 아니다.

실행: .venv\\Scripts\\python.exe 07-demo\\openkey-live\\tests\\frame_path.py
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
LIVE = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "hand-eval"))
sys.path.insert(0, str(LIVE))
import eval_hands as E  # noqa: E402
from engine.checks import guide_sequence, press_safety_violations, schema_errors  # noqa: E402
from integration import load, start_server, wait_kiosk  # noqa: E402


def main(port=8465, photo="Index_finger_open.JPG", max_s=45):
    import pw_driver
    pw_driver.patch()
    from playwright.sync_api import sync_playwright
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="openkey-frame-"))
    proc, api = start_server(port, tmp / "runs", tmp / "server.log")
    out = {"ok": False}
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(channel="msedge", headless=True, args=["--ignore-certificate-errors"])
            page = br.new_context(viewport={"width": 1600, "height": 900}, ignore_https_errors=True).new_page()
            page.goto(f"https://localhost:{port}/kiosk-host?layout=B")
            wait_kiosk(api)
            time.sleep(4)  # 손 인식 모델 준비
            api.post("/api/settings", {"auto_click": True, "laptop_voice": "off"})
            api.post("/api/attempt/start", {"conditions": {"layout": "B", "operator_note": "합성 카메라 프레임 경로 시험"}, "goal_id": "iced-americano-1",
                                            "data_source": "synthetic", "reset_kiosk": True})
            live = wait_kiosk(api, layout="B", screen="start")
            page.evaluate("document.getElementById('side').style.display='none'")
            screen = cv2.imdecode(np.frombuffer(page.screenshot(), np.uint8), cv2.IMREAD_COLOR)
            page.evaluate("document.getElementById('side').style.display=''")
            stage = page.evaluate("""() => { const f = document.getElementById('k'); const s = f.contentDocument.getElementById('stage').getBoundingClientRect(); return {x: s.left, y: s.top, w: s.width, h: s.height}; }""")
            regs = {r["id"]: r for r in live["kiosk"]["regions"]}
            b = regs["dine-store"]["bbox"]
            gt = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            spec = E.PHOTOS[photo]
            hand = E.cutout(E.HANDS / photo, spec["bg"], spec["dir"])
            comp = E.place_hand(screen, hand, 0.30 * screen.shape[0], (stage["x"] + gt[0] * stage["w"], stage["y"] + gt[1] * stage["h"]))
            t0 = time.time()
            k = 0
            tracked_n = sent = 0
            while time.time() - t0 < max_s:
                img = E.to_camera(comp, 1280, 720, 0.78, 0.10, np.random.default_rng(100 + k))  # 매 장 조금씩 다른 잡음·밝기
                k += 1
                E.post_frame(api, img)
                sent += 1
                live = api.get("/api/live")
                if live["finger"]["tracked"]:
                    tracked_n += 1
                if live["kiosk"]["screen"] != "start" or live["attempt"] is None:
                    break
                time.sleep(0.1)
            api.post("/api/attempt/end", {"reason": "aborted"})
            live = api.get("/api/live")
            recs = load(live["last_attempt"]["path"])
            presses = [r for r in recs if r["kind"] == "press"]
            seq = guide_sequence(recs, with_text=True)
            fingers = [r for r in recs if r["kind"] == "finger"]
            out = {"photo": photo, "frames_sent": sent, "live_tracked_polls": tracked_n, "seconds": round(time.time() - t0, 1),
                   "press": [(p["hit_id"], p["result"], p["source"], p["screen"], p["next_screen"]) for p in presses],
                   "guides": seq, "finger_samples": len(fingers),
                   "finger_err_med": float(np.median([np.hypot(f["x"] - gt[0], f["y"] - gt[1]) for f in fingers])) if fingers else None,
                   "perf": [r for r in recs if r["kind"] == "perf"][-1:] or None,
                   "schema_errors": schema_errors(recs), "safety_violations": press_safety_violations(recs)}
            out["ok"] = bool(presses) and presses[0]["result"] == "correct" and presses[0]["source"] == "auto_click" \
                and presses[0]["next_screen"] == "menu" and any(c == "PRESS" for c, _ in seq) and not out["safety_violations"]
            br.close()
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return out


if __name__ == "__main__":
    photo = sys.argv[1] if len(sys.argv) > 1 else "Index_finger_open.JPG"
    r = main(photo=photo)
    sys.exit(0 if r.get("ok") else 1)
