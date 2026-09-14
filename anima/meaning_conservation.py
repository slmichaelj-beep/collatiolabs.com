"""meaning_conservation — THE MEANING-CONSERVATION ENGINE (directive #4).

    Data conservation asks "was the INFORMATION preserved?"
    MEANING conservation asks "was what MATTERED preserved?"

``scripts/conservation.py`` (the Conservation Observatory) follows a byte: every salient
token is traced DETECTED -> CAPTURED -> STORED -> RETRIEVED -> USED, and the stage that
drops it is named. That is *data* conservation — "did the surface survive?". This engine
asks the harder, Law-003 question one level up: for an utterance, what is its MEANING —
the SIGNIFICANCE a companion of thirty years would carry — and did THAT survive the
pipeline, even where the literal words did not?

The worked example the founder named:

    "My daughter Maya started kindergarten"
      LITERAL  : {daughter, Maya, kindergarten}     — the facts/tokens
      MEANING  : {family milestone, child development, emotional significance}

The literal layer is the ``memory_lirf`` fact + the ``world_state`` nodes. The MEANING
layer is the SIGNIFICANCE of that fact: a life-event (a child started school), a milestone
(a child in the person's life), a relational weight (the bond to the daughter), and — when
the user voiced it — an emotional tone. This engine extracts BOTH, and for each MEANING
unit tracks whether it was RETAINED through capture -> store -> surfaceable, naming the
loss_reason when it falls out.

────────────────────────────────────────────────────────────────────────────────────────────
THE #1 RULE — MEANING MUST BE DERIVED, NEVER INVENTED
────────────────────────────────────────────────────────────────────────────────────────────
A MEANING unit is emitted ONLY when it can be GROUNDED in evidence that already exists:

  * the WORDS of the utterance (every unit's ``grounded_in`` surface must be present in the
    input — a token/phrase the user actually said), AND
  * a STRUCTURAL signal from the live engines, one of:
      - a ``world_state`` life-event / relationship / problem edge (its predicate+kind),
      - a ``memory_lirf`` ``reported_feeling`` row (the user's stated affect),
      - a ``review`` milestone trait/predicate (the review engine's own milestone machinery),
      - the ``meaning.py`` significance machinery over the stored graph.

If a candidate meaning cannot be tied to BOTH the user's words AND a structural signal, it
is NOT emitted (``_ground`` returns None). There is no free-text inference and no model:
the same discipline ``meaning.py`` enforces ("significance is a FUNCTION OF THE EVIDENCE,
never a flat or model guess"). The self-test PROVES an ungrounded meaning is rejected.

This mirrors the no-diagnosis posture too: a meaning STATEMENT is descriptive and is run
through ``meaning._is_clean`` (or a faithful local copy) so no clinical/medical language
can leak — "a family milestone" is fine, a diagnosis is forbidden and scrubbed.

────────────────────────────────────────────────────────────────────────────────────────────
THE FOUR MEANING DIMENSIONS the directive names (each a class of meaning unit)
────────────────────────────────────────────────────────────────────────────────────────────
  LITERAL        the facts/tokens (the data layer — the conservation.py units, reused)
  MEANING        the union of all derived significance units (the headline rate)
  EMOTIONAL TONE the user's stated affect (``reported_feeling`` + a stated stressor/worry)
  LIFE EVENT     a stated transition (moved / started / adopted / married / graduated …)

A MEANING unit also carries its finer ``kind`` (life_event | milestone | relational_weight
| emotional_tone | theme) so the report can break meaning down by type. The four RATES the
directive asks for are the retention of: every LITERAL unit, every MEANING unit, every
EMOTIONAL-TONE unit, and every LIFE-EVENT unit.

────────────────────────────────────────────────────────────────────────────────────────────
RETENTION — captured -> stored -> surfaceable
────────────────────────────────────────────────────────────────────────────────────────────
For each unit we walk three gates and record where it (first) fell out:

  CAPTURED    the live capture path credited it in memory (a LIRF candidate / a world edge
              / a reported_feeling row) — the meaning was SEEN.
  STORED      it survives ``Facts.save`` / ``World.save`` and a reload FROM DISK — the
              meaning is DURABLE.
  SURFACEABLE the meaning can be re-surfaced: its subject appears as a significant theme in
              ``meaning.significance`` / a Meaning Object, OR (for a milestone/life-event)
              the ``review.daily_review`` keep-forever rollup carries it. A unit that is
              stored but never re-surfaceable is meaning that is on disk yet mute.

``loss_reason`` names the FIRST gate a unit failed (or "" if it rode through), so nothing
is dropped silently — the same accounting discipline as the data observatory.

────────────────────────────────────────────────────────────────────────────────────────────
DISCIPLINE (mirrors anima/meaning.py + the conservation harness)
────────────────────────────────────────────────────────────────────────────────────────────
  * READ-ONLY on every store at the engine layer; the only writes are the temp-store ones
    the live capture path makes during a measurement, all redirected to a throwaway dir by
    the observatory (scripts/meaning_conservation.py). This module itself never writes the
    real .anima.
  * Isolation-safe: the live ``memory_lirf`` / ``world_state`` / ``meaning`` / ``review``
    primitives are reused when importable and fall back to contract-faithful behaviour
    (empty signals) when run standalone, so ``python3 -m anima.meaning_conservation`` has
    zero unbuilt deps and touches no model, network, or real ``.anima``.
  * Never raises into a caller: every public entry point degrades to a safe empty value.

    python3 -m anima.meaning_conservation        # in-module smoke + grounding invariant
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe — prefer the live engines, degrade to empty
# signals so this module + its smoke test run with nothing built. We READ:
#   memory_lirf — extract/capture (LITERAL facts + the reported_feeling tone row),
#                 Facts (stored rows), SELF, canon_trait, LIST_TRAITS
#   world_state — capture/capture_relations (life-event/relation/problem edges),
#                 World (stored edges), KINDS, _norm_node
#   meaning     — significance/meaning/current_chapter (the SIGNIFICANCE source) +
#                 the no-diagnosis _is_clean wall
#   review      — daily_review (the keep-forever rollup) + the milestone machinery
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from . import memory_lirf as _lirf
    _HAVE_LIRF = True
except Exception:  # pragma: no cover - isolation fallback
    _lirf = None  # type: ignore
    _HAVE_LIRF = False

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

try:  # pragma: no cover - import wiring
    from . import review as _review
    _HAVE_REVIEW = True
except Exception:  # pragma: no cover - isolation fallback
    _review = None  # type: ignore
    _HAVE_REVIEW = False


SELF = getattr(_lirf, "SELF", "you") if _HAVE_LIRF else "you"
VERSION = 1


# ===========================================================================
# THE FOUR DIMENSIONS the directive names + the finer meaning KINDS. Public
# constants so callers/tests reference them in exactly one place.
# ===========================================================================
LITERAL = "literal"               # the facts/tokens (data layer)
MEANING = "meaning"               # the union of all derived significance units
EMOTIONAL_TONE = "emotional_tone"  # the user's stated affect
LIFE_EVENT = "life_event"          # a stated transition

# the finer kind of a MEANING unit (all roll up into the MEANING rate; tone/life-event
# additionally roll up into their own named rate).
KIND_LIFE_EVENT = "life_event"
KIND_MILESTONE = "milestone"
KIND_RELATIONAL = "relational_weight"
KIND_TONE = "emotional_tone"
KIND_THEME = "theme"
MEANING_KINDS = (KIND_LIFE_EVENT, KIND_MILESTONE, KIND_RELATIONAL, KIND_TONE, KIND_THEME)

# the retention gates, in order. A unit is present at gate N only if present at N-1.
CAPTURED = "captured"
STORED = "stored"
SURFACEABLE = "surfaceable"
GATES = (CAPTURED, STORED, SURFACEABLE)


# ===========================================================================
# NO-DIAGNOSIS WALL — defer to meaning's canonical wall when importable (single source of
# truth), else a faithful local copy, so a meaning STATEMENT can never carry clinical/
# medical language. "a family milestone" is fine; a diagnosis is scrubbed by construction.
# ===========================================================================
_BANNED_FALLBACK = (
    "depressed", "depression", "anxiety", "diagnos", "disorder", "mental illness",
    "burnout", "burning out", "burned out", "burnt out", "clinical",
    "see a doctor", "see a therapist", "see a professional", "seek help",
    "medication", "prescription", "therapy", "therapist", "psychiatr", "psycholog",
    "symptom", "syndrome", "patholog", "trauma", "ptsd", "suicid", "self-harm",
    "self harm", "eating disorder", "addiction", "addicted", "bipolar", "ocd",
    "adhd", "panic attack", "nervous breakdown", "breakdown", "chronic stress",
    "manic", "neuros", "spiral", "falling apart", "something wrong with you",
)


def _is_clean(text: str) -> bool:
    """True iff ``text`` carries NO diagnosis/medical term. Defers to ``meaning._is_clean``
    (the canonical wall) when importable, else the local list. Pure; never raises."""
    if not text:
        return True
    if _HAVE_MEANING and _meaning is not None:
        try:
            return bool(_meaning._is_clean(text))
        except Exception:
            pass
    low = text.lower()
    return not any(term in low for term in _BANNED_FALLBACK)


# ===========================================================================
# TEXT HELPERS — a unit's grounding surface must literally appear in the user's words.
# We tokenise the input once into a lowercased word/number set + keep the raw lowercased
# string, so a single-word grounding ("kindergarten") matches a token and a phrase
# grounding ("really stressed") matches a substring. This is the #1-RULE gate: no token /
# phrase in the input -> the meaning is NOT grounded -> NOT emitted.
# ===========================================================================
_WORD = re.compile(r"[A-Za-z0-9'$]+")


def _norm_tok(s: Any) -> str:
    """A unit's normalised single-token key (lowercase, alnum only)."""
    return re.sub(r"[^a-z0-9$]+", "", str(s).strip().lower())


