# 통합 시험 결과 (가상 시험)

실행: 2026-11-13 00:09 / A(안내 실행부). 명령: `.venv\Scripts\python.exe 07-demo\openkey-live\tests\integration.py --write-examples`

**가상 시험**이다: 실제 `server.py` + headless Edge의 `kiosk-host.html`(진짜 MORU 키오스크가 화면 전환) + 합성 손끝 좌표(`/api/hand` source=synthetic, 키오스크 정규 좌표 직접 주입).
합성 사용자(`tests/sim.py`)는 버튼 좌표를 모르고 말하기 큐의 안내 코드만 듣고 움직인다(속도·반응 지연은 임의 값). 카메라·MediaPipe·실제 휴대폰·사람은 쓰지 않았다.
누름 경로: `direct`는 Playwright `page.mouse.click`(실제 포인터 이벤트), `auto_click`은 서버 자동 누름 명령을 kiosk-host가 실행한 것(시연 보조).
키오스크는 `fixed=1`(타이머 정지·주문 번호 27 고정)이고 결제는 간편결제(모의)를 목표로 한다. 카드 화면은 `fixed=1`에서 자동 승인되지 않기 때문이다.

결과: **6/6 통과**. 페이지 오류: 0건

| 시나리오 | 결과 | 소요(벽시계) | 기록 시간 | 누름(버튼, 결과, 경로) | 안내 수 | 기록 파일 |
| --- | --- | --- | --- | --- | --- | --- |
| 배치 B · 실제 포인터 입력으로 누름 | 통과 | 46.3s | 46.3s | dine-store/correct/direct, item-americano/correct/direct, opt-temp-ICE/correct/direct, opt-add/correct/direct, checkout/correct/direct, cf-pay/correct/direct, pay-simple/correct/direct | 53 | `runs/examples/20261113-000431-5f99.jsonl` |
| 배치 A · 실제 포인터 입력으로 누름 | 통과 | 46.1s | 46.0s | dine-store/correct/direct, item-americano/correct/direct, opt-temp-ICE/correct/direct, opt-add/correct/direct, checkout/correct/direct, cf-pay/correct/direct, pay-simple/correct/direct | 49 | `runs/examples/20261113-000517-2472.jsonl` |
| 배치 B · 시연 보조 자동 누름 | 통과 | 48.4s | 48.3s | dine-store/correct/auto_click, item-americano/correct/auto_click, opt-temp-ICE/correct/auto_click, opt-add/correct/auto_click, checkout/correct/auto_click, cf-pay/correct/auto_click, pay-simple/correct/auto_click | 51 | `runs/examples/20261113-000603-5354.jsonl` |
| 배치 A · 시연 보조 자동 누름 | 통과 | 47.8s | 47.7s | dine-store/correct/auto_click, item-americano/correct/auto_click, opt-temp-ICE/correct/auto_click, opt-add/correct/auto_click, checkout/correct/auto_click, cf-pay/correct/auto_click, pay-simple/correct/auto_click | 47 | `runs/examples/20261113-000652-fca2.jsonl` |
| 배치 B · 메뉴에서 일부러 다른 메뉴(카페라떼) 누름 → 알림 → 되돌림 | 통과 | 55.8s | 55.8s | dine-store/correct/direct, item-latte/wrong/direct, opt-cancel/correct/direct, item-americano/correct/direct, opt-temp-ICE/correct/direct, opt-add/correct/direct, checkout/correct/direct, cf-pay/correct/direct, pay-simple/correct/direct | 59 | `runs/examples/20261113-000739-9a68.jsonl` |
| 배치 A · 옵션 화면 '멈추세요' 직후 손 2.5초 사라짐 | 통과 | 49.0s | 48.9s | dine-store/correct/direct, item-americano/correct/direct, opt-temp-ICE/correct/direct, opt-add/correct/direct, checkout/correct/direct, cf-pay/correct/direct, pay-simple/correct/direct | 50 | `runs/examples/20261113-000835-a586.jsonl` |

확인 항목(각 시나리오 공통): 주문 번호까지 완료, SCHEMA v1 필드·허용값(`engine/checks.py schema_errors`), PRESS 안전 규칙(`press_safety_violations`: 손 놓침 중·위치 맞춤 무효 중·현재 목표 아닌 PRESS 없음),
안내 SCREEN·PRESS·PRESS_OK·PAY_CHECK·DONE 포함, step_done 순서 menu→option→confirm→pay→done. 시나리오별: 누름 경로, 결제 화면 손 내림 요청·확인, 잘못 누름 알림·되돌림, 손 놓침 중 PRESS 없음.

