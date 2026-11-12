// OpenKey 모의 키오스크 v2 — 메뉴·옵션·배치 데이터.
// 화면 좌표의 정답은 렌더링된 DOM에서 측정한다(kiosk.js의 currentMap). 이 파일은 내용 정의다.
// 채점·정답 목표 모드·데이터 생성 전용이며, AI 안내 런타임 입력으로 쓰지 않는다.
window.OPENKEY_LAYOUTS = (function () {
  const CATEGORIES = [
    { id: "all", name: "전체 메뉴" },
    { id: "coffee", name: "커피" },
    { id: "noncoffee", name: "논커피" },
    { id: "tea", name: "티" },
    { id: "dessert", name: "디저트" },
  ];

  // art: iced | hot | tea | croffle | cake | macaron, color: 음료색
  // temps: 선택 가능한 온도. 하나뿐이면 기본 선택된다.
  const MENU = [
    { id: "americano", cat: "coffee", name: "아메리카노", price: 2000, desc: "에스프레소 + 물", art: "iced", color: "#3b2316", temps: ["ICE", "HOT"], shot: true, size: true, badge: "BEST" },
    { id: "latte", cat: "coffee", name: "카페라떼", price: 3200, desc: "에스프레소 + 우유", art: "iced", color: "#b07a52", temps: ["ICE", "HOT"], shot: true, size: true },
    { id: "vanilla", cat: "coffee", name: "바닐라라떼", price: 3700, desc: "바닐라 시럽 + 에스프레소 + 우유", art: "iced", color: "#c49a6c", temps: ["ICE", "HOT"], shot: true, size: true },
    { id: "caramel", cat: "coffee", name: "카라멜마키아토", price: 3900, desc: "카라멜 소스 + 에스프레소 + 우유", art: "iced", color: "#a8672f", temps: ["ICE", "HOT"], shot: true, size: true },
    { id: "cappuccino", cat: "coffee", name: "카푸치노", price: 3200, desc: "에스프레소 + 우유 거품", art: "hot", color: "#9c6b45", temps: ["HOT"], shot: true, size: true },
    { id: "coldbrew", cat: "coffee", name: "콜드브루", price: 3500, desc: "찬물로 오래 추출한 커피", art: "iced", color: "#2a160c", temps: ["ICE"], shot: false, size: true },
    { id: "choco", cat: "noncoffee", name: "초코라떼", price: 3500, desc: "초콜릿 + 우유", art: "iced", color: "#6b3b22", temps: ["ICE", "HOT"], shot: false, size: true },
    { id: "greentea", cat: "noncoffee", name: "녹차라떼", price: 3500, desc: "말차 + 우유", art: "iced", color: "#8db35a", temps: ["ICE", "HOT"], shot: false, size: true },
    { id: "strawberry", cat: "noncoffee", name: "딸기라떼", price: 3900, desc: "딸기청 + 우유", art: "iced", color: "#e98aa0", temps: ["ICE"], shot: false, size: true, badge: "NEW" },
    { id: "yuja", cat: "tea", name: "유자차", price: 3300, desc: "고흥 유자청", art: "tea", color: "#f2b632", temps: ["ICE", "HOT"], shot: false, size: false },
    { id: "chamomile", cat: "tea", name: "캐모마일", price: 2800, desc: "허브티", art: "tea", color: "#e8cf7a", temps: ["ICE", "HOT"], shot: false, size: false },
    { id: "icetea", cat: "tea", name: "복숭아아이스티", price: 3000, desc: "복숭아 아이스티", art: "iced", color: "#e0894a", temps: ["ICE"], shot: false, size: true },
    { id: "croffle", cat: "dessert", name: "크로플", price: 3500, desc: "버터 크루아상 와플", art: "croffle", color: "#d9a35b", temps: [], shot: false, size: false },
    { id: "cheesecake", cat: "dessert", name: "치즈케이크", price: 4500, desc: "뉴욕 치즈케이크", art: "cake", color: "#f3dfa2", temps: [], shot: false, size: false },
    { id: "macaron", cat: "dessert", name: "마카롱", price: 2300, desc: "바닐라 마카롱", art: "macaron", color: "#f2a7c3", temps: [], shot: false, size: false },
  ];

  const OPTION_PRICES = { sizeL: 500, shot: 500, shotMax: 2 };

  // 배치 A: 좌측 카테고리 열·3열×3행·가격 숫자만. 배치 B: 상단 탭·3열×3행·가격 "원" 표기·하단 큰 결제 버튼.
  const LAYOUTS = {
    A: { id: "A", name: "좌측 카테고리", perPage: 9, priceSuffix: "" },
    B: { id: "B", name: "상단 탭", perPage: 9, priceSuffix: "원" },
  };

  return { CATEGORIES, MENU, OPTION_PRICES, LAYOUTS, LOGICAL: { width: 1080, height: 1920 } };
})();
