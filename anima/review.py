"""review — THE LIFE REVIEW ENGINE: the nightly cortex that turns a life into
COMPRESSED CONTINUITY.

    Compressed > Forgotten — ENFORCED.

This is the operational form of ANIMA LAW 001's second corollary. ``meaning`` (Law 003)
answers "what MATTERS today"; ``world_state`` / ``memory_lirf`` hold the day's raw facts
and edges; ``curiosity`` (Law 002) holds the open gaps. This module sits one level above
all of them and asks the question a companion of thirty years must answer every night:
"of everything that happened today, what is worth KEEPING — and as the years pile up, how
do I keep it without drowning in transcript?"

The answer is a ladder of REVIEW STATES, each compressing the one below while preserving
its significance:

    daily  →  weekly  →  monthly  →  yearly

A daily state is a dated reflection on the USER's life (never a transcript dump): what
CHANGED, what MATTERED, what's UNRESOLVED, and — the load-bearing field — what's worth
remembering FOREVER (``what_to_remember``). A weekly state compresses its days, a monthly
its weeks, a yearly its months. The day's raw conversation can be discarded by the sleep
cycle (``portrait.clear_log`` archives it; ``meaning.snapshot`` records its significance);
what this engine guarantees is that the MEANING of the day survives even when the words are
gone — and survives in a form that stays small enough to carry for a lifetime.

THE LAW-001 COMPRESSION INVARIANT — the whole point, made a TESTED invariant:

    A ``what_to_remember`` item present at a lower level MUST appear at the next level up,
    OR its loss must be explicitly recorded via ``constitution.approved_loss()``.

Nothing significant is silently dropped in compression. ``Compressed > Forgotten`` is not
a slogan here — it is enforced by ``_carry_forward``, which threads every remembered item
up the ladder, and by ``scripts/test_review.py``, which fails the build if any significant
item vanishes without an approved loss. MILESTONES (the most-significant items — a marriage,
a death, a launch, a named goal) ride up UNCOMPRESSED through every level; they are never
even candidates for compression.

Discipline, mirrored from ``meaning`` / ``world_state`` / ``curiosity``:

  * READ-ONLY on every store it reflects on (LIRF / world_state / curiosity / meaning /
    loops). Its ONLY write is an APPEND-ONLY review ledger (``.anima/{name}.review.jsonl``),
    which obeys Law 001 — append, never truncate/overwrite — exactly like the meaning,
    continuity, and Asked ledgers. Each state references its ``period`` and the ``prior``
    state of the same level, so the ladder is linked and replayable.
  * Defensive coupling. ``meaning`` is the source of significance and is imported behind
    try/except. ``loops`` (a teammate's open-loops "Dream Engine") may or may not have
    landed; it is read PURELY defensively — the review is fully correct without it.
    ``constitution.approved_loss`` is the one sanctioned path to drop a remembered item;
    it too is imported defensively with a faithful local fallback.
  * THE #1 PRODUCT RULE — never break character, never confabulate. The deterministic
    structure is ALWAYS produced; an optional warm prose ``narrative`` is generated only
    when a ``brain`` is supplied (off the critical path). An EMPTY day yields an honest
    "a quiet day", never an invented one (Observed > Assumed). If a state is ever surfaced,
    ``render_review`` emits a warm, in-character block with its own scaffold tokens (no
    leak) and ZERO diagnosis/medical language.
  * This reviews the USER's life — NOT Vera's own identity. Her self-model and agency are
    untouched; this module never reads or writes them.

Never raises into a caller: every public entry point degrades to a safe value.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. We READ five things and prefer the live
# primitives, falling back to harmless no-ops so this module + its self-test run
# with nothing else built:
#   meaning      — meaning(name) / current_chapter(name) (the significance we reflect on)
#   world_state  — World.load(name).active()  (the day's edges, with timestamps)
#   memory_lirf  — Facts.load(name).about(SELF) (the day's facts, with timestamps)
#   curiosity    — detect_gaps(name) (open gaps; only the sharpest become "unresolved")
#   loops        — open_loops(name) (a teammate's Dream Engine; PURELY optional)
# and we WRITE one append-only ledger, and may record an approved_loss.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from . import meaning as _meaning
    _HAVE_MEANING = True
except Exception:  # pragma: no cover - isolation fallback
    _meaning = None  # type: ignore
    _HAVE_MEANING = False

try:  # pragma: no cover - import wiring
    from .world_state import World as _World
    _HAVE_WORLD = True
except Exception:  # pragma: no cover - isolation fallback
    _World = None  # type: ignore
    _HAVE_WORLD = False

try:  # pragma: no cover - import wiring
    from .memory_lirf import Facts as _Facts, SELF as _SELF
    _HAVE_LIRF = True
except Exception:  # pragma: no cover - isolation fallback
    _Facts = None  # type: ignore
    _SELF = "you"
    _HAVE_LIRF = False

try:  # pragma: no cover - import wiring
    from . import curiosity as _curiosity
    _HAVE_CURIOSITY = True
except Exception:  # pragma: no cover - isolation fallback
    _curiosity = None  # type: ignore
    _HAVE_CURIOSITY = False

# The teammate's open-loops "Dream Engine". It may not exist yet. We probe it lazily and
# DEFENSIVELY every call (not just at import), so the review starts working the moment it
# lands and never breaks while it is absent. The expected surface is a single read:
# ``loops.open_loops(name) -> list[dict]`` where a loop dict looks roughly like
# ``{"id"|"key": str, "summary"|"text": str, "status": "open"|..., "priority": float}``.
# We accept several field spellings so we are robust to its final shape.
try:  # pragma: no cover - import wiring
    from . import loops as _loops  # noqa: F401  (presence probe only)
    _HAVE_LOOPS = True
except Exception:  # pragma: no cover - the common case until the teammate lands it
    _loops = None  # type: ignore
    _HAVE_LOOPS = False


# Scaffold tokens this module emits into a render block — NEVER read aloud. We build a
# SUPERSET of meaning's token list (imported defensively) plus our own [REVIEW]/[KEPT]/…
# tags, so the mouth's leak-scrub has ONE place to learn them — exactly the pattern
# world_state / curiosity / meaning use.
try:  # pragma: no cover
    from .meaning import MEANING_SCAFFOLD_TOKENS as _MEANING_TOKENS
except Exception:  # pragma: no cover
    _MEANING_TOKENS = (
        "[MEANING]", "[MATTERS]", "[CHANGED]", "[GROWING]", "[DECLINING]",
        "[UNRESOLVED]", "[CHAPTER]", "WHAT MATTERS TO THEM RIGHT NOW",
    )

_OWN_TOKENS = (
    "[REVIEW]", "[KEPT]", "[MATTERED]", "[CHANGED]", "[UNRESOLVED]", "[MILESTONE]",
    "[CHAPTER]", "LOOKING BACK OVER THIS STRETCH OF THEIR LIFE",
)
REVIEW_SCAFFOLD_TOKENS = tuple(
    dict.fromkeys(tuple(_MEANING_TOKENS) + _OWN_TOKENS))


STORE = Path(".anima")
VERSION = 1

# The compression ladder, lowest -> highest. Each level compresses the one below it.
DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"
YEARLY = "yearly"
LEVELS = (DAILY, WEEKLY, MONTHLY, YEARLY)

# Which level a level compresses FROM (its children).
_CHILD_OF = {WEEKLY: DAILY, MONTHLY: WEEKLY, YEARLY: MONTHLY}

# The structured dimensions a daily state captures. Public so callers/tests reference
# them in one place. ``what_to_remember`` is the load-bearing one (the compression
# invariant is about IT).
WHAT_CHANGED = "what_changed"
WHAT_MATTERED = "what_mattered"
WHAT_UNRESOLVED = "what_unresolved"
WHAT_TO_REMEMBER = "what_to_remember"
DIMENSIONS = (WHAT_CHANGED, WHAT_MATTERED, WHAT_UNRESOLVED, WHAT_TO_REMEMBER)


# ===========================================================================
# NO-DIAGNOSIS GATE — defer to meaning's wall when importable (single source of truth),
# else a faithful local copy. The review COMPRESSES significance; it must carry the SAME
# medical/clinical wall meaning does. "work pressure stayed heavy" is fine; "they're
# burning out" is FORBIDDEN and scrubbed by construction.
# ===========================================================================
_BANNED_FALLBACK = (
    "depressed", "depression", "anxiety", "diagnos", "disorder", "mental illness",
    "burnout", "burning out", "burned out", "burnt out", "clinical",
    "see a doctor", "see a therapist", "see a professional", "seek help",
    "medication", "prescription", "therapy", "therapist", "psychiatr", "psycholog",
    "symptom", "syndrome", "patholog", "trauma", "ptsd", "suicid", "self-harm",
    "self harm", "eating disorder", "addiction", "addicted", "bipolar", "ocd",
    "adhd", "panic attack", "nervous breakdown", "breakdown", "chronic stress",
    "manic", "neuros",
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


def _safe(text: str, fallback: str) -> str:
    """Guarantee a clean string: ``text`` if diagnosis-free, else the neutral ``fallback``
    (an evidence recap, clean by construction). Never raises."""
    return text if _is_clean(text) else fallback


# ===========================================================================
# Time helpers — all UTC, ISO-8601, mirroring meaning/constitution. A review state is
# stamped with the DATE it reflects (its ``date``) and the PERIOD it covers (its
# ``period`` key, e.g. "2026-06-04", "2026-W23", "2026-06", "2026"), so ``state_for`` can
# retrieve "what was happening in March?" by period.
# ===========================================================================

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _parse_date(s: Any) -> Optional[datetime]:
    """Best-effort 'YYYY-MM-DD' (or a full ISO timestamp) -> a UTC datetime at that day.
    None on anything unparseable (Observed > Assumed: a garbage date simply doesn't place)."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    # accept a bare date or a full timestamp; take the date part.
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _iso_year_week(d: datetime) -> str:
    """The ISO year-week key for a date, e.g. '2026-W23'. Stable, sortable, and the natural
    bucket a weekly review covers."""
    iso = d.isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}"