## 배치 B · 실제 포인터 입력으로 누름

시도 `20261113-000431-5f99` · 주문 번호 27 · 카운트 `{"presses": 7, "wrong_presses": 0, "reverts": 0, "hesitations": 4, "hand_lost": 0, "hand_down_requests": 2, "guides": 53}`

안내 문구 순서(실제로 낸 말만, 억제된 말 제외):

1. `INFO` 아이스 아메리카노 한 잔 주문.
2. `SCREEN` 첫 화면. 매장 버튼.
3. `UP` 위로
4. `UP_SMALL` 위로 조금
5. `LEFT_SMALL` 왼쪽 조금
6. `UP_SMALL` 위로 조금
7. `HOLD` 멈추세요.
8. `PRESS` 누르세요.
9. `PRESS_OK` 맞아요.
10. `SCREEN` 메뉴 화면. 아메리카노.
11. `UP` 위로
12. `UP_SMALL` 위로 조금
13. `LEFT` 왼쪽으로
14. `LEFT_SMALL` 왼쪽 조금
15. `UP_SMALL` 위로 조금
16. `HOLD` 멈추세요.
17. `PRESS` 누르세요.
18. `PRESS_OK` 맞아요.
19. `SCREEN` 옵션 화면. 차가운 것, 아이스.
20. `UP` 위로
21. `UP_SMALL` 위로 조금
22. `RIGHT` 오른쪽으로
23. `RIGHT_SMALL` 오른쪽 조금
24. `UP_SMALL` 위로 조금
25. `RIGHT_SMALL` 오른쪽 조금
26. `HOLD` 멈추세요.
27. `PRESS` 누르세요.
28. `PRESS_OK` 맞아요. 다음 담기.
29. `DOWN` 아래로
30. `DOWN_SMALL` 아래 조금
31. `HOLD` 멈추세요.
32. `PRESS` 누르세요.
33. `PRESS_OK` 맞아요.
34. `SCREEN` 담겼어요. 결제하기 버튼.
35. `RIGHT` 오른쪽으로
36. `RIGHT_SMALL` 오른쪽 조금
37. `HOLD` 멈추세요.
38. `PRESS` 누르세요.
39. `PRESS_OK` 맞아요.
40. `HAND_DOWN` 주문 확인. 손을 내려 주세요.
41. `PAY_CHECK` 아이스 아메리카노 한 잔, 2,000원. 맞으면 손을 올려 주세요. 결제하기 버튼.
42. `UP_SMALL` 위로 조금
43. `HOLD` 멈추세요.
44. `PRESS` 누르세요.
45. `PRESS_OK` 맞아요.
46. `HAND_DOWN` 결제 화면. 손을 내려 주세요.
47. `PAY_CHECK` 결제 금액 2,000원. 모의 결제예요. 손을 올려 주세요. 간편결제 버튼.
48. `UP` 위로
49. `UP_SMALL` 위로 조금
50. `HOLD` 멈추세요.
51. `PRESS` 누르세요.
52. `PRESS_OK` 맞아요.
53. `DONE` 주문 끝. 주문 번호 27번.

## 배치 A · 실제 포인터 입력으로 누름

시도 `20261113-000517-2472` · 주문 번호 27 · 카운트 `{"presses": 7, "wrong_presses": 0, "reverts": 0, "hesitations": 4, "hand_lost": 0, "hand_down_requests": 2, "guides": 49}`

안내 문구 순서(실제로 낸 말만, 억제된 말 제외):

