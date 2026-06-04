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


def traces(name: str) -> list:
    """Every committed trace for ``name``, oldest→newest (append order)."""
    return [r for r in _read(name) if isinstance(r, dict)]


def last(name: str) -> Optional[dict]:
    """The most recently committed trace, or None."""
    rows = traces(name)
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

    # Run the scenario inside a throwaway .anima so we never touch real state.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        os.chdir(tmp)
        STORE = Path(".anima")
        try:
            asyncio.run(scenario())
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
