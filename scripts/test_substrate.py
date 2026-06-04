#!/usr/bin/env python3
"""End-to-end proof that the Anima substrate's four pieces interlock.

This is the integration test the substrate's component self-tests can't be: each of
event_bus / memory_schema / telemetry / organs proves itself in ISOLATION (with
shims standing in for its siblings). This script wires the REAL four together and
drives one full turn through them, asserting the seams hold where the modules
actually meet — no shims, no models, no network, no mouth.

The turn it drives (mirrors the founder's interlock picture exactly):

    publish(QUESTION)                         telemetry.begin opens the trace
      → a TOY organ subscribed to QUESTION emits an Observation whose .memory is a
        canonical Universal-Memory-Schema object built by memory_schema.make
      → EventBus.gather_observations collects it
      → Coordinator.decide(question, [obs]) → Decision        telemetry.note_decision
      → publish(RESPONSE)                                     telemetry.commit (flush)

Then it REPLAYS the committed trace from disk and asserts the whole turn is
reconstructable: which organ contributed, which Memory id was used, and that there
was no escalation.

It also asserts the FREEZE is respected: the real Identity/Agency organs are STUBS
(interfaces present via the abstract Providers; only schema-valid, low-confidence
placeholders behind them) while ANIMA_ORGANS_LIVE is OFF — so nothing real plugged
in yet.

Run:  python3 scripts/test_substrate.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

# Make the repo importable regardless of CWD.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import memory_schema
from anima import telemetry
from anima.event_bus import Coordinator, EventBus, Observation, Question, Topic, new_turn_id
from anima.organs import (
    AgencyProvider,
    IdentityProvider,
    StubAgency,
    StubIdentity,
    agency_provider,
    identity_provider,
)
from anima.organs.base import Organ

_fails: list[str] = []


def ok(label: str, cond: bool) -> None:
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        _fails.append(label)


# ---------------------------------------------------------------------------
# A TOY organ — the canonical "real organ" stand-in the task asks for. It is a
# proper Organ: it subscribes to QUESTION and, on a Question, _emit()s ONE
# Observation carrying a Universal-Memory-Schema object. High confidence (0.98) so
# it clears the Coordinator's evidence floor — i.e. it behaves like a real organ
# would once one ships, which is the whole point of the interlock proof.
# ---------------------------------------------------------------------------
class ToyOrgan(Organ):
    name = "toy"

    async def on_question(self, bus, event) -> None:
        # The organ NEVER returns data; it builds a canonical Memory and publishes
        # an Observation. memory_schema.make is the ONE blessed constructor — the
        # same object LIRF stores, the same the bus carries, the same telemetry logs.
        await self._emit(
            bus,
            getattr(event, "turn_id", ""),
            type="fact",
            subject="Lamar",
            predicate="birthday",
            value="May 17",
            confidence=0.98,
            sources=["chat"],
            support=[],
            weight=1.0,
            note="toy organ: a known fact",
        )


async def _run_turn() -> dict:
    """Drive one full turn through the real substrate; return the replayed trace."""
    bus = EventBus()

    # Telemetry attaches as a PASSIVE peer subscriber of all four topics + error sink.
    tele = telemetry.attach(bus, "test_substrate")

    # The toy organ subscribes to QUESTION (this is what register_all does for real
    # organs; we wire one toy directly so the test owns a known, high-confidence fact).
    toy = ToyOrgan()
    bus.subscribe(Topic.QUESTION, lambda ev: toy.on_question(bus, ev))

    turn_id = new_turn_id()
    q = Question(
        text="when is Lamar's birthday?",
        name="test_substrate",
        context={"cloud_on": True, "cloud_model": "claude"},  # cloud available, not required
    )

    # 1) gather_observations publishes QUESTION (telemetry.begin fires via the bus),
    #    lets the organ emit, and returns the collected Observations.
    observations = await bus.gather_observations(q, turn_id=turn_id, timeout=0.5)

    # 2) The Coordinator decides — in code, deterministically, before any mouth.
    decision = Coordinator().decide(q, observations)

    # 3) Telemetry records the decision (it's reached off-bus, so we publish DECISION
    #    onto the bus too — telemetry's passive DECISION subscriber folds it in — AND
    #    call note_decision directly, proving both surfaces of the contract work).
    tele.note_decision(turn_id, decision)
    await bus.publish(Topic.DECISION, decision, turn_id=turn_id, source="coordinator")

    # 4) RESPONSE closes the turn → telemetry.commit flushes the append-only trace.
    await bus.publish(Topic.RESPONSE, "spoken", turn_id=turn_id, source="mouth")

    # ---- assertions on the live objects (before going to disk) ----
    # The Universal Memory Schema object the organ emitted.
    assert len(observations) == 1, f"expected exactly the toy organ's 1 observation, got {len(observations)}"
    mem = observations[0].memory

    valid, why = memory_schema.validate(mem)
    ok("the emitted memory VALIDATES against the Universal Memory Schema", valid)
    ok("schema validate() reason is 'ok'", why == "ok")
    ok("memory carries the requested fields (subject/predicate/value/confidence)",
       mem["subject"] == "Lamar" and mem["predicate"] == "birthday"
       and mem["value"] == "May 17" and mem["confidence"] == 0.98)
    ok("memory has exactly the 10 founder keys", set(mem.keys()) == set(memory_schema.KEYS))
    ok("memory id is f_-prefixed", isinstance(mem["id"], str) and mem["id"].startswith("f_"))
    ok("memory sources == ['chat']", mem["sources"] == ["chat"])
    ok("memory lirf is the cached one-line rendering", mem["lirf"] == memory_schema.to_lirf(mem))

    # The bus delivered it: the Observation the Coordinator saw is the organ's emission.
    ok("the BUS delivered the organ's observation (correct organ tag)",
       isinstance(observations[0], Observation) and observations[0].organ == "toy")
    ok("the delivered observation carries the SAME memory id the organ built",
       observations[0].memory["id"] == mem["id"])

    # The Coordinator decided from it.
    ok("the COORDINATOR produced a Decision", decision is not None)
    ok("the toy organ is a contributing organ (cleared the evidence floor)",
       "toy" in decision.contributing_organs)
    ok("the Memory id flowed into the Decision's memory_ids (provenance)",
       mem["id"] in decision.memory_ids)
    ok("model stayed local (real evidence sufficed — no need to reach out)",
       decision.model == "local")
    ok("NO escalation (local had standing to answer)", decision.escalation == "")
    ok("answer_plan is an instruction seed, not raw text", decision.answer_plan.startswith("Answer"))
    ok("answer_plan carries the evidence (the birthday value)", "May 17" in decision.answer_plan)

    # Determinism: the Coordinator is a pure function.
    again = Coordinator().decide(q, observations)
    ok("Coordinator is deterministic (same inputs → identical Decision)", again == decision)

    # ---- TELEMETRY can replay the full trace from disk ----
    trace = telemetry.replay("test_substrate", turn_id)
    return {"trace": trace, "memory_id": mem["id"], "turn_id": turn_id, "decision": decision}


def main() -> int:
    print("substrate end-to-end interlock test")
    print("=" * 64)

    # ---- FREEZE check: the real organs are STUBS, interfaces present, nothing live.
    #      (ANIMA_ORGANS_LIVE off by default — the held line until 2026-07-03.)
    os.environ.pop("ANIMA_ORGANS_LIVE", None)
    ident = identity_provider()
    agcy = agency_provider()
    ok("FREEZE: identity provider is the StubIdentity seam (no real organ)",
       isinstance(ident, StubIdentity))
    ok("FREEZE: agency provider is the StubAgency seam (no real organ)",
       isinstance(agcy, StubAgency))
    ok("FREEZE: the stub still SATISFIES the IdentityProvider interface",
       isinstance(ident, IdentityProvider))
    ok("FREEZE: the stub still SATISFIES the AgencyProvider interface",
       isinstance(agcy, AgencyProvider))
    # The interface is real (abstract) — it cannot be instantiated directly, proving
    # "interface present, no implementation" rather than an empty placeholder class.
    abstract_enforced = False
    try:
        IdentityProvider()  # type: ignore[abstract]
    except TypeError:
        abstract_enforced = True
    ok("FREEZE: IdentityProvider is abstract (can't instantiate the bare interface)",
       abstract_enforced)
    # And the stub's contributions are LOW-confidence placeholders — they could never
    # be mistaken for a real conviction (this is what keeps the freeze honest on-bus).
    cs = ident.current_state("test_substrate")
    ok("FREEZE: stub identity emits a schema-valid placeholder", memory_schema.validate(cs)[0])
    ok("FREEZE: stub confidence <= 0.3 (a placeholder, never a conviction)",
       cs["confidence"] <= 0.3 and cs["sources"] == ["stub"])

    # ---- the end-to-end turn, in a throwaway .anima so we never touch real state ----
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        os.chdir(tmp)
        # Re-point both telemetry's and metrics-style STORE at the temp dir.
        telemetry.STORE = telemetry.Path(".anima")
        try:
            result = asyncio.run(_run_turn())
        finally:
            os.chdir(cwd)
            telemetry.STORE = telemetry.Path(".anima")

    trace = result["trace"]
    mid = result["memory_id"]

    # ---- assertions on the replayed trace ----
    ok("TELEMETRY recorded a trace that replays from disk", isinstance(trace, dict))
    if isinstance(trace, dict):
        ok("replay: the turn_id matches", trace.get("turn_id") == result["turn_id"])
        ok("replay: the question text survived",
           (trace.get("question") or {}).get("text") == "when is Lamar's birthday?")
        ok("replay: exactly one observation was recorded (the toy organ's)",
           len(trace.get("observations") or []) == 1)
        obs0 = (trace.get("observations") or [{}])[0]
        ok("replay: the contributing ORGAN is recorded ('toy')", obs0.get("organ") == "toy")
        ok("replay: the MEMORY ID used is recorded", obs0.get("memory_id") == mid)
        ok("replay: the memory's confidence survived (0.98)", obs0.get("confidence") == 0.98)
        dec = trace.get("decision") or {}
        ok("replay: the decision recorded the contributing organ", dec.get("contributing_organs") == ["toy"])
        ok("replay: the decision recorded the memory id used", dec.get("memory_ids") == [mid])
        ok("replay: NO ESCALATION is recorded (escalated == False)", dec.get("escalated") is False)
        ok("replay: the committed trace is timestamped ISO8601-Z",
           isinstance(trace.get("committed"), str) and trace["committed"].endswith("Z"))
        ok("replay: no handler errors were recorded for a clean turn",
           (trace.get("errors") or []) == [])

    print("=" * 64)
    if _fails:
        print(f"FAILED ({len(_fails)}): " + "; ".join(_fails))
        return 1
    print("ALL SUBSTRATE INTERLOCK CHECKS PASSED — the four pieces cohere end-to-end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