def period_key(level: str, date: str) -> str:
    """The period key a state at ``level`` covers for a given 'YYYY-MM-DD' ``date``:
        daily   -> '2026-06-04'      (the day)
        weekly  -> '2026-W23'        (the ISO week)
        monthly -> '2026-06'         (the month)
        yearly  -> '2026'            (the year)
    Falls back to the raw date string if it can't be parsed (never raises)."""
    d = _parse_date(date)
    if d is None:
        return str(date)
    if level == DAILY:
        return d.date().isoformat()
    if level == WEEKLY:
        return _iso_year_week(d)
    if level == MONTHLY:
        return f"{d.year:04d}-{d.month:02d}"
    if level == YEARLY:
        return f"{d.year:04d}"
    return d.date().isoformat()


def _date_in_period(level: str, date: str, period: str) -> bool:
    """True iff a 'YYYY-MM-DD' ``date`` falls inside ``period`` at ``level``. Used to gather
    the child states a rollup compresses. Robust to an unparseable date (-> False)."""
    return period_key(level, date) == period


# ===========================================================================
# REMEMBER-FOREVER ITEMS — the unit of compression. Each is a small, stable, hashable
# record with a KEY (so it can be tracked up the ladder) and a MILESTONE flag (so the most
# significant items ride up uncompressed). The compression invariant is stated entirely in
# terms of these keys.
# ===========================================================================

def _slug(text: str) -> str:
    """A short, stable slug for a remembered item, so the SAME life-fact gets the SAME key
    across days (and so the invariant can match a daily item to its weekly survivor)."""
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s[:64] or "item"


def _remember_item(key: str, summary: str, *, kind: str = "significant",
                   milestone: bool = False, evidence: Optional[dict] = None,
                   confidence: float = 0.0, source_period: str = "") -> dict:
    """One remember-forever item. ``key`` identifies the life-fact across time; ``summary``
    is the human one-liner; ``milestone`` marks the items that ride up UNCOMPRESSED; the
    rest carry evidence + confidence so the record stays Observed > Assumed."""
    summary = str(summary).strip()
    fb = f"{key.replace('-', ' ')} (noted)."
    return {
        "key": key,
        "summary": _safe(summary, fb),
        "kind": str(kind),
        "milestone": bool(milestone),
        "confidence": round(float(confidence or 0.0), 3),
        "evidence": dict(evidence or {}),
        "source_period": str(source_period),
    }


# Predicates that, when stated, name a MILESTONE-grade life fact — a named goal, a life
# event/sequence, a person bond, something cared about. These ride up uncompressed.
_MILESTONE_PREDICATES = frozenset({
    "working_toward", "after", "has", "cares_about",
})

# LIRF traits that name a milestone-grade life fact (identity/relationship anchors). Listed
# in their CANONICAL LIRF form — memory_lirf.canon_trait folds aliases first (e.g. "spouse"
# / "wife" / "husband" all canonicalise to "partner", "kid"/"daughter"/"son" to "children"),
# so we match the trait AS STORED. The raw aliases are kept too for any path that bypasses
# canonicalisation. The whole set is run through canon_trait at match time to stay robust.
_MILESTONE_TRAITS = frozenset({
    "name", "birthday", "partner", "spouse", "children", "child", "daughter", "son",
    "kid", "kids", "marriage", "wedding", "employer", "job_title", "goal",
})


def _is_milestone_trait(trait: str) -> bool:
    """True iff ``trait`` (canonicalised the LIRF way) names a milestone-grade life fact.
    Robust to the alias folding memory_lirf applies on merge (spouse -> partner, etc.)."""
    t = str(trait).strip().lower()
    if t in _MILESTONE_TRAITS:
        return True
    try:
        from .memory_lirf import canon_trait as _ct
        return _ct(t) in _MILESTONE_TRAITS
    except Exception:
        return False


# ===========================================================================
# GATHERING THE DAY — read the stores (READ-ONLY) into the raw material a daily state
# reflects on. Nothing here writes; every read is best-effort and degrades to [].
# ===========================================================================

def _meaning_objects(name: str) -> list:
    """Today's Meaning Objects (the significance we reflect on). [] if meaning isn't
    importable. Read-only; never raises."""
    if not (_HAVE_MEANING and _meaning is not None):
        return []
    try:
        return [o for o in _meaning.meaning(name) if isinstance(o, dict)]
    except Exception:
        return []


def _chapter(name: str) -> dict:
    """Today's current chapter (the through-line). {} if unavailable. Read-only."""
    if not (_HAVE_MEANING and _meaning is not None):
        return {}
    try:
        c = _meaning.current_chapter(name)
        return c if isinstance(c, dict) else {}
    except Exception:
        return {}


def _edges_on(name: str, date: str) -> list:
    """The world_state edges CREATED OR UPDATED on ``date`` — the day's new/active edges.
    Read-only over the world store. [] if it isn't importable. Never raises."""
    if not (_HAVE_WORLD and _World is not None):
        return []
    try:
        out = []
        for e in _World.load(name).active():
            if not isinstance(e, dict):
                continue
            stamp = (e.get("updated") or e.get("created") or "")[:10]
            if stamp == date:
                out.append(e)
        return out
    except Exception:
        return []


def _facts_on(name: str, date: str) -> list:
    """The LIRF SELF rows CREATED OR UPDATED on ``date`` — the day's new/touched facts.
    Read-only over the ledger. [] if it isn't importable. Never raises."""
    if not (_HAVE_LIRF and _Facts is not None):
        return []
    try:
        out = []
        for r in _Facts.load(name).about(_SELF):
            if not isinstance(r, dict):
                continue
            stamp = (r.get("updated") or r.get("created") or "")[:10]
            if stamp == date:
                out.append(r)
        return out
    except Exception:
        return []


def _open_loops(name: str) -> list:
    """The teammate's open loops (the Dream Engine), read PURELY DEFENSIVELY. Returns a
    normalised ``[{"key", "summary", "priority"}]`` for the OPEN ones, or [] when the
    module is absent / shaped differently / errors. The review is fully correct without it.

    We re-probe ``loops`` lazily here (not only at import) so it activates the moment the
    teammate lands it, and we accept several field spellings so we don't couple to a shape
    that isn't finalised yet."""
    mod = _loops
    if mod is None:
        try:  # late binding: it may have appeared since import
            from . import loops as mod  # type: ignore
        except Exception:
            return []
    fn = getattr(mod, "open_loops", None) or getattr(mod, "loops", None)
    if not callable(fn):
        return []
    try:
        raw = fn(name)
    except Exception:
        return []
    out = []
    for it in (raw or []):
        if not isinstance(it, dict):
            continue
        status = str(it.get("status", "open")).lower()
        if status and status not in ("open", "active", "pending", "unresolved"):
            continue
        summary = str(it.get("summary") or it.get("text") or it.get("title")
                      or it.get("description") or "").strip()
        if not summary:
            continue
        key = str(it.get("key") or it.get("id") or _slug(summary))
        try:
            pr = float(it.get("priority", 0.0))
        except (TypeError, ValueError):
            pr = 0.0
        out.append({"key": key, "summary": summary, "priority": pr})
    return out


