from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx

from monitor.config import load_secrets

LOGIN_HINT = (
    "Kuma UI requires login; this dashboard cannot read the monitor list. "
    "Configure a public status page or API key in private/secrets.env. "
    "Do not assume Kuma has zero monitors."
)
STATUS_NAMES = {0: "down", 1: "up", 2: "pending", 3: "maintenance"}
LABEL_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)="((?:\\.|[^"\\])*)"')
MONITOR_STATUS_RE = re.compile(
    r"^monitor_status\{([^}]*)\}\s+([0-9.]+)\s*$",
    re.MULTILINE,
)
MONITOR_PING_RE = re.compile(
    r"^monitor_response_time\{([^}]*)\}\s+([0-9.]+)\s*$",
    re.MULTILINE,
)
EMBED_HINTS = ("embed", "embedding")

SYSTEM_PROMPT = """You summarize current home-lab network health from an Uptime Kuma snapshot.
Write 4 to 8 sentences.
Use only monitors and counts in the snapshot. Do not invent monitors, IP addresses, or outages.
Call out monitors tagged Critical, low uptime percentages, and practical next actions.
If a monitor is currently Up but historical uptime is low, say that can happen when a monitor was added after an outage or has a short history; do not treat it as proof the device is mostly broken.
If the snapshot has no monitors, that means this dashboard could not read Kuma's list (login, public status page, or API key missing). Do not claim Kuma has no monitors configured, and do not invent a monitor list. Tell the operator to publish a status page or set KUMA_API_KEY."""

_summary_cache: dict[str, Any] = {
    "fingerprint": None,
    "text": None,
    "model": None,
    "expires": 0.0,
}


def _url(scheme: str, host: str, port: int, path: str = "/") -> str:
    prefix = path if path.startswith("/") else f"/{path}"
    return f"{scheme}://{host}:{port}{prefix}"


def _kuma_base(config: dict[str, Any]) -> str:
    return _url(
        str(config.get("scheme") or "http"),
        str(config["host"]),
        int(config.get("port") or 3001),
        "/",
    ).rstrip("/")


def _public_probe(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": probe["url"],
        "ok": probe["ok"],
        "status_code": probe.get("status_code"),
        "elapsed_ms": probe.get("elapsed_ms"),
        "error": probe.get("error"),
    }


