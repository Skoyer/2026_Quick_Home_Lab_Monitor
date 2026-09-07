# Monitors

The dashboard binds using `dashboard.host` and `dashboard.port` in
`private/services.yaml` (defaults: `0.0.0.0` on port `8000`) so LAN
clients can open the UI. There is no login.

The dashboard runs four opinionated reachability checks plus a Kuma
status summary. Extra HTTP services can still be listed under
`services:` in `private/services.yaml`. The NAS check is a separate
`nas:` block; Uptime Kuma is a separate `uptime_kuma:` block.

## Can I Reach the Internet

Sends HTTPS GET requests to a short list of public endpoints. A check is
**up** when every probe succeeds, **degraded** when the configured
majority succeed, and **down** otherwise.

Current probes:

- `https://www.google.com/generate_204` (HTTP 204)
- `https://www.cloudflare.com/cdn-cgi/trace` (HTTP 200)
- `https://1.1.1.1/cdn-cgi/trace` (HTTP 200)

Response bodies are not shown in the UI so WAN addresses from trace
endpoints do not appear on the dashboard.

## Can I see LM Studio

HTTP GET to the OpenAI-compatible models endpoint:

`{scheme}://{host}:{port}/v1/models`

Success is HTTP 200. The card can show the model IDs returned by the
local API.

## Can I see the Ollama Server

HTTP GET to:

`{scheme}://{host}:{port}/api/version`

Success is HTTP 200. The card shows the reported Ollama version when
present.

## What is Uptime Kuma reporting?

Ingests **structured** Kuma monitor status and optionally summarizes it
with LM Studio. This is not “can I open the Kuma UI?”.

Data path, in order:

1. `GET /api/entry-page` to see if Kuma is reachable and whether a public
   status page is the site entry.
2. `GET /api/status-page/{slug}` plus `/api/status-page/heartbeat/{slug}`
   when `uptime_kuma.status_page_slug` is set (example:
   `network`) or advertised. Prefer heartbeat JSON over
   the HTML page at `/status/{slug}`. The slug is not an IP and is safe
   to document. Example public URL:
   `http://10.42.0.40:3001/status/network`.
3. `GET /metrics` only if **no** slug is configured. This lab does not use
   Prometheus; `KUMA_API_KEY` in `private/secrets.env` is unused when the
   status page answers.
4. Compact snapshot (names, up/down counts, uptime %, tags) sent to
   LM Studio `POST /v1/chat/completions`. Model name comes from
   `uptime_kuma.lm_studio_model` if that id is loaded, otherwise the first
   non-embedding model from `GET /v1/models` (example:
   `llama-3.2-8b-instruct`).

**Card is up** when Kuma data was retrieved and no monitor tagged
**Critical** is currently Down. A monitor that is Up with a low
historical uptime percentage does **not** mark the card Down (short
history / added after an outage). Unreachable Kuma is Down and skips
the LLM. Reachable Kuma with no monitor payload is degraded and shows
the login/status-page hint. If LM Studio is down, the card still shows
structured counts/names.

ICMP, history, retries, and notifications stay in Kuma (kuma-host in the
example map). See [COMPARE_TO_UPTIME_KUMA.md](COMPARE_TO_UPTIME_KUMA.md)
for the split and a better long-term implementation.

## Screenshot Obfuscate mode

For screenshots, click **Obfuscate** on the dashboard (or call
`GET /api/status?obfuscate=1` / header `X-Obfuscate: 1`). The toggle
persists in `localStorage`. A banner stays visible while ON.

Sanitizing is server-side so the HTML reflects the masked JSON, not a
CSS blur. Probe URLs that still contain a private IPv4 are not rendered.

What is masked:

- Private IPv4: `192.168.a.b` → `192.x.y.b` (last octet kept). Other RFC1918
  (`10.*`, `172.16–31.*`) become `10.x.y.<last>` / `172.x.y.<last>`.
- Parenthesized LAN hints in Kuma names, e.g. `Orbi Main (200.14)` →
  `Orbi Main (x.y.14)` (scheme: hide the third octet, keep the host’s last octet).
- UNC/SMB share names (`\\192.x.y.250\share`). Drive letter `Z:` stays.
- Inventory hostnames and usernames listed in `private/obfuscate.yaml`.
- `detail` and LM Studio `summary` strings (same sanitizer).

What stays visible: LM Studio / Ollama / NAS / Internet / Uptime Kuma
card titles, model names, ports 1234 / 11434 / 3001 / 8000 / 445, public
Google/Cloudflare probe URLs, counts, up/down, uptime %, `ping_ms`.

This is **not** the GitHub `10.42.0.x` rewrite. Extra replacements live
in `private/obfuscate.yaml` (example: `public/obfuscate.example.yaml`).

## Can I see my files on my NAS?

Primary check: the configured mapped drive (typically `Z:`) exists and
a directory listing succeeds. That is “I can see files.” An empty but
readable drive still counts as up. A missing, denied, or hung listing
is down.

If the drive is missing, the card tells you to reconnect with
`ConnectToHomeSan.ps1` or `connectDrive.bat`. The dashboard does **not**
run `net use` and does **not** load NAS credentials. Those stay in the
existing PowerShell SAN config, not this repository.

An optional TCP probe to SMB (port 445) can appear as extra detail when
a share host is configured. It does not decide the overall status.

The listing runs in a worker thread with a short timeout so a hung
share cannot freeze the other checks.
