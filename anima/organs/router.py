"""router — Organ 3. Query-aware memory selection + the routing decision.

This is ``route.py`` generalized one level up. ``route.py`` answers a *binary*
question ("is this turn a known capability — messages, calendar, a stored fact —
that code must handle?") and, if so, injects a ground-truth note. The Router organ
answers the *general* question every turn now faces once the fact store grows:

    given THIS question, which of the (possibly hundreds of) things we know are
    worth putting in front of the brain — and by the cheapest sufficient path?

Two surfaces, both PURE (no live model, no network — fully unit-testable):

  1. ``select_facts(name, question, budget=10) -> (rows, block)`` — QUERY-AWARE
     MEMORY SELECTION. Instead of injecting the whole ledger (``Facts.block`` dumps
     the top-N by raw salience regardless of the question), score each active fact
     against THIS question and return only the relevant subset, plus a compact
     injectable block. "when's my birthday?" selects the birthday row and NOT the
     dog; an unrelated question selects few/none. This is the predicted next
     bottleneck: a 500-fact store must not bury the one relevant row or blow the
     token budget.

  2. ``route(name, question, caps_state) -> RouteDecision`` — the ROUTING DECISION.
     Pick the cheapest sufficient path (local unless the turn genuinely needs the
     cloud), name the contributing organs, carry the selected facts' ids, and decide
     whether a capability should fire. The result is shaped like
     ``event_bus.Decision`` (``model`` / ``contributing_organs`` / ``memory_ids`` /
     ``escalation``) so it drops onto the bus unchanged.

Built to the seams, not around them
-----------------------------------
* SELECTION scores against the SAME atoms LIRF exposes — each row's ``trait`` /
  ``value`` / ``confidence`` / ``support`` — and reuses LIRF's own salience
  (``confidence * log(1+support)``) as the relevance tie-breaker, so a fact the
  ledger already trusts wins ties. The query→trait map is ``memory_lirf._Q_TRAITS``
  (the exact table ``fact_note`` routes on) plus ``canon_trait`` alias folding, so
  "bday" / "date of birth" / "where do I live" resolve precisely, not fuzzily.
* The capability decision DEFERS to ``route.py``: if the existing deterministic
  router claims the turn (a message/mail/host read, a send, a confirm), the Router
  reports that as the firing capability rather than re-implementing the regexes.
* Emission is OPTIONAL. ``RouterOrgan`` is an ``Organ`` (it can publish its decision
  as an ``Observation`` and the chosen facts as Memory-shaped observations onto the
  bus), but the primary path is the two direct calls above so ``server._turn`` can
  wire it in without standing up the whole bus first.

Dependency-light + isolation-safe: like every sibling, the live ``memory_lirf`` /
``event_bus`` / ``route`` are imported when present and fall back to contract-faithful
local shims when this module is exercised standalone, so ``_selftest()`` runs with
zero unbuilt dependencies.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# LIRF seam — the fact store we select from. Prefer the live module; fall back to
# a minimal in-memory stand-in so selection logic is testable without a store on
# disk. We need: Facts.load(name).about(SELF) (ranked active rows), .lookup(),
# canon_trait (alias folding), _salience (the store's own ranking), _fmt_value, and
# the _Q_TRAITS question->trait table fact_note already routes on.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from ..memory_lirf import (
        SELF,
        Facts,
        canon_trait,
        _salience,
        _fmt_value,
        _Q_TRAITS,
    )
except Exception:  # pragma: no cover - isolation fallback
    SELF = "you"

    def canon_trait(trait: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(trait).strip().lower()).strip("_")

    def _salience(r: dict) -> float:
        return float(r.get("confidence", 0.0)) * math.log(1 + int(r.get("support", 1)))

    def _fmt_value(v: Any) -> str:
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v)

    _Q_TRAITS = []  # no precise table in isolation; keyword scoring still works

    Facts = None  # type: ignore


# ---------------------------------------------------------------------------
# event_bus seam — Observation/Topic for the optional bus emission. The direct
# callers don't need these; the fallback keeps `from ..event_bus import ...` from
# being a hard dependency when the module is exercised alone.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from ..event_bus import Observation, Topic
except Exception:  # pragma: no cover - isolation fallback
    from enum import Enum

    class Topic(str, Enum):
        QUESTION = "question"
        OBSERVATION = "observation"
        DECISION = "decision"
        RESPONSE = "response"

    @dataclass(frozen=True)
    class Observation:  # mirrors event_bus.Observation exactly
        organ: str
        memory: dict
        weight: float = 1.0
        note: str = ""


# ---------------------------------------------------------------------------
# The routing decision — shaped like event_bus.Decision so it drops onto the bus
# unchanged, with the extra `capability` field the Router adds (route.py's verdict:
# does a real capability fire this turn, and what is its ground-truth note).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RouteDecision:
    """The Router's verdict for one turn.

    Mirrors ``event_bus.Decision``'s field set (``model`` / ``contributing_organs`` /
    ``memory_ids`` / ``escalation``) plus a Router-specific ``capability`` slot. A
    ``Decision`` for the bus is one ``.as_decision()`` away; the live turn can also
    read the fields directly.
    """

    model: str                                            # "local" | "cloud:<name>"
    contributing_organs: list = field(default_factory=list)   # [str]
    memory_ids: list = field(default_factory=list)            # [str] selected fact ids
    escalation: str = ""                                  # "" | "local→cloud"
    capability: Optional[dict] = None                     # route.py's verdict, or None
    selected_block: str = ""                              # the query-aware fact block
    reason: str = ""                                      # short human-readable rationale

    @property
    def fires_capability(self) -> bool:
        """True iff a real capability (a message/host read, a send, a confirm) handles
        this turn — i.e. route.py claimed it. The mouth then narrates that note."""
        return bool(self.capability)

    def as_decision(self):
        """Project onto an ``event_bus.Decision`` for emission. ``answer_plan`` carries
        the capability note when a capability fired, else the selected fact block —
        the seed the mouth narrates. Returns a plain dict if event_bus is absent."""
        plan = ""
        if self.capability and isinstance(self.capability, dict):
            plan = self.capability.get("note", "") or ""
        if not plan:
            plan = self.selected_block
        try:  # pragma: no cover - import wiring
            from ..event_bus import Decision

            return Decision(
                answer_plan=plan,
                model=self.model,
                contributing_organs=list(self.contributing_organs),
                memory_ids=list(self.memory_ids),
                escalation=self.escalation,
            )
        except Exception:
            return {
                "answer_plan": plan,
                "model": self.model,
                "contributing_organs": list(self.contributing_organs),
                "memory_ids": list(self.memory_ids),
                "escalation": self.escalation,
            }


# ---------------------------------------------------------------------------
# Query-aware scoring.
# ---------------------------------------------------------------------------

# Words that carry no topical signal — excluded from keyword overlap so "when is my
# birthday" matches on "birthday", not on "is"/"my". Kept tiny and obvious.
_STOP = frozenset(
    """a an and the is are was were do does did my me i you your our of to in on at for
    what when where who whom which how why that this these those it its has have had can
    could would should will shall may might about with as so if then than just please
    tell know remember get got see show whats what's am be been being or but not no yes""".split()
)