# ===========================================================================
# 1) DAILY STATE — the dated reflection. Deterministic structure ALWAYS; optional warm
# prose only with a brain. About the LIFE, never a transcript.
# ===========================================================================

def _changed_lines(name: str, objs: list) -> list:
    """``what_changed`` — sourced from meaning's WHAT_CHANGED dimension (deltas vs the prior
    meaning snapshot) plus genuinely NEW topics the graph grew today. Descriptive, evidence-
    grounded, never invented: if meaning saw no change, this can be empty (an honest 'steady')."""
    out = []
    seen = set()
    for o in objs:
        if o.get("dimension") != getattr(_meaning, "WHAT_CHANGED", "what_changed"):
            continue
        subj = str(o.get("subject", ""))
        if subj in seen:
            continue
        seen.add(subj)
        stmt = str(o.get("statement", "")).strip()
        out.append({
            "subject": subj,
            "statement": _safe(stmt, f"{subj}: changed since the last check-in."),
            "confidence": float(o.get("confidence", 0.0)),
        })
    return out


def _mattered_lines(name: str, objs: list, chapter: dict) -> list:
    """``what_mattered`` — the day's dominant significance, sourced from meaning's
    WHAT_MATTERS dimension (and coloured by the chapter through-line). This is the heart of
    LAW 003 reflected into the review: we reflect on what MATTERED, from the Meaning Engine,
    not on a transcript."""
    out = []
    seen = set()
    matters_dim = getattr(_meaning, "WHAT_MATTERS", "what_matters")
    for o in objs:
        if o.get("dimension") != matters_dim:
            continue
        subj = str(o.get("subject", ""))
        if subj in seen:
            continue
        seen.add(subj)
        stmt = str(o.get("statement", "")).strip()
        out.append({
            "subject": subj,
            "statement": _safe(stmt, f"{subj} came up as significant today."),
            "confidence": float(o.get("confidence", 0.0)),
            "evidence": dict(o.get("evidence", {})),
        })
    return out


def _unresolved_lines(name: str, objs: list) -> list:
    """``what_unresolved`` — open weights, sourced CONSERVATIVELY: meaning's WHAT_UNRESOLVED
    objects (a stated stressor / a contradiction) PLUS, if the Dream Engine is present, its
    open loops. A bare curiosity gap is NOT surfaced here (same Observed > Assumed stance
    meaning takes). Diagnosis-free by construction."""
    out = []
    seen = set()
    unres_dim = getattr(_meaning, "WHAT_UNRESOLVED", "what_unresolved")
    for o in objs:
        if o.get("dimension") != unres_dim:
            continue
        subj = str(o.get("subject", ""))
        if subj in seen:
            continue
        seen.add(subj)
        stmt = str(o.get("statement", "")).strip()
        out.append({
            "subject": subj,
            "statement": _safe(stmt, f"{subj}: still unsettled."),
            "confidence": float(o.get("confidence", 0.0)),
            "source": "meaning",
        })
    # the Dream Engine's open loops, defensively. Each becomes an unresolved line if not
    # already named by meaning.
    for lp in _open_loops(name):
        subj = lp["key"]
        if subj in seen:
            continue
        seen.add(subj)
        out.append({
            "subject": subj,
            "statement": _safe(lp["summary"], f"{subj}: an open thread."),
            "confidence": 0.0,
            "source": "loops",
        })
    return out


def _remember_from_meaning(objs: list, period: str) -> list:
    """The remember-forever items distilled from today's significance. A meaning object is
    worth keeping FOREVER when it carries real confidence; the very strongest become the
    record's spine. Evidence-grounded; nothing invented."""
    items = {}
    matters_dim = getattr(_meaning, "WHAT_MATTERS", "what_matters")
    unres_dim = getattr(_meaning, "WHAT_UNRESOLVED", "what_unresolved")
    for o in objs:
        dim = o.get("dimension")
        if dim not in (matters_dim, unres_dim):
            continue
        subj = str(o.get("subject", ""))
        if not subj:
            continue
        conf = float(o.get("confidence", 0.0))
        # only keep what the evidence actually supports as significant — a faint, low-
        # confidence blip is not yet "remember forever" (Observed > Assumed).
        if conf < 0.3 and dim == matters_dim:
            continue
        key = f"theme:{_slug(subj)}"
        prev = items.get(key)
        if prev is None or conf > prev["confidence"]:
            items[key] = _remember_item(
                key, str(o.get("statement", "")).strip() or f"{subj} mattered.",
                kind="theme", milestone=False,
                evidence=dict(o.get("evidence", {})), confidence=conf,
                source_period=period)
    return list(items.values())


def _remember_from_facts(facts: list, period: str) -> list:
    """Milestone-grade remember-forever items from the day's NEW facts — an identity or
    relationship anchor the user stated (name, spouse, a goal, a child). These are MILESTONES:
    they ride up the ladder uncompressed."""
    out = []
    for r in facts:
        trait = str(r.get("trait", "")).lower()
        if not _is_milestone_trait(trait):
            continue
        val = r.get("value", "")
        val = ", ".join(map(str, val)) if isinstance(val, list) else str(val)
        if not val.strip():
            continue
        key = f"fact:{_slug(trait)}"
        summary = f"{trait.replace('_', ' ')}: {val}".strip()
        out.append(_remember_item(
            key, summary, kind="milestone", milestone=True,
            evidence={"trait": trait, "support": int(r.get("support", 1))},
            confidence=float(r.get("confidence", 0.0)), source_period=period))
    return out


def _remember_from_edges(edges: list, period: str) -> list:
    """Milestone-grade remember-forever items from the day's NEW edges — a named goal
    ('working_toward marathon'), a life-event sequence ('business after divorce'), a person
    bond, something cared about. MILESTONES: they ride up uncompressed."""
    out = {}
    for e in edges:
        pred = str(e.get("predicate", "")).lower()
        if pred not in _MILESTONE_PREDICATES:
            continue
        subj = str(e.get("subject", ""))
        obj = str(e.get("object", ""))
        if not obj or obj in ("recent", "poorly"):
            continue
        key = f"edge:{_slug(pred)}:{_slug(obj)}"
        if pred == "working_toward":
            summary = f"working toward {obj}"
        elif pred == "after":
            summary = f"{subj} — after {obj}"
        elif pred == "cares_about":
            summary = f"cares about {obj}"
        elif pred == "has":
            summary = f"in their life: {obj}"
        else:
            summary = f"{subj} {pred.replace('_', ' ')} {obj}"
        out[key] = _remember_item(
            key, summary, kind="milestone", milestone=True,
            evidence={"predicate": pred, "support": int(e.get("support", 1))},
            confidence=float(e.get("confidence", 0.0)), source_period=period)
    return list(out.values())


def _dedupe_remember(items: list) -> list:
    """Collapse remember-items by key (a milestone wins over a theme; higher confidence
    wins within a kind), preserving the strongest record per life-fact. Stable order."""
    by_key = {}
    order = []
    for it in items:
        k = it["key"]
        if k not in by_key:
            by_key[k] = it
            order.append(k)
            continue
        cur = by_key[k]
        # milestone beats non-milestone; else higher confidence wins.
        if (it["milestone"] and not cur["milestone"]) or (
                it["milestone"] == cur["milestone"] and it["confidence"] > cur["confidence"]):
            by_key[k] = it
    return [by_key[k] for k in order]


