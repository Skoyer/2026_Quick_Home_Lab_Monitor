# Home Lab Monitor

Python dashboard that answers four questions from a browser:

- Can I reach the internet?
- Can I see LM Studio?
- Can I see the Ollama server?
- Can I see my files on my NAS?

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
```

Put credentials only in `private/secrets.env`. That file is not uploaded.
NAS username and password stay in the existing PowerShell SAN config;
do not copy them into this repo.

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
