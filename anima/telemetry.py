"""telemetry — the substrate's passive flight recorder.

Telemetry watches a turn happen and writes down what happened. It is the third
load-bearing seam of the moonshot substrate, stated once in ``event_bus`` and
enforced here:

  * **Passive peer subscriber.** ``telemetry.attach(bus, name)`` wires one recorder
    to the very same events the Coordinator reads — QUESTION / OBSERVATION /
    DECISION / RESPONSE — plus the bus's error sink. It is NEVER in the request
    path: it only ever *appends* to its own buffer, never blocks, never speaks back
    onto the bus. Exactly like ``metrics._append``, a telemetry failure can never
    slow or break a turn — every public method swallows its own exceptions.

  * **One trace per turn, append-only.** ``begin(turn_id)`` opens a trace;
    OBSERVATION events fold in provenance (which organ contributed, which Memory id,
    the organ's weight, its note); ``note_decision(turn_id, decision)`` records the
    verdict (contributing organs, memory ids used, escalation, model); ``commit``
    (or the RESPONSE event) flushes the closed trace as ONE line onto
    ``.anima/{name}.telemetry.jsonl`` — append-only, the same jsonl posture
    ``metrics`` uses, gitignored and machine-local.

  * **Replayable.** ``replay(name, turn_id)`` reads the log back and returns the
    exact trace dict that was committed, so a turn can be reconstructed after the
    fact: the question asked, every observation seen (with its memory id and
    confidence), the decision reached, and whether it escalated. ``last(name)`` and
    ``traces(name)`` are the bulk readers.

Anchored to existing conventions: ``STORE = Path(".anima")``; ``_now()`` ISO8601-`Z`
timestamps reused from ``memory_lirf`` (byte-identical fallback in isolation); the
append/read pair mirrors ``metrics._append`` / ``metrics._read`` verbatim, including
the swallow-everything guard. A trace is a plain dict of plain values, so it
serialises with stdlib json and is diffable.

Why a buffer keyed by ``turn_id`` and not a single "current" trace: the bus fans out
concurrently and multiple turns can be in flight, so each turn's evidence must
accumulate independently. The buffer holds only OPEN turns; ``commit`` flushes and
evicts, so a long-running process doesn't grow unboundedly.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

# Reuse the ledger's canonical timestamp so a telemetry line stamps the SAME
# ISO8601-Z shape as every other .anima artifact. Byte-identical fallback when the
# module is exercised in isolation (e.g. python3 anima/telemetry.py --selftest).
try:  # pragma: no cover - import wiring
    from .memory_lirf import _now as _now
except Exception:  # pragma: no cover - isolation fallback
    from datetime import datetime, timezone

    def _now() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )


# Topic is needed to route the four event kinds. Prefer the real enum; fall back to
# the same string values so attach() works even if event_bus isn't importable.
try:  # pragma: no cover - import wiring
    from .event_bus import Topic
except Exception:  # pragma: no cover - isolation fallback
    from enum import Enum

    class Topic(str, Enum):
        QUESTION = "question"
        OBSERVATION = "observation"
        DECISION = "decision"
        RESPONSE = "response"


STORE = Path(".anima")
SCHEMA_VERSION = 1


def _path(name: str) -> Path:
    return STORE / f"{name}.telemetry.jsonl"


def _append(name: str, row: dict) -> None:
    """Append one committed trace as a single jsonl line. Mirrors metrics._append
    exactly — including the blanket guard: a diagnostic must NEVER break a turn."""
    try:
        STORE.mkdir(exist_ok=True)
        with open(_path(name), "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass  # a diagnostic must NEVER break a turn


def _read(name: str) -> list:
    """Read every committed trace back. Mirrors metrics._read: a malformed line is
    skipped, never fatal."""
    rows, p = [], _path(name)
    if p.exists():
        try:
            for line in p.read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
        except Exception:
            pass
    return rows


# ---------------------------------------------------------------------------
# Telemetry — one instance per attached creature. Holds the open-turn buffer.
# ---------------------------------------------------------------------------
class Telemetry:
    """A passive recorder. One per creature, attached to a bus.

    Every method is best-effort: it captures its own exceptions so a recording
    failure can never propagate into a turn. The bus delivers events to ``_on_event``
    concurrently with the Coordinator's own consumption — telemetry sees exactly what
    the Coordinator sees, but only ever writes to its own buffer.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        # turn_id -> open trace dict. Only OPEN turns live here; commit evicts.
        self._open: dict[str, dict] = {}
        # Guards the buffer: the bus fans out concurrently, so two coroutines may
        # touch different turns at once. A plain lock keeps the dict consistent.
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    def begin(self, turn_id: str, question: Any = None) -> None:
        """Open a trace for ``turn_id``. Idempotent: re-opening keeps the first one.

        ``question`` (a ``Question``-like object or None) is recorded by value — its
        text/name/context — so the replayed trace shows what was actually asked
        without holding a reference to a live object.
        """
        try:
            with self._lock:
                if turn_id in self._open:
                    return
                self._open[turn_id] = {
                    "v": SCHEMA_VERSION,
                    "turn_id": turn_id,
                    "name": self.name,
                    "opened": _now(),
                    "question": self._render_question(question),
                    "observations": [],   # provenance, one per OBSERVATION seen
                    "decision": None,      # filled by note_decision
                    "committed": None,     # filled by commit
                    "errors": [],          # any handler exceptions the bus surfaced
                }
        except Exception:
            pass

    def note_observation(self, turn_id: str, observation: Any) -> None:
        """Fold one observation's provenance into the open trace. The recorded shape
        is deliberately compact: organ, memory id, the memory's own confidence, the
        organ's weight, and its note — the minimum to reconstruct *who said what,
        and how strongly*. Falls back gracefully on a sparse/partial observation."""
        try:
            organ = getattr(observation, "organ", "")
            mem = getattr(observation, "memory", None)
            mid = mem.get("id") if isinstance(mem, dict) else None
            conf = mem.get("confidence") if isinstance(mem, dict) else None
            lirf = mem.get("lirf") if isinstance(mem, dict) else None
            entry = {
                "organ": organ,
                "memory_id": mid,
                "confidence": conf,
                "weight": getattr(observation, "weight", None),
                "note": getattr(observation, "note", ""),
                "lirf": lirf,
            }
            with self._lock:
                tr = self._open.get(turn_id)
                if tr is not None:
                    tr["observations"].append(entry)
        except Exception:
            pass

    def note_decision(self, turn_id: str, decision: Any) -> None:
        """Record the Coordinator's verdict on the open trace: the model chosen, the
        organs that actually contributed, the memory ids used, and whether the turn
        escalated. ``escalated`` is the boolean the replay can assert on directly."""
        try:
            esc = getattr(decision, "escalation", "") or ""
            entry = {
                "model": getattr(decision, "model", ""),
                "contributing_organs": list(getattr(decision, "contributing_organs", []) or []),
                "memory_ids": list(getattr(decision, "memory_ids", []) or []),
                "escalation": esc,
                "escalated": bool(esc),
                "answer_plan": getattr(decision, "answer_plan", ""),
            }
            with self._lock:
                tr = self._open.get(turn_id)
                if tr is not None:
                    tr["decision"] = entry
        except Exception:
            pass

    def note_error(self, turn_id: str, exc: BaseException) -> None:
        """Record a handler exception the bus surfaced for this turn. Diagnostic
        only — the bus has already kept the turn alive; this just leaves a mark."""
        try:
            with self._lock:
                tr = self._open.get(turn_id)
                if tr is not None:
                    tr["errors"].append({"type": type(exc).__name__, "msg": str(exc)})
        except Exception:
            pass

    def commit(self, turn_id: str) -> Optional[dict]:
        """Close and flush the trace for ``turn_id``: stamp ``committed``, append it
        as ONE jsonl line, evict it from the open buffer, and return the committed
        dict (or None if there was nothing open). Append-only — never rewrites a
        prior line. Safe to call twice; the second call is a no-op returning None."""
        try:
            with self._lock:
                tr = self._open.pop(turn_id, None)
            if tr is None:
                return None
            tr["committed"] = _now()
            _append(self.name, tr)
            return tr
        except Exception:
            return None

    # -- the passive subscriber + error sink wired by attach() -------------
    async def _on_event(self, event: Any) -> None:
        """The single coroutine the bus delivers EVERY subscribed topic to. Pure
        recording, no I/O on the hot path except the commit flush on RESPONSE. Never
        raises — every branch is inside the methods' own guards."""
        try:
            topic = getattr(event, "topic", None)
            turn_id = getattr(event, "turn_id", "")
            payload = getattr(event, "payload", None)
            if topic == Topic.QUESTION:
                self.begin(turn_id, payload)
            elif topic == Topic.OBSERVATION:
                # An observation can arrive before QUESTION was seen in odd orderings;
                # open a trace defensively so nothing is dropped.
                with self._lock:
                    have = turn_id in self._open
                if not have:
                    self.begin(turn_id, None)
                self.note_observation(turn_id, payload)
            elif topic == Topic.DECISION:
                self.note_decision(turn_id, payload)
            elif topic == Topic.RESPONSE:
                self.commit(turn_id)
        except Exception:
            pass  # a diagnostic must NEVER break a turn

    async def _on_error(self, event: Any, exc: BaseException) -> None:
        """Bus error-sink callback: a handler raised, the bus kept the turn alive,
        and routes the exception here. Record it against the turn; never re-raise."""
        try:
            self.note_error(getattr(event, "turn_id", ""), exc)
        except Exception:
            pass

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _render_question(question: Any) -> Optional[dict]:
        if question is None:
            return None
        if isinstance(question, dict):
            return {
                "text": question.get("text", ""),
                "name": question.get("name", ""),
                "context": question.get("context", {}),
            }
        return {
            "text": getattr(question, "text", ""),
            "name": getattr(question, "name", ""),
            "context": dict(getattr(question, "context", {}) or {}),
        }


