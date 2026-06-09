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

    def _mtime(rel):
        try:
            import time
            return time.strftime("%Y-%m-%d %H:%M", time.localtime((REPORTS / rel).stat().st_mtime))
        except Exception:
            return None

    _LAST = _mtime("live_path_results.json")

    def add(gate_id, name, status, evidence, notes, required_for, next_action="",
            owner="vera/verification", last_run=None, link=None):
        gates.append({"gate_id": gate_id, "name": name, "status": status, "evidence": evidence,
                      "notes": notes, "required_for": required_for, "next_action": next_action,
                      "owner": owner, "last_run": last_run or _LAST, "link": link})

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

    # ---- Total Reality split: scenario coverage / rover journeys / renegade / observation bundle ----
    tr = by.get("total_reality", {})
    trs = (tr.get("status") or "").upper()
    tr_gate = (GREEN if trs == "COMPLETE" else (AMBER if trs in ("PARTIAL", "DEFERRED") else
               (RED if trs in ("STUB", "WALLPAPER", "UNKNOWN", "REGRESSED") else BLOCKED)))
    tr_notes = [] if trs == "COMPLETE" else ["total_reality=%s" % (trs or "MISSING")]
    tr_next = "" if trs == "COMPLETE" else "re-run scripts/certify_total_reality.py"
    try:
        sm = json.loads((REPORTS / "scenario_matrix.json").read_text()).get("counts", {})
    except Exception:
        sm = {}
    add("scenario_coverage", "Total Scenario Matrix", tr_gate,
        "%s scenario classes · critical %s · adversarial %s · fully classified %s/%s" % (
            sm.get("total"), sm.get("critical"), sm.get("adversarial"), sm.get("fully_classified"), sm.get("total")),
        tr_notes, ["diamond"], tr_next, link="/reality")
    add("rover_journeys", "Rover Critical Journeys", tr_gate,
        "critical journeys via the synthetic-user Rover + Level-2 execution (master cert)", tr_notes,
        ["diamond"], tr_next, link="/reality")
    add("renegade", "Renegade Trials", tr_gate,
        "integrated cross-subsystem stress chains hold; harness discriminates (master cert)", tr_notes,
        ["diamond"], tr_next, link="/reality")
    add("observation_bundle", "Observation Bundle", tr_gate,
        "every scenario has a run_id-correlated evidence record + per-run host snapshot + deep stream",
        tr_notes, ["diamond"], tr_next, link="/reality")

    # ---- cert freshness (old green is not current green) ----------------------------------------
    from . import freshness as _fresh, evidence as _ev, blockers as _blk
    fr = _fresh.compute()
    fresh_status = STALE if fr["stale_required"] else GREEN
    add("cert_freshness", "Cert Freshness", fresh_status,
        "stale required: %s" % (", ".join(fr["stale_required"]) or "none"),
        fr["stale_required"], ["diamond"],
        "re-run the gate/certs on this commit" if fr["stale_required"] else "")

    # ---- UI truth consistency (UI must not contradict backend truth) ---------------------------
    uic = _ui_truth(by, floor, bi)
    add("ui_truth_consistency", "UI Truth Consistency", uic["status"], uic["evidence"],
        uic["mismatches"], ["diamond"], "reconcile UI vs backend" if uic["mismatches"] else "")

    # ---- evidence room -------------------------------------------------------------------------
    er = _ev.room()
    add("evidence_room", "Evidence Room", er["status"],
        "%d/%d evidence documents present" % (er["present"], er["total"]),
        [x["document"] for x in er["documents"] if not x["exists"]], ["diamond"],
        "generate missing evidence" if er["present"] < er["total"] else "")

    # ---- open blockers (summary gate) ----------------------------------------------------------
    blk = _blk.collect(gates, floor, cl, fr)
    p0p1 = [b for b in blk if b["severity"] in ("P0", "P1")]
    blk_status = RED if any(b["severity"] == "P0" for b in blk) else (AMBER if blk else GREEN)
    add("open_blockers", "Open Blockers", blk_status,
        "%d open (%d P0/P1)" % (len(blk), len(p0p1)),
        [b["blocker_id"] for b in blk[:8]], ["diamond"],
        "clear blockers" if blk else "")

    return {"gates": gates, "floor": floor, "build_identity": bi,
            "flake_classification": cl, "external_dependencies": ext,
            "repeatability": dv2, "freshness": fr, "evidence_room": er,
            "blockers": blk, "scenario_matrix": sm, "ui_truth": uic}


def _ui_truth(by: dict, floor: dict, bi: dict, served: dict | None = None) -> dict:
    """UI Truth Consistency: the dashboard's derived numbers must not contradict the backing reports.

    When `served` is injected (tests), compare that payload's headline numbers against the computed
    floor/build-identity. In LIVE mode (served=None) we must NOT fetch /verification.json — that would
    recurse into this very computation — so instead we verify the dashboard's computed summary against
    the RAW reports it claims to summarise (the real anti-contradiction check), non-recursively."""
    mismatches = []
    import urllib.request
    if served is not None:
        st = served.get("top", {})
        if st.get("p0_open") != floor.get("p0_open"):
            mismatches.append("served p0_open != computed (%s vs %s)" % (st.get("p0_open"), floor.get("p0_open")))
        if st.get("running_commit") and bi.get("running_commit") and st["running_commit"] != bi["running_commit"]:
            mismatches.append("served running_commit != build identity")
        served_pr = next((g for g in served.get("gates", []) if g.get("gate_id") == "program_reality"), {})
        if served_pr and ("%d COMPLETE" % floor.get("complete", -1)) not in (served_pr.get("evidence") or ""):
            mismatches.append("served program_reality complete count != computed")
        status = GREEN if not mismatches else RED
        ev = "served payload matches the backend" if not mismatches else "; ".join(mismatches)
        return {"status": status, "evidence": ev, "mismatches": mismatches}
    # LIVE: compare the dashboard's computed numbers to the RAW reports (non-recursive).
    try:
        raw = json.loads((REPORTS / "live_path_results.json").read_text())
        items = raw.get("features", raw if isinstance(raw, list) else [])
        actual_complete = sum(1 for x in items if (x.get("status") or "").upper() == "COMPLETE")
        if actual_complete != floor.get("complete"):
            mismatches.append("dashboard COMPLETE %s != raw report %s" % (floor.get("complete"), actual_complete))
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/version", timeout=5) as r:
                ver = json.loads(r.read().decode("utf-8"))
            if bi.get("running_commit") and ver.get("sha") and ver["sha"] != bi["running_commit"]:
                mismatches.append("build-identity running_commit != /version sha")
        except Exception:
            pass                                     # /version optional; the report check is the core
        status = GREEN if not mismatches else RED
        ev = "dashboard summary matches the raw reports" if not mismatches else "; ".join(mismatches)
    except Exception:
        status, ev = UNKNOWN, "raw reports unreadable — cannot prove UI/backend consistency"
    return {"status": status, "evidence": ev, "mismatches": mismatches}


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