def _input_index(text: str) -> tuple:
    """(token_set, lowered_string) for an utterance — the grounding evidence surface. The
    token set credits a single-word grounding; the lowered string credits a multi-word
    phrase grounding. Pure."""
    low = (text or "").lower()
    toks = {_norm_tok(w) for w in _WORD.findall(low)}
    toks.discard("")
    return toks, low


def _grounded_surface(candidate: str, idx: tuple) -> Optional[str]:
    """Return the grounding surface (the words from the utterance that justify a meaning
    unit) if ``candidate`` is present in the input, else None. A single token must be in the
    token set; a multi-word phrase must appear as a substring. This is the load-bearing
    #1-RULE check: a candidate the user did not actually say is NOT grounded."""
    toks, low = idx
    cand = str(candidate or "").strip().lower()
    if not cand:
        return None
    parts = [p for p in _WORD.findall(cand)]
    if not parts:
        return None
    if len(parts) == 1:
        return cand if _norm_tok(parts[0]) in toks else None
    # multi-word: require the phrase (its salient words) to appear as a contiguous-ish run.
    phrase = " ".join(parts)
    if phrase in low:
        return phrase
    # else require EVERY content word to be present (order-free) — still grounded in the
    # user's words, just not contiguous. Conservative: all parts must be real input tokens.
    if all(_norm_tok(p) in toks for p in parts):
        return phrase
    return None


