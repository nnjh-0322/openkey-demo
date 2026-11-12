"""통합 시험: 실제 server.py + headless Edge로 띄운 kiosk-host(진짜 MORU 키오스크) + 합성 손끝 입력.

합성 사용자(tests/sim.py)는 버튼 좌표를 모르고 휴대폰이 받는 말하기 큐(/api/say)만 듣고 움직인다.
누름은 (a) Playwright 실제 포인터 입력(page.mouse.click) 또는 (b) 서버 자동 누름 명령(kiosk-host 실행)으로 한다.
실제 휴대폰·카메라·사람 손은 쓰지 않는다(가상 시험).

실행(프로젝트 루트):
    .venv\\Scripts\\python.exe 07-demo\\openkey-live\\tests\\integration.py              # 임시 폴더에 기록
    .venv\\Scripts\\python.exe 07-demo\\openkey-live\\tests\\integration.py --write-examples   # runs/examples/ + tests/INTEGRATION-RESULT.md 갱신
"""
from __future__ import annotations

import argparse
import datetime
import http.client
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
LIVE = HERE.parent
ROOT = LIVE.parents[1]
sys.path.insert(0, str(LIVE))
sys.path.insert(0, str(HERE))

from engine.checks import guide_sequence, press_safety_violations, schema_errors  # noqa: E402
from sim import SimUser  # noqa: E402

PY = ROOT / ".venv" / "Scripts" / "python.exe"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CTX = ssl._create_unverified_context()


class Api:
    def __init__(self, port):
        self.port = port
        self.c = None

    def _conn(self):
        if self.c is None:
            self.c = http.client.HTTPSConnection("localhost", self.port, context=CTX, timeout=10)
        return self.c

    def req(self, method, path, body=None):
        for attempt in range(3):
            try:
                c = self._conn()
                data = json.dumps(body).encode() if body is not None else None
                c.request(method, path, body=data, headers={"Content-Type": "application/json"} if data else {})
                r = c.getresponse()
                raw = r.read()
                if r.status == 204:
                    return None
                return json.loads(raw) if raw and r.getheader("Content-Type", "").startswith("application/json") else raw
            except (http.client.HTTPException, ConnectionError, OSError):
                self.c = None
                if attempt == 2:
                    raise
                time.sleep(0.2)

    def get(self, p):
        return self.req("GET", p)

    def post(self, p, b):
        return self.req("POST", p, b)


def start_server(port, runs_dir, log_path):
    args = [str(PY), str(LIVE / "server.py"), "--port", str(port), "--allow-synthetic", "--runs-dir", str(runs_dir), "--data-source", "synthetic"]
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    fh = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(args, stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT), env=env)
    api = Api(port)
    for _ in range(60):
        try:
            if api.get("/api/health"):
                return proc, api
        except Exception:
            time.sleep(0.25)
    proc.kill()
    raise RuntimeError("서버가 뜨지 않음: " + log_path.read_text(encoding="utf-8"))


def stage_rect(page):
    return page.evaluate("""() => { const f = document.getElementById('k'); const s = f.contentDocument.getElementById('stage').getBoundingClientRect();
        const fr = f.getBoundingClientRect(); return {x: fr.left + s.left, y: fr.top + s.top, w: s.width, h: s.height}; }""")


