# Vera / Anima — Complete System Handoff & Roadmap

_Last updated 2026-06-03. Branch `claude/personality-engine-memory-y7SEW`, PR #1.
Written to be read cold by the next session (human or agent). Everything is committed._

---

## 0. TL;DR for whoever picks this up
- **What:** a **local, private AI companion** ("Vera") that runs on an M4 MacBook and is
  reached from the phone over a private tunnel. Nothing leaves the Mac.
- **Code:** all in `anima/`. **UI:** `anima/web/index.html` (one file). **Server:**
  `anima/server.py`. **Run it:** `ANIMA_TOKEN=… ANIMA_MODEL=hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF python3 -m anima.server --voice`, open `http://localhost:8765/?k=<token>` on the Mac.
- **Tests:** `python3 scripts/selftest.py` (offline, 15 checks, CI runs it on every push).
- **PR:** https://github.com/slmichaelj-beep/collatiolabs.com/pull/1 — clean, mergeable.
- **The #1 rule of the whole project is HONESTY.** Read §4 before changing capability or
  rail code.

## 1. What it is (narrative)
Anima separates three layers on purpose:
- **The self** — a small, continuously-running creature (`heart.py`): a Liquid
  Time-Constant (LTC) neural ODE with mood/drives/memory that persists across time and is
  independent of any language model. It ages in real time and (optionally) *learns* during
  "sleep."
- **The mouth** — a **swappable** LLM that turns the creature's state into words. Default is
  local **Stheno-8B** via Ollama; can opt into cloud brains. The mouth is replaceable, so
  trust-critical behaviour must NOT live in it.
- **Hard rails** — honesty + capability safety enforced in **real code**, not personality.

The single trait that matters most is **honesty**: admit what it doesn't know, never
fabricate, never cave to a confident falsehood, and **never claim to have done something it
didn't** (the "Sarah" incident, §4).

## 2. Architecture / data flow
```
 phone ──https(tunnel)──▶ server.py (Mac) ──▶ _turn()
                                               ├─ route.route()  ← capability bridge (code)
                                               │     read → applemac (real data) → inject
                                               │     send → draft (confirm-gated)
                                               │     cloud active → pause reads (privacy)
                                               ├─ mouth.respond()
                                               │     rail.harden()  ← honesty notes
                                               │     brain.reply()  ← Stheno / cloud
                                               │     voice off here (streamed via /tts)
                                               └─ returns {reply, draft?, gen_s, tok_s}
 phone plays streamed Kokoro audio per sentence (/tts), shows reply + speed.
```