1. `SCREEN` 첫 화면. 매장 버튼.
2. `UP` 위로
3. `UP_SMALL` 위로 조금
4. `LEFT_SMALL` 왼쪽 조금
5. `UP_SMALL` 위로 조금
6. `HOLD` 멈추세요.
7. `PRESS` 누르세요.
8. `PRESS_OK` 맞아요.
9. `SCREEN` 메뉴 화면. 아메리카노.
10. `UP` 위로
11. `UP_SMALL` 위로 조금
12. `LEFT_SMALL` 왼쪽 조금
13. `HOLD` 멈추세요.
14. `PRESS` 누르세요.
15. `PRESS_OK` 맞아요.
16. `SCREEN` 옵션 화면. 차가운 것, 아이스.
17. `UP` 위로
18. `UP_SMALL` 위로 조금
19. `RIGHT_SMALL` 오른쪽 조금
20. `UP_SMALL` 위로 조금
21. `RIGHT_SMALL` 오른쪽 조금
22. `HOLD` 멈추세요.
23. `PRESS` 누르세요.
24. `PRESS_OK` 맞아요. 다음 담기.
25. `DOWN` 아래로
26. `DOWN_SMALL` 아래 조금
27. `HOLD` 멈추세요.
28. `PRESS` 누르세요.
29. `PRESS_OK` 맞아요.
30. `SCREEN` 담겼어요. 결제하기 버튼.
31. `RIGHT` 오른쪽으로
32. `RIGHT_SMALL` 오른쪽 조금
33. `HOLD` 멈추세요.
34. `PRESS` 누르세요.
35. `PRESS_OK` 맞아요.
36. `HAND_DOWN` 주문 확인. 손을 내려 주세요.
37. `PAY_CHECK` 아이스 아메리카노 한 잔, 2,000원. 맞으면 손을 올려 주세요. 결제하기 버튼.
38. `UP_SMALL` 위로 조금
39. `HOLD` 멈추세요.
40. `PRESS` 누르세요.
41. `PRESS_OK` 맞아요.
42. `HAND_DOWN` 결제 화면. 손을 내려 주세요.
43. `PAY_CHECK` 결제 금액 2,000원. 모의 결제예요. 손을 올려 주세요. 간편결제 버튼.
44. `UP` 위로
45. `UP_SMALL` 위로 조금
46. `HOLD` 멈추세요.
47. `PRESS` 누르세요.
48. `PRESS_OK` 맞아요.
49. `DONE` 주문 끝. 주문 번호 27번.

## 배치 B · 시연 보조 자동 누름

시도 `20261113-000603-5354` · 주문 번호 27 · 카운트 `{"presses": 7, "wrong_presses": 0, "reverts": 0, "hesitations": 2, "hand_lost": 0, "hand_down_requests": 2, "guides": 51}`

안내 문구 순서(실제로 낸 말만, 억제된 말 제외):

1. `SCREEN` 첫 화면. 매장 버튼.
2. `UP` 위로
3. `UP_SMALL` 위로 조금
4. `LEFT_SMALL` 왼쪽 조금
5. `UP_SMALL` 위로 조금
6. `HOLD` 멈추세요.
7. `PRESS` 누르세요.
8. `PRESS_OK` 맞아요.
9. `SCREEN` 메뉴 화면. 아메리카노.
10. `UP` 위로
11. `UP_SMALL` 위로 조금
12. `LEFT` 왼쪽으로
13. `LEFT_SMALL` 왼쪽 조금
14. `HOLD` 멈추세요.
15. `PRESS` 누르세요.
16. `PRESS_OK` 맞아요.
17. `SCREEN` 옵션 화면. 차가운 것, 아이스.
18. `UP` 위로
19. `UP_SMALL` 위로 조금
20. `RIGHT` 오른쪽으로
21. `RIGHT_SMALL` 오른쪽 조금
22. `UP_SMALL` 위로 조금
23. `RIGHT_SMALL` 오른쪽 조금
24. `HOLD` 멈추세요.
25. `PRESS` 누르세요.
26. `PRESS_OK` 맞아요. 다음 담기.
27. `DOWN` 아래로
28. `DOWN` 아래로
29. `HOLD` 멈추세요.
30. `PRESS` 누르세요.
31. `PRESS_OK` 맞아요.
32. `SCREEN` 담겼어요. 결제하기 버튼.
33. `RIGHT` 오른쪽으로
34. `RIGHT_SMALL` 오른쪽 조금
35. `HOLD` 멈추세요.
36. `PRESS` 누르세요.
37. `PRESS_OK` 맞아요.
38. `HAND_DOWN` 주문 확인. 손을 내려 주세요.
39. `PAY_CHECK` 아이스 아메리카노 한 잔, 2,000원. 맞으면 손을 올려 주세요. 결제하기 버튼.
40. `UP_SMALL` 위로 조금
41. `HOLD` 멈추세요.
42. `PRESS` 누르세요.
43. `PRESS_OK` 맞아요.
44. `HAND_DOWN` 결제 화면. 손을 내려 주세요.
45. `PAY_CHECK` 결제 금액 2,000원. 모의 결제예요. 손을 올려 주세요. 간편결제 버튼.
46. `UP` 위로
47. `UP_SMALL` 위로 조금
48. `HOLD` 멈추세요.
49. `PRESS` 누르세요.
50. `PRESS_OK` 맞아요.
51. `DONE` 주문 끝. 주문 번호 27번.

## 배치 A · 시연 보조 자동 누름

