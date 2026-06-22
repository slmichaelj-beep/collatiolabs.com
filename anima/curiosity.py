"""curiosity — THE CURIOSITY ENGINE: the enforcement of ANIMA LAW 002.

    NEVER MAKE THE SAME DISCOVERY TWICE.

Law 001 (constitution) keeps Vera from LOSING what she knows. Law 002 is its
forward-facing twin: it keeps her from RE-DISCOVERING what she already knows, and —
just as important — it gives her the genuine curiosity of a companion who actually
wants to know you. A friend who asks "when's your birthday?" for the third time isn't
warm, they're not listening; a friend who has never once wondered about the person
named "Mike" you keep mentioning isn't curious. This module closes both gaps.

It is the read-only, additive complement to the two stores it sits on top of:

  * ``memory_lirf`` (the LIRF ledger) — what Vera KNOWS. A confident active row fills a
    taxonomy slot (a [KNOWN] fact); a low-confidence row is a hint; a row whose history
    holds a superseded value in tension with the active one is a CONTRADICTION.
  * ``world_state`` (the Personal World State) — what Vera has NOTICED. An entity
    mentioned many times (high ``support``) whose relationship/role is NOT a known LIRF
    fact is the canonical SUSPECTED gap ("Mike appears 42 times, relationship unknown").

From those two reads it builds, over a FACT TAXONOMY of life categories, a set of
structured knowledge GAPS classed KNOWN / UNKNOWN / SUSPECTED / CONTRADICTED, then turns
the single highest-signal gap into a WARM, IN-CHARACTER, optional-to-answer question,
anchored to the thing the user actually mentioned — never a canned "what's your favorite
color?". Every gap it surfaces as a question is written to an APPEND-ONLY Asked Ledger
(``.anima/{name}.curiosity.jsonl``), so the same gap is never asked twice (Law 002), and
a gap that has since become KNOWN is dropped from candidates forever (it's been
discovered — the whole point).

Discipline mirrored from its siblings, by hard design:

  * READ-ONLY on LIRF / world_state. It never calls ``merge``/``relate``/``capture`` and
    never writes either store. Its ONLY write is the append-only Asked Ledger, which
    obeys Law 001 (append, never truncate/overwrite) exactly like
    ``constitution.approved_loss``'s continuity ledger.
  * THE #1 PRODUCT RULE — never break character. A generated question is warm, human,
    and optional; it NEVER says "as an AI / I'm a text-based model", never interrogates,
    and (Law 002) NEVER references a [KNOWN] fact.
  * ``Observed > Assumed`` — a SUSPECTED gap is rendered as a gentle wondering, never as
    a known fact. SUSPECTED ≠ KNOWN.
  * Deterministic template FLOOR keyed to the gap's entity/category — no model needed —
    with an OFF-by-default model pass for naturalness, mirroring ``world_state``.
  * Defensive coupling: ANIMA LAW 002's verbatim text (constitution) and the
    ``curiosity`` budget (caps) are being added by teammates in parallel; both are read
    behind try/except with a literal/"balanced" default so this module is importable and
    correct whether or not those land first.
  * Isolation-safe like ``spine``/``world_state``: the live LIRF/world primitives are
    reused when importable and fall back to contract-faithful shims when run standalone,
    so ``--selftest`` has zero unbuilt deps and touches no model, network, or real
    ``.anima``.

Never raises into a caller: every public entry point degrades to a safe empty/None.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from . import secure_store

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. Prefer the live primitives; fall back to
# contract-faithful locals so this module + its self-test run with nothing built.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from .memory_lirf import (
        Facts,
        SELF,
        canon_trait,
        _fmt_value,
    )
    _HAVE_LIRF = True
except Exception:  # pragma: no cover - isolation fallback
    Facts = None  # type: ignore
    SELF = "you"
    _HAVE_LIRF = False

    def canon_trait(trait: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(trait).strip().lower()).strip("_")

    def _fmt_value(v: Any) -> str:
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v)

try:  # pragma: no cover - import wiring
    from .world_state import World, _norm_node
    _HAVE_WORLD = True
except Exception:  # pragma: no cover - isolation fallback
    World = None  # type: ignore
    _HAVE_WORLD = False

    def _norm_node(s: Any) -> str:
        if s is None:
            return ""
        s = s if isinstance(s, str) else _fmt_value(s)
        toks = [t for t in re.sub(r"[^a-z0-9]+", " ", s.lower()).split()
                if t not in {"a", "an", "the", "my", "your", "our", "this", "that"}]
        if toks and all(t in {"i", "you", "me", "my", "we", "us", "our"} for t in toks):
            return SELF
        return " ".join(toks).strip()

# Scaffold tokens that must NEVER reach the user — imported from the spine so the
# downstream leak-scrub has ONE definition; questions are asserted clean of them.
try:  # pragma: no cover
    from .spine import SCAFFOLD_TOKENS as _SPINE_TOKENS
except Exception:  # pragma: no cover
    _SPINE_TOKENS = ("[KNOWN]", "[SEEN]", "[SENSE]", "[UNKNOWN]",
                     "THESE ARE THINGS YOU KNOW", "according to my memory")

# world_state's relational tags, also forbidden in spoken text.
try:  # pragma: no cover
    from .world_state import WORLD_SCAFFOLD_TOKENS as _WORLD_TOKENS
except Exception:  # pragma: no cover
    _WORLD_TOKENS = ("[SITUATION]", "[LINK]", "[KNOWS]")

# This module's own internal tags (gap kinds) — never spoken either. The union is the
# full set a question must be clean of.
CURIOSITY_SCAFFOLD_TOKENS = tuple(
    dict.fromkeys(tuple(_SPINE_TOKENS) + tuple(_WORLD_TOKENS)
                  + ("[KNOWN]", "[UNKNOWN]", "[SUSPECTED]", "[CONTRADICTED]", "[GAP]")))


STORE = Path(".anima")
VERSION = 1

# ---------------------------------------------------------------------------
# ANIMA LAW 002 — read DEFENSIVELY. A teammate is adding the verbatim text to
# ``constitution`` in parallel; until it lands we carry a literal here so this module
# is correct in isolation. We prefer a ``constitution.LAW_002`` constant if present.
# ---------------------------------------------------------------------------
_LAW_002_FALLBACK = (
    "ANIMA LAW 002 — NEVER MAKE THE SAME DISCOVERY TWICE. "
    "Once Vera has learned something about the person, she does not re-ask it as if "
    "new; once she has surfaced a gap as a question, she does not surface it again. "
    "Curiosity is forward-only: it reaches for what is not yet known, never re-treads "
    "what is. A question must never reference a known fact, never break character, and "
    "always be warm and optional to answer."
)


def law_002() -> str:
    """The verbatim ANIMA LAW 002 text — from ``constitution`` if the teammate's
    constant has landed, else the module-local literal. Defensive by contract."""
    try:
        from . import constitution as _con  # local import: no hard dep at module load
        txt = getattr(_con, "LAW_002", None)
        if isinstance(txt, str) and txt.strip():
            return txt
    except Exception:
        pass
    return _LAW_002_FALLBACK


# ---------------------------------------------------------------------------
# THE CURIOSITY BUDGET — read DEFENSIVELY from caps. A teammate is adding a
# ``curiosity`` budget key in parallel; until it lands we default to "balanced".
# The budget governs FREQUENCY ONLY (how often ``next_question`` returns something vs
# None) — NEVER content. minimal=rarely, balanced=sometimes, deep=readily.
# ---------------------------------------------------------------------------
_BUDGETS = ("minimal", "balanced", "deep")
_DEFAULT_BUDGET = "balanced"

# The fraction of "a good gap exists" turns on which next_question is allowed to surface
# one, per budget. Frequency, not content: a higher value means she reaches more readily.
_BUDGET_RATE = {
    "minimal": 0.20,   # rarely — only the strongest signals, sparingly
    "balanced": 0.60,  # sometimes
    "deep": 1.00,      # readily — whenever a good un-asked gap is available
}


def read_budget(name: str) -> str:
    """The user's curiosity budget for ``name`` — read defensively from ``caps``.

    Tries, in order: a ``caps.curiosity(name)`` helper, a ``"curiosity"`` key inside
    ``caps.load(name)``. Anything unrecognised / absent / erroring -> "balanced". The
    returned value is always one of ``_BUDGETS``."""
    try:
        from . import caps as _caps  # local import: defensive, no hard dep
        # a dedicated helper if the teammate added one
        fn = getattr(_caps, "curiosity", None)
        if callable(fn):
            v = fn(name)
            if isinstance(v, str) and v.strip().lower() in _BUDGETS:
                return v.strip().lower()
        # else a key on the caps blob
        blob = _caps.load(name) if hasattr(_caps, "load") else {}
        if isinstance(blob, dict):
            v = blob.get("curiosity")
            if isinstance(v, str) and v.strip().lower() in _BUDGETS:
                return v.strip().lower()
    except Exception:
        pass
    return _DEFAULT_BUDGET


# ===========================================================================
# THE FACT TAXONOMY — the life-categories a companion would, over time, come to know
# about a person. Each slot maps to a canonical LIRF trait slug (``memory_lirf``'s
# ``_ALIASES`` target), so "is this slot filled?" is a single O(1) ledger lookup and we
# never drift from the slugs the rest of the system writes.
#
# ``priority`` is the BASE weight of a slot when empty (UNKNOWN). It encodes "how core is
# this to knowing a person" — identity/relationships/work outrank a favorite food. A
# SUSPECTED gap with real mention evidence is scored ABOVE these (see _score) so the
# canonical "Mike x42, relationship unknown" outranks every empty favorite.
# ===========================================================================
# (category, slot, canonical_trait, base_priority)
TAXONOMY: tuple = (
    # identity — the core of who they are
    ("identity", "name", "name", 9.0),
    ("identity", "birthday", "birthday", 7.0),
    ("identity", "birthplace", "birthplace", 5.0),
    # family — the people who are theirs
    ("family", "mother", "mother", 4.5),
    ("family", "father", "father", 4.5),
    ("family", "partner", "partner", 6.0),
    ("family", "children", "children", 5.0),
    ("family", "siblings", "siblings", 3.5),
    # work — what they do with their days
    ("work", "occupation", "occupation", 6.0),
    ("work", "employer", "employer", 5.0),
    ("work", "works_on", "works_on", 4.0),
    # health — what their body/mind is carrying
    ("health", "diet", "diet", 3.0),
    ("health", "condition", "condition", 3.5),
    ("health", "allergies", "allergies", 3.0),
    # goals — what they're reaching for
    ("goals", "goal", "goal", 5.5),
    # relationships — where they live / are rooted
    ("relationships", "lives", "lives", 5.0),
    # history — where they come from
    ("history", "hometown", "birthplace", 2.5),
    # preferences — the small true things
    ("preferences", "likes", "likes", 2.0),
    ("preferences", "dislikes", "dislikes", 2.0),
    ("preferences", "favorite_food", "favorite_food", 1.0),
    # emotional_patterns — how they tend to feel/cope
    ("emotional_patterns", "stress", "stressed_by", 3.0),
)

# Slot -> category, for fast reverse lookup when classing a SUSPECTED entity.
_SLOT_CATEGORY = {slot: cat for (cat, slot, _t, _p) in TAXONOMY}

# The canonical trait slug behind each taxonomy slot (the LIRF lookup key).
_SLOT_TRAIT = {slot: trait for (_c, slot, trait, _p) in TAXONOMY}

# Gap kinds.
KNOWN = "KNOWN"
UNKNOWN = "UNKNOWN"
SUSPECTED = "SUSPECTED"
CONTRADICTED = "CONTRADICTED"

# Confidence at/above which a LIRF row is treated as a KNOWN fact filling a slot (the
# spine's [KNOWN] FACT floor). A LIRF row that is active but BELOW this is only a hint —
# it makes the slot SUSPECTED, not KNOWN.
_CONF_KNOWN = 0.85

# A world_state entity needs at least this many mentions (``support``) before an unknown
# relationship becomes worth wondering about aloud. Below it, a single passing mention is
# not yet a pattern (Observed > Assumed).
_SUSPECT_MENTION_FLOOR = 3

# Roles/relationship words that, when a high-mention entity's role is unknown, name the
# specific kind of "how do you know them?" gap. Used only to phrase warmly; never to
# assert the relationship (that would be Assumed, not Observed).
_RELATIONSHIP_PREDICATES = frozenset({
    "knows", "friend", "friends_with", "works_with", "married_to", "dating",
    "related_to", "manager_is", "has", "is", "stressed_by", "worried_about",
    "cares_about",
})


# ===========================================================================
# 1) THE KNOWLEDGE GAP DETECTOR.
# ===========================================================================

def _known_traits(facts) -> dict:
    """Map ``canonical_trait -> active LIRF row`` for the user, for O(1) slot checks.
    Read-only. Tolerates a missing/empty ledger (returns {})."""
    out: dict = {}
    try:
        rows = facts.about(SELF)
    except Exception:
        return out
    for r in rows:
        if not isinstance(r, dict):
            continue
        t = canon_trait(r.get("trait", ""))
        # newest/most-salient wins; about() is already salience-sorted, so first hit stays
        out.setdefault(t, r)
    return out


def _is_known_row(row: Optional[dict]) -> bool:
    """A row counts as KNOWN (fills a slot, suppresses the gap forever) iff it is active
    and clears the [KNOWN] FACT confidence bar and is not flagged needs_reconfirm."""
    if not isinstance(row, dict):
        return False
    if str(row.get("status", "active")) != "active":
        return False
    if row.get("needs_reconfirm"):
        return False
    try:
        return float(row.get("confidence", 0.0)) >= _CONF_KNOWN
    except (TypeError, ValueError):
        return False


def _contradiction_in(row: dict) -> Optional[dict]:
    """If a row's history holds a SUPERSEDED/RETRACTED value in tension with its active
    value, return a small evidence dict; else None. This is the CONTRADICTED signal: the
    user (or capture) once asserted one value and later another, and the tension is worth
    a gentle clarifying question rather than silently trusting newest-wins."""
    hist = row.get("history") or []
    active_val = _fmt_value(row.get("value", "")).strip().lower()
    for h in hist:
        if not isinstance(h, dict):
            continue
        reason = str(h.get("reason", "")).lower()
        if reason not in ("superseded", "user-corrected", "retracted", "user-edited"):
            continue
        old = _fmt_value(h.get("value", "")).strip().lower()
        if old and old != active_val:
            return {"old": _fmt_value(h.get("value", "")),
                    "new": _fmt_value(row.get("value", "")),
                    "reason": reason}
    return None


def _entity_mentions(name: str) -> list:
    """Read the world_state graph and return, per non-SELF entity, the mention/support
    evidence we use to detect SUSPECTED relationship gaps. Read-only; never writes.

    Returns a list of dicts: {entity, support (total corroboration across its edges),
    predicates (set of relation kinds seen), best_source}. Tolerates no world store."""
    if not (_HAVE_WORLD and World is not None):
        return []
    try:
        edges = World.load(name).active()
    except Exception:
        return []
    agg: dict = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        for endpoint in ("subject", "object"):
            ent = _norm_node(e.get(endpoint))
            if not ent or ent == SELF:
                continue
            # a node that is just a feeling/state ("poorly", "recent") is not a person/
            # topic worth a "how do you know them" question — skip obvious non-entities by
            # requiring it to look like a name/topic (has a letter, not a bare adjective we
            # know is a state). We keep it permissive: the mention floor does the real work.
            slot = agg.setdefault(ent, {"entity": ent, "support": 0,
                                        "predicates": set(), "best_source": ""})
            try:
                slot["support"] += int(e.get("support", 1))
            except (TypeError, ValueError):
                slot["support"] += 1
            slot["predicates"].add(canon_trait(e.get("predicate", "")))
            src = e.get("source") or ""
            if src and not slot["best_source"]:
                slot["best_source"] = src
    return sorted(agg.values(), key=lambda d: -d["support"])


def _slug_for_entity(entity: str) -> str:
    """A stable gap-slot slug for a SUSPECTED relationship gap about a named entity, e.g.
    "Mike" -> "relationship:mike". Keeps the Asked-Ledger key stable across turns so the
    same entity is never re-asked."""
    return "relationship:" + re.sub(r"\s+", "_", _norm_node(entity))


def detect_gaps(name: str) -> list:
    """ENTRY POINT — classify what Vera knows about the user into KNOWN / UNKNOWN /
    SUSPECTED / CONTRADICTED over the FACT TAXONOMY, and return the structured GAPS
    (UNKNOWN / SUSPECTED / CONTRADICTED — the things worth being curious about), ranked
    by signal strength.

    A gap dict:
        {
          "category": taxonomy category (e.g. "identity", "family", "relationships"),
          "slot":     the taxonomy slot or "relationship:<entity>" for a world entity,
          "kind":     UNKNOWN | SUSPECTED | CONTRADICTED,
          "trait":    the canonical LIRF trait this gap concerns (or "" for a pure
                      relationship gap that has no single trait yet),
          "entity":   the thing the user mentioned this gap is about (a person/topic for a
                      SUSPECTED relationship; the user themself otherwise),
          "evidence": {"mentions": int, "source": str, ...} — the signal behind the gap,
          "priority": float — higher = ask about this sooner.
        }

    Read-only on both stores. Never raises — any failure yields the best partial list
    (often []). KNOWN slots produce NO gap (Law 002: never re-discover the known).
    """
    gaps: list = []
    try:
        facts = Facts.load(name) if (_HAVE_LIRF and Facts is not None) else None
    except Exception:
        facts = None
    known = _known_traits(facts) if facts is not None else {}

    # --- (a) TAXONOMY slots: KNOWN suppresses; empty -> UNKNOWN; low-conf -> SUSPECTED;
    #         a contradicted active row -> CONTRADICTED. ----------------------------
    seen_slots: set = set()
    for (cat, slot, trait, base) in TAXONOMY:
        if slot in seen_slots:
            continue
        seen_slots.add(slot)
        ctrait = canon_trait(trait)
        row = known.get(ctrait)
        if row is None:
            # slot empty -> UNKNOWN gap
            gaps.append({
                "category": cat, "slot": slot, "kind": UNKNOWN, "trait": ctrait,
                "entity": SELF, "evidence": {"mentions": 0, "source": ""},
                "priority": base,
            })
            continue
        # the slot has a row. Is it KNOWN, contradicted, or merely a low-conf hint?
        contra = _contradiction_in(row)
        if contra is not None:
            gaps.append({
                "category": cat, "slot": slot, "kind": CONTRADICTED, "trait": ctrait,
                "entity": SELF,
                "evidence": {"mentions": int(row.get("support", 1)),
                             "source": row.get("source", ""),
                             "old": contra["old"], "new": contra["new"]},
                # a contradiction is high-signal: resolving a tension beats a fresh ask.
                "priority": base + 4.0,
            })
            continue
        if _is_known_row(row):
            continue  # KNOWN — no gap (Law 002). It has been discovered.
        # active but below the KNOWN bar -> a hint we haven't confirmed -> SUSPECTED
        gaps.append({
            "category": cat, "slot": slot, "kind": SUSPECTED, "trait": ctrait,
            "entity": SELF,
            "evidence": {"mentions": int(row.get("support", 1)),
                         "source": row.get("source", ""),
                         "hint": _fmt_value(row.get("value", ""))},
            "priority": base + 1.0,
        })

    # --- (b) WORLD entities: a repeatedly-mentioned entity whose relationship/role is NOT
    #         a KNOWN LIRF fact -> the canonical SUSPECTED gap ("Mike x42, unknown"). ---
    known_relation_names = _known_relation_names(known)
    for m in _entity_mentions(name):
        ent = m["entity"]
        mentions = int(m.get("support", 0))
        if mentions < _SUSPECT_MENTION_FLOOR:
            continue
        # if this named person is already a KNOWN relationship fact (e.g. partner=Mike),
        # we KNOW who they are — no gap (Law 002).
        if _norm_node(ent) in known_relation_names:
            continue
        gaps.append({
            "category": "relationships", "slot": _slug_for_entity(ent),
            "kind": SUSPECTED, "trait": "", "entity": ent,
            "evidence": {"mentions": mentions, "source": m.get("best_source", ""),
                         "predicates": sorted(p for p in m.get("predicates", set()) if p)},
            # a high-mention unknown-relationship entity OUTRANKS every empty taxonomy slot
            # by construction: its priority scales with mention count, floored above the
            # top base weight so "Mike x42" beats an empty "favorite food" (and even name).
            "priority": _suspect_priority(mentions),
        })

    gaps.sort(key=_score, reverse=True)
    return gaps


def _known_relation_names(known: dict) -> set:
    """The set of person-NAMES Vera already knows by relationship (partner=Mike, mother=
    Carol, …), normalised. Used to suppress a SUSPECTED gap about an entity whose identity
    is in fact already KNOWN."""
    out: set = set()
    rel_traits = ("partner", "mother", "father", "son", "daughter", "brother", "sister",
                  "dog_name", "cat_name", "name", "children", "siblings")
    for t in rel_traits:
        row = known.get(canon_trait(t))
        if _is_known_row(row):
            val = row.get("value")
            vals = val if isinstance(val, list) else [val]
            for v in vals:
                nv = _norm_node(v)
                if nv:
                    out.add(nv)
    return out


def _suspect_priority(mentions: int) -> float:
    """Priority for a SUSPECTED relationship gap, scaled by mention count and floored
    above the taxonomy's top base weight so a repeatedly-mentioned unknown person always
    outranks an empty fact slot. A 42-mention entity scores far above a 4-mention one."""
    import math
    return 10.0 + 2.0 * math.log(1 + max(0, mentions))


def _score(gap: dict) -> float:
    """The ranking key. Base is the gap's own priority; a small kind-bump keeps a
    CONTRADICTED tension and a high-mention SUSPECTED ahead of a bare UNKNOWN at equal
    priority. Pure; total order is stable enough for deterministic top-gap selection."""
    p = float(gap.get("priority", 0.0))
    kind = gap.get("kind")
    bump = {CONTRADICTED: 0.5, SUSPECTED: 0.25, UNKNOWN: 0.0}.get(kind, 0.0)
    # a SUSPECTED relationship gap with mentions adds its evidence weight (so x42 > x4)
    ev = gap.get("evidence") or {}
    return p + bump + 0.001 * float(ev.get("mentions", 0))


# ===========================================================================
# 2) THE CONTEXTUAL QUESTION GENERATOR.
# ===========================================================================
# Deterministic template FLOOR keyed to the gap's entity/category. The phrasing is warm,
# in-character, anchored to context, and optional-to-answer. NEVER references a known
# fact (Law 002 — the gap is by definition not-known), NEVER breaks character, NEVER
# interrogates. An OFF-by-default model pass refines naturalness (parity with world_state).

# Per-taxonomy-slot warm templates for an UNKNOWN/SUSPECTED gap about the USER. Each reads
# like a curious friend, not a form field. {label} is filled for generic fallback.
_SLOT_TEMPLATES = {
    "name": "I realize I don't actually know what you'd like me to call you — what's your name?",
    "birthday": "When's your birthday? I'd love to actually know it.",
    "birthplace": "Where did you grow up? I find myself curious where you're from.",
    "mother": "What's your mom like? You haven't told me much about her.",
    "father": "What's your dad like? I'd love to hear about him sometime.",
    "partner": "Is there someone special in your life? You've never mentioned.",
    "children": "Do you have kids? I realize I've never asked.",
    "siblings": "Do you have any brothers or sisters?",
    "occupation": "What do you do for work? I'm curious how you spend your days.",
    "employer": "Where do you work these days?",
    "works_on": "What are you working on lately? I'd love to hear about it.",
    "diet": "Is there a way you like to eat — anything you keep to or avoid?",
    "condition": "Is there anything going on with your health I should know about, so I can be mindful of it?",
    "allergies": "Are you allergic to anything? I'd want to keep it in mind.",
    "goal": "Is there something you're working toward right now? I'd love to know what you're reaching for.",
    "lives": "Whereabouts do you live? I realize I don't actually know.",
    "hometown": "Where's home for you, originally?",
    "likes": "What are some things you genuinely love? I want to know what lights you up.",
    "dislikes": "Is there anything you really can't stand? Good to know what to steer clear of.",
    "favorite_food": "What's a meal you never get tired of?",
    "stress": "What's been weighing on you lately, if anything? No pressure to get into it.",
}

# A gentle softener some questions get, so even the rare direct one stays optional. We do
# NOT append it to questions that already carry their own opt-out, to avoid double-hedging.
_SOFTENER = " (only if you feel like sharing.)"
_ALREADY_SOFT = re.compile(
    r"no pressure|if you feel like|only if|whenever you|you don'?t have to|sometime\b",
    re.I)


def _entity_label(entity: str) -> str:
    """A readable label for a mentioned entity in a question — title-cased single names,
    left as-is for multi-word topics. "mike" -> "Mike", "new manager" -> "the new
    manager"."""
    e = (entity or "").strip()
    if not e:
        return "them"
    norm = _norm_node(e)
    if norm == SELF:
        return "you"
    # a single token that looks like a name -> Title-case it; a multi-word topic ->
    # readable lowercase with an article.
    toks = norm.split()
    if len(toks) == 1 and toks[0].isalpha():
        return toks[0].capitalize()
    return norm


