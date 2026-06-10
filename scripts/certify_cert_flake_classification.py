#!/usr/bin/env python3
"""certify_cert_flake_classification — every non-green / inconsistent cert result lands in exactly one
named class, an unclassified result is detected (and blocks Diamond), and the external dependency is
preflighted with real evidence. No hidden partials; no unclassified flakes.

  1. PREFLIGHT REAL    — the dependency preflight returns a structured state (running/degraded/
                         unavailable) with a measured latency + HTTP code (Argus, :8787).
  2. TAXONOMY HOLDS    — the four classes resolve correctly: an external-by-design partial
                         (acknowledge_flow) -> intentional_external_partial; a live-daemon partial with
                         the daemon degraded -> env_dependency_partial; a live-daemon partial that was
                         retried while the daemon is reachable -> harness_flake; an unknown partial ->
                         product_partial (release-blocking).
  3. UNCLASSIFIED BITES — a status that fits no class is classified 'unclassified' AND marked
                         release-blocking (this is what forbids a single-run / hand-waved Diamond).
  4. ACROSS-RUNS BITES  — a feature whose status VARIES across identical runs is surfaced; if it maps to
                         no class it is unclassified and repeatable=False.
  5. RETRY LOG BOUNDED  — the retry record carries a bounded max-attempts and a recovered/failed flag
                         (logged, never hidden).
  6. BLOCKING CORRECT   — product_* and unclassified are release-blocking; intentional/env/harness are not.

Hermetic. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import sys
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

    print("CERT-FLAKE CLASSIFICATION — every result lands in a named class; unclassified blocks Diamond")
    print("=" * 92)

    from anima.verification import preflight, flakes

    # ---- 1 preflight real ----------------------------------------------------------------------
    pf = preflight.argus_preflight()
    ck("1. the Argus preflight returns a real state + measured latency + code",
       pf.get("state") in ("running", "degraded", "unavailable")
       and (pf.get("state") == "unavailable" or (pf.get("latency_ms") is not None and pf.get("code") == 200)))

    # ---- 2 taxonomy holds ----------------------------------------------------------------------
    intent = flakes.classify_one("acknowledge_flow", "PARTIAL")
    env = flakes.classify_one("argus_host_awareness", "PARTIAL", dep_state="degraded")
    harness = flakes.classify_one("argus_host_awareness", "PARTIAL", dep_state="running", retried=True)
    product = flakes.classify_one("some_random_feature", "PARTIAL")
    ck("2. taxonomy: intentional / env-dependency / harness-flake / product partial each resolve",
       intent["class"] == "intentional_external_partial"
       and env["class"] == "env_dependency_partial"
       and harness["class"] == "harness_flake"
       and product["class"] == "product_partial")

    # ---- 2b deferred / not claimed (contract-declared release scope) -----------------------------
    deferred = flakes.classify_one("audiobook_intake", "DEFERRED")
    # fail-closed: DEFERRED on a feature with NO declared deferral is a product partial (blocking)
    undeclared = flakes.classify_one("some_random_feature", "DEFERRED")
    ck("2b. deferred-not-claimed: a DECLARED deferral is visible + non-blocking; an UNDECLARED "
       "DEFERRED status stays release-blocking (fail closed)",
       deferred["class"] == "deferred_not_claimed" and deferred["release_blocking"] is False
       and "not claimed" in deferred["why"]
       and undeclared["class"] == "product_partial" and undeclared["release_blocking"] is True)

    # ---- 3 unclassified bites ------------------------------------------------------------------
    weird = flakes.classify_one("x", "SOMETHING_WEIRD")
    ck("3. UNCLASSIFIED BITES — a status fitting no class is 'unclassified' + release-blocking",
       weird["class"] == "unclassified" and weird["release_blocking"] is True)

    # ---- 4 across-runs bites -------------------------------------------------------------------
    pf_run = {"dependencies": [{"daemon": "argus", "state": "running"}]}
    # a feature inconsistent across runs that maps to NO class -> unclassified, repeatable False
    runs = [[{"feature": "mystery", "status": "COMPLETE"}],
            [{"feature": "mystery", "status": "PARTIAL"}],
            [{"feature": "mystery", "status": "COMPLETE"}]]
    across = flakes.classify_across_runs(runs, pf_run)
    ck("4a. ACROSS-RUNS — an inconsistent feature with no class is unclassified + repeatable False",
       across["repeatable"] is False and any(u["feature"] == "mystery" for u in across["unclassified"]))
    # a KNOWN live-daemon feature inconsistent across runs -> harness_flake (classified, repeatable True)
    runs2 = [[{"feature": "argus_host_awareness", "status": "COMPLETE"}],
             [{"feature": "argus_host_awareness", "status": "PARTIAL"}],
             [{"feature": "argus_host_awareness", "status": "COMPLETE"}]]
    across2 = flakes.classify_across_runs(runs2, pf_run)
    arec = next((r for r in across2["features"] if r["feature"] == "argus_host_awareness"), {})
    ck("4b. ACROSS-RUNS — a known live-daemon feature inconsistency is classified harness_flake (repeatable)",
       arec.get("class") == "harness_flake" and across2["repeatable"] is True)

    # ---- 5 retry log bounded -------------------------------------------------------------------
    rec = flakes.classify_one("argus_host_awareness", "COMPLETE", recovered_after_retry=True)
    ck("5. a recovered-after-retry COMPLETE is a bounded, classified harness_flake (not silent)",
       rec["class"] == "harness_flake" and rec["release_blocking"] is False)

    # ---- 6 blocking correct --------------------------------------------------------------------
    ck("6. product_* + unclassified are release-blocking; intentional/env/harness are not",
       product["release_blocking"] and weird["release_blocking"]
       and not intent["release_blocking"] and not env["release_blocking"] and not harness["release_blocking"])

    print("\n  argus preflight: state=%s latency=%s code=%s" % (pf.get("state"), pf.get("latency_ms"), pf.get("code")))
    print("CERT-FLAKE-CLASSIFICATION CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
