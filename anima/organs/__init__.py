"""organs — the substrate's pluggable contributors, gated default-OFF.

This package holds the *seams* for the moonshot's organs. Each organ is an
``Organ`` (see :mod:`anima.organs.base`) that reacts to ``Topic.QUESTION`` and
emits canonical ``Memory`` objects onto ``Topic.OBSERVATION``. It never returns
data and never speaks to the mouth.

The feature flag below is the held line. In the spirit of :mod:`anima.caps`
(default-OFF, an explicit toggle), ``ANIMA_ORGANS_LIVE`` decides whether the LIVE
Identity Core / Agency are wired in or whether the SEAM STUBS run. It is OFF by
default — the real organs stay HELD until the 2026-07-03 observation window
closes. Until then the stubs let the EventBus, Coordinator, and telemetry be
exercised end-to-end with nothing real behind them.

The three blessed entrypoints:

* :func:`identity_provider` — the flag-selected Identity organ.
* :func:`agency_provider`   — the flag-selected Agency organ.
* :func:`register_all`      — instantiate both and subscribe them to the bus. The
  single call the server makes to wire organs onto the substrate.

Flag note (flagged for the founder, per the design): this uses an env-var gate to
match the "held until 2026-07-03" framing. To persist it per-creature instead,
swap :func:`_organs_live` for ``caps.enabled(name, "organs_live")`` (a new key in
``.anima/{name}.caps.json``) — a one-line change, no other call site moves.
"""

from __future__ import annotations

import os

from .agency import AgencyProvider, StubAgency
from .base import Organ
from .identity import IdentityProvider, StubIdentity

__all__ = [
    "Organ",
    "IdentityProvider",
    "StubIdentity",
    "AgencyProvider",
    "StubAgency",
    "ORGAN_FLAG",
    "identity_provider",
    "agency_provider",
    "register_all",
]

#: env flag; "" / unset / "0" / "false" -> stubs (the default, pre-2026-07-03).
ORGAN_FLAG = "ANIMA_ORGANS_LIVE"


