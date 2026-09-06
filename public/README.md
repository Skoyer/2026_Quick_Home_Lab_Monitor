# Public examples

Files in this folder are safe to publish. They use fictitious addresses
from `private/ip_map.yaml`, never the live home-lab map.

- `services.example.yaml` — masked copy of the local service list
- `ip_map.example.yaml` — mapping file shape, with made-up source IPs
- `docs/home-lab-architecture.example.md` — invented lab diagram

Copy `services.example.yaml` to `private/services.yaml` on a new machine,
then put real hosts only in `private/`.