async def _get(
    client: httpx.AsyncClient,
    url: str,
    *,
    auth: tuple[str, str] | None = None,
    headers: dict[str, str] | None = None,
    expect_status: int | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = await client.get(url, auth=auth, headers=headers)
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
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                result["json"] = response.json()
            except ValueError:
                pass
        else:
            result["text"] = response.text
        return result
    except httpx.HTTPError as exc:
        return {
            "url": url,
            "ok": False,
            "status_code": None,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


def parse_prometheus_labels(raw: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for key, value in LABEL_RE.findall(raw):
        labels[key] = value.replace('\\"', '"').replace("\\\\", "\\")
    return labels


def format_uptime(value: Any) -> str | None:
    if value is None:
        return None
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return None
    if ratio > 1:
        pct = ratio
    else:
        pct = ratio * 100
    if pct >= 99.95:
        return "100%"
    formatted = f"{pct:.2f}".rstrip("0").rstrip(".")
    return f"{formatted}%"


def _status_name(value: Any) -> str:
    try:
        return STATUS_NAMES.get(int(float(value)), "unknown")
    except (TypeError, ValueError):
        if isinstance(value, str) and value.lower() in {"up", "down", "pending", "maintenance"}:
            return value.lower()
        return "unknown"


def parse_prometheus_metrics(text: str) -> list[dict[str, Any]]:
    ping_by_name: dict[str, float] = {}
    for labels_raw, value in MONITOR_PING_RE.findall(text or ""):
        labels = parse_prometheus_labels(labels_raw)
        name = labels.get("monitor_name")
        if not name:
            continue
        try:
            ping_by_name[name] = float(value)
        except ValueError:
            continue

    monitors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for labels_raw, value in MONITOR_STATUS_RE.findall(text or ""):
        labels = parse_prometheus_labels(labels_raw)
        name = labels.get("monitor_name")
        if not name or name in seen:
            continue
        seen.add(name)
        tags = [
            labels[key]
            for key in sorted(labels)
            if key.startswith("tag_") and labels[key]
        ]
        item: dict[str, Any] = {
            "name": name,
            "status": _status_name(value),
            "type": labels.get("monitor_type"),
            "tags": tags,
        }
        ping = ping_by_name.get(name)
        if ping is not None:
            item["ping_ms"] = ping
        monitors.append(item)
    return monitors


def parse_status_page(
    page: dict[str, Any],
    heartbeat: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    heartbeat = heartbeat or {}
    heartbeat_list = heartbeat.get("heartbeatList") or {}
    uptime_list = heartbeat.get("uptimeList") or {}
    monitors: list[dict[str, Any]] = []
    for group in page.get("publicGroupList") or []:
        group_name = group.get("name")
        for monitor in group.get("monitorList") or []:
            monitor_id = str(monitor.get("id", ""))
            beats = heartbeat_list.get(monitor_id) or heartbeat_list.get(monitor.get("id")) or []
            latest = beats[-1] if beats else {}
            tags: list[str] = []
            if group_name:
                tags.append(str(group_name))
            for tag in monitor.get("tags") or []:
                if isinstance(tag, dict) and tag.get("name"):
                    tags.append(str(tag["name"]))
                elif isinstance(tag, str):
                    tags.append(tag)
            unique_tags = list(dict.fromkeys(tags))
            uptime = uptime_list.get(f"{monitor_id}_24")
            if uptime is None and monitor_id:
                uptime = uptime_list.get(f"{monitor.get('id')}_24")
            item: dict[str, Any] = {
                "name": monitor.get("name") or f"monitor-{monitor_id}",
                "status": _status_name(latest.get("status")) if latest else "unknown",
                "type": monitor.get("type"),
                "tags": unique_tags,
            }
            formatted = format_uptime(uptime)
            if formatted:
                item["uptime"] = formatted
            ping = latest.get("ping")
            if ping is not None:
                item["ping_ms"] = ping
            monitors.append(item)
    return monitors


def count_statuses(monitors: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"up": 0, "down": 0, "pending": 0, "maintenance": 0, "unknown": 0}
    for monitor in monitors:
        status = monitor.get("status") or "unknown"
        if status not in counts:
            counts["unknown"] += 1
        else:
            counts[status] += 1
    return counts


def is_critical(monitor: dict[str, Any]) -> bool:
    return any(str(tag).lower() == "critical" for tag in monitor.get("tags") or [])


def card_state(reachable: bool, monitors: list[dict[str, Any]]) -> str:
    if not reachable:
        return "down"
    if not monitors:
        return "degraded"
    critical_down = [
        monitor
        for monitor in monitors
        if is_critical(monitor) and monitor.get("status") == "down"
    ]
    if critical_down:
        return "down"
    if any(monitor.get("status") == "down" for monitor in monitors):
        return "degraded"
    return "up"


def format_counts(counts: dict[str, int]) -> str:
    detail = f"{counts.get('up', 0)} up / {counts.get('down', 0)} down"
    extra = []
    if counts.get("maintenance"):
        extra.append(f"{counts['maintenance']} maintenance")
    if counts.get("pending"):
        extra.append(f"{counts['pending']} pending")
    if extra:
        detail = f"{detail}; {', '.join(extra)}"
    return detail


def compact_snapshot(
    *,
    source: str,
    monitors: list[dict[str, Any]],
    note: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": source,
        "counts": count_statuses(monitors),
        "monitors": [
            {
                "name": item.get("name"),
                "status": item.get("status"),
                "uptime": item.get("uptime"),
                "tags": item.get("tags") or [],
                "ping_ms": item.get("ping_ms"),
            }
            for item in monitors
        ],
    }
    if not monitors:
        payload["monitor_list"] = "unavailable"
    if note:
        payload["note"] = note
    for item in payload["monitors"]:
        if item.get("uptime") is None:
            item.pop("uptime", None)
        if item.get("ping_ms") is None:
            item.pop("ping_ms", None)
    return payload


def snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    """Cache key is the up/down set (and tags), not drifting uptime percentages."""
    key = [
        snapshot.get("source"),
        snapshot.get("monitor_list"),
        [
            (
                item.get("name"),
                item.get("status"),
                tuple(item.get("tags") or []),
            )
            for item in snapshot.get("monitors") or []
        ],
    ]
    return json.dumps(key, sort_keys=True)


def metrics_auth(secrets: dict[str, str]) -> tuple[str, str] | None:
    api_key = secrets.get("KUMA_API_KEY")
    if api_key:
        return ("", api_key)
    username = secrets.get("KUMA_USERNAME")
    password = secrets.get("KUMA_PASSWORD")
    if username and password:
        return (username, password)
    if password:
        return ("", password)
    return None


def request_headers(secrets: dict[str, str]) -> dict[str, str] | None:
    cookie = secrets.get("KUMA_COOKIE")
    if cookie:
        return {"Cookie": cookie}
    return None


def lm_studio_origin(config: dict[str, Any]) -> str | None:
    for service in config.get("services") or []:
        if service.get("id") != "lm_studio":
            continue
        return _url(
            str(service.get("scheme") or "http"),
            str(service["host"]),
            int(service["port"]),
            "/",
        ).rstrip("/")
    return None


def choose_model(model_ids: list[str], preferred: str | None) -> str | None:
    usable = [name for name in model_ids if not any(hint in name.lower() for hint in EMBED_HINTS)]
    if preferred and preferred in usable:
        return preferred
    if preferred and preferred in model_ids:
        return preferred
    return usable[0] if usable else (model_ids[0] if model_ids else preferred)


def _cached_summary(fingerprint: str) -> tuple[str, str] | None:
    expires = float(_summary_cache.get("expires") or 0)
    if (
        _summary_cache.get("fingerprint") == fingerprint
        and _summary_cache.get("text")
        and time.monotonic() < expires
    ):
        return str(_summary_cache["text"]), str(_summary_cache.get("model") or "")
    return None


def _store_summary(fingerprint: str, text: str, model: str, ttl: float) -> None:
    _summary_cache["fingerprint"] = fingerprint
    _summary_cache["text"] = text
    _summary_cache["model"] = model
    _summary_cache["expires"] = time.monotonic() + max(ttl, 0)


def reset_summary_cache() -> None:
    _summary_cache["fingerprint"] = None
    _summary_cache["text"] = None
    _summary_cache["model"] = None
    _summary_cache["expires"] = 0.0


async def fetch_kuma_snapshot(
    client: httpx.AsyncClient,
    kuma_config: dict[str, Any],
    secrets: dict[str, str] | None = None,
) -> dict[str, Any]:
    secrets = secrets if secrets is not None else load_secrets()
    base = _kuma_base(kuma_config)
    headers = request_headers(secrets)
    probes: list[dict[str, Any]] = []
    monitors: list[dict[str, Any]] = []
    source = "none"
    note = None

    entry = await _get(client, f"{base}/api/entry-page", headers=headers)
    probes.append(_public_probe(entry))
    reachable = bool(entry.get("ok") and isinstance(entry.get("json"), dict))
    if not reachable and entry.get("error"):
        return {
            "reachable": False,
            "source": source,
            "monitors": [],
            "note": entry.get("error") or "Cannot reach Uptime Kuma",
            "probes": probes,
            "entry_page": None,
        }

    if not reachable:
        root = await _get(client, f"{base}/")
        probes.append(_public_probe(root))
        reachable = root.get("status_code") is not None and root.get("status_code") < 500
        if not reachable:
            return {
                "reachable": False,
                "source": source,
                "monitors": [],
                "note": root.get("error") or "Cannot reach Uptime Kuma",
                "probes": probes,
                "entry_page": None,
            }

    entry_page = (entry.get("json") or {}).get("entryPage")
    slug_from_config = str(kuma_config.get("status_page_slug") or "").strip()
    slug = slug_from_config or (
        str(entry_page).strip() if isinstance(entry_page, str) and entry_page else ""
    )
    if slug:
        page = await _get(client, f"{base}/api/status-page/{slug}", headers=headers)
        probes.append(_public_probe(page))
        if page.get("ok") and isinstance(page.get("json"), dict) and "publicGroupList" in page["json"]:
            beats = await _get(client, f"{base}/api/status-page/heartbeat/{slug}", headers=headers)
            probes.append(_public_probe(beats))
            monitors = parse_status_page(page["json"], beats.get("json") if beats.get("ok") else {})
            if monitors:
                source = "status_page"

    # Prometheus /metrics is optional. Skip it when a status-page slug is configured
    # (this lab publishes heartbeat JSON and does not use Prometheus).
    if not monitors and not slug_from_config:
        auth = metrics_auth(secrets)
        metrics = await _get(client, f"{base}/metrics", auth=auth, headers=headers)
        probes.append(_public_probe(metrics))
        if metrics.get("ok") and metrics.get("text"):
            monitors = parse_prometheus_metrics(metrics["text"])
            if monitors:
                source = "metrics"

    if not monitors:
        note = LOGIN_HINT
        source = "none"

    return {
        "reachable": True,
        "source": source,
        "monitors": monitors,
        "note": note,
        "probes": probes,
        "entry_page": entry_page,
        "slug": slug or None,
    }


async def resolve_lm_studio_model(
    client: httpx.AsyncClient,
    origin: str,
    preferred: str | None,
    timeout: float,
) -> str | None:
    try:
        response = await client.get(f"{origin}/v1/models", timeout=timeout)
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return preferred
    names = [
        item.get("id")
        for item in (payload.get("data") or [])
        if isinstance(item, dict) and item.get("id")
    ]
    return choose_model([str(name) for name in names], preferred)


async def summarize_with_lm_studio(
    snapshot: dict[str, Any],
    *,
    origin: str,
    preferred_model: str | None,
    timeout: float,
    cache_seconds: float,
) -> dict[str, Any]:
    fingerprint = snapshot_fingerprint(snapshot)
    cached = _cached_summary(fingerprint)
    if cached:
        text, model = cached
        return {"ok": True, "text": text, "model": model, "cached": True}

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        model = await resolve_lm_studio_model(client, origin, preferred_model, min(timeout, 5))
        if not model:
            return {
                "ok": False,
                "text": None,
                "model": None,
                "cached": False,
                "error": "No LM Studio model available",
            }
        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 400,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Current Uptime Kuma snapshot (JSON). "
                        "Summarize home-lab network health now.\n"
                        + json.dumps(snapshot, indent=2)
                    ),
                },
            ],
        }
        try:
            response = await client.post(f"{origin}/v1/chat/completions", json=payload)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "text": None,
                "model": model,
                "cached": False,
                "error": str(exc),
            }
        except ValueError:
            return {
                "ok": False,
                "text": None,
                "model": model,
                "cached": False,
                "error": "LM Studio returned non-JSON",
            }

    choices = body.get("choices") or []
    message = (choices[0].get("message") if choices else {}) or {}
    text = str(message.get("content") or "").strip()
    if not text:
        return {
            "ok": False,
            "text": None,
            "model": model,
            "cached": False,
            "error": "LM Studio returned an empty summary",
        }
    _store_summary(fingerprint, text, model, cache_seconds)
    return {"ok": True, "text": text, "model": model, "cached": False}


