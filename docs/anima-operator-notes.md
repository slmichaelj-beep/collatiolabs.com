# Anima — Operator Notes (state that lives OUTSIDE the code)

_Last updated: 2026-06-03._

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
- **NOTE (2026-06-03):** this `tailscale serve` `.ts.net` path has been **superseded by
  Caddy on the owned domain `vera.guruu.ai`** (next section). `tailscale serve` for :443
  is now OFF; Tailscale itself is still the tunnel.

## vera.guruu.ai operations — DONE (built 2026-06-03)
Vera now has a real, publicly-trusted HTTPS cert at **`https://vera.guruu.ai/`**, reached
from the phone over Tailscale. **Caddy** terminates TLS (Let's Encrypt via Cloudflare
**DNS-01** — required because the `vera` A-record is the Mac's private Tailscale IP) and
reverse-proxies to Vera on `127.0.0.1:8765`. Full build steps + concepts:
`docs/vera-domain-setup.md`. DNS lives in Cloudflare (Free zone; nameservers
`edward`/`leanna.ns.cloudflare.com`); Tailscale is still the tunnel (Caddy only replaced
`tailscale serve`). **Track B (Headscale on DigitalOcean) was NOT done — optional.**

- **Files (all in the repo):**
  - `deploy/Caddyfile` — the front-door config (reads `{env.CF_API_TOKEN}`; HTTP/3
    disabled via `protocols h1 h2`; access log → `.anima/caddy-access.log`).
  - `scripts/caddy-daemon.sh` — the daemon wrapper: exports `HOME=/var/root`, reads the
    token from `~/.cf-vera-token`, then `exec ./caddy run --config deploy/Caddyfile`.
  - `deploy/ai.vera.caddy.plist` — source for the LaunchDaemon (installed copy at
    `/Library/LaunchDaemons/ai.vera.caddy.plist`); `RunAtLoad` + `KeepAlive` → survives
    reboots and auto-renews the cert. Daemon log → `.anima/caddy.log`.
- **Restart command:** `sudo launchctl kickstart -k system/ai.vera.caddy`
- **Cloudflare token:** "Edit zone DNS" scoped to `guruu.ai` only; stored **ONLY** in
  `~/.cf-vera-token` (chmod 600). Never in git or the plist.
- **URLs:** phone (Tailscale ON) → `https://vera.guruu.ai/` — **auth is currently OFF, so
  no `?k=` token needed.** On the **Mac itself**, use `http://localhost:8765/` (the Mac
  can't reach its own tailnet IP — see gotcha 2 below).
- **DNS records preserved alongside `vera`** (all DNS-only / grey cloud): apex A →
  `76.76.21.21` (Vercel), `www` → `cname.vercel-dns.com`, `pay` →
  `paylinks.commerce.godaddy.com`, `_domainconnect`, `_dmarc`, and the Clerk auth records
  `accounts`/`clerk`/`clkmail`/`clk._domainkey`/`clk2._domainkey`. **Cloudflare's auto-scan
  MISSED the Clerk records — they were re-added by hand. Re-check them if the zone is ever
  re-migrated.**

### vera.guruu.ai gotchas (each cost real time)
1. **NordVPN on the Mac breaks the Tailscale path** — it hijacks the default route and its
   kill-switch drops the tunnel's return traffic, so the phone gets a blank/"not secure"
   page even though Caddy is fine. **Fix: pause NordVPN, or split-tunnel Tailscale to
   bypass it.**
2. **The Mac cannot reach its OWN tailnet IP (`100.97.182.66`)** — a hairpin quirk, so
   `vera.guruu.ai` always times out *from the Mac*. **Test from the phone**; on the Mac use
   `http://localhost:8765/` (or `curl --resolve vera.guruu.ai:443:127.0.0.1 ...`).
3. **launchd runs daemons with no `$HOME`** → Caddy used a relative storage path that
   collided with the `./caddy` binary. **Fix: `export HOME=/var/root` in
   `scripts/caddy-daemon.sh`** (already in place).

## Gotchas learned
- In this Mac's **zsh**, pasting lines like `# 2) do a thing` throws
  `parse error near ')'` — interactive comments aren't enabled, so the `)` breaks
  parsing. Give the user clean commands with NO inline `# N)` comments.