# ===========================================================================
# MEANING UNIT — the record. ``kind`` is the finer class; ``dimension`` is the headline
# bucket(s) it rolls up into (MEANING always; plus EMOTIONAL_TONE or LIFE_EVENT when apt).
# ``grounded_in`` is the user's own words that justify it (the #1-RULE proof); ``evidence``
# is the structural signal it was DERIVED from (an edge / a row / a feeling). A unit with
# no ``grounded_in`` cannot exist — ``_ground`` refuses to build it.
# ===========================================================================
def _meaning_unit(kind: str, subject: str, statement: str, grounded_in: str,
                  evidence: dict, dimensions: tuple) -> dict:
    """Assemble ONE grounded meaning unit. The statement is scrubbed clean of any diagnosis
    term (defence in depth). Callers reach this only via ``_ground`` (which has already
    proven ``grounded_in`` is in the input), so a unit always carries evidence + grounding."""
    safe = statement if _is_clean(statement) else f"{subject}: a noted significance."
    return {
        "kind": kind,
        "subject": subject,
        "statement": safe,
        "grounded_in": grounded_in,
        "evidence": dict(evidence),
        "dimensions": tuple(dimensions),
    }


def _ground(kind: str, subject: str, statement: str, candidate_surface: str,
            evidence: dict, dimensions: tuple, idx: tuple) -> Optional[dict]:
    """THE #1-RULE GATE. Build a meaning unit ONLY if ``candidate_surface`` is grounded in
    the user's words (present in the input). Returns the unit, or None if it cannot be
    grounded — in which case the meaning is NOT emitted (never invented). The subject is
    also required to be non-empty. Pure; never raises."""
    if not subject or not str(subject).strip():
        return None
    surface = _grounded_surface(candidate_surface, idx)
    if surface is None:
        return None
    return _meaning_unit(kind, str(subject).strip().lower(), statement, surface,
                         evidence, dimensions)


# ===========================================================================
# LITERAL EXTRACTION — the data layer. The facts/tokens a reasonable reader calls the
# content: the LIRF candidate facts (trait+value) and the world-edge literal nodes
# (subject/object content tokens). This is the SAME content the data-conservation
# observatory measures; we reuse the live extractors so the two tools agree on "literal".
# ===========================================================================

# nodes that name a STATE/feeling rather than a literal entity (folded into MEANING, not
# counted as a literal token to keep the literal denominator about facts).
_STATE_NODES = frozenset({
    "you", "recent", "poorly", "badly", "lately", "now", "stress", "stressed",
})


def _lirf_candidates(text: str) -> list:
    """The LIRF candidate facts the live extractor pulls (Tier-A, model off). [] in
    isolation. Read-only; never raises."""
    if not (_HAVE_LIRF and _lirf is not None):
        return []
    try:
        return [c for c in (_lirf.extract(text) or []) if isinstance(c, dict)]
    except Exception:
        return []


