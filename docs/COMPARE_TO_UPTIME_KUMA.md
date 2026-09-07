# Briefing: this project vs Uptime Kuma

Use this file to compare **this custom Python home-lab monitor** to **Uptime Kuma** (often just “Kuma”). It is a narrow LAN dashboard, not a Kuma replacement.

Public fictitious examples used here (never treat these as live hosts):

- LM Studio: `10.42.0.10:1234`
- Ollama: `10.42.0.20:11434`
- NAS: `10.42.0.30` share `\\10.42.0.30\shared`, mapped as `Z:`
- Uptime Kuma (mcp-01): `10.42.0.40:3001`
- Dashboard bind: `0.0.0.0:8000` (open locally at `http://127.0.0.1:8000`)

---

## Questions this program answers

The example UI is five cards (internet, LM Studio, Ollama, Uptime Kuma summary, NAS). Extra HTTP services can be appended under `services:` in YAML; they get a generic GET + status-code check, not the LM Studio / Ollama / Kuma summaries. The Kuma card is a dedicated `uptime_kuma:` block: structured monitor status plus an optional LM Studio paragraph.

All top-level checks (internet, each HTTP service, NAS) run **in parallel** via `asyncio.gather`. Shared HTTP client: `httpx.AsyncClient`, `timeout` from `dashboard.timeout_seconds` (example: **5s**), `follow_redirects=True`. Auto-refresh interval is `dashboard.refresh_seconds` (example: **10s**). There is also a “Check now” button and a CLI: `scripts/verify_endpoints.py` (JSON dump; exit 1 if any check is `down`).

Dashboard cards show: **name**, **state** (`up` / `degraded` / `down`), **detail** string, **elapsed_ms**, and **target** when present. The JSON API (`GET /api/status`) also includes per-probe objects; the HTML UI does not list every probe URL.

---

### 1. Can I Reach the Internet?

**Yes means:** HTTPS GET to every configured public URL succeeds with the expected status. Example config (`success_threshold: 2`):

| URL | Expected status |
| --- | --- |
| `https://www.google.com/generate_204` | **204** (any URL containing `generate_204`) |
| `https://www.cloudflare.com/cdn-cgi/trace` | **200** |
| `https://1.1.1.1/cdn-cgi/trace` | **200** |

State machine:

- **up** — successes == probe count (and also >= threshold)
- **degraded** — successes >= `success_threshold` but not all probes
- **down** — successes < threshold

Default threshold if omitted: `max(1, len(urls))` (all must succeed).

**How it is checked:** Sequential `httpx` GETs inside the internet check (not parallel among themselves). Success is status-code match only. Response JSON/text is **stripped** before the API (`_public_probe`) so Cloudflare/Google trace bodies (WAN IPs) never reach the dashboard.

**Dashboard shows:** state; detail like `2/3 public endpoints reachable`; elapsed_ms = **max** of the probe times. No `target` URL on the card.

**Does not do:** ICMP/ping, DNS-only probes, keyword/body matching, or displaying probe response bodies.

---

### 2. Can I see LM Studio?

**Yes means:** HTTP GET `{scheme}://{host}:{port}/v1/models` returns `expect_status` (example: `http://10.42.0.10:1234/v1/models` → **200**). That is “the OpenAI-compatible API answered,” not “a model completed a chat.”

**How it is checked:** One GET. If `Content-Type` is JSON, the handler reads `data[].id` for a model list.

**Dashboard shows:** `up`/`down`; detail `{n} model(s): id1, id2, …` when IDs exist, else `API reachable` on success; HTTP error/status on failure; elapsed_ms; **target** = full URL.

**Does not do:** Load a model, send a completion, check GPU/VRAM, or require an API key (not implemented in this repo).

---

### 3. Can I see the Ollama Server?

**Yes means:** HTTP GET `{scheme}://{host}:{port}/api/version` returns `expect_status` (example: `http://10.42.0.20:11434/api/version` → **200**). That is “the version API answered,” not “a generate call works.”

**How it is checked:** One GET. JSON field `version` is used when present.

**Dashboard shows:** `up`/`down`; detail `Ollama {version}` when present, else short text or `API reachable`; error/status on failure; elapsed_ms; **target** = full URL.

**Does not do:** List models (`/api/tags`), run inference, or check which model is loaded.

---

### 4. Can I see my files on my NAS?

