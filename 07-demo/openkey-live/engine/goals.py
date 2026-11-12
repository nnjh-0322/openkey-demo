"""주문 목표와 화면별 목표 버튼 계획(순수 로직).

입력은 모의 키오스크가 보고한 화면 지도(currentMap 형식)다. 버튼 위치는
시연용 정답 좌표(button_source="kiosk_ground_truth")이며 OCR 결과가 아니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STEPS = [
    {"step": 1, "name": "menu", "label": "메뉴 고르기"},
    {"step": 2, "name": "option", "label": "옵션"},
    {"step": 3, "name": "confirm", "label": "확인"},
    {"step": 4, "name": "pay", "label": "결제"},
    {"step": 5, "name": "done", "label": "주문 번호"},
]
STEP_NAME = {s["step"]: s["name"] for s in STEPS}

# 결제·금액이 보이는 화면: 항상 손을 내리고 전체 확인 후 진행(지시문 2절).
PAYMENT_SCREENS = {"menu+confirm", "pay"}

CAT_NAME = {"coffee": "커피", "noncoffee": "논커피", "tea": "티", "dessert": "디저트", "all": "전체 메뉴"}

GOALS = {
    "iced-americano-1": {"id": "iced-americano-1", "label": "아이스 아메리카노 한 잔", "menu": "americano", "name": "아메리카노",
                          "cat": "coffee", "temp": "ICE", "temp_say": "차가운 것, 아이스", "qty": 1, "dine": "매장", "say": "아이스 아메리카노 한 잔"},
    "hot-latte-1": {"id": "hot-latte-1", "label": "따뜻한 카페라떼 한 잔", "menu": "latte", "name": "카페라떼",
                     "cat": "coffee", "temp": "HOT", "temp_say": "따뜻한 것, 핫", "qty": 1, "dine": "매장", "say": "따뜻한 카페라떼 한 잔"},
    "coldbrew-1": {"id": "coldbrew-1", "label": "콜드브루 한 잔(포장)", "menu": "coldbrew", "name": "콜드브루",
                    "cat": "coffee", "temp": "ICE", "temp_say": "차가운 것", "qty": 1, "dine": "포장", "say": "콜드브루 한 잔, 포장"},
}
DEFAULT_GOAL = "iced-americano-1"


def goal_public(g: dict) -> dict:
    """attempt_start.goal 형식."""
    return {"id": g["id"], "label": g["label"], "steps": [
        {"step": 1, "screen": "menu", "target_label": g["name"], "required": True},
        {"step": 2, "screen": "menu+option", "target_label": g["temp"], "required": True},
        {"step": 3, "screen": "menu+confirm", "target_label": "결제하기", "required": True},
        {"step": 4, "screen": "pay", "target_label": "간편결제(모의)", "required": True},
        {"step": 5, "screen": "done", "target_label": "주문 번호", "required": True},
    ]}


def goals_list() -> list:
    return [{"id": g["id"], "label": g["label"], "default": g["id"] == DEFAULT_GOAL} for g in GOALS.values()]


@dataclass
class Plan:
    step: int
    target_id: str | None = None
    label: str | None = None          # 말로 부를 버튼 이름
    kind: str = "forward"             # forward | revert | fix | none
    announce: str | None = None       # 새 화면에서 할 짧은 화면 안내
    announce_code: str = "SCREEN"
    pay_check: str | None = None      # 손 내림 뒤 읽어 줄 금액 안내
    payment: bool = False
    screen_name: str = ""
    done: bool = False
    order_no: int | None = None
    notes: list = field(default_factory=list)


def josa(word: str, pair: str) -> str:
    """받침에 따라 조사를 붙인다. pair 예: '을/를', '이/가', '은/는'."""
    a, b = pair.split("/")
    ch = (word or " ").strip()[-1:]
    if "가" <= ch <= "힣":
        return word + (a if (ord(ch) - 0xAC00) % 28 else b)
    return word + b


def won(n) -> str:
    return f"{int(n):,}원"


def _line_ok(it: dict, g: dict) -> bool:
    return it.get("menu") == g["menu"] and (not g.get("temp") or it.get("temp") == g["temp"])


def cart_state(order: dict, g: dict) -> str:
    """'empty' | 'goal'(정확히 목표만) | 'extra'(목표 아닌 것·수량 다름)."""
    cart = (order or {}).get("cart") or []
    if not cart:
        return "empty"
    if all(_line_ok(it, g) for it in cart) and sum(int(it.get("qty") or 0) for it in cart) == g["qty"]:
        return "goal"
    return "extra"


def hit_regions(kiosk: dict) -> dict:
    return {r["id"]: r for r in (kiosk.get("regions") or []) if r.get("hit") and r.get("id") and not r.get("dimmed")}


def plan_target(goal: dict, kiosk: dict) -> Plan:
    """현재 화면에서 다음에 눌러야 할 버튼을 정한다."""
    scr = kiosk.get("screen") or ""
    order = kiosk.get("order") or {}
    regs = hit_regions(kiosk)
    g = goal
    cs = cart_state(order, g)

    def pick(step, rid, label, **kw):
        r = regs.get(rid)
        if not r or not r.get("enabled", True):
            p = Plan(step=step, kind="none", **{k: v for k, v in kw.items() if k != "kind"})
            p.notes.append(f"target_missing:{rid}")
            return p
        return Plan(step=step, target_id=rid, label=label, **kw)

    if scr == "start":
        rid = "dine-takeout" if g.get("dine") == "포장" else "dine-store"
        return pick(1, rid, g.get("dine", "매장"), screen_name="주문 시작 화면",
                    announce=f"첫 화면. {g.get('dine', '매장')} 버튼.")
    if scr.startswith("practice"):
        return pick(1, "home", "처음으로", kind="revert", screen_name="연습 화면",
                    announce="연습 화면. 처음으로 버튼.")
    if scr == "menu+timeout":
        return pick(1, "to-continue", "주문 계속", kind="fix", screen_name="시간 안내 창",
                    announce="시간 초과 창. 주문 계속 버튼.")
    if scr == "menu+option":
        d = order.get("draft") or {}
        if d.get("menu") != g["menu"]:
            return pick(1, "opt-cancel", "취소", kind="revert", screen_name="옵션 화면",
                        announce="다른 메뉴예요. 취소 버튼.")
        if g.get("temp") and d.get("temp") != g["temp"]:
            return pick(2, f"opt-temp-{g['temp']}", g["temp"], screen_name="옵션 화면",
                        announce=f"옵션 화면. {g['temp_say']}.")
        qty = int(d.get("qty") or 1)
        if qty > g["qty"]:
            return pick(2, "draft-minus", "빼기", kind="fix", screen_name="옵션 화면", announce="수량 빼기.")
        if qty < g["qty"]:
            return pick(2, "draft-plus", "더하기", kind="fix", screen_name="옵션 화면", announce="수량 더하기.")
        return pick(2, "opt-add", "담기", screen_name="옵션 화면", announce="담기 버튼.")
    if scr == "menu+confirm":
        total = order.get("cartTotal") or 0
        if cs != "goal":
            return pick(3, "cf-back", "이전", kind="revert", screen_name="주문 확인 화면",
                        announce="주문이 달라요. 이전 버튼.")
        return pick(3, "cf-pay", "결제하기", screen_name="주문 확인 화면", payment=True,
                    announce="주문 확인.",
                    pay_check=f"{g['say']}, {won(total)}. 맞으면 손을 올려 주세요. 결제하기 버튼.")
    if scr == "menu":
        if cs == "extra":
            return pick(1, "clear", "전체삭제", kind="fix", screen_name="메뉴 화면",
                        announce="다른 메뉴가 담겼어요. 전체삭제 버튼.")
        if cs == "goal":
            return pick(3, "checkout", "결제하기", screen_name="메뉴 화면",
                        announce="담겼어요. 결제하기 버튼.")
        item = f"item-{g['menu']}"
        if item in regs:
            return pick(1, item, g["name"], screen_name="메뉴 화면", announce=f"메뉴 화면. {g['name']}.")
        if int(order.get("page") or 0) > 0 and "page-prev" in regs:
            return pick(1, "page-prev", "이전 쪽", kind="fix", screen_name="메뉴 화면",
                        announce=f"{g['name']}는 앞쪽에. 이전 쪽 버튼.")
        cat = g.get("cat", "all")
        return pick(1, f"cat-{cat}", CAT_NAME.get(cat, cat), kind="fix", screen_name="메뉴 화면",
                    announce=f"메뉴 화면. {CAT_NAME.get(cat, cat)} 탭.")
    if scr == "pay":
        total = order.get("cartTotal") or 0
        return pick(4, "pay-simple", "간편결제", screen_name="결제 화면", payment=True,
                    announce="결제 화면.",
                    pay_check=f"결제 금액 {won(total)}. 모의 결제예요. 손을 올려 주세요. 간편결제 버튼.")
    if scr == "card":
        return pick(4, "card-cancel", "결제 취소", kind="revert", screen_name="카드 결제 화면",
                    announce="카드 화면이에요. 결제 취소 버튼.")
    if scr == "done":
        no = order.get("orderNo")
        return Plan(step=5, kind="none", screen_name="주문 완료 화면", done=True, order_no=no, announce_code="DONE",
                    announce=f"주문 끝. 주문 번호 {int(no)}번." if no is not None else "주문이 끝났어요.")
    return Plan(step=1, kind="none", screen_name="알 수 없는 화면", announce=None, notes=[f"unknown_screen:{scr}"])
