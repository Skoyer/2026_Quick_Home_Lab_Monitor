from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

import httpx

from monitor.config import load_services_config
from monitor.kuma import check_uptime_kuma

WINDOWS_RECONNECT_HINT = "Reconnect with ConnectToHomeSan.ps1 or connectDrive.bat."
LINUX_RECONNECT_HINT = (
    "Remount the NAS share on the host and ensure it is bind-mounted into the container."
)


def is_windows_drive(raw: str) -> bool:
    value = (raw or "").strip()
    return len(value) >= 2 and value[1] == ":" and value[0].isalpha()


def format_list_path(raw: str) -> str:
    """Stable display path: Windows drive letters get a trailing slash; POSIX stays as written."""
    value = (raw or "Z:").strip()
    if is_windows_drive(value):
        if not value.endswith(("\\", "/")):
            value = value + "\\"
        return value
    return value


def normalize_list_path(raw: str) -> Path:
    """Path object for os.listdir. POSIX paths keep forward slashes when possible."""
    display = format_list_path(raw)
    if display.startswith("/") and not is_windows_drive(display):
        # Avoid Path("/mnt/nas") → "\\mnt\\nas" on Windows when only formatting matters.
        return Path(display)
    return Path(display)


def nas_list_target(config: dict[str, Any]) -> tuple[str, str]:
    """
    Return (label, path) for the NAS listing check.

    Prefer nas.path (Ubuntu/Docker network or bind-mount path). Fall back to
    nas.drive for the Windows mapped-drive workflow on the workstation.
    """
    path_value = config.get("path")
    if path_value:
        label = str(path_value).strip()
        return label, label
    drive = str(config.get("drive") or "Z:").strip() or "Z:"
    return drive, drive


def reconnect_hint_for(target: str) -> str:
    if is_windows_drive(target):
        return WINDOWS_RECONNECT_HINT
    return LINUX_RECONNECT_HINT


def share_host(share: str | None, host: str | None = None) -> str | None:
    if host:
        return str(host)
    if not share:
        return None
    cleaned = str(share).replace("/", "\\").strip().lstrip("\\")
    server = cleaned.split("\\", 1)[0].strip()
    return server or None


def inspect_list_path(raw: str) -> dict[str, Any]:
    display = format_list_path(raw)
    path = Path(display)
    if not path.exists():
        return {"ok": False, "reason": "missing", "path": display}
    names = os.listdir(path)
    return {
        "ok": True,
        "reason": "listed",
        "path": display,
        "count": len(names),
    }


async def list_path_async(raw: str, timeout: float) -> dict[str, Any]:
    return await asyncio.wait_for(
        asyncio.to_thread(inspect_list_path, raw),
        timeout=timeout,
    )


# Backward-compatible aliases used by older tests/callers.
normalize_drive_path = normalize_list_path
inspect_mapped_drive = inspect_list_path
list_mapped_drive_async = list_path_async


