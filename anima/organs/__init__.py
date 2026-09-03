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

* :func:`identity_provider` — the switch-selected Identity organ.
* :func:`agency_provider`   — the switch-selected Agency organ.
* :func:`register_all`      — instantiate both and subscribe them to the bus. The
  single call the server makes to wire organs onto the substrate.

The switch (per the founder's design): a per-creature capability flag,
``identity_agency``, persisted default-OFF in ``.anima/{name}.caps.json`` exactly
like every other cap. :func:`is_enabled` reads it. While it is OFF — the default,
and the line the 2026-07-03 observation window holds — the providers return the
DORMANT organs: wired onto the bus but contributing NOTHING, so no identity- or
agency-shaping signal runs. The founder flips it ON in Settings if/when they
choose; the same switch will govern the real Identity Core / Agency once those are
built (the live path below is a no-op until then).

A second, orthogonal env gate (``ANIMA_ORGANS_LIVE``) only chooses LIVE-vs-stub
*once the switch is ON*; it is irrelevant while the switch is OFF.
"""

from __future__ import annotations

import os

from .agency import AgencyProvider, DormantAgency, StubAgency
from .base import Organ
from .identity import DormantIdentity, IdentityProvider, StubIdentity

__all__ = [
    "Organ",
    "IdentityProvider",
    "StubIdentity",
    "DormantIdentity",
    "AgencyProvider",
    "StubAgency",
    "DormantAgency",
    "ORGAN_FLAG",
    "CAP_FLAG",
    "is_enabled",
    "identity_provider",
    "agency_provider",
    "register_all",
]

#: per-creature capability key (in .anima/{name}.caps.json) — the user-facing ON/OFF
#: switch for the Identity & Agency organs. Default-OFF; held until 2026-07-03.
CAP_FLAG = "identity_agency"

#: env flag; only consulted when the switch is ON, to pick LIVE vs stub.
ORGAN_FLAG = "ANIMA_ORGANS_LIVE"


def is_enabled(name: str) -> bool:
    """True iff this creature's ``identity_agency`` capability is turned ON.

    Reads the per-creature caps file via :mod:`anima.caps` (default-OFF). This is
    THE switch: OFF -> dormant organs (nothing runs); ON -> the stub seam (later,
    the live core). Fails closed — any read error is treated as OFF, so the
    observation-window freeze can never be lifted by accident.
    """
    try:
        from .. import caps

        return bool(caps.enabled(name, CAP_FLAG))
    except Exception:
        return False


def _organs_live() -> bool:
    """True iff the LIVE-organ env flag is explicitly turned on.

    Orthogonal to :func:`is_enabled`: this only selects LIVE-vs-stub once the
    per-creature switch is already ON. Mirrors caps' default-OFF posture.
    """
    return os.environ.get(ORGAN_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def identity_provider(name: str = "vera") -> IdentityProvider:
    """The switch-selected Identity organ for ``name``.

    * switch OFF (default) -> :class:`DormantIdentity` (active=False, emits nothing).
    * switch ON            -> the LIVE Identity Core iff the env flag is on AND it
      is importable, else the :class:`StubIdentity` seam.

    The 2026-07-03 observation window is what the founder waits on before flipping
    the switch ON. The live import is attempted lazily so a held live module never
    breaks the path.
    """
    if not is_enabled(name):
        return DormantIdentity()
    if _organs_live():
        try:  # pragma: no cover - live organ is HELD until 2026-07-03
            from .identity_live import LiveIdentity  # type: ignore

            return LiveIdentity()
        except Exception:
            pass
    return StubIdentity()


def agency_provider(name: str = "vera") -> AgencyProvider:
    """The switch-selected Agency organ for ``name``. Same gate as
    :func:`identity_provider`: switch OFF -> :class:`DormantAgency`; switch ON ->
    live iff available, else :class:`StubAgency`."""
    if not is_enabled(name):
        return DormantAgency()
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

    organs: list[Organ] = [identity_provider(name), agency_provider(name)]
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

    # Hermetic caps store so the switch can be toggled without touching real files.
    import tempfile
    from pathlib import Path as _Path

    from .. import caps as _caps

    _tmp = tempfile.mkdtemp(prefix="organs_selftest_")
    _orig_store = _caps.STORE
    _caps.STORE = _Path(_tmp)
    os.environ.pop(ORGAN_FLAG, None)
    NM = "selftest_creature"

    try:
        # 1. Switch default-OFF -> DORMANT organs (nothing identity-shaping runs).
        check(not is_enabled(NM), "identity_agency defaults OFF (never persisted)")
        d_id = identity_provider(NM)
        d_ag = agency_provider(NM)
        check(isinstance(d_id, DormantIdentity), "switch OFF -> DormantIdentity")
        check(isinstance(d_ag, DormantAgency), "switch OFF -> DormantAgency")
        check(d_id.active is False and d_ag.active is False, "dormant organs report active=False")
        check(d_id.values(NM) == [] and d_ag.evaluate(["x"]) == [], "dormant organs contribute nothing")

        # Dormant on_question emits NOTHING onto the bus.
        class _NoBus:
            published = 0

            async def publish(self, *a, **k):
                self.published += 1

        _nb = _NoBus()

        class _Q0:
            turn_id = "f_dormantturn"

        asyncio.run(d_id.on_question(_nb, _Q0))
        asyncio.run(d_ag.on_question(_nb, _Q0))
        check(_nb.published == 0, "dormant organs publish 0 Observations")

        # 2. Switch ON (persisted) -> stub seam; with live held, env flag still stubs.
        _caps.save(NM, {"identity_agency": True})
        check(is_enabled(NM), "identity_agency reads back ON after save")
        ident = identity_provider(NM)
        agcy = agency_provider(NM)
        check(isinstance(ident, StubIdentity), "switch ON -> StubIdentity")
        check(isinstance(agcy, StubAgency), "switch ON -> StubAgency")
        check(ident.active and agcy.active, "stub organs report active=True")
        check(isinstance(ident, IdentityProvider), "StubIdentity satisfies IdentityProvider")
        check(isinstance(agcy, AgencyProvider), "StubAgency satisfies AgencyProvider")
        os.environ[ORGAN_FLAG] = "1"
        check(isinstance(identity_provider(NM), StubIdentity), "switch ON, env ON, live held -> StubIdentity")
        check(isinstance(agency_provider(NM), StubAgency), "switch ON, env ON, live held -> StubAgency")
        os.environ.pop(ORGAN_FLAG, None)
    finally:
        _caps.STORE = _orig_store

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

    # Re-enter the hermetic store with the switch ON so register_all wires stubs.
    _caps.STORE = _Path(_tmp)
    try:
        _caps.save(NM, {"identity_agency": True})
        organs = register_all(WiringBus(), NM)
    finally:
        _caps.STORE = _orig_store
    check(len(organs) == 2, "register_all returns 2 organs")
    check(all(getattr(o, "active", True) for o in organs), "switch ON -> register_all wires ACTIVE organs")
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

    # 6. THE FREEZE: register_all with the switch OFF wires dormant organs whose
    #    handlers publish NOTHING — the default path runs the whole bus silently.
    off_collected: list = []
    off_published = 0

    class OffBus:
        def subscribe(self, topic, handler):
            off_collected.append((topic, handler))

        async def publish(self, *a, **k):
            nonlocal off_published
            off_published += 1

    _caps.STORE = _Path(_tmp)
    try:
        off_organs = register_all(OffBus(), "switched_off_creature")  # never persisted -> OFF
    finally:
        _caps.STORE = _orig_store
    check(len(off_organs) == 2 and not any(getattr(o, "active", True) for o in off_organs),
          "switch OFF -> register_all wires 2 DORMANT organs")
    for _topic, handler in off_collected:
        asyncio.run(handler(Q))
    check(off_published == 0, "switch OFF -> registered handlers emit 0 Observations (freeze holds)")

    print("-" * 60)
    if failures:
        print(f"FAILED ({len(failures)}): " + "; ".join(failures))
        return 1
    print(f"PASS — all checks green ({n_ident + n_agcy} Observations emitted across organs)")
    return 0
