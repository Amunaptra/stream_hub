const app = document.querySelector("#app");
const MAX_PLAYLIST_STREAMS = 50;

const state = {
  devices: [],
  filter: "all",
  selected: null,
  config: null,
  streamHealth: [],
  library: [],
  timer: null,
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const message = await response.json().then(x => formatApiError(x.detail, response.status)).catch(() => `HTTP ${response.status}`);
    const error = new Error(message || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

function formatApiError(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map(item => {
      const location = Array.isArray(item.loc) ? item.loc.filter(part => part !== "body").join(".") : "";
      return `${location ? `${location}: ` : ""}${item.msg || "Geçersiz değer"}`;
    }).join("; ");
  }
  if (detail && typeof detail === "object") return detail.message || detail.msg || JSON.stringify(detail);
  return `HTTP ${status}`;
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

function deviceName(device) {
  return device.display_name || device.hostname;
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
  const usernameField = el("div", "field");
  usernameField.append(el("label", "", "Kullanıcı adı"));
  const username = document.createElement("input");
  username.type = "text"; username.autocomplete = "username"; username.placeholder = "Kullanıcı adınız";
  usernameField.append(username);
  const passwordField = el("div", "field");
  passwordField.append(el("label", "", "Parola"));
  const password = document.createElement("input");
  password.type = "password"; password.autocomplete = "current-password"; password.placeholder = "Parolanız";
  passwordField.append(password);
  const button = el("button", "btn primary", "Giriş yap");
  button.style.marginTop = "14px";
  button.style.width = "100%";
  const error = el("div", "error", message);
  error.hidden = !message;
  async function login() {
    error.hidden = true; button.disabled = true;
    try {
      await api("/api/v1/session", { method: "POST", body: JSON.stringify({ username: username.value.trim(), password: password.value }) });
      await loadDevices();
    } catch (e) {
      error.textContent = "Kullanıcı adı veya parola hatalı."; error.hidden = false;
    } finally { button.disabled = false; }
  }
  button.onclick = login;
  username.addEventListener("keydown", event => { if (event.key === "Enter") password.focus(); });
  password.addEventListener("keydown", event => { if (event.key === "Enter") login(); });
  card.append(usernameField, passwordField, button, error); wrap.append(card); app.append(wrap); username.focus();
}

function renderDashboard() {
  app.innerHTML = `
    <div class="shell">
      <header class="topbar"><div class="topbar-inner">
        <div class="brand"><span class="brand-mark"></span><span>Stream Hub</span></div>
        <div class="top-actions"><button class="btn ghost" id="streamLibrary">Yayın kütüphanesi</button><button class="btn ghost" id="hubMigration">Hub adresi</button><button class="btn ghost" id="refresh">Yenile</button><button class="btn ghost" id="account">Hesap</button><button class="btn ghost" id="logout">Çıkış</button></div>
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
  document.querySelector("#streamLibrary").onclick = openStreamLibrary;
  document.querySelector("#hubMigration").onclick = openHubMigration;
  document.querySelector("#account").onclick = openAccount;
  document.querySelector("#logout").onclick = async () => { await api("/api/v1/session", { method: "DELETE" }); renderLogin(); };
  renderSummary(); renderFilters(); renderDeviceList();
}

function parseLibraryText(filename, text) {
  const trimmed = text.trim();
  if (!trimmed) throw new Error("Dosya boş.");
  if (filename.toLowerCase().endsWith(".json") || trimmed.startsWith("[") || trimmed.startsWith("{")) {
    const parsed = JSON.parse(trimmed);
    const rows = Array.isArray(parsed) ? parsed : parsed.streams;
    if (!Array.isArray(rows)) throw new Error("JSON bir dizi veya streams dizisi içermeli.");
    return rows.map(item => ({ id: item.id ?? item.name ?? "", url: item.url ?? "", seconds: Number(item.seconds ?? 20) }));
  }
  let generated = 0;
  return trimmed.split(/\r?\n/).map(line => line.trim()).filter(line => line && !line.startsWith("#")).map(line => {
    const parts = line.includes("|") ? line.split("|").map(value => value.trim()) : [line];
    if (parts.length === 1) {
      generated += 1;
      return { id: `stream-${String(generated).padStart(3, "0")}`, url: parts[0], seconds: 20 };
    }
    return { id: parts[0], url: parts[1] || "", seconds: Number(parts[2] || 20) };
  });
}

async function openStreamLibrary() {
  const backdrop = el("div", "library-backdrop");
  const card = el("section", "library-card");
  const head = el("div", "drawer-head");
  const title = el("div"); title.append(el("div", "eyebrow", "Ortak kaynak havuzu"), el("h2", "", "Yayın kütüphanesi"));
  const close = el("button", "btn ghost", "Kapat"); close.onclick = () => backdrop.remove(); head.append(title, close); card.append(head);
  card.append(el("div", "notice", "Dosyadaki yayınlar yalnız Hub kütüphanesine kaydedilir; hiçbir Odroid playlist'i otomatik değişmez. TXT: id|url|süre veya satır başına yalnız URL. JSON: [{id, url, seconds}]."));
  const importArea = el("div", "library-import");
  const file = document.createElement("input"); file.type = "file"; file.accept = ".txt,.json,text/plain,application/json";
  const importButton = el("button", "btn primary", "Dosyayı içe aktar"); importButton.disabled = true;
  const preview = el("div", "library-preview", "Bir TXT veya JSON dosyası seçin.");
  let pending = [];
  file.onchange = async () => {
    importButton.disabled = true;
    try {
      const selectedFile = file.files[0];
      if (!selectedFile) throw new Error("Dosya seçilmedi.");
      pending = parseLibraryText(selectedFile.name, await selectedFile.text());
      if (!pending.length) throw new Error("Dosyada yayın bulunamadı.");
      preview.textContent = `${pending.length} yayın bulundu. İlk kayıt: ${pending[0].id} → ${pending[0].url}`;
      importButton.disabled = false;
    } catch (error) {
      pending = [];
      preview.textContent = `Dosya okunamadı: ${error.message}`;
    }
  };
  importArea.append(file, importButton, preview); card.append(importArea);
  const result = el("div", "library-result"); card.append(result);
  const libraryToolbar = el("div", "library-toolbar");
  const search = document.createElement("input"); search.type = "search"; search.placeholder = "Yayın ID veya URL ara"; search.autocomplete = "off";
  const selectVisible = el("button", "btn", "Görünenleri seç");
  const clearSelection = el("button", "btn ghost", "Seçimi temizle");
  const deleteSelected = el("button", "btn danger", "Seçilileri sil (0)"); deleteSelected.disabled = true;
  libraryToolbar.append(search, selectVisible, clearSelection, deleteSelected); card.append(libraryToolbar);
  const list = el("div", "library-list"); card.append(list);
  const selectedIds = new Set();

  const filteredLibrary = () => {
    const query = search.value.trim().toLocaleLowerCase("tr-TR");
    if (!query) return state.library;
    return state.library.filter(item => `${item.id} ${item.url}`.toLocaleLowerCase("tr-TR").includes(query));
  };

  const updateSelection = () => {
    deleteSelected.textContent = `Seçilileri sil (${selectedIds.size})`;
    deleteSelected.disabled = selectedIds.size === 0;
    clearSelection.disabled = selectedIds.size === 0;
  };

  const renderRows = () => {
    list.innerHTML = "";
    const visible = filteredLibrary();
    const heading = el("div", "section-title");
    heading.append(el("h3", "", `Kayıtlı yayınlar (${visible.length}/${state.library.length})`));
    list.append(heading);
    selectVisible.disabled = visible.length === 0;
    if (!visible.length) {
      list.append(el("div", "empty compact", state.library.length ? "Aramayla eşleşen yayın yok." : "Kütüphane henüz boş."));
      updateSelection();
      return;
    }
    visible.forEach(item => {
      const row = el("div", "library-row");
      const selected = document.createElement("input"); selected.type = "checkbox"; selected.checked = selectedIds.has(item.id); selected.title = "Toplu işlem için seç";
      selected.onchange = () => { selected.checked ? selectedIds.add(item.id) : selectedIds.delete(item.id); updateSelection(); };
      const info = el("div", "library-info"); info.append(el("strong", "", item.id), el("span", "", item.url));
      const duration = badge(item.seconds === 0 ? "Süresiz" : `${item.seconds} sn`, "info");
      const remove = el("button", "btn ghost remove", "×"); remove.title = "Kütüphaneden kaldır";
      remove.onclick = async () => {
        if (!confirm(`${item.id} kütüphaneden kaldırılsın mı? Cihaz playlist'leri etkilenmez.`)) return;
        await api(`/api/v1/stream-library/${encodeURIComponent(item.id)}`, { method: "DELETE" });
        selectedIds.delete(item.id);
        await renderList();
      };
      row.append(selected, info, duration, remove); list.append(row);
    });
    updateSelection();
  };

  const renderList = async () => {
    state.library = await api("/api/v1/stream-library");
    const validIds = new Set(state.library.map(item => item.id));
    [...selectedIds].forEach(id => { if (!validIds.has(id)) selectedIds.delete(id); });
    renderRows();
  };
  search.oninput = renderRows;
  selectVisible.onclick = () => { filteredLibrary().forEach(item => selectedIds.add(item.id)); renderRows(); };
  clearSelection.onclick = () => { selectedIds.clear(); renderRows(); };
  deleteSelected.onclick = async () => {
    const ids = [...selectedIds];
    if (!ids.length || !confirm(`${ids.length} yayın kütüphaneden silinsin mi? Cihaz playlist'leri etkilenmez.`)) return;
    deleteSelected.disabled = true;
    try {
      const response = await api("/api/v1/stream-library/bulk-delete", { method: "POST", body: JSON.stringify({ ids }) });
      selectedIds.clear();
      result.innerHTML = "";
      result.append(badge(`${response.deleted.length} yayın silindi`, "ok"));
      if (response.missing.length) result.append(document.createTextNode(" "), badge(`${response.missing.length} bulunamadı`, "warn"));
      await renderList();
    } catch (error) { result.innerHTML = ""; result.append(el("div", "error", error.message)); updateSelection(); }
  };
  importButton.onclick = async () => {
    importButton.disabled = true; result.innerHTML = "";
    try {
      const response = await api("/api/v1/stream-library/import", { method: "POST", body: JSON.stringify({ items: pending }) });
      result.append(badge(`${response.imported.length} aktarıldı`, "ok"));
      if (response.errors.length) {
        result.append(document.createTextNode(" "), badge(`${response.errors.length} hatalı`, "bad"));
        response.errors.forEach(item => result.append(el("div", "error", `Satır ${item.index + 1}${item.id ? ` (${item.id})` : ""}: ${item.message}`)));
      }
      await renderList();
    } catch (error) { result.append(el("div", "error", error.message)); }
    finally { importButton.disabled = false; }
  };
  backdrop.onclick = event => { if (event.target === backdrop) backdrop.remove(); };
  backdrop.append(card); document.body.append(backdrop);
  try { await renderList(); } catch (error) { result.append(el("div", "error", `Kütüphane alınamadı: ${error.message}`)); }
}