def _organs_live() -> bool:
    """True iff the organ feature flag is explicitly turned on.

    Mirrors caps' default-OFF posture: anything other than a clearly-truthy value
    keeps the stubs in place.
    """
    return os.environ.get(ORGAN_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def identity_provider() -> IdentityProvider:
    """Return the LIVE Identity Core iff the flag is on AND it is importable;
    otherwise the :class:`StubIdentity` seam.

    The 2026-07-03 observation window is what flips the flag on. The import is
    attempted lazily so a missing/held live module never breaks the default path.
    """
    if _organs_live():
        try:  # pragma: no cover - live organ is HELD until 2026-07-03
            from .identity_live import LiveIdentity  # type: ignore

            return LiveIdentity()
        except Exception:
            pass
    return StubIdentity()


def agency_provider() -> AgencyProvider:
    """Return the LIVE Agency iff the flag is on AND it is importable; otherwise
    the :class:`StubAgency` seam. Same gate as :func:`identity_provider`."""
    if _organs_live():
        try:  # pragma: no cover - live organ is HELD until 2026-07-03
            from .agency_live import LiveAgency  # type: ignore

            return LiveAgency()
        except Exception:
            pass
    return StubAgency()


def register_all(bus, name: str) -> list[Organ]:
    """Instantiate the flag-selected organs and subscribe each to ``Topic.QUESTION``.

    Returns the live list of organ instances (so the caller can later
    ``unsubscribe`` or introspect them). This is the one call the server makes to
    wire organs onto the substrate.

    Each organ's ``on_question`` is bound into a one-arg bus handler ``(event) ->
    awaitable`` because the EventBus delivers a single ``Event`` to subscribers;
    the organ also needs the bus to publish its Observations, so we close over it.
    """
    from .base import Topic

    organs: list[Organ] = [identity_provider(), agency_provider()]
    for organ in organs:
        def _handler(event, _organ=organ):
            return _organ.on_question(bus, event)

        bus.subscribe(Topic.QUESTION, _handler)
    return organs


# ---------------------------------------------------------------------------
# Self-test: proves the organs package works in isolation — no server, no models,
# no real bus/schema required (the base shims stand in if siblings aren't present).
#   python3 -m anima.organs --selftest
# ---------------------------------------------------------------------------
def _selftest() -> int:  # pragma: no cover - exercised via __main__
    import asyncio

    from .base import Observation, Topic, schema_validate

    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(("  ok  " if cond else " FAIL ") + label)
        if not cond:
            failures.append(label)

    print("organs selftest")
    print("-" * 60)

    # 1. Flag default-OFF -> stub providers.
    os.environ.pop(ORGAN_FLAG, None)
    ident = identity_provider()
    agcy = agency_provider()
    check(isinstance(ident, StubIdentity), "flag OFF -> StubIdentity")
    check(isinstance(agcy, StubAgency), "flag OFF -> StubAgency")
    check(isinstance(ident, IdentityProvider), "StubIdentity satisfies IdentityProvider")
    check(isinstance(agcy, AgencyProvider), "StubAgency satisfies AgencyProvider")

    # 2. Truthy flag still falls back to stubs when no live module exists (held).
    os.environ[ORGAN_FLAG] = "1"
    check(isinstance(identity_provider(), StubIdentity), "flag ON, live held -> StubIdentity")
    check(isinstance(agency_provider(), StubAgency), "flag ON, live held -> StubAgency")
    os.environ.pop(ORGAN_FLAG, None)

    # 3. Every reader method returns schema-valid canonical Memories.
    cs = ident.current_state("vera")
    ok, why = schema_validate(cs)
    check(ok, f"identity.current_state -> valid Memory ({why})")
    check(cs.get("type") == "value", "current_state type == value")
    check(cs.get("confidence", 1.0) <= 0.3, "current_state confidence <= 0.3 (stub ceiling)")
    check(cs.get("sources") == ["stub"], "current_state sources == ['stub']")

    vals = ident.values("vera")
    check(isinstance(vals, list) and len(vals) >= 1, "identity.values -> non-empty list")
    check(all(schema_validate(m)[0] for m in vals), "all values are valid Memories")

    narr = ident.narrative("vera")
    check(schema_validate(narr)[0] and narr.get("type") == "narrative", "narrative -> valid type=narrative")

    rels = ident.relationships("vera")
    check(
        isinstance(rels, list) and all(schema_validate(m)[0] and m["type"] == "relationship" for m in rels),
        "relationships -> list of valid type=relationship",
    )

    ev = agcy.evaluate(["greet", "ask", {"id": "defer"}])
    check(
        isinstance(ev, list) and len(ev) == 3 and all(schema_validate(m)[0] and m["type"] == "agency" for m in ev),
        "agency.evaluate -> one valid agency Memory per option",
    )
    pref = agcy.preferred_action(["greet", "ask"])
    check(
        schema_validate(pref)[0] and pref.get("value") == "greet" and pref["type"] == "agency",
        "agency.preferred_action -> picks first option, valid Memory",
    )
    check(agcy.preferred_action([])["value"] == "(none)", "preferred_action([]) -> '(none)' (no crash)")

    # 4. on_question emits Observations onto Topic.OBSERVATION via a fake bus.
    captured: list[Observation] = []

    class FakeBus:
        async def publish(self, topic, payload, *, turn_id, source=""):
            check_topic = topic == Topic.OBSERVATION
            if not check_topic:
                failures.append(f"emitted on wrong topic: {topic}")
            captured.append(payload)

    fake = FakeBus()

    class Q:  # minimal stand-in for event_bus.Question-bearing Event
        turn_id = "f_testturn01"

        class payload:
            context = {"options": ["smile", "wave"]}

    asyncio.run(ident.on_question(fake, Q))
    n_ident = len(captured)
    check(n_ident == 3, f"identity.on_question emitted 3 Observations (got {n_ident})")

    asyncio.run(agcy.on_question(fake, Q))
    n_agcy = len(captured) - n_ident
    check(n_agcy == 1, f"agency.on_question emitted 1 Observation (got {n_agcy})")

    check(all(isinstance(o, Observation) for o in captured), "all emissions are Observation envelopes")
    check(all(schema_validate(o.memory)[0] for o in captured), "every emitted Observation.memory is schema-valid")
    check(all(o.memory["id"].startswith("f_") for o in captured), "every Memory.id is f_-prefixed")
    check(captured[-1].memory["value"] == "smile", "agency read options from event context -> 'smile'")
    check({o.organ for o in captured} == {"identity", "agency"}, "Observations tagged with organ names")

    # 5. register_all subscribes both organs to QUESTION, and the registered
    #    handlers actually drive the organs (proving the closed-over bus works).
    import inspect

    collected: list = []  # (topic, handler) pairs the bus was asked to subscribe

    captured.clear()
    fake3 = FakeBus()

    class WiringBus:
        # subscribe records the wiring; publish is what the handlers call through.
        def subscribe(self, topic, handler):
            collected.append((topic, handler))

        async def publish(self, topic, payload, *, turn_id, source=""):
            await fake3.publish(topic, payload, turn_id=turn_id, source=source)

    organs = register_all(WiringBus(), "vera")
    check(len(organs) == 2, "register_all returns 2 organs")
    check(
        len(collected) == 2 and all(t == Topic.QUESTION for t, _ in collected),
        "both organs subscribed to Topic.QUESTION",
    )
    # required positional args = params with no default (the bound _organ has one)
    def _required_args(h) -> int:
        return sum(
            1
            for p in inspect.signature(h).parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        )

    arities = [_required_args(h) for _, h in collected]
    check(all(a == 1 for a in arities), "registered handlers require exactly one arg (event)")

    # drive each registered handler with a Question event; they should publish
    # Observations through the closed-over WiringBus -> fake3 -> captured.
    for _topic, handler in collected:
        asyncio.run(handler(Q))
    check(len(captured) == 4, f"registered handlers emitted 4 Observations total (got {len(captured)})")
    check(
        all(isinstance(o, Observation) and schema_validate(o.memory)[0] for o in captured),
        "handler-driven emissions are valid Observations",
    )

    print("-" * 60)
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print(f"PASS — all checks green ({n_ident + n_agcy} Observations emitted across organs)")
    return 0
