#!/usr/bin/env python3
"""
inventory_features — Program Reality Audit, Phase 1 FOUNDATION: the FEATURE INVENTORY.

The program's law: "No feature is complete because code/UI/endpoint/trace exists — only when the
live user path is proven end-to-end." This scanner is the BASE LAYER everything else (the live-path
certs, the no-wallpaper cross-checks, the audit dashboard) consumes. It enumerates every CLAIMED
feature surface and writes a single normalized inventory that downstream tooling reads.

WHAT IT DOES (PURE STATIC ANALYSIS — read-only).
  Detects a "claim" from five surfaces and unions them by feature slug:
    * ui        — controls in anima/web/index.html: <button id=…>, data-cap=…, the Add-Knowledge
                  pill + menu, toolbar items, settings toggles, status chips, the dashboard knob.
    * endpoint  — every dispatched path in anima/server.py do_GET / do_POST (`u.path == …` /
                  `path == …` / `path in (…)`), GET and POST.
    * cap       — every BOOL_KEYS / ENUM_KEYS capability in anima/caps.py.
    * cert      — every scripts/certify_*.py and scripts/gate0_*.py (each is a claimed guarantee).
    * docstring — the one-line module claim atop each anima/*.py.

  Each inventory entry:
    { "feature", "claim", "claimed_by":[surfaces], "owner_modules":[files],
      "user_visible_entry":bool, "durable":bool|"unknown", "status":"UNTESTED" }

HARD CONTRACT. Reads files only. Writes ONLY to reports/ (reports/feature_inventory.json + .md).
NEVER writes .anima, never starts the server, never hits 127.0.0.1:8765, never runs a live turn.
Deterministic + fast + stdlib-only (ast + re + pathlib + json).

CLI:
    python3 scripts/inventory_features.py            # write both reports + print the summary
    python3 scripts/inventory_features.py --json     # print the JSON payload to stdout too
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANIMA = ROOT / "anima"
SCRIPTS = ROOT / "scripts"
WEB_INDEX = ANIMA / "web" / "index.html"
REPORTS = ROOT / "reports"

# The ONLY directory this tool may write. A belt-and-suspenders guard (see _safe_write) refuses to
# write anywhere else — so a clean concurrent Gate 0 Prime freeze-proof over .anima stays valid.
_WRITE_ALLOWED = REPORTS.resolve()


# ===================================================================================================
# Slug + feature mapping. Surfaces are heterogeneous (a button id, a URL path, a cap key, a file
# name, a module). We map each raw claim onto a stable feature SLUG so the inventory unions them:
# e.g. the `/intake/plan` endpoint, the `tbAdd` pill, and intake.py's docstring all roll up to the
# `universal_knowledge_intake` feature. Mapping is deterministic + table-driven (no heuristics that
# could reorder run-to-run).
# ===================================================================================================

# endpoint path  ->  (feature_slug, one-line claim)
_ENDPOINT_FEATURE = {
    "/": ("app_shell", "Serve the app shell (public; holds no secrets)"),
    "/index.html": ("app_shell", "Serve the app shell (public; holds no secrets)"),
    "/version": ("deploy_fingerprint", "LAW 005: report the commit THIS process is running (git == running)"),
    "/auth/status": ("face_id_unlock", "Report passkey/Face-ID enrollment + required status"),
    "/auth/register/begin": ("face_id_unlock", "WebAuthn passkey enrollment — begin"),
    "/auth/register/finish": ("face_id_unlock", "WebAuthn passkey enrollment — finish"),
    "/auth/login/begin": ("face_id_unlock", "WebAuthn Face-ID unlock — begin"),
    "/auth/login/finish": ("face_id_unlock", "WebAuthn Face-ID unlock — finish"),
    "/auth/disable": ("face_id_unlock", "Disable the enrolled passkey"),
    "/audio": ("voice_io", "Serve the last synthesized reply WAV"),
    "/audio/": ("voice_io", "Serve a rendered briefing/reminder audio file (basename-only)"),
    "/state": ("affective_core", "Report the heart's current feeling vector"),
    "/persona": ("persona_editor", "Get/save the creature's persona text"),
    "/values": ("values_editor", "Get/save the creature's values toggles"),
    "/dials": ("personality_dials", "Get/save the personality dials (manner, never honesty)"),
    "/identity/export": ("portable_self", "Export the whole mind/identity as a portable file"),
    "/identity/import": ("portable_self", "Import an identity bundle, adopt the character"),
    "/capabilities": ("capability_truth", "Get/save the per-creature capability ledger (default-OFF)"),
    "/brain": ("brain_select", "Get/save the brain (local vs cloud), verify a cloud key"),
    "/models": ("local_model_manager", "List fit-checked local models"),
    "/models/select": ("local_model_manager", "Switch to a chosen local model"),
    "/models/pull": ("local_model_manager", "Download a local model"),
    "/models/remove": ("local_model_manager", "Remove a local model"),
    "/models/cleanup": ("local_model_manager", "Remove all unused local models"),
    "/metrics": ("growth_dashboard", "Operator diagnostics: identity-health metrics (env ANIMA_METRICS=1)"),
    "/talk": ("live_turn", "One live conversational turn (text in, reply out)"),
    "/say": ("live_turn", "One live turn, text-only (phone speaks with its own voice)"),
    "/tts": ("voice_io", "Synthesize one chunk of text to a WAV (Kokoro)"),
    "/stt": ("voice_io", "Transcribe uploaded audio to text (Whisper)"),
    "/imessage/draft": ("messaging_send", "Create a pending iMessage draft (sends nothing)"),
    "/mail/draft": ("messaging_send", "Create a pending Mail draft (sends nothing)"),
    "/imessage/send": ("messaging_send", "Send a previously-drafted iMessage (the only send path)"),
    "/mail/send": ("messaging_send", "Send a previously-drafted email (the only send path)"),
    "/imessage/read": ("messaging_read", "Read recent iMessages (gated on capability)"),
    "/mail/read": ("messaging_read", "Read recent mail (gated on capability)"),
    "/web/fetch": ("web_fetch", "Read-only web fetch, allow-list restricted"),
    "/loc": ("proactive_outreach", "Persist the phone's location for the proactive briefing"),
    "/device": ("proactive_outreach", "Persist the phone's push token(s) for reminders/calls"),
    "/acknowledge": ("proactive_outreach", "Acknowledge a reminder so it won't escalate to a call"),
    "/intake/plan": ("universal_knowledge_intake", "Stage raw + run Wave-1 plan (no durable write)"),
    "/intake/approve": ("universal_knowledge_intake", "Re-parse from staging + commit on the user's approval"),
    "/intake/queue": ("universal_knowledge_intake", "List every ingested source + its lifecycle state"),
    "/intake/trace": ("universal_knowledge_intake", "Per-source intake MRI trace + render"),
    "/library": ("knowledge_library", "List normalized knowledge-library items (section-filtered)"),
    "/library/edit": ("knowledge_library", "Reprocess/archive/delete a library item (audited)"),
    "/search": ("labeled_search", "Cross-store labeled search over the knowledge stores"),
    "/host/awareness": ("argus_host_awareness", "Human-level host/network picture (read-only Argus; cloud-redacted)"),
    "/host/timeline": ("argus_host_awareness", "Argus's narrated recent history (read-only)"),
    "/host/action_log": ("argus_host_awareness", "Argus's audit log of actions IT took (read-only)"),
    "/host/certification": ("argus_host_awareness", "The Argus certification handshake Vera verified before integrating"),
}

# capability key  ->  (feature_slug, claim)
_CAP_FEATURE = {
    "imessage": ("messaging_send", "Capability: send iMessage (draft→confirm→send)"),
    "mail": ("messaging_send", "Capability: send mail (draft→confirm→send)"),
    "web": ("web_fetch", "Capability: read allow-listed web sites"),
    "imessage_read": ("messaging_read", "Capability: read recent iMessages"),
    "mail_read": ("messaging_read", "Capability: read recent mail"),
    "identity_agency": ("identity_sandbox", "Capability: Identity & Agency organs (held/frozen until 2026-07-03)"),
    "grow_intelligence": ("lerf_runtime", "Capability: autonomous skill growth master switch (LERF Phase 6)"),
    "host_awareness": ("argus_host_awareness", "Capability: read host + outbound-network state (read-only Argus)"),
    "curiosity": ("curiosity_engine", "Setting: how often Vera surfaces a contextual question"),
    "grow_mode": ("lerf_runtime", "Setting: autonomous growth intensity (off/low/medium/high/research)"),
}

# A cert/gate script file stem -> (feature_slug, claim). Anything not listed falls back to its own
# stem as the feature slug (so a new cert is still inventoried as its own guarantee).
_CERT_FEATURE = {
    "certify_no_stubs": ("universal_knowledge_intake",
                         "Cert: UKI is REAL end-to-end (UI→endpoint→storage→retrieval→trace→survival)"),
    "certify_argus_integration": ("argus_host_awareness",
                                  "Cert: the Vera↔Argus first wave (read-only, certified, no host action)"),
    "certify_whole_mri": ("whole_system_mri",
                          "Cert: the Whole-System MRI (turn_id on every turn; unified trace; viewer renders)"),
    "gate0_prime": ("gate0_prime",
                    "Cert: THE certificate — passes only if every hardening target passes; real Vera byte-unchanged"),
    "gate0": ("gate0_prime", "Cert: architecture is SAFE TO GROW (six pass-conditions)"),
    "gate0_prime_experience": ("response_completeness",
                               "Cert: live experience stays grounded + complete under high-volume probes"),
    "gate0_prime_longhorizon": ("gate0_prime", "Cert: bounded + frozen across 10y/20y/50y"),
    "gate0_prime_population": ("gate0_prime", "Cert: fast + linear across 10k/100k/1M objects"),
    "gate0_prime_recovery": ("gate0_prime", "Cert: recovery never silently accepts corruption"),
    "gate0_prime_merge_growth": ("gate0_prime", "Cert: merge gate can't be tricked + autonomous growth stays safe"),
    "gate0_experience": ("response_completeness", "Cert (Gate 0 test 10): human experience"),
    "gate0_growth": ("lerf_runtime", "Cert (Gate 0 tests 3+4): growth & routing"),
    "gate0_guards": ("gate0_prime", "Cert (Gate 0 tests 5+6): guards & reality"),
    "gate0_resource": ("gate0_prime", "Cert (Gate 0 tests 8+9): resource & recovery"),
    "gate0_twin": ("identity_sandbox", "Cert (Gate 0 tests 1,2,7): twin safety / zero identity mutation"),
}

# module file stem -> feature_slug (so the docstring claim unions onto the right feature). Modules
# not listed are inventoried under their own stem as a `docstring`-only claim (still a claim!).
_MODULE_FEATURE = {
    "intake": "universal_knowledge_intake",
    "intake_parsers": "universal_knowledge_intake",
    "intake_queue": "universal_knowledge_intake",
    "intake_search": "labeled_search",
    "source_aware": "source_aware_answering",
    "host_awareness": "argus_host_awareness",
    "host_window": "whole_system_mri",
    "host_access": "host_access_write",
    "whole_mri": "whole_system_mri",
    "whole_mri_shape": "whole_system_mri",
    "telemetry": "mri_trace",
    "caps": "capability_truth",
    "spine": "known_fact_memory",
    "memory_lirf": "known_fact_memory",
    "lerf": "lerf_runtime",
    "lerf_router": "lerf_runtime",
    "lerf_grow": "lerf_runtime",
    "lerf_distill": "lerf_runtime",
    "identity_sandbox": "identity_sandbox",
    "self_narrative": "identity_sandbox",
    "metrics": "growth_dashboard",
    "growth": "growth_dashboard",
    "mouth": "response_completeness",
    "curiosity": "curiosity_engine",
    "loops": "conversation_repair",
    "route": "capability_truth",
    "rail": "capability_truth",
    "cloud": "brain_select",
    "models": "local_model_manager",
    "dials": "personality_dials",
    "passkey": "face_id_unlock",
    "proactive": "proactive_outreach",
    "reminders": "proactive_outreach",
    "webget": "web_fetch",
}

# Features whose entry point is a thing the USER directly clicks/types (a button, the chat box, a
# settings toggle, the dashboard knob). Everything else is internal/operator-facing. Used to set
# user_visible_entry deterministically (a cap or a UI control always implies user-visible).
_USER_VISIBLE_FEATURES = {
    "universal_knowledge_intake", "source_aware_answering", "knowledge_library", "labeled_search",
    "live_turn", "voice_io", "messaging_send", "messaging_read", "web_fetch", "argus_host_awareness",
    "capability_truth", "personality_dials", "persona_editor", "values_editor", "portable_self",
    "brain_select", "local_model_manager", "face_id_unlock", "identity_sandbox", "growth_dashboard",
    "app_shell", "curiosity_engine",
}

# Features that persist to durable storage (.anima / a ledger that survives restart). "unknown"
# where the inventory cannot tell statically — Phase-1 keeps it honest; the live-path cert resolves.
_DURABLE = {
    "universal_knowledge_intake": True, "source_aware_answering": True, "knowledge_library": True,
    "labeled_search": True, "known_fact_memory": True, "lerf_runtime": True, "capability_truth": True,
    "personality_dials": True, "persona_editor": True, "values_editor": True, "portable_self": True,
    "brain_select": True, "proactive_outreach": True, "identity_sandbox": True, "whole_system_mri": True,
    "mri_trace": True, "messaging_send": False, "messaging_read": False, "web_fetch": False,
    "voice_io": False, "live_turn": False, "app_shell": False, "deploy_fingerprint": False,
    "growth_dashboard": False, "affective_core": True, "host_access_write": "unknown",
    "conversation_repair": "unknown", "curiosity_engine": True, "argus_host_awareness": False,
    "response_completeness": False, "gate0_prime": "unknown", "face_id_unlock": True,
    "local_model_manager": True,
}


def _feature_for_module(stem: str) -> str:
    return _MODULE_FEATURE.get(stem, stem)


def _feature_for_cert(stem: str):
    return _CERT_FEATURE.get(stem, (stem, f"Cert/gate guarantee: {stem}"))


# ===================================================================================================
# SURFACE SCANNERS — each returns a list of raw claims: dicts with feature/claim/surface/module.
# ===================================================================================================
def scan_endpoints() -> list:
    """Every dispatched path in server.py do_GET/do_POST. We parse the AST and read the string
    literals compared against `u.path` / `path` (== and `in (...)`), so a new branch is picked up
    structurally — not by a brittle line regex. Falls back to a regex sweep if the AST shape shifts."""
    claims = []
    seen = set()
    src = (ANIMA / "server.py").read_text(encoding="utf-8", errors="replace")

    def _emit(path_literal: str):
        if not isinstance(path_literal, str) or not path_literal.startswith("/"):
            return
        if path_literal in seen:
            return
        seen.add(path_literal)
        feat, claim = _ENDPOINT_FEATURE.get(
            path_literal, (("endpoint" + path_literal.replace("/", "_")).strip("_"),
                           f"HTTP endpoint {path_literal}"))
        claims.append({"feature": feat, "claim": claim, "surface": "endpoint",
                       "module": "anima/server.py", "detail": path_literal})

    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            # `x == "literal"` comparisons
            if isinstance(node, ast.Compare):
                lits = [c.value for c in node.comparators
                        if isinstance(c, ast.Constant) and isinstance(c.value, str)]
                # also `"lit" in (...)` / `path in (...)` tuples
                for c in node.comparators:
                    if isinstance(c, (ast.Tuple, ast.List)):
                        lits.extend(e.value for e in c.elts
                                    if isinstance(e, ast.Constant) and isinstance(e.value, str))
                for lit in lits:
                    _emit(lit)
            # `u.path.startswith("/audio/")` etc.
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "startswith":
                for a in node.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        _emit(a.value)
    except SyntaxError:
        for m in re.finditer(r'(?:u\.path|path)\s*(?:==|in)\s*\(?\s*["\']([^"\']+)["\']', src):
            _emit(m.group(1))
    return claims


def scan_caps() -> list:
    """Every BOOL_KEYS flag + ENUM_KEYS setting in caps.py (read from the AST so the registry is the
    source of truth — not a copy)."""
    claims = []
    src = (ANIMA / "caps.py").read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    bool_keys, enum_keys = [], []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "BOOL_KEYS" and isinstance(node.value, ast.Tuple):
                    bool_keys = [e.value for e in node.value.elts
                                 if isinstance(e, ast.Constant)]
                if isinstance(tgt, ast.Name) and tgt.id == "ENUM_KEYS" and isinstance(node.value, ast.Dict):
                    enum_keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    for k in list(bool_keys) + list(enum_keys):
        feat, claim = _CAP_FEATURE.get(k, (f"cap_{k}", f"Capability/setting: {k}"))
        claims.append({"feature": feat, "claim": claim, "surface": "cap",
                       "module": "anima/caps.py", "detail": k})
    return claims


# UI control patterns. Each tuple is (regex, feature_slug, claim). Matched against the index.html
# snapshot (read ONCE — the file may be edited concurrently, so we do not depend on it being stable).
_UI_PATTERNS = [
    (r'id="tbAdd"', "universal_knowledge_intake", "UI: '+ Add Knowledge' pill (the knowledge-base entry)"),
    (r'id="amUpload"', "universal_knowledge_intake", "UI: Add-menu — Upload file"),
    (r'id="amLink"', "universal_knowledge_intake", "UI: Add-menu — Paste a link"),
    (r'id="amText"', "universal_knowledge_intake", "UI: Add-menu — Paste text"),
    (r'id="amQueue"', "universal_knowledge_intake", "UI: Add-menu — View intake queue"),
    (r'id="pasteOverlay"', "universal_knowledge_intake", "UI: paste-a-link / paste-text overlay"),
    (r'id="queueOverlay"', "universal_knowledge_intake", "UI: intake-queue overlay (per-item MRI)"),
    (r'class="intake-approve"', "universal_knowledge_intake", "UI: per-source Approve button (control picker)"),
    (r'id="tbLib"', "knowledge_library", "UI: Library drawer toggle"),
    (r'id="libChips"', "knowledge_library", "UI: Library section filter chips"),
    (r'id="tbSearch"', "labeled_search", "UI: Search panel toggle"),
    (r'id="searchInput"', "labeled_search", "UI: labeled cross-store search box"),
    (r'id="tbExport"', "export_menu", "UI: Copy/Export menu toggle"),
    (r'id="emExportMind"', "portable_self", "UI: Export whole mind archive"),
    (r'id="emExportSources"', "source_aware_answering", "UI: Export source summary"),
    (r'id="tbCode"', "code_context", "UI: code-context toolbar button"),
    (r'id="mic"', "voice_io", "UI: mic (tap-to-talk, barge-in)"),
    (r'id="mute"', "voice_io", "UI: voice on/off toggle"),
    (r'id="mriOverlay"', "mri_trace", "UI: intake MRI trace overlay"),
    (r'id="dashknob"', "growth_dashboard", "UI: dashboard knob (operator gauges + verdict)"),
    (r'id="dash"', "growth_dashboard", "UI: identity-health dashboard"),
    (r'id="dials"', "personality_dials", "UI: personality dials"),
    (r'id="caps"', "capability_truth", "UI: Access capability toggles (default-OFF)"),
    (r'data-cap="host_awareness"', "argus_host_awareness", "UI: 'Read host & network state' toggle (read-only)"),
    (r'data-cap="identity_agency"', "identity_sandbox", "UI: 'Identity & Agency' toggle (held/experimental)"),
    (r'data-cap="imessage_read"', "messaging_read", "UI: 'Read recent' iMessage toggle"),
    (r'data-cap="mail_read"', "messaging_read", "UI: 'Read recent' mail toggle"),
    (r'data-cap="imessage"', "messaging_send", "UI: iMessage 'Send (draft→confirm)' toggle"),
    (r'data-cap="mail"', "messaging_send", "UI: mail 'Send (draft→confirm)' toggle (live)"),
    (r'data-cap="web"', "web_fetch", "UI: 'Read allow-listed sites' toggle (soon)"),
    (r'id="provider"', "brain_select", "UI: brain provider selector (local vs cloud)"),
    (r'id="localModels"', "local_model_manager", "UI: local model manager"),
    (r'id="faceRow"', "face_id_unlock", "UI: Face-ID enable/disable"),
    (r'id="idexport"', "portable_self", "UI: Export self"),
    (r'id="idimport"', "portable_self", "UI: Import self"),
    (r'addSources', "source_aware_answering", "UI: 'based on …' source attribution chips"),
    (r'class="status-chip"', "knowledge_library", "UI: lifecycle status chips/dots"),
]


def scan_ui() -> list:
    """One-time snapshot of index.html; emit a claim per matched control pattern. Read-only and
    tolerant: if the file is missing we simply emit nothing (it may be edited concurrently)."""
    claims = []
    if not WEB_INDEX.exists():
        return claims
    html = WEB_INDEX.read_text(encoding="utf-8", errors="replace")
    for rx, feat, claim in _UI_PATTERNS:
        if re.search(rx, html):
            claims.append({"feature": feat, "claim": claim, "surface": "ui",
                           "module": "anima/web/index.html", "detail": rx})
    return claims


def scan_certs() -> list:
    """Every scripts/certify_*.py and scripts/gate0_*.py — each is a claimed guarantee. The claim is
    the cert's mapped purpose (or its own one-line docstring as a fallback)."""
    claims = []
    files = sorted(SCRIPTS.glob("certify_*.py")) + sorted(SCRIPTS.glob("gate0_*.py"))
    for fp in files:
        stem = fp.stem
        feat, claim = _feature_for_cert(stem)
        # prefer the mapped claim; otherwise the module's own first docstring line
        if stem not in _CERT_FEATURE:
            doc = _first_docline(fp)
            if doc:
                claim = doc
        claims.append({"feature": feat, "claim": claim, "surface": "cert",
                       "module": fp.relative_to(ROOT).as_posix(), "detail": stem})
    return claims