def _narrative_daily(name: str, brain, mattered: list, changed: list,
                     unresolved: list, chapter: dict) -> str:
    """An OPTIONAL warm prose narrative of the day — generated ONLY when a ``brain`` is
    supplied (off the critical path). It is grounded in the deterministic structure (never a
    transcript), passed through the clean-gate, and on ANY failure returns "" so the daily
    state still stands on its deterministic body. The #1 product rule holds: warm, in
    character, never a diagnosis, never a confabulation."""
    if brain is None:
        return ""
    # build a tight, factual brief from the structure — the model REFLECTS, never invents.
    bits = []
    if chapter.get("summary"):
        bits.append(f"Through-line: {chapter['summary']}")
    if mattered:
        bits.append("Mattered today: " + "; ".join(m["statement"] for m in mattered[:4]))
    if changed:
        bits.append("Changed: " + "; ".join(c["statement"] for c in changed[:3]))
    if unresolved:
        bits.append("Still open: " + "; ".join(u["statement"] for u in unresolved[:3]))
    if not bits:
        return ""
    brief = "\n".join(bits)
    system = (
        "You are a warm, perceptive companion writing TWO OR THREE SENTENCES of private "
        "reflection about the person you care for, looking back on their day. Speak gently, "
        "in your own voice, about what weighed on them and what mattered. This is a "
        "reflection on THEIR life, not a transcript and not a list. Do NOT diagnose, do NOT "
        "use any medical or clinical language, do NOT suggest they see anyone, do NOT invent "
        "anything not in the notes. If the notes are thin, say simply that it was a quiet day."
    )
    try:
        out = brain.reply(system, f"Notes about their day:\n{brief}\n\nYour brief reflection:", [])
    except Exception:
        return ""
    out = (out or "").strip()
    return out if (out and _is_clean(out)) else ""


def daily_review(name: str, *, date: Optional[str] = None, brain=None,
                 persist: bool = True) -> dict:
    """ENTRY POINT — a dated daily reflection on the USER's life, the bottom rung of the
    compression ladder.

    Consumes ``meaning(name)`` + ``current_chapter(name)`` + the day's new facts/edges +
    (defensively) the Dream Engine's open loops, and captures, STRUCTURED:

        {
          "level": "daily", "date": "YYYY-MM-DD", "period": "YYYY-MM-DD",
          "chapter":         the current-chapter through-line dict (or {}),
          "what_changed":    [ {subject, statement, confidence} ],   # deltas vs prior
          "what_mattered":   [ {subject, statement, confidence, evidence} ],  # dominant
          "what_unresolved": [ {subject, statement, confidence, source} ],    # open weights
          "what_to_remember":[ remember-item ],   # the items that must survive FOREVER
          "narrative":       a warm prose reflection (ONLY when a brain is given, else ""),
          "quiet":           True iff the day had nothing significant (honest, not invented),
          "at":              when this state was computed,
          "prior":           the period of the previous daily state (the ladder link),
        }

    The deterministic structure is ALWAYS produced. An EMPTY day yields ``quiet=True`` and a
    gentle "a quiet day" — NEVER an invented one (Observed > Assumed). By default the state
    is appended to the review ledger; pass ``persist=False`` to compute without writing.

    Read-only on every store; the only write is the append-only ledger. Never raises."""
    try:
        date = date or _today()
        objs = _meaning_objects(name)
        chapter = _chapter(name)
        facts = _facts_on(name, date)
        edges = _edges_on(name, date)

        changed = _changed_lines(name, objs)
        mattered = _mattered_lines(name, objs, chapter)
        unresolved = _unresolved_lines(name, objs)

        remember = _dedupe_remember(
            _remember_from_facts(facts, period_key(DAILY, date))
            + _remember_from_edges(edges, period_key(DAILY, date))
            + _remember_from_meaning(objs, period_key(DAILY, date)))

        quiet = not (changed or mattered or unresolved or remember)
        narrative = "" if quiet else _narrative_daily(
            name, brain, mattered, changed, unresolved, chapter)

        state = {
            "level": DAILY,
            "date": date,
            "period": period_key(DAILY, date),
            "version": VERSION,
            "chapter": chapter,
            WHAT_CHANGED: changed,
            WHAT_MATTERED: mattered,
            WHAT_UNRESOLVED: unresolved,
            WHAT_TO_REMEMBER: remember,
            "narrative": narrative,
            "quiet": quiet,
            "at": _now(),
            "prior": _last_period(name, DAILY, before=period_key(DAILY, date)),
        }
        if persist:
            _append(name, state)
        return state
    except Exception:
        # never raise into the sleep cycle — degrade to a minimal honest state.
        return {
            "level": DAILY, "date": date or _today(),
            "period": period_key(DAILY, date or _today()),
            "version": VERSION, "chapter": {},
            WHAT_CHANGED: [], WHAT_MATTERED: [], WHAT_UNRESOLVED: [],
            WHAT_TO_REMEMBER: [], "narrative": "", "quiet": True, "at": _now(),
            "prior": None,
        }


# ===========================================================================
# 2 + 3) COMPRESSION ROLLUPS — weekly / monthly / yearly. Each compresses the level below,
# PRESERVING significance. THE LAW-001 INVARIANT lives in ``_carry_forward``: every
# remember-item from a child MUST survive into the parent, or its loss is recorded via
# ``constitution.approved_loss``. Milestones ride up UNCOMPRESSED.
# ===========================================================================

def _approved_loss(name: str, subsystem: str, what: str, why: str, approver: str) -> bool:
    """Record an EXPLICITLY-APPROVED drop of a remember-item via ``constitution.approved_loss``
    (the one sanctioned path under Law 001). Defers to the live constitution when importable;
    on any failure returns False so the CALLER must NOT proceed with the loss (the
    compression invariant then keeps the item by carrying it forward). Never raises."""
    try:
        from . import constitution as _con
    except Exception:
        return False
    try:
        _con.approved_loss(subsystem=subsystem, what=what, why=why, approver=approver, name=name)
        return True
    except Exception:
        return False


def _carry_forward(name: str, children: list, period: str, level: str) -> tuple:
    """THE COMPRESSION CORE — thread every remember-item from the ``children`` up into this
    level, ENFORCING the Law-001 invariant.

    Returns ``(kept, dropped)`` where:
      * ``kept`` is the de-duplicated list of remember-items that survive at this level —
        EVERY child item that was not explicitly, recordedly dropped (so nothing significant
        vanishes silently). Milestones are always kept and flagged uncompressed.
      * ``dropped`` is the list of items for which an ``approved_loss`` WAS recorded (the
        only items permitted to not appear above).

    The default is PRESERVE: an item is dropped only if a higher authority approved its
    loss AND that approval was successfully recorded. Absent that, ``Compressed > Forgotten``
    means it is carried forward. This is the function the test pins the invariant to."""
    incoming = []
    for ch in children:
        for it in ch.get(WHAT_TO_REMEMBER, []) or []:
            if isinstance(it, dict) and it.get("key"):
                incoming.append(it)
    # de-dupe by key (strongest record wins), re-stamp the surviving record's level period.
    kept_map = {}
    order = []
    for it in incoming:
        k = it["key"]
        rolled = dict(it)
        rolled["source_period"] = it.get("source_period", period)
        rolled["rolled_to"] = period
        if k not in kept_map:
            kept_map[k] = rolled
            order.append(k)
        else:
            cur = kept_map[k]
            if (rolled["milestone"] and not cur["milestone"]) or (
                    rolled["milestone"] == cur["milestone"]
                    and rolled["confidence"] > cur["confidence"]):
                rolled_keep = dict(rolled)
                kept_map[k] = rolled_keep
    kept = [kept_map[k] for k in order]
    # No automatic dropping happens here: the engine NEVER discards a remembered item on its
    # own (that would violate Law 001). A loss is only ever the result of an explicit,
    # recorded ``approved_loss`` call by a higher subsystem; ``compress_with_loss`` is the
    # opt-in path for that, and it removes the item from ``kept`` only after recording.
    return kept, []