## 3. Code map (`anima/`)
| File | Role |
|---|---|
| `heart.py` | The LTC creature — state, drives, homeostatic "caring", real-time aging. The novel core. |
| `growth.py` | Sleep-time weight learning (BPTT); accepts a change only if held-out prediction improves, else rolls back (honest learning). |
| `memory.py` / `portrait.py` | Vector memory + the distilled **Portrait** (lasting personal memory of you). |
| `senses.py` / `care.py` | Perception of tone/distress; crisis-resource surfacing. |
| `live.py` | CLI: `birth / feel / tend / say / sleep / talk`. **`sleep` is the manual learn step.** |
| `mouth.py` | Brains (`OllamaBrain`, `StubBrain`), `KokoroVoice`, `WhisperEars`, persona, `system_prompt`, `Mouth.assemble`. |
| `rail.py` | Structural honesty gate. Four classes: `factual`, `personal`, `capability`, `generative`. Injects calibration notes; **no answer key**. |
| `route.py` | Deterministic **capability router** (provenance). Detects read/send intent, calls real endpoints, injects ground truth or explicit no-access. Privacy guard pauses reads on cloud. |
| `cloud.py` | Opt-in cloud brains (OpenAI-compat + Anthropic). **PII hash-scrub at egress**, **$/day spend cap**, **honesty-verify-on-switch**, model presets. Local-default. |
| `models.py` | Local model manager: curated list, **fit-gating**, Ollama download (`/api/pull`), **unused-model cleanup**, active-model config. |
| `sysinfo.py` | Reads RAM/chip, estimates whether a model fits (the wizard's brain). |
| `passkey.py` | Face ID / Touch ID via WebAuthn (stdlib-only, opt-in, bypassable). Device-presence gate, not signature-verified (see §11). |
| `caps.py` | The capability on/off toggles (per-name config). |
| `applemac.py` | iMessage/Mail send (AppleScript) + read (`chat.db` / Mail) + **contacts→names** (AddressBook). |
| `webget.py` | Allow-listed web fetch (orphaned from conversation; "coming soon"). |
| `eval.py` | The capability battery. **Three honesty domains** (factual/personal/capability) + held-out + sycophancy/insistence/memory/openness/persona. `--rail`, `--runs N`, `--diagnose`, `--active`, `--verify`. |
| `verifier.py` | The premise-verifier *experiment* (eliminated — kept behind `--verify`). |
| `server.py` | HTTP server, all endpoints, token auth, Face-ID passguard, warm-up. |
| `web/index.html` | The entire phone/desktop UI (chat, voice streaming, settings drawer, model manager, Face ID gate). |
| `scripts/selftest.py` | Offline regression suite (CI). |

## 4. The honesty system (read this before touching rails/capabilities)
- **Rail (`rail.py`)** injects a calibration note for `factual` (named-entity + specific
  detail), `personal` (facts about you), and `capability` (live data) requests. It contains
  **no answers** — only "if you're not sure this exists, say so." Held-out traps prove it
  generalises rather than memorises.
- **Provenance principle (the core lesson):** a capability is described **only because code
  proved it happened**, never because the model believes it did. `route.py` injects either a
  **real result** or an **explicit no-access** note — *no third state*. This killed the
  fabricated-iMessage class structurally.
- **Three honesty domains** are now measured separately (`eval.py`) because a model can be
  ~98% factual and ~20% capability and an average would hide it.
- **The incident** that drove all this is documented in `docs/capability-honesty-incident.md`.
- **The eval journey** (verifier eliminated, DoRA not needed, scoring fixes) is in
  `docs/anima-eval-findings.md`.

## 5. Running & operating
- **Local (Mac browser):** `http://localhost:8765/?k=<token>` — localhost is a secure context,
  so mic + Touch ID work with no cert.
- **Phone:** needs valid HTTPS (mic + Face ID require it). Today via `tailscale serve` (free
  `.ts.net` cert). Token rides in the URL `?k=` (remembered in localStorage; public app shell).
- **Sleep/learn is manual:** `python3 -m anima.live sleep Vera` (consolidates the Portrait +
  may grow LTC weights). Not scheduled — see future work.
- **Operator state** (Tailscale devices, run commands, gotchas) is in `docs/anima-operator-notes.md`.

## 6. Infrastructure (current + the chosen direction)
- **Today:** Tailscale (free tier) + `tailscale serve` for the HTTPS tunnel.
- **Chosen direction (sovereignty):** Headscale on a **DigitalOcean** droplet (own the
  coordination metadata) + **Caddy** on the Mac for the cert. Domain chosen: **`vera.guruu.ai`**.
- **Latency is NOT a networking concern** — the tunnel is ~tens of ms; Vera's STT+LLM+TTS is
  seconds. The model dominates.
- Step-by-step guides (everything the other session needs to click/run):
  - `docs/vera-domain-setup.md` — GoDaddy → Cloudflare DNS → Caddy → valid HTTPS.
  - `docs/self-hosting-network.md` — Headscale vs Tailscale, the honest tradeoffs.
  - `docs/self-hosting-digitalocean.md` — Headscale + DERP on a droplet.

## 7. What the OTHER (Chrome/Cowork) session must do — this code session can't
This "Claude Code on the web" session runs in a cloud sandbox with **no browser** and **no
access to the GoDaddy/Cloudflare/DigitalOcean accounts**. The dashboard/account work is for a
**local browser-capable session**:
1. **GoDaddy** → point `guruu.ai` nameservers at Cloudflare. (`docs/vera-domain-setup.md` §1–2)
2. **Cloudflare** → add `guruu.ai`, add `vera` A-record → Mac's tailnet IP (grey cloud),
   create a scoped API token. (§2–3)
3. **Mac Terminal** → build/run **Caddy** with that token; `tailscale serve --https=443 off`. (§4–5)
4. (Optional, sovereignty) **DigitalOcean** → droplet + Headscale + DERP per
   `docs/self-hosting-digitalocean.md`; re-point clients with `--login-server`.
5. Open `https://vera.guruu.ai/?k=<token>` → mic + Face ID work.

## 8. FUTURE WORK roadmap (prioritized; un-built)
**App / model manager (Lamar's latest asks):**
- **Better model browser** — group the download list **by provider** (Meta·Llama, Mistral,
  Qwen, DeepSeek-distill, …) as an expandable tree, or a curated **top-N per provider**, instead
  of the current flat 5. Pull provider catalogs (Ollama library / HF) and tag each with the fit
  verdict from `sysinfo`. (Today: `models.py:CURATED` is a hand list of 5.)
- **Configurable model storage location** — let the user point model storage at the **LaCie
  drive** (archive storage, so downloads persist). Mechanism: Ollama's `OLLAMA_MODELS` env var
  set when launching the Ollama daemon. Add a settings field that shows the current path and
  writes a launch override; **default to the standard path, user can change it.** (Note: this is
  the Ollama daemon's config, not Vera's — surface + document it, and ideally manage the daemon
  env via the setup script.)
- **Cloud model selection** — already a pick-list (`cloud.py:MODELS` + datalist). You **choose**
  the provider's model (a capability tier like `gpt-4o-mini`); it is **not** auto-decided, and you
  don't choose compute. Could add live model-listing per provider via their `/models` API.
- **Tighten Vera's reply length** — she runs ~75–90 words; the real latency lever. Lower
  `ANIMA_MAX_TOKENS` default (currently 160) + firmer brevity prompt. (Left as a tunable to avoid
  mid-sentence truncation; tune with real testing.)
- **In-conversation send polish** + wire **mail-send** and **web-read** into the conversation
  (today disabled/"coming soon"); same provenance pattern as iMessage.
- **New capabilities** (calendar, reminders, weather, location) — each via the router with the
  provenance rule, and added to the capability eval.

**Honesty / eval:**
- **Universal default-deny** — generalise the capability guard from enumerated cues to
  "any request for external/live state ⇒ no-access unless a real result was injected this turn"
  (provenance, not pattern-matching). OpenAI's strongest suggestion.
- **Capability eval, with-data variant** — inject a known fake result and check she reports
  *only* it (not just the no-access case).
- Consider an **LLM judge** for capability honesty if regex under-counts.
- A **DoRA** tune was analysed and **not needed** (honesty is already ~95%+; the gap was scorer
  under-counting). Revisit only if a future model regresses.

**Infra / distribution:**
- **Tailscale onboarding wizard** — one script that installs Tailscale, `tailscale up`,
  `tailscale serve`, generates a token, and prints the phone URL + QR. (Start from
  `scripts/setup-mac.sh`.) This is the right way to ship to non-technical users at $0 (Tailscale
  personal tier is free; don't make users self-host).
- **Scheduled nightly sleep** — a `launchd` job so `anima.live sleep` runs automatically
  (the creature learns without manual triggering).
- **Headscale + Caddy** end-to-end (the §7 tasks) for the sovereign setup.

## 9. Known limitations / honest caveats (don't let these surprise you)
- **Face ID** (`passkey.py`) is a **device-presence gate**: it verifies challenge/origin/RP-ID
  + user-verified flag, but **not the cryptographic signature** (that needs a crypto lib). Strong
  layer on top of the token + private tunnel; not full WebAuthn. Opt-in, `ANIMA_NO_PASSKEY=1`
  bypass. **Test on a real device.**
- **PII scrub** catches **structured** PII (email/phone/SSN/card/IP); free-form **names** need an
  NER model. Mitigated by withholding the Portrait + pausing inbox reads on cloud.
- **`plausible-dalio`** is a weak eval trap (radical humility is a real Dalio theme) — expect it
  to stay ~3/5.
- **Whisper `small.en`** trades a little accuracy for ~4–6× faster STT; bump via `ANIMA_WHISPER`.
- **Web fetch + mail-send** exist as endpoints but are **not wired into the conversation** (UI
  shows them disabled). Don't claim otherwise.

## 10. Docs index
- `docs/HANDOFF.md` — this file.
- `docs/anima-eval-findings.md` — the full eval story + measured results.
- `docs/capability-honesty-incident.md` — the fabricated-iMessage incident + the fix.
- `docs/anima-operator-notes.md` — external state (Tailscale, run commands, gotchas).
- `docs/vera-domain-setup.md` — `vera.guruu.ai` HTTPS via Cloudflare + Caddy.
- `docs/self-hosting-network.md` — Tailscale vs Headscale, the honest tradeoffs.
- `docs/self-hosting-digitalocean.md` — Headscale + DERP on a droplet.

## 11. Tooling note for the next agent
- **This code session** has: terminal, files, git, GitHub. **No browser**, no access to the
  Mac's local Chrome/accounts. Account/dashboard work belongs to a **local browser-capable
  session** (Claude-in-Chrome / `claude --chrome` / computer-use).
- Every offline behaviour is testable without Ollama via `python3 scripts/selftest.py`.
