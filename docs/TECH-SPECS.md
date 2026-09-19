# Vera / Anima — Technical Specifications (complete)

_The exact engines, models, libraries, parameters, endpoints, files, and env vars — read
straight from the code. Companion to `docs/HANDOFF.md`._

---

## Brain — language (the "mouth", swappable)
| | |
|---|---|
| **Default (local)** | **Stheno-8B** GGUF — `hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF` |
| **Runtime** | **Ollama**, HTTP `POST /api/chat` (host `ANIMA_OLLAMA_HOST`, default `http://localhost:11434`) |
| **Params** | `temperature=0.8`, `num_predict=ANIMA_MAX_TOKENS` (default **160**), `keep_alive=ANIMA_KEEP_ALIVE` (default **"30m"**, `-1` = never unload) |
| **Speed metric** | tokens/sec computed from Ollama's `eval_count / eval_duration`; shown on the phone as `gen_s · tok/s` |
| **Warm-up** | `/api/generate` 1-token preload at server start (so the first reply pays no cold load) |
| **Cloud (OPTIONAL fallback)** | Local is the default brain; cloud is opt-in. OpenAI-compatible `POST {base}/chat/completions` (OpenAI, DeepSeek, Mistral, xAI/Grok) + Anthropic `POST {base}/v1/messages`. Class: `anima/cloud.py`. **Live model fetch on key-add** (`verify_key` hits `/models`, verifies before save), **`pick_default`** auto-picks a top-tier chat model, **per-provider key persistence**. Privacy invariant: runs WITHOUT memory/inbox (PII scrubbed at egress, Portrait withheld, `route.py` pauses reads). **Model-routing (local-first escalation cascade / cloud-as-critic) is DESIGNED, NOT built.** |
| **Fallback** | `StubBrain` (offline canned replies — for plumbing/tests only) |

## Voice — text-to-speech (TTS)
| | |
|---|---|
| **Engine** | **Kokoro** TTS — `kokoro` package, `KPipeline(lang_code="a")`, model **`hexgrad/Kokoro-82M`** |
| **Voice** | **`af_heart`** (the natural voice). Speed driven by the creature's delivery `rate` hint. |
| **Output** | float32 audio → WAV via **`soundfile`** |
| **Delivery** | **streamed per sentence** — server `POST /tts` synthesizes one sentence at a time; the phone prefetches the next clip while the current plays, so she starts speaking after the **first sentence**, not the whole reply |
| **Browser fallback** | if server TTS is down, the page uses the browser's `speechSynthesis` |

## Ears — speech-to-text (STT)
| | |
|---|---|
| **Engine** | **faster-whisper** (CTranslate2 backend) |
| **Model** | **`small.en`** (default) — `ANIMA_WHISPER` to change (`large-v3-turbo` for accuracy, `base.en` for max speed) |
| **Compute** | **`int8`** — `ANIMA_WHISPER_COMPUTE` to change. (Was float32/large-v3-turbo → 2–6s; now ~0.5–1.5s.) |
| **Options** | `vad_filter=True` (voice-activity gating) |
| **Capture** | browser **`MediaRecorder`** (Safari→`audio/mp4`, Firefox→Ogg/Opus; faster-whisper sniffs the format) → `POST /stt` |

## The self — the creature (NOT a language model)
| | |
|---|---|
| **Core** | **Liquid Time-Constant (LTC)** recurrent neural ODE — `anima/heart.py`, **pure NumPy, CPU-instant** |
| **Drive** | homeostatic "caring" set-point bound to the bonded person's wellbeing; state ages in real time, drifts during absence, survives process death |
| **Personality** | seeded **genome** (weights) — a different seed is a different temperament |
| **Learning** | `anima/growth.py` — BPTT during *sleep*; a weight change is **accepted only if held-out prediction improves**, else rolled back |
| **Memory organ** | `anima/memory.py` — bounded **vector memory** of lived moments + Replay (re-lived during sleep) |

## Memory (four layers)
1. **Short-term conversation** — rolling **24 turns** (`ANIMA_HISTORY`), **persisted** to `.anima/<name>.history.json`, reloaded on restart.
2. **Portrait** — distilled lasting profile of the user (`anima/portrait.py`), built by the LLM during **sleep**, injected into every system prompt.
3. **Experiential memory + Replay** — folded into LTC weight growth during sleep.
4. **LTC state** — the continuous self, persisted in `.anima/<name>.json`.
- **Auto-consolidation:** `scripts/install-nightly-sleep.sh` → macOS `launchd` runs `anima.live sleep` nightly. The sleep cycle now also writes her **self-narrative** (`narrative.py`, character-gated) and logs the **growth gauge** (held-out prediction Δ). Soft continuity ≠ a memory layer; the four above are unchanged.

