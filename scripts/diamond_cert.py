#!/usr/bin/env python3
"""diamond_cert — the ONE authoritative truth gate for Vera (Diamond Hardening Mode).

It aggregates the gates that ACTUALLY EXIST into a single verdict, and — this is the whole point —
reports the not-yet-built hardening phases as DEFERRED, never as fake-green. A stage prints GREEN
only when a real cert ran and passed. Phases with no cert yet print DEFERRED (Phase N — not built),
so the diamond cert can never claim security/privacy/performance/polish are done before they are.

Baseline stages (must exist + pass for DIAMOND BASELINE: GREEN):
  - DEPLOYMENT        scripts/deploy_check.py                (running == committed, clean tree)
  - PRODUCT REALITY   scripts/certify_live_paths.py --gate   (live-path / no-wallpaper; writes matrix)
  - GATE 0 PRIME      scripts/gate0_prime.py --gate          (platform-trust + stress suite)
  - SELFTESTS         scripts/selftest.py                    (LAW invariants)

Future hardening stages (reported DEFERRED until their cert exists — they do NOT fail the baseline,
but they are NEVER printed green):
  - SECURITY (P3) · AI SECURITY (P4) · PRIVACY/VAULT (P5) · PERMISSIONS (P3) ·
    PERFORMANCE (P11) · UX POLISH (P12) · ENTERPRISE READINESS (P14)

Matrix invariant for GREEN: 0 WALLPAPER, 0 STUB, 0 UNREACHABLE, 0 REGRESSED, 0 UNKNOWN.
A PARTIAL is allowed ONLY when it is honestly external-dependency-blocked.

Modes:
  --baseline    run the baseline gates, write the baseline + matrix + blockers reports (default)
  --gate        exit NON-ZERO unless DIAMOND BASELINE: GREEN  (for CI / pre-PR)
  --enterprise  also require EVERY future stage to exist + pass (NOT READY until they are built)
  --fast        trust the existing reports/live_path_results.json for PRODUCT REALITY instead of
                re-running the (slow) live-path gate — only honored when the tree is clean.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)
MATRIX = REPORTS / "live_path_results.json"

GREEN, RED, DEFERRED = "GREEN", "RED", "DEFERRED"
_BAD_STATUSES = ("WALLPAPER", "STUB", "UNREACHABLE", "REGRESSED", "UNKNOWN")


def _run(args, pass_token=None, timeout=1200):
    try:
        p = subprocess.run([sys.executable, *[str(a) for a in args]],
                           capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
        out = (p.stdout or "") + (p.stderr or "")
        ok = (p.returncode == 0) and (pass_token is None or pass_token in out)
        return ok, out
    except Exception as e:  # pragma: no cover
        return False, f"runner error: {e!r}"


def _git(*a):
    try:
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=str(ROOT)).stdout.strip()
    except Exception:
        return ""


BASELINE = [
    ("deploy",   "DEPLOYMENT  (running == committed)",          "deploy_check.py",      [],         "GREEN"),
    ("reality",  "PRODUCT REALITY  (live-path / no-wallpaper)", "certify_live_paths.py", ["--gate"], None),
    ("gate0",    "GATE 0 PRIME  (platform trust + stress)",     "gate0_prime.py",       [],         "GATE 0 PRIME: PASS"),
    ("selftest", "SELFTESTS  (LAW invariants)",                 "selftest.py",          [],         "ALL SELFTESTS PASS"),
]
FUTURE = [
    ("security",    "SECURITY BASELINE",          3,  "certify_security_baseline.py"),
    ("ai_security", "AI SECURITY  (red team)",    4,  "certify_ai_security.py"),
    ("privacy",     "PRIVACY / VAULT / FORGET",   5,  "certify_privacy.py"),
    ("permissions", "PERMISSIONS / TRUST ZONES",  3,  "certify_permissions.py"),
    ("performance", "PERFORMANCE / EFFICIENCY",   11, "certify_performance.py"),
    ("polish",      "UX DIAMOND POLISH",          12, "certify_product_polish.py"),
    ("enterprise",  "ENTERPRISE READINESS",       14, "enterprise_readiness.py"),
]


def load_matrix():
    if not MATRIX.exists():
        return None
    try:
        d = json.load(open(MATRIX))
        feats = d.get("features") or []
        counts = {}
        for f in feats:
            counts[f.get("status", "?")] = counts.get(f.get("status", "?"), 0) + 1
        return {"features": feats, "counts": counts, "total": len(feats)}
    except Exception:
        return None


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    gate = "--gate" in argv
    enterprise = "--enterprise" in argv
    fast = "--fast" in argv

    head = _git("rev-parse", "--short", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    stamp = datetime.now().isoformat(timespec="seconds")

    print("=" * 96)
    print("DIAMOND CERT — the one authoritative truth gate   (commit %s%s)"
          % (head or "?", "  DIRTY-TREE" if dirty else ""))
    print("=" * 96)

    results = {}
    for key, label, script, args, tok in BASELINE:
        path = SCRIPTS / script
        if key == "reality" and fast and MATRIX.exists() and not dirty:
            results[key] = (GREEN, "(--fast: trusting current reports/live_path_results.json)")
            print("  %-44s %s  %s" % (label, GREEN, results[key][1]))
            continue
        if not path.exists():
            results[key] = (RED, "MISSING baseline gate %s" % script)
            print("  %-44s %s  MISSING %s" % (label, RED, script))
            continue
        ok, out = _run([path, *args], pass_token=tok)
        tail = next((ln for ln in reversed(out.splitlines()) if ln.strip()), "")[:88]
        results[key] = (GREEN if ok else RED, tail)
        print("  %-44s %s  %s" % (label, GREEN if ok else RED, tail))

    m = load_matrix()
    matrix_ok = False
    if m:
        c = m["counts"]
        bad = {s: c.get(s, 0) for s in _BAD_STATUSES if c.get(s, 0)}
        partials = [f for f in m["features"] if f.get("status") == "PARTIAL"]
        unblocked = [f["feature"] for f in partials
                     if "EXTERNAL" not in (f.get("reason") or "").upper()]
        matrix_ok = (not bad) and (not unblocked)
        print("-" * 96)
        print("  FEATURE AUDIT  %d contracts: %s"
              % (m["total"], " / ".join("%d %s" % (v, k) for k, v in sorted(c.items()))))
        if bad:
            print("    !! HARD-GAP statuses present: %s" % bad)
        if unblocked:
            print("    !! PARTIAL without an external-dependency reason: %s" % unblocked)
        for f in partials:
            print("    PARTIAL  %-22s %s" % (f["feature"], (f.get("reason") or "")[:82]))
    else:
        print("  FEATURE AUDIT  matrix unavailable (reports/live_path_results.json missing)")

    print("-" * 96)
    future_state = {}
    for key, label, phase, script in FUTURE:
        path = SCRIPTS / script
        if not path.exists():
            future_state[key] = DEFERRED
            print("  %-44s %s  (Phase %d — %s not built)" % (label, DEFERRED, phase, script))
        else:
            ok, out = _run([path, "--gate"])
            future_state[key] = GREEN if ok else RED
            tail = next((ln for ln in reversed(out.splitlines()) if ln.strip()), "")[:78]
            print("  %-44s %s  %s" % (label, future_state[key], tail))

    baseline_green = (all(v[0] == GREEN for v in results.values()) and matrix_ok and not dirty)
    all_future_green = all(s == GREEN for s in future_state.values())
    print("=" * 96)
    if baseline_green:
        print("DIAMOND BASELINE: GREEN   — every existing truth gate passes; 0 wallpaper / 0 unknown / "
              "0 stub; running == committed.")
    else:
        why = [k for k, v in results.items() if v[0] != GREEN]
        if dirty:
            why.append("dirty-tree")
        if not matrix_ok:
            why.append("matrix-hard-gap")
        print("DIAMOND BASELINE: RED   — blocking: %s" % (", ".join(why) or "unknown"))
    deferred_n = sum(1 for s in future_state.values() if s == DEFERRED)
    print("HARDENING PHASES: %d/%d built  (%d DEFERRED — honestly not green until their cert exists)"
          % (len(FUTURE) - deferred_n, len(FUTURE), deferred_n))
    if enterprise:
        print("ENTERPRISE: %s" % ("READY" if (baseline_green and all_future_green)
              else "NOT READY (%d hardening phases not yet certified)"
              % sum(1 for s in future_state.values() if s != GREEN)))

    _write_reports(head, dirty, stamp, results, m, future_state, baseline_green)
    print("reports: reports/diamond_baseline.md · current_audit_matrix.{json,md} · "
          "external_blockers.md · no_wallpaper_report.md · diamond_cert_report.json")

    if gate:
        return 0 if (baseline_green and (all_future_green if enterprise else True)) else 1
    return 0


def _write_reports(head, dirty, stamp, results, m, future_state, baseline_green):
    feats = (m or {}).get("features") or []
    counts = (m or {}).get("counts") or {}
    (REPORTS / "current_audit_matrix.json").write_text(json.dumps({
        "stamp": stamp, "commit": head, "dirty": dirty, "counts": counts, "total": len(feats),
        "features": [{"feature": f.get("feature"), "status": f.get("status"),
                      "reason": (f.get("reason") or "")[:300]} for f in feats]}, indent=2))
    rows = "\n".join("| %s | %s | %s |" % (f.get("feature"), f.get("status"),
                     (f.get("reason") or "").replace("|", "/")[:120])
                     for f in sorted(feats, key=lambda x: (x.get("status"), x.get("feature"))))
    (REPORTS / "current_audit_matrix.md").write_text(
        "# Vera — Current Audit Matrix\n\n_%s · commit %s%s_\n\n%s\n\n| feature | status | reason |\n"
        "|---|---|---|\n%s\n" % (stamp, head, " (DIRTY)" if dirty else "",
        " / ".join("**%d %s**" % (v, k) for k, v in sorted(counts.items())), rows))
    blocked = [f for f in feats if f.get("status") == "PARTIAL"]
    eb = ["# Vera — External Dependency Blockers\n", "_%s · commit %s_\n" % (stamp, head)]
    if not blocked:
        eb.append("\nNone — every contract is COMPLETE.\n")
    for f in blocked:
        eb.append("\n## %s — PARTIAL\n\n%s\n" % (f.get("feature"), f.get("reason") or ""))
        if f.get("missing_links"):
            eb.append("\nMissing links:\n" + "".join("- %s\n" % x for x in f["missing_links"]))
    (REPORTS / "external_blockers.md").write_text("".join(eb))
    bad = {s: counts.get(s, 0) for s in _BAD_STATUSES if counts.get(s, 0)}
    (REPORTS / "no_wallpaper_report.md").write_text(
        "# Vera — No-Wallpaper Report\n\n_%s · commit %s_\n\n"
        "WALLPAPER: **%d** · STUB: **%d** · UNREACHABLE: **%d** · REGRESSED: **%d** · UNKNOWN: **%d**\n\n%s\n"
        % (stamp, head, counts.get("WALLPAPER", 0), counts.get("STUB", 0), counts.get("UNREACHABLE", 0),
           counts.get("REGRESSED", 0), counts.get("UNKNOWN", 0),
           "Zero wallpaper / stub / unknown — every COMPLETE claim has a passing live-path cert."
           if not bad else "HARD GAPS PRESENT: %s" % bad))
    (REPORTS / "diamond_cert_report.json").write_text(json.dumps({
        "stamp": stamp, "commit": head, "dirty": dirty, "baseline_green": baseline_green,
        "baseline": {k: v[0] for k, v in results.items()},
        "matrix_counts": counts, "future": future_state}, indent=2))
    (REPORTS / "diamond_baseline.md").write_text(
        "# Vera — Diamond Audit Baseline\n\n_%s · commit %s%s_\n\n## Verdict: %s\n\n"
        "### Truth gates\n%s\n\n### Feature audit (%d contracts)\n%s\n\n"
        "### Hardening phases (honest)\n%s\n\n### External-blocked partials\n%s\n" % (
            stamp, head, " — DIRTY TREE" if dirty else "",
            "**DIAMOND BASELINE: GREEN**" if baseline_green else "**DIAMOND BASELINE: RED**",
            "\n".join("- %s — **%s**" % (k, v[0]) for k, v in results.items()),
            len(feats), " · ".join("**%d %s**" % (v, k) for k, v in sorted(counts.items())),
            "\n".join("- Phase %d %s — **%s**" % (p, lbl, future_state.get(k, "?"))
                      for k, lbl, p, _ in FUTURE),
            "\n".join("- **%s**: %s" % (f.get("feature"), (f.get("reason") or "")[:160])
                      for f in blocked) or "- none"))


if __name__ == "__main__":
    raise SystemExit(main())