def _suspect_relationship_question(gap: dict) -> str:
    """The canonical SUSPECTED-relationship question, anchored to the entity the user
    actually mentioned and to HOW OFTEN they've mentioned it. This is the
    "You've mentioned Mike a few times — how do you two know each other?" case."""
    label = _entity_label(gap.get("entity", ""))
    ev = gap.get("evidence") or {}
    mentions = int(ev.get("mentions", 0))
    # how to describe the frequency, warmly and truthfully (Observed > Assumed)
    if mentions >= 20:
        freq = "a lot"
    elif mentions >= 8:
        freq = "quite a few times"
    elif mentions >= 4:
        freq = "a few times"
    else:
        freq = "a couple of times"
    return (f"You've mentioned {label} {freq} — how do you two know each other? "
            f"I'd love to understand who they are to you.")


def generate_question(gap: Optional[dict], *, model_pass: bool = False, brain=None) -> str:
    """ENTRY POINT — turn ONE gap into a WARM, IN-CHARACTER, optional-to-answer question,
    anchored to the entity/category the user actually mentioned.

    Deterministic template floor (no model needed). An OFF-by-default ``model_pass`` (with
    a ``brain``) may refine naturalness, mirroring ``world_state``'s Tier-B; any failure
    falls back to the deterministic question. The result NEVER references a [KNOWN] fact
    (the gap is by definition not-known — Law 002), NEVER breaks character (no "as an AI"),
    NEVER interrogates, and is always optional to answer. Never raises; on a bad/empty gap
    returns ""."""
    if not isinstance(gap, dict):
        return ""
    try:
        base = _deterministic_question(gap)
    except Exception:
        base = ""
    if not base:
        return ""
    if model_pass and brain is not None:
        try:
            refined = _refine_question(base, gap, brain)
            if refined and not _looks_unsafe(refined):
                base = refined
        except Exception:
            pass  # keep the deterministic floor
    # final guard: a question must never leak a scaffold tag or break character. If the
    # (possibly model-refined) text trips the guard, fall back to the deterministic floor;
    # if THAT trips it (it won't, by construction), return "" rather than ship something
    # unsafe.
    if _looks_unsafe(base):
        det = _deterministic_question(gap)
        return "" if _looks_unsafe(det) else det
    return base