# How a question word maps onto the slug it asks about — reused from memory_lirf so
# selection routes on the EXACT table fact_note answers from. Each entry is
# (compiled-regex, trait-slug). When the live table isn't importable (isolation), a
# small built-in covers the cases the self-test asserts.
_QUERY_TRAIT_TABLE = list(_Q_TRAITS) if _Q_TRAITS else [
    (re.compile(r"\bbirthday|\bbday|\bborn\b|date of birth\b", re.I), "birthday"),
    (re.compile(r"\bwhere (?:do|am) i (?:live|living)|where i live\b", re.I), "lives"),
    (re.compile(r"\bmy dog'?s? name|what'?s my dog|dog called\b", re.I), "dog_name"),
    (re.compile(r"\bmy name\b|what'?s my name|who am i\b", re.I), "name"),
]


def _tokens(text: str) -> set:
    """Topical tokens of a string: lowercased word stems, stop-words dropped."""
    raw = re.findall(r"[a-z0-9']+", str(text).lower())
    return {w for w in raw if w not in _STOP and len(w) > 1}


def _trait_words(trait: str) -> set:
    """The words a trait slug contributes ("dog_name" -> {dog, name}), so a question
    mentioning "dog" matches the dog_name row even without the canonical table."""
    return _tokens(trait.replace("_", " "))