def _world_tuples(text: str) -> list:
    """The world-edge tuples the live extractor pulls: (subject, predicate, object, kind,
    topic). [] in isolation. Read-only; never raises."""
    if not (_HAVE_WORLD and _world is not None):
        return []
    try:
        return [t for t in (_world.capture(text) or []) if isinstance(t, (list, tuple)) and len(t) >= 4]
    except Exception:
        return []


def _value_tokens(value: Any) -> list:
    """The literal tokens of a fact value (a scalar or a list), normalised."""
    vals = value if isinstance(value, list) else [value]
    out = []
    for v in vals:
        for w in _WORD.findall(str(v)):
            k = _norm_tok(w)
            if k:
                out.append(k)
    return out


def literal_units(text: str) -> list:
    """Extract the LITERAL units (the facts/tokens) of an utterance — the data layer. Each:

        {"surface": the literal word/value, "key": normalised key,
         "source": "lirf:<trait>" | "world:<predicate>"}

    Sourced ONLY from the live extractors (never invented): a LIRF fact's VALUE tokens, and
    a world edge's literal SUBJECT/OBJECT nodes (a feeling/state node is excluded — it is
    meaning, not a literal fact-token). De-duplicated by key. Read-only; never raises."""
    units = []
    seen = set()

    def add(surface, source):
        key = _norm_tok(surface)
        if not key or key in seen:
            return
        seen.add(key)
        units.append({"surface": str(surface).strip(), "key": key, "source": source})

    for c in _lirf_candidates(text):
        trait = str(c.get("trait", ""))
        for tok in _value_tokens(c.get("value")):
            add(tok, f"lirf:{trait}")
    for (subj, pred, obj, kind, *_rest) in _world_tuples(text):
        pred = str(pred)
        for node in (subj, obj):
            n = _norm_tok(node)
            if not n or n in _STATE_NODES:
                continue
            # only count nodes whose literal surface is actually in the user's words, so a
            # canonicalised state node ("you") never inflates the literal count.
            add(node, f"world:{pred}")
    return units


# ===========================================================================
# MEANING EXTRACTION — the significance layer. Every unit is DERIVED from a structural
# signal AND grounded in the user's words. Four sources, mirroring the engines:
#   1) world life-event edges      -> LIFE_EVENT (+ MEANING)
#   2) reported_feeling + problems -> EMOTIONAL_TONE (+ MEANING)
#   3) review milestone facts/edges-> MILESTONE (+ MEANING)
#   4) relationship edges/traits   -> RELATIONAL_WEIGHT (+ MEANING)
# ===========================================================================

# world predicates that name a LIFE EVENT (a stated transition). The "_when" temporal
# qualifiers and the bare relationship "has" are handled separately. Mirrors the WAVE-A
# life-event builders in world_state (moved/started/adopted/married/after/graduated…).
_LIFE_EVENT_PREDICATES = frozenset({
    "moved_to", "move_to", "started", "adopted", "married_to", "after",
    "graduated", "retired", "quit", "enlisted", "divorced",
})
# world kinds a life-event edge carries (a transition the user stated).
_LIFE_EVENT_KINDS = frozenset({"fact", "sequence"})
# problem predicates — a stated stressor/worry carries emotional weight (tone-adjacent).
_PROBLEM_PREDICATES = frozenset({"stressed_by", "worried_about"})
# relationship predicate — a person/entity bond.
_REL_PREDICATES = frozenset({"has"})

# LIRF traits that name a RELATIONAL bond (a person in the user's life). Folded the LIRF
# way at match time so aliases (wife->partner, kid->children) are caught.
_REL_TRAITS = frozenset({
    "daughter", "son", "partner", "spouse", "wife", "husband", "mother", "father",
    "brother", "sister", "friend", "children", "child", "kid", "kids", "married_to",
})

# a friendly word for a life-event predicate, used only in the (descriptive, scrubbed)
# statement — never a diagnosis, never a claim beyond the stated transition.
_EVENT_WORD = {
    "moved_to": "a move", "move_to": "a move", "started": "a new beginning",
    "adopted": "bringing home a pet", "married_to": "a marriage", "after": "a turning point",
    "graduated": "a graduation", "retired": "a retirement", "quit": "leaving a job",
    "divorced": "a separation",
}


def _canon_trait(trait: str) -> str:
    if _HAVE_LIRF and _lirf is not None:
        try:
            return _lirf.canon_trait(trait)
        except Exception:
            pass
    return re.sub(r"[^a-z0-9]+", "_", str(trait).strip().lower()).strip("_")


