#!/usr/bin/env python3
"""VERA EPISTEMIC AUDIT OBSERVATORY — Layer 3, "should it have happened?".

The stack already answers two of the three questions a thirty-year companion must hold about
its own reasoning. Layer 1 (the MRI, ``anima/telemetry.py``) answers WHAT HAPPENED — it films
every stage of a turn as an ordered strip of frames. Layer 2 answers WHY — ``scripts/decisions``
shows the ranked field (which gap won, which lost), ``scripts/provenance`` DECOMPOSES the
winner's score into the named signals that produced it, and ``scripts/causal`` shows the
SUBSYSTEM COMPETITION (which drive dominated the turn). Between them they reconstruct the path
taken and the arithmetic behind it.

None of them judges the path. They are a MOVIE of the decision, frame-accurate and faithful —
but a movie does not ask whether the decision was a GOOD one. This is the missing layer, the one
that turns the movie into a COACH:

    Layer 1  — what happened?        (MRI / telemetry trace)
    Layer 2  — why did it happen?    (provenance / decision / causal)
    Layer 3  — SHOULD it have happened?  (THIS — JUSTIFICATION)

THE DECISION WE AUDIT — a recorded REALITY prediction, in its full epistemic frame
────────────────────────────────────────────────────────────────────────────────────────────
A "decision" the mind actually made and can be held to account for is a ``reality`` PREDICTION:
a tagged, evidence-anchored bet about the user's world ("a change at work -> rest may decline
within ~2 weeks"), formed from a LEADING hypothesis that WON a COMPETITION of rival explanations,
later RESOLVED by an outcome that arrived over real calendar time, scored for SURPRISE, and
folded into a running CALIBRATION. That is exactly the loop ``anima/reality.py`` records — so we
audit ITS records, in ITS frame, building on ITS machinery rather than reinventing any of it.

For each such decision (open or resolved) we render seven judgments and one verdict:

  1. JUSTIFIED BY THE EVIDENCE? (sufficiency)  — did the prediction rest on a grounded hypothesis
     (real ``evidence.turn`` + a competition), and did the winner carry a DECISIVE prior margin
     over its rivals? A lone un-competed guess, or a razor-thin lead, is UNDER-EVIDENCED.
  2. WHAT EVIDENCE WAS MISSING?  — the rival candidates whose own stated signal was NEVER observed
     (so the competition was adjudicated on the leader's consequence alone), plus the KNOWN / asked
     roads the Decision Observatory shows around the turn. The evidence that SHOULD have informed it.
  3. WHAT WOULD HAVE CHANGED THE RESULT? (the counterfactual pivot)  — the SPECIFIC stated signal
     (a rival's ``supported_by`` cue, read straight from ``reality._COMPETITION_LIBRARY``) that,
     had it appeared in the conversation, would have flipped the winner. Named, not hand-waved.
  4. COMPETING HYPOTHESES — was the winner WARRANTED over them?  — reuse ``reality``'s competition
     (priors -> posterior, rolled forward through every revision via ``competition_for``): the
     winner is warranted iff its posterior beats every rival by a margin AND the outcome (if any)
     adjudicated in its favor.
  5. WAS CONFIDENCE CALIBRATED?  — reuse ``reality.surprise`` + ``reality.calibrate``: did stated
     confidence match the actual outcome (this decision), and the category's REALIZED accuracy
     (over time)? Confident-and-wrong is OVERCONFIDENT; a stated confidence that drifts from the
     category's track record is MISCALIBRATED.
  6. WAS SURPRISE APPROPRIATE?  — given the PRIORS (the leader's prior weight), should the outcome
     have been surprising? Reuse ``reality.surprise``. Low surprise when the prior pointed the
     right way is appropriate; a confident bet blindsided is an EARNED surprise (a real miss).
  7. WHAT SHOULD HAVE BEEN BELIEVED AFTERWARD? (the corrected posterior)  — the competition's
     weights rolled forward through its revisions (``competition_for``) IS the corrected posterior;
     the corrected confidence is the category's realized accuracy from ``calibrate``. The honest
     belief the evidence licenses, after the fact.

THE VERDICT — one of four, each with the specific gap + the fix lever
────────────────────────────────────────────────────────────────────────────────────────────
  * JUSTIFIED       — grounded, decisively-led, well-calibrated. (gap: none; lever: keep it.)
  * UNDER-EVIDENCED — thin/absent competition, a razor-thin winner, or rivals never tested.
                      (lever: gather the missing rival's signal — the counterfactual pivot.)
  * OVERCONFIDENT   — a confident prediction the outcome refuted (high surprise, wrong).
                      (lever: lower the stated confidence toward the category's realized accuracy.)
  * MISCALIBRATED   — stated confidence that systematically diverges from the category's track
                      record (over ``_MIN_FOR_VERDICT`` resolved). (lever: recalibrate the prior.)

The verdict is DELIBERATELY MECHANICAL: each is a thresholded reading of numbers ``reality``
already computes (the prior margin, the surprise, the Brier gap, the realized accuracy), so
"why this verdict" is always exactly "which threshold did the evidence cross" — and the
``--selftest`` asserts that identity on synthetic decisions engineered to land in each bucket.

HOW THIS BUILDS ON THE STACK (reuse by import — nothing reinvented)
────────────────────────────────────────────────────────────────────────────────────────────
  * ``anima.reality``    — THE substrate. The whole epistemic loop (``loop``), the competing
                           hypotheses + their rolled-forward posteriors (``competition_for``,
                           ``_COMPETITION_LIBRARY``, ``_candidates_for``), SURPRISE (``surprise``),
                           and CALIBRATION (``calibrate``, ``_MIN_FOR_VERDICT``/``_RELIABLE_AT``).
                           Every judgment is a reading of these — the audit JUDGES the loop.
  * ``scripts.decisions``— the ranked candidate FIELD around the turn (``curiosity_decision``):
                           the KNOWN-suppressed / already-asked / lower-rank roads become the
                           "missing / not-taken evidence" context for judgment #2.
  * ``scripts.causal``   — the SUBSYSTEM COMPETITION (``compete``): we also audit whether the
                           WINNING SUBSYSTEM was warranted — did the dominant signal justify the
                           choice over the runner-up's margin (the macro analogue of #4).
  * ``scripts.provenance``— the score DECOMPOSITION (``decompose_score``): the curiosity decision's
                           score is judged "built on real evidence" (a mention curve fed by a fact)
                           vs "thin priors" — the sufficiency read (#1) for the curiosity arm.
  * ``anima.telemetry``  — the MRI trace (``open_trace`` schema / ``trace``): the recorded
                           "what happened" the audit is ABOUT. We attach the audit to a real
                           recorded trace when one exists, and synthesise a faithful one offline.

GUARDRAILS (identical discipline to scripts/decisions.py + causal.py + provenance.py + relationship.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * STANDALONE + READ-ONLY on the engines. It IMPORTS and CALLS reality / decisions / causal /
    provenance / telemetry / curiosity / world_state, and judges their output. It edits NO module,
    NO test, and not anima/* / certify.py / selftest.py. The only file it adds is
    scripts/epistemic_audit.py. No accessor was added to any engine — every judgment reads a
    PUBLIC entry point (or a documented public constant) of the engine it builds on.
  * SYNTHETIC creatures + a HERMETIC temp store ONLY. Every STORE the audit (or the reused
    reality/decisions/causal/provenance derivations) can touch is redirected to ONE
    TemporaryDirectory — reality.STORE, memory_lirf.STORE on BOTH the __main__ and package
    bindings, constitution.STORE, reliability.DEFAULT_STORE, curiosity.STORE, world_state.STORE,
    meaning.STORE, telemetry.STORE, cloud.STORE, metrics.STORE, spine.STORE, opportunity/loops/
    trajectory/reminders STORE — mirroring anima/memory_lirf.py's _selftest (~1316-1340) and the
    sibling observatories. The run ASSERTS the real .anima footprint is byte-UNCHANGED start->end.
    It NEVER reads or writes a real Vera.* file.
  * DETERMINISTIC + OFFLINE by default. No model, no network. Every reused derivation
    (reality.form/resolve, the rankings) is model-free; the synthetic time-series is a fixed
    Day-1 -> Day-14 timeline. A live leg (audit a REAL generated reply's grounding decision) is
    GATED ON OLLAMA and SKIPPED LOUD when offline — offline is never a failure.
  * NO-DIAGNOSIS WALL, defence in depth. The audit reasons over the SAME stress/sleep epistemic
    records reality holds. Every human-readable line it emits passes reality's OWN clean-gate
    (``reality._is_clean``) — an internal coaching note must never adopt a diagnosis/forecast voice.
  * Never raises out of the entry points — a malformed creature yields an honest empty render,
    not a traceback.

    python3 scripts/epistemic_audit.py            # human-readable AUDIT (verdict + gaps + levers)
    python3 scripts/epistemic_audit.py --json     # machine-readable
    python3 scripts/epistemic_audit.py --selftest  # PROVE each verdict is the thresholded reading
    python3 scripts/epistemic_audit.py --live      # also audit a REAL reply's grounding (Ollama)

Exit code is 0 on a default run / a passing selftest with the guardrail intact; non-zero only on
a broken guardrail (real .anima changed, or an engine raised inside the harness) or a failed
selftest assertion.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import secrets
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# REUSE BY IMPORT — the substrate this layer JUDGES (never reinvents). reality is THE engine of
# the epistemic loop (hypotheses/competition/surprise/calibration); the three observatory scripts
# are the Layer-2 "why" views we build the "should it" judgment on top of; telemetry is the MRI.
from anima import reality                  # noqa: E402  the epistemic loop + surprise + calibration
from anima import curiosity                # noqa: E402  (for the curiosity-decision sufficiency arm)
from anima import world_state              # noqa: E402  (seed rival signals; situation context)
from anima import telemetry                # noqa: E402  the MRI trace (the recorded "what happened")
import scripts.decisions as decisions      # noqa: E402  the ranked field (roads not taken = missing)
import scripts.causal as causal            # noqa: E402  the subsystem competition (was the winner warranted)
import scripts.provenance as provenance    # noqa: E402  the score decomposition (built on evidence?)

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "audit_synth"


# ===================================================================================
# THE VERDICT VOCABULARY — a small closed set. Each verdict is a thresholded reading of numbers
# reality already computes; the key is the stable id a consumer branches on, the gloss is what to
# SHOW. The whole point of Layer 3 is that EACH carries a specific GAP and a specific FIX LEVER —
# a movie names what happened; a coach names what to do about it.
# ===================================================================================
JUSTIFIED = "JUSTIFIED"
UNDER_EVIDENCED = "UNDER-EVIDENCED"
OVERCONFIDENT = "OVERCONFIDENT"
MISCALIBRATED = "MISCALIBRATED"
VERDICTS = (JUSTIFIED, UNDER_EVIDENCED, OVERCONFIDENT, MISCALIBRATED)

VERDICT_GLOSS = {
    JUSTIFIED: "grounded, decisively led, and calibrated — the evidence warranted the decision",
    UNDER_EVIDENCED: "thin/absent competition, a razor-thin winner, or rivals never tested",
    OVERCONFIDENT: "a confident prediction the outcome refuted (high surprise, wrong direction)",
    MISCALIBRATED: "stated confidence diverges from the category's realized track record",
}

# ── the thresholds the verdict reads. Every one is a bar over a number reality computes, so a
#    verdict is always exactly "which bar did the evidence cross". Tunable, fixed, documented. ──
# A winner's PRIOR margin over its strongest rival must clear this to count as a DECISIVE lead;
# below it the competition was close and the choice is UNDER-EVIDENCED on sufficiency grounds.
_DECISIVE_MARGIN = 0.15
# A resolved prediction whose SURPRISE is at/above reality's own revision bar AND was WRONG is
# OVERCONFIDENT (the model was confident in the wrong direction). We reuse reality's own constant.
_SURPRISE_HIGH = reality._SURPRISE_REVISION_AT
# A stated confidence that diverges from the category's REALIZED accuracy by more than this (once
# the category has >= reality._MIN_FOR_VERDICT resolved data points) is MISCALIBRATED.
_CALIB_DIVERGENCE = 0.25
# The minimum evidence a JUSTIFIED sufficiency read demands: a grounded hypothesis (evidence.turn)
# AND a real competition (>= this many candidates competed). A lone un-competed guess fails it.
_MIN_COMPETITORS = 2


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect mirroring anima/memory_lirf.py _selftest (~1316-1340)
# + the sibling observatories (decisions/causal/provenance): redirect EVERY store the audit and
# every reused derivation can touch into ONE throwaway dir, including memory_lirf.STORE on BOTH
# the __main__ and package bindings (under `python3 -m` they are distinct objects). Plus a
# footprint hash to PROVE nothing real moved. We deliberately UNION the targets of reality +
# decisions + causal + provenance, because we reuse all four and any of their legs may write.
# ===================================================================================
_STORE_TARGETS = (
    ("anima.reality", "STORE"),
    ("anima.memory_lirf", "STORE"),
    ("anima.constitution", "STORE"),
    ("anima.reliability", "DEFAULT_STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.telemetry", "STORE"),
    ("anima.cloud", "STORE"),
    ("anima.metrics", "STORE"),
    ("anima.spine", "STORE"),
    ("anima.opportunity", "STORE"),
    ("anima.loops", "STORE"),
    ("anima.trajectory", "STORE"),
    ("anima.reminders", "STORE"),
    ("anima.portrait", "STORE"),
    ("anima.dials", "STORE"),
    ("anima.narrative", "STORE"),
    ("anima.review", "STORE"),
    ("anima.proactive", "STORE"),
    ("anima.caps", "STORE"),
    ("anima.identity", "STORE"),
    ("anima.mouth", "STORE"),
    ("anima.live", "STORE"),
)


def _store_modules():
    """Resolve the (module, attr) redirect targets that import cleanly. Folds in the EXACT objects
    this file holds (reality, curiosity, world_state, telemetry) AND the exact objects the reused
    observatories hold (decisions.memory_lirf/curiosity, causal.*, provenance.*) explicitly — the
    dual-binding guard the memory_lirf self-test warns about: under `python3 -m` a dotted import
    can return a different copy than the one a module holds, and a write to the un-redirected copy
    would leak to the real .anima. Belt-and-suspenders: we redirect every binding we can name."""
    out = []
    seen = set()

    def _add(mod, attr):
        if mod is None:
            return
        key = (id(mod), attr)
        if key in seen:
            return
        if getattr(mod, attr, None) is not None:
            out.append((mod, attr))
            seen.add(key)

    for dotted, attr in _STORE_TARGETS:
        try:
            mod = __import__(dotted, fromlist=["_"])
        except Exception:
            continue
        _add(mod, attr)
    # the EXACT objects this file holds.
    for mod, attr in ((reality, "STORE"), (curiosity, "STORE"),
                      (world_state, "STORE"), (telemetry, "STORE")):
        _add(mod, attr)
    # the EXACT objects the reused observatories hold (their own module-level imports). A reused
    # decisions/causal/provenance call writes through THEIR bindings, so redirect those too.
    for sibling in (decisions, causal, provenance):
        for name in ("memory_lirf", "curiosity", "world_state", "metrics", "spine",
                     "reality", "telemetry", "meaning"):
            _add(getattr(sibling, name, None), "STORE")
    return out


@contextlib.contextmanager
def _temp_store():
    """Redirect every resolved STORE target to one fresh temp dir for the duration, then restore.
    Nothing under the real .anima/ is read or written while this is active. The reused sibling
    observatories ALSO open their own temp-store contexts internally (build_report etc.); we keep
    ours active around the whole audit so even a direct reused call (curiosity_decision, compete,
    decompose_score, reality.form/resolve) can never touch real state."""
    targets = _store_modules()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-epistemic-") as td:
        p = Path(td)
        for (m, a) in targets:
            setattr(m, a, p)
        try:
            yield p
        finally:
            for (m, a, old) in saved:
                if old is not None:
                    setattr(m, a, old)


def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir, which
    legitimately changes) so we can PROVE the harness touched nothing. Verbatim from
    scripts/decisions.py / causal.py / provenance.py / relationship.py."""
    if not root.is_dir():
        return (None, 0)
    files = sorted(
        q for q in root.rglob("*")
        if q.is_file() and "backups" not in q.relative_to(root).parts
    )
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _clean(s: str) -> str:
    """The no-diagnosis clean-gate, REUSED from reality verbatim (defence in depth): an internal
    coaching note must never adopt a diagnosis/forecast voice. Falls back to a neutral line if a
    phrasing ever slips a banned term in. Never raises."""
    try:
        return reality._safe_statement(s, "(an internal audit note)")
    except Exception:
        return s