# ---------------------------------------------------------------------------
# Module-level surface — the contract the design states (telemetry.attach, .begin,
# .note_decision, .commit, .replay). attach() returns the Telemetry so callers can
# also drive begin/note_decision/commit directly (e.g. the Coordinator path that
# decides in code, off the bus).
# ---------------------------------------------------------------------------
def attach(bus: Any, name: str) -> Telemetry:
    """Wire a fresh ``Telemetry`` to ``bus`` as a passive peer subscriber.

    Subscribes one recorder to all four topics and installs it as the bus's error
    sink, so it sees the very same events the Coordinator reads — and any handler
    exception the bus surfaces — without ever sitting in the request path. Returns
    the recorder. Idempotent per (bus, topic, handler) because EventBus.subscribe
    de-dupes, but a second attach() makes a NEW recorder; attach once per turn-loop.
    """
    t = Telemetry(name)
    try:
        for topic in (Topic.QUESTION, Topic.OBSERVATION, Topic.DECISION, Topic.RESPONSE):
            bus.subscribe(topic, t._on_event)
        if hasattr(bus, "set_error_sink"):
            bus.set_error_sink(t._on_error)
    except Exception:
        pass
    return t


def replay(name: str, turn_id: str) -> Optional[dict]:
    """Reconstruct one committed turn from the on-disk log. Returns the exact trace
    dict that was flushed (most recent if a turn_id somehow recurs), or None if no
    such turn was ever committed. This is the replayability guarantee: question →
    observations → decision → escalation, all readable after the fact."""
    found = None
    for row in _read(name):
        if isinstance(row, dict) and row.get("turn_id") == turn_id:
            found = row
    return found


