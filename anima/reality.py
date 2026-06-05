"""reality — THE REALITY LEARNING KEYSTONE: Memory + Experience = Knowledge.

    UNDERSTANDING BEATS REMEMBERING — applied to BEING RIGHT OVER TIME.

``memory_lirf`` stores FACTS a person stated. ``world_state`` connects those facts into
SITUATIONS (manager -> stress -> sleep). ``meaning`` ranks what MATTERS now; ``trajectory``
reads the DIRECTION a life is drifting. This module closes the last loop a companion of
thirty years must hold — the one that turns a good memory into genuine LEARNING:

        MEMORY  ->  BELIEF  ->  PREDICTION  ->  OUTCOME  ->  LEARNING
        (a fact)   (a grounded   (a future,    (what really  (was the mind
                    inference)    time-gated)   happened)      RIGHT?)

A BELIEF is a tagged INFERENCE about the USER's world, drawn from REAL evidence (the exact
turn / situation / world-edge it rests on) and carrying its confidence. A PREDICTION is a
belief about a FUTURE outcome plus a time horizon. An OUTCOME is what actually happened,
arriving in a LATER turn. A LEARNING is what we recorded when a prediction RESOLVED against
its outcome: confirmed or refuted, with the delta. Over many resolved predictions,
``calibrate`` measures — per category — which kinds of prediction Vera gets RIGHT and which
she does not. That running accuracy IS "was the mind right?", made auditable.

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
   ``LIVE-HOOK`` comment — and is deliberately NOT wired.

2. GROUNDED — NO CONFABULATION (#1 rule). A belief is a tagged inference WITH its evidence
   attached; we ``form`` one ONLY when the source carries REAL evidence. Thin evidence ->
   NOTHING. We never invent an inner life or an unfounded claim. Every record cites the turn
   it came from (the LAW-003-style "always cite your evidence" invariant).

3. TIME-GATED — be honest. Real learning accrues only as real OUTCOMES arrive over real
   CALENDAR TIME (the same wall as longitudinal certification). The MACHINERY is built now
   and PROVEN on a synthetic time-series (see ``_selftest`` / ``build_synthetic_loop``):
   Day-1 "my manager changed" -> belief stress_risk + prediction sleep_decline (horizon
   ~14d); Day-14 "I've barely slept" -> outcome; the loop resolves prediction_correct=True
   and calibration updates. LIVE calibration needs real calendar time and accrues on its own
   (like the Evolution Observatory). Stated up front and in the report.

4. IDENTITY = OBSERVE-ONLY. Beliefs are about the USER's world, never Vera's identity
   (FROZEN until 2026-07-03). This module never reads, writes, or reasons about persona /
   portrait / identity. Subject of every record is the USER's world.

The ledger is APPEND-ONLY and PER-CREATURE, in its OWN file ``.anima/{name}.reality.jsonl``
(redirectable via ``STORE`` exactly like ``memory_lirf.STORE`` / ``meaning.STORE``). It is a
SEPARATE file — it never touches the LIRF ledger, the world store, or the meaning ledger.
A record is never overwritten or truncated (Law 001); a resolution APPENDS an outcome+learning
record that REFERS to the open prediction by id, it does not rewrite the prediction line.

Isolation-safe like its siblings: ``world_state`` / ``meaning`` are imported behind
try/except with faithful fallbacks, so this module and its self-test import and run with
nothing else built, touching no model, no network, and no real ``.anima``. Never raises out
of a public entry point — every one degrades to a safe value.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. We BUILD ON (never replace) the world-model: a belief is
# grounded in the world-state's edges/situation. world_state + meaning are imported behind
# try/except with contract-faithful fallbacks so this module + its selftest run standalone.
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
VERSION = 1


# ===========================================================================
# RECORD KINDS — the four ledger record types. Public so callers/tests reference them in one
# place. Every record is a dict with a "kind" tag; the ledger is a flat append-only stream of
# them, joined by ``prediction_id`` (outcome/learning point back at the open prediction).
# ===========================================================================
BELIEF = "belief"
PREDICTION = "prediction"
OUTCOME = "outcome"
LEARNING = "learning"
KINDS = (BELIEF, PREDICTION, OUTCOME, LEARNING)

# Prediction lifecycle status.
OPEN = "open"
CONFIRMED = "confirmed"
REFUTED = "refuted"


# ===========================================================================
# THE EVIDENCE-DRIVEN INFERENCE LIBRARY — the heart of GROUNDED belief formation.
#
# Each PATTERN is a conservative, evidence-anchored rule mapping a CLEAR signal in the
# recorded source (a turn the user actually said, or a world-edge they stated) to:
#   * a belief category + claim (an inference about the USER's world), and
#   * OPTIONALLY a prediction category + claim + horizon (when the belief implies a future).
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


# A pattern: (category, belief_claim, prediction_or_None). A prediction is
# (pred_category, pred_claim, horizon_days, confirm_regex, refute_regex). When a source matches
# ``cue``, we form the belief, and (if a prediction is given) an OPEN prediction.
class _Pattern:
    __slots__ = ("cue", "category", "belief_claim", "belief_conf",
                 "pred_category", "pred_claim", "horizon_days", "confidence",
                 "confirm", "refute")

    def __init__(self, cue, category, belief_claim, belief_conf,
                 pred_category=None, pred_claim=None, horizon_days=None, confidence=None,
                 confirm=None, refute=None):
        self.cue = cue
        self.category = category
        self.belief_claim = belief_claim
        self.belief_conf = belief_conf
        self.pred_category = pred_category
        self.pred_claim = pred_claim
        self.horizon_days = horizon_days
        self.confidence = confidence
        self.confirm = confirm
        self.refute = refute


# The conservative inference library. Each entry rests on a STATED event and forms a belief
# about the USER's world; most imply a near-future outcome we can later check. Confidences are
# deliberately moderate (we describe a tendency, we never certify a person's future). Horizons
# are honest calendar windows. NOTHING here is a diagnosis; every claim is a neutral inference.
_PATTERNS = (
    # a destabilising change -> stress is likely rising, and sleep MAY decline within ~2 weeks.
    _Pattern(
        cue=_RE_CHANGE, category="stress_risk",
        belief_claim="a recent change in their situation is a plausible new source of strain",
        belief_conf=0.62,
        pred_category="sleep_decline",
        pred_claim="rest may be affected within the next couple of weeks",
        horizon_days=14, confidence=0.67,
        confirm=_RE_SLEEP_BAD, refute=_RE_SLEEP_GOOD,
    ),
    # a stated goal -> they MAY follow through within ~3 weeks (a check on intention vs action).
    _Pattern(
        cue=_RE_GOAL, category="goal_followthrough",
        belief_claim="they have stated an intention they mean to act on",
        belief_conf=0.6,
        pred_category="goal_followthrough",
        pred_claim="the stated intention may be acted on within a few weeks",
        horizon_days=21, confidence=0.55,
        confirm=_RE_GOAL_DONE, refute=_RE_GOAL_DROPPED,
    ),
    # an overload -> recovery/downtime MAY shrink within ~10 days.
    _Pattern(
        cue=_RE_OVERLOAD, category="load_risk",
        belief_claim="their workload is heavier than usual right now",
        belief_conf=0.6,
        pred_category="downtime_decline",
        pred_claim="time for rest/recovery may shrink in the coming days",
        horizon_days=10, confidence=0.6,
        confirm=_RE_LESS_DOWNTIME, refute=None,
    ),
)


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
# THE LEDGER — append-only, per-creature, its OWN file. NEVER truncated/overwritten (Law 001),
# exactly like the meaning / continuity / trajectory ledgers. A resolution APPENDS outcome +
# learning records that refer to the prediction by id; it never rewrites the prediction line.
# ===========================================================================

def ledger_path(name: str) -> Path:
    """The append-only reality ledger for ``name`` — one JSON record per line, never rewritten
    (Law 001). A SEPARATE file from LIRF / world / meaning; this module's only persisted state."""
    return STORE / f"{name}.reality.jsonl"


