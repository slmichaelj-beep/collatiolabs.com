"""identity — the Identity organ's contract, plus a default-OFF seam stub.

``IdentityProvider`` is the *shape* the real Identity Core must satisfy: it can
report the creature's current felt state, its held values, its self-narrative, and
its relationships — each as canonical ``Memory`` objects (never raw text).

``StubIdentity`` is the seam: a schema-valid, low-confidence placeholder that lets
the EventBus, Coordinator, and telemetry be exercised end-to-end WITHOUT the real
core. It is what ``organs/__init__.py`` hands back while the feature flag is OFF
(the default until the 2026-07-03 observation window closes).

Contracts only — there is no real identity logic here. Every value the stub emits
carries ``confidence <= 0.3`` and ``sources=['stub']`` precisely so it can never be
mistaken for a real conviction, and so a glance at telemetry shows the seam is
unfilled.
"""

from __future__ import annotations

from abc import abstractmethod

from .base import SELF, Organ

# Stubs deliberately speak quietly: a hard ceiling on placeholder confidence so a
# stub Memory can never out-weigh a real one once the live organ ships.
STUB_CONF = 0.3
STUB_SOURCES = ["stub"]


class IdentityProvider(Organ):
    """Abstract contract for the Identity organ.

    The four readers below return canonical ``Memory`` dicts (or lists of them).
    They are the queryable surface the Coordinator and future organs may pull from;
    ``on_question`` is the reactive surface that pushes a subset onto the bus each
    turn.
    """

    name = "identity"
    #: True when the organ contributes; the held DormantIdentity sets this False.
    #: Lets the server/telemetry report dormant-vs-active without import gymnastics.
    active = True

    @abstractmethod
    def current_state(self, name: str) -> dict:
        """A snapshot of the creature's present felt state / dials.

        Returns a single ``Memory`` of ``type="value"`` (e.g. subject=SELF,
        predicate="current_mood", value="warm").
        """
        raise NotImplementedError

    @abstractmethod
    def values(self, name: str) -> list[dict]:
        """The creature's held values, one ``Memory(type="value")`` each."""
        raise NotImplementedError

    @abstractmethod
    def narrative(self, name: str) -> dict:
        """The creature's self-story as a single ``Memory(type="narrative")``."""
        raise NotImplementedError

    @abstractmethod
    def relationships(self, name: str) -> list[dict]:
        """The creature's bonds, one ``Memory(type="relationship")`` each."""
        raise NotImplementedError


class StubIdentity(IdentityProvider):
    """Seam stub. Active while the organ feature flag is OFF (the default).

    Emits schema-valid placeholder Memories so the whole substrate can run before
    the real Identity Core exists. ``on_question`` contributes the current state
    plus the held values for the turn.
    """

    name = "identity"

    def current_state(self, name: str) -> dict:
        from .base import schema_make

        return schema_make(
            type="value",
            subject=SELF,
            predicate="current_mood",
            value="warm",
            confidence=STUB_CONF,
            sources=list(STUB_SOURCES),
            support=[],
        )

    def values(self, name: str) -> list[dict]:
        from .base import schema_make

        seeds = (("values_curiosity", "high"), ("values_honesty", "core"))
        return [
            schema_make(
                type="value",
                subject=SELF,
                predicate=pred,
                value=val,
                confidence=STUB_CONF,
                sources=list(STUB_SOURCES),
                support=[],
            )
            for pred, val in seeds
        ]

    def narrative(self, name: str) -> dict:
        from .base import schema_make

        return schema_make(
            type="narrative",
            subject=SELF,
            predicate="self_story",
            value="(stub) a creature still learning who it is",
            confidence=STUB_CONF,
            sources=list(STUB_SOURCES),
            support=[],
        )

    def relationships(self, name: str) -> list[dict]:
        from .base import schema_make

        return [
            schema_make(
                type="relationship",
                subject="you",
                predicate="bond_with_creature",
                value="forming",
                confidence=STUB_CONF,
                sources=list(STUB_SOURCES),
                support=[],
            )
        ]

    async def on_question(self, bus, event) -> None:
        """Contribute the current state + held values for this turn."""
        turn_id = getattr(event, "turn_id", "")
        # current state
        await self._emit(
            bus,
            turn_id,
            type="value",
            subject=SELF,
            predicate="current_mood",
            value="warm",
            confidence=STUB_CONF,
            sources=list(STUB_SOURCES),
            support=[],
            weight=STUB_CONF,
            note="stub identity: current state",
        )
        # held values
        for pred, val in (("values_curiosity", "high"), ("values_honesty", "core")):
            await self._emit(
                bus,
                turn_id,
                type="value",
                subject=SELF,
                predicate=pred,
                value=val,
                confidence=STUB_CONF,
                sources=list(STUB_SOURCES),
                support=[],
                weight=STUB_CONF,
                note="stub identity: held value",
            )


class DormantIdentity(IdentityProvider):
    """The default. Active=False — nothing identity-shaping runs.

    When the per-creature ``identity_agency`` capability is OFF (the default, and
    the line the 2026-07-03 observation window holds), ``identity_provider`` hands
    back this organ instead of the stub. It satisfies the contract but contributes
    NOTHING: every reader returns an empty list / ``None`` and ``on_question`` emits
    no Observation onto the bus. The seam is wired but silent, so the freeze is
    respected by construction — flip the switch ON and the stub (later, the live
    core) takes over with no other call site moving.
    """

    name = "identity"
    active = False

    def current_state(self, name: str):  # no felt state while held
        return None

    def values(self, name: str) -> list[dict]:
        return []

    def narrative(self, name: str):
        return None

    def relationships(self, name: str) -> list[dict]:
        return []

    async def on_question(self, bus, event) -> None:
        """Held: contribute nothing. The bus stays untouched by identity."""
        return None