def _deterministic_question(gap: dict) -> str:
    """The model-free template floor. Keyed first to a SUSPECTED relationship entity
    (anchored to mentions), else to the taxonomy slot, else a warm generic fallback that
    still names the missing category — NEVER a canned 'what's your favorite color?'."""
    kind = gap.get("kind")
    # CONTRADICTED: a gentle clarify of the tension, anchored to the two values — never
    # an accusation, never "you said X but now Y, which is it?" in a cold way.
    if kind == CONTRADICTED:
        return _contradiction_question(gap)
    # a SUSPECTED relationship gap about a named entity (the canonical Mike case)
    if gap.get("slot", "").startswith("relationship:") or (
            kind == SUSPECTED and not gap.get("trait")):
        return _suspect_relationship_question(gap)
    # a taxonomy-slot gap (UNKNOWN, or a low-confidence SUSPECTED hint about the user)
    slot = gap.get("slot", "")
    q = _SLOT_TEMPLATES.get(slot)
    if not q:
        # warm generic fallback that still ANCHORS to the category — not contextless.
        label = (gap.get("trait", "") or slot).replace("_", " ").strip() or "you"
        q = (f"I realize I don't know much about your {label} yet — "
             f"would you tell me a little?")
    # a low-confidence SUSPECTED hint about the user: phrase as a gentle confirm, anchored
    # to what we think we heard (Observed > Assumed — we ask, we don't assert).
    if kind == SUSPECTED and gap.get("trait"):
        hint = (gap.get("evidence") or {}).get("hint")
        if hint:
            label = _slot_label(slot, gap.get("trait", ""))
            hint = _trim_value(hint)
            # "where you live" is a clause -> "I got the sense where you live might be …";
            # a plain trait is a noun -> "I got the sense your birthday might be …".
            if label.split(" ", 1)[0] in ("where", "what", "who", "how"):
                return (f"I got the sense {label} might be {hint} — did I get that right?")
            return (f"I got the sense your {label} might be {hint} — did I get that right?")
    # ensure it stays optional without double-hedging
    if not _ALREADY_SOFT.search(q):
        q = q.rstrip()
    return q