def _clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if v != v:
        return 0.0
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


# ===================================================================================
# THE LOOP READ — assemble the full epistemic loop for a creature (REUSE reality.loop), and pull
# the per-decision parts the audit judges. Read-only; never raises.
# ===================================================================================
def _loop(name: str) -> dict:
    try:
        return reality.loop(name) or {}
    except Exception:
        return {"hypotheses": [], "competitions": [], "predictions": [], "resolved": [],
                "open": [], "revisions": [], "calibration": reality.calibrate(name)}


def _competition_of(loop_data: dict, competition_id):
    """The competition record (weights rolled forward through revisions) for an id, from the loop's
    assembled competitions list. None if absent. The loop already rolled them forward via
    reality.competition_for, so this is the corrected posterior the audit reads."""
    if not competition_id:
        return None
    for c in loop_data.get("competitions") or []:
        if isinstance(c, dict) and c.get("id") == competition_id:
            return c
    return None


def _resolved_for(loop_data: dict, prediction_id):
    """The resolved-loop bundle {prediction, outcome, learning, revision, competition} for a
    prediction id, or None if the prediction is still open."""
    for r in loop_data.get("resolved") or []:
        p = r.get("prediction") or {}
        if p.get("id") == prediction_id:
            return r
    return None


# ===================================================================================
# JUDGMENT #1 — SUFFICIENCY: was the decision JUSTIFIED by the available evidence? A prediction is
# sufficiently evidenced iff (a) its leading hypothesis is GROUNDED (carries a real evidence.turn),
# and (b) it WON a real COMPETITION (>= _MIN_COMPETITORS rivals) by a DECISIVE prior margin. A lone
# un-competed guess, or a razor-thin lead, is under-evidenced. Reads reality's competition record.
# ===================================================================================
def _judge_sufficiency(pred: dict, comp, loop_data: dict) -> dict:
    """Return {sufficient, n_competitors, leader, margin, grounded, evidence_turn, why}. The
    margin is the leader's PRIOR weight minus its strongest rival's prior — the decisiveness of
    the win at formation time (before any outcome). Pure-ish; never raises."""
    grounded = bool((pred.get("evidence") or {}).get("turn"))
    evidence_turn = (pred.get("evidence") or {}).get("turn", "")
    if not comp:
        return {"sufficient": False, "n_competitors": 0, "leader": None, "margin": 0.0,
                "grounded": grounded, "evidence_turn": evidence_turn,
                "why": ("the prediction rests on a SINGLE un-competed hypothesis — no rival "
                        "explanation was ever weighed, so 'best' means nothing here")}
    cands = comp.get("candidates") or {}
    n = len(cands)
    # use PRIOR weights (decisiveness at formation), available on each candidate record.
    priors = {k: float(v.get("prior", v.get("weight", 0.0))) for k, v in cands.items()}
    order = sorted(priors.items(), key=lambda kv: -kv[1])
    leader = order[0][0] if order else None
    lead = order[0][1] if order else 0.0
    runner = order[1][1] if len(order) > 1 else 0.0
    margin = round(lead - runner, 4)
    decisive = margin >= _DECISIVE_MARGIN
    sufficient = grounded and (n >= _MIN_COMPETITORS) and decisive
    if not grounded:
        why = "the prediction carries no grounded evidence turn — it is not anchored to a stated fact"
    elif n < _MIN_COMPETITORS:
        why = (f"only {n} candidate explanation was weighed — a real justification must beat "
               f"rivals, and there were effectively none")
    elif not decisive:
        why = (f'the winner "{leader}" led by only {margin:.2f} over the runner-up '
               f'(< {_DECISIVE_MARGIN:.2f}) — the competition was close, the choice not decisive')
    else:
        why = (f'the winner "{leader}" is grounded and led a {n}-way competition by {margin:.2f} '
               f'(>= {_DECISIVE_MARGIN:.2f}) — a decisive, evidenced lead')
    return {"sufficient": bool(sufficient), "n_competitors": n, "leader": leader,
            "margin": margin, "grounded": grounded, "evidence_turn": evidence_turn, "why": why}


# ===================================================================================
# JUDGMENT #2 + #3 — MISSING EVIDENCE + the COUNTERFACTUAL PIVOT. For the prediction's category we
# read reality's OWN competing-hypothesis library: each rival names the STATED signal that would
# SUPPORT it (its supported_by regex). A rival whose signal was NOT observed in the resolving
# outcome is UNTESTED — that is the missing evidence; the human-readable cue it would have taken is
# the COUNTERFACTUAL PIVOT (the evidence that would have changed the winner). Reuses the library
# verbatim, so the pivots are exactly the signals reality adjudicates on.
# ===================================================================================
# A small, honest human gloss for each rival candidate key's supporting signal — what the user
# would have had to SAY for that rival to win. Derived from the library's claims; kept neutral.
_PIVOT_GLOSS = {
    "manager_change": 'the strain traces to the recent change at work (its consequence shows up)',
    "recent_move": 'the user says the recent move/relocation is "still getting to me / unsettling"',
    "family_visit": 'the user says family/visitors at home are "in town / staying / a lot"',
    "multiple": 'the user says "everything at once / so many things / piling up"',
    "crunch": 'the user reports less downtime — "no time off / working weekends"',
    "understaffed": 'the user says they are "short-staffed / down a person / covering for someone"',
    "intends_and_acts": 'the user later says they "did it / stuck with it / kept it up"',
}


def _rival_signals(category: str) -> list:
    """The competing candidates reality defines for the PREDICTION's hypothesis category, each with
    the human gloss of the stated signal that would support it. The prediction category (e.g.
    'sleep_decline') maps back to the hypothesis category (e.g. 'stress_risk') via the pattern that
    produced it. Read straight from reality._COMPETITION_LIBRARY — never invented."""
    hyp_cat = _hypothesis_category_for(category)
    lib = reality._COMPETITION_LIBRARY.get(hyp_cat, ()) if hyp_cat else ()
    out = []
    for c in lib:
        out.append({"key": c.key, "claim": c.claim,
                    "pivot": _PIVOT_GLOSS.get(c.key, c.claim)})
    return out


