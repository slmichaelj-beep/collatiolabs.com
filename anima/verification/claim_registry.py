"""verification.claim_registry — the canonical release-claim status of every feature.

One registry, derived from ground truth (feature contracts + the live-path classifier + the
release-tier waiver table), so "what does this release actually claim?" has exactly one answer.

Statuses:
    claimed_green     — claimed by the current release and proven COMPLETE.
    claimed_amber     — claimed, honestly PARTIAL (visible work state).
    claimed_red       — claimed but red (STUB/WALLPAPER/UNKNOWN/REGRESSED) — release-blocking.
    deferred_visible  — explicit contract-declared deferral; visible everywhere, never blocking.
    not_claimed       — not part of any current tier's claims and not advertised.
    enterprise_only   — claimed only at the Enterprise rung; never blocks Local/Internal.
    future_tier_only  — becomes required only at a named FUTURE tier (not yet on the ladder).
    removed           — no longer in the product; may not have any active UI route.
    unknown_invalid   — fits nothing above. BLOCKS ALL GREEN until classified.

Rules (enforced by certify_claim_registry / certify_release_tier_blockers /
certify_deferred_capabilities):
    unknown_invalid blocks all green
    deferred_visible remains visible
    not_claimed is not advertised
    enterprise_only does not block Local/Internal
    future_tier_only does not block current tiers
    removed cannot have an active UI route
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS = ROOT / "reports"
CONTRACTS = ROOT / "feature_contracts"

STATUSES = ("claimed_green", "claimed_amber", "claimed_red", "deferred_visible", "not_claimed",
            "enterprise_only", "future_tier_only", "removed", "unknown_invalid")

# advertise-tokens: if ANY of these strings appears in the served app UI, the feature is being
# actively claimed there. Used to prove deferred/not_claimed/removed features are NOT advertised.
ADVERTISE_TOKENS = {
    "audiobook_intake": ("audiobook", ".m4b"),
}

_RED = {"STUB", "WALLPAPER", "UNKNOWN", "REGRESSED"}


def _live_statuses() -> dict:
    try:
        d = json.loads((REPORTS / "live_path_results.json").read_text())
        items = d if isinstance(d, list) else d.get("results", d.get("features", []))
        return {x.get("feature"): (x.get("status") or "").upper() for x in items}
    except Exception:
        return {}


def classify(feature: str, contract: dict, live_status: str | None,
             required_at: dict, future_tiers: dict) -> tuple[str, str]:
    """(registry_status, reason) for one feature — pure over its inputs."""
    if contract.get("removed") is True:
        return "removed", "contract marks the feature removed from the product"
    # explicit contract-declared deferral (the audiobook_intake mechanism)
    if ((contract.get("status") or "").upper() == "DEFERRED"
            and contract.get("release_required") is False
            and contract.get("claimed_by_current_tier") is False):
        return "deferred_visible", (contract.get("deferred_reason") or "contract-declared deferral"
                                    ) + " — future tier: %s" % (contract.get("future_tier") or "?")
    spec = required_at.get(feature)
    if spec:
        req_tier, _kind = spec
        if req_tier in future_tiers:
            return "future_tier_only", "required only at the future %r tier" % future_tiers[req_tier]
        if req_tier == "enterprise":
            return "enterprise_only", "claimed only at the Enterprise rung"
    if live_status == "COMPLETE":
        return "claimed_green", "claimed by the current release and proven COMPLETE"
    if live_status in ("PARTIAL", "DEFERRED", "DISABLED"):
        return "claimed_amber", "claimed, honestly %s (visible work state)" % live_status
    if live_status in _RED:
        return "claimed_red", "claimed but %s — release-blocking" % live_status
    return "unknown_invalid", "no live-path status and no declared scope — must be classified"


def build() -> dict:
    """Build the registry from ground truth and write reports/claim_registry.{json,md}."""
    from .release_tiers import REQUIRED_AT, FUTURE_TIERS
    live = _live_statuses()
    feats = {}
    for f in sorted(CONTRACTS.glob("*.json")):
        try:
            contract = json.loads(f.read_text())
        except Exception:
            contract = {}
        name = contract.get("feature") or f.stem
        status, reason = classify(name, contract, live.get(name), REQUIRED_AT, FUTURE_TIERS)
        feats[name] = {
            "status": status,
            "reason": reason,
            "live_path_status": live.get(name),
            "future_tier": contract.get("future_tier"),
            "advertise_tokens": list(ADVERTISE_TOKENS.get(name, ())),
        }
    # live-path features with NO contract are unknown_invalid too (a probe with no claim)
    for name, st in live.items():
        if name and name not in feats:
            feats[name] = {"status": "unknown_invalid",
                           "reason": "live-path feature with no contract", "live_path_status": st,
                           "future_tier": None, "advertise_tokens": []}
    counts = {}
    for v in feats.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    out = {
        "report": "claim_registry",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": _head(),
        "features": feats,
        "counts": counts,
        "unknown_invalid": sorted(n for n, v in feats.items() if v["status"] == "unknown_invalid"),
        "green_blocked": bool(any(v["status"] == "unknown_invalid" for v in feats.values())),
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "claim_registry.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    md = ["# Claim registry — what this release actually claims",
          "", "Generated %s at commit `%s`." % (out["generated_at"], out["commit"]), "",
          "| feature | registry status | live path | reason |", "|---|---|---|---|"]
    order = {s: i for i, s in enumerate(STATUSES)}
    for n, v in sorted(feats.items(), key=lambda kv: (order.get(kv[1]["status"], 99), kv[0])):
        md.append("| %s | **%s** | %s | %s |" % (n, v["status"], v["live_path_status"] or "—",
                                                 v["reason"]))
    md.append("")
    md.append("Counts: " + ", ".join("%s=%d" % kv for kv in sorted(counts.items())))
    (REPORTS / "claim_registry.md").write_text("\n".join(md) + "\n")
    return out


def ui_violations(html_text: str, registry: dict | None = None) -> list[dict]:
    """Deferred / not_claimed / removed features whose advertise-tokens appear in the served UI —
    each is an ACTIVE CLAIM of a non-claimed feature and fails the deferred-capabilities cert."""
    reg = registry or load()
    low = (html_text or "").lower()
    bad = []
    for name, v in (reg.get("features") or {}).items():
        if v["status"] in ("deferred_visible", "not_claimed", "removed", "future_tier_only"):
            hit = [t for t in v.get("advertise_tokens", []) if t and t.lower() in low]
            if hit:
                bad.append({"feature": name, "status": v["status"], "tokens": hit})
    return bad


def load() -> dict:
    try:
        return json.loads((REPORTS / "claim_registry.json").read_text())
    except Exception:
        return {}


def _head() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


if __name__ == "__main__":
    print(json.dumps(build()["counts"], indent=1))
