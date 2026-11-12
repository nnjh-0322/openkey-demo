"""Playwright 실행 도우미 (05-data/tools/kiosk-export/pwhelper.py 복사본, 관리자 콘솔 시험용).

이 프로젝트 경로에는 한글이 있어 Playwright 1.49.1 드라이버(node)가 프로젝트 .venv 안에서
access violation(0xC0000005)으로 종료된다(2026-11-08 확인). 같은 드라이버를 영문 경로
%LOCALAPPDATA%\\openkey-tools\\playwright-driver-<버전>으로 복사해 실행한다.
브라우저는 설치된 Microsoft Edge(channel="msedge")를 사용하므로 별도 브라우저 다운로드가 없다.
"""
import os
import pathlib
import shutil

import playwright
from playwright._impl import _transport
from playwright._repo_version import version as PW_VERSION


def _ascii_driver() -> pathlib.Path:
    src = pathlib.Path(playwright.__file__).parent / "driver"
    base = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home())) / "openkey-tools"
    dst = base / f"playwright-driver-{PW_VERSION}"
    marker = dst / ".copied"
    if not marker.exists():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        marker.write_text(str(src), encoding="utf-8")
    return dst


def patch_driver() -> str:
    d = _ascii_driver()
    node = d / ("node.exe" if os.name == "nt" else "node")
    cli = d / "package" / "cli.js"
    _transport.compute_driver_executable = lambda: (str(node), str(cli))
    return str(d)


def launch(p, **kw):
    """sync_playwright() 객체로 Edge를 띄운다."""
    return p.chromium.launch(channel="msedge", **kw)