def _append(name: str, record: dict) -> Optional[dict]:
    """Append one record to the ledger and return it. APPEND-ONLY: O_APPEND, never truncates an
    existing ledger (Law 001). Best-effort: a write failure returns None rather than raising."""
    try:
        path = ledger_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
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
        for line in path.read_text(encoding="utf-8").splitlines():
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


# ===========================================================================
# GROUNDING — extract the REAL evidence a source carries. A source may be (a) a raw recorded
# turn string, or (b) a structured situation/world-edge dict. We never form a belief without a
# concrete evidence string pinned to it. Mirrors world_state.capture's never-infer anchoring.
# ===========================================================================

def _source_text(source: Any) -> str:
    """The text to scan for evidence. A string source IS the text; a dict source may carry a
    ``text`` / ``utterance`` / ``query`` field (a recorded turn) — we read that, never invent
    one. Anything else yields "" (-> no belief). Pure."""
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
    citation of that edge — so a formed belief rests on the world-state too, not only the raw
    turn. Read-only on the world store; None when nothing corroborates or world_state is absent.

    This is the EXTENDS-not-replaces link to world_state: reality builds beliefs ON its edges.
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
    # cite the first stressor/problem/relationship edge — the kind that grounds a strain belief.
    for e in edges:
        if not isinstance(e, dict):
            continue
        pred = str(e.get("predicate", ""))
        if pred in ("stressed_by", "worried_about", "because", "is", "has"):
            return (f"world-edge: {e.get('subject')} --{pred}--> {e.get('object')}")
    return None