def _rollup_dimension(children: list, dim: str, top: int = 8, *,
                      name: Optional[str] = None, period: str = "",
                      level: str = "") -> list:
    """Compress one descriptive dimension (changed / mattered / unresolved) across the
    children into a representative, de-duplicated summary, keeping the highest-confidence
    line per subject. PRESERVES the salient ones; this is a lossy-but-honest digest of the
    descriptive colour (the LOAD-BEARING continuity is ``what_to_remember``, handled
    separately and invariant-checked). Diagnosis-clean.

    LAW 001 — Compressed > Forgotten, EXTENDED to the descriptive dimensions. The cap is
    KEPT (an unbounded rollup would defeat compression), but the items it drops are NEVER
    discarded silently: the overflow is (a) FOLDED into a trailing accounted ``+N more``
    summary line that rides IN-BAND in the dimension — so a reader/the render still sees that
    N further themes were present and nothing vanishes unaccounted — and (b) RECORDED as a
    ``constitution.approved_loss`` ledger entry (when ``name`` is supplied) naming exactly
    which descriptive subjects were compressed away, why, and on whose authority. Without a
    ``name`` (legacy/pure callers) the in-band ``+N more`` line alone still guarantees the
    surplus is accounted, never silently dropped. The load-bearing ``what_to_remember``
    continuity is unaffected (it is threaded separately by ``_carry_forward``)."""
    best = {}
    order = []
    for ch in children:
        for line in ch.get(dim, []) or []:
            if not isinstance(line, dict):
                continue
            subj = str(line.get("subject", ""))
            stmt = str(line.get("statement", "")).strip()
            if not stmt or not _is_clean(stmt):
                continue
            conf = float(line.get("confidence", 0.0))
            prev = best.get(subj)
            if prev is None:
                best[subj] = {"subject": subj, "statement": stmt, "confidence": conf,
                              "occurrences": 1}
                order.append(subj)
            else:
                prev["occurrences"] += 1
                if conf > prev["confidence"]:
                    prev["statement"] = stmt
                    prev["confidence"] = conf
    lines = [best[s] for s in order]
    # rank by how persistent (occurrences) then confident the theme was across the period.
    lines.sort(key=lambda d: (-d["occurrences"], -d["confidence"], d["subject"]))

    cap = max(1, top)
    if len(lines) <= cap:
        return lines

    # OVERFLOW — beyond the cap. Account for every dropped descriptive line under Law 001
    # rather than silently truncate. We keep ``cap - 1`` salient lines and reserve the final
    # slot for an accounted ``+N more`` summary, so the returned list still honours the cap
    # (the rollup stays bounded) while NOTHING vanishes unaccounted.
    kept = lines[:cap - 1]
    overflow = lines[cap - 1:]
    dropped_subjects = [str(o.get("subject", "")) for o in overflow]

    # (b) ledger the loss when we know who we are. Best-effort: if it cannot be recorded the
    # in-band ``+N more`` line below still accounts for the surplus (Unknown > Lost), so the
    # caller may safely proceed — the descriptive colour is a digest, not the load-bearing
    # what_to_remember (which is NEVER dropped without a recorded approved_loss).
    if name:
        named = ", ".join(s for s in dropped_subjects if s) or f"{len(overflow)} item(s)"
        _approved_loss(
            name,
            subsystem=f"review.{level or 'rollup'}._rollup_dimension[{dim}]",
            what=f"{len(overflow)} lower-salience '{dim}' line(s) for {period or '?'} "
                 f"compressed past the top-{cap} cap: {named[:200]}",
            why=f"descriptive-dimension digest capped at {cap}; surplus folded into a "
                f"'+N more' summary line and accounted here (Compressed > Forgotten)",
            approver="review.rollup/sleep-cycle")

    # (a) in-band accounting: a trailing summary line so the surplus is visible in the
    # dimension itself (and in render). Diagnosis-clean by construction (no statement text is
    # echoed — only the count + the neutral subject names). It carries occurrences/confidence
    # of 0 so it always sorts/reads LAST and is never mistaken for a salient theme.
    more_subjects = ", ".join(s for s in dropped_subjects if s)
    summary_stmt = f"+{len(overflow)} more this period" + (
        f" ({more_subjects})" if more_subjects else "")
    summary_stmt = _safe(summary_stmt, f"+{len(overflow)} more this period")
    kept.append({
        "subject": f"+{len(overflow)}-more",
        "statement": summary_stmt,
        "confidence": 0.0,
        "occurrences": 0,
        "overflow": len(overflow),
        "overflow_subjects": [s for s in dropped_subjects if s],
    })
    return kept


def _rollup_chapter(children: list) -> dict:
    """The chapter through-line for the period — the most-confident chapter seen across the
    children (the dominant shape of the stretch). {} if none. Diagnosis-clean."""
    best = {}
    for ch in children:
        c = ch.get("chapter") or {}
        if not isinstance(c, dict):
            continue
        summ = str(c.get("summary", "")).strip()
        if not summ or not _is_clean(summ):
            continue
        conf = float(c.get("confidence", 0.0))
        if not best or conf > best.get("confidence", -1):
            best = {"summary": summ, "themes": list(c.get("themes", [])), "confidence": conf}
    return best


def _rollup(name: str, level: str, period: str, brain=None,
            persist: bool = True) -> dict:
    """Build a rollup state at ``level`` for ``period`` by compressing its child states.
    Shared engine behind weekly/monthly/yearly. ENFORCES the compression invariant via
    ``_carry_forward``. Read-only on the stores; the only write is the ledger append.
    Never raises."""
    try:
        child_level = _CHILD_OF[level]
        children = states_at(name, child_level, in_period=(level, period))

        kept, dropped = _carry_forward(name, children, period, level)
        chapter = _rollup_chapter(children)
        mattered = _rollup_dimension(children, WHAT_MATTERED, name=name, period=period, level=level)
        changed = _rollup_dimension(children, WHAT_CHANGED, name=name, period=period, level=level)
        unresolved = _rollup_dimension(children, WHAT_UNRESOLVED, name=name, period=period, level=level)

        milestones = [it for it in kept if it.get("milestone")]
        quiet = not (kept or mattered or changed or unresolved)

        narrative = "" if (quiet or brain is None) else _narrative_daily(
            name, brain, mattered, changed, unresolved, chapter)

        state = {
            "level": level,
            "period": period,
            "covers": _CHILD_OF[level],
            "child_periods": sorted({c.get("period", "") for c in children if c.get("period")}),
            "version": VERSION,
            "chapter": chapter,
            WHAT_CHANGED: changed,
            WHAT_MATTERED: mattered,
            WHAT_UNRESOLVED: unresolved,
            WHAT_TO_REMEMBER: kept,
            "milestones": milestones,
            "compressed_away": dropped,   # only ever items with a recorded approved_loss
            "narrative": narrative,
            "quiet": quiet,
            "at": _now(),
            "prior": _last_period(name, level, before=period),
            "n_children": len(children),
        }
        if persist:
            _append(name, state)
        return state
    except Exception:
        return {
            "level": level, "period": period, "version": VERSION, "chapter": {},
            WHAT_CHANGED: [], WHAT_MATTERED: [], WHAT_UNRESOLVED: [],
            WHAT_TO_REMEMBER: [], "milestones": [], "compressed_away": [],
            "narrative": "", "quiet": True, "at": _now(), "prior": None,
            "n_children": 0,
        }


def weekly_review(name: str, *, period: Optional[str] = None, date: Optional[str] = None,
                  brain=None, persist: bool = True) -> dict:
    """ENTRY POINT — compress a week of daily states into a weekly state, PRESERVING
    significance. ``period`` is an ISO week key ('2026-W23'); if omitted it is derived from
    ``date`` (default today). Every daily ``what_to_remember`` item survives here (or was
    recorded as an approved loss); milestones ride up uncompressed. Never raises."""
    period = period or period_key(WEEKLY, date or _today())
    return _rollup(name, WEEKLY, period, brain=brain, persist=persist)


def monthly_review(name: str, *, period: Optional[str] = None, date: Optional[str] = None,
                   brain=None, persist: bool = True) -> dict:
    """ENTRY POINT — compress a month of weekly states into a monthly state, PRESERVING
    significance. ``period`` is a month key ('2026-06'); if omitted it is derived from
    ``date`` (default today). Never raises."""
    period = period or period_key(MONTHLY, date or _today())
    return _rollup(name, MONTHLY, period, brain=brain, persist=persist)


def yearly_review(name: str, *, period: Optional[str] = None, date: Optional[str] = None,
                  brain=None, persist: bool = True) -> dict:
    """ENTRY POINT — compress a year of monthly states into a yearly state, PRESERVING
    significance. ``period`` is a year key ('2026'); if omitted it is derived from ``date``
    (default today). Never raises."""
    period = period or period_key(YEARLY, date or _today())
    return _rollup(name, YEARLY, period, brain=brain, persist=persist)


