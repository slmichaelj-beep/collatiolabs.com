#!/usr/bin/env python3
"""
certify_meaning_conservation — was what MATTERED preserved (not just the bytes)?

Data conservation asks "was the INFORMATION preserved?". MEANING conservation asks the harder,
Law-003 question one level up: for an utterance, what is its MEANING — the significance a
companion of thirty years would carry — and did THAT survive the pipeline, even where the
literal words did not? This certifies that measure ON A REAL CAPTURE, through the SAME engine
(anima.meaning_conservation) + observatory (scripts/meaning_conservation.py) the Final Digital
Mind cert and the CLI observatory drive, on the founder's worked example
("My daughter Maya started kindergarten last week"):

  A. LITERAL vs MEANING — literal_units extracts the data-layer tokens (maya, kindergarten);
     meaning_units DERIVES the significance: a LIFE_EVENT (started kindergarten), a
     RELATIONAL_WEIGHT (the daughter bond), and a MILESTONE — every unit rolled up into the
     MEANING dimension. The two layers are distinct (meaning is not just the tokens).
  B. THE #1 RULE — MEANING IS DERIVED, NEVER INVENTED — every emitted unit's grounding surface
     literally appears in the utterance AND it carries non-empty structural evidence (a world
     edge / a reported_feeling row / a milestone trait). An UNGROUNDED candidate ("graduation",
     a word never said) is REJECTED (_ground -> None); no statement trips the no-diagnosis wall.
  C. THE REAL CAPTURE (the live measure) — the observatory's meaning_ledger runs the REAL
     engines on a real capture inside a hermetic temp store: memory_lirf.capture +
     world_state.capture_relations PERSIST to disk, Facts/World reload FROM DISK, and the
     CAPTURED/STORED/SURFACEABLE gates are built from the live engines (STORED from the on-disk
     reload, SURFACEABLE from meaning.significance + review.daily_review). The Maya meaning
     RIDES THROUGH — it is CAPTURED, STORED, and SURFACEABLE — proving what MATTERED was kept,
     not merely the bytes; nothing is dropped silently (each lost unit names its loss_reason).
  D. THE FOUR RATES — conservation_rates returns literal/meaning/emotional_tone/life_event, each
     a probability in [0,1]; MEANING conservation is 1.0 when every unit is retained; and the
     routinely-thin EMOTIONAL-TONE class, when absent from the gates, is FLAGGED with a CAPTURE
     loss_reason (counted + attributed, never silent).

Hermetic + offline (no model, no network): every engine store (memory_lirf/world_state/meaning/
review/curiosity/constitution/reliability/telemetry/cloud) is redirected to a throwaway dir —
both via gate0's _temp_store and the observatory's own redirect — and the real .anima is
fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

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


# The engine stores the meaning pipeline's STORED/SURFACEABLE legs touch that gate0's
# _temp_store does NOT redirect (it covers memory_lirf/world_state/meaning/review/... but not
# reliability's DEFAULT_STORE) — we redirect them ourselves inside the with-block and restore in
# finally, so the real .anima can never be written by the live capture.
_EXTRA_TARGETS = (
    ("anima.memory_lirf", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.review", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.constitution", "STORE"),
    ("anima.reliability", "DEFAULT_STORE"),
    ("anima.telemetry", "STORE"),
    ("anima.cloud", "STORE"),
)


def _load_observatory():
    """Import the Meaning-Conservation OBSERVATORY (scripts/meaning_conservation.py) as a module
    — it drives the REAL engines on a real capture (memory_lirf.capture + world_state.
    capture_relations -> disk -> reload -> meaning.significance + review.daily_review). Loaded by
    path so it never shadows the engine package anima.meaning_conservation."""
    spec = importlib.util.spec_from_file_location(
        "mc_observatory", str(ROOT / "scripts" / "meaning_conservation.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    from anima import meaning_conservation as mc
    obs = _load_observatory()
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("MEANING CONSERVATION — was what MATTERED preserved (not just the bytes)?")
    print("=" * 72)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    MAYA = "My daughter Maya started kindergarten last week"
    STRESS = "I've been really stressed about the Q3 launch"

    # --- pure-function legs (no store) are exercised outside the with-block too --------------
    idx = mc._input_index(MAYA)
    # B (part): an UNGROUNDED meaning ("graduation" — a real life-event word the Maya utterance
    # never says) MUST be refused; a no-grounding candidate MUST be refused. The never-confabulate
    # proof, independent of any store.
    invented = mc._ground(mc.KIND_LIFE_EVENT, "graduation", "A milestone — they graduated.",
                          "graduation", {"predicate": "graduated", "source": "world_state"},
                          (mc.MEANING, mc.LIFE_EVENT), idx)
    ck("B0: an UNGROUNDED meaning ('graduation', never said) is REJECTED (#1 rule, pure)",
       invented is None)
    ck("B0b: a meaning with NO grounding surface is refused",
       mc._ground(mc.KIND_THEME, "x", "y", "", {}, (mc.MEANING,), idx) is None)

    saved = []
    with _temp_store():
        # belt-and-suspenders: redirect the engine stores gate0 doesn't cover, into the SAME
        # temp dir, so the real .anima can never be touched by the real capture path.
        tmp = None
        try:
            import anima.memory_lirf as _ml
            tmp = getattr(_ml, "STORE", None)
        except Exception:
            tmp = None
        for modname, attr in _EXTRA_TARGETS:
            try:
                m = __import__(modname, fromlist=["_"])
            except Exception:
                continue
            saved.append((m, attr, getattr(m, attr, None)))
            if tmp is not None and getattr(m, attr, None) is not None:
                setattr(m, attr, tmp)
        try:
            # ---- A. LITERAL vs MEANING --------------------------------------------------
            lits = {u["key"] for u in mc.literal_units(MAYA)}
            ck("A1: literal_units extracts the data-layer tokens (maya, kindergarten)",
               "maya" in lits and "kindergarten" in lits)
            units = mc.meaning_units(MAYA)
            kinds = {u["kind"] for u in units}
            dims = {d for u in units for d in u["dimensions"]}
            ck("A2: meaning_units DERIVES a LIFE_EVENT unit (started kindergarten)",
               mc.KIND_LIFE_EVENT in kinds and mc.LIFE_EVENT in dims)
            ck("A3: meaning_units DERIVES a RELATIONAL_WEIGHT unit (the daughter bond)",
               mc.KIND_RELATIONAL in kinds)
            ck("A4: meaning_units DERIVES a MILESTONE unit (a child in their life)",
               mc.KIND_MILESTONE in kinds)
            ck("A5: every meaning unit rolls up into the MEANING dimension",
               len(units) >= 3 and all(mc.MEANING in u["dimensions"] for u in units))
            ck("A6: MEANING is more than the literal tokens (the two layers are distinct)",
               {u["subject"] for u in units} != lits)

            # ---- B. THE #1 RULE — DERIVED, NEVER INVENTED -------------------------------
            ck("B1: every emitted unit's grounding surface IS in the utterance",
               all(mc._grounded_surface(u["grounded_in"], idx) is not None for u in units))
            ck("B2: every emitted unit carries non-empty STRUCTURAL evidence (edge/row/trait)",
               all(isinstance(u.get("evidence"), dict) and u["evidence"] for u in units))
            ck("B3: the worked example: 'kindergarten' grounds a LIFE_EVENT meaning unit",
               any(u["kind"] == mc.KIND_LIFE_EVENT and "kindergarten" in u["grounded_in"]
                   for u in units))
            ck("B4: no emitted unit was grounded on a word ('graduation') absent from the input",
               not any("graduation" in u["grounded_in"] for u in units))
            ck("B5: NO meaning-unit statement trips the no-diagnosis wall",
               all(mc._is_clean(u["statement"]) for u in units))

            # ---- C. THE REAL CAPTURE (the live measure) --------------------------------
            # meaning_ledger runs the REAL engines on a real capture inside a hermetic temp
            # store: memory_lirf.capture + world_state.capture_relations PERSIST to disk,
            # Facts/World reload FROM DISK, and the gates come from meaning.significance +
            # review.daily_review. This is the live conservation measure on a real capture.
            led = obs.meaning_ledger(MAYA)
            ck("C1: the ledger ran the real engines and produced literal + meaning + traces",
               isinstance(led, dict) and led.get("meaning") and led.get("meaning_trace")
               and led.get("literal"))
            mtrace = led["meaning_trace"]
            ck("C2: the real capture SAW the meaning — at least one unit reached CAPTURED",
               any(t.get(mc.CAPTURED) for t in mtrace))
            ck("C3: the meaning is DURABLE — at least one unit survived the on-disk reload (STORED)",
               any(t.get(mc.STORED) for t in mtrace))
            # the load-bearing claim: what MATTERED is re-surfaceable, not just on disk.
            surfaceable = [t for t in mtrace if t.get(mc.SURFACEABLE)]
            ck("C4: the Maya meaning is SURFACEABLE — its significance re-surfaces (what MATTERED "
               "rode through, not just the bytes)", len(surfaceable) >= 1)
            ck("C5: the daughter/kindergarten significance specifically rode through to surfaceable",
               any(t.get(mc.SURFACEABLE) and (
                   "kindergarten" in mc._unit_keys(t) or "daughter" in mc._unit_keys(t)
                   or "maya" in mc._unit_keys(t)) for t in mtrace))
            # nothing dropped silently: every NON-surfaceable unit names the first gate it failed.
            ck("C6: nothing is dropped silently — every lost unit names a loss_reason",
               all(t.get("loss_reason") for t in mtrace if not t.get(mc.SURFACEABLE)))
            # the gates are MONOTONE in the engine walk (surfaceable => stored => captured).
            ck("C7: the retention gates are monotone (surfaceable implies stored implies captured)",
               all((not t.get(mc.SURFACEABLE) or t.get(mc.STORED)) and
                   (not t.get(mc.STORED) or t.get(mc.CAPTURED)) for t in mtrace))

            # ---- D. THE FOUR RATES -----------------------------------------------------
            rates = led["rates"]
            ck("D1: all four rates present (literal/meaning/emotional_tone/life_event)",
               set(rates.keys()) == {"literal", "meaning", "emotional_tone", "life_event"})
            ck("D2: every rate is a probability in [0,1]",
               all(0.0 <= rates[k]["rate"] <= 1.0 for k in rates))
            ck("D3: the MEANING rate equals retained/total of the meaning units (a real fraction)",
               rates["meaning"]["total"] == len(mtrace)
               and rates["meaning"]["retained"] == len(surfaceable))

            # the four conservation_rates over hand-built traces: MEANING == 1.0 iff all retained,
            # and a tone unit absent from the gates is flagged with a CAPTURE loss_reason.
            full_gates = {g: set().union(*[mc._unit_keys(u) for u in units]) for g in mc.GATES}
            full_traces = mc.retention_of(units, full_gates)
            full_rates = mc.conservation_rates([], full_traces)
            ck("D4: MEANING conservation is 1.0 when EVERY meaning unit is retained",
               full_rates["meaning"]["rate"] == 1.0)

            tone_units = [u for u in mc.meaning_units(STRESS) if u["kind"] == mc.KIND_TONE]
            ck("D5: the stress line derives an EMOTIONAL_TONE unit from the user's reported feeling "
               "(the user's stated affect, never Vera's state)",
               any("stressed" in u["grounded_in"] for u in tone_units)
               and any(u["evidence"].get("trait") == "reported_feeling" for u in tone_units))
            # walk the tone units against EMPTY gates: the routinely-thin class is dropped at
            # CAPTURE with a named loss_reason — counted + attributed, never silent.
            dropped = mc.retention_of(tone_units, {g: set() for g in mc.GATES})
            ck("D6: an emotional-tone unit absent from the gates is FLAGGED (not silent) at CAPTURE",
               bool(dropped) and all(not t.get(mc.SURFACEABLE) and t.get("loss_reason")
                                     and "not captured" in t["loss_reason"] for t in dropped))
            tone_rate = mc.conservation_rates([], dropped)["emotional_tone"]
            ck("D7: the EMOTIONAL-TONE rate counts only tone-dimension units and reflects the loss",
               tone_rate["total"] == len(tone_units) and tone_rate["rate"] == 0.0)
        finally:
            for m, attr, old in saved:
                if old is not None:
                    setattr(m, attr, old)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nMEANING-CONSERVATION CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