시도 `20261113-000652-fca2` · 주문 번호 27 · 카운트 `{"presses": 7, "wrong_presses": 0, "reverts": 0, "hesitations": 5, "hand_lost": 0, "hand_down_requests": 2, "guides": 47}`

안내 문구 순서(실제로 낸 말만, 억제된 말 제외):

1. `SCREEN` 첫 화면. 매장 버튼.
2. `UP` 위로
3. `UP_SMALL` 위로 조금
4. `LEFT_SMALL` 왼쪽 조금
5. `UP_SMALL` 위로 조금
6. `HOLD` 멈추세요.
7. `PRESS` 누르세요.
8. `PRESS_OK` 맞아요.
9. `SCREEN` 메뉴 화면. 아메리카노.
10. `UP` 위로
11. `UP_SMALL` 위로 조금
12. `LEFT_SMALL` 왼쪽 조금
13. `HOLD` 멈추세요.
14. `PRESS` 누르세요.
15. `PRESS_OK` 맞아요.
16. `SCREEN` 옵션 화면. 차가운 것, 아이스.
17. `UP` 위로
18. `UP_SMALL` 위로 조금
19. `RIGHT_SMALL` 오른쪽 조금
20. `HOLD` 멈추세요.
21. `PRESS` 누르세요.
22. `PRESS_OK` 맞아요. 다음 담기.
23. `DOWN` 아래로
24. `DOWN_SMALL` 아래 조금
25. `HOLD` 멈추세요.
26. `PRESS` 누르세요.
27. `PRESS_OK` 맞아요.
28. `SCREEN` 담겼어요. 결제하기 버튼.
29. `RIGHT` 오른쪽으로
30. `RIGHT_SMALL` 오른쪽 조금
31. `HOLD` 멈추세요.
32. `PRESS` 누르세요.
33. `PRESS_OK` 맞아요.
34. `HAND_DOWN` 주문 확인. 손을 내려 주세요.
35. `PAY_CHECK` 아이스 아메리카노 한 잔, 2,000원. 맞으면 손을 올려 주세요. 결제하기 버튼.
36. `UP_SMALL` 위로 조금
37. `HOLD` 멈추세요.
38. `PRESS` 누르세요.
39. `PRESS_OK` 맞아요.
40. `HAND_DOWN` 결제 화면. 손을 내려 주세요.
41. `PAY_CHECK` 결제 금액 2,000원. 모의 결제예요. 손을 올려 주세요. 간편결제 버튼.
42. `UP` 위로
43. `UP_SMALL` 위로 조금
44. `HOLD` 멈추세요.
45. `PRESS` 누르세요.
46. `PRESS_OK` 맞아요.
47. `DONE` 주문 끝. 주문 번호 27번.

## 배치 B · 메뉴에서 일부러 다른 메뉴(카페라떼) 누름 → 알림 → 되돌림

시도 `20261113-000739-9a68` · 주문 번호 27 · 카운트 `{"presses": 9, "wrong_presses": 1, "reverts": 1, "hesitations": 3, "hand_lost": 0, "hand_down_requests": 2, "guides": 59}`

안내 문구 순서(실제로 낸 말만, 억제된 말 제외):

