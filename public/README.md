# Public examples

Files in this folder are safe to publish. They use fictitious addresses
from `private/ip_map.yaml`, never the live home-lab map.

- `services.example.yaml` — masked copy of the local service list
- `ip_map.example.yaml` — mapping file shape, with made-up source IPs
- `obfuscate.example.yaml` — extra screenshot-mode replacements (fake share/hostname/user only; live Obfuscate mode rewrites RFC1918 to `192.x.y.z`, not `10.42.0.x`)
- `docs/home-lab-architecture.example.md` — invented lab diagram (includes example Uptime Kuma on mcp-01 at `10.42.0.40` with status page slug `ping-networkinfrastructure`; Orbi names without last-octet IPs)

Copy `services.example.yaml` to `private/services.yaml` on a new machine,
then put real hosts only in `private/`. Optionally copy
`obfuscate.example.yaml` to `private/obfuscate.yaml` and add real share
names and hostnames so screenshot mode can mask them.
