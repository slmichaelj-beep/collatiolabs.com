#!/usr/bin/env bash
# Bring Vera's domain online on the Mac: build Caddy with the Cloudflare DNS plugin (once),
# hand port 443 over from `tailscale serve`, then run Caddy — which fetches a real
# Let's Encrypt cert via DNS-01 and reverse-proxies https://vera.guruu.ai -> 127.0.0.1:8765.
#
#   export CF_API_TOKEN='<your Cloudflare token>'   # must be an "Edit zone DNS" token for guruu.ai
#   bash scripts/run-caddy.sh
#
# (The Anima server must be running separately: python3 -m anima.server --voice)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${CF_API_TOKEN:?Set CF_API_TOKEN to your Cloudflare 'Edit zone DNS' token first}"
cd "$REPO"

if [ ! -x ./caddy ]; then
  echo "Downloading Caddy with the Cloudflare DNS plugin (one-time, no build tools needed)…"
  case "$(uname -m)" in arm64) A=arm64 ;; x86_64) A=amd64 ;; *) A=amd64 ;; esac
  curl -fsSL "https://caddyserver.com/api/download?os=darwin&arch=${A}&p=github.com/caddy-dns/cloudflare" -o caddy
  chmod +x caddy
fi

echo "Freeing port 443 from tailscale serve (Caddy takes over)…"
tailscale serve --https=443 off 2>/dev/null || true

echo "Starting Caddy for vera.guruu.ai — first run fetches the cert (binds :443 via sudo)…"
exec sudo -E ./caddy run --config deploy/Caddyfile
