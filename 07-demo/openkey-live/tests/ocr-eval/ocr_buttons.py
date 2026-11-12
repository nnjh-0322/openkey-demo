"""선택 과제: 카메라 OCR(PP-OCRv5)로 버튼 글자를 찾아 시연용 정답 좌표와 비교(합성 시험, 실제 휴대폰 아님).

경로: kiosk-host 화면 캡처 → 원근 왜곡한 합성 카메라 프레임(손 없음) → POST /api/frame(서버 ArUco 호모그래피)
→ 그 H로 키오스크 평면으로 펴기 → RapidOCR(PP-OCRv5 mobile det + korean rec, work/ppocrv5-models) → 글자 상자 중심이
그 버튼의 정답 영역(currentMap bbox) 안에 있는지. 화면: 배치 B 메뉴, 옵션 창(아메리카노). 거리 near/far.
이미지는 저장하지 않는다.

실행: .venv\\Scripts\\python.exe 07-demo\\openkey-live\\tests\\ocr-eval\\ocr_buttons.py
"""
import datetime
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from urllib.parse import unquote

import cv2
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
TESTS = HERE.parent
LIVE = TESTS.parent
ROOT = LIVE.parents[1]
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS / "hand-eval"))
import eval_hands as E  # noqa: E402
from integration import start_server, wait_kiosk  # noqa: E402

RW, RH = 720, 1280  # 펴낸 키오스크 평면 크기(9:16)


def key_of(label):
    toks = re.findall(r"[가-힣A-Za-z]{2,}", label or "")
    toks = [t for t in toks if t not in ("BEST", "NEW")]
    return max(toks, key=len) if toks else None


def norm(t):
    return "".join(unicodedata.normalize("NFKC", t).split())


def frame_h(api, img):
    j = E.post_frame(api, img)
    c = api._conn()
    c.request("GET", f"/api/frame/latest?after={j['seq'] - 1}")
    r = c.getresponse()
    info = json.loads(unquote(r.getheader("X-Info")))
    r.read()
    return j, info


def main(port=8466):
    import pw_driver
    pw_driver.patch()
    from playwright.sync_api import sync_playwright
    from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR
    eng = RapidOCR(params={"Global.model_root_dir": str(ROOT / "work" / "ppocrv5-models"), "Global.use_cls": False, "Global.log_level": "warning",
                           "Det.engine_type": EngineType.ONNXRUNTIME, "Det.lang_type": LangDet.CH, "Det.model_type": ModelType.MOBILE, "Det.ocr_version": OCRVersion.PPOCRV5,
                           "Rec.engine_type": EngineType.ONNXRUNTIME, "Rec.lang_type": LangRec.KOREAN, "Rec.model_type": ModelType.MOBILE, "Rec.ocr_version": OCRVersion.PPOCRV5,
                           "Det.mean": [0.485, 0.456, 0.406], "Det.std": [0.229, 0.224, 0.225], "Det.limit_side_len": 960, "Det.limit_type": "max",
                           "Det.box_thresh": 0.6, "Det.unclip_ratio": 1.5, "Det.use_dilation": False})
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="openkey-ocr-"))
    proc, api = start_server(port, tmp / "runs", tmp / "server.log")
    rows = []
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(channel="msedge", headless=True, args=["--ignore-certificate-errors"])
            page = br.new_context(viewport={"width": 1600, "height": 900}, ignore_https_errors=True).new_page()
            page.goto(f"https://localhost:{port}/kiosk-host?layout=B&screen=menu")
            wait_kiosk(api, screen="menu")
            page.evaluate("document.getElementById('side').style.display='none'")
            for scr in ("menu", "menu+option"):
                if scr == "menu+option":
                    page.evaluate("document.getElementById('k').contentWindow.OPENKEY_KIOSK.actions.pick('americano')")
                live = wait_kiosk(api, screen=scr)
                time.sleep(0.5)
                shot = cv2.imdecode(np.frombuffer(page.screenshot(), np.uint8), cv2.IMREAD_COLOR)
                regs = [r for r in live["kiosk"]["regions"] if key_of(r["label"])]
                for dist, frac in (("near", 0.78), ("far", 0.45)):
                    for cam_w, cam_h in ((1280, 720), (1920, 1080)):
                        img = E.to_camera(shot, cam_w, cam_h, frac, 0.10, np.random.default_rng(3))
                        j, info = frame_h(api, img)
                        if not info.get("H"):
                            rows.append({"screen": scr, "dist": dist, "cam": f"{cam_w}x{cam_h}", "error": "위치 맞춤 없음"})
                            continue
                        H = np.array(info["H"])
                        S = np.array([[RW, 0, 0], [0, RH, 0], [0, 0, 1]], float)
                        flat = cv2.warpPerspective(img, S @ H, (RW, RH))
                        t0 = time.time()
                        res = eng(flat)
                        ms = (time.time() - t0) * 1000
                        lines = []
                        for box, txt, sc in zip(res.boxes if res.boxes is not None else [], res.txts or [], res.scores or []):
                            b = np.array(box)
                            lines.append({"t": norm(txt), "c": (float(b[:, 0].mean()) / RW, float(b[:, 1].mean()) / RH), "s": float(sc)})
                        found = wrong = missing = 0
                        detail = []
                        for r in regs:
                            k = norm(key_of(r["label"]))
                            cands = [ln for ln in lines if k in ln["t"] or (len(ln["t"]) >= 2 and ln["t"] in k)]
                            bb = r["bbox"]
                            if not cands:
                                missing += 1
                                detail.append((r["id"], k, "없음"))
                                continue
                            best = max(cands, key=lambda ln: ln["s"])
                            ok = bb[0] <= best["c"][0] <= bb[2] and bb[1] <= best["c"][1] <= bb[3]
                            found += ok
                            wrong += not ok
                            detail.append((r["id"], k, "맞음" if ok else f"다른 곳({best['t']})"))
                        rows.append({"screen": scr, "dist": dist, "cam": f"{cam_w}x{cam_h}", "markers": j.get("known_markers"), "buttons": len(regs),
                                     "found": found, "wrong": wrong, "missing": missing, "ocr_ms": round(ms), "lines": len(lines), "detail": detail})
                        print(rows[-1]["screen"], dist, rows[-1]["cam"], f"{found}/{len(regs)} 틀림 {wrong} 못찾음 {missing} {round(ms)}ms", flush=True)
            br.close()
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
    write(rows)


