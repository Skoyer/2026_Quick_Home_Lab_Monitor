import asyncio
import json

import httpx

from monitor.kuma import (
    LOGIN_HINT,
    card_state,
    check_uptime_kuma,
    compact_snapshot,
    fetch_kuma_snapshot,
    format_counts,
    format_uptime,
    parse_prometheus_metrics,
    parse_status_page,
    reset_summary_cache,
    snapshot_fingerprint,
    summarize_with_lm_studio,
)


PROMETHEUS = """
# HELP monitor_status Monitor Status (1 = UP, 0 = DOWN, 2 = PENDING, 3 = MAINTENANCE)
# TYPE monitor_status gauge
monitor_status{monitor_name="Orbi Main",monitor_type="ping",monitor_url="http://10.42.0.14",monitor_hostname="10.42.0.14",monitor_port=""} 1
monitor_status{monitor_name="Orbi Sat 1",monitor_type="ping",monitor_url="http://10.42.0.15",monitor_hostname="10.42.0.15",monitor_port=""} 1
monitor_status{monitor_name="Ping Gateway",monitor_type="ping",monitor_url="http://10.42.0.1",monitor_hostname="10.42.0.1",monitor_port=""} 0
monitor_response_time{monitor_name="Orbi Main",monitor_type="ping",monitor_url="http://10.42.0.14",monitor_hostname="10.42.0.14",monitor_port=""} 4
"""

STATUS_PAGE = {
    "publicGroupList": [
        {
            "name": "Network Infrastructure",
            "monitorList": [
                {
                    "id": 1,
                    "name": "Orbi Main",
                    "type": "ping",
                    "tags": [{"name": "Critical"}, {"name": "Network Infrastructure"}],
                },
                {
                    "id": 2,
                    "name": "Orbi Sat 1",
                    "type": "ping",
                    "tags": [{"name": "Network Infrastructure"}],
                },
                {
                    "id": 3,
                    "name": "Ping Gateway",
                    "type": "ping",
                    "tags": [{"name": "Network Infrastructure"}, {"name": "Critical"}],
                },
            ],
        }
    ]
}

HEARTBEAT = {
    "heartbeatList": {
        "1": [{"status": 1, "ping": 5}],
        "2": [{"status": 1, "ping": 3}],
        "3": [{"status": 1, "ping": 2}],
    },
    "uptimeList": {
        "1_24": 0.1429,
        "2_24": 1.0,
        "3_24": 0.912,
    },
}


def test_parse_prometheus_status_and_ping():
    monitors = parse_prometheus_metrics(PROMETHEUS)
    by_name = {item["name"]: item for item in monitors}
    assert by_name["Orbi Main"]["status"] == "up"
    assert by_name["Orbi Main"]["ping_ms"] == 4
    assert "monitor_url" not in by_name["Orbi Main"]
    assert by_name["Ping Gateway"]["status"] == "down"


def test_parse_status_page_uptime_and_tags():
    monitors = parse_status_page(STATUS_PAGE, HEARTBEAT)
    main = next(item for item in monitors if item["name"] == "Orbi Main")
    gateway = next(item for item in monitors if item["name"] == "Ping Gateway")
    assert main["status"] == "up"
    assert main["uptime"] == "14.29%"
    assert "Critical" in main["tags"]
    assert gateway["uptime"] == "91.2%"
    assert format_uptime(1.0) == "100%"


def test_low_uptime_while_up_does_not_mark_card_down():
    monitors = parse_status_page(STATUS_PAGE, HEARTBEAT)
    assert card_state(True, monitors) == "up"
    assert format_counts(compact_snapshot(source="status_page", monitors=monitors)["counts"]) == (
        "3 up / 0 down"
    )


def test_critical_down_marks_card_down():
    heartbeat = {
        "heartbeatList": {
            "1": [{"status": 0, "ping": 0}],
            "2": [{"status": 1, "ping": 3}],
            "3": [{"status": 1, "ping": 2}],
        },
        "uptimeList": HEARTBEAT["uptimeList"],
    }
    monitors = parse_status_page(STATUS_PAGE, heartbeat)
    assert card_state(True, monitors) == "down"


