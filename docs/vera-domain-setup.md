# Giving Vera a real home: `vera.guruu.ai` (valid HTTPS, mic + Face ID)

> **STATUS: BUILT 2026-06-03 — this is now the AS-BUILT setup, not just a plan.**
> Nameservers are on Cloudflare (`edward`/`leanna.ns.cloudflare.com`), `vera` A →
> `100.97.182.66` (DNS-only), and **Caddy runs as a root launchd daemon
> (`ai.vera.caddy`)** that auto-renews the cert and survives reboots — NOT the manual
> `sudo ./caddy run` shown in older drafts. The Cloudflare token lives only in
> `~/.cf-vera-token` (chmod 600). Read **§7 (gotchas)** before debugging — two of the
> three (NordVPN, the Mac's own-IP hairpin) will look like "the cert/Caddy is broken"
> when it isn't.

This points a subdomain of your GoDaddy-registered `guruu.ai` at your Mac, with a real
Let's Encrypt cert — so the phone gets a secure context (required for the microphone and
Face ID). The domain stays registered at GoDaddy; only DNS moves to Cloudflare (free),
because GoDaddy's DNS API is locked on small accounts and Caddy needs API access to
auto-issue the cert.

Vera still binds `127.0.0.1:8765`; **Caddy** sits in front and terminates TLS. All your
data stays on the Mac.

---

## 1. Move `guruu.ai` DNS to Cloudflare (free, ~10 min, keep registration at GoDaddy)
1. Make a free Cloudflare account → **Add a site** → `guruu.ai` → Free plan.
2. Cloudflare scans existing records. **WARNING — the auto-scan is incomplete.** As built,
   `guruu.ai` already hosted a live site + auth, and **Cloudflare's scan MISSED the Clerk
   records.** Verify the imported list and **re-add anything missing before switching**.
   The records that must end up in the zone (all **DNS-only / grey cloud**):
   - apex `@` A → `76.76.21.21` (Vercel) and `www` CNAME → `cname.vercel-dns.com` (the site)
   - `pay` CNAME → `paylinks.commerce.godaddy.com` (GoDaddy pay link)
   - `_domainconnect` and `_dmarc` (TXT) — pre-existing
   - **Clerk auth (the ones the scan dropped — re-add manually):** `accounts`, `clerk`,
     `clkmail`, `clk._domainkey`, `clk2._domainkey`
3. Cloudflare shows **two nameservers** — as built these are
   `edward.ns.cloudflare.com` and `leanna.ns.cloudflare.com`.
4. In **GoDaddy → guruu.ai → Nameservers → Change → "I'll use my own"**, paste the two
   Cloudflare nameservers. Save. (Propagation: minutes to a couple hours.)

## 2. Point `vera.guruu.ai` at the Mac's tailnet IP
In **Cloudflare → guruu.ai → DNS → Add record**:
- Type **A**, Name **`vera`**, IPv4 **`100.97.182.66`** (the Mac's Tailscale IP — from
  `tailscale ip -4` on the Mac; update this if it ever changes).
- **Proxy status: DNS only (grey cloud, NOT orange).** Cloudflare can't proxy a private
  `100.x` address, and you only want your tailnet devices reaching it.

Only devices on your tailnet can route `100.x`, so this name is useless to anyone else —
which is what we want.

## 3. A Cloudflare API token for the cert
Cloudflare → **My Profile → API Tokens → Create Token → "Edit zone DNS"** template →
Zone Resources: **Include → Specific zone → guruu.ai** → Create. **Copy the token.**

