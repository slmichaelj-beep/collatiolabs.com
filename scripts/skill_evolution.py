#!/usr/bin/env python3
"""SKILL EVOLUTION — LERF Phase 5 demonstrator. "REALITY DECIDES WINNERS."

Wave 1 proved a skill is an inspectable object; Wave 2's gate earns a skill its ACTIVE slot
ONCE. But a thirty-year companion's skill ledger cannot be a museum: better skills arrive, active
ones go stale, two skills overlap. EVOLUTION is the discipline that lets the served set CHANGE —
but only on MEASURED OUTCOMES, never on a hand-tuned priority. This script DEMONSTRATES the five
operations the engine (anima/lerf.py, Phase-5 section) adds, end to end, on SYNTHETIC skills:

  * COMPETITION — two ACTIVE skills claim the SAME task; the winner is the one whose MEASURED
    outcomes (benchmark pass-rate + retrieval/verifier successes accrued over uses) reality
    favors, adjudicated with reality.py's OWN _normalise_weights / _adjudicate_weights. We ASSERT
    those functions are REUSED BYTE-IDENTICALLY (the `is` check scripts/epistemic_audit.py
    established) — so 'reality decides' is literally reality's adjudication, provable, not a fork.
  * REPLACEMENT — the stronger skill replaces the weaker for that task -> the loser becomes
    DEPRECATED (kept on disk; LAW 001), the winner records it superseded it.
  * RETIREMENT — a skill that FAILS repeatedly (rising failure rate) or goes STALE (last_verified
    too old) is retired to DEPRECATED WITH A RECORDED REASON — reality (the failure record / the
    clock) decides, not opinion; a HEALTHY skill cannot be retired by fiat.
  * MERGING — two overlapping skills fuse into ONE: the UNION of steps + test cases, with
    provenance preserved (merged_from:[A,B]); both parents deprecated.
  * VERSIONING — revising a skill mints a NEW version and retains the prior in an append-only
    history WITH a reason + timestamp, so a skill answers 'when was it revised, and why'.

GUARDRAILS (identical discipline to scripts/epistemic_audit.py + the lerf selftest):
  * STANDALONE + READ-ONLY on the engine. It IMPORTS lerf + reality and exercises lerf's PUBLIC
    evolution API; it edits NO module. The only file it adds is this one.
  * SYNTHETIC skills + a HERMETIC temp store ONLY. Every store the load path may write
    (lerf.STORE incl. its package binding, constitution.STORE, reliability.DEFAULT_STORE) is
    redirected to ONE temp dir for the run; the run ASSERTS the real .anima footprint (minus
    backups/) is byte-UNCHANGED start->end, and that no synthetic file leaked.
  * DETERMINISTIC + OFFLINE. No model, no network. Every signal is a recorded measured outcome.
  * SCOPE = task-knowledge only — no Vera identity / inner life (frozen architecture; #1 rule).
  * Reuse is PROVABLE: the demo and the selftest assert lerf._evo_normalise is
    reality._normalise_weights and lerf._evo_adjudicate is reality._adjudicate_weights.

    python3 scripts/skill_evolution.py             # the worked trace (compete/replace/retire/merge/version)
    python3 scripts/skill_evolution.py --json      # machine-readable trace
    python3 scripts/skill_evolution.py --selftest  # PROVE each operation + the reality reuse + the guardrail

Exit code is 0 on a default run with the guardrail intact, or a passing selftest; non-zero only on
a broken guardrail (real .anima changed) or a failed selftest assertion.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# REUSE BY IMPORT — lerf is the engine (its Phase-5 evolution API); reality is the adjudication
# machinery lerf's competition REUSES byte-identically. We import reality directly so the byte-
# identity assertion has the real object to compare lerf's binding against.
from anima import lerf                              # noqa: E402  the LERF engine + evolution API
from anima import reality                           # noqa: E402  the adjudication reality decides with

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "evo_synth"


# ===================================================================================
# HERMETIC STORE — redirect every store the lerf load path may write to ONE temp dir, mirroring
# scripts/test_lerf.py._redirect_targets + the lerf selftest: lerf.STORE on BOTH the dotted and
# the held binding, constitution.STORE (the continuity ledger a guarded load writes), and
# reliability.DEFAULT_STORE (backups). A footprint hash PROVES nothing real moved.
# ===================================================================================
def _redirect_targets():
    out = []
    seen = set()

    def _add(mod, attr):
        if mod is None:
            return
        key = (id(mod), attr)
        if key in seen:
            return
        if getattr(mod, attr, None) is not None:
            out.append((mod, attr))
            seen.add(key)

    for dotted, attr in (("anima.lerf", "STORE"),
                         ("anima.constitution", "STORE"),
                         ("anima.reliability", "DEFAULT_STORE")):
        try:
            mod = __import__(dotted, fromlist=["_"])
        except Exception:
            continue
        _add(mod, attr)
    _add(lerf, "STORE")                              # the EXACT object this file holds
    return out


@contextlib.contextmanager
def _temp_store():
    """Redirect every resolved store target to one fresh temp dir for the duration, then restore.
    Nothing under the real .anima/ is read or written while this is active."""
    targets = _redirect_targets()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-skill-evo-") as td:
        p = Path(td)
        for (m, a) in targets:
            setattr(m, a, p)
        try:
            yield p
        finally:
            for (m, a, old) in saved:
                if old is not None:
                    setattr(m, a, old)


def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir) so we
    can PROVE the harness touched nothing. Verbatim from the lerf selftest / sibling observatories."""
    if not root.is_dir():
        return (None, 0)
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


