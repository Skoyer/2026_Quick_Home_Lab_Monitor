import json

from fastapi.testclient import TestClient

from monitor.obfuscate import obfuscate_payload, obfuscate_text, request_wants_obfuscate


# Documented sanitizer *input* only (not live inventory in app source).
EXAMPLE_LAN = "192.168.200."
LM_STUDIO = "192.168.200.10"
OLLAMA = "192.168.200.20"
KUMA = "192.168.200.40"
NAS = "192.168.200.30"
SHARE = "labshare"
HOST_A = "kuma-host"
HOST_B = "workstation-01"
NAS_UNC = "\\\\" + NAS + "\\" + SHARE

EXTRAS = {
    SHARE: "shared",
    HOST_A: "kuma-host",
    HOST_B: "workstation",
    "labuser": "user",
}

FAKE_PAYLOAD = {
    "checks": [
        {
            "id": "lm_studio",
            "name": "Can I see LM Studio",
            "state": "up",
            "detail": "2 model(s): llama-3.2-8b-instruct, text-embedding-nomic",
            "target": f"http://{LM_STUDIO}:1234/v1/models",
            "probes": [{"url": f"http://{LM_STUDIO}:1234/v1/models", "ok": True}],
            "elapsed_ms": 12,
        },
        {
            "id": "ollama",
            "name": "Can I see the Ollama Server",
            "state": "up",
            "detail": "Ollama 0.11.4",
            "target": f"http://{OLLAMA}:11434/api/version",
            "elapsed_ms": 8,
        },
        {
            "id": "nas",
            "name": "Can I see my files on my NAS?",
            "state": "up",
            "detail": f"3 item(s) visible on Z:; SMB 445 reachable at {NAS_UNC}",
            "target": "Z:\\",
            "probes": [{"kind": "tcp", "host": NAS, "port": 445, "ok": True}],
        },
        {
            "id": "internet",
            "name": "Can I Reach the Internet",
            "state": "up",
            "detail": "3/3 public endpoints reachable",
            "probes": [
                {"url": "https://www.google.com/generate_204", "ok": True},
                {"url": "https://1.1.1.1/cdn-cgi/trace", "ok": True},
            ],
        },
        {
            "id": "uptime_kuma",
            "name": "What is Uptime Kuma reporting?",
            "state": "up",
            "detail": "4 up / 0 down",
            "target": f"http://{KUMA}:3001",
            "summary": (
                f"Orbi Main (200.14) is up. {HOST_B} can list {NAS_UNC}. "
                f"{HOST_A} looks healthy. user=labuser connected to {LM_STUDIO}."
            ),
            "monitors": [
                {
                    "name": "Orbi Main (200.14)",
                    "status": "up",
                    "uptime": "14%",
                    "ping_ms": 5,
                    "tags": ["Critical"],
                }
            ],
            "counts": {"up": 4, "down": 0},
            "probes": [{"url": f"http://{KUMA}:3001/api/status-page/network"}],
        },
    ],
    "refresh_seconds": 10,
    "using_private_config": True,
}


def _dump(payload) -> str:
    return json.dumps(payload)


def test_obfuscate_rewrites_lan_and_not_public_examples():
    masked = obfuscate_payload(
        FAKE_PAYLOAD,
        extras=EXTRAS,
        lan_prefixes=[EXAMPLE_LAN],
    )
    blob = _dump(masked)
    assert EXAMPLE_LAN not in blob
    assert "10.42.0." not in blob
    assert SHARE not in blob
    assert HOST_A not in blob
    assert HOST_B not in blob
    assert "labuser" not in blob
    assert "55.14" not in blob
    assert "192.x.y.10" in blob
    assert "192.x.y.87" in blob
    assert "192.x.y.51" in blob
    assert "192.x.y.250" in blob
    assert "llama-3.2-8b-instruct" in blob
    assert "https://www.google.com/generate_204" in blob
    assert "https://1.1.1.1/cdn-cgi/trace" in blob
    assert "3/3 public endpoints reachable" in blob
    assert "4 up / 0 down" in blob
    assert "14%" in blob
    assert masked["obfuscated"] is True
    nas = next(item for item in masked["checks"] if item["id"] == "nas")
    assert nas["target"] == "Z:\\"
    assert "192.x.y.250" in nas["detail"]
    assert SHARE not in nas["detail"]
    assert "shared" in nas["detail"] or "\\share" in nas["detail"]
    kuma = next(item for item in masked["checks"] if item["id"] == "uptime_kuma")
    assert "Orbi Main (x.y.14)" in kuma["summary"]
    assert SHARE not in kuma["summary"]
    assert HOST_A not in kuma["summary"]
    assert HOST_B not in kuma["summary"]
    assert kuma["monitors"][0]["ping_ms"] == 5


def test_obfuscate_other_rfc1918_and_unc_without_extras():
    text = "probe 10.9.8.7 and 172.16.4.9 plus " + "\\\\" + NAS + "\\" + SHARE
    masked = obfuscate_text(text, extras={}, lan_thirds={"55"}, lan_prefixes=[EXAMPLE_LAN])
    assert "10.9.8.7" not in masked
    assert "172.16.4.9" not in masked
    assert "10.x.y.7" in masked
    assert "172.x.y.9" in masked
    assert SHARE not in masked
    assert EXAMPLE_LAN not in masked


def test_obfuscate_off_leaves_payload_unchanged():
    clone = json.loads(json.dumps(FAKE_PAYLOAD))
    assert clone == FAKE_PAYLOAD
    assert request_wants_obfuscate(False, None) is False
    assert request_wants_obfuscate(True, None) is True
    assert request_wants_obfuscate(False, "1") is True
    assert request_wants_obfuscate(False, "off") is False


def test_api_status_obfuscate_query(monkeypatch):
    from monitor import main

    async def fake_checks():
        return json.loads(json.dumps(FAKE_PAYLOAD))

    monkeypatch.setattr(main, "run_all_checks", fake_checks)
    monkeypatch.setattr(
        "monitor.obfuscate.load_obfuscate_extras",
        lambda: EXTRAS,
    )
    monkeypatch.setattr(
        "monitor.obfuscate.load_lan_prefixes",
        lambda: [EXAMPLE_LAN],
    )

    client = TestClient(main.app)
    raw = client.get("/api/status")
    assert raw.status_code == 200
    raw_blob = raw.text
    assert LM_STUDIO in raw_blob
    assert raw.json()["obfuscated"] is False

    masked = client.get("/api/status?obfuscate=1")
    assert masked.status_code == 200
    body = masked.json()
    blob = masked.text
    assert body["obfuscated"] is True
    assert EXAMPLE_LAN not in blob
    assert SHARE not in blob
    assert HOST_B not in blob
    assert "192.x.y.10" in blob

    headed = client.get("/api/status", headers={"X-Obfuscate": "true"})
    assert headed.json()["obfuscated"] is True
    assert EXAMPLE_LAN not in headed.text
