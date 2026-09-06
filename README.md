# Home Lab Monitor

Python dashboard that answers three questions from a browser:

- Can I reach the internet?
- Can I see LM Studio?
- Can I see the Ollama server?

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

## Run

```powershell
.\.venv\Scripts\python run.py
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). The dashboard binds
to localhost by default and has no login.

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