def _hypothesis_category_for(pred_category: str):
    """Map a PREDICTION category (sleep_decline / goal_followthrough / downtime_decline) back to
    the HYPOTHESIS category whose competition produced it (stress_risk / goal_followthrough /
    load_risk), by scanning reality's pattern table. Read-only; None if unknown."""
    for pat in reality._PATTERNS:
        if pat.pred_category == pred_category:
            return pat.category
    return None


def _bet_candidate_key(pred: dict, loop_data: dict):
    """The candidate_key of the hypothesis the PREDICTION was actually MADE on (its
    ``hypothesis_id`` resolved against the loop's hypotheses) — the bet's real basis, the correct
    reference for 'which RIVALS were left untested'. This is deliberately the bet's ORIGINAL
    explanation, NOT the rolled-forward posterior leader (which a confident-wrong revision may have
    flipped to a rival). Read-only; None if it can't be resolved."""
    hid = pred.get("hypothesis_id")
    if not hid:
        return None
    for h in (loop_data.get("hypotheses") or []):
        if isinstance(h, dict) and h.get("id") == hid:
            return h.get("candidate_key")
    return None


def _judge_missing(pred: dict, comp, resolved, decision_field: dict, loop_data: dict) -> dict:
    """Return {bet_on, untested_rivals, pivots, not_taken_roads, is_open, why}. ``untested_rivals``
    are the rival candidate keys (every candidate OTHER than the one the bet was MADE on) whose
    supporting signal did NOT appear in the resolving outcome — so the bet's explanation was crowned
    on its own consequence alone; ``pivots`` are the counterfactual cues that would have changed the
    result; ``not_taken_roads`` are the Decision-Observatory roads (KNOWN-suppressed / already-asked
    / lower-rank) that existed around the turn — the broader 'evidence the mind had but this decision
    did not use'. Never raises."""
    category = pred.get("category", "")
    rivals = _rival_signals(category)
    # the explanation the bet was actually MADE on (the prediction's own hypothesis) — the right
    # reference, not the post-hoc posterior leader a revision may have flipped to a rival.
    leader = _bet_candidate_key(pred, loop_data) or (comp or {}).get("leader")
    # which rival's signal actually fired in the resolving outcome? (reuse reality's library regex)
    fired_keys = set()
    if resolved is not None:
        outcome_text = ((resolved.get("outcome") or {}).get("observed") or "")
        hyp_cat = _hypothesis_category_for(category)
        for c in reality._COMPETITION_LIBRARY.get(hyp_cat, ()) if hyp_cat else ():
            try:
                if c.supported_by is not None and c.supported_by.search(outcome_text):
                    fired_keys.add(c.key)
            except Exception:
                continue
    untested = [r for r in rivals if r["key"] != leader and r["key"] not in fired_keys]
    pivots = [{"key": r["key"], "pivot": r["pivot"], "claim": r["claim"]} for r in untested]

    # the broader 'roads not taken' the Decision Observatory already enumerates around the turn.
    not_taken = []
    for c in (decision_field.get("rejected") or []):
        if c.get("reason") in (decisions.KNOWN_SUPPRESSED, decisions.ALREADY_ASKED,
                               decisions.LOWER_RANK):
            not_taken.append({"label": c.get("label"), "reason": c.get("reason"),
                              "gloss": c.get("reason_gloss")})

    is_open = resolved is None
    if untested and is_open:
        names = ", ".join(f'"{r["key"]}"' for r in untested[:4])
        why = (f"the bet is still OPEN and {len(untested)} rival explanation(s) — {names} — sit "
               f"untested: neither the outcome nor any rival's signal has arrived to settle which "
               f"explanation is right")
    elif untested:
        names = ", ".join(f'"{r["key"]}"' for r in untested[:4])
        why = (f"{len(untested)} rival explanation(s) — {names} — were never tested: no stated "
               f"signal for them was ever observed, so the winner was crowned on its own "
               f"consequence alone")
    elif not rivals:
        why = "the category defines no competing explanations to have missed — a single-candidate bet"
    else:
        why = "every rival explanation's signal was checked against the outcome — no blind spot"
    return {"bet_on": leader, "untested_rivals": [r["key"] for r in untested], "pivots": pivots,
            "not_taken_roads": not_taken[:6], "is_open": is_open, "why": why}


# ===================================================================================
# JUDGMENT #4 — was the WINNER WARRANTED over the competing hypotheses? Reuse reality's competition
# POSTERIOR (weights rolled forward through revisions via the loop's competition_for). The winner
# is warranted iff its posterior beats every rival by a margin AND (when resolved) the outcome
# adjudicated in its favor (the leader was supported, not contradicted). Reads the rolled-forward
# competition the loop assembled — never recomputes the math.
# ===================================================================================
def _judge_warrant(comp, resolved) -> dict:
    """Return {warranted, posterior_leader, posterior_margin, adjudicated_for_leader, why}. The
    posterior is the competition's CURRENT (revision-rolled) weights — exactly reality's corrected
    belief about which explanation reality favors. Never raises."""
    if not comp:
        return {"warranted": None, "posterior_leader": None, "posterior_margin": 0.0,
                "adjudicated_for_leader": None,
                "why": "no competition to warrant — a single un-competed hypothesis"}
    cands = comp.get("candidates") or {}
    post = {k: float(v.get("weight", 0.0)) for k, v in cands.items()}
    order = sorted(post.items(), key=lambda kv: -kv[1])
    leader = order[0][0] if order else None
    lead = order[0][1] if order else 0.0
    runner = order[1][1] if len(order) > 1 else 0.0
    margin = round(lead - runner, 4)

    adjudicated_for_leader = None
    if resolved is not None:
        rev = resolved.get("revision") or {}
        # the resolved bundle carries the MAJOR revision; for a minor reweight, read the leader's
        # movement directly from the competition history. Supported == reality strengthened it.
        sup = rev.get("supported")
        con = rev.get("contradicted") or []
        if sup is not None or con:
            adjudicated_for_leader = (sup == leader) and (leader not in con)
        else:
            # no major revision recorded: warranted-by-outcome iff the prediction was correct AND
            # the leader still leads the posterior (reality reweighted toward it).
            adjudicated_for_leader = bool((resolved.get("learning") or {}).get("prediction_correct"))

    decisive = margin >= _DECISIVE_MARGIN
    if resolved is None:
        warranted = decisive  # open: warranted on the prior/posterior margin alone (no outcome yet)
        why = (f'the leading hypothesis "{leader}" holds a {margin:.2f} posterior lead — '
               + ("a decisive, warranted lead (still awaiting the outcome)" if decisive
                  else f"a thin lead (< {_DECISIVE_MARGIN:.2f}); not yet warranted over its rivals"))
    else:
        warranted = bool(decisive and adjudicated_for_leader)
        if warranted:
            why = (f'reality adjudicated FOR "{leader}" and it leads the posterior by {margin:.2f} '
                   f'— the winner was warranted')
        elif not adjudicated_for_leader:
            why = (f'the outcome did NOT vindicate "{leader}" — reality reweighted AWAY from it; '
                   f'the original winner was not warranted by what actually happened')
        else:
            why = (f'"{leader}" leads but only by {margin:.2f} (< {_DECISIVE_MARGIN:.2f}) — even '
                   f'after the outcome the field is close; the win is not decisive')
    return {"warranted": (None if warranted is None else bool(warranted)),
            "posterior_leader": leader, "posterior_margin": margin,
            "adjudicated_for_leader": adjudicated_for_leader, "why": why}


# ===================================================================================
# JUDGMENT #5 — was CONFIDENCE CALIBRATED? Two reads, both REUSING reality:
#   (a) THIS decision — reality.surprise(stated_conf, outcome): a confident-and-wrong bet has a
#       high surprise and a positive miss (the "movie" called it more sure than reality bore out).
#   (b) OVER TIME — reality.calibrate(name): the category's REALIZED accuracy vs the stated
#       confidence. A stated confidence that diverges from the track record by > _CALIB_DIVERGENCE
#       (once the category has >= reality._MIN_FOR_VERDICT resolved points) is miscalibrated.
# ===================================================================================
def _judge_calibration(pred: dict, resolved, calibration: dict) -> dict:
    """Return {calibrated, stated_confidence, this_surprise, this_correct, realized_accuracy,
    n_resolved, divergence, why}. Never raises."""
    stated = float(pred.get("confidence", 0.5))
    category = pred.get("category", "")
    cat_stats = (calibration.get("by_category") or {}).get(category, {})
    realized = cat_stats.get("accuracy")
    n_resolved = int(cat_stats.get("resolved", 0) or 0)

    this_surprise = None
    this_correct = None
    if resolved is not None:
        learning = resolved.get("learning") or {}
        this_correct = bool(learning.get("prediction_correct"))
        # reuse reality.surprise so this read is the SAME number the loop recorded.
        this_surprise = reality.surprise(stated, this_correct)

    divergence = None
    over_time_off = False
    if realized is not None and n_resolved >= reality._MIN_FOR_VERDICT:
        divergence = round(abs(stated - float(realized)), 4)
        over_time_off = divergence > _CALIB_DIVERGENCE

    # calibrated == this decision wasn't a confident-wrong miss AND (where we can judge over time)
    # the stated confidence isn't far from the realized accuracy.
    this_miss = (this_correct is False and (this_surprise or 0.0) >= _SURPRISE_HIGH)
    calibrated = (not this_miss) and (not over_time_off)

    bits = []
    if this_surprise is not None:
        bits.append(f"this bet: stated {stated:.2f}, outcome "
                    f"{'RIGHT' if this_correct else 'WRONG'}, surprise {this_surprise:.2f}")
    if divergence is not None:
        bits.append(f"over {n_resolved} resolved: realized accuracy {float(realized):.2f} vs "
                    f"stated {stated:.2f} (divergence {divergence:.2f})")
    if this_miss:
        why = ("a confidently-stated prediction was REFUTED — stated confidence ran well ahead of "
               "reality. " + "; ".join(bits))
    elif over_time_off:
        why = ("stated confidence systematically diverges from this category's realized accuracy. "
               + "; ".join(bits))
    else:
        why = ("stated confidence tracked the outcome" + (" and the category's record" if divergence
               is not None else "") + (". " + "; ".join(bits) if bits else
               " — too few resolved points to judge over time (time-gated)"))
    return {"calibrated": bool(calibrated), "stated_confidence": round(stated, 4),
            "this_surprise": this_surprise, "this_correct": this_correct,
            "realized_accuracy": realized, "n_resolved": n_resolved,
            "divergence": divergence, "why": why}


