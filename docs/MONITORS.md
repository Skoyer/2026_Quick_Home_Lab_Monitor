# Monitors

The dashboard runs three built-in reachability checks. Add more services
by appending entries to `private/services.yaml`.

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