def test_noncritical_down_is_degraded():
    monitors = [
        {"name": "Orbi Sat 1", "status": "down", "tags": ["Network Infrastructure"]},
        {"name": "Orbi Sat 2", "status": "up", "tags": ["Network Infrastructure"]},
    ]
    assert card_state(True, monitors) == "degraded"


def test_unreachable_and_empty_payload_states():
    assert card_state(False, []) == "down"
    assert card_state(True, []) == "degraded"


def test_fingerprint_changes_when_status_changes():
    up = compact_snapshot(
        source="metrics",
        monitors=[{"name": "Ping Gateway", "status": "up", "tags": ["Critical"]}],
    )
    down = compact_snapshot(
        source="metrics",
        monitors=[{"name": "Ping Gateway", "status": "down", "tags": ["Critical"]}],
    )
    assert snapshot_fingerprint(up) != snapshot_fingerprint(down)


def test_fingerprint_ignores_uptime_percent():
    up_high = compact_snapshot(
        source="status_page",
        monitors=[{"name": "Orbi Main", "status": "up", "uptime": "14.29%", "tags": ["Critical"]}],
    )
    up_low = compact_snapshot(
        source="status_page",
        monitors=[{"name": "Orbi Main", "status": "up", "uptime": "22.31%", "tags": ["Critical"]}],
    )
    assert snapshot_fingerprint(up_high) == snapshot_fingerprint(up_low)


def test_login_hint_constant():
    assert "public status page" in LOGIN_HINT
    assert "private/secrets.env" in LOGIN_HINT
    assert "cannot read the monitor list" in LOGIN_HINT


KUMA_CFG = {
    "id": "uptime_kuma",
    "name": "What is Uptime Kuma reporting?",
    "scheme": "http",
    "host": "10.42.0.40",
    "port": 3001,
    "status_page_slug": "ping-networkinfrastructure",
    "lm_studio_model": "llama-3.2-8b-instruct",
    "summarize_timeout_seconds": 2,
    "summary_cache_seconds": 90,
}

FULL_CFG = {
    "services": [
        {
            "id": "lm_studio",
            "scheme": "http",
            "host": "10.42.0.10",
            "port": 1234,
        }
    ],
    "uptime_kuma": KUMA_CFG,
}


def _json_response(payload, status=200):
    return httpx.Response(
        status,
        json=payload,
        headers={"content-type": "application/json"},
    )


def _run(coro):
    return asyncio.run(coro)


def test_fetch_prefers_status_page_over_login_hint():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/api/entry-page"):
            return _json_response({"type": "entryPage", "entryPage": None})
        if path.endswith("/api/status-page/ping-networkinfrastructure"):
            return _json_response(STATUS_PAGE)
        if path.endswith("/api/status-page/heartbeat/ping-networkinfrastructure"):
            return _json_response(HEARTBEAT)
        if path.endswith("/metrics"):
            raise AssertionError("configured status-page slug should skip /metrics")
        return httpx.Response(404, text="no")

    async def inner():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_kuma_snapshot(client, KUMA_CFG)

    fetched = _run(inner())
    assert fetched["reachable"] is True
    assert fetched["source"] == "status_page"
    assert fetched["slug"] == "ping-networkinfrastructure"
    assert len(fetched["monitors"]) == 3


def test_fetch_falls_back_to_metrics_with_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/api/entry-page"):
            return _json_response({"type": "entryPage", "entryPage": None})
        if path.endswith("/metrics"):
            assert request.headers.get("authorization", "").startswith("Basic ")
            return httpx.Response(200, text=PROMETHEUS)
        return httpx.Response(404, text="no")

    async def inner():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_kuma_snapshot(
                client,
                {**KUMA_CFG, "status_page_slug": ""},
                secrets={"KUMA_API_KEY": "uk2_test_placeholder"},
            )

    fetched = _run(inner())
    assert fetched["source"] == "metrics"
    assert any(item["name"] == "Orbi Main" for item in fetched["monitors"])