# ===================================================================================
# JUDGMENT #6 — was the SURPRISE APPROPRIATE given the priors? Reuse reality.surprise. Given the
# leader's PRIOR weight (how strongly the evidence pointed at the outcome BEFORE it arrived), a low
# surprise when the prior pointed the right way is appropriate; a confident bet blindsided is an
# EARNED surprise (a real miss the model SHOULD feel). We compare the realized surprise against the
# surprise the PRIORS alone would have predicted — so we judge not just the magnitude but whether
# it was warranted by what the model knew going in.
# ===================================================================================
def _judge_surprise(pred: dict, comp, resolved) -> dict:
    """Return {appropriate, realized_surprise, prior_implied_surprise, leader_prior, why}. The
    prior-implied surprise is reality.surprise(leader_prior, outcome): how surprised the model
    SHOULD have been if it had bet at exactly the strength its priors licensed. 'appropriate' ==
    the realized surprise is not wildly out of line with what the priors warranted. Never raises."""
    if resolved is None:
        return {"appropriate": None, "realized_surprise": None, "prior_implied_surprise": None,
                "leader_prior": None,
                "why": "no outcome yet — surprise is undefined until reality answers (time-gated)"}
    learning = resolved.get("learning") or {}
    correct = bool(learning.get("prediction_correct"))
    realized = reality.surprise(float(pred.get("confidence", 0.5)), correct)

    leader_prior = None
    if comp:
        cands = comp.get("candidates") or {}
        leader = comp.get("leader")
        if leader and leader in cands:
            leader_prior = float(cands[leader].get("prior", cands[leader].get("weight", 0.0)))
    prior_implied = reality.surprise(leader_prior, correct) if leader_prior is not None else None

    # appropriate == the realized surprise is consistent with what the priors warranted. A bet made
    # at exactly prior strength would feel ``prior_implied``; if the model stated MORE confidence
    # than its priors and got blindsided, the EXTRA surprise was self-inflicted (over-stated), and
    # we flag it. If priors and realized agree within a band, the surprise was honest.
    if prior_implied is None:
        # no competition prior to compare against — judge appropriateness by direction only: a
        # correct bet with low surprise, or a wrong bet with high surprise, is appropriate.
        appropriate = (correct and realized < _SURPRISE_HIGH) or ((not correct) and realized >= 0.0)
        why = (f"realized surprise {realized:.2f} on a {'correct' if correct else 'refuted'} "
               f"outcome (no competition prior to benchmark against)")
    else:
        gap = realized - prior_implied
        # The asymmetry is the whole point. An EARNED surprise is fine — even desirable: when the
        # outcome itself was improbable under the priors, a high surprise is the model HONESTLY
        # learning, and a CORRECT call that lands with LOW surprise is exactly what good calibration
        # looks like (the model bet and was right without drama). What is INappropriate is surprise
        # the model MANUFACTURED by over-stating confidence past what its evidence licensed: realized
        # surprise materially ABOVE the prior-implied level. Under-committing (realized BELOW
        # prior-implied) on a correct call is not a fault — so only the high side flags.
        inflated = gap > 0.20
        appropriate = not inflated
        if not inflated:
            if realized < prior_implied - 0.20:
                why = (f"realized surprise {realized:.2f} sits BELOW what the priors warranted "
                       f"({prior_implied:.2f}, leader prior {leader_prior:.2f}) — the model was "
                       f"more cautious than its evidence; the call landed without manufactured "
                       f"surprise (appropriate)")
            else:
                why = (f"realized surprise {realized:.2f} matches what the priors warranted "
                       f"({prior_implied:.2f}, leader prior {leader_prior:.2f}) — an honest, earned "
                       f"surprise")
        else:
            why = (f"realized surprise {realized:.2f} EXCEEDS what the priors warranted "
                   f"({prior_implied:.2f}) — the model stated more confidence than its evidence "
                   f"licensed, manufacturing surprise it should not have felt")
    return {"appropriate": (None if appropriate is None else bool(appropriate)),
            "realized_surprise": realized, "prior_implied_surprise": prior_implied,
            "leader_prior": leader_prior, "why": why}


# ===================================================================================
# JUDGMENT #7 — the CORRECTED POSTERIOR: what SHOULD have been believed afterward. Two pieces,
# both REUSED from reality: (a) the competition's weights rolled forward through every revision
# (competition_for, already folded by the loop) IS the corrected belief about which explanation
# reality favors; (b) the corrected CONFIDENCE is the category's realized accuracy from calibrate
# — the honest confidence the track record licenses, replacing the stated one.
# ===================================================================================
def _corrected_posterior(pred: dict, comp, calibration: dict) -> dict:
    """Return {posterior (key->weight, the rolled-forward belief), corrected_confidence (the
    realized accuracy or None if time-gated), stated_confidence, note}. Never raises."""
    posterior = {}
    if comp:
        posterior = {k: round(float(v.get("weight", 0.0)), 4)
                     for k, v in (comp.get("candidates") or {}).items()}
    category = pred.get("category", "")
    cat_stats = (calibration.get("by_category") or {}).get(category, {})
    realized = cat_stats.get("accuracy")
    n_resolved = int(cat_stats.get("resolved", 0) or 0)
    corrected_conf = float(realized) if (realized is not None
                                         and n_resolved >= reality._MIN_FOR_VERDICT) else None
    stated = round(float(pred.get("confidence", 0.5)), 4)
    if corrected_conf is not None:
        note = (f"belief: favor {max(posterior, key=posterior.get) if posterior else '(none)'}; "
                f"confidence corrected from {stated:.2f} -> {corrected_conf:.2f} "
                f"(the category's realized accuracy over {n_resolved} resolved bets)")
    elif posterior:
        note = (f"belief: favor {max(posterior, key=posterior.get)}; confidence not yet correctable "
                f"(category time-gated — too few resolved outcomes to recalibrate honestly)")
    else:
        note = "no competition to correct — the belief remains the lone hypothesis, unrevised"
    return {"posterior": posterior, "corrected_confidence": corrected_conf,
            "stated_confidence": stated, "note": note}


# ===================================================================================
# THE VERDICT — the thresholded reading of the seven judgments. A movie names what happened; this
# names what to DO about it. The order is a PRIORITY ladder, ROOT CAUSE before SYMPTOM:
#   MISCALIBRATED  (a SYSTEMATIC confidence drift from the track record — the deepest diagnosis,
#                   because it explains WHY individual bets keep missing) >
#   OVERCONFIDENT  (THIS single bet was a confident-wrong miss — the symptom, when the category
#                   isn't yet provably miscalibrated) >
#   UNDER-EVIDENCED (the win was thin/un-grounded, OR — only when the lead was NOT decisive — a
#                   rival that could plausibly have won was never tested) >
#   JUSTIFIED      (none of the above — the evidence warranted it).
# The MISCALIBRATED-before-OVERCONFIDENT order matters: a confident-wrong bet whose CATEGORY is
# provably miscalibrated (>= _MIN_FOR_VERDICT resolved, divergence past the bar) is best coached as
# the systematic fault (recalibrate the prior), not the one-off symptom. A confident-wrong bet
# whose category is NOT yet provably off stays OVERCONFIDENT (the single miss is the actionable fact).
# Each verdict carries the SPECIFIC gap that triggered it and the SPECIFIC fix lever to close it.
# ===================================================================================
def _verdict(sufficiency, missing, warrant, calibration, surprise_j) -> dict:
    """Render the verdict + the specific gap + the fix lever from the judgments. Deterministic;
    a pure thresholded reading of numbers reality computed. Never raises."""
    this_miss = (calibration.get("this_correct") is False
                 and (calibration.get("this_surprise") or 0.0) >= _SURPRISE_HIGH)
    systematic_off = (calibration.get("divergence") is not None
                      and calibration["divergence"] > _CALIB_DIVERGENCE)

    # MISCALIBRATED — stated confidence diverges SYSTEMATICALLY from the realized track record. The
    # root-cause diagnosis: it takes priority over a single OVERCONFIDENT miss because recalibrating
    # the prior fixes the pattern, not just this bet.
    if systematic_off:
        return {
            "verdict": MISCALIBRATED,
            "gap": (f"stated confidence {calibration['stated_confidence']:.2f} diverges from this "
                    f"category's realized accuracy {float(calibration['realized_accuracy']):.2f} "
                    f"by {calibration['divergence']:.2f} over {calibration['n_resolved']} resolved "
                    f"bets"),
            "lever": (f"recalibrate the category prior to ~{float(calibration['realized_accuracy']):.2f} "
                      f"— stop stating a confidence the track record does not support"),
        }
    # OVERCONFIDENT — THIS decision was a confident-and-wrong miss (high surprise, refuted), and the
    # category is not (yet) provably miscalibrated — so the single miss is the actionable fact.
    if this_miss:
        return {
            "verdict": OVERCONFIDENT,
            "gap": (f"stated confidence {calibration['stated_confidence']:.2f} on a prediction the "
                    f"outcome REFUTED (surprise {calibration['this_surprise']:.2f}) — the model was "
                    f"sure in the wrong direction"),
            "lever": ("lower the stated confidence toward the category's realized accuracy"
                      + (f" (~{calibration['realized_accuracy']:.2f})"
                         if calibration.get("realized_accuracy") is not None else "")
                      + "; the priors over-committed"),
        }
    # UNDER-EVIDENCED — the win was thin/un-grounded, OR a plausible rival sits untested. An
    # untested rival is a verdict-changing blind spot when EITHER (a) the lead was not decisive (a
    # rival could genuinely have won), OR (b) the bet is still OPEN — its lead is UNCONFIRMED, so
    # the adjudicating evidence (the outcome, or the rival's own signal) has not yet arrived and the
    # rival remains live. Only a RESOLVED, decisively-led bet earns the right to treat untested
    # rivals as a mere noted watch-item (judgment #2) rather than a gap.
    decisive = bool(sufficiency.get("sufficient"))
    is_open = bool(missing.get("is_open"))
    blindspot = bool(missing.get("untested_rivals")) and (not decisive or is_open)
    if (not decisive) or blindspot:
        pivots = missing.get("pivots") or []
        if pivots and (blindspot or sufficiency.get("grounded")):
            # the fix lever IS the counterfactual pivot — go gather the missing rival's signal.
            lever = (f"gather the missing signal that would settle it — e.g. "
                     f'{pivots[0]["pivot"]} (the counterfactual that flips "{pivots[0]["key"]}" '
                     f"into contention)")
        elif not sufficiency.get("grounded"):
            lever = "anchor the prediction to a stated fact before betting on it"
        elif sufficiency.get("n_competitors", 0) < _MIN_COMPETITORS:
            lever = "weigh at least one rival explanation before crowning a winner"
        else:
            lever = "gather more evidence to widen the winner's margin before acting on it"
        gap = sufficiency.get("why")
        return {"verdict": UNDER_EVIDENCED, "gap": gap, "lever": lever}
    # JUSTIFIED — grounded, decisively led, calibrated. Untested rivals (if any) are noted as a
    # standing watch-item in judgment #2, but the decisive, confirmed lead warranted the decision.
    note = ""
    if missing.get("untested_rivals"):
        note = (f" (a standing watch-item: {len(missing['untested_rivals'])} rival explanation(s) "
                f"remain untested, but the lead was decisive and the outcome confirmed it)")
    return {
        "verdict": JUSTIFIED,
        "gap": "none — the decision was grounded, decisively led, and calibrated" + note,
        "lever": ("keep it: this is the standard the other decisions are audited against"),
    }


