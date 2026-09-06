# Privacy and repository boundaries

## Never commit

- `private/` — live service map, IP rewrite table, secrets, home-lab docs
- `.env`, `private/secrets.env`, passwords, tokens, API keys
- `.venv/`

`.gitignore` already excludes those paths.

## Safe to commit

- `public/` — fictitious examples generated from the private map
- `docs/` — how the monitors work, without live addresses
- application source, `requirements.txt`, `.env.example`

## Masking workflow

1. Keep real hosts in `private/services.yaml`.
2. Keep real-to-fictitious rewrites in `private/ip_map.yaml`.
3. Run `python scripts/generate_public_examples.py` after changing either file.
4. The generator refuses to write `public/` if a real mapped value is still present.

Do not paste live IPs, passwords, or WAN addresses into README files or
into anything under `public/`.
