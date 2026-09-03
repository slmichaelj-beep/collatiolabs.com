"""verification.build_identity — prove the exact app Lamar is touching is the exact app that was
certified: running == committed == served == certified.

All four legs are computed from reality:
  running   — the SHA the live server reports at GET /version (the actual backend process).
  committed — git HEAD of the active worktree (the code on disk).
  served    — a hash of the served frontend bundle (anima/web), cross-checked against what the live
              server actually returns for a sample page (so a stale bundle / index stub is caught).
  certified — the SHA stamped by the most recent verification run (reports/verification/last_run.json).

A mismatch on any leg is a release blocker. Nothing is assumed; an unknown leg is BLOCKED, not green.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WEB = ROOT / "anima" / "web"
LAST_RUN = ROOT / "reports" / "verification" / "last_run.json"
SERVER = "http://127.0.0.1:8765"


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except Exception:
        return ""


def _server_version() -> dict:
    try:
        with urllib.request.urlopen(SERVER + "/version", timeout=6) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}


def frontend_hash() -> str:
    """A deterministic hash of the served frontend bundle (every web asset, by sorted path)."""
    h = hashlib.sha256()
    if not WEB.is_dir():
        return ""
    for p in sorted(WEB.rglob("*")):
        if p.is_file() and p.suffix in (".html", ".js", ".css"):
            h.update(p.relative_to(WEB).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _served_matches_disk(sample: str = "/reality") -> bool:
    """Cross-check: the bytes the LIVE server returns for a sample page equal the on-disk file (so a
    stale/old served bundle or an index stub is caught — served == committed, not just claimed)."""
    fn = WEB / (sample.lstrip("/") + ".html")
    if not fn.is_file():
        return False
    try:
        with urllib.request.urlopen(SERVER + sample, timeout=6) as r:
            served = r.read()
        return hashlib.sha256(served).hexdigest() == hashlib.sha256(fn.read_bytes()).hexdigest()
    except Exception:
        return False


def certified_commit() -> str | None:
    try:
        return json.loads(LAST_RUN.read_text()).get("commit")
    except Exception:
        return None


def compute() -> dict:
    """Return the full build-identity picture + a computed match verdict. Never raises."""
    head = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    ver = _server_version()
    running = (ver.get("sha") or "")
    committed_short = head[:len(running)] if running else head[:7]
    fe = frontend_hash()
    served_ok = _served_matches_disk()
    certified = certified_commit()

    running_known = bool(running)
    running_matches = running_known and (running == committed_short)
    certified_matches = bool(certified) and certified.startswith(running) if running else False

    # GREEN requires all four legs known + matching + a clean tree. Any unknown => not green.
    legs = {
        "running_known": running_known,
        "running_eq_committed": running_matches,
        "served_eq_committed": served_ok,
        "certified_eq_running": certified_matches,
        "clean_tree": not dirty,
    }
    status = "green" if all(legs.values()) else ("blocked" if not running_known else "red")
    return {
        "status": status,
        "running_commit": running or None,
        "committed_commit": head or None,
        "certified_commit": certified,
        "branch": branch or None,
        "worktree": str(ROOT),
        "backend_process": SERVER,
        "served_frontend_hash": fe or None,
        "clean_tree": not dirty,
        "legs": legs,
        "match": all(legs.values()),
        "server_started": ver.get("started"),
    }


def stamp_run(commit: str | None = None) -> str:
    """Record that a verification run executed at `commit` (defaults to HEAD) — this is what makes
    `certified` real and non-circular: a run stamps the certified SHA."""
    commit = commit or _git("rev-parse", "HEAD")
    LAST_RUN.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN.write_text(json.dumps({"commit": commit}, indent=2))
    return commit


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
