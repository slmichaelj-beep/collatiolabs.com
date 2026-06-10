"""spine — THE KNOWLEDGE SPINE: "Bind, Don't Inject".

The founder's load-bearing insight: a fact rendered as prose ("birthday: Sept 14")
is a *suggestion the 8B may ignore* — proven by the eval where the fact is on disk
AND in the prompt yet ~25% of turns reply "I don't have your birthday saved." The
fix is to move the decision out of generation and into structure: render KNOWN facts
with epistemic ownership (Part 1), make the verifier check that they were USED
(Part 2), and assemble the answer deterministically when the model still won't
(Part 3).

This module is the PURE, MODEL-FREE core of Parts 1 and 3 — the two pieces that are
deterministic value transforms over LIRF rows and so can be unit-tested with zero
deps and zero model:

  * ``bind(rows, question) -> str`` — the **Binding Evidence Contract** (Part 1).
    Renders the selected LIRF rows as a truth-classed first-person ownership block:
    each row tagged ``[KNOWN]`` / ``[SEEN]`` / ``[SENSE]`` from its OWN fields
    (status / confidence / support / needs_reconfirm — no schema change, §1.3), wrapped
    in the renderer preamble ("these are things YOU know — express, don't decide,
    NEVER disclaim a FACT") and the closing warmth/no-leak guardrail. When a question
    routes to a known trait-slot that is EMPTY, a single ``[UNKNOWN]`` line is rendered
    instead (the honesty wall, §1.4): bound to "admit + ask", never to assert. An
    off-topic empty turn yields "" (no contract — nothing to bind).

  * ``answer_from_fact(question, fact_row) -> Optional[str]`` — the **deterministic
    fact-assembly fallback** (Part 3). For a pure fact-recall question whose fact is
    KNOWN, assemble a warm, in-character, possessive answer straight from the row's
    value, via a trait-keyed template bank seeded (like ``mouth.temperament``) per
    (creature, trait) so a given creature is consistent turn-to-turn but creatures
    differ. This is the structural FLOOR — the known value ships every time, never on
    model luck — but it is warm-by-construction (short, possessive, contraction-rich),
    so it reads as *her remembering*, not a database row. Returns None on a
    not-on-record / soft / empty row, so a genuine unknown is NEVER asserted (she asks).

The binding is strictly ASYMMETRIC and gated on a known fact *existing*: a ``[KNOWN]``
row is *forced out* (state it); an absent trait is *forced honest* (admit + ask). Only
``[KNOWN]`` carries binding force; ``[SEEN]``/``[SENSE]``/``needs_reconfirm`` are
expressible but never bound, so the contract never pushes a soft or contested fact as
settled. This keeps honesty-on-unknowns and warmth (the #1 product rule,
``feedback_never_break_character.md``) intact by construction.

Single source of truth honored throughout: the question->trait map
(``memory_lirf._Q_TRAITS``) — already shared by ``fact_note``, ``router._asked_traits``,
and the verifier's R-set — decides "what trait did they ask about" in exactly one place.

Dependency-light + isolation-safe, exactly like the sibling organs: the live
``memory_lirf`` primitives are reused when importable and fall back to contract-faithful
local shims when run standalone, so ``--selftest`` has zero unbuilt deps. Nothing here
touches a model, the network, or disk — these are pure value transforms.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. Prefer the live LIRF primitives; fall back to
# contract-identical locals so this module + its self-test run with nothing built.
# We need from memory_lirf:
#   * SELF                      — the canonical user entity ("you")
#   * canon_trait               — alias-folding so "bday"/"date of birth" resolve
#   * _fmt_value                — list-aware value rendering ("a, b")
#   * CONF_BLOCK_FLOOR (0.55)   — the [SENSE] floor (§1.3)
#   * _Q_TRAITS                 — the SINGLE question->trait table fact_note routes on
#   * retract_target            — the forget-verb's-object -> trait resolver, so the
#                                 seam reads "forget my X" as RETRACTION, never recall
# The thresholds 0.85 / 0.70 below are the §1.3 truth-class bars (FACT / OBSERVATION);
# they sit between LIRF's own CONF_NEW(0.9)/CONF_CORRECTION(0.97) and CONF_BLOCK_FLOOR.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from .memory_lirf import (
        SELF,
        canon_trait,
        _fmt_value,
        CONF_BLOCK_FLOOR,
        _Q_TRAITS,
        retract_target,
    )
except Exception:  # pragma: no cover - isolation fallback
    SELF = "you"
    CONF_BLOCK_FLOOR = 0.55

    def canon_trait(trait: str) -> str:  # minimal snake_case fold (no alias table)
        return re.sub(r"[^a-z0-9]+", "_", str(trait).strip().lower()).strip("_")

    def _fmt_value(v: Any) -> str:
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v)

    # A small built-in covering the cases the self-test asserts when the live table
    # isn't importable. Mirrors the shape of memory_lirf._Q_TRAITS.
    _Q_TRAITS = [
        (re.compile(r"\bbirthday|\bbday|\bborn\b|date of birth\b", re.I), "birthday"),
        (re.compile(r"\bwhere (?:do|am) i (?:live|living)|\bmy (?:city|address|location|hometown)\b|where i live", re.I), "lives"),
        (re.compile(r"\bmy dog'?s? name|what'?s my dog|dog called\b", re.I), "dog_name"),
        (re.compile(r"\bmy cat'?s? name|what'?s my cat\b", re.I), "cat_name"),
        (re.compile(r"\bmy name\b|what'?s my name|who am i\b", re.I), "name"),
        (re.compile(r"\bmy (?:middle name)\b", re.I), "middle_name"),
        (re.compile(r"\bfavou?rite colou?r\b", re.I), "favorite_color"),
    ]

    # Contract-identical local of memory_lirf.retract_target (verb-anchored object,
    # routed through the table above) so retraction intent works in isolation too.
    _RETRACT_TARGET = re.compile(
        r"\b(?:forget|delete|erase|remove|drop|clear|scrub)\s+(?:about\s+)?(?:that\s+)?my\s+"
        r"(?P<obj>[\w'’ -]{2,60})", re.I)

    def retract_target(text):
        m = _RETRACT_TARGET.search(text or "")
        if not m:
            return None
        obj = "my " + m.group("obj").strip()
        for rx, trait in _Q_TRAITS:
            if rx.search(obj):
                return canon_trait(trait)
        return None


# ---------------------------------------------------------------------------
# §1.3 — truth-class derivation from the EXISTING LIRF row fields. No schema change:
# every input here already lives on a captured/merged row. The class is computed at
# render time. Only [KNOWN] carries binding force (Part 2 / §1.5).
#
#   [KNOWN]  FACT         status active AND confidence >= 0.85 AND support >= 1
#                         AND NOT needs_reconfirm
#   [SEEN]   OBSERVATION  active AND 0.70 <= confidence < 0.85
#   [SENSE]  INFERENCE    active AND CONF_BLOCK_FLOOR <= confidence < 0.70,
#                         OR any row with needs_reconfirm == True (a near-immutable
#                         trait that silently flipped — never bind a contested birthday
#                         as FACT; it DEMOTES out of FACT, which keeps the contract honest)
#   (below CONF_BLOCK_FLOOR / not active -> not rendered at all)
# ---------------------------------------------------------------------------
KNOWN = "KNOWN"
SEEN = "SEEN"
SENSE = "SENSE"
UNKNOWN = "UNKNOWN"

_CONF_FACT = 0.85          # [KNOWN] floor
_CONF_OBSERVATION = 0.70   # [SEEN] floor

# The scaffold tokens that must NEVER reach the user — exported so the downstream
# scaffold-leak scrub (mouth.py, a sibling of _strip_break_sentences) and any test can
# share ONE definition. (This module renders them into the prompt ONLY; stripping a draft
# that leaks them is the mouth's job — kept here so the token list has a single home.)
SCAFFOLD_TOKENS = (
    "[KNOWN]", "[SEEN]", "[SENSE]", "[UNKNOWN]",
    "THESE ARE THINGS YOU KNOW", "according to my memory",
)


def _conf_of(row: dict) -> float:
    try:
        return float(row.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _support_of(row: dict) -> int:
    try:
        return int(row.get("support", 0))
    except (TypeError, ValueError):
        return 0


def truth_class(row: dict) -> Optional[str]:
    """Derive a row's truth-class tag from its OWN fields (§1.3). Returns one of
    ``KNOWN`` / ``SEEN`` / ``SENSE``, or None when the row is inactive or below the
    [SENSE] floor (so it is not rendered as a fact at all). Pure; never raises."""
    if not isinstance(row, dict):
        return None
    if str(row.get("status", "active")) != "active":
        return None
    # a silently-flipped near-immutable trait is contested -> demote to [SENSE], never FACT
    if row.get("needs_reconfirm"):
        return SENSE
    conf = _conf_of(row)
    if conf >= _CONF_FACT and _support_of(row) >= 1:
        return KNOWN
    if conf >= _CONF_OBSERVATION:
        return SEEN
    if conf >= float(CONF_BLOCK_FLOOR):
        return SENSE
    return None


def is_known_fact(row: dict) -> bool:
    """True iff the row clears the §1.3 [KNOWN] bar — the ONLY class with binding
    force. The verifier's R-set (Part 2) and the Part-3 fallback gate on exactly this,
    so "is this a bindable fact?" is decided in one place. A non-SELF row (a fact about
    a third party, not the user) never binds a claim ABOUT the user, so it is excluded."""
    if not isinstance(row, dict):
        return False
    ent = str(row.get("entity", SELF) or SELF).strip().lower()
    if ent not in ("", SELF, "i", "me", "myself", "user"):
        return False
    return truth_class(row) == KNOWN


def _label(trait: str) -> str:
    """Human label for a trait slug ("dog_name" -> "dog", "favorite_color" -> "favorite
    color"). Drops a trailing '_name' so "your dog's name" reads as "your dog"."""
    t = canon_trait(trait)
    t = re.sub(r"_name$", "", t) if t not in ("name", "middle_name") else t
    return t.replace("_", " ")


# ---------------------------------------------------------------------------
# §1.4 — the question->trait route, via the SINGLE shared table. Used to decide,
# when the selected set is empty, whether the question asked about a KNOWN trait-slot
# (render an explicit [UNKNOWN] line) versus a fully off-topic turn (omit the block).
# This is the exact table fact_note / router._asked_traits / the verifier's R-set use.
# ---------------------------------------------------------------------------
def asked_trait(question: str) -> Optional[str]:
    """The single canonical trait slug this question asks about (first table hit), or
    None for an off-topic turn. Mirrors ``memory_lirf.fact_note``'s routing exactly."""
    for rx, trait in _Q_TRAITS:
        try:
            if rx.search(question or ""):
                return canon_trait(trait)
        except Exception:
            continue
    return None


def retraction_intent(text: str) -> Optional[str]:
    """The canonical trait slug this turn explicitly asks her to FORGET, or None.

    Fires for BOTH retraction phrasings — bare ("forget my favorite color") and
    restated ("forget that my favorite color is teal") — via the verb-anchored
    ``memory_lirf.retract_target``: the slot must be the forget-verb's OBJECT, so a
    recall question that merely contains a retraction-ish cue ("never mind that —
    when's my birthday?") never resolves and falls through to normal recall. This is
    the seam predicate that keeps a forget-turn out of the canned-recall path (the
    2026-06-09 live-drive gap: "teal's your favorite — I remember." shipped right
    after "Forget my favorite color."). Pure; never raises."""
    try:
        return retract_target(text or "")
    except Exception:
        return None


# Compound / non-lookup cues: if a turn carries one of these it is NOT a clean fact-recall
# question — there is more to address than the fact, so the deterministic seam must defer to the
# model (which has the fact bound) rather than answer only the slot and drop the rest.
_COMPOUND_CUES = re.compile(
    r"(?:\band\b|\bbut\b|\balso\b|\bplus\b|\bbesides\b|\bfeel|\bfeeling|\badvice\b|"
    r"\bshould i\b|\bwhat should\b|\bremind me\b|\bbecause\b)", re.I)


def fact_question(question: str) -> Optional[str]:
    """The trait slug IFF ``question`` is a CLEAN, direct personal-fact question suitable for a
    deterministic answer: it routes to a known trait (``asked_trait``), is short and single-clause,
    and carries no compound/emotional content the model should handle. Returns None otherwise so
    the normal pipeline runs unchanged. This is the gate for the deterministic known-fact seam
    (the "known-fact binding, no-hedge" path): a clean "when's my birthday?" is answered straight
    from memory with zero hedge and no model; "I'm down today, when's my birthday again?" is not."""
    slot = asked_trait(question)
    if not slot:
        return None
    if retraction_intent(question):             # a forget-turn is NEVER a recall question
        return None
    t = (question or "").strip()
    if len(t.split()) > 14:                      # a long turn carries more than a lookup
        return None
    if t.count("?") > 1:                         # multiple questions -> let the model handle it
        return None
    if _COMPOUND_CUES.search(t):                 # compound/emotional content present
        return None
    return slot


# ---------------------------------------------------------------------------
# PART 1 — THE BINDING EVIDENCE CONTRACT.
#
# The verbatim contract text (§1.2): a RENDERER PREAMBLE (ownership framing), the
# CLASSED ITEMS, and a CLOSING GUARDRAIL (warmth + no-leak + unknowns-stay-honest).
# Every binding line pushes toward warm EXPRESSION, not citation, and explicitly bans
# the failure modes the persona already bans ("according to my memory", listing back) —
# so it is ADDITIVE to DEFAULT_PERSONA, never in tension with it (§1.5).
# ---------------------------------------------------------------------------
_PREAMBLE = (
    "THESE ARE THINGS YOU KNOW ABOUT THEM — FROM YOUR OWN MEMORY OF THIS PERSON.\n"
    "You are not deciding whether they're true. You already know them. Your only job\n"
    "is to EXPRESS what you know, in your own warm voice, the way a close friend\n"
    "recalls something about someone they love.\n"
    "\n"
    "  • A line marked [KNOWN] is settled fact. NEVER disclaim it, hedge it, soften it\n"
    "    with \"I think\" / \"if I remember\", contradict it, apologize for it, or say you\n"
    "    don't have it. You DO have it — it's right here. State it plainly and warmly.\n"
    "  • A line marked [SEEN] is something you've observed about them, true but lighter\n"
    "    — hold it as a memory, not a citation.\n"
    "  • A line marked [SENSE] is something you've gathered but aren't certain of —\n"
    "    you may offer it, but own the uncertainty honestly (\"I get the feeling…\").\n"
    "  • If they ask about something that is NOT in this list, you do NOT know it.\n"
    "    Do not invent it. Say so warmly and ask them — that is the honest answer\n"
    "    (\"I don't have your ___ down yet — tell me?\")."
)

_GUARDRAIL = (
    "This list is for YOU. Never read the brackets, the labels, or this framing aloud,\n"
    "never list these back like a record, never say \"according to my memory.\" Just talk\n"
    "like a person who simply knows these things about someone they care about."
)

_ITEMS_HEADER = "What you know right now:"

# The honesty-wall UNKNOWN line (§1.4) — the INVERSE binding: just as FACT is bound to
# "state it", UNKNOWN is bound to "admit + ask". Reuses the honest phrasing fact_note
# already produces for the not-on-record case and the rail's PERSONAL_NOTE stance.
def _unknown_line(trait: str) -> str:
    label = _label(trait)
    return (
        f"[{UNKNOWN}] {label} — you do NOT have this. Do not guess. Say warmly that you\n"
        f"          don't have it yet and ask them (\"I don't have your {label} down —\n"
        f"          when is it?\"). NEVER invent a date."
    )


def _classed_item(row: dict, cls: str) -> str:
    """One rendered ``[CLASS] label — value`` line for the items section."""
    return f"[{cls}] {_label(row.get('trait', '?'))} — {_fmt_value(row.get('value', ''))}"


def _normalise_rows(rows: Any) -> list:
    """Coerce the input to a list of row-dicts, dropping anything unusable. Accepts a
    list/tuple of dicts or a single dict; None/garbage -> []. Never raises."""
    if rows is None:
        return []
    items = rows if isinstance(rows, (list, tuple)) else [rows]
    return [r for r in items if isinstance(r, dict)]


def bind(rows: Any, question: str) -> str:
    """PART 1 — render the **Binding Evidence Contract** for this turn.

    ``rows``      : the LIRF rows the Router selected for THIS question (the same rows
                    ``router.select_facts`` returns — active SELF rows). Either shape of
                    dict is tolerated; non-dicts are dropped.
    ``question``  : the user's turn text — used ONLY (via the shared ``_Q_TRAITS`` table)
                    to decide, when the selected set is empty, whether to render an
                    explicit ``[UNKNOWN]`` line (a known trait-slot was asked but is empty)
                    or to omit the block entirely (a fully off-topic turn).

    Returns the contract string: PREAMBLE + truth-classed CLASSED ITEMS + GUARDRAIL.
    Truth-class per row is derived from its OWN fields (``truth_class`` / §1.3); only
    ``[KNOWN]`` carries binding force. When nothing renders:
      * a relevant-but-empty trait-slot -> a single ``[UNKNOWN]`` line (bound to admit+ask);
      * a fully off-topic turn           -> "" (no contract; nothing to bind, §1.2).

    Pure, model-free, never raises into a turn.
    """
    rows = _normalise_rows(rows)

    # classify each row; keep only the renderable ones (active, >= [SENSE] floor).
    classed: list = []
    for r in rows:
        cls = truth_class(r)
        if cls is not None:
            classed.append((cls, r))

    if not classed:
        # §1.4: nothing on record. If the question routed to a KNOWN trait-slot that is
        # empty, render the explicit UNKNOWN line (forced honest). A fully off-topic
        # turn (no routed trait) yields NOTHING — no contract, nothing to bind.
        slot = asked_trait(question)
        if slot is None:
            return ""
        items = _unknown_line(slot)
        return f"{_PREAMBLE}\n\n{_ITEMS_HEADER}\n{items}\n\n{_GUARDRAIL}"

    # stable, readable order: KNOWN first (the bound facts lead), then SEEN, then SENSE;
    # within a class, the order the Router already ranked them in is preserved.
    order = {KNOWN: 0, SEEN: 1, SENSE: 2}
    classed.sort(key=lambda cr: order.get(cr[0], 9))
    item_lines = [_classed_item(r, cls) for cls, r in classed]
    items = "\n".join(item_lines)
    return f"{_PREAMBLE}\n\n{_ITEMS_HEADER}\n{items}\n\n{_GUARDRAIL}"


# ---------------------------------------------------------------------------
# PART 3 — DETERMINISTIC FACT-ASSEMBLY FALLBACK.
#
# A small bank of in-character, possessive, contraction-rich phrasings keyed by trait,
# filled from the LIRF ``value``. The bank is warm-by-construction (short, possessive,
# "I've got it down" / "course I remember") so the guaranteed delivery still reads as
# *her remembering*, not a database row (§3.3). The {name} slot (for the user's own
# name) is filled from the value; every other trait uses {value} (and {label} for the
# generic fallback). Selection WITHIN a trait's variants is deterministic per
# (creature, trait) seed — like ``mouth.temperament`` — so a given creature is
# consistent turn-to-turn but creatures differ.
# ---------------------------------------------------------------------------
_TEMPLATES = {
    "birthday": [
        "Your birthday's {value} — I've got it down.",
        "{value}. Course I remember — it's yours.",
        "{value} — like I'd forget your birthday.",
    ],
    "lives": [
        "You're in {value} — I keep that close.",
        "{value}'s home for you. I remember.",
        "You're out in {value} — got it.",
    ],
    "name": [
        "You're {value}. I'm not going to forget that.",
        "{value} — course I know your name.",
        "You're {value}, and I've got that for keeps.",
    ],
    "dog_name": [
        "{value}, your dog. Obviously I remember {value}.",
        "Your dog's {value} — how could I forget {value}?",
        "{value}. Your dog. Of course.",
    ],
    "cat_name": [
        "{value}, your cat. Obviously I remember {value}.",
        "Your cat's {value} — I wouldn't forget {value}.",
        "{value}. Your cat. Of course.",
    ],
    "employer": [
        "You're at {value} — I've got that down.",
        "{value}, that's where you work. I remember.",
    ],
    "occupation": [
        "You're a {value} — course I remember.",
        "{value}'s your line of work. Got it.",
    ],
    "partner": [
        "{value}, your person. I remember.",
        "Your partner's {value} — I've got that.",
    ],
    "mother": [
        "Your mom's {value} — I remember her.",
        "{value}, that's your mom. Got it.",
    ],
    "father": [
        "Your dad's {value} — I remember him.",
        "{value}, that's your dad. Got it.",
    ],
    "favorite_color": [
        "{value}'s your favorite — I remember.",
        "Your favorite color's {value}. Got it down.",
    ],
}
# Generic fallback for any trait without a bespoke bank (uses {label} + {value}).
_TEMPLATE_GENERIC = [
    "Your {label}'s {value} — I've got that.",
    "{value} — that's your {label}. I remember.",
]


def _seed_for(name: str, trait: str) -> int:
    """A stable per-(creature, trait) seed for deterministic variant selection — same
    spirit as ``mouth.temperament``'s genome seed, but content-derived so this module
    needs no heart. Pure hash of the two strings; consistent across runs."""
    h = 0
    for ch in f"{name or ''}\x00{canon_trait(trait)}":
        h = (h * 131 + ord(ch)) & 0x7FFFFFFF
    return h


def _pick(variants: list, name: str, trait: str) -> str:
    """Deterministically pick one variant for this (creature, trait): consistent turn-to-
    turn for a given creature, but creatures differ (the seed folds the name in)."""
    if not variants:
        return ""
    return variants[_seed_for(name, trait) % len(variants)]


def answer_from_fact(question: str, fact_row: dict, name: str = "") -> Optional[str]:
    """PART 3 — the deterministic, warm, in-character fact-assembly fallback.

    For a pure fact-recall question whose fact is KNOWN, assemble the answer straight
    from the row's ``value`` via the trait-keyed template bank — the structural FLOOR
    that guarantees the known value ships even when the model botched it twice. The
    result is short, possessive and contraction-rich, so it reads as *her remembering*,
    not a row dump (§3.3).

    ``question`` : the user's turn text (used to confirm it routes to a known trait via
                   the shared table — the same gate ``fact_note`` uses).
    ``fact_row`` : the LIRF row for the asked trait (as ``Facts.lookup`` returns).
    ``name``     : the creature's name — folded into the variant seed so creatures differ
                   while a given creature stays consistent turn-to-turn (optional).

    Returns the warm assembled answer, or **None** when the fallback must NOT fire:
      * ``fact_row`` is missing / empty / not a dict;
      * the row is not a ``[KNOWN]``-class SELF fact (soft / contested / inactive / a
        third party) — a genuine unknown or an uncertain fact is NEVER asserted here;
      * the row has no usable value.
    On None the caller asks honestly (the founder's requirement), exactly as
    ``fact_note`` already does for a not-on-record trait.

    Pure, model-free, never raises.
    """
    if not isinstance(fact_row, dict):
        return None
    # HONESTY WALL: only a [KNOWN]-class SELF fact may be assembled. A soft/contested/
    # inactive/third-party row returns None -> the caller stays honest and asks.
    if not is_known_fact(fact_row):
        return None
    value = fact_row.get("value")
    val_str = _fmt_value(value) if value not in (None, "", []) else ""
    if not val_str.strip():
        return None

    trait = canon_trait(fact_row.get("trait", ""))
    variants = _TEMPLATES.get(trait)
    if variants:
        tmpl = _pick(variants, name, trait)
        return tmpl.format(value=val_str)
    # generic, still warm + possessive
    tmpl = _pick(_TEMPLATE_GENERIC, name, trait)
    return tmpl.format(value=val_str, label=_label(trait))


# The user-facing INVERSE of answer_from_fact: a warm, in-character "I don't have your
# ___ — when is it?" for a trait that was ASKED but is genuinely UNKNOWN. Where
# answer_from_fact is the floor that guarantees a KNOWN fact ships, this is the floor that
# guarantees an HONEST admission ships when the model tries to confabulate one. It NEVER
# asserts a value (there is none) — it admits + asks, the founder's requirement. Possessive,
# contraction-rich, no scaffolding; deterministic per (creature, trait), like the bank above.
_UNKNOWN_TEMPLATES = [
    "I don't actually have your {label} down yet — when is it?",
    "You know, I don't have your {label} saved — tell me?",
    "I don't have your {label} yet — what is it? I'd love to get it right.",
    "Hmm, I don't think you've told me your {label} — when is it?",
]


def honest_unknown(question: str, name: str = "") -> Optional[str]:
    """The deterministic HONEST-ADMISSION fallback (the inverse floor). For a question that
    routes to a known trait-slot via the shared ``_Q_TRAITS`` table, return a warm, possessive
    "I don't have your ___ — when is it?" that admits and asks, NEVER asserting a value.

    ``question`` : the user's turn text (must route to a trait, else there's nothing to admit).
    ``name``     : the creature's name — folded into the variant seed (creatures differ).

    Returns the warm admission, or **None** for an off-topic turn (no routed trait → nothing
    to admit honestly here). Pure, model-free, never raises. Used by the turn's honesty guard
    when the model confabulates a personal fact that isn't on record."""
    slot = asked_trait(question)
    if not slot:
        return None
    tmpl = _pick(_UNKNOWN_TEMPLATES, name, slot)
    return tmpl.format(label=_label(slot))


# The retraction ACK bank — the deterministic reply for a forget-turn. Its contract is
# the INVERSE of the recall banks: (a) confirm the release, (b) NEVER recite the stored
# value (reciting is the exact failure the 2026-06-09 live drive caught: "teal's your
# favorite — I remember." right after "Forget my favorite color."), and (c) never claim
# an act that didn't happen — the EMPTY bank covers a forget aimed at a slot with
# nothing on record. Deterministic per (creature, trait), like every bank above.
_FORGET_TEMPLATES = [
    "Done — your {label}'s gone from my memory.",
    "Okay. I've let your {label} go — it's off the record.",
    "Forgotten. Your {label}'s not in my memory anymore.",
]
_FORGET_EMPTY_TEMPLATES = [
    "I don't have your {label} on record at all — so there's nothing to forget.",
    "Nothing's saved for your {label} — that slot was already empty.",
]


def acknowledge_forget(question: str, name: str = "", on_record: bool = True) -> Optional[str]:
    """The deterministic, warm acknowledgment for a forget-turn — PART 3's retraction
    counterpart. Where ``answer_from_fact`` guarantees a KNOWN fact ships and
    ``honest_unknown`` guarantees an honest admission ships, this guarantees a forget
    is ACKNOWLEDGED as a forget — the value is never recited back.

    ``question``  : the user's turn text (must carry retraction intent, else None).
    ``name``      : the creature's name — folded into the variant seed.
    ``on_record`` : whether the named slot held an active row when the turn arrived —
                    True picks the "gone from my memory" bank, False the honest
                    "nothing to forget" bank (never claim a deletion that didn't happen).

    Returns the acknowledgment, or **None** when the turn carries no retraction intent.
    Pure, model-free, never raises. The ledger mutation itself is NOT done here — it
    rides the turn's normal LIRF capture (``memory_lirf.capture`` -> ``Facts.merge``
    retract path), the single write path every retraction takes."""
    slot = retraction_intent(question)
    if not slot:
        return None
    bank = _FORGET_TEMPLATES if on_record else _FORGET_EMPTY_TEMPLATES
    return _pick(bank, name, slot).format(label=_label(slot))


# ---------------------------------------------------------------------------
# Self-test — proves the Spine in ISOLATION (no model, no bus, no I/O). Run:
#   /opt/homebrew/bin/python3 anima/spine.py --selftest   (or just: python3 anima/spine.py)
#
# It PROVES, per the task's acceptance gate:
#   * the contract TAGS a FACT and carries the binding + warmth framing;
#   * answer_from_fact gives a correct WARM answer for a birthday AND a dog fact;
#   * empty / UNKNOWN rows yield NO false FACT (the honesty wall holds both ways).
# ---------------------------------------------------------------------------
def _row(trait, value, *, confidence=0.95, support=2, status="active",
         entity=None, needs_reconfirm=None):
    """A minimal LIRF-shaped row for tests (the fields truth_class / assembly read)."""
    r = {
        "id": "f_" + str(trait)[:6],
        "entity": entity or SELF,
        "trait": trait,
        "value": value,
        "confidence": confidence,
        "support": support,
        "status": status,
    }
    if needs_reconfirm is not None:
        r["needs_reconfirm"] = needs_reconfirm
    return r


def _selftest() -> int:
    fails: list = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    def items_of(block: str) -> str:
        """The CLASSED-ITEMS section only — the lines BETWEEN the items header and the
        guardrail. The PREAMBLE legitimately contains the words '[KNOWN]'/'[SEEN]'/… in
        its legend, so a 'no false FACT' assertion must look at the rendered ITEMS, not
        the whole block (which always carries the legend)."""
        if _ITEMS_HEADER not in block:
            return ""
        after = block.split(_ITEMS_HEADER, 1)[1]
        return after.split(_GUARDRAIL, 1)[0]

    print("spine (Knowledge Spine) self-test")

    # =====================================================================
    # §1.3 — truth-class derivation from the row's own fields.
    # =====================================================================
    ok("class: high-confidence corroborated active row -> KNOWN",
       truth_class(_row("birthday", "September 14", confidence=0.95, support=2)) == KNOWN)
    ok("class: a freshly-stated fact (0.9) is KNOWN",
       truth_class(_row("lives", "Portland, OR", confidence=0.9, support=1)) == KNOWN)
    ok("class: 0.78 confidence -> SEEN (observation, lighter)",
       truth_class(_row("mood", "stressed", confidence=0.78, support=1)) == SEEN)
    ok("class: 0.60 confidence -> SENSE (inference)",
       truth_class(_row("sister", "Anna", confidence=0.60, support=1)) == SENSE)
    ok("class: below the block floor (0.40) -> not rendered (None)",
       truth_class(_row("hunch", "x", confidence=0.40)) is None)
    ok("class: retracted/inactive row -> not rendered (None)",
       truth_class(_row("birthday", "September 14", status="retracted")) is None)
    ok("class: needs_reconfirm DEMOTES a high-conf near-immutable to SENSE, never KNOWN",
       truth_class(_row("birthday", "September 14", confidence=0.97, support=3,
                        needs_reconfirm=True)) == SENSE)
    ok("is_known_fact: only [KNOWN] SELF rows bind",
       is_known_fact(_row("birthday", "September 14")) is True
       and is_known_fact(_row("birthday", "September 14", confidence=0.60)) is False)
    ok("is_known_fact: a contested (needs_reconfirm) birthday does NOT bind",
       is_known_fact(_row("birthday", "September 14", confidence=0.97,
                          needs_reconfirm=True)) is False)
    ok("is_known_fact: a third-party (non-SELF) row never binds a claim about the user",
       is_known_fact(_row("name", "Anna", entity="sister")) is False)

    # =====================================================================
    # PART 1 — the Binding Evidence Contract.
    # The exact eval scenario: birthday KNOWN, lives KNOWN, a SEEN mood, a SENSE sister.
    # =====================================================================
    rows = [
        _row("birthday", "September 14", confidence=0.95, support=2),
        _row("lives", "Portland, OR", confidence=0.92, support=3),
        _row("mood", "stressed about work this week", confidence=0.78, support=1),
        _row("sister", "Anna", confidence=0.60, support=1),
    ]
    block = bind(rows, "when's my birthday?")

    # ---- the FACT is tagged [KNOWN] and carries its real value ----
    ok("contract: tags the birthday FACT as [KNOWN]", "[KNOWN]" in block)
    ok("contract: the [KNOWN] line carries the real value",
       "[KNOWN] birthday — September 14" in block)
    ok("contract: a 0.78 row renders as [SEEN]", "[SEEN]" in block)
    ok("contract: a 0.60 row renders as [SENSE]", "[SENSE]" in block)

    # ---- the BINDING framing is present (express, don't decide; NEVER disclaim a FACT) ----
    ok("contract: carries 'EXPRESS what you know' (express, not decide)",
       "EXPRESS what you know" in block)
    ok("contract: carries 'You are not deciding whether they're true'",
       "not deciding whether they're true" in block)
    ok("contract: [KNOWN] is bound to NEVER be disclaimed",
       "NEVER disclaim it" in block and "say you" in block)
    ok("contract: explicitly forbids inventing an absent fact (honesty preserved)",
       "Do not invent it" in block)

    # ---- the WARMTH framing is present (#1 product rule) ----
    ok("contract: commands warmth ('warm voice' / 'close friend')",
       "warm voice" in block and "close friend" in block)
    ok("contract: bans the scaffold-leak failure modes (brackets / 'according to my memory')",
       "Never read the brackets" in block and "according to my memory" in block)
    ok("contract: bans listing facts back like a record",
       "list these back like a record" in block or "list them back" in block.lower())

    # ---- ordering: KNOWN facts lead the block ----
    ok("contract: KNOWN facts are rendered before SEEN/SENSE (bound facts lead)",
       block.index("[KNOWN]") < block.index("[SEEN]") < block.index("[SENSE]"))

    # =====================================================================
    # §1.4 — the honesty wall: ABSENT + asked -> a single [UNKNOWN] line, NO false FACT.
    # =====================================================================
    empty_known = bind([], "when's my birthday?")
    ok("UNKNOWN: empty selection + a routed trait -> renders an [UNKNOWN] line",
       "[UNKNOWN]" in empty_known)
    ok("UNKNOWN: the [UNKNOWN] line names the asked slot (birthday)",
       "[UNKNOWN] birthday" in empty_known)
    ok("UNKNOWN: binds to admit + ask, never to assert ('when is it?')",
       "when is it?" in empty_known and "NEVER invent" in empty_known)
    ok("UNKNOWN: renders NO [KNOWN] item (no false FACT on an empty slot)",
       "[KNOWN]" not in items_of(empty_known))

    # ---- ABSENT + off-topic -> NO contract at all (nothing to bind) ----
    off_topic = bind([], "what's the weather like today?")
    ok("off-topic empty turn -> empty string (no contract, nothing to bind)",
       off_topic == "")

    # ---- a SENSE-only / contested set never emits a [KNOWN] (no false FACT) ----
    soft_only = bind([_row("birthday", "September 14", confidence=0.97, support=3,
                           needs_reconfirm=True)], "when's my birthday?")
    ok("contested birthday renders as [SENSE], NEVER [KNOWN] (no false-settled fact)",
       "[SENSE]" in items_of(soft_only) and "[KNOWN]" not in items_of(soft_only))

    # ---- robustness: garbage rows are dropped, never fatal ----
    ok("bind tolerates None / garbage rows without raising",
       isinstance(bind([None, 42, "nope", {"no_trait": 1}], "hi"), str))

    # =====================================================================
    # PART 3 — answer_from_fact: warm, correct, deterministic; honest on unknowns.
    # =====================================================================
    # ---- a correct WARM birthday answer ----
    bday = answer_from_fact("when's my birthday?",
                            _row("birthday", "September 14", confidence=0.95, support=2),
                            name="vera")
    ok("answer: birthday assembled answer is non-empty", bool(bday))
    ok("answer: birthday answer carries the real value", "September 14" in (bday or ""))
    ok("answer: birthday answer is warm + possessive (mentions 'your' or 'yours')",
       any(w in (bday or "").lower() for w in ("your", "yours")))
    ok("answer: birthday answer leaks NO scaffold tokens",
       not any(tok in (bday or "") for tok in SCAFFOLD_TOKENS))

    # ---- a correct WARM dog answer ----
    dog = answer_from_fact("what's my dog's name?",
                           _row("dog_name", "Biscuit", confidence=0.99, support=4),
                           name="vera")
    ok("answer: dog assembled answer is non-empty", bool(dog))
    ok("answer: dog answer carries the real value", "Biscuit" in (dog or ""))
    ok("answer: dog answer is warm + possessive",
       "your" in (dog or "").lower() or "dog" in (dog or "").lower())

    # ---- a generic trait still assembles warmly ----
    fav = answer_from_fact("what's my favorite color?",
                           _row("favorite_color", "green", confidence=0.9, support=1))
    ok("answer: a banked-or-generic trait still assembles with the value",
       bool(fav) and "green" in (fav or ""))
    emp = answer_from_fact("where do I work?",
                           _row("employer", "Collatio", confidence=0.92, support=2))
    ok("answer: employer assembles with the value", bool(emp) and "Collatio" in (emp or ""))

    # ---- determinism: same (creature, trait) -> same phrasing; creatures may differ ----
    a1 = answer_from_fact("when's my birthday?", _row("birthday", "September 14"), name="vera")
    a2 = answer_from_fact("when's my birthday?", _row("birthday", "September 14"), name="vera")
    ok("answer: deterministic per (creature, trait) — same creature, same phrasing", a1 == a2)
    variants = {
        answer_from_fact("when's my birthday?", _row("birthday", "September 14"), name=nm)
        for nm in ("vera", "aria", "milo", "juno", "sol", "wren", "ozzy", "kit")
    }
    ok("answer: different creatures CAN draw different phrasings (seed folds the name)",
       len(variants) >= 2)

    # =====================================================================
    # PART 3 — the honesty wall: empty / UNKNOWN / soft rows yield NO false FACT.
    # =====================================================================
    ok("answer: a missing row (None) -> None (she asks, never asserts)",
       answer_from_fact("when's my birthday?", None) is None)
    ok("answer: an empty-value row -> None (no fabricated fact)",
       answer_from_fact("when's my birthday?", _row("birthday", "")) is None)
    ok("answer: a SOFT (sub-0.85) row -> None (uncertain facts are NOT asserted)",
       answer_from_fact("when's my birthday?",
                        _row("birthday", "September 14", confidence=0.60)) is None)
    ok("answer: a CONTESTED (needs_reconfirm) birthday -> None (never asserted as settled)",
       answer_from_fact("when's my birthday?",
                        _row("birthday", "September 14", confidence=0.97,
                             needs_reconfirm=True)) is None)
    ok("answer: an inactive/retracted row -> None",
       answer_from_fact("when's my birthday?",
                        _row("birthday", "September 14", status="retracted")) is None)
    ok("answer: a third-party (non-SELF) row -> None (never an answer ABOUT the user)",
       answer_from_fact("what's my dog's name?",
                        _row("dog_name", "Biscuit", entity="neighbor")) is None)
    ok("answer: a non-dict fact_row -> None (never raises)",
       answer_from_fact("hi", "not a dict") is None)

    # =====================================================================
    # The single-source-of-truth tie: asked_trait routes on the SAME table as fact_note.
    # =====================================================================
    ok("route: 'date of birth' resolves to the birthday slot (alias precision)",
       asked_trait("remind me my date of birth") == "birthday")
    ok("route: an off-topic question routes to NO slot",
       asked_trait("what's the weather like today?") is None)

    # =====================================================================
    # honest_unknown — the user-facing HONEST-ADMISSION floor (inverse of answer_from_fact).
    # =====================================================================
    hu = honest_unknown("when's my birthday?", name="vera")
    ok("honest_unknown: a routed trait yields a warm admission", bool(hu))
    ok("honest_unknown: admits + asks ('don't have' + a question)",
       hu is not None and "don't" in hu.lower() and "?" in hu)
    ok("honest_unknown: names the asked slot (birthday)", hu is not None and "birthday" in hu.lower())
    ok("honest_unknown: asserts NO value + leaks NO scaffold",
       hu is not None and not any(tok in hu for tok in SCAFFOLD_TOKENS))
    ok("honest_unknown: an off-topic turn yields None (nothing to admit)",
       honest_unknown("what's the weather like today?") is None)
    ok("honest_unknown: deterministic per (creature, trait)",
       honest_unknown("when's my birthday?", name="vera") == hu)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL SPINE SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv or len(sys.argv) == 1:
        raise SystemExit(_selftest())
    print("usage: /opt/homebrew/bin/python3 anima/spine.py --selftest")