def wait_kiosk(api, layout=None, screen=None, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        live = api.get("/api/live")
        k = live.get("kiosk")
        if k and k["connected"] and (layout is None or k["layout"] == layout) and (screen is None or k["screen"] == screen):
            return live
        time.sleep(0.2)
    raise RuntimeError(f"키오스크 연결 대기 시간 초과 layout={layout} screen={screen}")


def run_scenario(api, page, name, layout, auto, goal="iced-americano-1", wrong_on=None, hide_on=None, max_s=150, seed=1):
    """한 시도를 끝까지 돌린다. wrong_on: 그 화면 안내를 들으면 일부러 다른 버튼을 누름. hide_on: 그 화면 첫 HOLD에서 2.5초 손을 숨김."""
    api.post("/api/settings", {"auto_click": auto, "laptop_voice": "off"})
    api.post("/api/attempt/start", {"conditions": {"layout": layout, "guidance": "on", "blindfold": "unknown", "operator_note": f"자동 시험 {name}"},
                                    "goal_id": goal, "data_source": "synthetic", "reset_kiosk": True})
    wait_kiosk(api, layout=layout, screen="start")
    user = SimUser(start=(0.5, 0.75), seed=seed)
    say_n = api.get("/api/say?ch=test&after=0&wait=0")["n"] - 2  # 시작 안내부터 듣는다
    t_start = time.time()
    dt = 0.05
    wrong_done = hide_done = False
    pending_wrong = None
    cur_screen = None
    hold_seen_on = set()
    clicks = []
    while time.time() - t_start < max_s:
        t0 = time.time()
        now = t0
        j = api.get(f"/api/say?ch=test&after={max(0, say_n)}&wait=0")
        for it in j["items"]:
            if it["n"] <= say_n:
                continue
            say_n = it["n"]
            user.hear(now, it)
            if it["code"] == "SCREEN" and wrong_on and not wrong_done and cur_screen == wrong_on:
                pending_wrong = now + 0.8
            if it["code"] == "HOLD" and hide_on and not hide_done and cur_screen == hide_on and cur_screen not in hold_seen_on:
                hold_seen_on.add(cur_screen)
                user.hide_until = now + 2.5
                hide_done = True
        live = api.get("/api/live")
        if live["attempt"] is None:
            break
        cur_screen = (live.get("kiosk") or {}).get("screen")
        user.update(now, dt)
        if user.visible(now):
            api.post("/api/hand", {"source": "synthetic", "tracked": True, "x": user.p[0], "y": user.p[1], "aligned": True, "count": 1})
        else:
            api.post("/api/hand", {"source": "synthetic", "tracked": False, "aligned": True})
        if pending_wrong and now >= pending_wrong:
            pending_wrong = None
            wrong_done = True
            regs = {r["id"]: r for r in live["kiosk"]["regions"]}
            tgt = (live.get("target") or {}).get("id")
            wrong = next((rid for rid in ("item-latte", "item-vanilla", "item-caramel") if rid in regs and rid != tgt), None)
            b = regs[wrong]["bbox"]
            sr = stage_rect(page)
            page.mouse.click(sr["x"] + (b[0] + b[2]) / 2 * sr["w"], sr["y"] + (b[1] + b[3]) / 2 * sr["h"])
            clicks.append(("wrong", wrong))
            user.p = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]
        if not auto and user.take_press():
            sr = stage_rect(page)
            page.mouse.click(sr["x"] + user.p[0] * sr["w"], sr["y"] + user.p[1] * sr["h"])
            clicks.append(("press", round(user.p[0], 3), round(user.p[1], 3)))
        elif auto:
            user.take_press()
        spent = time.time() - t0
        if spent < dt:
            time.sleep(dt - spent)
    live = api.get("/api/live")
    if live["attempt"] is not None:
        api.post("/api/attempt/end", {"reason": "timeout"})
        live = api.get("/api/live")
    return live["last_attempt"], user, clicks