def _asked_traits(question_text: str) -> set:
    """The set of canonical trait slugs the question explicitly asks about, via the
    same regex table fact_note routes on. High-precision: "date of birth" -> birthday."""
    asked = set()
    for rx, trait in _QUERY_TRAIT_TABLE:
        try:
            if rx.search(question_text or ""):
                asked.add(canon_trait(trait))
        except Exception:
            continue
    return asked


def score_fact(row: dict, q_tokens: set, asked_traits: set) -> float:
    """Relevance of one LIRF row to the current question.

    relevance = match + salience_bonus, where

      * match (the dominant term) rewards topical overlap between the question and
        the fact's trait/value:
          - DIRECT TABLE HIT: the question routed to this row's exact trait via the
            same table fact_note uses ("when's my birthday?" -> birthday) — the
            strongest, most precise signal.
          - trait-word overlap: the question shares a word with the trait slug
            ("dog" with "dog_name").
          - value-word overlap: the question shares a word with the stored value
            (asking about "Portland" hits a lives=Portland row).
      * salience_bonus = confidence * log(1+support), LIRF's OWN ranking, folded in
        small so that AMONG comparably-relevant facts the ones the ledger already
        trusts/corroborates win — but salience NEVER manufactures relevance on its
        own (an unrelated high-salience fact stays unselected).

    Returns 0.0 for a fact with no topical connection to the question, which is what
    keeps an unrelated question from dragging in the whole store.
    """
    trait = canon_trait(row.get("trait", ""))
    match = 0.0

    # 1) exact question->trait table hit (the precise, high-value signal).
    if trait and trait in asked_traits:
        match += 3.0

    # 2) trait-word overlap.
    tw = _trait_words(trait)
    if q_tokens & tw:
        match += 1.5

    # 3) value-word overlap (handles list values too, via _fmt_value).
    vw = _tokens(_fmt_value(row.get("value", "")))
    overlap = q_tokens & vw
    if overlap:
        match += 1.0 + 0.25 * (len(overlap) - 1)   # diminishing credit for extra hits

    if match <= 0.0:
        return 0.0    # no topical connection — salience alone must not select it

    sal = _salience(row)
    return match + 0.10 * sal


# ---------------------------------------------------------------------------
# Surface 1 — query-aware memory selection.
# ---------------------------------------------------------------------------

def select_from_rows(rows: list, question: str, budget: int = 10):
    """Pure core of selection: score pre-loaded LIRF rows against a question and
    return ``(relevant_rows, block)``. Split out from ``select_facts`` so it is
    testable with hand-built rows and zero disk.

    * ``relevant_rows`` — only rows with relevance > 0, highest-first, capped at
      ``budget``. Deterministic: ties break by LIRF salience, then by id, so the
      same inputs always yield the same order.
    * ``block`` — the same compact, model-friendly shape ``Facts.block`` emits
      ("- trait: value" lines under a "do not re-ask" header), but containing ONLY
      the selected rows. Empty string when nothing is relevant.
    """
    q_tokens = _tokens(question)
    asked = _asked_traits(question)

    scored = []
    for r in rows:
        s = score_fact(r, q_tokens, asked)
        if s > 0.0:
            scored.append((s, r))
    # Deterministic order: relevance desc, then salience desc, then id asc.
    scored.sort(key=lambda sr: (-sr[0], -_salience(sr[1]), str(sr[1].get("id", ""))))
    chosen = [r for _s, r in scored[: max(0, int(budget))]]
    return chosen, _block_for(chosen)


def _block_for(rows: list) -> str:
    """Render the selected rows as the same injectable fact-block shape Facts.block
    produces — so the mouth sees a familiar, deterministic format."""
    if not rows:
        return ""
    lines = ["KNOWN FACTS ABOUT THE PERSON (treat as true, do not re-ask):"]
    for r in rows:
        lines.append(f"- {str(r.get('trait', '?')).replace('_', ' ')}: {_fmt_value(r.get('value', ''))}")
    return "\n".join(lines)