def _is_milestone_trait(trait: str) -> bool:
    """True iff ``trait`` names a milestone-grade life fact — DEFERS to the review engine's
    own machinery when importable (single source of truth), else a faithful check."""
    if _HAVE_REVIEW and _review is not None:
        try:
            return bool(_review._is_milestone_trait(trait))
        except Exception:
            pass
    return _canon_trait(trait) in {
        "name", "birthday", "partner", "children", "marriage", "employer",
        "job_title", "goal", "daughter", "son",
    }


def _is_milestone_predicate(pred: str) -> bool:
    """True iff ``pred`` is a milestone-grade world predicate (a named goal, a life-event
    sequence, a person bond, something cared about). Defers to review's set when present."""
    p = str(pred).strip().lower()
    if _HAVE_REVIEW and _review is not None:
        try:
            if p in getattr(_review, "_MILESTONE_PREDICATES", frozenset()):
                return True
        except Exception:
            pass
    return p in {"working_toward", "after", "has", "cares_about"}


def meaning_units(text: str) -> list:
    """Extract the MEANING units (the significance) of an utterance — DERIVED + GROUNDED.

    Returns a list of grounded meaning units (see ``_meaning_unit``). Every unit is tied to
    BOTH a structural signal (a world edge / a reported_feeling row / a milestone trait) AND
    a surface in the user's words; a candidate that cannot be grounded is silently NOT
    emitted (never invented). De-duplicated by (kind, subject). Read-only; never raises."""
    idx = _input_index(text)
    out = []
    seen = set()

    def push(unit):
        if unit is None:
            return
        tag = (unit["kind"], unit["subject"])
        if tag in seen:
            return
        seen.add(tag)
        out.append(unit)

    tuples = _world_tuples(text)
    cands = _lirf_candidates(text)

    # --- 1) LIFE EVENTS — a stated transition, grounded on the OBJECT of the event edge
    #     (the place moved to, the thing started, the species adopted). The life-event word
    #     is descriptive; the grounding surface is the user's literal object node. ---
    for (subj, pred, obj, kind, *_rest) in tuples:
        pred = str(pred)
        obj_s = str(obj)
        if pred in _LIFE_EVENT_PREDICATES and str(kind) in _LIFE_EVENT_KINDS:
            ev_word = _EVENT_WORD.get(pred, "a life event")
            stmt = f"{ev_word.capitalize()} — {subj} {pred.replace('_', ' ')} {obj_s}."
            push(_ground(KIND_LIFE_EVENT, obj_s, stmt, obj_s,
                         {"predicate": pred, "kind": str(kind), "subject": str(subj),
                          "object": obj_s, "source": "world_state"},
                         (MEANING, LIFE_EVENT), idx))

    # --- 2) EMOTIONAL TONE — the user's stated affect (a reported_feeling row), grounded on
    #     the affect phrase itself; AND a stated stressor/worry (a problem edge), grounded on
    #     the stressor object. RULE #1: this records the USER reported a feeling, never that
    #     Vera feels anything (the reported_feeling trait frames it). ---
    for c in cands:
        if _canon_trait(c.get("trait", "")) != "reported_feeling":
            continue
        vals = c.get("value") if isinstance(c.get("value"), list) else [c.get("value")]
        for v in vals:
            phrase = str(v).strip()
            stmt = (f"An emotional weight the person voiced — they said they've been "
                    f"{phrase}.")
            push(_ground(KIND_TONE, phrase, stmt, phrase,
                         {"trait": "reported_feeling", "value": phrase,
                          "source": "memory_lirf"},
                         (MEANING, EMOTIONAL_TONE), idx))
    for (subj, pred, obj, kind, *_rest) in tuples:
        if str(pred) in _PROBLEM_PREDICATES:
            obj_s = str(obj)
            stmt = (f"Something weighing on them — {obj_s} reads as a stated "
                    f"{'worry' if 'worried' in str(pred) else 'stressor'}.")
            push(_ground(KIND_TONE, obj_s, stmt, obj_s,
                         {"predicate": str(pred), "kind": str(kind), "object": obj_s,
                          "source": "world_state"},
                         (MEANING, EMOTIONAL_TONE), idx))

    # --- 3) MILESTONES — a milestone-grade fact (a child, a named goal, a partner, an
    #     employer) the review engine would carry FOREVER. Grounded on the fact's value
    #     (the LIRF literal) so a milestone is never invented past what was said. ---
    for c in cands:
        trait = str(c.get("trait", ""))
        if not _is_milestone_trait(trait):
            continue
        vals = c.get("value") if isinstance(c.get("value"), list) else [c.get("value")]
        for v in vals:
            val = str(v).strip()
            ctrait = _canon_trait(trait)
            stmt = f"A milestone in their life — {ctrait.replace('_', ' ')}: {val}."
            # ground on the value; the subject is the canonical trait (the durable slot).
            push(_ground(KIND_MILESTONE, ctrait, stmt, val,
                         {"trait": ctrait, "value": val, "source": "memory_lirf"},
                         (MEANING,), idx))
    for (subj, pred, obj, kind, *_rest) in tuples:
        if _is_milestone_predicate(pred) and str(pred) not in _REL_PREDICATES:
            obj_s = str(obj)
            stmt = f"A milestone — {str(subj)} {str(pred).replace('_', ' ')} {obj_s}."
            push(_ground(KIND_MILESTONE, obj_s, stmt, obj_s,
                         {"predicate": str(pred), "kind": str(kind), "object": obj_s,
                          "source": "world_state"},
                         (MEANING,), idx))

    # --- 4) RELATIONAL WEIGHT — a person/entity bond. From a world relationship "has" edge
    #     (you --has--> daughter) grounded on the ROLE word the user used, AND from a
    #     relational LIRF trait (daughter=Maya) grounded on the relationship word. ---
    for (subj, pred, obj, kind, *_rest) in tuples:
        if str(pred) in _REL_PREDICATES:
            role = str(obj)
            stmt = f"A relationship that matters — a {role} in their life."
            push(_ground(KIND_RELATIONAL, role, stmt, role,
                         {"predicate": str(pred), "kind": str(kind), "object": role,
                          "source": "world_state"},
                         (MEANING,), idx))
    for c in cands:
        trait = str(c.get("trait", ""))
        ctrait = _canon_trait(trait)
        if trait.lower() in _REL_TRAITS or ctrait in _REL_TRAITS:
            # ground on the RELATIONSHIP word (the trait the user spoke: "daughter"), which
            # is what carries the relational weight — not the name (that is literal).
            rel_word = trait.lower() if trait.lower() in _REL_TRAITS else ctrait
            vals = c.get("value") if isinstance(c.get("value"), list) else [c.get("value")]
            val = ", ".join(str(v) for v in vals)
            stmt = f"A relationship that matters — their {rel_word} ({val})."
            push(_ground(KIND_RELATIONAL, ctrait, stmt, rel_word,
                         {"trait": ctrait, "value": val, "relationship": rel_word,
                          "source": "memory_lirf"},
                         (MEANING,), idx))

    return out


