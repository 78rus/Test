(() => {
  "use strict";

  const icons = {
    "panel-left": "<rect x=\"3\" y=\"4\" width=\"18\" height=\"16\" rx=\"2\"/><path d=\"M9 4v16\"/>",
    "chevron-down": "<path d=\"m6 9 6 6 6-6\"/>",
    plus: "<path d=\"M12 5v14M5 12h14\"/>",
    "layout-dashboard": "<rect x=\"3\" y=\"3\" width=\"7\" height=\"7\" rx=\"1\"/><rect x=\"14\" y=\"3\" width=\"7\" height=\"7\" rx=\"1\"/><rect x=\"3\" y=\"14\" width=\"7\" height=\"7\" rx=\"1\"/><rect x=\"14\" y=\"14\" width=\"7\" height=\"7\" rx=\"1\"/>",
    activity: "<path d=\"M3 12h4l3-8 4 16 3-8h4\"/>",
    bookmark: "<path d=\"M6 4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18l-6-4-6 4Z\"/>",
    layers: "<path d=\"m12 2 9 5-9 5-9-5 9-5Z\"/><path d=\"m3 12 9 5 9-5M3 17l9 5 9-5\"/>",
    "arrow-right": "<path d=\"M5 12h14M13 6l6 6-6 6\"/>",
    "shield-check": "<path d=\"M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z\"/><path d=\"m9 12 2 2 4-4\"/>",
    "more-horizontal": "<circle cx=\"5\" cy=\"12\" r=\"1\" fill=\"currentColor\" stroke=\"none\"/><circle cx=\"12\" cy=\"12\" r=\"1\" fill=\"currentColor\" stroke=\"none\"/><circle cx=\"19\" cy=\"12\" r=\"1\" fill=\"currentColor\" stroke=\"none\"/>",
    "chevron-right": "<path d=\"m9 18 6-6-6-6\"/>",
    search: "<circle cx=\"11\" cy=\"11\" r=\"7\"/><path d=\"m20 20-4-4\"/>",
    bell: "<path d=\"M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4\"/>",
    store: "<path d=\"M3 10h18l-1-6H4l-1 6Z\"/><path d=\"M5 10v10h14V10M3 10a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0M9 20v-5h6v5\"/>",
    "map-pin": "<path d=\"M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z\"/><circle cx=\"12\" cy=\"10\" r=\"2.5\"/>",
    server: "<rect x=\"3\" y=\"3\" width=\"18\" height=\"7\" rx=\"1\"/><rect x=\"3\" y=\"14\" width=\"18\" height=\"7\" rx=\"1\"/><path d=\"M7 7h.01M7 18h.01\"/>",
    "refresh-cw": "<path d=\"M20 11a8.1 8.1 0 0 0-15.5-2M4 5v4h4M4 13a8.1 8.1 0 0 0 15.5 2M20 19v-4h-4\"/>",
    "terminal-square": "<rect x=\"3\" y=\"3\" width=\"18\" height=\"18\" rx=\"3\"/><path d=\"m7 8 3 4-3 4M13 16h4\"/>",
    "grid-2x2": "<rect x=\"3\" y=\"3\" width=\"7\" height=\"7\" rx=\"1\"/><rect x=\"14\" y=\"3\" width=\"7\" height=\"7\" rx=\"1\"/><rect x=\"3\" y=\"14\" width=\"7\" height=\"7\" rx=\"1\"/><rect x=\"14\" y=\"14\" width=\"7\" height=\"7\" rx=\"1\"/>",
    terminal: "<path d=\"m4 17 6-5-6-5M12 17h8\"/>",
    "folder-open": "<path d=\"m3 7 2-3h5l2 3h9v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z\"/><path d=\"M3 12h18\"/>",
    database: "<ellipse cx=\"12\" cy=\"5\" rx=\"8\" ry=\"3\"/><path d=\"M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7\"/>",
    monitor: "<rect x=\"3\" y=\"4\" width=\"18\" height=\"13\" rx=\"2\"/><path d=\"M8 21h8M12 17v4\"/>",
    cpu: "<rect x=\"4\" y=\"4\" width=\"16\" height=\"16\" rx=\"2\"/><rect x=\"8\" y=\"8\" width=\"8\" height=\"8\" rx=\"1\"/><path d=\"M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3\"/>",
    "scan-line": "<path d=\"M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M3 12h18\"/>",
    "check-circle-2": "<path d=\"M22 11.1V12a10 10 0 1 1-5.9-9.1\"/><path d=\"m22 4-10 10.01-3-3\"/>",
    gauge: "<path d=\"m12 14 4-4\"/><path d=\"M3.3 17a10 10 0 1 1 17.4 0\"/><path d=\"M6.7 13.8a6 6 0 0 1 10.6 0\"/>",
    "memory-stick": "<rect x=\"3\" y=\"5\" width=\"18\" height=\"14\" rx=\"2\"/><path d=\"M7 5v-2M11 5v-2M15 5v-2M19 5v-2M7 19v2M11 19v2M15 19v2M19 19v2M7 9h10v6H7Z\"/>",
    waypoints: "<circle cx=\"5\" cy=\"5\" r=\"2\"/><circle cx=\"19\" cy=\"19\" r=\"2\"/><path d=\"m7 5 5 0a4 4 0 0 1 4 4v1a4 4 0 0 0 4 4h-1M5 7v5a4 4 0 0 0 4 4h4\"/>",
    "arrow-up-right": "<path d=\"M7 17 17 7M7 7h10v10\"/>",
    check: "<path d=\"m5 12 4 4L19 6\"/>",
    "table-2": "<path d=\"M3 3h18v18H3zM3 9h18M9 9v12\"/>",
    "file-edit": "<path d=\"M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z\"/><path d=\"M13 2v7h7M9.5 17.5l5.6-5.6 2 2-5.6 5.6-2.7.7Z\"/>",
    "upload-cloud": "<path d=\"M16 16l-4-4-4 4M12 12v9\"/><path d=\"M20.4 17.5A5 5 0 0 0 18 8h-1.3A7 7 0 1 0 5 14.3\"/>",
    "rotate-cw": "<path d=\"M21 12a9 9 0 1 1-2.6-6.4L21 8\"/><path d=\"M21 3v5h-5\"/>",
    eraser: "<path d=\"m7 21 10-10\"/><path d=\"m16 3 5 5-9 9H6l-3-3 11-11a2 2 0 0 1 2 0Z\"/><path d=\"M6 17h11\"/>",
    "lock-keyhole": "<rect x=\"4\" y=\"10\" width=\"16\" height=\"11\" rx=\"2\"/><path d=\"M8 10V7a4 4 0 0 1 8 0v3M12 14v3\"/>",
    "maximize-2": "<path d=\"M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7\"/>",
    wifi: "<path d=\"M5 13a10 10 0 0 1 14 0M2 9a15 15 0 0 1 20 0M8 17a5 5 0 0 1 8 0M12 21h.01\"/>",
    "wifi-off": "<path d=\"M1 1l22 22M5 13a10 10 0 0 1 4-2.5M2 9a15 15 0 0 1 5-3M16 16a5 5 0 0 1 3 2M19 19h.01\"/>",
    upload: "<path d=\"M12 16V4M7 9l5-5 5 5M5 20h14\"/>",
    "file-plus-2": "<path d=\"M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6Z\"/><path d=\"M14 2v4h4M12 11v6M9 14h6\"/>",
    "hard-drive": "<path d=\"M3 6h18v12H3z\"/><path d=\"M3 10h18M7 14h.01M11 14h.01\"/>",
    "arrow-left": "<path d=\"M19 12H5M11 18l-6-6 6-6\"/>",
    list: "<path d=\"M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01\"/>",
    "file-code-2": "<path d=\"M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6Z\"/><path d=\"M14 2v4h4M10 13l-2 2 2 2M14 13l2 2-2 2\"/>",
    play: "<path d=\"m8 5 11 7-11 7V5Z\"/>",
    receipt: "<path d=\"M4 2v20l3-2 3 2 2-2 3 2 3-2 2 2V2l-3 2-3-2-2 2-3-2-3 2-2-2Z\"/><path d=\"M8 9h8M8 13h8M8 17h4\"/>",
    package: "<path d=\"m16.5 9.4-9-5.19M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z\"/><path d=\"M3.3 7 12 12l8.7-5M12 22V12\"/>",
    "settings-2": "<path d=\"M20 7h-9M14 17H5M17 3v4M7 13v4M17 17v4M7 3v4\"/><circle cx=\"7\" cy=\"9\" r=\"2\"/><circle cx=\"17\" cy=\"15\" r=\"2\"/>",
    "mouse-pointer-2": "<path d=\"m4 4 6.5 16 2.5-7 7-2.5L4 4Z\"/><path d=\"m13 13 6 6\"/>",
    keyboard: "<rect x=\"2\" y=\"5\" width=\"20\" height=\"14\" rx=\"2\"/><path d=\"M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 13h.01M10 13h.01M14 13h4M6 16h12\"/>",
    "scan-barcode": "<path d=\"M3 5V3h2M17 3h2v2M19 19h2v-2M5 21H3v-2M7 7v10M10 7v10M13 7v10M16 7v10\"/>",
    printer: "<path d=\"M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2\"/><path d=\"M6 14h12v8H6zM18 13h.01\"/>",
    scale: "<path d=\"M12 3v18M5 7h14M5 7l-3 6a3 3 0 0 0 6 0L5 7ZM19 7l-3 6a3 3 0 0 0 6 0l-3-6ZM5 21h14\"/>",
    sparkles: "<path d=\"m12 3-1.4 4.6L6 9l4.6 1.4L12 15l1.4-4.6L18 9l-4.6-1.4L12 3ZM19 15l-.7 2.3L16 18l2.3.7L19 21l.7-2.3L22 18l-2.3-.7L19 15ZM5 15l-.5 1.5L3 17l1.5.5L5 19l.5-1.5L7 17l-1.5-.5L5 15Z\"/>",
    "plug-zap": "<path d=\"m12 22 4-4M7 8V3M17 8V3M5 8h14v2a7 7 0 0 1-14 0V8ZM12 15v7M19 3l-3 5h5l-3 5\"/>",
    x: "<path d=\"M18 6 6 18M6 6l12 12\"/>",
    "corner-down-left": "<path d=\"m9 10-5 5 5 5M4 15h11a5 5 0 0 0 5-5V4\"/>",
    download: "<path d=\"M12 3v12M7 10l5 5 5-5M5 21h14\"/>",
    folder: "<path d=\"M3 6a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z\"/>"
  };

  const makeIcon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.sparkles}</svg>`;
  document.querySelectorAll("[data-icon]").forEach((node) => { node.innerHTML = makeIcon(node.dataset.icon); });

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const toastStack = $("#toastStack");
  const originalTerminal = $("#terminalOutput").innerHTML;

  const sessions = {
    warehouse: { title: "Склад · Терминал 01", ip: "10.24.8.41", location: "Москва, Ленинский пр-т", uptime: "В сети 00:42:18", type: "POS", status: "online" },
    cafe: { title: "Кафе · Касса 02", ip: "10.24.8.42", location: "Москва, ул. Малая Бронная", uptime: "В сети 02:16:04", type: "SCO", status: "online" },
    shop: { title: "Магазин · Линия 03", ip: "10.24.8.50", location: "Химки, мкр. Левобережный", uptime: "Переподключение", type: "Touch", status: "warning" },
    reserve: { title: "Резерв · Терминал 01", ip: "10.24.8.60", location: "Москва, резервный контур", uptime: "Была в сети вчера", type: "Hybrid", status: "offline" }
  };
  let activeSession = "warehouse";

  function showToast(message, tone = "success", icon = "check-circle-2") {
    const toast = document.createElement("div");
    toast.className = `toast ${tone === "warning" ? "warning" : ""}`;
    toast.innerHTML = `<span class="icon">${makeIcon(icon)}</span><span>${message}</span>`;
    toastStack.appendChild(toast);
    window.setTimeout(() => {
      toast.classList.add("out");
      window.setTimeout(() => toast.remove(), 260);
    }, 3200);
  }

  function selectSession(id, announce = true) {
    const data = sessions[id];
    if (!data) return;
    activeSession = id;
    $$(".session-card").forEach((card) => card.classList.toggle("selected", card.dataset.session === id));
    $("#sessionTitle").textContent = data.title;
    $("#breadcrumbSession").textContent = data.title;
    $("#sessionIp").textContent = data.ip;
    $("#terminalHost").textContent = data.ip;
    $("#sessionUptime").textContent = data.uptime;
    const headerPill = $(".title-line .connection-pill");
    const statusMetric = $(".status-card .metric-value");
    const statusFoot = $(".status-card .metric-foot");
    if (data.status === "online") {
      headerPill.innerHTML = '<span class="status-dot online"></span> Подключено';
      headerPill.style.borderColor = "";
      headerPill.style.color = "";
      headerPill.style.background = "";
      statusMetric.textContent = "Онлайн";
      statusFoot.innerHTML = '<span class="status-dot online"></span> Все сервисы отвечают <span class="metric-time">32 ms</span>';
    } else if (data.status === "warning") {
      headerPill.innerHTML = '<span class="status-dot warning"></span> Нестабильно';
      headerPill.style.borderColor = "rgba(242,183,103,.18)";
      headerPill.style.color = "#f7c982";
      headerPill.style.background = "rgba(242,183,103,.08)";
      statusMetric.textContent = "Проверка";
      statusFoot.innerHTML = '<span class="status-dot warning"></span> Требуется внимание <span class="metric-time">—</span>';
    } else {
      headerPill.innerHTML = '<span class="status-dot offline"></span> Нет связи';
      headerPill.style.borderColor = "rgba(147,156,174,.18)";
      headerPill.style.color = "#aab4c4";
      headerPill.style.background = "rgba(147,156,174,.08)";
      statusMetric.textContent = "Офлайн";
      statusFoot.innerHTML = '<span class="status-dot offline"></span> Последний ответ вчера <span class="metric-time">—</span>';
    }
    if (announce) showToast(`Открыта сессия «${data.title}»`, data.status === "offline" ? "warning" : "success", data.status === "offline" ? "wifi-off" : "check-circle-2");
  }

  function showTab(tab) {
    $$(".module-tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
    $$(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === tab));
    if (tab === "terminal") window.setTimeout(() => $("#terminalInput").focus(), 80);
    if (tab === "overview") window.scrollTo({ top: 0, behavior: "smooth" });
  }

  $$(".session-card").forEach((card) => card.addEventListener("click", () => selectSession(card.dataset.session)));
  $$(".module-tab").forEach((button) => button.addEventListener("click", () => showTab(button.dataset.tab)));
  $$('[data-open-tab], [data-quick-tab]').forEach((button) => button.addEventListener("click", () => showTab(button.dataset.openTab || button.dataset.quickTab)));

  $("#openTerminal").addEventListener("click", () => showTab("terminal"));
  $("#refreshSession").addEventListener("click", (event) => {
    const button = event.currentTarget;
    const icon = $(".icon", button);
    icon.classList.add("is-spinning");
    window.setTimeout(() => icon.classList.remove("is-spinning"), 750);
    showToast("Состояние сессии обновлено");
  });
  $("#rescanButton").addEventListener("click", (event) => runScan(event.currentTarget, "Сканирование завершено: найдено 18 компонентов"));
  $("#scanHardware").addEventListener("click", (event) => runScan(event.currentTarget, "Оборудование проверено: 6 устройств готовы"));
  $("#viewTunnels").addEventListener("click", () => showToast("Открыт менеджер туннелей · 3 активных", "success", "waypoints"));
  $("#connectionMenu").addEventListener("click", () => showToast("Меню подключений открыто", "success", "settings-2"));
  $("#manageConnections").addEventListener("click", () => showToast("Менеджер подключений уже доступен в настройках профиля", "success", "bookmark"));
  $("#manageSessions").addEventListener("click", () => showToast("Доступно 6 свободных слотов для новых касс", "success", "layers"));
  $("#showAllSessions").addEventListener("click", () => showToast("Показаны активные сессии · всего 4 из 10", "success", "layers"));
  $("#openActivity").addEventListener("click", () => {
    $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.nav === "activity"));
    showToast("Журнал событий синхронизирован", "success", "activity");
  });
  $("#notificationButton").addEventListener("click", () => showToast("3 уведомления: 1 требует внимания", "warning", "bell"));
  $("#moreActions").addEventListener("click", () => showToast("Дополнительные действия доступны в меню сессии", "success", "more-horizontal"));
  $("#profileButton").addEventListener("click", () => showToast("Профиль инженера · рабочее пространство защищено", "success", "shield-check"));

  function runScan(button, message) {
    const original = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="icon is-spinning">${makeIcon("refresh-cw")}</span> Проверяем…`;
    window.setTimeout(() => {
      button.disabled = false;
      button.innerHTML = original;
      button.querySelectorAll("[data-icon]").forEach((node) => { node.innerHTML = makeIcon(node.dataset.icon); });
      showToast(message, "success", "check-circle-2");
    }, 1150);
  }

  // New connection dialog
  const modal = $("#connectionModal");
  const openModal = () => { modal.hidden = false; document.body.classList.add("modal-open"); $("#connectionForm input[name=name]").focus(); };
  const closeModal = () => { modal.hidden = true; document.body.classList.remove("modal-open"); };
  $("#newConnection").addEventListener("click", openModal);
  $("#closeConnectionModal").addEventListener("click", closeModal);
  $("#cancelConnection").addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => { if (event.target === modal) closeModal(); });
  $("#connectionForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name")).trim();
    const host = String(form.get("host")).trim();
    const type = String(form.get("type"));
    const id = `custom-${Date.now()}`;
    sessions[id] = { title: name, ip: host, location: "Новая сессия", uptime: "В сети 00:00:01", type, status: "online" };
    const card = document.createElement("button");
    card.type = "button";
    card.className = "session-card";
    card.dataset.session = id;
    card.innerHTML = `<span class="session-badge blue">${name.charAt(0).toUpperCase() || "Н"}</span><span class="session-card-copy"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(host)} <span class="session-type">${escapeHtml(type)}</span></small></span><span class="status-dot online"></span>`;
    card.addEventListener("click", () => selectSession(id));
    $("#sessionList").appendChild(card);
    closeModal();
    selectSession(id, false);
    showTab("overview");
    showToast(`Сессия «${name}» подключена`, "success", "plug-zap");
    event.currentTarget.reset();
  });

  // Terminal interaction
  $("#terminalForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("#terminalInput");
    const command = input.value.trim();
    if (!command) return;
    const output = $("#terminalOutput");
    const caret = output.querySelector(".terminal-caret");
    if (caret) caret.closest("div").remove();
    const prompt = document.createElement("div");
    prompt.innerHTML = `<span class="terminal-green">alexey@cashdesk-01</span><span class="terminal-muted">:</span><span class="terminal-blue">~</span><span class="terminal-muted">$</span> ${escapeHtml(command)}`;
    output.appendChild(prompt);
    const response = document.createElement("div");
    response.className = "terminal-response";
    const lower = command.toLowerCase();
    if (lower.includes("uptime")) response.textContent = " 14:33:04 up 2 days,  6:18,  1 user,  load average: 0.42, 0.38, 0.31";
    else if (lower.includes("df")) response.textContent = "/dev/mapper/ubuntu--vg-root   200G  128G   62G  68% /";
    else if (lower.includes("clear")) { output.innerHTML = ""; input.value = ""; return; }
    else if (lower.includes("help")) response.textContent = "Доступно: systemctl status cashdesk, uptime, df -h, devices --list";
    else response.textContent = `Команда выполнена на ${sessions[activeSession]?.ip || "кассе"} · код 0`;
    output.appendChild(response);
    const finalPrompt = document.createElement("div");
    finalPrompt.innerHTML = '<span class="terminal-green">alexey@cashdesk-01</span><span class="terminal-muted">:</span><span class="terminal-blue">~</span><span class="terminal-muted">$</span> <span class="terminal-caret">▊</span>';
    output.appendChild(finalPrompt);
    input.value = "";
    output.scrollTop = output.scrollHeight;
  });
  $("#clearTerminal").addEventListener("click", () => {
    $("#terminalOutput").innerHTML = originalTerminal;
    showToast("Экран терминала очищен", "success", "eraser");
  });

  // File manager actions
  $$(".file-row").forEach((row) => row.addEventListener("click", () => {
    $$(".file-row").forEach((item) => item.classList.remove("selected"));
    row.classList.add("selected");
    const file = $("strong", row)?.textContent || "файл";
    showToast(`Выбран файл «${file}»`, "success", "file-edit");
  }));
  $("#uploadFile").addEventListener("click", () => showToast("Выберите файл для загрузки в /opt/cashdesk", "success", "upload"));
  $("#newFile").addEventListener("click", () => showToast("Создание нового файла в /opt/cashdesk", "success", "file-plus-2"));

  // Database actions
  $("#runQuery").addEventListener("click", () => {
    const button = $("#runQuery");
    const previous = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="icon is-spinning">${makeIcon("refresh-cw")}</span> Выполняется`;
    window.setTimeout(() => {
      button.disabled = false;
      button.innerHTML = previous;
      showToast("Запрос выполнен · 24 строки · 0.12 сек", "success", "check-circle-2");
    }, 750);
  });
  $("#queryInput").addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); $("#runQuery").click(); }
  });
  $("#refreshDatabase").addEventListener("click", () => showToast("Схема базы данных обновлена", "success", "refresh-cw"));
  $("#exportData").addEventListener("click", () => downloadFile("orders.csv", "order_id,status,total_amount,created_at\n104829,paid,2480.00,2026-09-05T14:28:12Z\n104828,paid,860.00,2026-09-05T14:25:47Z\n104827,pending,1240.00,2026-09-05T14:24:03Z\n104826,paid,5610.00,2026-09-05T14:20:58Z\n104825,cancelled,320.00,2026-09-05T14:18:22Z\n", "text/csv"));
  $$(".schema-table").forEach((row) => row.addEventListener("click", () => {
    $$(".schema-table").forEach((item) => item.classList.remove("active"));
    row.classList.add("active");
    showToast(`Открыта таблица ${row.textContent.trim().split(" ")[0]}`, "success", "table-2");
  }));

  // VNC and report actions
  $("#vncFullscreen").addEventListener("click", async () => {
    const screen = $(".vnc-screen");
    try {
      if (!document.fullscreenElement) await screen.requestFullscreen();
      else await document.exitFullscreen();
    } catch (error) { showToast("Полноэкранный режим недоступен в этом окне", "warning", "monitor"); }
  });
  $("#restartVnc").addEventListener("click", () => showToast("VNC-подключение переподнимается…", "success", "rotate-cw"));
  $("#hardwareReport").addEventListener("click", () => downloadFile("cashdesk-hardware-report.txt", "Касса Control — отчёт оборудования\nСессия: Склад · Терминал 01\nПроверено: 05.09.2026 14:32 UTC\n\nТип: POS · Touch\nОС: Ubuntu 22.04 LTS x86_64\nНайдено устройств: 6\nСостояние: все критичные компоненты в норме\n", "text/plain"));

  function downloadFile(filename, content, type) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([content], { type }));
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 500);
    showToast(`Файл «${filename}» подготовлен`, "success", "download");
  }

  // Quick command palette
  const palette = $("#commandPalette");
  const openPalette = () => { palette.hidden = false; $("#paletteInput").value = ""; $("#paletteInput").focus(); };
  const closePalette = () => { palette.hidden = true; };
  $("#searchTrigger").addEventListener("click", openPalette);
  palette.addEventListener("click", (event) => { if (event.target === palette) closePalette(); });
  $$("[data-palette-tab]").forEach((button) => button.addEventListener("click", () => { closePalette(); showTab(button.dataset.paletteTab); }));
  $("#paletteInput").addEventListener("input", (event) => {
    const value = event.target.value.toLowerCase();
    $$(".palette-items button").forEach((item) => { item.hidden = value && !item.textContent.toLowerCase().includes(value); });
  });

  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openPalette(); }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "n") { event.preventDefault(); openModal(); }
    if (event.key === "Escape") { if (!palette.hidden) closePalette(); if (!modal.hidden) closeModal(); }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "l" && $("[data-panel=terminal]").classList.contains("active")) { event.preventDefault(); $("#clearTerminal").click(); }
  });

  function escapeHtml(value) {
    return value.replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
  }

  // Keep the preview useful on narrow screens: the desktop rail can be opened with a generated menu button.
  const mobileMenu = document.createElement("button");
  mobileMenu.type = "button";
  mobileMenu.className = "icon-button mobile-menu";
  mobileMenu.setAttribute("aria-label", "Открыть меню");
  mobileMenu.innerHTML = makeIcon("panel-left");
  $(".topbar").prepend(mobileMenu);
  mobileMenu.addEventListener("click", () => $("#sidebar").classList.toggle("is-open"));
  $("#sidebarClose").addEventListener("click", () => $("#sidebar").classList.remove("is-open"));
})();
