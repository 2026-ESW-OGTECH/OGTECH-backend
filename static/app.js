const appState = {
  scenarios: [],
  drawers: [],
  inventory: [],
  led: null,
  kit: null,
  events: [],
  currentScenarioForRisk: null,
  currentSession: null,
  currentInventoryResult: null,
  timerId: null,
  timerLeft: 0,
  metronomeId: null,
  audioCtx: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const DEMO_STATE = {
  disclaimer: "본 화면은 정적 데모 모드입니다. 의료기기가 아니며 진단/치료/복약 판단을 수행하지 않습니다.",
  scenarios: [
    {
      id: "bleeding",
      title: "출혈",
      subtitle: "피가 나는 상처의 직접 압박과 119 판단 보조",
      drawers: ["ppe", "gauze"],
      risk_questions: [
        { id: "massive_bleeding", text: "피가 많이 나거나 멈추지 않음" },
        { id: "unconscious", text: "의식이 없거나 반응이 약함" },
      ],
    },
    {
      id: "burn",
      title: "화상",
      subtitle: "냉각과 보호 물품 위치 안내",
      drawers: ["burn_pad"],
      risk_questions: [
        { id: "large_burn", text: "넓은 부위 또는 얼굴/기도 화상 의심" },
      ],
    },
    {
      id: "cpr",
      title: "CPR",
      subtitle: "119 연결과 110 BPM 메트로놈 보조",
      drawers: [],
      risk_questions: [
        { id: "unconscious", text: "의식 없음" },
        { id: "abnormal_breathing", text: "정상 호흡 아님" },
      ],
    },
  ],
  drawers: [
    { id: "ppe", label: "3단", item: "장갑/마스크", color: "#0f766e" },
    { id: "gauze", label: "1단", item: "거즈/붕대", color: "#dc2626" },
    { id: "burn_pad", label: "2단", item: "화상 패드", color: "#2563eb" },
  ],
  inventory: [
    {
      id: "fucidin",
      name: "후시딘",
      aliases: ["후시딘", "연고"],
      layer: 2,
      cell: "2-1",
      quantity: 1,
      expiry_date: "2026-12-31",
      available: true,
      expired: false,
      is_medicine: true,
      auto_open_allowed: true,
    },
    {
      id: "band_aid",
      name: "밴드",
      aliases: ["밴드", "반창고"],
      layer: 3,
      cell: "3-1",
      quantity: 8,
      expiry_date: "2027-03-31",
      available: true,
      expired: false,
      is_medicine: false,
      auto_open_allowed: true,
    },
    {
      id: "danger_painkiller",
      name: "위험 의약품 보관칸",
      aliases: ["마약성 진통제", "주사기", "위험 의약품"],
      layer: 3,
      cell: "3-3",
      quantity: 1,
      expiry_date: "2026-10-31",
      available: true,
      expired: false,
      is_medicine: true,
      auto_open_allowed: false,
    },
  ],
  led: { state: { active_drawers: [], display_mode: "idle" } },
  kit: {
    mode: "static-demo",
    state: {
      open_layer: null,
      active_cell: null,
      stock: {},
      battery: { voltage: 7.8, percent: 82, charging: false, low: false },
    },
  },
  events: [{ at: "정적 데모", event: "static_demo_ready", payload: { mode: "browser_only" } }],
  sessions: {},
  nextSessionId: 1,
};

function cloneDemo(value) {
  return JSON.parse(JSON.stringify(value));
}

function demoEvent(event, payload = {}) {
  DEMO_STATE.events.unshift({ at: new Date().toLocaleTimeString("ko-KR"), event, payload });
  DEMO_STATE.events = DEMO_STATE.events.slice(0, 20);
}

function parseJsonBody(options) {
  if (!options?.body) return {};
  try {
    return JSON.parse(options.body);
  } catch {
    return {};
  }
}

function findInventoryItem(text) {
  const query = String(text || "").toLowerCase();
  return DEMO_STATE.inventory.find((item) => {
    const terms = [item.name, ...(item.aliases || [])].map((term) => String(term).toLowerCase());
    return terms.some((term) => query.includes(term));
  });
}

function demoInventoryQuery(text) {
  const item = findInventoryItem(text);
  if (!item || !item.available) {
    return { found: false, openable: false, item: null, message: "등록된 재고에서 찾지 못했습니다." };
  }
  const restricted = !item.auto_open_allowed;
  return {
    found: true,
    openable: item.auto_open_allowed,
    item: cloneDemo(item),
    message: restricted
      ? "네, 있습니다. 안전 보관칸 물품이라 위치 존재 여부만 안내하고 자동 개방은 하지 않습니다."
      : "네, 있습니다. 열어 드릴까요?",
  };
}

function demoClassify(text) {
  const normalized = String(text || "");
  const scenarioId = normalized.includes("화상") ? "burn" : normalized.includes("심폐") || normalized.includes("의식") ? "cpr" : "bleeding";
  const scenario = DEMO_STATE.scenarios.find((item) => item.id === scenarioId);
  const riskFlags = [];
  if (normalized.includes("의식")) riskFlags.push("unconscious");
  if (normalized.includes("호흡")) riskFlags.push("abnormal_breathing");
  if (normalized.includes("피") || normalized.includes("출혈")) riskFlags.push("massive_bleeding");
  return {
    scenario_id: scenario.id,
    scenario_title: scenario.title,
    confidence: "medium",
    risk_flags: riskFlags,
    classifier: "static-demo",
  };
}

function makeDemoSession(scenarioId, riskFlags = []) {
  const scenario = DEMO_STATE.scenarios.find((item) => item.id === scenarioId) || DEMO_STATE.scenarios[0];
  const forceEmergency = riskFlags.some((flag) => ["unconscious", "abnormal_breathing", "massive_bleeding"].includes(flag));
  const steps = scenario.id === "cpr"
    ? [
      { title: "119 연결", body: "주변 사람에게 119 신고와 AED 요청을 맡기세요.", visual: "call119" },
      { title: "가슴압박 템포", body: "성인 기준 110 BPM 템포 보조음만 제공합니다.", visual: "cpr", metronome: true },
    ]
    : [
      { title: "위험 신호 확인", body: "심한 출혈, 의식 저하, 호흡 이상이 있으면 119 도움 요청 화면으로 이동하세요.", visual: "checklist" },
      { title: "물품 위치 안내", body: "필요 물품이 있는 칸의 LED와 층 상태를 표시합니다. 약 복용법이나 처치 판단은 제공하지 않습니다.", visual: scenario.id === "burn" ? "cool_water" : "press", timer_sec: scenario.id === "burn" ? 120 : null },
    ];
  const session = {
    id: `demo-${DEMO_STATE.nextSessionId++}`,
    scenario,
    step_index: 0,
    step_count: steps.length,
    step: steps[0],
    steps,
    drawers: scenario.drawers.map((drawerId) => DEMO_STATE.drawers.find((drawer) => drawer.id === drawerId)).filter(Boolean),
    risk_labels: riskFlags,
    force_emergency: forceEmergency,
    completed: false,
  };
  DEMO_STATE.sessions[session.id] = session;
  DEMO_STATE.led.state.active_drawers = [...scenario.drawers];
  DEMO_STATE.led.state.display_mode = forceEmergency ? "emergency" : "guided";
  demoEvent("demo_session_start", { scenario_id: scenario.id, risk_flags: riskFlags });
  return cloneDemo(session);
}

function advanceDemoSession(sessionId, action) {
  const session = DEMO_STATE.sessions[sessionId];
  if (!session) return makeDemoSession("bleeding");
  if (action === "worse" || action === "cant") session.force_emergency = true;
  if (action === "done" && session.step_index < session.steps.length - 1) {
    session.step_index += 1;
    session.step = session.steps[session.step_index];
  } else if (action === "done") {
    session.completed = true;
  }
  demoEvent("demo_session_action", { session_id: sessionId, action });
  return cloneDemo(session);
}

async function localDemoFetch(url, options = {}) {
  const path = new URL(url, window.location.href).pathname;
  const body = parseJsonBody(options);
  switch (path) {
    case "/api/state":
      return cloneDemo({
        disclaimer: DEMO_STATE.disclaimer,
        scenarios: DEMO_STATE.scenarios,
        drawers: DEMO_STATE.drawers,
        inventory: DEMO_STATE.inventory,
        led: DEMO_STATE.led,
        kit: DEMO_STATE.kit,
        events: DEMO_STATE.events,
      });
    case "/api/logs":
      return { events: cloneDemo(DEMO_STATE.events) };
    case "/api/classify":
      return demoClassify(body.text);
    case "/api/start": {
      const session = makeDemoSession(body.scenario_id, body.risk_flags || []);
      return { session, led: cloneDemo(DEMO_STATE.led) };
    }
    case "/api/cpr/start": {
      const session = makeDemoSession("cpr", ["unconscious", "abnormal_breathing"]);
      return { session, led: cloneDemo(DEMO_STATE.led) };
    }
    case "/api/inventory/query": {
      const result = demoInventoryQuery(body.text);
      demoEvent("demo_inventory_query", { text: body.text, found: result.found });
      return { result, inventory: cloneDemo(DEMO_STATE.inventory), kit: cloneDemo(DEMO_STATE.kit) };
    }
    case "/api/inventory/open": {
      const item = DEMO_STATE.inventory.find((entry) => entry.id === body.item_id);
      if (item?.available && item.auto_open_allowed) {
        DEMO_STATE.kit.state.open_layer = item.layer;
        DEMO_STATE.kit.state.active_cell = item.cell;
        demoEvent("demo_inventory_open", { item_id: item.id, layer: item.layer, cell: item.cell });
      }
      return { item: cloneDemo(item), kit: cloneDemo(DEMO_STATE.kit), inventory: cloneDemo(DEMO_STATE.inventory) };
    }
    case "/api/inventory/items": {
      const item = {
        id: `demo_item_${Date.now()}`,
        name: body.name || "개인 물품",
        aliases: body.aliases || [],
        layer: Number(body.layer || 3),
        cell: body.cell || "3-2",
        quantity: Number(body.quantity || 1),
        expiry_date: body.expiry_date || "2026-12-31",
        available: Number(body.quantity || 1) > 0,
        expired: false,
        is_medicine: Boolean(body.is_medicine),
        auto_open_allowed: Boolean(body.auto_open_allowed),
      };
      DEMO_STATE.inventory.push(item);
      demoEvent("demo_inventory_add", { item_id: item.id });
      return { item: cloneDemo(item), inventory: cloneDemo(DEMO_STATE.inventory), kit: cloneDemo(DEMO_STATE.kit) };
    }
    case "/api/sensor/co": {
      const danger = Number(body.ppm || 0) >= 50;
      if (danger) {
        const session = makeDemoSession("cpr", ["co_exposure"]);
        return { danger, session, led: cloneDemo(DEMO_STATE.led) };
      }
      demoEvent("demo_co_sensor", { ppm: Number(body.ppm || 0), danger });
      return { danger, ppm: Number(body.ppm || 0), led: cloneDemo(DEMO_STATE.led) };
    }
    case "/api/vision/upload":
      return {
        analysis: { summary: "정적 데모 모드에서는 사진을 실제 분석하지 않습니다.", flags: ["static_demo"] },
        suggested_scenario_id: null,
        suggested_title: null,
        image_url: "",
      };
    case "/api/emergency":
      return {
        emergency: {
          title: "119 도움 요청",
          tel_uri: "tel:119",
          summary: "정적 데모 모드: 위치, 인원, 증상, 의식/호흡 상태를 직접 확인해 신고하세요.",
          script: ["현재 위치를 말합니다.", "환자 상태를 짧게 말합니다.", "상담원의 지시를 따릅니다."],
        },
        led: cloneDemo(DEMO_STATE.led),
      };
    default:
      if (path.includes("/api/session/") && path.endsWith("/action")) {
        const sessionId = path.split("/")[3];
        const session = advanceDemoSession(sessionId, body.action);
        return { session, led: cloneDemo(DEMO_STATE.led) };
      }
      throw new Error("정적 데모 모드에서 지원하지 않는 요청입니다.");
  }
}

async function fetchJson(url, options = {}) {
  return localDemoFetch(url, options);
}

async function loadState() {
  const state = await fetchJson("/api/state");
  appState.scenarios = state.scenarios;
  appState.drawers = state.drawers;
  appState.inventory = state.inventory || [];
  appState.led = state.led;
  appState.kit = state.kit;
  appState.events = state.events;
  $("#disclaimer").textContent = state.disclaimer;
  renderScenarios();
  renderDrawers();
  renderKitStatus();
  renderInventoryList();
  renderEvents();
}

function renderScenarios() {
  const grid = $("#scenarioGrid");
  grid.innerHTML = "";
  appState.scenarios.forEach((scenario) => {
    const button = document.createElement("button");
    button.className = "scenario-card";
    button.innerHTML = `
      <strong>${scenario.title}</strong>
      <span>${scenario.subtitle}</span>
      <div class="drawer-chips">
        ${scenario.drawers.length ? scenario.drawers.map(drawerId => `<span class="chip">${drawerLabel(drawerId)}</span>`).join("") : `<span class="chip">물품 없음</span>`}
      </div>
    `;
    button.addEventListener("click", () => openRiskDialog(scenario.id));
    grid.appendChild(button);
  });
}

function renderDrawers() {
  const active = new Set(appState.led?.state?.active_drawers || []);
  const emergency = appState.led?.state?.display_mode === "emergency";
  $("#drawerList").innerHTML = appState.drawers.map((drawer) => `
    <div class="drawer-row ${active.has(drawer.id) || emergency ? "active" : ""}">
      <span class="led-dot" style="${active.has(drawer.id) ? `background:${drawer.color}` : ""}"></span>
      <strong>${drawer.label}</strong>
      <span>${drawer.item}</span>
    </div>
  `).join("");
}

function renderKitStatus() {
  const state = appState.kit?.state || {};
  const battery = state.battery || {};
  $("#kitStatus").innerHTML = `
    <div class="status-row">
      <span>열린 층</span>
      <strong>${state.open_layer ? `${state.open_layer}단` : "없음"}</strong>
    </div>
    <div class="status-row">
      <span>LED 칸</span>
      <strong>${state.active_cell || "꺼짐"}</strong>
    </div>
    <div class="status-row ${battery.low ? "warn" : ""}">
      <span>배터리</span>
      <strong>${battery.percent ?? "-"}% ${battery.charging ? "충전중" : ""}</strong>
    </div>
  `;
}

function renderInventoryList() {
  $("#inventoryList").innerHTML = (appState.inventory || []).map((item) => `
    <div class="inventory-row ${item.available ? "" : "empty"} ${item.expired ? "expired" : ""}">
      <div>
        <strong>${item.name}</strong>
        <span>${item.layer}단 ${item.cell}칸 · ${item.quantity}개</span>
      </div>
      <span>${item.available ? "있음" : "없음"}${item.expired ? " · 교체" : ""}</span>
    </div>
  `).join("");
}

function renderEvents() {
  $("#eventLog").innerHTML = (appState.events || []).slice(0, 10).map((event) => `
    <div class="event-row">
      <strong>${event.event}</strong>
      ${event.at}
    </div>
  `).join("");
}

function drawerLabel(drawerId) {
  const drawer = appState.drawers.find((item) => item.id === drawerId);
  return drawer ? `${drawer.label} ${drawer.item}` : drawerId;
}

function openRiskDialog(scenarioId) {
  const scenario = appState.scenarios.find((item) => item.id === scenarioId);
  appState.currentScenarioForRisk = scenario;
  $("#riskTitle").textContent = `${scenario.title} 위험 신호 확인`;
  $("#riskQuestions").innerHTML = scenario.risk_questions.map((question) => `
    <label>
      <input type="checkbox" value="${question.id}" />
      <span>${question.text}</span>
    </label>
  `).join("");
  $("#riskDialog").showModal();
}

async function startScenario(scenarioId, source = "touch", riskFlags = []) {
  stopTimer();
  stopMetronome();
  const payload = await fetchJson("/api/start", {
    method: "POST",
    body: JSON.stringify({ scenario_id: scenarioId, source, risk_flags: riskFlags }),
  });
  appState.currentSession = payload.session;
  appState.led = payload.led;
  renderDrawers();
  renderSession(payload.session);
  await refreshLogs();
}

function renderSession(session) {
  const panel = $("#sessionPanel");
  panel.classList.remove("hidden");
  const step = session.step;
  const progress = Math.round(((session.step_index + 1) / session.step_count) * 100);
  const drawerChips = session.drawers.map((drawer) => `<span class="chip">${drawer.label} ${drawer.item}</span>`).join("");
  const risk = session.risk_labels.length ? `<div class="notice">위험 신호: ${session.risk_labels.join(", ")}</div>` : "";
  const force = session.force_emergency ? `<button class="danger wide" id="sessionEmergencyBtn">119 도움 요청 화면 열기</button>` : "";

  panel.innerHTML = `
    <div class="session-header">
      <div>
        <h1>${session.scenario.title}</h1>
        <p>${session.scenario.subtitle}</p>
      </div>
      <span class="chip">${session.step_index + 1} / ${session.step_count}</span>
    </div>
    <div class="progress"><span style="width:${progress}%"></span></div>
    <div class="step-layout">
      <div class="visual-card">${visualSvg(step.visual || "generic", step.title)}</div>
      <div class="step-copy">
        ${risk}
        <h2>${step.title}</h2>
        <p>${step.body}</p>
        <div class="drawer-chips">${drawerChips || `<span class="chip">지정 물품 없음</span>`}</div>
        ${step.timer_sec ? timerMarkup(step.timer_sec) : ""}
        ${step.metronome ? metronomeMarkup() : ""}
        ${force}
      </div>
    </div>
    <div class="session-actions">
      <button id="doneBtn" class="primary">${session.completed ? "완료됨" : "완료"}</button>
      <button id="cantBtn">못 하겠음</button>
      <button id="worseBtn">증상 악화</button>
      <button id="speakBtn">음성 안내</button>
    </div>
  `;

  $("#doneBtn").addEventListener("click", () => advance("done"));
  $("#cantBtn").addEventListener("click", () => advance("cant"));
  $("#worseBtn").addEventListener("click", () => advance("worse"));
  $("#speakBtn").addEventListener("click", () => speak(`${step.title}. ${step.body}`));
  $("#sessionEmergencyBtn")?.addEventListener("click", () => showEmergency(session.id));
  $("#startTimerBtn")?.addEventListener("click", () => startTimer(step.timer_sec));
  $("#stopTimerBtn")?.addEventListener("click", stopTimer);
  $("#startMetronomeBtn")?.addEventListener("click", startMetronome);
  $("#stopMetronomeBtn")?.addEventListener("click", stopMetronome);

  if (step.timer_sec && step.timer_sec <= 180) startTimer(step.timer_sec);
  if (!step.metronome) stopMetronome();
}

function timerMarkup(seconds) {
  return `
    <div class="timer">
      <div>
        <strong id="timerValue">${formatTime(seconds)}</strong>
        <p>단계 타이머</p>
      </div>
      <div>
        <button id="startTimerBtn">시작</button>
        <button id="stopTimerBtn">정지</button>
      </div>
    </div>
  `;
}

function metronomeMarkup() {
  return `
    <div class="metronome">
      <span id="pulseDot" class="pulse-dot"></span>
      <div>
        <strong>110 BPM</strong>
        <p>가슴압박 템포 보조음</p>
      </div>
      <div>
        <button id="startMetronomeBtn" class="danger">시작</button>
        <button id="stopMetronomeBtn">정지</button>
      </div>
    </div>
  `;
}

async function advance(action) {
  if (!appState.currentSession) return;
  const payload = await fetchJson(`/api/session/${appState.currentSession.id}/action`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
  appState.currentSession = payload.session;
  appState.led = payload.led;
  renderDrawers();
  renderSession(payload.session);
  if (action === "cant" || action === "worse") showEmergency(payload.session.id);
  await refreshLogs();
}

async function classifyVoice() {
  const text = $("#voiceText").value.trim();
  if (!text) return;
  const result = await fetchJson("/api/classify", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  const box = $("#classifyResult");
  box.classList.remove("hidden");
  box.innerHTML = `
    <strong>분류 결과: ${result.scenario_title}</strong><br />
    신뢰도: ${result.confidence} / 분류기: ${result.classifier || "local"}<br />
    위험 신호: ${result.risk_flags?.length ? result.risk_flags.join(", ") : "없음"}<br />
    <button id="startClassifiedBtn" class="primary">이 절차 시작</button>
  `;
  $("#startClassifiedBtn").addEventListener("click", () => startScenario(result.scenario_id, "voice", result.risk_flags || []));
}

async function queryInventory() {
  const text = $("#inventoryQueryText").value.trim();
  if (!text) return;
  const payload = await fetchJson("/api/inventory/query", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  appState.inventory = payload.inventory || appState.inventory;
  appState.kit = payload.kit || appState.kit;
  appState.currentInventoryResult = payload.result;
  renderKitStatus();
  renderInventoryList();
  renderInventoryResult(payload.result);
  await refreshLogs();
}

function renderInventoryResult(result) {
  const box = $("#inventoryResult");
  box.classList.remove("hidden");
  const item = result.item;
  box.innerHTML = `
    <strong>${result.found ? "검색 결과" : "재고 확인"}</strong>
    <p>${result.message}</p>
    ${item ? `<p>${item.layer}단 ${item.cell}칸 · 수량 ${item.quantity}개${item.expired ? " · 유통기한 교체 필요" : ""}</p>` : ""}
    ${result.found && result.openable ? `<button id="openInventoryBtn" class="primary">해당 층 열기</button>` : ""}
  `;
  $("#openInventoryBtn")?.addEventListener("click", () => openInventoryItem(result.item.id));
}

async function openInventoryItem(itemId) {
  const payload = await fetchJson("/api/inventory/open", {
    method: "POST",
    body: JSON.stringify({ item_id: itemId }),
  });
  appState.inventory = payload.inventory || appState.inventory;
  appState.kit = { mode: appState.kit?.mode || "mock", state: payload.kit.state };
  renderKitStatus();
  renderInventoryList();
  $("#inventoryResult").insertAdjacentHTML("beforeend", `<p>서랍 ${payload.kit.state.open_layer}단을 열고 ${payload.kit.state.active_cell}칸 LED를 켰습니다.</p>`);
  await refreshLogs();
}

async function addInventoryItem(event) {
  event.preventDefault();
  const layer = Number($("#itemLayer").value);
  const cell = $("#itemCell").value.trim();
  const payload = await fetchJson("/api/inventory/items", {
    method: "POST",
    body: JSON.stringify({
      name: $("#itemName").value.trim(),
      aliases: $("#itemAliases").value.split(",").map((alias) => alias.trim()).filter(Boolean),
      layer,
      cell,
      quantity: Number($("#itemQuantity").value || 0),
      expiry_date: $("#itemExpiry").value || "2026-12-31",
      is_medicine: $("#itemMedicine").checked,
      auto_open_allowed: true,
      sensor_id: `stock_${cell.replace("-", "_")}`,
    }),
  });
  appState.inventory = payload.inventory || appState.inventory;
  appState.kit = payload.kit || appState.kit;
  renderInventoryList();
  renderKitStatus();
  $("#inventoryResult").classList.remove("hidden");
  $("#inventoryResult").innerHTML = `<strong>${payload.item.name}</strong><p>${payload.item.layer}단 ${payload.item.cell}칸에 등록했습니다.</p>`;
  $("#inventoryForm").reset();
  $("#itemLayer").value = "3";
  $("#itemCell").value = "3-2";
  $("#itemQuantity").value = "1";
  await refreshLogs();
}

async function analyzePhoto() {
  const file = $("#photoInput").files[0];
  if (!file) return;
  const payload = await localDemoFetch("/api/vision/upload", { method: "POST" });
  const result = $("#photoResult");
  result.classList.remove("hidden");
  result.innerHTML = `
    <p>${payload.analysis.summary}</p>
    <p>감지 플래그: ${payload.analysis.flags.join(", ")}</p>
    ${payload.suggested_scenario_id ? `<button id="startPhotoScenarioBtn" class="primary">${payload.suggested_title} 절차 시작</button>` : ""}
  `;
  $("#startPhotoScenarioBtn")?.addEventListener("click", () => openRiskDialog(payload.suggested_scenario_id));
  await refreshLogs();
}

async function showEmergency(sessionId = null) {
  activatePanel("emergencyPanel");
  const suffix = sessionId ? `?session_id=${sessionId}` : "";
  const payload = await fetchJson(`/api/emergency${suffix}`);
  appState.led = payload.led;
  renderDrawers();
  const emergency = payload.emergency;
  $("#emergencyContent").innerHTML = `
    <h2>${emergency.title}</h2>
    <p><a href="${emergency.tel_uri}">휴대폰에서 119 연결</a></p>
    <pre>${emergency.summary}</pre>
    <ol>${emergency.script.map((line) => `<li>${line}</li>`).join("")}</ol>
  `;
}

async function startCpr() {
  const payload = await fetchJson("/api/cpr/start", { method: "POST", body: "{}" });
  appState.currentSession = payload.session;
  appState.led = payload.led;
  renderDrawers();
  renderSession(payload.session);
  activatePanel("scenarioPanel");
}

async function submitCoSensor() {
  const ppm = Number($("#coPpm").value || 0);
  const payload = await fetchJson("/api/sensor/co", {
    method: "POST",
    body: JSON.stringify({ ppm }),
  });
  appState.led = payload.led;
  renderDrawers();
  if (payload.danger && payload.session) {
    appState.currentSession = payload.session;
    renderSession(payload.session);
    showEmergency(payload.session.id);
  }
  await refreshLogs();
}

function activatePanel(panelId) {
  $$(".mode-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.panel === panelId));
  $$(".panel").forEach((panel) => panel.classList.toggle("active", panel.id === panelId));
}

function startTimer(seconds) {
  stopTimer();
  appState.timerLeft = seconds;
  updateTimer();
  appState.timerId = setInterval(() => {
    appState.timerLeft -= 1;
    updateTimer();
    if (appState.timerLeft <= 0) stopTimer();
  }, 1000);
}

function stopTimer() {
  if (appState.timerId) clearInterval(appState.timerId);
  appState.timerId = null;
}

function updateTimer() {
  const el = $("#timerValue");
  if (el) el.textContent = formatTime(Math.max(appState.timerLeft, 0));
}

function formatTime(seconds) {
  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return `${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function startMetronome() {
  stopMetronome();
  const interval = Math.round(60000 / 110);
  appState.audioCtx ||= new (window.AudioContext || window.webkitAudioContext)();
  const beat = () => {
    const dot = $("#pulseDot");
    dot?.classList.add("beat");
    setTimeout(() => dot?.classList.remove("beat"), 90);
    const osc = appState.audioCtx.createOscillator();
    const gain = appState.audioCtx.createGain();
    osc.frequency.value = 880;
    gain.gain.value = 0.08;
    osc.connect(gain).connect(appState.audioCtx.destination);
    osc.start();
    osc.stop(appState.audioCtx.currentTime + 0.055);
  };
  beat();
  appState.metronomeId = setInterval(beat, interval);
}

function stopMetronome() {
  if (appState.metronomeId) clearInterval(appState.metronomeId);
  appState.metronomeId = null;
}

function speak(text) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "ko-KR";
  utterance.rate = 0.95;
  window.speechSynthesis.speak(utterance);
}

function setupSpeechRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const buttons = [
    { button: $("#listenBtn"), target: $("#voiceText") },
    { button: $("#listenInventoryBtn"), target: $("#inventoryQueryText") },
  ];
  if (!Recognition) {
    buttons.forEach(({ button }) => {
      button.disabled = true;
      button.textContent = "브라우저 미지원";
    });
    return;
  }
  buttons.forEach(({ button, target }) => {
    const recognition = new Recognition();
    recognition.lang = "ko-KR";
    recognition.interimResults = false;
    button.addEventListener("click", () => recognition.start());
    recognition.addEventListener("result", (event) => {
      target.value = event.results[0][0].transcript;
    });
  });
}

async function refreshLogs() {
  const logs = await fetchJson("/api/logs");
  appState.events = logs.events;
  renderEvents();
}

function visualSvg(key, label) {
  const titles = {
    ppe: "장갑",
    press: "직접 압박",
    stack_gauze: "거즈 추가",
    call119: "119",
    wash_hand: "손 위생",
    rinse: "세척",
    bandage: "붕대",
    checklist: "확인",
    safe_distance: "안전 거리",
    cool_water: "냉각",
    cover_burn: "덮기",
    do_not_pull: "제거 금지",
    side_pressure: "주변 압박",
    immobilize: "고정",
    stop_motion: "움직임 제한",
    support_joint: "위아래 지지",
    splint: "임시 고정",
    cold_pack: "냉찜질",
    warm_place: "보온",
    blanket: "보온포",
    warm_drink: "따뜻한 음료",
    shade: "그늘",
    loosen: "느슨하게",
    cool_body: "몸 식히기",
    drink_water: "수분",
    fresh_air: "밖으로 이동",
    do_not_enter: "재진입 금지",
    stinger: "벌침 제거",
    tap_shoulder: "반응 확인",
    breathing: "호흡 확인",
    cpr: "가슴압박",
    aed: "AED",
  };
  const title = titles[key] || label || "안내";
  const redKeys = new Set(["press", "stack_gauze", "call119", "do_not_pull", "side_pressure", "cpr"]);
  const blueKeys = new Set(["cool_water", "rinse", "cold_pack", "cool_body", "drink_water", "aed"]);
  const amberKeys = new Set(["warm_place", "blanket", "warm_drink", "fresh_air", "do_not_enter"]);
  const color = redKeys.has(key) ? "#dc2626" : blueKeys.has(key) ? "#2563eb" : amberKeys.has(key) ? "#b45309" : "#0f766e";
  return `
    <svg viewBox="0 0 520 360" role="img" aria-label="${title}">
      <rect width="520" height="360" fill="#f8fafc"/>
      <circle cx="260" cy="168" r="112" fill="${color}" opacity="0.12"/>
      <rect x="108" y="214" width="304" height="48" rx="8" fill="#ffffff" stroke="#cbd5e1" stroke-width="4"/>
      <path d="M166 210 C198 150 236 122 260 122 C284 122 322 150 354 210" fill="none" stroke="${color}" stroke-width="18" stroke-linecap="round"/>
      <circle cx="260" cy="105" r="34" fill="#ffffff" stroke="${color}" stroke-width="12"/>
      <line x1="196" y1="242" x2="324" y2="242" stroke="${color}" stroke-width="12" stroke-linecap="round"/>
      <text x="260" y="310" text-anchor="middle" fill="#172033" font-size="34" font-weight="700">${title}</text>
    </svg>
  `;
}

function bindEvents() {
  $$(".mode-tab").forEach((button) => button.addEventListener("click", () => activatePanel(button.dataset.panel)));
  $("#classifyBtn").addEventListener("click", classifyVoice);
  $("#searchInventoryBtn").addEventListener("click", queryInventory);
  $("#inventoryForm").addEventListener("submit", addInventoryItem);
  $("#analyzePhotoBtn").addEventListener("click", analyzePhoto);
  $("#emergencyBtn").addEventListener("click", () => showEmergency(appState.currentSession?.id));
  $("#startCprBtn").addEventListener("click", startCpr);
  $("#coSensorBtn").addEventListener("click", submitCoSensor);
  $$(".danger-actions button[data-risk]").forEach((button) => {
    button.addEventListener("click", () => startScenario("cpr", "life_threat", [button.dataset.risk]));
  });
  $("#riskStartBtn").addEventListener("click", (event) => {
    event.preventDefault();
    const flags = $$("#riskQuestions input:checked").map((input) => input.value);
    const scenario = appState.currentScenarioForRisk;
    $("#riskDialog").close();
    if (scenario) startScenario(scenario.id, "touch", flags);
  });
}

bindEvents();
setupSpeechRecognition();
loadState().catch((error) => {
  $("#connectionStatus").textContent = error.message;
});
