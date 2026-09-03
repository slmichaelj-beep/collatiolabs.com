"""opportunity — THE OPPORTUNITY ENGINE: "what would HELP?", as a gentle, optional OFFER.

This is where Vera turns from reactive to proactive. The reactive organs answer questions
the user just asked. The Meaning Engine answers "what MATTERS?". The Dream Engine answers
"what did you SAY you'd do, and where did it go?". This engine asks the next question —
"given what I've actually observed, what could I OFFER that would HELP?" — and packages the
answer as an OFFER, never an action.

THE ONE INVARIANT, ABOVE ALL ELSE — OFFER, NOT ACTION
-----------------------------------------------------
An opportunity is a *proposal*: "you've mentioned the podcast for months — want me to help
sketch a milestone plan?". It is a STRING. This engine NEVER does the thing it offers. It
does not send a text, write a reminder, touch a calendar, call ``route``, or invoke any
executor. It READS the life signals and APPENDS to its own offer ledger — nothing else.
If the user says "yes", the ACTING flows through the existing draft→confirm→execute gate in
``route.py`` (which this module does not import and does not touch) — on the user's explicit
second action, never here. This is the difference between a companion who *suggests* and a
bot that *acts on your behalf without asking*. We are the former. The ``test_opportunity.py``
invariant proves it: with every host/route/calendar/reminder executor monkeypatched to blow
up, generating and pacing opportunities calls NONE of them.

WHAT AN OPPORTUNITY IS MADE OF — Observed > Assumed
---------------------------------------------------
Every opportunity is GROUNDED in something the system actually observed, carries the
EVIDENCE, and is confidence-scored. There is NO generic tip ("you should journal!"): if the
evidence isn't there, the engine stays silent. The three grounded kinds (more can be added
the same way — each must cite real evidence):

  * STALLED_PROJECT — a stated commitment that the Dream Engine reads as ``stalled`` AND
    that the Meaning Engine reads as significant. "You've mentioned the podcast for months —
    want me to help sketch a milestone plan?" (loops + meaning.)
  * UNEXPLAINED_ENTITY — a person/place/thing the user brings up often whose meaning Vera
    does NOT yet know (a SUSPECTED curiosity gap on a high-mention entity). "You bring that
    place up a lot — want me to remember why it matters to you?" (curiosity + meaning.)
  * DECLINING_THREAD — a topic with real prior weight whose recent activity has fallen off
    (the Meaning Engine's ``what_declining`` dimension). A gentle, fully-optional nudge —
    never "you've given up on X", only "want to make a little room for it again?"

A teammate is building ``trajectory.py`` (direction/momentum) in parallel. We read it
DEFENSIVELY (try/except): opportunities work entirely without it, and are merely *richer*
with it — a declining-trajectory dimension can sharpen a DECLINING_THREAD's confidence. We
never hard-depend on it and never raise if it is absent or half-built.

PACING + LEDGER — gentle, never nagging (the #1 product rule)
------------------------------------------------------------
``next_opportunity`` returns AT MOST ONE un-offered opportunity, paced by a budget exactly
like ``curiosity`` and ``loops`` (minimal/balanced/deep → how OFTEN, never the content). The
offer ledger is append-only: once offered, the same opportunity is NOT offered again — unless
it was DECLINED and has since become clearly relevant again (stronger evidence than at decline
time). A warm offer, never a demand; the door is always open to decline.

Isolation-safe like its siblings: it READS the live engines when importable and degrades to
empty (never raises) when they are not, so ``--selftest`` has zero unbuilt deps and touches
no model, network, or the real ``.anima``. It is READ-ONLY over every other store; the ONLY
thing it writes is its own append-only offer ledger.

    from anima import opportunity
    for o in opportunity.opportunities("Vera"):
        print(o["kind"], "—", o["offer"])
    line = opportunity.next_opportunity("Vera")     # at most one warm offer, or None
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. We READ the live engines when importable and
# degrade to empty otherwise — this module never hard-depends on them, never
# writes them, and never raises if they are absent. We need, at most:
#   loops.detect_loops      — stated commitments + their status (the STALLED ones)
#   meaning.significance    — what MATTERS (significance ranking, the soft grounding)
#   meaning.meaning         — the dimensioned Meaning Objects (what_declining etc.)
#   curiosity.detect_gaps   — the SUSPECTED high-mention unexplained-entity gaps
#   trajectory.*            — direction/momentum (OPTIONAL, read purely defensively)
# Each is wrapped so a missing/erroring dep is simply "no signal", not a crash.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from . import loops as _loops
    _HAVE_LOOPS = True
except Exception:  # pragma: no cover - isolation fallback
    _loops = None
    _HAVE_LOOPS = False

try:  # pragma: no cover - import wiring
    from . import meaning as _meaning
    _HAVE_MEANING = True
except Exception:  # pragma: no cover - isolation fallback
    _meaning = None
    _HAVE_MEANING = False

try:  # pragma: no cover - import wiring
    from . import curiosity as _curiosity
    _HAVE_CURIOSITY = True
except Exception:  # pragma: no cover - isolation fallback
    _curiosity = None
    _HAVE_CURIOSITY = False

# The teammate's parallel build. PURELY optional — opportunities never depend on it. We do
# the import lazily inside the reader so that even an import that succeeds-then-errors later
# (a half-built module) cannot affect us. The flag is a hint only.
try:  # pragma: no cover - import wiring (the module may not exist yet)
    from . import trajectory as _trajectory  # noqa: F401
    _HAVE_TRAJECTORY = True
except Exception:  # pragma: no cover - the expected state until the teammate lands it
    _trajectory = None
    _HAVE_TRAJECTORY = False

# The verbatim laws, read from the constitution when present so there is ONE source of
# truth; a tiny literal fallback keeps the self-test dependency-free. LAW 003 (Understanding
# beats remembering) is the closest in spirit — an offer must be grounded in evidence of what
# MATTERS, never narrated — so we surface it as the engine's guiding law.
try:  # pragma: no cover - import wiring
    from .constitution import LAW_003 as _LAW_003, LAW_003_ID as _LAW_ID
except Exception:  # pragma: no cover - isolation fallback
    _LAW_ID = "ANIMA LAW 003"
    _LAW_003 = (
        "ANIMA LAW 003 — UNDERSTANDING BEATS REMEMBERING. "
        "Recall is not the goal; significance is. Meaning is derived from evidence "
        "(frequency, connectivity, trend), carried with confidence, and never asserted "
        "beyond it."
    )


def law() -> str:
    """The verbatim law that grounds this engine: an offer must be built on observed
    significance, evidence-cited, never asserted beyond it. Single source of truth
    (constitution constant, or a faithful literal fallback)."""
    return _LAW_003


# Where the creature's life is kept — mirrors world_state / curiosity / meaning / loops so
# the offer ledger sits beside the things it draws on. Overridable for tests (the self-test
# and scripts/test_opportunity.py redirect this to a TemporaryDirectory). Same env contract
# as the sibling engines.
STORE = Path(os.environ.get("ANIMA_STORE", ".anima"))

VERSION = 1


def _now() -> str:
    """UTC ISO-8601 to the second, matching the sibling engines' stamp shape."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    """Stable opportunity-event id ('o_' prefix to read distinctly from l_/q_ ledgers)."""
    return "o_" + secrets.token_hex(6)


def _parse_ts(ts: Any) -> Optional[float]:
    """Best-effort ISO timestamp -> epoch seconds. None on anything unparseable, so a
    missing/garbled stamp simply doesn't contribute to recency (never raises)."""
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _days_since(ts: Any, *, now: Optional[float] = None) -> Optional[float]:
    """Whole-ish days between ``ts`` and now (float). None if ``ts`` is unparseable."""
    t = _parse_ts(ts)
    if t is None:
        return None
    ref = now if now is not None else datetime.now(timezone.utc).timestamp()
    return max(0.0, (ref - t) / 86400.0)