def load(path):
    return [json.loads(x) for x in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def check(name, recs, expect):
    res = {"name": name, "ok": True, "problems": []}

    def need(cond, msg):
        if not cond:
            res["ok"] = False
            res["problems"].append(msg)

    end = recs[-1]
    need(end["kind"] == "attempt_end" and end["completed"] and end["end_reason"] == "done", "주문 번호까지 완료 못 함")
    need(end.get("order_no") is not None, "주문 번호 없음")
    need(schema_errors(recs) == [], f"형식 오류 {schema_errors(recs)[:3]}")
    need(press_safety_violations(recs) == [], f"PRESS 안전 위반 {press_safety_violations(recs)[:3]}")
    seq = guide_sequence(recs)
    for code in ("SCREEN", "PRESS", "PRESS_OK", "PAY_CHECK", "DONE"):
        need(code in seq, f"안내 {code} 없음")
    presses = [r for r in recs if r["kind"] == "press"]
    need([s["name"] for s in recs if s["kind"] == "step_done"] == ["menu", "option", "confirm", "pay", "done"], "단계 기록 순서 다름")
    if expect.get("source"):
        need({p["source"] for p in presses if p["result"] == "correct"} == {expect["source"]}, f"누름 경로가 {expect['source']}가 아님")
    if expect.get("hand_down"):
        need(any(r["kind"] == "hand_down_request" and r["reason"] == "payment_check" for r in recs), "결제 화면 손 내림 요청 없음")
        need(any(r["kind"] == "hand_down_done" for r in recs), "손 내림 확인 없음")
    if expect.get("wrong"):
        need(any(p["result"] == "wrong" for p in presses), "잘못 누름 기록 없음")
        need("PRESS_WRONG" in seq, "PRESS_WRONG 안내 없음")
        need(any(r["kind"] == "revert" and r["reason"] == "wrong_press" for r in recs), "되돌림 기록 없음")
        wr = [r for r in recs if r["kind"] == "guide" and r["code"] == "PRESS_WRONG"]
        need(any("돌아가요" in r["text"] for r in wr), "되돌림 안내 문구 없음")
    if expect.get("hand_lost"):
        need(any(r["kind"] == "hand_lost" for r in recs), "손 놓침 기록 없음")
        need("HAND_LOST" in seq, "손 놓침 안내 없음")
        # 손 놓침 ~ 다시 찾음 사이에는 PRESS가 없어야 한다
        lost = False
        for r in recs:
            if r["kind"] == "hand_lost":
                lost = True
            elif r["kind"] == "hand_found":
                lost = False
            elif r["kind"] == "guide" and r["code"] == "PRESS" and not r.get("suppressed"):
                need(not lost, f"손 놓침 중 PRESS(seq {r['seq']})")
    res["seq"] = guide_sequence(recs, with_text=True)
    res["summary"] = {"total_ms": end["total_ms"], "order_no": end.get("order_no"), "counts": end["counts"],
                      "presses": [(p["hit_id"], p["result"], p["source"]) for p in presses], "attempt": end["attempt"]}
    return res


SCENARIOS = [
    {"name": "B-direct", "layout": "B", "auto": False, "expect": {"source": "direct", "hand_down": True}, "title": "배치 B · 실제 포인터 입력으로 누름"},
    {"name": "A-direct", "layout": "A", "auto": False, "expect": {"source": "direct", "hand_down": True}, "title": "배치 A · 실제 포인터 입력으로 누름"},
    {"name": "B-auto", "layout": "B", "auto": True, "expect": {"source": "auto_click", "hand_down": True}, "title": "배치 B · 시연 보조 자동 누름"},
    {"name": "A-auto", "layout": "A", "auto": True, "expect": {"source": "auto_click", "hand_down": True}, "title": "배치 A · 시연 보조 자동 누름"},
    {"name": "B-wrong-press", "layout": "B", "auto": False, "wrong_on": "menu", "expect": {"wrong": True}, "title": "배치 B · 메뉴에서 일부러 다른 메뉴(카페라떼) 누름 → 알림 → 되돌림"},
    {"name": "A-hand-lost", "layout": "A", "auto": False, "hide_on": "menu+option", "expect": {"hand_lost": True}, "title": "배치 A · 옵션 화면 '멈추세요' 직후 손 2.5초 사라짐"},
]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8462)
    ap.add_argument("--write-examples", action="store_true")
    ap.add_argument("--only", default=None, help="쉼표로 구분한 시나리오 이름")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args(argv)
    import pw_driver
    pw_driver.patch()
    from playwright.sync_api import sync_playwright

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="openkey-int-"))
    runs = tmp / "runs"
    proc, api = start_server(a.port, runs, tmp / "server.log")
    results = []
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(channel="msedge", headless=not a.headed, args=["--ignore-certificate-errors", "--autoplay-policy=no-user-gesture-required"])
            ctxb = br.new_context(viewport={"width": 1600, "height": 900}, ignore_https_errors=True)
            page = ctxb.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"https://localhost:{a.port}/kiosk-host?layout=B")
            wait_kiosk(api)
            for sc in SCENARIOS:
                if a.only and sc["name"] not in a.only.split(","):
                    continue
                t0 = time.time()
                summ, user, clicks = run_scenario(api, page, sc["name"], sc["layout"], sc["auto"], wrong_on=sc.get("wrong_on"), hide_on=sc.get("hide_on"))
                recs = load(summ["path"])
                r = check(sc["name"], recs, sc["expect"])
                r.update(title=sc["title"], wall_s=round(time.time() - t0, 1), path=summ["path"], clicks=clicks)
                results.append(r)
                print(f"[{'통과' if r['ok'] else '실패'}] {sc['name']} {r['wall_s']}s {r['problems']}", flush=True)
            r_err = list(errors)
            ctxb.close()
            br.close()
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
    if a.write_examples:
        ex = LIVE / "runs" / "examples"
        ex.mkdir(parents=True, exist_ok=True)
        for old in ex.glob("*.jsonl"):
            old.unlink()
        for r in results:
            dst = ex / f"{pathlib.Path(r['path']).stem}.jsonl"
            shutil.copy(r["path"], dst)
            r["example"] = f"runs/examples/{dst.name}"
        write_report(results, r_err)
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"passed": sum(r["ok"] for r in results), "total": len(results), "page_errors": r_err}, ensure_ascii=False))
    return results, r_err