**Yes means:** The configured mapped drive (example `Z:`) **exists** and `os.listdir` succeeds. An **empty but readable** drive still counts as **up**. Missing, permission-denied, or hung listing is **down**.

**How it is checked:**

1. **Primary (decides state):** `inspect_mapped_drive` on a worker thread (`asyncio.to_thread`) wrapped in `asyncio.wait_for` using `nas.timeout_seconds` (example **5s**, else dashboard timeout). Path is normalized to `Z:\`.
2. **Optional extra (does not decide state):** TCP connect to `nas.host` (or host parsed from `nas.share`) on `smb_port` (example **445**). Success or failure is appended to the detail string only. Tests confirm listing-up + SMB-down still yields **up**.

**Dashboard shows:**

- Up, items: `{n} item(s) visible on Z:` (plus `; SMB 445 reachable` or `not reachable` if a host is set)
- Up, empty: `Drive Z: is readable`
- Down, missing: `Mapped drive Z: is not available. Reconnect with ConnectToHomeSan.ps1 or connectDrive.bat.`
- Down, timeout: `Timed out listing Z:. The share may be hung.`
- Target: drive path (`Z:\`)

**Does not do:** `net use`, SMB authenticate, store or load NAS username/password, or remount the share. Credentials stay in the existing PowerShell SAN config, **outside this repo**. The card only tells the operator to reconnect with those scripts.

---

### 5. What is Uptime Kuma reporting?

**Yes / up means:** Kuma **monitor data** was retrieved, and no monitor tagged **Critical** is currently Down. That is not “the Kuma UI returned HTTP 200.” Low historical uptime on a monitor that is currently Up does **not** mark this card Down (short window / added after an outage).

State machine:

- **up** — structured snapshot retrieved; no Critical monitor is currently Down
- **degraded** — Kuma is reachable but the monitor list could not be read (login / no public status page / no API key), or a non-Critical monitor is Down
- **down** — cannot reach Kuma, **or** a Critical monitor is currently Down

**How it is checked:**

1. `GET /api/entry-page` (reachability; also reads a default status-page slug if Kuma advertises one).
2. `GET /api/status-page/{slug}` and `GET /api/status-page/heartbeat/{slug}` when `uptime_kuma.status_page_slug` is set (example slug: `ping-networkinfrastructure`) or entry-page provides a slug. Prefer this JSON over the HTML status page. A public slug is not an IP and is fine to mention in docs.
3. Else, only if no slug is configured, `GET /metrics` with optional `KUMA_API_KEY` from `private/secrets.env`. This lab’s Kuma install does not use Prometheus; the published status page is the ingest path.
4. Build a compact snapshot: names, up/down counts, uptime %, tags (especially Critical). Status-page JSON is the source of 24h uptime; enable **Show Tags** on the Kuma status page if Critical tags should affect this card.
5. If Kuma is reachable, `POST` that snapshot to LM Studio `/v1/chat/completions` (OpenAI-compatible, same host as the LM Studio card). Model is `uptime_kuma.lm_studio_model` if it appears in `GET /v1/models`, otherwise the first non-embedding model. Chat timeout is `summarize_timeout_seconds` (example **8s**) so a hung LLM does not stall other cards. Summaries are reused for `summary_cache_seconds` (example **90s**) while the monitor set and up/down set stay the same; counts are always from the latest snapshot.
6. If Kuma is unreachable, the LLM is **not** called.

**Dashboard shows:** aggregate like `4 up / 0 down` from structured data; the LM Studio paragraph when available; if LM Studio is down, counts/names plus “summary unavailable”; if Kuma is down, card down with no summary. Target is the Kuma base URL.

**Does not do:** Clone Kuma’s heartbeat UI, scrape Orbi admin, OCR a screenshot, read MariaDB, or invent monitors that are not in the snapshot. Vision/screenshot OCR is a worse fallback than status-page heartbeat JSON.

---

## Purpose and scope

Home-lab “can I see X?” dashboard for one Windows workstation and its LAN: WAN HTTP reachability, two local AI HTTP APIs, a structured Uptime Kuma snapshot (optionally summarized by LM Studio), and “are NAS files visible on a mapped drive?”

Not a general SaaS uptime platform and **not a Kuma replacement**. Extra YAML HTTP GETs are possible; there is no plugin/monitor marketplace.

---

## This lab also runs Uptime Kuma

The same home lab now runs **Uptime Kuma** on host **mcp-01** (public example: `10.42.0.40:3001`) with **embedded MariaDB** on that VM. MariaDB credentials are not stored in this repository.

Near-term Kuma plan: the first monitor is an **ICMP ping to the LAN gateway**. This Python app explicitly does not use ICMP for internet (or gateway) reachability; that is Kuma’s job.

Use both tools. Grow this dashboard where the question is human-facing “can I see X?” and stock Kuma HTTP/ICMP is a poor fit. Put device inventory, retries, notifications, and history in Kuma.

---

## Hybrid recommendation

Durable split for this lab. Prefer one owner per question; add the other tool only when the question itself is different.

1. **This dashboard** — operator “can I see X?” checks that stock Kuma HTTP/ICMP cannot express well: LM Studio `GET /v1/models` (model list), Ollama `GET /api/version`, NAS **mapped drive listing** on Windows (`Z:`), a **Kuma status snapshot + LM Studio summary**, future app-semantic cards (for example “are the VMs I care about running?” via a Proxmox API), and the GitHub-safe private/public IP-masking workflow.
2. **Uptime Kuma** (mcp-01, MariaDB-backed history) — source of truth for ICMP, history, retries, notifications, and many devices. Gateway ping, Orbi/router IPs, Proxmox `:8006` reachability, lots of VMs/LXCs/switches/printers (inventory + tags), uptime-percentage graphs, and alerting (email, Discord, and so on).
3. **Orbi / wireless** — Kuma first: ICMP to the LAN gateway and Orbi router/AP IPs. Optional HTTP to the admin UI is usually auth-walled and a weak uptime signal. Mesh satellites are better as ping plus “can clients reach the gateway.” Do not scrape the Orbi admin UI from this Python app unless that is asked for later. Phone-to-dashboard already depends on LAN plus firewall TCP 8000.
4. **Proxmox** — Kuma: ping the node, HTTPS to the web UI (`:8006`), maybe guest pings. This dashboard (optional later): one card “Can I see Proxmox?” via API `/version` or cluster/nodes status using a **read-only token** stored only in `private/secrets.env` — only if that yes/no belongs next to LM Studio. Do not put `root@pam` passwords in either tool’s git repo. Proxmox-native node status (and optional Influx/Prometheus) is complementary, not required. Do not implement a Proxmox API monitor until a token exists. Do not fold Proxmox into the LM Studio Kuma summary until those Kuma monitors exist.
5. **Use both** when the same box has two questions: “is the host/port up over time, and should someone be notified?” (Kuma) versus “can I do the thing I care about right now?” (this dashboard). Example: Kuma pings the NAS and graphs downtime; this app lists `Z:` because “TCP 445 open” is not “I can see files.” Kuma owns ICMP heartbeats; this app reads Kuma’s structured status and summarizes it.

### Keep / grow in this FastAPI dashboard

- LM Studio `GET /v1/models` (model IDs on the card)
- Ollama `GET /api/version`
- NAS mapped-drive listing (`Z:`), not just ping
- Structured Kuma ingest + optional LM Studio summary (“What is Uptime Kuma reporting?”)
- Future similar app-semantic checks
- Private YAML + `ip_map.yaml` sanitizer so the GitHub tree stays fictitious

### Put in Uptime Kuma

- Gateway ping (first monitor)
- Orbi router/APs: ICMP to LAN gateway / Orbi IPs (keep Orbi in Kuma ICMP; do not scrape Orbi admin)
- Proxmox host: ICMP + HTTPS `:8006`
- Large inventories: VMs, LXCs, switches, printers, tags
- Alerting and uptime-percentage graphs
- Anything that needs retries, maintenance windows, or a status page
- Kuma process reachability as a monitor on **another** node later (do not treat “:3001 answers” as the home-lab health signal)

### Proxmox — recommended split

| Question | Where |
| --- | --- |
| Is the node pingable? Is `:8006` reachable? | Kuma |
| Are guests I care about pingable? | Kuma (optional) |
| “Can I see Proxmox?” as a first-class card next to LM Studio | This dashboard, later, read-only API token in `private/secrets.env` only — candidate, not implemented |
| Node CPU/RAM/disk graphs | Proxmox UI or optional Influx/Prometheus; not required for this split |

### Netgear Orbi — recommended split

| Question | Where |
| --- | --- |
| Is the gateway / Orbi LAN IP up? | Kuma ICMP |
| Can wireless clients reach the gateway? | Kuma ping from a useful vantage, or infer from this dashboard’s internet + phone-to-`:8000` path |
| Scrape Orbi admin | Neither, unless asked later; auth-walled HTML is a weak uptime signal |

---

## Better implementation (long-term)

Keep the split. Do not grow this dashboard into a second heartbeat UI.

- **Kuma** remains source of truth for ICMP (gateway, Orbi Main, satellites) plus history and Critical tags.
- **This dashboard** should ingest Kuma’s **structured status** and optionally **summarize with LM Studio**. It should not clone Kuma’s heartbeat timeline.
- Better than scraping HTML: publish a Kuma **public status page** and poll `/api/status-page/{slug}` plus `/api/status-page/heartbeat/{slug}`. Example: `http://10.42.0.40:3001/status/ping-networkinfrastructure` (slug `ping-networkinfrastructure`). A screenshot / vision OCR pipeline is a worse alternative. Prometheus `/metrics` is an optional fallback only when no slug is configured.
- Better than calling an LLM every refresh: keep raw counts always fresh; cache the summary (60–120s) and only re-summarize when the monitor set or up/down set changes. (This repo already skips a new chat when the fingerprint is unchanged inside `summary_cache_seconds`.)
- Better than “is :3001 up”: alert on **Critical tag Down**, not on Kuma process reachability. Kuma reachability can stay as a Kuma monitor on another node later.
- Interpret short-window uptime carefully. A currently Up monitor with low percentage (for example Orbi Main at 14%) is often a short history or a monitor added after an outage, not “the Orbi is 86% broken.”
- Do not scrape Orbi admin; keep Orbi in Kuma ICMP.
- Proxmox still belongs in Kuma first (ping + `:8006`), not in this LLM summary until those monitors exist.

