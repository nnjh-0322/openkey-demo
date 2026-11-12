"""시연 서버용 자체 서명 인증서를 만든다(휴대폰 카메라는 https에서만 켜지기 때문).

결과: work/live-capture-cert/cert.pem, key.pem  (저장소에는 넣지 않는다 — .gitignore의 work/)
이미 있으면 아무것도 하지 않는다. --force면 새로 만든다.
openssl은 Git for Windows에 함께 들어 있는 것을 찾아 쓴다(따로 설치할 필요 없음).
"""
import argparse
import pathlib
import shutil
import socket
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "work" / "live-capture-cert"


def find_openssl():
    cands = [shutil.which("openssl")]
    git = shutil.which("git")
    if git:
        g = pathlib.Path(git).resolve()
        for up in (g.parent.parent, g.parent.parent.parent):  # ...\Git\cmd\git.exe → ...\Git
            cands += [up / "usr" / "bin" / "openssl.exe", up / "mingw64" / "bin" / "openssl.exe", up / "ucrt64" / "bin" / "openssl.exe"]
    cands += [pathlib.Path(r"C:\Program Files\Git\usr\bin\openssl.exe"), pathlib.Path(r"C:\Program Files\Git\mingw64\bin\openssl.exe")]
    for c in cands:
        if c and pathlib.Path(c).is_file():
            return str(c)
    return None


def lan_ips():
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(i for i in ips if not i.startswith("127."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    cert, key = OUT / "cert.pem", OUT / "key.pem"
    if cert.is_file() and key.is_file() and not a.force:
        print(f"[cert] 이미 있음: {OUT}")
        return 0
    ossl = find_openssl()
    if not ossl:
        print("[cert] openssl을 찾지 못했습니다. Git for Windows를 설치하거나, 인증서(cert.pem·key.pem)를 팀원에게 받아 work\\live-capture-cert\\에 넣으세요.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    san = ",".join(["DNS:localhost", "IP:127.0.0.1"] + [f"IP:{i}" for i in lan_ips()])
    cmd = [ossl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", "825",
           "-keyout", str(key), "-out", str(cert), "-subj", "/CN=OpenKey demo", "-addext", f"subjectAltName={san}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not cert.is_file():
        print("[cert] 인증서 만들기 실패:", (r.stderr or r.stdout).strip()[-400:])
        return 1
    print(f"[cert] 만들었습니다: {OUT}  ({san})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
