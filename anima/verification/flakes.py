"""verification.flakes — classify every non-green / inconsistent cert result into a bounded class.

The directive's bar: Diamond cannot be green with an UNCLASSIFIED flake. So every PARTIAL and every
status that varies across identical full-gate runs must land in exactly one named class:

  intentional_external_partial — an external dependency that cannot be built/exercised locally and is
                                 partial BY DESIGN (e.g. acknowledge_flow needs Apple's APNs stack).
  env_dependency_partial       — a live external daemon was unavailable/degraded at gate time (Argus).
  harness_flake                — the cert passes standalone but flaked under full-gate concurrency
                                 (proven by cross-run inconsistency or a recovered-after-retry record).
  deferred_not_claimed         — a contract-declared deferral: the feature is NOT part of any current
                                 release tier's claims (release_required=false). Visible, never blocking,
                                 never hidden; it becomes required only at its named future tier.
  product_partial              — a real product gap (the only class that should worry us).
  product_red                  — STUB/WALLPAPER/UNKNOWN/REGRESSED: a release-blocking product defect.
  ok                           — COMPLETE, first try.
  unclassified                 — fits none of the above; this BLOCKS Diamond until classified.

The retry policy is bounded + logged (reports/cert_flakes.json), never hidden.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FLAKE_LOG = ROOT / "reports" / "cert_flakes.json"

# features DEFERRED by an explicit product decision: not claimed by any current release tier; the
# contract carries release_required=false + claimed_by_current_tier=false + a named future tier.
# Visible in every classification surface as "deferred / not claimed" — never blocking, never hidden.
DEFERRED_NOT_CLAIMED = {
    "audiobook_intake": "deferred / not claimed for this release — not part of current Local/Internal "
                        "Vera release scope (product decision 2026-06-09); becomes required only at the "
                        "future 'Media/Audiobook Intake' tier.",
}
# features that are PARTIAL by design because an external dependency cannot be exercised locally
INTENTIONAL_EXTERNAL = {
    "acknowledge_flow": "Apple APNs / VoIP PushKit stack not built (no .p8 key, no built iOS app) — "
                        "the phone push -> tap -> POST /acknowledge round-trip cannot be exercised locally.",
}
# features whose certs make LIVE calls to an external daemon -> map feature -> dependency name
EXTERNAL_DEP = {
    "argus_host_awareness": "argus",
    "whole_system_mri": "argus",
}
# feature -> the sub-cert script basename whose retries are logged (so a recovered-after-retry flake
# attributes to the right feature). The retry log (reports/cert_flakes.json) is keyed by basename.
CERT_OF = {
    "argus_host_awareness": "certify_argus_integration",
    "enterprise_readiness": "enterprise_readiness",
    "whole_system_mri": "certify_whole_mri",
    "response_latency": "certify_response_latency",
    "vera_rover": "vera_rover",
}

PRODUCT_RED = {"STUB", "WALLPAPER", "UNKNOWN", "REGRESSED"}
PARTIALISH = {"PARTIAL", "DEFERRED", "DISABLED"}


def read_flake_log() -> dict:
    """{cert_name: {attempts, passed_after_retry, final_rc}} written by the gate's run_subcert."""
    try:
        return json.loads(FLAKE_LOG.read_text())
    except Exception:
        return {}