def bus_traces(name: str) -> list:
    """Every committed BUS trace for ``name``, oldest→newest (append order).

    Renamed from ``traces`` so the richer MRI ``traces`` (defined later, the live
    reader the Viewer uses) can own that name without shadowing this one silently.
    The legacy bus path reads via ``replay`` / ``last`` / this; nothing external
    referenced the old ``traces`` name."""
    return [r for r in _read(name) if isinstance(r, dict)]


def last(name: str) -> Optional[dict]:
    """The most recently committed BUS trace, or None. Reads the bus log directly
    (``_read``) so it is independent of the later MRI ``traces`` definition —
    ``certify.py``'s replayability check depends on this staying the bus reader."""
    rows = bus_traces(name)
    return rows[-1] if rows else None


_RECORDERS: dict = {}


def get(name: str) -> Telemetry:
    """Singleton recorder for the DIRECT (off-bus) turn-loop path: the live server
    decides in code (no bus wired into the turn yet), so it drives begin/note_decision/
    commit on one persistent recorder per creature. When organs move onto the bus,
    switch to attach(bus, name) — same Telemetry, same on-disk trace."""
    r = _RECORDERS.get(name)
    if r is None:
        r = _RECORDERS[name] = Telemetry(name)
    return r


# ===========================================================================
# THE MRI RECORDER — total turn introspection.
#
# The Telemetry above is the lean bus recorder: question -> observations ->
# decision, one compact line. The MRI is its richer sibling for the DIRECT turn
# path (``server._turn``): it films EVERY stage of one turn as an ordered strip of
# "frames", each with its input shape, structured output, latency, what it DROPPED,
# its confidence, and a note — plus the shape transformations across organ
# boundaries and the alternatives a stage rejected. "If we can see it, we can
# understand it."
#
# Same posture as everything else in this file and in ``metrics``:
#   * PASSIVE — it only ever appends; it never speaks back into a turn.
#   * GUARDED — every public method swallows its own exceptions, so a recorder
#     failure can NEVER change a reply, break a turn, or even be noticed by it.
#   * APPEND-ONLY — a committed trace is one jsonl line on
#     ``.anima/{name}.mri.jsonl``, gitignored and machine-local, read back
#     verbatim by ``trace`` / ``last_trace`` / ``traces`` (the Viewer's input).
#
# THE PER-TURN SCHEMA (one JSON object per turn, the hard contract the Viewer
# reads — keep it EXACTLY):
#   {
#     "v": <schema version>, "kind": "mri",
#     "turn_id", "name", "at" (epoch seconds, float), "user_text", "reply",
#     "total_ms" (float),
#     "stages": [
#       {"stage": <name>, "t_ms": <float latency of this stage>,
#        "in_shape": <brief dict/str describing the input shape>,
#        "out": <the stage's structured output>,
#        "dropped": [<things this stage discarded>],
#        "confidence": <0..1 or null>, "note": <str>}
#     ],
#     "shapes": [
#       {"boundary": "<src>-><dst>", "received": <shape>, "expected": <shape>,
#        "transformation": <str>, "loss": [<dropped>]}
#     ],
#     "alternatives": [
#       {"decision": <str>, "selected": <str>,
#        "rejected": [{"option": <str>, "reason": <str>}]}
#     ]
#   }
#
# REQUIRED stage names (capture each that runs; skip-with-note if N/A):
#   perception · heart · capture · route · bind · situation · meaning ·
#   curiosity · prompt · generate · verify
# ===========================================================================

MRI_SCHEMA_VERSION = 1

# The canonical ordered stage names — the "frames" of the movie, in turn order.
# The Viewer can rely on this vocabulary; a stage not in this list is still
# accepted (forward-compatible), it just isn't one of the documented frames.
MRI_STAGES = (
    "perception", "heart", "capture", "route", "bind",
    "situation", "meaning", "curiosity", "prompt", "generate", "verify",
)


def _mri_path(name: str) -> Path:
    return STORE / f"{name}.mri.jsonl"