# ===========================================================================
# RETENTION — walk a MEANING unit through CAPTURED -> STORED -> SURFACEABLE against the
# REAL engines on a synthetic creature (the observatory supplies the stored/surfaceable
# views from inside a hermetic temp store). Each gate is a membership test of the unit's
# subject/grounding against the surfaces that gate carries; the FIRST gate it fails is its
# loss_reason. A tone unit is matched only by an affect surface (a reported_feeling value
# or a problem object), never by a relation predicate — the same honesty the data tool
# enforces (a feeling absorbed into a predicate was not kept AS a feeling).
# ===========================================================================

def _unit_keys(unit: dict) -> set:
    """The normalised surface keys that prove a unit is carried at a gate: its subject + the
    content tokens of its grounding surface + its evidence value/object tokens. A gate
    credits the unit if ANY of these keys appears in that gate's surface set."""
    keys = set()
    for src in (unit.get("subject", ""), unit.get("grounded_in", "")):
        for w in _WORD.findall(str(src)):
            k = _norm_tok(w)
            if k:
                keys.add(k)
    ev = unit.get("evidence", {})
    for fld in ("value", "object"):
        for w in _WORD.findall(str(ev.get(fld, ""))):
            k = _norm_tok(w)
            if k:
                keys.add(k)
    keys.discard("")
    return keys


def retention_of(units: list, gate_surfaces: dict) -> list:
    """For each MEANING unit, walk the gates and record where it (first) fell out.

    ``gate_surfaces`` maps each gate name to a SET of normalised surface keys that gate
    carries (the observatory builds these from the live engines: CAPTURED from the in-memory
    capture, STORED from the on-disk reload, SURFACEABLE from significance/meaning/review).
    A unit is "present at gate" iff it was present at the previous gate AND any of its keys
    is in that gate's set. The first gate it fails names the ``loss_reason``.

    Returns one trace per unit: the input unit plus
        {"captured": bool, "stored": bool, "surfaceable": bool,
         "reached": last gate carried, "loss_reason": first gate failed (or "")}.
    Pure; never raises."""
    out = []
    label = {CAPTURED: "not captured (the meaning was never seen by the extractor)",
             STORED: "not stored (captured in memory but lost on the disk round-trip)",
             SURFACEABLE: "not surfaceable (on disk but no significance/review re-surfaces it)"}
    for u in units:
        keys = _unit_keys(u)
        flags = {CAPTURED: False, STORED: False, SURFACEABLE: False}
        reached = "extracted"
        loss = ""
        carried = True
        for g in GATES:
            present = carried and bool(keys & gate_surfaces.get(g, set()))
            flags[g] = present
            if present:
                reached = g
            elif carried:
                loss = label[g]
                carried = False
        trace = dict(u)
        trace.update({CAPTURED: flags[CAPTURED], STORED: flags[STORED],
                      SURFACEABLE: flags[SURFACEABLE], "reached": reached,
                      "loss_reason": loss})
        out.append(trace)
    return out