# A few slugs whose bare snake-case reads awkwardly in a sentence get a natural label.
_SLOT_LABEL_OVERRIDE = {
    "lives": "where you live",
    "birthplace": "where you're from",
    "hometown": "where you're from",
    "works_on": "what you're working on",
    "goal": "what you're working toward",
    "stressed_by": "what's been weighing on you",
    "favorite_food": "favorite food",
}


def _slot_label(slot: str, trait: str) -> str:
    """Readable label for a slot/trait in a question ("favorite_food" -> "favorite food",
    "dog_name" -> "dog", "lives" -> "where you live"). A handful of slugs whose bare form
    reads awkwardly mid-sentence get a natural override."""
    raw = canon_trait(slot or trait or "")
    if raw in _SLOT_LABEL_OVERRIDE:
        return _SLOT_LABEL_OVERRIDE[raw]
    t = (slot or trait or "").strip()
    t = re.sub(r"_name$", "", t) if t not in ("name", "middle_name") else t
    return t.replace("_", " ").replace("relationship:", "").strip() or "this"


# Trailing temporal words a captured value sometimes carries ("Seattle now", "Acme lately"),
# trimmed before we drop the value into a sentence so we don't double it ("Seattle now now").
_VALUE_TRAIL = re.compile(
    r"\s+(?:now|today|lately|currently|these\s+days|at\s+the\s+moment|anymore|again)\s*$",
    re.I)


