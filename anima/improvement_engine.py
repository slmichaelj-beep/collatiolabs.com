"""
improvement_engine — the SELF-IMPROVING layer (Phase 6 of the Vera moonshot).

The Pattern Observatory (Phase 5) turns observation into engineering work orders:

    pattern  ->  evidence  ->  root cause  ->  recommended fix  ->  required cert

This module closes the loop. It ingests those work orders (reports/patterns.json) into a tracked
IMPROVEMENT BACKLOG and drives each one to CERTIFIED CLOSURE by actually RUNNING its required cert:

    work order  ->  backlog item  ->  run cert_required  ->  CERTIFIED (fix proven) | NEEDS_WORK

So the system does not just diagnose itself; it tracks its own diagnoses to a verifiable fix and
tells you, honestly, which are PROVEN done and which still need work. A backlog item's status is
DECIDED by its cert, never asserted — the same no-wallpaper rule, one level up: a fix is "done"
only when its cert passes RIGHT NOW.

Lifecycle (status is computed from the cert, not hand-set):
  OPEN        — a work order exists, not yet verified this run.
  CERTIFIED   — every runnable cert_required passes NOW (the fix is in and proven). Terminal-good.
  NEEDS_WORK  — a runnable cert_required ran and FAILED (the fix is absent or regressed). Actionable.
  MANUAL      — no cert_required could be resolved to a runnable command (a human must verify).

Design rules (mirror root_cause.py / patterns.py):
  * Pure + hermetic by default. The ONLY side effect is reading reports/patterns.json and writing
    reports/improvement_backlog.json. It NEVER writes .anima, never hits the live server. Running a
    cert is delegated to an injectable `runner` (the selftest injects a fake one — no subprocess),
    and the certs we DO run are themselves hermetic.
  * Severity + ranking come from anima.root_cause (single source of truth — no drift).
  * Re-ingesting preserves each item's history (created stamp, last verification) while refreshing
    the work-order fields from the latest patterns.json.
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from . import root_cause as _rc
except Exception:                                   # pragma: no cover - direct-script import
    import root_cause as _rc                         # type: ignore

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
PATTERNS_JSON = REPORTS / "patterns.json"
BACKLOG_JSON = REPORTS / "improvement_backlog.json"

OPEN, CERTIFIED, NEEDS_WORK, MANUAL = "OPEN", "CERTIFIED", "NEEDS_WORK", "MANUAL"
# Backlog ordering: actionable first (NEEDS_WORK, then OPEN), MANUAL, then the proven-done CERTIFIED.
_STATUS_RANK = {NEEDS_WORK: 0, OPEN: 1, MANUAL: 2, CERTIFIED: 3}

# Descriptive cert_required phrases the Observatory emits, mapped to the runnable cert that proves
# them (kept tiny + explicit so a phrase can never silently resolve to the wrong script).
_CERT_ALIASES: Dict[str, List[str]] = {
    "conversation_repair killer test": ["scripts/certify_repair.py"],
    "certify_repair.py": ["scripts/certify_repair.py"],
    "capability_truth live-path check": ["scripts/certify_live_paths.py", "--gate"],
    "response_completeness live-path check": ["scripts/certify_live_paths.py", "--gate"],
    "anima.host_window probe": ["python3", "-m", "anima.host_window", "--selftest"],
}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_cert(cert_str: str) -> Optional[List[str]]:
    """Map one cert_required phrase to a runnable argv (relative to repo root), or None if it is
    descriptive-only. Accepts: an explicit alias, a 'python3 -m pkg ...' form, a 'scripts/x.py ...'
    path, or a bare 'x.py' (assumed under scripts/)."""
    s = (cert_str or "").strip()
    if not s:
        return None
    if s in _CERT_ALIASES:
        return list(_CERT_ALIASES[s])
    parts = s.split()
    if parts[0] == "python3" and len(parts) >= 3 and parts[1] == "-m":
        return parts
    if parts[0].startswith("scripts/") and parts[0].endswith(".py"):
        return parts
    if parts[0].endswith(".py") and "/" not in parts[0]:
        return ["scripts/" + parts[0]] + parts[1:]
    return None


def runnable_certs(cert_required: List[str]) -> List[List[str]]:
    """The de-duplicated list of runnable argvs for an item's cert_required (order preserved)."""
    out: List[List[str]] = []
    seen = set()
    for c in cert_required or []:
        argv = resolve_cert(c)
        if argv is None:
            continue
        key = tuple(argv)
        if key not in seen:
            seen.add(key)
            out.append(argv)
    return out


