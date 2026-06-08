#!/usr/bin/env python3
"""certify_verification_dashboard — the Verification Dashboard obeys the no-wallpaper law it enforces.

The dashboard's verdict is COMPUTED from real reports + the live build identity, never hardcoded. This
cert proves the computation cannot be tricked into green:

  1. WIRED + SERVED    — verification.html exists, GET /verification + /verification.json are wired, and
                         the page carries no hardcoded RELEASE/DIAMOND verdict (it renders from the JSON).
  2. COMPUTED FROM REPORTS — dashboard.data() derives its gates from the real Program Reality report
                         (reports/live_path_results.json), not invented; build identity is computed live.
  3. DIAMOND BITES — P0     — release_decision.decide() returns diamond_eligible only for an all-green,
                         clean-build input; injecting one P0 (a red feature) flips it to not-eligible.
  4. DIAMOND BITES — UNKNOWN — an UNKNOWN in the floor flips diamond off.
  5. DIAMOND BITES — BUILD MISMATCH — build identity not green (running != certified, or a stale served
                         bundle) flips diamond off even when every gate is green.
  6. DIAMOND BITES — RED GATE — a single red required gate flips the release state to RED.

Hermetic for the decision teeth (pure function); the served-page leg is checked if the server is up.
Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("VERIFICATION DASHBOARD — the release-truth board cannot fake green (computed, with teeth)")
    print("=" * 92)

    from anima.verification import dashboard, release_decision, gates as gmod

    # ---- 1 wired + served, no hardcoded verdict -------------------------------------------------
    html = (ROOT / "anima" / "web" / "verification.html")
    srv = (ROOT / "anima" / "server.py").read_text()
    html_txt = html.read_text() if html.exists() else ""
    no_hardcoded = ("RELEASE: GREEN" not in html_txt) and ("diamond_eligible:true" not in html_txt.replace(" ", ""))
    ck("1. verification.html exists, /verification + /verification.json wired, no hardcoded verdict",
       html.exists() and "/verification" in srv and "/verification.json" in srv
       and "verification import dashboard" in srv and no_hardcoded and "fetch('/verification.json'" in html_txt)

    # ---- 2 computed from real reports -----------------------------------------------------------
    d = dashboard.data()
    gate_ids = {g["gate_id"] for g in d.get("gates", [])}
    pr = next((g for g in d["gates"] if g["gate_id"] == "program_reality"), {})
    ck("2. the dashboard computes its gates from the real Program Reality report (build identity live)",
       isinstance(d.get("gates"), list) and len(gate_ids) >= 8
       and {"build_identity", "program_reality", "live_user_reality"} <= gate_ids
       and "COMPLETE" in (pr.get("evidence") or ""))

    # ---- teeth: feed decide() synthetic inputs ---------------------------------------------------
    def G(status, rf=("diamond", "private_alpha")):
        return {"gate_id": "g_" + status, "status": status, "required_for": list(rf), "next_action": ""}

    all_green = [G("green"), {"gate_id": "build_identity", "status": "green", "required_for": ["diamond", "private_alpha"]},
                 {"gate_id": "live_user_reality", "status": "green", "required_for": ["diamond", "private_alpha"]}]
    floor0 = {"p0_open": 0, "p1_open": 0, "unknown_count": 0, "partial": 0}
    bi_green = {"status": "green", "running_commit": "abc1234"}

    base = release_decision.decide(all_green, floor0, bi_green)
    ck("3a. an all-green, clean-build input IS diamond-eligible (the check can say yes)",
       base["diamond_eligible"] is True and base["color"] == "green")

    p0 = release_decision.decide(all_green, {**floor0, "p0_open": 1}, bi_green)
    ck("3b. DIAMOND BITES (P0) — one P0 open flips diamond off + state to RED",
       p0["diamond_eligible"] is False and p0["color"] == "red")

    unk = release_decision.decide(all_green, {**floor0, "unknown_count": 1}, bi_green)
    ck("4. DIAMOND BITES (UNKNOWN) — an UNKNOWN flips diamond off",
       unk["diamond_eligible"] is False)

    mismatch = release_decision.decide(all_green, floor0, {"status": "red", "running_commit": "abc1234"})
    ck("5. DIAMOND BITES (BUILD MISMATCH) — build identity not green flips diamond off even if gates green",
       mismatch["diamond_eligible"] is False)

    red_gate = release_decision.decide([G("red")] + all_green, floor0, bi_green)
    ck("6. DIAMOND BITES (RED GATE) — a single red required gate flips the state to RED",
       red_gate["color"] == "red" and red_gate["diamond_eligible"] is False)

    # ---- cert-flake hardening teeth -------------------------------------------------------------
    rep_unknown = release_decision.decide(
        all_green + [{"gate_id": "repeatability", "status": "unknown", "required_for": ["diamond"]}], floor0, bi_green)
    ck("7. NO SINGLE-RUN DIAMOND — an un-run repeatability gate (unknown) flips diamond off",
       rep_unknown["diamond_eligible"] is False)

    flake_unknown = release_decision.decide(
        all_green + [{"gate_id": "flake_classification", "status": "unknown", "required_for": ["diamond"]}], floor0, bi_green)
    ck("8. NO UNCLASSIFIED FLAKE — a flake_classification gate with an unclassified flake flips diamond off",
       flake_unknown["diamond_eligible"] is False)

    # the live dashboard exposes the cert-flake hardening surface (classification + deps + repeatability)
    gids = {g["gate_id"] for g in d.get("gates", [])}
    cls = d.get("classification", {})
    ck("9. the dashboard surfaces the four flake classes + external dependency state + repeatability",
       {"flake_classification", "repeatability"} <= gids
       and {"intentional_external_partial", "env_dependency_partial", "harness_flake", "unclassified"} <= set(cls.keys())
       and isinstance(d.get("external_dependencies"), list)
       and "unclassified_flakes" in d.get("top", {}) and "repeatability_confirmed" in d.get("top", {}))

    # ---- served leg (only if the server is up) --------------------------------------------------
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/version", timeout=5) as r:
            up = r.status == 200
    except Exception:
        up = False
    if up:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/verification", timeout=6) as r:
                page_ok = r.status == 200 and b"Verification Dashboard" in r.read()
        except Exception:
            page_ok = False
        ck("10. GET /verification serves the dashboard page on the live server", page_ok)
    else:
        print("  --   10. (skipped — server not up; decision teeth above are server-independent)")

    print("\n  gates computed: %d · release_state=%s · diamond_eligible=%s"
          % (len(gate_ids), d.get("top", {}).get("release_state"), d.get("top", {}).get("diamond_eligible")))
    print("VERIFICATION-DASHBOARD CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
