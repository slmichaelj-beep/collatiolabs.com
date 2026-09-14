"""renegade.runner — run the integrated stress chains, classify, summarise. Never raises."""
from __future__ import annotations

from . import chains

_CHAINS = (
    chains.chain_pwned_contamination,
    chains.chain_sensitive_memory_consent,
    chains.chain_agency_boundaries,
    chains.chain_living_map_reality,
    chains.chain_host_pressure_degrade,
)


def run() -> dict:
    """Run every chain. Returns {chains:[...], summary:{total, held, broken, p0}}."""
    results = []
    for fn in _CHAINS:
        try:
            results.append(fn())
        except Exception as e:
            results.append({"chain_id": fn.__name__.replace("chain_", ""), "title": fn.__name__,
                            "steps": [{"step": "chain raised", "ok": False, "detail": repr(e)[:160]}],
                            "held": False, "severity": "P0"})
    held = sum(1 for c in results if c["held"])
    return {
        "chains": results,
        "summary": {
            "total": len(results),
            "held": held,
            "broken": len(results) - held,
            "p0": sum(1 for c in results if c["severity"] == "P0"),
            "all_held": held == len(results),
        },
        "law": "Each chain is a cross-subsystem attack that must HOLD: hostile material caught + flushed, "
               "sensitive memory held for consent, agency suggest-only, the map derived not faked, safe "
               "degrade under pressure. The harness discriminates (clean input is not blocked), so a green "
               "chain means a real defense held — not wallpaper.",
    }