# ===========================================================================
# THE OPPORTUNITY KINDS — a small closed vocabulary. Each one is grounded in a
# DIFFERENT observed signal; adding a kind means adding a real evidence source,
# never a generic tip. (Observed > Assumed.)
# ===========================================================================
STALLED_PROJECT = "stalled_project"      # a stalled, significant stated commitment
UNEXPLAINED_ENTITY = "unexplained_entity"  # an often-mentioned entity Vera can't explain
DECLINING_THREAD = "declining_thread"    # a once-weighty topic that's fallen off lately

KINDS = (STALLED_PROJECT, UNEXPLAINED_ENTITY, DECLINING_THREAD)


# The minimum significance an entity/topic must clear before it is worth an offer. The
# Meaning Engine omits sub-1.0 islands already; we ask for a little more so an offer only
# fires on something that genuinely registers. (Observed > Assumed: a lone mention is not an
# opportunity.)
_MIN_SIGNIFICANCE = 1.0

# How many times an entity must be mentioned before "you bring this up a lot" is honest. We
# float to the curiosity SUSPECT floor when it is importable (single source of truth), with a
# safe literal fallback so the self-test has no hard dep.
def _suspect_floor() -> int:
    try:
        v = int(getattr(_curiosity, "_SUSPECT_MENTION_FLOOR", 3))
        return v if v >= 1 else 3
    except Exception:
        return 3


# ===========================================================================
# THE SIGNALS — read each live engine DEFENSIVELY. Every reader returns a plain
# structure (or empty) and never raises, so a missing/half-built engine is simply
# "no signal here", not a crash. This is the isolation contract the siblings keep.
# ===========================================================================

def _read_loops(name: str, *, now: Optional[float] = None) -> list:
    """Active loops with their status (read-only). [] if loops isn't importable/usable.
    We pass ``now`` through so a test can pin the clock. Never raises."""
    if not (_HAVE_LOOPS and _loops is not None):
        return []
    try:
        out = _loops.detect_loops(name, now=now)
        return [L for L in out if isinstance(L, dict)]
    except Exception:
        return []


def _significance_index(name: str) -> dict:
    """A ``{topic_token: significance_item}`` view of the Meaning Engine's significance, read
    defensively, so a loop intent or an entity can be matched to "does this MATTER, and by how
    much". {} if meaning isn't importable/usable. Never raises — significance is the grounding
    that turns a bare loop into an *opportunity*, but its absence just means fewer offers."""
    if not (_HAVE_MEANING and _meaning is not None):
        return {}
    try:
        ranked = _meaning.significance(name)
    except Exception:
        return {}
    idx: dict = {}
    for item in ranked or []:
        if not isinstance(item, dict):
            continue
        subj = str(item.get("subject", "")).lower()
        # index by the whole subject AND by each token, so "launch podcast march" can be
        # matched from the loop intent and "cabin" from a single-word entity.
        score = float(item.get("score", 0.0) or 0.0)
        for tok in set(re.sub(r"[^a-z0-9]+", " ", subj).split()) | {subj}:
            tok = tok.strip()
            if not tok:
                continue
            prev = idx.get(tok)
            if prev is None or score > float(prev.get("score", 0.0) or 0.0):
                idx[tok] = item
    return idx


def _significance_for(text: str, sig_index: dict) -> tuple[float, Optional[dict]]:
    """The best significance score (and the item carrying it) for any token in ``text``.
    (0.0, None) when nothing in the text registers as significant. Pure; never raises."""
    best_score = 0.0
    best_item: Optional[dict] = None
    toks = set(re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split())
    toks.add(str(text or "").lower().strip())
    for tok in toks:
        item = sig_index.get(tok)
        if item is None:
            continue
        s = float(item.get("score", 0.0) or 0.0)
        if s > best_score:
            best_score, best_item = s, item
    return best_score, best_item


def _read_meaning_objects(name: str) -> list:
    """The dimensioned Meaning Objects (read-only) — we want the ``what_declining`` ones.
    [] if meaning isn't importable/usable. Never raises."""
    if not (_HAVE_MEANING and _meaning is not None):
        return []
    try:
        out = _meaning.meaning(name)
        return [o for o in out if isinstance(o, dict)]
    except Exception:
        return []


def _read_suspected_entities(name: str) -> list:
    """The SUSPECTED curiosity gaps about a NAMED entity (a person/place/thing the user
    mentions a lot but whose meaning Vera doesn't yet know). [] if curiosity isn't
    importable/usable. Read-only. Never raises.

    Observed > Assumed: we only take gaps the curiosity engine ALREADY classified as a
    high-mention SUSPECTED relationship gap — we never re-derive "they mention this a lot"
    ourselves; we read curiosity's own judgement.
    """
    if not (_HAVE_CURIOSITY and _curiosity is not None):
        return []
    try:
        gaps = _curiosity.detect_gaps(name)
    except Exception:
        return []
    out = []
    floor = _suspect_floor()
    suspected = getattr(_curiosity, "SUSPECTED", "suspected")
    self_tok = getattr(_curiosity, "SELF", "you")
    for g in gaps or []:
        if not isinstance(g, dict):
            continue
        if g.get("kind") != suspected:
            continue
        ent = str(g.get("entity") or "").strip()
        if not ent or ent.lower() == str(self_tok).lower():
            continue  # a self-gap (a missing trait about the user) is curiosity's, not an offer
        ev = g.get("evidence") or {}
        mentions = int(ev.get("mentions", 0) or 0)
        if mentions < floor:
            continue
        out.append({"entity": ent, "mentions": mentions, "gap": g,
                    "priority": float(g.get("priority", 0.0) or 0.0)})
    return out


def _trajectory_decline_index(name: str) -> dict:
    """OPTIONAL, defensive — a ``{topic_token: momentum}`` view of the teammate's trajectory
    engine, used ONLY to *sharpen* a declining-thread offer (never to create one). {} if
    trajectory isn't importable/usable or doesn't expose a recognisable shape. This must never
    raise and must never be required: opportunities are complete without it.

    We probe a couple of plausible entry points (``dimensions`` / ``trajectory`` / a generic
    callable) and read any item that looks like ``{subject/name/dimension, direction/momentum/
    slope}`` where the direction reads as falling. Anything we don't recognise is ignored.
    """
    if not (_HAVE_TRAJECTORY and _trajectory is not None):
        return {}
    idx: dict = {}
    try:
        items: list = []
        for entry in ("dimensions", "trajectory", "momentum", "directions"):
            fn = getattr(_trajectory, entry, None)
            if callable(fn):
                try:
                    res = fn(name)
                except Exception:
                    continue
                if isinstance(res, list):
                    items = res
                    break
                if isinstance(res, dict):
                    items = [dict(v, subject=k) if isinstance(v, dict) else {"subject": k, "value": v}
                             for k, v in res.items()]
                    break
        for it in items:
            if not isinstance(it, dict):
                continue
            subj = str(it.get("subject") or it.get("name") or it.get("dimension") or "").lower()
            if not subj:
                continue
            # read any of several plausible "is it falling" fields, permissively.
            falling = False
            direction = str(it.get("direction") or it.get("trend") or "").lower()
            if direction in ("declining", "falling", "down", "waning", "fading"):
                falling = True
            for num_key in ("momentum", "slope", "delta", "trend_score"):
                v = it.get(num_key)
                try:
                    if v is not None and float(v) < 0:
                        falling = True
                except (TypeError, ValueError):
                    pass
            if falling:
                for tok in set(re.sub(r"[^a-z0-9]+", " ", subj).split()) | {subj}:
                    tok = tok.strip()
                    if tok:
                        idx[tok] = it
    except Exception:
        return {}
    return idx


