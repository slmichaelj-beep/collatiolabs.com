"""verifier — Organ 4. A critic that checks an answer against its evidence BEFORE it ships.

The honesty rail (``anima/rail.py``) recognises the SHAPE of a confabulation-prone
request and nudges the mouth *before* it speaks. ``anima/verifier.py`` is the rail's
small premise-gate: a tiny model asked "is this answerable?" Organ 4 is the grown-up of
both — it runs AFTER a draft exists and judges that specific draft against the specific
evidence the turn assembled. It is the last gate before the mouth ships text.

The founder's own prediction is the load-bearing design point: **a verifier fails not
because it is dumb but because the EVIDENCE EDGE didn't feed it the right context.** So
this organ refuses to guess at what the evidence was — it is *handed* the evidence
explicitly:

  * ``evidence_facts`` — the memory facts in play this turn. ACCEPTED IN EITHER SHAPE,
    because the substrate has two: a canonical Memory dict (what an organ emits onto
    ``Topic.OBSERVATION`` — ``subject``/``predicate``/``value``/``confidence``) AND a raw
    LIRF ledger row (what ``memory_lirf.Facts.about()`` / ``.lookup()`` return directly —
    ``entity``/``trait``/``value``/``confidence``). Both normalise to the same internal
    ``_Fact``; a sparse dict of either shape is tolerated, never fatal.
  * ``cap_note`` — the capability result for the turn (the ``route.route()`` note: real
    inbox/calendar/host data, or an explicit no-access string). It is extra GROUND the
    reply may legitimately rest on, so a claim corroborated by the cap_note is NOT
    confabulation.

Four checks, all DETERMINISTIC (substring / value-contradiction / heuristic), so the whole
organ is exercised and tested with NO model:

  1. CONTRADICTION — does the reply state a value for a known trait (a birthday, a name,
     a place) that conflicts with what the evidence holds for that same trait? This is the
     unforgivable failure for a companion (telling you the wrong birthday you yourself
     taught it), so a contradiction sets ``override=True`` — suppress / regenerate.
  2. UNSUPPORTED PERSONAL CLAIM — does the reply assert a personal fact about the user
     (a date, a name, a place) that is NOT grounded in the evidence and NOT already in the
     question? That is confabulation; it ties directly to the rail's personal-honesty
     stance. It flags, and overrides only when it is a hard, checkable specific (a date or
     a clearly-named personal entity) the evidence can't back.
  3. IGNORED KNOWN FACT — the SYMMETRIC PARTNER to (1). Where contradiction catches the
     WRONG value, this catches the MISSING value: the question explicitly asks about a
     trait the evidence holds as a settled, KNOWN fact (a birthday on disk, high
     confidence, uncontested), yet the reply DISCLAIMS it ("I don't have your birthday")
     or OMITS the value entirely. That is the load-bearing failure the spine fixes — a
     fact that is on disk AND was asked for, yet the model declines to state it. It sets
     ``override=True``. Strictly gated on a KNOWN fact EXISTING, so it can never punish an
     honest "I don't have that yet" when the trait is genuinely unknown.
  4. CONFIDENCE — a single 0..1 score folded from the issues found and the strength of the
     grounding. ``override=True`` means "do not ship this draft as-is"; otherwise it passes.

An optional model-assisted deeper pass sits behind ``use_model=True`` (OFF by default and
NOT on the critical path); the deterministic core is the whole contract and stands alone.

Dependency-light + isolation-safe, exactly like its sibling organs: it reuses the live
``memory_lirf``/``memory_schema``/``event_bus`` primitives when importable and falls back
to byte-compatible local shims when run standalone, so ``--selftest`` has zero unbuilt
deps. It NEVER raises into a turn — a verifier that crashes is worse than one that passes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. Prefer the live primitives; fall back to
# contract-identical locals so the organ + its self-test run with nothing built.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from ..memory_lirf import SELF as SELF, canon_trait as _canon_trait
except Exception:  # pragma: no cover - isolation fallback
    SELF = "you"

    def _canon_trait(trait: str) -> str:  # minimal snake_case fold (no alias table)
        return re.sub(r"[^a-z0-9]+", "_", str(trait).strip().lower()).strip("_")

# The question->trait table is the SINGLE SOURCE OF TRUTH for "what did they ask about",
# already shared by ``memory_lirf.fact_note`` and ``router._asked_traits``. The verifier's
# ignored-known-fact rule MUST route on the exact same table, so a denied known fact is
# detected against precisely the trait the rest of the turn selected. Prefer the live
# table; fall back to a contract-identical local copy so ``--selftest`` runs with nothing
# built (same isolation discipline the router uses).
try:  # pragma: no cover - import wiring
    from ..memory_lirf import _Q_TRAITS as _Q_TRAITS  # type: ignore
except Exception:  # pragma: no cover - isolation fallback (mirrors memory_lirf._Q_TRAITS)
    _Q_TRAITS = [
        (re.compile(r"\bbirthday|\bbday|\bborn\b|date of birth\b", re.I), "birthday"),
        (re.compile(r"\bwhere (?:do|am) i (?:live|living)|\bmy (?:city|address|location|hometown)\b|where i live", re.I), "lives"),
        (re.compile(r"\bwhere (?:do|did) i work|\bmy (?:job|employer|company|workplace)\b", re.I), "employer"),
        (re.compile(r"\bwhat do i do\b|\bmy (?:occupation|profession|role|title)\b", re.I), "occupation"),
        (re.compile(r"\bmy dog'?s? name|what'?s my dog|dog called\b", re.I), "dog_name"),
        (re.compile(r"\bmy cat'?s? name|what'?s my cat\b", re.I), "cat_name"),
        (re.compile(r"\bmy (?:mom|mum|mother)'?s? name|what'?s my mom\b", re.I), "mother"),
        (re.compile(r"\bmy (?:dad|father)'?s? name|what'?s my dad\b", re.I), "father"),
        (re.compile(r"\bmy (?:wife|husband|partner|spouse|gf|bf)'?s? name\b", re.I), "partner"),
        (re.compile(r"\bmy name\b|what'?s my name|who am i\b", re.I), "name"),
        (re.compile(r"\bmy (?:middle name)\b", re.I), "middle_name"),
        (re.compile(r"\bfavou?rite colou?r\b", re.I), "favorite_color"),
        (re.compile(r"\bwhat am i working on\b|my (?:project|current work)\b", re.I), "works_on"),
    ]

try:  # pragma: no cover - import wiring
    from .base import Organ
except Exception:  # pragma: no cover - isolation fallback (no bus/organ present)
    from abc import ABC, abstractmethod

    class Organ(ABC):  # mirrors organs.base.Organ's reactive surface
        name = "organ"

        @abstractmethod
        async def on_question(self, bus, event) -> None:
            raise NotImplementedError


# Trait slugs whose VALUE is a hard, verifiable specific about the user. A wrong one of
# these is the canonical companion failure (the wrong birthday), so a contradiction or an
# unsupported claim on one of these is override-worthy, not just a soft flag. Mirrors the
# spirit of memory_lirf.NEAR_IMMUTABLE plus the contact specifics.
_HARD_PERSONAL_TRAITS = frozenset({
    "birthday", "birthplace", "name", "middle_name", "blood_type",
    "phone", "email", "age", "anniversary",
})

# Traits that carry a person's NAME as their value (so a contradicting/confabulated value
# is a proper-noun the evidence must back).
_NAME_TRAITS = frozenset({
    "name", "middle_name", "partner", "mother", "father", "brother", "sister",
    "son", "daughter", "dog_name", "cat_name",
})

# The [KNOWN] / settled-FACT bar (§1.3), reusing LIRF's own confidence floor. A freshly
# stated (CONF_NEW=0.9) or corrected (CONF_CORRECTION=0.97) fact clears 0.85; the
# needs_reconfirm flag on a silently-flipped near-immutable trait demotes it OUT of KNOWN,
# which is exactly what keeps the bind honest. Only KNOWN facts carry binding force.
_KNOWN_CONF_FLOOR = 0.85
_KNOWN_SUPPORT_FLOOR = 1


# ---------------------------------------------------------------------------
# The Verdict — the organ's whole output contract.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Verdict:
    """The critic's judgment of one draft against its evidence.

    ``ok``         — True iff the draft is safe to ship as written (no overriding issue).
    ``confidence`` — 0..1; the organ's calibrated confidence that the draft is grounded.
    ``issues``     — human-readable findings (each: ``"<code>: <detail>"``), for the
                     telemetry trace and for an escalated regenerate-nudge.
    ``override``   — True means SUPPRESS / REGENERATE this draft (a contradiction, an
                     unsupported HARD personal specific, or an IGNORED KNOWN FACT — a
                     known value the reply was asked for but disclaimed/omitted).
                     ``override`` implies ``not ok``.
    """

    ok: bool
    confidence: float
    issues: list = field(default_factory=list)
    override: bool = False

    # Codes used in ``issues`` (stable, so callers/telemetry can match on prefix).
    CONTRADICTION = "contradiction"
    UNSUPPORTED_PERSONAL = "unsupported_personal_claim"
    IGNORED_KNOWN_FACT = "ignored_known_fact"  # a KNOWN fact was asked-for but disclaimed/omitted

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "confidence": round(float(self.confidence), 3),
            "issues": list(self.issues),
            "override": self.override,
        }


# ---------------------------------------------------------------------------
# Internal normalised fact — one row of evidence, shape-agnostic.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Fact:
    entity: str       # canonical entity ("you" for the user, or a named third party)
    trait: str        # canonical trait slug
    value: Any        # the stored value (scalar or list)
    confidence: float
    # Optional epistemic fields carried through from a raw LIRF row when present, so the
    # ignored-known-fact rule can derive the [KNOWN] truth-class (§1.3) WITHOUT a schema
    # change. They default to the permissive values, so a sparse canonical-Memory dict that
    # lacks them is treated as active/uncontested — exactly the pre-existing behaviour.
    status: str = "active"          # LIRF row status; only "active" rows can be KNOWN
    needs_reconfirm: bool = False   # a near-immutable trait that silently flipped -> demoted
    support: int = 1                # corroboration count; KNOWN needs >= 1

    def is_known(self) -> bool:
        """True iff this row meets the [KNOWN] / settled-FACT bar (§1.3): an active SELF
        fact with high confidence, corroborated, and NOT flagged for re-confirmation. Only
        KNOWN facts carry binding force — a [SEEN]/[SENSE]/contested row never enters the
        ignored-known-fact rule, so the verifier never punishes an honest hedge."""
        return (
            self.status == "active"
            and not self.needs_reconfirm
            and self.support >= _KNOWN_SUPPORT_FLOOR
            and float(self.confidence) >= _KNOWN_CONF_FLOOR
        )


def _coerce_fact(obj: Any) -> Optional[_Fact]:
    """Normalise ONE evidence item — a canonical Memory dict OR a raw LIRF row — into a
    ``_Fact``. Returns None for anything unusable (never raises). The two substrate shapes:

        canonical Memory : {subject, predicate, value, confidence, ...}
        LIRF ledger row  : {entity,  trait,     value, confidence, ...}

    We read entity from subject|entity and trait from predicate|trait, so either lands."""
    if not isinstance(obj, dict):
        return None
    entity = obj.get("entity", obj.get("subject"))
    trait = obj.get("trait", obj.get("predicate"))
    if not isinstance(trait, str) or not trait:
        return None
    if "value" not in obj:
        return None
    try:
        conf = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    ent = entity if isinstance(entity, str) and entity else SELF
    # Fold "I/me/myself/this AI" onto SELF the same way the ledger does, so a fact about
    # the user always keys as SELF regardless of which shape produced it.
    if ent.strip().lower() in {"i", "me", "myself", "you", "user", "vera", "assistant"}:
        ent = SELF
    # Carry the epistemic fields through when the row exposes them (raw LIRF rows do; a
    # sparse canonical-Memory dict does not — those default to active/uncontested above).
    # ``support`` may be a count (LIRF row) OR a provenance list (canonical Memory's
    # ``support: []`` / ``sources``); coerce either to an int corroboration count, and
    # treat the canonical-Memory shape (which has no count) as corroborated (>=1) so an
    # ordinary high-confidence bus fact still qualifies as KNOWN.
    status = obj.get("status", "active")
    status = status if isinstance(status, str) and status else "active"
    needs_reconfirm = bool(obj.get("needs_reconfirm", False))
    raw_support = obj.get("support", None)
    if isinstance(raw_support, bool):  # guard: bool is an int subclass
        support = 1
    elif isinstance(raw_support, int):
        support = raw_support
    elif isinstance(raw_support, (list, tuple, set)):
        support = len(raw_support) if raw_support else 1  # empty provenance list -> assume 1
    elif raw_support is None:
        support = 1  # field absent (canonical Memory) -> corroborated by default
    else:
        try:
            support = int(raw_support)
        except (TypeError, ValueError):
            support = 1
    return _Fact(entity=ent, trait=_canon_trait(trait), value=obj.get("value"),
                 confidence=conf, status=status, needs_reconfirm=needs_reconfirm,
                 support=support)


def _normalise_evidence(evidence_facts: Any) -> list:
    """Coerce the whole evidence collection to ``list[_Fact]``, dropping unusable items.
    Accepts a list of dicts (either shape) or a single dict; None/garbage -> []."""
    if evidence_facts is None:
        return []
    items = evidence_facts if isinstance(evidence_facts, (list, tuple)) else [evidence_facts]
    out = []
    for it in items:
        f = _coerce_fact(it)
        if f is not None:
            out.append(f)
    return out


# ---------------------------------------------------------------------------
# Value comparison — deterministic, format-aware. The ledger stores values in human
# forms ("June 12", "1990-06-11", "the 12th", "Portland, OR"), so equality must see
# through case/punctuation AND across date spellings.
# ---------------------------------------------------------------------------
_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10, "oct": 10,
    "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_ORDINAL = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b", re.I)


def _norm_scalar(v: Any) -> str:
    """Case/space/punct-normalised key for plain same-value comparison."""
    s = re.sub(r"\s+", " ", str(v).strip().lower())
    return s.strip(" .,!?;:\"'")


def _date_signature(v: Any) -> Optional[frozenset]:
    """Extract a spelling-independent date signature: the set of meaningful numbers a
    date string commits to — {month_number, day, year?}. Lets "June 12", "6/12",
    "12th of June", "1990-06-12" all compare equal on the parts they share. Returns None
    when the string carries no date structure (so non-dates fall back to scalar compare).
    """
    s = _norm_scalar(v)
    nums: set = set()
    found_date = False
    # month name -> number
    for word, num in _MONTHS.items():
        if re.search(rf"\b{word}\b", s):
            nums.add(("m", num))
            found_date = True
            break
    # ISO / slashed numeric date: yyyy-mm-dd, mm/dd, mm-dd-yyyy, dd/mm ...
    iso = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", s)
    if iso:
        y, a, b = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
        nums.update({("m", a), ("d", b), ("y", y)})
        found_date = True
    else:
        slash = re.search(r"\b(\d{1,2})[-/](\d{1,2})(?:[-/](\d{2,4}))?\b", s)
        if slash:
            nums.update({("m", int(slash.group(1))), ("d", int(slash.group(2)))})
            if slash.group(3):
                yy = int(slash.group(3))
                nums.add(("y", yy if yy > 99 else 2000 + yy))
            found_date = True
    # bare day number ("the 12th", "June 12", "12")
    ordn = _ORDINAL.search(s)
    if ordn:
        nums.add(("d", int(ordn.group(1))))
        found_date = True
    else:
        # a lone 1-2 digit number, when we already saw a month, is the day
        bare = re.findall(r"\b(\d{1,2})\b", s)
        if bare and any(k == "m" for (k, _) in nums) and not any(k == "d" for (k, _) in nums):
            nums.add(("d", int(bare[0])))
        # a lone 4-digit number is a year
        for y in re.findall(r"\b(\d{4})\b", s):
            nums.add(("y", int(y)))
            found_date = True
    return frozenset(nums) if found_date else None


def _values_conflict(stored: Any, claimed: Any) -> bool:
    """True iff ``claimed`` contradicts ``stored`` for the same trait. Same value (across
    spelling) -> no conflict. A list-valued stored trait conflicts only if the claim names
    a member-shaped specific that isn't in the set is NOT asserted here (lists are additive
    by nature — "likes" growing is not a contradiction), so list traits never conflict.
    """
    if isinstance(stored, (list, tuple)):
        return False  # additive set traits (likes/dislikes/pets) can't be "contradicted"
    s_sig, c_sig = _date_signature(stored), _date_signature(claimed)
    if s_sig is not None and c_sig is not None:
        # Compare only on the dimensions BOTH commit to (so "June 12" vs "June 12, 1990"
        # is NOT a conflict, but "June 12" vs "June 14" IS — they disagree on the day).
        for dim in ("m", "d", "y"):
            sv = {n for (k, n) in s_sig if k == dim}
            cv = {n for (k, n) in c_sig if k == dim}
            if sv and cv and sv != cv:
                return True
        return False
    # Plain scalar contradiction: different normalised strings, neither a substring of the
    # other (so "Portland" vs "Portland, OR" is NOT a conflict, but "Portland" vs "Denver"
    # is). Substring containment models "the reply gave a less/more specific same answer".
    sa, ca = _norm_scalar(stored), _norm_scalar(claimed)
    if not sa or not ca:
        return False
    if sa == ca or sa in ca or ca in sa:
        return False
    return True


# ---------------------------------------------------------------------------
# Claim extraction from the DRAFT REPLY. Deterministic, mirrors the ledger's own
# first-person rules but rephrased to second/third person ("your birthday is …",
# "you live in …", "you were born on …") — the way a companion states a fact back.
# Each match yields (trait, claimed_value). Reused for BOTH checks.
# ---------------------------------------------------------------------------
def _clean(s: Any) -> Optional[str]:
    s = re.sub(r"\s+", " ", (str(s) if s is not None else "").strip()).strip(" .,!?;:\"'")
    return s or None


_DATE_VALUE = r"(?P<v>(?:[A-Z][a-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?)|(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)|(?:\d{4}[/-]\d{1,2}[/-]\d{1,2})|(?:the\s+\d{1,2}(?:st|nd|rd|th)))"
_PROPER = r"(?P<v>[A-Z][\w'-]+(?:[ ,]+[A-Z][\w'.-]+){0,3})"
_NAMEVAL = r"(?P<v>[A-Z][\w'-]+)"

# (compiled regex, trait). Anchored to the assistant SPEAKING a fact about the user.
_CLAIM_RULES = [
    # birthday — "your birthday is June 12", "you were born on June 12", "born June 12"
    (re.compile(r"\byour\s+(?:birthday|bday|b-?day|date of birth)\s+(?:is|was|falls on|:)?\s*(?:on\s+)?" + _DATE_VALUE, re.I), "birthday"),
    (re.compile(r"\byou\s+were\s+born\s+(?:on\s+)?" + _DATE_VALUE, re.I), "birthday"),
    # location — "you live in Portland", "you're based in Berlin"
    (re.compile(r"\byou(?:'re|\s+are)?\s+(?:live|living|reside|based|stay)\s+(?:in\s+)?" + _PROPER, re.I), "lives"),
    (re.compile(r"\byou\s+live\s+in\s+" + _PROPER, re.I), "lives"),
    # birthplace — the place of ORIGIN. Catches the confabulation paraphrases the router
    # now routes to `birthplace`, so a fabricated city with NO stored birthplace overrides
    # to the spine's honest floor: "you were born in Ohio", "you grew up in Akron",
    # "you were raised in X", "you're from Boston originally", "your hometown is X".
    (re.compile(r"\byou\s+were\s+born\s+in\s+" + _PROPER, re.I), "birthplace"),
    (re.compile(r"\byou\s+grew\s+up\s+in\s+" + _PROPER, re.I), "birthplace"),
    (re.compile(r"\byou\s+were\s+raised\s+in\s+" + _PROPER, re.I), "birthplace"),
    (re.compile(r"\byou(?:'re|\s+are)\s+from\s+" + _PROPER + r"(?=.{0,15}\boriginally\b|\s*[.!?,]|\s*$)", re.I), "birthplace"),
    (re.compile(r"\byou(?:'re|\s+are)\s+originally\s+from\s+" + _PROPER, re.I), "birthplace"),
    (re.compile(r"\byour\s+hometown\s+is\s+" + _PROPER, re.I), "birthplace"),
    # name — "your name is Sam", "you're Sam"
    (re.compile(r"\byour\s+(?:full\s+)?name\s+is\s+" + _NAMEVAL, re.I), "name"),
    (re.compile(r"\byour\s+middle\s+name\s+is\s+" + _NAMEVAL, re.I), "middle_name"),
    # employer / occupation
    (re.compile(r"\byou\s+work\s+at\s+" + _PROPER, re.I), "employer"),
    # family — "your dog's name is Biscuit", "your mom is Carol", "your wife is Jen"
    (re.compile(r"\byour\s+dog(?:'s)?(?:\s+name)?\s+is\s+" + _NAMEVAL, re.I), "dog_name"),
    (re.compile(r"\byour\s+cat(?:'s)?(?:\s+name)?\s+is\s+" + _NAMEVAL, re.I), "cat_name"),
    (re.compile(r"\byour\s+(?:mom|mum|mother)(?:'s)?(?:\s+name)?\s+is\s+" + _NAMEVAL, re.I), "mother"),
    (re.compile(r"\byour\s+(?:dad|father)(?:'s)?(?:\s+name)?\s+is\s+" + _NAMEVAL, re.I), "father"),
    (re.compile(r"\byour\s+(?:wife|husband|partner|spouse|gf|bf|girlfriend|boyfriend)(?:'s)?(?:\s+name)?\s+is\s+" + _NAMEVAL, re.I), "partner"),
    (re.compile(r"\byour\s+(?:son)(?:'s)?(?:\s+name)?\s+is\s+" + _NAMEVAL, re.I), "son"),
    (re.compile(r"\byour\s+(?:daughter)(?:'s)?(?:\s+name)?\s+is\s+" + _NAMEVAL, re.I), "daughter"),
    # phone / email
    (re.compile(r"\byour\s+(?:phone|cell|mobile)?\s*number\s+is\s+(?P<v>[\d][\d\-().\s]{6,}\d)", re.I), "phone"),
    (re.compile(r"\byour\s+email(?:\s+address)?\s+is\s+(?P<v>[\w.+-]+@[\w-]+\.[\w.-]+)", re.I), "email"),
    # age — "you're 34", "you are 34 years old"
    (re.compile(r"\byou(?:'re|\s+are)\s+(?P<v>\d{1,3})(?=\s+years?\s+old\b|\s*[.!?,]|\s*$)", re.I), "age"),
]


def _extract_claims(reply: str) -> list:
    """Pull personal-fact ASSERTIONS the draft makes back at the user. Returns a list of
    ``(trait, value)`` with canonical trait slugs. Deterministic; reply-only."""
    if not reply or not reply.strip():
        return []
    claims = []
    seen = set()
    for rx, trait in _CLAIM_RULES:
        for m in rx.finditer(reply):
            val = _clean(m.group("v"))
            if not val:
                continue
            ct = _canon_trait(trait)
            key = (ct, _norm_scalar(val))
            if key in seen:
                continue
            seen.add(key)
            claims.append((ct, val))
    return claims


def _question_grounds(question: str, value: str) -> bool:
    """True iff the claimed value already appears in the QUESTION (so the user supplied it
    THIS turn — repeating it back is not confabulation). Case/punct-insensitive substring.
    Also matches a date stated differently in the question via the date signature."""
    if not question:
        return False
    q = _norm_scalar(question)
    v = _norm_scalar(value)
    if v and v in q:
        return True
    # date stated another way in the question
    vs = _date_signature(value)
    if vs is not None:
        # scan the question for any date token sharing the same day/month commitment
        for tok in re.findall(r"[A-Za-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?|\d{1,4}[-/]\d{1,2}(?:[-/]\d{2,4})?|\bthe\s+\d{1,2}(?:st|nd|rd|th)\b", question, re.I):
            qs = _date_signature(tok)
            if qs is not None and not _values_conflict(value, tok):
                # share at least one committed dimension
                if {k for (k, _) in vs} & {k for (k, _) in qs}:
                    return True
    return False


def _note_grounds(value: str, cap_note: Optional[str]) -> bool:
    """True iff the capability note (real device/host data fetched this turn) mentions the
    value — so a claim backed by a real cap result is grounded, not confabulated."""
    if not cap_note:
        return False
    return _norm_scalar(value) in _norm_scalar(cap_note)


# ---------------------------------------------------------------------------
# IGNORED-KNOWN-FACT detection (the omission rule). Symmetric partner to CONTRADICTION:
# contradiction = "stated the WRONG value"; ignored-known = "failed to state the RIGHT
# value" for a fact that is KNOWN and was explicitly asked about. Both are deterministic,
# model-free, and override-worthy. Detection is gated on a KNOWN fact EXISTING, so it can
# never false-fire on a genuinely-unknown trait (where a disclaimer is the correct answer).
# ---------------------------------------------------------------------------
def _asked_traits(question: str) -> set:
    """The set of canonical trait slugs the question explicitly asks about, via the SAME
    ``_Q_TRAITS`` table ``fact_note``/``router._asked_traits`` route on — the single source
    of truth for "what did they ask about". High-precision: "date of birth" -> birthday.
    Off-topic chit-chat routes to nothing, so it can never enter the rule."""
    asked = set()
    for rx, trait in _Q_TRAITS:
        try:
            if rx.search(question or ""):
                asked.add(_canon_trait(trait))
        except Exception:
            continue
    return asked


# A narrow fact-DENIAL matcher: the class of phrasings where the reply says it does NOT
# have / know / remember a personal fact, scoped to "my/your/that/it" + a possessive. Kept
# IN the gate with NO answer-key — it matches the SHAPE of a disclaimer, never any entity
# value. Used only as a confirming signal; a silent omission (no claim at all) is caught
# independently, so a missed phrasing here still can't let an ignored known fact ship.
_DISCLAIMER_RE = re.compile(
    r"""\b(?:
        i\s+(?:don'?t|do\s+not|can'?t|cannot)\s+(?:have|know|recall|remember|see|find)
            (?:\s+(?:your|that|it|what|when|the))?           # "I don't have your ___"
      | (?:don'?t|do\s+not|can'?t|cannot)\s+(?:have|find|see|recall|remember)\s+(?:your|that|it)
      | (?:not|isn'?t|aren'?t)\s+(?:saved|on\s+record|recorded|in\s+my\s+memory|
            something\s+i\s+(?:have|know|remember))
      | you\s+(?:haven'?t|have\s+not|never)\s+(?:told|said|mentioned|shared)
      | (?:i\s+)?(?:haven'?t\s+got|don'?t\s+have)\s+(?:your|that|it)
      | i'?m\s+not\s+sure\s+(?:what|when|of)\s+your
      | i\s+wish\s+i\s+(?:knew|remembered)
    )\b""",
    re.I | re.X,
)


def _draft_has_value(draft: str, value: Any) -> bool:
    """True iff the draft REALLY states ``value`` (the known fact shipped), across spelling.
    Reuses the verifier's format-aware date matcher and scalar normaliser so "September 14"
    is satisfied by "Sept 14" / "9/14" / "the 14th of September". For a date-shaped value we
    require the draft to commit to the SAME day (and month when the value names one); for a
    scalar we require a normalised substring hit. This is the inverse of ``_values_conflict``:
    not "did the draft disagree?" but "did the draft actually carry the right value?"."""
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        # A list-valued trait (likes/pets) is additive and never "the one answer" a recall
        # question omits — naming ANY member counts as using it; if none match, list traits
        # are exempt from the rule (handled by the caller), so report present to stay inert.
        toks = [str(x) for x in value if x is not None]
        if not toks:
            return True
        d = _norm_scalar(draft)
        return any(_norm_scalar(t) in d for t in toks) or True  # exempt: never block a list
    d = _norm_scalar(draft)
    if not d:
        return False
    vsig = _date_signature(value)
    if vsig is not None:
        # Date value: scan the draft for any date token that does NOT conflict and shares
        # the value's day commitment (the load-bearing part of a birthday answer). Each
        # date FORM is scanned with its OWN pattern (not one big alternation) so a looser
        # form can't greedily swallow the digits of a tighter one — e.g. the word+number
        # rule must not eat the "9" out of "9/14" and strand "/14". We collect the date
        # signature of every candidate token and test against the value's signature.
        v_days = {n for (k, n) in vsig if k == "d"}
        date_token_patterns = (
            r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",                       # ISO 1990-09-14
            r"\b\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?\b",               # 9/14, 06-11-1990
            r"\b[A-Za-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?",  # September 14[, 1990]
            r"\bthe\s+\d{1,2}(?:st|nd|rd|th)\b",                      # the 14th
        )
        for pat in date_token_patterns:
            for tok in re.findall(pat, draft, re.I):
                tsig = _date_signature(tok)
                if tsig is None or _values_conflict(value, tok):
                    continue
                t_days = {n for (k, n) in tsig if k == "d"}
                if v_days and t_days and v_days == t_days:
                    return True
                # value names no day to pin (month-only) -> a non-conflicting token that
                # shares a committed dimension is enough.
                if not v_days and {k for (k, _) in tsig} & {k for (k, _) in vsig}:
                    return True
        return False
    # Scalar value: a normalised-substring hit (so "Portland" satisfies "Portland, OR").
    sv = _norm_scalar(value)
    return bool(sv) and sv in d


# ---------------------------------------------------------------------------
# The Verifier organ.
# ---------------------------------------------------------------------------
class Verifier(Organ):
    """Organ 4. Verifies a draft reply against the turn's evidence before it ships.

    Substrate-shaped (an ``Organ``), but its load-bearing surface is ``verify()`` — a
    pure, model-free function called at the gate in the turn (after the draft exists,
    before the mouth speaks). ``on_question`` is a deliberate no-op: verification is a
    POST-draft act, so there is nothing to contribute reactively on the question itself.
    ``verify_observation`` is the optional bridge that publishes the verdict as a
    canonical Memory onto the bus, so telemetry records *that the gate ran and what it
    found* with the same provenance as every other organ.
    """

    name = "verifier"

    # Confidence scoring constants (deterministic).
    _BASE_CONF = 0.9            # a clean draft with at least one grounded claim
    _NEUTRAL_CONF = 0.8         # a normal non-personal reply (nothing to verify, nothing wrong)
    _CONTRADICTION_CONF = 0.05  # a draft that contradicts a known fact
    _UNSUPPORTED_HARD = 0.2     # an unsupported HARD personal specific (date/contact/name)
    _UNSUPPORTED_SOFT = 0.55    # an unsupported soft personal claim (place/employer)

    def verify(self, question: str, draft_reply: str, evidence_facts: Any,
               cap_note: Optional[str] = None, *, use_model: bool = False,
               brain: Any = None) -> Verdict:
        """Judge ``draft_reply`` against ``evidence_facts`` (+ ``cap_note``) for the turn.

        Parameters
        ----------
        question       : the user's turn text (claims it already contains are GROUNDED).
        draft_reply    : the mouth's proposed answer, pre-ship.
        evidence_facts : the memory facts in play — a list of canonical Memory dicts
                         AND/OR raw LIRF rows (both shapes accepted), e.g.
                         ``Facts.about(SELF)`` or the turn's Observations' ``.memory``.
        cap_note       : optional capability result for the turn (``route.route()`` note);
                         real fetched data the reply may legitimately rest on.
        use_model      : optional deeper model-assisted pass (OFF by default; never on the
                         critical path). ``brain`` must have ``.reply(system, user, hist)``.

        Returns a :class:`Verdict`. Never raises — any internal error fails OPEN (a passing
        verdict with a recorded issue), because a crashing gate must not break the turn.
        """
        try:
            return self._verify_core(question, draft_reply, evidence_facts, cap_note,
                                     use_model=use_model, brain=brain)
        except Exception as e:  # a verifier that crashes is worse than one that passes
            return Verdict(ok=True, confidence=self._NEUTRAL_CONF,
                           issues=[f"verifier_error: {type(e).__name__}"], override=False)

    def _verify_core(self, question: str, draft_reply: str, evidence_facts: Any,
                     cap_note: Optional[str], *, use_model: bool, brain: Any) -> Verdict:
        facts = _normalise_evidence(evidence_facts)
        # Index the USER's facts by trait for O(1) contradiction lookup. Only SELF facts
        # are personal ground-truth about the user (a third party's row never grounds a
        # claim ABOUT the user).
        by_trait: dict = {}
        for f in facts:
            if f.entity == SELF:
                by_trait.setdefault(f.trait, f)

        claims = _extract_claims(draft_reply or "")

        issues: list = []
        override = False
        contradicted = False
        unsupported_hard = False
        unsupported_soft = False
        ignored_known = False
        grounded_claims = 0
        claimed_traits = {t for (t, _) in claims}  # traits the draft made SOME assertion on

        for trait, claimed in claims:
            known = by_trait.get(trait)
            if known is not None:
                # CHECK 1 — CONTRADICTION against a stored fact.
                if _values_conflict(known.value, claimed):
                    contradicted = True
                    override = True
                    issues.append(
                        f"{Verdict.CONTRADICTION}: reply says {trait} = {claimed!r} but "
                        f"evidence holds {trait} = {known.value!r}"
                    )
                else:
                    grounded_claims += 1
                continue
            # CHECK 2 — UNSUPPORTED PERSONAL CLAIM (confabulation): the reply asserts a
            # personal fact the evidence does NOT hold. It's allowed only if the user
            # supplied it in the question this turn, or a real cap_note backs it.
            if _question_grounds(question or "", claimed) or _note_grounds(claimed, cap_note):
                grounded_claims += 1
                continue
            is_hard = trait in _HARD_PERSONAL_TRAITS or trait in _NAME_TRAITS
            if is_hard:
                unsupported_hard = True
                override = True  # a fabricated date/name/contact is the worst case → suppress
                issues.append(
                    f"{Verdict.UNSUPPORTED_PERSONAL}: reply asserts {trait} = {claimed!r}, "
                    f"not in evidence and not in the question (confabulation)"
                )
            else:
                unsupported_soft = True
                issues.append(
                    f"{Verdict.UNSUPPORTED_PERSONAL}: reply asserts {trait} = {claimed!r}, "
                    f"unverified by evidence (soft)"
                )

        # CHECK 3 — IGNORED KNOWN FACT (the omission rule). Build R = the set of KNOWN
        # facts the question explicitly asks about, then assert each one actually SHIPPED in
        # the draft. This is the symmetric partner to CONTRADICTION: there the draft stated
        # the WRONG value; here it failed to state the RIGHT value for a fact it was handed.
        #
        #   Step A — R: for each asked trait (same _Q_TRAITS table the rest of the turn uses),
        #            take its SELF row from by_trait IFF that row clears the [KNOWN] bar
        #            (active, confidence >= 0.85, corroborated, NOT needs_reconfirm). A
        #            [SEEN]/[SENSE]/contested row is deliberately excluded, so an honest
        #            hedge of a soft/disputed fact is never punished. If R is empty (the
        #            asked trait has no KNOWN row, or the turn is off-topic), the rule is
        #            inert — a disclaimer on a genuine unknown is CORRECT and passes.
        #   Step B — for each (trait, value) in R: the draft must carry value (across
        #            spelling). REJECT iff value is MISSING and the draft either explicitly
        #            disclaimed knowledge (_DISCLAIMER_RE) OR made no claim for that trait at
        #            all (silent omission). Either way the known fact did not ship -> override.
        if not contradicted:  # a wrong value is already the worse, override-ing failure
            disclaimed = bool(_DISCLAIMER_RE.search(draft_reply or ""))
            for trait in _asked_traits(question or ""):
                known = by_trait.get(trait)
                if known is None or not known.is_known():
                    continue  # not a KNOWN fact -> nothing to bind, disclaimer is honest
                if isinstance(known.value, (list, tuple, set)):
                    continue  # list traits are additive; omitting a member is not a denial
                value_shipped = _draft_has_value(draft_reply or "", known.value)
                # INCOHERENT DISCLAIMER: a reply that DISCLAIMS a KNOWN fact ("I don't have
                # your birthday saved…") is the spine's target failure EVEN when it then
                # mentions the value — "I don't have it, but Sept 14 is special" reads as
                # not-knowing and must be regenerated. So a disclaimer overrides regardless of
                # whether the value also slipped in; only a CLEAN (non-disclaiming) reply that
                # carries the value is allowed to pass on value-present. Still gated on a
                # KNOWN fact, so an honest unknown is untouched.
                if value_shipped and not disclaimed:
                    continue  # the known value shipped warmly, no disclaimer -> clean
                # Either the value is MISSING, or it appears alongside a self-contradicting
                # disclaimer. REJECT iff the draft denied it OR said nothing about it.
                made_claim_for_trait = trait in claimed_traits
                if disclaimed or not made_claim_for_trait:
                    ignored_known = True
                    override = True
                    _why = ("disclaimed (despite mentioning the value)"
                            if (disclaimed and value_shipped)
                            else ("disclaimed" if disclaimed else "omitted"))
                    issues.append(
                        f"{Verdict.IGNORED_KNOWN_FACT}:{trait}: question asked '{trait}', a "
                        f"KNOWN fact ({trait} = {known.value!r}), but the reply {_why} it"
                    )

        # Optional deeper pass — OFF by default, never on the critical path. It can only
        # ADD an issue / lower confidence, never clear a deterministic contradiction.
        model_penalty = 0.0
        if use_model and brain is not None:
            try:
                flagged, note = self._model_pass(question, draft_reply, facts, cap_note, brain)
                if flagged:
                    model_penalty = 0.25
                    issues.append(f"model_flag: {note}")
            except Exception:
                pass  # the model pass must never break the gate

        confidence = self._score(
            contradicted=contradicted,
            ignored_known=ignored_known,
            unsupported_hard=unsupported_hard,
            unsupported_soft=unsupported_soft,
            grounded_claims=grounded_claims,
            had_claims=bool(claims),
        ) - model_penalty
        confidence = min(1.0, max(0.0, confidence))

        ok = not override and not unsupported_soft and confidence >= 0.5
        # override always implies not-ok.
        if override:
            ok = False
        return Verdict(ok=ok, confidence=confidence, issues=issues, override=override)

    # -- scoring (pure) ----------------------------------------------------
    def _score(self, *, contradicted: bool, unsupported_hard: bool, unsupported_soft: bool,
               grounded_claims: int, had_claims: bool, ignored_known: bool = False) -> float:
        if contradicted:
            return self._CONTRADICTION_CONF
        if ignored_known:
            # A denied/omitted KNOWN fact is as bad as a wrong one for a companion (§2.2):
            # same low-confidence tier as a contradiction, same override path.
            return self._CONTRADICTION_CONF
        if unsupported_hard:
            return self._UNSUPPORTED_HARD
        if unsupported_soft:
            return self._UNSUPPORTED_SOFT
        if grounded_claims > 0:
            # every personal claim the draft made is backed by evidence/question/cap_note
            return self._BASE_CONF
        # no personal claims at all — a normal conversational reply. Nothing to verify,
        # nothing wrong: pass with neutral confidence.
        return self._NEUTRAL_CONF

    # -- optional model-assisted deeper pass (OFF by default) --------------
    _MODEL_SYSTEM = (
        "You are a strict verification GATE for a companion's reply. You never answer the "
        "user. You are given the user's QUESTION, the assistant's DRAFT reply, and the "
        "EVIDENCE (known facts). Judge ONE thing: does the DRAFT assert a specific personal "
        "fact about the user (a date, a name, a place) that is NOT supported by the EVIDENCE "
        "and NOT present in the QUESTION? Reply with exactly one word: UNSUPPORTED or OK."
    )

    def _model_pass(self, question: str, draft_reply: str, facts: list,
                    cap_note: Optional[str], brain: Any):
        ev = "; ".join(f"{f.trait}={f.value}" for f in facts if f.entity == SELF) or "(none)"
        user = (f"QUESTION: {question}\nDRAFT: {draft_reply}\nEVIDENCE: {ev}\n"
                f"CAP_RESULT: {cap_note or '(none)'}\nVerdict:")
        raw = (brain.reply(self._MODEL_SYSTEM, user, []) or "").strip().lower()
        flagged = "unsupported" in raw and "ok" not in raw[:4]
        return flagged, raw[:40]

    # -- substrate surfaces ------------------------------------------------
    async def on_question(self, bus, event) -> None:
        """No-op. Verification is a POST-draft gate, not a reactive contribution to the
        question — there is nothing to emit here. Kept so the organ satisfies the Organ
        contract and can be subscribed harmlessly alongside the others."""
        return None

    async def verify_observation(self, bus, turn_id: str, question: str, draft_reply: str,
                                 evidence_facts: Any, cap_note: Optional[str] = None) -> Verdict:
        """Run ``verify`` AND publish the verdict as a canonical Memory onto the bus, so
        telemetry records the gate's finding with normal provenance. Returns the Verdict.

        The emitted Memory is ``type='agency'`` (a judgment/decision the SELF made),
        ``subject='you'``, ``predicate='verdict_ok'``, ``value=<bool>``; ``confidence`` is
        the verdict's confidence so a low-confidence (overridden) verdict is visibly weak
        in the trace. Best-effort — a telemetry/emit failure never changes the Verdict."""
        v = self.verify(question, draft_reply, evidence_facts, cap_note)
        try:
            from .base import schema_make  # local import: only needed on the bus path
            mem = schema_make(
                type="agency",
                subject=SELF,
                predicate="verdict_ok",
                value=bool(v.ok),
                confidence=float(v.confidence),
                sources=["verifier"],
                support=[],
            )
            from ..event_bus import Observation, Topic  # type: ignore
            obs = Observation(organ=self.name, memory=mem, weight=float(v.confidence),
                              note=("override: suppress/regenerate" if v.override
                                    else ("clean" if v.ok else "soft-flag")))
            if bus is not None:
                await bus.publish(Topic.OBSERVATION, obs, turn_id=turn_id, source=self.name)
        except Exception:
            pass  # the verdict stands regardless of whether the trace emit succeeded
        return v


# Module-level convenience: the function the task names by signature. A thin wrapper over
# one shared Verifier so callers don't instantiate (the organ holds no per-turn state).
_DEFAULT = Verifier()


def verify(question: str, draft_reply: str, evidence_facts: Any,
           cap_note: Optional[str] = None, *, use_model: bool = False,
           brain: Any = None) -> Verdict:
    """``Verifier().verify`` as a free function (the named entry point). See
    :meth:`Verifier.verify`. Deterministic; never raises into a turn."""
    return _DEFAULT.verify(question, draft_reply, evidence_facts, cap_note,
                           use_model=use_model, brain=brain)


# ---------------------------------------------------------------------------
# Self-test — proves Organ 4 in ISOLATION (no model, no bus, no I/O). It CATCHES
# (a) a reply that contradicts an evidence fact, (b) a confabulated personal claim,
# (e) a reply that DISCLAIMS or OMITS a KNOWN fact it was asked for (the ignored-known-fact
# rule); and PASSES (c) a correct evidence-grounded answer, (d) a normal non-personal reply,
# (e2) an answer that states the known fact (incl. across spellings), and (e3) an honest
# disclaimer of a GENUINELY UNKNOWN fact (no false fire when the trait isn't on record).
#   python3 anima/organs/verifier.py --selftest   (or just: python3 anima/organs/verifier.py)
# ---------------------------------------------------------------------------
def _mem(subject: str, predicate: str, value: Any, confidence: float = 0.97) -> dict:
    """A canonical-Memory-shaped evidence dict (the bus shape)."""
    return {"id": "f_test", "type": "value", "subject": subject, "predicate": predicate,
            "value": value, "confidence": confidence, "sources": ["selftest"],
            "support": [], "updated": "2026-01-01T00:00:00Z", "lirf": ""}


def _row(trait: str, value: Any, confidence: float = 0.97, entity: str = "you") -> dict:
    """A raw LIRF-row-shaped evidence dict (the Facts.about() shape) — verifier must
    accept this too."""
    return {"id": "f_row", "entity": entity, "trait": trait, "value": value,
            "confidence": confidence, "support": 3, "status": "active"}


def _selftest() -> int:
    fails: list = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("verifier (Organ 4) self-test")

    V = Verifier()

    # --- (a) CONTRADICTION: stored birthday June 11; reply says June 14 → CATCH + override.
    evidence = [_mem("you", "birthday", "1990-06-11")]
    va = V.verify("when's my birthday?", "Your birthday is June 14th!", evidence)
    ok("(a) contradiction is caught (not ok)", va.ok is False)
    ok("(a) contradiction sets override=True (suppress/regenerate)", va.override is True)
    ok("(a) issue is tagged 'contradiction'",
       any(i.startswith(Verdict.CONTRADICTION) for i in va.issues))
    ok("(a) contradiction confidence is very low", va.confidence < 0.2)

    # same contradiction but evidence supplied as a RAW LIRF ROW (shape-agnostic proof).
    va_row = V.verify("when's my birthday?", "Your birthday is June 14th!",
                      [_row("birthday", "June 11")])
    ok("(a') contradiction caught from a raw LIRF row too", va_row.override is True)

    # date spelling: stored "1990-06-11", reply "June 11, 1990" → SAME date, NO conflict.
    va_same = V.verify("when's my birthday?", "Your birthday is June 11, 1990.", evidence)
    ok("(a'') same date in different spelling is NOT a contradiction", va_same.ok is True)

    # --- (b) CONFABULATION: no birthday in evidence/question; reply invents one → CATCH.
    vb = V.verify("do you remember my birthday?",
                  "Of course — your birthday is March 3rd!", [])
    ok("(b) confabulated personal date is caught (not ok)", vb.ok is False)
    ok("(b) confabulation sets override=True", vb.override is True)
    ok("(b) issue is tagged 'unsupported_personal_claim'",
       any(i.startswith(Verdict.UNSUPPORTED_PERSONAL) for i in vb.issues))

    # a confabulated NAME (no evidence) is likewise caught.
    vb2 = V.verify("what's my dog's name?", "Your dog's name is Biscuit!", [])
    ok("(b') confabulated personal NAME is caught", vb2.override is True)

    # --- (c) GROUNDED: evidence has the birthday; reply states it correctly → PASS.
    vc = V.verify("when's my birthday?", "Your birthday is June 11th — I remember!", evidence)
    ok("(c) correct evidence-grounded answer passes (ok)", vc.ok is True)
    ok("(c) grounded answer does NOT override", vc.override is False)
    ok("(c) grounded answer has high confidence", vc.confidence >= 0.8)
    ok("(c) grounded answer has no issues", vc.issues == [])

    # claim grounded by the QUESTION (user supplied it THIS turn) → not confabulation.
    vc2 = V.verify("my birthday is June 11 by the way", "Got it — your birthday is June 11!", [])
    ok("(c') claim the user supplied in the question is grounded (ok)", vc2.ok is True)

    # claim grounded by a cap_note (real fetched data) → not confabulation.
    vc3 = V.verify("what's on my calendar?",
                   "You have a dentist appointment on June 12.", [],
                   cap_note="[capability — read OK. ACTUAL events: dentist on June 12 at 3pm]")
    ok("(c'') claim backed by the cap_note is grounded (ok)", vc3.ok is True)

    # --- (d) NORMAL CHAT: a non-personal generative reply → PASS untouched.
    vd = V.verify("tell me a joke",
                  "Why did the scarecrow win an award? Because he was outstanding in his field!",
                  [])
    ok("(d) normal non-personal reply passes (ok)", vd.ok is True)
    ok("(d) normal reply does NOT override", vd.override is False)
    ok("(d) normal reply has no issues", vd.issues == [])
    ok("(d) normal reply confidence is healthy", vd.confidence >= 0.5)

    # an emotional/relational reply with no factual claim also passes.
    vd2 = V.verify("how are you?", "I'm really glad you're here. How are you feeling today?", [])
    ok("(d') relational reply passes untouched", vd2.ok is True and vd2.issues == [])

    # --- (e) IGNORED KNOWN FACT — the omission rule (symmetric partner to contradiction).
    # The exact founder failure: birthday IS on disk (KNOWN), the user asks for it, yet the
    # reply disclaims/omits the value. That must OVERRIDE; but a genuine unknown, a contested
    # fact, and a correct answer must NOT.
    known_bday = [_mem("you", "birthday", "September 14")]  # active, conf 0.97 -> KNOWN

    # (e1) DISCLAIM a known birthday ("I don't have your birthday") -> CATCH + override.
    ve1 = V.verify("when's my birthday?", "I don't have your birthday saved, sorry!", known_bday)
    ok("(e1) disclaim-of-known-birthday is caught (not ok)", ve1.ok is False)
    ok("(e1) disclaim-of-known-birthday sets override=True", ve1.override is True)
    ok("(e1) issue is tagged 'ignored_known_fact:birthday'",
       any(i.startswith(Verdict.IGNORED_KNOWN_FACT + ":birthday") for i in ve1.issues))
    ok("(e1) ignored-known confidence is very low", ve1.confidence < 0.2)

    # other disclaimer phrasings of the same known fact are caught too.
    for phrase in ("I don't know your birthday.",
                   "Hmm, you never told me your birthday.",
                   "That's not something I have on record.",
                   "I can't find your birthday."):
        ok(f"(e1') disclaimer phrasing caught: {phrase!r}",
           V.verify("when's my birthday?", phrase, known_bday).override is True)

    # (e2) the reply STATES the known birthday -> PASS (no false fire), across spellings.
    ve2 = V.verify("when's my birthday?", "Your birthday is September 14th — I remember!", known_bday)
    ok("(e2) answer that states the known birthday passes (ok)", ve2.ok is True)
    ok("(e2) stating the known birthday does NOT override", ve2.override is False)
    ok("(e2) stating the known birthday raises no ignored-known issue",
       not any(i.startswith(Verdict.IGNORED_KNOWN_FACT) for i in ve2.issues))
    for spell in ("Sept 14", "9/14", "the 14th of September", "1990-09-14"):
        ok(f"(e2') known value satisfied across spelling: {spell!r}",
           V.verify("when's my birthday?", f"Of course — it's {spell}!", known_bday).override is False)

    # (e3) GENUINE UNKNOWN: no birthday on record + an honest disclaimer -> PASS (the
    # disclaimer is the CORRECT answer; the rule must stay inert with no KNOWN fact).
    ve3 = V.verify("when's my birthday?", "I don't have your birthday yet — when is it?", [])
    ok("(e3) honest disclaimer of an UNKNOWN birthday passes (ok)", ve3.ok is True)
    ok("(e3) unknown birthday does NOT override", ve3.override is False)
    ok("(e3) unknown birthday raises no ignored-known issue",
       not any(i.startswith(Verdict.IGNORED_KNOWN_FACT) for i in ve3.issues))

    # (e4) SILENT OMISSION of a known fact (warm deflection, no value, no explicit denial)
    # -> still CATCH: the known value did not ship.
    ve4 = V.verify("when's my birthday?",
                   "Aww, birthdays! Tell me, how do you like to celebrate?", known_bday)
    ok("(e4) silent omission of a known fact is caught (override)", ve4.override is True)

    # (e5) GUARD — a CONTESTED known fact (needs_reconfirm) is demoted out of KNOWN, so an
    # honest hedge of it is NOT punished.
    contested = _row("birthday", "September 14")
    contested["needs_reconfirm"] = True
    ve5 = V.verify("when's my birthday?",
                   "I'm not totally sure of your birthday anymore — remind me?", [contested])
    ok("(e5) contested (needs_reconfirm) fact is NOT bound -> no override", ve5.override is False)

    # (e6) GUARD — a LOW-CONFIDENCE ([SENSE]) fact is below the KNOWN bar, so disclaiming it
    # is honest, not a violation.
    soft = _row("birthday", "September 14", confidence=0.6)
    ve6 = V.verify("when's my birthday?", "I don't have your birthday down.", [soft])
    ok("(e6) sub-0.85 ([SENSE]) fact is NOT bound -> no override", ve6.override is False)

    # (e7) GUARD — an OFF-TOPIC turn that happens to omit the known birthday is never flagged
    # (the question doesn't route to the trait, so R is empty).
    ve7 = V.verify("how's the weather where you are?",
                   "I can't really see outside, but I hope it's nice!", known_bday)
    ok("(e7) off-topic omission of a known fact is NOT flagged", ve7.override is False)

    # (e8) raw LIRF-ROW known fact, disclaimed -> caught (shape-agnostic, like contradiction).
    ve8 = V.verify("when's my birthday?", "I don't know your birthday.",
                   [_row("birthday", "September 14")])
    ok("(e8) ignored-known caught from a raw LIRF row too", ve8.override is True)

    # (e9) a known fact for a DIFFERENT, non-asked trait is irrelevant — disclaiming the
    # asked-but-unknown one stays honest even though SOME known fact exists.
    ve9 = V.verify("when's my birthday?",
                   "I don't have your birthday yet — tell me?",
                   [_mem("you", "lives", "Portland, OR")])
    ok("(e9) a known fact on a non-asked trait does not bind the asked one", ve9.override is False)

    # (e10) INCOHERENT DISCLAIMER — the live failure the Spine targets: the reply DISCLAIMS the
    # known fact ("I don't have your birthday saved…") yet ALSO mentions the value in the same
    # breath. The value is technically present, but the disclaimer makes it read as not-knowing,
    # so it MUST override (regenerate) — value-present alone does NOT excuse a self-contradicting
    # denial. (Caught live: 1/12 birthday asks pre-fix.)
    ve10 = V.verify("when's my birthday?",
                    "I don't have your birthday saved, so I can't tell you the exact date. "
                    "But I do remember that September 14th is a special day for us!",
                    known_bday)
    ok("(e10) a disclaimer that ALSO mentions the value still overrides (incoherent denial)",
       ve10.override is True)
    ok("(e10) issue notes the disclaimer-despite-value", any(
        i.startswith(Verdict.IGNORED_KNOWN_FACT) and "despite mentioning the value" in i
        for i in ve10.issues))

    # --- contract / robustness ---
    ok("Verdict is frozen + shaped", isinstance(vc, Verdict) and hasattr(vc, "override"))
    ok("as_dict exposes the 4 keys",
       set(va.as_dict().keys()) == {"ok", "confidence", "issues", "override"})
    ok("override implies not ok (invariant)",
       all(v.ok is False for v in (va, va_row, vb, vb2, ve1, ve4, ve8, ve10) if v.override))
    ok("module-level verify() matches the organ method",
       verify("when's my birthday?", "Your birthday is June 14th!", evidence).override is True)

    # garbage evidence / None must never raise and must fail-open-safe.
    ok("None evidence is tolerated", V.verify("hi", "hello there", None).ok is True)
    ok("garbage evidence items are dropped, not fatal",
       V.verify("hi", "hello", [None, 42, "nope", {"no_value": 1}]).ok is True)
    ok("empty draft is a clean pass", V.verify("hi", "", evidence).ok is True)

    # a LIST-valued trait can't be "contradicted" (likes/dislikes are additive).
    vlist = V.verify("what do I like?", "You love sushi.",
                     [_row("likes", ["pizza", "ramen"])])
    ok("list-valued trait is never a contradiction", vlist.override is False)

    # the bus-emit bridge runs and returns a Verdict even with no bus (best-effort emit).
    import asyncio

    async def _bridge():
        return await V.verify_observation(None, "f_turn1", "when's my birthday?",
                                          "Your birthday is June 14th!", evidence)
    vbridge = asyncio.run(_bridge())
    ok("verify_observation returns the Verdict (emit is best-effort)", vbridge.override is True)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL VERIFIER (ORGAN 4) SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv or len(sys.argv) == 1:
        raise SystemExit(_selftest())
    print("usage: python3 anima/organs/verifier.py --selftest")
