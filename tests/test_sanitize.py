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
