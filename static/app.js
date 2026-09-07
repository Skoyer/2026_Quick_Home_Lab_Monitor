const cards = document.getElementById("cards");
const checkedAt = document.getElementById("checked-at");
const configSource = document.getElementById("config-source");
const refreshButton = document.getElementById("refresh");
const obfuscateButton = document.getElementById("obfuscate");
const obfuscateBanner = document.getElementById("obfuscate-banner");

const STORAGE_KEY = "home-lab-monitor-obfuscate";
const RAW_LAN = /(?:^|[^\dx])(?:192\.168\.|10\.(?!x\.y\.)|172\.(?:1[6-9]|2\d|3[01])\.)/i;
const RAW_UNC_SHARE = /\\\\[^\\\s]+\\(?!share\b)[^\\\s]+/i;

let refreshTimer = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function obfuscateEnabled() {
  return window.localStorage.getItem(STORAGE_KEY) === "1";
}

function setObfuscateEnabled(on) {
  window.localStorage.setItem(STORAGE_KEY, on ? "1" : "0");
  document.body.classList.toggle("obfuscate-on", on);
  obfuscateButton.setAttribute("aria-pressed", on ? "true" : "false");
  obfuscateButton.textContent = on ? "Obfuscate: ON" : "Obfuscate";
  obfuscateBanner.hidden = !on;
}

function safeTarget(target, obfuscated) {
  if (!target) {
    return "";
  }
  if (obfuscated && (RAW_LAN.test(target) || RAW_UNC_SHARE.test(target))) {
    return "";
  }
  return `<p class="target">${escapeHtml(target)}</p>`;
}

function render(payload) {
  const obfuscated = Boolean(payload.obfuscated) || obfuscateEnabled();
  const when = payload.checked_at ? new Date(payload.checked_at) : new Date();
  checkedAt.textContent = `Last check: ${when.toLocaleTimeString()}`;
  configSource.textContent = payload.using_private_config
    ? "Using private service map"
    : "Using public example map";
  if (obfuscated) {
    obfuscateBanner.hidden = false;
    document.body.classList.add("obfuscate-on");
  }

  cards.innerHTML = "";
  for (const check of payload.checks || []) {
    const card = document.createElement("article");
    const wide = check.summary ? " wide" : "";
    card.className = `card ${check.state || "unknown"}${wide}`;
    const target = safeTarget(check.target, obfuscated);
    const summary = check.summary
      ? `<p class="summary">${escapeHtml(check.summary)}</p>`
      : "";
    card.innerHTML = `
      <header>
        <h2>${escapeHtml(check.name)}</h2>
        <span class="light" aria-hidden="true"></span>
      </header>
      <p class="state">${escapeHtml(check.state)}</p>
      <p class="detail">${escapeHtml(check.detail || "")}</p>
      ${summary}
      <p class="timing">${escapeHtml(check.elapsed_ms ?? "—")} ms</p>
      ${target}
    `;
    cards.appendChild(card);
  }
}

async function loadStatus() {
  refreshButton.disabled = true;
  try {
    const query = obfuscateEnabled() ? "?obfuscate=1" : "";
    const response = await fetch(`/api/status${query}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    render(payload);
    const seconds = Number(payload.refresh_seconds || 10);
    if (refreshTimer) {
      clearInterval(refreshTimer);
    }
    refreshTimer = setInterval(loadStatus, seconds * 1000);
  } catch (error) {
    checkedAt.textContent = `Check failed: ${error.message}`;
  } finally {
    refreshButton.disabled = false;
  }
}

obfuscateButton.addEventListener("click", () => {
  setObfuscateEnabled(!obfuscateEnabled());
  loadStatus();
});
refreshButton.addEventListener("click", loadStatus);
setObfuscateEnabled(obfuscateEnabled());
loadStatus();