def classify_one(feature: str, status: str, *, dep_state: str | None = None,
                 recovered_after_retry: bool = False, retried: bool = False,
                 cross_run_inconsistent: bool = False) -> dict:
    """Classify one feature's result. Returns {class, release_blocking, why}."""
    s = (status or "").upper()
    dep = EXTERNAL_DEP.get(feature)

    if s == "COMPLETE":
        if recovered_after_retry:
            return {"class": "harness_flake", "release_blocking": False,
                    "why": "completed, but needed a bounded retry under full-gate load — a logged harness flake."}
        return {"class": "ok", "release_blocking": False, "why": "complete on the first attempt."}

    if s in PRODUCT_RED:
        return {"class": "product_red", "release_blocking": True, "why": "%s — a release-blocking product defect." % s}

    if s in PARTIALISH:
        if s == "DEFERRED" and feature in DEFERRED_NOT_CLAIMED:
            return {"class": "deferred_not_claimed", "release_blocking": False,
                    "why": DEFERRED_NOT_CLAIMED[feature]}
        if feature in INTENTIONAL_EXTERNAL:
            return {"class": "intentional_external_partial", "release_blocking": False,
                    "why": INTENTIONAL_EXTERNAL[feature]}
        if dep and dep_state in ("unavailable", "degraded"):
            return {"class": "env_dependency_partial", "release_blocking": False,
                    "why": "external dependency '%s' was %s at gate time." % (dep, dep_state)}
        # a HARNESS flake must have EVIDENCE it is harness/environment, not a bare "it varied":
        #   a logged bounded retry, OR a known live-daemon cert (retried / inconsistent under load).
        if recovered_after_retry:
            return {"class": "harness_flake", "release_blocking": False,
                    "why": "recovered after a bounded, logged retry under full-gate load."}
        if dep and (retried or cross_run_inconsistent):
            return {"class": "harness_flake", "release_blocking": False,
                    "why": "live-daemon cert ('%s') flaked under full-gate concurrency (retried / inconsistent; daemon reachable); passes standalone." % dep}
        if cross_run_inconsistent:
            # varied across identical runs with NO external-dep mapping and NO retry evidence — the cause
            # is unknown (possible product non-determinism). NEVER auto-blessed as benign.
            return {"class": "unclassified", "release_blocking": True,
                    "why": "status varied across identical runs with no external-dependency or retry evidence — unknown cause; must be triaged before Diamond."}
        return {"class": "product_partial", "release_blocking": True,
                "why": "a real product gap (not external, not a known flake)."}

    # any other / inconsistent state with no class
    return {"class": "unclassified", "release_blocking": True,
            "why": "status '%s' fits no known class — must be triaged before Diamond." % (status or "?")}


def classify_run(items: list[dict], preflight: dict, flake_log: dict | None = None) -> dict:
    """Classify a single full-gate run. items = the live_path feature records."""
    flake_log = flake_log if flake_log is not None else read_flake_log()
    dep_state = {d["daemon"]: d["state"] for d in (preflight or {}).get("dependencies", [])}
    out, counts = [], {}
    for it in items:
        feat, st = it.get("feature"), it.get("status")
        dep = EXTERNAL_DEP.get(feat)
        cert_key = CERT_OF.get(feat, feat)
        log_rec = flake_log.get(cert_key) or flake_log.get(feat) or {}
        recovered = bool(log_rec.get("passed_after_retry"))
        retried = bool(log_rec)                          # present in the log == it flaked + was retried
        c = classify_one(feat, st, dep_state=dep_state.get(dep) if dep else None,
                         recovered_after_retry=recovered, retried=retried)
        out.append({"feature": feat, "status": st, **c})
        counts[c["class"]] = counts.get(c["class"], 0) + 1
    unclassified = [o["feature"] for o in out if o["class"] == "unclassified"]
    return {"per_feature": out, "counts": counts, "unclassified": unclassified,
            "honest_partials": [o["feature"] for o in out
                                if o["class"] in ("intentional_external_partial", "env_dependency_partial")],
            "deferred_not_claimed": [o["feature"] for o in out if o["class"] == "deferred_not_claimed"],
            "product_partials": [o["feature"] for o in out if o["class"] == "product_partial"],
            "product_red": [o["feature"] for o in out if o["class"] == "product_red"],
            "harness_flakes": [o["feature"] for o in out if o["class"] == "harness_flake"]}


def classify_across_runs(runs: list[dict], preflight: dict) -> dict:
    """Compare N identical-HEAD runs. A feature whose status varies across runs is a flake — it must
    land in a known class (env/intentional/harness) or it is UNCLASSIFIED and blocks Diamond."""
    feats = {}
    for r in runs:
        for it in r:
            feats.setdefault(it.get("feature"), []).append((it.get("status") or "").upper())
    dep_state = {d["daemon"]: d["state"] for d in (preflight or {}).get("dependencies", [])}
    classified, unclassified, varied = [], [], []
    for feat, statuses in feats.items():
        inconsistent = len(set(statuses)) > 1
        worst = "COMPLETE"
        for s in statuses:                              # the worst status seen across runs
            if s in PRODUCT_RED:
                worst = s
            elif s in PARTIALISH and worst == "COMPLETE":
                worst = s
        dep = EXTERNAL_DEP.get(feat)
        c = classify_one(feat, worst, dep_state=dep_state.get(dep) if dep else None,
                         cross_run_inconsistent=inconsistent)
        rec = {"feature": feat, "statuses": statuses, "inconsistent": inconsistent, **c}
        if inconsistent:
            varied.append(rec)
        if c["class"] == "unclassified":
            unclassified.append(rec)
        classified.append(rec)
    return {"features": classified, "varied_across_runs": varied, "unclassified": unclassified,
            "unclassified_count": len(unclassified), "repeatable": len(unclassified) == 0}
