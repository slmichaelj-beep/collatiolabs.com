"""
event_bus — the moonshot's spine. Organs don't call each other; they REACT to events.

This is the event-driven core of the Anima substrate. A turn enters as a `Question`
published on `Topic.QUESTION`; subscribed organs each react by publishing one or more
`Observation`s onto `Topic.OBSERVATION` (whose `.memory` is ALWAYS a canonical Memory
dict, never a bespoke format); the `Coordinator` deterministically decides from those
observations — in code, before the mouth speaks — and the verdict goes out on
`Topic.DECISION`, with the closed turn signalled on `Topic.RESPONSE`.

Three load-bearing seams (stated once, enforced here):

  * An organ NEVER returns data; it `publish`es an `Observation` whose `.memory` is a
    Memory dict (the same canonical object `memory_lirf.LIRF` stores). The bus carries
    that dict opaquely — it reads only `memory["id"]` / `memory["confidence"]`, it never
    invents a format. Schema VALIDITY is the organ's responsibility (organs build via
    `memory_schema.make`); the bus is the transport, not the validator.
  * Telemetry is a PASSIVE peer subscriber. It reads the very same events the Coordinator
    reads (`telemetry.attach(bus, name)` wires it to QUESTION/OBSERVATION/DECISION/
    RESPONSE). It is never in the request path, so — exactly like `metrics._append` — a
    telemetry failure can never slow or break a turn.
  * The `Coordinator` is `route.py` generalized: a PURE function of
    (question, observations) → Decision. No models, no I/O, no globals — so it is
    unit-testable with hand-built `Observation`s and zero real organs.

Fan-out discipline: `publish` delivers to every subscriber concurrently via
`asyncio.gather(..., return_exceptions=True)`. One handler raising NEVER drops the other
handlers or the turn — exceptions are captured and (best-effort) surfaced to telemetry,
never re-raised into the turn. This mirrors the repo's "a diagnostic must NEVER break a
turn" invariant, lifted to the whole bus.

Dependency-light + local: stdlib `asyncio` only for the machinery. `memory_lirf._now`
(ISO8601-`Z`) and `memory_lirf._new_id` (`f_`-prefixed ids) are reused when importable so
timestamps and ids match the rest of `.anima`; when this file is exercised in isolation
(before its siblings land) it falls back to byte-identical local copies, so the self-test
runs with zero unbuilt dependencies.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional


# ---------------------------------------------------------------------------
# Shared primitives — reuse the live ones so ids/timestamps match all of .anima.
# Fall back to byte-identical local copies ONLY when memory_lirf isn't importable
# (i.e. running this module standalone), so the self-test has zero hard deps.
# ---------------------------------------------------------------------------
try:                                            # pragma: no cover - import shim
    from .memory_lirf import _now as _now, _new_id as _new_id
except Exception:                               # pragma: no cover - standalone path
    import secrets
    from datetime import datetime, timezone

    def _now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _new_id() -> str:
        return "f_" + secrets.token_hex(6)


def new_turn_id() -> str:
    """Mint a turn id. Same `f_`-prefixed shape as Memory ids, so every artifact of a
    turn — the turn key, the memories it used — shares one id vocabulary."""
    return _new_id()


# ---------------------------------------------------------------------------
# Topics — the only channels. A closed enum so a typo can't silently misroute an
# event into the void. `str` mixin → a Topic is also its wire string ("question").
# ---------------------------------------------------------------------------
class Topic(str, Enum):
    QUESTION = "question"        # a user turn enters the system
    OBSERVATION = "observation"  # an organ's contribution (payload.memory is ALWAYS a Memory)
    DECISION = "decision"        # the Coordinator's chosen response plan
    RESPONSE = "response"        # final, post-mouth (closes the turn / telemetry commit)


# ---------------------------------------------------------------------------
# Event envelope — every message that travels the bus.
# Frozen: an event is an immutable record of "this happened", safe to fan out to N
# subscribers without one mutating what another sees.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Event:
    topic: Topic
    turn_id: str                 # ties every event of one turn together (telemetry key)
    payload: Any                 # Question | Observation | Decision | str
    ts: str = field(default_factory=_now)   # ISO8601-Z, reuses memory_lirf._now
    source: str = ""             # organ that emitted it ("identity", "agency", "coordinator")


# ---------------------------------------------------------------------------
# The three concrete payloads.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Question:
    text: str
    name: str                    # creature name — which Vera (per-creature stores)
    context: dict = field(default_factory=dict)  # caps state, cloud_on, history len, …


@dataclass(frozen=True)
class Observation:
    """What an organ emits onto Topic.OBSERVATION.

    `memory` is a canonical Memory DICT (built by the organ via memory_schema.make).
    The bus does not validate it — it only reads `memory["id"]` / `memory["confidence"]`
    for routing/telemetry. Keeping it a plain dict (not a typed import) is what lets the
    bus stay dependency-light and the schema live entirely at the organ boundary.
    """
    organ: str                   # "identity" | "agency" | …
    memory: dict                 # a Memory dict (memory_schema.validate() MUST pass at the organ)
    weight: float = 1.0          # organ's own confidence IN this contribution (0..1)
    note: str = ""               # short human-readable rationale (for the telemetry trace)


@dataclass(frozen=True)
class Decision:
    """The Coordinator's verdict — an instruction the mouth will narrate, NOT raw text."""
    answer_plan: str             # seed/instruction the mouth narrates
    model: str                   # which brain answers ("local" | "cloud:<name>")
    contributing_organs: list = field(default_factory=list)  # [str] organs that shaped this
    memory_ids: list = field(default_factory=list)           # [str] Memory.id values actually used
    escalation: str = ""         # "" | "local→cloud" | "stub→real" | "deferred:…"