async def probe_tcp(host: str, port: int, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=1)
        except (TimeoutError, OSError):
            pass
        return {
            "ok": True,
            "host": host,
            "port": port,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }
    except TimeoutError:
        return {
            "ok": False,
            "host": host,
            "port": port,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "error": "timeout",
        }
    except OSError as exc:
        return {
            "ok": False,
            "host": host,
            "port": port,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


async def check_nas(config: dict[str, Any], timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    label, list_raw = nas_list_target(config)
    share = config.get("share")
    host = share_host(share, config.get("host"))
    smb_port = int(config.get("smb_port") or 445)
    nas_timeout = float(config.get("timeout_seconds") or timeout)
    service_id = config.get("id", "nas")
    name = config.get("name", "Can I see my files on my NAS?")
    hint = reconnect_hint_for(label)
    windows_drive = is_windows_drive(label)
    probes: list[dict[str, Any]] = []

    listing: dict[str, Any] | None = None
    list_error: str | None = None
    try:
        listing = await list_path_async(list_raw, nas_timeout)
    except TimeoutError:
        list_error = "timeout"
    except OSError as exc:
        list_error = str(exc)

    if listing and listing.get("ok"):
        state = "up"
        count = int(listing.get("count") or 0)
        if count:
            detail = f"{count} item(s) visible on {label}"
        elif windows_drive:
            detail = f"Drive {label} is readable"
        else:
            detail = f"Path {label} is readable"
        probes.append(
            {
                "kind": "listdir",
                "path": listing.get("path") or label,
                "ok": True,
                "item_count": count,
            }
        )
    else:
        state = "down"
        if list_error == "timeout":
            detail = f"Timed out listing {label}. The share may be hung."
        elif listing and listing.get("reason") == "missing":
            if windows_drive:
                detail = f"Mapped drive {label} is not available. {hint}"
            else:
                detail = f"NAS path {label} is not available. {hint}"
        else:
            detail = f"Could not list {label}. {list_error or hint}"
        probes.append(
            {
                "kind": "listdir",
                "path": (listing or {}).get("path") or label,
                "ok": False,
                "error": list_error or (listing or {}).get("reason"),
            }
        )

    if host:
        smb = await probe_tcp(host, smb_port, min(nas_timeout, timeout))
        probes.append(
            {
                "kind": "tcp",
                "host": host,
                "port": smb_port,
                "ok": smb.get("ok"),
                "elapsed_ms": smb.get("elapsed_ms"),
                "error": smb.get("error"),
            }
        )
        if smb.get("ok"):
            detail = f"{detail}; SMB {smb_port} reachable"
        else:
            detail = f"{detail}; SMB {smb_port} not reachable"

    return {
        "id": service_id,
        "name": name,
        "state": state,
        "ok": state != "down",
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "detail": detail,
        "target": format_list_path(list_raw),
        "probes": probes,
    }


def _url(scheme: str, host: str, port: int, path: str) -> str:
    prefix = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{host}:{port}{prefix}"


async def _probe(
    client: httpx.AsyncClient,
    url: str,
    expect_status: int | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = await client.get(url)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        ok = (
            response.status_code == expect_status
            if expect_status is not None
            else response.status_code < 400
        )
        result: dict[str, Any] = {
            "url": url,
            "ok": ok,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
        }
        if "application/json" in response.headers.get("content-type", ""):
            try:
                result["json"] = response.json()
            except ValueError:
                pass
        elif response.status_code == 200 and len(response.content) < 200:
            result["text"] = response.text.strip()
        return result
    except httpx.HTTPError as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        return {
            "url": url,
            "ok": False,
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
        }


def _summarize_lm_studio(probe: dict[str, Any]) -> str:
    payload = probe.get("json") or {}
    models = payload.get("data") or []
    names = [item.get("id") for item in models if isinstance(item, dict) and item.get("id")]
    if names:
        return f"{len(names)} model(s): {', '.join(names)}"
    if probe.get("ok"):
        return "API reachable"
    return probe.get("error") or f"HTTP {probe.get('status_code')}"


def _summarize_ollama(probe: dict[str, Any]) -> str:
    payload = probe.get("json") or {}
    version = payload.get("version")
    if version:
        return f"Ollama {version}"
    if probe.get("ok"):
        return probe.get("text") or "API reachable"
    return probe.get("error") or f"HTTP {probe.get('status_code')}"


def _public_probe(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": probe["url"],
        "ok": probe["ok"],
        "status_code": probe.get("status_code"),
        "elapsed_ms": probe.get("elapsed_ms"),
        "error": probe.get("error"),
    }


async def check_internet(client: httpx.AsyncClient, config: dict[str, Any]) -> dict[str, Any]:
    urls = list(config.get("urls") or [])
    threshold = int(config.get("success_threshold") or max(1, len(urls)))
    probes = []
    for url in urls:
        expect = 204 if "generate_204" in url else 200
        probes.append(await _probe(client, url, expect_status=expect))
    successes = sum(1 for probe in probes if probe["ok"])
    if successes >= threshold and successes == len(probes):
        state = "up"
    elif successes >= threshold:
        state = "degraded"
    else:
        state = "down"
    elapsed = max((probe.get("elapsed_ms") or 0) for probe in probes) if probes else 0
    return {
        "id": config.get("id", "internet"),
        "name": config.get("name", "Can I Reach the Internet"),
        "state": state,
        "ok": state != "down",
        "elapsed_ms": elapsed,
        "detail": f"{successes}/{len(probes)} public endpoints reachable",
        "probes": [_public_probe(probe) for probe in probes],
    }


async def check_service(client: httpx.AsyncClient, service: dict[str, Any]) -> dict[str, Any]:
    url = _url(
        service.get("scheme", "http"),
        service["host"],
        int(service["port"]),
        service.get("path", "/"),
    )
    probe = await _probe(client, url, expect_status=int(service.get("expect_status", 200)))
    service_id = service.get("id", service["host"])
    if service_id == "lm_studio":
        detail = _summarize_lm_studio(probe)
    elif service_id == "ollama":
        detail = _summarize_ollama(probe)
    elif probe.get("ok"):
        detail = "Reachable"
    else:
        detail = probe.get("error") or f"HTTP {probe.get('status_code')}"
    return {
        "id": service_id,
        "name": service.get("name", service_id),
        "state": "up" if probe["ok"] else "down",
        "ok": probe["ok"],
        "elapsed_ms": probe.get("elapsed_ms"),
        "detail": detail,
        "target": url,
        "probes": [_public_probe(probe)],
    }


async def run_all_checks() -> dict[str, Any]:
    config = load_services_config()
    dashboard = config.get("dashboard") or {}
    timeout = float(dashboard.get("timeout_seconds", 5))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        tasks = [check_internet(client, config.get("internet") or {})]
        legacy_kuma = None
        for service in config.get("services") or []:
            if service.get("id") == "uptime_kuma":
                legacy_kuma = service
                continue
            tasks.append(check_service(client, service))
        kuma = config.get("uptime_kuma") or legacy_kuma
        if kuma:
            tasks.append(check_uptime_kuma(client, kuma, config, timeout))
        nas = config.get("nas")
        if nas:
            tasks.append(check_nas(nas, timeout))
        results = await asyncio.gather(*tasks)
    return {"checks": list(results)}
