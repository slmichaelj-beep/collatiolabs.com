#!/usr/bin/env python3
"""
certify_reality_learning — THE EPISTEMIC LOOP: observation -> grounded HYPOTHESIS(es, COMPETING)
-> PREDICTION -> OUTCOME -> SURPRISE -> LEARNING -> MODEL REVISION, proven end-to-end through the
SAME anima.reality.form / resolve engine the observatory (scripts/reality.py) reads.

Proves a PREDICTION logged against an OUTCOME yields a LEARNING — deterministically, offline, and
hermetically — and that the whole loop is GROUNDED, INTERNAL-ONLY, and a DURABLE append-only ledger:

  A. PURE GRADIENT — surprise() is HIGH when confident-and-wrong (0.82,False -> ~0.82) OR
     doubtful-and-right (0.11,True -> ~0.89), LOW when confidence matched reality (0.90,True ->
     ~0.10); competition priors normalise to sum 1 and the adjudication reweight strengthens the
     supported hypothesis, weakens the contradicted one, renormalises, and never annihilates one.
  B. FORM GROUNDS COMPETING HYPOTHESES — a Day-1 "my manager just changed" turn yields >=3 grounded
     HYPOTHESIS records (manager_change/recent_move/family_visit), each carrying the EXACT turn as
     evidence; a COMPETITION led by manager_change; and a leading-hypothesis sleep_decline
     PREDICTION (horizon 14d, status OPEN, internal_only) linked to the leader + its competition.
  C. GROUNDED / CONSERVATIVE — a vague / mood-only / empty turn forms NOTHING (no confabulation).
  D. LOOP CLOSES (the core claim) — a Day-14 "I've barely slept" OUTCOME resolves the OPEN
     prediction: exactly one LEARNING with prediction_correct=True, an OUTCOME record on disk,
     SURPRISE ~0.33, and the competition ADJUDICATED (manager_change strengthened, recent_move
     weakened, weights still sum ~1, leader still manager_change).
  E. HIGH-SURPRISE REVISION — a confident prediction proven FALSE ("sleeping great") is
     high-surprise and appends a MAJOR model REVISION (before_weights -> after_weights, triggered
     by the learning); calibrate counts it as a model revision.
  F. CALIBRATE — 1 resolved / 1 correct -> accuracy 1.0 with a Brier score + mean surprise; one
     data point is NOT yet a reliability verdict (Observed > Assumed).
  G. RESTART-SURVIVAL — a FRESH records()/loop() read off disk re-derives the closed loop (the
     ledger is the durable, append-only source of truth — survives a "restart").
  H. INTERNAL-ONLY WALL — every formed record is internal_only=True; render() declares INTERNAL
     model-state / never spoken and trips no banned diagnosis/forecast term; a forecast-creep
     phrase is caught by the clean-gate (defence in depth).

Hermetic + offline (no model, no network): reality.STORE is redirected into the temp dir (the
_temp_store set covers world_state/meaning/memory_lirf/constitution but NOT reality, so this cert
redirects reality.STORE itself, plus reliability.DEFAULT_STORE defensively), and the real .anima is
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


def main() -> int:
    from anima import reality
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("REALITY LEARNING — the epistemic loop: hypothesis -> prediction -> outcome -> SURPRISE -> learning")
    print("=" * 99)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # ---- A. PURE GRADIENT (no store needed — these are pure functions) -------------------------
    ck("A1: surprise is HIGH for confident-and-WRONG (0.82,False -> ~0.82)",
       abs(reality.surprise(0.82, False) - 0.82) < 1e-6)
    ck("A2: surprise is HIGH for doubtful-and-RIGHT (0.11,True -> ~0.89)",
       abs(reality.surprise(0.11, True) - 0.89) < 1e-6)
    ck("A3: surprise is LOW when confidence matched reality (0.90,True -> ~0.10)",
       reality.surprise(0.90, True) < 0.12 and reality.surprise(0.05, False) < 0.06)
    _norm = reality._normalise_weights({"a": 2.0, "b": 1.0, "c": 1.0})
    ck("A4: competition priors normalise to sum 1.0 (a proper distribution)",
       abs(sum(_norm.values()) - 1.0) < 1e-6 and _norm["a"] > _norm["b"])
    _adj = reality._adjudicate_weights(
        {"a": {"weight": 0.5}, "b": {"weight": 0.3}, "c": {"weight": 0.2}},
        supported_key="a", contradicted_keys=["b"])
    ck("A5: adjudication strengthens supported, weakens contradicted, renormalises, floors (never 0)",
       abs(sum(_adj.values()) - 1.0) < 1e-6 and _adj["a"] > 0.5 and _adj["b"] < 0.3
       and all(v > 0.0 for v in _adj.values()))

    with _temp_store() as tp:
        # _temp_store covers world_state/meaning/memory_lirf/constitution but NOT reality itself,
        # and reliability is not in its set — redirect both here so EVERY store reality could touch
        # points at the temp dir, then restore in finally (the brain/personal-cert pattern).
        saved_reality_store = getattr(reality, "STORE", None)
        reality.STORE = tp
        extra = []
        for modname, attr in (("anima.reliability", "DEFAULT_STORE"),):
            try:
                m = __import__(modname, fromlist=["_"])
                extra.append((m, attr, getattr(m, attr, None)))
                if getattr(m, attr, None) is not None:
                    setattr(m, attr, tp)
            except Exception:
                pass
        try:
            DAY1 = reality._SYNTH_DAY1
            N = "RLcert"

            # ---- B. FORM GROUNDS COMPETING HYPOTHESES -----------------------------------------
            formed = reality.form(N, "my manager just changed and work's been heavy", at=DAY1)
            hyps = [r for r in formed if r["kind"] == reality.HYPOTHESIS]
            comp = next((r for r in formed if r["kind"] == reality.COMPETITION), None)
            pred = next((r for r in formed if r["kind"] == reality.PREDICTION), None)
            ck("B1: a stated change yields >=3 grounded HYPOTHESES (a competing set, not one belief)",
               reality.HYPOTHESIS in [r["kind"] for r in formed] and len(hyps) >= 3)
            ck("B2: the stress_risk competition spawns the rival explanations, led by manager_change",
               comp is not None and comp["category"] == "stress_risk"
               and {"manager_change", "recent_move", "family_visit"}.issubset(set(comp["candidates"]))
               and comp["leader"] == "manager_change")
            ck("B3: every competing hypothesis carries the EXACT turn as evidence (grounded)",
               bool(hyps) and all(h["evidence"].get("turn", "").startswith("my manager") for h in hyps))
            ck("B4: the leading hypothesis yields an OPEN sleep_decline PREDICTION (~14-day horizon)",
               bool(pred) and pred["category"] == "sleep_decline" and pred["horizon_days"] == 14
               and pred["status"] == reality.OPEN)
            ck("B5: the prediction is linked to the LEADING hypothesis + its competition",
               bool(pred) and pred.get("competition_id") == comp["id"]
               and pred.get("hypothesis_id") in {h["id"] for h in hyps})
            ck("B6: exactly one prediction is OPEN before any outcome arrives",
               len(reality.open_predictions(N)) == 1)

            # snapshot the competition's PRIOR weights for the adjudication assertion in D.
            weights_before = {k: v["weight"] for k, v in comp["candidates"].items()}

            # ---- C. GROUNDED / CONSERVATIVE — thin evidence forms NOTHING ----------------------
            ck("C1: a vague turn with no stated evidence forms nothing (no confabulation)",
               reality.form(N, "anyway, how are you?", at=DAY1, persist=False) == [])
            ck("C2: a mood word alone ('feeling off') is NOT enough evidence",
               reality.form(N, "feeling kind of off today", persist=False) == [])
            ck("C3: an empty / whitespace source forms nothing",
               reality.form(N, "", persist=False) == [] and reality.form(N, "   ", persist=False) == [])

            # ---- D. THE LOOP CLOSES — a prediction logged against an outcome yields a learning --
            learnings = reality.resolve(N, "honestly I've barely slept the last two weeks",
                                        at=reality._add_days(DAY1, 14))
            learning = learnings[0] if learnings else {}
            ck("D1: a matching later OUTCOME resolves the open prediction into exactly one LEARNING",
               len(learnings) == 1)
            ck("D2: the LEARNING records the mind was RIGHT (prediction_correct=True), linked to the pred",
               learning.get("prediction_correct") is True and learning.get("prediction_id") == pred["id"])
            ck("D3: the LEARNING carries the SURPRISE gradient (0.67 right -> ~0.33)",
               "surprise" in learning and abs(learning["surprise"] - 0.33) < 0.02)
            outs = reality._records_of(N, reality.OUTCOME)
            ck("D4: an OUTCOME record was appended with the observed reality",
               len(outs) == 1 and "barely slept" in outs[0].get("observed", ""))
            ck("D5: the prediction is no longer OPEN after resolution",
               len(reality.open_predictions(N)) == 0)
            comp_after = reality.competition_for(N, comp["id"])
            weights_after = {k: v["weight"] for k, v in comp_after["candidates"].items()}
            ck("D6: ADJUDICATED — manager_change (supported) strengthened, recent_move weakened, sum ~1",
               weights_after["manager_change"] > weights_before["manager_change"]
               and weights_after["recent_move"] < weights_before["recent_move"]
               and abs(sum(weights_after.values()) - 1.0) < 1e-4
               and comp_after["leader"] == "manager_change")

            # ---- E. HIGH-SURPRISE -> MODEL REVISION (confident prediction proven FALSE) ---------
            NCW = "RLcert_cw"
            f_cw = reality.form(NCW, "my manager just changed", at=DAY1)
            comp_cw = next((r for r in f_cw if r["kind"] == reality.COMPETITION), None)
            before_cw = {k: v["weight"] for k, v in comp_cw["candidates"].items()}
            l_cw = reality.resolve(NCW, "actually I've been sleeping great, fully rested",
                                   at=reality._add_days(DAY1, 14))
            ck("E1: a confident prediction proven FALSE is HIGH-surprise (>= revision threshold)",
               bool(l_cw) and l_cw[0]["prediction_correct"] is False
               and l_cw[0]["surprise"] >= reality._SURPRISE_REVISION_AT)
            revs_cw = [r for r in reality._records_of(NCW, reality.REVISION) if r.get("major")]
            ck("E2: it appends a MAJOR model REVISION (before_weights -> after_weights, triggered by the learning)",
               len(revs_cw) == 1 and "before_weights" in revs_cw[0] and "after_weights" in revs_cw[0]
               and revs_cw[0].get("triggered_by") == l_cw[0]["id"])
            ck("E3: calibrate counts the high-surprise outcome as a model revision",
               reality.calibrate(NCW)["revisions"] == 1)

            # ---- F. CALIBRATE — accuracy/Brier/mean-surprise; one point is NOT a verdict --------
            cal = reality.calibrate(N)
            ck("F1: calibration shows 1 resolved, 1 correct, accuracy 1.0",
               cal["resolved"] == 1 and cal["correct"] == 1 and cal["accuracy"] == 1.0)
            ck("F2: a Brier score AND a mean SURPRISE are computed",
               isinstance(cal["brier"], float) and isinstance(cal["mean_surprise"], float))
            ck("F3: one data point is NOT yet a reliability verdict (Observed > Assumed)",
               cal["by_category"]["sleep_decline"].get("reliable") is None
               and cal["reliable_kinds"] == [])

            # ---- G. RESTART-SURVIVAL — a FRESH read off disk re-derives the closed loop ---------
            disk = reality.records(N)
            ck("G1: the loop persisted to disk (hypotheses + competition + prediction + outcome + learning)",
               any(r.get("kind") == reality.HYPOTHESIS for r in disk)
               and any(r.get("kind") == reality.COMPETITION for r in disk)
               and any(r.get("kind") == reality.PREDICTION for r in disk)
               and any(r.get("kind") == reality.OUTCOME for r in disk)
               and any(r.get("kind") == reality.LEARNING for r in disk))
            data = reality.loop(N)   # a pure ledger READ — re-derives the closed loop from disk
            ck("G2: a fresh loop() read off disk re-derives the CLOSED loop (durable append-only ledger)",
               len(data["hypotheses"]) >= 3 and len(data["competitions"]) >= 1
               and len(data["resolved"]) == 1
               and data["resolved"][0]["prediction"]["status"] == reality.CONFIRMED
               and data["resolved"][0]["outcome"] is not None
               and "surprise" in data["resolved"][0]["learning"]
               and data["calibration"]["accuracy"] == 1.0)

            # ---- H. INTERNAL-ONLY WALL (never user-facing; defence-in-depth clean-gate) ---------
            ck("H1: every formed record is flagged internal_only (model-state, never a user assertion)",
               all(r.get("internal_only") is True for r in formed))
            block = reality.render(N)
            ck("H2: render declares INTERNAL model-state / never spoken and names the loop stages + SURPRISE",
               "INTERNAL model-state" in block and "never spoken" in block
               and "HYPOTHESES" in block and "HYPOTHESIS COMPETITION" in block
               and "PREDICTIONS" in block and "RESOLVED LOOPS" in block and "SURPRISE" in block)
            ck("H3: NO-DIAGNOSIS GATE — not one rendered line trips a banned diagnosis/forecast term",
               all(reality._is_clean(ln) for ln in block.splitlines()))
            ck("H4: the clean-gate catches a diagnosis AND a forecast-creep phrase (the wall holds)",
               not reality._is_clean("you're burning out") and not reality._is_clean("you will spiral")
               and reality._is_clean("a recent change is a plausible new source of strain"))
        finally:
            reality.STORE = saved_reality_store
            for m, attr, old in extra:
                if old is not None:
                    setattr(m, attr, old)

    fp_after = _footprint(real_anima)
    ck("Z1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nREALITY-LEARNING CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