# Handlers are async callables: `async def handler(event: Event) -> None`.
Handler = Callable[[Event], Awaitable[None]]


# ---------------------------------------------------------------------------
# EventBus — in-process async pub/sub.
# ---------------------------------------------------------------------------
class EventBus:
    """Fan-out pub/sub over a closed set of Topics.

    Subscribers register per-topic; `publish` wraps a payload in an `Event` and delivers
    it to every subscriber of that topic CONCURRENTLY. One handler raising never drops
    the others or the turn. `gather_observations` is the single await point that makes
    organs run in parallel: publish the QUESTION, let OBSERVATION handlers fire, drain
    until quiescent (or `timeout`), and hand the Coordinator the collected Observations.
    """

    def __init__(self) -> None:
        # topic -> ordered list of handlers (insertion order = subscription order, so
        # telemetry attached first sees an event no later than the Coordinator's path).
        self._subs: dict[Topic, list[Handler]] = {t: [] for t in Topic}
        # turn_id -> list[Observation] accumulated this turn (drained by gather_observations).
        self._inbox: dict[str, list[Observation]] = {}
        # best-effort sink for handler exceptions: async def(event, exc) -> None.
        # Wired by telemetry.attach when present; default is a no-op.
        self._error_sink: Optional[Callable[[Event, BaseException], Awaitable[None]]] = None

    # -- subscription ------------------------------------------------------
    def subscribe(self, topic: Topic, handler: Handler) -> None:
        """Register `handler` for `topic`. Idempotent: subscribing the same handler
        twice does not double-deliver."""
        bucket = self._subs[topic]
        if handler not in bucket:
            bucket.append(handler)

    def unsubscribe(self, topic: Topic, handler: Handler) -> None:
        """Remove `handler` from `topic` if present (no error if it wasn't)."""
        try:
            self._subs[topic].remove(handler)
        except ValueError:
            pass

    def set_error_sink(self, sink: Optional[Callable[[Event, BaseException], Awaitable[None]]]) -> None:
        """Install (or clear, with None) the async sink that receives handler exceptions.
        Telemetry uses this to record a failed organ WITHOUT the failure touching the turn."""
        self._error_sink = sink

    # -- internal: capture observations as a passive built-in subscriber ----
    async def _capture_observation(self, event: Event) -> None:
        """Bus-owned OBSERVATION subscriber: stash the payload so gather_observations can
        return it. Registered automatically per-turn; independent of any organ/telemetry."""
        if event.topic is Topic.OBSERVATION and isinstance(event.payload, Observation):
            self._inbox.setdefault(event.turn_id, []).append(event.payload)

    # -- publish -----------------------------------------------------------
    async def publish(self, topic: Topic, payload: Any, *, turn_id: str, source: str = "") -> None:
        """Wrap `payload` in an Event and deliver to every subscriber of `topic`.

        Fan-out is concurrent (`asyncio.gather(..., return_exceptions=True)`); a handler
        raising NEVER drops sibling handlers or the turn. Captured exceptions are routed
        to the error sink (telemetry) best-effort and otherwise swallowed — the turn is
        sacred. A topic with zero subscribers is a clean no-op.
        """
        event = Event(topic=topic, turn_id=turn_id, payload=payload, source=source)
        handlers = list(self._subs.get(topic, ()))   # snapshot: handlers may (un)subscribe mid-fan-out
        if not handlers:
            return
        results = await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)
        for exc in results:
            if isinstance(exc, BaseException):
                await self._surface(event, exc)

    async def _surface(self, event: Event, exc: BaseException) -> None:
        """Route a handler exception to the error sink. The sink itself failing, or a
        cancellation, must still not break the turn — so this swallows everything except
        a genuine CancelledError (which we re-raise to honor task cancellation)."""
        if isinstance(exc, asyncio.CancelledError):
            raise exc
        sink = self._error_sink
        if sink is None:
            return
        try:
            await sink(event, exc)
        except Exception:
            pass    # a diagnostic must NEVER break a turn

    # -- the parallel-organ await point ------------------------------------
    async def gather_observations(self, question: Question, *, turn_id: str,
                                  timeout: float = 2.0) -> list[Observation]:
        """Publish QUESTION, then collect every Observation organs emit for THIS turn_id
        until quiescent or `timeout`. Returns the Observation list the Coordinator decides
        on. This is the await point that makes organs parallel.

        Mechanics: a bus-owned OBSERVATION subscriber (`_capture_observation`) is attached
        for the duration so emissions land in `self._inbox[turn_id]` regardless of which
        organs (or telemetry) are also subscribed. Organs are presumed to do their work
        synchronously within their `on_question` coroutine, so when `publish(QUESTION)`
        returns, every organ's gather has resolved and its observations are already in.
        `timeout` is a backstop for an organ that defers emission onto a later task; it
        bounds the drain so a hung organ can't stall the turn.
        """
        self._inbox[turn_id] = []
        self.subscribe(Topic.OBSERVATION, self._capture_observation)
        try:
            # Publishing QUESTION awaits all on_question handlers (organs emit inline).
            await self.publish(Topic.QUESTION, question, turn_id=turn_id, source="bus")
            # Backstop drain: give any deferred emissions a bounded chance to land. We poll
            # for quiescence (a tick with no new observations) rather than always sleeping
            # the full timeout, so the common inline case returns immediately.
            deadline = asyncio.get_event_loop().time() + max(0.0, timeout)
            last = -1
            while asyncio.get_event_loop().time() < deadline:
                now_count = len(self._inbox.get(turn_id, ()))
                if now_count == last:           # a full tick with no growth → quiescent
                    break
                last = now_count
                await asyncio.sleep(0)          # yield so any pending organ tasks can run
            return list(self._inbox.get(turn_id, ()))
        finally:
            self.unsubscribe(Topic.OBSERVATION, self._capture_observation)
            self._inbox.pop(turn_id, None)