1. `SCREEN` 첫 화면. 매장 버튼.
2. `UP` 위로
3. `UP_SMALL` 위로 조금
4. `LEFT_SMALL` 왼쪽 조금
5. `UP_SMALL` 위로 조금
6. `HOLD` 멈추세요.
7. `PRESS` 누르세요.
8. `PRESS_OK` 맞아요.
9. `SCREEN` 메뉴 화면. 아메리카노.
10. `PRESS_WRONG` 다른 버튼이 눌렸어요. 취소 버튼으로 돌아가요.
11. `DOWN` 아래로
12. `DOWN_SMALL` 아래 조금
13. `LEFT_SMALL` 왼쪽 조금
14. `HOLD` 멈추세요.
15. `PRESS` 누르세요.
16. `PRESS_OK` 맞아요.
17. `SCREEN` 메뉴 화면. 아메리카노.
18. `UP` 위로
19. `UP_SMALL` 위로 조금
20. `LEFT` 왼쪽으로
21. `LEFT_SMALL` 왼쪽 조금
22. `UP_SMALL` 위로 조금
23. `HOLD` 멈추세요.
24. `PRESS` 누르세요.
25. `PRESS_OK` 맞아요.
26. `SCREEN` 옵션 화면. 차가운 것, 아이스.
27. `UP` 위로
28. `UP_SMALL` 위로 조금
29. `RIGHT` 오른쪽으로
30. `RIGHT_SMALL` 오른쪽 조금
31. `UP_SMALL` 위로 조금
32. `HOLD` 멈추세요.
33. `PRESS` 누르세요.
34. `PRESS_OK` 맞아요. 다음 담기.
35. `DOWN` 아래로
36. `DOWN_SMALL` 아래 조금
37. `HOLD` 멈추세요.
38. `PRESS` 누르세요.
39. `PRESS_OK` 맞아요.
40. `SCREEN` 담겼어요. 결제하기 버튼.
41. `RIGHT` 오른쪽으로
42. `RIGHT_SMALL` 오른쪽 조금
43. `HOLD` 멈추세요.
44. `PRESS` 누르세요.
45. `PRESS_OK` 맞아요.
46. `HAND_DOWN` 주문 확인. 손을 내려 주세요.
47. `PAY_CHECK` 아이스 아메리카노 한 잔, 2,000원. 맞으면 손을 올려 주세요. 결제하기 버튼.
48. `UP_SMALL` 위로 조금
49. `HOLD` 멈추세요.
50. `PRESS` 누르세요.
51. `PRESS_OK` 맞아요.
52. `HAND_DOWN` 결제 화면. 손을 내려 주세요.
53. `PAY_CHECK` 결제 금액 2,000원. 모의 결제예요. 손을 올려 주세요. 간편결제 버튼.
54. `UP` 위로
55. `UP_SMALL` 위로 조금
56. `HOLD` 멈추세요.
57. `PRESS` 누르세요.
58. `PRESS_OK` 맞아요.
59. `DONE` 주문 끝. 주문 번호 27번.

## 배치 A · 옵션 화면 '멈추세요' 직후 손 2.5초 사라짐

시도 `20261113-000835-a586` · 주문 번호 27 · 카운트 `{"presses": 7, "wrong_presses": 0, "reverts": 0, "hesitations": 3, "hand_lost": 1, "hand_down_requests": 2, "guides": 50}`

안내 문구 순서(실제로 낸 말만, 억제된 말 제외):

1. `SCREEN` 첫 화면. 매장 버튼.
2. `UP` 위로
3. `UP_SMALL` 위로 조금
4. `LEFT_SMALL` 왼쪽 조금
5. `UP_SMALL` 위로 조금
6. `HOLD` 멈추세요.
7. `PRESS` 누르세요.
8. `PRESS_OK` 맞아요.
9. `SCREEN` 메뉴 화면. 아메리카노.
10. `UP` 위로
11. `UP_SMALL` 위로 조금
12. `LEFT_SMALL` 왼쪽 조금
13. `HOLD` 멈추세요.
14. `PRESS` 누르세요.
15. `PRESS_OK` 맞아요.
16. `SCREEN` 옵션 화면. 차가운 것, 아이스.
17. `UP` 위로
18. `UP_SMALL` 위로 조금
19. `RIGHT_SMALL` 오른쪽 조금
20. `UP_SMALL` 위로 조금
21. `RIGHT_SMALL` 오른쪽 조금
22. `HOLD` 멈추세요.
23. `HAND_LOST` 손이 안 보여요.
24. `PRESS` 누르세요.
25. `PRESS_OK` 맞아요. 다음 담기.
26. `DOWN` 아래로
27. `DOWN_SMALL` 아래 조금
28. `HOLD` 멈추세요.
29. `PRESS` 누르세요.
30. `PRESS_OK` 맞아요.
31. `SCREEN` 담겼어요. 결제하기 버튼.
32. `RIGHT` 오른쪽으로
33. `RIGHT_SMALL` 오른쪽 조금
34. `HOLD` 멈추세요.
35. `PRESS` 누르세요.
36. `PRESS_OK` 맞아요.
37. `HAND_DOWN` 주문 확인. 손을 내려 주세요.
38. `PAY_CHECK` 아이스 아메리카노 한 잔, 2,000원. 맞으면 손을 올려 주세요. 결제하기 버튼.
39. `UP_SMALL` 위로 조금
40. `HOLD` 멈추세요.
41. `PRESS` 누르세요.
42. `PRESS_OK` 맞아요.
43. `HAND_DOWN` 결제 화면. 손을 내려 주세요.
44. `PAY_CHECK` 결제 금액 2,000원. 모의 결제예요. 손을 올려 주세요. 간편결제 버튼.
45. `UP` 위로
46. `UP_SMALL` 위로 조금
47. `HOLD` 멈추세요.
48. `PRESS` 누르세요.
49. `PRESS_OK` 맞아요.
50. `DONE` 주문 끝. 주문 번호 27번.