def test_fetch_login_hint_when_unauthenticated():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/entry-page"):
            return _json_response({"type": "entryPage", "entryPage": None})
        if request.url.path.endswith("/metrics"):
            return httpx.Response(401, text="")
        return httpx.Response(404, json={"msg": "Status Page Not Found"})

    async def inner():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_kuma_snapshot(client, {**KUMA_CFG, "status_page_slug": ""}, secrets={})

    fetched = _run(inner())
    assert fetched["reachable"] is True
    assert fetched["monitors"] == []
    assert fetched["note"] == LOGIN_HINT


def test_kuma_down_skips_llm():
    reset_summary_cache()
    llm_called = {"value": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if "10.42.0.10" in str(request.url):
            llm_called["value"] = True
            return httpx.Response(500, text="nope")
        raise httpx.ConnectError("kuma down", request=request)

    async def inner():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await check_uptime_kuma(client, KUMA_CFG, FULL_CFG, timeout=2)

    result = _run(inner())
    assert result["state"] == "down"
    assert result["summary"] is None
    assert llm_called["value"] is False
    assert "Cannot reach" in result["detail"] or "kuma down" in result["detail"]


def test_llm_failure_keeps_structured_counts():
    reset_summary_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/api/entry-page"):
            return _json_response({"type": "entryPage", "entryPage": None})
        if path.endswith("/api/status-page/ping-networkinfrastructure"):
            return _json_response(STATUS_PAGE)
        if path.endswith("/api/status-page/heartbeat/ping-networkinfrastructure"):
            return _json_response(HEARTBEAT)
        if path.endswith("/v1/models") or path.endswith("/v1/chat/completions"):
            raise httpx.ConnectError("lm studio down", request=request)
        return httpx.Response(404, text="no")

    async def inner():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await check_uptime_kuma(client, KUMA_CFG, FULL_CFG, timeout=2)

    result = _run(inner())
    assert result["state"] == "up"
    assert "3 up / 0 down" in result["detail"]
    assert result["summary"] is None
    assert "LM Studio summary unavailable" in result["detail"]


def test_summarize_uses_loaded_model_and_caches():
    reset_summary_cache()
    calls = {"chat": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/models"):
            return _json_response(
                {
                    "data": [
                        {"id": "text-embedding-nomic-embed-text-v1.5"},
                        {"id": "llama-3.2-8b-instruct"},
                    ]
                }
            )
        if request.url.path.endswith("/v1/chat/completions"):
            calls["chat"] += 1
            body = json.loads(request.content.decode())
            assert body["model"] == "llama-3.2-8b-instruct"
            return _json_response(
                {
                    "choices": [
                        {"message": {"content": "Network looks healthy overall."}}
                    ]
                }
            )
        return httpx.Response(404)

    snapshot = compact_snapshot(
        source="status_page",
        monitors=[{"name": "Orbi Main", "status": "up", "uptime": "14.29%", "tags": ["Critical"]}],
    )
    transport = httpx.MockTransport(handler)
    orig = httpx.AsyncClient

    class Wrapped(orig):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    import monitor.kuma as kuma_mod

    kuma_mod.httpx.AsyncClient = Wrapped
    try:
        first = _run(
            summarize_with_lm_studio(
                snapshot,
                origin="http://10.42.0.10:1234",
                preferred_model="llama-3.2-8b-instruct",
                timeout=2,
                cache_seconds=90,
            )
        )
        second = _run(
            summarize_with_lm_studio(
                snapshot,
                origin="http://10.42.0.10:1234",
                preferred_model="llama-3.2-8b-instruct",
                timeout=2,
                cache_seconds=90,
            )
        )
    finally:
        kuma_mod.httpx.AsyncClient = orig
        reset_summary_cache()
    assert first["ok"] is True
    assert first["cached"] is False
    assert second["cached"] is True
    assert calls["chat"] == 1
    assert "healthy" in first["text"]