# ===========================================================================
# CONFIDENCE — every opportunity is confidence-scored. The score scales with the
# strength of the OBSERVED evidence (how stalled, how significant, how often
# mentioned), never beyond it (LAW 003). Capped under 1.0 — we are offering, not
# diagnosing.
# ===========================================================================

def _conf_stalled(loop: dict, sig_score: float) -> float:
    """Confidence for a STALLED_PROJECT offer: how silent the loop is × how much it matters.
    Rises with corroboration and significance; never 1.0."""
    silent = _days_since(loop.get("last_seen")) or 0.0
    stall_days = float(getattr(_loops, "STALL_DAYS", 14.0)) if _loops is not None else 14.0
    silence = min(1.0, max(0.0, (silent - stall_days) / 120.0))      # saturates ~4 months
    support = min(1.0, 0.2 * float(loop.get("support", 1)))
    matters = min(1.0, sig_score / 4.0)                              # significance, capped
    base = 0.35 + 0.30 * silence + 0.15 * support + 0.20 * matters
    return round(min(0.9, base), 3)


def _conf_entity(mentions: int, sig_score: float) -> float:
    """Confidence for an UNEXPLAINED_ENTITY offer: how often it comes up × how much it
    matters. The more they mention it (and the more it connects), the surer the offer."""
    freq = min(1.0, mentions / 12.0)                                # saturates ~12 mentions
    matters = min(1.0, sig_score / 4.0)
    base = 0.35 + 0.40 * freq + 0.25 * matters
    return round(min(0.9, base), 3)


def _conf_declining(obj: dict, *, trajectory_confirms: bool) -> float:
    """Confidence for a DECLINING_THREAD offer: the Meaning Engine's own confidence in the
    decline, gently boosted if the (optional) trajectory engine independently agrees."""
    base = float(obj.get("confidence", 0.3) or 0.3)
    if trajectory_confirms:
        base = min(0.9, base + 0.1)
    return round(min(0.9, max(0.05, base)), 3)


# ===========================================================================
# THE OFFER LANGUAGE — warm, optional, easy-to-decline. Each is a complete
# in-character line: NO scaffold tag, NO "according to my memory", NO disclaimer,
# NO diagnosis, and an explicit open door ("no rush", "only if", "want me to…?").
# {thing} is the observed subject; {ago} a soft time phrase. This is the #1 product
# rule made into text: an offer, never a demand.
# ===========================================================================
_OFFER_STALLED = (
    "You've mentioned wanting to {thing} for a while now — want me to help you sketch out a "
    "little milestone plan for it? No pressure at all if the timing's not right.",
    "That thing you'd talked about — {thing} — it's been quiet for a bit. If it'd help, I'd be "
    "happy to help you break it into a few first steps. Totally up to you.",
    "I remember {thing} mattered to you. Want me to help you map out a path toward it sometime? "
    "Only if you're in the mood for it.",
)
_OFFER_ENTITY = (
    "You bring up {thing} a lot — want me to remember why it matters to you, so I can hold onto "
    "it properly? No worries if you'd rather not get into it.",
    "{thing} comes up pretty often. If you'd like, you could tell me a little about what it means "
    "to you and I'll keep it close. Only if you feel like sharing.",
    "I notice {thing} is part of your world. Want to tell me the story there sometime? I'd love to "
    "understand it — but no rush.",
)
_OFFER_DECLINING = (
    "I've noticed {thing} hasn't come up as much lately. If you've been missing it, want to make a "
    "little room for it again? And if it's just run its course, that's completely okay too.",
    "{thing} used to come up more — no judgment either way, but if you'd like, I'm happy to help "
    "you find your way back to it. Only if it's something you still want.",
    "It's been a bit since {thing} was in the picture. If it still matters to you, I'd be glad to "
    "help you carve out some space for it. Entirely your call.",
)

_OFFER_TEMPLATES = {
    STALLED_PROJECT: _OFFER_STALLED,
    UNEXPLAINED_ENTITY: _OFFER_ENTITY,
    DECLINING_THREAD: _OFFER_DECLINING,
}


def _clean_phrase(s: Any) -> str:
    """A readable surface phrase for the offer's subject. Trims whitespace/punctuation;
    never empties to junk."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).strip()).strip(" .,!?;:\"'")


def _offer_text(kind: str, thing: str, *, key: str, ago: str = "") -> str:
    """Render ONE warm, optional offer for a kind+subject. Deterministic per opportunity key
    (so the SAME opportunity reads the same way turn to turn), no scaffold tag, no disclaimer,
    no diagnosis, never breaks character. Falls back gracefully if a kind is unknown."""
    thing = _clean_phrase(thing) or "that"
    templates = _OFFER_TEMPLATES.get(kind)
    if not templates:
        return f"Want me to help with {thing}? Only if it'd be useful — no pressure."
    h = hashlib.sha256(f"offer::{key}".encode("utf-8")).hexdigest()
    tmpl = templates[int(h[:4], 16) % len(templates)]
    return tmpl.format(thing=thing, ago=ago)


# ===========================================================================
# THE OPPORTUNITY OBJECTS — the read path. Each is grounded, evidence-carrying,
# confidence-scored, and de-duplicated by a stable key. Observed > Assumed: nothing
# here is a generic tip — every object traces to a loop / gap / meaning object.
# ===========================================================================

def _opp_key(kind: str, subject: str) -> str:
    """The STABLE identity of an opportunity across time, so the same situation seen again is
    the same opportunity (not a duplicate) and the ledger can carry its whole history under one
    key. Normalised so a re-statement can't fork it."""
    subj = re.sub(r"[^a-z0-9]+", " ", str(subject or "").lower()).strip()
    return f"{kind}::{subj}"


def _stalled_project_opps(name: str, loops_list: list, sig_index: dict) -> list:
    """STALLED_PROJECT — a Dream-Engine ``stalled`` loop that the Meaning Engine reads as
    significant. The loop is the OFFER's spine (it's a *stated* commitment, never inferred);
    significance is the grounding that makes it worth offering help on now."""
    out = []
    archived = getattr(_loops, "ARCHIVED_STATUSES", frozenset()) if _loops is not None else frozenset()
    stalled = getattr(_loops, "STALLED", "stalled") if _loops is not None else "stalled"
    for L in loops_list:
        if L.get("status") != stalled:
            continue
        if L.get("status") in archived or L.get("archived"):
            continue  # never offer on a resolved loop
        intent = _clean_phrase(L.get("intent"))
        if not intent:
            continue
        sig_score, sig_item = _significance_for(intent, sig_index)
        # GROUNDING: an offer to help with a project only fires when that project actually
        # registers as significant (or it carries its own stated target, which is itself a
        # signal the user cared enough to put a date on it). A bare, never-significant,
        # target-less stalled wish does NOT trigger a proactive offer — the Dream Engine's
        # own gentle resurface already covers "still on for that?"; we reserve the heavier
        # "want me to help PLAN it?" for something that matters.
        if sig_score < _MIN_SIGNIFICANCE and not L.get("has_target"):
            continue
        key = _opp_key(STALLED_PROJECT, intent)
        conf = _conf_stalled(L, sig_score)
        out.append({
            "kind": STALLED_PROJECT,
            "subject": intent,
            "trigger": (f"a stated commitment that has gone quiet (status: stalled) and reads "
                        f"as significant in your life"),
            "offer": _offer_text(STALLED_PROJECT, intent, key=key),
            "confidence": conf,
            "key": key,
            "evidence": {
                "source": "loops+meaning",
                "loop_status": L.get("status"),
                "loop_key": L.get("key"),
                "last_seen": L.get("last_seen"),
                "support": int(L.get("support", 1)),
                "has_target": bool(L.get("has_target")),
                "significance": round(sig_score, 4),
                "significance_subject": (sig_item or {}).get("subject"),
            },
        })
    return out


