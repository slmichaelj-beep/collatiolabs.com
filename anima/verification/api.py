"""verification.api — the verification run store, founder-override store, and blocker acknowledgements.

Read endpoints serve the computed dashboard. Write actions are auth-gated and RECORDED:
  - a verification run is spawned in the background and tracked (id / type / commit / status / log).
  - a Founder Override is the ONLY way a human may move the release verdict, and it cannot be created
    without a complete record (who / why / risk / expiry / follow-up). It NEVER flips a gate — it is a
    recorded, expiring human acceptance surfaced alongside the computed verdict.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
VDIR = ROOT / "reports" / "verification"
RUNS = VDIR / "runs"
OVERRIDES = VDIR / "overrides.json"
ACKS = VDIR / "acknowledgements.json"

RUN_SCRIPTS = {
    "smoke": "run_verification_smoke.py",
    "critical": "run_verification_critical.py",
    "full": "run_verification_full.py",
    "diamond": "run_diamond_v2.py",
}


def _git(*a):
    try:
        return subprocess.run(["git", *a], cwd=str(ROOT), capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _load(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def _newid(prefix):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:10])


# ---- runs --------------------------------------------------------------------------------------
def start_run(run_type: str, at: str | None = None) -> dict:
    """Spawn the run script in the background; return the tracked run record. at: a timestamp string
    (passed by the caller — this module never reads the clock)."""
    if run_type not in RUN_SCRIPTS:
        return {"error": "unknown run_type %r" % run_type}
    RUNS.mkdir(parents=True, exist_ok=True)
    rid = _newid(run_type)
    log = RUNS / (rid + ".log")
    args = [sys.executable, str(ROOT / "scripts" / RUN_SCRIPTS[run_type])]
    if run_type in ("diamond",):
        args += ["--gate"]
    rec = {"verification_run_id": rid, "run_type": run_type, "commit": _git("rev-parse", "HEAD"),
           "started_at": at, "status": "running", "log": "reports/verification/runs/%s.log" % rid}
    try:
        with log.open("w") as fh:
            subprocess.Popen(args, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT)
    except Exception as e:
        rec["status"] = "error"
        rec["error"] = repr(e)[:120]
    (RUNS / (rid + ".json")).write_text(json.dumps(rec, indent=2))
    return rec


def get_run(rid: str) -> dict:
    rec = _load(RUNS / (rid + ".json"), None)
    if rec is None:
        return {"error": "no such run %r" % rid}
    log = RUNS / (rid + ".log")
    tail = ""
    try:
        tail = log.read_text()[-2000:]
    except Exception:
        pass
    # a run is 'done' once its script has emitted a terminal line
    if any(k in tail for k in ("REPEATABILITY: CONFIRMED", "REPEATABILITY: BLOCKED",
                               "VERIFICATION STATUS", "CERTIFICATION COMPLETE", "exit=")):
        rec["status"] = "done"
        (RUNS / (rid + ".json")).write_text(json.dumps(rec, indent=2))
    rec["tail"] = tail
    return rec


def list_runs() -> list[dict]:
    out = []
    if RUNS.is_dir():
        for f in sorted(RUNS.glob("*.json"), reverse=True)[:50]:
            out.append(_load(f, {}))
    return out


# ---- founder override --------------------------------------------------------------------------
def record_override(who, gate, why, risk_accepted, expires_at, required_follow_up, at=None) -> dict:
    """Append a Founder Override. REQUIRES every field — an incomplete override is rejected, not stored."""
    missing = [k for k, v in (("who", who), ("gate", gate), ("why", why),
                              ("risk_accepted", risk_accepted), ("expires_at", expires_at),
                              ("required_follow_up", required_follow_up)) if not v]
    if missing:
        return {"error": "founder override REQUIRES: %s" % ", ".join(missing)}
    from . import schema
    rec = schema.founder_override(who, gate, why, risk_accepted=risk_accepted, expires_at=expires_at,
                                  required_follow_up=required_follow_up, at=at)
    VDIR.mkdir(parents=True, exist_ok=True)
    data = _load(OVERRIDES, [])
    data.append(rec)
    OVERRIDES.write_text(json.dumps(data, indent=2))
    return rec


def overrides() -> list[dict]:
    return _load(OVERRIDES, [])


def active_overrides(now: str | None = None) -> list[dict]:
    """Overrides whose expires_at is not before `now` (string compare on ISO timestamps). If `now` is
    not supplied, all recorded overrides are returned (the caller decides expiry)."""
    data = _load(OVERRIDES, [])
    if now is None:
        return data
    return [o for o in data if str(o.get("expires_at") or "") >= now]


def acknowledge_blocker(blocker_id, who, note="", at=None) -> dict:
    if not blocker_id or not who:
        return {"error": "acknowledge requires blocker_id + who"}
    VDIR.mkdir(parents=True, exist_ok=True)
    data = _load(ACKS, [])
    rec = {"blocker_id": blocker_id, "who": who, "note": note, "at": at}
    data.append(rec)
    ACKS.write_text(json.dumps(data, indent=2))
    return rec