def _detail_for(state: str, snapshot: dict[str, Any], summary_note: str | None) -> str:
    monitors = snapshot.get("monitors") or []
    counts = snapshot.get("counts") or count_statuses(monitors)
    if state == "down" and not snapshot.get("reachable", True):
        return snapshot.get("note") or "Cannot reach Uptime Kuma"
    if monitors:
        detail = format_counts(counts)
    else:
        detail = snapshot.get("note") or LOGIN_HINT
    if summary_note:
        detail = f"{detail}. {summary_note}"
    return detail


async def check_uptime_kuma(
    client: httpx.AsyncClient,
    kuma_config: dict[str, Any],
    full_config: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    service_id = kuma_config.get("id", "uptime_kuma")
    name = kuma_config.get("name", "What is Uptime Kuma reporting?")
    target = _kuma_base(kuma_config)
    llm_timeout = float(kuma_config.get("summarize_timeout_seconds") or 8)
    cache_seconds = float(kuma_config.get("summary_cache_seconds") or 90)
    preferred_model = kuma_config.get("lm_studio_model") or "llama-3.2-8b-instruct"

    fetched = await fetch_kuma_snapshot(client, kuma_config)
    reachable = bool(fetched.get("reachable"))
    monitors = list(fetched.get("monitors") or [])
    snapshot = compact_snapshot(
        source=str(fetched.get("source") or "none"),
        monitors=monitors,
        note=fetched.get("note"),
    )
    snapshot["reachable"] = reachable
    state = card_state(reachable, monitors)
    summary_text = None
    summary_error = None
    model = None
    summary_cached = False

    if reachable:
        origin = lm_studio_origin(full_config)
        if origin:
            try:
                result = await asyncio.wait_for(
                    summarize_with_lm_studio(
                        snapshot,
                        origin=origin,
                        preferred_model=str(preferred_model),
                        timeout=llm_timeout,
                        cache_seconds=cache_seconds,
                    ),
                    timeout=max(llm_timeout, 1.0),
                )
            except TimeoutError:
                result = {
                    "ok": False,
                    "text": None,
                    "model": None,
                    "cached": False,
                    "error": "LM Studio summary timed out",
                }
            if result.get("ok"):
                summary_text = result.get("text")
                model = result.get("model")
                summary_cached = bool(result.get("cached"))
            else:
                summary_error = result.get("error") or "LM Studio summary unavailable"
                model = result.get("model")
        else:
            summary_error = "LM Studio is not configured"

    summary_note = None
    if reachable and not summary_text:
        summary_note = "LM Studio summary unavailable"
        if summary_error:
            summary_note = f"{summary_note}: {summary_error}"

    detail = _detail_for(state, snapshot, summary_note)
    return {
        "id": service_id,
        "name": name,
        "state": state,
        "ok": state != "down",
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "detail": detail,
        "summary": summary_text,
        "summary_available": bool(summary_text),
        "summary_cached": summary_cached,
        "model": model,
        "target": target,
        "source": fetched.get("source"),
        "counts": snapshot.get("counts"),
        "monitors": snapshot.get("monitors"),
        "probes": fetched.get("probes") or [],
        "timeout_seconds": timeout,
    }