async function openLibraryPicker(playlist) {
  let items;
  try { items = await api("/api/v1/stream-library"); }
  catch (error) { toast(`Kütüphane alınamadı: ${error.message}`); return; }
  const existingIds = new Set([...playlist.querySelectorAll(".stream-id")].map(input => input.value.trim()));
  const existingUrls = new Set([...playlist.querySelectorAll(".stream-url")].map(input => input.value.trim()));
  const backdrop = el("div", "library-backdrop picker");
  const card = el("section", "library-card picker-card");
  const head = el("div", "drawer-head");
  const title = el("div"); title.append(el("div", "eyebrow", "Playlist planlama"), el("h2", "", "Kütüphaneden yayın ekle"));
  const close = el("button", "btn ghost", "Kapat"); close.onclick = () => backdrop.remove(); head.append(title, close); card.append(head);
  card.append(el("div", "notice", "Seçilen yayınlar bu cihazın formuna pasif eklenir. Oynatmak istediklerinizi etkinleştirip Kaydet ve gönder düğmesine basın."));
  const choices = el("div", "library-choices");
  items.forEach(item => {
    const disabled = existingIds.has(item.id) || existingUrls.has(item.url);
    const label = el("label", `library-choice${disabled ? " disabled" : ""}`);
    const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.disabled = disabled; checkbox.dataset.id = item.id;
    const info = el("span", "library-info"); info.append(el("strong", "", item.id), el("span", "", disabled ? `${item.url} · zaten listede` : item.url));
    label.append(checkbox, info); choices.append(label);
  });
  if (!items.length) choices.append(el("div", "empty compact", "Kütüphane boş."));
  const addSelected = el("button", "btn primary", "Seçilileri pasif ekle");
  addSelected.onclick = () => {
    const selected = [...choices.querySelectorAll("input:checked")].map(input => items.find(item => item.id === input.dataset.id));
    if (playlist.children.length + selected.length > MAX_PLAYLIST_STREAMS) { toast(`Cihaz listesi ${MAX_PLAYLIST_STREAMS} yayın sınırını aşamaz`); return; }
    selected.forEach(item => playlist.append(streamRow({ id: item.id, url: item.url, seconds: item.seconds, enabled: false })));
    backdrop.remove(); toast(`${selected.length} yayın forma pasif eklendi`);
  };
  card.append(choices, addSelected); backdrop.append(card); document.body.append(backdrop);
}

