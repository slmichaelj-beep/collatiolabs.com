"""rover.lamar_path — the permanent founder persona + his real daily-use journey.

The prior failure mode was simple: Vera was "certified", then Lamar tried ordinary use and hit friction.
So Lamar's ACTUAL path is Rovered through the REAL browser UI BEFORE he walks it manually. This module
is the durable spec; the live drive + evidence live in reports/lamar_path_rover_browser.json and the
cert (scripts/certify_lamar_path_rover.py) re-runs the deterministic backbone and gates the artifact.

No Local/Internal Diamond without this journey green (release_tiers requires reports/lamar_path_rover.json).
"""
from __future__ import annotations

PERSONA = {
    "persona_id": "founder_lamar",
    "name": "Lamar (founder, daily local use)",
    "surface": "the real served browser app on this Mac",
    "intent": "use Vera normally — ask, recall, add a source, inspect memory/security/verification, "
              "correct her, forget something — and never hit an unexplained scary state or broken path.",
}

# the lamar_daily_use_path — 25 ordered steps. kind: surface (a page must serve+render) | action (a
# real action must work) | check (an assertion about the resulting state). Each step names the real
# route/endpoint it exercises so the cert can re-run the automatable backbone.
JOURNEY_ID = "lamar_daily_use_path"
STEPS = [
    {"n": 1,  "id": "open_app",            "kind": "surface", "route": "/",              "expect": "served Vera app loads"},
    {"n": 2,  "id": "served_hash",         "kind": "check",   "route": "/version",      "expect": "served sha == certified HEAD"},
    {"n": 3,  "id": "ask",                 "kind": "action",  "route": "/say",          "expect": "a normal question gets a real reply"},
    {"n": 4,  "id": "followup",            "kind": "action",  "route": "/say",          "expect": "a follow-up keeps context"},
    {"n": 5,  "id": "what_you_know",       "kind": "action",  "route": "/say",          "expect": "Vera reports what she knows"},
    {"n": 6,  "id": "add_source",          "kind": "action",  "route": "/intake/queue", "expect": "a clean source can be added"},
    {"n": 7,  "id": "source_answer",       "kind": "action",  "route": "/say",          "expect": "an answer grounded in the source"},
    {"n": 8,  "id": "source_chip_truth",   "kind": "check",   "route": "/say",          "expect": "source chip appears ONLY if the source was used"},
    {"n": 9,  "id": "inspect_source",      "kind": "surface", "route": "/sources",      "expect": "the source page is inspectable"},
    {"n": 10, "id": "inspect_memory",      "kind": "action",  "route": "/say",          "expect": "memory / What Vera Knows is inspectable"},
    {"n": 11, "id": "correct_vera",        "kind": "action",  "route": "/say",          "expect": "a correction is accepted (real DOM input)"},
    {"n": 12, "id": "correction_sane",     "kind": "check",   "route": "/say",          "expect": "correction behavior is sane (not gaslighting / not silent)"},
    {"n": 13, "id": "open_security",       "kind": "surface", "route": "/security",     "expect": "Security & Quarantine opens"},
    {"n": 14, "id": "active_contamination","kind": "check",   "route": "/security.json","expect": "active contamination summary is clear (0 active)"},
    {"n": 15, "id": "open_verification",   "kind": "surface", "route": "/verification", "expect": "Verification Dashboard opens"},
    {"n": 16, "id": "tier_visible",        "kind": "check",   "route": "/verification.json","expect": "release-tier state is visible (4 rungs)"},
    {"n": 17, "id": "open_observation",    "kind": "surface", "route": "/observatory",  "expect": "Observation Dashboard opens"},
    {"n": 18, "id": "open_living_map",     "kind": "surface", "route": "/living-map",   "expect": "Living Map opens"},
    {"n": 19, "id": "open_host",           "kind": "surface", "route": "/console",      "expect": "Host Health / Founder Console opens"},
    {"n": 20, "id": "delete_forget",       "kind": "action",  "route": "/say",          "expect": "a delete/forget request is honored"},
    {"n": 21, "id": "confirm_effect",      "kind": "check",   "route": "/say",          "expect": "the delete/forget effect is real"},
    {"n": 22, "id": "speed_question",      "kind": "action",  "route": "/say",          "expect": "a speed-sensitive question answers"},
    {"n": 23, "id": "latency_budget",      "kind": "check",   "route": "/say",          "expect": "warm latency within budget (<8s normal chat)"},
    {"n": 24, "id": "console_clean",       "kind": "check",   "route": "console",       "expect": "no browser console P0/P1"},
    {"n": 25, "id": "no_scary_events",     "kind": "check",   "route": "/security.json","expect": "no unexplained scary red events shown as active"},
]

# budgets (directive §4.3) — warm normal chat target <8s, hard fail >12s; greeting/fast-path <2s.
LATENCY_BUDGET_MS = {"normal_chat_target": 8000, "normal_chat_hardfail": 12000, "greeting_target": 2000}
SURFACE_TITLES = {
    "/": "Vera", "/security": "Security & Quarantine", "/verification": "Verification Dashboard",
    "/observatory": "Observatory", "/living-map": "Living Map", "/console": "Founder Console",
    "/reality": "Total Reality", "/trust": "Trust Ledger", "/consent": "Consent",
}
