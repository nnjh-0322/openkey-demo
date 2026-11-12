"""관리자 콘솔 헤드리스 캡처 (모의 서버 + Edge headless).

실행: .\\.venv\\Scripts\\python.exe 07-demo/openkey-live/admin/dev/capture.py
결과: 07-demo/openkey-live/admin/captures/<상황>-<가로>x<세로>.png
모의 서버를 포트 8471에 직접 띄우고 끝나면 그 프로세스만 종료한다.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pwhelper  # noqa: E402  (한글 경로에서 드라이버가 죽는 문제 우회)

pwhelper.patch_driver()

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "captures"
PORT = 8471
BASE = f"http://127.0.0.1:{PORT}"
SIZES = [(960, 1080), (1366, 768), (1536, 864), (1920, 1080)]
# (상황, 크기 목록)
PLAN = [
    ("guiding", SIZES),
    ("idle", [(960, 1080), (1366, 768)]),
    ("hand_lost", [(960, 1080), (1366, 768)]),
    ("markers_low", [(960, 1080), (1366, 768)]),
    ("done", [(960, 1080), (1366, 768)]),
    ("schematic", [(960, 1080)]),
    ("camera_off", [(1366, 768)]),
    ("offline", [(1366, 768)]),
]


def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def wait_up():
    for _ in range(100):
        try:
            urllib.request.urlopen(BASE + "/api/live", timeout=1).read()
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("mock server did not start")


def main():
    only = set(sys.argv[1:])
    OUT.mkdir(exist_ok=True)
    proc = subprocess.Popen([sys.executable, str(HERE / "mock_server.py"), "--port", str(PORT), "--seed-attempts", "3"])
    try:
        wait_up()
        with sync_playwright() as p:
            br = p.chromium.launch(channel="msedge", headless=True)
            for name, sizes in PLAN:
                if only and name not in only:
                    continue
                for w, h in sizes:
                    post("/dev/scenario", {"name": "live" if name == "offline" else name})
                    ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, locale="ko-KR")
                    pg = ctx.new_page()
                    errors = []
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    pg.goto(BASE + "/admin/")
                    pg.wait_for_timeout(2200)
                    if name == "offline":
                        post("/dev/scenario", {"name": "offline"})
                        pg.wait_for_timeout(3000)
                    f = OUT / f"{name}-{w}x{h}.png"
                    pg.screenshot(path=str(f))
                    sw, sh = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.scrollHeight]")
                    print(f"{f.name}: scroll {sw}x{sh}{' ERR ' + '; '.join(errors) if errors else ''}", flush=True)
                    ctx.close()
                    if name == "offline":
                        post("/dev/scenario", {"name": "live"})
            br.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
