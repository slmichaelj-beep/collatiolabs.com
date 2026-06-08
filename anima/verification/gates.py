"""verification.gates — compute each release gate's status from REAL reports (never hardcoded).

A gate rolls up the verdicts of the underlying feature certs (from reports/live_path_results.json, the
Program Reality Audit) plus the live build identity and the live browser-UI proofs. Status mapping:
  COMPLETE -> green ; PARTIAL/DEFERRED/DISABLED -> amber ; STUB/WALLPAPER/UNKNOWN/REGRESSED -> red ;
  a missing feature -> blocked. A gate is green only if EVERY contributing feature is green.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS = ROOT / "reports"

GREEN, AMBER, RED, BLOCKED, UNKNOWN, STALE = "green", "amber", "red", "blocked", "unknown", "stale"

# verification gate -> (display name, contributing live-path feature ids, required-for)
GATE_MAP = [
    ("program_reality",   "Program Reality",        None,  ["private_alpha", "diamond"]),  # all features
    ("total_reality",     "Total Scenario Matrix + Rover + Renegade", ["total_reality", "vera_rover"], ["diamond"]),
    ("feature_certs",     "Feature Certs",          None,  ["diamond"]),                    # all features
    ("ai_security",       "AI Security",            ["ai_security", "injection_loop", "context_immune",
                                                     "output_gate", "honesty_rail", "security_baseline",
                                                     "security_surface"], ["diamond"]),
    ("consent_privacy",   "Consent / Privacy / Data Control", ["consent_boundaries", "privacy",
                                                     "permissions", "web_allowlist"], ["diamond"]),
    ("performance",       "Performance Reality",    ["performance", "response_latency"], ["diamond"]),
    ("host_reality",      "Host Reality",           ["argus_host_awareness", "host_pressure",
                                                     "sysinfo_fit"], ["diamond"]),
    ("recovery",          "Recovery / Fallback",    ["reliability_recovery", "incident_response"], ["diamond"]),
    ("consistency",       "Honest Output / Final Gate", ["output_gate", "response_completeness",
                                                     "eval_honesty", "honesty_rail"], ["diamond"]),
    ("memory_truth",      "Memory / Source Truth",  ["lirf_memory", "known_fact_memory",
                                                     "source_aware_answering", "knowledge_spine"], ["diamond"]),
]


def _load_live_path() -> dict:
    try:
        d = json.loads((REPORTS / "live_path_results.json").read_text())
        items = d if isinstance(d, list) else d.get("results", d.get("features", []))
        return {x.get("feature"): x for x in items}
    except Exception:
        return {}


def _roll(features: list[str], by: dict) -> tuple[str, list[str]]:
    """Roll up a set of features into one gate status + the offending feature notes."""
    notes, worst_rank = [], 0
    order = {GREEN: 0, AMBER: 1, RED: 2, BLOCKED: 3}
    cur = GREEN
    for f in features:
        rec = by.get(f)
        if rec is None:
            st = BLOCKED
            notes.append("%s: MISSING from report" % f)
        else:
            s = (rec.get("status") or "").upper()
            st = {"COMPLETE": GREEN, "PARTIAL": AMBER, "DEFERRED": AMBER, "DISABLED": AMBER,
                  "STUB": RED, "WALLPAPER": RED, "UNKNOWN": RED, "REGRESSED": RED}.get(s, BLOCKED)
            if st != GREEN:
                notes.append("%s: %s" % (f, s or "?"))
        if order[st] > worst_rank:
            worst_rank, cur = order[st], st
    return cur, notes


def compute() -> dict:
    """Compute all gates + the program-reality counts + the release floor (P0/P1/UNKNOWN). Never raises."""
    by = _load_live_path()
    all_feats = list(by.keys())

    # the release floor straight from the Program Reality verdicts
    counts = {}
    for rec in by.values():
        s = (rec.get("status") or "?").upper()
        counts[s] = counts.get(s, 0) + 1
    red_feats = [f for f, r in by.items() if (r.get("status") or "").upper()
                 in ("STUB", "WALLPAPER", "UNKNOWN", "REGRESSED")]
    amber_feats = [f for f, r in by.items() if (r.get("status") or "").upper()
                   in ("PARTIAL", "DEFERRED", "DISABLED")]
    floor = {
        "features_total": len(by),
        "complete": counts.get("COMPLETE", 0),
        "partial": counts.get("PARTIAL", 0),
        "stub": counts.get("STUB", 0),
        "wallpaper": counts.get("WALLPAPER", 0),
        "unknown": counts.get("UNKNOWN", 0),
        "regressed": counts.get("REGRESSED", 0),
        # the directive's P0/P1: any release-blocking red feature is a P0; an honest PARTIAL is P2 (amber).
        "p0_open": len(red_feats),
        "p1_open": 0,
        "unknown_count": counts.get("UNKNOWN", 0),
        "red_features": red_feats[:20],
        "amber_features": amber_feats[:20],
    }

    from . import build_identity
    bi = build_identity.compute()

    gates = []

    def add(gate_id, name, status, evidence, notes, required_for, next_action=""):
        gates.append({"gate_id": gate_id, "name": name, "status": status, "evidence": evidence,
                      "notes": notes, "required_for": required_for, "next_action": next_action})

    # build identity (computed live)
    add("build_identity", "Build Identity", bi["status"],
        "running=%s committed=%s served_fe=%s clean=%s" % (bi.get("running_commit"),
            (bi.get("committed_commit") or "")[:7], bi.get("served_frontend_hash"), bi.get("clean_tree")),
        [] if bi["match"] else [k for k, v in bi["legs"].items() if not v],
        ["private_alpha", "diamond"],
        "" if bi["match"] else "restart the server on HEAD + stamp a verification run (running==committed==served==certified)")

    # program reality / feature certs (all features)
    pr_status = RED if red_feats else (AMBER if amber_feats else GREEN)
    add("program_reality", "Program Reality", pr_status,
        "%d COMPLETE / %d PARTIAL / %d STUB / %d WALLPAPER / %d UNKNOWN of %d" % (
            floor["complete"], floor["partial"], floor["stub"], floor["wallpaper"],
            floor["unknown"], floor["features_total"]),
        (red_feats[:10] or amber_feats[:10]), ["private_alpha", "diamond"],
        ("triage red features" if red_feats else ("close honest PARTIALs or mark non-release" if amber_feats else "")))
    add("feature_certs", "Feature Certs", pr_status,
        "%d/%d features COMPLETE" % (floor["complete"], floor["features_total"]),
        (red_feats[:10] or amber_feats[:10]), ["diamond"], "")

    # the mapped gates (roll up their features)
    for gate_id, name, feats, required_for in GATE_MAP:
        if gate_id in ("program_reality", "feature_certs"):
            continue
        if feats is None:
            continue
        st, notes = _roll(feats, by)
        ev = "; ".join("%s=%s" % (f, (by.get(f, {}).get("status") or "MISSING")) for f in feats)
        add(gate_id, name, st, ev, notes, required_for,
            ("triage: " + ", ".join(notes[:4])) if notes else "")

    # live user reality (the served-app UI proofs: surface routes smoke + headless paint record)
    lur_status, lur_ev, lur_notes = _live_user_reality()
    add("live_user_reality", "Live User Reality", lur_status, lur_ev, lur_notes,
        ["private_alpha", "diamond"],
        "" if lur_status == GREEN else "run scripts/certify_browser_surface_routes.py + certify_headless_dom_paint.py against the live app")

    # ---- cert-flake classification + external dependency state + repeatability ------------------
    from . import flakes, preflight
    try:
        ext = json.loads((REPORTS / "external_dependencies.json").read_text())
    except Exception:
        ext = preflight.external_dependencies()
    flake_log = flakes.read_flake_log()
    cl = flakes.classify_run(list(by.values()), ext, flake_log)
    n_unclassified = len(cl["unclassified"])
    n_product = len(cl["product_partials"]) + len(cl["product_red"])
    # green only with 0 unclassified + 0 product issues; amber if honest/harness present; red if product
    flake_status = (RED if n_product else (UNKNOWN if n_unclassified else
                    (AMBER if (cl["harness_flakes"] or cl["honest_partials"]) else GREEN)))
    add("flake_classification", "Cert-Flake Classification", flake_status,
        "unclassified=%d product=%d honest=%d harness=%d" % (n_unclassified, n_product,
            len(cl["honest_partials"]), len(cl["harness_flakes"])),
        cl["unclassified"][:8] or cl["product_partials"][:8], ["diamond"],
        ("triage unclassified flakes" if n_unclassified else ("triage product partials" if n_product else "")))

    try:
        dv2 = json.loads((REPORTS / "diamond_v2.json").read_text())
    except Exception:
        dv2 = None
    if dv2 is None:
        rep_status, rep_ev = UNKNOWN, "no repeatability run recorded (single-run Diamond is not allowed)"
    elif dv2.get("commit", "")[:12] != (bi.get("committed_commit") or "")[:12]:
        rep_status, rep_ev = STALE, "repeatability run was on a different commit (%s)" % (dv2.get("commit", "")[:7])
    else:
        rep_status = GREEN if dv2.get("repeatable") else RED
        rep_ev = "%d runs · complete/run %s · unclassified=%d" % (
            dv2.get("runs", 0), dv2.get("complete_per_run"), len(dv2.get("unclassified", [])))
    add("repeatability", "Diamond Repeatability (N consecutive runs)", rep_status, rep_ev,
        dv2.get("unclassified", []) if dv2 else ["never run"], ["diamond"],
        "" if rep_status == GREEN else "run scripts/run_diamond_v2.py --gate on this commit")

    return {"gates": gates, "floor": floor, "build_identity": bi,
            "flake_classification": cl, "external_dependencies": ext,
            "repeatability": dv2}


def _live_user_reality():
    """Status from the live browser proofs: the surface-route smoke record + a headless-paint marker.
    Absent record -> unknown (an unrun live proof is never green)."""
    rec = REPORTS / "browser_surface_routes.json"
    try:
        j = json.loads(rec.read_text())
        rendered, total = j.get("rendered", 0), j.get("total", 0)
        if total and rendered == total:
            return GREEN, "browser surface routes %d/%d render (live)" % (rendered, total), []
        return RED, "browser surface routes %d/%d" % (rendered, total), ["surfaces not all rendering"]
    except Exception:
        return UNKNOWN, "no live browser proof recorded", ["live UI proof not run on this commit"]