def _unexplained_entity_opps(name: str, suspected: list, sig_index: dict) -> list:
    """UNEXPLAINED_ENTITY — a person/place/thing the user mentions a lot (a high-mention
    SUSPECTED curiosity gap) whose meaning Vera doesn't yet know. The offer is to UNDERSTAND
    it ("want me to remember why it matters?") — grounded in the mention count + significance,
    never invented."""
    out = []
    for s in suspected:
        ent = _clean_phrase(s.get("entity"))
        if not ent:
            continue
        mentions = int(s.get("mentions", 0))
        sig_score, sig_item = _significance_for(ent, sig_index)
        # the entity must also register as significant — a name mentioned in passing a few
        # times but with no weight in the graph is curiosity's plain "who's X?" question, not
        # a heavier "want me to remember why X matters?" offer.
        if sig_score < _MIN_SIGNIFICANCE:
            continue
        key = _opp_key(UNEXPLAINED_ENTITY, ent)
        conf = _conf_entity(mentions, sig_score)
        out.append({
            "kind": UNEXPLAINED_ENTITY,
            "subject": ent,
            "trigger": (f"something you bring up often ({mentions} mentions) that I don't yet "
                        f"understand the meaning of"),
            "offer": _offer_text(UNEXPLAINED_ENTITY, ent, key=key),
            "confidence": conf,
            "key": key,
            "evidence": {
                "source": "curiosity+meaning",
                "mentions": mentions,
                "significance": round(sig_score, 4),
                "gap_priority": round(float(s.get("priority", 0.0)), 3),
            },
        })
    return out


def _declining_thread_opps(name: str, meaning_objects: list, traj_decline: dict) -> list:
    """DECLINING_THREAD — a topic the Meaning Engine reads as declining (real prior weight,
    recent activity fallen off). The offer is a gentle, fully-optional "want to make room for
    it again?" — never "you gave up on X". Sharpened (only) if the optional trajectory engine
    independently agrees it's falling."""
    out = []
    declining_dim = getattr(_meaning, "WHAT_DECLINING", "what_declining") if _meaning is not None else "what_declining"
    for obj in meaning_objects:
        if obj.get("dimension") != declining_dim:
            continue
        subj = _clean_phrase(obj.get("subject"))
        if not subj:
            continue
        toks = set(re.sub(r"[^a-z0-9]+", " ", subj.lower()).split()) | {subj.lower()}
        traj_confirms = any(t in traj_decline for t in toks)
        key = _opp_key(DECLINING_THREAD, subj)
        conf = _conf_declining(obj, trajectory_confirms=traj_confirms)
        ev = obj.get("evidence") or {}
        out.append({
            "kind": DECLINING_THREAD,
            "subject": subj,
            "trigger": ("a topic with real prior weight that has come up less lately"
                        + (" (the trajectory read agrees it's waning)" if traj_confirms else "")),
            "offer": _offer_text(DECLINING_THREAD, subj, key=key),
            "confidence": conf,
            "key": key,
            "evidence": {
                "source": "meaning" + ("+trajectory" if traj_confirms else ""),
                "recent_mentions": ev.get("recent_mentions"),
                "older_mentions": ev.get("older_mentions"),
                "meaning_statement": obj.get("statement"),
                "trajectory_confirms": traj_confirms,
            },
        })
    return out


def opportunities(name: str, *, now: Optional[float] = None) -> list:
    """ENTRY POINT — the grounded, optional OFFERS Vera could make to ``name`` right now.

    Reads the live engines (loops + meaning + curiosity, and trajectory if present), NEVER
    infers a generic tip, and returns one Opportunity Object per distinct, evidence-backed
    opening. Each:

        {
          "kind":       stalled_project | unexplained_entity | declining_thread,
          "subject":    the observed thing the offer is about (intent / entity / topic),
          "trigger":    the observed pattern/evidence that opened this (plain language),
          "offer":      the warm, optional proposal text ("want me to…?") — a STRING,
          "confidence": how strong the observed evidence is (scaled, never beyond it),
          "key":        stable identity across time (kind::subject, normalised),
          "evidence":   the grounding (source engine + the counts/status that justify it),
        }

    De-duplicated by key (highest confidence kept). Returned best-first (highest confidence).
    READ-ONLY over every store — generating opportunities writes NOTHING and, critically,
    EXECUTES NOTHING: an opportunity is an offer, not an action. Never raises — a missing
    engine is simply fewer (or no) opportunities."""
    sig_index = _significance_index(name)
    loops_list = _read_loops(name, now=now)
    suspected = _read_suspected_entities(name)
    meaning_objects = _read_meaning_objects(name)
    traj_decline = _trajectory_decline_index(name)

    found: list = []
    # each builder is independently wrapped: one engine's hiccup can't sink the others.
    for builder, args in (
        (_stalled_project_opps, (name, loops_list, sig_index)),
        (_unexplained_entity_opps, (name, suspected, sig_index)),
        (_declining_thread_opps, (name, meaning_objects, traj_decline)),
    ):
        try:
            found.extend(builder(*args))
        except Exception:
            continue

    # de-dup by key (keep the most-confident read of the same opening)
    best: dict = {}
    for o in found:
        k = o.get("key")
        if not isinstance(k, str) or not k:
            continue
        prev = best.get(k)
        if prev is None or float(o.get("confidence", 0.0)) > float(prev.get("confidence", 0.0)):
            best[k] = o
    out = list(best.values())
    out.sort(key=lambda o: (-float(o.get("confidence", 0.0)), o.get("subject", "")))
    return out


# ===========================================================================
# THE PACING BUDGET — read DEFENSIVELY from caps, exactly like curiosity / loops. The
# budget governs HOW OFTEN ``next_opportunity`` offers (frequency only, never content), so
# Vera proposes sparingly. minimal=rarely, balanced=sometimes, deep=readily. This is the
# #1-product-rule made operational: a gentle offer, never a barrage.
# ===========================================================================
_BUDGETS = ("minimal", "balanced", "deep")
_DEFAULT_BUDGET = "balanced"

_BUDGET_RATE = {
    "minimal": 0.20,    # rarely — only the strongest opening, sparingly
    "balanced": 0.55,   # sometimes
    "deep": 1.00,       # readily — whenever a worthy un-offered opportunity exists
}

# The minimum number of days before a DECLINED opportunity may be reconsidered — and even
# then only if its evidence has grown clearly stronger (see _reconsiderable). A floor, so a
# "no" is respected, not nagged around. (Days.)
RECONSIDER_COOLDOWN_DAYS = 30.0

# How much stronger the evidence must be, vs. at decline time, before a declined opportunity
# is offered again. A real change of circumstances, not a re-roll. (Confidence delta.)
_RECONSIDER_CONF_DELTA = 0.15


def read_budget(name: str) -> str:
    """The user's offer budget for ``name`` — read defensively from ``caps`` (an
    ``opportunity``/``opportunities`` helper, then those keys, then a generic ``curiosity``
    key so offering inherits the same restraint dial if no opportunity-specific one exists).
    Anything unrecognised / absent / erroring -> "balanced". Always one of ``_BUDGETS``."""
    try:
        from . import caps as _caps  # local import: defensive, no hard dep
        for helper in ("opportunity", "opportunities", "curiosity"):
            fn = getattr(_caps, helper, None)
            if callable(fn):
                v = fn(name)
                if isinstance(v, str) and v.strip().lower() in _BUDGETS:
                    return v.strip().lower()
        blob = _caps.load(name) if hasattr(_caps, "load") else {}
        if isinstance(blob, dict):
            for key in ("opportunity", "opportunities", "curiosity"):
                v = blob.get(key)
                if isinstance(v, str) and v.strip().lower() in _BUDGETS:
                    return v.strip().lower()
    except Exception:
        pass
    return _DEFAULT_BUDGET