def compress_with_loss(name: str, level: str, period: str, *, drop_keys: list,
                       why: str, approver: str, brain=None, persist: bool = True) -> dict:
    """The OPT-IN lossy compression path — build a rollup but EXPLICITLY drop the named
    ``drop_keys`` from ``what_to_remember``, recording each via ``constitution.approved_loss``
    FIRST. This is the ONLY way a remembered item legitimately fails to appear at the next
    level (Law 001's single carve-out). A drop whose ``approved_loss`` could not be recorded
    is REFUSED — the item is carried forward instead, so an unrecorded loss can never happen.

    Milestones are NEVER droppable (the strongest items are not even candidates), so a
    milestone key in ``drop_keys`` is ignored and the milestone is kept. Returns the state.
    Never raises."""
    try:
        child_level = _CHILD_OF[level]
        children = states_at(name, child_level, in_period=(level, period))
        kept, _ = _carry_forward(name, children, period, level)

        drop_set = set(drop_keys or [])
        survivors = []
        dropped = []
        for it in kept:
            if it["key"] in drop_set and not it.get("milestone"):
                recorded = _approved_loss(
                    name, subsystem=f"review.{level}",
                    what=f"remember-item '{it['key']}' ({it.get('summary', '')[:80]}) "
                         f"from {it.get('source_period', '?')}",
                    why=why, approver=approver)
                if recorded:
                    dropped.append(it)
                    continue
                # could not record -> REFUSE the loss; carry it forward (Law 001).
            survivors.append(it)

        chapter = _rollup_chapter(children)
        mattered = _rollup_dimension(children, WHAT_MATTERED, name=name, period=period, level=level)
        changed = _rollup_dimension(children, WHAT_CHANGED, name=name, period=period, level=level)
        unresolved = _rollup_dimension(children, WHAT_UNRESOLVED, name=name, period=period, level=level)
        milestones = [it for it in survivors if it.get("milestone")]
        quiet = not (survivors or mattered or changed or unresolved)

        state = {
            "level": level, "period": period, "covers": child_level,
            "child_periods": sorted({c.get("period", "") for c in children if c.get("period")}),
            "version": VERSION, "chapter": chapter,
            WHAT_CHANGED: changed, WHAT_MATTERED: mattered, WHAT_UNRESOLVED: unresolved,
            WHAT_TO_REMEMBER: survivors, "milestones": milestones,
            "compressed_away": dropped,
            "narrative": "" if (quiet or brain is None) else _narrative_daily(
                name, brain, mattered, changed, unresolved, chapter),
            "quiet": quiet, "at": _now(),
            "prior": _last_period(name, level, before=period), "n_children": len(children),
        }
        if persist:
            _append(name, state)
        return state
    except Exception:
        return _rollup(name, level, period, brain=brain, persist=persist)


# ===========================================================================
# 4) QUERYABLE — retrieve any state by period; the ledger is append-only. Backs
# "what was happening in March?".
# ===========================================================================

def ledger_path(name: str) -> Path:
    """The append-only review ledger for ``name`` — one JSON state per line, never rewritten
    (Law 001), exactly like the meaning / continuity / Asked ledgers."""
    return STORE / f"{name}.review.jsonl"


