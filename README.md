# Home Lab Monitor

Python dashboard that answers operator “can I see X?” questions from a
browser:

- Can I reach the internet?
- Can I see LM Studio?
- Can I see the Ollama server?
- What is Uptime Kuma reporting?
- Can I see my files on my NAS?

It is not a replacement for Uptime Kuma. Use both: this app for
app-semantic checks (model list, mapped `Z:` listing) and for a
structured Kuma snapshot plus optional LM Studio summary; Kuma for
ICMP, history, retries, Critical tags, and notifications. See
[docs/COMPARE_TO_UPTIME_KUMA.md](docs/COMPARE_TO_UPTIME_KUMA.md).

Live addresses, passwords, and home-lab notes stay in `private/`, which
is gitignored. `public/` holds fictitious examples for GitHub.

## Setup (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt
```

If `private/services.yaml` is missing, copy the example and edit it:

```powershell
New-Item -ItemType Directory -Force private | Out-Null
Copy-Item public\services.example.yaml private\services.yaml
Copy-Item public\ip_map.example.yaml private\ip_map.yaml
Copy-Item public\obfuscate.example.yaml private\obfuscate.yaml
```

Put credentials only in `private/secrets.env`. That file is not uploaded.
NAS username and password stay in the existing PowerShell SAN config;
do not copy them into this repo. Kuma ingest uses a public status-page
slug (`network` in the example map). Optional
`KUMA_API_KEY` is only for a Prometheus `/metrics` fallback when no slug
is set — never invent or commit a real key.

## Run

```powershell
.\.venv\Scripts\python run.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) on this machine, or
`http://<this-host>:8000` from another device on the LAN. Host and port
come from `dashboard.host` / `dashboard.port` in `private/services.yaml`
(defaults: all interfaces `0.0.0.0`, port `8000`). There is no login.

On Windows, allow inbound TCP 8000 on the Private profile if phones
cannot connect. Prefer a rule scoped to your LAN subnet.

One-shot CLI check:

```powershell
.\.venv\Scripts\python scripts\verify_endpoints.py
```

## Public examples

After you change the private service list or IP map:

```powershell
.\.venv\Scripts\python scripts\generate_public_examples.py
```

That rewrites real hosts to the fictitious values in `private/ip_map.yaml`
and refuses to write `public/` if a mapped real value is still present.

See [docs/PRIVACY.md](docs/PRIVACY.md) and [docs/MONITORS.md](docs/MONITORS.md).

## Screenshot Obfuscate mode

Turn **Obfuscate** ON on the dashboard before capturing a screenshot. The
choice is stored in `localStorage` and the next `/api/status?obfuscate=1`
response is sanitized **on the server** (a yellow banner shows so
`192.x.y.10` is not mistaken for a real address).

Masked when ON:

- RFC1918 IPv4 (`192.168.a.b` → `192.x.y.b`, plus `10.` / `172.16–31` the same way)
- UNC/SMB share names (drive letter `Z:` stays)
- Inventory hostnames and usernames from `private/obfuscate.yaml` (and non-IP keys in `private/ip_map.yaml`)
- Kuma name hints such as `(a.b)` → `(x.y.b)`
- The same rewriting on `detail`, `summary`, probe URLs, and monitor names

Left visible: service names, model names, well-known ports, public Google/Cloudflare URLs, up/down counts, uptime %, `ping_ms`.

Copy `public/obfuscate.example.yaml` to `private/obfuscate.yaml` for extra string replacements. Screenshot mode does **not** use the fictitious `10.42.0.x` GitHub map.
