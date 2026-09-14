# Task brief for the browser-capable session (Claude-in-Chrome / Cowork)

> ## STATUS (2026-06-03): TRACK A COMPLETE — `vera.guruu.ai` is live with valid HTTPS
> **Track A below is DONE.** `guruu.ai` nameservers now point to Cloudflare
> (`edward`/`leanna.ns.cloudflare.com`), Cloudflare hosts the DNS (Free zone), and
> `vera` A → `100.97.182.66` (the Mac's Tailscale IP, DNS-only / grey cloud). **Caddy**
> terminates TLS with a real Let's Encrypt cert (Cloudflare **DNS-01**, required because
> the A-record is a private IP) and reverse-proxies to Vera on `127.0.0.1:8765`. Caddy
> runs as a **root launchd daemon** (`ai.vera.caddy`), not a manual `caddy run` —
> survives reboots and auto-renews the cert.
> - **Phone (Tailscale ON):** `https://vera.guruu.ai/` — auth is currently OFF, so **no
>   `?k=` token** is needed.
> - **On the Mac itself:** use `http://localhost:8765/` (the Mac can't reach its own
>   tailnet IP — see gotcha 2).
> - **Tailscale is still the tunnel** — Caddy only replaced `tailscale serve`, not the
>   network. **Track B (Headscale on DigitalOcean) was NOT done — still optional.**
>
> **The 3 gotchas that cost hours (carry these forward):**
> 1. **NordVPN on the Mac breaks the Tailscale path** — it hijacks the default route and
>    its kill-switch drops the tunnel's return traffic, so the phone gets a
>    blank/"not secure" page. **Fix: pause NordVPN, or split-tunnel Tailscale to bypass it.**
> 2. **The Mac cannot reach its OWN tailnet IP** (`100.97.182.66`) — a hairpin quirk, so
>    `vera.guruu.ai` always times out *from the Mac*. **Test from the phone**; on the Mac
>    use `http://localhost:8765/` (or `curl --resolve vera.guruu.ai:443:127.0.0.1`).
> 3. **launchd runs daemons with no `$HOME`** → Caddy used a relative storage path that
>    collided with the `./caddy` binary. **Fix: `export HOME=/var/root` in the wrapper.**
>
> **Cloudflare also missed the Clerk auth records on its auto-scan** — `accounts`,
> `clerk`, `clkmail`, `clk._domainkey`, `clk2._domainkey` had to be **re-added manually**
> (along with the pre-existing Vercel apex/www + GoDaddy `pay` + `_domainconnect`/`_dmarc`).
> Re-check these if the zone is ever re-migrated.
>
> The history below is kept for reference; you don't need to re-run Track A.

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
