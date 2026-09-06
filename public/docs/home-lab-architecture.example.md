# Example home lab architecture (public)

This is a fictitious example for the GitHub repository. Real addresses,
passwords, and inventory live only in the local `private/` folder.

## Example LAN

- Network: `10.42.0.0/24`
- Monitoring dashboard: workstation bound to all interfaces (`0.0.0.0:8000`); LAN clients use `http://10.42.0.10:8000`

## Example services

| Service | Example address | Health check |
| --- | --- | --- |
| LM Studio | `http://10.42.0.10:1234` | `GET /v1/models` |
| Ollama | `http://10.42.0.20:11434` | `GET /api/version` |
| NAS files | `Z:` → `\\10.42.0.30\shared` | Mapped drive listing |

## Internet reachability

The dashboard probes a few public HTTPS endpoints and treats the check
as healthy when a configured majority succeed.

## NAS files

The example share is a mapped `Z:` drive on `\\10.42.0.30\shared`.
The dashboard lists that drive; it does not store NAS credentials.
Reconnect the share with your existing PowerShell/login script if the
drive is missing.
