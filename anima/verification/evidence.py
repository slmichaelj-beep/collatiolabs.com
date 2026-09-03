"""verification.evidence — the Evidence Room (directive §20): the product-proof documents that back
the release verdict, each with its freshness. A document referenced but absent is a gap, not green.
"""
from __future__ import annotations

import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS = ROOT / "reports"

# document -> path (relative to ROOT). These are the real artifacts the certs/gate produce.
DOCS = {
    "Program Reality report": "reports/live_path_matrix.md",
    "Program Reality (json)": "reports/live_path_results.json",
    "Scenario Coverage report": "reports/scenario_coverage.md",
    "Scenario Matrix (json)": "reports/scenario_matrix.json",
    "Diamond v2 repeatability": "reports/diamond_v2.json",
    "Cert-flake log": "reports/cert_flakes.json",
    "External dependency state": "reports/external_dependencies.json",
    "Browser surface routes": "reports/browser_surface_routes.json",
    "Control inventory": "reports/control_inventory.json",
    "API inventory": "reports/api_inventory.json",
}


def room() -> dict:
    """List each evidence document with existence + last-generated + staleness. Never raises."""
    now = time.time()
    items, present = [], 0
    for title, rel in DOCS.items():
        p = ROOT / rel
        exists = p.is_file()
        present += 1 if exists else 0
        age_h = None
        if exists:
            try:
                age_h = round((now - p.stat().st_mtime) / 3600.0, 1)
            except Exception:
                age_h = None
        items.append({"document": title, "path": rel, "exists": exists, "age_hours": age_h,
                      "status": "present" if exists else "missing", "link": "/" + rel})
    return {"documents": items, "present": present, "total": len(DOCS),
            "status": "green" if present == len(DOCS) else ("amber" if present else "red")}


if __name__ == "__main__":
    import json
    print(json.dumps(room(), indent=2))
