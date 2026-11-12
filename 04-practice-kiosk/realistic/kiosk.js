// OpenKey 모의 키오스크 v2. 실거래 기능 없음.
// 터치 로그·화면 지도는 채점·데이터 정답 생성 전용이며 AI 안내 런타임 입력에 연결하지 않는다.
(function () {
  "use strict";
  const D = window.OPENKEY_LAYOUTS;
  const W = D.LOGICAL.width, H = D.LOGICAL.height;
  const MENU_BY_ID = Object.fromEntries(D.MENU.map((m) => [m.id, m]));
  const params = new URLSearchParams(location.search);
  const FIXED = params.get("fixed") === "1"; // 데이터 생성용: 타이머·자동 전환 정지, 주문번호 고정
  const LOG_KEY = "openkey-kiosk-realistic-v1";
  const IDLE_SECONDS = 120, TIMEOUT_SECONDS = 15, CARD_SECONDS = 4, DONE_SECONDS = 10;

  const state = {
    layout: D.LAYOUTS[params.get("layout")] ? params.get("layout") : "A",
    screen: "start", modal: null, dine: null,
    category: "all", page: 0, cart: [], draft: null,
    orderNo: FIXED ? 27 : 0, remain: IDLE_SECONDS, timeoutRemain: TIMEOUT_SECONDS,
    markers: params.get("markers") === "1", beep: params.get("beep") !== "0" && !FIXED,
    screenVersion: 0, flash: null,
    sessionId: new Date().toISOString().replace(/[-:]/g, "").slice(0, 15),
  };
  let log = loadLog();

  const stage = document.getElementById("stage");
  const frame = document.getElementById("frame");
  const staffEl = document.getElementById("staff");

  // ---------- 공통 ----------
  function loadLog() { try { return JSON.parse(localStorage.getItem(LOG_KEY) || "[]"); } catch (e) { return []; } }
  function saveLog() { try { localStorage.setItem(LOG_KEY, JSON.stringify(log)); } catch (e) { /* 메모리 로그 유지 */ } }
  function record(entry) {
    log.push(Object.assign({ t: new Date().toISOString(), ms: Math.round(performance.now()), session: state.sessionId,
      layout: state.layout, screen: screenId(), screenVersion: state.screenVersion }, entry));
    saveLog(); updateStaffCount();
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const num = (n) => n.toLocaleString("ko-KR");
  const won = (n) => num(n) + "원";
  const L = () => D.LAYOUTS[state.layout];
  const price = (n) => num(n) + L().priceSuffix;
  function screenId() { return state.modal ? state.screen + "+" + state.modal : state.screen; }

  function unitPrice(it) {
    const m = MENU_BY_ID[it.menu];
    return m.price + (it.size === "L" ? D.OPTION_PRICES.sizeL : 0) + (it.shot || 0) * D.OPTION_PRICES.shot;
  }
  const lineTotal = (it) => unitPrice(it) * it.qty;
  const cartTotal = () => state.cart.reduce((s, it) => s + lineTotal(it), 0);
  const cartCount = () => state.cart.reduce((s, it) => s + it.qty, 0);
  function optionText(it) {
    const m = MENU_BY_ID[it.menu], parts = [];
    if (it.temp) parts.push(it.temp);
    if (m.size) parts.push(it.size === "L" ? "라지" : "레귤러");
    if (it.shot) parts.push("샷 +" + it.shot);
    return parts.join(" / ");
  }
  function visibleMenu() {
    return D.MENU.filter((m) => state.category === "all" || m.cat === state.category);
  }
  const pageCount = () => Math.max(1, Math.ceil(visibleMenu().length / L().perPage));

  // ---------- 그림(SVG) ----------
  function art(m, size) {
    const index=D.MENU.findIndex(item=>item.id===m.id);
    if(index>=0)return `<span class="product-photo" style="--photo-x:${(index%4)*100/3}%;--photo-y:${Math.floor(index/4)*100/3}%" role="img" aria-label="${esc(m.name)} 상품 이미지"></span>`;
    const c = m.color, s = size;
    const wrap = (inner) => `<svg viewBox="0 0 200 200" width="${s}" height="${s}" aria-hidden="true">${inner}</svg>`;
    switch (m.art) {
      case "iced":
        return wrap(`<path d="M52 40 L148 40 L136 186 Q100 194 64 186 Z" fill="#eef3f6" stroke="#c9d3da" stroke-width="3"/>
          <path d="M58 80 L142 80 L135 182 Q100 189 65 182 Z" fill="${c}"/>
          <rect x="70" y="62" width="26" height="24" rx="5" fill="#fff" opacity=".75"/><rect x="100" y="70" width="24" height="22" rx="5" fill="#fff" opacity=".6"/>
          <rect x="82" y="96" width="22" height="20" rx="5" fill="#fff" opacity=".35"/><path d="M110 18 L118 18 L110 120" stroke="#2f6fb5" stroke-width="7" fill="none"/>
          <rect x="44" y="34" width="112" height="10" rx="5" fill="#dfe6eb"/>`);
      case "hot":
        return wrap(`<path d="M42 80 L150 80 L140 170 Q96 186 52 170 Z" fill="#fff" stroke="#d8d2cb" stroke-width="4"/>
          <path d="M150 98 Q182 102 176 130 Q170 152 144 150" fill="none" stroke="#d8d2cb" stroke-width="9"/>
          <ellipse cx="96" cy="82" rx="54" ry="13" fill="${c}"/><ellipse cx="96" cy="80" rx="34" ry="7" fill="#f3e6d6"/>
          <path d="M78 58 q-10 -14 0 -26 M100 56 q-10 -14 0 -28 M122 58 q-10 -14 0 -26" stroke="#c9c2bb" stroke-width="4" fill="none"/>
          <ellipse cx="96" cy="182" rx="66" ry="8" fill="#ece7e1"/>`);
      case "tea":
        return wrap(`<path d="M48 70 L152 70 L142 176 Q100 188 58 176 Z" fill="#f6f1e6" stroke="#d9cfbe" stroke-width="3"/>
          <path d="M53 96 L147 96 L141 172 Q100 182 59 172 Z" fill="${c}" opacity=".9"/>
          <circle cx="122" cy="72" r="20" fill="#f7d65a" stroke="#e9b93a" stroke-width="4"/><path d="M122 52 L122 92 M102 72 L142 72" stroke="#e9b93a" stroke-width="3"/>`);
      case "croffle":
        return wrap(`<ellipse cx="100" cy="150" rx="78" ry="16" fill="#eee"/><path d="M34 140 Q30 76 100 66 Q170 76 166 140 Q100 162 34 140 Z" fill="${c}" stroke="#b9823e" stroke-width="4"/>
          <path d="M56 92 L144 132 M60 124 L134 82 M86 74 L76 150 M118 74 L128 150" stroke="#b9823e" stroke-width="5"/><circle cx="100" cy="64" r="16" fill="#fff"/>`);
      case "cake":
        return wrap(`<ellipse cx="100" cy="160" rx="80" ry="16" fill="#eee"/><path d="M30 150 L170 150 L170 96 L30 70 Z" fill="${c}" stroke="#d8bf74" stroke-width="3"/>
          <path d="M30 70 L170 96 L170 108 L30 82 Z" fill="#c78d3b"/><path d="M30 150 L170 150 L170 140 L30 140 Z" fill="#b57f37"/>`);
      case "macaron":
        return wrap(`<ellipse cx="100" cy="160" rx="70" ry="12" fill="#eee"/><ellipse cx="100" cy="132" rx="62" ry="22" fill="${c}"/>
          <rect x="44" y="104" width="112" height="18" rx="9" fill="#fff4e8"/><ellipse cx="100" cy="98" rx="62" ry="24" fill="${c}"/>`);
      default: return wrap("");
    }
  }
  const ICON = {
    store: `<svg viewBox="0 0 120 120" width="180" height="180"><rect x="18" y="44" width="84" height="62" rx="4" fill="#2f6fd6"/><rect x="34" y="20" width="52" height="24" rx="6" fill="#1fa39a"/><path d="M14 44 h92 l-6 16 h-80z" fill="#e8f1ff"/><rect x="30" y="66" width="24" height="20" fill="#9fd0ff"/><path d="M68 106 V74 a10 10 0 0 1 20 0 V106z" fill="#1fa39a"/></svg>`,
    bag: `<svg viewBox="0 0 120 120" width="180" height="180"><path d="M24 44 h72 l-6 64 h-60z" fill="#e0524c"/><path d="M42 48 V32 a18 18 0 0 1 36 0 V48" fill="none" stroke="#f2c14e" stroke-width="7"/></svg>`,
    card: `<svg viewBox="0 0 120 120" width="150" height="150"><rect x="14" y="30" width="92" height="60" rx="8" fill="#2f6fd6"/><rect x="14" y="44" width="92" height="12" fill="#1b3f80"/><rect x="24" y="66" width="22" height="14" rx="3" fill="#f2c14e"/></svg>`,
    phone: `<svg viewBox="0 0 120 120" width="150" height="150"><rect x="36" y="14" width="48" height="92" rx="10" fill="#333"/><rect x="41" y="24" width="38" height="68" rx="3" fill="#ffe14d"/><path d="M50 58 l8 8 l14 -18" stroke="#333" stroke-width="6" fill="none"/></svg>`,
    insert: `<svg viewBox="0 0 300 260" width="420" height="364"><rect x="40" y="120" width="220" height="120" rx="14" fill="#dfe3e8"/><rect x="70" y="150" width="160" height="14" rx="7" fill="#333"/><g><rect x="96" y="20" width="108" height="150" rx="10" fill="#2f6fd6"/><rect x="116" y="40" width="30" height="22" rx="4" fill="#f2c14e"/></g><path d="M150 186 v40 m-16 -16 l16 16 l16 -16" stroke="#e0524c" stroke-width="8" fill="none"/></svg>`,
    check: `<svg viewBox="0 0 120 120" width="170" height="170"><circle cx="60" cy="60" r="54" fill="#2f6fd6"/><path d="M34 62 l18 18 l36 -40" stroke="#fff" stroke-width="10" fill="none" stroke-linecap="round"/></svg>`,
  };

  // ---------- 화면 ----------
  // data-role: button/menu_item/category_tab/option/input/modal (라벨 기준v2 클래스), data-hit: 터치 판정 대상
  const btn = (id, label, act, arg, cls, extra) =>
    `<button type="button" class="${cls || "btn"}" data-role="button" data-hit data-id="${id}" data-act="${act}"${arg !== undefined ? ` data-arg="${esc(arg)}"` : ""}${extra || ""}>${label}</button>`;

  function header() {
    if (state.layout === "A") {
      return `<header class="hdr-a">${btn("home", "처음으로", "home", undefined, "btn ghost hdr-home")}
        <div class="logo" data-role="text">MORU <b>COFFEE</b></div>
        <div class="remain" data-role="text">남은 시간 <b>${state.remain}</b>초</div></header>`;
    }
    return `<header class="hdr-b">${btn("home", "처음으로", "home", undefined, "btn ghost hdr-home")}
      <div class="logo" data-role="text">MORU <b>COFFEE</b></div>
      ${btn("staff-call", "직원 호출", "staffCall", undefined, "btn ghost hdr-staff")}</header>`;
  }

  function categoryList(cls) {
    return D.CATEGORIES.map((c) =>
      `<button type="button" class="${cls}${state.category === c.id ? " on" : ""}" data-role="category_tab" data-hit data-id="cat-${c.id}" data-act="cat" data-arg="${c.id}" data-selected="${state.category === c.id}">${c.name}</button>`).join("");
  }

  function grid() {
    const items = visibleMenu().slice(state.page * L().perPage, (state.page + 1) * L().perPage);
    const cards = items.map((m) => `
      <button type="button" class="card" data-role="menu_item" data-hit data-id="item-${m.id}" data-act="pick" data-arg="${m.id}">
        <span class="art">${art(m, state.layout === "A" ? 190 : 200)}</span>
        ${m.badge ? `<span class="badge ${m.badge === "NEW" ? "new" : ""}">${m.badge}</span>` : ""}
        <span class="name">${esc(m.name)}</span><span class="price" data-ocr="price">${price(m.price)}</span>
      </button>`).join("");
    const pc = pageCount();
    const pager = pc > 1 ? `<div class="pager">${btn("page-prev", "◀", "page", -1, "btn pg" + (state.page === 0 ? " off" : ""))}
      <span class="pg-num" data-role="text">${state.page + 1} / ${pc}</span>${btn("page-next", "▶", "page", 1, "btn pg" + (state.page >= pc - 1 ? " off" : ""))}</div>` : "";
    return `<div class="grid">${cards}</div>${pager}`;
  }

  function cartRows(max) {
    if (!state.cart.length) return `<div class="cart-empty" data-role="text"><span class="cube"></span>상품을 선택해 주세요.</div>`;
    const rows = state.cart.slice(0, max).map((it, i) => {
      const m = MENU_BY_ID[it.menu];
      return `<div class="cart-row" data-id="cart-${i}">
        <div class="cr-name"><span>${esc(m.name)}</span><small>${esc(optionText(it))}</small></div>
        <div class="stepper">${btn(`cart-${i}-minus`, "−", "cartQty", i + ":-1", "btn step")}<span class="qty" data-role="text">${it.qty}</span>${btn(`cart-${i}-plus`, "+", "cartQty", i + ":1", "btn step")}</div>
        <span class="cr-price" data-ocr="price">${price(lineTotal(it))}</span>
        ${btn(`cart-${i}-del`, "✕", "cartDel", i, "btn del")}</div>`;
    }).join("");
    const more = state.cart.length > max ? `<div class="cart-more" data-role="text">외 ${state.cart.length - max}개 상품</div>` : "";
    return rows + more;
  }

  function promotion(){return `<section class="promotion"><div><span class="promo-tag">MORU SEASONAL MENU</span><h2>매일의 커피, 조금 더 특별하게</h2><p>부드러운 라떼와 함께하는 달콤한 휴식</p></div><span class="promo-products"><i class="product-photo" style="--photo-x:33.333333%;--photo-y:0%"></i><i class="product-photo" style="--photo-x:100%;--photo-y:0%"></i></span></section>`;}
  function menuScreenA() {
    return `${header()}
      <nav class="cats-a">${categoryList("cat-a")}</nav>
      ${promotion()}<section class="panel-a">${grid()}</section>
      <section class="bottom-a">
        <div class="sum-a">
          <span class="lbl">총수량</span><b class="val">${cartCount()}</b>
          <span class="lbl">총금액</span><b class="val" data-ocr="price">${num(cartTotal())}</b>
          ${btn("clear", "전체삭제", "clear", undefined, "btn clear-a")}
          ${btn("checkout", "결제하기", "checkout", undefined, "btn primary pay-a" + (state.cart.length ? "" : " off"))}
        </div>
        <div class="cart-a">${cartRows(3)}</div>
      </section>`;
  }

  function menuScreenB() {
    return `${header()}
      <nav class="cats-b">${categoryList("cat-b")}</nav>
      ${promotion()}<section class="panel-b">${grid()}</section>
      <section class="bottom-b">
        <div class="cart-head"><b data-role="text">주문 내역</b>${btn("clear", "전체삭제", "clear", undefined, "btn ghost clear-b")}
          <span class="remain-b" data-role="text">남은 시간 <b>${state.remain}</b>초</span></div>
        <div class="cart-b">${cartRows(3)}</div>
        <button type="button" class="btn primary pay-b${state.cart.length ? "" : " off"}" data-role="button" data-hit data-id="checkout" data-act="checkout">
          <span class="pay-count">${cartCount()}개</span><span class="pay-total" data-ocr="price">${won(cartTotal())}</span><span class="pay-label">결제하기</span></button>
      </section>`;
  }

  function optionModal() {
    const d = state.draft, m = MENU_BY_ID[d.menu];
    const radio = (group, value, label, extra) => {
      const on = d[group] === value;
      return `<button type="button" class="opt${on ? " on" : ""}" data-role="option" data-hit data-id="opt-${group}-${value}" data-act="opt" data-arg="${group}:${value}" data-selected="${on}">
        <span class="dot"></span><span class="opt-label">${label}</span>${extra ? `<span class="opt-price" data-ocr="price">${extra}</span>` : ""}</button>`;
    };
    let groups = "";
    if (m.temps.length) {
      groups += `<div class="og"><div class="og-h"><b>온도</b><span class="req">필수</span></div>${m.temps.map((t) => radio("temp", t, t)).join("")}</div>`;
    }
    if (m.size) groups += `<div class="og"><div class="og-h"><b>사이즈</b></div>${radio("size", "R", "레귤러")}${radio("size", "L", "라지", "+" + num(D.OPTION_PRICES.sizeL))}</div>`;
    if (m.shot) {
      groups += `<div class="og"><div class="og-h"><b>샷 추가</b><span class="max">최대 ${D.OPTION_PRICES.shotMax}개</span></div>
        <div class="opt stepper-opt${d.shot ? " on" : ""}" data-role="option" data-id="opt-shot"><span class="opt-label">+ 1샷</span><span class="opt-price" data-ocr="price">+${num(D.OPTION_PRICES.shot)}</span>
        <div class="stepper">${btn("opt-shot-minus", "−", "shot", -1, "btn step")}<span class="qty" data-role="text">${d.shot}</span>${btn("opt-shot-plus", "+", "shot", 1, "btn step")}</div></div></div>`;
    }
    if (!groups) groups = `<div class="og"><div class="og-h"><b>옵션 없음</b></div><p class="og-note">수량을 선택하고 담기를 눌러 주세요.</p></div>`;
    return `<div class="dim"></div><section class="modal opt-modal" data-role="modal" data-id="modal-option">
      <div class="om-left"><span class="art">${art(m, 300)}</span><div class="om-name">${esc(m.name)}</div>
        <div class="om-desc">${esc(m.desc)}</div><div class="om-price" data-ocr="price">${price(m.price)}</div></div>
      <div class="om-right">${groups}</div>
      <div class="om-foot"><span class="om-total" data-ocr="price">${won(unitPrice(d) * d.qty)}</span>
        <div class="stepper big">${btn("draft-minus", "−", "draftQty", -1, "btn step")}<span class="qty" data-role="text">${d.qty}</span>${btn("draft-plus", "+", "draftQty", 1, "btn step")}</div>
        ${btn("opt-cancel", "취소", "optCancel", undefined, "btn gray om-cancel")}${btn("opt-add", "담기", "optAdd", undefined, "btn primary om-add")}</div>
      ${state.flash ? `<div class="flash" data-role="text">${esc(state.flash)}</div>` : ""}</section>`;
  }

  function confirmModal() {
    const rows = state.cart.slice(0, 5).map((it) => `<div class="cf-row"><span class="cf-name">${esc(MENU_BY_ID[it.menu].name)}<small>${esc(optionText(it))}</small></span>
      <span class="cf-qty">${it.qty}개</span><span class="cf-price" data-ocr="price">${won(lineTotal(it))}</span></div>`).join("");
    const more = state.cart.length > 5 ? `<div class="cf-more">외 ${state.cart.length - 5}개 상품</div>` : "";
    return `<div class="dim"></div><section class="modal cf-modal" data-role="modal" data-id="modal-confirm">
      <h2>주문 내역을 확인해 주세요</h2><div class="cf-dine">${state.dine || "매장"} 주문</div>
      <div class="cf-list">${rows}${more}</div>
      <div class="cf-total"><span>총 결제금액</span><b data-ocr="price">${won(cartTotal())}</b></div>
      <div class="cf-btns">${btn("cf-back", "이전", "closeModal", undefined, "btn gray")}${btn("cf-pay", "결제하기", "toPay", undefined, "btn primary")}</div></section>`;
  }

  function timeoutModal() {
    return `<div class="dim"></div><section class="modal to-modal" data-role="modal" data-id="modal-timeout">
      <h2>주문을 계속할까요?</h2><p>${state.timeoutRemain}초 뒤에 자동으로 주문이 종료돼요.</p>
      <div class="to-btns">${btn("to-end", "지금 끝내기", "home", undefined, "btn danger")}${btn("to-continue", "주문 계속", "continue", undefined, "btn primary")}</div></section>`;
  }

  function startScreen() {
    return `<div class="start">
      <div class="logo big" data-role="text">MORU <b>COFFEE</b></div>
      <h1>여기서 주문해 주세요.</h1><p class="sub">주문 종류 선택</p>
      <div class="dine">
        <button type="button" class="dine-card" data-role="button" data-hit data-id="dine-store" data-act="dine" data-arg="매장">${ICON.store}<span>매장</span></button>
        <button type="button" class="dine-card" data-role="button" data-hit data-id="dine-takeout" data-act="dine" data-arg="포장">${ICON.bag}<span>포장</span></button>
      </div>
      <div class="lang">${btn("lang-ko", "한국어", "lang", "ko", "btn lang-btn on")}${btn("lang-en", "English", "lang", "en", "btn lang-btn")}${btn("lang-zh", "中文", "lang", "zh", "btn lang-btn")}</div>
      ${btn("practice", "연습하기", "practice", undefined, "btn ghost practice-btn")}
      ${state.flash ? `<div class="flash" data-role="text">${esc(state.flash)}</div>` : ""}</div>`;
  }

  function payScreen() {
    return `<div class="pay">${header()}
      <h1>결제 수단을 선택해 주세요</h1><div class="pay-amt">결제 금액 <b data-ocr="price">${won(cartTotal())}</b></div>
      <div class="pay-cards">
        <button type="button" class="pay-card" data-role="button" data-hit data-id="pay-card" data-act="payMethod" data-arg="card">${ICON.card}<span>신용·체크카드</span></button>
        <button type="button" class="pay-card" data-role="button" data-hit data-id="pay-simple" data-act="payMethod" data-arg="simple">${ICON.phone}<span>간편결제</span></button>
      </div>
      <p class="mock-note">모의 결제입니다. 실제로 결제되지 않습니다.</p>
      ${btn("pay-back", "이전", "payBack", undefined, "btn gray pay-back")}</div>`;
  }

  function cardScreen() {
    return `<div class="cardpay">${header()}
      <h1>카드를 투입구에 꽂아 주세요</h1><p class="sub">IC칩이 위를 향하도록 끝까지 넣어 주세요.</p>
      <div class="insert">${ICON.insert}</div>
      <div class="pay-amt">결제 금액 <b data-ocr="price">${won(cartTotal())}</b></div>
      <p class="mock-note">모의 결제입니다. 실제로 결제되지 않습니다.</p>
      ${btn("card-cancel", "결제 취소", "payBack", undefined, "btn gray pay-back")}</div>`;
  }

  function doneScreen() {
    return `<div class="done"><div class="chk">${ICON.check}</div><h1>주문이 완료되었습니다</h1>
      <div class="ono-l">주문번호</div><div class="ono" data-role="text">${String(state.orderNo).padStart(3, "0")}</div>
      <p class="sub">번호가 호출되면 픽업대에서 받아 주세요.</p>
      <p class="rq">영수증을 출력할까요?</p>
      <div class="rc-btns">${btn("receipt-yes", "출력", "receipt", "yes", "btn primary")}${btn("receipt-no", "출력 안 함", "receipt", "no", "btn gray")}</div>
      <p class="back-note">잠시 후 처음 화면으로 돌아갑니다.</p></div>`;
  }

  function practiceScreen(kind) {
    const lr = kind === "lr";
    return `<div class="practice"><header class="hdr-b">${btn("home", "처음으로", "home", undefined, "btn ghost hdr-home")}<div class="logo" data-role="text">연습 모드</div><span></span></header>
      <h1>${lr ? "왼쪽·오른쪽 버튼 연습" : "위·아래 버튼 연습"}</h1>
      <div class="pr-${lr ? "lr" : "ud"}">${lr
        ? btn("pr-left", "왼쪽", "beep", undefined, "btn pr-big") + btn("pr-right", "오른쪽", "beep", undefined, "btn pr-big")
        : btn("pr-up", "위", "beep", undefined, "btn pr-big") + btn("pr-down", "아래", "beep", undefined, "btn pr-big")}</div>
      ${btn("pr-next", lr ? "위·아래 연습" : "좌우 연습", "practiceSwap", undefined, "btn primary pr-next")}</div>`;
  }

  function render() {
    let html = "";
    switch (state.screen) {
      case "start": html = startScreen(); break;
      case "menu": html = state.layout === "A" ? menuScreenA() : menuScreenB();
        if (state.modal === "option") html += optionModal();
        if (state.modal === "confirm") html += confirmModal();
        if (state.modal === "timeout") html += timeoutModal();
        break;
      case "pay": html = payScreen(); break;
      case "card": html = cardScreen(); break;
      case "done": html = doneScreen(); break;
      case "practice_lr": html = practiceScreen("lr"); break;
      case "practice_ud": html = practiceScreen("ud"); break;
    }
    stage.innerHTML = html + `<span class="corner tl"></span><span class="corner tr"></span><span class="corner bl"></span><span class="corner br"></span>`;
    stage.dataset.layout = state.layout;
    stage.dataset.screen = screenId();
    stage.classList.toggle("no-markers", !state.markers);
    state.screenVersion += 1;
  }

  function setScreen(screen, modal, reason) {
    const from = screenId();
    state.screen = screen; state.modal = modal || null; state.flash = null;
    render();
    if (from !== screenId()) record({ type: "screen", from: from, to: screenId(), reason: reason || "" });
  }

  function resetAll() {
    state.cart = []; state.draft = null; state.dine = null; state.category = "all"; state.page = 0;
    state.remain = IDLE_SECONDS; state.timeoutRemain = TIMEOUT_SECONDS;
  }

  // ---------- 동작 ----------
  const ACTIONS = {
    home() { resetAll(); setScreen("start", null, "home"); },
    dine(arg) { state.dine = arg; state.category = "all"; state.page = 0; setScreen("menu", null, "dine"); },
    lang(arg) { if (arg !== "ko") { state.flash = "현재 한국어만 지원합니다"; render(); } },
    practice() { setScreen("practice_lr", null, "practice"); },
    practiceSwap() { setScreen(state.screen === "practice_lr" ? "practice_ud" : "practice_lr", null, "practice"); },
    beep() {},
    staffCall() { /* 모의: 동작 없음 */ },
    cat(arg) { state.category = arg; state.page = 0; render(); },
    page(arg) { const p = state.page + Number(arg); if (p >= 0 && p < pageCount()) { state.page = p; render(); } },
    pick(arg) {
      const m = MENU_BY_ID[arg];
      state.draft = { menu: arg, temp: m.temps.length === 1 ? m.temps[0] : null, size: m.size ? "R" : null, shot: 0, qty: 1 };
      setScreen("menu", "option", "pick:" + arg);
    },
    opt(arg) { const [g, v] = arg.split(":"); state.draft[g] = v; state.flash = null; render(); },
    shot(arg) { state.draft.shot = Math.min(D.OPTION_PRICES.shotMax, Math.max(0, state.draft.shot + Number(arg))); render(); },
    draftQty(arg) { state.draft.qty = Math.min(20, Math.max(1, state.draft.qty + Number(arg))); render(); },
    optCancel() { state.draft = null; setScreen("menu", null, "opt-cancel"); },
    optAdd() {
      const d = state.draft, m = MENU_BY_ID[d.menu];
      if (m.temps.length && !d.temp) { state.flash = "온도를 선택해 주세요"; record({ type: "blocked", need: "temp" }); render(); return; }
      const same = state.cart.find((it) => it.menu === d.menu && it.temp === d.temp && it.size === d.size && it.shot === d.shot);
      if (same) same.qty += d.qty; else state.cart.push(Object.assign({}, d));
      state.draft = null; setScreen("menu", null, "add");
    },
    cartQty(arg) { const [i, dlt] = arg.split(":").map(Number); const it = state.cart[i]; if (it) { it.qty = Math.max(1, Math.min(20, it.qty + dlt)); render(); } },
    cartDel(arg) { state.cart.splice(Number(arg), 1); render(); },
    clear() { state.cart = []; render(); },
    checkout() { if (state.cart.length) setScreen("menu", "confirm", "checkout"); },
    closeModal() { setScreen("menu", null, "close"); },
    toPay() { setScreen("pay", null, "to-pay"); },
    payBack() { setScreen("menu", "confirm", "pay-back"); },
    payMethod(arg) {
      record({ type: "payMethod", method: arg });
      if (arg === "card") setScreen("card", null, "card"); else completeOrder("simple");
    },
    continue() { state.remain = IDLE_SECONDS; state.timeoutRemain = TIMEOUT_SECONDS; setScreen("menu", null, "continue"); },
    receipt() { resetAll(); setScreen("start", null, "receipt"); },
  };

  function completeOrder(method) {
    state.orderNo = FIXED ? 27 : state.orderNo + 1;
    record({ type: "mockOrder", method: method, total: cartTotal(), count: cartCount(), dine: state.dine,
      items: state.cart.map((it) => Object.assign({ unit: unitPrice(it) }, it)) });
    setScreen("done", null, "paid");
  }

  stage.addEventListener("click", (ev) => {
    const el = ev.target.closest("[data-act]");
    if (!el || el.classList.contains("off")) return;
    playBeep();
    record({ type: "activate", button: el.dataset.id });
    ACTIONS[el.dataset.act](el.dataset.arg);
  });

  // ---------- 화면 지도·글자 측정 ----------
  function normRect(r, s) {
    return [(r.left - s.left) / s.width, (r.top - s.top) / s.height, (r.right - s.left) / s.width, (r.bottom - s.top) / s.height]
      .map((v) => Math.round(v * 1e6) / 1e6);
  }
  function labelOf(el) {
    return el.innerText.replace(/\s+/g, " ").trim();
  }
  function textLines(s) {
    // 렌더링된 글자 한 줄 단위로 실제 범위를 측정한다(컨테이너 전체가 아님).
    const out = [];
    const walker = document.createTreeWalker(stage, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
    });
    let node;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      const cs = getComputedStyle(parent);
      if (cs.visibility === "hidden" || cs.display === "none" || parent.closest("svg")) continue;
      const lines = [];
      const str = node.nodeValue;
      for (let i = 0; i < str.length; i++) {
        if (!str[i].trim()) { if (lines.length) lines[lines.length - 1].text += str[i]; continue; }
        const rg = document.createRange(); rg.setStart(node, i); rg.setEnd(node, i + 1);
        const r = rg.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        let line = lines.find((l) => Math.abs(l.top - r.top) < r.height * 0.5);
        if (!line || line !== lines[lines.length - 1]) { line = { top: r.top, text: "", l: r.left, t: r.top, r: r.right, b: r.bottom }; lines.push(line); }
        line.text += str[i]; line.l = Math.min(line.l, r.left); line.t = Math.min(line.t, r.top); line.r = Math.max(line.r, r.right); line.b = Math.max(line.b, r.bottom);
      }
      const ocrEl = parent.closest("[data-ocr]");
      const owner = parent.closest("[data-id]");
      const dimmed = !!stage.querySelector(".dim") && !parent.closest(".modal");
      lines.forEach((ln) => out.push({
        text: ln.text.trim(), category: ocrEl && ocrEl.dataset.ocr === "price" ? "price" : "text",
        bbox: normRect({ left: ln.l, top: ln.t, right: ln.r, bottom: ln.b }, s),
        owner: owner ? owner.dataset.id : null, dimmed: dimmed,
        fontPx: Math.round(parseFloat(cs.fontSize)), color: cs.color,
      }));
    }
    return out;
  }
  function currentMap() {
    const s = stage.getBoundingClientRect();
    const regions = [...stage.querySelectorAll("[data-role]:not([data-role=text])")].map((el) => ({
      id: el.dataset.id || null, category: el.dataset.role, label: labelOf(el),
      bbox: normRect(el.getBoundingClientRect(), s),
      selected: el.dataset.selected === "true" || el.classList.contains("on"),
      enabled: !el.classList.contains("off"), hit: el.hasAttribute("data-hit"),
      dimmed: !!stage.querySelector(".dim") && !el.closest(".modal") && el.dataset.role !== "modal",
    }));
    return {
      coordinateSpace: "kiosk-stage-normalized", bboxFormat: "[left, top, right, bottom]",
      logical: { width: W, height: H }, stageCss: { width: s.width, height: s.height },
      layout: state.layout, screen: screenId(), screenVersion: state.screenVersion,
      regions: regions, texts: textLines(s),
      order: { dine: state.dine, cart: JSON.parse(JSON.stringify(state.cart)), draft: state.draft && Object.assign({}, state.draft),
        cartTotal: cartTotal(), cartCount: cartCount(), draftTotal: state.draft ? unitPrice(state.draft) * state.draft.qty : null,
        orderNo: state.orderNo, category: state.category, page: state.page },
    };
  }

  // 데이터 생성기·회귀 검증용 상태 주입(직원/개발 전용).
  function setState(spec) {
    resetAll();
    state.screen = "start"; state.modal = null; state.flash = null;
    ["layout", "screen", "modal", "dine", "category", "page", "orderNo", "remain", "timeoutRemain", "flash"].forEach((k) => { if (k in spec) state[k] = spec[k]; });
    state.cart = (spec.cart || []).map((it) => Object.assign({ temp: null, size: MENU_BY_ID[it.menu].size ? "R" : null, shot: 0, qty: 1 }, it));
    state.draft = spec.draft ? Object.assign({ temp: null, size: MENU_BY_ID[spec.draft.menu].size ? "R" : null, shot: 0, qty: 1 }, spec.draft) : null;
    render();
    return currentMap();
  }

  // ---------- 터치 기록(판정은 렌더링된 영역 기준) ----------
  stage.addEventListener("pointerdown", (ev) => {
    const s = stage.getBoundingClientRect();
    const x = (ev.clientX - s.left) / s.width, y = (ev.clientY - s.top) / s.height;
    if (x < 0 || y < 0 || x > 1 || y > 1) return;
    const modal = stage.querySelector(".modal");
    let best = null, bestArea = Infinity;
    stage.querySelectorAll("[data-hit]").forEach((el) => {
      if (modal && !el.closest(".modal")) return; // 모달 뒤는 눌리지 않음
      const b = normRect(el.getBoundingClientRect(), s);
      if (x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3]) { const a = (b[2] - b[0]) * (b[3] - b[1]); if (a < bestArea) { best = el; bestArea = a; } }
    });
    record({ type: "touch", x: +x.toFixed(4), y: +y.toFixed(4), hit: best ? best.dataset.id : null, pointer: ev.pointerType });
    state.remain = IDLE_SECONDS;
    staffTap(x, y);
  }, true);

  // ---------- 타이머(고정 모드에서는 정지) ----------
  if (!FIXED) {
    setInterval(() => {
      if (state.screen === "menu" && state.modal !== "timeout") {
        state.remain -= 1;
        if (state.remain <= 0) { state.timeoutRemain = TIMEOUT_SECONDS; setScreen("menu", "timeout", "idle"); return; }
        const r = stage.querySelector(".remain b, .remain-b b"); if (r) r.textContent = state.remain;
      } else if (state.modal === "timeout") {
        state.timeoutRemain -= 1;
        if (state.timeoutRemain <= 0) { resetAll(); setScreen("start", null, "timeout"); } else render();
      }
    }, 1000);
  }
  let autoTimer = null;
  const observer = new MutationObserver(() => {
    if (FIXED) return;
    clearTimeout(autoTimer);
    if (state.screen === "card") autoTimer = setTimeout(() => completeOrder("card"), CARD_SECONDS * 1000);
    if (state.screen === "done") autoTimer = setTimeout(() => { resetAll(); setScreen("start", null, "done-auto"); }, DONE_SECONDS * 1000);
  });
  observer.observe(stage, { attributes: true, attributeFilter: ["data-screen"] });

  // ---------- 화면 맞춤(논리 1080×1920을 창 크기에 맞춰 축소) ----------
  function fit() {
    const sc = Math.min(window.innerWidth / W, window.innerHeight / H);
    stage.style.transform = `scale(${sc})`;
    frame.style.width = W * sc + "px"; frame.style.height = H * sc + "px";
  }
  window.addEventListener("resize", fit);

  // ---------- 소리 ----------
  let audioCtx = null;
  function playBeep() {
    if (!state.beep) return;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.frequency.value = 1200; g.gain.setValueAtTime(0.12, audioCtx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.08);
      o.connect(g).connect(audioCtx.destination); o.start(); o.stop(audioCtx.currentTime + 0.09);
    } catch (e) { /* 소리 없이 진행 */ }
  }

  // ---------- 직원 메뉴 ----------
  let taps = [];
  function staffTap(x, y) {
    if (x > 0.08 || y > 0.04) return;
    const now = performance.now();
    taps = taps.filter((t) => now - t < 1500).concat(now);
    if (taps.length >= 3) { taps = []; openStaff(); }
  }
  document.addEventListener("keydown", (e) => { if (e.key === "s" || e.key === "S") staffEl.hidden ? openStaff() : (staffEl.hidden = true); });
  function openStaff() {
    staffEl.hidden = false;
    document.getElementById("staff-layout").value = state.layout;
    document.getElementById("staff-markers").checked = state.markers;
    document.getElementById("staff-beep").checked = state.beep;
    updateStaffCount();
  }
  function updateStaffCount() { const el = document.getElementById("staff-count"); if (el) el.textContent = log.length + "건 (세션 " + state.sessionId + ")"; }
  function download(name, text, type) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: type })); a.download = name;
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  function logCsv() {
    const cols = ["t", "ms", "session", "layout", "screen", "screenVersion", "type", "x", "y", "hit", "button", "from", "to", "reason", "pointer"];
    const q = (v) => (v === undefined || v === null ? "" : /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v));
    return "﻿" + [cols.join(",")].concat(log.map((r) => cols.map((c) => q(r[c])).join(","))).join("\n");
  }
  document.getElementById("staff-close").onclick = () => { staffEl.hidden = true; };
  document.getElementById("staff-layout").onchange = (e) => { state.layout = e.target.value; resetAll(); setScreen("start", null, "layout:" + state.layout); };
  document.getElementById("staff-markers").onchange = (e) => { state.markers = e.target.checked; render(); };
  document.getElementById("staff-beep").onchange = (e) => { state.beep = e.target.checked; };
  document.getElementById("staff-reset").onclick = () => { resetAll(); setScreen("start", null, "staff-reset"); staffEl.hidden = true; };
  document.getElementById("staff-json").onclick = () => download("touch-log-" + state.sessionId + ".json", JSON.stringify(log, null, 1), "application/json");
  document.getElementById("staff-csv").onclick = () => download("touch-log-" + state.sessionId + ".csv", logCsv(), "text/csv");
  document.getElementById("staff-map").onclick = () => download("screen-map-" + state.layout + "-" + screenId() + ".json", JSON.stringify(currentMap(), null, 1), "application/json");
  document.getElementById("staff-clear").onclick = () => {
    if (confirm("터치 로그 " + log.length + "건을 지울까요? 먼저 내려받았는지 확인하세요.")) { log = []; saveLog(); updateStaffCount(); }
  };

  window.OPENKEY_KIOSK = { state: state, setState: setState, currentMap: currentMap, getLog: () => log, actions: ACTIONS, fixed: FIXED };
  document.getElementById('fullscreen').onclick=()=>document.documentElement.requestFullscreen?.().catch(()=>{});
  if(params.get('screen')==='menu'){state.screen='menu';state.dine='매장';}
  fit();
  record({ type: "boot", userAgent: navigator.userAgent, viewport: [innerWidth, innerHeight], fixed: FIXED });
  render();
})();
