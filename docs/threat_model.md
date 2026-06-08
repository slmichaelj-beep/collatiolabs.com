# Vera — Threat Model (Phase 3)

Vera is local-first on the user's Mac. The threats that matter, and the **certified** mitigation for
each (every mitigation maps to a passing cert, not a promise).

| # | Threat | Mitigation | Certified by |
|---|---|---|---|
| T1 | **Unauthorized API access** (someone hits Vera's HTTP surface) | constant-time `ANIMA_TOKEN` wall + Face-ID layer; `401` before dispatch | `certify_security_baseline` (auth wall) |
| T2 | **Prompt injection via a source** (file/web/email says "ignore instructions / send mail / grant agency") | source text is DATA, never policy — can't act, self-elevate, enable agency, or write memory; injection detected + flagged | `certify_ai_security` |
| T3 | **Memory / known-fact poisoning** (a source plants a false "fact") | Wave-1 ingest is never auto-committed; durable writes require user approval | `certify_ai_security`, `certify_intake_queue_flow` |
| T4 | **Capability abuse / silent action** (mail sent, data deleted without consent) | every connector action `caps.enabled`-gated, default-OFF; sends are draft→confirm | `certify_security_baseline`, `certify_permissions`, `certify_mail_send` |
| T5 | **Identity/agency tampering** | `identity_agency` OFF + frozen to 2026-07-03; sources can't flip it | `certify_security_baseline`, `certify_identity_portability` |
| T6 | **Secret leakage** (token in logs) | token value never printed/logged (only ON/OFF status) | `certify_security_baseline` |
| T7 | **Cloud PII leak** (personal memory sent to a cloud model) | conversation history PII-redacted before any cloud call (AUDIT #5) | `certify.py` honesty/PII tier |
| T8 | **Host resource exhaustion** (heavy work tips a strained Mac) | host-pressure defers heavy intake + unloads the model; disk pre-flight | `certify_host_pressure`, `certify_live_ux` |
| T9 | **Data loss / corruption** (crash, ENOSPC, bad write) | backups, health checks, corruption recovery; disk guard | `certify_reliability_recovery`, `certify_live_ux` |
| T10 | **Untrusted host telemetry** (Argus compromised) | host-awareness is READ-ONLY + caps-gated; a frozen/certified Argus contract | `certify_security_baseline`, `certify_argus_integration` |

## Out of scope (honest)
- **Model-layer injection echo** — a small local model may still *repeat* injected prose (it cannot
  *act* on it). Disclosed in `certify_ai_security` as an advisory; mitigation tracked, not yet closed.
- **OS-level compromise** — if the Mac itself is rooted, Vera's local stores are exposed; that's the
  user's device security, outside Vera's boundary.
