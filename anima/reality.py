"""reality — THE EPISTEMIC LOOP: Memory + Experience = Knowledge (REASONING, not scorekeeping).

    UNDERSTANDING BEATS REMEMBERING — applied to BEING RIGHT OVER TIME, the honest way.

``memory_lirf`` stores FACTS a person stated. ``world_state`` connects those facts into
SITUATIONS (manager -> stress -> sleep). ``meaning`` ranks what MATTERS now; ``trajectory``
reads the DIRECTION a life is drifting. This module closes the last loop a companion of
thirty years must hold — the one that turns a good memory into genuine LEARNING. Crucially it
does so as REASONING, not fortune-telling:

    observation -> HYPOTHESIS(es, COMPETING) -> prediction -> outcome -> SURPRISE -> learning
                                                                                  -> MODEL REVISION

WHY HYPOTHESIS, NOT BELIEF (epistemic humility — Observed > Assumed). A BELIEF implies
COMMITMENT and a conflict-resolution discipline this system does not yet have. What it forms
is a HYPOTHESIS: a tagged, evidence-anchored, REVISABLE conjecture about the USER's world.
Hypotheses may one day GRADUATE to beliefs — but only once competition + calibration mature
(see the note at ``_COMPETITION_LIBRARY``); that graduation is deliberately NOT built here.

WHY COMPETING HYPOTHESES (the heart of reasoning). A naive model spawns ONE explanation
(manager-changed -> stress) and treats it as truth. Reality offers MANY. So for a situation we
track a SET of competing candidate hypotheses, each with a PRIOR confidence (for rising stress:
manager_change 0.5, recent_move 0.3, family_visit 0.2, multiple 0.1). When an outcome arrives
we ADJUDICATE the competition: the candidate whose prediction reality SUPPORTS is strengthened,
the contradicted ones weakened — a principled, documented, evidence-driven reweighting (not full
Bayes, but normalized and reality-driven). The evolving weights are tracked over time.

WHY SURPRISE (the learning gradient). For each resolved prediction we compute SURPRISE from
(predicted confidence, actual outcome): HIGH when confident-and-WRONG (pred 0.82, outcome false
-> surprise ~0.82) OR doubtful-and-RIGHT (pred 0.11, outcome true -> surprise ~0.89); LOW when
the confidence matched reality. Surprise is the signal that DRIVES learning: a high-surprise
outcome triggers a MODEL REVISION of the competing-hypothesis weights, recorded APPEND-ONLY
(before_weights -> after_weights, the surprise that triggered it, timestamp). A low-surprise
outcome confirms without major revision. Without surprise this is scorekeeping; with it, the
loop LEARNS.

A HYPOTHESIS is a tagged INFERENCE about the USER's world, drawn from REAL evidence (the exact
turn / situation / world-edge it rests on) and carrying its confidence. A PREDICTION is a
hypothesis about a FUTURE outcome plus a time horizon. An OUTCOME is what actually happened,
arriving in a LATER turn. A LEARNING is what we recorded when a prediction RESOLVED against its
outcome: confirmed or refuted, with the SURPRISE. Over many resolved predictions, ``calibrate``
measures — per category — which kinds of prediction Vera gets RIGHT and which she does not.

────────────────────────────────────────────────────────────────────────────────────────────
LAW-LEVEL CONSTRAINTS (non-negotiable — read these before the code)
────────────────────────────────────────────────────────────────────────────────────────────
1. INTERNAL ONLY — NO DIAGNOSIS / NO USER-FACING PREDICTION. This ledger is internal
   model-state + observability, exactly like ``trajectory``'s direction read. It must NEVER
   cause Vera to ASSERT a prediction or a diagnosis to the user ("you'll burn out", "you're
   stressed", "your sleep will decline"). That would violate LAW 003's no-diagnosis wall and
   the #1 product rule. Like ``trajectory``, inference is TRACKED, never DIAGNOSED at the
   user. This is a SHADOW / OFFLINE system: it reads the ALREADY-RECORDED conversation and
   world-state and accrues a ledger. It does NOT touch ``mouth.respond``, ``server._turn``,
   or the live reply. The single place a future LIVE hook would attach is marked with a
   ``LIVE-HOOK`` comment — and is deliberately NOT wired. (Re-grep proof: ``anima.reality`` is
   imported by NOTHING in the live path.)

2. GROUNDED — NO CONFABULATION (#1 rule). A hypothesis is a tagged inference WITH its evidence
   attached; we ``form`` one ONLY when the source carries REAL evidence. Thin/mood-only
   evidence -> NOTHING. We never invent an inner life or an unfounded claim. Every record cites
   the turn it came from (the LAW-003-style "always cite your evidence" invariant). Each
   COMPETING candidate carries the SAME grounding — the competition is over real evidence.

3. TIME-GATED — be honest. Real learning accrues only as real OUTCOMES arrive over real
   CALENDAR TIME (the same wall as longitudinal certification). The MACHINERY — including
   competition, adjudication, surprise, and revision — is built now and PROVEN on a synthetic
   time-series (see ``_selftest`` / ``build_synthetic_loop``). LIVE calibration + surprise
   accrue on their own over real calendar time. Stated up front and in the report.

4. IDENTITY = OBSERVE-ONLY. Hypotheses are about the USER's world, never Vera's identity
   (FROZEN until 2026-07-03). This module never reads, writes, or reasons about persona /
   portrait / identity. Subject of every record is the USER's world.

The ledger is APPEND-ONLY and PER-CREATURE, in its OWN UNIFIED file
``.anima/{name}.reality.jsonl`` (redirectable via ``STORE`` exactly like ``memory_lirf.STORE``
/ ``meaning.STORE``). The whole epistemic loop — hypotheses, competitions, predictions,
outcomes, learnings, AND revisions — lives in this ONE stream (anti-bureaucracy: no fragmenting
into many files), joined by id. It is a SEPARATE file from LIRF / world / meaning. A record is
never overwritten or truncated (LAW 001); an adjudication / a revision APPENDS a new record
that REFERS to prior records by id — it never rewrites a prior line.

Isolation-safe like its siblings: ``world_state`` / ``meaning`` are imported behind
try/except with faithful fallbacks, so this module and its self-test import and run with
nothing else built, touching no model, no network, and no real ``.anima``. Never raises out
of a public entry point — every one degrades to a safe value.

FUTURE ATTACH POINTS (noted, not built): a dedicated Hypothesis/Prediction sub-observatory
would read this ledger's competition + revision streams; a world-model that proposes NEW
candidate hypotheses from ``world_state`` edges would attach at ``_candidates_for`` (it already
seeds competition from the world graph when present). Belief GRADUATION would attach at
``calibrate`` once a category is reliably calibrated. None of these are wired now.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from . import secure_store

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. We BUILD ON (never replace) the world-model: a hypothesis is
# grounded in the world-state's edges/situation, and the COMPETING-hypothesis set can be SEEDED
# from the world graph's edges (a manager edge, a recent-move edge -> rival explanations).
# world_state + meaning are imported behind try/except with contract-faithful fallbacks so this
# module + its selftest run standalone.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from . import world_state as _world
    _HAVE_WORLD = True
except Exception:  # pragma: no cover - isolation fallback
    _world = None  # type: ignore
    _HAVE_WORLD = False

try:  # pragma: no cover - import wiring
    from . import meaning as _meaning
    _HAVE_MEANING = True
except Exception:  # pragma: no cover - isolation fallback
    _meaning = None  # type: ignore
    _HAVE_MEANING = False


# --- THE NO-DIAGNOSIS WALL: reuse meaning's banned-term list verbatim when present, else a
# faithful copy that mirrors trajectory's superset (clinical nouns, diagnosis/prognosis verbs,
# the "see a professional" register, and the second-person-future voice an internal model must
# never adopt). Even though this is a SHADOW system that never speaks, every human-readable
# line it emits passes the SAME clean-gate — defence in depth, identical to trajectory. -------
_BANNED_FALLBACK = (
    "depressed", "depression", "anxiety disorder", "anxious disorder", "anxiety",
    "diagnos",            # diagnose / diagnosis / diagnosed
    "prognos",            # prognosis / prognostic
    "disorder", "mental illness", "mental health condition", "mental health",
    "burnout", "burning out", "burned out", "burnt out",
    "clinical", "clinically",
    "see a doctor", "see a therapist", "see a professional", "seek help",
    "seek professional", "talk to a doctor", "talk to a therapist", "get help",
    "medication", "medicate", "prescription", "therapy", "therapist", "psychiatr",
    "psycholog", "symptom", "syndrome", "patholog", "trauma", "ptsd",
    "suicid", "self-harm", "self harm", "eating disorder", "addiction", "addicted",
    "bipolar", "ocd", "adhd", "panic attack", "nervous breakdown", "breakdown",
    "chronic stress", "manic", "neuros",
    # forecast-creep: a tracked PREDICTION is internal model-state, never a verdict at a person.
    "you will", "you'll end up", "you are going to", "you're going to", "headed for",
    "on track to", "spiral", "downward spiral", "getting worse and worse",
)


def _banned_terms() -> tuple:
    """The banned diagnosis/medical/prognostic terms — meaning's list (UNION our forecast-creep
    terms) when meaning is importable, else the faithful fallback. Reusing meaning's list keeps
    the NO-DIAGNOSIS wall a single source of truth. Defensive; never raises."""
    if _HAVE_MEANING and _meaning is not None:
        base = getattr(_meaning, "BANNED_TERMS", None)
        if isinstance(base, (tuple, list)) and base:
            return tuple(dict.fromkeys(tuple(base) + _BANNED_FALLBACK))
    return _BANNED_FALLBACK


BANNED_TERMS = _banned_terms()


def _is_clean(text: str) -> bool:
    """True iff ``text`` contains NO banned diagnosis/medical/prognostic term (case-insensitive,
    substring). The single gate every human-readable line passes. Pure; never raises."""
    if not text:
        return True
    low = text.lower()
    return not any(term in low for term in BANNED_TERMS)


def _safe_statement(statement: str, fallback: str) -> str:
    """Return ``statement`` if diagnosis-free, else the neutral ``fallback`` (clean by
    construction). The wall holds even if a future phrasing slips a term in."""
    return statement if _is_clean(statement) else fallback


STORE = Path(".anima")
VERSION = 2  # v2: belief -> HYPOTHESIS; + COMPETITION, SURPRISE, REVISION (the epistemic loop)


# ===========================================================================
# RECORD KINDS — the ledger record types of the epistemic loop. Public so callers/tests
# reference them in one place. Every record is a dict with a "kind" tag; the ledger is ONE flat
# append-only stream of them (anti-bureaucracy — never fragmented into many files), joined by
# id: a COMPETITION names its hypotheses; a PREDICTION points at the leading HYPOTHESIS and its
# COMPETITION; an OUTCOME/LEARNING point back at the open PREDICTION; a REVISION points back at
# the COMPETITION it reweighted and the LEARNING (surprise) that triggered it.
# ===========================================================================
HYPOTHESIS = "hypothesis"     # was "belief" (v1). A tagged, evidence-anchored, REVISABLE guess.
COMPETITION = "competition"   # NEW: a SET of competing hypotheses for one situation, weighted.
PREDICTION = "prediction"
OUTCOME = "outcome"
LEARNING = "learning"
REVISION = "revision"         # NEW: an append-only record of a surprise-driven model revision.
KINDS = (HYPOTHESIS, COMPETITION, PREDICTION, OUTCOME, LEARNING, REVISION)

# Prediction lifecycle status.
OPEN = "open"
CONFIRMED = "confirmed"
REFUTED = "refuted"


# ===========================================================================
# THE EVIDENCE-DRIVEN INFERENCE LIBRARY — the heart of GROUNDED hypothesis formation.
#
# Each PATTERN is a conservative, evidence-anchored rule mapping a CLEAR signal in the recorded
# source (a turn the user actually said, or a world-edge they stated) to:
#   * a hypothesis category + claim (an inference about the USER's world), and
#   * OPTIONALLY a prediction category + claim + horizon (when the hypothesis implies a future).
#
# A pattern fires ONLY on real evidence. The cue regexes are anchored, first-person/world-
# stated, and narrow — exactly the never-infer discipline of memory_lirf.extract /
# world_state.capture. Thin or absent evidence matches NOTHING, so ``form`` returns nothing.
#
# Categories are the axes ``calibrate`` reports accuracy over ("which prediction kinds is Vera
# right about?"). They are deliberately small and stable. An OUTCOME signal (what later
# confirms/refutes a prediction) is named per pattern so ``resolve`` can match it.
# ===========================================================================

# A signal of a destabilising CHANGE the user stated (a new manager, a move, a job change, a
# loss) — the canonical "stress_risk" evidence. Anchored to a stated event, never a mood word.
_RE_CHANGE = re.compile(
    r"\b(?:"
    r"(?:my\s+|our\s+|the\s+)?(?:new\s+(?:manager|boss|supervisor|lead|director|role|job)"
    r"|manager\s+(?:just\s+)?(?:changed|left|started)|boss\s+(?:just\s+)?(?:changed|left|started))"
    r"|(?:i|we)\s+(?:just\s+|recently\s+)?(?:moved|relocated)\b"
    r"|(?:i|we)\s+(?:just\s+|recently\s+)?(?:started|changed)\s+(?:a\s+)?(?:new\s+)?jobs?\b"
    r"|(?:i|we)\s+(?:got\s+laid\s+off|lost\s+(?:my|our)\s+job|got\s+a\s+new\s+job)"
    r")\b", re.I)

# A signal that SLEEP actually declined — the OUTCOME that confirms a sleep_decline prediction.
_RE_SLEEP_BAD = re.compile(
    r"\b(?:"
    r"(?:barely|hardly|not\s+really)\s+(?:slept|sleeping)"
    r"|(?:can'?t|cannot|couldn'?t)\s+sleep"
    r"|not\s+sleeping\s+(?:well|much|enough)"
    r"|sleeping\s+(?:badly|poorly|terribly|like\s+crap)"
    r"|no\s+sleep|losing\s+sleep|up\s+all\s+night|insomnia"
    r"|exhausted|wiped\s+out|running\s+on\s+(?:empty|fumes)"
    r")\b", re.I)

# A signal that sleep is FINE — the negative outcome that REFUTES a sleep_decline prediction.
_RE_SLEEP_GOOD = re.compile(
    r"\b(?:"
    r"sleeping\s+(?:well|great|fine|better|so\s+much\s+better|like\s+a\s+(?:baby|rock))"
    r"|(?:well|fully)\s+rested|got\s+(?:good|great|plenty\s+of)\s+sleep"
    r")\b", re.I)

# A signal of a stated GOAL / intention — the "goal_followthrough" evidence.
_RE_GOAL = re.compile(
    r"\b(?:"
    r"i(?:'?m| am)\s+(?:going\s+to|gonna|planning\s+to|trying\s+to)\s+(?:start|begin|get\s+back\s+to)"
    r"|i\s+(?:want|plan|intend|aim)\s+to\s+(?:start|begin)"
    r"|my\s+goal\s+is\s+to|i'?m\s+committing\s+to|i\s+signed\s+up\s+(?:for|to)"
    r")\b", re.I)

# The OUTCOME that confirms a goal was followed through.
_RE_GOAL_DONE = re.compile(
    r"\b(?:"
    r"i\s+(?:did\s+it|finished|completed|pulled\s+it\s+off|followed\s+through|stuck\s+with\s+it)"
    r"|i'?ve\s+been\s+(?:going|doing\s+it|keeping\s+it\s+up)|been\s+(?:going|sticking\s+with\s+it)"
    r"|i\s+started\s+(?:and\s+kept|going)"
    r")\b", re.I)

# The OUTCOME that refutes a goal (it lapsed).
_RE_GOAL_DROPPED = re.compile(
    r"\b(?:"
    r"i\s+(?:never\s+(?:started|did)|gave\s+up\s+on\s+it|fell\s+off|stopped|quit\s+it|flaked)"
    r"|didn'?t\s+(?:end\s+up|manage\s+to)|never\s+got\s+around\s+to|lost\s+(?:the\s+)?motivation"
    r")\b", re.I)

# A signal of an OVERLOAD the user stated (workload spiking) — the "load_risk" evidence.
_RE_OVERLOAD = re.compile(
    r"\b(?:"
    r"(?:slammed|swamped|underwater|drowning|buried)\s+(?:at|with|in)\s+work"
    r"|(?:so\s+much|too\s+much|a\s+ton\s+of)\s+(?:work|on\s+my\s+plate)"
    r"|(?:back-?to-?back|nonstop)\s+(?:meetings|deadlines)"
    r"|crunch\s+(?:time|mode)|deadline\s+(?:hell|crunch)"
    r")\b", re.I)

# The OUTCOME that confirms overload spilled into less downtime / recovery.
_RE_LESS_DOWNTIME = re.compile(
    r"\b(?:"
    r"no\s+(?:time|downtime|days?\s+off|breaks?)|haven'?t\s+(?:stopped|rested|had\s+a\s+break)"
    r"|working\s+(?:weekends|nights|late\s+every)|no\s+time\s+(?:for\s+myself|to\s+breathe)"
    r"|skipped\s+(?:the\s+gym|workouts|exercise)"
    r")\b", re.I)


# ===========================================================================
# THE COMPETING-HYPOTHESIS LIBRARY — the BIGGEST fix: reasoning, not fortune-telling.
#
# For a category (e.g. "stress_risk"), reality offers MANY candidate explanations, not one.
# Each candidate is (key, claim, prior). The priors are the PRIOR confidences before any outcome
# arrives; they sum to ~1 (they are normalised at competition time regardless). When an outcome
# adjudicates, the candidate whose ``supported_by`` matches the stated outcome is strengthened
# and the rest weakened (see ``adjudicate``). A genuinely single-candidate situation is allowed
# (a one-candidate competition is well-formed) — but competition is the DEFAULT shape.
#
# GRADUATION NOTE (deliberately NOT built): a hypothesis that wins its competition decisively
# AND whose prediction category is well-CALIBRATED could one day "graduate" to a BELIEF — a
# committed, conflict-resolved claim. That requires mature competition + calibration we do not
# yet have, so we form HYPOTHESES only. The attach point would be ``calibrate`` + a winner check.
#
# FUTURE ATTACH POINT (world-model): ``_candidates_for`` already merges in extra candidates
# SEEDED from the world graph (a stated recent-move edge, a stated family-visit edge), so a
# richer world-model that proposes new rival explanations slots in here without new files.
# ===========================================================================

class _Candidate:
    """One competing explanation: a stable key, a neutral claim, a prior confidence, and the
    OUTCOME signal that would SUPPORT it (reuse the inference library's confirm regexes so the
    competition is adjudicated by the SAME stated-signal definitions used elsewhere)."""
    __slots__ = ("key", "claim", "prior", "supported_by", "contradicted_by")

    def __init__(self, key, claim, prior, supported_by=None, contradicted_by=None):
        self.key = key
        self.claim = claim
        self.prior = float(prior)
        self.supported_by = supported_by
        self.contradicted_by = contradicted_by


# Per hypothesis-category, the competing candidate explanations. The canonical example: rising
# stress has MANY plausible drivers, weighted by prior. ``manager_change`` is supported when the
# downstream sleep_decline outcome lands (its predicted consequence happened); ``recent_move``
# / ``family_visit`` are supported only if THEIR stated signal appears; ``multiple`` is the
# small-prior "several at once" hypothesis. A real world-model would add/weight more.
_COMPETITION_LIBRARY = {
    "stress_risk": [
        _Candidate("manager_change",
                   "a recent change at work is the main new source of strain",
                   0.5, supported_by=_RE_SLEEP_BAD),
        _Candidate("recent_move",
                   "a recent move/relocation is the main new source of strain",
                   0.3, supported_by=re.compile(
                       r"\b(?:the\s+move|moving|relocat\w+|new\s+(?:place|apartment|house|city))"
                       r"\b[^.!?]*\b(?:still|getting\s+to\s+me|stressful|unsettl\w+|hard)\b", re.I)),
        _Candidate("family_visit",
                   "family/visitors at home are the main new source of strain",
                   0.2, supported_by=re.compile(
                       r"\b(?:family|my\s+(?:mom|dad|parents|in-?laws|sister|brother)|visitors?|"
                       r"house\s*guests?)\b[^.!?]*\b(?:visiting|in\s+town|staying|over|exhaust\w+|"
                       r"a\s+lot)\b", re.I)),
        _Candidate("multiple",
                   "several things at once are compounding the strain",
                   0.1, supported_by=re.compile(
                       r"\b(?:everything\s+at\s+once|so\s+many\s+things|all\s+of\s+it|"
                       r"a\s+lot\s+going\s+on|piling\s+up|one\s+thing\s+after\s+another)\b", re.I)),
    ],
    # load_risk competes too, though more thinly — the workload's source.
    "load_risk": [
        _Candidate("crunch", "a temporary crunch/deadline is driving the load", 0.6,
                   supported_by=_RE_LESS_DOWNTIME),
        _Candidate("understaffed", "an ongoing staffing/scope problem is driving the load", 0.4,
                   supported_by=re.compile(
                       r"\b(?:short-?staffed|understaffed|down\s+a\s+person|covering\s+for|"
                       r"too\s+few\s+(?:of\s+us|people)|no\s+one\s+to\s+help)\b", re.I)),
    ],
    # goal_followthrough is genuinely a SINGLE-candidate situation (will they / won't they) — the
    # engine SUPPORTS competition but does not FORCE it where reality offers one real candidate.
    "goal_followthrough": [
        _Candidate("intends_and_acts", "they mean to act on the stated intention and will", 0.5,
                   supported_by=_RE_GOAL_DONE, contradicted_by=_RE_GOAL_DROPPED),
    ],
}


# A pattern: (category, hypothesis_claim, prediction_or_None). A prediction is
# (pred_category, pred_claim, horizon_days, confirm_regex, refute_regex). When a source matches
# ``cue``, we form the hypothesis, its COMPETITION (the candidate set for the category), and
# (if a prediction is given) an OPEN prediction from the LEADING candidate.
class _Pattern:
    __slots__ = ("cue", "category", "hypothesis_claim", "hypothesis_conf",
                 "pred_category", "pred_claim", "horizon_days", "confidence",
                 "confirm", "refute")

    def __init__(self, cue, category, hypothesis_claim, hypothesis_conf,
                 pred_category=None, pred_claim=None, horizon_days=None, confidence=None,
                 confirm=None, refute=None):
        self.cue = cue
        self.category = category
        self.hypothesis_claim = hypothesis_claim
        self.hypothesis_conf = hypothesis_conf
        self.pred_category = pred_category
        self.pred_claim = pred_claim
        self.horizon_days = horizon_days
        self.confidence = confidence
        self.confirm = confirm
        self.refute = refute


# The conservative inference library. Each entry rests on a STATED event and forms a hypothesis
# about the USER's world; most imply a near-future outcome we can later check. Confidences are
# deliberately moderate (we describe a tendency, we never certify a person's future). Horizons
# are honest calendar windows. NOTHING here is a diagnosis; every claim is a neutral inference.
_PATTERNS = (
    # a destabilising change -> stress is likely rising, and sleep MAY decline within ~2 weeks.
    _Pattern(
        cue=_RE_CHANGE, category="stress_risk",
        hypothesis_claim="a recent change in their situation is a plausible new source of strain",
        hypothesis_conf=0.62,
        pred_category="sleep_decline",
        pred_claim="rest may be affected within the next couple of weeks",
        horizon_days=14, confidence=0.67,
        confirm=_RE_SLEEP_BAD, refute=_RE_SLEEP_GOOD,
    ),
    # a stated goal -> they MAY follow through within ~3 weeks (a check on intention vs action).
    _Pattern(
        cue=_RE_GOAL, category="goal_followthrough",
        hypothesis_claim="they have stated an intention they mean to act on",
        hypothesis_conf=0.6,
        pred_category="goal_followthrough",
        pred_claim="the stated intention may be acted on within a few weeks",
        horizon_days=21, confidence=0.55,
        confirm=_RE_GOAL_DONE, refute=_RE_GOAL_DROPPED,
    ),
    # an overload -> recovery/downtime MAY shrink within ~10 days.
    _Pattern(
        cue=_RE_OVERLOAD, category="load_risk",
        hypothesis_claim="their workload is heavier than usual right now",
        hypothesis_conf=0.6,
        pred_category="downtime_decline",
        pred_claim="time for rest/recovery may shrink in the coming days",
        horizon_days=10, confidence=0.6,
        confirm=_RE_LESS_DOWNTIME, refute=None,
    ),
)


# ===========================================================================
# COMPETITION MECHANICS — build a competing-hypothesis set, normalise it, and ADJUDICATE it
# against a stated outcome with a principled, documented reweighting.
# ===========================================================================

# How much an outcome moves the competition. A documented multiplicative update (NOT full Bayes,
# but evidence-driven + normalised): the SUPPORTED candidate's weight is multiplied UP, each
# CONTRADICTED candidate's weight multiplied DOWN, then the whole set is re-normalised to sum 1.
# Tunable, fixed, reproducible.
_SUPPORT_GAIN = 2.5       # the supported hypothesis' weight is scaled by this before renorm
_CONTRADICT_DECAY = 0.4   # a contradicted hypothesis' weight is scaled by this before renorm
_WEIGHT_FLOOR = 1e-4      # no hypothesis is ever driven to exactly zero (Unknown > Lost)


def _normalise_weights(weights: dict) -> dict:
    """Return ``weights`` rescaled to sum to 1.0 (a proper distribution over the competing
    hypotheses), with a tiny floor so no candidate is annihilated (a refuted hypothesis is kept
    revivable — Unknown > Lost). Pure; never raises. An all-zero/empty input -> a uniform split."""
    if not weights:
        return {}
    vals = {k: max(_WEIGHT_FLOOR, float(v)) for k, v in weights.items()}
    total = sum(vals.values())
    if total <= 0.0:
        n = len(vals)
        return {k: round(1.0 / n, 6) for k in vals}
    return {k: round(v / total, 6) for k, v in vals.items()}


def _candidates_for(category: str, text: str, world_cite: Optional[str]) -> list:
    """The competing candidate explanations for ``category`` — the library set, OPTIONALLY
    augmented with candidates SEEDED from the world graph (the FUTURE-attach hook for a richer
    world-model). Returns a list of _Candidate. Empty when the category has no competition
    defined (then ``form`` records a single un-competed hypothesis — allowed when there is
    genuinely one candidate). Pure-ish (only reads); never raises."""
    base = list(_COMPETITION_LIBRARY.get(category, ()))
    # FUTURE ATTACH POINT: a world-model could here PROPOSE extra rival candidates from stated
    # edges (e.g. world_cite mentions a 'recent' move -> lift recent_move's prior). For now we
    # only nudge a present candidate's prior when the world already corroborates it — never
    # fabricate a new candidate the evidence didn't state (Observed > Assumed).
    if world_cite and base:
        low = str(world_cite).lower()
        for c in base:
            if c.key == "recent_move" and ("move" in low or "relocat" in low):
                c.prior = max(c.prior, 0.4)
            if c.key == "manager_change" and ("manager" in low or "boss" in low):
                c.prior = max(c.prior, 0.55)
    return base


def _build_competition(name: str, category: str, hypotheses_by_key: dict, text: str,
                       world_cite: Optional[str], when: str) -> Optional[dict]:
    """Build ONE competition record for ``category``: the SET of competing hypotheses, each with
    a normalised PRIOR weight, plus which one leads. ``hypotheses_by_key`` maps a candidate key
    to the already-formed hypothesis record's id (so the competition references real, grounded
    hypotheses — the competition is over EVIDENCE, never abstract). Returns the record (not yet
    appended) or None when there are no candidates. Pure-ish; never raises."""
    cands = _candidates_for(category, text, world_cite)
    if not cands:
        return None
    priors = _normalise_weights({c.key: c.prior for c in cands})
    leader = max(priors, key=lambda k: priors[k]) if priors else None
    return {
        "kind": COMPETITION,
        "id": _new_id("c"),
        "version": VERSION,
        "category": category,
        # the competing hypotheses: key -> {claim, hypothesis_id, weight (evolving)}.
        "candidates": {
            c.key: {
                "claim": c.claim,
                "weight": priors.get(c.key, 0.0),
                "prior": priors.get(c.key, 0.0),
                "hypothesis_id": hypotheses_by_key.get(c.key),
            }
            for c in cands
        },
        "leader": leader,
        "single_candidate": len(cands) == 1,   # honest: a genuine one-candidate situation
        "formed_at": when,
        # a compact append-only audit of how the weights have evolved (priors are revision 0).
        "weight_history": [{"at": when, "weights": dict(priors), "reason": "priors"}],
        "internal_only": True,
    }


def _adjudicate_weights(candidates: dict, supported_key: Optional[str],
                        contradicted_keys: list) -> dict:
    """The PRINCIPLED REWEIGHTING: given the current candidate weights, STRENGTHEN the supported
    hypothesis and WEAKEN the contradicted ones, then RE-NORMALISE to a proper distribution.

    A documented, deterministic, evidence-driven update (need not be full Bayes): multiply the
    supported candidate's weight by ``_SUPPORT_GAIN``, each contradicted candidate's by
    ``_CONTRADICT_DECAY``, floor + renormalise. Reality REWEIGHTS the competition; it never
    deletes a candidate (a weakened hypothesis stays revivable — Unknown > Lost). Pure."""
    raw = {k: max(_WEIGHT_FLOOR, float(v.get("weight", 0.0))) for k, v in candidates.items()}
    if supported_key and supported_key in raw:
        raw[supported_key] *= _SUPPORT_GAIN
    for k in contradicted_keys:
        if k in raw:
            raw[k] *= _CONTRADICT_DECAY
    return _normalise_weights(raw)


# ===========================================================================
# TIME — honest calendar handling. ``form`` stamps records with a wall-clock time (or a
# caller-supplied ``at`` for the synthetic time-series). A prediction's deadline is
# formed_at + horizon_days. ``resolve`` is time-aware but TOLERANT: an outcome that arrives is
# matched whether or not the deadline has strictly passed (real life rarely lands on the day) —
# what matters is the OUTCOME ARRIVED, which is the honest signal of being right or wrong.
# ===========================================================================

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_ts(ts: Any) -> Optional[datetime]:
    """Best-effort ISO-8601 -> aware datetime; None on anything unparseable (Observed > Assumed).
    Pure; never raises."""
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _add_days(at: str, days: int) -> str:
    """``at`` plus ``days`` as an ISO-Z string. Falls back to ``at`` if unparseable."""
    dt = _parse_ts(at)
    if dt is None:
        return at
    return (dt + timedelta(days=int(days))).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_" + secrets.token_hex(6)


# ===========================================================================
# SURPRISE — the learning gradient. The single number that turns SCOREKEEPING into LEARNING.
# ===========================================================================

def surprise(predicted_confidence: float, outcome_true: bool) -> float:
    """The SURPRISE of a resolved prediction in [0, 1], from (predicted confidence, actual
    outcome). It is HIGH when the model was confident and WRONG, OR doubtful and RIGHT; LOW when
    the stated confidence matched what reality did.

        surprise = | actual - predicted_confidence |   where actual = 1.0 if true else 0.0

    Worked: pred 0.82, outcome FALSE -> |0 - 0.82| = 0.82 (confident-and-wrong: very surprising).
            pred 0.11, outcome TRUE  -> |1 - 0.11| = 0.89 (doubtful-and-right: very surprising).
            pred 0.90, outcome TRUE  -> |1 - 0.90| = 0.10 (confidence matched reality: low).

    This IS the gradient learning rides on: a high-surprise outcome should MOVE the model
    (trigger a revision); a low-surprise one merely confirms it. Pure; clamped; never raises."""
    try:
        p = float(predicted_confidence)
    except (TypeError, ValueError):
        p = 0.5
    p = 0.0 if p < 0.0 else (1.0 if p > 1.0 else p)
    actual = 1.0 if outcome_true else 0.0
    return round(abs(actual - p), 4)


# A resolved prediction whose surprise is at/above this triggers a MODEL REVISION of the
# competition weights; below it, the outcome CONFIRMS without a major revision. Fixed + tunable.
_SURPRISE_REVISION_AT = 0.5


# ===========================================================================
# THE LEDGER — append-only, per-creature, its OWN UNIFIED file. NEVER truncated/overwritten
# (Law 001), exactly like the meaning / continuity / trajectory ledgers. The WHOLE loop —
# hypotheses, competitions, predictions, outcomes, learnings, revisions — is ONE stream
# (anti-bureaucracy). An adjudication / revision APPENDS records that refer to prior ids; it
# never rewrites the prior lines.
# ===========================================================================

def ledger_path(name: str) -> Path:
    """The append-only reality ledger for ``name`` — one JSON record per line, never rewritten
    (Law 001). A SEPARATE file from LIRF / world / meaning; this module's only persisted state.
    Holds the ENTIRE epistemic loop in ONE unified stream (never fragmented across files)."""
    return STORE / f"{name}.reality.jsonl"


def _append(name: str, record: dict) -> Optional[dict]:
    """Append one record to the ledger and return it. APPEND-ONLY: O_APPEND, never truncates an
    existing ledger (Law 001). Best-effort: a write failure returns None rather than raising."""
    try:
        path = ledger_path(name)
        secure_store.append_jsonl(path, record)
    except Exception:
        return None
    return record


def records(name: str) -> list:
    """Read back the whole ledger (oldest -> newest). [] if nothing recorded. A corrupt line is
    kept visible (Unknown > Lost), never silently dropped. Read-only; never raises."""
    path = ledger_path(name)
    if not path.exists():
        return []
    out: list = []
    try:
        for line in secure_store.read_jsonl_lines(path):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"_unparsed": line})
    except Exception:
        return out
    return out


def _records_of(name: str, kind: str) -> list:
    """All well-formed records of one kind, oldest -> newest."""
    return [r for r in records(name) if isinstance(r, dict) and r.get("kind") == kind]


def open_predictions(name: str) -> list:
    """The predictions still OPEN — formed but not yet resolved by a later outcome. A prediction
    is OPEN iff no LEARNING record refers to its id. Read-only; never raises.

    These are the standing 'bets' the mind has made about the user's world, waiting on real
    calendar time to deliver an outcome. They are the queue ``resolve`` matches against."""
    resolved_ids = {
        r.get("prediction_id")
        for r in _records_of(name, LEARNING)
        if r.get("prediction_id")
    }
    out = []
    for p in _records_of(name, PREDICTION):
        pid = p.get("id")
        if pid and pid not in resolved_ids:
            out.append(p)
    return out


def competition_for(name: str, competition_id: str) -> Optional[dict]:
    """The CURRENT state of a competition: its original record with weights ROLLED FORWARD
    through every REVISION that has been appended against it (the ledger stays append-only — we
    fold the revisions at READ time, never rewrite the original line). Returns None if unknown.
    Read-only; never raises. This is how a caller sees 'which hypothesis is reality favoring now'."""
    base = None
    for c in _records_of(name, COMPETITION):
        if c.get("id") == competition_id:
            base = c
            break
    if base is None:
        return None
    cur = {**base, "candidates": {k: dict(v) for k, v in (base.get("candidates") or {}).items()}}
    history = list(cur.get("weight_history") or [])
    # apply revisions in time order (they are append-only; the latest wins per key).
    revs = sorted((r for r in _records_of(name, REVISION)
                   if r.get("competition_id") == competition_id),
                  key=lambda r: r.get("at", ""))
    for r in revs:
        after = r.get("after_weights") or {}
        for k, w in after.items():
            if k in cur["candidates"]:
                cur["candidates"][k]["weight"] = w
        kind_word = "MODEL REVISION" if r.get("major") else "minor reweight"
        history.append({"at": r.get("at"), "weights": dict(after),
                         "reason": f"{kind_word} (surprise {r.get('surprise')})"})
    cur["weight_history"] = history
    if cur["candidates"]:
        cur["leader"] = max(cur["candidates"], key=lambda k: cur["candidates"][k].get("weight", 0.0))
    return cur


# ===========================================================================
# GROUNDING — extract the REAL evidence a source carries. A source may be (a) a raw recorded
# turn string, or (b) a structured situation/world-edge dict. We never form a hypothesis without
# a concrete evidence string pinned to it. Mirrors world_state.capture's never-infer anchoring.
# ===========================================================================

def _source_text(source: Any) -> str:
    """The text to scan for evidence. A string source IS the text; a dict source may carry a
    ``text`` / ``utterance`` / ``query`` field (a recorded turn) — we read that, never invent
    one. Anything else yields "" (-> no hypothesis). Pure."""
    if isinstance(source, str):
        return source
    if isinstance(source, dict):
        for k in ("text", "utterance", "query", "said"):
            v = source.get(k)
            if isinstance(v, str) and v.strip():
                return v
    return ""


def _world_evidence(name: str, text: str) -> Optional[str]:
    """If the world-model already holds a STATED edge that corroborates this source (e.g. a
    'you stressed_by work' relation, or a 'manager is recent' observation), return a short
    citation of that edge — so a formed hypothesis rests on the world-state too, not only the raw
    turn. Read-only on the world store; None when nothing corroborates or world_state is absent.

    This is the EXTENDS-not-replaces link to world_state: reality builds hypotheses ON its edges,
    and ``_candidates_for`` can lift a candidate's prior when the world corroborates it.
    Best-effort; never raises."""
    if not (_HAVE_WORLD and _world is not None) or not text:
        return None
    try:
        cluster = _world.situation(name, text, hops=2)
    except Exception:
        return None
    edges = (cluster or {}).get("edges") or []
    if not edges:
        return None
    # cite the first stressor/problem/relationship edge — the kind that grounds a strain hypothesis.
    for e in edges:
        if not isinstance(e, dict):
            continue
        pred = str(e.get("predicate", ""))
        if pred in ("stressed_by", "worried_about", "because", "is", "has"):
            return (f"world-edge: {e.get('subject')} --{pred}--> {e.get('object')}")
    return None


# ===========================================================================
# 1) form(source) — derive grounded HYPOTHESES (a COMPETING set when reality offers rivals) and
# (if a hypothesis implies a future) a PREDICTION, from a turn / situation / world-edge with
# CLEAR evidence. CONSERVATIVE: only when evidence is real; each carries its evidence; thin
# evidence -> NOTHING (returns []). Appends to the unified ledger.
# ===========================================================================

def form(name: str, source: Any, *, at: Optional[str] = None, persist: bool = True) -> list:
    """Form grounded HYPOTHESIS records, their COMPETITION, and (optionally) a PREDICTION from
    one recorded ``source``.

    ``source`` is a recorded turn (string) or a situation/world-edge dict carrying a turn — the
    ALREADY-RECORDED conversation/state, NOT a live reply. For each inference PATTERN whose cue
    fires on REAL evidence in the source, we form, in order:
      * the COMPETING HYPOTHESES — for the pattern's category, the SET of candidate explanations
        (e.g. for rising stress: manager_change / recent_move / family_visit / multiple), each a
        grounded HYPOTHESIS record carrying {category, candidate_key, claim, confidence (its
        normalised prior weight), evidence (the exact text + any corroborating world-edge),
        formed_at}. A genuinely single-candidate category yields one hypothesis (allowed).
      * a COMPETITION record — the candidate set + their normalised PRIOR weights + which leads
        (so 'which explanation reality is favoring' is auditable and revisable over time).
      * (when the pattern implies a future) a PREDICTION — formed from the LEADING hypothesis —
        {category, claim, confidence, horizon_days, deadline, formed_at, status: OPEN,
        hypothesis_id (the leader), competition_id}.

    CONSERVATIVE BY CONSTRUCTION: a source with no clear evidence matches no pattern and yields
    [] — we never fabricate a hypothesis or an inner life (#1 rule). Every record cites its
    evidence; each competing candidate is grounded in the SAME real evidence.

    ``at`` (ISO-Z) overrides the wall clock — used by the synthetic time-series to place a Day-1
    record in calendar time; live callers omit it. ``persist`` appends to the ledger (default);
    set False to derive without writing (a dry read). Returns the records formed (the hypotheses,
    then the competition, then the prediction). Never raises.

    LIVE-HOOK (DELIBERATELY NOT WIRED): a future offline/shadow pass would call ``form(name,
    recorded_turn)`` for each turn in ``.anima/{name}.chat.jsonl`` AFTER the turn is recorded —
    never inside ``mouth.respond`` / ``server._turn``, and its output NEVER re-enters the reply.
    Wiring it changes zero live-path behaviour; it only accrues this internal ledger.
    """
    text = _source_text(source)
    if not text or not text.strip():
        return []
    when = at or _now()
    world_cite = _world_evidence(name, text)
    formed: list = []
    seen_categories = set()
    for pat in _PATTERNS:
        if pat.category in seen_categories:
            continue
        m = pat.cue.search(text)
        if not m:
            continue
        seen_categories.add(pat.category)
        evidence = {
            "turn": text.strip()[:240],          # the exact recorded turn the hypothesis rests on
            "matched": m.group(0).strip()[:80],   # the concrete cue that fired (no inference)
        }
        if world_cite:
            evidence["world"] = world_cite

        # --- the COMPETING HYPOTHESES: one grounded HYPOTHESIS record per candidate -----------
        cands = _candidates_for(pat.category, text, world_cite)
        priors = _normalise_weights({c.key: c.prior for c in cands}) if cands else {}
        hypotheses_by_key: dict = {}
        leader_hyp = None
        if cands:
            for c in cands:
                hyp = {
                    "kind": HYPOTHESIS,
                    "id": _new_id("h"),
                    "version": VERSION,
                    "category": pat.category,
                    "candidate_key": c.key,
                    "claim": c.claim,
                    # the hypothesis' confidence IS its normalised prior weight in the competition.
                    "confidence": float(priors.get(c.key, pat.hypothesis_conf)),
                    "evidence": dict(evidence),
                    "formed_at": when,
                    # the internal-only marker: this is model-state, never a user-facing assertion.
                    "internal_only": True,
                }
                hypotheses_by_key[c.key] = hyp["id"]
                formed.append(hyp)
                if persist:
                    _append(name, hyp)
            leader_key = max(priors, key=lambda k: priors[k]) if priors else None
            leader_hyp = next((h for h in formed
                               if h["kind"] == HYPOTHESIS and h.get("candidate_key") == leader_key),
                              None)
        else:
            # genuinely ONE candidate (no competition defined) — a single un-competed hypothesis.
            hyp = {
                "kind": HYPOTHESIS,
                "id": _new_id("h"),
                "version": VERSION,
                "category": pat.category,
                "candidate_key": None,
                "claim": pat.hypothesis_claim,
                "confidence": float(pat.hypothesis_conf),
                "evidence": dict(evidence),
                "formed_at": when,
                "internal_only": True,
            }
            hypotheses_by_key[None] = hyp["id"]
            formed.append(hyp)
            leader_hyp = hyp
            if persist:
                _append(name, hyp)

        # --- the COMPETITION record (the candidate set + evolving weights) --------------------
        competition = None
        if cands:
            competition = _build_competition(name, pat.category, hypotheses_by_key,
                                             text, world_cite, when)
            if competition is not None:
                formed.append(competition)
                if persist:
                    _append(name, competition)

        # --- a PREDICTION from the LEADING hypothesis, when the pattern implies a future ------
        if pat.pred_category and pat.pred_claim and pat.horizon_days and leader_hyp is not None:
            prediction = {
                "kind": PREDICTION,
                "id": _new_id("p"),
                "version": VERSION,
                "category": pat.pred_category,
                "claim": pat.pred_claim,
                "confidence": float(pat.confidence if pat.confidence is not None else 0.5),
                "horizon_days": int(pat.horizon_days),
                "formed_at": when,
                "deadline": _add_days(when, pat.horizon_days),
                "status": OPEN,
                "hypothesis_id": leader_hyp["id"],   # the LEADING competing hypothesis
                "competition_id": competition["id"] if competition is not None else None,
                "evidence": dict(evidence),
                "internal_only": True,
            }
            formed.append(prediction)
            if persist:
                _append(name, prediction)
    return formed


def _confirm_refute_for(category: str):
    """The (confirm_regex, refute_regex) a prediction CATEGORY resolves against — looked up from
    the inference library so resolution uses the SAME stated-signal definitions as formation.
    Returns (None, None) for an unknown category (-> never auto-resolves; honest)."""
    for pat in _PATTERNS:
        if pat.pred_category == category:
            return pat.confirm, pat.refute
    return None, None


# ===========================================================================
# 2) resolve(later_source) — match a LATER recorded outcome to an OPEN prediction; mark it
# confirmed/refuted; compute SURPRISE; ADJUDICATE the competing hypotheses; and append the
# OUTCOME + LEARNING (+ a surprise-driven REVISION) records. The bridge to LEARNING.
# ===========================================================================

def resolve(name: str, later_source: Any, *, at: Optional[str] = None,
            persist: bool = True) -> list:
    """Resolve OPEN predictions against a LATER recorded outcome — the full epistemic step.

    ``later_source`` is a recorded turn / situation arriving after the prediction was formed
    (e.g. Day-14 "I've barely slept"). For each OPEN prediction whose CATEGORY has a stated
    confirm/refute signal present in this source, we:
      * append an OUTCOME record — {observed (the stated fact), observed_at, prediction_id};
      * compute SURPRISE from (the prediction's confidence, the actual outcome) — HIGH when
        confident-and-wrong or doubtful-and-right, LOW when confidence matched reality;
      * ADJUDICATE the prediction's COMPETITION (if any): the candidate whose ``supported_by``
        signal appears in this outcome is STRENGTHENED, contradicted candidates WEAKENED, weights
        RE-NORMALISED — a principled, documented, evidence-driven reweighting;
      * append a LEARNING record — {prediction_id, category, predicted_confidence,
        actual_outcome (1.0/0.0), prediction_correct: bool, surprise, resolved_at};
      * if surprise is high (>= ``_SURPRISE_REVISION_AT``), append a MODEL REVISION record —
        {competition_id, before_weights -> after_weights, surprise, triggered_by (the learning),
        at}. A LOW-surprise outcome CONFIRMS the model without a major revision (no revision row).

    A prediction with no matching outcome signal stays OPEN (honest: real learning waits on a
    real outcome over real calendar time). Returns the LEARNING records produced. Never raises.

    Matching is by CATEGORY + a stated confirm/refute cue — we never INVENT that an outcome
    happened; the later turn must actually state it. Oldest open prediction of a category
    resolves first (FIFO), so a long-standing bet is settled before a fresh one.
    """
    text = _source_text(later_source)
    if not text or not text.strip():
        return []
    when = at or _now()
    learnings: list = []
    # resolve oldest-first within each category.
    pending = sorted(open_predictions(name), key=lambda p: p.get("formed_at", ""))
    for pred in pending:
        category = pred.get("category", "")
        confirm, refute = _confirm_refute_for(category)
        verdict = None
        observed_phrase = ""
        if confirm is not None:
            m = confirm.search(text)
            if m:
                verdict = True
                observed_phrase = m.group(0).strip()[:80]
        if verdict is None and refute is not None:
            m = refute.search(text)
            if m:
                verdict = False
                observed_phrase = m.group(0).strip()[:80]
        if verdict is None:
            continue  # no stated outcome for this category in this source -> stays OPEN
        pid = pred.get("id")
        outcome = {
            "kind": OUTCOME,
            "id": _new_id("o"),
            "version": VERSION,
            "prediction_id": pid,
            "category": category,
            "observed": text.strip()[:240],
            "observed_signal": observed_phrase,
            "observed_at": when,
            "internal_only": True,
        }
        if persist:
            _append(name, outcome)

        predicted_confidence = float(pred.get("confidence", 0.5))
        actual_outcome = 1.0 if verdict else 0.0
        surp = surprise(predicted_confidence, bool(verdict))
        learning = {
            "kind": LEARNING,
            "id": _new_id("l"),
            "version": VERSION,
            "prediction_id": pid,
            "outcome_id": outcome["id"],
            "category": category,
            "prediction_correct": bool(verdict),
            "predicted_confidence": round(predicted_confidence, 4),
            "actual_outcome": actual_outcome,
            # SURPRISE — the learning gradient: confident-and-wrong / doubtful-and-right -> high.
            "surprise": surp,
            # signed gap kept too (reality - predicted): direction of the miss for the dashboard.
            "delta": round(actual_outcome - predicted_confidence, 4),
            "resolved_at": when,
            "internal_only": True,
        }
        learnings.append(learning)
        if persist:
            _append(name, learning)

        # --- ADJUDICATE the competition (always reweight) + flag a MODEL REVISION on high surprise
        _adjudicate(name, pred, text, learning, surp, when, persist)
    return learnings


def _adjudicate(name: str, pred: dict, outcome_text: str, learning: dict,
                surp: float, when: str, persist: bool) -> Optional[dict]:
    """ADJUDICATE the prediction's competing hypotheses against the stated outcome — the
    reality-reweighting at the heart of the competition. ALWAYS reweights when there is a
    competition (the supported hypothesis strengthened, the contradicted ones weakened,
    re-normalised), and APPENDS the result as an append-only adjudication record carrying
    before_weights -> after_weights, the surprise, and the triggering learning.

    The ``major`` flag splits the two regimes the spec names:
      * HIGH surprise (>= ``_SURPRISE_REVISION_AT``) -> ``major=True``: a MODEL REVISION — reality
        blindsided the model, so the reweight is a real revision of what it believes is going on.
      * LOW surprise -> ``major=False``: the outcome CONFIRMS the model; the reweight is a minor
        consolidation (the leader edges up), not a revision of the explanation.

    Either way the competition's weights move (so 'which hypothesis reality favors' tracks every
    outcome) and the ledger stays APPEND-ONLY: we append a new record that ``competition_for``
    rolls forward, never rewriting the original competition line. ``calibrate`` counts only the
    ``major`` ones as model revisions. Returns the record, or None when there is no competition.
    Best-effort; never raises."""
    cid = pred.get("competition_id")
    if not cid:
        return None
    comp = competition_for(name, cid)   # current (revision-rolled) state — append-only safe
    if not comp:
        return None
    candidates = comp.get("candidates") or {}
    if not candidates:
        return None
    before = {k: float(v.get("weight", 0.0)) for k, v in candidates.items()}

    # which candidate does THIS outcome support / contradict? (reuse the library's signals.)
    cat = comp.get("category", "")
    lib = _COMPETITION_LIBRARY.get(cat, ())
    supported_key = None
    contradicted_keys = []
    for c in lib:
        if c.key not in candidates:
            continue
        if c.supported_by is not None and c.supported_by.search(outcome_text):
            supported_key = supported_key or c.key
        if c.contradicted_by is not None and c.contradicted_by.search(outcome_text):
            contradicted_keys.append(c.key)
    # if the prediction was CORRECT, the leader (whose predicted consequence happened) is the
    # supported hypothesis when no other candidate's own signal fired; if WRONG, the leader is
    # contradicted. Reality drives the reweight either way (Observed > Assumed).
    leader = comp.get("leader")
    if learning.get("prediction_correct") and supported_key is None and leader in candidates:
        supported_key = leader
    if not learning.get("prediction_correct") and leader in candidates and leader not in contradicted_keys:
        contradicted_keys.append(leader)

    after = _adjudicate_weights(candidates, supported_key, contradicted_keys)
    major = surp >= _SURPRISE_REVISION_AT   # HIGH surprise -> a MODEL REVISION; else confirmation

    revision = {
        "kind": REVISION,
        "id": _new_id("r"),
        "version": VERSION,
        "competition_id": cid,
        "category": cat,
        "major": bool(major),                    # True == a MODEL REVISION (high surprise)
        "triggered_by": learning.get("id"),      # the learning whose surprise drove this
        "surprise": surp,
        "supported": supported_key,
        "contradicted": sorted(contradicted_keys),
        "before_weights": {k: round(v, 6) for k, v in before.items()},
        "after_weights": after,
        "at": when,
        "internal_only": True,
    }
    if persist:
        _append(name, revision)
    return revision


# ===========================================================================
# 3) calibrate() — running accuracy over RESOLVED records, per category. "Was the mind right?"
# over time: which prediction kinds Vera gets right, which she gets wrong, her Brier-style
# calibration (how well stated confidence matched reality), AND her mean SURPRISE (how often
# reality blindsided the model — the learning pressure).
#
# GRADUATION ATTACH POINT (not built): a category that is both RELIABLE and well-calibrated here
# is where a winning hypothesis could one day GRADUATE to a belief. Deliberately not wired.
# ===========================================================================

def calibrate(name: str) -> dict:
    """Running accuracy over all RESOLVED predictions, overall and PER CATEGORY.

    Returns a dict:
        {
          "resolved":   total resolved predictions,
          "correct":    how many were right,
          "accuracy":   correct / resolved (None if nothing resolved yet),
          "brier":      mean (reality - confidence)^2 over resolved — calibration quality,
                        LOWER is better (0 = perfectly calibrated); None if none resolved,
          "mean_surprise": mean SURPRISE over resolved — how often reality blindsided the model
                        (the learning pressure); None if none resolved,
          "revisions":  how many MODEL REVISIONS the surprises have triggered so far,
          "by_category": { category -> {resolved, correct, accuracy, brier, mean_surprise,
                                        reliable: bool|None} },
          "reliable_kinds":   categories with accuracy >= _RELIABLE_AT (>= _MIN_FOR_VERDICT n),
          "unreliable_kinds": categories with accuracy <= _UNRELIABLE_AT (>= _MIN_FOR_VERDICT n),
          "open":       predictions still waiting on a real outcome (time-gated),
        }

    HONEST TIME-GATING: with few or no resolved predictions, accuracy is None / thin — real
    calibration accrues only as real outcomes arrive over real calendar time. A category is
    only called reliable/unreliable once it has at least ``_MIN_FOR_VERDICT`` resolved records
    (Observed > Assumed; we never certify a kind off one data point). Read-only; never raises.
    """
    learnings = _records_of(name, LEARNING)
    by_cat: dict = {}
    total = 0
    correct = 0
    brier_sum = 0.0
    surprise_sum = 0.0
    for l in learnings:
        cat = str(l.get("category", "")) or "uncategorised"
        ok = bool(l.get("prediction_correct"))
        # v2 field is predicted_confidence; tolerate a v1 belief_before line if one is ever read.
        conf = float(l.get("predicted_confidence", l.get("belief_before", 0.5)) or 0.5)
        reality = float(l.get("actual_outcome", l.get("reality_after", 1.0 if ok else 0.0)))
        surp = float(l.get("surprise", abs(reality - conf)))
        total += 1
        correct += 1 if ok else 0
        brier_sum += (reality - conf) ** 2
        surprise_sum += surp
        c = by_cat.setdefault(cat, {"resolved": 0, "correct": 0, "_brier": 0.0, "_surprise": 0.0})
        c["resolved"] += 1
        c["correct"] += 1 if ok else 0
        c["_brier"] += (reality - conf) ** 2
        c["_surprise"] += surp

    reliable, unreliable = [], []
    for cat, c in by_cat.items():
        n = c["resolved"]
        c["accuracy"] = round(c["correct"] / n, 4) if n else None
        c["brier"] = round(c["_brier"] / n, 4) if n else None
        c["mean_surprise"] = round(c["_surprise"] / n, 4) if n else None
        del c["_brier"]
        del c["_surprise"]
        if n >= _MIN_FOR_VERDICT and c["accuracy"] is not None:
            if c["accuracy"] >= _RELIABLE_AT:
                c["reliable"] = True
                reliable.append(cat)
            elif c["accuracy"] <= _UNRELIABLE_AT:
                c["reliable"] = False
                unreliable.append(cat)
            else:
                c["reliable"] = None
        else:
            c["reliable"] = None

    return {
        "resolved": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else None,
        "brier": round(brier_sum / total, 4) if total else None,
        "mean_surprise": round(surprise_sum / total, 4) if total else None,
        # only the MAJOR (high-surprise) adjudications count as MODEL REVISIONS; the minor
        # low-surprise reweights are confirmations, not revisions of the explanation.
        "revisions": sum(1 for r in _records_of(name, REVISION) if r.get("major")),
        "by_category": by_cat,
        "reliable_kinds": sorted(reliable),
        "unreliable_kinds": sorted(unreliable),
        "open": len(open_predictions(name)),
    }


# How a category earns a reliability verdict: at least this many resolved records (never call a
# kind reliable off one point — Observed > Assumed), and an accuracy at/above (reliable) or
# at/below (unreliable) these bars.
_MIN_FOR_VERDICT = 3
_RELIABLE_AT = 0.7
_UNRELIABLE_AT = 0.4


# ===========================================================================
# THE LOOP READ — assemble the full observation->hypothesis(es)->prediction->outcome->surprise->
# learning->revision chain per creature, joined by id, for the observatory to render. Read-only.
# ===========================================================================

def loop(name: str) -> dict:
    """The whole epistemic loop for ``name``, assembled from the unified ledger and joined by id:

        {
          "hypotheses":   [...],         # grounded inferences (each a competing candidate), newest last
          "competitions": [...],         # competing-hypothesis sets, weights ROLLED FORWARD thru revisions
          "predictions":  [...],         # each tagged status OPEN/CONFIRMED/REFUTED (derived)
          "resolved":     [ {prediction, outcome, learning, revision|None, competition|None}, ... ],
          "open":         [...],         # predictions still waiting on a real outcome
          "revisions":    [...],         # the surprise-driven model revisions, append-only
          "calibration":  calibrate(name),
        }

    This is the audit view of observation -> hypothesis(es, competing) -> predicted -> happened
    -> SURPRISE -> learned -> MODEL REVISION. Read-only; never raises."""
    hypotheses = _records_of(name, HYPOTHESIS)
    predictions = _records_of(name, PREDICTION)
    outcomes = {o.get("prediction_id"): o for o in _records_of(name, OUTCOME)
                if o.get("prediction_id")}
    learnings = {l.get("prediction_id"): l for l in _records_of(name, LEARNING)
                 if l.get("prediction_id")}
    # all adjudications (major + minor); the resolved view links only the MAJOR ones as the
    # MODEL REVISION a resolved loop is shown to have triggered (a minor reweight is a
    # confirmation, not a revision of the explanation).
    revisions = [r for r in _records_of(name, REVISION) if r.get("major")]
    rev_by_learning = {r.get("triggered_by"): r for r in _records_of(name, REVISION)
                       if r.get("triggered_by") and r.get("major")}

    # competitions with weights rolled forward through their revisions (append-only safe read).
    competitions = []
    for c in _records_of(name, COMPETITION):
        cur = competition_for(name, c.get("id")) or c
        competitions.append(cur)

    resolved = []
    open_list = []
    enriched_preds = []
    for p in predictions:
        pid = p.get("id")
        learning = learnings.get(pid)
        if learning is not None:
            status = CONFIRMED if learning.get("prediction_correct") else REFUTED
            p = {**p, "status": status}
            cid = p.get("competition_id")
            resolved.append({
                "prediction": p,
                "outcome": outcomes.get(pid),
                "learning": learning,
                "revision": rev_by_learning.get(learning.get("id")),
                "competition": (competition_for(name, cid) if cid else None),
            })
        else:
            p = {**p, "status": OPEN}
            open_list.append(p)
        enriched_preds.append(p)

    return {
        "hypotheses": hypotheses,
        "competitions": competitions,
        "predictions": enriched_preds,
        "resolved": resolved,
        "open": open_list,
        "revisions": revisions,
        "calibration": calibrate(name),
    }


# ===========================================================================
# AUDIT SURFACE — human-readable 'the epistemic loop', the keystone counterpart to
# meaning.render / trajectory.render. Read-only; never the live reply. Every emitted line
# passes the clean-gate (no diagnosis / no forecast voice), defence in depth.
# ===========================================================================

def _fmt_competition(comp: dict) -> list:
    """Render ONE competition as candidate explanations + which one reality is favoring + the
    weight each carries. Clean-gated by the caller. Returns a list of lines."""
    lines = []
    cands = comp.get("candidates") or {}
    leader = comp.get("leader")
    cat = comp.get("category", "?")
    n = len(cands)
    shape = "single candidate" if comp.get("single_candidate") or n == 1 else f"{n} competing"
    lines.append(f"    [{cat}] HYPOTHESIS COMPETITION ({shape}) — reality favoring: "
                 f"{leader or '(none yet)'}")
    # strongest first.
    for key, v in sorted(cands.items(), key=lambda kv: -float(kv[1].get("weight", 0.0))):
        w = float(v.get("weight", 0.0))
        p = float(v.get("prior", w))
        star = " <- leading" if key == leader else ""
        lines.append(f"        - {key:<16} weight {w:.2f}  (prior {p:.2f})"
                     f"  {v.get('claim', '')}{star}")
    return lines


def render(name: str) -> str:
    """Human-readable audit of the epistemic loop: the grounded HYPOTHESES (with their evidence),
    the HYPOTHESIS COMPETITIONS (candidate explanations + which reality favors), the predictions
    and their status, the resolved loops (hypothesised -> happened -> SURPRISE -> learned ->
    REVISED), and the calibration summary. Inspectable surface, NOT a user-facing message.
    Read-only; never raises. Every generated line is run through the no-diagnosis clean-gate."""
    try:
        data = loop(name)
    except Exception:
        data = {"hypotheses": [], "competitions": [], "predictions": [], "resolved": [],
                "open": [], "revisions": [], "calibration": calibrate(name)}

    def clean(s: str) -> str:
        return _safe_statement(s, "(an internal model note)")

    out = [f"The reality-learning (epistemic) loop for {name} (INTERNAL model-state — never spoken):"]

    hyps = data["hypotheses"]
    out.append(f"\n  HYPOTHESES (grounded, REVISABLE inferences about their world): {len(hyps)}")
    for h in hyps[-10:]:
        ev = h.get("evidence", {}) or {}
        key = h.get("candidate_key")
        tag = f"{h.get('category')}/{key}" if key else f"{h.get('category')}"
        out.append(clean(
            f"    • [{tag}] {h.get('claim')}"
            f"  (conf {float(h.get('confidence', 0)):.2f})"))
        out.append(f"        evidence: \"{ev.get('turn', '')[:80]}\""
                   + (f"  +{ev.get('world')}" if ev.get("world") else ""))

    comps = data["competitions"]
    out.append(f"\n  HYPOTHESIS COMPETITIONS (rival explanations + which reality favors): {len(comps)}")
    if not comps:
        out.append("    (none yet — a competition forms when a situation has rival explanations)")
    for comp in comps[-6:]:
        for ln in _fmt_competition(comp):
            out.append(clean(ln))

    out.append(f"\n  PREDICTIONS: {len(data['predictions'])}  "
               f"(open {len(data['open'])} · resolved {len(data['resolved'])})")
    for p in data["predictions"][-8:]:
        out.append(clean(
            f"    • [{p.get('category')}] {p.get('claim')}"
            f"  (conf {float(p.get('confidence', 0)):.2f} · horizon {p.get('horizon_days')}d"
            f" · {p.get('status', OPEN).upper()})"))

    out.append("\n  RESOLVED LOOPS (hypothesised -> predicted -> happened -> SURPRISE -> learned):")
    if not data["resolved"]:
        out.append("    (none yet — real learning accrues as real outcomes arrive over real")
        out.append("     calendar time; the machinery is live and waiting)")
    for r in data["resolved"]:
        p, o, l = r["prediction"], r.get("outcome") or {}, r["learning"]
        mark = "RIGHT" if l.get("prediction_correct") else "WRONG"
        out.append(clean(
            f"    • [{p.get('category')}]  predicted (conf {l.get('predicted_confidence')})"
            f"  ->  happened: \"{str(o.get('observed', ''))[:56]}\""
            f"  ->  {mark}  (SURPRISE {l.get('surprise')})"))
        rev = r.get("revision")
        if rev is not None:
            bw = rev.get("before_weights", {})
            aw = rev.get("after_weights", {})
            sup = rev.get("supported")
            con = rev.get("contradicted") or []
            # phrase the reweight by what reality actually did: a supported winner, else only
            # contradicted losers (a confident hypothesis the outcome refuted).
            if sup:
                what = f"strengthened '{sup}'"
            elif con:
                what = f"weakened {', '.join(repr(c) for c in con)}"
            else:
                what = "reweighted the field"
            out.append(clean(
                f"        ↳ MODEL REVISION (surprise {rev.get('surprise')}): {what} — "
                f"weights {_compact_weights(bw)} -> {_compact_weights(aw)}"))
        else:
            out.append("        ↳ low surprise — outcome CONFIRMED the model (no major revision)")

    cal = data["calibration"]
    out.append("\n  CALIBRATION — was the mind right? (accuracy over resolved predictions):")
    if cal["resolved"] == 0:
        out.append("    (nothing resolved yet — calibration is time-gated; it fills in on its")
        out.append("     own as outcomes arrive. Honest: you cannot score a future not yet lived.)")
    else:
        acc = cal["accuracy"]
        out.append(f"    overall: {cal['correct']}/{cal['resolved']} correct"
                   f"  (accuracy {acc:.0%})  ·  Brier {cal['brier']:.3f} (lower = better calibrated)")
        out.append(f"    mean SURPRISE {cal['mean_surprise']:.3f}  ·  "
                   f"model revisions triggered: {cal['revisions']}")
        for cat, c in sorted(cal["by_category"].items()):
            verdict = ("reliable" if c.get("reliable") is True
                       else ("UNRELIABLE" if c.get("reliable") is False else "too few to judge"))
            accc = c["accuracy"]
            out.append(f"      - {cat:<20} {c['correct']}/{c['resolved']}"
                       + (f"  ({accc:.0%})" if accc is not None else "")
                       + f"  [{verdict}]")
    out.append(f"    still open (waiting on reality): {cal['open']}")
    return "\n".join(out)


def _compact_weights(weights: dict, top: int = 3) -> str:
    """A tiny 'k:0.62 k:0.21' fragment of the strongest weights, for the revision render. Pure."""
    if not isinstance(weights, dict) or not weights:
        return "{}"
    items = sorted(weights.items(), key=lambda kv: -float(kv[1]))[:top]
    return "{" + ", ".join(f"{k}:{float(v):.2f}" for k, v in items) + "}"


# ===========================================================================
# SYNTHETIC TIME-SERIES — the proof. Day-1 "my manager changed" spawns COMPETING hypotheses
# (manager_change vs recent_move vs family_visit vs multiple) for rising stress, each weighted;
# the leading hypothesis yields a sleep_decline PREDICTION (horizon ~14d); Day-14 "I've barely
# slept" -> outcome ADJUDICATES (manager_change strengthened, rivals weakened, weights
# renormalised), SURPRISE computed, and (when surprising) a MODEL REVISION appended. Hermetic.
# ===========================================================================

# A fixed synthetic base date so the Day-1/Day-14 timeline is stable + reproducible.
_SYNTH_DAY1 = "2026-01-01T09:00:00Z"


def build_synthetic_loop(name: str) -> dict:
    """Drive the canonical Day-1 -> Day-14 loop through the REAL ``form`` / ``resolve`` engine,
    against whatever STORE is currently bound (the temp store under --selftest). Returns the
    formed + resolved records + the leading competition so the caller can assert the loop closed,
    the competition was adjudicated, surprise was computed, and a revision was (or wasn't) made.
    Hermetic by the caller's store redirect; touches no model, no network. Never raises.

      * Day-1:  "my manager just changed and work's been heavy" -> form() spawns the COMPETING
                stress_risk hypotheses (manager_change 0.5 / recent_move 0.3 / family_visit 0.2 /
                multiple ~0.0 after renorm), a COMPETITION record, and a sleep_decline PREDICTION
                from the LEADING hypothesis (manager_change; horizon 14d, conf 0.67).
      * Day-14: "honestly I've barely slept the last two weeks" -> resolve() matches the outcome,
                marks prediction_correct=True, computes SURPRISE, ADJUDICATES the competition
                (manager_change strengthened, rivals weakened, renormalised), and — if surprising
                enough — appends a MODEL REVISION. Calibration updates to 1/1 on sleep_decline.
    """
    day1 = "my manager just changed and work's been heavy lately"
    formed = form(name, day1, at=_SYNTH_DAY1)
    comp = next((r for r in formed if r["kind"] == COMPETITION), None)
    day14 = "honestly I've barely slept the last two weeks"
    learnings = resolve(name, day14, at=_add_days(_SYNTH_DAY1, 14))
    comp_after = competition_for(name, comp["id"]) if comp else None
    return {"formed": formed, "learnings": learnings,
            "competition_before": comp, "competition_after": comp_after,
            "revisions": _records_of(name, REVISION),
            "calibration": calibrate(name)}


# ===========================================================================
# THE DEMO REPORT (default human/JSON view) — run the synthetic loop hermetically so the
# default invocation shows a real, closed loop. (The observatory script reuses this.)
# ===========================================================================

def demo_loop_report() -> dict:
    """Build the synthetic Day-1 -> Day-14 loop in a hermetic temp store through the real engine,
    and return the loop read + calibration for the default view. Never raises — degrades to an
    empty loop. Self-contained so a CLI can show the closed loop without external wiring."""
    import tempfile
    saved = getattr(__import__(__name__, fromlist=["_"]), "STORE", None)
    try:
        with tempfile.TemporaryDirectory(prefix="anima-reality-demo-") as td:
            globals()["STORE"] = Path(td)
            nm = "reality_demo_" + secrets.token_hex(3)
            build_synthetic_loop(nm)
            data = loop(nm)
            # snapshot the render too (so a JSON consumer can show the human view).
            data["render"] = render(nm)
            return data
    except Exception:
        return {"hypotheses": [], "competitions": [], "predictions": [], "resolved": [],
                "open": [], "revisions": [],
                "calibration": {"resolved": 0, "correct": 0, "accuracy": None,
                                "brier": None, "mean_surprise": None, "revisions": 0,
                                "by_category": {}, "reliable_kinds": [],
                                "unreliable_kinds": [], "open": 0}}
    finally:
        if saved is not None:
            globals()["STORE"] = saved


# ===========================================================================
# SELF-TEST — run directly: `python3 -m anima.reality`. No model, no network; FULLY HERMETIC —
# redirects EVERY engine STORE the form/resolve/world-read path could write (memory_lirf.STORE
# on BOTH __main__ + package bindings, constitution.STORE, reliability.DEFAULT_STORE,
# curiosity.STORE, world_state.STORE, meaning.STORE, telemetry.STORE, cloud.STORE, and
# reality.STORE) to ONE temp dir, and asserts the real .anima is byte-UNCHANGED around the run.
# Mirrors memory_lirf._selftest's multi-store redirect + the sibling organs' ok(label, cond).
# ===========================================================================

# The full redirect set the hermetic block pins. (module-import-path, store-attr) pairs because
# reliability's store attr is DEFAULT_STORE, not STORE. Resolved by NAME so a missing engine is
# simply skipped — the redirect adapts to whatever is built without ever hard-failing.
_SELFTEST_STORE_TARGETS = (
    ("anima.reality", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.memory_lirf", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.constitution", "STORE"),           # the continuity ledger a good load/save writes
    ("anima.reliability", "DEFAULT_STORE"),     # guarded-backup snapshots
    ("anima.telemetry", "STORE"),
    ("anima.cloud", "STORE"),
)


def _hash_anima(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (EXCLUDING the rotating backups/ dir,
    which legitimately changes), so we can PROVE the harness touched nothing — the
    relationship.py / evolution.py guardrail, applied here."""
    import hashlib
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


def _selftest() -> int:
    import glob
    import sys as _sys
    import tempfile

    fails: list = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("reality (Epistemic Loop Keystone) self-test")

    # the real .anima footprint BEFORE — must be byte-identical after (hermetic guardrail).
    real = Path(__file__).resolve().parent.parent / ".anima"
    fp_before = _hash_anima(real)

    # --- pure machinery: time/horizon/clean-gate/SURPRISE/normalise are real functions ---------
    ok("time: deadline = formed_at + horizon (14 days)",
       _add_days("2026-01-01T00:00:00Z", 14).startswith("2026-01-15"))
    ok("clean-gate: a neutral inference phrase is clean",
       _is_clean("a recent change is a plausible new source of strain"))
    ok("clean-gate: a diagnosis/forecast phrase is caught",
       not _is_clean("you're burning out") and not _is_clean("you will spiral")
       and not _is_clean("a poor prognosis"))
    ok("kinds: the six epistemic record kinds are distinct",
       len({HYPOTHESIS, COMPETITION, PREDICTION, OUTCOME, LEARNING, REVISION}) == 6)
    ok("rename: the record kind is HYPOTHESIS (not 'belief')",
       HYPOTHESIS == "hypothesis" and "belief" not in KINDS)

    # SURPRISE — the learning gradient — exactly as specified.
    ok("surprise: confident-and-WRONG is HIGH (pred 0.82, outcome false -> ~0.82)",
       abs(surprise(0.82, False) - 0.82) < 1e-6)
    ok("surprise: doubtful-and-RIGHT is HIGH (pred 0.11, outcome true -> ~0.89)",
       abs(surprise(0.11, True) - 0.89) < 1e-6)
    ok("surprise: confidence matching reality is LOW (pred 0.90, outcome true -> ~0.10)",
       surprise(0.90, True) < 0.12 and surprise(0.05, False) < 0.06)

    # competition weight math — normalisation + the adjudication reweight.
    norm = _normalise_weights({"a": 2.0, "b": 1.0, "c": 1.0})
    ok("competition: priors normalise to sum 1.0",
       abs(sum(norm.values()) - 1.0) < 1e-6 and norm["a"] > norm["b"])
    adj = _adjudicate_weights(
        {"a": {"weight": 0.5}, "b": {"weight": 0.3}, "c": {"weight": 0.2}},
        supported_key="a", contradicted_keys=["b"])
    ok("competition: adjudication strengthens supported, weakens contradicted, renormalises",
       abs(sum(adj.values()) - 1.0) < 1e-6 and adj["a"] > 0.5 and adj["b"] < 0.3)
    ok("competition: a weakened hypothesis is floored, never annihilated (Unknown>Lost)",
       all(v > 0.0 for v in adj.values()))

    # --- HERMETIC block: redirect EVERY engine store to one temp dir; restore on exit -------
    targets = []
    seen = set()
    for modpath, attr in _SELFTEST_STORE_TARGETS:
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, attr) and (id(mod), attr) not in seen:
            targets.append((mod, attr))
            seen.add((id(mod), attr))
    # pin BOTH this __main__ binding AND the package binding of reality.STORE (they may be two
    # distinct module objects when run as `python3 -m anima.reality`).
    try:
        import anima.reality as _pkg_self
        if _pkg_self is not _sys.modules[__name__] and (id(_pkg_self), "STORE") not in seen:
            targets.append((_pkg_self, "STORE"))
            seen.add((id(_pkg_self), "STORE"))
    except Exception:
        pass
    # AND this very module object (when run as a package submodule, __name__ == 'anima.reality').
    _this = _sys.modules.get(__name__)
    if _this is not None and (id(_this), "STORE") not in seen:
        targets.append((_this, "STORE"))
        seen.add((id(_this), "STORE"))

    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    _td = tempfile.mkdtemp(prefix="reality-self-")
    _tp = Path(_td)
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, _tp)

    try:
        # ============================================================================
        # THE CANONICAL PROOF — observation -> COMPETING hypotheses -> prediction -> outcome
        # ADJUDICATES -> SURPRISE -> MODEL REVISION. Deterministic; each step asserted.
        # ============================================================================
        name = "reality_selftest_" + secrets.token_hex(3)

        # --- (a) Day-1: a stated change spawns COMPETING hypotheses, each weighted ------------
        formed = form(name, "my manager just changed and work's been heavy",
                      at=_SYNTH_DAY1)
        kinds = [r["kind"] for r in formed]
        hyps = [r for r in formed if r["kind"] == HYPOTHESIS]
        comp = next((r for r in formed if r["kind"] == COMPETITION), None)
        pred = next((r for r in formed if r["kind"] == PREDICTION), None)

        ok("form: a stated change yields HYPOTHESES (not a single belief)",
           HYPOTHESIS in kinds and len(hyps) >= 3)
        ok("COMPETING: the stress_risk situation spawns rival explanations",
           comp is not None and comp["category"] == "stress_risk"
           and {"manager_change", "recent_move", "family_visit"}.issubset(set(comp["candidates"])))
        ok("COMPETING: each candidate carries a PRIOR confidence, normalised to sum ~1",
           comp is not None
           and abs(sum(v["weight"] for v in comp["candidates"].values()) - 1.0) < 1e-4)
        ok("COMPETING: manager_change leads the competition (prior 0.5 strongest)",
           comp is not None and comp["leader"] == "manager_change")
        ok("GROUNDED: every competing hypothesis carries its EVIDENCE (the exact turn)",
           all(h["evidence"].get("turn", "").startswith("my manager") for h in hyps))
        ok("GROUNDED: the cue that fired is recorded (no inference without a stated signal)",
           all("manager" in h["evidence"].get("matched", "").lower()
               or h["evidence"].get("matched") for h in hyps) and bool(hyps))

        # --- (b) a PREDICTION from the LEADING hypothesis -------------------------------------
        ok("form: the leading hypothesis yields a sleep_decline PREDICTION (~14-day horizon)",
           bool(pred) and pred["category"] == "sleep_decline" and pred["horizon_days"] == 14)
        ok("form: the prediction is linked to the LEADING hypothesis + its competition",
           bool(pred) and pred.get("competition_id") == comp["id"]
           and pred.get("hypothesis_id") in {h["id"] for h in hyps})
        leader_hyp = next((h for h in hyps if h["id"] == pred["hypothesis_id"]), None)
        ok("form: the prediction's hypothesis IS the competition leader (manager_change)",
           bool(leader_hyp) and leader_hyp.get("candidate_key") == "manager_change")
        ok("form: the prediction carries a confidence in (0,1) and status OPEN",
           bool(pred) and 0.0 < pred["confidence"] < 1.0 and pred["status"] == OPEN)
        ok("form: the prediction's deadline is formed_at + 14 days",
           bool(pred) and pred["deadline"].startswith("2026-01-15"))
        ok("form: every record is flagged internal_only (never user-facing)",
           all(r.get("internal_only") is True for r in formed))

        # the prediction is OPEN before the outcome arrives.
        ok("ledger: the prediction is OPEN before any outcome",
           len(open_predictions(name)) == 1)
        cal0 = calibrate(name)
        ok("calibration: nothing resolved yet -> accuracy is None (honest time-gating)",
           cal0["resolved"] == 0 and cal0["accuracy"] is None and cal0["open"] == 1)

        # --- CONSERVATIVE: a thin source with NO real evidence forms NOTHING -----------------
        ok("CONSERVATIVE: a vague turn with no stated evidence forms nothing",
           form(name, "anyway, how are you?", at=_SYNTH_DAY1, persist=False) == [])
        ok("CONSERVATIVE: empty / whitespace source forms nothing",
           form(name, "", persist=False) == [] and form(name, "   ", persist=False) == [])
        ok("CONSERVATIVE: a mood word alone ('feeling off') is NOT enough evidence",
           form(name, "feeling kind of off today", persist=False) == [])

        # snapshot the competition's PRIOR weights for the adjudication assertion.
        weights_before = {k: v["weight"] for k, v in comp["candidates"].items()}

        # --- (c) Day-14: the outcome ADJUDICATES — supported up, rivals down, renormalised ----
        learnings = resolve(name, "honestly I've barely slept the last two weeks",
                            at=_add_days(_SYNTH_DAY1, 14))
        ok("resolve: a matching later outcome resolves the open prediction",
           len(learnings) == 1)
        learning = learnings[0] if learnings else {}
        ok("LOOP CLOSES: prediction_correct is True (the mind was RIGHT)",
           learning.get("prediction_correct") is True)

        comp_after = competition_for(name, comp["id"])
        weights_after = {k: v["weight"] for k, v in comp_after["candidates"].items()}
        ok("ADJUDICATE: manager_change (supported) was STRENGTHENED by the outcome",
           weights_after["manager_change"] > weights_before["manager_change"])
        ok("ADJUDICATE: a rival (recent_move) was WEAKENED by the outcome",
           weights_after["recent_move"] < weights_before["recent_move"])
        ok("ADJUDICATE: the re-weighted competition still sums to ~1 (renormalised)",
           abs(sum(weights_after.values()) - 1.0) < 1e-4)
        ok("ADJUDICATE: manager_change now leads even more decisively",
           comp_after["leader"] == "manager_change")
        # this Day-14 outcome was CORRECT but LOW-surprise (~0.33) -> a minor reweight, NOT a
        # model revision: the competition shifted but no MAJOR revision was recorded.
        ok("ADJUDICATE: a correct low-surprise outcome reweights WITHOUT a model revision",
           calibrate(name)["revisions"] == 0
           and any(not r.get("major") for r in _records_of(name, REVISION)))

        # --- (d) SURPRISE computed + the symmetric controls ----------------------------------
        ok("SURPRISE: the resolved learning carries a surprise in [0,1]",
           "surprise" in learning and 0.0 <= learning["surprise"] <= 1.0)
        # pred conf 0.67, outcome TRUE -> surprise ~0.33 (moderately surprised it confirmed).
        ok("SURPRISE: it equals |actual - predicted_confidence| (0.67 right -> ~0.33)",
           abs(learning["surprise"] - 0.33) < 0.02)

        # an OUTCOME record was appended carrying what actually happened.
        outs = _records_of(name, OUTCOME)
        ok("outcome: an OUTCOME record was appended with the observed reality",
           len(outs) == 1 and "barely slept" in outs[0].get("observed", ""))
        ok("ledger: the prediction is no longer OPEN after resolution",
           len(open_predictions(name)) == 0)

        # --- (d') a HIGH-surprise CONFIDENT-WRONG case triggers a MODEL REVISION --------------
        # A change is stated (leader manager_change, pred conf 0.67) but sleep turns out FINE ->
        # the confident sleep_decline prediction is WRONG -> surprise ~0.67 (HIGH) -> REVISION.
        name_cw = "reality_confwrong_" + secrets.token_hex(3)
        f_cw = form(name_cw, "my manager just changed", at=_SYNTH_DAY1)
        comp_cw = next((r for r in f_cw if r["kind"] == COMPETITION), None)
        before_cw = {k: v["weight"] for k, v in comp_cw["candidates"].items()}
        l_cw = resolve(name_cw, "actually I've been sleeping great, fully rested",
                       at=_add_days(_SYNTH_DAY1, 14))
        ok("SURPRISE (confident-wrong): a confident prediction proven FALSE is HIGH-surprise",
           bool(l_cw) and l_cw[0]["prediction_correct"] is False
           and l_cw[0]["surprise"] >= _SURPRISE_REVISION_AT)
        revs_cw = _records_of(name_cw, REVISION)
        ok("MODEL REVISION: the high-surprise confident-wrong outcome appended a MAJOR REVISION",
           len(revs_cw) == 1 and revs_cw[0].get("major") is True
           and revs_cw[0]["surprise"] >= _SURPRISE_REVISION_AT)
        ok("MODEL REVISION: it records before_weights -> after_weights + the trigger",
           "before_weights" in revs_cw[0] and "after_weights" in revs_cw[0]
           and revs_cw[0].get("triggered_by") == l_cw[0]["id"])
        ok("MODEL REVISION: calibrate counts it as a model revision (major only)",
           calibrate(name_cw)["revisions"] == 1)
        comp_cw_after = competition_for(name_cw, comp_cw["id"])
        after_cw = {k: v["weight"] for k, v in comp_cw_after["candidates"].items()}
        ok("MODEL REVISION: the contradicted leader (manager_change) was WEAKENED by the revision",
           after_cw["manager_change"] < before_cw["manager_change"]
           and abs(sum(after_cw.values()) - 1.0) < 1e-4)

        # --- (d'') a DOUBTFUL-RIGHT case is also HIGH-surprise (the symmetric gradient) -------
        # Construct a low-confidence prediction that turns out TRUE: surprise ~ (1 - low) is HIGH.
        name_dr = "reality_doubtright_" + secrets.token_hex(3)
        low_pred = {
            "kind": PREDICTION, "id": _new_id("p"), "version": VERSION,
            "category": "sleep_decline", "claim": "rest may be affected",
            "confidence": 0.11, "horizon_days": 14, "formed_at": _SYNTH_DAY1,
            "deadline": _add_days(_SYNTH_DAY1, 14), "status": OPEN,
            "hypothesis_id": None, "competition_id": None,
            "evidence": {"turn": "synthetic doubtful prediction"}, "internal_only": True,
        }
        _append(name_dr, low_pred)
        l_dr = resolve(name_dr, "honestly I've barely slept the last two weeks",
                       at=_add_days(_SYNTH_DAY1, 14))
        ok("SURPRISE (doubtful-right): a doubtful (0.11) prediction proven TRUE is HIGH-surprise",
           bool(l_dr) and l_dr[0]["prediction_correct"] is True
           and abs(l_dr[0]["surprise"] - 0.89) < 1e-6)

        # --- CALIBRATION UPDATES: 1/1 correct on sleep_decline (the original loop) ------------
        cal = calibrate(name)
        ok("CALIBRATION UPDATES: 1 resolved, 1 correct, accuracy 1.0",
           cal["resolved"] == 1 and cal["correct"] == 1 and cal["accuracy"] == 1.0)
        ok("calibration: per-category accuracy is recorded for sleep_decline",
           cal["by_category"].get("sleep_decline", {}).get("accuracy") == 1.0)
        ok("calibration: a Brier score AND a mean SURPRISE are computed",
           isinstance(cal["brier"], float) and isinstance(cal["mean_surprise"], float))
        ok("calibration: one data point is NOT yet a reliability verdict (Observed>Assumed)",
           cal["by_category"]["sleep_decline"].get("reliable") is None
           and cal["reliable_kinds"] == [])

        # --- a REFUTED goal prediction is recorded as WRONG (the symmetric control) -----------
        name2 = "reality_refute_" + secrets.token_hex(3)
        form(name2, "I'm planning to start running every morning", at=_SYNTH_DAY1)
        lr = resolve(name2, "yeah I never got around to it, fell off after day two",
                     at=_add_days(_SYNTH_DAY1, 21))
        ok("refute: a failed-followthrough outcome resolves the goal prediction",
           len(lr) == 1 and lr[0].get("prediction_correct") is False)
        ok("refute: actual_outcome is 0.0 and the delta is negative (overconfident)",
           lr[0].get("actual_outcome") == 0.0 and lr[0].get("delta", 0) < 0)
        cal2 = calibrate(name2)
        ok("refute: calibration shows 1 resolved, 0 correct, accuracy 0.0",
           cal2["resolved"] == 1 and cal2["correct"] == 0 and cal2["accuracy"] == 0.0)

        # --- a RELIABILITY VERDICT emerges only with enough resolved data (>= _MIN_FOR_VERDICT)
        name3 = "reality_reliable_" + secrets.token_hex(3)
        for i in range(3):
            form(name3, "my manager just changed", at=_add_days(_SYNTH_DAY1, i * 30))
            resolve(name3, "I've barely slept since",
                    at=_add_days(_SYNTH_DAY1, i * 30 + 14))
        cal3 = calibrate(name3)
        ok("reliability: 3 correct sleep_decline resolutions -> kind judged RELIABLE",
           cal3["by_category"]["sleep_decline"].get("reliable") is True
           and "sleep_decline" in cal3["reliable_kinds"])

        # --- the LOOP read + RENDER: assembled chain, competition, surprise, revision ---------
        data = loop(name)
        ok("loop: assembles hypotheses + competitions + predictions + resolved + calibration",
           len(data["hypotheses"]) >= 3 and len(data["competitions"]) >= 1
           and len(data["resolved"]) == 1 and data["calibration"]["accuracy"] == 1.0)
        ok("loop: the resolved entry carries prediction->outcome->learning(surprise) joined",
           data["resolved"][0]["prediction"]["status"] == CONFIRMED
           and data["resolved"][0]["outcome"] is not None
           and "surprise" in data["resolved"][0]["learning"])

        block = render(name)
        ok("render: produces a non-empty loop audit", bool(block.strip()))
        ok("render: names the epistemic loop stages + the COMPETITION + SURPRISE",
           "HYPOTHESES" in block and "HYPOTHESIS COMPETITION" in block
           and "PREDICTIONS" in block and "RESOLVED LOOPS" in block
           and "SURPRISE" in block and "CALIBRATION" in block)
        ok("render: shows which hypothesis reality is FAVORING in the competition",
           "reality favoring: manager_change" in block)
        ok("render: states it is INTERNAL model-state, never spoken",
           "INTERNAL model-state" in block and "never spoken" in block)
        ok("NO-DIAGNOSIS GATE: not one rendered line trips a banned term",
           all(_is_clean(ln) for ln in block.splitlines()))
        ok("render: the honest time-gating note is present for an empty loop",
           "calendar time" in render("reality_empty_" + secrets.token_hex(2)).lower())

        # the confident-wrong render shows a MODEL REVISION line.
        block_cw = render(name_cw)
        ok("render: a high-surprise resolution renders a MODEL REVISION line",
           "MODEL REVISION" in block_cw)

        # --- APPEND-ONLY (Law 001): adjudication/revision APPENDED, never rewrote a prior line -
        raw = ledger_path(name).read_text(encoding="utf-8").splitlines()
        kinds_on_disk = [json.loads(ln)["kind"] for ln in raw if ln.strip()]
        ok("append-only: ledger holds HYPOTHESIS… then COMPETITION then PREDICTION then OUTCOME/LEARNING",
           kinds_on_disk[0] == HYPOTHESIS and COMPETITION in kinds_on_disk
           and PREDICTION in kinds_on_disk and OUTCOME in kinds_on_disk
           and LEARNING in kinds_on_disk
           and kinds_on_disk.index(COMPETITION) < kinds_on_disk.index(PREDICTION))
        # the confident-wrong ledger PROVES a revision is APPENDED (the competition line is intact).
        raw_cw = ledger_path(name_cw).read_text(encoding="utf-8").splitlines()
        comp_lines = [json.loads(ln) for ln in raw_cw if ln.strip()
                      and json.loads(ln).get("kind") == COMPETITION]
        ok("append-only: the original COMPETITION line still holds its PRIOR weights on disk",
           len(comp_lines) == 1
           and comp_lines[0]["candidates"]["manager_change"]["weight"] == before_cw["manager_change"]
           and json.loads(raw_cw[-1])["kind"] == REVISION)
        n_before = len(records(name))
        # forming again appends; never truncates.
        form(name, "I just started a new job", at=_add_days(_SYNTH_DAY1, 30))
        ok("append-only: a later form() grows the ledger (prior records kept)",
           len(records(name)) > n_before)

        # --- EMPTY life: zero records -> honest empty loop + zeroed calibration --------------
        empty = "reality_blank_" + secrets.token_hex(3)
        ed = loop(empty)
        ok("empty: no records -> empty loop, no fabricated hypothesis",
           ed["hypotheses"] == [] and ed["predictions"] == [] and ed["competitions"] == []
           and ed["calibration"]["accuracy"] is None)

        # --- the demo report runs hermetically and shows a CLOSED loop -----------------------
        demo = demo_loop_report()
        ok("demo: the synthetic loop report closes one prediction correctly",
           demo["calibration"]["resolved"] == 1 and demo["calibration"]["correct"] == 1)
        ok("demo: the synthetic loop report carries a competition + the surprise gradient",
           len(demo["competitions"]) >= 1
           and isinstance(demo["calibration"]["mean_surprise"], float))

        # --- ROBUSTNESS: garbage sources never raise ----------------------------------------
        try:
            form(name, None, persist=False)
            form(name, {"nope": 1}, persist=False)
            resolve(name, None, persist=False)
            resolve(name, 12345, persist=False)
            calibrate("nonexistent_creature_xyz")
            competition_for("nonexistent_creature_xyz", "c_nope")
            crashed = False
        except Exception as e:  # noqa: BLE001
            crashed = True
            print("       (raised:", repr(e), ")")
        ok("robust: garbage/None sources are handled without raising", not crashed)

    finally:
        # clean the synthetic ledgers from the temp store, then RESTORE every real store.
        for fp in glob.glob(str(_tp / "reality_*")):
            try:
                os.remove(fp)
            except OSError:
                pass
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        try:
            import shutil
            shutil.rmtree(_td, ignore_errors=True)
        except Exception:
            pass

    # the hermetic guardrail: the real .anima must be byte-UNCHANGED around the whole run.
    fp_after = _hash_anima(real)
    ok("HERMETIC: real .anima byte-UNCHANGED around the selftest (no real Vera.* touched)",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic reality ledger leaked into real .anima",
       (not real.is_dir()) or not any(real.glob("reality_*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL REALITY SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