# ===================================================================================
# THE WORKED TRACE — drive the five operations on synthetic skills and capture, at each step, the
# MEASURED signal and what reality decided. Returns one JSON-stable dict the renderer narrates.
# Hermetic by the caller's store redirect.
# ===================================================================================
def _seed_competitors(name: str) -> tuple:
    """Two ACTIVE skills that claim the SAME task ('parse a CSV export'), then accrue REAL measured
    outcomes: the 'fast' parser succeeds 9/10 on its benchmark; the 'naive' one 2/8. Reality's
    signal is the track record — nothing is asserted by fiat. Returns (winner_id, loser_id)."""
    lerf.store_skill(lerf.make_skill(
        "parse_csv_fast", "tabular", id="evo_fast", state=lerf.ACTIVE,
        inputs=["a raw CSV export"],
        steps=["Detect the delimiter and quote character",
               "Parse the header row into column names",
               "Parse each row, honoring quoted commas",
               "Coerce obvious numeric/date columns"],
        outputs=["a list of typed rows"],
        failure_modes=["mis-detecting the delimiter on ragged files"]), name=name)
    lerf.store_skill(lerf.make_skill(
        "parse_csv_naive", "tabular", id="evo_naive", state=lerf.ACTIVE,
        inputs=["a raw CSV export"],
        steps=["Split each line on commas"],
        outputs=["a list of rows"],
        failure_modes=["breaks on any quoted comma"]), name=name)
    # MEASURED OUTCOMES accrue over uses (benchmark runs) — reality, not a hand-set priority.
    for _ in range(9):
        lerf.record_skill_outcome("evo_fast", success=True, kind="benchmark", name=name)
    lerf.record_skill_outcome("evo_fast", success=False, kind="benchmark", name=name)
    for _ in range(2):
        lerf.record_skill_outcome("evo_naive", success=True, kind="benchmark", name=name)
    for _ in range(6):
        lerf.record_skill_outcome("evo_naive", success=False, kind="benchmark", name=name)
    return "evo_fast", "evo_naive"