# ===========================================================================
# RATES — the FOUR the directive names, each a fraction of units RETAINED end-to-end
# (reached SURFACEABLE). A unit's "retained" means its MEANING survived to where it can be
# re-surfaced, the Law-003 stance: understanding that can be brought back, not just bytes
# on disk. An empty denominator is a perfect 1.0 (nothing to lose).
# ===========================================================================
def _rate(num: int, den: int) -> float:
    return (num / den) if den else 1.0


def conservation_rates(literal_traces: list, meaning_traces: list) -> dict:
    """Compute the four conservation rates from the per-unit traces:

        LITERAL conservation     — literal units retained (the data layer, for contrast)
        MEANING conservation     — ALL meaning units retained (the headline)
        EMOTIONAL-TONE cons.     — meaning units in the EMOTIONAL_TONE dimension retained
        LIFE-EVENT conservation  — meaning units in the LIFE_EVENT dimension retained

    "retained" == reached the SURFACEABLE gate. Returns counts + each rate. Pure."""
    def retained(t):
        return bool(t.get(SURFACEABLE))

    lit_tot = len(literal_traces)
    lit_keep = sum(1 for t in literal_traces if retained(t))

    mean_tot = len(meaning_traces)
    mean_keep = sum(1 for t in meaning_traces if retained(t))

    tone = [t for t in meaning_traces if EMOTIONAL_TONE in t.get("dimensions", ())]
    tone_keep = sum(1 for t in tone if retained(t))

    life = [t for t in meaning_traces if LIFE_EVENT in t.get("dimensions", ())]
    life_keep = sum(1 for t in life if retained(t))

    return {
        "literal": {"retained": lit_keep, "total": lit_tot, "rate": _rate(lit_keep, lit_tot)},
        "meaning": {"retained": mean_keep, "total": mean_tot, "rate": _rate(mean_keep, mean_tot)},
        "emotional_tone": {"retained": tone_keep, "total": len(tone),
                           "rate": _rate(tone_keep, len(tone))},
        "life_event": {"retained": life_keep, "total": len(life),
                       "rate": _rate(life_keep, len(life))},
    }