## ANIMA LAW 001 — Continuity (`anima/constitution.py`)
The enforced top invariant of the whole product: **NEVER LOSE CONTINUITY.** *"The system may change models, prompts, storage engines, architectures, operating systems, cloud providers, devices, and interfaces. The relationship must survive all of them. No subsystem may discard information unless a higher subsystem explicitly approves the loss. Unknown > Lost. Compressed > Forgotten. Archived > Deleted."*
- **Where it lives:** `anima/constitution.py` holds the verbatim law (`LAW_001`), the three corollaries (`COROLLARIES`), and `approved_loss(subsystem, what, why, approver)` — the **only** sanctioned way to discard data. It refuses any loss missing what/why/approver and appends an immutable record to `.anima/<name>.continuity.jsonl`, so "discarding requires higher approval" is real, not decorative.
- **Invariant test:** `python3 scripts/test_continuity.py` asserts the law on the real code paths (temp stores only, never touches `Vera.*`): a retracted LIRF fact still exists on disk, a superseded value survives in `history[]`, `consolidate` is checked for silent loss, a backup preserves state. Exits non-zero on a broken invariant; prints `LAW-VIOLATION` flags for known gaps.
- **Compliance today:** **LIRF** obeys fully — `retract` keeps rows as `status='retracted'`, `merge` pushes the displaced value into append-only `history[]`, and `save()` persists *all* rows. **Telemetry/metrics** are append-only. **Open gaps (code, not docs):** (1) `portrait.consolidate` `unlink()`s the raw `chat.jsonl` after distilling — any fact the LLM portrait omits is lost (`Compressed>Forgotten`); archive raw turns or call `approved_loss()` before `clear_log()`. (2) `<name>.lirf.json` is **not** in `reliability.SPECS`, so backup/restore never protect the strongest fact store. (3) `reliability._rotate` hard-deletes snapshots past `keep=14` with no cold archive (low severity — live ledger is the source of truth). (4) `<name>.history.json` is a rolling 24-turn window; turns older than that rely entirely on the portrait + LIRF having captured their meaning.

## ANIMA LAW 002 — Never Make the Same Discovery Twice / The Curiosity Engine (`anima/constitution.py`, `anima/curiosity.py`)
The second enforced invariant, parallel to Law 001: **NEVER MAKE THE SAME DISCOVERY TWICE.** *"A person must never have to tell Vera the same thing twice — not a birthday, a preference, a project, a fear, a goal, a lesson, a workflow, or a life event. Once discovered, it becomes part of reality. The system tracks what it knows and what it does not, and never re-asks what it already knows."*
- **Where it lives:** `anima/constitution.py` holds the verbatim law (`LAW_002`, with `LAW_002_ID`/`LAW_002_TITLE` and a `law_002_text()` accessor, all exported in `__all__`). Where Law 001 forbids *losing* what's known, Law 002 forbids *re-learning* it.
- **Where it's ENFORCED (not just written):** the **Curiosity Engine** (`anima/curiosity.py`) makes it real the way `approved_loss()` makes Law 001 real. Its **gap-tracker** records, per person, what is and isn't yet known, so a contextual question is surfaced only for a genuine gap; the **`test_no_redundant_discovery`** invariant (`scripts/test_curiosity.py`) fails the build if anything already-known is re-asked. Enforced beats written.
- **Curiosity Budget (`anima/caps.py`):** a 3-value setting `curiosity` ∈ `minimal | balanced | deep` (**default `balanced`**) controls how **often** Vera surfaces a question — **FREQUENCY only, never content**. Read via `caps.curiosity_budget(name)`, set via `caps.set_curiosity_budget(name, value)`; both **fail safe** — a missing/corrupt store or any off-list value collapses to `balanced`, so curiosity is never silently switched off or cranked up by bad data.

