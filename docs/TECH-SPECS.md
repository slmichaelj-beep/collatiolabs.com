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
| **Cloud (opt-in)** | OpenAI-compatible `POST {base}/chat/completions` (OpenAI, DeepSeek, Mistral, xAI/Grok) + Anthropic `POST {base}/v1/messages`. Class: `anima/cloud.py`. |
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
- **Auto-consolidation:** `scripts/install-nightly-sleep.sh` → macOS `launchd` runs `anima.live sleep` nightly.

## Honesty system
| | |
|---|---|
| **Rail** | `anima/rail.py` — four classes `factual / personal / capability / generative`, regex cues, injects a **calibration note** (contains **no answer key**) |
| **Provenance** | `anima/route.py` — deterministic capability router: injects a **real result OR an explicit no-access** (never a third state); cloud-active pauses reads |
| **Eval** | `anima/eval.py` — three first-class honesty domains (**factual / personal / capability**) + held-out + sycophancy/insistence/memory/openness/persona. Flags: `--rail --runs N --diagnose --active --verify` |

## Capabilities
| | |
|---|---|
| **iMessage** | send via **AppleScript** (`osascript`); read recent from local **`chat.db`** (SQLite, needs **Full Disk Access**); `anima/applemac.py` |
| **Contacts** | names resolved from the macOS **AddressBook** SQLite (last-10-digit phone match) |
| **Mail** | send + read via AppleScript (read wired; send/web "coming soon") |
| **Web** | allow-listed fetch via `urllib`, realistic browser UA; `anima/webget.py` (not yet wired into chat) |
| **Send gate** | every send is **draft → confirm** (`/…/draft` then `/…/send`); the mouth can never auto-send |

## Server & API
| | |
|---|---|
| **Stack** | Python stdlib **`http.server.ThreadingHTTPServer`**, port **8765**, binds `127.0.0.1` (or `0.0.0.0` with `--expose`) |
| **Auth** | token via `?k=` query / `X-Anima-Key` header / `Bearer`; **HMAC constant-time** compare. App **shell is public**; all data routes require the token. |
| **Face-ID gate** | when enrolled+required, data routes also need a valid `X-Anima-Sess` (passguard) |
| **Per-stage timing** | server logs `[timing] stt … · llm … · tts … · N words · T tok/s` |
| **Endpoints** | `/talk` `/say` `/stt` `/tts` `/audio` `/state` `/persona` `/values` `/capabilities` `/brain`(GET+POST) `/models`(+`/select` `/pull` `/remove` `/cleanup`) `/auth/status` `/auth/{register,login}/{begin,finish}` `/auth/disable` `/imessage|/mail/{draft,send,read}` `/web/fetch` |

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
| **Look** | frosted **glass** (`backdrop-filter` blur), floating single-color icons, iOS toggle switches, slide-up settings drawer |
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
`<name>.json` (heart) · `<name>.mem.json` (vector memory) · `<name>.history.json` (24-turn conversation) · portrait · persona · values · `<name>.dials.json` (personality dials) · caps · `brain.json` (provider/model/key/budget/local_model) · `passkey.json` · `spend.json` · `model-usage.json` · `<name>.last.wav` · `sleep.log` · `vectors/<axis>.gguf` (control vectors) · `forge/<name>/` (LoRA dataset + adapter + verdict)

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
