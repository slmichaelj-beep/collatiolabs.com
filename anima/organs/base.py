"""base — the shared organ contract.

An organ is the moonshot's unit of contribution. It is subscribed to
``Topic.QUESTION`` on the EventBus and, when a turn arrives, builds zero or more
canonical ``Memory`` objects and *publishes* each onto ``Topic.OBSERVATION``.

Three rules, load-bearing and stated once:

1.  **An organ NEVER returns data.** It calls :meth:`Organ._emit`, which wraps a
    canonical ``Memory`` in an ``Observation`` and ``publish``es it. The mouth
    never reads an organ's return value; the Coordinator decides from the
    Observations on the bus.
2.  **Every emitted payload is a canonical ``Memory``** built by
    ``memory_schema.make`` — the exact same object ``memory_lirf.LIRF`` stores.
    No organ invents its own format.
3.  **Stubs are seams, gated default-OFF** (see ``organs/__init__.py``). The real
    Identity Core and Agency stay HELD until the 2026-07-03 window closes; the
    flag is the line between a wired seam and a live organ.

This module is deliberately dependency-light. ``memory_schema`` and ``event_bus``
are sibling deliverables on the same substrate; until they land, the small shims
below provide a contract-identical ``make``/``validate`` and ``Observation``/
``Topic`` so an organ can be exercised end-to-end in isolation. The shims defer to
the real modules the instant they are importable, so nothing changes at wiring
time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

# ---------------------------------------------------------------------------
# Timestamp / id helpers — reuse the ledger's canonical generators verbatim so
# every organ stamps the exact same ISO8601-Z / f_-prefixed shapes as LIRF.
# Falls back to identical local definitions if memory_lirf can't be imported in
# a bare unit-test context.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from ..memory_lirf import SELF, _new_id, _now
except Exception:  # pragma: no cover - isolation fallback
    import secrets
    from datetime import datetime, timezone

    SELF = "you"

    def _now() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _new_id() -> str:
        return "f_" + secrets.token_hex(6)


# ---------------------------------------------------------------------------
# memory_schema shim — prefer the canonical module; otherwise a contract-faithful
# local implementation of make()/validate()/to_lirf() so organs stay testable now.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from .. import memory_schema as _schema  # type: ignore
except Exception:  # pragma: no cover - isolation fallback
    _schema = None


_MEM_TYPES = {"fact", "value", "relationship", "narrative", "agency"}


def _fallback_to_lirf(mem: dict) -> str:
    conf = mem.get("confidence", 0.0)
    n = len(mem.get("support") or [])
    tail = f"  (conf {conf:.2f}" + (f", x{n}" if n else "") + ")"
    return f"{mem.get('subject', '?')} · {mem.get('predicate', '?')} = {mem.get('value')}" + tail


def _fallback_make(
    *,
    type: str,
    subject: str,
    predicate: str,
    value: Any,
    confidence: float,
    sources: list | None = None,
    support: list | None = None,
    id: str | None = None,
    updated: str | None = None,
) -> dict:
    mem = {
        "id": id or _new_id(),
        "type": type,
        "subject": subject,
        "predicate": predicate,
        "value": value,
        "confidence": float(confidence),
        "sources": list(sources or []),
        "support": list(support or []),
        "updated": updated or _now(),
    }
    mem["lirf"] = _fallback_to_lirf(mem)
    return mem


def _fallback_validate(mem: dict) -> tuple[bool, str]:
    if not isinstance(mem, dict):
        return (False, "not a memory")
    required = (
        "id",
        "type",
        "subject",
        "predicate",
        "value",
        "confidence",
        "sources",
        "support",
        "updated",
        "lirf",
    )
    for k in required:
        if k not in mem:
            return (False, f"missing key: {k}")
    if mem["type"] not in _MEM_TYPES:
        return (False, f"bad type: {mem['type']}")
    if not isinstance(mem["subject"], str) or not mem["subject"]:
        return (False, "subject must be non-empty str")
    if not isinstance(mem["predicate"], str) or not mem["predicate"]:
        return (False, "predicate must be non-empty str")
    c = mem["confidence"]
    if not isinstance(c, (int, float)) or isinstance(c, bool) or not (0.0 <= c <= 1.0):
        return (False, "confidence must be a float in [0,1]")
    for k in ("sources", "support"):
        v = mem[k]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            return (False, f"{k} must be a list of str")
    if not isinstance(mem["updated"], str) or not mem["updated"]:
        return (False, "updated must be ISO8601 str")
    return (True, "ok")


def schema_make(**kw) -> dict:
    """Build a canonical Memory via memory_schema.make, or the faithful fallback."""
    if _schema is not None and hasattr(_schema, "make"):
        return _schema.make(**kw)
    return _fallback_make(**kw)


def schema_validate(mem: dict) -> tuple[bool, str]:
    """Validate a Memory via memory_schema.validate, or the faithful fallback."""
    if _schema is not None and hasattr(_schema, "validate"):
        return _schema.validate(mem)
    return _fallback_validate(mem)


# ---------------------------------------------------------------------------
# event_bus shim — prefer the real Observation/Topic; otherwise minimal stand-ins
# with the same field names so _emit() and the self-test run with no bus present.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from ..event_bus import Observation, Topic  # type: ignore
except Exception:  # pragma: no cover - isolation fallback
    from dataclasses import dataclass, field
    from enum import Enum

    class Topic(str, Enum):
        QUESTION = "question"
        OBSERVATION = "observation"
        DECISION = "decision"
        RESPONSE = "response"

    @dataclass(frozen=True)
    class Observation:  # mirrors event_bus.Observation exactly
        organ: str
        memory: dict
        weight: float = 1.0
        note: str = ""


# ---------------------------------------------------------------------------
# The organ contract.
# ---------------------------------------------------------------------------
class Organ(ABC):
    """Abstract base every organ implements.

    Concrete organs override :meth:`on_question` to decide *what* to contribute
    for a given turn, then call :meth:`_emit` (one or more times) to speak. They
    never return data and never touch the mouth.
    """

    #: short, stable organ name ("identity", "agency", ...). Set on the subclass.
    name: str = "organ"

    @abstractmethod
    async def on_question(self, bus, event) -> None:
        """Handle a published ``Topic.QUESTION`` event.

        Implementations inspect ``event`` (a ``Question``-bearing envelope), build
        0..n Observations, and publish each via :meth:`_emit`. This coroutine is
        what ``register_all`` subscribes onto ``Topic.QUESTION``.

        Must never raise into the bus: the EventBus captures handler exceptions and
        surfaces them to telemetry, but an organ should still fail soft.
        """
        raise NotImplementedError

    async def _emit(
        self,
        bus,
        turn_id: str,
        *,
        type: str,
        subject: str,
        predicate: str,
        value: Any,
        confidence: float,
        sources: list | None = None,
        support: list | None = None,
        weight: float = 1.0,
        note: str = "",
    ) -> dict:
        """The ONE way an organ speaks.

        Builds a canonical Memory (``memory_schema.make``), wraps it in an
        ``Observation`` tagged with this organ's name, and publishes it onto
        ``Topic.OBSERVATION`` for the given ``turn_id``. Returns the Memory dict so
        callers/tests can inspect what was emitted (the return is a courtesy for
        testing only — the bus, not the return value, is the real channel).

        Guarantees every organ's output is schema-valid before it touches the bus.
        """
        mem = schema_make(
            type=type,
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=confidence,
            sources=list(sources or []),
            support=list(support or []),
        )
        ok, why = schema_validate(mem)
        if not ok:
            # A malformed Memory must never reach the bus. Fail soft, stay silent
            # on the wire, and let the (optional) telemetry path notice the gap.
            raise ValueError(f"{self.name}: refusing to emit invalid memory: {why}")
        obs = Observation(organ=self.name, memory=mem, weight=float(weight), note=note)
        if bus is not None:
            await bus.publish(Topic.OBSERVATION, obs, turn_id=turn_id, source=self.name)
        return mem