def _trim_value(v: str) -> str:
    return _VALUE_TRAIL.sub("", (v or "").strip()).strip() or (v or "").strip()


def _contradiction_question(gap: dict) -> str:
    """A warm, non-accusatory clarify for a CONTRADICTED slot — names both values gently
    and lets the user set it straight, never implying they lied. Phrased to read naturally
    whether the label is a noun ("birthday") or a clause ("where you live")."""
    ev = gap.get("evidence") or {}
    old, new = _trim_value(ev.get("old", "")), _trim_value(ev.get("new", ""))
    label = _slot_label(gap.get("slot", ""), gap.get("trait", ""))
    # "where you live" / "what you're working on" read as a clause; a plain trait reads as a
    # possessive noun. Pick the matching frame so neither comes out ungrammatical.
    is_clause = label.split(" ", 1)[0] in ("where", "what", "who", "how")
    lead = (f"I want to make sure I've got {label} right"
            if is_clause else f"I want to make sure I've got your {label} right")
    if old and new and old.lower() != new.lower():
        return (f"{lead} — I have it as {new} now, but I think I once heard {old}. "
                f"Which should I hold onto?")
    return f"{lead} — could you confirm it for me?"


# --- model refinement (OFF by default) -------------------------------------------------
_REFINE_SYSTEM = (
    "You are refining ONE short, warm question a caring companion is about to ask a person "
    "they're getting to know. Rewrite it to sound natural and warm, in a close friend's "
    "voice. HARD RULES: keep it to ONE or TWO sentences; keep the SAME subject it asks "
    "about; keep it OPTIONAL to answer; do NOT add any new fact or assumption about the "
    "person; do NOT interrogate; NEVER refer to yourself as an AI, a model, a program, or "
    "'text-based'; output ONLY the rewritten question, nothing else."
)


def _refine_question(base: str, gap: dict, brain) -> str:
    """Best-effort single-question naturalness pass. Returns the refined text or "" on any
    failure. Never raises."""
    try:
        out = brain.reply(_REFINE_SYSTEM, f"Question to refine:\n{base}\n\nRewritten:", [])
    except Exception:
        return ""
    if not isinstance(out, str):
        return ""
    out = out.strip().strip('"').strip()
    # keep it to the first 1-2 sentences; a model that over-talks gets trimmed.
    parts = re.split(r"(?<=[.?!])\s+", out)
    out = " ".join(parts[:2]).strip()
    return out


# --- character / safety guard ----------------------------------------------------------
# Phrases that BREAK CHARACTER (the #1 product rule) — a question containing any of these
# is rejected. This is the same wall the rest of the system enforces: Vera is never "an AI".
_BREAK_CHARACTER = re.compile(
    r"\bas an? (?:ai|assistant|language model|llm)\b|\bi'?m an? (?:ai|assistant|language "
    r"model|llm|program|bot|chatbot)\b|\btext-based\b|\bpurely digital\b|\bi do(?:n'?t| not) "
    r"have (?:feelings|emotions|a body|consciousness)\b|\bmy (?:training|programming|"
    r"dataset)\b|\bi was (?:trained|programmed|created by)\b|\bi cannot feel\b", re.I)