def _jsonable(obj: Any, _depth: int = 0):
    """Best-effort coerce an arbitrary stage output into something json.dumps can
    serialise WITHOUT ever raising. Numbers/str/bool/None pass through; dict/list
    recurse (bounded depth + width so a pathological structure can't blow up the
    recorder); numpy scalars/arrays degrade to floats/lists; everything else falls
    back to a short ``repr``. This is what lets a stage hand us its native object
    and trust the MRI to store *something* faithful rather than crash."""
    try:
        if obj is None or isinstance(obj, (bool, int, float, str)):
            # guard against NaN/Inf which are not valid JSON
            if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
                return None
            return obj
        if _depth >= 6:
            return repr(obj)[:200]
        if isinstance(obj, dict):
            out = {}
            for i, (k, v) in enumerate(obj.items()):
                if i >= 80:                       # width cap — never store an unbounded dict
                    out["…"] = f"+{len(obj) - i} more"
                    break
                out[str(k)] = _jsonable(v, _depth + 1)
            return out
        if isinstance(obj, (list, tuple, set)):
            seq = list(obj)
            out = [_jsonable(v, _depth + 1) for v in seq[:120]]   # width cap
            if len(seq) > 120:
                out.append(f"…+{len(seq) - 120} more")
            return out
        # numpy scalar / array, or anything exposing tolist()/item()
        if hasattr(obj, "tolist"):
            try:
                return _jsonable(obj.tolist(), _depth + 1)
            except Exception:
                pass
        if hasattr(obj, "item"):
            try:
                return _jsonable(obj.item(), _depth + 1)
            except Exception:
                pass
        # dataclass / simple object — fold its public attributes
        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict) and d:
            return _jsonable({k: v for k, v in d.items() if not k.startswith("_")}, _depth + 1)
        return repr(obj)[:200]
    except Exception:
        try:
            return repr(obj)[:120]
        except Exception:
            return "<unserialisable>"


class MRITrace:
    """One turn's complete introspective trace — the film of a single exchange.

    Build it imperatively as the turn runs:

        tr = telemetry.open_trace(name, turn_id, user_text)
        tr.stage("perception", t_ms=..., in_shape=..., out=..., dropped=..., confidence=...)
        ...
        tr.shape("perception->heart", received=..., expected=..., transformation=..., loss=...)
        tr.alternative("curiosity:which gap to ask", selected="dog_name", rejected=[...])
        tr.commit(reply=..., total_ms=...)

    Every method is best-effort and append-only to the in-memory object; ``commit``
    flushes ONE jsonl line and is the only disk touch. Nothing here can raise into a
    turn — the whole point is that the camera never trips the actor."""

    def __init__(self, name: str, turn_id: str, user_text: str = "") -> None:
        self.name = name
        self.turn_id = turn_id
        self._committed = False
        self._lock = threading.Lock()
        self.doc: dict = {
            "v": MRI_SCHEMA_VERSION,
            "kind": "mri",
            "turn_id": turn_id,
            "name": name,
            "at": None,                 # epoch seconds, stamped at commit
            "user_text": str(user_text or "")[:4000],
            "reply": None,
            "total_ms": None,
            "stages": [],
            "shapes": [],
            "alternatives": [],
        }
        try:
            import time as _t
            self.doc["at"] = _t.time()
        except Exception:
            pass

    # -- a stage frame -----------------------------------------------------
    def stage(self, name: str, *, t_ms: Any = None, in_shape: Any = None,
              out: Any = None, dropped: Any = None, confidence: Any = None,
              note: str = "") -> "MRITrace":
        """Append one ordered stage frame. ``out`` is coerced json-safe; ``dropped``
        is the list of things this stage discarded (the conservation ledger of a turn);
        ``confidence`` is a 0..1 score or None; ``note`` is freeform (use it to record
        WHY a stage was skipped — 'N/A: cloud brain', etc.)."""
        try:
            frame = {
                "stage": str(name),
                "t_ms": _round_ms(t_ms),
                "in_shape": _jsonable(in_shape),
                "out": _jsonable(out),
                "dropped": _as_list(dropped),
                "confidence": _conf(confidence),
                "note": str(note or "")[:600],
            }
            with self._lock:
                self.doc["stages"].append(frame)
        except Exception:
            pass
        return self

    # -- a shape transformation across an organ boundary -------------------
    def shape(self, boundary: str, *, received: Any = None, expected: Any = None,
              transformation: str = "", loss: Any = None) -> "MRITrace":
        """Record what crossed one boundary ('perception->heart'): the shape received,
        the shape expected, a one-line description of the transformation, and the
        ``loss`` (fields dropped on the way through). This is where shape-mismatch and
        silent data loss become visible."""
        try:
            entry = {
                "boundary": str(boundary),
                "received": _jsonable(received),
                "expected": _jsonable(expected),
                "transformation": str(transformation or "")[:300],
                "loss": _as_list(loss),
            }
            with self._lock:
                self.doc["shapes"].append(entry)
        except Exception:
            pass
        return self

    # -- a decision and the roads not taken --------------------------------
    def alternative(self, decision: str, *, selected: Any = None,
                    rejected: Any = None) -> "MRITrace":
        """Record a branch point: the ``decision`` made, what was ``selected``, and the
        ``rejected`` options each with a reason. ``rejected`` accepts a list of
        ``{"option":..., "reason":...}`` dicts (other shapes are coerced best-effort)."""
        try:
            rej = []
            for r in (rejected or []):
                if isinstance(r, dict):
                    rej.append({"option": _jsonable(r.get("option")),
                                "reason": str(r.get("reason", ""))[:300]})
                else:
                    rej.append({"option": _jsonable(r), "reason": ""})
            entry = {
                "decision": str(decision),
                "selected": _jsonable(selected),
                "rejected": rej,
            }
            with self._lock:
                self.doc["alternatives"].append(entry)
        except Exception:
            pass
        return self

    # -- close + flush -----------------------------------------------------
    def commit(self, *, reply: Any = None, total_ms: Any = None) -> Optional[dict]:
        """Stamp the reply + total latency and append the whole trace as ONE jsonl line
        to ``.anima/{name}.mri.jsonl``. Append-only; idempotent (a second call is a
        no-op returning None). Returns the committed doc, or None on any failure."""
        try:
            with self._lock:
                if self._committed:
                    return None
                self._committed = True
                if reply is not None:
                    self.doc["reply"] = str(reply)[:8000]
                self.doc["total_ms"] = _round_ms(total_ms)
                if self.doc.get("at") is None:
                    try:
                        import time as _t
                        self.doc["at"] = _t.time()
                    except Exception:
                        pass
                doc = self.doc
            _append_mri(self.name, doc)
            return doc
        except Exception:
            return None