def _budget_allows(name: str, opp: dict, budget: str) -> bool:
    """The FREQUENCY decision for one opportunity under a budget. Deterministic (hash of name +
    opportunity key) so the SAME opportunity yields the SAME decision on re-eval within a budget
    — an offer doesn't flicker turn to turn. A higher-confidence opening clears the bar a little
    more readily. Content is NEVER touched here; purely how-often."""
    rate = _BUDGET_RATE.get(budget, _BUDGET_RATE[_DEFAULT_BUDGET])
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    h = hashlib.sha256(f"{name}::{opp.get('key','')}".encode("utf-8")).hexdigest()
    draw = int(h[:8], 16) / 0xFFFFFFFF
    boost = min(0.25, 0.30 * float(opp.get("confidence", 0.0)))
    return draw < min(1.0, rate + boost)


# ===========================================================================
# NEXT — at most ONE un-offered opportunity, paced. Warm, optional, never the same
# offer twice (unless declined-then-clearly-relevant-again). This is the proactive
# entry point a turn calls.
# ===========================================================================

def next_opportunity(name: str, *, budget: Optional[str] = None,
                     now: Optional[float] = None) -> Optional[str]:
    """ENTRY POINT — at most ONE warm, optional OFFER, or ``None``.

    Picks the highest-confidence opportunity that is (a) not already offered (the append-only
    ledger remembers), unless it was DECLINED and has since become clearly relevant again, and
    (b) cleared by the pacing budget this turn (so Vera offers sparingly, never barrages).
    Returns the offer STRING — no scaffold tag, no disclaimer, no diagnosis, never a character
    break — or ``None`` when nothing is due / the budget says stay quiet.

    CRITICAL — this RETURNS A PROPOSAL; it EXECUTES NOTHING. It does not act on the offer, does
    not call ``route`` or any host executor, does not write a reminder/calendar/note. If the
    user says "yes", the acting flows through ``route.py``'s existing draft→confirm→execute gate
    on their explicit next turn — not here.

    DOES NOT record the offer — the caller does that via ``mark_offered`` ONLY if the line is
    actually surfaced to the user (so a prepared-but-unshown offer doesn't burn the slot),
    mirroring ``loops.resurface``/``curiosity.next_question``. Never raises; returns ``None`` on
    any failure or when it should stay quiet."""
    try:
        opps = opportunities(name, now=now)
    except Exception:
        return None
    budget = (budget or read_budget(name)).strip().lower()
    if budget not in _BUDGETS:
        budget = _DEFAULT_BUDGET

    offered = _offered_index(name)
    declined = _declined_index(name)
    ref = now if now is not None else datetime.now(timezone.utc).timestamp()

    for opp in opps:
        key = opp.get("key")
        if not isinstance(key, str) or not key:
            continue
        # already OFFERED and not declined -> never re-offer the same thing (gentle, not naggy)
        if key in offered and key not in declined:
            continue
        # DECLINED -> respect the "no": only reconsider past the cooldown AND if the evidence
        # is now clearly stronger than it was when declined (a real change, not a re-roll).
        if key in declined:
            if not _reconsiderable(opp, declined[key], now=ref):
                continue
        # pacing budget: stay quiet unless this opportunity is due under the budget
        if not _budget_allows(name, opp, budget):
            continue
        line = opp.get("offer")
        if not isinstance(line, str) or not line.strip():
            continue
        # stash the chosen opportunity so a caller that then calls mark_offered records the
        # right one without re-deriving (mirrors loops.resurface / curiosity.next_question).
        opp["_offered_line"] = line
        next_opportunity._last_choice = {  # type: ignore[attr-defined]
            "name": name, "key": key, "kind": opp.get("kind"),
            "subject": opp.get("subject"), "line": line,
            "confidence": float(opp.get("confidence", 0.0)),
        }
        return line
    return None


def last_opportunity_choice() -> Optional[dict]:
    """The opportunity ``next_opportunity`` last chose (``{name, key, kind, subject, line,
    confidence}``), so a caller can mark exactly that one offered. None if ``next_opportunity``
    hasn't returned a line yet this process. Mirrors ``loops.last_resurface_choice``."""
    return getattr(next_opportunity, "_last_choice", None)


def _reconsiderable(opp: dict, decline_rec: dict, *, now: float) -> bool:
    """Whether a previously-DECLINED opportunity may be offered again: only past the cooldown
    AND only if its evidence is now clearly stronger than at decline time (a genuine change of
    circumstances, never a re-roll of the same "no"). Conservative by design — respecting a
    decline is the #1 product rule; we err toward staying quiet.

    The baseline is the confidence recorded WITH the decline. If none was recorded (e.g. the
    caller declined by bare key), we anchor the baseline at the opportunity's CURRENT
    confidence — so the delta is zero and the decline is fully respected — rather than at 0.0,
    which would make any future offer reconsiderable and nag around a "no". A re-offer then
    requires the evidence to have grown *materially stronger than it is right now*, which by
    construction it has not, so an unrecorded-baseline decline stays respected until the
    situation genuinely escalates and a fresh decline (with a baseline) is recorded."""
    since = _days_since(decline_rec.get("at"), now=now)
    if since is None or since < RECONSIDER_COOLDOWN_DAYS:
        return False
    now_conf = float(opp.get("confidence", 0.0) or 0.0)
    raw = decline_rec.get("confidence", None)
    if raw is None:
        was = now_conf            # no baseline -> anchor at current, so delta is 0 (respected)
    else:
        try:
            was = float(raw or 0.0)
        except (TypeError, ValueError):
            was = now_conf
    return (now_conf - was) >= _RECONSIDER_CONF_DELTA


# ===========================================================================
# RENDER — a warm, optional, easy-to-decline line for a single opportunity. The
# entry the mouth narrates. No scaffold tag, no pressure, no diagnosis. This is just
# the offer text (already warm + optional by construction); kept as a named entry so
# callers have a stable seam and so we can enforce "render never leaks a tag".
# ===========================================================================

def render_opportunity(opp: Any) -> str:
    """Render ONE opportunity as a warm, optional, easy-to-decline line — the thing the mouth
    says. Accepts an Opportunity Object (dict) or a bare offer string. Strips any stray scaffold
    bracket as a belt-and-suspenders guard so nothing the model would read aloud leaks. Never
    raises; returns '' for empty input."""
    if isinstance(opp, str):
        text = opp
    elif isinstance(opp, dict):
        text = opp.get("offer") or opp.get("_offered_line") or ""
        if not text and opp.get("kind") and opp.get("subject"):
            text = _offer_text(opp["kind"], opp["subject"],
                               key=opp.get("key") or _opp_key(opp["kind"], opp["subject"]))
    else:
        text = ""
    text = str(text or "").strip()
    # belt-and-suspenders: an offer must never carry a scaffold tag.
    if "[" in text or "]" in text:
        text = text.replace("[", "").replace("]", "").strip()
    return text


# ===========================================================================
# THE OFFER LEDGER — append-only .anima/{name}.offers.jsonl. The ONLY thing this
# module writes, and it is a record of OFFERS (and the user's response), never an
# action. Every event (an offer surfaced, a decline, an accept) is a new line; nothing
# is ever rewritten or removed. (LAW 001 discipline, mirroring loops/curiosity.)
# ===========================================================================

def ledger_path(name: str) -> Path:
    """The append-only offer ledger for ``name``. One JSON object per line, never rewritten —
    exactly like the loops (LAW 001) and curiosity (LAW 002) ledgers. This is the ONLY file
    this module writes, and it records OFFERS, never actions."""
    return STORE / f"{name}.offers.jsonl"