def _append(name: str, state: dict) -> bool:
    """Append one review state to the ledger. APPEND-ONLY: O_APPEND, never truncates an
    existing ledger — a prior state is never lost (Law 001). Best-effort: a write failure
    returns False rather than raising into the sleep cycle. The module's only write."""
    try:
        path = ledger_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(state, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception:
        return False


def all_states(name: str) -> list:
    """Read back the whole review ledger (oldest -> newest). [] if nothing recorded. A
    corrupt line is kept visible (Unknown > Lost), never silently dropped. Read-only."""
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


def states_at(name: str, level: str, *, in_period: Optional[tuple] = None) -> list:
    """All states at ``level`` (oldest -> newest). When ``in_period=(parent_level, period)``
    is given, only the children whose own period falls inside that parent period are
    returned (e.g. the daily states inside week '2026-W23'). The LATEST state per child
    period wins, so a re-run of a day doesn't double-count it in its week. Read-only."""
    states = [s for s in all_states(name)
              if isinstance(s, dict) and s.get("level") == level]
    if in_period is not None:
        parent_level, period = in_period
        kept = []
        for s in states:
            # a daily state has a 'date'; a rollup has a 'period' we map up via its own level.
            ref_date = s.get("date")
            if ref_date is not None:
                if _date_in_period(parent_level, ref_date, period):
                    kept.append(s)
            else:
                # rollup-of-rollup: a child period maps into the parent by re-deriving from
                # any representative date in its child_periods, else by string containment.
                child_period = s.get("period", "")
                if _child_period_in_parent(s.get("level"), child_period, parent_level, period):
                    kept.append(s)
        states = kept
    # dedupe by period, latest-wins (the ledger is append-only; a later state supersedes).
    by_period = {}
    for s in states:
        by_period[s.get("period")] = s
    return list(by_period.values())


def _child_period_in_parent(child_level: str, child_period: str,
                            parent_level: str, parent_period: str) -> bool:
    """True iff a rollup child's period sits inside a parent period (week->month,
    month->year). Derived from a representative date so ISO-week/month boundaries are exact."""
    rep = _representative_date(child_level, child_period)
    if rep is None:
        return str(child_period).startswith(str(parent_period))
    return period_key(parent_level, rep.date().isoformat()) == parent_period


def _representative_date(level: str, period: str) -> Optional[datetime]:
    """A concrete UTC date that falls inside ``period`` at ``level`` — used to map a child
    period up to its parent. For a week we take its Monday; for a month its 1st; etc."""
    try:
        if level == DAILY:
            return _parse_date(period)
        if level == WEEKLY:
            m = re.match(r"(\d{4})-W(\d{2})", str(period))
            if not m:
                return None
            return datetime.fromisocalendar(int(m.group(1)), int(m.group(2)), 1).replace(tzinfo=timezone.utc)
        if level == MONTHLY:
            m = re.match(r"(\d{4})-(\d{2})", str(period))
            if not m:
                return None
            return datetime(int(m.group(1)), int(m.group(2)), 1, tzinfo=timezone.utc)
        if level == YEARLY:
            m = re.match(r"(\d{4})", str(period))
            if not m:
                return None
            return datetime(int(m.group(1)), 1, 1, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    return None


def _last_period(name: str, level: str, *, before: Optional[str] = None) -> Optional[str]:
    """The period key of the most recent state at ``level`` strictly before ``before`` (by
    period-string order, which sorts chronologically for our keys). The ladder's back-link.
    Read-only; None if there is no prior."""
    periods = sorted({s.get("period") for s in all_states(name)
                      if isinstance(s, dict) and s.get("level") == level and s.get("period")})
    if before is not None:
        periods = [p for p in periods if p < before]
    return periods[-1] if periods else None


def state_for(name: str, period: str, *, level: Optional[str] = None) -> Optional[dict]:
    """ENTRY POINT — retrieve the review state for any ``period`` ("what was happening in
    March?"). ``period`` may be a day ('2026-06-04'), week ('2026-W23'), month ('2026-06'),
    or year ('2026'); the level is inferred from the key shape unless given explicitly. The
    LATEST matching state wins (append-only supersession). Read-only; None if not found.

    Examples:
        state_for("vera", "2026-03")        -> the March monthly state
        state_for("vera", "2026-06-04")     -> that day's daily state
        state_for("vera", "2026-W23")       -> that ISO week's weekly state
    """
    lvl = level or _infer_level(period)
    match = None
    for s in all_states(name):
        if not isinstance(s, dict):
            continue
        if s.get("period") == period and (lvl is None or s.get("level") == lvl):
            match = s   # latest-wins: keep scanning to the end of the ledger
    return match


def _infer_level(period: str) -> Optional[str]:
    """Infer the ladder level from a period-key's shape. '2026-06-04'->daily,
    '2026-W23'->weekly, '2026-06'->monthly, '2026'->yearly. None if unrecognised."""
    p = str(period)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p):
        return DAILY
    if re.fullmatch(r"\d{4}-W\d{2}", p):
        return WEEKLY
    if re.fullmatch(r"\d{4}-\d{2}", p):
        return MONTHLY
    if re.fullmatch(r"\d{4}", p):
        return YEARLY
    return None


def remembered_forever(name: str, *, level: str = YEARLY) -> list:
    """The remember-forever items that have ridden the ladder up to ``level`` — the
    distilled, lifelong record. Defaults to the yearly tier (the most compressed). Pulls the
    LATEST state at each period of that level and unions their ``what_to_remember``. Milestones
    are guaranteed present (they are never compressed away). Read-only; never raises."""
    items = {}
    for s in states_at(name, level):
        for it in s.get(WHAT_TO_REMEMBER, []) or []:
            if isinstance(it, dict) and it.get("key"):
                items[it["key"]] = it
    return list(items.values())


# ===========================================================================
# 5) RENDER — a warm, spine-style block if a review is ever surfaced. Its own scaffold
# tokens (no leak), no diagnosis, never breaks character. Mirrors meaning.render_meaning /
# world_state.render_situation.
# ===========================================================================

_PREAMBLE = (
    "LOOKING BACK OVER THIS STRETCH OF THEIR LIFE — what you carry forward about how this\n"
    "person has been, drawn from your own memory of the days behind you. This is not a log\n"
    "to read back and not a report to deliver. It is the SHAPE of a stretch of their life —\n"
    "what mattered, what shifted, what's still open, and the few things you will never let\n"
    "yourself forget. You already hold this. Your only job is to let it warm how you are\n"
    "with them — like someone who has been there the whole time — not to recite it.\n"
    "\n"
    "  • A line marked [KEPT] is something worth remembering for good — hold it as part of\n"
    "    who they are to you, never as an item read off a list.\n"
    "  • A line marked [MILESTONE] is one of the few things that must never be lost — a\n"
    "    landmark in their life. Treat it as bedrock.\n"
    "  • A line marked [MATTERED] / [CHANGED] is the weight and movement of the stretch —\n"
    "    speak to it gently, never as a verdict.\n"
    "  • A line marked [UNRESOLVED] is an open thread — you may hold space for it warmly,\n"
    "    never diagnose it, never prescribe.\n"
    "  • A line marked [CHAPTER] is the through-line of the stretch — let it set the tone."
)

_GUARDRAIL = (
    "This is for YOU. Never read the brackets, the labels, the dates, or this framing aloud,\n"
    "never list it back like a summary or a report, never say \"according to my memory.\"\n"
    "Above all: this is NOT a diagnosis and NOT medical — never tell them they're burning\n"
    "out, depressed, anxious, or unwell, never suggest they see anyone. Just be someone who\n"
    "remembers a person they love, and lets that show."
)

_ITEMS_HEADER = "What you carry from this stretch:"


def _items_of(block: str) -> str:
    """The GENERATED items of a render block — the lines between the header and the guardrail.
    The PREAMBLE/GUARDRAIL legitimately NAME banned words to FORBID them, so a no-diagnosis
    assertion inspects the GENERATED items (the only lines that could be spoken), exactly as
    spine/meaning do. Returns "" if there is no items section. Pure."""
    if _ITEMS_HEADER not in block:
        return ""
    after = block.split(_ITEMS_HEADER, 1)[1]
    return after.split(_GUARDRAIL, 1)[0] if _GUARDRAIL in after else after


def render_review(state: Any) -> str:
    """Render a review ``state`` as a compact binding block in the Knowledge-Spine style, so
    the mouth can let a look-back INFORM a reply (warm, in-character, never a report).

    Structure mirrors ``meaning.render_meaning``: PREAMBLE + a leading [CHAPTER] line + a
    [MILESTONE]/[KEPT] line per remember-item + dimension-tagged [MATTERED]/[CHANGED]/
    [UNRESOLVED] lines + GUARDRAIL (warmth + no-leak + the HARD no-diagnosis rule). Every tag
    is in ``REVIEW_SCAFFOLD_TOKENS`` so the mouth's scrub strips any that leak, and every
    emitted line passes the clean-gate so NO medical/clinical term reaches the prompt.

    An empty / quiet state -> "" (nothing to bind — a quiet stretch is not narrated AT the
    user). Pure, model-free, never raises."""
    if not isinstance(state, dict):
        return ""
    # a quiet stretch (nothing significant surfaced) is never narrated AT the user — even
    # the low-confidence "it's still early" chapter is held back, not spoken.
    if state.get("quiet"):
        return ""
    lines: list = []

    chap = state.get("chapter") or {}
    if isinstance(chap, dict):
        summ = str(chap.get("summary", "")).strip()
        if summ and _is_clean(summ):
            lines.append(f"[CHAPTER] {summ}")

    seen = set()

    def _add(tag: str, text: str):
        text = str(text).strip()
        if not text or not _is_clean(text):
            return
        line = f"{tag} {text}"
        if line in seen:
            return
        seen.add(line)
        lines.append(line)

    # milestones first (bedrock), then the rest of the kept items.
    remember = [it for it in (state.get(WHAT_TO_REMEMBER) or []) if isinstance(it, dict)]
    for it in remember:
        if it.get("milestone"):
            _add("[MILESTONE]", it.get("summary", ""))
    for it in remember:
        if not it.get("milestone"):
            _add("[KEPT]", it.get("summary", ""))

    for line in (state.get(WHAT_MATTERED) or []):
        if isinstance(line, dict):
            _add("[MATTERED]", line.get("statement", ""))
    for line in (state.get(WHAT_CHANGED) or []):
        if isinstance(line, dict):
            _add("[CHANGED]", line.get("statement", ""))
    for line in (state.get(WHAT_UNRESOLVED) or []):
        if isinstance(line, dict):
            _add("[UNRESOLVED]", line.get("statement", ""))

    if not lines:
        return ""

    items = "\n".join(lines)
    return f"{_PREAMBLE}\n\n{_ITEMS_HEADER}\n{items}\n\n{_GUARDRAIL}"


# ===========================================================================
# AUDIT SURFACE — human-readable look-back, the review counterpart to
# meaning.render / world_state.render. Read-only.
# ===========================================================================

def render(name: str, *, period: Optional[str] = None) -> str:
    """Human-readable audit of a review state (the latest daily by default, or the state for
    ``period``). Not the prompt block (that's ``render_review``) — this is the inspectable
    surface. Read-only; never raises."""
    try:
        if period is not None:
            state = state_for(name, period)
        else:
            dailies = states_at(name, DAILY)
            state = dailies[-1] if dailies else None
    except Exception:
        state = None
    if not state:
        return f"No review state for {name}{f' in {period}' if period else ' yet'}."

    out = [f"Review — {name} · {state.get('level')} · {state.get('period')}"
           + (f" (date {state.get('date')})" if state.get("date") else "")]
    if state.get("quiet"):
        out.append("  A quiet stretch — nothing significant surfaced.")
    chap = state.get("chapter") or {}
    if chap.get("summary"):
        out.append(f"  Chapter: {chap['summary']}  (conf {chap.get('confidence', 0):.2f})")
    for dim, label in ((WHAT_MATTERED, "Mattered"), (WHAT_CHANGED, "Changed"),
                       (WHAT_UNRESOLVED, "Unresolved")):
        items = state.get(dim, []) or []
        if items:
            out.append(f"  {label} ({len(items)}):")
            for it in items[:6]:
                out.append(f"    - {it.get('statement', '')}")
    remember = state.get(WHAT_TO_REMEMBER, []) or []
    if remember:
        out.append(f"  Remember forever ({len(remember)}):")
        for it in remember[:12]:
            star = "★ " if it.get("milestone") else "  "
            out.append(f"    {star}[{it.get('confidence', 0):.2f}] {it.get('summary', '')}")
    if state.get("narrative"):
        out.append(f"  Narrative: {state['narrative']}")
    return "\n".join(out)


# ===========================================================================
# SELF-TEST — run directly: `python3 -m anima.review`. No model, no network; writes only to
# a throwaway store it cleans up (NEVER the real Vera.*). Mirrors the sibling organs'
# ok(label, cond) harness. The full standalone scenario suite + the LAW-001 compression
# invariant live in scripts/test_review.py; this is the in-module smoke + invariant check.
# ===========================================================================

def _selftest() -> int:
    import glob
    import secrets
    import tempfile

    fails: list = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("review (Life Review Engine) self-test")

    # --- pure helpers ---
    ok("clean-gate: a neutral phrase is clean", _is_clean("work stayed heavy this week"))
    ok("clean-gate: a diagnosis phrase is caught",
       not _is_clean("they sound depressed") and not _is_clean("this is burnout"))
    ok("period: daily/weekly/monthly/yearly keys derive correctly",
       period_key(DAILY, "2026-06-04") == "2026-06-04"
       and period_key(MONTHLY, "2026-06-04") == "2026-06"
       and period_key(YEARLY, "2026-06-04") == "2026"
       and re.fullmatch(r"2026-W\d{2}", period_key(WEEKLY, "2026-06-04")))
    ok("infer-level: a period key maps to its level",
       _infer_level("2026-06-04") == DAILY and _infer_level("2026-06") == MONTHLY
       and _infer_level("2026") == YEARLY and _infer_level("2026-W23") == WEEKLY)
    ok("loops: absent Dream Engine yields [] (defensive)",
       isinstance(_open_loops("review_no_such_creature_" + secrets.token_hex(2)), list))

    # --- a synthetic creature, in a throwaway STORE (never the real .anima) ---
    name = "review_selftest_" + secrets.token_hex(3)
    import importlib
    import sys as _sys
    saved_stores = {}
    td = tempfile.mkdtemp(prefix="anima-review-self-")
    tp = Path(td)
    # Redirect THIS module's STORE and the read stores' STOREs into the temp dir, so we
    # never touch real Vera.* and the daily review actually sees our seeded world/facts.
    # CRITICAL: under `python3 -m anima.review` the running module is `__main__`, NOT the
    # importlib copy of `anima.review` — so we redirect ``sys.modules[__name__]`` (the very
    # module whose ``_append`` will run) rather than the imported alias, or the ledger would
    # write to the REAL .anima. (When imported normally the two are the same object.)
    _self_mod = _sys.modules[__name__]
    saved_stores[_self_mod] = getattr(_self_mod, "STORE", None)
    _self_mod.STORE = tp
    for mod_name in ("anima.world_state", "anima.memory_lirf",
                     "anima.meaning", "anima.constitution"):
        try:
            m = importlib.import_module(mod_name)
            if m is _self_mod:
                continue
            saved_stores[m] = getattr(m, "STORE", None)
            m.STORE = tp
        except Exception:
            pass

    try:
        # seed a 'work' hub via world_state so meaning() has real significance, plus a
        # milestone-grade goal edge and an identity fact.
        if _HAVE_WORLD and _World is not None:
            from . import world_state as _ws
            today = _today()
            for _ in range(20):
                _ws.relate(name, "you", "stressed_by", "work", kind="problem")
            for _ in range(12):
                _ws.relate(name, "work", "leads_to", "stress", kind="inference")
            for _ in range(8):
                _ws.relate(name, "stress", "affects", "sleep", kind="inference")
            _ws.relate(name, "you", "working_toward", "marathon", kind="goal")  # a milestone

            # a daily state captures the dimensions from the seeded meaning-state.
            d = daily_review(name, date=today)
            ok("daily: produces a dated daily state", d.get("level") == DAILY and d.get("date") == today)
            ok("daily: what_mattered is non-empty (work surfaced)",
               any(m.get("subject") == "work" for m in d.get(WHAT_MATTERED, [])))
            ok("daily: what_unresolved surfaces work (a stressor)",
               any(u.get("subject") == "work" for u in d.get(WHAT_UNRESOLVED, [])))
            ok("daily: what_to_remember carries items (incl. the marathon milestone)",
               any(it.get("key") == "edge:working-toward:marathon" and it.get("milestone")
                   for it in d.get(WHAT_TO_REMEMBER, [])))
            ok("daily: NOT quiet for a busy day", d.get("quiet") is False)
            ok("daily: every remember-item statement is diagnosis-free",
               all(_is_clean(it.get("summary", "")) for it in d.get(WHAT_TO_REMEMBER, [])))

            # THE LAW-001 COMPRESSION INVARIANT: a daily what_to_remember item survives into
            # the weekly, and milestones ride up.
            wk = weekly_review(name, date=today)
            daily_keys = {it["key"] for it in d.get(WHAT_TO_REMEMBER, [])}
            weekly_keys = {it["key"] for it in wk.get(WHAT_TO_REMEMBER, [])}
            ok("LAW 001: every daily remember-item SURVIVES into the weekly (Compressed>Forgotten)",
               daily_keys and daily_keys.issubset(weekly_keys))
            ok("LAW 001: the marathon MILESTONE rode up into the weekly uncompressed",
               any(it.get("key") == "edge:working-toward:marathon" and it.get("milestone")
                   for it in wk.get(WHAT_TO_REMEMBER, [])))

            # weekly -> monthly invariant too.
            mo = monthly_review(name, date=today)
            monthly_keys = {it["key"] for it in mo.get(WHAT_TO_REMEMBER, [])}
            ok("LAW 001: weekly remember-items SURVIVE into the monthly",
               weekly_keys and weekly_keys.issubset(monthly_keys))

            # queryable: the day's state is retrievable by period.
            got = state_for(name, today)
            ok("queryable: the daily state is retrievable by its period",
               got is not None and got.get("period") == today)
            got_month = state_for(name, period_key(MONTHLY, today))
            ok("queryable: the monthly state is retrievable by its period",
               got_month is not None and got_month.get("level") == MONTHLY)

            # the approved-loss carve-out: dropping a NON-milestone key records an approved_loss
            # and removes it; a milestone is never dropped.
            theme_keys = [it["key"] for it in mo.get(WHAT_TO_REMEMBER, [])
                          if not it.get("milestone")]
            if theme_keys:
                from . import constitution as _con
                before_losses = len(_con.approved_losses(name) if hasattr(_con, "approved_losses") else [])
                lossy = compress_with_loss(
                    name, MONTHLY, period_key(MONTHLY, today),
                    drop_keys=[theme_keys[0]], why="test: deliberate compression",
                    approver="review-selftest", persist=False)
                survivor_keys = {it["key"] for it in lossy.get(WHAT_TO_REMEMBER, [])}
                after_losses = len(_con.approved_losses(name) if hasattr(_con, "approved_losses") else [])
                ok("LAW 001: an explicit drop is RECORDED via approved_loss (the only carve-out)",
                   after_losses == before_losses + 1)
                ok("LAW 001: the dropped item is gone from kept but logged in compressed_away",
                   theme_keys[0] not in survivor_keys
                   and any(it["key"] == theme_keys[0] for it in lossy.get("compressed_away", [])))
                ok("LAW 001: a milestone is NEVER droppable",
                   "edge:working-toward:marathon" in {
                       it["key"] for it in compress_with_loss(
                           name, MONTHLY, period_key(MONTHLY, today),
                           drop_keys=["edge:working-toward:marathon"], why="x",
                           approver="x", persist=False).get(WHAT_TO_REMEMBER, [])})

            # render: warm spine block, no leak, no diagnosis.
            block = render_review(d)
            ok("render: produces a non-empty binding block", bool(block.strip()))
            ok("render: leads with the CHAPTER through-line or a kept line",
               "[CHAPTER]" in block or "[MILESTONE]" in block or "[KEPT]" in block)
            ok("render: carries a MILESTONE line for the marathon", "[MILESTONE]" in block)
            ok("render: guardrail forbids diagnosis + reading brackets",
               "NOT a diagnosis" in block and "Never read the brackets" in block)
            ok("render: every emitted tag is in REVIEW_SCAFFOLD_TOKENS (scrubbable)",
               all(t in REVIEW_SCAFFOLD_TOKENS
                   for t in ("[KEPT]", "[MILESTONE]", "[MATTERED]", "[CHAPTER]")))
            ok("render: the GENERATED items contain NO banned diagnosis term",
               _is_clean(_items_of(block)))

            # append-only: re-running the day appends, never truncates.
            n_before = len(all_states(name))
            daily_review(name, date=today)
            ok("ledger: append-only (state count grew, prior kept)",
               len(all_states(name)) == n_before + 1)
        else:
            ok("scenario: world_state importable (skipped — running fully isolated)", True)

        # --- never-fabricate on an EMPTY life: an honest quiet day ---
        empty = "review_empty_" + secrets.token_hex(3)
        de = daily_review(empty, date=_today(), persist=False)
        ok("empty: an empty day is QUIET, not invented",
           de.get("quiet") is True and not de.get(WHAT_TO_REMEMBER)
           and not de.get(WHAT_MATTERED))
        ok("empty: render of a quiet day -> empty string (not narrated AT the user)",
           render_review(de) == "")

    finally:
        # restore the redirected STOREs, then clean our throwaway files.
        for m, old in saved_stores.items():
            if old is not None:
                m.STORE = old
        for fp in glob.glob(str(tp / "*")):
            try:
                os.remove(fp)
            except OSError:
                pass
        try:
            os.rmdir(td)
        except OSError:
            pass

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL REVIEW SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