async function openHubMigration() {
  const backdrop = el("div", "drawer-backdrop");
  const card = el("section", "account-card hub-migration-card");
  const head = el("div", "drawer-head");
  const title = el("div");
  title.append(el("div", "eyebrow", "Filo bağlantısı"), el("h2", "", "Hub adresini değiştir"));
  const close = el("button", "btn ghost", "Kapat");
  let pollTimer = null;
  const dismiss = () => { clearInterval(pollTimer); backdrop.remove(); };
  close.onclick = dismiss; head.append(title, close); card.append(head);
  card.append(el("div", "notice", "Odroidlerin erişebildiği LAN adresini yazın. Her cihaz önce yeni Hub'ı test eder; başarılı olursa adresi kalıcı kaydeder. Player yeniden başlamaz."));
  const field = el("div", "field"); field.append(el("label", "", "Yeni Hub adresi"));
  const input = document.createElement("input"); input.placeholder = "http://192.168.100.200:8788"; input.autocomplete = "off"; input.spellcheck = false; field.append(input); card.append(field);
  const send = el("button", "btn primary", "Test et ve tüm cihazlara gönder"); send.style.marginTop = "18px"; send.style.width = "100%";
  const error = el("div", "error"); error.hidden = true;
  const results = el("div", "migration-results");
  card.append(send, error, results);
  send.onclick = async () => {
    const hubUrl = input.value.trim().replace(/\/$/, "");
    if (!confirm(`${hubUrl} adresi tüm onaylı Odroidlere gönderilsin mi?`)) return;
    send.disabled = true; error.hidden = true; results.innerHTML = "";
    try {
      const queued = await api("/api/v1/fleet/hub-url", { method: "POST", body: JSON.stringify({ hub_url: hubUrl }) });
      const tracked = new Map(queued.map(item => [item.device_id, item.command_id]));
      const renderStatus = async () => {
        const rows = await Promise.all([...tracked].map(async ([deviceId, commandId]) => {
          const commands = await api(`/api/v1/devices/${encodeURIComponent(deviceId)}/commands`);
          return commands.find(item => item.command_id === commandId);
        }));
        results.innerHTML = "";
        rows.forEach(item => {
          const device = state.devices.find(entry => entry.device_id === item.device_id);
          const row = el("div", "migration-result");
          const kind = item.status === "completed" ? "ok" : item.status === "failed" ? "bad" : "info";
          row.append(el("span", "", device ? deviceName(device) : item.device_id), badge(item.status, kind));
          if (item.result_message) row.append(el("small", "", item.result_message));
          results.append(row);
        });
        if (rows.every(item => ["completed", "failed"].includes(item.status))) clearInterval(pollTimer);
      };
      await renderStatus(); pollTimer = setInterval(() => renderStatus().catch(() => {}), 3000);
      toast(`${queued.length} cihaza Hub adresi komutu gönderildi`);
    } catch (e) { error.textContent = e.message; error.hidden = false; send.disabled = false; }
  };
  backdrop.onclick = event => { if (event.target === backdrop) dismiss(); };
  backdrop.append(card); document.body.append(backdrop); input.focus();
}