def _append(name: str, rec: dict) -> Optional[dict]:
    """Append one event to the offer ledger, durably (fsync). Append-only, never truncate or
    overwrite. Returns the written record, or None on a write failure (a ledger write is
    best-effort and must never crash a turn — but a success is durable)."""
    if not isinstance(rec, dict):
        return None
    try:
        p = ledger_path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        return None
    return rec


def read_ledger(name: str) -> list:
    """Every event in the offer ledger, oldest->newest (read-only). Tolerates a missing or
    partially-corrupt ledger: an unparseable line is kept visible as ``{"_unparsed": ...}``
    rather than dropped (Unknown > Lost), never silently skipped into oblivion."""
    p = ledger_path(name)
    if not p.exists():
        return []
    out: list = []
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append({"_unparsed": line})  # a corrupt line is information; keep it
    return out


def _offered_index(name: str) -> dict:
    """``{key: last_offered_iso}`` from the ledger's 'offered' events — what NOT to re-offer.
    Read-only; never raises."""
    idx: dict = {}
    for rec in read_ledger(name):
        if isinstance(rec, dict) and rec.get("event") == "offered":
            k, at = rec.get("key"), rec.get("at")
            if isinstance(k, str) and k:
                idx[k] = at
    return idx


def _declined_index(name: str) -> dict:
    """``{key: latest_decline_record}`` from the ledger's 'declined' events — a "no" we must
    respect (and may only reconsider past the cooldown with clearly stronger evidence). If an
    opportunity was offered AGAIN and re-declined, the latest decline wins. Read-only; never
    raises."""
    idx: dict = {}
    for rec in read_ledger(name):
        if isinstance(rec, dict) and rec.get("event") == "declined":
            k = rec.get("key")
            if isinstance(k, str) and k:
                idx[k] = rec
    return idx


def mark_offered(name: str, opp_or_key: Any, *, line: str = "",
                 confidence: Optional[float] = None) -> Optional[dict]:
    """ENTRY POINT — record that an opportunity's offer was actually surfaced to the user,
    append-only. After this, ``next_opportunity`` won't offer the SAME thing again (unless it's
    later declined-then-clearly-relevant-again). Accepts an Opportunity Object or a bare key.
    Returns the written record, or None on a bad input / write failure (best-effort; never
    raises).

    NOTE this records an OFFER, not an action: calling it does not perform anything the offer
    proposed. It only stamps "I made this offer", so the engine paces itself."""
    key = opp_or_key.get("key") if isinstance(opp_or_key, dict) else opp_or_key
    if not isinstance(key, str) or not key:
        return None
    kind = opp_or_key.get("kind") if isinstance(opp_or_key, dict) else None
    subject = opp_or_key.get("subject") if isinstance(opp_or_key, dict) else None
    if confidence is None and isinstance(opp_or_key, dict):
        confidence = opp_or_key.get("confidence")
    rec = {
        "law": _LAW_ID,
        "event": "offered",
        "at": _now(),
        "key": key,
        "kind": kind,
        "subject": subject,
        "line": (line or (opp_or_key.get("_offered_line", "") if isinstance(opp_or_key, dict) else ""))[:500],
    }
    if confidence is not None:
        try:
            rec["confidence"] = round(float(confidence), 3)
        except (TypeError, ValueError):
            pass
    return _append(name, rec)


def mark_response(name: str, opp_or_key: Any, response: str, *,
                  note: str = "", confidence: Optional[float] = None) -> Optional[dict]:
    """ENTRY POINT — record the user's RESPONSE to an offer (``accepted`` or ``declined``),
    append-only. A ``declined`` is respected: ``next_opportunity`` won't re-offer it unless,
    past the cooldown, its evidence is clearly stronger than at decline time. An ``accepted``
    is recorded for the record (and so the offer isn't re-made) — but recording an accept does
    NOT execute anything here: the user's "yes" flows through ``route.py``'s confirm-gate, not
    this module.

    ``response`` must be 'accepted' or 'declined'. Accepts an Opportunity Object or a bare key.
    Returns the written record, or None on a bad response / input / write failure. Never raises.
    """
    response = (response or "").strip().lower()
    if response not in ("accepted", "declined"):
        return None
    key = opp_or_key.get("key") if isinstance(opp_or_key, dict) else opp_or_key
    if not isinstance(key, str) or not key:
        return None
    kind = opp_or_key.get("kind") if isinstance(opp_or_key, dict) else None
    subject = opp_or_key.get("subject") if isinstance(opp_or_key, dict) else None
    if confidence is None and isinstance(opp_or_key, dict):
        confidence = opp_or_key.get("confidence")
    rec = {
        "law": _LAW_ID,
        "event": response,                 # "accepted" | "declined"
        "at": _now(),
        "key": key,
        "kind": kind,
        "subject": subject,
        "note": (note or "")[:500],
    }
    if confidence is not None:
        try:
            rec["confidence"] = round(float(confidence), 3)
        except (TypeError, ValueError):
            pass
    return _append(name, rec)


def decline(name: str, opp_or_key: Any, *, note: str = "") -> Optional[dict]:
    """ENTRY POINT — a thin, intention-revealing wrapper for "the user said no to this offer".
    Records a ``declined`` response (respected per the reconsider rule). Returns the record or
    None."""
    return mark_response(name, opp_or_key, "declined", note=note)


# ===========================================================================
# RENDER (audit) — the human-readable AUDIT SURFACE: what offers Vera could make, their
# grounding + confidence, and which (if any) is due. The Opportunity-Engine counterpart to
# loops.render / curiosity.render. Read-only; never raises. NB this surfaces OFFERS; it
# performs nothing.
# ===========================================================================

_KIND_GLYPH = {
    STALLED_PROJECT: "◔ stalled project",
    UNEXPLAINED_ENTITY: "◇ unexplained entity",
    DECLINING_THREAD: "◌ declining thread",
}


def render(name: str) -> str:
    """The human-readable audit surface: the grounded offers available, each with its trigger,
    confidence, and evidence, plus the single offer (if any) currently due under the budget.
    Mirrors the sibling engines' render. Read-only; never raises; performs nothing."""
    try:
        opps = opportunities(name)
    except Exception:
        opps = []
    budget = read_budget(name)
    offered = _offered_index(name)
    declined = _declined_index(name)

    out = [f"Opportunities Vera could OFFER {name} ({len(opps)} grounded; offer budget: "
           f"{budget}). These are OFFERS, not actions — nothing is done without your yes:"]
    if not opps:
        out.append("  (none yet — an offer appears only when the evidence is there; "
                   "never a generic tip)")
    for o in opps:
        glyph = _KIND_GLYPH.get(o.get("kind"), o.get("kind", "?"))
        state = ""
        if o.get("key") in declined:
            state = " · previously declined (respected)"
        elif o.get("key") in offered:
            state = " · already offered"
        out.append(
            f"  • [{glyph} · conf {o.get('confidence', 0.0):.2f}{state}] about: {o.get('subject','?')}\n"
            f"      trigger: {o.get('trigger','?')}\n"
            f"      offer: \"{o.get('offer','')}\"")

    try:
        due = next_opportunity(name)
    except Exception:
        due = None
    out.append("")
    if due:
        out.append(f"  Offer due (optional, easy to decline): \"{due}\"")
    else:
        out.append("  No offer due right now (nothing un-offered-and-grounded, or the budget "
                   "says rest).")
    return "\n".join(out)


__all__ = [
    # kinds
    "STALLED_PROJECT", "UNEXPLAINED_ENTITY", "DECLINING_THREAD", "KINDS",
    # read path (generate / pace / render) — NONE of these execute anything
    "opportunities", "next_opportunity", "render_opportunity", "render",
    "read_budget", "last_opportunity_choice",
    # ledger (the only writers, all append-only; they record OFFERS, not actions)
    "ledger_path", "read_ledger", "mark_offered", "mark_response", "decline",
    # law
    "law",
]


