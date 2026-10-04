# Home Lab Monitor

Python dashboard that answers operator “can I see X?” questions from a
browser:

- Can I reach the internet?
- Can I see LM Studio?
- Can I see the Ollama server?
- What is Uptime Kuma reporting?
- Can I see my files on my NAS?

It is not a replacement for Uptime Kuma. Use both: this app for
app-semantic checks (model list, NAS path listing) and for a
structured Kuma snapshot plus optional LM Studio summary; Kuma for
ICMP, history, retries, Critical tags, and notifications. See
[docs/COMPARE_TO_UPTIME_KUMA.md](docs/COMPARE_TO_UPTIME_KUMA.md).

Live addresses, passwords, and home-lab notes stay in `private/`, which
is gitignored. `public/` holds fictitious examples for GitHub.

Two supported runtimes:

| Host | How it runs | NAS listing |
| --- | --- | --- |
| **Windows workstation** | Local `.venv` + `run.py` (unchanged) | Mapped drive `Z:` via `nas.drive` |
| **Ubuntu 24.04 Docker host** (kuma-host) | Docker Compose at `/opt/homelab/home-dashboard` | Bind-mounted network path via `nas.path` (no `Z:`) |

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

## Run (Windows)

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

## Start at login (Windows)

Copy `scripts/startHomeLabMonitor.bat` to `C:\scripts`. That wrapper
points at `scripts/Start-HomeLabMonitor.ps1` in this repo. It starts the
venv `python.exe` with `run.py` only when TCP 8000 is free. If this
dashboard is already listening, it prints a message and exits 0. If
another process owns 8000, it warns and exits non-zero.

Optional: Task Scheduler at logon, or the Startup folder, can run
`C:\scripts\startHomeLabMonitor.bat`. Open
[http://127.0.0.1:8000](http://127.0.0.1:8000) on this PC, or port 8000
on this machine’s LAN IP from another device.

## Run on Ubuntu 24.04 (Docker on kuma-host)

Intended checkout: `/opt/homelab/home-dashboard` on the Ubuntu Docker
host that already runs Uptime Kuma (public example name: **kuma-host**).
Python comes from the Ubuntu 24.04 image (`Dockerfile`); do not use a
Windows `.venv` on that host. Use the Compose **plugin**:
`docker compose` (not the legacy `docker-compose` binary).

1. Clone or sync this repo to `/opt/homelab/home-dashboard`.
2. Create `private/` on the server (never commit it). Copy the public
   examples and edit real LAN values:

   ```bash
   mkdir -p private
   cp public/services.example.yaml private/services.yaml
   cp public/ip_map.example.yaml private/ip_map.yaml
   cp public/obfuscate.example.yaml private/obfuscate.yaml
   ```

3. In `private/services.yaml`, set the NAS check to a network path
   (there is no `Z:` drive on Ubuntu):

   ```yaml
   nas:
     path: /mnt/nas
     # drive: "Z:"   # Windows only — leave unset or unused on Linux
     share: '\\10.42.0.30\shared'
     host: 10.42.0.30
     smb_port: 445
   ```

4. Mount the NAS share on the **host** (CIFS/NFS) at `/mnt/nas` (or set
   `NAS_MOUNT_PATH` to your host mount). Compose bind-mounts that path
   into the container at `/mnt/nas` read-only. The app only lists the
   path; it does not store NAS credentials.
5. Build and start (publishes host port **8000**):

   ```bash
   cd /opt/homelab/home-dashboard
   docker compose up -d --build
   ```

Open `http://<kuma-host>:8000` on the LAN. `private/` is mounted
read-only at `/app/private` and is excluded from the image via
`.dockerignore`.

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