@dataclass
class BacklogItem:
    pattern_id: str
    title: str
    severity: str
    frequency: int = 0
    root_cause: str = ""
    recommended_fix: str = ""
    cert_required: List[str] = field(default_factory=list)
    expected_improvement: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Any] = field(default_factory=list)
    source: str = ""
    status: str = OPEN
    created: str = ""
    updated: str = ""
    verification: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_pattern(cls, p: dict) -> "BacklogItem":
        now = _now()
        return cls(
            pattern_id=str(p.get("pattern_id", "")),
            title=str(p.get("title", p.get("pattern_id", ""))),
            severity=str(p.get("severity", _rc.default_severity_for(str(p.get("pattern_id", ""))))),
            frequency=int(p.get("frequency", 0) or 0),
            root_cause=str(p.get("root_cause", "")),
            recommended_fix=str(p.get("recommended_fix", "")),
            cert_required=list(p.get("cert_required", []) or []),
            expected_improvement=dict(p.get("expected_improvement", {}) or {}),
            evidence=list(p.get("evidence", []) or []),
            source=str(p.get("source", "")),
            status=OPEN, created=now, updated=now,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "BacklogItem":
        known = {f for f in cls.__dataclass_fields__}            # tolerate extra keys
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


def _patterns_list(payload: Any) -> List[dict]:
    """Accept the full pattern_observatory payload ({'patterns': [...]}) or a bare list."""
    if isinstance(payload, dict):
        items = payload.get("patterns", [])
    else:
        items = payload
    return [p for p in (items or []) if isinstance(p, dict) and p.get("pattern_id")]


def ingest(payload: Any, existing: Optional[List[BacklogItem]] = None) -> List[BacklogItem]:
    """Fold patterns into the backlog. New pattern_ids are added OPEN; known ones keep their
    created stamp + last verification/status but refresh the work-order fields from the latest
    patterns.json (so a re-detected pattern cannot silently drift from its current remediation)."""
    by_id: Dict[str, BacklogItem] = {it.pattern_id: it for it in (existing or [])}
    for p in _patterns_list(payload):
        pid = str(p["pattern_id"])
        fresh = BacklogItem.from_pattern(p)
        if pid in by_id:
            prev = by_id[pid]
            fresh.created = prev.created or fresh.created
            fresh.status = prev.status
            fresh.verification = prev.verification
        fresh.updated = _now()
        by_id[pid] = fresh
    return list(by_id.values())


def _default_runner(argv: List[str], timeout: int = 600) -> Tuple[int, str]:
    """Run a cert argv from repo root; return (exit_code, tail). 'python3 -m pkg' uses this
    interpreter. A timeout is reported as exit 124 (never a spurious pass)."""
    if argv and argv[0] == "python3":
        cmd = [sys.executable] + argv[1:]
    else:
        cmd = [sys.executable] + argv
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or ""))[-600:]
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def verify_item(item: BacklogItem,
                runner: Callable[[List[str]], Tuple[int, str]] = _default_runner) -> BacklogItem:
    """Decide an item's status by RUNNING its cert_required. CERTIFIED iff every runnable cert
    exits 0; NEEDS_WORK iff any runnable cert fails; MANUAL iff none could be resolved to a command."""
    argvs = runnable_certs(item.cert_required)
    results = []
    if not argvs:
        item.status = MANUAL
        item.verification = {"checked_at": _now(), "runnable": 0,
                             "note": "no cert_required resolved to a runnable command"}
        item.updated = _now()
        return item
    all_ok = True
    for argv in argvs:
        rc, tail = runner(argv)
        ok = (rc == 0)
        all_ok = all_ok and ok
        results.append({"cmd": " ".join(argv), "exit": rc, "ok": ok})
    item.status = CERTIFIED if all_ok else NEEDS_WORK
    item.verification = {"checked_at": _now(), "runnable": len(argvs),
                         "all_ok": all_ok, "results": results}
    item.updated = _now()
    return item


def rank(items: List[BacklogItem]) -> List[BacklogItem]:
    """Backlog order: actionable first (NEEDS_WORK, OPEN), then MANUAL, then CERTIFIED; within a
    status, P0 before P1 before P2; ties broken by higher frequency."""
    return sorted(items, key=lambda it: (_STATUS_RANK.get(it.status, 9),
                                         _rc.severity_rank(it.severity),
                                         -int(it.frequency or 0), it.pattern_id))


def stats(items: List[BacklogItem]) -> Dict[str, Any]:
    by_status: Dict[str, int] = {}
    by_sev: Dict[str, int] = {}
    for it in items:
        by_status[it.status] = by_status.get(it.status, 0) + 1
        by_sev[it.severity] = by_sev.get(it.severity, 0) + 1
    return {"total": len(items), "by_status": by_status, "by_severity": by_sev,
            "open_actionable": by_status.get(OPEN, 0) + by_status.get(NEEDS_WORK, 0),
            "certified": by_status.get(CERTIFIED, 0)}


def load_backlog(path: Path = BACKLOG_JSON) -> List[BacklogItem]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return []
    items = data.get("items", data) if isinstance(data, dict) else data
    return [BacklogItem.from_dict(d) for d in (items or []) if isinstance(d, dict)]


