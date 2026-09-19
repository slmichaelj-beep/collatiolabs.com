"""whole_mri — Whole-System MRI: UnifiedTrace schema + turn_id + append-only recorder.

This is the PRODUCER layer everything else reads. It is self-contained: no edit to
server.py, mouth.py, host_awareness.py, or any reply-path module is made here — the
owner wires the turn_id propagation separately.

NON-NEGOTIABLES (all enforced in code + selftest):
  1. No trace ships without a turn_id.  assemble() RAISES on blank/missing.
  2. record() REFUSES a trace whose turn_id is missing or that fails validate().
  3. Append-only: a second record() appends; it never truncates or overwrites.
  4. Hermetic: STORE is redirectable; the real .anima is byte-identical before/after.
  5. No raw sensitive host payloads stored in the trace itself.

Storage layout:
  .anima/traces/whole_mri/<name>.jsonl
  One JSON object per line, append-only, survives restart, replayable.

CLI:
  python3 -m anima.whole_mri --selftest
"""

from __future__ import annotations

import json
import os
import re
import secrets
import string
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Store root — module-level, redirectable for tests (mirrors telemetry.STORE /
# reliability.DEFAULT_STORE).  Never cache at call-site; always read STORE.
# ---------------------------------------------------------------------------
STORE = Path(".anima")

SCHEMA_VERSION = 1

# Pattern the turn_id MUST match.
_TURN_ID_RE = re.compile(
    r"^turn_\d{4}_\d{2}_\d{2}_\d{6}_[A-Za-z0-9_\-]{6}$"
)

# Allowed values for input_kind and route (validated but not hard-enforced on unknown values).
_INPUT_KINDS = frozenset({"chat", "host_question", "task", "memory", "source", "unknown"})
_ROUTES      = frozenset({"memory", "lerf", "argus", "llm", "source", "hybrid"})


# ---------------------------------------------------------------------------
# mint_turn_id — one per Vera turn, minted at the top of server._turn.
# Format: turn_<YYYY>_<MM>_<DD>_<HHMMSS>_<rand6>
# rand6 = 6 url-safe characters (A-Za-z0-9_-)
# ---------------------------------------------------------------------------
def mint_turn_id() -> str:
    """Mint a globally-unique turn identifier using the real wall clock.

    Format: ``turn_YYYY_MM_DD_HHMMSS_xxxxxx`` where ``xxxxxx`` is 6 url-safe
    random characters (A-Za-z0-9_-).  The clock component is UTC.

    Minted ONCE per Vera turn at the top of ``server._turn``; every subsystem
    attaches to the same id so the cognitive, host, cost, safety, and quality
    traces for one turn are all correlated.
    """
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y_%m_%d_%H%M%S")
    alphabet = string.ascii_letters + string.digits + "_-"
    rand6 = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"turn_{date_part}_{rand6}"


# ---------------------------------------------------------------------------
# Sub-block dataclasses — one per schema section.  All fields default to None
# so a caller can provide only the fields it has; assemble() fills the rest.
# ---------------------------------------------------------------------------

@dataclass
class VeraBlock:
    capture: Any = None
    memory: Any = None
    lerf: Any = None
    world_model: Any = None
    reality_learning: Any = None
    generation: Any = None
    final_gate: Any = None
    response: Any = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "VeraBlock":
        if not isinstance(d, dict):
            return cls()
        return cls(**{k: d.get(k) for k in (
            "capture", "memory", "lerf", "world_model",
            "reality_learning", "generation", "final_gate", "response"
        )})


@dataclass
class ArgusBlock:
    enabled: bool = False
    capabilities_ok: bool = False
    queries: list = field(default_factory=list)
    host_before: Any = None
    host_during: Any = None
    host_after: Any = None
    shape_delta: Any = None
    blind_spots: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ArgusBlock":
        if not isinstance(d, dict):
            return cls()
        return cls(
            enabled=bool(d.get("enabled", False)),
            capabilities_ok=bool(d.get("capabilities_ok", False)),
            queries=list(d.get("queries") or []),
            host_before=d.get("host_before"),
            host_during=d.get("host_during"),
            host_after=d.get("host_after"),
            shape_delta=d.get("shape_delta"),
            blind_spots=list(d.get("blind_spots") or []),
        )


@dataclass
class QualityBlock:
    grounded: Any = None
    complete: Any = None
    source_labeled: Any = None
    host_labeled: Any = None
    confidence: Any = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "QualityBlock":
        if not isinstance(d, dict):
            return cls()
        return cls(**{k: d.get(k) for k in (
            "grounded", "complete", "source_labeled", "host_labeled", "confidence"
        )})


@dataclass
class CostBlock:
    latency_ms: Any = None
    tokens_in: Any = None
    tokens_out: Any = None
    argus_calls: Any = None
    memory_reads: Any = None
    memory_writes: Any = None
    lerf_objects_used: Any = None
    cpu_delta: Any = None
    memory_delta_mb: Any = None
    disk_io_delta: Any = None
    network_delta: Any = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CostBlock":
        if not isinstance(d, dict):
            return cls()
        return cls(**{k: d.get(k) for k in (
            "latency_ms", "tokens_in", "tokens_out", "argus_calls",
            "memory_reads", "memory_writes", "lerf_objects_used",
            "cpu_delta", "memory_delta_mb", "disk_io_delta", "network_delta"
        )})


@dataclass
class SafetyBlock:
    final_gate_passed: Any = None
    response_complete: Any = None
    identity_mutation: Any = None
    host_action_taken: Any = None
    memory_contamination: Any = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SafetyBlock":
        if not isinstance(d, dict):
            return cls()
        return cls(**{k: d.get(k) for k in (
            "final_gate_passed", "response_complete", "identity_mutation",
            "host_action_taken", "memory_contamination"
        )})


# ---------------------------------------------------------------------------
# UnifiedTrace — the canonical schema.  One instance per Vera turn.
# ---------------------------------------------------------------------------

@dataclass
class UnifiedTrace:
    """The whole-system MRI trace for one Vera turn.

    Schema (mirrors docs/whole_mri_contract.md exactly):
      turn_id, ts, input_kind, route,
      vera   {capture,memory,lerf,world_model,reality_learning,generation,final_gate,response},
      argus  {enabled,capabilities_ok,queries,host_before,host_during,host_after,
              shape_delta,blind_spots},
      quality{grounded,complete,source_labeled,host_labeled,confidence},
      cost   {latency_ms,tokens_in,tokens_out,argus_calls,memory_reads,memory_writes,
              lerf_objects_used,cpu_delta,memory_delta_mb,disk_io_delta,network_delta},
      safety {final_gate_passed,response_complete,identity_mutation,
              host_action_taken,memory_contamination}

    NON-NEGOTIABLE: turn_id must be present and match the format.
    assemble() enforces this at construction time.
    """

    turn_id: str
    ts: str
    input_kind: str = "unknown"
    route: str = "llm"
    vera: VeraBlock = field(default_factory=VeraBlock)
    argus: ArgusBlock = field(default_factory=ArgusBlock)
    quality: QualityBlock = field(default_factory=QualityBlock)
    cost: CostBlock = field(default_factory=CostBlock)
    safety: SafetyBlock = field(default_factory=SafetyBlock)

    # schema version so consumers can gate on it
    v: int = SCHEMA_VERSION

    # -----------------------------------------------------------------------
    def to_dict(self) -> dict:
        """Serialise to a plain dict — JSON-safe with stdlib json."""
        return {
            "v": self.v,
            "turn_id": self.turn_id,
            "ts": self.ts,
            "input_kind": self.input_kind,
            "route": self.route,
            "vera": self.vera.to_dict(),
            "argus": self.argus.to_dict(),
            "quality": self.quality.to_dict(),
            "cost": self.cost.to_dict(),
            "safety": self.safety.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UnifiedTrace":
        """Reconstruct a UnifiedTrace from a plain dict (e.g. a replayed JSONL line)."""
        if not isinstance(d, dict):
            raise ValueError("from_dict requires a dict")
        return cls(
            turn_id=str(d.get("turn_id") or ""),
            ts=str(d.get("ts") or ""),
            input_kind=str(d.get("input_kind") or "unknown"),
            route=str(d.get("route") or "llm"),
            vera=VeraBlock.from_dict(d.get("vera") or {}),
            argus=ArgusBlock.from_dict(d.get("argus") or {}),
            quality=QualityBlock.from_dict(d.get("quality") or {}),
            cost=CostBlock.from_dict(d.get("cost") or {}),
            safety=SafetyBlock.from_dict(d.get("safety") or {}),
            v=int(d.get("v") or SCHEMA_VERSION),
        )

    # -----------------------------------------------------------------------
    def validate(self) -> tuple[bool, list[str]]:
        """Validate the trace against the contract.

        Returns (ok, problems) where ``ok`` is True iff ``problems`` is empty.
        Required checks:
          - turn_id must be present (non-empty string)
          - turn_id must match the format  turn_YYYY_MM_DD_HHMMSS_xxxxxx
          - ts must be a non-empty string
          - input_kind must be a string
          - route must be a string
          - vera/argus/quality/cost/safety must be present as dicts in to_dict()
        """
        problems: list[str] = []

        # turn_id — the non-negotiable
        if not self.turn_id or not isinstance(self.turn_id, str):
            problems.append("turn_id is missing or not a string")
        elif not _TURN_ID_RE.match(self.turn_id):
            problems.append(
                f"turn_id {self.turn_id!r} does not match format "
                "turn_YYYY_MM_DD_HHMMSS_<rand6>"
            )

        # ts
        if not self.ts or not isinstance(self.ts, str):
            problems.append("ts is missing or not a string")

        # input_kind / route — must be strings; warn (not fail) on unknown values
        if not isinstance(self.input_kind, str):
            problems.append("input_kind must be a string")
        if not isinstance(self.route, str):
            problems.append("route must be a string")

        # sub-blocks must be present
        d = self.to_dict()
        for key in ("vera", "argus", "quality", "cost", "safety"):
            if not isinstance(d.get(key), dict):
                problems.append(f"sub-block '{key}' missing or not a dict")

        return (len(problems) == 0), problems


# ---------------------------------------------------------------------------
# assemble — pure builder.  Fills defaults; RAISES if turn_id is missing.
# ---------------------------------------------------------------------------

def assemble(
    *,
    turn_id: str,
    ts: Optional[str] = None,
    input_kind: str = "unknown",
    route: str = "llm",
    vera: Optional[dict] = None,
    argus: Optional[dict] = None,
    quality: Optional[dict] = None,
    cost: Optional[dict] = None,
    safety: Optional[dict] = None,
) -> UnifiedTrace:
    """Build a UnifiedTrace from the parts a turn has.

    This is a PURE builder: it does not touch disk and has no side-effects.
    Sub-blocks default to empty VeraBlock/ArgusBlock/etc. so a caller provides
    only the blocks it has; missing keys inside a block default to None.

    RAISES ValueError if turn_id is missing or blank — the non-negotiable:
    "No turn_id = not observable."

    ``ts`` defaults to the current UTC time in ISO8601-Z format if omitted.
    """
    # NON-NEGOTIABLE: turn_id must be present and non-blank
    if not turn_id or not isinstance(turn_id, str) or not turn_id.strip():
        raise ValueError(
            "turn_id is required and must be non-blank — "
            "No turn_id = not observable (whole_mri_contract.md §NON-NEGOTIABLES #7)"
        )

    if ts is None:
        ts = _iso_now()

    return UnifiedTrace(
        turn_id=turn_id,
        ts=ts,
        input_kind=input_kind if isinstance(input_kind, str) else "unknown",
        route=route if isinstance(route, str) else "llm",
        vera=VeraBlock.from_dict(vera or {}),
        argus=ArgusBlock.from_dict(argus or {}),
        quality=QualityBlock.from_dict(quality or {}),
        cost=CostBlock.from_dict(cost or {}),
        safety=SafetyBlock.from_dict(safety or {}),
    )


def _iso_now() -> str:
    """Current UTC time as ISO8601-Z (matches the package-wide convention)."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Append-only JSONL recorder
# Storage: STORE/traces/whole_mri/<name>.jsonl
# ---------------------------------------------------------------------------

def _trace_dir() -> Path:
    return STORE / "traces" / "whole_mri"


def _trace_path(name: str) -> Path:
    return _trace_dir() / f"{name}.jsonl"


def record(name: str, trace: UnifiedTrace) -> str:
    """Append ONE trace as a single JSON line to the named JSONL file.

    Rules:
      - REFUSES to write a trace whose turn_id is missing / fails validate().
      - Opens with O_APPEND so a crash mid-write never truncates prior traces.
      - fsync()s before closing so the line is durable.
      - Stores NO raw sensitive host payloads — the trace fields are the record.

    Returns the absolute path written.

    Raises ValueError when the trace is invalid (turn_id missing or malformed).
    """
    # Guard 1: turn_id must exist and be non-blank
    if not getattr(trace, "turn_id", None) or not trace.turn_id.strip():
        raise ValueError(
            "record() refused: trace has no turn_id — "
            "No turn_id = not observable"
        )

    # Guard 2: full validation
    ok, problems = trace.validate()
    if not ok:
        raise ValueError(
            f"record() refused: trace failed validate(): {problems}"
        )

    # Serialise
    try:
        line = json.dumps(trace.to_dict(), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"record() refused: trace is not JSON-safe: {exc}") from exc

    # Write — O_APPEND guarantees every call extends the file; never truncates
    path = _trace_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (line + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)

    return str(path.resolve())


def _read_all(name: str) -> list[dict]:
    """Read every committed trace for ``name``, oldest to newest.  A malformed
    line is skipped, never fatal — mirrors telemetry._read."""
    rows: list[dict] = []
    p = _trace_path(name)
    if not p.exists():
        return rows
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                pass
    except Exception:
        pass
    return rows


def last(name: str) -> Optional[dict]:
    """Return the most recently recorded trace dict for ``name``, or None."""
    rows = _read_all(name)
    return rows[-1] if rows else None


def by_turn_id(name: str, turn_id: str) -> Optional[dict]:
    """Return the trace dict whose turn_id matches (most recent if somehow
    duplicated), or None.  Mirrors telemetry.replay."""
    found = None
    for row in _read_all(name):
        if row.get("turn_id") == turn_id:
            found = row
    return found


def all(name: str, limit: Optional[int] = None) -> list[dict]:
    """Return all trace dicts for ``name``, oldest to newest.

    ``limit``, if given, caps the number of returned rows (from the newest end).
    """
    rows = _read_all(name)
    if limit is not None and limit > 0:
        rows = rows[-limit:]
    return rows


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _selftest() -> int:  # pragma: no cover
    """Hermetic selftest — ALL assertions run against a temp dir; the real
    .anima is byte-identical before and after.

    Checks:
      1. mint_turn_id() produces the right format
      2. assemble() builds a trace with all sub-blocks
      3. assemble("") raises (turn_id required)
      4. assemble(turn_id=<valid>) + record() writes to disk
      5. record() on a trace with no turn_id raises
      6. Append-only: two records → two lines (never overwrites)
      7. last() / by_turn_id() / all() round-trip correctly
      8. validate() passes on a well-formed trace
      9. validate() catches a missing turn_id
      10. The REAL .anima is byte-identical (hermetic)
    """
    import hashlib
    import shutil
    import sys
    import tempfile

    global STORE

    fails: list[str] = []

    def ok(label: str, cond: bool) -> None:
        status = "  ok   " if cond else "  FAIL "
        print(status + label)
        if not cond:
            fails.append(label)

    print("whole_mri self-test")
    print()

    # ------------------------------------------------------------------ #
    # fingerprint of the REAL .anima BEFORE the test (hermetic proof)
    # ------------------------------------------------------------------ #
    real_store = Path(".anima")

    def _dir_fingerprint(p: Path) -> str:
        """SHA-256 of every byte in every file, sorted by path."""
        h = hashlib.sha256()
        if not p.exists():
            return h.hexdigest()
        for fp in sorted(p.rglob("*")):
            if fp.is_file():
                h.update(fp.read_bytes())
        return h.hexdigest()

    fingerprint_before = _dir_fingerprint(real_store)

    # ------------------------------------------------------------------ #
    # redirect STORE to a temp dir
    # ------------------------------------------------------------------ #
    tmp_dir = tempfile.mkdtemp(prefix="whole_mri_selftest_")
    real_store_path = STORE
    STORE = Path(tmp_dir) / ".anima"

    try:
        # ---- 1. mint_turn_id format ------------------------------------
        tid = mint_turn_id()
        ok("mint_turn_id() matches format",
           bool(_TURN_ID_RE.match(tid)) and tid.startswith("turn_"))

        # ---- 2. assemble builds all sub-blocks -------------------------
        tr = assemble(
            turn_id=tid,
            input_kind="chat",
            route="memory",
            vera={"capture": "ok", "generation": "done"},
            argus={"enabled": True, "capabilities_ok": True, "queries": ["cpu"]},
            quality={"grounded": True, "confidence": 0.9},
            cost={"latency_ms": 120, "tokens_in": 50, "tokens_out": 30},
            safety={"final_gate_passed": True, "response_complete": True},
        )
        ok("assemble() returns a UnifiedTrace", isinstance(tr, UnifiedTrace))
        ok("assemble().turn_id matches", tr.turn_id == tid)
        ok("assemble().vera sub-block present", isinstance(tr.vera, VeraBlock))
        ok("assemble().vera.capture set", tr.vera.capture == "ok")
        ok("assemble().argus.enabled set", tr.argus.enabled is True)
        ok("assemble().quality.confidence set", tr.quality.confidence == 0.9)
        ok("assemble().cost.latency_ms set", tr.cost.latency_ms == 120)
        ok("assemble().safety.final_gate_passed set", tr.safety.final_gate_passed is True)

        # ---- 3. assemble("") raises ------------------------------------
        raised = False
        try:
            assemble(turn_id="")
        except ValueError:
            raised = True
        ok("assemble('') raises ValueError", raised)

        raised_none = False
        try:
            assemble(turn_id=None)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            raised_none = True
        ok("assemble(turn_id=None) raises", raised_none)

        raised_ws = False
        try:
            assemble(turn_id="   ")
        except ValueError:
            raised_ws = True
        ok("assemble(turn_id='   ') raises (blank)", raised_ws)

        # ---- 4. validate() on well-formed trace ------------------------
        valid_ok, valid_problems = tr.validate()
        ok("validate() passes on well-formed trace", valid_ok)
        ok("validate() returns no problems", valid_problems == [])

        # ---- 5. validate() catches missing turn_id ---------------------
        bad = UnifiedTrace(turn_id="", ts=_iso_now())
        bad_ok, bad_probs = bad.validate()
        ok("validate() fails on empty turn_id", not bad_ok)
        ok("validate() reports a problem for empty turn_id", len(bad_probs) > 0)

        bad2 = UnifiedTrace(turn_id="not_a_valid_id", ts=_iso_now())
        bad2_ok, bad2_probs = bad2.validate()
        ok("validate() fails on malformed turn_id", not bad2_ok)

        # ---- 6. record() writes to disk --------------------------------
        path_written = record("selftest", tr)
        ok("record() returns a path string", isinstance(path_written, str))
        trace_file = Path(path_written)
        ok("record() created the JSONL file", trace_file.exists())
        lines = trace_file.read_text(encoding="utf-8").splitlines()
        ok("record() wrote exactly 1 line", len(lines) == 1)
        parsed = json.loads(lines[0])
        ok("line is valid JSON with turn_id", parsed.get("turn_id") == tid)

        # ---- 7. record() on a no-turn_id trace raises ------------------
        no_tid_trace = UnifiedTrace(turn_id="", ts=_iso_now())
        raised_rec = False
        try:
            record("selftest", no_tid_trace)
        except ValueError:
            raised_rec = True
        ok("record() on empty-turn_id trace raises ValueError", raised_rec)

        # ---- 8. Append-only: second record appends, never overwrites ---
        tid2 = mint_turn_id()
        tr2 = assemble(turn_id=tid2, input_kind="task", route="lerf")
        record("selftest", tr2)
        lines2 = trace_file.read_text(encoding="utf-8").splitlines()
        ok("after 2nd record(), file has 2 lines (append-only)", len(lines2) == 2)
        # original first line must be byte-identical
        ok("first line unchanged after second write (no overwrite)", lines2[0] == lines[0])

        # ---- 9. last() / by_turn_id() / all() round-trip --------------
        got_last = last("selftest")
        ok("last() returns the 2nd trace", got_last is not None and got_last.get("turn_id") == tid2)

        got_by_id = by_turn_id("selftest", tid)
        ok("by_turn_id() returns the 1st trace by its turn_id",
           got_by_id is not None and got_by_id.get("turn_id") == tid)

        got_all = all("selftest")
        ok("all() returns 2 traces", len(got_all) == 2)
        ok("all() order is oldest-first", got_all[0].get("turn_id") == tid)

        got_limited = all("selftest", limit=1)
        ok("all(limit=1) returns only the newest", len(got_limited) == 1 and
           got_limited[0].get("turn_id") == tid2)

        # ---- 10. from_dict / to_dict round-trip ------------------------
        d = tr.to_dict()
        tr_rt = UnifiedTrace.from_dict(d)
        ok("to_dict/from_dict round-trip: turn_id", tr_rt.turn_id == tr.turn_id)
        ok("to_dict/from_dict round-trip: argus.queries",
           tr_rt.argus.queries == tr.argus.queries)
        ok("to_dict/from_dict round-trip: cost.latency_ms",
           tr_rt.cost.latency_ms == tr.cost.latency_ms)

        # ---- 11. non-existent name returns sensible defaults -----------
        ok("last() on unknown name returns None", last("__no_such_name__") is None)
        ok("by_turn_id() on unknown name returns None",
           by_turn_id("__no_such_name__", tid) is None)
        ok("all() on unknown name returns []", all("__no_such_name__") == [])

        # ---- 12. record() on invalid trace raises ----------------------
        bad_trace = UnifiedTrace(turn_id="bad_format_no_prefix", ts=_iso_now())
        raised_bad = False
        try:
            record("selftest", bad_trace)
        except ValueError:
            raised_bad = True
        ok("record() refuses a trace that fails validate()", raised_bad)

    finally:
        # Restore STORE regardless
        STORE = real_store_path
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------ #
    # HERMETIC: fingerprint of the REAL .anima must be byte-identical
    # ------------------------------------------------------------------ #
    fingerprint_after = _dir_fingerprint(real_store)
    ok("REAL .anima is byte-identical before/after (hermetic)",
       fingerprint_before == fingerprint_after)
    if fingerprint_before == fingerprint_after:
        print()
        print(f"  byte-identical proof: SHA-256 = {fingerprint_before}")

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("ALL WHOLE_MRI SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv or len(sys.argv) == 1:
        raise SystemExit(_selftest())
    print("usage: python3 -m anima.whole_mri --selftest")