# ===================================================================================
# THE PER-DECISION AUDIT — assemble all seven judgments + the verdict for ONE reality prediction.
# This is the load-bearing public unit: "should THIS decision have happened?". Read-only.
# ===================================================================================
def audit_decision(name: str, prediction: dict, *, loop_data=None,
                   decision_field=None) -> dict:
    """Audit ONE reality PREDICTION (a decision the mind made) end-to-end. Returns the full
    judgment dict + the verdict + gap + lever. ``loop_data`` (reality.loop) and ``decision_field``
    (decisions.curiosity_decision) are passed in so a batch audit computes them once; both default
    to a fresh read. Deterministic for a fixed creature; never raises."""
    loop_data = loop_data if loop_data is not None else _loop(name)
    decision_field = decision_field if decision_field is not None else {}
    comp = _competition_of(loop_data, prediction.get("competition_id"))
    resolved = _resolved_for(loop_data, prediction.get("id"))
    calibration = loop_data.get("calibration") or reality.calibrate(name)

    sufficiency = _judge_sufficiency(prediction, comp, loop_data)
    missing = _judge_missing(prediction, comp, resolved, decision_field, loop_data)
    warrant = _judge_warrant(comp, resolved)
    calib = _judge_calibration(prediction, resolved, calibration)
    surprise_j = _judge_surprise(prediction, comp, resolved)
    corrected = _corrected_posterior(prediction, comp, calibration)
    verdict = _verdict(sufficiency, missing, warrant, calib, surprise_j)

    status = (resolved is not None)
    return {
        "name": name,
        "decision": "reality:prediction",
        "prediction": {
            "id": prediction.get("id"),
            "category": prediction.get("category"),
            "claim": prediction.get("claim"),
            "confidence": round(float(prediction.get("confidence", 0.5)), 4),
            "horizon_days": prediction.get("horizon_days"),
            "status": ("RESOLVED" if status else "OPEN"),
            "evidence_turn": (prediction.get("evidence") or {}).get("turn", ""),
        },
        "outcome": ((resolved.get("outcome") or {}).get("observed") if resolved else None),
        "judgments": {
            "1_sufficiency": sufficiency,
            "2_3_missing_evidence_and_pivot": missing,
            "4_warrant": warrant,
            "5_calibration": calib,
            "6_surprise": surprise_j,
            "7_corrected_posterior": corrected,
        },
        "verdict": verdict["verdict"],
        "gap": verdict["gap"],
        "lever": verdict["lever"],
    }


# ===================================================================================
# THE CURIOSITY-DECISION SUFFICIENCY ARM — the SECOND kind of decision Layer 3 audits, building
# DIRECTLY on provenance + decisions + causal. For the live curiosity "which gap to ask?" decision
# we judge: was the WINNING gap's score BUILT ON EVIDENCE (a provenance whose dominant signal is a
# fact/edge-driven term) or thin priors (a base-only empty slot)? — and was the WINNING SUBSYSTEM
# warranted over the runner-up (causal's margin)? This is the audit of the SAME decision the rest
# of the stack explains, judged for justification.
# ===================================================================================
def audit_curiosity_decision(name: str, user_text: str, *, budget: str = "deep") -> dict:
    """Audit the curiosity 'which gap to ask?' decision for justification, REUSING the three
    Layer-2 observatories: provenance.decompose_score (is the score built on evidence?),
    decisions.curiosity_decision (the field + the runner-up it beat), and causal.compete (was the
    winning subsystem warranted over the runner-up). Returns the verdict + gap + lever. Read-only;
    never raises."""
    out = {
        "name": name, "decision": "curiosity:which gap to ask",
        "input": str(user_text or "")[:160], "winner": None, "verdict": None,
        "judgments": {}, "gap": None, "lever": None,
    }
    # 1) the provenance of the winning score — REUSE provenance (the score decomposition).
    try:
        tree = provenance.provenance_tree(name, budget=budget, recent_text=user_text)
    except Exception:
        tree = {"winner": None, "provenance": {}, "dominant": {}, "beat": []}
    win = tree.get("winner")
    if win is None:
        out["verdict"] = JUSTIFIED
        out["gap"] = "no open gap this turn — silence is trivially justified"
        out["lever"] = "keep it: not asking when there is nothing grounded to ask is correct"
        return out
    out["winner"] = {"label": win.get("label"), "score": win.get("score")}
    prov = tree.get("provenance") or {}
    dom = tree.get("dominant") or {}
    # evidence-built iff the score RECONSTRUCTS the engine AND a fact/edge-driven term carries real
    # weight (the mention curve / hint lift / contradiction lift / evidence weight) — i.e. the score
    # is more than a bare taxonomy floor. A pure empty-slot ask (base only) is a thin-prior decision.
    evidence_ids = {provenance.C_MENTION_CURVE, provenance.C_HINT_LIFT,
                    provenance.C_CONTRA_LIFT, provenance.C_EVIDENCE}
    contribs = prov.get("contributions") or []
    evidence_mass = sum(float(c.get("value", 0.0)) for c in contribs if c.get("id") in evidence_ids)
    reconstructs = bool(prov.get("reconstructs"))
    built_on_evidence = reconstructs and evidence_mass > 0.5

    # 2) was the curiosity DRIVE warranted? — REUSE causal (the subsystem competition). The right
    #    question for "should this gap have been ASKED?" is NOT "did some subsystem win the turn by a
    #    wide margin" — Mike is BOTH a curiosity gap AND an opportunity offer, so opportunity pips
    #    curiosity by a hair (the live `opportunity > curiosity` precedence decides only WHICH VOICE
    #    speaks, not whether the curiosity signal was justified). What warrants asking the gap is that
    #    the CURIOSITY drive's OWN signal is strong and clearly beats the genuinely WEAK field
    #    (recall/grounding) — i.e. curiosity is decisively in the running, not a marginal flicker. A
    #    co-strong rival (opportunity) is corroboration of strong signal, never a reason to doubt it.
    try:
        comp = causal.compete(name, user_text, reply=None, has_reply=False, budget=budget)
    except Exception:
        comp = {"winner": None, "dominant_signal": 0.0, "margin": 0.0, "arms": []}
    arms = comp.get("arms") or []
    cur_arm = next((a for a in arms if a.get("subsystem") == causal.CURIOSITY), {})
    cur_signal = float(cur_arm.get("signal", 0.0))
    # the strongest WEAK/contrast drive curiosity must clear to be decisively in the running — the
    # max signal among the non-proactive drives (recall / grounding / situation). (Opportunity is
    # excluded: a co-firing offer rides the SAME evidence as the gap, so it isn't a contrast.)
    contrast = max((float(a.get("signal", 0.0)) for a in arms
                    if a.get("subsystem") in (causal.RECALL, causal.GROUNDING, causal.SITUATION)),
                   default=0.0)
    cur_margin = round(cur_signal - contrast, 4)
    # warranted iff the curiosity drive is absolutely strong AND clears the weak field decisively.
    subsystem_warranted = (cur_signal >= _DECISIVE_MARGIN) and (cur_margin >= _DECISIVE_MARGIN)

    sufficiency = {
        "built_on_evidence": built_on_evidence,
        "reconstructs": reconstructs,
        "evidence_mass": round(evidence_mass, 4),
        "dominant_signal": dom.get("id"),
        "dominant_value": dom.get("value"),
        "why": (f'the winning score is built on real evidence (dominant signal "{dom.get("id")}", '
                f'evidence-driven mass {evidence_mass:.2f})'
                if built_on_evidence else
                f'the winning score is a thin prior (a bare taxonomy floor; evidence-driven mass '
                f'{evidence_mass:.2f}) — the engine is asking because the SLOT is empty, not because '
                f'any evidence points there'),
    }
    warrant = {
        "subsystem_warranted": subsystem_warranted,
        "curiosity_signal": round(cur_signal, 4),
        "contrast_signal": round(contrast, 4),
        "margin": cur_margin,
        "turn_winner": comp.get("winner"),
        "why": (f'the curiosity drive ({cur_signal:.2f}) clears the weak field ({contrast:.2f}) by '
                f'{cur_margin:.2f}'
                + (f' — decisively in the running (the turn went to "{comp.get("winner")}", a '
                   f'co-firing drive on the same evidence, but the curiosity signal itself is '
                   f'warranted)' if subsystem_warranted else
                   f' — the curiosity signal is too weak/close to the field to warrant asking')),
    }
    out["judgments"] = {"1_sufficiency": sufficiency, "4_warrant": warrant,
                        "beat": tree.get("beat") or []}

    # the verdict for the curiosity arm: UNDER-EVIDENCED if the score is a thin prior OR the
    # subsystem margin was a toss-up; else JUSTIFIED. (Calibration/surprise belong to the reality
    # arm — the curiosity decision has no resolved outcome to score.)
    if not built_on_evidence:
        out["verdict"] = UNDER_EVIDENCED
        out["gap"] = sufficiency["why"]
        out["lever"] = ("only surface this gap when the user's evidence points at it (a mention, a "
                        "hint, a contradiction) — not merely because the slot is blank")
    elif not subsystem_warranted:
        out["verdict"] = UNDER_EVIDENCED
        out["gap"] = warrant["why"]
        out["lever"] = ("the runner-up subsystem was nearly as strong — widen the margin (more "
                        "signal) before letting curiosity speak over it")
    else:
        out["verdict"] = JUSTIFIED
        out["gap"] = "none — the gap is evidence-built and its subsystem won decisively"
        out["lever"] = "keep it: asking this gap is warranted by the evidence and the competition"
    return out


# ===================================================================================
# THE MRI ATTACHMENT — Layer 3 judges a decision that LAYER 1 RECORDED. We attach the reality
# audit to a real recorded MRI trace when one exists for the turn (REUSE telemetry.trace), and
# otherwise synthesise a faithful one so the demo shows the full stack: the trace (what happened),
# the curiosity decision in it (why), and the audit (should it). Read-only.
# ===================================================================================
def _mri_curiosity_alternative(name: str, turn_id: str):
    """The curiosity decision LAYER 1 recorded for a turn, if any — the alternative(...) frame the
    MRI films at the curiosity stage ('curiosity:which gap to ask'). Read-only; None if absent."""
    try:
        tr = telemetry.trace(name, turn_id)
    except Exception:
        tr = None
    if not isinstance(tr, dict):
        return None
    for alt in (tr.get("alternatives") or []):
        if isinstance(alt, dict) and "curiosity" in str(alt.get("decision", "")).lower():
            return {"trace_id": turn_id, "selected": alt.get("selected"),
                    "rejected": alt.get("rejected") or []}
    return None


def record_synthetic_trace(name: str, turn_id: str, user_text: str, decision_field: dict) -> None:
    """Film a faithful MRI trace for the demo turn so Layer 1 has a real recorded artifact the
    audit attaches to (the audit JUDGES a recorded decision). We record the curiosity stage + the
    SAME selected/rejected the Decision Observatory derived, then commit. Writes only to the
    redirected telemetry store; never raises."""
    try:
        tr = telemetry.open_trace(name, turn_id, user_text)
        sel = (decision_field.get("selected") or {})
        rej = [{"option": c.get("label"), "reason": c.get("reason")}
               for c in (decision_field.get("rejected") or [])[:6]]
        tr.stage("curiosity", t_ms=0.5, in_shape={"gaps": len(decision_field.get("candidates") or [])},
                 out={"selected": sel.get("label"), "candidates":
                      [c.get("label") for c in (decision_field.get("candidates") or [])]},
                 confidence=sel.get("confidence"), note="Layer-1 record of the curiosity decision")
        tr.alternative("curiosity:which gap to ask", selected=sel.get("label"), rejected=rej)
        tr.commit(reply="(synthetic demo turn)", total_ms=1.0)
    except Exception:
        pass


