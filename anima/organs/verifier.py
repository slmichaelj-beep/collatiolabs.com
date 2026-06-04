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

Three checks, in order, all DETERMINISTIC (substring / value-contradiction / heuristic),
so the whole organ is exercised and tested with NO model:

  1. CONTRADICTION — does the reply state a value for a known trait (a birthday, a name,
     a place) that conflicts with what the evidence holds for that same trait? This is the
     unforgivable failure for a companion (telling you the wrong birthday you yourself
     taught it), so a contradiction sets ``override=True`` — suppress / regenerate.
  2. UNSUPPORTED PERSONAL CLAIM — does the reply assert a personal fact about the user
     (a date, a name, a place) that is NOT grounded in the evidence and NOT already in the
     question? That is confabulation; it ties directly to the rail's personal-honesty
     stance. It flags, and overrides only when it is a hard, checkable specific (a date or
     a clearly-named personal entity) the evidence can't back.
  3. CONFIDENCE — a single 0..1 score folded from the issues found and the strength of the
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
    ``override``   — True means SUPPRESS / REGENERATE this draft (a contradiction, or an
                     unsupported HARD personal specific). ``override`` implies ``not ok``.
    """

    ok: bool
    confidence: float
    issues: list = field(default_factory=list)
    override: bool = False

    # Codes used in ``issues`` (stable, so callers/telemetry can match on prefix).
    CONTRADICTION = "contradiction"
    UNSUPPORTED_PERSONAL = "unsupported_personal_claim"

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
    return _Fact(entity=ent, trait=_canon_trait(trait), value=obj.get("value"), confidence=conf)


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
    # birthplace — "you were born in Ohio", "your hometown is Akron"
    (re.compile(r"\byou\s+were\s+born\s+in\s+" + _PROPER, re.I), "birthplace"),
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
        grounded_claims = 0

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
               grounded_claims: int, had_claims: bool) -> float:
        if contradicted:
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
# (a) a reply that contradicts an evidence fact, (b) a confabulated personal claim;
# and PASSES (c) a correct evidence-grounded answer, (d) a normal non-personal reply.
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

    # --- contract / robustness ---
    ok("Verdict is frozen + shaped", isinstance(vc, Verdict) and hasattr(vc, "override"))
    ok("as_dict exposes the 4 keys",
       set(va.as_dict().keys()) == {"ok", "confidence", "issues", "override"})
    ok("override implies not ok (invariant)",
       all(v.ok is False for v in (va, va_row, vb, vb2) if v.override))
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
