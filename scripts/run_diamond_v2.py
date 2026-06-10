#!/usr/bin/env python3
"""run_diamond_v2 — Diamond requires REPEATABILITY. One green run is not enough if a previous run
showed a different feature status.

Runs the full live-path gate N consecutive times on the SAME head (no commits between), holding the
build identity constant, and proves:

  same commit · same served UI hash · same backend · same scenario-matrix version · same feature-
  contract version · same host-dependency preflight · N consecutive runs · same result classification
  · 0 UNCLASSIFIED flakes.

Every feature whose status VARIES across the identical runs must land in a named class
(harness_flake / env_dependency_partial / intentional_external_partial) — an inconsistency with no
class is UNCLASSIFIED and blocks Diamond. The output distinguishes product partial vs environmental
dependency partial vs verification harness flake vs intentional external partial.

  python3 scripts/run_diamond_v2.py --gate           # 3 runs; exit non-zero unless repeatable + no product defect
  python3 scripts/run_diamond_v2.py --gate --runs 5
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPORTS = ROOT / "reports"


def _git(*a):
    try:
        return subprocess.run(["git", *a], cwd=str(ROOT), capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _dir_hash(p: Path, suffixes=(".json", ".html", ".js", ".py")) -> str:
    h = hashlib.sha256()
    if p.is_dir():
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix in suffixes:
                h.update(f.relative_to(p).as_posix().encode()); h.update(f.read_bytes())
    elif p.is_file():
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _identity():
    from anima.verification import build_identity, preflight
    return {
        "commit": _git("rev-parse", "HEAD"),
        "served_ui_hash": build_identity.frontend_hash(),
        "feature_contracts_hash": _dir_hash(ROOT / "feature_contracts"),
        "scenario_matrix_hash": _dir_hash(REPORTS / "scenario_matrix.json"),
        "preflight": preflight.external_dependencies(),
    }


def _run_gate(timeout=900) -> list[dict]:
    """Run the full gate once; return the per-feature records from the fresh report."""
    subprocess.run([sys.executable, str(ROOT / "scripts" / "certify_live_paths.py"), "--gate"],
                   cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    d = json.loads((REPORTS / "live_path_results.json").read_text())
    return d if isinstance(d, list) else d.get("features", d.get("results", []))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_diamond_v2")
    ap.add_argument("--gate", action="store_true", help="exit non-zero unless repeatable + no product defect")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args(argv)
    n = max(2, args.runs)

    from anima.verification import flakes, preflight

    print("DIAMOND v2 — REPEATABILITY (%d consecutive full-gate runs on the same head)" % n)
    print("=" * 92)
    id0 = _identity()
    print("head=%s  served_ui=%s  contracts=%s  matrix=%s"
          % (id0["commit"][:12], id0["served_ui_hash"], id0["feature_contracts_hash"], id0["scenario_matrix_hash"]))
    print(preflight.render_block(id0["preflight"]))
    print()

    runs, identities = [], []
    for i in range(n):
        print("  run %d/%d ..." % (i + 1, n), flush=True)
        runs.append(_run_gate())
        identities.append(_identity())

    # ---- identity must be constant across the runs --------------------------------------------
    def same(key):
        vals = {json.dumps(idn[key], sort_keys=True) for idn in identities}
        return len(vals) == 1
    identity_stable = all(same(k) for k in ("commit", "served_ui_hash", "feature_contracts_hash", "scenario_matrix_hash"))
    pre_states = {tuple(sorted((d["daemon"], d["state"]) for d in idn["preflight"]["dependencies"])) for idn in identities}
    preflight_stable = len(pre_states) == 1

    # ---- classify across the runs -------------------------------------------------------------
    cl = flakes.classify_across_runs(runs, id0["preflight"])
    # per-run single classifications (to report product defects, honest partials)
    last = flakes.classify_run(runs[-1], id0["preflight"], flakes.read_flake_log())
    product_red = sorted({f for r in runs for f in flakes.classify_run(r, id0["preflight"], {}).get("product_red", [])})
    product_partial = sorted({rec["feature"] for rec in cl["features"] if rec["class"] == "product_partial"})

    repeatable = (identity_stable and preflight_stable and cl["repeatable"]
                  and not product_red and not product_partial)

    # ---- counts for the final line ------------------------------------------------------------
    complete_each = [sum(1 for it in r if (it.get("status") or "").upper() == "COMPLETE") for r in runs]
    honest = sorted({rec["feature"] for rec in cl["features"]
                     if rec["class"] in ("intentional_external_partial", "env_dependency_partial")})
    harness = sorted({rec["feature"] for rec in cl["features"] if rec["class"] == "harness_flake"})

    print("\nIDENTITY STABLE across runs: %s  (commit/served-ui/contracts/matrix/preflight)"
          % ("YES" if (identity_stable and preflight_stable) else "NO"))
    print("COMPLETE per run: %s" % complete_each)
    if cl["varied_across_runs"]:
        print("VARIED across runs (must be a classified flake):")
        for v in cl["varied_across_runs"]:
            print("  %-26s %s -> %s" % (v["feature"], v["statuses"], v["class"]))
    # per-feature class from the final run, for the dependency-cert line
    cls_by_feat = {o["feature"]: o["class"] for o in last["per_feature"]}
    print("\nEXTERNAL DEPENDENCY STATE:")
    for d in id0["preflight"]["dependencies"]:
        dep_feats = [f for f, dep in flakes.EXTERNAL_DEP.items() if dep == d["daemon"]]
        worst = "pass"
        for f in dep_feats:
            c = cls_by_feat.get(f, "ok")
            if c in ("product_partial", "product_red"):
                worst = "fail"
            elif c in ("env_dependency_partial", "harness_flake") and worst == "pass":
                worst = "classified-flake"
        impact = "none" if repeatable else ("blocked" if (product_red or product_partial) else "partial")
        print("  %-8s daemon: %-11s cert: %-16s impact on Diamond: %s"
              % (d["daemon"], d["state"], worst, impact))

    print("\nCLASS BREAKDOWN (distinguishes the four kinds):")
    deferred = sorted({rec["feature"] for rec in cl["features"] if rec["class"] == "deferred_not_claimed"})
    print("  deferred / not claimed     : %s" % (deferred or "none"))
    print("  product partial            : %s" % (product_partial or "none"))
    print("  product red (defect)       : %s" % (product_red or "none"))
    print("  environmental dependency   : %s" % ([f for f in honest if f in flakes.EXTERNAL_DEP] or "none"))
    print("  intentional external       : %s" % ([f for f in honest if f in flakes.INTENTIONAL_EXTERNAL] or "none"))
    print("  verification harness flake : %s" % (harness or "none"))
    print("  UNCLASSIFIED               : %s" % ([u["feature"] for u in cl["unclassified"]] or "none"))

    cmin = min(complete_each)
    print("\n%d COMPLETE / %d HONEST PARTIAL; %d UNCLASSIFIED FLAKES; full gate repeatability %s"
          % (cmin, len(honest), cl["unclassified_count"], "confirmed" if repeatable else "NOT confirmed"))
    print("DIAMOND v2 REPEATABILITY: " + ("CONFIRMED" if repeatable else "BLOCKED"))
    if not repeatable:
        reasons = []
        if not identity_stable: reasons.append("build identity changed across runs")
        if not preflight_stable: reasons.append("dependency preflight changed across runs")
        if cl["unclassified_count"]: reasons.append("%d unclassified flake(s)" % cl["unclassified_count"])
        if product_red: reasons.append("product defect(s): %s" % ", ".join(product_red))
        if product_partial: reasons.append("product partial(s): %s" % ", ".join(product_partial))
        print("  blocked by: " + "; ".join(reasons))

    # persist the repeatability verdict for the dashboard
    try:
        (REPORTS / "diamond_v2.json").write_text(json.dumps({
            "runs": n, "complete_per_run": complete_each, "identity_stable": identity_stable and preflight_stable,
            "repeatable": repeatable, "unclassified": [u["feature"] for u in cl["unclassified"]],
            "honest_partials": honest, "harness_flakes": harness,
            "product_partial": product_partial, "product_red": product_red,
            "commit": id0["commit"], "preflight": id0["preflight"],
        }, indent=2))
    except Exception:
        pass

    if args.gate:
        return 0 if repeatable else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
