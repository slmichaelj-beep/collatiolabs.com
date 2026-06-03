# Task brief for the browser-capable session (Claude-in-Chrome / Cowork)

You have a **browser tool** and access to Lamar's **logged-in Chrome** and accounts. The
prior *code* session (Claude Code on the web) built and shipped all of Vera's code but
**has no browser** — so the **dashboard/account work below was left for you.** Everything
is committed on branch `claude/personality-engine-memory-y7SEW` (PR #1).

**Before you start:** read `docs/HANDOFF.md` for the full system picture, and
`docs/vera-domain-setup.md` + `docs/self-hosting-digitalocean.md` for the detailed steps
this brief summarizes.

**Accounts in play (Lamar is logged in):** GoDaddy (registrar), Cloudflare (will host DNS),
DigitalOcean (optional droplet). Domain chosen: **`vera.guruu.ai`** (a subdomain of the
unused `guruu.ai`).

**Ground rules (important):**
- **Confirm with Lamar before anything irreversible** — DNS nameserver changes, creating a
  paid droplet, deleting records. Show what you're about to do first.
- **Do NOT touch unrelated tabs** (unemployment/job forms, email, banking). Stay on the
  GoDaddy/Cloudflare/DigitalOcean tabs for this task only.
- Vera's data lives on the Mac and must stay there — you are setting up the *network +
  cert*, never moving her data anywhere.

---

## TRACK A — required: give Vera valid HTTPS at `vera.guruu.ai`
Goal: the phone reaches `https://vera.guruu.ai` with a real cert, so the **mic and Face ID**
work. (Today she's on Tailscale's free `.ts.net` cert, which works — this is the "owned
domain" upgrade.)

1. **Cloudflare — add the zone & get nameservers.**
   - dash.cloudflare.com → **Add a site** → `guruu.ai` → **Free** plan → Continue.
   - It scans existing DNS (guruu.ai is unused — little/nothing to keep). Continue.
   - **Copy the two nameservers** it shows (e.g. `x.ns.cloudflare.com`, `y.ns.cloudflare.com`).

2. **GoDaddy — point the domain at Cloudflare.** *(confirm with Lamar first)*
   - dcc.godaddy.com → `guruu.ai` → **Domain Settings → Nameservers → Change** →
     "I'll use my own nameservers" → paste Cloudflare's two → **Save** (Authy will prompt).
   - Back in Cloudflare: **Done, check nameservers.** Wait until the zone shows **Active**
     (minutes–hours).

3. **Cloudflare — DNS record + API token.**
   - DNS → **Add record**: **A**, name **`vera`**, value = the Mac's **Tailscale IP**
     (run `tailscale ip -4` on the Mac to get it; today it's `100.97.182.66`),
     **Proxy status: DNS only (grey cloud)**.
   - My Profile → **API Tokens → Create Token → "Edit zone DNS"** → Zone: **guruu.ai** →
     Create → **copy the token** (for Caddy).

4. **Mac Terminal — Caddy (valid cert + reverse proxy).**
   ```bash
   brew install xcaddy
   xcaddy build --with github.com/caddy-dns/cloudflare      # -> ./caddy
   ```
   Create `Caddyfile`:
   ```
   vera.guruu.ai {
       tls { dns cloudflare PASTE_CLOUDFLARE_TOKEN }
       reverse_proxy 127.0.0.1:8765
   }
   ```
   ```bash
   tailscale serve --https=443 off          # Caddy takes over :443
   sudo ./caddy run --config Caddyfile      # gets the Let's Encrypt cert via DNS-01
   ```

5. **Verify.** With the Vera server running, open on the phone (Tailscale on):
   `https://vera.guruu.ai/?k=<ANIMA_TOKEN>` → padlock valid → mic + Face ID work.
   Update the saved/home-screen URL to this.

**Done with Track A** = Lamar has an owned, valid-HTTPS home for Vera.

---

## TRACK B — optional: own the network too (Headscale on DigitalOcean)
Only if Lamar wants to remove Tailscale-the-company from coordination. Full steps in
`docs/self-hosting-digitalocean.md`; summary:

1. **DigitalOcean** *(confirm — this is a paid droplet)*: create an **Ubuntu 24.04** basic
   droplet (~$4–6/mo). Note the public IP. Open ports 22, 80, 443, 3478/udp.
2. **Cloudflare**: A-records (grey cloud) `headscale.guruu.ai` and `derp.guruu.ai` → droplet IP.
3. **Droplet**: install Headscale, drop in the config from the doc (embedded DERP, HTTP-01
   TLS), `systemctl enable --now headscale`, create a user + reusable pre-auth key.
4. **Re-point clients**: on Mac + iPhone, `tailscale up --login-server https://headscale.guruu.ai --authkey <key>`. Then `tailscale ip -4` on the Mac → **update the `vera` A-record** to the new IP.
5. Track A's Caddy on the Mac still terminates TLS (never on the droplet — the droplet must
   never see plaintext).

---

## When you finish
- Tell Lamar the final phone URL and confirm mic + Face ID work over it.
- If you changed the Mac's tailnet IP (Track B), make sure the `vera` DNS A-record and
  `docs/anima-operator-notes.md` are updated.
- The code session can keep building Vera; this brief is only the browser/account half.
