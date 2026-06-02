# Anima — Operator Notes (state that lives OUTSIDE the code)

_Last updated: 2026-06-02._

This file exists because each Claude Code session runs in a fresh container whose
only durable memory is this repo. Anything done on the **Mac itself** (installing
software, system setup, network config) is invisible to a future session unless it
is written down here. So: write it down here.

**Never commit secrets** (tokens, passwords). Record *that* a secret exists and how
it's used, not its value.

---

## Host machine
- **Mac:** `lamars-macbook-pro` — Apple Silicon (M4) MacBook Pro. Runs the server.
- Repo lives at `~/collatiolabs.com`.

## Tailscale — DONE (set up 2026-06; confirmed by admin-console screenshot)
- Account: `slmichaelj@gmail.com`.
- Devices on the tailnet:
  - `lamars-macbook-pro` → `100.97.182.66`  (the server host)
  - `iphone181`          → `100.69.246.12`  (the phone)
- This is the private path for reaching Vera from the phone. The tailnet is private
  to these devices — do NOT expose the server on the public internet.

## Running the server for phone access
- Server: `python3 -m anima.server --voice`, default port **8765**, binds
  `127.0.0.1` (localhost-only) unless `--expose` is passed.
- Brain: `ANIMA_MODEL=hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF` (Stheno via Ollama).
- Auth: set **`ANIMA_TOKEN`** to a secret of your choice to require a token
  (the secret itself is NOT stored here). Page is then reached with `?k=<token>`.
- Phone bridge: keep the server on localhost and run **`tailscale serve --bg 8765`**
  on the Mac. That publishes it over **HTTPS** at the Mac's `*.ts.net` MagicDNS name.
  HTTPS is required because the phone microphone (voice dictation) only works in a
  secure context — a plain `http://100.x:8765` would load but block the mic.
- **Live phone URL (set up & confirmed 2026-06-02):**
  `https://lamars-macbook-pro.tailb51e2f.ts.net/` (tailnet `tailb51e2f.ts.net`),
  proxying to `127.0.0.1:8765`. Reach it with `?k=<ANIMA_TOKEN>` appended.
- Undo the bridge: `tailscale serve --https=443 off`.

## Gotchas learned
- In this Mac's **zsh**, pasting lines like `# 2) do a thing` throws
  `parse error near ')'` — interactive comments aren't enabled, so the `)` breaks
  parsing. Give the user clean commands with NO inline `# N)` comments.
