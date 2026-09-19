#!/usr/bin/env python3
"""
certify_event_bus — the substrate Event Bus: a published event REACHES every subscriber and is
RECORDED + REPLAYABLE, with fail-safe fan-out. Hermetic + offline (no model, no network).

event_bus.py is the moonshot's spine: organs don't call each other, they REACT to events. This
certifies the bus's load-bearing transport contract through the SAME passive recorder the substrate
uses — `telemetry.attach(bus, name)` — so the path proven is publish -> real subscriber delivery ->
real on-disk telemetry record -> real replay, not a unit in a vacuum:

  A. DELIVERY — gather_observations(Question) publishes Topic.QUESTION; a real organ-like subscriber
     FIRES and emits an Observation onto Topic.OBSERVATION; a passive peer subscriber sees the SAME
     Observation; the bus returns the collected Observation list (the Coordinator's await point).
  B. RECORDED + REPLAYABLE — a Telemetry recorder attached via telemetry.attach saw those very events;
     after the Coordinator's Decision is published on DECISION and a RESPONSE closes the turn, the
     recorder COMMITTED exactly one trace to .anima/{name}.telemetry.jsonl (in the REDIRECTED temp
     store) and telemetry.replay(name, turn_id) reads back the question text, the observation's
     Memory id + confidence, and the decision (model + contributing organ + memory id). Real delivery
     -> real durable record -> real replay.
  C. PURE COORDINATOR — Coordinator.decide(question, observations) is deterministic and ranks the real
     fact above a low-confidence stub (stub does NOT clear the evidence floor); identical inputs ->
     identical Decision.
  D. FAIL-SAFE FAN-OUT — a handler that raises does NOT drop its sibling, and the exception is
     surfaced to the error sink (telemetry records it as a turn error, never re-raised into the turn).
  E. DISCIPLINE — subscribe is idempotent (no double delivery), unsubscribe stops delivery, publish to
     a topic with no subscribers is a clean no-op, and Event is a frozen ISO8601-Z-stamped record.

Hermetic: telemetry.STORE is redirected by _temp_store (telemetry is in its _STORE_MODULES set), so
every committed trace lands in the temp dir; the real .anima is fingerprinted before/after and
asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import event_bus as eb, telemetry
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("EVENT BUS — publish reaches subscribers + is recorded/replayable, fail-safe fan-out")
    print("=" * 84)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # ---- E (pure, store-free): Event is a frozen, auto-stamped record -------------------
    ev = eb.Event(topic=eb.Topic.QUESTION, turn_id="t1", payload="x")
    ck("E0a: Event auto-stamps an ISO8601-Z ts", isinstance(ev.ts, str) and ev.ts.endswith("Z"))
    frozen_ok = False
    try:
        ev.turn_id = "t2"      # type: ignore[misc]
    except Exception:
        frozen_ok = True
    ck("E0b: Event is frozen (an immutable 'this happened' record)", frozen_ok)
    ck("E0c: Topic is a closed 4-channel enum and is its own wire string",
       len(list(eb.Topic)) == 4 and eb.Topic.QUESTION == "question")

    # Capture results out of the async scenario so the checks run at module scope.
    box: dict = {}

    async def scenario() -> None:
        # The bus + a REAL passive telemetry recorder wired exactly as the substrate wires it.
        bus = eb.EventBus()
        name = "EventBusCert"
        rec = telemetry.attach(bus, name)               # passive peer subscriber on all 4 topics

        # A real organ-like subscriber: reacts to QUESTION by publishing one Observation whose
        # .memory is a canonical Memory dict (the bus reads only id/confidence). NO model, NO I/O.
        async def identity_organ(event):
            mem = eb._fake_memory(mid="f_evbus_real01", subject="you", predicate="birthday",
                                  value="1990-06-11", confidence=0.97,
                                  lirf="you · birthday = 1990-06-11  (conf 0.97)")
            await bus.publish(eb.Topic.OBSERVATION,
                              eb.Observation(organ="identity", memory=mem, weight=1.0, note="known fact"),
                              turn_id=event.turn_id, source="identity")

        # A low-confidence stub organ: must inform the trace but NOT outrank the real fact.
        async def stub_agency(event):
            mem = eb._fake_memory(mid="f_evbus_stub02", subject="you", predicate="preferred_action",
                                  value="defer", confidence=0.2)
            await bus.publish(eb.Topic.OBSERVATION,
                              eb.Observation(organ="agency", memory=mem, weight=0.5, note="stub"),
                              turn_id=event.turn_id, source="agency")

        # A passive peer subscriber (a second, independent consumer of OBSERVATION).
        peer_seen: list[str] = []

        async def peer(event):
            if event.topic is eb.Topic.OBSERVATION:
                peer_seen.append(event.payload.memory["id"])

        bus.subscribe(eb.Topic.QUESTION, identity_organ)
        bus.subscribe(eb.Topic.QUESTION, stub_agency)
        bus.subscribe(eb.Topic.OBSERVATION, peer)

        turn_id = eb.new_turn_id()
        q = eb.Question(text="when's my birthday?", name=name,
                        context={"cloud_on": True, "cloud_model": "claude"})

        # ---- A. DELIVERY ---------------------------------------------------------------
        obs = await bus.gather_observations(q, turn_id=turn_id, timeout=0.5)
        box["deliver_count"] = len(obs)
        box["peer_saw_same"] = sorted(peer_seen) == sorted(o.memory["id"] for o in obs)
        box["real_obs_present"] = any(o.memory.get("id") == "f_evbus_real01" for o in obs)

        # ---- C. PURE COORDINATOR -------------------------------------------------------
        decision = eb.Coordinator().decide(q, obs)
        box["decision_is_decision"] = isinstance(decision, eb.Decision)
        box["real_contributed"] = "identity" in decision.contributing_organs
        box["stub_filtered"] = "agency" not in decision.contributing_organs
        box["mid_in_decision"] = "f_evbus_real01" in decision.memory_ids
        box["deterministic"] = (eb.Coordinator().decide(q, obs) == decision)

        # Publish the verdict + close the turn on the bus, so the ATTACHED recorder folds in the
        # decision and FLUSHES the trace to disk (DECISION -> note_decision, RESPONSE -> commit).
        await bus.publish(eb.Topic.DECISION, decision, turn_id=turn_id, source="coordinator")
        await bus.publish(eb.Topic.RESPONSE, "ok", turn_id=turn_id, source="mouth")

        # ---- B. RECORDED + REPLAYABLE (real on-disk telemetry, redirected store) -------
        tr = telemetry.replay(name, turn_id)
        box["replay_exists"] = isinstance(tr, dict)
        if isinstance(tr, dict):
            box["replay_committed"] = bool(tr.get("committed"))
            box["replay_question"] = (tr.get("question") or {}).get("text") == "when's my birthday?"
            rec_obs = tr.get("observations") or []
            ids = {o.get("memory_id") for o in rec_obs}
            box["replay_obs_id"] = "f_evbus_real01" in ids
            box["replay_obs_conf"] = any(o.get("confidence") == 0.97 for o in rec_obs)
            dec = tr.get("decision") or {}
            box["replay_decision"] = (dec.get("model") == "local"
                                      and "identity" in (dec.get("contributing_organs") or [])
                                      and "f_evbus_real01" in (dec.get("memory_ids") or []))
        else:
            box["replay_committed"] = box["replay_question"] = box["replay_obs_id"] = False
            box["replay_obs_conf"] = box["replay_decision"] = False
        # Exactly ONE trace for this turn (append-only, one line per closed turn).
        box["one_trace"] = sum(1 for r in telemetry.bus_traces(name)
                               if r.get("turn_id") == turn_id) == 1
        # The recorder we attached is the one that recorded it (sanity on the live wire).
        box["recorder_is_telemetry"] = isinstance(rec, telemetry.Telemetry)

        # ---- D. FAIL-SAFE FAN-OUT ------------------------------------------------------
        bus2 = eb.EventBus()
        rec2 = telemetry.attach(bus2, name + "_fail")
        ran: list[str] = []

        async def boom(event):
            raise RuntimeError("organ exploded")

        async def good(event):
            ran.append("ran")

        bus2.subscribe(eb.Topic.QUESTION, boom)
        bus2.subscribe(eb.Topic.QUESTION, good)
        ftid = eb.new_turn_id()
        await bus2.publish(eb.Topic.QUESTION, eb.Question(text="x", name=name + "_fail"),
                           turn_id=ftid, source="bus")
        await bus2.publish(eb.Topic.RESPONSE, "ok", turn_id=ftid, source="mouth")
        box["sibling_survived"] = ran == ["ran"]
        ftr = telemetry.replay(name + "_fail", ftid)
        box["error_surfaced"] = (isinstance(ftr, dict)
                                 and any(e.get("type") == "RuntimeError"
                                         for e in (ftr.get("errors") or [])))
        # rec2 referenced so the wiring is explicit (attach returns the recorder under test).
        box["fail_recorder"] = isinstance(rec2, telemetry.Telemetry)

        # ---- E. DISCIPLINE -------------------------------------------------------------
        bus3 = eb.EventBus()
        hits: list[int] = []

        async def once(event):
            hits.append(1)

        bus3.subscribe(eb.Topic.RESPONSE, once)
        bus3.subscribe(eb.Topic.RESPONSE, once)        # duplicate -> must NOT double-deliver
        await bus3.publish(eb.Topic.RESPONSE, "done", turn_id="f_disc", source="x")
        box["idempotent"] = len(hits) == 1
        bus3.unsubscribe(eb.Topic.RESPONSE, once)
        await bus3.publish(eb.Topic.RESPONSE, "done", turn_id="f_disc", source="x")
        box["unsub_stops"] = len(hits) == 1
        await bus3.publish(eb.Topic.DECISION, "nobody listening", turn_id="f_x", source="x")
        box["empty_noop"] = True   # reaching here without raising IS the no-op proof

    with _temp_store():
        # telemetry.STORE is redirected by _temp_store, so every committed trace lands in temp.
        asyncio.run(scenario())

    # ---- A ---------------------------------------------------------------------------------
    ck("A1: gather_observations delivered BOTH subscribed organs' observations",
       box.get("deliver_count") == 2)
    ck("A2: the real fact organ's Observation is present (publish reached the subscriber)",
       box.get("real_obs_present") is True)
    ck("A3: a passive peer subscriber saw the SAME observations (concurrent fan-out)",
       box.get("peer_saw_same") is True)

    # ---- B ---------------------------------------------------------------------------------
    ck("B1: the attached telemetry recorder COMMITTED a trace (recorded on RESPONSE)",
       box.get("replay_exists") is True and box.get("replay_committed") is True)
    ck("B2: replay reads back the question text that was published",
       box.get("replay_question") is True)
    ck("B3: replay carries the observation's Memory id AND its confidence (provenance recorded)",
       box.get("replay_obs_id") is True and box.get("replay_obs_conf") is True)
    ck("B4: replay carries the Decision (model + contributing organ + memory id)",
       box.get("replay_decision") is True)
    ck("B5: exactly ONE append-only trace was flushed for the turn",
       box.get("one_trace") is True)
    ck("B6: the recorder under test IS a real telemetry.Telemetry (live wire, not a mock)",
       box.get("recorder_is_telemetry") is True)

    # ---- C ---------------------------------------------------------------------------------
    ck("C1: Coordinator.decide returns a Decision", box.get("decision_is_decision") is True)
    ck("C2: the real fact contributed; the low-conf stub did NOT clear the evidence floor",
       box.get("real_contributed") is True and box.get("stub_filtered") is True)
    ck("C3: the real Memory.id flowed into the Decision", box.get("mid_in_decision") is True)
    ck("C4: the Coordinator is deterministic (same inputs -> identical Decision)",
       box.get("deterministic") is True)

    # ---- D ---------------------------------------------------------------------------------
    ck("D1: a raising handler did NOT drop its sibling (the turn is sacred)",
       box.get("sibling_survived") is True)
    ck("D2: the exception was surfaced to the error sink and recorded against the turn",
       box.get("error_surfaced") is True)

    # ---- E ---------------------------------------------------------------------------------
    ck("E1: subscribe is idempotent (no double delivery)", box.get("idempotent") is True)
    ck("E2: unsubscribe stops delivery", box.get("unsub_stops") is True)
    ck("E3: publish to a topic with no subscribers is a clean no-op", box.get("empty_noop") is True)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nEVENT-BUS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