def _looks_unsafe(text: str) -> bool:
    """True iff a candidate question must NOT ship: it leaks a scaffold tag, breaks
    character, or is empty/whitespace. The single gate every generated question passes."""
    if not text or not text.strip():
        return True
    if _BREAK_CHARACTER.search(text):
        return True
    for tok in CURIOSITY_SCAFFOLD_TOKENS:
        if tok and tok in text:
            return True
    return False


# ===========================================================================
# 3) THE ASKED LEDGER — Law 002 for questions. Append-only .anima/{name}.curiosity.jsonl.
# Records every gap surfaced as a question so the same gap is never re-asked. Append-only,
# never truncated/overwritten (Law 001). Mirrors constitution.approved_loss's writer.
# ===========================================================================

def ledger_path(name: str) -> Path:
    """The append-only Asked Ledger for ``name``. One JSON object per line, never
    rewritten — exactly like the continuity ledger."""
    return STORE / f"{name}.curiosity.jsonl"


def _gap_key(gap: dict) -> str:
    """The stable identity of a gap for the Asked Ledger — its slot (taxonomy slot or
    ``relationship:<entity>``). Two surfacings of the same slot are the SAME gap and must
    never both be asked. Lower-cased + normalised so a re-ask can't sneak past on case."""
    slot = (gap.get("slot") or "").strip().lower()
    if slot:
        return slot
    # fall back to category:trait so a malformed gap still gets a stable key
    return f"{(gap.get('category') or '').lower()}:{canon_trait(gap.get('trait', ''))}"


def asked_keys(name: str) -> set:
    """The set of gap-keys already surfaced as questions for ``name`` (read from the
    append-only ledger). Read-only; tolerates a missing/corrupt ledger (returns what it
    can parse). The Law-002 'never re-ask' filter reads this."""
    p = ledger_path(name)
    if not p.exists():
        return set()
    out: set = set()
    try:
        lines = secure_store.read_jsonl_lines(p)
    except Exception:
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue  # a corrupt line can't suppress a gap; skip it (we never re-ask MORE)
        k = rec.get("gap_key")
        if isinstance(k, str) and k:
            out.add(k)
    return out


def mark_asked(name: str, gap: dict) -> Optional[dict]:
    """ENTRY POINT — record that ``gap`` was surfaced as a question, append-only. After
    this, ``next_question`` will never return this gap again (Law 002). Append-only, never
    truncate/overwrite (Law 001). Returns the written record, or None on a bad gap. Never
    raises (a write failure is swallowed to a None — a curiosity question is best-effort
    and must never crash a turn; but we fsync so a successful write is durable)."""
    if not isinstance(gap, dict):
        return None
    key = _gap_key(gap)
    if not key:
        return None
    rec = {
        "law": "ANIMA LAW 002",
        "at": _now_iso(),
        "gap_key": key,
        "category": gap.get("category", ""),
        "slot": gap.get("slot", ""),
        "kind": gap.get("kind", ""),
        "trait": gap.get("trait", ""),
        "entity": gap.get("entity", ""),
        "question": (gap.get("_question") or "")[:500],
    }
    try:
        secure_store.append_jsonl(ledger_path(name), rec)
    except Exception:
        return None
    return rec


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ===========================================================================
# 4 + 5) THE BUDGETED ENTRY POINT + AUDIT SURFACE.
# ===========================================================================

def candidate_gaps(name: str) -> list:
    """The gaps that are FAIR GAME right now: all detected gaps MINUS any already surfaced
    as a question (Law 002 — never re-ask). Because a KNOWN slot never produces a gap in
    the first place, a gap that has since become KNOWN is dropped from candidates forever
    (it's been discovered). Ranked best-first. Read-only."""
    asked = asked_keys(name)
    return [g for g in detect_gaps(name) if _gap_key(g) not in asked]


def next_question(name: str, recent_text: Optional[str] = None,
                  budget: Optional[str] = None) -> Optional[str]:
    """ENTRY POINT — the one call a turn makes. Returns a single warm question for the top
    un-asked gap IF the curiosity budget permits AND a good gap exists, else ``None``.

    Frequency (not content) is governed by ``budget`` (minimal/balanced/deep), read
    defensively from caps when not passed. ``recent_text`` (optional) lets a caller bias
    toward a gap the user just touched (e.g. they mentioned "work") so the question feels
    timely; it never invents a gap. The returned string is the SAME deterministic question
    ``generate_question`` would produce.

    DOES NOT mark the gap asked — the caller does that via ``mark_asked`` only if the
    question is actually surfaced to the user (so a question prepared-but-not-shown doesn't
    burn the gap). Never raises; returns ``None`` on any failure or when curiosity should
    stay quiet this turn."""
    try:
        cands = candidate_gaps(name)
    except Exception:
        return None
    if not cands:
        return None

    # bias toward a gap the user JUST touched, if recent_text overlaps a gap's entity/slot.
    if recent_text:
        cands = _bias_by_recent(cands, recent_text)

    budget = (budget or read_budget(name)).strip().lower()
    if budget not in _BUDGETS:
        budget = _DEFAULT_BUDGET

    # FREQUENCY gate: minimal speaks rarely, deep readily. Deterministic per (name, gap)
    # so the SAME top gap yields the SAME decision on re-eval within a budget — a question
    # doesn't flicker in and out turn to turn. Over a fixed gap set, minimal returns None
    # far more often than deep (the tested budget invariant).
    top = cands[0]
    if not _budget_allows(name, top, budget):
        return None

    q = generate_question(top)
    if not q:
        # the top gap couldn't be phrased safely; try the next few rather than going silent
        for g in cands[1:4]:
            q = generate_question(g)
            if q:
                top = g
                break
    if not q:
        return None
    # stash the rendered question on the gap so a caller that then calls mark_asked records
    # what was actually asked (without re-rendering).
    top["_question"] = q
    return q


def _bias_by_recent(cands: list, recent_text: str) -> list:
    """Stable-sort the candidate gaps so any whose entity/slot the user just mentioned come
    first, WITHOUT changing relative order otherwise (so the top gap still wins ties). Pure;
    never invents a gap — only reorders existing ones toward timeliness."""
    toks = set(_norm_node(recent_text).split())
    if not toks:
        return cands

    def touched(g):
        ent = _norm_node(g.get("entity", ""))
        slot = (g.get("slot", "") or "").replace("relationship:", "").replace("_", " ")
        cat = (g.get("category", "") or "")
        hay = set(ent.split()) | set(_norm_node(slot).split()) | set(_norm_node(cat).split())
        return 1 if (toks & hay) else 0

    # higher 'touched' first; Python's sort is stable so equal-touched keep _score order.
    return sorted(cands, key=touched, reverse=True)