# ===========================================================================
# 1) form(source) — derive a grounded BELIEF and (if it implies a future) a PREDICTION, from a
# turn / situation / world-edge with CLEAR evidence. CONSERVATIVE: only when evidence is real,
# each carries its evidence, thin evidence -> NOTHING (returns []). Appends to the ledger.
# ===========================================================================

def form(name: str, source: Any, *, at: Optional[str] = None, persist: bool = True) -> list:
    """Form grounded BELIEF (+ optional PREDICTION) records from one recorded ``source``.

    ``source`` is a recorded turn (string) or a situation/world-edge dict carrying a turn — the
    ALREADY-RECORDED conversation/state, NOT a live reply. For each inference PATTERN whose cue
    fires on REAL evidence in the source, we form:
      * a BELIEF — a tagged inference about the USER's world, carrying {category, claim,
        confidence, evidence (the exact text + any corroborating world-edge), formed_at}, and
      * (when the pattern implies a future) a PREDICTION — {category, claim, confidence,
        horizon_days, deadline, formed_at, status: OPEN, belief_id}.

    CONSERVATIVE BY CONSTRUCTION: a source with no clear evidence matches no pattern and yields
    [] — we never fabricate a belief or an inner life (#1 rule). Every record cites its evidence.

    ``at`` (ISO-Z) overrides the wall clock — used by the synthetic time-series to place a Day-1
    record in calendar time; live callers omit it. ``persist`` appends to the ledger (default);
    set False to derive without writing (a dry read). Returns the records formed (belief first,
    then its prediction). Never raises.

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
            "turn": text.strip()[:240],          # the exact recorded turn the belief rests on
            "matched": m.group(0).strip()[:80],   # the concrete cue that fired (no inference)
        }
        if world_cite:
            evidence["world"] = world_cite
        belief = {
            "kind": BELIEF,
            "id": _new_id("b"),
            "version": VERSION,
            "category": pat.category,
            "claim": pat.belief_claim,
            "confidence": float(pat.belief_conf),
            "evidence": evidence,
            "formed_at": when,
            # the internal-only marker: this is model-state, never a user-facing assertion.
            "internal_only": True,
        }
        formed.append(belief)
        if persist:
            _append(name, belief)
        # a prediction, only when the pattern implies a checkable future.
        if pat.pred_category and pat.pred_claim and pat.horizon_days:
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
                "belief_id": belief["id"],
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
# 2) resolve(later_source) — match a LATER recorded outcome to an OPEN prediction, mark it
# confirmed/refuted, and append the OUTCOME + LEARNING records (belief_before, reality_after,
# delta, prediction_correct). The bridge from continuity to LEARNING.
# ===========================================================================

def resolve(name: str, later_source: Any, *, at: Optional[str] = None,
            persist: bool = True) -> list:
    """Resolve OPEN predictions against a LATER recorded outcome.

    ``later_source`` is a recorded turn / situation arriving after the prediction was formed
    (e.g. Day-14 "I've barely slept"). For each OPEN prediction whose CATEGORY has a stated
    confirm/refute signal present in this source, we:
      * append an OUTCOME record — {observed (the stated fact), observed_at, prediction_id}, and
      * append a LEARNING record — {prediction_id, category, belief_before (the prediction's
        confidence), reality_after (1.0 confirmed / 0.0 refuted), delta, prediction_correct:
        bool, resolved_at} — which is what marks the prediction RESOLVED and feeds ``calibrate``.

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
        belief_before = float(pred.get("confidence", 0.5))
        reality_after = 1.0 if verdict else 0.0
        learning = {
            "kind": LEARNING,
            "id": _new_id("l"),
            "version": VERSION,
            "prediction_id": pid,
            "outcome_id": outcome["id"],
            "category": category,
            "prediction_correct": bool(verdict),
            "belief_before": round(belief_before, 4),
            "reality_after": reality_after,
            # the surprise: how far the predicted confidence sat from what actually happened.
            "delta": round(reality_after - belief_before, 4),
            "resolved_at": when,
            "internal_only": True,
        }
        learnings.append(learning)
        if persist:
            _append(name, learning)
    return learnings