async function openAccount() {
  let profile;
  try { profile = await api("/api/v1/admin/profile"); }
  catch (e) { toast(`Hesap bilgisi alınamadı: ${e.message}`); return; }
  const backdrop = el("div", "drawer-backdrop");
  const card = el("section", "account-card");
  const head = el("div", "drawer-head");
  const title = el("div"); title.append(el("div", "eyebrow", "Yönetici hesabı"), el("h2", "", "Giriş bilgilerini değiştir"));
  const close = el("button", "btn ghost", "Kapat"); close.onclick = () => backdrop.remove(); head.append(title, close); card.append(head);
  const usernameField = el("div", "field"); usernameField.append(el("label", "", "Kullanıcı adı"));
  const username = document.createElement("input"); username.value = profile.username; username.autocomplete = "username"; usernameField.append(username);
  const currentField = el("div", "field"); currentField.append(el("label", "", "Mevcut parola"));
  const current = document.createElement("input"); current.type = "password"; current.autocomplete = "current-password"; currentField.append(current);
  const passwordField = el("div", "field"); passwordField.append(el("label", "", "Yeni parola (en az 8 karakter)"));
  const password = document.createElement("input"); password.type = "password"; password.autocomplete = "new-password"; passwordField.append(password);
  const repeatField = el("div", "field"); repeatField.append(el("label", "", "Yeni parola tekrar"));
  const repeat = document.createElement("input"); repeat.type = "password"; repeat.autocomplete = "new-password"; repeatField.append(repeat);
  const error = el("div", "error"); error.hidden = true;
  const save = el("button", "btn primary", "Bilgileri değiştir"); save.style.marginTop = "18px"; save.style.width = "100%";
  save.onclick = async () => {
    error.hidden = true;
    if (password.value !== repeat.value) { error.textContent = "Yeni parolalar eşleşmiyor."; error.hidden = false; return; }
    save.disabled = true;
    try {
      await api("/api/v1/admin/credentials", { method: "PUT", body: JSON.stringify({ current_password: current.value, username: username.value.trim(), new_password: password.value }) });
      backdrop.remove(); renderLogin(); toast("Bilgiler değiştirildi. Yeni bilgilerinizle giriş yapın.");
    } catch (e) { error.textContent = e.message; error.hidden = false; save.disabled = false; }
  };
  card.append(usernameField, currentField, passwordField, repeatField, save, error);
  backdrop.onclick = event => { if (event.target === backdrop) backdrop.remove(); };
  backdrop.append(card); document.body.append(backdrop); current.focus();
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
    const name = el("td"); name.append(el("div", "device-name", deviceName(device)), el("div", "device-id", `${device.hostname} · ${device.device_id}`));
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
  const url = document.createElement("input"); url.value = stream.url; url.placeholder = "http(s), rtmp(s), rtsp(s), udp veya rtp://239.x.x.x:port"; url.className = "stream-url"; url.autocomplete = "off"; url.spellcheck = false;
  const remove = el("button", "btn ghost remove", "×"); remove.title = "Yayını kaldır"; remove.onclick = () => row.remove();
  row.append(enabled, id, seconds, url, streamHealthView(stream, health), remove); return row;
}

