# OpenKey Live (시연 프로그램)

기존 키오스크에 붙이는 AI 손끝 안내. 휴대폰 카메라가 키오스크 화면과 손끝을 보고, 원하는 버튼까지 음성으로 안내한다. **누르는 것은 사용자 본인이다.**

- 바로 시험하기: 루트 [지금-테스트하기.md](../../지금-테스트하기.md) (`시연-시작.bat`, `자동시험.bat`)
- 상태(2026-11-13): PC 가상 시험 통과(엔진+통합 24개, 콘솔 3개). 실제 휴대폰으로 손 인식 확인(팀원 시험). **실제 사용자 시험은 아직.**

| 파일·폴더 | 내용 | 담당 |
| --- | --- | --- |
| [RUN.md](RUN.md) | 실행 방법·옵션·문제 해결 | A |
| [PHONE-TEST.md](PHONE-TEST.md) | 실제 휴대폰 시험 절차표 | A |
| [SCHEMA.md](SCHEMA.md) | 기록 형식 v1·실시간 API 계약 | PM |
| [API.md](API.md) | 실제 구현한 API(SCHEMA + 추가분 ★) | A |
| `server.py`, `engine/` | 서버(8460), 안내 판단 엔진 | A |
| `kiosk-host.html`, `phone.html`, `static/` | 노트북 키오스크+마커+손 인식 / 휴대폰 사용자 화면 | A |
| [admin/](admin/ADMIN.md) | 관리자 콘솔 | B |
| `tests/` | 단위·통합 시험, [통합 결과](tests/INTEGRATION-RESULT.md), [손 인식 비교](tests/hand-eval/REPORT.md), [OCR 비교](tests/ocr-eval/REPORT.md) | A |
| `runs/` | 시도 기록(JSONL). `runs/examples/`는 자동 시험이 만든 합성 기록 | — |
| `start-demo.ps1` | `시연-시작.bat`이 부르는 실행 스크립트 | PM |

서버는 실행 중에 `03-software/vendor/`(MediaPipe)와 `04-practice-kiosk/realistic/`(MORU 모의 키오스크)를 읽는다.