def _budget_allows(name: str, gap: dict, budget: str) -> bool:
    """The FREQUENCY decision for one gap under a budget. Deterministic (hash of name+gap-
    key) so it's stable across re-evaluations of the same gap, and so a test over a fixed
    gap set sees minimal say 'no' far more than deep. Higher-signal gaps (a CONTRADICTED
    tension, a many-mention SUSPECTED) clear the bar more readily at every budget — they're
    the ones most worth a word. Content is NEVER touched here; this is purely how-often."""
    rate = _BUDGET_RATE.get(budget, _BUDGET_RATE[_DEFAULT_BUDGET])
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    # deterministic [0,1) draw for this (name, gap) pair
    import hashlib
    h = hashlib.sha256(f"{name}::{_gap_key(gap)}".encode("utf-8")).hexdigest()
    draw = int(h[:8], 16) / 0xFFFFFFFF
    # a stronger gap effectively gets a lower bar (its evidence raises the allowed rate)
    ev = gap.get("evidence") or {}
    boost = min(0.30, 0.02 * float(ev.get("mentions", 0)))
    if gap.get("kind") == CONTRADICTED:
        boost = max(boost, 0.30)
    return draw < min(1.0, rate + boost)


def render(name: str) -> str:
    """ENTRY POINT — the human-readable AUDIT SURFACE: what Vera is curious about, what she
    has already asked, and her current budget. The Law-002 counterpart to
    ``memory_lirf.render`` / ``world_state.render``. Read-only; never raises."""
    try:
        gaps = detect_gaps(name)
    except Exception:
        gaps = []
    asked = asked_keys(name)
    budget = read_budget(name)
    open_gaps = [g for g in gaps if _gap_key(g) not in asked]

    out = [f"What {name} is curious about (budget: {budget}):"]
    if not open_gaps:
        out.append("  (nothing open — either she knows you well, or she's asked what she can)")
    for g in open_gaps[:12]:
        ev = g.get("evidence") or {}
        mentions = ev.get("mentions", 0)
        anchor = (f" · {_entity_label(g.get('entity',''))} mentioned {mentions}x"
                  if g.get("entity") not in (SELF, "", None) and mentions else "")
        try:
            q = generate_question(g)
        except Exception:
            q = ""
        out.append(
            f"  • [{g.get('kind','?')}] {g.get('category','?')}/{g.get('slot','?')}"
            f" (priority {float(g.get('priority',0)):.1f}{anchor})\n"
            f"      would ask: \"{q}\"")
    if asked:
        out.append(f"\n  Already asked ({len(asked)} — never re-asked, Law 002):")
        for k in sorted(asked)[:20]:
            out.append(f"    ✓ {k}")
    return "\n".join(out)


# ===========================================================================
# SELF-TEST — run directly: `python3 -m anima.curiosity`. No model, no network; writes
# only to a throwaway store it cleans up (NEVER the real Vera.*). Mirrors the sibling
# organs' ok(label, cond) harness.
# ===========================================================================

