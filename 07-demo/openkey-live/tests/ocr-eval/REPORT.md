# 선택 과제: 카메라 OCR로 버튼 찾기 (합성 시험)

실행: 2026-11-12 18:55 / A. 명령: `.venv\Scripts\python.exe 07-demo\openkey-live\tests\ocr-eval\ocr_buttons.py`

**합성 시험, 실제 휴대폰 아님.** kiosk-host 화면 캡처(배치 B)를 원근 왜곡(위쪽 10% 좁힘)·흐림·밝기 변화로 카메라 프레임처럼 만들고(손 없음), 서버의 실제 마커 위치 맞춤(H)으로 720×1280 키오스크 평면에 편 뒤
RapidOCR 3.10 + PP-OCRv5 mobile(det ch, rec korean; `06-validation/experiments/benchmark-005-ppocrv5` 설정)으로 읽었다. 버튼마다 대표 글자(라벨의 가장 긴 한글·영문 낱말, 예: 아메리카노·ICE·담기·결제하기)를 OCR 줄에서 찾고,
그 글자 상자 중심이 키오스크 정답 영역(`currentMap` bbox) 안이면 '맞음'. 반사·모아레·초점·손 가림이 없는 깨끗한 조건이다. 안내 엔진에는 연결하지 않았다(버튼 위치는 계속 정답 좌표).

| 화면 | 거리 | 카메라 | 마커 | 버튼 수 | 맞음 | 다른 곳 | 못 찾음 | OCR 시간 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| menu | near | 1280x720 | 4/4 | 17 | 5 | 1 | 11 | 1603ms |
| menu | near | 1920x1080 | 4/4 | 17 | 16 | 1 | 0 | 1158ms |
| menu | far | 1280x720 | 4/4 | 17 | 0 | 0 | 17 | 1165ms |
| menu | far | 1920x1080 | 4/4 | 17 | 2 | 1 | 14 | 1156ms |
| menu+option | near | 1280x720 | 4/4 | 6 | 4 | 0 | 2 | 1352ms |
| menu+option | near | 1920x1080 | 4/4 | 6 | 5 | 0 | 1 | 1337ms |
| menu+option | far | 1280x720 | 4/4 | 6 | 1 | 0 | 5 | 1266ms |
| menu+option | far | 1920x1080 | 4/4 | 6 | 3 | 0 | 3 | 1233ms |

못 찾거나 다른 곳으로 나온 버튼(실패 조건 그대로):

- menu · near · 1280x720: `home`(처음으로) → 없음, `cat-coffee`(커피) → 다른 곳(매일의커피,조금더특별하게), `item-americano`(아메리카노) → 없음, `item-latte`(카페라떼) → 없음, `item-vanilla`(바닐라라떼) → 없음, `item-caramel`(카라멜마키아토) → 없음, `item-cappuccino`(카푸치노) → 없음, `item-coldbrew`(콜드브루) → 없음, `item-choco`(초코라떼) → 없음, `item-greentea`(녹차라떼) → 없음, `item-strawberry`(딸기라떼) → 없음, `clear`(전체삭제) → 없음
- menu · near · 1920x1080: `cat-coffee`(커피) → 다른 곳(논커피)
- menu · far · 1280x720: `home`(처음으로) → 없음, `staff-call`(직원) → 없음, `cat-all`(전체) → 없음, `cat-coffee`(커피) → 없음, `cat-noncoffee`(논커피) → 없음, `cat-dessert`(디저트) → 없음, `item-americano`(아메리카노) → 없음, `item-latte`(카페라떼) → 없음, `item-vanilla`(바닐라라떼) → 없음, `item-caramel`(카라멜마키아토) → 없음, `item-cappuccino`(카푸치노) → 없음, `item-coldbrew`(콜드브루) → 없음, `item-choco`(초코라떼) → 없음, `item-greentea`(녹차라떼) → 없음, `item-strawberry`(딸기라떼) → 없음, `clear`(전체삭제) → 없음, `checkout`(결제하기) → 없음
- menu · far · 1920x1080: `home`(처음으로) → 없음, `staff-call`(직원) → 없음, `cat-all`(전체) → 없음, `cat-coffee`(커피) → 다른 곳(매일의커피,조금더특별하게), `cat-noncoffee`(논커피) → 없음, `item-americano`(아메리카노) → 없음, `item-latte`(카페라떼) → 없음, `item-vanilla`(바닐라라떼) → 없음, `item-caramel`(카라멜마키아토) → 없음, `item-cappuccino`(카푸치노) → 없음, `item-coldbrew`(콜드브루) → 없음, `item-choco`(초코라떼) → 없음, `item-greentea`(녹차라떼) → 없음, `item-strawberry`(딸기라떼) → 없음, `clear`(전체삭제) → 없음
- menu+option · near · 1280x720: `opt-temp-ICE`(ICE) → 없음, `opt-size-R`(레귤러) → 없음
- menu+option · near · 1920x1080: `opt-size-R`(레귤러) → 없음
- menu+option · far · 1280x720: `opt-temp-ICE`(ICE) → 없음, `opt-temp-HOT`(HOT) → 없음, `opt-size-R`(레귤러) → 없음, `opt-size-L`(라지) → 없음, `opt-add`(담기) → 없음
- menu+option · far · 1920x1080: `opt-temp-ICE`(ICE) → 없음, `opt-size-R`(레귤러) → 없음, `opt-size-L`(라지) → 없음

## 해석

사실(위 표):
- 카메라 1920×1080·near(노트북 화면이 카메라 폭의 78%)에서만 메뉴 16/17, 옵션 5/6으로 쓸 만했다. 같은 거리라도 1280×720은 메뉴 5/17, far(45%)는 0~3개 수준으로 **실패**.
- 1280×720·near에서 키오스크 부분은 카메라 영상에서 대략 폭 380px 정도다(노트북 1600px 화면 중 키오스크 607px × 0.78). 메뉴 카드 이름 글자가 너무 작아 검출되지 않은 것이 주 실패다('없음'이 대부분).
- '다른 곳' 1건(`cat-coffee` → '논커피'·'매일의 커피…' 배너)은 낱말 포함 비교의 채점 한계다(커피 ⊂ 논커피). 실제로 쓰려면 버튼 글자 전체 일치·위치 제약이 필요하다.
- OCR 한 번 1.2~1.6초(PC CPU). 손 안내처럼 매 프레임 쓸 수는 없고, 새 화면이 뜰 때 한 번 읽는 용도여야 한다. 이때 손이 화면을 가리면 못 읽으므로 손 내림 정책(새 화면을 못 읽을 때 약 1초 뒤 손 내림 요청)이 필요해진다.

판단(AI 제안): 지금 시연은 정답 좌표(`kiosk_ground_truth`)를 유지한다. OCR 모드는 (1) 휴대폰 1920 전송 또는 키오스크 부분만 고해상도로 보내기, (2) 글자 전체 일치 + 화면 구조(같은 줄·카드 안) 규칙, (3) 실제 촬영 영상에서 반사·모아레 시험을 거친 뒤에 검토한다. 이 결과는 깨끗한 합성 조건이라 실제보다 좋게 나왔을 가능성이 크다.