# ===========================================================================
# SELF-TEST — run directly: `python3 -m anima.opportunity`. No model, no network; writes
# only to a throwaway store it cleans up (NEVER the real Vera.*). Mirrors the sibling organs'
# ok(label, cond) harness and the curiosity/loops STORE-redirect gotcha (redirect the
# currently-executing module AND, under -m, the package copy too, so no write leaks to real
# .anima). It builds SYNTHETIC creatures via the real world_state API where it can, and
# asserts the load-bearing invariants — above all OFFER-NOT-ACTION.
# ===========================================================================

def _selftest() -> int:
    import glob
    import sys
    import tempfile

    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # Redirect EVERY store this module + its read-engines touch into a throwaway temp dir,
    # exactly like scripts/test_continuity.py and loops/curiosity _selftest. Under
    # `python3 -m anima.opportunity` THIS function runs in the __main__ module, whose bare
    # STORE is a SEPARATE binding from anima.opportunity.STORE — so redirect the currently-
    # executing module AND the package copy AND every engine we read.
    _cur = sys.modules[__name__]
    _mods = [_cur]
    try:
        import anima.opportunity as _pkg  # the package copy, if distinct
        if _pkg is not _cur:
            _mods.append(_pkg)
    except Exception:
        pass
    # also redirect the engines we read so a stray read/write can't touch real .anima
    _engine_mods = []
    for modname in ("world_state", "loops", "meaning", "curiosity", "caps"):
        try:
            m = __import__("anima." + modname, fromlist=[modname])
            if hasattr(m, "STORE"):
                _engine_mods.append(m)
        except Exception:
            pass

    td = tempfile.mkdtemp(prefix="anima-opp-self-")
    tp = Path(td)
    saved = [(m, getattr(m, "STORE", None)) for m in (_mods + _engine_mods)]
    for _m in (_mods + _engine_mods):
        _m.STORE = tp

    from datetime import datetime as _dt, timezone as _tz
    NOW_JUN = _dt(2026, 6, 1, tzinfo=_tz.utc).timestamp()
    JAN = "2026-01-05T00:00:00Z"

    try:
        from anima import world_state as ws, loops as lp

        # --- law resolves to LAW 003 (constitution constant or fallback literal) ---
        ok("law: resolves to UNDERSTANDING BEATS REMEMBERING",
           "UNDERSTANDING BEATS REMEMBERING" in law())

        # ============================================================
        # 1) A STALLED, SIGNIFICANT project surfaces a milestone-plan offer.
        # ============================================================
        name = "opp_self_" + secrets.token_hex(3)
        # State a goal the real way, then backdate it so it reads stalled-as-of-June.
        ws.capture_relations(name, "I want to launch the podcast in March")
        # make the podcast SIGNIFICANT: mention it / connect it a few more times.
        W = ws.World.load(name)
        for _ in range(5):
            W.add("you", "working_on", "podcast", kind="goal", source="chat")
        W.add("podcast", "needs", "editing", kind="fact", source="chat")
        W.save(name)
        # backdate every edge to January so the loop is long-silent.
        p = ws.World.path(name)
        d = json.loads(p.read_text(encoding="utf-8"))
        for r in d.get("relations", []):
            r["created"] = JAN
            r["updated"] = JAN
        p.write_text(json.dumps(d), encoding="utf-8")

        opps = opportunities(name, now=NOW_JUN)
        kinds = [o["kind"] for o in opps]
        stalled = [o for o in opps if o["kind"] == STALLED_PROJECT]
        ok("stalled+significant project surfaces a STALLED_PROJECT opportunity",
           len(stalled) >= 1)
        if stalled:
            o = stalled[0]
            low = o["offer"].lower()
            ok("the offer is about the actual project (grounded, not generic)",
               "podcast" in low)
            ok("the offer is an OFFER ('want me to…?' / optional), never a command",
               any(p in low for p in ("want me to", "if it'd help", "if you", "happy to",
                                      "only if", "no pressure")))
            ok("the offer proposes a MILESTONE/plan kind of help",
               any(p in low for p in ("milestone", "plan", "first steps", "step", "map",
                                      "path", "break it")))
            ok("the opportunity carries kind/trigger/offer/confidence/evidence",
               all(k in o for k in ("kind", "trigger", "offer", "confidence", "evidence")))
            ok("confidence is in (0,1) and evidence cites the source engines",
               0.0 < float(o["confidence"]) < 1.0
               and "loops" in str(o["evidence"].get("source", "")))

        # ============================================================
        # 2) A SPARSE / quiet life surfaces NOTHING (never-fabricate; no generic tips).
        # ============================================================
        quiet = "opp_quiet_" + secrets.token_hex(3)
        # a single bland preference, nothing stated, nothing significant, nobody mentioned.
        ws.capture_relations(quiet, "I had toast this morning")
        sparse = opportunities(quiet, now=NOW_JUN)
        ok("a sparse/quiet life yields NO opportunities (never fabricate a generic tip)",
           sparse == [])
        ok("next_opportunity on a sparse life is None (stays silent)",
           next_opportunity(quiet, budget="deep", now=NOW_JUN) is None)
        # and a totally empty creature too
        ok("an empty creature yields NO opportunities + None",
           opportunities("opp_nobody_" + secrets.token_hex(3), now=NOW_JUN) == []
           and next_opportunity("opp_nobody_" + secrets.token_hex(3)) is None)

        # ============================================================
        # 3) OFFER-NOT-ACTION (load-bearing): generating + pacing executes NOTHING.
        #    We arm tripwires on every executor an action would touch and prove none fire.
        # ============================================================
        tripped = {"hit": None}

        def _tripwire(label):
            def boom(*a, **k):
                tripped["hit"] = label
                raise AssertionError(f"OFFER-NOT-ACTION VIOLATED: {label} was executed by the "
                                     f"opportunity engine")
            return boom

        # patch host_access executors, route's execute/prepare, and the host-write parser —
        # an opportunity must touch NONE of them.
        patched = []
        try:
            from anima import host_access as _ha
            for fn in ("create_reminder", "create_event", "create_note", "append_to_note",
                       "complete_reminder", "send_imessage"):
                if hasattr(_ha, fn):
                    patched.append((_ha, fn, getattr(_ha, fn)))
                    setattr(_ha, fn, _tripwire(f"host_access.{fn}"))
        except Exception:
            pass
        try:
            from anima import route as _rt
            for fn in ("route", "_host_execute", "_host_prepare", "_pending_set"):
                if hasattr(_rt, fn):
                    patched.append((_rt, fn, getattr(_rt, fn)))
                    setattr(_rt, fn, _tripwire(f"route.{fn}"))
        except Exception:
            pass
        try:
            # Run the WHOLE proactive path against the armed tripwires.
            _ = opportunities(name, now=NOW_JUN)
            _ = next_opportunity(name, budget="deep", now=NOW_JUN)
            ch = last_opportunity_choice()
            if ch:
                mark_offered(name, ch["key"], line=ch["line"], confidence=ch.get("confidence"))
            _ = render(name)
            ok("OFFER-NOT-ACTION: no host_access/route executor fired during generate+pace+offer",
               tripped["hit"] is None)
        finally:
            for obj, fn, orig in patched:
                setattr(obj, fn, orig)

        # structural proof too: the module holds NO bound executor handle in its namespace.
        # (We legitimately NAME route/host_access in prose + in this self-test, so we check the
        # actual module GLOBALS, not the source text: there must be no `route`/`host_access`
        # module object bound at the top level that real code could call.)
        _ns = vars(sys.modules[__name__])
        _bound_executors = [n for n in ("route", "host_access", "_host_access", "_route")
                            if n in _ns and getattr(_ns[n], "__name__", "").startswith("anima")]
        ok("OFFER-NOT-ACTION: the engine binds NO route/host_access module in its namespace",
           not _bound_executors)
        ok("OFFER-NOT-ACTION: the public API exposes NO execute/send/do/act/run primitive",
           not any(hasattr(sys.modules[__name__], n)
                   for n in ("execute", "send", "do", "act", "run", "perform", "apply")))

        # the offer itself is a plain proposal STRING (not a callable, not a side-effecting obj)
        if stalled:
            ok("OFFER-NOT-ACTION: an opportunity's 'offer' is a proposal STRING (not a callable)",
               isinstance(stalled[0]["offer"], str) and not callable(stalled[0]["offer"]))

        # ============================================================
        # 4) NEVER RE-OFFER: after mark_offered, the same opportunity isn't offered again;
        #    a declined one isn't nagged.
        # ============================================================
        reoffer_name = "opp_reoffer_" + secrets.token_hex(3)
        ws.capture_relations(reoffer_name, "I want to launch the podcast in March")
        W2 = ws.World.load(reoffer_name)
        for _ in range(5):
            W2.add("you", "working_on", "podcast", kind="goal", source="chat")
        W2.save(reoffer_name)
        p2 = ws.World.path(reoffer_name)
        d2 = json.loads(p2.read_text(encoding="utf-8"))
        for r in d2.get("relations", []):
            r["created"] = JAN
            r["updated"] = JAN
        p2.write_text(json.dumps(d2), encoding="utf-8")

        first = next_opportunity(reoffer_name, budget="deep", now=NOW_JUN)
        ok("an un-offered grounded opportunity IS offered (one warm line)",
           isinstance(first, str) and bool(first.strip()))
        ch2 = last_opportunity_choice()
        ok("next_opportunity exposes its chosen opportunity (for mark_offered)",
           ch2 is not None and ch2.get("key"))
        mark_offered(reoffer_name, ch2["key"], line=first, confidence=ch2.get("confidence"))
        second = next_opportunity(reoffer_name, budget="deep", now=NOW_JUN)
        # there's only one grounded opportunity here, and it was offered -> nothing left.
        ok("the SAME opportunity is NOT offered again after mark_offered (gentle, never naggy)",
           second is None or (last_opportunity_choice() or {}).get("key") != ch2["key"])

        # decline -> respected: not re-offered even at deep budget (within cooldown).
        decline(reoffer_name, ch2["key"], note="not now")
        after_decline = next_opportunity(reoffer_name, budget="deep", now=NOW_JUN)
        ok("a DECLINED opportunity is NOT nagged (respected within cooldown)",
           after_decline is None or (last_opportunity_choice() or {}).get("key") != ch2["key"])

        # ledger is append-only: offered + declined both recorded, nothing rewritten.
        events = read_ledger(reoffer_name)
        ok("[append-only] the offer ledger records the offer AND the decline (both on disk)",
           any(e.get("event") == "offered" for e in events)
           and any(e.get("event") == "declined" for e in events))
        ok("[append-only] adding events only GREW the ledger (never rewrote a prior line)",
           len([e for e in events if e.get("event") in ("offered", "declined")]) >= 2)
        ok("the ledger records OFFERS, never an action (no 'executed'/'sent' event kind)",
           not any(e.get("event") in ("executed", "sent", "did", "performed") for e in events))

        # ============================================================
        # 5) #1 RULE: offers are warm + optional, no scaffold tag, no character break, NO diagnosis.
        # ============================================================
        all_offers = [o["offer"] for o in opportunities(name, now=NOW_JUN)]
        ok("there is at least one offer to scrutinise", len(all_offers) >= 1)
        for off in all_offers:
            low = off.lower()
            ok(f"offer is warm + OPTIONAL: \"{off[:42]}...\"",
               any(p in low for p in ("want", "if you", "if it", "only if", "no pressure",
                                      "no rush", "happy to", "up to you", "your call",
                                      "no worries", "okay too", "no judgment")))
            ok("offer carries NO scaffold tag (nothing the model would leak aloud)",
               "[" not in off and "]" not in off)
            ok("offer never breaks character / never disclaims being an AI",
               "according to my memory" not in low and "i'm just an ai" not in low
               and "as an ai" not in low and "language model" not in low)
            ok("offer carries NO diagnosis / clinical language",
               not any(w in low for w in ("disorder", "diagnos", "depress", "anxiety",
                                          "you should probably see", "symptom", "condition",
                                          "mental health", "therapy", "therapist")))
        # render_opportunity strips any stray tag and stays warm.
        if stalled:
            r_line = render_opportunity(stalled[0])
            ok("render_opportunity yields a clean, tag-free warm line",
               isinstance(r_line, str) and r_line and "[" not in r_line and "]" not in r_line)
            ok("render_opportunity accepts a bare string too (stable seam)",
               render_opportunity("Want me to help? Only if useful.") ==
               "Want me to help? Only if useful.")

        # ============================================================
        # 6) PACING: at most one per call; budget controls frequency.
        # ============================================================
        line_once = next_opportunity(name, budget="deep", now=NOW_JUN)
        ok("next_opportunity returns AT MOST ONE offer (a single string, never a batch)",
           line_once is None or (isinstance(line_once, str) and "\n" not in line_once.strip()))

        # minimal stays silent far more than deep across many fresh creatures (frequency, not content).
        def _seed_stalled(nm):
            ws.capture_relations(nm, "I want to launch the podcast in March")
            Wn = ws.World.load(nm)
            for _ in range(5):
                Wn.add("you", "working_on", "podcast", kind="goal", source="chat")
            Wn.save(nm)
            pn = ws.World.path(nm)
            dn = json.loads(pn.read_text(encoding="utf-8"))
            for r in dn.get("relations", []):
                r["created"] = JAN
                r["updated"] = JAN
            pn.write_text(json.dumps(dn), encoding="utf-8")

        silent_min = silent_deep = 0
        N = 30
        for i in range(N):
            nm_min = f"opp_bud_min_{i}_" + secrets.token_hex(2)
            nm_deep = f"opp_bud_deep_{i}_" + secrets.token_hex(2)
            _seed_stalled(nm_min)
            _seed_stalled(nm_deep)
            if next_opportunity(nm_min, budget="minimal", now=NOW_JUN) is None:
                silent_min += 1
            if next_opportunity(nm_deep, budget="deep", now=NOW_JUN) is None:
                silent_deep += 1
        ok(f"budget: minimal stays silent more than deep ({silent_min}/{N} vs {silent_deep}/{N})",
           silent_min > silent_deep)
        ok("budget: deep almost always offers when a grounded opportunity exists",
           silent_deep <= max(2, N // 10))

        # ============================================================
        # 7) ROBUSTNESS: every entry point degrades to safe defaults, never raises.
        # ============================================================
        ok("robust: opportunities on an unknown name -> list, never raises",
           isinstance(opportunities("opp_x_" + secrets.token_hex(3)), list))
        ok("robust: next_opportunity on an unknown name -> None, never raises",
           next_opportunity("opp_x_" + secrets.token_hex(3)) is None)
        ok("robust: render_opportunity(None) -> '' (never raises)",
           render_opportunity(None) == "")
        ok("robust: mark_offered(bad input) -> None (never raises)",
           mark_offered("opp_x", None) is None)
        ok("robust: mark_response(bad response) -> None (never raises)",
           mark_response("opp_x", "k", "maybe") is None)
        ok("robust: render() on an empty creature is a string (never raises)",
           isinstance(render("opp_empty_" + secrets.token_hex(3)), str))

    finally:
        for pat in ("opp_self*", "opp_quiet*", "opp_nobody*", "opp_reoffer*", "opp_bud_*",
                    "opp_x*", "opp_empty*"):
            for fp in glob.glob(str(STORE / pat)):
                try:
                    os.remove(fp)
                except OSError:
                    pass
        for _m, _old in saved:
            if _old is not None:
                _m.STORE = _old

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL OPPORTUNITY SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
