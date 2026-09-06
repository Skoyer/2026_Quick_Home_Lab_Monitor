const cards = document.getElementById("cards");
const checkedAt = document.getElementById("checked-at");
const configSource = document.getElementById("config-source");
const refreshButton = document.getElementById("refresh");

let refreshTimer = null;

function render(payload) {
  const when = payload.checked_at ? new Date(payload.checked_at) : new Date();
  checkedAt.textContent = `Last check: ${when.toLocaleTimeString()}`;
  configSource.textContent = payload.using_private_config
    ? "Using private service map"
    : "Using public example map";

  cards.innerHTML = "";
  for (const check of payload.checks || []) {
    const card = document.createElement("article");
    card.className = `card ${check.state || "unknown"}`;
    const target = check.target
      ? `<p class="target">${check.target}</p>`
      : "";
    card.innerHTML = `
      <header>
        <h2>${check.name}</h2>
        <span class="light" aria-hidden="true"></span>
      </header>
      <p class="state">${check.state}</p>
      <p class="detail">${check.detail || ""}</p>
      <p class="timing">${check.elapsed_ms ?? "—"} ms</p>
      ${target}
    `;
    cards.appendChild(card);
  }
}

async function loadStatus() {
  refreshButton.disabled = true;
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
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

refreshButton.addEventListener("click", loadStatus);
loadStatus();
