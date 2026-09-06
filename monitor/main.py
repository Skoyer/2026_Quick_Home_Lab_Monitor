from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from monitor.checks import run_all_checks
from monitor.config import ROOT, SERVICES_PRIVATE, load_services_config

STATIC_DIR = ROOT / "static"

app = FastAPI(title="Home Lab Monitor", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
async def status() -> dict:
    payload = await run_all_checks()
    config = load_services_config()
    dashboard = config.get("dashboard") or {}
    payload.update(
        {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "refresh_seconds": int(dashboard.get("refresh_seconds", 10)),
            "using_private_config": SERVICES_PRIVATE.exists(),
        }
    )
    return payload


def dashboard_bind() -> tuple[str, int]:
    dashboard = (load_services_config().get("dashboard") or {})
    return str(dashboard.get("host", "127.0.0.1")), int(dashboard.get("port", 8080))