---

## Runtime

| Item | This repo |
| --- | --- |
| Language | Python 3 |
| Web | FastAPI + Uvicorn (`run.py` → `monitor.main:app`) |
| HTTP client | httpx |
| Config | PyYAML |
| Install | Windows-first venv: `python -m venv .venv`, `pip install -r requirements.txt` |
| Bind | `dashboard.host` / `dashboard.port` (defaults **`0.0.0.0:8000`**) |
| Auth | **No login.** LAN clients use `http://<this-host>:8000`. README notes a Windows inbound TCP 8000 rule on the Private profile if phones cannot connect. |
| UI | Static `index.html` + `app.js`; `GET /` and `GET /api/status` |
| Persistence | None. Each refresh re-runs live probes. |
| Containers | No Dockerfile or compose file in this repo |

`.env.example` reserves `DASHBOARD_USER` / `DASHBOARD_PASSWORD` “for future” service tokens or dashboard credentials. Those are **not implemented** in application code.

---

## Configuration model

| Location | Role | Git |
| --- | --- | --- |
| `private/services.yaml` | Live hosts, ports, NAS drive, dashboard bind | gitignored |
| `private/ip_map.yaml` | Real → fictitious rewrite table | gitignored |
| `private/obfuscate.yaml` | Screenshot extras: share names, hostnames, usernames | gitignored |
| `private/secrets.env` | Reserved; NAS creds must **not** live here | gitignored |
| `public/services.example.yaml` | Fictitious copy for GitHub | committed |
| `public/ip_map.example.yaml` | Example map shape (`192.168.1.x` → `10.42.0.x`) | committed |
| `public/obfuscate.example.yaml` | Example screenshot extras (fake names only) | committed |

