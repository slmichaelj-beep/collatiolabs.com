#!/usr/bin/env bash
# Bring Vera all the way up with ONE command — no tab/venv/token juggling.
#
#   bash scripts/up.sh                 # fastest: serves her over Tailscale (free .ts.net HTTPS)
#   CF_API_TOKEN='cfut_…' bash scripts/up.sh   # serve at https://vera.guruu.ai via Caddy
#
# It picks the Python that actually has her libraries, starts her server on :8765
# in the background (logs to .anima/server.log), then puts HTTPS in front of it.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# 1) Find a Python that can import her deps — never another app's venv.
PY=""
for c in /opt/homebrew/bin/python3 venv/bin/python3 .venv/bin/python3 "$(command -v python3 || true)"; do
  if [ -n "$c" ] && [ -x "$c" ] && "$c" -c 'import numpy' >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "✗ No Python with Vera's libraries found."
  echo "  Install them:  /opt/homebrew/bin/pip3 install -r requirements.txt -r anima/requirements-voice.txt"
  exit 1
fi
echo "→ Python: $PY"

# 2) Start her server on :8765 if it isn't already answering.
if curl -s -o /dev/null --max-time 2 http://127.0.0.1:8765/ ; then
  echo "→ Server already up on :8765."
else
  mkdir -p .anima
  echo "→ Starting Vera's server (with voice) in the background → .anima/server.log"
  nohup "$PY" -m anima.server --voice >> .anima/server.log 2>&1 &
  for i in 1 2 3 4 5 6 7 8; do
    sleep 1
    curl -s -o /dev/null --max-time 2 http://127.0.0.1:8765/ && { echo "  ✓ server up"; break; }
    [ "$i" = 8 ] && echo "  ⚠ not answering yet — tail .anima/server.log to see why"
  done
fi

# 3) Put HTTPS in front. Caddy (custom domain) if a token is set, else Tailscale serve.
if [ -n "${CF_API_TOKEN:-}" ]; then
  echo "→ CF_API_TOKEN set — bringing up Caddy for https://vera.guruu.ai"
  exec bash scripts/run-caddy.sh
else
  echo "→ No CF_API_TOKEN — serving over Tailscale (free, instant, valid HTTPS)."
  tailscale serve --bg --https=443 http://127.0.0.1:8765 2>/dev/null \
    || tailscale serve --bg https / http://127.0.0.1:8765 2>/dev/null \
    || tailscale serve https:443 http://127.0.0.1:8765
  echo
  echo "✓ Vera is served. Your phone URL (Tailscale must be ON on the phone):"
  tailscale serve status 2>/dev/null || true
  echo "  (To use https://vera.guruu.ai instead, re-run with CF_API_TOKEN set.)"
fi
