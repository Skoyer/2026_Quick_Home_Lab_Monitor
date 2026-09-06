# Example home lab architecture (public)

This is a fictitious example for the GitHub repository. Real addresses,
passwords, and inventory live only in the local `private/` folder.

## Example LAN

- Network: `10.42.0.0/24`
- Monitoring dashboard: workstation bound to `127.0.0.1:8080`

## Example services

| Service | Example address | Health check |
| --- | --- | --- |
| LM Studio | `http://10.42.0.10:1234` | `GET /v1/models` |
| Ollama | `http://10.42.0.20:11434` | `GET /api/version` |

## Internet reachability

The dashboard probes a few public HTTPS endpoints and treats the check
as healthy when a configured majority succeed.
