// OpenKey 안내 콘솔 — SCHEMA.md 5절 실시간 API 계약만 사용한다. 프레임워크·빌드 없음.
// 없는 값(null), 끊긴 연결, 시도 없음 상태를 모두 견디게 쓴다.
"use strict";

const $ = (id) => document.getElementById(id);
const API = ""; // 같은 출처(/admin/ 을 제공하는 서버)
const LIVE_MS = 160;
const STEP_SUB = { done: "완료", active: "지금", todo: "" };
const SOURCE_LABEL = { synthetic: "예시 데이터 (합성)", rehearsal: "연습 기록 (팀원)", field: "실제 사용자 기록" };
const RESULT_LABEL = { correct: "맞게 누름", wrong: "다른 버튼", no_button: "버튼 밖", no_target: "목표 없음" };
const SAFETY_LABEL = {
  not_on_target: "손끝이 목표 위에 있지 않음", hand_lost: "손을 놓침", not_aligned: "위치 맞춤 전",
  stale_target: "화면이 바뀌어 목표를 다시 정하는 중", screen_changed: "화면이 바뀌어 목표를 다시 정하는 중",
  no_target: "목표 버튼 없음", paused: "안내 멈춤 중", ok: "조건 충족", no_attempt: "시도 전",
  hand_down_check: "결제 금액 확인을 위해 손 내림 확인 중", screen_unreadable: "새 화면을 아직 읽지 못함", kiosk_lost: "키오스크 화면 정보가 끊김",
  no_hand: "손이 보이지 않음", multiple_hands: "키오스크 앞에 손이 두 개 이상", dwell: "목표 위에서 잠시 머무는 중",
};
const SCREEN_LABEL = { menu: "메뉴", option: "옵션", confirm: "주문 확인", pay: "결제", done: "주문 번호", dine: "매장/포장", start: "시작(매장/포장)", payment: "결제" };
const screenName = (v) => String(v).split("+").map((x) => SCREEN_LABEL[x] || x).join(" · ");
const DIR_OF = { LEFT: [-1, 0], RIGHT: [1, 0], UP: [0, -1], DOWN: [0, 1] };
const END_LABEL = { done: "완료", aborted: "중단", timeout: "시간 초과", error: "오류" };

const state = {
  live: null, lastOk: 0, fails: 0, online: null,
  goals: [], attemptId: null, evSeq: 0, guides: [], orderNo: null, lastEvPress: null,
  frame: null, frameErr: null, frameMissing: false, viewMode: "auto",
  pendingPause: null, ended: null, prevComplete: false,
};