# -- a no-op trace so a guarded call site never has to None-check ------------
class _NullTrace(MRITrace):
    """Returned when even opening a trace failed. Every method is inherited but the
    underlying doc append is harmless; commit writes nothing because the parent's
    guard short-circuits. Keeps ``_turn`` free of ``if tr is not None`` clutter."""

    def commit(self, *, reply: Any = None, total_ms: Any = None) -> Optional[dict]:
        return None


def _round_ms(v: Any) -> Any:
    try:
        if v is None:
            return None
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):   # NaN / Inf are not valid JSON
            return None
        return round(f, 3)
    except Exception:
        return None


def _conf(v: Any) -> Any:
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:                      # NaN
            return None
        return max(0.0, min(1.0, f))
    except Exception:
        return None


def _as_list(v: Any) -> list:
    try:
        if v is None:
            return []
        if isinstance(v, (list, tuple, set)):
            return [_jsonable(x) for x in list(v)[:200]]
        return [_jsonable(v)]
    except Exception:
        return []


def _is_json_safe(obj: Any) -> bool:
    """True iff ``obj`` serialises with stdlib json and no fallback. Used by the
    self-test to prove a committed trace is the Viewer-ready, lossless JSON the
    contract promises (not something only ``default=`` rescued)."""
    try:
        json.dumps(obj, allow_nan=False)
        return True
    except Exception:
        return False