def _first_docline(fp: Path) -> str:
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return ""
    doc = ast.get_docstring(tree) or ""
    for line in doc.splitlines():
        if line.strip():
            return line.strip()
    return ""


def scan_docstrings() -> list:
    """The one-line module claim atop every anima/*.py (read via AST). Unioned onto the feature the
    module owns (via _MODULE_FEATURE); an unmapped module is inventoried under its own stem."""
    claims = []
    for fp in sorted(ANIMA.glob("*.py")):
        if fp.name == "__init__.py":
            continue
        doc = _first_docline(fp)
        if not doc:
            continue
        feat = _feature_for_module(fp.stem)
        claims.append({"feature": feat, "claim": doc, "surface": "docstring",
                       "module": fp.relative_to(ROOT).as_posix(), "detail": fp.stem})
    return claims


# ===================================================================================================
# AGGREGATION — union raw claims by feature slug into the inventory schema.
# ===================================================================================================
def build_inventory() -> dict:
    raw = []
    raw += scan_ui()
    raw += scan_endpoints()
    raw += scan_caps()
    raw += scan_certs()
    raw += scan_docstrings()

    feats = {}
    for c in raw:
        f = c["feature"]
        if f not in feats:
            feats[f] = {"feature": f, "claim": c["claim"], "claimed_by": set(),
                        "owner_modules": set(), "_surface_claims": {}}
        rec = feats[f]
        rec["claimed_by"].add(c["surface"])
        rec["owner_modules"].add(c["module"])
        # keep the most specific claim per surface so the .md can show provenance; prefer a
        # docstring/endpoint/cap claim as the headline (more descriptive than a UI id).
        rec["_surface_claims"].setdefault(c["surface"], c["claim"])

    # headline-claim preference order — pick the clearest sentence as the feature's claim.
    _claim_pref = ("docstring", "cert", "endpoint", "cap", "ui")
    entries = []
    for f, rec in feats.items():
        claim = rec["claim"]
        for s in _claim_pref:
            if s in rec["_surface_claims"]:
                claim = rec["_surface_claims"][s]
                break
        claimed_by = sorted(rec["claimed_by"])
        user_visible = (f in _USER_VISIBLE_FEATURES) or ("ui" in claimed_by) or ("cap" in claimed_by)
        durable = _DURABLE.get(f, "unknown")
        entries.append({
            "feature": f,
            "claim": claim,
            "claimed_by": claimed_by,
            "owner_modules": sorted(rec["owner_modules"]),
            "user_visible_entry": bool(user_visible),
            "durable": durable,
            "status": "UNTESTED",
        })
    entries.sort(key=lambda e: e["feature"])

    # summary count by surface (how many DISTINCT features carry a claim from each surface)
    by_surface = {s: 0 for s in ("ui", "endpoint", "cap", "cert", "docstring")}
    for e in entries:
        for s in e["claimed_by"]:
            if s in by_surface:
                by_surface[s] += 1
    # also count raw claims per surface (total hits, not distinct features)
    raw_by_surface = {s: 0 for s in by_surface}
    for c in raw:
        if c["surface"] in raw_by_surface:
            raw_by_surface[c["surface"]] += 1

    return {
        "audit": "program-reality / phase-1 / feature-inventory",
        "law": ("No feature is complete because code/UI/endpoint/trace exists — "
                "only when the live user path is proven end-to-end."),
        "feature_count": len(entries),
        "summary_by_surface": by_surface,
        "raw_claims_by_surface": raw_by_surface,
        "features": entries,
    }