def write(rows):
    L = ["# 선택 과제: 카메라 OCR로 버튼 찾기 (합성 시험)", "",
         f"실행: {datetime.datetime.now().astimezone():%Y-%m-%d %H:%M} / A. 명령: `.venv\\Scripts\\python.exe 07-demo\\openkey-live\\tests\\ocr-eval\\ocr_buttons.py`", "",
         "**합성 시험, 실제 휴대폰 아님.** kiosk-host 화면 캡처(배치 B)를 원근 왜곡(위쪽 10% 좁힘)·흐림·밝기 변화로 카메라 프레임처럼 만들고(손 없음), 서버의 실제 마커 위치 맞춤(H)으로 720×1280 키오스크 평면에 편 뒤",
         "RapidOCR 3.10 + PP-OCRv5 mobile(det ch, rec korean; `06-validation/experiments/benchmark-005-ppocrv5` 설정)으로 읽었다. 버튼마다 대표 글자(라벨의 가장 긴 한글·영문 낱말, 예: 아메리카노·ICE·담기·결제하기)를 OCR 줄에서 찾고,",
         "그 글자 상자 중심이 키오스크 정답 영역(`currentMap` bbox) 안이면 '맞음'. 반사·모아레·초점·손 가림이 없는 깨끗한 조건이다. 안내 엔진에는 연결하지 않았다(버튼 위치는 계속 정답 좌표).", "",
         "| 화면 | 거리 | 카메라 | 마커 | 버튼 수 | 맞음 | 다른 곳 | 못 찾음 | OCR 시간 |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        if "error" in r:
            L.append(f"| {r['screen']} | {r['dist']} | {r['cam']} | - | - | - | - | - | {r['error']} |")
            continue
        L.append(f"| {r['screen']} | {r['dist']} | {r['cam']} | {r['markers']}/4 | {r['buttons']} | {r['found']} | {r['wrong']} | {r['missing']} | {r['ocr_ms']}ms |")
    L += ["", "못 찾거나 다른 곳으로 나온 버튼(실패 조건 그대로):", ""]
    for r in rows:
        bad = [d for d in r.get("detail", []) if d[2] != "맞음"]
        if bad:
            L.append(f"- {r['screen']} · {r['dist']} · {r['cam']}: " + ", ".join(f"`{i}`({k}) → {v}" for i, k, v in bad))
    L += ["", "해석(AI 판단): 아래 보고서 끝 참고.", ""]
    (HERE / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
