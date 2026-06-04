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
- **Phone:** needs valid HTTPS (mic + Face ID require it). **As of 2026-06-03: `https://vera.guruu.ai/`**
  (Caddy launchd daemon, real Let's Encrypt cert over the Tailscale tunnel — see §6). Auth is
  currently OFF, so no `?k=` token; when on, the token rides in the URL `?k=` (remembered in
  localStorage; public app shell). The old `tailscale serve` `.ts.net` cert is superseded.
- **Sleep/learn is manual:** `python3 -m anima.live sleep Vera` (consolidates the Portrait +
  may grow LTC weights). Not scheduled — see future work.
- **Operator state** (Tailscale devices, run commands, gotchas) is in `docs/anima-operator-notes.md`.

## 6. Infrastructure (current + the chosen direction)
- **Today (DONE 2026-06-03 — Track A complete):** `https://vera.guruu.ai/` is **live with a
  real Let's Encrypt cert.** **Caddy** on the Mac terminates TLS (cert via Cloudflare
  **DNS-01**, required because the `vera` A-record is the Mac's private Tailscale IP) and
  reverse-proxies to Vera on `127.0.0.1:8765`. Caddy runs as a **root launchd daemon**
  (`ai.vera.caddy`, plist at `/Library/LaunchDaemons/`, wrapper `scripts/caddy-daemon.sh`,
  config `deploy/Caddyfile`) → survives reboots, auto-renews. **Tailscale is still the
  tunnel** — Caddy only replaced `tailscale serve`. DNS is on Cloudflare (Free zone,
  nameservers `edward`/`leanna.ns.cloudflare.com`); the token lives only in
  `~/.cf-vera-token` (0600). **Phone URL:** `https://vera.guruu.ai/` (auth OFF → no `?k=`);
  **on the Mac:** `http://localhost:8765/` (the Mac can't reach its own tailnet IP). The
  earlier `tailscale serve` `.ts.net` URL is now superseded.
- **Optional next step (sovereignty), NOT done — "Track B":** Headscale on a **DigitalOcean**
  droplet to own the coordination metadata too. Still purely optional; Vera works fully
  without it. (`docs/self-hosting-digitalocean.md`.)
- **Latency is NOT a networking concern** — the tunnel is ~tens of ms; Vera's STT+LLM+TTS is
  seconds. The model dominates.
- **The 3 gotchas that bit us (see `docs/vera-domain-setup.md` §7 / operator notes):**
  (1) NordVPN on the Mac breaks the Tailscale path — pause it; (2) the Mac can't reach its
  own tailnet IP, so test from the phone; (3) launchd has no `$HOME` → `export
  HOME=/var/root` in the wrapper. Cloudflare's auto-scan also missed the Clerk DNS records
  (re-added manually).
- Step-by-step guides:
  - `docs/vera-domain-setup.md` — **AS-BUILT** GoDaddy → Cloudflare DNS → Caddy launchd
    daemon → valid HTTPS, plus the 3 gotchas.
  - `docs/self-hosting-network.md` — Headscale vs Tailscale, the honest tradeoffs (Track B).
  - `docs/self-hosting-digitalocean.md` — Headscale + DERP on a droplet (Track B, optional).

## 7. What the OTHER (Chrome/Cowork) session must do — this code session can't
**Track A is COMPLETE (2026-06-03) — items 1–3 and 5 below are DONE; `vera.guruu.ai` is
live.** Nothing here is outstanding except the *optional* Track B (item 4).
1. ~~**GoDaddy** → point `guruu.ai` nameservers at Cloudflare.~~ **DONE** — nameservers are
   `edward`/`leanna.ns.cloudflare.com`. (`docs/vera-domain-setup.md` §1–2)
2. ~~**Cloudflare** → add `guruu.ai`, add `vera` A-record → Mac's tailnet IP (grey cloud),
   create a scoped API token.~~ **DONE** — `vera` A → `100.97.182.66` (DNS-only); token
   scoped to `guruu.ai`, stored in `~/.cf-vera-token`. **The auto-scan missed the Clerk DNS
   records — they were re-added manually** (`accounts`/`clerk`/`clkmail`/`clk._domainkey`/
   `clk2._domainkey`). (§2–3)
3. ~~**Mac Terminal** → build/run **Caddy** with that token; `tailscale serve --https=443
   off`.~~ **DONE** — Caddy runs as the **`ai.vera.caddy` launchd daemon** (not a manual
   run); `tailscale serve` is off but Tailscale is still the tunnel. (§4–5)
4. **(STILL OPTIONAL — Track B, NOT done)** **DigitalOcean** → droplet + Headscale + DERP per
   `docs/self-hosting-digitalocean.md`; re-point clients with `--login-server`. Only if you
   want to own the coordination metadata too; Vera is fully working without it.
5. ~~Open `https://vera.guruu.ai/?k=<token>` → mic + Face ID work.~~ **DONE** — live at
   `https://vera.guruu.ai/` (auth is OFF, so **no `?k=`**). Test from the **phone** (the Mac
   can't reach its own tailnet IP); on the Mac use `http://localhost:8765/`.

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
- **Scheduled nightly sleep** — **DONE**: `scripts/install-nightly-sleep.sh` installs a
  macOS `launchd` job so `anima.live sleep` runs nightly (the creature consolidates the
  Portrait + grows weights without manual triggering).
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

## 9b. Personality engine — Builds 1–3 (the dials/forge/identity stack)

The decision that ties these together: **the dials are the stable contract; the
backend underneath is swappable.** A person's character is portable and
model-independent; only the heavy artifacts (vectors, adapter) are model-bound and
regenerated when the model changes. Honesty is never a dial — it stays a code rail.

**Build 1 — Personality dials (`anima/dials.py`).** 8 axes (warmth, edge,
playfulness, flirtiness, directness, openness, length, mood), 0–100, persisted to
`.anima/<name>.dials.json`. One contract, two compilers:
- `to_prompt()` → graded system-prompt directives. **Live now on any brain** (Ollama/
  cloud); wired into `mouth.system_prompt`. Empathy is **down by default** (warmth 35,
  edge 68) and the base persona gained an anti-fawning clause.
- `to_vectors()` → `[(vector.gguf, scale)]` for **llama.cpp** control vectors (V2).
  `anima/llamacpp.py` is the vector-aware brain (drop-in for `OllamaBrain`, selected
  with `ANIMA_BRAIN=llamacpp`); `scripts/make_vectors.py` generates per-model vectors
  with `repeng` (run on the Mac; needs the HF weights of the GGUF you serve).
  Honest constraint: llama.cpp applies vectors at **model-load**, so committing a
  slider relaunches `llama-server` (`launch_command`) — live feel still comes from the
  prompt path. UI: sliders in the Settings drawer (`/dials` GET/POST).

**Build 2 — Character Forge (`anima/forge.py`, `scripts/forge.py`).** Corpus → voice.
Ingest **files / URLs / YouTube** → chunk → MLX-LM LoRA dataset → `mlx_lm.lora` train
(Mac) → **eval gate** (`forge.gate`): accept the adapter **only if honesty held and
persona didn't regress** — same accept-only-if-better discipline as sleep-learning.
Shifts **voice/style, not knowledge and not IQ**; knowledge still belongs in
`anima/memory.py`. Stage 1 (dataset) needs no model; stages 2–3 need MLX + the model.

**Build 3 — Portable identity (`anima/identity.py`).** The "1000-year" layer. A
versioned bundle (`SCHEMA`, `migrate()`): **portable core** = dials + persona + values
+ Portrait (plain JSON, model-independent); **artifacts** = vectors + adapter, recorded
by **hash + model_family**, never embedded. Export/import via `/identity/export`
(downloads `<name>.identity.json`) and `/identity/import`; UI has Export/Import in the
"Portable self" section. On import, model-bound artifacts that don't match the current
model are reported as **regenerate** steps — never silent breakage.

All three are covered by `scripts/selftest.py` (now **36 offline checks**, CI-gated).
**Not yet validated on hardware** (no GPU/model in the code sandbox): the actual vector
steering, the MLX train, and the live eval gate must be exercised on the Mac.

## 10. Docs index
- `docs/HANDOFF.md` — this file.
- `docs/TECH-SPECS.md` — **complete technical spec sheet** (every engine, model, lib, param, endpoint, env var, file).
- `docs/CHROME-SESSION-TASKS.md` — executable brief for the browser-capable session (the dashboard/account work).
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
