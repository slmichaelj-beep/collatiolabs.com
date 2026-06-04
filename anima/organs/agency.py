"""agency — the Agency organ's contract, plus a default-OFF seam stub.

``AgencyProvider`` is the *shape* the real Agency must satisfy: given a set of
options, it can score them and name a preferred action — each expressed as a
canonical ``Memory`` of ``type="agency"`` (never raw text, never a bare return to
the mouth).

``StubAgency`` is the seam: ``preferred_action`` returns the first option at
confidence 0.2, ``evaluate`` flat-scores every option. This lets the Coordinator's
option-weighing path run before the real organ exists. Contracts only — no real
deliberation here.
"""

from __future__ import annotations

from abc import abstractmethod

from .base import Organ

# Stubs speak even more quietly than identity: a flat, near-floor confidence so the
# Coordinator can wire up option-weighing without ever acting on a real preference.
STUB_CONF = 0.2
STUB_SOURCES = ["stub"]


class AgencyProvider(Organ):
    """Abstract contract for the Agency organ.

    ``evaluate`` and ``preferred_action`` are the queryable surface (score the
    field / pick one); ``on_question`` is the reactive surface that pushes the
    current preference onto the bus each turn.
    """

    name = "agency"

    @abstractmethod
    def evaluate(self, options: list) -> list[dict]:
        """Score each option, returning one ``Memory(type="agency")`` per option."""
        raise NotImplementedError

    @abstractmethod
    def preferred_action(self, options: list) -> dict:
        """The single chosen option as one ``Memory(type="agency")``."""
        raise NotImplementedError


def _opt_label(opt) -> str:
    """A stable, readable label for an option of unknown shape."""
    if isinstance(opt, str):
        return opt
    if isinstance(opt, dict):
        for k in ("id", "name", "label", "action"):
            v = opt.get(k)
            if isinstance(v, str) and v:
                return v
    return str(opt)


class StubAgency(AgencyProvider):
    """Seam stub. Active while the organ feature flag is OFF (the default).

    Flat-scores all options and prefers the first, both at floor confidence, so the
    Coordinator's option-weighing path is live before the real Agency ships.
    """

    name = "agency"

    def evaluate(self, options: list) -> list[dict]:
        from .base import schema_make

        options = list(options or [])
        out = []
        for opt in options:
            out.append(
                schema_make(
                    type="agency",
                    subject="you",
                    predicate="option_score",
                    value={"option": _opt_label(opt), "score": STUB_CONF},
                    confidence=STUB_CONF,
                    sources=list(STUB_SOURCES),
                    support=[],
                )
            )
        return out

    def preferred_action(self, options: list) -> dict:
        from .base import schema_make

        options = list(options or [])
        pick = _opt_label(options[0]) if options else "(none)"
        return schema_make(
            type="agency",
            subject="you",
            predicate="preferred_action",
            value=pick,
            confidence=STUB_CONF,
            sources=list(STUB_SOURCES),
            support=[],
        )

    async def on_question(self, bus, event) -> None:
        """Contribute the preferred action for this turn.

        The stub has no real option set from a bare Question, so it surfaces a
        floor-confidence 'no preference yet' agency Memory — enough for the
        Coordinator to see the organ is present and weigh it (at near-zero weight).
        """
        turn_id = getattr(event, "turn_id", "")
        ctx = getattr(getattr(event, "payload", None), "context", None)
        options = ctx.get("options", []) if isinstance(ctx, dict) else []
        pick = _opt_label(options[0]) if options else "(none)"
        await self._emit(
            bus,
            turn_id,
            type="agency",
            subject="you",
            predicate="preferred_action",
            value=pick,
            confidence=STUB_CONF,
            sources=list(STUB_SOURCES),
            support=[],
            weight=STUB_CONF,
            note="stub agency: preferred action",
        )
