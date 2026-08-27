const state = { token: "", status: null, backups: [], activeJob: null, pollTimer: null };
const $ = (selector) => document.querySelector(selector);

function formatBytes(value) {
  if (!Number.isFinite(value)) return "—";
  const units = ["B", "KiB", "MiB", "GiB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  return `${size.toFixed(unit ? 1 : 0)} ${units[unit]}`;
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  window.setTimeout(() => node.classList.remove("show"), 3200);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}), "X-Mowbi-Token": state.token };
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) logout();
  if (!response.ok) {
    let detail = `Błąd ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* response is not JSON */ }
    throw new Error(detail);
  }
  return response;
}

function storeToken(token, remember) {
  sessionStorage.setItem("mowbiToken", token);
  if (remember) localStorage.setItem("mowbiToken", token);
  state.token = token;
}

function logout() {
  sessionStorage.removeItem("mowbiToken");
  localStorage.removeItem("mowbiToken");
  state.token = "";
  $("#appShell").classList.add("hidden");
  $("#loginScreen").classList.remove("hidden");
}

async function login(token, remember = false) {
  const response = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (!response.ok) throw new Error("Nieprawidłowy klucz dostępu");
  storeToken(token, remember);
  $("#loginScreen").classList.add("hidden");
  $("#appShell").classList.remove("hidden");
  await refreshAll();
}

function renderStatus(status) {
  state.status = status;
  const probe = status.probe;
  $("#probeLabel").textContent = probe.connected ? "CMSIS-DAP online" : "Sonda offline";
  $("#probeDetail").textContent = probe.connected ? `${probe.uid} · ${probe.vendor_id}:${probe.product_id}` : probe.detail;
  $("#probeSignal").classList.toggle("online", probe.connected);
  $("#checkProbe").textContent = probe.connected ? "✓" : "○";
  $("#checkProbe").classList.toggle("ok", probe.connected);
  $("#checkProbeText").textContent = probe.connected ? "Sonda gotowa" : "Podłącz sondę";

  const profile = status.profile;
  $("#profileLabel").textContent = profile.profile_confirmed ? profile.chip_marking : "Niepotwierdzony";
  $("#profileDetail").textContent = `${profile.device_label} · ${profile.repeat_reads} odczyty`;
  $("#checkProfile").textContent = profile.profile_confirmed ? "✓" : "○";
  $("#checkProfile").classList.toggle("ok", profile.profile_confirmed);
  $("#checkProfileText").textContent = profile.profile_confirmed ? "Oznaczenie zapisane" : "Wymaga oznaczenia MCU";
  $("#profileWarning").classList.toggle("hidden", profile.profile_confirmed);
  $("#profileButton").textContent = profile.profile_confirmed ? "Zobacz" : "Ustaw";

  $("#backupCount").textContent = `${status.backup.count} ${status.backup.count === 1 ? "backup" : "backupów"}`;
  $("#storageDetail").textContent = `${formatBytes(status.storage.free)} wolne`;
  $("#checkStorage").textContent = status.storage.free > 20 * 1024 * 1024 ? "✓" : "!";
  $("#checkStorage").classList.toggle("ok", status.storage.free > 20 * 1024 * 1024);
  $("#checkStorageText").textContent = `${formatBytes(status.storage.free)} dostępne`;
  updateBackupButton();
}

function consensusHash(item) {
  const region = (item.regions || []).find((entry) => entry.region_id === "internal_flash");
  return region?.consensus_sha256 || "Brak consensus";
}

function renderBackups(items) {
  state.backups = items;
  const list = $("#archiveList");
  if (!items.length) {
    list.innerHTML = '<div class="empty-state"><span>⬡</span><b>Brak zapisanych backupów</b><p>Pierwszy zgodny zestaw pojawi się tutaj.</p></div>';
    return;
  }
  list.innerHTML = items.map((item) => {
    const complete = item.complete_persistent_backup;
    const date = new Date(item.created_at).toLocaleString("pl-PL");
    return `<article class="archive-row">
      <div><b>${escapeHtml(item.device_name)}</b><small>${date} · ${escapeHtml(item.backup_id)}</small></div>
      <span class="archive-status ${complete ? "" : "partial"}">${complete ? "PEŁNY" : "CZĘŚCIOWY"}</span>
      <span class="archive-hash" title="${consensusHash(item)}">SHA-256 ${consensusHash(item)}</span>
      <div class="row-actions">
        <button data-verify="${item.backup_id}">Sprawdź</button>
        <button data-download="${item.backup_id}" ${item.download_available ? "" : "disabled"}>Pobierz ZIP</button>
      </div>
    </article>`;
  }).join("");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

async function refreshAll() {
  try {
    const [statusResponse, backupResponse] = await Promise.all([api("/api/status"), api("/api/backups")]);
    renderStatus(await statusResponse.json());
    const backups = await backupResponse.json();
    renderBackups(backups.items);
    const active = backups.jobs.find((job) => ["queued", "running"].includes(job.status));
    if (active) watchJob(active.job_id);
  } catch (error) { toast(error.message); }
}

function updateBackupButton() {
  const ready = state.status?.probe.connected && state.status?.profile.profile_confirmed && $("#readOnlyConfirm").checked && !state.activeJob;
  $("#backupButton").disabled = !ready;
}

async function startBackup(event) {
  event.preventDefault();
  $("#backupError").textContent = "";
  try {
    const response = await api("/api/backups", {
      method: "POST",
      body: JSON.stringify({
        device_name: $("#deviceName").value,
        note: $("#backupNote").value,
        confirmation: state.status.backup.confirmation_phrase,
      }),
    });
    const job = await response.json();
    watchJob(job.job_id);
  } catch (error) { $("#backupError").textContent = error.message; }
}

function renderJob(job) {
  state.activeJob = ["queued", "running"].includes(job.status) ? job.job_id : null;
  $("#jobProgress").classList.remove("hidden");
  $("#jobPhase").textContent = job.phase.toUpperCase();
  $("#jobMessage").textContent = job.message;
  $("#jobPercent").textContent = `${job.progress}%`;
  $("#jobBar").style.width = `${job.progress}%`;
  updateBackupButton();
}

function watchJob(jobId) {
  window.clearInterval(state.pollTimer);
  state.activeJob = jobId;
  const poll = async () => {
    try {
      const response = await api(`/api/jobs/${jobId}`);
      const job = await response.json();
      renderJob(job);
      if (!["queued", "running"].includes(job.status)) {
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
        state.activeJob = null;
        toast(job.status === "completed" ? "Backup zapisany i zweryfikowany" : `Backup nieudany: ${job.message}`);
        await refreshAll();
      }
    } catch (error) { toast(error.message); }
  };
  poll();
  state.pollTimer = window.setInterval(poll, 1500);
}

async function verifyBackup(backupId) {
  const response = await api(`/api/backups/${backupId}/verify`, { method: "POST" });
  const result = await response.json();
  toast(result.ok ? `Integralność potwierdzona (${result.files_checked} pliki)` : `Błąd integralności: ${result.failures.join(", ")}`);
}

async function downloadBackup(backupId) {
  const response = await api(`/api/backups/${backupId}/download`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${backupId}.zip`;
  link.click();
  URL.revokeObjectURL(url);
}