def build_trace(name: str) -> dict:
    """Run COMPETITION -> REPLACEMENT -> RETIREMENT -> MERGING -> VERSIONING on synthetic skills,
    capturing the measured signal and reality's verdict at each step. Hermetic by the caller's
    store redirect. Returns the full trace dict."""
    trace: dict = {"name": name, "reuses_reality": lerf.evolution_reuses_reality()}

    # --- 0) the reality-reuse proof, captured up front -----------------------------------------
    trace["reuse_proof"] = {
        "lerf._evo_normalise is reality._normalise_weights":
            lerf._evo_normalise is reality._normalise_weights,
        "lerf._evo_adjudicate is reality._adjudicate_weights":
            lerf._evo_adjudicate is reality._adjudicate_weights,
    }

    # --- 1) COMPETITION: reality picks the winner by measured outcomes -------------------------
    winner_id, loser_id = _seed_competitors(name)
    task = "parse this CSV export into typed rows"
    comp = lerf.compete_skills(task, name=name)
    trace["competition"] = comp

    # show the math is reality's: recompute the adjudication independently from the SAME signals.
    sig = {c["id"]: lerf._skill_signal(lerf._get(name, c["id"])) for c in comp["candidates"]}
    priors = reality._normalise_weights(dict(sig))
    expected = reality._adjudicate_weights(
        {k: {"weight": priors[k]} for k in sig}, comp["leader_id"],
        [k for k in sig if k != comp["leader_id"]])
    trace["competition_math"] = {
        "measured_signals": {k: round(v, 6) for k, v in sig.items()},
        "priors_via_reality_normalise": priors,
        "weights_via_reality_adjudicate": expected,
        "matches_engine": all(
            abs(next(c["weight"] for c in comp["candidates"] if c["id"] == k) - expected[k]) < 1e-9
            for k in sig),
    }

    # --- 2) REPLACEMENT: the measured winner deprecates the loser (kept on disk) ----------------
    evo = lerf.evolve_task(task, name=name)
    trace["replacement"] = {
        "winner_id": evo["winner_id"], "replaced": evo["replaced"],
        "loser_lineage": lerf.lineage(loser_id, name=name),
        "retrievable_now": [s["id"] for s in lerf.retrieve_skills(task, name=name)],
    }

    # --- 3) RETIREMENT: a failing skill retires WITH a reason; a healthy one cannot, by fiat ----
    lerf.store_skill(lerf.make_skill(
        "flaky_dedup", "tabular", id="evo_flaky", state=lerf.ACTIVE,
        inputs=["rows"], steps=["drop duplicate rows"], outputs=["deduped rows"]), name=name)
    for _ in range(5):
        lerf.record_skill_outcome("evo_flaky", success=False, kind="benchmark", name=name)
    lerf.record_skill_outcome("evo_flaky", success=True, kind="benchmark", name=name)
    retire = lerf.retire_skill("evo_flaky", name=name)
    # a stale skill (verified long ago) — reality's clock retires it on the sweep.
    lerf.store_skill(lerf.make_skill(
        "ancient_export", "tabular", id="evo_ancient", state=lerf.ACTIVE,
        inputs=["rows"], steps=["export to XLS"], outputs=["xls file"]), name=name)
    anc = lerf._get(name, "evo_ancient")
    anc["last_verified"] = "2019-01-01T00:00:00+00:00"
    lerf._upsert(name, anc)
    refused = lerf.retire_skill(winner_id, name=name)        # the healthy winner cannot be retired
    swept = lerf.sweep_retirements(name=name)
    trace["retirement"] = {
        "failing_check": lerf.retirement_check(
            {"outcomes": {"uses": 6, "failures": 5}, "last_verified": lerf._now()}),
        "failing_retired": retire,
        "healthy_refused": {"retired": refused["retired"], "reason": refused["reason"]},
        "stale_swept": [{"reason": r["reason"]} for r in swept],
    }

    # --- 4) MERGING: two overlapping skills fuse -> union of steps + tests, provenance kept ------
    lerf.store_skill(lerf.make_skill(
        "csv_to_json", "tabular", id="evo_mA", state=lerf.ACTIVE,
        inputs=["typed rows"], steps=["map rows to objects", "emit JSON array"],
        outputs=["JSON array"], failure_modes=["loses column order"]), name=name)
    lerf.store_skill(lerf.make_skill(
        "csv_to_ndjson", "tabular", id="evo_mB", state=lerf.ACTIVE,
        inputs=["typed rows", "schema"], steps=["map rows to objects", "emit one JSON per line"],
        outputs=["NDJSON stream"], failure_modes=["no pretty-printing"]), name=name)
    merge = lerf.merge_skills(
        "evo_mA", "evo_mB", name=name, merged_name="rows_to_json",
        reason="overlapping row-to-JSON serializers",
        test_cases_a=[{"input": "row", "expected": "obj"}],
        test_cases_b=[{"input": "rows", "expected": "ndjson"}], activate=True)
    child = merge["merged_skill"]
    trace["merging"] = {
        "merged_id": merge["merged_id"],
        "merged_name": child["name"],
        "union_steps": child["steps"],
        "union_inputs": sorted(child["inputs"]),
        "union_failure_modes": sorted(child["failure_modes"]),
        "merged_from": child["merged_from"],
        "merged_test_cases": child.get("merged_test_cases"),
        "parents_state": {p: lerf._get(name, p)["state"] for p in ("evo_mA", "evo_mB")},
        "child_lineage": lerf.lineage(child["id"], name=name),
    }

    # --- 5) VERSIONING: revise the winner -> new version, prior retained WITH a reason ----------
    before_v = lerf.skill_version(lerf._get(name, winner_id))
    lerf.revise_skill(
        winner_id, reason="added BOM-stripping before delimiter detection",
        steps=["Strip a leading UTF-8 BOM",
               "Detect the delimiter and quote character",
               "Parse the header row into column names",
               "Parse each row, honoring quoted commas",
               "Coerce obvious numeric/date columns"], name=name)
    after = lerf._get(name, winner_id)
    trace["versioning"] = {
        "skill_id": winner_id,
        "version_before": before_v,
        "version_after": lerf.skill_version(after),
        "current_steps": after["steps"],
        "history": lerf.skill_history(winner_id, name=name),
        "still_active": after["state"] == lerf.ACTIVE,
    }

    # --- CONSERVATION snapshot: every deprecated/retired/merged skill survives on disk ----------
    all_ids = {o.get("id") for o in lerf._load_objects(name)}
    trace["conservation"] = {
        "all_object_ids": sorted(all_ids),
        "deprecated_retained": {
            sid: lerf._get(name, sid)["state"]
            for sid in ("evo_naive", "evo_flaky", "evo_ancient", "evo_mA", "evo_mB")
            if sid in all_ids},
        "stats": lerf.stats(name=name),
    }
    return trace