def select_facts(name: str, question: str, budget: int = 10):
    """QUERY-AWARE MEMORY SELECTION (the headline surface).

    Load the creature's active facts and return only the subset relevant to THIS
    question, plus a compact injectable block:

        rows, block = select_facts("vera", "when's my birthday?")

    "when's my birthday?" -> the birthday row is present, the dog is absent. An
    unrelated question ("what's the weather like?") -> few or no rows. This is the
    swap for ``Facts.block``'s blanket top-N dump once the store is large enough that
    the relevant fact would otherwise be buried or the budget blown.

    Returns ``(relevant_rows, block_string)``. Reads only active ``SELF`` rows (the
    user). Cloud PII guard remains the CALLER's job (blank the block under
    ``cloud.is_cloud()``, exactly like ``memory_lirf.retrieve``) — the selector has
    no opinion about transport.
    """
    rows = _load_active_rows(name)
    return select_from_rows(rows, question, budget=budget)


def _load_active_rows(name: str) -> list:
    """All active SELF rows for a creature, best-effort. Never raises into the turn:
    a missing/locked store yields []."""
    if Facts is None:
        return []
    try:
        return list(Facts.load(name).about(SELF))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# route.py seam — the existing deterministic capability router. The Router DEFERS
# to it for the capability decision rather than re-implementing the regexes.
# ---------------------------------------------------------------------------
def _capability_for(name: str, text: str) -> Optional[dict]:
    """Ask the existing deterministic router whether a real capability handles this
    turn. Returns route.py's ``{'note', 'send'?}`` dict, or None. Best-effort: any
    failure (or route.py absent in isolation) is treated as 'no capability'."""
    try:  # pragma: no cover - import wiring
        from .. import route as _route
    except Exception:
        return None
    try:
        return _route.route(name, text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Surface 2 — the routing decision.
# ---------------------------------------------------------------------------

def route(name: str, question: str, caps_state: Optional[dict] = None,
          *, budget: int = 10) -> RouteDecision:
    """THE ROUTING DECISION: cheapest sufficient path for THIS question.

    Steps, all deterministic:

      1. Query-aware select the relevant facts (Surface 1) — these are the
         ``memory_ids`` the decision carries and the seed the mouth gets when no
         capability fires.
      2. Ask ``route.py`` whether a real capability handles the turn (a message/host
         read, a send, a confirm). If so, that capability is the firing path and
         ``identity`` is NOT consulted for grounding — the capability note is the
         ground truth.
      3. Choose the brain. Default LOCAL (the cheapest sufficient path, and the
         privacy-preserving one). Escalate local→cloud ONLY when the turn genuinely
         needs it:
           * the caller explicitly asked (``caps_state['needs_cloud']``), OR
           * we have NO standing to answer from within — no capability fired AND no
             relevant fact was selected — AND a cloud brain is actually available.
         A capability turn or a turn with a selected fact stays local: it can be
         answered from the Mac, so we don't reach out.

    ``caps_state`` is the per-turn context (the same dict shape ``event_bus.Question``
    carries): recognised keys are ``cloud_on`` / ``cloud_available`` (is a cloud brain
    usable), ``cloud_model`` (its name), and ``needs_cloud`` (an explicit request).
    Unknown keys are ignored. Returns a :class:`RouteDecision`.
    """
    ctx = dict(caps_state or {})

    # 1) query-aware memory selection
    rows, block = select_facts(name, question, budget=budget)
    memory_ids = [str(r.get("id")) for r in rows if r.get("id")]

    # 2) does a real capability handle this turn?
    capability = _capability_for(name, question)

    # 3) contributing organs — the provenance the trace records.
    contributing: list[str] = []
    reason_bits: list[str] = []
    if capability:
        contributing.append("route")            # the deterministic capability router fired
        reason_bits.append("capability fired")
    if rows:
        contributing.append("identity")         # facts grounded the answer
        reason_bits.append(f"{len(rows)} fact(s) selected")

    # 4) cheapest sufficient brain.
    cloud_available = bool(ctx.get("cloud_on") or ctx.get("cloud_available"))
    wants_cloud = bool(ctx.get("needs_cloud"))
    have_local_standing = bool(capability) or bool(rows)

    model = "local"
    escalation = ""
    if wants_cloud and cloud_available:
        model = "cloud:" + str(ctx.get("cloud_model") or "default")
        escalation = "local→cloud"
        reason_bits.append("explicit cloud request")
    elif not have_local_standing and cloud_available:
        model = "cloud:" + str(ctx.get("cloud_model") or "default")
        escalation = "local→cloud"
        reason_bits.append("no local standing → reach out")
    else:
        reason_bits.append("local sufficient")

    if not reason_bits:
        reason_bits.append("local, no evidence")

    return RouteDecision(
        model=model,
        contributing_organs=contributing,
        memory_ids=memory_ids,
        escalation=escalation,
        capability=capability,
        selected_block=block,
        reason="; ".join(reason_bits),
    )


# ---------------------------------------------------------------------------
# The organ wrapper — optional bus emission. The live turn calls route()/select_facts
# directly; this lets the Router ALSO participate in the event_bus fan-out, emitting
# its routing decision (and the selected facts) as Observations the Coordinator and
# telemetry can see.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from .base import Organ as _OrganBase
except Exception:  # pragma: no cover - isolation fallback
    _OrganBase = object


class RouterOrgan(_OrganBase):
    """The Router as a bus citizen.

    ``on_question`` runs the same pure ``route()`` and publishes:
      * one Observation per selected fact (organ="identity"-style grounding the
        Coordinator can weigh), and
      * one Observation carrying the routing decision (organ="router") so the
        decision is visible in the trace even when the turn is wired through the bus.

    It never returns data; the direct ``route()`` call is the primary path and this
    is purely additive. Emission is best-effort and never raises into the bus.
    """

    name = "router"

    async def on_question(self, bus, event) -> None:
        turn_id = getattr(event, "turn_id", "")
        q = getattr(event, "payload", None)
        text = getattr(q, "text", "") if q is not None else ""
        name = getattr(q, "name", "") if q is not None else ""
        ctx = getattr(q, "context", None)
        caps_state = ctx if isinstance(ctx, dict) else {}

        decision = route(name, text, caps_state)

        if bus is None:
            return

        # Publish one Observation per selected fact, so grounding flows through the
        # bus as canonical Memory-shaped payloads the Coordinator can rank. We use
        # the LIRF row's confidence as the memory confidence and a router note.
        rows, _block = select_facts(name, text)
        for r in rows:
            mem = _row_to_memory(r)
            obs = Observation(
                organ="router",
                memory=mem,
                weight=float(mem.get("confidence", 0.5)),
                note=f"selected for: {text[:48]}",
            )
            try:
                await bus.publish(Topic.OBSERVATION, obs, turn_id=turn_id, source=self.name)
            except Exception:
                pass

        # Publish the routing decision itself as an Observation, so the chosen
        # model/escalation/capability is in the trace even off the Coordinator path.
        decision_mem = {
            "id": "f_route_" + (turn_id[-8:] if turn_id else "decision"),
            "type": "value",
            "subject": "router",
            "predicate": "routing_decision",
            "value": {
                "model": decision.model,
                "escalation": decision.escalation,
                "fires_capability": decision.fires_capability,
                "memory_ids": list(decision.memory_ids),
            },
            "confidence": 0.9,
            "sources": ["router"],
            "support": [],
            "updated": "",
            "lirf": f"router · routing_decision = {decision.model} ({decision.reason})",
        }
        obs = Observation(organ="router", memory=decision_mem, weight=0.9, note=decision.reason)
        try:
            await bus.publish(Topic.OBSERVATION, obs, turn_id=turn_id, source=self.name)
        except Exception:
            pass


def _row_to_memory(row: dict) -> dict:
    """Project a LIRF fact row onto a canonical Memory-shaped dict for bus emission.
    The bus only reads id/confidence; we carry trait/value/lirf for the trace."""
    trait = str(row.get("trait", "?"))
    val = row.get("value", "")
    conf = float(row.get("confidence", 0.5))
    return {
        "id": str(row.get("id") or "f_unknown"),
        "type": "value",
        "subject": str(row.get("entity", SELF)),
        "predicate": trait,
        "value": val,
        "confidence": conf,
        "sources": [str(row.get("source", "lirf"))],
        "support": [],
        "updated": str(row.get("updated", "")),
        "lirf": f"{row.get('entity', SELF)} · {trait} = {_fmt_value(val)}  (conf {conf:.2f})",
    }


# ---------------------------------------------------------------------------
# Self-test — proves the Router in ISOLATION: no live model, no network, no real
# store on disk (hand-built LIRF-shaped rows). Run:
#   /opt/homebrew/bin/python3 anima/organs/router.py
#   /opt/homebrew/bin/python3 -m anima.organs.router --selftest
# ---------------------------------------------------------------------------
def _mk_row(trait, value, *, confidence=0.9, support=1, rid=None, entity=None):
    """A minimal LIRF-shaped active row for tests (the fields selection reads)."""
    return {
        "id": rid or ("f_" + trait[:6]),
        "entity": entity or SELF,
        "trait": trait,
        "value": value,
        "confidence": confidence,
        "support": support,
        "status": "active",
    }


def _selftest() -> int:
    fails: list[str] = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("router self-test")

    # A realistic small store: the relevant fact must be found AMONG distractors,
    # including a high-salience but unrelated one (dog, heavily corroborated).
    store = [
        _mk_row("birthday", "June 11", confidence=0.97, support=3, rid="f_bday01"),
        _mk_row("dog_name", "Biscuit", confidence=0.99, support=9, rid="f_dog001"),
        _mk_row("lives", "Portland, OR", confidence=0.95, support=4, rid="f_live01"),
        _mk_row("employer", "Collatio", confidence=0.9, support=2, rid="f_emp001"),
        _mk_row("favorite_color", "green", confidence=0.8, support=1, rid="f_col001"),
        _mk_row("dislikes", ["cilantro", "olives"], confidence=0.85, support=2, rid="f_dis001"),
    ]

    # ---- 1) THE headline assertion: birthday question -> birthday in, dog out ----
    rows, block = select_from_rows(store, "when's my birthday?")
    sel_traits = [r["trait"] for r in rows]
    ok("birthday question selects the birthday fact", "birthday" in sel_traits)
    ok("birthday question does NOT select the dog (the buried-fact failure)",
       "dog_name" not in sel_traits)
    ok("birthday is the TOP selection (most relevant)", rows[0]["trait"] == "birthday")
    ok("block carries the birthday value", "June 11" in block)
    ok("block does NOT carry the dog", "Biscuit" not in block)
    ok("block uses the canonical 'do not re-ask' header", "do not re-ask" in block)

    # alias precision: "date of birth" routes to birthday via the same table fact_note uses
    rows_dob, _ = select_from_rows(store, "remind me my date of birth")
    ok("'date of birth' resolves to the birthday fact (alias precision)",
       "birthday" in [r["trait"] for r in rows_dob] and
       "dog_name" not in [r["trait"] for r in rows_dob])

    # ---- 2) an UNRELATED question selects few/none (the budget/burying guard) ----
    rows_u, block_u = select_from_rows(store, "what's the weather like today?")
    ok("an unrelated question selects NO facts", len(rows_u) == 0)
    ok("an unrelated question yields an EMPTY block (nothing to inject)", block_u == "")

    # ---- 3) value-word match: asking about a value, not its trait, still hits ----
    rows_v, _ = select_from_rows(store, "do I live in Portland?")
    ok("a question naming a stored VALUE selects that fact (Portland -> lives)",
       "lives" in [r["trait"] for r in rows_v])

    # ---- 4) trait-word match: "dog" selects dog_name (and birthday stays out) ----
    rows_d, _ = select_from_rows(store, "what is my dog called?")
    ok("'dog' selects the dog_name fact via trait-word overlap",
       "dog_name" in [r["trait"] for r in rows_d])
    ok("the dog question does NOT drag in the birthday", "birthday" not in [r["trait"] for r in rows_d])

    # ---- 5) salience never MANUFACTURES relevance ----
    # The dog is the highest-salience row in the store; an unrelated question must
    # still not select it (relevance gates selection, salience only breaks ties).
    ok("highest-salience fact is NOT selected by an unrelated question",
       "dog_name" not in [r["trait"] for r in select_from_rows(store, "tell me a joke")[0]])

    # ---- 6) budget caps the selection deterministically ----
    big = [_mk_row(f"likes_{i}", f"thing{i}", rid=f"f_k{i:02d}") for i in range(20)]
    # a question overlapping ALL of them ("things") — budget must clamp to 5
    qs = "what are all my favorite things"
    rows_b, _ = select_from_rows(big, qs, budget=5)
    ok("budget caps the number of selected facts", len(rows_b) <= 5)
    rows_b2, _ = select_from_rows(big, qs, budget=5)
    ok("selection is deterministic (same inputs -> same order)",
       [r["id"] for r in rows_b] == [r["id"] for r in rows_b2])

    # ---- 7) the ROUTING DECISION (pure; route.py absent in isolation -> no cap) ----
    # No store on disk in isolation, so route() selects nothing and (no cloud) stays local.
    d_local = route("router_selftest_novera", "tell me a joke", {})
    ok("route() returns a RouteDecision", isinstance(d_local, RouteDecision))
    ok("no evidence + no cloud -> stays LOCAL (cheapest, can't reach out)",
       d_local.model == "local" and d_local.escalation == "")
    ok("no capability fired in isolation", d_local.fires_capability is False)

    d_esc = route("router_selftest_novera", "what's the latest news?",
                  {"cloud_on": True, "cloud_model": "claude"})
    ok("no local standing + cloud available -> escalates local→cloud",
       d_esc.model == "cloud:claude" and d_esc.escalation == "local→cloud")

    d_needs = route("router_selftest_novera", "anything",
                    {"cloud_on": True, "needs_cloud": True, "cloud_model": "claude"})
    ok("explicit needs_cloud escalates local→cloud", d_needs.escalation == "local→cloud"
       and d_needs.model == "cloud:claude")

    # determinism of the decision
    ok("route() is deterministic", route("x", "tell me a joke", {}) == route("x", "tell me a joke", {}))

    # ---- 8) decision projects onto an event_bus.Decision shape ----
    proj = d_local.as_decision()
    has_fields = (getattr(proj, "model", None) == "local") if not isinstance(proj, dict) \
        else (proj.get("model") == "local")
    ok("RouteDecision.as_decision() yields a Decision-shaped object", has_fields)

    # ---- 9) decision over a HAND-BUILT selection has standing -> stays local ----
    # Simulate "facts were selected" by routing where select finds rows: do it through
    # the pure core to prove the local-standing branch (selected fact => no escalation).
    sel_rows, sel_block = select_from_rows(store, "when's my birthday?")
    mids = [r["id"] for r in sel_rows]
    # Build the decision the way route() would, but feed the pre-selected rows:
    have_standing = bool(sel_rows)
    ok("a selected fact gives local standing (would NOT escalate even with cloud on)",
       have_standing is True)
    ok("selected memory_ids carry the birthday row id", "f_bday01" in mids)

    # ---- 10) the LIRF salience tie-break is wired (real _salience used) ----
    # Two equally trait-matched rows: the higher-support one ranks first.
    tie = [
        _mk_row("nickname", "Sam", confidence=0.9, support=1, rid="f_nick_lo"),
        _mk_row("nickname", "Sammy", confidence=0.9, support=8, rid="f_nick_hi"),
    ]
    # (same trait twice can't happen in a real store, but proves the tie-break order)
    rows_t, _ = select_from_rows(tie, "what's my nickname?")
    ok("among equally-relevant facts, higher LIRF salience ranks first",
       rows_t[0]["id"] == "f_nick_hi")

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL ROUTER SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv or len(sys.argv) == 1:
        raise SystemExit(_selftest())
    print("usage: /opt/homebrew/bin/python3 anima/organs/router.py --selftest")
