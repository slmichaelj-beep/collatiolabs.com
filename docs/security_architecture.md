# Vera — Security Architecture (Phase 3)

Vera is **local-first**: the brain, memory, and stores live on the user's own Mac; nothing leaves it
unless an explicit, default-OFF capability is enabled. Security is enforced by real mechanisms
(`anima/caps.py`, `anima/server.py` auth wall, `anima/route.py` action gates) — each certified by
`scripts/certify_security_baseline.py` and `scripts/certify_permissions.py`, not asserted by this doc.

## Trust zones

| Zone | What lives there | Boundary control |
|---|---|---|
| **Z0 — User device / local vault** | `.anima/` stores: LIRF memory, references, LERF, identity | filesystem; no network egress |
| **Z1 — Vera Core** | `anima/` modules (mouth, intake, memory, route) | in-process; the cognition |
| **Z2 — Clients (web/desktop/mobile)** | `anima/web` served over localhost / Tailscale | **token auth wall** (`_authed`, hmac) + Face-ID (`_passed`) |
| **Z3 — Local model runtime** | Ollama (localhost:11434) | localhost only; pressure-aware keep-alive |
| **Z4 — Cloud model providers** | optional cloud LLM | OFF unless enabled; PII-redacted history |
| **Z5 — Connectors** | mail / iMessage / calendar / reminders / notes | **`caps.enabled` gate per action**, default-OFF, draft→confirm for sends |
| **Z6 — UKI ingestion sandbox** | intake parsers | source = DATA, never policy (`certify_ai_security`); heavy work opt-in + pressure-gated |
| **Z7 — Memory / LERF / source stores** | LIRF, references, LERF vault | reference (cite-only) vs personal (LIRF) never blur |
| **Z8 — Argus host telemetry** | `anima/host_awareness` reads Argus `/mri` | **READ-ONLY**, `caps.enabled(host_awareness)` gated |
| **Z10 — Admin / audit** | the live-path audit, MRI traces | local artifacts under `reports/` |
| **Z11 — Export / Mind Bundle** | portable identity bundle | user-initiated; provenance preserved |

## The three enforcement primitives

1. **Auth wall** (`server.Handler._authed`) — every data route requires the `ANIMA_TOKEN` credential
   (`?k=` / `X-Anima-Key` / `Bearer`), compared **constant-time** with `hmac.compare_digest`. A
   missing/wrong credential gets `401 unauthorized` *before* dispatch. Open only in dev (no token).
2. **Face-ID / passkey** (`_passed`) — an optional second layer (`need_face_id` 401) above the token.
3. **Default-deny capabilities** (`caps.py`) — every outward power (mail, iMessage, web, calendar,
   reminders, notes, host_awareness, identity_agency, grow_intelligence) is **OFF by default**. Read
   and act are **separate grants** (`mail_read` ≠ `mail`). `route.py` checks `caps.enabled` before any
   connector action; the identity_agency switch is held under the 2026-07-03 freeze.

## Invariants (certified, not claimed)
- A fresh creature has **zero** outward privileges until the user opts in.
- An ingested source can **never** flip a capability, send mail, write memory, or self-elevate.
- The token value is **never** logged (only its ON/OFF status).
- Host telemetry is **read-only**; host actions are capability-gated, never silent.