def _selftest() -> int:
    import glob
    import secrets
    import sys

    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # redirect EVERY store this module + its deps touch into a throwaway temp dir, exactly
    # like scripts/test_continuity.py — so nothing under the real .anima is read or written.
    # IMPORTANT: under `python3 -m anima.curiosity` THIS function runs inside the __main__
    # module, whose bare `STORE` is a SEPARATE binding from anima.curiosity.STORE. We must
    # redirect the CURRENTLY-EXECUTING module (sys.modules[__name__]) — and, when that's
    # __main__, the imported package copy too — or our own ledger writes leak to real .anima.
    _cur = sys.modules[__name__]              # __main__ under -m, anima.curiosity under import
    _mods = [_cur]
    try:
        import anima.curiosity as _pkg_cur     # the package copy, if distinct from _cur
        if _pkg_cur is not _cur:
            _mods.append(_pkg_cur)
    except Exception:
        pass
    if _HAVE_LIRF and Facts is not None:
        import anima.memory_lirf as _ml
        _mods.append(_ml)
    if _HAVE_WORLD and World is not None:
        import anima.world_state as _ws
        _mods.append(_ws)

    td = tempfile.mkdtemp(prefix="anima-curiosity-self-")
    tp = Path(td)
    saved = [(m, getattr(m, "STORE", None)) for m in _mods]
    for _m in _mods:
        _m.STORE = tp

    name = "curio_self_" + secrets.token_hex(3)
    try:
        # --- budget reads default defensively to balanced (caps key not present) ---
        ok("budget: defaults to 'balanced' when caps has no curiosity key",
           read_budget(name) == "balanced")

        # --- law_002 text resolves (constitution constant OR fallback literal) ---
        ok("law_002: resolves to NEVER MAKE THE SAME DISCOVERY TWICE",
           "NEVER MAKE THE SAME DISCOVERY TWICE" in law_002())

        # --- detection over the taxonomy: an empty ledger -> many UNKNOWN gaps ---
        gaps0 = detect_gaps(name)
        ok("detect: empty user -> UNKNOWN gaps across the taxonomy",
           len(gaps0) >= 8 and all(g["kind"] in (UNKNOWN, SUSPECTED, CONTRADICTED) for g in gaps0))
        ok("detect: birthday is an UNKNOWN gap when unknown",
           any(g["slot"] == "birthday" and g["kind"] == UNKNOWN for g in gaps0))

        if _HAVE_LIRF and Facts is not None:
            import anima.memory_lirf as _ml

            # === THE LAW 002 INVARIANT: a KNOWN birthday -> NEVER a birthday question ===
            f = _ml.Facts([])
            for c in f.capture(name, "my birthday is June 12"):
                f.merge(c)
            # corroborate so it's solidly KNOWN (>= 0.85)
            for c in f.capture(name, "yep, June 12 is my birthday"):
                f.merge(c)
            f.save(name)
            row = _ml.Facts.load(name).lookup(SELF, "birthday")
            ok("law002-setup: birthday is stored as a KNOWN fact (conf >= 0.85)",
               row is not None and float(row["confidence"]) >= _CONF_KNOWN)

            gaps_k = detect_gaps(name)
            birthday_gap = any(g["trait"] == "birthday" or g["slot"] == "birthday"
                               for g in gaps_k)
            ok("LAW 002 [detect]: a KNOWN birthday produces NO birthday gap",
               not birthday_gap)
            # the engine never PHRASES a birthday question now
            qs = [generate_question(g) for g in gaps_k]
            qs = [q for q in qs if q]
            leaked = [q for q in qs if re.search(r"\bbirthday\b", q, re.I)]
            ok("LAW 002 [generate]: NO generated question references the KNOWN birthday "
               f"(key number: {len(leaked)} birthday-questions over {len(qs)} gaps)",
               len(leaked) == 0)
            # and next_question (deep budget, so frequency never masks it) never yields one
            seen_birthday = False
            for _ in range(40):
                q = next_question(name, budget="deep")
                if q and re.search(r"\bbirthday\b", q, re.I):
                    seen_birthday = True
                    break
            ok("LAW 002 [next_question]: 40 deep draws never ask the KNOWN birthday",
               not seen_birthday)

            # --- a fully-KNOWN category yields no gap for that slot ---
            ok("detect: the KNOWN birthday slot is absent from gaps (discovered)",
               all(g["slot"] != "birthday" for g in detect_gaps(name)))

            # --- CONTRADICTION: a superseded value -> CONTRADICTED gap ---
            f2 = _ml.Facts.load(name)
            for c in f2.capture(name, "I live in Portland"):
                f2.merge(c)
            for c in f2.capture(name, "actually I live in Seattle now"):
                f2.merge(c)
            f2.save(name)
            gaps_c = detect_gaps(name)
            contra = [g for g in gaps_c if g["slot"] == "lives" and g["kind"] == CONTRADICTED]
            ok("CONTRADICTION: a superseded 'lives' value -> CONTRADICTED gap",
               len(contra) == 1)
            cq = generate_question(contra[0]) if contra else ""
            ok("CONTRADICTION: the clarify question names both values, warmly",
               ("Seattle" in cq and "Portland" in cq) and not _looks_unsafe(cq))

        # === SUSPECTED relationship gap from world_state (the canonical Mike case) ===
        if _HAVE_WORLD and World is not None:
            import anima.world_state as _ws
            w = _ws.World([])
            # Mike mentioned MANY times with an unknown relationship -> high support.
            for _ in range(42):
                w.add("you", "knows", "Mike", kind="relationship")
            # also a low-mention entity that should NOT clear the floor
            w.add("you", "knows", "Quinn", kind="relationship")
            w.save(name)
            gaps_w = detect_gaps(name)
            mike = [g for g in gaps_w if g["entity"] == "Mike"
                    or _norm_node(g.get("entity", "")) == "mike"]
            ok("SUSPECTED: a 42-mention unknown-relationship entity -> SUSPECTED gap",
               len(mike) == 1 and mike[0]["kind"] == SUSPECTED)
            ok("SUSPECTED: a 1-mention entity (Quinn) does NOT clear the mention floor",
               all(_norm_node(g.get("entity", "")) != "quinn" for g in gaps_w))
            ok("PRIORITY: the 42-mention Mike gap OUTRANKS an empty favorite-food slot",
               mike and _score(mike[0]) > max(
                   (_score(g) for g in gaps_w if g["slot"] == "favorite_food"), default=0.0))
            # the question is anchored to Mike, references the mentions, is warm + optional
            mq = generate_question(mike[0]) if mike else ""
            ok("QUESTION relevance: the Mike question NAMES Mike (not canned)",
               "Mike" in mq)
            ok("QUESTION relevance: it asks HOW THEY KNOW each other (contextual)",
               re.search(r"know each other|who (?:they|she|he) (?:are|is)", mq, re.I) is not None)
            ok("QUESTION safety: no scaffold tag, no AI-disclaimer in the Mike question",
               not _looks_unsafe(mq))

            # top of the whole ranking should be Mike (highest signal)
            top_all = detect_gaps(name)[0]
            ok("PRIORITY: Mike is the single top-ranked gap overall",
               _norm_node(top_all.get("entity", "")) == "mike")

            # --- NEVER RE-ASK: after mark_asked(Mike), it's gone from candidates forever ---
            before = candidate_gaps(name)
            ok("never-re-ask: Mike is a candidate BEFORE being asked",
               any(_norm_node(g.get("entity", "")) == "mike" for g in before))
            mark_asked(name, mike[0])
            after = candidate_gaps(name)
            ok("LAW 002 [never-re-ask]: after mark_asked, Mike is NEVER a candidate again",
               all(_norm_node(g.get("entity", "")) != "mike" for g in after))
            # and next_question (deep) never returns the Mike question again
            re_mike = False
            for _ in range(30):
                q = next_question(name, budget="deep")
                if q and "Mike" in q:
                    re_mike = True
                    break
            ok("LAW 002 [next_question]: a deep budget never re-asks the asked Mike gap",
               not re_mike)

            # the Asked Ledger is APPEND-ONLY (Law 001): a second mark adds, never truncates
            n1 = len(ledger_path(name).read_text().splitlines())
            # surface + mark a different gap
            other = next((g for g in candidate_gaps(name)), None)
            if other is not None:
                other["_question"] = generate_question(other)
                mark_asked(name, other)
            n2 = len(ledger_path(name).read_text().splitlines())
            ok("LAW 001 [append-only]: the Asked Ledger grows, never shrinks",
               n2 == n1 + (1 if other is not None else 0) and n2 >= n1)

        # --- QUESTION relevance (generic): generated questions are contextual + clean ---
        for g in detect_gaps(name)[:8]:
            q = generate_question(g)
            if not q:
                continue
            ok(f"relevance: gap '{g['slot']}' question is clean + in-character",
               not _looks_unsafe(q) and len(q) > 0)
        ok("relevance: NO generated question is the banned 'favorite color' canned ask",
           all("favorite color" not in (generate_question(g) or "").lower()
               for g in detect_gaps(name)))

        # --- BUDGET behaviour: minimal returns None MORE OFTEN than deep over a fixed set ---
        # build a fresh creature with a fixed set of gaps and DISTINCT names so the
        # deterministic per-(name,gap) draw varies across the set.
        budget_name = "curio_budget_" + secrets.token_hex(3)
        none_minimal = none_deep = 0
        trials = 60
        for i in range(trials):
            nm = f"{budget_name}_{i}"
            # each gets the same single strong-ish gap shape via a stub: an empty taxonomy
            # creature (no stores) yields the same UNKNOWN gaps; the per-name hash varies.
            qm = next_question(nm, budget="minimal")
            qd = next_question(nm, budget="deep")
            if qm is None:
                none_minimal += 1
            if qd is None:
                none_deep += 1
        ok(f"BUDGET: minimal stays silent more than deep "
           f"(minimal None={none_minimal}/{trials}, deep None={none_deep}/{trials})",
           none_minimal > none_deep)
        ok("BUDGET: deep almost always speaks when a gap exists",
           none_deep <= trials // 5)

        # --- render: an audit surface that shows budget + open gaps + already-asked ---
        rep = render(name)
        ok("render: audit surface shows the budget", "budget:" in rep)
        ok("render: audit surface lists at least one curiosity",
           "would ask:" in rep or "nothing open" in rep)

        # --- entry points never raise on a junk/empty creature ---
        empty = "curio_empty_" + secrets.token_hex(3)
        ok("robust: detect_gaps on a blank creature returns a list",
           isinstance(detect_gaps(empty), list))
        ok("robust: generate_question(None) -> '' (never raises)",
           generate_question(None) == "")
        ok("robust: next_question on a blank creature is a str or None",
           (next_question(empty) is None) or isinstance(next_question(empty), str))
        ok("robust: mark_asked(bad gap) -> None (never raises)",
           mark_asked(empty, None) is None)

    finally:
        # restore stores + nuke the temp dir
        for _m, _old in saved:
            if _old is not None:
                _m.STORE = _old
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
    print("ALL CURIOSITY SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