# ===========================================================================
# 3) calibrate() — running accuracy over RESOLVED records, per category. "Was the mind right?"
# over time: which prediction kinds Vera gets right, which she gets wrong, and her overall
# Brier-style calibration (how well her stated confidence matched reality).
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
          "by_category": { category -> {resolved, correct, accuracy, brier,
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
    for l in learnings:
        cat = str(l.get("category", "")) or "uncategorised"
        ok = bool(l.get("prediction_correct"))
        conf = float(l.get("belief_before", 0.5) or 0.5)
        reality = float(l.get("reality_after", 1.0 if ok else 0.0))
        total += 1
        correct += 1 if ok else 0
        brier_sum += (reality - conf) ** 2
        c = by_cat.setdefault(cat, {"resolved": 0, "correct": 0, "_brier": 0.0})
        c["resolved"] += 1
        c["correct"] += 1 if ok else 0
        c["_brier"] += (reality - conf) ** 2

    reliable, unreliable = [], []
    for cat, c in by_cat.items():
        n = c["resolved"]
        c["accuracy"] = round(c["correct"] / n, 4) if n else None
        c["brier"] = round(c["_brier"] / n, 4) if n else None
        del c["_brier"]
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
# THE LOOP READ — assemble the full Memory->Belief->Prediction->Outcome->Learning chain per
# creature, joined by id, for the observatory to render. Read-only; never raises.
# ===========================================================================

def loop(name: str) -> dict:
    """The whole learning loop for ``name``, assembled from the ledger and joined by id:

        {
          "beliefs":     [...],          # grounded inferences, newest last
          "predictions": [...],          # each tagged status OPEN/CONFIRMED/REFUTED (derived)
          "resolved":    [ {prediction, outcome, learning}, ... ],  # closed loops
          "open":        [...],          # predictions still waiting on a real outcome
          "calibration": calibrate(name),
        }

    This is the audit view of "believed -> predicted -> happened -> learned". Read-only."""
    beliefs = _records_of(name, BELIEF)
    predictions = _records_of(name, PREDICTION)
    outcomes = {o.get("prediction_id"): o for o in _records_of(name, OUTCOME)
                if o.get("prediction_id")}
    learnings = {l.get("prediction_id"): l for l in _records_of(name, LEARNING)
                 if l.get("prediction_id")}

    resolved = []
    open_list = []
    enriched_preds = []
    for p in predictions:
        pid = p.get("id")
        learning = learnings.get(pid)
        if learning is not None:
            status = CONFIRMED if learning.get("prediction_correct") else REFUTED
            p = {**p, "status": status}
            resolved.append({"prediction": p, "outcome": outcomes.get(pid), "learning": learning})
        else:
            p = {**p, "status": OPEN}
            open_list.append(p)
        enriched_preds.append(p)

    return {
        "beliefs": beliefs,
        "predictions": enriched_preds,
        "resolved": resolved,
        "open": open_list,
        "calibration": calibrate(name),
    }


# ===========================================================================
# AUDIT SURFACE — human-readable 'the learning loop', the keystone counterpart to
# meaning.render / trajectory.render. Read-only; never the live reply. Every emitted line
# passes the clean-gate (no diagnosis / no forecast voice), defence in depth.
# ===========================================================================

def render(name: str) -> str:
    """Human-readable audit of the learning loop: the grounded beliefs (with their evidence),
    the predictions and their status, the resolved loops (believed -> happened -> learned), and
    the calibration summary. Inspectable surface, NOT a user-facing message. Read-only; never
    raises. Every generated line is run through the no-diagnosis clean-gate."""
    try:
        data = loop(name)
    except Exception:
        data = {"beliefs": [], "predictions": [], "resolved": [], "open": [],
                "calibration": calibrate(name)}

    def clean(s: str) -> str:
        return _safe_statement(s, "(an internal model note)")

    out = [f"The reality-learning loop for {name} (INTERNAL model-state — never spoken):"]
    beliefs = data["beliefs"]
    out.append(f"\n  BELIEFS (grounded inferences about their world): {len(beliefs)}")
    for b in beliefs[-8:]:
        ev = b.get("evidence", {}) or {}
        out.append(clean(
            f"    • [{b.get('category')}] {b.get('claim')}"
            f"  (conf {float(b.get('confidence', 0)):.2f})"))
        out.append(f"        evidence: \"{ev.get('turn', '')[:80]}\""
                   + (f"  +{ev.get('world')}" if ev.get("world") else ""))

    out.append(f"\n  PREDICTIONS: {len(data['predictions'])}  "
               f"(open {len(data['open'])} · resolved {len(data['resolved'])})")
    for p in data["predictions"][-8:]:
        out.append(clean(
            f"    • [{p.get('category')}] {p.get('claim')}"
            f"  (conf {float(p.get('confidence', 0)):.2f} · horizon {p.get('horizon_days')}d"
            f" · {p.get('status', OPEN).upper()})"))

    out.append("\n  RESOLVED LOOPS (believed -> predicted -> happened -> learned):")
    if not data["resolved"]:
        out.append("    (none yet — real learning accrues as real outcomes arrive over real")
        out.append("     calendar time; the machinery is live and waiting)")
    for r in data["resolved"]:
        p, o, l = r["prediction"], r.get("outcome") or {}, r["learning"]
        mark = "RIGHT" if l.get("prediction_correct") else "WRONG"
        out.append(clean(
            f"    • [{p.get('category')}]  predicted (conf {l.get('belief_before')})"
            f"  ->  happened: \"{str(o.get('observed', ''))[:60]}\""
            f"  ->  {mark}  (delta {l.get('delta')})"))

    cal = data["calibration"]
    out.append("\n  CALIBRATION — was the mind right? (accuracy over resolved predictions):")
    if cal["resolved"] == 0:
        out.append("    (nothing resolved yet — calibration is time-gated; it fills in on its")
        out.append("     own as outcomes arrive. Honest: you cannot score a future not yet lived.)")
    else:
        acc = cal["accuracy"]
        out.append(f"    overall: {cal['correct']}/{cal['resolved']} correct"
                   f"  (accuracy {acc:.0%})  ·  Brier {cal['brier']:.3f} (lower = better calibrated)")
        for cat, c in sorted(cal["by_category"].items()):
            verdict = ("reliable" if c.get("reliable") is True
                       else ("UNRELIABLE" if c.get("reliable") is False else "too few to judge"))
            accc = c["accuracy"]
            out.append(f"      - {cat:<20} {c['correct']}/{c['resolved']}"
                       + (f"  ({accc:.0%})" if accc is not None else "")
                       + f"  [{verdict}]")
    out.append(f"    still open (waiting on reality): {cal['open']}")
    return "\n".join(out)


# ===========================================================================
# SYNTHETIC TIME-SERIES — the proof. Day-1 "my manager changed" -> belief stress_risk +
# prediction sleep_decline (horizon ~14d); Day-14 "I've barely slept" -> outcome; the loop
# resolves prediction_correct=True and calibration updates. Hermetic; no model, no network.
# ===========================================================================

# A fixed synthetic base date so the Day-1/Day-14 timeline is stable + reproducible.
_SYNTH_DAY1 = "2026-01-01T09:00:00Z"


def build_synthetic_loop(name: str) -> dict:
    """Drive the canonical Day-1 -> Day-14 loop through the REAL ``form`` / ``resolve`` engine,
    against whatever STORE is currently bound (the temp store under --selftest). Returns the
    formed + resolved records so the caller can assert the loop closed. Hermetic by the caller's
    store redirect; touches no model, no network. Never raises.

      * Day-1:  "my manager just changed and work's been heavy" -> form() derives a
                stress_risk BELIEF + a sleep_decline PREDICTION (horizon 14d, conf 0.67).
      * Day-14: "honestly I've barely slept the last two weeks" -> resolve() matches the
                outcome to the open prediction, marks prediction_correct=True, records the
                OUTCOME + LEARNING, and calibration updates to 1/1 on sleep_decline.
    """
    day1 = "my manager just changed and work's been heavy lately"
    formed = form(name, day1, at=_SYNTH_DAY1)
    day14 = "honestly I've barely slept the last two weeks"
    learnings = resolve(name, day14, at=_add_days(_SYNTH_DAY1, 14))
    return {"formed": formed, "learnings": learnings, "calibration": calibrate(name)}


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
        return {"beliefs": [], "predictions": [], "resolved": [], "open": [],
                "calibration": {"resolved": 0, "correct": 0, "accuracy": None,
                                "brier": None, "by_category": {}, "reliable_kinds": [],
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

    print("reality (Reality Learning Keystone) self-test")

    # the real .anima footprint BEFORE — must be byte-identical after (hermetic guardrail).
    real = Path(__file__).resolve().parent.parent / ".anima"
    fp_before = _hash_anima(real)

    # --- pure machinery: time/horizon/clean-gate are real functions (no store needed) -------
    ok("time: deadline = formed_at + horizon (14 days)",
       _add_days("2026-01-01T00:00:00Z", 14).startswith("2026-01-15"))
    ok("clean-gate: a neutral inference phrase is clean",
       _is_clean("a recent change is a plausible new source of strain"))
    ok("clean-gate: a diagnosis/forecast phrase is caught",
       not _is_clean("you're burning out") and not _is_clean("you will spiral")
       and not _is_clean("a poor prognosis"))
    ok("kinds: the four record kinds are distinct",
       len({BELIEF, PREDICTION, OUTCOME, LEARNING}) == 4)

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
        # THE CANONICAL PROOF — Day-1 -> Day-14 loop closes, prediction_correct, cal updates.
        # ============================================================================
        name = "reality_selftest_" + secrets.token_hex(3)

        # --- Day-1: form a grounded belief + prediction from a stated change -----------------
        formed = form(name, "my manager just changed and work's been heavy",
                      at=_SYNTH_DAY1)
        kinds = [r["kind"] for r in formed]
        ok("form: a stated change yields a BELIEF", BELIEF in kinds)
        ok("form: it also yields a future PREDICTION", PREDICTION in kinds)
        belief = next((r for r in formed if r["kind"] == BELIEF), None)
        pred = next((r for r in formed if r["kind"] == PREDICTION), None)
        ok("form: the belief is the stress_risk category",
           bool(belief) and belief["category"] == "stress_risk")
        ok("GROUNDED: the belief carries its EVIDENCE (the exact turn it rests on)",
           bool(belief) and belief["evidence"].get("turn", "").startswith("my manager"))
        ok("GROUNDED: the cue that fired is recorded (no inference without a stated signal)",
           bool(belief) and "manager" in belief["evidence"].get("matched", "").lower())
        ok("form: the prediction is sleep_decline with a ~14-day horizon",
           bool(pred) and pred["category"] == "sleep_decline" and pred["horizon_days"] == 14)
        ok("form: the prediction carries a confidence in (0,1) and status OPEN",
           bool(pred) and 0.0 < pred["confidence"] < 1.0 and pred["status"] == OPEN)
        ok("form: the prediction's deadline is formed_at + 14 days",
           bool(pred) and pred["deadline"].startswith("2026-01-15"))
        ok("form: every record is flagged internal_only (never user-facing)",
           all(r.get("internal_only") is True for r in formed))
        ok("form: prediction is linked to its belief by id",
           bool(pred) and pred.get("belief_id") == belief["id"])

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

        # --- Day-14: the outcome arrives; the loop RESOLVES prediction_correct=True ----------
        learnings = resolve(name, "honestly I've barely slept the last two weeks",
                            at=_add_days(_SYNTH_DAY1, 14))
        ok("resolve: a matching later outcome resolves the open prediction",
           len(learnings) == 1)
        learning = learnings[0] if learnings else {}
        ok("LOOP CLOSES: prediction_correct is True (the mind was RIGHT)",
           learning.get("prediction_correct") is True)
        ok("learning: it records belief_before, reality_after, and the delta",
           "belief_before" in learning and learning.get("reality_after") == 1.0
           and "delta" in learning)
        ok("learning: the learning points back at the prediction by id",
           learning.get("prediction_id") == pred["id"])
        # an OUTCOME record was appended carrying what actually happened.
        outs = _records_of(name, OUTCOME)
        ok("outcome: an OUTCOME record was appended with the observed reality",
           len(outs) == 1 and "barely slept" in outs[0].get("observed", ""))
        ok("ledger: the prediction is no longer OPEN after resolution",
           len(open_predictions(name)) == 0)

        # --- CALIBRATION UPDATES: 1/1 correct on sleep_decline -------------------------------
        cal = calibrate(name)
        ok("CALIBRATION UPDATES: 1 resolved, 1 correct, accuracy 1.0",
           cal["resolved"] == 1 and cal["correct"] == 1 and cal["accuracy"] == 1.0)
        ok("calibration: per-category accuracy is recorded for sleep_decline",
           cal["by_category"].get("sleep_decline", {}).get("accuracy") == 1.0)
        ok("calibration: a Brier score is computed (calibration quality)",
           isinstance(cal["brier"], float))
        ok("calibration: one data point is NOT yet a reliability verdict (Observed>Assumed)",
           cal["by_category"]["sleep_decline"].get("reliable") is None
           and cal["reliable_kinds"] == [])

        # --- a REFUTED prediction is recorded as WRONG (the symmetric control) ---------------
        name2 = "reality_refute_" + secrets.token_hex(3)
        form(name2, "I'm planning to start running every morning", at=_SYNTH_DAY1)
        lr = resolve(name2, "yeah I never got around to it, fell off after day two",
                     at=_add_days(_SYNTH_DAY1, 21))
        ok("refute: a failed-followthrough outcome resolves the goal prediction",
           len(lr) == 1 and lr[0].get("prediction_correct") is False)
        ok("refute: reality_after is 0.0 and the delta is negative (overconfident)",
           lr[0].get("reality_after") == 0.0 and lr[0].get("delta", 0) < 0)
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

        # --- the LOOP read + RENDER: assembled chain, no-diagnosis, never raises -------------
        data = loop(name)
        ok("loop: assembles beliefs + predictions + resolved + calibration",
           len(data["beliefs"]) >= 1 and len(data["resolved"]) == 1
           and data["calibration"]["accuracy"] == 1.0)
        ok("loop: the resolved entry carries belief->outcome->learning joined",
           data["resolved"][0]["prediction"]["status"] == CONFIRMED
           and data["resolved"][0]["outcome"] is not None
           and data["resolved"][0]["learning"]["prediction_correct"] is True)

        block = render(name)
        ok("render: produces a non-empty loop audit", bool(block.strip()))
        ok("render: names the loop stages (believed -> predicted -> happened -> learned)",
           "BELIEFS" in block and "PREDICTIONS" in block and "RESOLVED LOOPS" in block
           and "CALIBRATION" in block)
        ok("render: states it is INTERNAL model-state, never spoken",
           "INTERNAL model-state" in block and "never spoken" in block)
        ok("NO-DIAGNOSIS GATE: not one rendered line trips a banned term",
           all(_is_clean(ln) for ln in block.splitlines()))
        ok("render: the honest time-gating note is present for an empty loop",
           "calendar time" in render("reality_empty_" + secrets.token_hex(2)).lower())

        # --- APPEND-ONLY (Law 001): resolution APPENDED, never rewrote the prediction line ---
        raw = ledger_path(name).read_text(encoding="utf-8").splitlines()
        kinds_on_disk = [json.loads(ln)["kind"] for ln in raw if ln.strip()]
        ok("append-only: ledger holds belief THEN prediction THEN outcome THEN learning",
           kinds_on_disk[:2] == [BELIEF, PREDICTION]
           and OUTCOME in kinds_on_disk and LEARNING in kinds_on_disk)
        n_before = len(records(name))
        # forming again appends; never truncates.
        form(name, "I just started a new job", at=_add_days(_SYNTH_DAY1, 30))
        ok("append-only: a later form() grows the ledger (prior records kept)",
           len(records(name)) > n_before)

        # --- EMPTY life: zero records -> honest empty loop + zeroed calibration --------------
        empty = "reality_blank_" + secrets.token_hex(3)
        ed = loop(empty)
        ok("empty: no records -> empty loop, no fabricated belief",
           ed["beliefs"] == [] and ed["predictions"] == []
           and ed["calibration"]["accuracy"] is None)

        # --- the demo report runs hermetically and shows a CLOSED loop -----------------------
        demo = demo_loop_report()
        ok("demo: the synthetic loop report closes one prediction correctly",
           demo["calibration"]["resolved"] == 1 and demo["calibration"]["correct"] == 1)

        # --- ROBUSTNESS: garbage sources never raise ----------------------------------------
        try:
            form(name, None, persist=False)
            form(name, {"nope": 1}, persist=False)
            resolve(name, None, persist=False)
            resolve(name, 12345, persist=False)
            calibrate("nonexistent_creature_xyz")
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
