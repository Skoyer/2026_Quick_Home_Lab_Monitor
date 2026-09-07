# Privacy and repository boundaries

## Never commit

- `private/` — live service map, IP rewrite table, screenshot extras, secrets, home-lab docs
- `.env`, `private/secrets.env`, passwords, tokens, API keys (including `KUMA_API_KEY`)
- `.venv/`

`.gitignore` already excludes those paths.

## Safe to commit

- `public/` — fictitious examples generated from the private map
- `docs/` — how the monitors work, without live addresses
- application source, `requirements.txt`, `.env.example`
- tests that feed example RFC1918 addresses **into** the screenshot sanitizer

## Masking workflow (GitHub tree)

1. Keep real hosts in `private/services.yaml`.
2. Keep real-to-fictitious rewrites in `private/ip_map.yaml` (`10.42.0.x` public examples).
3. Keep screenshot extras (share names, hostnames, usernames) in `private/obfuscate.yaml`.
4. Run `python scripts/generate_public_examples.py` after changing the service list or IP map.
5. The generator refuses to write `public/` if a real mapped value is still present.

## Screenshot Obfuscate mode (dashboard)

This is separate from the GitHub `10.42.0.x` map. Turn **Obfuscate** ON
before a screenshot, or call `GET /api/status?obfuscate=1` (header
`X-Obfuscate: 1` also works). The UI stores the toggle in `localStorage`
and shows a banner so `192.x.y.10` is not mistaken for a live address.

Masked in the JSON and therefore in the UI:

- RFC1918 IPv4: `192.168.a.b` → `192.x.y.b` (last octet kept); `10.*` →
  `10.x.y.<last>`; `172.16–31.*` → `172.x.y.<last>`
- Windows UNC and SMB share names (drive letter `Z:` stays)
- Inventory hostnames and usernames from `private/obfuscate.yaml` and
  non-IP keys in `private/ip_map.yaml`
- Kuma monitor LAN hints: `Orbi Main (55.14)` → `Orbi Main (x.y.14)`
- `detail`, LM Studio `summary`, probe URLs, and monitor names

Not masked (needed for the screenshot to make sense):

- Service names (LM Studio, Ollama, NAS, Internet, Uptime Kuma)
- Model names, well-known ports, public Google/Cloudflare URLs
- Counts, up/down, uptime percentages, `ping_ms`

Do not paste live IPs, passwords, share names, or WAN addresses into
README files or into anything under `public/`. NAS credentials stay in
the existing PowerShell SAN config, not this repository. A Kuma public
status-page slug such as `ping-networkinfrastructure` is not an IP and
is safe to mention in docs.