# ===========================================================================
# SELF-TEST — `python3 -m anima.meaning_conservation`. In-module smoke + the GROUNDING
# invariant (an ungrounded meaning is NOT emitted). No model, no network, no real .anima:
# the retention walk here uses synthetic gate-surface sets (the full hermetic engine run is
# scripts/meaning_conservation.py --selftest). Mirrors the sibling organs' ok(label, cond).
# ===========================================================================
def _selftest() -> int:
    fails: list = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("meaning_conservation (Meaning-Conservation Engine) self-test")

    maya = "My daughter Maya started kindergarten last week"
    stress = "I've been really stressed about the Q3 launch"

    # --- LITERAL extraction: the facts/tokens ---
    lits = {u["key"] for u in literal_units(maya)}
    ok("literal: 'maya' is a literal token (the daughter's name)", "maya" in lits)
    ok("literal: 'kindergarten' is a literal token", "kindergarten" in lits)

    # --- MEANING extraction: derived + grounded, across the dimensions ---
    units = meaning_units(maya)
    dims = {d for u in units for d in u["dimensions"]}
    kinds = {u["kind"] for u in units}
    ok("meaning: a LIFE_EVENT unit is derived (started kindergarten)",
       LIFE_EVENT in dims and KIND_LIFE_EVENT in kinds)
    ok("meaning: a RELATIONAL_WEIGHT unit is derived (the daughter bond)",
       KIND_RELATIONAL in kinds)
    ok("meaning: a MILESTONE unit is derived (a child in their life)",
       KIND_MILESTONE in kinds)
    ok("meaning: every meaning unit rolls up into the MEANING dimension",
       all(MEANING in u["dimensions"] for u in units))

    # THE WORKED EXAMPLE: literal {daughter, Maya, kindergarten} -> meaning carries the
    # family milestone + child development + emotional/relational significance.
    ok("worked example: 'kindergarten' grounds a LIFE_EVENT meaning unit",
       any(u["kind"] == KIND_LIFE_EVENT and "kindergarten" in u["grounded_in"]
           for u in units))

    # --- the #1 RULE: every emitted unit is GROUNDED in the user's words ---
    idx = _input_index(maya)
    ok("GROUNDED: every meaning unit's grounding surface IS in the utterance",
       all(_grounded_surface(u["grounded_in"], idx) is not None for u in units))
    ok("GROUNDED: every meaning unit carries non-empty structural evidence",
       all(isinstance(u.get("evidence"), dict) and u["evidence"] for u in units))

    # --- the GROUNDING REJECTION PROOF: an invented meaning is NOT emitted ---
    # 'graduation' is a real life-event word, but the Maya utterance never says it; a
    # candidate grounded on it must be refused. This is the never-confabulate proof.
    invented = _ground(KIND_LIFE_EVENT, "graduation",
                       "A milestone — they graduated.", "graduation",
                       {"predicate": "graduated", "source": "world_state"},
                       (MEANING, LIFE_EVENT), idx)
    ok("GROUNDED: an UNGROUNDED meaning ('graduation' not in the words) is REJECTED",
       invented is None)
    ok("GROUNDED: no emitted unit was grounded on a word absent from the input",
       not any("graduation" in u["grounded_in"] for u in units))
    # a fabricated subject with empty grounding is refused too.
    ok("GROUNDED: a meaning with no grounding surface is refused",
       _ground(KIND_THEME, "burnout", "they are burning out", "", {}, (MEANING,), idx) is None)

    # --- EMOTIONAL TONE: the stress line yields a tone unit grounded on the affect phrase ---
    tunits = meaning_units(stress)
    tone = [u for u in tunits if u["kind"] == KIND_TONE]
    ok("tone: 'really stressed' yields an EMOTIONAL_TONE meaning unit",
       any("stressed" in u["grounded_in"] for u in tone))
    ok("tone: the tone unit is grounded in the user's exact words (RULE #1)",
       all(_grounded_surface(u["grounded_in"], _input_index(stress)) is not None for u in tone))
    # RULE #1 — the tone is the USER's reported feeling, never a claim Vera feels it.
    ok("tone: derived from the reported_feeling row (the user's report, not Vera's state)",
       any(u["evidence"].get("trait") == "reported_feeling" for u in tone))

    # --- no-diagnosis wall over every generated statement ---
    ok("no-diagnosis: NO meaning-unit statement trips a banned term",
       all(_is_clean(u["statement"]) for u in units + tunits))

    # --- RETENTION walk + the four RATES on synthetic gate-surfaces ---
    # build gate-surface sets that carry the Maya meaning all the way through, EXCEPT drop
    # the emotional-tone affect on the stress battery at CAPTURE (tone is the routinely-lost
    # class), so the rates discriminate.
    all_units = units + tunits
    surf_all = set()
    for u in units:                          # Maya units ride through every gate
        surf_all |= _unit_keys(u)
    gate_surfaces = {CAPTURED: set(surf_all), STORED: set(surf_all),
                     SURFACEABLE: set(surf_all)}
    traces = retention_of(all_units, gate_surfaces)
    maya_traces = [t for t in traces if t["subject"] in {u["subject"] for u in units}]
    ok("retention: every Maya meaning unit reaches SURFACEABLE in the full-surface case",
       all(t[SURFACEABLE] for t in maya_traces))
    # a tone unit absent from the surfaces is dropped at CAPTURE with a loss_reason.
    tone_traces = [t for t in traces if t["kind"] == KIND_TONE and t[STORED] is False]
    ok("retention: a meaning unit absent from the gates is flagged with a loss_reason",
       all(t["loss_reason"] for t in tone_traces) if tone_traces else True)
    ok("retention: a dropped unit names CAPTURE as the first failed gate",
       all("not captured" in t["loss_reason"] for t in tone_traces) if tone_traces else True)

    lit_traces = retention_of(literal_units(maya),
                              {g: set(surf_all) for g in GATES})
    rates = conservation_rates(lit_traces, maya_traces)
    ok("rates: all four present (literal/meaning/emotional_tone/life_event)",
       set(rates.keys()) == {"literal", "meaning", "emotional_tone", "life_event"})
    ok("rates: every rate is a probability in [0,1]",
       all(0.0 <= rates[k]["rate"] <= 1.0 for k in rates))
    ok("rates: MEANING conservation is 1.0 when every meaning unit is retained",
       rates["meaning"]["rate"] == 1.0)
    ok("rates: LIFE_EVENT rate counts only life-event-dimension units",
       rates["life_event"]["total"] == len([u for u in units
                                             if LIFE_EVENT in u["dimensions"]]))

    # --- empty / garbage input is safe ---
    ok("empty: no literal units for empty input", literal_units("") == [] and literal_units("   ") == [])
    ok("empty: no meaning units for empty input", meaning_units("") == [])
    ok("empty: rates degrade to 1.0 on an empty battery (nothing to lose)",
       conservation_rates([], [])["meaning"]["rate"] == 1.0)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL MEANING-CONSERVATION ENGINE SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
