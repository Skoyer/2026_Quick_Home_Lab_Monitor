import asyncio

from monitor.checks import check_nas, nas_list_target


def _run(config, timeout=2, list_result=None, list_error=None, smb=None):
    async def fake_list(path, list_timeout):
        if list_error is not None:
            raise list_error
        return list_result

    async def fake_smb(host, port, smb_timeout):
        return smb or {
            "ok": True,
            "host": host,
            "port": port,
            "elapsed_ms": 1,
        }

    import monitor.checks as checks

    original_list = checks.list_path_async
    original_smb = checks.probe_tcp
    checks.list_path_async = fake_list
    checks.probe_tcp = fake_smb
    try:
        return asyncio.run(check_nas(config, timeout))
    finally:
        checks.list_path_async = original_list
        checks.probe_tcp = original_smb


NAS = {
    "id": "nas",
    "name": "Can I see my files on my NAS?",
    "drive": "Z:",
    "host": "10.42.0.30",
    "share": r"\\10.42.0.30\shared",
    "smb_port": 445,
}

NAS_LINUX = {
    "id": "nas",
    "name": "Can I see my files on my NAS?",
    "path": "/mnt/nas",
    "host": "10.42.0.30",
    "share": r"\\10.42.0.30\shared",
    "smb_port": 445,
}


def test_nas_up_when_listing_succeeds():
    result = _run(
        NAS,
        list_result={"ok": True, "reason": "listed", "path": "Z:\\", "count": 3},
    )
    assert result["state"] == "up"
    assert result["ok"] is True
    assert result["id"] == "nas"
    assert "3 item(s) visible" in result["detail"]
    assert "SMB 445 reachable" in result["detail"]


def test_nas_up_when_drive_is_empty_but_readable():
    result = _run(
        NAS,
        list_result={"ok": True, "reason": "listed", "path": "Z:\\", "count": 0},
    )
    assert result["state"] == "up"
    assert "readable" in result["detail"]


def test_nas_down_when_drive_missing():
    result = _run(
        NAS,
        list_result={"ok": False, "reason": "missing", "path": "Z:\\"},
    )
    assert result["state"] == "down"
    assert result["ok"] is False
    assert "not available" in result["detail"]
    assert "ConnectToHomeSan.ps1" in result["detail"]
    assert "connectDrive.bat" in result["detail"]


def test_nas_down_on_listing_timeout():
    result = _run(NAS, list_error=TimeoutError())
    assert result["state"] == "down"
    assert "Timed out" in result["detail"]


def test_nas_status_ignores_smb_failure():
    result = _run(
        NAS,
        list_result={"ok": True, "reason": "listed", "path": "Z:\\", "count": 2},
        smb={"ok": False, "host": "10.42.0.30", "port": 445, "elapsed_ms": 2, "error": "refused"},
    )
    assert result["state"] == "up"
    assert "SMB 445 not reachable" in result["detail"]


def test_nas_list_target_prefers_path_over_drive():
    label, raw = nas_list_target({"path": "/mnt/nas", "drive": "Z:"})
    assert label == "/mnt/nas"
    assert raw == "/mnt/nas"


def test_nas_linux_path_up_when_listing_succeeds():
    result = _run(
        NAS_LINUX,
        list_result={"ok": True, "reason": "listed", "path": "/mnt/nas", "count": 4},
    )
    assert result["state"] == "up"
    assert "4 item(s) visible on /mnt/nas" in result["detail"]
    assert result["target"] == "/mnt/nas"


def test_nas_linux_path_missing_uses_linux_hint():
    result = _run(
        NAS_LINUX,
        list_result={"ok": False, "reason": "missing", "path": "/mnt/nas"},
    )
    assert result["state"] == "down"
    assert "NAS path /mnt/nas is not available" in result["detail"]
    assert "bind-mounted" in result["detail"]
    assert "ConnectToHomeSan.ps1" not in result["detail"]