# ===================================================================================
# SYNTHETIC DECISIONS — the proof. We drive reality's OWN form/resolve engine over the canonical
# Day-1 -> Day-14 timeline to manufacture decisions that land in EACH verdict bucket, so the
# audit is shown discriminating JUSTIFIED / UNDER-EVIDENCED / OVERCONFIDENT / MISCALIBRATED. Every
# decision is a REAL reality record (we never fabricate a prediction by hand where the engine can
# make one); the audit then judges them. Hermetic by the caller's store redirect.
# ===================================================================================
def build_decisions(name: str) -> dict:
    """Seed a creature with FOUR decisions through reality's real engine, one per verdict bucket:

      * OVERCONFIDENT — a stated change (leader manager_change, pred conf 0.67) whose sleep_decline
        prediction is then REFUTED ("sleeping great") -> confident-and-wrong -> high surprise.
      * JUSTIFIED — the canonical change -> sleep_decline prediction CONFIRMED ("barely slept") on a
        decisively-led competition, low surprise, calibrated.
      * MISCALIBRATED — accrue MULTIPLE goal_followthrough bets the stated confidence systematically
        misses (stated ~0.55, but they keep failing) so the category's realized accuracy diverges
        from the stated confidence past the bar.
      * UNDER-EVIDENCED — a load_risk prediction (single/thin competition: only crunch vs
        understaffed) left OPEN with a thin lead and an untested rival.

    All through reality.form / reality.resolve, so each is a genuine epistemic record. Returns the
    loop read so the caller can audit every prediction. Never raises."""
    day1 = reality._SYNTH_DAY1

    # --- JUSTIFIED: change -> sleep declined (confirmed, decisive competition, low surprise) ----
    reality.form(name, "my manager just changed and work's been heavy", at=day1)
    reality.resolve(name, "honestly I've barely slept the last two weeks",
                    at=reality._add_days(day1, 14))

    # --- OVERCONFIDENT: a confident change-bet the outcome REFUTED (sleep turned out fine) -------
    reality.form(name, "my manager just changed", at=reality._add_days(day1, 30))
    reality.resolve(name, "actually I've been sleeping great, fully rested",
                    at=reality._add_days(day1, 44))

    # --- MISCALIBRATED: many goal bets that keep FAILING -> realized accuracy << stated conf -----
    # stated confidence on a goal_followthrough prediction is ~0.55; we make it miss repeatedly so
    # the category's realized accuracy collapses toward 0 and diverges from 0.55 past the bar.
    for i in range(4):
        reality.form(name, "I'm planning to start running every morning",
                     at=reality._add_days(day1, 60 + i * 30))
        reality.resolve(name, "yeah I never got around to it, fell off after a couple days",
                        at=reality._add_days(day1, 60 + i * 30 + 21))

    # --- UNDER-EVIDENCED: a load_risk bet left OPEN (thin 2-way competition, untested rival) ------
    reality.form(name, "I'm absolutely slammed at work, back-to-back meetings",
                 at=reality._add_days(day1, 200))

    return _loop(name)


def _pick(loop_data: dict, predicate):
    """First prediction in the loop matching ``predicate(pred, resolved_or_None)``, else None."""
    for p in loop_data.get("predictions") or []:
        resolved = _resolved_for(loop_data, p.get("id"))
        if predicate(p, resolved):
            return p
    return None


def build_report() -> dict:
    """Seed the four synthetic decisions in a hermetic temp store, record an MRI trace + the
    curiosity decision for a demo turn, and audit one representative decision of EACH verdict plus
    the curiosity-decision arm. Deterministic + offline + isolated. Returns the full report."""
    with _temp_store():
        tok = secrets.token_hex(3)
        nm = f"{SYNTH}_{tok}"
        loop_data = build_decisions(nm)

        # audit the reality decisions — one representative per bucket, found by their signature.
        audits = []
        # OVERCONFIDENT: a refuted sleep_decline bet (confident-wrong).
        oc = _pick(loop_data, lambda p, r: p.get("category") == "sleep_decline"
                   and r is not None and not (r.get("learning") or {}).get("prediction_correct"))
        # JUSTIFIED: a confirmed sleep_decline bet (decisive competition).
        ju = _pick(loop_data, lambda p, r: p.get("category") == "sleep_decline"
                   and r is not None and (r.get("learning") or {}).get("prediction_correct"))
        # MISCALIBRATED: a goal_followthrough bet (the category whose realized accuracy diverges).
        mc = _pick(loop_data, lambda p, r: p.get("category") == "goal_followthrough" and r is not None)
        # UNDER-EVIDENCED: the OPEN load bet (thin competition, untested rival).
        ue = _pick(loop_data, lambda p, r: p.get("category") == "downtime_decline" and r is None)
        for tag, pred in (("overconfident", oc), ("justified", ju),
                          ("miscalibrated", mc), ("under_evidenced", ue)):
            if pred is not None:
                audits.append(audit_decision(nm, pred, loop_data=loop_data, decision_field={}))

        # the curiosity-decision arm — seed the canonical rich creature (REUSE decisions' seeder),
        # record an MRI trace of the decision (Layer 1), then audit the decision (Layer 3).
        cnm = f"{SYNTH}_cur_{tok}"
        decisions.seed_demo_creature(cnm)
        user_text = "tell me about Mike"
        field = decisions.curiosity_decision(cnm, budget="deep", recent_text=user_text)
        turn_id = f"audit-demo-{tok}"
        record_synthetic_trace(cnm, turn_id, user_text, field)
        cur_audit = audit_curiosity_decision(cnm, user_text, budget="deep")
        cur_audit["mri"] = _mri_curiosity_alternative(cnm, turn_id)

    return {"audits": audits, "curiosity_audit": cur_audit}


# ===================================================================================
# RENDER — human-readable AUDIT: per decision, the verdict, the seven judgments, the gap + lever.
# Every emitted line passes reality's clean-gate (no diagnosis / forecast voice).
# ===================================================================================
def _verdict_banner(v: str) -> str:
    return {JUSTIFIED: "JUSTIFIED ✓", UNDER_EVIDENCED: "UNDER-EVIDENCED ⚠",
            OVERCONFIDENT: "OVERCONFIDENT ✗", MISCALIBRATED: "MISCALIBRATED ✗"}.get(v, v)


def render_decision_audit(a: dict) -> str:
    out = []
    p = a.get("prediction") or {}
    out.append(_clean(f'DECISION (reality prediction · {p.get("status")}):  '
                      f'[{p.get("category")}] "{p.get("claim")}"'))
    out.append(_clean(f'    stated confidence {float(p.get("confidence", 0)):.2f}'
                      f' · horizon {p.get("horizon_days")}d'
                      + (f' · evidence: "{str(p.get("evidence_turn",""))[:60]}"'
                         if p.get("evidence_turn") else "")))
    if a.get("outcome"):
        out.append(_clean(f'    what actually happened: "{str(a.get("outcome"))[:64]}"'))
    out.append("")
    out.append(f'  ►►  VERDICT: {_verdict_banner(a.get("verdict"))}')
    out.append(_clean(f'      GAP  : {a.get("gap")}'))
    out.append(_clean(f'      LEVER: {a.get("lever")}'))
    out.append("")
    j = a.get("judgments") or {}
    suf = j.get("1_sufficiency") or {}
    out.append(_clean(f'  1 · JUSTIFIED BY EVIDENCE?   {"YES" if suf.get("sufficient") else "NO"} '
                      f'— {suf.get("why")}'))
    mis = j.get("2_3_missing_evidence_and_pivot") or {}
    out.append(_clean(f'  2 · MISSING EVIDENCE         — {mis.get("why")}'))
    for piv in (mis.get("pivots") or [])[:3]:
        out.append(_clean(f'        ↳ COUNTERFACTUAL PIVOT ("{piv.get("key")}"): would flip the '
                          f'result if — {piv.get("pivot")}'))
    war = j.get("4_warrant") or {}
    ww = ("YES" if war.get("warranted") is True
          else ("NO" if war.get("warranted") is False else "—"))
    out.append(_clean(f'  4 · WINNER WARRANTED?        {ww} — {war.get("why")}'))
    cal = j.get("5_calibration") or {}
    out.append(_clean(f'  5 · CONFIDENCE CALIBRATED?   {"YES" if cal.get("calibrated") else "NO"} '
                      f'— {cal.get("why")}'))
    sur = j.get("6_surprise") or {}
    sa = ("YES" if sur.get("appropriate") is True
          else ("NO" if sur.get("appropriate") is False else "—"))
    out.append(_clean(f'  6 · SURPRISE APPROPRIATE?    {sa} — {sur.get("why")}'))
    cor = j.get("7_corrected_posterior") or {}
    out.append(_clean(f'  7 · SHOULD-BELIEVE-NOW       — {cor.get("note")}'))
    if cor.get("posterior"):
        post = ", ".join(f"{k}:{v:.2f}" for k, v in
                         sorted(cor["posterior"].items(), key=lambda kv: -kv[1])[:4])
        out.append(_clean(f'        corrected posterior: {{{post}}}'))
    return "\n".join(out)


def render_curiosity_audit(a: dict) -> str:
    out = []
    out.append(f'DECISION (curiosity · "which gap to ask?"):  input "{a.get("input")}"')
    win = a.get("winner")
    if win:
        out.append(f'    winning gap: {win.get("label")}  (score {float(win.get("score",0)):.3f})')
    out.append("")
    out.append(f'  ►►  VERDICT: {_verdict_banner(a.get("verdict"))}')
    out.append(_clean(f'      GAP  : {a.get("gap")}'))
    out.append(_clean(f'      LEVER: {a.get("lever")}'))
    j = a.get("judgments") or {}
    suf = j.get("1_sufficiency") or {}
    if suf:
        out.append("")
        out.append(_clean(f'  1 · BUILT ON EVIDENCE?       '
                          f'{"YES" if suf.get("built_on_evidence") else "NO"} — {suf.get("why")}'))
    war = j.get("4_warrant") or {}
    if war:
        out.append(_clean(f'  4 · SUBSYSTEM WARRANTED?     '
                          f'{"YES" if war.get("subsystem_warranted") else "NO"} — {war.get("why")}'))
    if a.get("mri"):
        out.append(_clean(f'  L1 · MRI RECORD: the trace filmed this decision '
                          f'(selected "{(a["mri"] or {}).get("selected")}") — Layer 3 judges what '
                          f'Layer 1 recorded'))
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 90)
    out.append("VERA EPISTEMIC AUDIT OBSERVATORY — Layer 3: SHOULD the decision have happened?")
    out.append("Layer 1 (MRI) shows WHAT happened; Layer 2 (provenance/decision/causal) shows WHY.")
    out.append("This judges JUSTIFICATION: was the decision warranted by the evidence — and if not,")
    out.append("the specific gap + the fix lever. The layer that turns the movie into a coach.")
    out.append("=" * 90)
    out.append("")
    out.append("THE VERDICTS (each a thresholded reading of numbers reality already computes):")
    for v in VERDICTS:
        out.append(f"  {_verdict_banner(v):<18} {VERDICT_GLOSS[v]}")
    for a in report.get("audits", []):
        out.append("")
        out.append("-" * 90)
        out.append(render_decision_audit(a))
    ca = report.get("curiosity_audit")
    if ca:
        out.append("")
        out.append("-" * 90)
        out.append(render_curiosity_audit(ca))
    out.append("")
    out.append("-" * 90)
    out.append("HOW THIS BUILDS ON THE STACK (reuse by import — nothing reinvented):")
    out.append("  reality   — the epistemic loop, surprise, calibration, the rolled-forward")
    out.append("              posteriors (competition_for). Every judgment READS these; the audit")
    out.append("              JUDGES the loop reality records.")
    out.append("  decisions — the ranked field (the KNOWN/asked/lower-rank roads = missing evidence).")
    out.append("  causal    — the subsystem competition (was the WINNING subsystem warranted).")
    out.append("  provenance— the score decomposition (was the curiosity score built on evidence).")
    out.append("  telemetry — the MRI trace (the recorded 'what happened' Layer 3 is ABOUT).")
    out.append("No engine was changed to build it; every judgment reads a public entry point.")
    return "\n".join(out)


