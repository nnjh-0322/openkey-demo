"""통합 시험(pytest 진입점). 실제 server.py(포트 8462) + headless Edge kiosk-host + 합성 손끝. 약 7분.

건너뛰기: 환경 변수 OPENKEY_SKIP_INTEGRATION=1
"""
import os
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


@pytest.mark.skipif(os.environ.get("OPENKEY_SKIP_INTEGRATION") == "1", reason="OPENKEY_SKIP_INTEGRATION=1")
def test_integration_all_scenarios():
    import integration
    results, page_errors = integration.main(["--port", "8463"])
    assert results, "시나리오가 돌지 않음"
    bad = [(r["name"], r["problems"]) for r in results if not r["ok"]]
    assert not bad, bad
    assert not page_errors, page_errors
