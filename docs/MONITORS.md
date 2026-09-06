# Monitors

The dashboard binds using `dashboard.host` and `dashboard.port` in
`private/services.yaml` (defaults: `0.0.0.0` on port `8000`) so LAN
clients can open the UI. There is no login.

The dashboard runs four built-in reachability checks. Add more HTTP
services by appending entries to `private/services.yaml`. The NAS check
is a separate `nas:` block in that same file.

## Can I Reach the Internet

Sends HTTPS GET requests to a short list of public endpoints. A check is
**up** when every probe succeeds, **degraded** when the configured
majority succeed, and **down** otherwise.

Current probes:

- `https://www.google.com/generate_204` (HTTP 204)
- `https://www.cloudflare.com/cdn-cgi/trace` (HTTP 200)
- `https://1.1.1.1/cdn-cgi/trace` (HTTP 200)

Response bodies are not shown in the UI so WAN addresses from trace
endpoints do not appear on the dashboard.

## Can I see LM Studio

HTTP GET to the OpenAI-compatible models endpoint:

`{scheme}://{host}:{port}/v1/models`

Success is HTTP 200. The card can show the model IDs returned by the
local API.

## Can I see the Ollama Server

HTTP GET to:

`{scheme}://{host}:{port}/api/version`

Success is HTTP 200. The card shows the reported Ollama version when
present.

## Can I see my files on my NAS?

Primary check: the configured mapped drive (typically `Z:`) exists and
a directory listing succeeds. That is “I can see files.” An empty but
readable drive still counts as up. A missing, denied, or hung listing
is down.

If the drive is missing, the card tells you to reconnect with
`ConnectToHomeSan.ps1` or `connectDrive.bat`. The dashboard does **not**
run `net use` and does **not** load NAS credentials. Those stay in the
existing PowerShell SAN config, not this repository.

An optional TCP probe to SMB (port 445) can appear as extra detail when
a share host is configured. It does not decide the overall status.

The listing runs in a worker thread with a short timeout so a hung
share cannot freeze the other checks.
