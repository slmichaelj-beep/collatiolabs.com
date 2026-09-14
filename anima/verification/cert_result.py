"""verification.cert_result — the machine-readable cert result spine.

Every cert can EMIT a structured result file (reports/cert_results/<cert_name>.json) carrying the
exact context it ran in — commit, tree dirt, host, runtime profile, dependency versions, an inputs
hash over the files it observed — and every consumer EVALUATES that record against the live context
before treating it as green. The rules are the dashboard-green rules, enforced in one place:

    current commit == cert commit                      else -> stale
    dirty_worktree == false OR dirty files waived      else -> blocked
    required report files exist                        else -> blocked
    host_id matches (host-specific certs)              else -> blocked
    runtime_profile_id matches (host-specific certs)   else -> blocked
    inputs_hash still valid                            else -> stale
    dependency versions known                          else -> amber (visible, not green)

No UI state can create green. No stale record can create green. No unknown can create green.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = ROOT / "reports" / "cert_results"

STATUSES = ("green", "amber", "red", "blocked", "stale", "unknown")

REQUIRED_FIELDS = (
    "cert_name", "status", "commit", "dirty_worktree", "dirty_files", "files_observed",
    "files_changed_since", "generated_at", "host_id", "runtime_profile_id",
    "dependency_versions", "inputs_hash", "report_paths", "evidence_paths",
    "duration_sec", "failures", "warnings", "next_action",
)


# ---------------------------------------------------------------------------------------------
# live context
# ---------------------------------------------------------------------------------------------
def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def head_commit() -> str:
    return _git("rev-parse", "--short", "HEAD")


def dirty_files() -> list[str]:
    out = _git("status", "--short")
    return [ln[3:].strip() for ln in out.splitlines() if ln.strip()]


def host_id() -> str:
    """A stable, non-PII id for THIS machine: sha256 of the hardware platform UUID (fallback:
    hostname), first 16 hex chars. Host-specific certs are only green on the host they ran on."""
    raw = ""
    try:
        out = subprocess.run(["ioreg", "-d2", "-c", "IOPlatformExpertDevice"],
                             capture_output=True, text=True, timeout=10).stdout
        for ln in out.splitlines():
            if "IOPlatformUUID" in ln:
                raw = ln.split('"')[-2]
                break
    except Exception:
        pass
    if not raw:
        raw = platform.node()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def runtime_profile_id() -> str:
    """The active host runtime profile id, read from reports/host_runtime_profile.json
    (Increment 3's contract). Before a profile exists this is the honest 'unprofiled'."""
    try:
        j = json.loads((ROOT / "reports" / "host_runtime_profile.json").read_text())
        return "%s@%s" % (j.get("selected_profile", "?"), j.get("host_id", "?"))
    except Exception:
        return "unprofiled"


def dependency_versions(extra: dict | None = None) -> dict:
    deps = {"python": sys.version.split()[0]}
    try:
        import numpy
        deps["numpy"] = numpy.__version__
    except Exception:
        pass
    try:
        out = subprocess.run(["ollama", "--version"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
        if out:
            deps["ollama"] = out.split()[-1]
    except Exception:
        pass
    if extra:
        deps.update(extra)
    return deps


def inputs_hash(paths: list[str | Path]) -> str:
    """Deterministic sha256 over the (sorted) observed input files' bytes. A changed input
    invalidates the result — green cannot ride a hash that no longer matches reality."""
    h = hashlib.sha256()
    for p in sorted(str(x) for x in paths):
        f = (ROOT / p) if not Path(p).is_absolute() else Path(p)
        h.update(p.encode())
        try:
            h.update(f.read_bytes())
        except Exception:
            h.update(b"<unreadable>")
    return h.hexdigest()[:32]


# ---------------------------------------------------------------------------------------------
# emit / load
# ---------------------------------------------------------------------------------------------
def emit(cert_name: str, status: str, *, files_observed: list | None = None,
         report_paths: list | None = None, evidence_paths: list | None = None,
         failures: list | None = None, warnings: list | None = None,
         next_action: str = "", duration_sec: float = 0.0,
         host_specific: bool = False, extra_dependency_versions: dict | None = None) -> dict:
    """Write the schema-complete result record for one cert run. Returns the record."""
    if status not in STATUSES:
        status = "unknown"
    dirty = dirty_files()
    obs = [str(x) for x in (files_observed or [])]
    rec = {
        "cert_name": cert_name,
        "status": status,
        "commit": head_commit(),
        "dirty_worktree": bool(dirty),
        "dirty_files": dirty,
        "files_observed": obs,
        "files_changed_since": [],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host_id": host_id() if host_specific else "any",
        "runtime_profile_id": runtime_profile_id() if host_specific else "any",
        "dependency_versions": dependency_versions(extra_dependency_versions),
        "inputs_hash": inputs_hash(obs) if obs else "",
        "report_paths": [str(x) for x in (report_paths or [])],
        "evidence_paths": [str(x) for x in (evidence_paths or [])],
        "duration_sec": round(float(duration_sec), 3),
        "failures": list(failures or []),
        "warnings": list(warnings or []),
        "next_action": next_action,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{cert_name}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    return rec


def load(cert_name: str) -> dict | None:
    try:
        return json.loads((RESULTS_DIR / f"{cert_name}.json").read_text())
    except Exception:
        return None


def load_all() -> dict:
    out = {}
    if RESULTS_DIR.is_dir():
        for f in sorted(RESULTS_DIR.glob("*.json")):
            try:
                out[f.stem] = json.loads(f.read_text())
            except Exception:
                out[f.stem] = None
    return out


# ---------------------------------------------------------------------------------------------
# evaluate — the single green gate
# ---------------------------------------------------------------------------------------------
def evaluate(rec: dict | None, *, head: str | None = None, live_dirty: list | None = None,
             live_host_id: str | None = None, live_profile_id: str | None = None,
             waived_dirty: tuple = ()) -> dict:
    """Effective status of a stored cert result against the LIVE context. NEVER upgrades; only
    downgrades a recorded green that no longer holds. Returns {effective, recorded, reasons}."""
    if not rec or not isinstance(rec, dict):
        return {"effective": "unknown", "recorded": None,
                "reasons": ["no cert result record — unknown can never be green"]}
    reasons: list[str] = []
    recorded = rec.get("status", "unknown")
    if recorded not in STATUSES:
        recorded = "unknown"
    missing = [k for k in REQUIRED_FIELDS if k not in rec]
    if missing:
        return {"effective": "unknown", "recorded": recorded,
                "reasons": ["schema-incomplete record (missing: %s)" % ", ".join(missing)]}

    effective = recorded
    head = head if head is not None else head_commit()
    live_dirty = live_dirty if live_dirty is not None else dirty_files()

    # 1. commit must match
    if rec.get("commit") and head and rec["commit"] != head:
        effective = "stale"
        reasons.append("recorded commit %s != HEAD %s" % (rec["commit"], head))

    # 2. dirty tree blocks unless every dirty file is explicitly waived as non-impacting
    unwaived = [f for f in live_dirty if f not in waived_dirty]
    if unwaived and effective == "green":
        effective = "blocked"
        reasons.append("dirty worktree (unwaived: %s)" % ", ".join(unwaived[:8]))

    # 3. required report files must exist
    gone = [p for p in rec.get("report_paths", [])
            if not ((ROOT / p) if not Path(p).is_absolute() else Path(p)).exists()]
    if gone and effective in ("green", "amber"):
        effective = "blocked"
        reasons.append("required report(s) missing: %s" % ", ".join(gone[:8]))

    # 4/5. host + profile must match for host-specific certs
    if rec.get("host_id") not in ("any", None, ""):
        lh = live_host_id if live_host_id is not None else host_id()
        if rec["host_id"] != lh:
            effective = "blocked"
            reasons.append("host mismatch (ran on %s, this is %s)" % (rec["host_id"], lh))
    if rec.get("runtime_profile_id") not in ("any", None, ""):
        lp = live_profile_id if live_profile_id is not None else runtime_profile_id()
        if rec["runtime_profile_id"] != lp:
            effective = "blocked"
            reasons.append("runtime profile mismatch (ran under %s, live is %s)"
                           % (rec["runtime_profile_id"], lp))

    # 6. inputs hash must still hold
    if rec.get("inputs_hash") and rec.get("files_observed"):
        now = inputs_hash(rec["files_observed"])
        if now != rec["inputs_hash"]:
            if effective == "green":
                effective = "stale"
            reasons.append("inputs hash changed (observed files were modified since the run)")

    # 7. dependency versions must be known
    if not rec.get("dependency_versions"):
        if effective == "green":
            effective = "amber"
        reasons.append("dependency versions unknown")

    return {"effective": effective, "recorded": recorded, "reasons": reasons}


def evaluate_all(**ctx) -> dict:
    """{cert_name: evaluate(...)} over every stored result — the dashboard consumes this; a
    record whose effective status is not green can never light a green anywhere."""
    return {name: evaluate(rec, **ctx) for name, rec in load_all().items()}