# ---------------------------------------------------------------------------
# Coordinator — route.py generalized: deterministic decision from evidence, in code,
# BEFORE the mouth speaks. A pure function of (question, observations) → Decision.
# ---------------------------------------------------------------------------
class Coordinator:
    """Decide the response plan from the observations organs emitted.

    Pure + deterministic: identical (question, observations) → identical Decision. No
    models, no I/O, no globals — so it is exhaustively unit-testable with hand-built
    Observations and zero real organs. The policy here is intentionally simple and
    explicit (the seam, not the final brain): real routing intelligence grows in place
    behind this same signature.

    Routing policy (v1):
      * Weight each observation by `weight × memory.confidence` (an organ's stated
        confidence IN the contribution, scaled by the memory's OWN confidence). Stub
        organs emit ≤0.3 confidence, so real evidence outranks placeholders automatically.
      * Pick the local brain by default. Escalate local→cloud iff the question context
        explicitly asks for it (`context["needs_cloud"]`) or no observation clears the
        evidence floor AND cloud is available — i.e. we only reach outward when we lack
        the standing to answer from within.
      * `contributing_organs` / `memory_ids` are the organs/memories whose observations
        actually cleared the floor (the provenance the telemetry trace records).
    """

    # An observation must clear this combined (weight × confidence) score to count as
    # real evidence. Stub placeholders (≤0.3 conf) fall below it, so they inform the
    # trace without being mistaken for grounds to answer.
    EVIDENCE_FLOOR = 0.35

    def decide(self, question: Question, observations: list[Observation]) -> Decision:
        ranked = sorted(
            observations,
            key=lambda o: self._score(o),
            reverse=True,
        )
        used = [o for o in ranked if self._score(o) >= self.EVIDENCE_FLOOR]

        ctx = question.context or {}
        cloud_available = bool(ctx.get("cloud_on") or ctx.get("cloud_available"))
        wants_cloud = bool(ctx.get("needs_cloud"))

        escalation = ""
        model = "local"
        if wants_cloud and cloud_available:
            model = "cloud:" + str(ctx.get("cloud_model") or "default")
            escalation = "local→cloud"
        elif not used and cloud_available:
            # No standing to answer from within, but we CAN reach out — do so explicitly.
            model = "cloud:" + str(ctx.get("cloud_model") or "default")
            escalation = "local→cloud"

        contributing_organs: list[str] = []
        memory_ids: list[str] = []
        for o in used:
            if o.organ not in contributing_organs:
                contributing_organs.append(o.organ)
            mid = self._memory_id(o)
            if mid and mid not in memory_ids:
                memory_ids.append(mid)

        answer_plan = self._plan(question, used)
        return Decision(
            answer_plan=answer_plan,
            model=model,
            contributing_organs=contributing_organs,
            memory_ids=memory_ids,
            escalation=escalation,
        )

    # -- scoring helpers (defensive: an organ's dict may be sparse) ---------
    @staticmethod
    def _score(o: Observation) -> float:
        conf = 0.0
        if isinstance(o.memory, dict):
            try:
                conf = float(o.memory.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
        try:
            w = float(o.weight)
        except (TypeError, ValueError):
            w = 0.0
        # Clamp both into [0,1] so a malformed organ can't inflate its own ranking.
        conf = min(1.0, max(0.0, conf))
        w = min(1.0, max(0.0, w))
        return w * conf

    @staticmethod
    def _memory_id(o: Observation) -> str:
        if isinstance(o.memory, dict):
            mid = o.memory.get("id")
            if isinstance(mid, str):
                return mid
        return ""

    @staticmethod
    def _plan(question: Question, used: list[Observation]) -> str:
        """Build the mouth's seed: the question plus a compact, deterministic digest of
        the evidence (each memory's cached `lirf` line when present, else a minimal
        rendering). Deterministic ordering — `used` is already rank-sorted."""
        if not used:
            return f"Answer the user plainly. Q: {question.text}"
        lines = []
        for o in used:
            mem = o.memory if isinstance(o.memory, dict) else {}
            lirf = mem.get("lirf")
            if isinstance(lirf, str) and lirf:
                lines.append(lirf)
            else:
                subj = mem.get("subject", "?")
                pred = mem.get("predicate", "?")
                val = mem.get("value", "?")
                lines.append(f"{subj} · {pred} = {val}")
        evidence = "; ".join(lines)
        return f"Answer using what you know. Q: {question.text} | evidence: {evidence}"


# ---------------------------------------------------------------------------
# Self-test — proves the bus + Coordinator in ISOLATION (no real organs, no models,
# no I/O). Run:  python -m anima.event_bus --selftest   (or: python anima/event_bus.py)
# ---------------------------------------------------------------------------
def _fake_memory(*, mid: str, subject: str, predicate: str, value: Any, confidence: float,
                 lirf: str = "") -> dict:
    """A minimal Memory-shaped dict for tests. Mirrors the canonical key set the real
    memory_schema.make produces; the bus only reads id/confidence, so this is sufficient
    to exercise routing without importing the schema layer."""
    return {
        "id": mid,
        "type": "value",
        "subject": subject,
        "predicate": predicate,
        "value": value,
        "confidence": confidence,
        "sources": ["selftest"],
        "support": [],
        "updated": _now(),
        "lirf": lirf or f"{subject} · {predicate} = {value}  (conf {confidence:.2f})",
    }


def _selftest() -> int:
    failures: list[str] = []

    def ok(label: str, cond: bool) -> None:
        mark = "ok  " if cond else "FAIL"
        print(f"  [{mark}] {label}")
        if not cond:
            failures.append(label)

    print("event_bus self-test")

    # 1) Topic enum is closed and string-valued.
    ok("Topic has exactly 4 channels", len(list(Topic)) == 4)
    ok("Topic.QUESTION is its wire string", Topic.QUESTION == "question" and Topic.QUESTION.value == "question")

    # 2) Event/payload dataclasses are frozen + auto-stamp ts.
    ev = Event(topic=Topic.QUESTION, turn_id="t1", payload="x")
    ok("Event auto-stamps ISO8601-Z ts", isinstance(ev.ts, str) and ev.ts.endswith("Z"))
    frozen_ok = False
    try:
        ev.turn_id = "t2"   # type: ignore[misc]
    except Exception:
        frozen_ok = True
    ok("Event is frozen (immutable record)", frozen_ok)

    # 3) ids/turn-ids carry the f_ vocabulary.
    ok("new_turn_id is f_-prefixed", new_turn_id().startswith("f_"))

    async def scenario() -> None:
        bus = EventBus()

        # --- An organ is just a coroutine subscribed to QUESTION that publishes an
        #     Observation onto OBSERVATION. NO real organ, NO model, NO I/O. ---
        async def identity_organ(event: Event) -> None:
            q: Question = event.payload
            mem = _fake_memory(mid="f_idmem001", subject="you", predicate="birthday",
                               value="1990-06-11", confidence=0.97,
                               lirf="you · birthday = 1990-06-11  (conf 0.97, ×3)")
            obs = Observation(organ="identity", memory=mem, weight=1.0, note="known fact")
            await bus.publish(Topic.OBSERVATION, obs, turn_id=event.turn_id, source="identity")

        async def stub_agency(event: Event) -> None:
            # A placeholder organ: low confidence, must NOT outrank the real fact and must
            # NOT clear the evidence floor.
            mem = _fake_memory(mid="f_stub00002", subject="you", predicate="preferred_action",
                               value="defer", confidence=0.2)
            obs = Observation(organ="agency", memory=mem, weight=0.5, note="stub")
            await bus.publish(Topic.OBSERVATION, obs, turn_id=event.turn_id, source="agency")

        # --- A passive telemetry-like peer subscriber: records every observation it sees
        #     on the SAME event the Coordinator will decide from. Proves the passive seam. ---
        seen: list[str] = []

        async def telemetry_peer(event: Event) -> None:
            if event.topic is Topic.OBSERVATION:
                seen.append(event.payload.memory["id"])

        bus.subscribe(Topic.QUESTION, identity_organ)
        bus.subscribe(Topic.QUESTION, stub_agency)
        bus.subscribe(Topic.OBSERVATION, telemetry_peer)

        turn_id = new_turn_id()
        q = Question(text="when's my birthday?", name="vera",
                     context={"cloud_on": True, "cloud_model": "claude"})

        obs = await bus.gather_observations(q, turn_id=turn_id, timeout=0.5)
        ok("gather collected both organs' observations", len(obs) == 2)
        ok("telemetry peer saw the SAME observations (passive seam)",
           sorted(seen) == sorted(o.memory["id"] for o in obs))

        decision = Coordinator().decide(q, obs)
        ok("Decision is a Decision", isinstance(decision, Decision))
        ok("real fact (identity) is a contributing organ", "identity" in decision.contributing_organs)
        ok("stub (low-conf) did NOT clear the evidence floor", "agency" not in decision.contributing_organs)
        ok("the real Memory.id flowed into the Decision", "f_idmem001" in decision.memory_ids)
        ok("default model is local (evidence sufficed, no escalation)", decision.model == "local")
        ok("no escalation when local has standing", decision.escalation == "")
        ok("answer_plan is an instruction, not raw text", decision.answer_plan.startswith("Answer"))
        ok("answer_plan carries the lirf evidence line", "1990-06-11" in decision.answer_plan)

        # --- Determinism: same inputs → identical Decision. ---
        d2 = Coordinator().decide(q, obs)
        ok("Coordinator is deterministic", d2 == decision)

        # --- Escalation paths. ---
        d_needs = Coordinator().decide(
            Question(text="latest news?", name="vera",
                     context={"cloud_on": True, "needs_cloud": True, "cloud_model": "claude"}),
            obs)
        ok("explicit needs_cloud escalates local→cloud", d_needs.model == "cloud:claude"
           and d_needs.escalation == "local→cloud")

        d_noevidence = Coordinator().decide(
            Question(text="?", name="vera", context={"cloud_on": True, "cloud_model": "claude"}),
            [Observation(organ="agency",
                         memory=_fake_memory(mid="f_low", subject="you", predicate="x",
                                             value="y", confidence=0.1),
                         weight=0.5)])
        ok("no standing + cloud available escalates", d_noevidence.escalation == "local→cloud")

        d_local_only = Coordinator().decide(
            Question(text="?", name="vera", context={}),   # no cloud
            [Observation(organ="agency",
                         memory=_fake_memory(mid="f_low2", subject="you", predicate="x",
                                             value="y", confidence=0.1),
                         weight=0.5)])
        ok("no standing + no cloud stays local (can't reach out)",
           d_local_only.model == "local" and d_local_only.escalation == "")

        # --- A raising handler must NOT drop siblings or break the turn; the error sink
        #     (telemetry's seam) must SEE the exception. ---
        captured: list[str] = []

        async def err_sink(event: Event, exc: BaseException) -> None:
            captured.append(type(exc).__name__)

        bus2 = EventBus()
        bus2.set_error_sink(err_sink)

        async def boom(event: Event) -> None:
            raise RuntimeError("organ exploded")

        good_seen: list[str] = []

        async def good(event: Event) -> None:
            good_seen.append("ran")

        bus2.subscribe(Topic.QUESTION, boom)
        bus2.subscribe(Topic.QUESTION, good)
        await bus2.publish(Topic.QUESTION, Question(text="x", name="v"), turn_id="f_t")
        ok("a raising handler did NOT drop its sibling", good_seen == ["ran"])
        ok("the exception was surfaced to the error sink", captured == ["RuntimeError"])

        # --- subscribe is idempotent; unsubscribe stops delivery. ---
        bus3 = EventBus()
        hits: list[int] = []

        async def once(event: Event) -> None:
            hits.append(1)

        bus3.subscribe(Topic.RESPONSE, once)
        bus3.subscribe(Topic.RESPONSE, once)   # duplicate — must not double-deliver
        await bus3.publish(Topic.RESPONSE, "done", turn_id="f_r")
        ok("subscribe is idempotent (no double delivery)", len(hits) == 1)
        bus3.unsubscribe(Topic.RESPONSE, once)
        await bus3.publish(Topic.RESPONSE, "done", turn_id="f_r")
        ok("unsubscribe stops delivery", len(hits) == 1)

        # --- publishing to a topic with no subscribers is a clean no-op. ---
        await bus3.publish(Topic.DECISION, "nobody listening", turn_id="f_x")
        ok("publish to empty topic is a no-op", True)

    asyncio.run(scenario())

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): {failures}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv or len(sys.argv) == 1:
        raise SystemExit(_selftest())
    print("usage: python -m anima.event_bus --selftest")