def save_backlog(items: List[BacklogItem], path: Path = BACKLOG_JSON) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "6 — Improvement Engine",
        "schema": "work order -> backlog item -> run cert_required -> CERTIFIED | NEEDS_WORK",
        "generated_at": _now(),
        "stats": stats(items),
        "items": [it.to_dict() for it in rank(items)],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_patterns(path: Path = PATTERNS_JSON) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {"patterns": []}


# --------------------------------------------------------------------------------------------
# selftest — hermetic. Proves ingest -> verify (with a FAKE runner: no subprocess, no .anima) ->
# rank -> save/load round-trip, and that status is DECIDED by the cert (CERTIFIED/NEEDS_WORK/MANUAL).
# --------------------------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("improvement_engine — self-improving loop (hermetic)")
    print("=" * 60)

    # a synthetic patterns payload: a P0 that will CERTIFY, a P1 that will FAIL, a P2 descriptive-only
    payload = {"patterns": [
        {"pattern_id": "conversation_repair", "title": "Correction lost", "severity": "P0",
         "frequency": 3, "cert_required": ["conversation_repair killer test", "certify_repair.py"],
         "expected_improvement": {"to": "SUPERSEDED->Atlas"}, "source": "audit:conversation_repair"},
        {"pattern_id": "completeness", "title": "Response stripped", "severity": "P1",
         "frequency": 2, "cert_required": ["scripts/certify_whole_mri.py --gate"], "source": "traces"},
        {"pattern_id": "host_resource_spike", "title": "Host spike", "severity": "P2",
         "frequency": 1, "cert_required": ["anima.host_window probe but unmapped phrase only"],
         "source": "traces"},
    ]}

    items = ingest(payload)
    ck("ingest creates one backlog item per pattern", len(items) == 3)
    ck("all start OPEN", all(it.status == OPEN for it in items))

    # cert resolution
    ck("resolve 'certify_repair.py' -> scripts/certify_repair.py",
       resolve_cert("certify_repair.py") == ["scripts/certify_repair.py"])
    ck("resolve 'scripts/certify_whole_mri.py --gate' keeps flags",
       resolve_cert("scripts/certify_whole_mri.py --gate") == ["scripts/certify_whole_mri.py", "--gate"])
    ck("resolve descriptive-only phrase -> None",
       resolve_cert("anima.host_window probe but unmapped phrase only") is None)
    ck("conversation_repair de-dupes its two cert phrases to ONE command",
       len(runnable_certs(["conversation_repair killer test", "certify_repair.py"])) == 1)

    # FAKE runner: certify_repair passes, certify_whole_mri fails — status decided by the cert
    def fake_runner(argv):
        joined = " ".join(argv)
        if "certify_repair.py" in joined:
            return 0, "CERTIFIED"
        if "certify_whole_mri.py" in joined:
            return 1, "FAIL"
        return 0, ""
    for it in items:
        verify_item(it, runner=fake_runner)
    by_id = {it.pattern_id: it for it in items}
    ck("P0 with a passing cert -> CERTIFIED (loop closed, fix proven)",
       by_id["conversation_repair"].status == CERTIFIED)
    ck("P1 with a failing cert -> NEEDS_WORK (actionable, honest)",
       by_id["completeness"].status == NEEDS_WORK)
    ck("P2 with no runnable cert -> MANUAL", by_id["host_resource_spike"].status == MANUAL)
    ck("verification records the per-cert exit for the CERTIFIED item",
       by_id["conversation_repair"].verification.get("all_ok") is True)

    # ranking: NEEDS_WORK first, CERTIFIED last
    ordered = rank(items)
    ck("rank() puts the actionable NEEDS_WORK item first",
       ordered[0].pattern_id == "completeness")
    ck("rank() puts the CERTIFIED item last", ordered[-1].pattern_id == "conversation_repair")

    # save/load round-trip + re-ingest preserves status & created
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "improvement_backlog.json"
        save_backlog(items, p)
        loaded = load_backlog(p)
        ck("save/load round-trips all items", len(loaded) == 3)
        ck("status survives the round-trip",
           {it.pattern_id: it.status for it in loaded} ==
           {it.pattern_id: it.status for it in items})
        created0 = {it.pattern_id: it.created for it in loaded}
        re_ingested = ingest(payload, existing=loaded)
        ck("re-ingest preserves the original created stamp (history kept)",
           all(it.created == created0[it.pattern_id] for it in re_ingested))
        ck("re-ingest preserves prior CERTIFIED status",
           {it.pattern_id: it.status for it in re_ingested}["conversation_repair"] == CERTIFIED)

    st = stats(items)
    ck("stats counts 1 certified + 1 actionable-open(NEEDS_WORK)",
       st["certified"] == 1 and st["open_actionable"] == 1)

    print("\nIMPROVEMENT ENGINE SELFTEST: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
