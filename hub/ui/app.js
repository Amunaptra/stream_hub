const app = document.querySelector("#app");
const MAX_PLAYLIST_STREAMS = 50;

const state = {
  devices: [],
  filter: "all",
  selected: null,
  config: null,
  streamHealth: [],
  timer: null,
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const message = await response.json().then(x => x.detail).catch(() => `HTTP ${response.status}`);
    const error = new Error(message || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatBytes(value) {
  if (value === null || value === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = Number(value), index = 0;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return `${size.toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}

function formatUptime(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return days ? `${days}g ${hours}s` : `${hours}s`;
}

function deviceIssue(device) {
  if (!device.online) return "offline";
  if (!device.approved) return "pending";
  if (device.player_service !== "active") return "player";
  if (device.disk_percent >= 90 || (device.temperature_c ?? 0) >= 80 || device.log_usage_bytes >= 900 * 1024 * 1024) return "health";
  if (["pending", "delivered", "failed"].includes(device.config_sync_status)) return "sync";
  return null;
}

function badge(text, kind = "") {
  return el("span", `badge ${kind}`, text);
}

function toast(message) {
  document.querySelector(".toast")?.remove();
  const node = el("div", "toast", message);
  document.body.append(node);
  setTimeout(() => node.remove(), 2600);
}

function renderLogin(message = "") {
  clearInterval(state.timer);
  app.innerHTML = "";
  const wrap = el("main", "login-wrap");
  const card = el("section", "login-card");
  card.append(el("div", "eyebrow", "Yerel yönetim"), el("h1", "", "Stream Hub"), el("p", "subtitle", "Odroid yayın cihazlarınızı tek noktadan yönetin."));
  const field = el("div", "field");
  field.append(el("label", "", "Hub yönetici token’ı"));
  const input = document.createElement("input");
  input.type = "password"; input.autocomplete = "current-password"; input.placeholder = "Yönetici token’ını girin";
  field.append(input);
  const button = el("button", "btn primary", "Giriş yap");
  button.style.marginTop = "14px";
  button.style.width = "100%";
  const error = el("div", "error", message);
  error.hidden = !message;
  async function login() {
    error.hidden = true; button.disabled = true;
    try {
      await api("/api/v1/session", { method: "POST", body: JSON.stringify({ token: input.value }) });
      await loadDevices();
    } catch (e) {
      error.textContent = "Token doğrulanamadı."; error.hidden = false;
    } finally { button.disabled = false; }
  }
  button.onclick = login;
  input.addEventListener("keydown", event => { if (event.key === "Enter") login(); });
  card.append(field, button, error); wrap.append(card); app.append(wrap); input.focus();
}

function renderDashboard() {
  app.innerHTML = `
    <div class="shell">
      <header class="topbar"><div class="topbar-inner">
        <div class="brand"><span class="brand-mark"></span><span>Stream Hub</span></div>
        <div class="top-actions"><button class="btn ghost" id="refresh">Yenile</button><button class="btn ghost" id="logout">Çıkış</button></div>
      </div></header>
      <main class="content">
        <div class="eyebrow">Merkezi yayın kontrolü</div>
        <h1>Cihaz filosu</h1>
        <p class="subtitle">Tüm Odroid oynatıcıların canlı durumu ve merkezi yönetimi.</p>
        <section class="summary" id="summary"></section>
        <div class="toolbar"><div class="filters" id="filters"></div><span class="last-update" id="updated"></span></div>
        <section class="panel"><div id="deviceList"></div></section>
      </main>
    </div>`;
  document.querySelector("#refresh").onclick = () => loadDevices(true);
  document.querySelector("#logout").onclick = async () => { await api("/api/v1/session", { method: "DELETE" }); renderLogin(); };
  renderSummary(); renderFilters(); renderDeviceList();
}

function renderSummary() {
  const summary = document.querySelector("#summary");
  if (!summary) return;
  const total = state.devices.length;
  const online = state.devices.filter(x => x.online).length;
  const pending = state.devices.filter(x => !x.approved).length;
  const issues = state.devices.filter(x => deviceIssue(x) && deviceIssue(x) !== "pending").length;
  summary.innerHTML = "";
  [["Toplam cihaz", total], ["Online", online], ["Onay bekleyen", pending], ["Dikkat gereken", issues]].forEach(([label, value]) => {
    const card = el("article", "metric"); card.append(el("div", "metric-label", label), el("div", "metric-value", value)); summary.append(card);
  });
}

function renderFilters() {
  const filters = document.querySelector("#filters");
  if (!filters) return;
  filters.innerHTML = "";
  [["all", "Tümü"], ["online", "Online"], ["pending", "Onay bekleyen"], ["issues", "Sorunlu"]].forEach(([id, label]) => {
    const button = el("button", `filter ${state.filter === id ? "active" : ""}`, label);
    button.onclick = () => { state.filter = id; renderFilters(); renderDeviceList(); };
    filters.append(button);
  });
}

function filteredDevices() {
  if (state.filter === "online") return state.devices.filter(x => x.online);
  if (state.filter === "pending") return state.devices.filter(x => !x.approved);
  if (state.filter === "issues") return state.devices.filter(x => deviceIssue(x));
  return state.devices;
}

function renderDeviceList() {
  const host = document.querySelector("#deviceList");
  if (!host) return;
  host.innerHTML = "";
  const devices = filteredDevices();
  if (!devices.length) { host.append(el("div", "empty", "Bu filtrede cihaz bulunmuyor.")); return; }
  const table = el("table", "device-table");
  table.innerHTML = "<thead><tr><th>Cihaz</th><th>Durum</th><th>Aktif yayın</th><th>Sağlık</th><th>Config</th><th></th></tr></thead>";
  const body = document.createElement("tbody");
  devices.forEach(device => {
    const row = el("tr", "device-row");
    const name = el("td"); name.append(el("div", "device-name", device.hostname), el("div", "device-id", device.device_id));
    const statusCell = el("td"); statusCell.append(device.online ? badge("Online", "ok") : badge("Offline", "bad"));
    if (!device.approved) statusCell.append(document.createTextNode(" "), badge("Onay bekliyor", "warn"));
    const stream = el("td", "stream-name", device.current_stream_id || "—");
    const health = el("td");
    const healthBad = device.disk_percent >= 90 || (device.temperature_c ?? 0) >= 80;
    health.append(badge(healthBad ? "Kritik" : `${device.disk_percent.toFixed(0)}% disk`, healthBad ? "bad" : "ok"));
    const sync = el("td");
    const syncText = device.config_sync_status || "reported";
    sync.append(badge(syncText, syncText === "failed" ? "bad" : syncText === "applied" ? "ok" : "info"));
    const action = el("td"); const open = el("button", "btn", "Yönet"); open.onclick = () => openDevice(device.device_id); action.append(open);
    row.append(name, statusCell, stream, health, sync, action); body.append(row);
  });
  table.append(body); host.append(table);
}

async function loadDevices(showToast = false) {
  try {
    state.devices = await api("/api/v1/devices");
    if (!document.querySelector(".shell")) renderDashboard();
    else { renderSummary(); renderDeviceList(); }
    const updated = document.querySelector("#updated");
    if (updated) updated.textContent = `Son güncelleme ${new Date().toLocaleTimeString()}`;
    if (showToast) toast("Cihaz listesi güncellendi");
    clearInterval(state.timer); state.timer = setInterval(() => loadDevices(), 10000);
  } catch (e) {
    if (e.status === 401) renderLogin(); else if (showToast) toast("Cihaz listesi alınamadı");
  }
}

async function openDevice(deviceId) {
  const [device, config, streamHealth] = await Promise.all([
    api(`/api/v1/devices/${encodeURIComponent(deviceId)}`),
    api(`/api/v1/devices/${encodeURIComponent(deviceId)}/config`),
    api(`/api/v1/devices/${encodeURIComponent(deviceId)}/stream-health`),
  ]);
  state.selected = device; state.config = config; state.streamHealth = streamHealth;
  renderDrawer();
}

function detailStat(label, value) {
  const node = el("div", "detail-stat"); node.append(el("span", "", label), el("strong", "", value)); return node;
}

function streamHealthView(stream, health) {
  const wrap = el("div", "stream-health");
  if (!stream.enabled) {
    wrap.append(badge("Devre dışı"));
    return wrap;
  }
  if (!health) {
    wrap.append(badge("Kontrol bekliyor"));
    return wrap;
  }
  wrap.append(badge(health.ok ? "Sağlıklı" : "Hatalı", health.ok ? "ok" : "bad"));
  const details = health.ok
    ? `${health.status_code ?? "—"} · ${health.latency_ms} ms`
    : `${health.status_code ?? "—"} · ${health.error || "Kaynak yanıt vermiyor"}`;
  const checked = new Date(health.checked_at).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  wrap.append(el("small", "", details), el("small", "", `Son kontrol ${checked}`));
  return wrap;
}

function streamRow(stream = { id: "", enabled: true, seconds: 20, url: "" }, health = null) {
  const row = el("div", "stream-row");
  const enabled = document.createElement("input"); enabled.type = "checkbox"; enabled.checked = stream.enabled; enabled.className = "stream-enabled"; enabled.title = "Aktif";
  const id = document.createElement("input"); id.value = stream.id; id.placeholder = "Yayın ID"; id.className = "stream-id";
  const seconds = document.createElement("input"); seconds.type = "number"; seconds.min = "0"; seconds.max = "86400"; seconds.value = stream.seconds; seconds.className = "stream-seconds";
  const url = document.createElement("input"); url.value = stream.url; url.placeholder = "https://…/index.m3u8"; url.className = "stream-url";
  const remove = el("button", "btn ghost remove", "×"); remove.title = "Yayını kaldır"; remove.onclick = () => row.remove();
  row.append(enabled, id, seconds, url, streamHealthView(stream, health), remove); return row;
}

function renderDrawer() {
  document.querySelector(".drawer-backdrop")?.remove();
  const device = state.selected, config = state.config, streamHealth = state.streamHealth;
  const backdrop = el("div", "drawer-backdrop");
  const drawer = el("aside", "drawer");
  const head = el("div", "drawer-head");
  const title = el("div"); title.append(el("div", "eyebrow", device.device_id), el("h2", "", device.hostname), device.online ? badge("Online", "ok") : badge("Offline", "bad"));
  const close = el("button", "btn ghost", "Kapat"); close.onclick = () => backdrop.remove(); head.append(title, close); drawer.append(head);
  const grid = el("div", "detail-grid");
  grid.append(
    detailStat("IP", device.ip_addresses[0] || "—"),
    detailStat("CPU / RAM", `${device.cpu_percent ?? "—"}% / ${device.memory_percent ?? "—"}%`),
    detailStat("Disk boş", formatBytes(device.disk_free_bytes)),
    detailStat("Sıcaklık", device.temperature_c === null ? "—" : `${device.temperature_c}°C`),
    detailStat("Log kullanımı", formatBytes(device.log_usage_bytes)),
    detailStat("Uptime", formatUptime(device.uptime_seconds)),
    detailStat("Player", device.player_service),
    detailStat("Revision", `${device.config_revision} → ${device.desired_revision ?? device.config_revision}`)
  );
  drawer.append(grid);
  if (!device.approved) {
    const notice = el("div", "notice", "Bu cihaz otomatik keşfedildi. Config veya sistem komutu göndermeden önce cihazı onaylayın.");
    const approve = el("button", "btn primary", "Cihazı onayla"); approve.style.marginTop = "10px";
    approve.onclick = async () => { await api(`/api/v1/devices/${encodeURIComponent(device.device_id)}/approve`, { method: "POST" }); toast("Cihaz onaylandı"); await loadDevices(); await openDevice(device.device_id); };
    notice.append(document.createElement("br"), approve); drawer.append(notice);
  }
  const playlistSection = el("section", "section");
  const sectionTitle = el("div", "section-title"); sectionTitle.append(el("h3", "", "Oynatma listesi"));
  const healthyCount = streamHealth.filter(item => item.ok).length;
  const unhealthyCount = streamHealth.filter(item => !item.ok).length;
  const healthSummary = el("div", "playlist-health-summary");
  healthSummary.append(badge(`${healthyCount} sağlıklı`, "ok"), badge(`${unhealthyCount} hatalı`, unhealthyCount ? "bad" : ""));
  sectionTitle.append(healthSummary);
  const actions = el("div", "actions"); const add = el("button", "btn", "+ Yayın"); const send = el("button", "btn primary", "Kaydet ve gönder");
  actions.append(add, send); sectionTitle.append(actions); playlistSection.append(sectionTitle);
  const healthById = new Map(streamHealth.map(item => [item.id, item]));
  const playlist = el("div", "playlist"); (config.streams || []).forEach(item => playlist.append(streamRow(item, healthById.get(item.id)))); if (!config.streams?.length) playlist.append(streamRow());
  add.onclick = () => {
    if (playlist.children.length >= MAX_PLAYLIST_STREAMS) {
      toast(`Bir oynatma listesi en fazla ${MAX_PLAYLIST_STREAMS} yayın içerebilir`);
      return;
    }
    playlist.append(streamRow());
  };
  send.disabled = !device.approved;
  send.onclick = async () => {
    const streams = [...playlist.querySelectorAll(".stream-row")].map(row => ({
      id: row.querySelector(".stream-id").value.trim(),
      enabled: row.querySelector(".stream-enabled").checked,
      seconds: Number(row.querySelector(".stream-seconds").value),
      url: row.querySelector(".stream-url").value.trim(),
    })).filter(item => item.id || item.url);
    send.disabled = true;
    try {
      const result = await api(`/api/v1/devices/${encodeURIComponent(device.device_id)}/config`, { method: "PUT", body: JSON.stringify({ default_seconds: config.default_seconds || 20, streams }) });
      toast(`Config revision ${result.revision} gönderim kuyruğunda`); await loadDevices();
    } catch (e) { toast(`Config kaydedilemedi: ${e.message}`); }
    finally { send.disabled = false; }
  };
  playlistSection.append(playlist); drawer.append(playlistSection);
  const commands = el("section", "section"); commands.append(el("h3", "", "Cihaz komutları"));
  const commandActions = el("div", "command-actions");
  const restart = el("button", "btn", "Player restart"); const reboot = el("button", "btn danger", "Cihazı reboot et");
  restart.disabled = reboot.disabled = !device.approved;
  restart.onclick = () => queueCommand(device.device_id, "player_restart", "Player restart kuyruğa alındı");
  reboot.onclick = async () => { if (confirm(`${device.hostname} yeniden başlatılsın mı?`)) await queueCommand(device.device_id, "reboot", "Reboot kuyruğa alındı"); };
  commandActions.append(restart, reboot); commands.append(commandActions); drawer.append(commands);
  backdrop.onclick = event => { if (event.target === backdrop) backdrop.remove(); };
  backdrop.append(drawer); document.body.append(backdrop);
}

async function queueCommand(deviceId, command, message) {
  await api(`/api/v1/devices/${encodeURIComponent(deviceId)}/commands`, { method: "POST", body: JSON.stringify({ command }) });
  toast(message);
}

loadDevices();