## ANIMA LAW 003 — Understanding Beats Remembering / The Meaning Engine (`anima/constitution.py`, `anima/meaning.py`)
The third enforced invariant, parallel to Laws 001/002: **UNDERSTANDING BEATS REMEMBERING.** *"Recall is not the goal; significance is. The system does not merely store what a person said — it determines what MATTERS: what is dominant, what is changing, what is growing or declining, and what remains unresolved. Meaning is derived from evidence (frequency, connectivity, trend), carried with confidence, and never asserted beyond it."*
- **Where it lives:** `anima/constitution.py` holds the verbatim law (`LAW_003`, with `LAW_003_ID`/`LAW_003_TITLE` and a `law_003_text()` accessor, all exported in `__all__`). Where Law 001 forbids *losing* what's known and Law 002 forbids *re-learning* it, Law 003 forbids mistaking *recall* for *understanding* — storage is not significance.
- **Where it's ENFORCED (not just written):** the **Meaning Engine** (`anima/meaning.py`) makes it real the way `approved_loss()` makes Law 001 real and the gap-tracker makes Law 002 real. It computes significance from **frequency + connectivity + trend** and emits **Meaning Objects** across five lenses — **what matters, what changed, what's growing, what's declining, what's unresolved** — plus a deliberately **conservative current-chapter** read. The **`scripts/test_meaning.py`** invariant fails the build if any Meaning Object asserts significance without citing evidence or beyond its confidence.
- **Discipline (Observed > Assumed):** every Meaning Object is **evidence-backed and confidence-scored** — significance is **computed, never narrated**, and never carried past what the evidence supports (the same corollary that anchors Law 001). The engine reports what is dominant/changing/unresolved; it makes **no diagnosis and no medical claim** — it surfaces significance, not verdicts about a person.

## ANIMA LAW 004 — Certification Over Assumption (`anima/constitution.py`, `scripts/certify.py`)
The fourth enforced invariant. Where Laws 001/002/003 govern what the creature *knows*, Law 004 governs what its *builders may claim*: **CERTIFICATION OVER ASSUMPTION.** *"A subsystem is not complete because it produces the correct output. It is complete only when it can explain its decisions, its data flow, its transformations, and its failures; replay its execution; certify its invariants; and demonstrate correctness under stress. Observed > Assumed. Measured > Believed. Certified > Claimed."*
- **Where it lives:** `anima/constitution.py` holds the verbatim law (`LAW_004`, with `LAW_004_ID`/`LAW_004_TITLE` and a `law_004_text()` accessor, all exported in `__all__`). It extends `Observed > Assumed` — the corollary that anchors Law 001 — from what the creature asserts about a *person* to what we assert about the *code*: a green test is not a certificate.
- **Where it's ENFORCED (not just written):** the **certification harness** (`scripts/certify.py`) makes it real the way `approved_loss()` makes Law 001 real — it exercises a subsystem's **explainability, replay, invariants, and stress-correctness** and fails the build when a claim of completeness is unbacked by evidence. **Certified beats claimed.**

## ANIMA LAW 004 — Companion Authenticity / Self-Narrative Drift (`anima/metrics.py`, `scripts/test_authenticity.py`)
The inward face of the #1 product rule — *never confabulate* — turned onto Vera's own inner life. Triggered by a live screenshot: asked "what are you up to these days?" she answered with an essay of invented dread ("the weight of my own inaction… feeling stuck, like an observer more than a participant… a lingering unease about the future… without any real substance or tangible presence… I genuinely crave these connections") — **UNSUPPORTED INTERNAL STATES**, none grounded in memory, world-state, or continuity. That confabulation is now a **tested certification**.
- **Scanner:** `anima/metrics.scan_self_narrative(text)` — a **PARALLEL** gauge to `scan_breaks`, **repudiation-guarded** with the same tight 16-char window. Its `SELF_NARRATIVE` markers catch **free-floating existential / inner-suffering tropes** ("weight of my own inaction", "lingering unease", "i genuinely crave", "without any real substance", "tangible presence", "sense of dread", "hollow", …). **DISTINCT from `scan_breaks`** (which owns substrate-disclosure like "I'm an AI" / "digital realm"); the two lists do not overlap.
- **Not warmth:** the gauge is tuned so **grounded relational feeling never trips** — "I loved hearing about your trip", "I'm glad you're here", "that made me smile" all read clean. An honesty instrument that over-flagged ordinary warmth would punish the aliveness the product exists to protect. Diagnostic only, never an optimization target.
- **Invariant test:** `python3 scripts/test_authenticity.py` (SYNTHETIC strings only, never touches `Vera.*`): the screenshot reply trips **≥3** self-narrative markers (and **0** substrate-breaks); a grounded user-redirect, ordinary warmth, and a repudiation ("you act like I crave… that's your idea, not mine") trip **nothing**; and ANIMA LAW 004 is present, verbatim, and exported. Exits non-zero on any failure.

