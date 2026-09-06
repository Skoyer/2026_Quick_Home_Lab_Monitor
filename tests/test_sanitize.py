from monitor.sanitize import apply_replacements, leftover_real_values


def test_specific_hosts_are_rewritten():
    text = "http://192.168.1.10:1234 and http://192.168.1.20:11434"
    replacements = {
        "192.168.1.10": "10.42.0.10",
        "192.168.1.20": "10.42.0.20",
        "192.168.1.": "10.42.0.",
    }
    masked = apply_replacements(text, replacements)
    assert masked == "http://10.42.0.10:1234 and http://10.42.0.20:11434"
    assert leftover_real_values(text, replacements) == []


def test_nas_unc_and_ip_are_masked():
    text = r"Drive Z: maps to \\192.168.1.30\labshare on port 445"
    replacements = {
        "192.168.1.30": "10.42.0.30",
        "192.168.1.10": "10.42.0.10",
        "192.168.1.20": "10.42.0.20",
        "labshare": "shared",
        "192.168.1.": "10.42.0.",
    }
    masked = apply_replacements(text, replacements)
    assert masked == r"Drive Z: maps to \\10.42.0.30\shared on port 445"
    assert leftover_real_values(text, replacements) == []
    assert leftover_real_values(
        r"\\192.168.1.30\labshare",
        {"192.168.1.30": "192.168.1.30"},
    ) == ["192.168.1.30"]
