"""verification.freshness — old green is not current green.

A cert/report is STALE if a file it covers changed AFTER the report was written, or (for reports that
record the commit they ran at) if that commit != the current HEAD. Stale required certs can never be
green. This is what stops a months-old PASS from masking today's code.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS = ROOT / "reports"

# report -> (covered globs relative to ROOT, whether it is required for diamond)
COVERED = {
    "live_path_results.json": (["anima/**/*.py", "scripts/certify_*.py", "feature_contracts/*.json"], True),
    "scenario_matrix.json":   (["anima/scenarios/*.py"], True),
    "browser_surface_routes.json": (["anima/web/*.html", "anima/server.py"], True),
    "diamond_v2.json":        (["anima/verification/*.py", "scripts/certify_live_paths.py"], True),
}


def _head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _newest_mtime(globs: list[str]) -> float:
    newest = 0.0
    for g in globs:
        for p in ROOT.glob(g):
            try:
                if p.is_file():
                    newest = max(newest, p.stat().st_mtime)
            except Exception:
                pass
    return newest


def compute() -> dict:
    """Per-report freshness: stale if a covered file is newer than the report, or its recorded commit
    differs from HEAD. Returns {reports:[...], any_stale, stale_required}."""
    head = _head()
    out = []
    for name, (globs, required) in COVERED.items():
        f = REPORTS / name
        if not f.exists():
            out.append({"report": name, "exists": False, "stale": True, "required": required,
                        "reason": "report missing (never generated on this checkout)"})
            continue
        try:
            rmtime = f.stat().st_mtime
        except Exception:
            rmtime = 0.0
        newest = _newest_mtime(globs)
        mtime_stale = newest > rmtime
        commit_stale = False
        recorded = None
        try:
            recorded = (json.loads(f.read_text()).get("commit") or "")
        except Exception:
            recorded = None
        if recorded and head:
            commit_stale = recorded[:12] != head[:12]      # report ran at a different commit than HEAD
        stale = mtime_stale or commit_stale
        reason = ""
        if mtime_stale:
            reason = "a covered source changed after the report was written"
        elif commit_stale:
            reason = "report ran at commit %s, HEAD is %s" % (recorded[:7], head[:7])
        out.append({"report": name, "exists": True, "stale": stale, "required": required,
                    "mtime_stale": mtime_stale, "commit_stale": commit_stale,
                    "recorded_commit": (recorded or None), "reason": reason})
    any_stale = any(r["stale"] for r in out)
    stale_required = [r["report"] for r in out if r["stale"] and r["required"]]
    return {"reports": out, "any_stale": any_stale, "stale_required": stale_required, "head": head}


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
