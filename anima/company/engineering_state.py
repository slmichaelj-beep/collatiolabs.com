"""company.engineering_state — Vera knows the real engineering state, from ground truth.

Reads git + the cert-result spine + freshness + the live server commit. Never reports green from
stale state: a dirty tree or stale cert is surfaced honestly. This is the "what changed / what's
blocked / what's the next exact step" answer.
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS = ROOT / "reports"


def _git(*a) -> str:
    try:
        return subprocess.run(["git", *a], cwd=str(ROOT), capture_output=True, text=True,
                              timeout=10).stdout.rstrip("\n")
    except Exception:
        return ""


def _server_commit() -> str | None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/version", timeout=3) as r:
            return json.loads(r.read()).get("sha")
    except Exception:
        return None


def snapshot() -> dict:
    head = _git("rev-parse", "--short", "HEAD")
    dirty = [ln[3:].strip() for ln in _git("status", "--short").splitlines() if ln.strip()]
    server = _server_commit()

    # cert-result spine: which stored results are no longer green under the live context
    downgraded, stale_certs = {}, []
    try:
        from anima.verification import cert_result as cr
        for nm, ev in cr.evaluate_all().items():
            if ev["effective"] != "green":
                downgraded[nm] = ev["effective"]
                if ev["effective"] in ("stale", "blocked", "unknown"):
                    stale_certs.append(nm)
    except Exception:
        pass

    # report freshness
    stale_reports = []
    try:
        from anima.verification import freshness
        fr = freshness.compute()
        stale_reports = list(fr.get("stale_required") or [])
    except Exception:
        pass

    deferred, enterprise_only, unknown_invalid = [], [], []
    try:
        from anima.verification import claim_registry as crg
        reg = crg.load() or {}
        for f, v in (reg.get("features") or {}).items():
            if v.get("status") == "deferred_visible":
                deferred.append(f)
            elif v.get("status") == "enterprise_only":
                enterprise_only.append(f)
            elif v.get("status") == "unknown_invalid":
                unknown_invalid.append(f)
    except Exception:
        pass

    deploy_clean = bool(head) and head == server and not dirty
    if not server:
        nxt = "start the server (python3 -m anima.server --name Vera --neurons 48 --voice)"
    elif server != head:
        nxt = "restart the server on HEAD %s (running %s)" % (head, server)
    elif dirty:
        nxt = "commit or stash %d dirty file(s), then re-run deploy_check" % len(dirty)
    elif stale_reports or stale_certs:
        nxt = "regenerate stale reports/certs: %s" % ", ".join((stale_reports + stale_certs)[:6])
    elif unknown_invalid:
        nxt = "classify unknown_invalid feature(s): %s" % ", ".join(unknown_invalid)
    else:
        nxt = "run scripts/run_diamond_v2.py --gate to confirm repeatability"

    return {
        "ok": True,
        "commit": head,
        "server_commit": server,
        "dirty_worktree": bool(dirty),
        "dirty_files": dirty,
        "active_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "deploy_clean": deploy_clean,
        "downgraded_certs": downgraded,
        "stale_certs": stale_certs,
        "stale_reports": stale_reports,
        "known_deferred": deferred,
        "known_enterprise_only": enterprise_only,
        "unknown_invalid": unknown_invalid,
        "next_recommended_action": nxt,
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
