# Own the network: Headscale + DERP on a DigitalOcean droplet

> **STATUS NOTE (2026-06-03):** This is **Track B** and is **optional / NOT done.** Track A
> (`vera.guruu.ai` HTTPS via Caddy over Tailscale) is **already complete** —
> `docs/vera-domain-setup.md`. Nothing here is required for Vera to work; do it only if you
> want to own the coordination metadata too. (If you ever do, note the `vera` A-record will
> need updating to the Mac's *new* tailnet IP — see step 7.)

This replaces Tailscale-the-company's coordination cloud with your own, on a small
DigitalOcean droplet. The droplet only ever handles **encrypted coordination + relay**
— it never sees your traffic. Vera and all your data stay on the Mac.

> Versions drift: Headscale's config keys change between releases. Treat the config
> below as a template and diff it against the `config-example.yaml` shipped with the
> exact Headscale version you install.

---

## 0. DNS records (in Cloudflare, once `guruu.ai` nameservers point there)
Add two **A** records, **DNS-only (grey cloud)**, pointing at the droplet's public IP:
- `headscale.guruu.ai` → `<droplet-ip>`   (the coordinator)
- `derp.guruu.ai`      → `<droplet-ip>`   (the relay; same box is fine)

(The app's `vera.guruu.ai` A-record still points at the **Mac's** tailnet IP — see
`vera-domain-setup.md`. Different host on purpose: app on the Mac, coordination on the droplet.)

## 1. Create the droplet
- DigitalOcean → Create → Droplet → **Ubuntu 24.04**, the **$4–6/mo** basic size is plenty.
- Add your SSH key. Note the **public IP**.
- Firewall (DO firewall or `ufw`): allow **22** (ssh), **80** + **443** (Headscale control +
  embedded DERP over HTTPS, and ACME), and **3478/udp** (STUN, for NAT traversal).

## 2. Install Headscale
```bash
ssh root@<droplet-ip>
ARCH=amd64
VER=$(curl -s https://api.github.com/repos/juanfont/headscale/releases/latest | grep -o '"tag_name": "[^"]*' | cut -d'"' -f4)
curl -fsSL -o /usr/local/bin/headscale "https://github.com/juanfont/headscale/releases/download/${VER}/headscale_${VER#v}_linux_${ARCH}"
chmod +x /usr/local/bin/headscale
mkdir -p /etc/headscale /var/lib/headscale
```

## 3. Config — `/etc/headscale/config.yaml` (template)
```yaml
server_url: https://headscale.guruu.ai
listen_addr: 0.0.0.0:443
metrics_listen_addr: 127.0.0.1:9090

noise:
  private_key_path: /var/lib/headscale/noise_private.key
prefixes:
  v4: 100.64.0.0/10
  v6: fd7a:115c:a1e0::/48

# Your OWN relay (embedded) — do NOT fall back to Tailscale's public DERP
derp:
  server:
    enabled: true
    region_id: 999
    region_code: "guruu"
    region_name: "Guruu DERP"
    stun_listen_addr: "0.0.0.0:3478"
  urls: []
  paths: []
  auto_update_enabled: false

database:
  type: sqlite
  sqlite:
    path: /var/lib/headscale/db.sqlite

# Headscale gets its own cert (droplet has a public IP + port 80 for the challenge)
tls_letsencrypt_hostname: headscale.guruu.ai
tls_letsencrypt_challenge_type: HTTP-01
tls_letsencrypt_cache_dir: /var/lib/headscale/cache

dns:
  magic_dns: true
  base_domain: ts.guruu.ai          # internal device names, e.g. mac.ts.guruu.ai
  nameservers:
    global: [1.1.1.1, 9.9.9.9]
```

## 4. Run it as a service
```bash
headscale serve   # test in the foreground first; Ctrl-C when it's serving cleanly
# then install the unit shipped in the release, or:
cat >/etc/systemd/system/headscale.service <<'EOF'
[Unit]
Description=headscale
After=network.target
[Service]
ExecStart=/usr/local/bin/headscale serve
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF
systemctl enable --now headscale
```

## 5. A user + a reusable pre-auth key
```bash
headscale users create lamar
headscale preauthkeys create -u lamar --reusable --expiration 720h
# copy the key it prints
```

## 6. Point your devices at YOUR coordinator
- **Mac:** install Tailscale (brew or the app), then:
  ```bash
  sudo tailscale up --login-server https://headscale.guruu.ai --authkey <key>
  tailscale ip -4      # the Mac's new tailnet IP -> use this in the vera.guruu.ai A record
  ```
- **iPhone:** Tailscale app → tap your account → **Use custom coordination server** →
  `https://headscale.guruu.ai` → sign in with the same auth key.
- Verify on the droplet: `headscale nodes list` shows both devices.

## 7. App TLS still lives on the Mac
Follow `vera-domain-setup.md`: Caddy on the Mac terminates TLS for `vera.guruu.ai`
(so the droplet never sees your plaintext). Update the `vera` A-record to the Mac's
**new** tailnet IP from step 6.

---

## Who sees what (the point of all this)
- **Droplet (Headscale + DERP):** encrypted coordination + relay metadata. Never plaintext.
- **Mac (Vera + Caddy):** your data, your conversations, the TLS endpoint. Never leaves.
- **No third party** in either the data path or the coordination path.

## The honest maintenance cost
You now keep alive: a droplet, Headscale, the embedded DERP, Cloudflare DNS, and two
sets of certs (Headscale's + the Mac's Caddy). All can expire or drift. Worth it for
total sovereignty on *your* setup; too heavy to put on every end-user — ship them
Tailscale-free and keep this as your own.