def write_report(results, page_errors):
    lines = ["# 통합 시험 결과 (가상 시험)", "",
             f"실행: {datetime.datetime.now().astimezone():%Y-%m-%d %H:%M} / A(안내 실행부). 명령: `.venv\\Scripts\\python.exe 07-demo\\openkey-live\\tests\\integration.py --write-examples`", "",
             "**가상 시험**이다: 실제 `server.py` + headless Edge의 `kiosk-host.html`(진짜 MORU 키오스크가 화면 전환) + 합성 손끝 좌표(`/api/hand` source=synthetic, 키오스크 정규 좌표 직접 주입).",
             "합성 사용자(`tests/sim.py`)는 버튼 좌표를 모르고 말하기 큐의 안내 코드만 듣고 움직인다(속도·반응 지연은 임의 값). 카메라·MediaPipe·실제 휴대폰·사람은 쓰지 않았다.",
             "누름 경로: `direct`는 Playwright `page.mouse.click`(실제 포인터 이벤트), `auto_click`은 서버 자동 누름 명령을 kiosk-host가 실행한 것(시연 보조).",
             "키오스크는 `fixed=1`(타이머 정지·주문 번호 27 고정)이고 결제는 간편결제(모의)를 목표로 한다. 카드 화면은 `fixed=1`에서 자동 승인되지 않기 때문이다.", "",
             f"결과: **{sum(r['ok'] for r in results)}/{len(results)} 통과**. 페이지 오류: {len(page_errors)}건{(' — ' + '; '.join(page_errors[:3])) if page_errors else ''}", "",
             "| 시나리오 | 결과 | 소요(벽시계) | 기록 시간 | 누름(버튼, 결과, 경로) | 안내 수 | 기록 파일 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        s = r["summary"]
        pr = ", ".join(f"{h}/{res}/{src}" for h, res, src in s["presses"])
        lines.append(f"| {r['title']} | {'통과' if r['ok'] else '실패: ' + '; '.join(r['problems'])} | {r['wall_s']}s | {s['total_ms'] / 1000:.1f}s | {pr} | {s['counts']['guides']} | `{r.get('example', '')}` |")
    lines += ["", "확인 항목(각 시나리오 공통): 주문 번호까지 완료, SCHEMA v1 필드·허용값(`engine/checks.py schema_errors`), PRESS 안전 규칙(`press_safety_violations`: 손 놓침 중·위치 맞춤 무효 중·현재 목표 아닌 PRESS 없음),",
              "안내 SCREEN·PRESS·PRESS_OK·PAY_CHECK·DONE 포함, step_done 순서 menu→option→confirm→pay→done. 시나리오별: 누름 경로, 결제 화면 손 내림 요청·확인, 잘못 누름 알림·되돌림, 손 놓침 중 PRESS 없음.", ""]
    for r in results:
        lines += [f"## {r['title']}", "", f"시도 `{r['summary']['attempt']}` · 주문 번호 {r['summary']['order_no']} · 카운트 `{json.dumps(r['summary']['counts'], ensure_ascii=False)}`", "",
                  "안내 문구 순서(실제로 낸 말만, 억제된 말 제외):", ""]
        for i, (code, text) in enumerate(r["seq"], 1):
            lines.append(f"{i}. `{code}` {text}")
        lines.append("")
    (HERE / "INTEGRATION-RESULT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    res, errs = main()
    sys.exit(0 if res and all(r["ok"] for r in res) and not errs else 1)