async function confirmProfile(event) {
  event.preventDefault();
  if (!$("#profileConfirm").checked) {
    $("#profileError").textContent = "Potwierdź, że oznaczenie pochodzi z tej płyty.";
    return;
  }
  try {
    const response = await api("/api/profile/confirm", {
      method: "POST",
      body: JSON.stringify({
        chip_marking: $("#chipMarking").value,
        flash_length: Number($("#flashLength").value),
        confirmation: "POTWIERDZAM OZNACZENIE MCU",
      }),
    });
    await response.json();
    $("#profileDialog").close();
    toast("Profil MCU został potwierdzony");
    await refreshAll();
  } catch (error) { $("#profileError").textContent = error.message; }
}

$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#loginError").textContent = "";
  try { await login($("#accessToken").value, $("#rememberToken").checked); }
  catch (error) { $("#loginError").textContent = error.message; }
});
$("#logoutButton").addEventListener("click", logout);
$("#refreshButton").addEventListener("click", refreshAll);
$("#readOnlyConfirm").addEventListener("change", updateBackupButton);
$("#backupForm").addEventListener("submit", startBackup);
$("#profileButton").addEventListener("click", () => {
  $("#chipMarking").value = state.status?.profile.profile_confirmed ? state.status.profile.chip_marking : "";
  $("#profileDialog").showModal();
});
$("#profileForm").addEventListener("submit", confirmProfile);
$("#archiveList").addEventListener("click", async (event) => {
  const verify = event.target.closest("[data-verify]");
  const download = event.target.closest("[data-download]");
  try {
    if (verify) await verifyBackup(verify.dataset.verify);
    if (download) await downloadBackup(download.dataset.download);
  } catch (error) { toast(error.message); }
});

window.setInterval(() => { $("#clock").textContent = new Date().toLocaleTimeString("pl-PL"); }, 1000);
const existingToken = sessionStorage.getItem("mowbiToken") || localStorage.getItem("mowbiToken");
if (existingToken) login(existingToken).catch(() => logout());