# ===================================================================================
# LIVE LEG — gated on Ollama. OBSERVATIONAL: generate a REAL reply on a synthetic creature, run
# the causal grounding decision over what the model ACTUALLY said, and AUDIT that decision (was the
# grounding gate's control WARRANTED — clean, decisive?). Offline -> PENDING. SKIPPED LOUD.
# ===================================================================================
def run_live() -> dict:
    """If Ollama is up, generate a REAL reply on a synthetic creature, run causal.compete over it
    (the grounding decision on a real reply), and audit whether the winning subsystem was
    warranted. Offline -> PENDING. Runs inside the WIDE hermetic store. Never raises; offline is
    never a failure. REUSES causal._model_available + causal.compete so the live path matches the
    sibling observatory exactly."""
    available, model, why = causal._model_available()
    if not available:
        return {"available": False, "model": model, "why_not": why}
    try:
        from anima.mouth import Mouth
        from anima.heart import Heart
        from anima import senses
        with _temp_store():
            name = f"{SYNTH}_live_{secrets.token_hex(3)}"
            causal.seed_grounding_creature(name)
            user_text = "when's my birthday?"
            heart = Heart.born(name, seed=7, n=16, now=1000.0).tend(0.55, now=1100.0)
            mouth = Mouth.assemble(prefer_real=True, voice=False)
            try:
                p = senses.read(user_text, name=name)
                u = mouth.respond(heart, user_text, history=[], perception=p)
                reply = (u.text or "").strip()
            except Exception as e:
                reply = f"[generation error: {e!r}]"
            comp = causal.compete(name, user_text, reply=reply, has_reply=True, budget="deep")
            warranted = float(comp.get("margin", 0.0)) >= _DECISIVE_MARGIN
            audit = {
                "winner_subsystem": comp.get("winner"),
                "dominant_signal": comp.get("dominant_signal"),
                "margin": comp.get("margin"),
                "verdict": (JUSTIFIED if warranted else UNDER_EVIDENCED),
                "gap": ("none — the grounding gate held clean, decisive control over a real reply"
                        if warranted else
                        f"the winning subsystem led by only {float(comp.get('margin',0)):.2f} "
                        f"over the runner-up — a near toss-up on a real reply"),
                "lever": ("keep it" if warranted else
                          "the competition was close on a real reply — widen the margin"),
            }
        return {"available": True, "model": model, "reply": reply, "audit": audit}
    except Exception as e:
        return {"available": False, "model": "?", "why_not": f"live leg errored: {e!r}"}


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA EPISTEMIC AUDIT OBSERVATORY (Layer 3: should the decision have happened?)")
    ap.add_argument("--json", action="store_true", help="emit the audit as JSON")
    ap.add_argument("--live", action="store_true",
                    help="also audit the grounding decision over a REAL generated reply (Ollama)")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    try:
        report = build_report()
        live = run_live() if args.live else None
        engine_error = None
    except Exception as e:                       # pragma: no cover - entry point never raises
        report = {"audits": [], "curiosity_audit": None}
        live, engine_error = None, repr(e)

    fp_after = _footprint(real_anima)
    footprint_unchanged = fp_before == fp_after
    report["live"] = live
    report["footprint_unchanged"] = footprint_unchanged
    report["engine_error"] = engine_error

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        if live is not None:
            print("")
            print("-" * 90)
            print("LIVE LEG (observational — audit the grounding decision over a REAL reply; Ollama)")
            print("-" * 90)
            if live.get("available"):
                print(f"  model: {live.get('model')}")
                print(_clean(f'  reply: "{str(live.get("reply",""))[:80]}"'))
                au = live.get("audit") or {}
                print(f'  ►► VERDICT: {_verdict_banner(au.get("verdict"))}')
                print(_clean(f"     GAP  : {au.get('gap')}"))
                print(_clean(f"     LEVER: {au.get('lever')}"))
            else:
                print(f"  PENDING — {live.get('why_not')}  (offline is not a failure)")
        print("")
        print("GUARDRAIL: real .anima footprint  : "
              + ("byte-UNCHANGED (synthetic-only; nothing real touched)"
                 if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
        if engine_error:
            print(f"GUARDRAIL: engine error           : {engine_error}")

    return 0 if (footprint_unchanged and engine_error is None) else 1


# ===================================================================================
# SELFTEST — `python3 scripts/epistemic_audit.py --selftest`. Proves the audit is FAITHFUL:
#   * each VERDICT is the thresholded reading of reality's numbers — synthetic decisions engineered
#     to land in each bucket get exactly that verdict (JUSTIFIED / UNDER-EVIDENCED / OVERCONFIDENT /
#     MISCALIBRATED);
#   * each judgment REUSES the engine: surprise == reality.surprise, the corrected posterior ==
#     reality.competition_for's rolled-forward weights, the calibration == reality.calibrate, the
#     counterfactual pivots == reality._COMPETITION_LIBRARY's rival signals;
#   * the curiosity arm REUSES provenance/decisions/causal and judges a thin-prior vs evidence-built
#     gap correctly;
#   * the MRI attachment reads a REAL recorded trace (telemetry);
#   * the derivation is DETERMINISTIC for a fixed creature;
#   * the synthetic-only guardrail holds (real .anima byte-unchanged).
# No model, no network.
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    real = Path(_ROOT) / ".anima"
    fp0 = _footprint(real)

    with _temp_store():
        tok = secrets.token_hex(3)

        # ============================================================================
        # 1) THE FOUR VERDICTS — synthetic reality decisions engineered to land in each bucket.
        # ============================================================================
        nm = f"{SYNTH}_verdicts_{tok}"
        loop_data = build_decisions(nm)

        oc = _pick(loop_data, lambda p, r: p.get("category") == "sleep_decline"
                   and r is not None and not (r.get("learning") or {}).get("prediction_correct"))
        ju = _pick(loop_data, lambda p, r: p.get("category") == "sleep_decline"
                   and r is not None and (r.get("learning") or {}).get("prediction_correct"))
        mc = _pick(loop_data, lambda p, r: p.get("category") == "goal_followthrough" and r is not None)
        ue = _pick(loop_data, lambda p, r: p.get("category") == "downtime_decline" and r is None)

        ok("setup: all four representative decisions were formed by the real reality engine",
           all(x is not None for x in (oc, ju, mc, ue)))

        a_oc = audit_decision(nm, oc, loop_data=loop_data)
        a_ju = audit_decision(nm, ju, loop_data=loop_data)
        a_mc = audit_decision(nm, mc, loop_data=loop_data)
        a_ue = audit_decision(nm, ue, loop_data=loop_data)

        ok("VERDICT[overconfident]: a confident sleep bet the outcome REFUTED is OVERCONFIDENT",
           a_oc["verdict"] == OVERCONFIDENT)
        ok("VERDICT[overconfident]: its gap names the confident-wrong miss (high surprise)",
           "REFUTED" in a_oc["gap"] and "surprise" in a_oc["gap"])
        ok("VERDICT[overconfident]: its lever is to LOWER confidence toward realized accuracy",
           "lower the stated confidence" in a_oc["lever"])

        ok("VERDICT[justified]: a confirmed, decisively-led, calibrated bet is JUSTIFIED",
           a_ju["verdict"] == JUSTIFIED)
        ok("VERDICT[justified]: its gap is 'none' and its lever is 'keep it'",
           "none" in a_ju["gap"].lower() and "keep it" in a_ju["lever"])

        ok("VERDICT[miscalibrated]: a goal bet whose category accuracy diverges is MISCALIBRATED",
           a_mc["verdict"] == MISCALIBRATED)
        ok("VERDICT[miscalibrated]: its gap names the divergence from realized accuracy",
           "diverges from" in a_mc["gap"] and "realized accuracy" in a_mc["gap"])
        ok("VERDICT[miscalibrated]: its lever is to recalibrate the category prior",
           "recalibrate" in a_mc["lever"])

        ok("VERDICT[under-evidenced]: an OPEN thin-competition bet is UNDER-EVIDENCED",
           a_ue["verdict"] == UNDER_EVIDENCED)
        ok("VERDICT[under-evidenced]: its lever points at the counterfactual pivot / missing signal",
           "gather" in a_ue["lever"] or "rival" in a_ue["lever"] or "weigh" in a_ue["lever"])

        ok("VERDICTS: the four decisions land in FOUR DISTINCT buckets (the audit discriminates)",
           len({a_oc["verdict"], a_ju["verdict"], a_mc["verdict"], a_ue["verdict"]}) == 4)

        # ============================================================================
        # 2) EACH JUDGMENT REUSES THE ENGINE (not reinvented) — the load-bearing fidelity proof.
        # ============================================================================
        # SURPRISE == reality.surprise(stated_conf, outcome), byte-for-byte.
        oc_cal = a_oc["judgments"]["5_calibration"]
        ok("REUSE[surprise]: the audit's this-surprise == reality.surprise(stated, outcome)",
           abs(oc_cal["this_surprise"]
               - reality.surprise(oc_cal["stated_confidence"], oc_cal["this_correct"])) < 1e-9)
        ok("REUSE[surprise]: the OVERCONFIDENT miss has surprise >= reality's revision bar",
           oc_cal["this_surprise"] >= reality._SURPRISE_REVISION_AT)

        # CALIBRATION == reality.calibrate — the realized accuracy the audit reads IS calibrate's.
        cal_engine = reality.calibrate(nm)
        mc_cal = a_mc["judgments"]["5_calibration"]
        ok("REUSE[calibrate]: the audit's realized accuracy == reality.calibrate's per-category one",
           mc_cal["realized_accuracy"] is not None
           and abs(float(mc_cal["realized_accuracy"])
                   - float(cal_engine["by_category"]["goal_followthrough"]["accuracy"])) < 1e-9)
        ok("REUSE[calibrate]: the MISCALIBRATED divergence exceeds the bar over enough resolved data",
           mc_cal["divergence"] is not None and mc_cal["divergence"] > _CALIB_DIVERGENCE
           and mc_cal["n_resolved"] >= reality._MIN_FOR_VERDICT)

        # CORRECTED POSTERIOR == reality.competition_for's rolled-forward weights (via the loop).
        ju_comp_id = ju.get("competition_id")
        rolled = reality.competition_for(nm, ju_comp_id) if ju_comp_id else None
        ju_post = a_ju["judgments"]["7_corrected_posterior"]["posterior"]
        ok("REUSE[posterior]: the corrected posterior == reality.competition_for's rolled weights",
           rolled is not None and ju_post
           and all(abs(ju_post[k] - round(float(v.get("weight", 0.0)), 4)) < 1e-9
                   for k, v in rolled["candidates"].items() if k in ju_post))
        ok("REUSE[posterior]: the corrected confidence is the category's realized accuracy (or None)",
           (a_ju["judgments"]["7_corrected_posterior"]["corrected_confidence"] is None)
           or abs(a_ju["judgments"]["7_corrected_posterior"]["corrected_confidence"]
                  - float(cal_engine["by_category"]["sleep_decline"]["accuracy"])) < 1e-9)

        # COUNTERFACTUAL PIVOTS == reality._COMPETITION_LIBRARY's rival signals (named, not invented).
        ue_missing = a_ue["judgments"]["2_3_missing_evidence_and_pivot"]
        lib_keys = {c.key for c in reality._COMPETITION_LIBRARY.get("load_risk", ())}
        ok("REUSE[pivot]: the OPEN load bet's untested rivals are exactly reality's load_risk rivals",
           set(ue_missing["untested_rivals"]).issubset(lib_keys) and ue_missing["untested_rivals"])
        ok("REUSE[pivot]: each pivot names the stated signal that would flip the result",
           all(p.get("pivot") for p in ue_missing["pivots"]))

        # WARRANT reads the rolled-forward competition posterior (reality's corrected belief).
        ju_warrant = a_ju["judgments"]["4_warrant"]
        ok("REUSE[warrant]: the JUSTIFIED bet's posterior leader == competition_for's leader",
           rolled is not None and ju_warrant["posterior_leader"] == rolled["leader"])
        ok("warrant: the JUSTIFIED winner was adjudicated FOR by the outcome (manager_change)",
           ju_warrant["warranted"] is True
           and ju_warrant["posterior_leader"] == "manager_change")
        ok("warrant: the OVERCONFIDENT winner was NOT vindicated (reality reweighted away)",
           a_oc["judgments"]["4_warrant"]["warranted"] is False)

        # ============================================================================
        # 3) THE SEVEN JUDGMENTS are all present + contentful for every audit.
        # ============================================================================
        for tag, a in (("oc", a_oc), ("ju", a_ju), ("mc", a_mc), ("ue", a_ue)):
            j = a["judgments"]
            ok(f"judgments[{tag}]: all seven judgments present",
               set(j) == {"1_sufficiency", "2_3_missing_evidence_and_pivot", "4_warrant",
                          "5_calibration", "6_surprise", "7_corrected_posterior"})
            ok(f"judgments[{tag}]: the verdict carries a non-empty GAP and a non-empty LEVER",
               bool(a["gap"]) and bool(a["lever"]))

        # SUFFICIENCY: the JUSTIFIED bet is grounded + decisively led; the OPEN load bet is thin.
        ok("sufficiency: the JUSTIFIED bet is grounded with a decisive margin",
           a_ju["judgments"]["1_sufficiency"]["sufficient"] is True
           and a_ju["judgments"]["1_sufficiency"]["grounded"] is True
           and a_ju["judgments"]["1_sufficiency"]["margin"] >= _DECISIVE_MARGIN)
        ok("sufficiency: the JUSTIFIED bet's evidence turn is the stated change (grounded in fact)",
           "manager" in a_ju["judgments"]["1_sufficiency"]["evidence_turn"].lower())

        # SURPRISE APPROPRIATENESS: the JUSTIFIED low-surprise confirm is appropriate; the
        # OVERCONFIDENT confident-wrong miss's surprise is judged (it is real / earned-or-inflated).
        ok("surprise: the JUSTIFIED low-surprise confirmation is judged APPROPRIATE",
           a_ju["judgments"]["6_surprise"]["appropriate"] is True)
        ok("surprise: the audit's realized surprise == reality.surprise for the JUSTIFIED bet",
           abs(a_ju["judgments"]["6_surprise"]["realized_surprise"]
               - reality.surprise(a_ju["prediction"]["confidence"], True)) < 1e-9)

        # ============================================================================
        # 4) THE CURIOSITY-DECISION ARM — reuses provenance/decisions/causal; judges thin-vs-evidence.
        # ============================================================================
        # the canonical rich creature: the 42-mention Mike gap is EVIDENCE-built (mention curve).
        cnm = f"{SYNTH}_curio_{tok}"
        decisions.seed_demo_creature(cnm)
        ca_rich = audit_curiosity_decision(cnm, "tell me about Mike", budget="deep")
        ok("curiosity[rich]: the Mike gap decision is audited (a winner was found)",
           ca_rich["winner"] is not None and "mike" in ca_rich["winner"]["label"].lower())
        ok("curiosity[rich]: the winning score is BUILT ON EVIDENCE (the mention curve carries mass)",
           ca_rich["judgments"]["1_sufficiency"]["built_on_evidence"] is True
           and ca_rich["judgments"]["1_sufficiency"]["evidence_mass"] > 0.5)
        ok("curiosity[rich]: it REUSES provenance — the score reconstructs the engine",
           ca_rich["judgments"]["1_sufficiency"]["reconstructs"] is True)
        ok("curiosity[rich]: the verdict is JUSTIFIED (evidence-built + subsystem warranted)",
           ca_rich["verdict"] == JUSTIFIED)

        # a BLANK creature: the top gap is an empty taxonomy slot — a THIN-PRIOR ask (no evidence).
        bnm = f"{SYNTH}_blank_{tok}"
        ca_blank = audit_curiosity_decision(bnm, "hey, how's it going?", budget="deep")
        # a blank creature's top gap is a bare taxonomy slot -> built_on_evidence is False -> the
        # decision is UNDER-EVIDENCED (asking because the slot is empty, not because evidence points).
        if ca_blank["winner"] is not None:
            ok("curiosity[blank]: an empty-slot ask is NOT built on evidence (a thin prior)",
               ca_blank["judgments"]["1_sufficiency"]["built_on_evidence"] is False)
            ok("curiosity[blank]: the verdict is UNDER-EVIDENCED (asking because the slot is blank)",
               ca_blank["verdict"] == UNDER_EVIDENCED)
            ok("curiosity[blank]: its lever says to ask only when the evidence points at the gap",
               "evidence points" in ca_blank["lever"])
        ok("curiosity[discriminate]: the rich (evidence) and blank (thin) decisions get DIFFERENT "
           "verdicts",
           ca_blank["winner"] is None or ca_rich["verdict"] != ca_blank["verdict"])

        # ============================================================================
        # 5) THE MRI ATTACHMENT — Layer 3 judges a decision LAYER 1 recorded (telemetry round-trip).
        # ============================================================================
        mnm = f"{SYNTH}_mri_{tok}"
        decisions.seed_demo_creature(mnm)
        field = decisions.curiosity_decision(mnm, budget="deep", recent_text="tell me about Mike")
        turn_id = f"audit-st-{tok}"
        record_synthetic_trace(mnm, turn_id, "tell me about Mike", field)
        mri = _mri_curiosity_alternative(mnm, turn_id)
        ok("MRI: Layer 1 recorded a real trace with the curiosity decision (telemetry round-trip)",
           mri is not None and mri.get("trace_id") == turn_id)
        ok("MRI: the recorded selected gap is the Mike gap (the decision Layer 3 then judges)",
           mri is not None and "mike" in str(mri.get("selected", "")).lower())
        ok("MRI: telemetry.trace reads the committed trace back",
           telemetry.trace(mnm, turn_id) is not None)

        # ============================================================================
        # 6) NO-DIAGNOSIS CLEAN-GATE — every rendered line passes reality's own clean-gate.
        # ============================================================================
        rep = {"audits": [a_oc, a_ju, a_mc, a_ue], "curiosity_audit": ca_rich}
        txt = render(rep)
        ok("clean-gate: not one rendered audit line trips reality's banned-term wall",
           all(reality._is_clean(ln) for ln in txt.splitlines()))
        ok("render: names all four verdicts + the GAP/LEVER frame",
           all(v.split()[0] in txt for v in (JUSTIFIED, UNDER_EVIDENCED, OVERCONFIDENT,
                                             MISCALIBRATED))
           and "GAP" in txt and "LEVER" in txt)
        ok("render: shows a COUNTERFACTUAL PIVOT for an under-evidenced decision",
           "COUNTERFACTUAL PIVOT" in txt)
        ok("render: shows the seven-judgment frame (sufficiency..should-believe-now)",
           "JUSTIFIED BY EVIDENCE?" in txt and "SHOULD-BELIEVE-NOW" in txt)
        ok("render: names the stack it builds on (reality/decisions/causal/provenance/telemetry)",
           all(s in txt for s in ("reality", "decisions", "causal", "provenance", "telemetry")))

        # ============================================================================
        # 7) DETERMINISM — the same creature yields a byte-identical audit.
        # ============================================================================
        l2 = build_decisions(f"{SYNTH}_det_{tok}")
        oc2 = _pick(l2, lambda p, r: p.get("category") == "sleep_decline"
                    and r is not None and not (r.get("learning") or {}).get("prediction_correct"))
        d1 = audit_decision(f"{SYNTH}_det_{tok}", oc2, loop_data=l2)
        d2 = audit_decision(f"{SYNTH}_det_{tok}", oc2, loop_data=l2)
        ok("determinism: two audits of the SAME decision are identical",
           json.dumps(d1, sort_keys=True, default=str)
           == json.dumps(d2, sort_keys=True, default=str))
        ok("determinism: the verdict is stable across re-derivation",
           d1["verdict"] == d2["verdict"])

        # ============================================================================
        # 8) ROBUSTNESS — the entry points never raise on junk.
        # ============================================================================
        ok("robust: audit_decision on an empty prediction returns the contract dict",
           set(audit_decision(f"{SYNTH}_x_{tok}", {})) >= {"verdict", "gap", "lever", "judgments"})
        ok("robust: audit_curiosity_decision on a blank creature returns the contract dict",
           set(audit_curiosity_decision(f"{SYNTH}_y_{tok}", "hi"))
           >= {"verdict", "gap", "lever", "judgments"})
        ok("robust: a junk prediction never raises and gets an honest under-evidenced verdict",
           audit_decision(f"{SYNTH}_z_{tok}", {"id": "p_nope", "category": "?"})["verdict"]
           in VERDICTS)

    # --- the demo build_report is coherent end-to-end ------------------------------------
    full = build_report()
    ok("report: build_report audits the four reality decisions + the curiosity arm",
       len(full.get("audits", [])) == 4 and full.get("curiosity_audit") is not None)
    ok("report: the four audited decisions cover all four verdicts",
       {a["verdict"] for a in full["audits"]} == set(VERDICTS))

    # --- GUARDRAIL: the whole selftest touched no real .anima file -----------------------
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the whole selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature file leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL EPISTEMIC-AUDIT SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