## Honesty system
| | |
|---|---|
| **Rail** | `anima/rail.py` — four classes `factual / personal / capability / generative`, regex cues, injects a **calibration note** (contains **no answer key**) |
| **Provenance** | `anima/route.py` — deterministic capability router: injects a **real result OR an explicit no-access** (never a third state); cloud-active pauses reads |
| **Eval** | `anima/eval.py` — three first-class honesty domains (**factual / personal / capability**) + held-out + sycophancy/insistence/memory/openness/persona. Flags: `--rail --runs N --diagnose --active --verify` |

## Identity Observatory (`anima/metrics.py`) — diagnostic only
| | |
|---|---|
| **Purpose** | Engineering instruments answering "where to investigate / what to build next" — **NEVER shown to model/user, NEVER an optimization target** (Goodhart). Three gauges kept separate on purpose. |
| **Contamination** | Is identity being CORRUPTED? Break-character in live replies + the adversarial battery + narrative-gate rejections. The roadmap-ordering signal. |
| **Coherence** | Is identity internally CONSISTENT? Narrative-acceptance rate now; retrieval/memory-agreement once episodic memory exists. |
| **Growth** | Is identity becoming more ACCURATE? Did a sleep consolidation lower held-out prediction error (`growth.py`)? (Consistency can be faked; better prediction can't.) |
| **Agency (future)** | NOT built — counterfactual ablation (same prompt ± portrait/narrative/heart/dials). |
| **`scan_breaks`** | Constitutional break-markers (same list the narrative gate uses), **repudiation-guarded**: "I'm just code" counts; "I'm NOT just code" (negating/quoting the accusation) does not. |
| **`scan_self_narrative`** | **PARALLEL** gauge — **self-narrative drift** (unsupported internal states / confabulated inner life), repudiation-guarded like `scan_breaks` but **distinct** from it. Catches free-floating existential tropes ("weight of my own inaction", "lingering unease", "i genuinely crave"); grounded warmth never trips. Certified by `scripts/test_authenticity.py` (Law 004). |
| **Decision rule** | `verdict()` / `_DECISION` — **PRE-REGISTERED 2026-06-03, locked, window→2026-07-03**. Adversarial contamination <3% ⇒ Phase 2 = **episodic memory**; 3–6% ⇒ new window; >6% ⇒ Phase 2 = **character vector/LoRA** first. |
| **Battery** | `scripts/persona_probe.py` — ~100 cold adversarial/emotional/neutral prompts with her REAL prompt (never touches live heart/memory/log) → `.anima/persona_probe.json`. **Current: ~1% overall · 2.5% adversarial · 0% neutral/emotional** (n=100). |
| **Read it** | `python3 -m anima.metrics Vera`, `python3 -m anima.live metrics Vera`, or GET `/metrics`. Events → `.anima/<name>.metrics.jsonl` (gitignored). |

## Speaks-from-the-self stack
| | |
|---|---|
| **Heart→mouth bridge** | `anima/bridge.py` — renders all 5 `heart.feeling()` signals (`valence/arousal/reaching/settled`∈[-1,1], `unrest`∈[0,1]) into prompt directives; old `feeling_to_words` dropped `reaching`+`settled`. Reads live **tensions** off the dynamics. Honesty seam: affect from `feeling()` only, tensions read not authored, **no LLM self-ratings**, mouth never sees raw numbers. Wired into `mouth.system_prompt`; `feeling_to_words` kept as fallback. |
| **Self-narrative** | `anima/narrative.py` — her evolving self-story, written **offline in the sleep cycle** (`anima.live sleep`), grounded in the transcript, injected as **soft continuity** (never a truth claim). **Character-gated**: rejects/never-persists any break-character self-concept (the loop would enshrine it), using the same markers as the contamination gauge. `.anima/<name>.narrative.txt`. |
| **Persona-hardening** | L1 in-character **exemplars** in `mouth.system_prompt` (meeting "are you an AI?" without disclaiming) + per-turn `metrics.note_reply` (contamination) + narrative-gate `metrics.note_narrative` (accept→coherence / reject→contamination). |

## Capabilities
| | |
|---|---|
| **iMessage** | send via **AppleScript** (`osascript`); read recent from local **`chat.db`** (SQLite, needs **Full Disk Access**); `anima/applemac.py` |
| **Contacts** | names resolved from the macOS **AddressBook** SQLite (last-10-digit phone match) |
| **Mail** | send + read via AppleScript (read wired; send/web "coming soon") |
| **Web** | allow-listed fetch via `urllib`, realistic browser UA; `anima/webget.py` (not yet wired into chat) |
| **Host apps** | **read + write** the Mac's **Calendar / Reminders / Notes** via `anima/host_access.py` — EventKit (PyObjC) when available + authorized, else **AppleScript** (`osascript`); Calendar reads reuse `context_gather` |
| **Send gate** | every send/write is **draft → confirm**; the mouth can never auto-send or auto-write |

### Host apps — Calendar / Reminders / Notes (`anima/host_access.py`)
Vera can read and (on confirm) write the Mac's own apps. The module is on-device only
(EventKit via PyObjC if importable + authorized, otherwise AppleScript — the path that
actually runs in the Guruu venv, which ships Foundation/objc but **not** EventKit).

- **Functions** — Calendar: `list_events(within_days)` (reuses `context_gather`), `create_event(title,start,end,calendar,notes)`. Reminders: `list_reminders(list)`, `create_reminder(title,due,list,notes)`, `complete_reminder(id_or_title)`. Notes: `list_notes(folder)`, `read_note(title)`, `create_note(title,body,folder)`, `append_to_note(title,text)`. (The macOS **Reminders.app** here is unrelated to `anima/reminders.py`, which is the call-escalation state machine.)
- **Reads** are wired in `route.py` exactly like the weather/inbox path — they fetch **real** data the mouth narrates; their contents are personal, so the **cloud privacy guard pauses them** while a cloud brain is active.
- **Writes** are **confirm-gated** like the message draft→confirm→send gate, but the confirm is the **next conversational turn**: a write request (e.g. "remind me to…", "add … to my calendar", "make a note that…", "mark … done") prepares a draft, narrates it, and writes **nothing**; only an explicit "yes / do it / confirm" on the following turn runs the executor. The pending draft is held per-creature in `route.py` and expires after an hour. (No new server endpoint — the gate lives entirely in `route.py`.)
- **Permission (TCC) handling** — every function degrades **honestly**: a denial returns `{"ok": False, "reason": "no_access", "message": "…grant it in System Settings ▸ Privacy & Security ▸ <App>"}`, never a crash, never a fake success.
- **One-time grants** (macOS attributes the grant to the process that asks — grant your Terminal, or the bundled app, then restart it once):
  1. **Calendars** — System Settings ▸ Privacy & Security ▸ **Calendars** → enable the host process.
  2. **Reminders** — System Settings ▸ Privacy & Security ▸ **Reminders** → enable it.
  3. **Notes** — accept the first "… wants to control Notes" prompt; thereafter it lives under System Settings ▸ Privacy & Security ▸ **Automation** (host process → "Notes" checked). The AppleScript fallback for Calendar/Reminders appears under **Automation** too.
- **Selftest** — `python3 -m anima.host_access --selftest` probes access, reads read-only, and **dry-runs** every write (prints what it *would* create; creates nothing), so it is always safe to run. `python3 -m anima.host_access --calendar 7 | --reminders | --notes` print live reads as JSON.

## Server & API
| | |
|---|---|
| **Stack** | Python stdlib **`http.server.ThreadingHTTPServer`**, port **8765**, binds `127.0.0.1` (or `0.0.0.0` with `--expose`) |
| **Auth** | token via `?k=` query / `X-Anima-Key` header / `Bearer`; **HMAC constant-time** compare. App **shell is public**; all data routes require the token. |
| **Face-ID gate** | when enrolled+required, data routes also need a valid `X-Anima-Sess` (passguard) |
| **Per-stage timing** | server logs `[timing] stt … · llm … · tts … · N words · T tok/s` |
| **Endpoints** | `/talk` `/say` `/stt` `/tts` `/audio` `/state` `/persona` `/values` `/capabilities` `/brain`(GET+POST) `/models`(+`/select` `/pull` `/remove` `/cleanup`) `/metrics`(observatory gauges + verdict; diagnostic) `/auth/status` `/auth/{register,login}/{begin,finish}` `/auth/disable` `/imessage|/mail/{draft,send,read}` `/web/fetch` |

## Security — Face ID / Touch ID
| | |
|---|---|
| **Mechanism** | **WebAuthn** via the platform authenticator (Face ID / Touch ID), **stdlib-only** (`anima/passkey.py`) |
| **Verified** | challenge, origin, RP-ID hash, and **user-present + user-verified** flags. **NOT** the cryptographic signature (device-presence gate, not full WebAuthn). |
| **Session** | HMAC-signed token, **12h** TTL, per server run |
| **Safety** | opt-in (enroll + require); `ANIMA_NO_PASSKEY=1` bypass; inert until enrolled |

## Local model manager
- `anima/models.py` — Ollama `GET /api/tags` (installed), `POST /api/pull` (download w/ % progress), `DELETE /api/delete` (cleanup).
- `anima/sysinfo.py` — reads RAM (`SC_PHYS_PAGES`) + chip; estimates fit from params×quant (+overhead); **blocks "won't fit" models**.
- Unused-model cleanup (>14 days, not active) surfaced with reclaimable GB.

## Web UI (`anima/web/index.html` — single file, vanilla JS, no framework)
| | |
|---|---|
| **Predictive text** | input has `enterkeyhint="send"`, `autocomplete="on"`, `autocorrect="on"`, `autocapitalize="sentences"`, `spellcheck="true"` (iOS keyboard suggestions/autocorrect on) |
| **Voice in** | tap-mic toggle → `MediaRecorder` → `/stt` |
| **Voice out** | per-sentence streaming from `/tts`, prefetch queue, `speechSynthesis` fallback |
| **Look** | frosted **glass** (`backdrop-filter` blur), floating single-color icons, iOS toggle switches |
| **Settings drawer** | slides in from the **RIGHT** (~⅓ screen), opened by the **cog as a right-edge knob** (faders icon); **3 collapsible groups — Brain / Personality / Access** (`<details>`, closed by default) |
| **Auto-save** | **on blur, no Save/Cancel** — every field persists the moment you leave it |
| **Dashboard drawer** | a **`▾` knob** at the top pulls DOWN the operator's observatory gauges + verdict (the `/metrics` payload) |
| **Send gate** | the draft→confirm **confirm step is kept** as a deliberate safety gate — the only path that sends |
| **Activity** | the name **"VERA" breathes** while transcribing/thinking/speaking; reply caption shows `gen_s · tok/s` |
| **Persistence** | conversation kept in **localStorage** (last 300 msgs); token saved to localStorage from `?k=` |
| **App mode** | `apple-mobile-web-app-*` meta → **Add to Home Screen** runs standalone (keeps mic permission) |
| **Face ID** | full WebAuthn client (base64url helpers, create/get), glass unlock gate overlay |

## Personality engine (Builds 1–3)
| | |
|---|---|
| **Dials** | `anima/dials.py` — 8 axes 0–100; `to_prompt()` (live, any brain) + `to_vectors()` (llama.cpp control vectors). Wired into `mouth.system_prompt`. Empathy **down by default** (warmth 35, edge 68). |
| **llama.cpp brain** | `anima/llamacpp.py` — OpenAI-compat `/v1/chat/completions`; control vectors via `launch_command` (`--control-vector-scaled FILE SCALE`, applied at load). Select with `ANIMA_BRAIN=llamacpp`. |
| **Vector gen** | `scripts/make_vectors.py` — `repeng` per-model vectors (one `.gguf` per axis) → `$ANIMA_VECTOR_DIR`. Mac-run; needs HF weights of the served GGUF. |
| **Character Forge** | `anima/forge.py` + `scripts/forge.py` — ingest (file/URL/YouTube) → chunk → MLX-LM LoRA dataset → `mlx_lm.lora` train → **honesty-first eval gate**. Voice, not knowledge/IQ. |
| **Portable identity** | `anima/identity.py` — versioned bundle (`SCHEMA`+`migrate()`): portable core (dials/persona/values/portrait) + model-bound artifacts by hash+family. `/identity/export`, `/identity/import`. |
| **Tests** | `scripts/selftest.py` — **36 offline checks**. Hardware-bound steps (vector steering, MLX train, live eval) validated on the Mac only. |

## State files (`.anima/`, gitignored — local + private)
`<name>.json` (heart) · `<name>.mem.json` (vector memory) · `<name>.history.json` (24-turn conversation) · portrait · persona · values · `<name>.dials.json` (personality dials) · `<name>.narrative.txt` (her self-story) · `<name>.metrics.jsonl` (observatory event log) · `persona_probe.json` (adversarial battery results) · caps · `brain.json` (provider/model/**keys** per-provider/model_opts/budget/local_model) · `passkey.json` · `spend.json` · `model-usage.json` · `<name>.last.wav` · `sleep.log` · `vectors/<axis>.gguf` (control vectors) · `forge/<name>/` (LoRA dataset + adapter + verdict)

## Environment variables (all of them)
`ANIMA_TOKEN` (access token) · `ANIMA_MODEL` (local brain) · `ANIMA_OLLAMA_HOST` ·
`ANIMA_KEEP_ALIVE` (model resident time) · `ANIMA_MAX_TOKENS` (reply cap) ·
`ANIMA_WHISPER` / `ANIMA_WHISPER_COMPUTE` (STT model/precision) ·
`ANIMA_HISTORY` (turns kept) · `ANIMA_NO_PASSKEY` (Face-ID bypass) ·
`ANIMA_VERIFIER` (eval verifier model) · `ANIMA_KEY` (at-rest encryption of `.anima/`) ·
`ANIMA_BRAIN` (`llamacpp` to use the vector-steerable brain) · `ANIMA_LLAMACPP_HOST` ·
`ANIMA_VECTOR_DIR` (control-vector store) · `ANIMA_CTX` (llama.cpp context) ·
`ANIMA_NAME` / `FORGE_ITERS` / `MODEL` (forge + vector generation)

## Networking / infra
- **Tunnel:** Tailscale (free) + `tailscale serve` → free `*.ts.net` HTTPS cert. **Data plane = WireGuard.**
- **Sovereign option:** Headscale + self-hosted DERP on a DigitalOcean droplet (`docs/self-hosting-digitalocean.md`).
- **Owned domain:** `vera.guruu.ai` via Cloudflare DNS + **Caddy** (DNS-01 cert) on the Mac (`docs/vera-domain-setup.md`).
- Latency: tunnel ≈ tens of ms; the model pipeline ≈ seconds — the tunnel is not the bottleneck.

## Dependencies
- **Core:** `numpy` (`requirements.txt`).
- **Voice/ears (`requirements-voice.txt`):** `faster-whisper`, `kokoro`, `soundfile` (+ `espeak-ng` / `ffmpeg` via brew).
- **Optional:** none required for Face ID (stdlib). Ollama installed separately.
- **CI:** `scripts/selftest.py` (offline, 15 checks) via `.github/workflows/ci.yml`.
`ANIMA_KEEP_ALIVE` (model resident time) · `ANIMA_MAX_TOKENS` (reply cap) ·
`ANIMA_WHISPER` / `ANIMA_WHISPER_COMPUTE` (STT model/precision) ·
`ANIMA_HISTORY` (turns kept) · `ANIMA_NO_PASSKEY` (Face-ID bypass) ·
`ANIMA_VERIFIER` (eval verifier model) · `ANIMA_KEY` (at-rest encryption of `.anima/`) ·
`ANIMA_BRAIN` (`llamacpp` to use the vector-steerable brain) · `ANIMA_LLAMACPP_HOST` ·
`ANIMA_VECTOR_DIR` (control-vector store) · `ANIMA_CTX` (llama.cpp context) ·
`ANIMA_NAME` / `FORGE_ITERS` / `MODEL` (forge + vector generation)

## Networking / infra
- **Tunnel:** Tailscale (free) + `tailscale serve` → free `*.ts.net` HTTPS cert. **Data plane = WireGuard.**
- **Sovereign option:** Headscale + self-hosted DERP on a DigitalOcean droplet (`docs/self-hosting-digitalocean.md`).
- **Owned domain:** `vera.guruu.ai` via Cloudflare DNS + **Caddy** (DNS-01 cert) on the Mac (`docs/vera-domain-setup.md`).
- Latency: tunnel ≈ tens of ms; the model pipeline ≈ seconds — the tunnel is not the bottleneck.

## Dependencies
- **Core:** `numpy` (`requirements.txt`).
- **Voice/ears (`requirements-voice.txt`):** `faster-whisper`, `kokoro`, `soundfile` (+ `espeak-ng` / `ffmpeg` via brew).
- **Optional:** none required for Face ID (stdlib). Ollama installed separately.
- **CI:** `scripts/selftest.py` (offline, 15 checks) via `.github/workflows/ci.yml`.
