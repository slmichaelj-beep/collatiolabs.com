#!/usr/bin/env bash
# Caddy front door for vera.guruu.ai, run as a root launchd daemon (binds :443).
# The Cloudflare DNS-01 token is read at runtime from the user's 0600 file, so the
# secret never lives in this script, in the .plist, or in git.
set -euo pipefail
# launchd starts daemons with no $HOME; Caddy then falls back to a relative "caddy/"
# data path that collides with the ./caddy binary. Pin HOME so its storage is absolute
# (/var/root/Library/Application Support/Caddy) — same place the manual run cached the cert.
export HOME=/var/root
export CF_API_TOKEN="$(cat /Users/lamarmichael/.cf-vera-token)"
cd /Users/lamarmichael/collatiolabs.com
exec ./caddy run --config deploy/Caddyfile
