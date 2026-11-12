"""관리자 콘솔 자동 시험 (모의 서버 + Edge headless).

실행: .\\.venv\\Scripts\\python.exe -m pytest 07-demo/openkey-live/admin/dev/test_admin.py -q
콘솔 조작만으로 시도 시작 → 진행 → 종료 → 기록 내려받기(JSONL/CSV/JSON)까지 확인한다.
모의 서버는 포트 8472에 직접 띄우고 시험이 끝나면 그 프로세스만 종료한다. 실제 서버(8460)는 시험하지 않는다.
"""
import csv
import io
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pwhelper  # noqa: E402

pwhelper.patch_driver()

PORT = 8472
BASE = f"http://127.0.0.1:{PORT}"


def api(path, body=None):
    if body is None:
        return json.loads(urllib.request.urlopen(BASE + path, timeout=5).read())
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


@pytest.fixture(scope="module")
def server():
    proc = subprocess.Popen([sys.executable, str(HERE / "mock_server.py"), "--port", str(PORT), "--speed", "4", "--seed-attempts", "0"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            api("/api/live")
            break
        except Exception:
            time.sleep(0.1)
    yield proc
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def browser(server):
    p = sync_playwright().start()
    br = p.chromium.launch(channel="msedge", headless=True)
    yield br
    # 내려받기를 한 뒤에는 이 환경의 Playwright 드라이버가 종료 중 TargetClosedError를 내며 먼저 끝날 수 있다.
    # 시험 결과와 무관한 정리 단계 오류라서 무시한다(브라우저는 드라이버와 함께 종료됨).
    for close in (br.close, p.stop):
        try:
            close()
        except Exception:
            pass


@pytest.fixture(scope="module")
def page(browser):
    # Playwright 1.49 + 이 환경에서는 내려받기 뒤 context.close()가 멈추는 문제가 있어(2026-11-08 기록)
    # 페이지 하나를 모든 시험이 함께 쓰고 닫기는 브라우저 종료에 맡긴다.
    ctx = browser.new_context(viewport={"width": 1366, "height": 768}, accept_downloads=True, locale="ko-KR")
    ctx.set_default_timeout(15000)
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(BASE + "/admin/")
    expect(pg.locator("#conn")).to_have_text("서버 연결됨", timeout=5000)
    yield pg


def test_abort_needs_confirm(page):
    pg = page
    expect(pg.locator("#pastBody")).to_contain_text("아직 기록된 시도가 없습니다")
    pg.select_option("#fSource", "synthetic")
    pg.fill("#fCode", "P08")
    pg.click("#btnStart")
    expect(pg.locator("#running")).to_be_visible(timeout=5000)
    pg.click("#btnEnd")
    expect(pg.locator("#endConfirm")).to_be_visible()
    pg.keyboard.press("Escape")  # 취소하면 계속 진행
    expect(pg.locator("#endConfirm")).to_be_hidden()
    assert api("/api/live")["attempt"] is not None
    pg.click("#btnEnd")
    pg.click("#btnEndAbort")
    expect(pg.locator("#startForm")).to_be_visible(timeout=5000)
    last = [x for x in api("/api/attempts")["attempts"] if x["conditions"]["participant_code"] == "P08"][0]
    assert last["end_reason"] == "aborted" and last["completed"] is False
    expect(pg.locator("#pastBody tr").first).to_contain_text("중단", timeout=5000)


def test_survives_disconnect_and_null_status(page):
    pg = page
    api("/dev/scenario", {"name": "offline"})
    expect(pg.locator("#offlineBanner")).to_be_visible(timeout=5000)
    expect(pg.locator("#conn")).to_contain_text("끊김")
    expect(pg.locator("#btnStart")).to_be_disabled()
    api("/dev/scenario", {"name": "live"})
    expect(pg.locator("#offlineBanner")).to_be_hidden(timeout=5000)
    # 카메라 꺼짐: 값이 null이어도 깨지지 않고 할 일 한 줄을 보여 준다
    api("/dev/scenario", {"name": "camera_off"})
    expect(pg.locator("#statusTodo")).to_contain_text("카메라 영상이 들어오지 않습니다", timeout=5000)
    expect(pg.locator("#stageNote")).to_contain_text("도식", timeout=5000)
    api("/dev/scenario", {"name": "markers_low"})
    expect(pg.locator("#statusTodo")).to_contain_text("마커가 2개만 보입니다", timeout=5000)
    api("/dev/scenario", {"name": "idle"})
    expect(pg.locator("#startForm")).to_be_visible(timeout=5000)
    api("/dev/scenario", {"name": "live"})


def test_full_attempt_and_export(page, tmp_path):
    pg = page
    pg.reload()
    expect(pg.locator("#conn")).to_have_text("서버 연결됨", timeout=5000)
    expect(pg.locator("#startForm")).to_be_visible()
    # 항상 보이는 원칙 표시
    expect(pg.locator("#privacy")).to_have_text("영상은 저장하지 않습니다 · 좌표와 시간만 기록")
    expect(pg.locator("#btnSource")).to_have_text("버튼 위치: 시연용 정답 좌표 사용")
    expect(pg.locator("#source")).to_contain_text("예시 데이터")
    expect(pg.locator("#fGoal option")).to_have_count(3)

    # 조건 입력. 이름을 적으면 막는다
    pg.select_option("#fSource", "synthetic")
    pg.select_option("#fGoal", "iced-americano-1")
    pg.check("input[name=layout][value=B]")
    pg.check("input[name=guidance][value=on]")
    pg.check("input[name=blindfold][value=yes]")
    pg.fill("#fLight", "시험 조명")
    pg.fill("#fNote", "자동 시험")
    pg.fill("#fCode", "홍길동")
    pg.click("#btnStart")
    expect(pg.locator("#runMsg")).to_contain_text("이름을 적지 않습니다")
    assert api("/api/live")["attempt"] is None
    pg.fill("#fCode", "p07")

    # 시도 시작 (키보드: Ctrl+Enter)
    pg.locator("#fNote").focus()
    pg.keyboard.press("Control+Enter")
    expect(pg.locator("#running")).to_be_visible(timeout=5000)
    expect(pg.locator("#runCond")).to_contain_text("P07")
    live = api("/api/live")
    a = live["attempt"]
    assert a and a["data_source"] == "synthetic"
    assert a["conditions"] == {"layout": "B", "guidance": "on", "blindfold": "yes", "lighting_note": "시험 조명", "participant_code": "P07", "operator_note": "자동 시험"}

    # 진행: 단계 표시와 안내 문구가 바뀐다
    expect(pg.locator("#steps li.active")).to_have_count(1)
    expect(pg.locator("#guideNow")).not_to_have_class("guide-now empty", timeout=5000)
    expect(pg.locator("#steps li").nth(1)).to_have_class("active", timeout=20000)

    # 다시 듣기 / 멈춤 / 재개 (키보드 R, P)
    pg.locator("body").click(position={"x": 5, "y": 760})
    pg.keyboard.press("r")
    expect(pg.locator("#runMsg")).to_contain_text("다시 읽도록")
    pg.keyboard.press("p")
    expect(pg.locator("#pausedTag")).to_be_visible(timeout=3000)
    pg.keyboard.press("p")
    expect(pg.locator("#pausedTag")).to_be_hidden(timeout=3000)

    # 주문 번호까지
    expect(pg.locator("#screenLine")).to_contain_text("주문 번호", timeout=40000)
    expect(pg.locator("#steps li.done")).to_have_count(5)
    expect(pg.locator("#btnEnd")).to_have_text("시도 종료 (주문 완료)")

    # 종료
    pg.click("#btnEnd")
    expect(pg.locator("#startForm")).to_be_visible(timeout=5000)
    assert api("/api/live")["attempt"] is None
    expect(pg.locator("#screenLine")).to_contain_text("직전 시도 · 주문을 마쳤습니다")
    expect(pg.locator("#steps li.done")).to_have_count(5)
    row = pg.locator("#pastBody tr").first
    expect(row).to_contain_text("P07", timeout=5000)
    expect(row).to_contain_text("완료")
    aid = row.get_attribute("data-id")
    assert aid == a["id"]

    # 내려받기: JSONL
    with pg.expect_download() as d:
        row.locator("a[data-kind=jsonl]").click()
    p1 = tmp_path / d.value.suggested_filename
    d.value.save_as(p1)
    assert p1.name == f"{aid}.jsonl"
    recs = [json.loads(s) for s in p1.read_text(encoding="utf-8").splitlines() if s.strip()]
    assert recs[0]["kind"] == "attempt_start" and recs[0]["data_source"] == "synthetic"
    assert recs[0]["conditions"]["participant_code"] == "P07"
    assert recs[-1]["kind"] == "attempt_end" and recs[-1]["completed"] is True and recs[-1]["end_reason"] == "done"
    assert [r["seq"] for r in recs] == list(range(1, len(recs) + 1))
    kinds = {r["kind"] for r in recs}
    assert {"guide", "press", "step_done", "screen", "operator"} <= kinds
    assert any(r["kind"] == "operator" and r["action"] == "stop" for r in recs)

    # CSV
    with pg.expect_download() as d:
        row.locator("a[data-kind=csv]").click()
    p2 = tmp_path / d.value.suggested_filename
    d.value.save_as(p2)
    rows = list(csv.reader(io.StringIO(p2.read_text(encoding="utf-8-sig"))))
    assert rows[0][:6] == ["v", "attempt", "seq", "t", "ms", "kind"]
    assert len(rows) - 1 == len(recs)

    # 배열 JSON
    with pg.expect_download() as d:
        row.locator("button[data-json]").click()
    p3 = tmp_path / d.value.suggested_filename
    d.value.save_as(p3)
    arr = json.loads(p3.read_text(encoding="utf-8"))
    assert p3.name == f"{aid}.json" and arr == recs
    assert not pg.errors, pg.errors