function renderDrawer() {
  document.querySelector(".drawer-backdrop")?.remove();
  const device = state.selected, config = state.config, streamHealth = state.streamHealth;
  const backdrop = el("div", "drawer-backdrop");
  const drawer = el("aside", "drawer");
  const head = el("div", "drawer-head");
  const title = el("div"); title.append(el("div", "eyebrow", `${device.hostname} · ${device.device_id}`), el("h2", "", deviceName(device)), device.online ? badge("Online", "ok") : badge("Offline", "bad"));
  const close = el("button", "btn ghost", "Kapat"); close.onclick = () => backdrop.remove(); head.append(title, close); drawer.append(head);
  const nameSection = el("section", "device-name-editor");
  const nameField = el("div", "field"); nameField.append(el("label", "", "Hub üzerindeki cihaz adı"));
  const nameInput = document.createElement("input"); nameInput.value = device.display_name || ""; nameInput.maxLength = 80; nameInput.placeholder = device.hostname; nameField.append(nameInput);
  const nameSave = el("button", "btn primary", "Adı kaydet");
  nameSave.onclick = async () => {
    nameSave.disabled = true;
    try {
      await api(`/api/v1/devices/${encodeURIComponent(device.device_id)}/name`, { method: "PUT", body: JSON.stringify({ display_name: nameInput.value.trim() || null }) });
      toast("Cihaz adı kaydedildi"); await loadDevices(); await openDevice(device.device_id);
    } catch (e) { toast(`Cihaz adı kaydedilemedi: ${e.message}`); nameSave.disabled = false; }
  };
  nameInput.addEventListener("keydown", event => { if (event.key === "Enter") nameSave.click(); });
  nameSection.append(nameField, nameSave); drawer.append(nameSection);
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
  const actions = el("div", "actions"); const add = el("button", "btn", "+ Yayın"); const addLibrary = el("button", "btn", "+ Kütüphaneden"); const send = el("button", "btn primary", "Kaydet ve gönder");
  actions.append(add, addLibrary, send); sectionTitle.append(actions); playlistSection.append(sectionTitle);
  const healthById = new Map(streamHealth.map(item => [item.id, item]));
  const playlist = el("div", "playlist"); (config.streams || []).forEach(item => playlist.append(streamRow(item, healthById.get(item.id)))); if (!config.streams?.length) playlist.append(streamRow());
  add.onclick = () => {
    if (playlist.children.length >= MAX_PLAYLIST_STREAMS) {
      toast(`Bir oynatma listesi en fazla ${MAX_PLAYLIST_STREAMS} yayın içerebilir`);
      return;
    }
    playlist.append(streamRow());
  };
  addLibrary.onclick = () => openLibraryPicker(playlist);
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
  reboot.onclick = async () => { if (confirm(`${deviceName(device)} yeniden başlatılsın mı?`)) await queueCommand(device.device_id, "reboot", "Reboot kuyruğa alındı"); };
  commandActions.append(restart, reboot); commands.append(commandActions); drawer.append(commands);
  backdrop.onclick = event => { if (event.target === backdrop) backdrop.remove(); };
  backdrop.append(drawer); document.body.append(backdrop);
}

async function queueCommand(deviceId, command, message) {
  await api(`/api/v1/devices/${encodeURIComponent(deviceId)}/commands`, { method: "POST", body: JSON.stringify({ command }) });
  toast(message);
}

loadDevices();
