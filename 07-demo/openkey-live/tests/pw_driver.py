"""Playwright 드라이버 우회: 프로젝트 경로(한글·공백)에 있는 Node 드라이버가 Windows에서 바로 죽는다
(2026-11-12 확인: node.exe가 cli.js를 불러오다 0xC0000005로 종료, ASCII 경로 복사본은 정상).
드라이버를 ASCII 경로(%TEMP%\\openkey-pwdriver-<버전>)로 한 번 복사하고 그 위치를 쓰게 한다. 저장소에는 아무것도 쓰지 않는다.
"""
import inspect
import pathlib
import shutil
import tempfile


def patch():
    import playwright
    import playwright._impl._transport as tr
    from playwright._repo_version import version

    src = pathlib.Path(inspect.getfile(playwright)).parent / "driver"
    if str(src).isascii():
        return str(src)
    dst = pathlib.Path(tempfile.gettempdir()) / f"openkey-pwdriver-{version}"
    if not str(dst).isascii():
        dst = pathlib.Path("C:/openkey-pwdriver-" + version)
    if not (dst / "package" / "cli.js").is_file():
        shutil.copytree(src, dst, dirs_exist_ok=True)

    def compute():
        return str(dst / "node.exe"), str(dst / "package" / "cli.js")

    tr.compute_driver_executable = compute
    return str(dst)
