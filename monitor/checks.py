from __future__ import annotations

import time
from typing import Any

import httpx

from monitor.config import load_services_config


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
    results = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        results.append(await check_internet(client, config.get("internet") or {}))
        for service in config.get("services") or []:
            results.append(await check_service(client, service))
    return {"checks": results}