// ---------------------------------------------------------------- 공통
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v) => typeof v === "number" && isFinite(v);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const store = {
  get(k, d) { try { const v = localStorage.getItem("ok-admin-" + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("ok-admin-" + k, JSON.stringify(v)); } catch (e) { /* 저장 안 돼도 동작 */ } },
};
function fmtSec(ms) { return num(ms) ? (ms / 1000).toFixed(1) + "초" : "—"; }
function fmtClock(ms) {
  if (!num(ms)) return "";
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return String(iso).slice(0, 16);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
async function getJSON(path, timeout = 2500) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeout);
  try {
    const r = await fetch(API + path, { signal: ac.signal, cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}
async function postJSON(path, body) {
  const r = await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  let j = null;
  try { j = await r.json(); } catch (e) { /* 빈 응답 허용 */ }
  if (!r.ok) throw new Error((j && (j.error || j.message)) || "HTTP " + r.status);
  return j || {};
}
const asList = (j, ...keys) => (Array.isArray(j) ? j : (j && keys.map((k) => j[k]).find(Array.isArray)) || []);
function setMsg(text, err) { const m = $("runMsg"); m.textContent = text || ""; m.className = "msg" + (err ? " err" : ""); }

// ---------------------------------------------------------------- 실시간 상태
async function liveLoop() {
  for (;;) {
    const t0 = performance.now();
    try {
      const j = await getJSON("/api/live", 2000);
      state.live = j; state.lastOk = Date.now(); state.fails = 0;
      onLive(j);
      setOnline(true);
    } catch (e) {
      state.fails++;
      if (state.fails >= 2 || Date.now() - state.lastOk > 1500) setOnline(false);
    }
    await sleep(Math.max(40, (state.online === false ? 1000 : LIVE_MS) - (performance.now() - t0)));
  }
}
function setOnline(on) {
  const el = $("conn");
  if (on) { el.className = "conn ok"; el.lastChild.textContent = "서버 연결됨"; }
  else {
    const ago = state.lastOk ? Math.round((Date.now() - state.lastOk) / 1000) : null;
    el.className = "conn bad"; el.lastChild.textContent = ago == null ? "서버에 연결할 수 없음 · 다시 시도 중" : `서버 연결 끊김 · ${ago}초 전 상태 표시 중`;
  }
  if (state.online !== on) {
    document.body.classList.toggle("offline", !on);
    $("offlineBanner").hidden = on;
    state.online = on;
    if (on) { loadGoals(); loadAttempts(); }
    renderRun();
  }
}

function onLive(L) {
  const aid = L.attempt && L.attempt.id || null;
  if (aid !== state.attemptId) {
    const ended = state.attemptId && !aid;
    if (ended) {
      // 시도가 끝나도(서버가 주문 번호에서 스스로 끝내는 경우 포함) 안내 기록과 완료 표시를 잠시 유지
      const la = L.last_attempt && (!L.last_attempt.id || L.last_attempt.id === state.attemptId) ? L.last_attempt : null;
      state.ended = { id: state.attemptId, at: Date.now(), completed: la ? la.completed === true : state.prevComplete,
        order_no: la && num(la.order_no) ? la.order_no : state.orderNo, total_ms: la ? la.total_ms : null, end_reason: la ? la.end_reason : null };
      setMsg("시도가 끝났습니다. 기록은 지난 시도에서 내려받을 수 있습니다.");
      loadAttempts();
    } else {
      state.guides = []; state.orderNo = null; state.lastEvPress = null; state.ended = null;
    }
    state.attemptId = aid; state.evSeq = 0;
    if (aid) loadAttempts();
  }
  if (L.attempt) state.prevComplete = stepsDone(L) || !!(L.kiosk && L.kiosk.screen === "done");
  if (L.guide && L.guide.text) addGuide({ code: L.guide.code, text: L.guide.text, ms: L.guide.ms });
  if (num(L.order_no)) state.orderNo = L.order_no;
  renderHeader(L); renderProgress(L); renderGuide(L); renderCounts(L); renderStatus(L); renderRun();
}

function addGuide(g) {
  const list = state.guides;
  const dup = list.find((x) => x.code === g.code && x.text === g.text && (!num(x.ms) || !num(g.ms) || Math.abs(x.ms - g.ms) < 400));
  if (dup) return;
  list.push(g);
  list.sort((a, b) => (num(a.ms) && num(b.ms) ? a.ms - b.ms : 0));
  if (list.length > 40) list.splice(0, list.length - 40);
}

// ---------------------------------------------------------------- 기록(이벤트) 받기
async function eventsLoop() {
  for (;;) {
    const aid = state.attemptId;
    if (!aid || state.online === false) { await sleep(800); continue; }
    try {
      const j = await getJSON(`/api/events?after=${state.evSeq}`, 4000);
      if (state.attemptId !== aid) continue;
      if (j && !Array.isArray(j) && j.attempt && j.attempt !== aid) { await sleep(300); continue; }
      const recs = asList(j, "events", "records", "items");
      if (j && num(j.last_seq)) state.evSeq = Math.max(state.evSeq, j.last_seq);
      for (const r of recs) {
        if (r.attempt && r.attempt !== aid) continue;
        if (num(r.seq)) state.evSeq = Math.max(state.evSeq, r.seq);
        if (r.kind === "guide" && !r.suppressed && r.text) addGuide({ code: r.code, text: r.text, ms: r.ms });
        else if (r.kind === "press") state.lastEvPress = r;
        else if (r.kind === "attempt_end" && num(r.order_no)) state.orderNo = r.order_no;
        else if (r.kind === "guide" && r.code === "DONE") { const m = /(\d+)\s*번/.exec(r.text || ""); if (m && !state.orderNo) state.orderNo = +m[1]; }
      }
      if (!recs.length) await sleep(150);
    } catch (e) { await sleep(1000); }
  }
}

// ---------------------------------------------------------------- 그리기: 머리줄
function renderHeader(L) {
  const src = (L.attempt && L.attempt.data_source) || null;
  const serverSyn = L.data_source === "synthetic" || L.mock === true || !!(L.status && L.status.input === "synthetic");
  const el = $("source");
  let txt = "", cls = "source";
  if (src) { txt = SOURCE_LABEL[src] || src; cls += " " + src; }
  if (serverSyn && src !== "synthetic") txt = (txt ? txt + " · " : "") + (L.mock === true || L.data_source === "synthetic" ? "모의 서버 예시 데이터" : "합성 입력");
  if (serverSyn && src === "synthetic") cls = "source synthetic";
  if (serverSyn && !src) cls = "source synthetic";
  el.hidden = !txt; el.textContent = txt; el.className = cls;
  const bs = L.button_source;
  const b = $("btnSource");
  b.hidden = !bs;
  b.textContent = bs === "kiosk_ground_truth" ? "버튼 위치: 시연용 정답 좌표 사용" : bs === "ocr" ? "버튼 위치: 카메라 글자 인식(OCR)" : "버튼 위치: " + bs;
}

// ---------------------------------------------------------------- 주문 진행
function stepsDone(L) { const s = L.steps || []; return s.length > 0 && s.every((x) => x.status === "done"); }
function renderProgress(L) {
  $("goalLabel").textContent = L.goal && L.goal.label ? "목표 · " + L.goal.label : "목표 없음";
  $("elapsed").textContent = L.attempt && num(L.attempt.ms) ? "경과 " + fmtClock(L.attempt.ms) : L.attempt ? "" : "시도 전";
  const E = !L.attempt && state.ended && Date.now() - state.ended.at < 30000 ? state.ended : null;
  const allDone = (n) => ({ step: n.step, name: n.name, label: n.label, status: "done" });
  const steps = Array.isArray(L.steps) && L.steps.length ? (E && E.completed ? L.steps.map(allDone) : L.steps)
    : ["menu", "option", "confirm", "pay", "done"].map((n, i) => ({ step: i + 1, name: n, label: ["메뉴 고르기", "옵션", "확인", "결제", "주문 번호"][i], status: "todo" }));
  const html = steps.map((s, i) => {
    const st = ["done", "active", "todo"].includes(s.status) ? s.status : "todo";
    return `<li class="${st}"${st === "active" ? ' aria-current="step"' : ""}><span class="dot num">${esc(s.step ?? i + 1)}</span><span>${esc(s.label || s.name)}</span><span class="sub">${STEP_SUB[st]}</span></li>`;
  }).join("");
  if ($("steps").innerHTML !== html) $("steps").innerHTML = html;
  const k = L.kiosk || {};
  const line = $("screenLine");
  const complete = stepsDone(L) || k.screen === "done";
  if (complete && L.attempt) {
    line.className = "screen-line complete";
    line.innerHTML = state.orderNo ? `주문을 마쳤습니다 · 주문 번호 <b class="num">${esc(state.orderNo)}</b>` : "주문을 마쳤습니다";
    return;
  }
  const la = !L.attempt && (state.ended || L.last_attempt);
  if (la) {
    const ok = la.completed === true;
    line.className = "screen-line" + (ok && E ? " complete" : "");
    const parts = [ok ? "직전 시도 · 주문을 마쳤습니다" : `직전 시도 · ${END_LABEL[la.end_reason] || "종료"}`];
    if (ok && num(la.order_no)) parts.push(`주문 번호 <b class="num">${esc(la.order_no)}</b>`);
    if (num(la.total_ms)) parts.push(fmtSec(la.total_ms));
    line.innerHTML = parts.join(" · ");
    return;
  }
  line.className = "screen-line";
  if (L.kiosk === null || k.connected === false) { line.textContent = "키오스크 화면이 연결되지 않았습니다"; return; }
  const parts = [];
  if (k.screen) parts.push(`키오스크 화면 <b>${esc(screenName(k.screen))}</b>`);
  if (k.layout) parts.push(`배치 ${esc(k.layout)}`);
  const tv = L.target && num(L.target.screen_version) && num(k.screen_version) && L.target.screen_version !== k.screen_version;
  if (L.target && L.target.label) parts.push(`목표 버튼 <b>${esc(L.target.label)}</b>${tv ? " (화면이 바뀌어 다시 정하는 중)" : ""}`);
  else if (L.attempt) parts.push("목표 버튼 정하는 중");
  line.innerHTML = parts.join(" · ") || "키오스크 화면 정보를 기다리는 중";
}

// ---------------------------------------------------------------- 지금 안내
function renderGuide(L) {
  const g = state.guides;
  const now = $("guideNow");
  const cur = g[g.length - 1];
  const nowMs = L.attempt && num(L.attempt.ms) ? L.attempt.ms : null;
  if (cur) {
    now.textContent = cur.text;
    const age = nowMs != null && num(cur.ms) ? nowMs - cur.ms : null;
    now.className = "guide-now" + (age != null && age > 8000 ? " stale" : "");
    $("guideMeta").textContent = age != null ? (age < 1000 ? "방금" : `${Math.round(age / 1000)}초 전`) : "";
  } else {
    now.textContent = L.attempt ? "아직 나간 안내가 없습니다" : "시도를 시작하면 휴대폰이 안내를 읽습니다";
    now.className = "guide-now empty";
    $("guideMeta").textContent = "";
  }
  const prev = g.slice(0, -1).slice(-10).reverse();
  const html = prev.map((x) => `<li><span>${esc(x.text)}</span><span class="t num">${num(x.ms) ? fmtSec(x.ms) : ""}</span></li>`).join("");
  const gp = $("guidePrev");
  if (gp.innerHTML !== html) gp.innerHTML = html;
  // 칸에 다 들어가지 않는 줄은 반쯤 잘려 보이지 않게 숨김
  const limit = gp.clientHeight;
  for (const li of gp.children) li.style.visibility = li.offsetTop - gp.offsetTop + li.offsetHeight > limit + 1 ? "hidden" : "";
  const paused = L.paused === true || (L.control && L.control.paused === true) || (L.paused == null && state.pendingPause === true);
  $("pausedTag").hidden = !paused;
  $("autoTag").hidden = L.auto_click !== true;
  $("btnPause").innerHTML = (paused ? "재개" : "멈춤") + " <kbd>P</kbd>";
  $("btnPause").dataset.paused = paused ? "1" : "";
  const s = L.safety || {};
  const sf = $("safety");
  if (!L.attempt || stepsDone(L)) { sf.textContent = ""; sf.className = "safety"; }
  else if (L.hand_down && typeof L.hand_down === "object") { sf.textContent = L.hand_down.kind === "payment" ? "결제 금액 확인 중 · 손을 내려 달라고 요청함" : "새 화면 확인 중 · 손을 내려 달라고 요청함"; sf.className = "safety"; }
  else if (s.press_allowed === true) { sf.textContent = "누르기 안내 가능 (손끝이 목표 위)"; sf.className = "safety on"; }
  else if (s.press_allowed === false) { sf.textContent = "누르기 안내 보류 · " + (SAFETY_LABEL[s.reason] || s.reason || "조건 미충족"); sf.className = "safety"; }
  else { sf.textContent = ""; sf.className = "safety"; }
}

// ---------------------------------------------------------------- 요약
const COUNT_ITEMS = [["presses", "누름"], ["wrong_presses", "다른 버튼 누름"], ["reverts", "되돌림"], ["hesitations", "망설임"], ["hand_lost", "손 놓침"], ["hand_down_requests", "손 내림 요청"], ["guides", "안내"]];
function renderCounts(L) {
  const c = L.counts || {};
  const html = L.attempt
    ? COUNT_ITEMS.map(([k, lab]) => `<div><dt>${lab}</dt><dd>${num(c[k]) ? c[k] : "—"}</dd></div>`).join("")
    : `<div><dt>시도를 시작하면 이번 시도의 누름·망설임·손 놓침 횟수가 여기에 쌓입니다</dt></div>`;
  if ($("counts").innerHTML !== html) $("counts").innerHTML = html;
  const p = L.last_press || (state.lastEvPress && { hit_id: state.lastEvPress.hit_id, result: state.lastEvPress.result, ms: state.lastEvPress.ms });
  if (p && L.attempt) {
    const reg = (L.kiosk && L.kiosk.regions || []).find((r) => r.id === p.hit_id);
    const name = p.label || (reg && reg.label) || p.hit_id || "버튼 밖";
    $("lastPress").textContent = `최근 누름 · ${name} · ${RESULT_LABEL[p.result] || p.result || ""}${num(p.ms) ? " · " + fmtSec(p.ms) : ""}`;
  } else $("lastPress").textContent = "";
}

// ---------------------------------------------------------------- 인식 상태
function renderStatus(L) {
  const s = L.status || {};
  const k = L.kiosk || {};
  const rows = [];
  const issues = []; // [level, text]
  const add = (label, value, level) => rows.push(`<div class="${level || ""}"><dt>${label}</dt><dd>${value}</dd></div>`);
  // 카메라
  if (s.camera === false) { add("카메라", "연결 안 됨", "bad"); issues.push(["bad", "카메라 영상이 들어오지 않습니다 — 휴대폰에서 카메라 화면을 다시 열어 주세요"]); }
  else add("카메라", s.camera ? (num(s.cam_w) ? `${s.cam_w}×${s.cam_h}` : "연결됨") : "—");
  // 마커·위치 맞춤
  const m = num(s.markers) ? s.markers : null;
  if (s.camera !== false) {
    if (s.aligned === false) {
      add("마커·맞춤", `${m ?? "—"}/4 · 맞춤 전`, "bad");
      issues.push(["bad", `위치 맞춤 전입니다 — 키오스크 옆 마커 4개가 모두 화면에 들어오게 휴대폰을 옮겨 주세요${m != null ? ` (지금 ${m}개)` : ""}`]);
    } else if (m != null && m < 4) {
      add("마커·맞춤", `${m}/4 · 맞춤 유지`, "warn");
      issues.push(["warn", `마커가 ${m}개만 보입니다 — 휴대폰을 조금 뒤로 옮겨 네 모서리가 모두 보이게 해 주세요`]);
    } else add("마커·맞춤", s.aligned ? `${m ?? "—"}/4 · 맞춤 됨` : `${m ?? "—"}/4`);
  } else add("마커·맞춤", "—");
  // 손 인식률
  if (num(s.hand_rate)) {
    const pct = Math.round(s.hand_rate * 100);
    const low = L.attempt && s.hand_rate < 0.6;
    add("손 인식률", pct + "%", low ? "warn" : "");
    if (low) issues.push(["warn", `손 인식이 낮습니다(${pct}%) — 조명을 밝게 하거나 손이 화면 안에 들어오는지 확인해 주세요`]);
  } else add("손 인식률", "—");
  // 지연
  if (num(s.frame_age_ms)) {
    const slow = s.frame_age_ms > 500;
    add("프레임 지연", s.frame_age_ms + "ms", slow ? "warn" : "");
    if (slow) issues.push(["warn", "영상이 늦게 도착합니다 — 휴대폰과 노트북의 와이파이 연결을 확인해 주세요"]);
  } else add("프레임 지연", "—");
  if (num(s.model_ms)) { const slow = s.model_ms > 120; add("모델 시간", s.model_ms + "ms", slow ? "warn" : ""); if (slow) issues.push(["warn", "손 인식 계산이 느립니다 — 노트북의 다른 프로그램을 닫아 주세요"]); }
  else add("모델 시간", "—");
  if (num(s.fps)) { const slow = s.fps < 6; add("초당 장수", s.fps + "장", slow ? "warn" : ""); if (slow) issues.push(["warn", "초당 받는 영상이 적습니다 — 휴대폰 화면이 꺼지지 않았는지 확인해 주세요"]); }
  else add("초당 장수", "—");
  if (L.kiosk === null || k.connected === false) { add("키오스크", "연결 안 됨", "bad"); issues.push(["bad", "키오스크 화면이 연결되지 않았습니다 — 노트북에서 키오스크 페이지를 다시 열어 주세요"]); }
  else add("키오스크", k.connected ? "연결됨" : "—");
  const ph = L.phone;
  if (ph && typeof ph === "object") {
    if (ph.connected === false) { add("휴대폰", "연결 안 됨", "bad"); issues.push(["bad", "휴대폰이 연결되지 않았습니다 — 휴대폰에서 안내 페이지(/phone)를 열어 주세요"]); }
    else if (ph.audio_unlocked === false) { add("휴대폰", "소리 잠김", "warn"); issues.push(["warn", "휴대폰 소리가 아직 꺼져 있습니다 — 휴대폰 화면을 한 번 눌러 주세요"]); }
    else add("휴대폰", ph.connected ? "연결 · 소리 켜짐" : "—");
  }
  const gcode = L.guide && L.guide.code;
  if (L.finger && L.finger.tracked === false && L.attempt && s.camera !== false && !stepsDone(L) && gcode !== "HAND_DOWN" && gcode !== "PAY_CHECK" && !L.hand_down) {
    issues.unshift(["warn", "손이 보이지 않습니다 — 손이 키오스크 화면 앞에 있는지 확인해 주세요. 손이 화면 밖이면 기다려도 됩니다"]);
  }
  const html = rows.join("");
  if ($("statusList").innerHTML !== html) $("statusList").innerHTML = html;
  const todo = $("statusTodo");
  if (!L.status) { todo.textContent = "인식 상태 정보가 없습니다"; todo.className = "status-todo none"; return; }
  const top = issues.find((x) => x[0] === "bad") || issues[0];
  if (top) { todo.textContent = top[1]; todo.className = "status-todo " + top[0]; }
  else { todo.textContent = "인식 상태 정상"; todo.className = "status-todo"; }
}

// ---------------------------------------------------------------- 시험 운영
async function loadGoals() {
  let j = null;
  try {
    j = await getJSON("/api/goals");
    state.goals = asList(j, "goals", "items").filter((g) => g && g.id);
  } catch (e) { if (!state.goals.length) { $("fGoal").innerHTML = '<option value="">목표 목록을 불러오지 못함</option>'; } return; }
  const def = state.goals.find((g) => g.default === true);
  const cur = (state.live && state.live.goal && state.live.goal.id) || (j && j.current) || store.get("goal", "") || (def && def.id);
  const opts = state.goals.map((g) => `<option value="${esc(g.id)}">${esc(g.label || g.id)}</option>`).join("");
  for (const id of ["fGoal", "fGoalLive"]) {
    const sel = $(id);
    sel.innerHTML = opts || '<option value="">목표 없음</option>';
    if (cur && state.goals.some((g) => g.id === cur)) sel.value = cur;
  }
}

function formValues() {
  const f = $("startForm");
  const v = (n) => (f.elements[n] && f.elements[n].value) || "";
  return {
    data_source: v("data_source"), goal_id: v("goal_id"),
    conditions: { layout: v("layout") || "A", guidance: v("guidance") || "on", blindfold: v("blindfold") || "unknown",
      lighting_note: v("lighting_note").trim(), participant_code: v("participant_code").trim().toUpperCase(), operator_note: v("operator_note").trim() },
  };
}
function restoreForm() {
  const saved = store.get("form", null);
  const f = $("startForm");
  if (saved) {
    for (const [n, val] of Object.entries(saved)) {
      const el = f.elements[n];
      if (!el || val == null) continue;
      if (el instanceof RadioNodeList) { for (const r of el) r.checked = r.value === val; }
      else el.value = val;
    }
  }
}
function saveForm() {
  const v = formValues();
  store.set("form", { data_source: v.data_source, layout: v.conditions.layout, guidance: v.conditions.guidance, blindfold: v.conditions.blindfold, participant_code: v.conditions.participant_code, lighting_note: v.conditions.lighting_note });
}

async function startAttempt(ev) {
  if (ev) ev.preventDefault();
  if (state.live && state.live.attempt) { setMsg("이미 진행 중인 시도가 있습니다.", true); return; }
  const v = formValues();
  if (/[가-힣]/.test(v.conditions.participant_code)) { setMsg("참가자 코드에는 이름을 적지 않습니다. P01처럼 적어 주세요.", true); $("fCode").focus(); return; }
  if (!v.goal_id) { setMsg("주문 목표를 골라 주세요.", true); $("fGoal").focus(); return; }
  $("btnStart").disabled = true;
  setMsg("시도를 시작하는 중");
  try {
    const j = await postJSON("/api/attempt/start", v);
    saveForm(); store.set("goal", v.goal_id);
    setMsg(`시도를 시작했습니다${j.attempt ? " · " + (j.attempt.id || j.attempt) : ""}`);
    await refreshLiveNow();
    loadAttempts();
  } catch (e) { setMsg("시작하지 못했습니다: " + e.message, true); }
  finally { $("btnStart").disabled = false; }
}
async function endAttempt(reason) {
  $("endConfirm").hidden = true;
  $("btnEnd").disabled = true;
  try {
    await postJSON("/api/attempt/end", { reason });
    setMsg(reason === "done" ? "주문 완료로 시도를 끝냈습니다." : "중단으로 기록하고 시도를 끝냈습니다.");
    await refreshLiveNow();
    loadAttempts();
  } catch (e) { setMsg("종료하지 못했습니다: " + e.message, true); }
  finally { $("btnEnd").disabled = false; }
}
function onEndClick() {
  const L = state.live;
  if (!L || !L.attempt) return;
  if (stepsDone(L) || (L.kiosk && L.kiosk.screen === "done")) endAttempt("done");
  else { $("endConfirm").hidden = false; $("btnEndAbort").focus(); }
}
async function refreshLiveNow() {
  try { const j = await getJSON("/api/live"); state.live = j; state.lastOk = Date.now(); onLive(j); setOnline(true); } catch (e) { /* 다음 조회에서 다시 */ }
}
async function control(action) {
  if (action === "stop" || action === "resume") state.pendingPause = action === "stop";
  try { await postJSON("/api/control", { action }); setMsg(action === "repeat" ? "마지막 안내를 다시 읽도록 요청했습니다." : action === "stop" ? "안내를 멈췄습니다." : "안내를 다시 시작했습니다."); }
  catch (e) { setMsg("요청하지 못했습니다: " + e.message, true); }
}
async function changeGoal(id) {
  if (!id) return;
  try { await postJSON("/api/goal", { goal_id: id }); store.set("goal", id); setMsg("주문 목표를 바꿨습니다."); }
  catch (e) { setMsg("목표를 바꾸지 못했습니다: " + e.message, true); }
}

function renderRun() {
  const L = state.live;
  const a = L && L.attempt;
  const off = state.online === false;
  $("startForm").hidden = !!a;
  $("running").hidden = !a;
  $("btnStart").disabled = off;
  $("btnEnd").disabled = off;
  $("btnRepeat").disabled = off;
  $("btnPause").disabled = off;
  if (!a) { $("runMeta").textContent = off ? "" : "대기 중"; $("endConfirm").hidden = true; return; }
  const c = a.conditions || {};
  $("runMeta").textContent = `${a.id || ""}`;
  const bits = [
    c.participant_code ? esc(c.participant_code) : "코드 없음",
    "배치 " + esc(c.layout || "—"),
    c.guidance === "off" ? "안내 없음" : c.guidance === "on" ? "안내 있음" : "안내 —",
    c.blindfold === "yes" ? "안대 예" : c.blindfold === "no" ? "안대 아니오" : "안대 모름",
  ];
  if (c.lighting_note) bits.push("조명 " + esc(c.lighting_note));
  if (a.data_source) bits.push(esc(SOURCE_LABEL[a.data_source] || a.data_source));
  const html = bits.join('<span class="sep">|</span>') + (c.operator_note ? `<span class="sep">|</span>${esc(c.operator_note)}` : "");
  if ($("runCond").innerHTML !== html) $("runCond").innerHTML = html;
  const done = stepsDone(L) || (L.kiosk && L.kiosk.screen === "done");
  $("btnEnd").textContent = done ? "시도 종료 (주문 완료)" : "시도 종료";
  $("endNote").textContent = done ? "주문 번호까지 끝났습니다" : `경과 ${fmtClock(a.ms) || "—"}`;
  const gl = $("fGoalLive");
  if (L.goal && L.goal.id && document.activeElement !== gl && gl.value !== L.goal.id && state.goals.some((g) => g.id === L.goal.id)) gl.value = L.goal.id;
}

// ---------------------------------------------------------------- 지난 시도·내려받기
async function loadAttempts() {
  let list;
  try { list = asList(await getJSON("/api/attempts", 4000), "attempts", "items"); }
  catch (e) { if (!$("pastBody").dataset.loaded) $("pastBody").innerHTML = '<tr><td colspan="3" class="empty">지난 시도 목록을 불러오지 못했습니다</td></tr>'; return; }
  $("pastBody").dataset.loaded = "1";
  if (!list.length) { $("pastBody").innerHTML = '<tr><td colspan="3" class="empty">아직 기록된 시도가 없습니다</td></tr>'; return; }
  list = list.slice().sort((x, y) => String(y.started || y.t || y.id || "").localeCompare(String(x.started || x.t || x.id || "")));
  $("pastBody").innerHTML = list.slice(0, 50).map((a) => {
    const id = a.id || a.attempt || "";
    const c = Object.assign({ layout: a.layout, guidance: a.guidance, blindfold: a.blindfold, participant_code: a.participant_code }, a.conditions || {});
    const cond = [c.layout ? "배치 " + c.layout : null, c.guidance === "off" ? "안내 없음" : c.guidance === "on" ? "안내 있음" : null, c.blindfold === "yes" ? "안대" : c.blindfold === "no" ? "안대 없음" : null].filter(Boolean).join(" · ");
    const running = a.running === true || (state.attemptId && id === state.attemptId);
    let result;
    if (running) result = "진행 중";
    else if (a.completed === true) result = `완료${num(a.order_no) ? " · 주문 " + a.order_no : ""}`;
    else if (a.end_reason) result = END_LABEL[a.end_reason] || a.end_reason;
    else if (a.completed === false) result = "미완료";
    else result = "종료 기록 없음";
    const sub = [num(a.total_ms) ? fmtSec(a.total_ms) : null, a.data_source ? (SOURCE_LABEL[a.data_source] || a.data_source) : null, a.folder === "examples" ? "예시 폴더" : null].filter(Boolean).join(" · ");
    const gl = typeof a.goal === "string" ? (state.goals.find((g) => g.id === a.goal) || {}).label || a.goal : a.goal && (a.goal.label || a.goal.id);
    const goal = gl || a.goal_label || "";
    const enc = encodeURIComponent(id);
    const uJ = a.url_jsonl || `${API}/api/attempts/${enc}.jsonl`, uC = a.url_csv || `${API}/api/attempts/${enc}.csv`;
    return `<tr class="${running ? "running" : ""}" data-id="${esc(id)}">
      <td>${esc(fmtTime(a.started || a.t))} · ${esc(c.participant_code || "코드 없음")}<span class="s">${esc(cond)}</span><span class="s">${esc(goal)}</span></td>
      <td>${esc(result)}<span class="s">${esc(sub)}</span><span class="s id">${esc(id)}</span></td>
      <td><div class="dl"><a href="${esc(uJ)}" download="${esc(id)}.jsonl" data-kind="jsonl">JSONL</a><a href="${esc(uC)}" download="${esc(id)}.csv" data-kind="csv">CSV</a><button type="button" data-json="${esc(id)}" data-url="${esc(uJ)}" title="JSONL을 배열 JSON 한 파일로 저장">JSON</button></div></td>
    </tr>`;
  }).join("");
}
async function downloadJsonArray(id, url) {
  try {
    const r = await fetch(url || `${API}/api/attempts/${encodeURIComponent(id)}.jsonl`, { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const lines = (await r.text()).split(/\r?\n/).filter((s) => s.trim());
    const arr = lines.map((s) => JSON.parse(s));
    const blob = new Blob([JSON.stringify(arr, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = id + ".json";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    setMsg(`${id}.json 저장 (기록 ${arr.length}줄)`);
  } catch (e) { setMsg("JSON으로 저장하지 못했습니다: " + e.message, true); }
}

// ---------------------------------------------------------------- 카메라 프레임
async function frameLoop() {
  let after = 0;
  for (;;) {
    if (state.viewMode === "schematic" || state.online === false) { await sleep(500); continue; }
    if (state.frameMissing) { await sleep(5000); state.frameMissing = false; }
    try {
      const ac = new AbortController();
      const t = setTimeout(() => ac.abort(), 4000);
      const r = await fetch(`${API}/api/frame/latest?after=${after}`, { signal: ac.signal, cache: "no-store" });
      clearTimeout(t);
      if (r.status === 204) { await sleep(60); continue; }
      if (r.status === 404 || r.status === 501) { state.frameMissing = true; state.frame = null; continue; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      const raw = r.headers.get("X-Info");
      let info = {};
      if (raw) { try { info = JSON.parse(decodeURIComponent(raw)); } catch (e) { info = {}; } }
      const blob = await r.blob();
      const bmp = await createImageBitmap(blob);
      if (state.frame && state.frame.bmp && state.frame.bmp.close) state.frame.bmp.close();
      if (!num(info.w)) info.w = bmp.width;
      if (!num(info.h)) info.h = bmp.height;
      state.frame = { bmp, info, at: Date.now(), Hi: validH(info.H) ? inv(info.H) : null };
      if (num(info.seq)) after = info.seq;
    } catch (e) { await sleep(800); }
  }
}
function validH(H) { return Array.isArray(H) && H.length === 3 && H.every((r) => Array.isArray(r) && r.length === 3 && r.every(num)); }
function apply(H, x, y) { const w = H[2][0] * x + H[2][1] * y + H[2][2]; return [(H[0][0] * x + H[0][1] * y + H[0][2]) / w, (H[1][0] * x + H[1][1] * y + H[1][2]) / w]; }
function inv(m) {
  const [a, b, c] = m[0], [d, e, f] = m[1], [g, h, i] = m[2];
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g, det = a * A + b * B + c * C;
  return [[A / det, -(b * i - c * h) / det, (b * f - c * e) / det], [B / det, (a * i - c * g) / det, -(a * f - c * d) / det], [C / det, -(a * h - b * g) / det, (a * e - b * d) / det]];
}

// ---------------------------------------------------------------- 그림: 키오스크 부분 확대 / 도식
const cv = $("cv"), ctx = cv.getContext("2d");
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let COLORS = null;
function kioskAspect(L) {
  const k = L && L.kiosk || {};
  if (Array.isArray(k.size) && num(k.size[0]) && num(k.size[1])) return k.size[0] / k.size[1];
  if (num(k.w) && num(k.h)) return k.w / k.h;
  if (num(k.aspect)) return k.aspect;
  return 1080 / 1920; // 모의 키오스크 논리 해상도(04-practice-kiosk/realistic/kiosk.css)
}
function draw() {
  requestAnimationFrame(draw);
  if (!COLORS) COLORS = { accent: css("--accent"), text: css("--text"), muted: css("--muted"), line: css("--line-strong"), stage: css("--stage-bg"), bad: css("--bad") };
  const st = $("stage");
  const dpr = window.devicePixelRatio || 1;
  const W = st.clientWidth, H = st.clientHeight;
  if (!W || !H) return;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const L = state.live;
  const fr = state.frame;
  const frameFresh = fr && Date.now() - fr.at < 3000;
  const mode = state.viewMode;
  let toScreen = null; // 키오스크 정규 좌표 → 화면 px
  let note = "";
  let camera = false;
  if (mode !== "schematic" && frameFresh) {
    const info = fr.info;
    let crop = { x: 0, y: 0, w: info.w, h: info.h };
    if (mode !== "full" && fr.Hi) {
      const q = [[0, 0], [1, 0], [1, 1], [0, 1]].map(([x, y]) => apply(fr.Hi, x, y));
      const xs = q.map((p) => p[0]), ys = q.map((p) => p[1]);
      let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      const m = 0.06 * Math.max(x1 - x0, y1 - y0);
      x0 = Math.max(0, x0 - m); y0 = Math.max(0, y0 - m); x1 = Math.min(info.w, x1 + m); y1 = Math.min(info.h, y1 + m);
      if (x1 - x0 > 32 && y1 - y0 > 32) crop = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
    }
    const s = Math.min(W / crop.w, H / crop.h);
    const ox = (W - crop.w * s) / 2, oy = (H - crop.h * s) / 2;
    ctx.fillStyle = "#2a2b2e"; ctx.fillRect(0, 0, W, H);
    ctx.drawImage(fr.bmp, crop.x, crop.y, crop.w, crop.h, ox, oy, crop.w * s, crop.h * s);
    camera = true;
    if (fr.Hi) {
      const Hi = fr.Hi;
      toScreen = (x, y) => { const p = apply(Hi, x, y); return [(p[0] - crop.x) * s + ox, (p[1] - crop.y) * s + oy]; };
      // 키오스크 테두리
      ctx.strokeStyle = "rgba(255,255,255,.7)"; ctx.lineWidth = 1.5; ctx.setLineDash([6, 4]);
      poly([[0, 0], [1, 0], [1, 1], [0, 1]].map(([x, y]) => toScreen(x, y))); ctx.stroke(); ctx.setLineDash([]);
    } else note = "위치 맞춤 전이라 영상 위에 손끝·목표를 겹치지 못합니다";
    if (mode === "full" && Array.isArray(info.markers)) {
      ctx.strokeStyle = "#5fae80"; ctx.lineWidth = 2;
      for (const mk of info.markers) { if (Array.isArray(mk.corners)) { poly(mk.corners.map(([x, y]) => [(x - crop.x) * s + ox, (y - crop.y) * s + oy])); ctx.stroke(); } }
    }
    if (info.synthetic) note = (note ? note + " · " : "") + "예시 영상(합성 그림)";
  } else {
    // 도식: 키오스크 정규 좌표로 버튼 윤곽만
    const asp = kioskAspect(L);
    const pad = 14;
    let w = W - pad * 2, h = w / asp;
    if (h > H - pad * 2) { h = H - pad * 2; w = h * asp; }
    const ox = (W - w) / 2, oy = (H - h) / 2;
    toScreen = (x, y) => [ox + x * w, oy + y * h];
    ctx.fillStyle = "#ffffff"; ctx.strokeStyle = COLORS.line; ctx.lineWidth = 1;
    ctx.fillRect(ox, oy, w, h); ctx.strokeRect(ox + 0.5, oy + 0.5, w - 1, h - 1);
    const regs = (L && L.kiosk && Array.isArray(L.kiosk.regions)) ? L.kiosk.regions : [];
    ctx.font = `${Math.max(10, Math.min(13, w / 26))}px ${getComputedStyle(document.body).fontFamily}`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (const r of regs) {
      if (!Array.isArray(r.bbox)) continue;
      const [a, b] = toScreen(r.bbox[0], r.bbox[1]), [c, d] = toScreen(r.bbox[2], r.bbox[3]);
      ctx.strokeStyle = r.enabled === false ? "#dcdcd8" : "#b9bbb8";
      ctx.strokeRect(a + 0.5, b + 0.5, c - a - 1, d - b - 1);
      ctx.fillStyle = r.enabled === false ? "#b9bbb8" : COLORS.muted;
      const lab = String(r.label || r.id || "");
      ctx.fillText(lab.length > 10 ? lab.slice(0, 9) + "…" : lab, (a + c) / 2, (b + d) / 2, c - a - 4);
    }
    ctx.textAlign = "start"; ctx.textBaseline = "alphabetic";
    if (mode === "schematic") note = "도식 보기 · 키오스크 정규 좌표";
    else if (state.frameMissing) note = "서버가 카메라 영상을 주지 않아 도식으로 표시합니다";
    else if (L && L.status && L.status.camera === false) note = "카메라 영상 없음 · 도식으로 표시합니다";
    else if (!frameFresh) note = "카메라 영상을 기다리는 중 · 도식으로 표시합니다";
    if (!regs.length && L) note = (note ? note + " · " : "") + "버튼 영역 정보 없음";
  }
  if (L && toScreen) drawOverlay(L, toScreen, camera);
  const sn = $("stageNote");
  if (sn.textContent !== note) sn.textContent = note;
}
function poly(pts) { ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); }
function drawOverlay(L, P, camera) {
  const t = L.target;
  if (t && Array.isArray(t.bbox)) {
    const b = t.bbox;
    const pts = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]].map(([x, y]) => P(x, y));
    ctx.fillStyle = camera ? "rgba(47, 88, 200, .28)" : "rgba(47, 88, 200, .14)";
    ctx.strokeStyle = COLORS.accent; ctx.lineWidth = 2.5;
    poly(pts); ctx.fill(); ctx.stroke();
    const top = pts.reduce((m, p) => (p[1] < m[1] ? p : m), pts[0]);
    const lab = "목표 · " + (t.label || t.id || "");
    ctx.font = `12px ${getComputedStyle(document.body).fontFamily}`;
    const tw = ctx.measureText(lab).width + 10;
    const lx = Math.min(Math.max(2, Math.min(...pts.map((p) => p[0]))), cv.width / (window.devicePixelRatio || 1) - tw - 2);
    const ly = Math.max(2, top[1] - 20);
    ctx.fillStyle = COLORS.accent; ctx.fillRect(lx, ly, tw, 17);
    ctx.fillStyle = "#fff"; ctx.fillText(lab, lx + 5, ly + 12.5);
  }
  const f = L.finger;
  if (!f || !num(f.x) || !num(f.y)) return;
  const [x, y] = P(f.x, f.y);
  const fresh = f.tracked === true && !(num(f.age_ms) && f.age_ms > 800);
  if (!fresh) {
    ctx.setLineDash([4, 3]); ctx.strokeStyle = camera ? "rgba(255,255,255,.85)" : COLORS.muted; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
    ctx.font = `12px ${getComputedStyle(document.body).fontFamily}`;
    const lab = "마지막으로 본 손끝";
    const tw = ctx.measureText(lab).width + 10;
    ctx.fillStyle = "rgba(255,255,255,.9)"; ctx.fillRect(x + 14, y - 9, tw, 18);
    ctx.fillStyle = COLORS.muted; ctx.fillText(lab, x + 19, y + 4);
    return;
  }
  // 안내 방향 화살표
  const g = L.guide;
  let dir = g && Array.isArray(g.direction) && g.direction.length === 2 && g.direction.every(num) ? g.direction : null;
  if (!dir && g && g.code) dir = DIR_OF[String(g.code).replace("_SMALL", "")] || null;
  if (dir && (dir[0] || dir[1])) {
    const n = Math.hypot(dir[0], dir[1]);
    const small = g && String(g.code || "").endsWith("_SMALL");
    const len = small ? 30 : 48;
    const ux = dir[0] / n, uy = dir[1] / n;
    const sx = x + ux * 14, sy = y + uy * 14, ex = x + ux * (14 + len), ey = y + uy * (14 + len);
    ctx.strokeStyle = COLORS.accent; ctx.fillStyle = COLORS.accent; ctx.lineWidth = 3.5; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex - ux * 6, ey - uy * 6); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(ex - ux * 12 - uy * 7, ey - uy * 12 + ux * 7); ctx.lineTo(ex - ux * 12 + uy * 7, ey - uy * 12 - ux * 7); ctx.closePath(); ctx.fill();
    ctx.lineCap = "butt";
  }
  ctx.fillStyle = "#ffffff"; ctx.strokeStyle = COLORS.text; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.fillStyle = COLORS.text; ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill();
}

// ---------------------------------------------------------------- 조작 연결
function setViewMode(m) {
  state.viewMode = m; store.set("view", m);
  for (const b of $("viewSeg").querySelectorAll("button")) b.setAttribute("aria-pressed", b.dataset.mode === m ? "true" : "false");
}
function bind() {
  $("startForm").addEventListener("submit", startAttempt);
  $("btnEnd").onclick = onEndClick;
  $("btnEndAbort").onclick = () => endAttempt("aborted");
  $("btnEndCancel").onclick = () => { $("endConfirm").hidden = true; $("btnEnd").focus(); };
  $("btnRepeat").onclick = () => control("repeat");
  $("btnPause").onclick = () => control($("btnPause").dataset.paused ? "resume" : "stop");
  $("btnReload").onclick = loadAttempts;
  $("fGoal").onchange = (e) => { if (!(state.live && state.live.attempt)) changeGoal(e.target.value); };
  $("fGoalLive").onchange = (e) => changeGoal(e.target.value);
  $("viewSeg").addEventListener("click", (e) => { const b = e.target.closest("button[data-mode]"); if (b) setViewMode(b.dataset.mode); });
  $("pastBody").addEventListener("click", (e) => { const b = e.target.closest("button[data-json]"); if (b) downloadJsonArray(b.dataset.json, b.dataset.url); });
  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName);
    if (e.key === "Escape" && !$("endConfirm").hidden) { $("endConfirm").hidden = true; $("btnEnd").focus(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { if (!(state.live && state.live.attempt)) { e.preventDefault(); startAttempt(); } return; }
    if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "r" || e.key === "R") { e.preventDefault(); if (!$("btnRepeat").disabled) control("repeat"); }
    else if (e.key === "p" || e.key === "P") { e.preventDefault(); if (!$("btnPause").disabled) $("btnPause").click(); }
  });
}

function init() {
  restoreForm();
  setViewMode(new URLSearchParams(location.search).get("view") || store.get("view", "auto"));
  bind();
  loadGoals();
  loadAttempts();
  setInterval(() => { if (state.online) loadAttempts(); }, 15000);
  liveLoop(); eventsLoop(); frameLoop();
  requestAnimationFrame(draw);
  // 모의 서버면 기록 구분 기본값을 예시 데이터로
  const once = setInterval(() => {
    const L = state.live;
    if (!L) return;
    clearInterval(once);
    if ((L.data_source === "synthetic" || L.mock === true) && !store.get("form", null)) $("fSource").value = "synthetic";
  }, 200);
}
init();