If `private/services.yaml` is missing, the app falls back to the public example map. The UI says “Using private service map” vs “Using public example map.”

After editing private files: `python scripts/generate_public_examples.py` rewrites hosts using the IP map and **refuses to write `public/`** if a mapped real value is still present.

---

## Privacy design (why this exists vs a GitHub-visible Kuma config)

Kuma typically stores monitor URLs (LAN IPs, share paths, hostnames) in its own data directory, compose volume, or embedded MariaDB (mcp-01 in this lab). If that config or a Kuma backup is copied into a public git repo, real home-lab addresses leak. Keep Kuma’s database on mcp-01; do not commit exports.

This project splits:

- **private/** — live map, secrets, home-lab notes (never commit)
- **public/** + **docs/** — fictitious examples and how-it-works docs
- Internet probe **bodies omitted** so WAN IPs from `/cdn-cgi/trace` do not appear on the dashboard
- NAS passwords stay in the existing PowerShell SAN scripts, not in YAML
- **Obfuscate** screenshot mode (`/api/status?obfuscate=1`) rewrites LAN IPs to `192.x.y.z` (not `10.42.0.x`), plus UNC shares, inventory hostnames, usernames, and Kuma `(a.b)` name hints, including LM Studio summary text

That workflow is the main “GitHub-safe” difference, not feature parity with Kuma.

---

## Kuma-like features this app does not have

Confirmed absent from this repo (code + docs):

- Public internet status pages (status.example.com style)
- Login, users, roles, 2FA
- Alerting: Telegram, Discord, Slack, email, webhooks, or any notifier
- Historical uptime %, incident log, heartbeat charts, or a database
- Docker / one-click compose
- Probe types beyond HTTP GET (status code), NAS listdir + optional TCP, and the dedicated Kuma ingest: no ICMP, DNS, keyword, POST body, push/heartbeat, Docker container, SQL, or TLS-expiry monitors from this app itself
- Maintenance windows, tags, groups, or monitor dependencies
- Reverse-proxy / SSO / HTTPS termination in-app

If something is not listed above, treat it as **not implemented in this repo**.

---

## What this app does that a stock Kuma HTTP monitor might not

- **NAS success = Windows mapped-drive listing**, not “TCP 445 open” or “HTTP on the NAS UI.” Empty readable `Z:` is up. Hung listing times out in a worker thread so other checks keep running.
- **LM Studio card lists model IDs** from `/v1/models`. The Kuma card can also **ask LM Studio to summarize** a Kuma snapshot (`POST /v1/chat/completions`).
- **Ollama card shows `/api/version`.**
- **Internet majority + degraded** plus **body-stripped** probes (Kuma HTTP can do multi-URL only as separate monitors; it would typically store/show response extras unless you hide them).
- **Private YAML + IP-map sanitizer** so the GitHub tree can stay fictitious.
- **Obfuscate screenshot toggle** so a live dashboard capture does not leak RFC1918 addresses, UNC share names, or inventory hostnames. Server-side; banner while ON.
- **Kuma snapshot card** shows live up/down counts from status-page heartbeat JSON, not “UI returned 200.”

---

## Suggested comparison dimensions

1. **Setup cost** — Kuma: often Docker + UI wizard. This: Python venv, copy YAML, already-mapped `Z:`.
2. **Probe fidelity** — Kuma: many monitor types. This: four opinionated checks (HTTP 204/200 majority; `/v1/models`; `/api/version`; `listdir` on a drive) plus structured Kuma ingest + LM Studio summary. Extra YAML HTTP GETs are still possible.
3. **Alerting** — Kuma: many channels. This: look at the page (or CLI exit code). No notifiers.
4. **History** — Kuma: graphs and retention. This: last snapshot only.
5. **Multi-device access** — both can be LAN-visible. This binds `0.0.0.0:8000` with **no auth**; Kuma has accounts and optional public pages.
6. **Secrets handling** — Kuma: credentials inside its store. This: no NAS password in-repo; reconnect scripts stay outside; public tree is sanitized.
7. **Windows NAS** — this treats “I can see files on `Z:`” as the question. Stock Kuma has no first-class mapped-drive listing monitor.
8. **GitHub safety** — this repo is built so live IPs never need to be committed. A default Kuma export/backup often contains real targets unless you sanitize it yourself.

---

## API snapshot (for implementers)

`GET /api/status` returns `{ checks, checked_at, refresh_seconds, using_private_config, obfuscated }`. Pass `?obfuscate=1` or header `X-Obfuscate: 1` to sanitize the payload for screenshots (`192.168.a.b` → `192.x.y.b`, plus shares / hostnames / usernames / Kuma LAN hints / summary text). Default is off. Each check: `id`, `name`, `state`, `ok` (`state != "down"`), `elapsed_ms`, `detail`, optional `target`, `probes`. The Kuma check also includes `summary`, `monitors`, `counts`, and `source`.

`degraded` is produced by the internet check and by the Kuma check. `ok` is still true when degraded.
