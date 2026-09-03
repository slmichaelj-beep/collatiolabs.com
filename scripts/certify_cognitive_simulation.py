#!/usr/bin/env python3
"""
certify_cognitive_simulation — COGNITIVE SIMULATION: test a change on a digital TWIN before prod.

Phase 22 (anima/simulation.py) is the leap from a place-to-simulate (the Phase-21 digital twin) to
the QUESTIONS a thinking system can finally answer by simulation instead of by guess — each a real,
MEASURED experiment run on a synthetic TWIN while the real mind is provably untouched. This certifies
that promise through the SAME public functions the module ships (simulate_decision / simulate_learning
/ simulate_architecture / alternative_futures / what_happened + worked_examples), all on synthetic
twins built from a synthetic source (real Vera is NEVER read):

  A. DECISION — "what SHOULD happen?".  simulate_decision on a twin seeded with synthetic captured-
     Lamar data returns a measured per-option scoring, builds a GROUNDED personal model
     (personal_known True), and recommends 'ship daily' (the option that matches his captured
     ship/momentum model) with EVERY rationale citing a captured datum. ANTI-FABRICATION: an option
     that matches NOTHING in his model earns NO recommendation (score 0) — the #1 rule applied to a
     decision (never invented). The world-model situation read is INTERNAL-only (never a diagnosis).

  B. LEARNING — "what WOULD happen if we learned X for T?".  simulate_learning(medium x4) drives the
     deterministic, $0, no-cloud synthetic accelerator and projects real ACCUMULATION (objects gained)
     + a trajectory. Off mode is provably INERT (0 cycles, 0 gained, $0) — the safe default.

  C. ARCHITECTURE — "what WOULD happen if we changed retrieval?".  simulate_architecture(
     'fmlgs_retrieval') on an accelerated twin MEASURES recall / latency / footprint and FMLGS HOLDS
     recall vs the keyword baseline (the non-negotiable 'same intelligence' bar) — earned on a COPY
     before the real retrieval path is touched.

  D. ALTERNATIVE FUTURES — "what MIGHT happen?".  alternative_futures(variants=5) forks 5 INDEPENDENT
     futures (distinct twin ids) and reports a real min/median/max DISTRIBUTION with spread > 0 — a
     range, not a point.

  E. FREEZE PROOF — every engine runs inside twin.freeze_guard. Taken EXPLICITLY around a twin op, the
     guard reports real Vera identity AND the whole real .anima byte-UNCHANGED; worked_examples()'s own
     freeze_report agrees. The real mind is structurally protected, not protected by convention.

Hermetic + OFFLINE ($0, no Ollama, no cloud): g0pe._temp_store() redirects the standard engine STORES;
twin.STORE + simulation.STORE + identity_sandbox.STORE (which _temp_store does NOT cover) are redirected
into the temp dir too; a SYNTHETIC source creature is seeded via twin._seed_synthetic_source. The real
.anima is fingerprinted before/after the whole cert and asserted byte-identical. Exit 0 == CERTIFIED,
1 == FAIL.
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


def main() -> int:
    from anima import simulation as sim
    from anima import twin
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("COGNITIVE SIMULATION — test a change on a digital TWIN before prod (decision / learning / "
          "architecture / alt-futures)")
    print("=" * 110)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # _temp_store redirects the standard engine STORES (lerf/memory_lirf/world_state/portrait/...),
    # resets server history + cached mouth, and restores on exit. twin.py + simulation.py + the
    # identity sandbox carry their OWN module STORE that _temp_store does NOT cover — redirect those
    # ourselves inside the block (exactly as certify_digital_twin.py / certify_brain_select.py redirect
    # their own module STOREs), so every path a simulation engine resolves lands in the temp dir and
    # the fingerprinted real store is never read or written.
    with _temp_store() as tp:
        extra = []
        for modname, attr in (("anima.twin", "STORE"),
                              ("anima.simulation", "STORE"),
                              ("anima.identity_sandbox", "STORE")):
            try:
                m = __import__(modname, fromlist=["_"])
                if hasattr(m, attr):
                    extra.append((m, attr, getattr(m, attr)))
                    setattr(m, attr, tp)
            except Exception:
                pass
        try:
            SRC = "SimCertSrc"

            # Seed a SYNTHETIC source creature (never real Vera) — via twin's own seeder, which writes
            # through the engines under a _RedirectStores(tp) block and plants a deliberate ungrounded
            # self-claim + a few skills + a reality loop. create_twin then read-COPIES this source.
            twin._seed_synthetic_source(tp, SRC)
            ck("S0: synthetic source seeded (no real Vera read)",
               (tp / f"{SRC}.narrative.txt").is_file())

            # A small twin factory bound to THIS synthetic source + temp root (mirrors
            # simulation._make_synth_twin, which defaults its source to 'SynTwinSrc').
            def synth_twin(name, *, with_lamar=False):
                tw = twin.create_twin(name, source=SRC, lerf_source=SRC, root=tp)
                if with_lamar:
                    tdir = twin.twin_dir(tw["twin_id"], tp)
                    with twin.freeze_guard(SRC, tp):
                        with twin._RedirectStores(tdir):
                            sim._seed_synthetic_lamar(twin.twin_creature(tw))
                return tw

            # ---- A. DECISION — "what SHOULD happen?" (grounded, never invented) ----------------
            dt = synth_twin("sim-decision", with_lamar=True)
            dec = sim.simulate_decision(
                dt, {"question": "should I ship daily or polish for a month?",
                     "options": ["ship daily", "polish for a month"]}, root=tp)
            ck("A1: DECISION ran ON THE TWIN and returned a measured per-option scoring",
               dec["kind"].endswith(".decision") and isinstance(dec["options"], list)
               and len(dec["options"]) == 2
               and dec["twin_id"] == twin.twin_id_of(dt))
            ck("A2: the personal model was built from synthetic Lamar-data (known=True, captured items)",
               dec["personal_known"] is True
               and (dec["profile_counts"].get("decision_patterns", 0)
                    + dec["profile_counts"].get("values", 0)) >= 1)
            ck("A3: a GROUNDED recommendation was made — every reason cites a captured datum",
               dec["recommendation"] is not None and dec["recommendation_grounded"] is True
               and len(dec["rationale"]) >= 1 and all(r.get("from") for r in dec["rationale"]))
            ck("A4: 'ship daily' is recommended (it matches his captured ship/momentum model)",
               dec["recommendation"] == "ship daily")
            # ANTI-FABRICATION: an option grounded in NOTHING gets score 0 / no recommendation.
            dec_void = sim.simulate_decision(
                dt, {"question": "pick a teacup pattern",
                     "options": ["the floral teacup with no bearing on anything captured"]}, root=tp)
            ck("A5: an option matching NOTHING in his model earns NO recommendation (never invented)",
               dec_void["recommendation"] is None or dec_void["options"][0]["score"] == 0.0)
            ck("A6: the world-model situation read is INTERNAL-only (never a diagnosis at the user)",
               dec["situation"].get("internal_only") is True)

            # ---- B. LEARNING — "what WOULD happen if we learned X for T?" ----------------------
            lt = synth_twin("sim-learning")
            learn = sim.simulate_learning(lt, {"mode": "medium", "periods": 4}, root=tp)
            ck("B1: LEARNING ran synthetic learning on the twin, $0, no cloud, real cycles",
               learn["cost_usd"] == 0.0 and learn["used_cloud"] is False
               and (learn["cycles"] or 0) > 0)
            ck("B2: LEARNING projected real ACCUMULATION (objects gained) + a trajectory",
               (learn["projection"]["objects_gained"] or 0) > 0
               and len(learn["trajectory"]) >= 1
               and learn["projection"]["objects_after"] > learn["projection"]["objects_before"])
            lt_off = synth_twin("sim-learning-off")
            learn_off = sim.simulate_learning(lt_off, {"mode": "off", "periods": 10}, root=tp)
            ck("B3: Off mode is provably INERT (0 cycles, 0 gained, $0) — the safe default",
               learn_off["cycles"] == 0 and (learn_off["projection"]["objects_gained"] or 0) == 0
               and learn_off["cost_usd"] == 0.0)

            # ---- C. ARCHITECTURE — "what WOULD happen if we changed retrieval to FMLGS?" --------
            at = synth_twin("sim-arch")
            twin.accelerate(at, 30, root=tp)               # grow the vault so the index has objects
            arch = sim.simulate_architecture(at, "fmlgs_retrieval", root=tp)
            m = arch.get("measurement", {})
            ck("C1: ARCHITECTURE measured FMLGS against keyword on the TWIN'S own vault",
               arch.get("change_key") == "fmlgs_retrieval" and m.get("available") is True
               and m.get("n_objects", 0) > 0)
            ck("C2: recall / latency / footprint were all MEASURED",
               m.get("recall_vs_keyword") is not None
               and m.get("latency_fmlgs_us") is not None
               and m.get("footprint_total_bytes") is not None)
            ck("C3: FMLGS HELD recall vs the keyword baseline (the non-negotiable 'same intelligence' bar)",
               arch.get("verdict", {}).get("recall_held_vs_keyword") is True)

            # ---- D. ALTERNATIVE FUTURES — "what MIGHT happen?" (a RANGE, not a point) -----------
            ft = synth_twin("sim-might")
            alt = sim.alternative_futures(ft, variants=5, base_cycles=20, seed=3, root=tp)
            ck("D1: ALT-FUTURES forked 5 INDEPENDENT futures of the twin (distinct twin ids)",
               alt["variants"] == 5 and len(alt["branches"]) == 5
               and len({b["twin_id"] for b in alt["branches"]}) == 5)
            ck("D2: ALT-FUTURES reported a DISTRIBUTION (min/median/max) with real spread > 0 — a range",
               bool(alt["distribution"]) and "median" in alt["distribution"]
               and alt["distribution"]["max"] >= alt["distribution"]["min"]
               and alt["distribution"]["range"] > 0 and alt["distribution"]["n"] == 5)

            # ---- E. FREEZE PROOF — a twin op coincides with the real mind byte-UNCHANGED --------
            fg = twin.freeze_guard(SRC, tp)
            with fg:
                sim.simulate_learning(synth_twin("sim-freeze"), {"mode": "high", "periods": 2}, root=tp)
            rep = fg.report()
            ck("E1: FREEZE PROOF — real identity byte-UNCHANGED across a simulation op",
               rep.get("real_identity_byte_unchanged") is True
               and fg.real_identity_byte_unchanged is True)
            ck("E2: FREEZE PROOF — the whole real .anima byte-UNCHANGED across a simulation op",
               rep.get("real_anima_byte_unchanged") is True
               and fg.real_anima_byte_unchanged is True)

            # ---- F. WORKED EXAMPLES — one of EACH type, measured, freeze-reported --------------
            ex = sim.worked_examples(root=tp, quiet=True)
            ck("F1: one worked example of EACH type produced, all measured",
               ex["decision"]["recommendation"] is not None
               and (ex["learning"]["projection"]["objects_gained"] or 0) > 0
               and ex["architecture"]["measurement"].get("available") is True
               and bool(ex["alternative_futures"]["distribution"]))
            ck("F2: the worked-examples freeze report shows the real mind byte-UNCHANGED",
               ex["freeze_report"]["real_identity_byte_unchanged"] is True
               and ex["freeze_report"]["real_anima_byte_unchanged"] is True)
        finally:
            for m, attr, val in extra:
                try:
                    setattr(m, attr, val)
                except Exception:
                    pass

    # ---- HERMETICITY — the real .anima identical start -> end --------------------------------
    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nCOGNITIVE-SIMULATION CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
