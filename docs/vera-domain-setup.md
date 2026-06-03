# Giving Vera a real home: `vera.guruu.ai` (valid HTTPS, mic + Face ID)

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
2. Cloudflare scans existing records. **`guruu.ai` is unused, so there's little/nothing
   to lose — but glance at the imported list** and re-add anything you care about
   (especially MX/email) before switching.
3. Cloudflare shows **two nameservers** (e.g. `xxx.ns.cloudflare.com`).
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

## 4. Caddy on the Mac (gets + renews the cert, fronts Vera)
Caddy needs the Cloudflare DNS plugin (the stock binary doesn't include it). Easiest:
```bash
brew install xcaddy
xcaddy build --with github.com/caddy-dns/cloudflare    # produces ./caddy
```
(Or download a build with the `caddy-dns/cloudflare` module from caddyserver.com/download.)

Create a `Caddyfile` (next to the binary):
```
vera.guruu.ai {
    tls {
        dns cloudflare YOUR_CLOUDFLARE_API_TOKEN
    }
    reverse_proxy 127.0.0.1:8765
}
```
Run it (binding :443 needs sudo):
```bash
sudo ./caddy run --config Caddyfile
```
Caddy proves domain control via a DNS-01 TXT record (Cloudflare API), gets a valid
Let's Encrypt cert for `vera.guruu.ai`, listens on :443, and proxies to Vera on :8765.

## 5. Turn off `tailscale serve` (Caddy owns :443 now)
```bash
tailscale serve --https=443 off
```

## 6. Start Vera as usual, open on the phone
```bash
cd ~/collatiolabs.com
ANIMA_TOKEN='vera2026' ANIMA_MODEL=hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF python3 -m anima.server --voice
```
On the phone (Tailscale on):
```
https://vera.guruu.ai/?k=vera2026
```
Valid cert ⇒ the mic works and **Face ID** can enroll/unlock. The app needed zero
changes — its Face-ID `rp_id` is read from the Host header, so it's now bound to
`vera.guruu.ai`.

---

## Recap of who does what
- **GoDaddy** — registrar only (owns the name).
- **Cloudflare** — DNS host (free) + the API Caddy uses to prove domain control.
- **Tailscale/Headscale** — the encrypted WireGuard path between phone and Mac.
- **Caddy** — TLS termination + reverse proxy (replaces `tailscale serve`).
- **Vera** — unchanged, still `127.0.0.1:8765`, all data on the Mac.

If `vera.guruu.ai` ever shows a cert error, it's almost always (a) nameservers not yet
propagated, (b) the API token not scoped to `guruu.ai`, or (c) Caddy not allowed to bind
:443 (run with sudo).