def _append_mri(name: str, row: dict) -> None:
    """Append one committed MRI trace as a single jsonl line. Mirrors ``_append``
    exactly — including the blanket guard: the camera must NEVER break the turn. Uses
    ``default=str`` as a final serialisation backstop so an exotic value that slipped
    past ``_jsonable`` still can't raise."""
    try:
        STORE.mkdir(exist_ok=True)
        line = json.dumps(row, default=lambda o: repr(o)[:120])
        with open(_mri_path(name), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _read_mri(name: str) -> list:
    """Read every committed MRI trace back. Mirrors ``_read``: a malformed line is
    skipped, never fatal."""
    rows, p = [], _mri_path(name)
    if p.exists():
        try:
            for line in p.read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
        except Exception:
            pass
    return rows


def open_trace(name: str, turn_id: str, user_text: str = "") -> MRITrace:
    """Open a fresh MRI trace for one turn. ALWAYS returns a usable trace object (a
    ``_NullTrace`` if construction somehow fails), so a call site never has to guard
    the handle itself — only the eventual ``commit`` touches disk. The turn drives
    ``.stage/.shape/.alternative`` on it as each stage runs, then ``.commit``."""
    try:
        return MRITrace(name, turn_id, user_text)
    except Exception:
        try:
            return _NullTrace(name, turn_id, user_text)
        except Exception:
            # last-ditch: an object that at least has the methods (no disk).
            t = _NullTrace.__new__(_NullTrace)
            t.name, t.turn_id, t._committed = name, turn_id, True
            t._lock = threading.Lock()
            t.doc = {"stages": [], "shapes": [], "alternatives": []}
            return t


def trace(name: str, turn_id: str) -> Optional[dict]:
    """Read back ONE committed MRI trace by turn_id (the most recent if a turn_id ever
    recurs), or None. The Viewer's point lookup."""
    found = None
    for row in _read_mri(name):
        if isinstance(row, dict) and row.get("turn_id") == turn_id:
            found = row
    return found


def traces(name: str) -> list:  # noqa: F811 - intentional: MRI bulk reader (see note)
    """Every committed MRI trace for ``name``, oldest->newest (append order).

    NOTE: this shadows the bus-recorder ``traces`` defined earlier in the module.
    That is deliberate — the MRI is the richer, current reader, and the live system
    reads MRI traces. The bus trace list remains reachable via ``_read(name)`` /
    ``replay`` for the legacy path; nothing in the live turn depends on the old
    ``traces`` name."""
    return [r for r in _read_mri(name) if isinstance(r, dict)]


def last_trace(name: str) -> Optional[dict]:
    """The most recently committed MRI trace, or None."""
    rows = traces(name)
    return rows[-1] if rows else None


# ---------------------------------------------------------------------------
# Self-test — proves telemetry in isolation against a tiny fake bus, then verifies
# the replay round-trips from a real temp .anima dir. No models, no network.
#   python3 anima/telemetry.py --selftest
# ---------------------------------------------------------------------------
def _selftest() -> int:  # pragma: no cover - exercised via __main__
    import asyncio
    import os
    import tempfile

    global STORE

    fails: list[str] = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("telemetry self-test")

    # Minimal event/payload stand-ins (avoid importing event_bus to stay isolated).
    class _Ev:
        def __init__(self, topic, turn_id, payload):
            self.topic, self.turn_id, self.payload = topic, turn_id, payload

    class _Q:
        def __init__(self, text, name, context):
            self.text, self.name, self.context = text, name, context

    class _Obs:
        def __init__(self, organ, memory, weight=1.0, note=""):
            self.organ, self.memory, self.weight, self.note = organ, memory, weight, note

    class _Dec:
        def __init__(self, model, organs, mids, esc, plan):
            self.model = model
            self.contributing_organs = organs
            self.memory_ids = mids
            self.escalation = esc
            self.answer_plan = plan

    # A fake bus that records subscriptions and lets us deliver events by hand.
    class _Bus:
        def __init__(self):
            self.subs: dict = {}
            self.sink = None

        def subscribe(self, topic, handler):
            self.subs.setdefault(topic, []).append(handler)

        def set_error_sink(self, sink):
            self.sink = sink

        async def deliver(self, topic, turn_id, payload):
            for h in self.subs.get(topic, []):
                await h(_Ev(topic, turn_id, payload))

    async def scenario() -> None:
        bus = _Bus()
        t = attach(bus, "selftest_vera")

        ok("attach subscribed all 4 topics",
           all(len(bus.subs.get(top, [])) == 1
               for top in (Topic.QUESTION, Topic.OBSERVATION, Topic.DECISION, Topic.RESPONSE)))
        ok("attach installed the error sink", bus.sink is not None)

        tid = "f_telemtest01"
        mem = {"id": "f_mem001", "confidence": 0.97, "lirf": "you · birthday = 1990-06-11"}

        # Drive a full turn through the bus, telemetry recording passively.
        await bus.deliver(Topic.QUESTION, tid, _Q("when's my birthday?", "vera", {"cloud_on": True}))
        ok("begin opened a trace on QUESTION", tid in t._open)
        ok("question text recorded", t._open[tid]["question"]["text"] == "when's my birthday?")

        await bus.deliver(Topic.OBSERVATION, tid, _Obs("identity", mem, weight=1.0, note="known fact"))
        await bus.deliver(Topic.OBSERVATION, tid,
                          _Obs("agency", {"id": "f_stub", "confidence": 0.2}, weight=0.5, note="stub"))
        ok("two observations folded in", len(t._open[tid]["observations"]) == 2)
        ok("observation captured memory id + confidence",
           t._open[tid]["observations"][0]["memory_id"] == "f_mem001"
           and t._open[tid]["observations"][0]["confidence"] == 0.97)

        await bus.deliver(Topic.DECISION, tid,
                          _Dec("local", ["identity"], ["f_mem001"], "", "Answer using what you know."))
        ok("decision recorded (organ contributed, memory id used)",
           t._open[tid]["decision"]["contributing_organs"] == ["identity"]
           and t._open[tid]["decision"]["memory_ids"] == ["f_mem001"])
        ok("no escalation recorded as escalated=False", t._open[tid]["decision"]["escalated"] is False)

        # RESPONSE closes + flushes the trace; buffer should now be empty for tid.
        await bus.deliver(Topic.RESPONSE, tid, "done")
        ok("RESPONSE committed + evicted the open trace", tid not in t._open)

        # Replay round-trips from disk.
        rt = replay("selftest_vera", tid)
        ok("replay finds the committed turn", rt is not None and rt["turn_id"] == tid)
        ok("replay: question survived", rt["question"]["text"] == "when's my birthday?")
        ok("replay: both observations survived", len(rt["observations"]) == 2)
        ok("replay: the used memory id survived", rt["decision"]["memory_ids"] == ["f_mem001"])
        ok("replay: escalation reconstructable", rt["decision"]["escalated"] is False)
        ok("replay: committed timestamp is ISO8601-Z",
           isinstance(rt["committed"], str) and rt["committed"].endswith("Z"))

        # last() returns it too.
        ok("last() returns the most recent trace", (last("selftest_vera") or {}).get("turn_id") == tid)

        # A telemetry failure must never propagate: feed a payload that breaks
        # attribute access and ensure _on_event still returns cleanly.
        class _Boom:
            @property
            def memory(self):
                raise RuntimeError("boom")
            organ = "x"
            weight = 1.0
            note = ""

        await bus.deliver(Topic.QUESTION, "f_t2", _Q("x", "v", {}))
        await bus.deliver(Topic.OBSERVATION, "f_t2", _Boom())   # must not raise
        ok("a malformed observation never breaks recording", "f_t2" in t._open)
        await bus.deliver(Topic.RESPONSE, "f_t2", "done")
        ok("turn still commits despite the bad observation", replay("selftest_vera", "f_t2") is not None)

        # Error-sink path: the bus surfaces a handler exception → telemetry marks it.
        await bus.deliver(Topic.QUESTION, "f_t3", _Q("x", "v", {}))
        await t._on_error(_Ev(Topic.QUESTION, "f_t3", None), RuntimeError("organ exploded"))
        await bus.deliver(Topic.RESPONSE, "f_t3", "done")
        rt3 = replay("selftest_vera", "f_t3")
        ok("error sink recorded the handler exception",
           rt3 is not None and rt3["errors"] and rt3["errors"][0]["type"] == "RuntimeError")

    # -----------------------------------------------------------------------
    # MRI scenario — build a synthetic full-schema trace exercising EVERY required
    # stage, a shape transformation, and a rejected-alternative, then read it back
    # and assert the hard contract round-trips byte-for-shape. No bus, no models.
    # -----------------------------------------------------------------------
    def mri_scenario() -> None:
        import numpy as _np

        print()
        print("MRI recorder self-test")

        nm, tid = "selftest_mri_vera", "t-1717000000000"
        tr = open_trace(nm, tid, "when's my birthday?")
        ok("open_trace returns a usable trace", isinstance(tr, MRITrace) and tr.turn_id == tid)

        # perception — entities/sentiment + a SUMMARY of the perception vector.
        tr.stage("perception", t_ms=0.42,
                 in_shape={"text_len": 19},
                 out={"entities": ["birthday"], "sentiment": 0.1,
                      "vector": {"presence": 1.0, "attention": 0.85, "mood": 0.1}},
                 dropped=["raw_token_stream"], confidence=0.6, note="9-field percept")
        # heart — feeling vector + neuron-state summary + unrest (the NEURAL frame).
        _h = _np.zeros(24)
        tr.stage("heart", t_ms=1.3,
                 in_shape={"percept_dims": 9, "neurons": 24},
                 out={"feeling": {"valence": 0.2, "arousal": 0.3, "reaching": 0.1,
                                  "settled": 0.4, "unrest": 0.05},
                      "neurons": {"n": 24, "mean": float(_h.mean()), "l2": float(_np.linalg.norm(_h))},
                      "unrest": 0.05},
                 dropped=[], confidence=None, note="LTC state read")
        # capture — LIRF facts + world edges + salient-in vs DROPPED = conservation.
        tr.stage("capture", t_ms=2.1,
                 in_shape={"text_len": 19},
                 out={"lirf_facts_written": ["f_b1"], "world_edges_written": [],
                      "salient_in": 2, "salient_kept": 1},
                 dropped=["salient:weather(low-signal)"], confidence=0.9,
                 note="conservation: 2 in, 1 kept, 1 dropped")
        # route — facts selected ids+values + routing decision.
        tr.stage("route", t_ms=0.8,
                 in_shape={"candidate_facts": 3},
                 out={"selected": [{"id": "f_b1", "trait": "birthday", "value": "1990-06-11"}],
                      "model": "local", "escalation": ""},
                 dropped=["f_x9:lives(off-topic)"], confidence=0.95, note="query-aware")
        # bind — the bound spine block + fact truth-classes.
        tr.stage("bind", t_ms=0.3,
                 in_shape={"selected_facts": 1},
                 out={"block_len": 142, "truth_classes": {"birthday": "KNOWN"}},
                 dropped=[], confidence=1.0, note="binding contract")
        # situation — cluster nodes + edges.
        tr.stage("situation", t_ms=1.0,
                 in_shape={"query": "birthday"},
                 out={"nodes": ["you", "birthday"], "edges": 1, "seed": ["you"]},
                 dropped=[], confidence=None, note="2-hop cluster")
        # meaning — significance objects.
        tr.stage("meaning", t_ms=0.0,
                 in_shape={"topics": 0}, out={"objects": []},
                 dropped=[], confidence=None, note="N/A: sparse life")
        # curiosity — gaps + candidates + SELECTED + REJECTED{option,reason}.
        tr.stage("curiosity", t_ms=0.5,
                 in_shape={"gaps": 2},
                 out={"candidates": ["dog_name", "job"], "selected": "dog_name"},
                 dropped=["job(lower priority)"], confidence=0.7, note="one aside max")
        tr.alternative("curiosity:which gap to ask", selected="dog_name",
                       rejected=[{"option": "job", "reason": "lower priority this turn"}])
        # prompt — system-prompt length + the mem block.
        tr.stage("prompt", t_ms=0.2,
                 in_shape={"history_turns": 3},
                 out={"system_prompt_len": 2048, "mem_block_len": 142},
                 dropped=[], confidence=None, note="assembled")
        # generate — model + reply + token count + tok/s.
        tr.stage("generate", t_ms=812.0,
                 in_shape={"prompt_chars": 2190},
                 out={"model": "qwen", "reply": "Your birthday is June 11th.",
                      "tokens": 7, "tok_s": 42.0},
                 dropped=[], confidence=None, note="local")
        # verify — verdict + issues + override.
        tr.stage("verify", t_ms=0.6,
                 in_shape={"reply_len": 27, "evidence_facts": 1},
                 out={"verdict": "ok", "issues": [], "override": False},
                 dropped=[], confidence=0.98, note="passed")

        # a shape transformation across a boundary, with declared loss.
        tr.shape("perception->heart",
                 received={"fields": 9, "type": "Perception"},
                 expected={"fields": 9, "type": "ndarray(9,)"},
                 transformation="Perception.vector(): 9 named affect fields -> float64[9]",
                 loss=["entities", "sentiment(string label)"])

        committed = tr.commit(reply="Your birthday is June 11th.", total_ms=820.0)
        ok("commit returns the committed doc", isinstance(committed, dict))
        ok("commit is idempotent (2nd returns None)", tr.commit(reply="x", total_ms=1) is None)

        # Read it back from disk — the Viewer's exact path.
        rt = trace(nm, tid)
        ok("trace() finds the committed turn", rt is not None and rt["turn_id"] == tid)
        ok("schema: top-level keys present",
           all(k in rt for k in ("turn_id", "name", "at", "user_text", "reply",
                                 "total_ms", "stages", "shapes", "alternatives")))
        ok("schema: at is an epoch float", isinstance(rt["at"], (int, float)))
        ok("schema: user_text + reply survived",
           rt["user_text"] == "when's my birthday?" and rt["reply"].startswith("Your birthday"))
        ok("schema: total_ms recorded", rt["total_ms"] == 820.0)

        seen = [s["stage"] for s in rt["stages"]]
        ok("all 11 required stages captured, in order", seen == list(MRI_STAGES))
        # every frame carries the full per-stage contract.
        good_frames = all(
            set(f) >= {"stage", "t_ms", "in_shape", "out", "dropped", "confidence", "note"}
            for f in rt["stages"])
        ok("every stage frame has the full key set", good_frames)

        per = {s["stage"]: s for s in rt["stages"]}
        ok("perception frame summarises the percept vector",
           "vector" in per["perception"]["out"] and per["perception"]["dropped"] == ["raw_token_stream"])
        ok("heart frame carries feeling + neuron summary + unrest",
           per["heart"]["out"]["unrest"] == 0.05 and per["heart"]["out"]["neurons"]["n"] == 24)
        ok("capture frame is the conservation ledger",
           per["capture"]["out"]["salient_in"] == 2 and per["capture"]["dropped"] == ["salient:weather(low-signal)"])
        ok("route frame records selected ids+values + the decision",
           per["route"]["out"]["selected"][0]["id"] == "f_b1" and per["route"]["out"]["model"] == "local")
        ok("bind frame carries truth-classes", per["bind"]["out"]["truth_classes"]["birthday"] == "KNOWN")
        ok("generate frame carries model + tokens + tok/s",
           per["generate"]["out"]["tokens"] == 7 and per["generate"]["out"]["tok_s"] == 42.0)
        ok("verify frame carries verdict + override",
           per["verify"]["out"]["verdict"] == "ok" and per["verify"]["out"]["override"] is False)
        ok("a skipped stage is recorded with a note, not omitted",
           per["meaning"]["note"].startswith("N/A"))
        ok("confidence is clamped 0..1 or null",
           all((f["confidence"] is None) or (0.0 <= f["confidence"] <= 1.0) for f in rt["stages"]))

        ok("shapes: the boundary transformation round-trips",
           rt["shapes"] and rt["shapes"][0]["boundary"] == "perception->heart"
           and "entities" in rt["shapes"][0]["loss"])
        ok("alternatives: the rejected option + reason survived",
           rt["alternatives"] and rt["alternatives"][0]["selected"] == "dog_name"
           and rt["alternatives"][0]["rejected"][0]["option"] == "job"
           and "priority" in rt["alternatives"][0]["rejected"][0]["reason"])

        ok("last_trace() returns it too", (last_trace(nm) or {}).get("turn_id") == tid)
        ok("the whole doc is JSON-serialisable", _is_json_safe(rt))

        # GUARDRAIL: a stage handed un-serialisable / pathological input must NOT raise,
        # and must NOT corrupt the trace — the camera never trips the actor.
        tr2 = open_trace(nm, "t-guard")

        class _Unserialisable:
            def __repr__(self):
                raise RuntimeError("repr boom")
        tr2.stage("perception", out={"obj": _Unserialisable(), "circular": None}, t_ms="not-a-number")
        # a NaN confidence and an Inf latency must degrade to null, never crash.
        tr2.stage("heart", confidence=float("nan"), t_ms=float("inf"))
        g = tr2.commit(reply="ok", total_ms=1.0)
        ok("a stage with an un-serialisable output never breaks the recorder", isinstance(g, dict))
        rt2 = trace(nm, "t-guard")
        ok("the guarded trace still committed + reads back", rt2 is not None and len(rt2["stages"]) == 2)
        ok("NaN confidence degraded to null", rt2["stages"][1]["confidence"] is None)
        ok("non-numeric / Inf latency degraded to null",
           rt2["stages"][0]["t_ms"] is None and rt2["stages"][1]["t_ms"] is None)

    # Run BOTH scenarios inside a throwaway .anima so we never touch real state.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        os.chdir(tmp)
        STORE = Path(".anima")
        try:
            asyncio.run(scenario())
            mri_scenario()
        finally:
            os.chdir(cwd)
            STORE = Path(".anima")

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("ALL TELEMETRY SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv or len(sys.argv) == 1:
        raise SystemExit(_selftest())
    print("usage: python3 anima/telemetry.py --selftest")