**As built, the token is stored ONLY in `~/.cf-vera-token` (chmod 600) — never in git,
the Caddyfile, or the plist.** The daemon reads it at runtime and exports it as
`$CF_API_TOKEN`; the `Caddyfile` references `{env.CF_API_TOKEN}`. (The token is scoped to
`guruu.ai` only, so it's low-risk, but keep it out of any committed file.)

## 4. Caddy on the Mac (gets + renews the cert, fronts Vera)
Caddy needs the Cloudflare DNS plugin (the stock binary doesn't include it). Easiest:
```bash
brew install xcaddy
xcaddy build --with github.com/caddy-dns/cloudflare    # produces ./caddy
```
(Or download a build with the `caddy-dns/cloudflare` module from caddyserver.com/download.)

**As built, the `Caddyfile` lives at `deploy/Caddyfile`** and reads the token from the
environment (set by the daemon wrapper from `~/.cf-vera-token`), so no secret is in the
file. It also **disables HTTP/3** — iOS Safari prefers h3/QUIC, which is unreliable across
the Tailscale tunnel and yields a blank page; TCP (h1/h2) carries fine:
```
{
    servers { protocols h1 h2 }     # HTTP/3 OFF — see gotcha 1
}
vera.guruu.ai {
    tls {
        dns cloudflare {env.CF_API_TOKEN}
        resolvers 1.1.1.1 8.8.8.8    # don't let a slow local resolver stall DNS-01
        propagation_delay 30s
        propagation_timeout 5m
    }
    reverse_proxy 127.0.0.1:8765
    log { output file /Users/lamarmichael/collatiolabs.com/.anima/caddy-access.log }
}
```
Caddy proves domain control via a DNS-01 TXT record (Cloudflare API), gets a valid
Let's Encrypt cert for `vera.guruu.ai`, listens on :443, and proxies to Vera on :8765.
**DNS-01 is mandatory here** — the A-record is a private `100.x` IP, so HTTP-01 can never
reach it from the public ACME server.

## 5. Run Caddy as a persistent launchd daemon (NOT a manual `caddy run`)
As built, Caddy is **not** started by hand — it runs as a **root LaunchDaemon** so it
binds :443, survives reboots, and auto-renews the cert:
- **Label:** `ai.vera.caddy`
- **Plist:** `/Library/LaunchDaemons/ai.vera.caddy.plist` (source kept at
  `deploy/ai.vera.caddy.plist`), with `RunAtLoad` + `KeepAlive` so it restarts itself and
  starts on boot.
- **Wrapper it runs:** `scripts/caddy-daemon.sh`, which:
  - `export HOME=/var/root` — **REQUIRED.** launchd starts daemons with no `$HOME`, and
    without this Caddy falls back to a relative `caddy/` storage path that collides with
    the `./caddy` binary (see gotcha 3).
  - `export CF_API_TOKEN="$(cat ~/.cf-vera-token)"` — pulls the token from the 0600 file.
  - `cd ~/collatiolabs.com && exec ./caddy run --config deploy/Caddyfile`.

Install once (`sudo cp deploy/ai.vera.caddy.plist /Library/LaunchDaemons/ && sudo
launchctl load /Library/LaunchDaemons/ai.vera.caddy.plist`), then **restart with:**
```bash
sudo launchctl kickstart -k system/ai.vera.caddy
```
Caddy replaces `tailscale serve` for :443 — but **Tailscale is still the tunnel** (only
`serve` was turned off, not the network).

## 6. Open on the phone
**Auth is currently OFF** (no `ANIMA_TOKEN` set), so the URL needs **no `?k=` token**.
On the phone (Tailscale on):
```
https://vera.guruu.ai/
```
On the **Mac itself**, do NOT use the domain (it times out — gotcha 2); use:
```
http://localhost:8765/
```
Valid cert ⇒ the mic works and **Face ID** can enroll/unlock. The app needed zero
changes — its Face-ID `rp_id` is read from the Host header, so it's now bound to
`vera.guruu.ai`. (To re-enable auth later, restart Vera with `ANIMA_TOKEN` **and** the
existing `ANIMA_KEY`, then append `?k=<token>`.)

## 7. The 3 gotchas (each cost real debugging time)
1. **NordVPN on the Mac breaks the Tailscale path.** Nord hijacks the default route and
   its kill-switch drops the tunnel's return traffic, so the phone gets a blank /
   "not secure" page even though Caddy and the cert are fine. **Fix: pause NordVPN, or
   split-tunnel Tailscale so it bypasses Nord.** (This — not HTTP/3 — was the real cause of
   "the phone can't load the page.")
2. **The Mac cannot reach its OWN tailnet IP (`100.97.182.66`).** A hairpin quirk:
   `https://vera.guruu.ai` and `curl` from the Mac **always time out**, which looks like
   Caddy is down when it's fine. **Test from the phone.** On the Mac, hit Vera directly at
   `http://localhost:8765/`, or test the cert path with
   `curl --resolve vera.guruu.ai:443:127.0.0.1 https://vera.guruu.ai/`.
3. **launchd daemons run with no `$HOME`.** Caddy then used a relative `caddy/` storage
   path that collided with the `./caddy` binary ("not a directory"). **Fix:
   `export HOME=/var/root` in `scripts/caddy-daemon.sh`** (already done) so storage is
   absolute (`/var/root/Library/Application Support/Caddy`).

---

## Recap of who does what
- **GoDaddy** — registrar only (owns the name).
- **Cloudflare** — DNS host (free) + the API Caddy uses to prove domain control.
- **Tailscale** — the encrypted WireGuard path between phone and Mac. (Headscale —
  "Track B", `self-hosting-digitalocean.md` — was **NOT** done; still optional.)
- **Caddy** — TLS termination + reverse proxy, run as the `ai.vera.caddy` launchd daemon
  (replaces `tailscale serve`).
- **Vera** — unchanged, still `127.0.0.1:8765`, all data on the Mac.

If `vera.guruu.ai` ever shows a cert error or won't load, check in this order: (a) **is
NordVPN running on the Mac?** pause it (gotcha 1); (b) are you testing **from the Mac**?
the Mac can't reach its own tailnet IP — use the phone (gotcha 2); (c) is the daemon up?
`sudo launchctl kickstart -k system/ai.vera.caddy` and check `.anima/caddy.log`; (d)
nameservers not yet propagated; (e) the API token not scoped to `guruu.ai`.