def _safe_write(path: Path, text: str) -> None:
    """Write ONLY inside reports/. Refuses any other destination (so this scanner can never touch
    .anima or anything outside its lane)."""
    rp = path.resolve()
    if _WRITE_ALLOWED not in rp.parents and rp.parent != _WRITE_ALLOWED:
        raise RuntimeError(f"refusing to write outside reports/: {rp}")
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(text, encoding="utf-8")


def _render_md(inv: dict) -> str:
    lines = []
    lines.append("# Feature Inventory — Program Reality Audit (Phase 1 foundation)")
    lines.append("")
    lines.append(f"> **Law:** {inv['law']}")
    lines.append("")
    lines.append(f"**{inv['feature_count']} features** claimed across surfaces. Every status is "
                 "`UNTESTED` — the live-path cert fills these in later (this layer only enumerates "
                 "the CLAIMS).")
    lines.append("")
    s = inv["summary_by_surface"]
    r = inv["raw_claims_by_surface"]
    lines.append("## Claims by surface (distinct features / raw claim hits)")
    lines.append("")
    lines.append("| surface | features | raw claims |")
    lines.append("|---|---:|---:|")
    for k in ("ui", "endpoint", "cap", "cert", "docstring"):
        lines.append(f"| {k} | {s.get(k, 0)} | {r.get(k, 0)} |")
    lines.append("")
    lines.append("## Features")
    lines.append("")
    lines.append("| feature | claimed_by | user-visible | durable | claim |")
    lines.append("|---|---|:--:|:--:|---|")
    for e in inv["features"]:
        cb = ", ".join(e["claimed_by"])
        uv = "yes" if e["user_visible_entry"] else "no"
        du = "yes" if e["durable"] is True else ("no" if e["durable"] is False else "?")
        claim = e["claim"].replace("|", "\\|")
        lines.append(f"| `{e['feature']}` | {cb} | {uv} | {du} | {claim} |")
    lines.append("")
    lines.append("## Owner modules")
    lines.append("")
    for e in inv["features"]:
        mods = ", ".join(f"`{m}`" for m in e["owner_modules"])
        lines.append(f"- **`{e['feature']}`** — {mods}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="inventory_features",
        description="Program Reality Audit Phase 1: enumerate every CLAIMED feature surface "
                    "(read-only) and write reports/feature_inventory.{json,md}.")
    ap.add_argument("--json", action="store_true", help="also print the JSON payload to stdout")
    args = ap.parse_args(argv)

    inv = build_inventory()

    json_path = REPORTS / "feature_inventory.json"
    md_path = REPORTS / "feature_inventory.md"
    _safe_write(json_path, json.dumps(inv, indent=2, ensure_ascii=False) + "\n")
    _safe_write(md_path, _render_md(inv))

    s = inv["summary_by_surface"]
    print("FEATURE INVENTORY — Program Reality Audit (Phase 1 foundation)")
    print("=" * 70)
    print(f"  features (distinct, unioned by slug): {inv['feature_count']}")
    print("  claims by surface  (distinct features / raw hits):")
    r = inv["raw_claims_by_surface"]
    for k in ("ui", "endpoint", "cap", "cert", "docstring"):
        print(f"      {k:<10} {s.get(k, 0):>3} features   ({r.get(k, 0)} raw claims)")
    nuv = sum(1 for e in inv["features"] if e["user_visible_entry"])
    ndur = sum(1 for e in inv["features"] if e["durable"] is True)
    print(f"  user-visible-entry features: {nuv}")
    print(f"  durable features:            {ndur}  (rest: False or unknown)")
    print(f"  wrote: {json_path.relative_to(ROOT)}")
    print(f"  wrote: {md_path.relative_to(ROOT)}")
    print("  status of every feature: UNTESTED (the live-path cert resolves these)")

    if args.json:
        print()
        print(json.dumps(inv, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