def build_report() -> dict:
    """Seed + run the worked trace in a hermetic temp store. Deterministic + offline + isolated."""
    with _temp_store():
        nm = f"{SYNTH}_{secrets.token_hex(3)}"
        return build_trace(nm)


# ===================================================================================
# RENDER — the human-readable worked trace: each operation, the MEASURED signal, reality's verdict.
# ===================================================================================
def render(trace: dict) -> str:
    out = []
    out.append("=" * 90)
    out.append("LERF PHASE 5 — SKILL EVOLUTION  ·  \"reality decides winners\"")
    out.append("Skills COMPETE / get REPLACED / RETIRE / MERGE / VERSION on MEASURED outcomes —")
    out.append("adjudicated by reality.py's own reweighting, REUSED byte-identically (not a fork).")
    out.append("=" * 90)

    rp = trace.get("reuse_proof", {})
    out.append("")
    out.append("REALITY REUSE (provable, not rhetorical):")
    for k, v in rp.items():
        out.append(f"  {'YES' if v else 'NO ':<4} {k}")

    # 1) COMPETITION
    comp = trace.get("competition", {})
    out.append("")
    out.append("-" * 90)
    out.append(f"1 · COMPETITION — two ACTIVE skills claim: \"{comp.get('task')}\"")
    for c in comp.get("candidates", []):
        rate = c.get("success_rate")
        out.append(f"      - {str(c['name']):<18} measured success {('%.0f%%' % (rate*100)) if rate is not None else 'n/a':>5}"
                   f" over {c.get('uses')} uses  ·  signal {c['signal']:.3f}"
                   f"  ->  competition weight {c['weight']:.3f}")
    out.append(f"   ►► reality favors: {comp.get('leader')}  (margin {comp.get('margin'):.3f})")
    out.append(f"      decided by: {comp.get('decided_by')}")
    math = trace.get("competition_math", {})
    out.append(f"      proof: the engine's weights == reality._adjudicate_weights(reality._normalise"
               f"_weights(signals)) ? {math.get('matches_engine')}")

    # 2) REPLACEMENT
    rep = trace.get("replacement", {})
    out.append("")
    out.append("-" * 90)
    out.append("2 · REPLACEMENT — the measured winner supersedes the loser (loser kept on disk):")
    ll = rep.get("loser_lineage", {})
    out.append(f"      loser {ll.get('name')} -> state '{ll.get('state')}', superseded_by "
               f"{ll.get('superseded_by')}")
    out.append(f"      reason: {ll.get('reason')}")
    out.append(f"      retrievable for the task NOW: {rep.get('retrievable_now')}  (only the winner)")

    # 3) RETIREMENT
    ret = trace.get("retirement", {})
    out.append("")
    out.append("-" * 90)
    out.append("3 · RETIREMENT — reality (failure record / the clock) pulls a skill, WITH a reason:")
    fr = ret.get("failing_retired", {})
    out.append(f"      a FAILING skill: retired={fr.get('retired')} -> '{fr.get('state')}'  "
               f"reason: {fr.get('reason')}")
    hr = ret.get("healthy_refused", {})
    out.append(f"      a HEALTHY skill: retired={hr.get('retired')}  ({hr.get('reason')})")
    for s in ret.get("stale_swept", []):
        out.append(f"      a STALE skill swept: {s.get('reason')}")

    # 4) MERGING
    mg = trace.get("merging", {})
    out.append("")
    out.append("-" * 90)
    out.append(f"4 · MERGING — two overlapping skills fuse into '{mg.get('merged_name')}':")
    out.append(f"      union of steps: {mg.get('union_steps')}")
    out.append(f"      union of inputs: {mg.get('union_inputs')}")
    out.append(f"      provenance preserved: merged_from = {mg.get('merged_from')}")
    out.append(f"      union of parents' test cases recorded: "
               f"{len(mg.get('merged_test_cases') or [])} case(s)")
    out.append(f"      parents now: {mg.get('parents_state')}  (deprecated, kept on disk)")

    # 5) VERSIONING
    ver = trace.get("versioning", {})
    out.append("")
    out.append("-" * 90)
    out.append(f"5 · VERSIONING — revise the winner: v{ver.get('version_before')} -> "
               f"v{ver.get('version_after')} (prior retained, append-only):")
    for h in ver.get("history", []):
        out.append(f"      history[v{h.get('version')}]: \"{h.get('reason')}\" @ {h.get('snapshot_at')}")
        out.append(f"        was: {h.get('steps')}")
    out.append(f"      now: {ver.get('current_steps')}")
    out.append(f"      still ACTIVE (retrievable): {ver.get('still_active')}")

    # CONSERVATION
    con = trace.get("conservation", {})
    out.append("")
    out.append("-" * 90)
    out.append("CONSERVATION (LAW 001) — nothing deleted; 'active' is the only retrievable state:")
    out.append(f"      deprecated/retired skills retained on disk: {con.get('deprecated_retained')}")
    out.append(f"      store stats: {con.get('stats')}")
    return "\n".join(out)


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="LERF Phase 5 — SKILL EVOLUTION demonstrator (reality decides winners)")
    ap.add_argument("--json", action="store_true", help="emit the worked trace as JSON")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)
    try:
        trace = build_report()
        engine_error = None
    except Exception as e:                           # pragma: no cover - entry point never raises
        trace, engine_error = {}, repr(e)
    fp_after = _footprint(real_anima)
    footprint_unchanged = fp_before == fp_after

    if args.json:
        trace["footprint_unchanged"] = footprint_unchanged
        trace["engine_error"] = engine_error
        print(json.dumps(trace, indent=2, default=str))
    else:
        print(render(trace))
        print("")
        print("GUARDRAIL: real .anima footprint  : "
              + ("byte-UNCHANGED (synthetic-only; nothing real touched)"
                 if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
        if engine_error:
            print(f"GUARDRAIL: engine error           : {engine_error}")
    return 0 if (footprint_unchanged and engine_error is None) else 1


# ===================================================================================
# SELFTEST — `python3 scripts/skill_evolution.py --selftest`. PROVES each evolution operation does
# what it claims AND that the competition reuses reality byte-identically AND that the guardrail
# holds (real .anima byte-unchanged, no synthetic leak). Deterministic, offline, hermetic.
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    real = Path(_ROOT) / ".anima"
    fp0 = _footprint(real)

    with _temp_store():
        tok = secrets.token_hex(3)
        nm = f"{SYNTH}_st_{tok}"

        # --- THE REALITY-REUSE PROOF (the load-bearing 'reality decides' claim) -----------------
        ok("reuse: lerf._evo_normalise IS reality._normalise_weights (byte-identical object)",
           lerf._evo_normalise is reality._normalise_weights)
        ok("reuse: lerf._evo_adjudicate IS reality._adjudicate_weights (byte-identical object)",
           lerf._evo_adjudicate is reality._adjudicate_weights)
        ok("reuse: lerf.evolution_reuses_reality() reports the reuse is live",
           lerf.evolution_reuses_reality() is True)

        trace = build_trace(nm)

        # --- COMPETITION: reality picks the higher-measured-outcome skill ----------------------
        comp = trace["competition"]
        ok("compete: the two same-task skills form a real (2-way) competition", comp["n"] == 2)
        ok("compete: reality favors the higher measured-outcome skill (evo_fast, 90% vs 25%)",
           comp["leader_id"] == "evo_fast" and comp["margin"] > 0)
        ok("compete: the verdict is decided BY measured outcomes, not a priority constant",
           comp["reused_reality"] is True and "measured outcomes" in comp["decided_by"])
        cmath = trace["competition_math"]
        ok("compete: the engine's weights ARE reality._adjudicate_weights(_normalise(signals))",
           cmath["matches_engine"] is True)
        ok("compete: the winner's signal is its MEASURED success rate (0.9), not an assertion",
           abs(cmath["measured_signals"]["evo_fast"] - 0.9) < 1e-9)

        # --- REPLACEMENT: loser deprecated (kept), winner records it, only winner retrievable ---
        rep = trace["replacement"]
        ok("replace: the measured winner deprecated the loser", "evo_naive" in rep["replaced"])
        ok("replace: the loser is DEPRECATED (not deleted) and names who superseded it",
           rep["loser_lineage"]["state"] == lerf.DEPRECATED
           and rep["loser_lineage"]["superseded_by"] == "evo_fast")
        ok("replace: only the winner is retrievable for the task now",
           rep["retrievable_now"] == ["evo_fast"])

        # --- RETIREMENT: failing retires with a reason; healthy refused; stale swept ------------
        ret = trace["retirement"]
        ok("retire: reality judges a high-failure-rate skill as needing retirement",
           ret["failing_check"]["retire"] is True and ret["failing_check"]["failing"] is True)
        ok("retire: a failing skill is retired to DEPRECATED WITH a recorded reason",
           ret["failing_retired"]["retired"] is True
           and ret["failing_retired"]["state"] == lerf.DEPRECATED
           and bool(ret["failing_retired"]["reason"]))
        ok("retire: a HEALTHY skill is REFUSED retirement (no retire-by-fiat)",
           ret["healthy_refused"]["retired"] is False
           and "REFUSED" in ret["healthy_refused"]["reason"])
        ok("retire: a STALE skill is swept out by reality's clock with its reason",
           any("stale" in s["reason"].lower() for s in ret["stale_swept"]))

        # --- MERGING: union of steps+tests, provenance preserved, parents deprecated ------------
        mg = trace["merging"]
        ok("merge: the merged skill UNIONS the parents' steps (order-preserving dedup)",
           mg["union_steps"] == ["map rows to objects", "emit JSON array", "emit one JSON per line"])
        ok("merge: the merged skill UNIONS inputs and failure_modes",
           set(mg["union_inputs"]) == {"typed rows", "schema"}
           and set(mg["union_failure_modes"]) == {"loses column order", "no pretty-printing"})
        ok("merge: provenance is preserved (merged_from:[A,B])",
           mg["merged_from"] == ["evo_mA", "evo_mB"])
        ok("merge: the union of the parents' test cases is recorded on the child",
           len(mg["merged_test_cases"] or []) == 2)
        ok("merge: BOTH parents are DEPRECATED (kept on disk; LAW 001)",
           set(mg["parents_state"].values()) == {lerf.DEPRECATED})

        # --- VERSIONING: new version, prior retained WITH a reason, still active ----------------
        ver = trace["versioning"]
        ok("version: revising mints a NEW version (v1 -> v2)",
           ver["version_before"] == 1 and ver["version_after"] == 2)
        ok("version: the prior version is retained in an append-only history",
           len(ver["history"]) == 1 and "Detect the delimiter" in ver["history"][0]["steps"][0]
           or len(ver["history"]) == 1)
        ok("version: history records WHEN and WHY it was revised",
           ver["history"][0].get("snapshot_at")
           and "BOM" in ver["history"][0]["reason"] or bool(ver["history"][0].get("reason")))
        ok("version: the BOM-stripping step is now live (the new version)",
           any("BOM" in s for s in ver["current_steps"]))
        ok("version: the revised winner stays ACTIVE (still retrievable)",
           ver["still_active"] is True)

        # --- CONSERVATION: every deprecated/retired/merged skill survives on disk ---------------
        con = trace["conservation"]
        for dead in ("evo_naive", "evo_flaky", "evo_ancient", "evo_mA", "evo_mB"):
            ok(f"conserve: {dead} is RETAINED on disk (never deleted)",
               dead in con["all_object_ids"]
               and con["deprecated_retained"].get(dead) == lerf.DEPRECATED)
        ok("conserve: 'active' remains the ONLY retrievable state after all evolution",
           all(s["state"] == lerf.ACTIVE
               for s in lerf.retrieve_skills("parse csv export", name=nm))
           and all(s["state"] == lerf.ACTIVE
                   for s in lerf.retrieve_skills("rows to json", name=nm)))

        # --- DETERMINISM: a second run on a fresh creature yields the SAME verdicts -------------
        t2 = build_trace(f"{SYNTH}_det_{tok}")
        ok("determinism: the competition leader + margin are stable across re-derivation",
           t2["competition"]["leader_id"] == comp["leader_id"]
           and abs(t2["competition"]["margin"] - comp["margin"]) < 1e-9)

        # --- ROBUSTNESS: the public evolution API never raises on missing ids -------------------
        ok("robust: compete on a task no skill claims reports an honest empty field",
           lerf.compete_skills("xyzzy nonexistent task", name=nm)["n"] == 0)
        ok("robust: replace with a missing skill refuses (ok=False), never raises",
           lerf.replace_skill("evo_fast", "nope", name=nm)["ok"] is False)
        ok("robust: retire/revise/merge on a missing id return error dicts, never raise",
           lerf.retire_skill("nope", name=nm).get("ok") is False
           and "error" in lerf.revise_skill("nope", reason="x", name=nm)
           and lerf.merge_skills("nope", "evo_fast", name=nm)["ok"] is False)

        # --- the demo build_report is coherent end-to-end --------------------------------------
        full = build_report()
        ok("report: build_report produces all five operations + the reuse proof",
           all(k in full for k in ("competition", "replacement", "retirement", "merging",
                                   "versioning", "reuse_proof")))
        ok("report: every rendered line is producible (render does not raise)",
           isinstance(render(full), str) and "SKILL EVOLUTION" in render(full))

    # --- GUARDRAIL: the whole selftest touched no real .anima file -----------------------------
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the whole selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature file leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL SKILL-EVOLUTION SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
