# Self-hosting the network (Headscale) — owning the whole stack

_Goal: reach Vera on your phone from anywhere, with the same WireGuard encryption as
Tailscale, but with **no third-party coordination server**. You run the control plane._

This keeps the project's promise: nothing — not even your device/coordination
metadata — depends on a company. Same WireGuard data plane, you own the rest.

## The honest trade vs. Tailscale
Tailscale gives two conveniences for free that you now run yourself:

1. **Coordination + NAT traversal** → **Headscale** (open-source Tailscale control
   server) + optionally your own **DERP relay** for hole-punching from CGNAT/cellular.
2. **Public HTTPS cert** (`tailscale serve` on a `.ts.net` name) → **Caddy** + a
   **domain you own**. This part is *mandatory* for Vera: the phone microphone and
   Face ID both require a valid-HTTPS secure context. Plain `http://100.x` won't do.

Everything else (MagicDNS names, the official Tailscale clients, the WireGuard tunnel)
you keep.

## The picture
```
 iPhone (Tailscale client) ──WireGuard──┐
                                        ├── direct, or via your DERP relay
 Mac  (Tailscale client + Vera) ────────┘
   │  control plane: Headscale  (on a public host: cheap VPS, or home + DDNS)
   │  app TLS:       Caddy → reverse-proxy → 127.0.0.1:8765 (Vera)
   └  cert:          Let's Encrypt via Caddy DNS-01, for vera.yourdomain.com
```
One public-reachable host is unavoidable for the control plane (and DERP). A $4–5/mo
VPS is the simplest; a home server with a port forward + dynamic DNS also works.

## Steps

### 1. Control plane — Headscale (on the public host)
- Install Headscale (single Go binary / container). Put **Caddy or nginx** in front
  for TLS on `headscale.yourdomain.com`.
- Create a user and a pre-auth key:
  `headscale users create lamar` · `headscale preauthkeys create -u lamar --reusable`

### 2. (Optional, for CGNAT) self-host a DERP relay
- Run `derper` (from Tailscale's repo) on the same VPS; add it to your Headscale
  config's `derp` section. Now even relayed traffic never touches Tailscale Inc.
  (If you skip this, Headscale can point at Tailscale's public DERP — traffic stays
  end-to-end encrypted, but you'd be using their relays for fallback.)

### 3. Clients — official Tailscale apps, pointed at your server
- Mac: `tailscale up --login-server https://headscale.yourdomain.com --authkey <key>`
- iPhone: Tailscale app → advanced → custom coordination server → your Headscale URL.
- `tailscale status` now shows your devices on *your* tailnet.

### 4. App HTTPS — Caddy on the Mac (this is what makes mic + Face ID work)
- Own a domain; use Caddy's **DNS-01** ACME (no public port needed) to get a real cert
  for `vera.yourdomain.com`. Minimal Caddyfile on the Mac:
  ```
  vera.yourdomain.com {
      tls { dns <your-dns-provider> <api-token> }
      reverse_proxy 127.0.0.1:8765
  }
  ```
- Point `vera.yourdomain.com` at the Mac's tailnet IP (split-horizon DNS, or just a
  host entry on your devices). Open `https://vera.yourdomain.com/?k=<token>` on the
  phone — valid cert ⇒ mic and Face ID work.

## What the app needs: nothing
Vera is portable across whatever you choose:
- The server binds `127.0.0.1:8765`; Caddy fronts it (same as `tailscale serve` did).
- Face ID (WebAuthn) derives its `rp_id`/origin from the **Host header**, so it works
  on `vera.yourdomain.com` exactly as it did on `.ts.net` — no code change.
- The token (`ANIMA_TOKEN`) still gates all data; Face ID is still the second layer.

## Honest tradeoffs
- You now run and maintain: Headscale, (a DERP relay), Caddy, and a domain. More
  moving parts than Tailscale's one-command setup.
- A public-reachable host is required somewhere (VPS or home + DDNS).
- TLS is now your job (Caddy makes it ~3 lines, but it's yours to renew/monitor).
In exchange: no third party in your coordination path — the sovereignty you're after.
