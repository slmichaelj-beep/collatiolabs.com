"""loops — THE DREAM ENGINE: the open loops a person leaves open, tracked FOREVER.

A human carries unfinished things. They say "I want to launch VeraCall in March," they
begin a project, they voice an intention — and then life moves on. Most systems lose
those threads the moment the conversation scrolls away. Vera must not. This is the engine
behind "you wanted to launch VeraCall in March — still on for that?": once a commitment is
STATED, it becomes an OPEN LOOP that is tracked until it resolves, and a resolved loop is
ARCHIVED, never deleted. That permanence is ANIMA LAW 001 made concrete for goals.

This is DISTINCT from its two siblings, by hard design:

  * The Life Review (temporal compression) answers "what is the through-line of this
    relationship over time?" — it summarises the PAST.
  * The Meaning Engine (``meaning`` / LAW 003) answers "what MATTERS right now?" — it ranks
    present significance. (An open loop that is ALSO significant ranks higher here, because
    ``rank_loops`` reads meaning's significance as a soft multiplier — never the source of
    a loop, only its ordering.)
  * The Dream Engine (this module) answers "what did you SAY you'd do, and where did it
    go?" — it tracks STATED COMMITMENTS across time and gently resurfaces stalled ones.

Four jobs, mirroring the curiosity/meaning division of labour:

  1. DETECT — ``detect_loops(name)`` reads the stores (NEVER infers) for explicitly stated
     goals / intentions / commitments that are unfinished: ``world_state`` ``working_toward``
     / ``goal`` edges, and "I want to / I'm going to / I plan to / I've been meaning to"
     intentions, and a project named with a target. Each loop is a dict
     ``{subject, intent, stated_when, last_seen, status, evidence, ...}``. Observed > Assumed:
     a loop only ever comes from something the user actually SAID.

  2. STATUS over time — ``open`` / ``progressing`` (progress mentioned) / ``stalled``
     (stated, then long silent) / ``done`` (completion mentioned) / ``declined`` (the user
     said no). Status is DERIVED FROM EVIDENCE (recency + progress/completion/decline cues),
     carried with a confidence. ``done`` and ``declined`` ARCHIVE the loop (a status flip +
     a history entry), they NEVER delete it.

  3. RESURFACE — ``resurface(name, budget=None)`` returns at most ONE stalled open loop
     worth a gentle, OPTIONAL check-in, phrased warmly and in-character ("a while back you
     mentioned wanting to launch VeraCall in March — is that still in the picture?"). It
     NEVER resurfaces a done/declined loop, and never the same loop too often — paced by a
     budget exactly like curiosity, so Vera offers a thread, she does not nag.

  4. LEDGER — an append-only ``.anima/{name}.loops.jsonl``. A loop, once stated, is tracked
     forever; resurfacing is recorded so the pacing can see it; resolution ARCHIVES (a new
     ``status`` line), it never rewrites or removes a prior line. LAW 001.

Isolation-safe like its siblings (``world_state`` / ``curiosity`` / ``meaning``): the live
stores are read when importable and the module degrades to empty (never raises) when they
are not, so ``--selftest`` has zero unbuilt deps and touches no model, network, or the real
``.anima``. It is READ-ONLY over every other store; the ONLY thing it writes is its own
append-only loops ledger.

    from anima import loops
    for L in loops.detect_loops("Vera"):
        print(L["intent"], "—", L["status"])
    line = loops.resurface("Vera")          # at most one gentle check-in, or None
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

from . import secure_store

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. We READ the live stores when importable and
# degrade to empty otherwise — this module never hard-depends on them, never
# writes them, and never raises if they are absent. We need, at most:
#   world_state.World  — the relation graph (goal / working_toward edges)
#   memory_lirf.Facts  — the LIRF ledger (stated goal/intention rows), SELF
#   meaning.significance — soft ordering boost for a loop that also MATTERS
# Each is wrapped so a missing/erroring dep is simply "no data", not a crash.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from .world_state import World as _World
    _HAVE_WORLD = True
except Exception:  # pragma: no cover - isolation fallback
    _World = None
    _HAVE_WORLD = False

try:  # pragma: no cover - import wiring
    from .memory_lirf import Facts as _Facts, SELF as _SELF
    _HAVE_LIRF = True
except Exception:  # pragma: no cover - isolation fallback
    _Facts = None
    _SELF = "you"
    _HAVE_LIRF = False

try:  # pragma: no cover - import wiring
    from . import meaning as _meaning
    _HAVE_MEANING = True
except Exception:  # pragma: no cover - isolation fallback
    _meaning = None
    _HAVE_MEANING = False

# The verbatim law this engine enforces, read from the constitution when present so there is
# ONE source of truth; a tiny literal fallback keeps the self-test dependency-free.
try:  # pragma: no cover - import wiring
    from .constitution import LAW_001 as _LAW_001, LAW_ID as _LAW_ID
except Exception:  # pragma: no cover - isolation fallback
    _LAW_ID = "ANIMA LAW 001"
    _LAW_001 = (
        "ANIMA LAW 001 — NEVER LOSE CONTINUITY. "
        "Unknown > Lost. Compressed > Forgotten. Archived > Deleted. Observed > Assumed."
    )


def law() -> str:
    """The verbatim LAW 001 this engine makes concrete for stated commitments. Single
    source of truth (constitution constant, or a faithful literal fallback)."""
    return _LAW_001


# Where the creature's life is kept — mirrors world_state / curiosity / meaning so the
# loops ledger sits beside the things it tracks. Overridable for tests (the self-test and
# scripts/test_loops.py redirect this to a TemporaryDirectory).
STORE = Path(os.environ.get("ANIMA_STORE", ".anima"))

VERSION = 1


def _now() -> str:
    """UTC ISO-8601 to the second, matching memory_lirf/world_state stamp shape."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id() -> str:
    """Stable loop id, same shape family as the ledgers ('l_' prefix to read distinctly)."""
    return "l_" + secrets.token_hex(6)


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
# STATUS — the small closed vocabulary, and the two that ARCHIVE (LAW 001:
# a resolved loop is archived via a status flip + history, never deleted).
# ===========================================================================
OPEN = "open"                 # stated, live, no progress/resolution signal yet
PROGRESSING = "progressing"   # the user mentioned moving on it
STALLED = "stalled"           # stated, then long silent — the resurface candidate
DONE = "done"                 # the user mentioned completing it  -> ARCHIVED
DECLINED = "declined"         # the user said no / dropped it      -> ARCHIVED

STATUSES = (OPEN, PROGRESSING, STALLED, DONE, DECLINED)

# The two terminal, archived states. A loop in either is resolved: kept on disk forever,
# never resurfaced again. (Archived > Deleted.)
ARCHIVED_STATUSES = frozenset({DONE, DECLINED})

# How long a stated-and-then-silent loop must go quiet before it reads "stalled" and
# becomes eligible for a gentle check-in. Conservative — a loop is not nagged the week
# after it's stated. (Days.)
STALL_DAYS = 14.0


# ===========================================================================
# DETECT — stated commitments ONLY. Two sources, both already disciplined to
# "never infer": world_state goal edges, and LIRF goal/intention rows. Plus a
# light scan for an explicit project-with-a-target if it surfaced as a fact.
# Observed > Assumed: nothing here is derived from a hunch — only from a row or
# edge the capture layers stored because the user SAID it.
# ===========================================================================

# The world_state predicates that ARE a stated commitment. ``working_toward`` is exactly
# what world_state writes for "I want to / I'm trying to / my goal is to" (see its rule 7),
# and the ``goal`` KIND tags the same. We accept either signal.
_GOAL_PREDICATES = frozenset({"working_toward", "goal", "wants_to", "plans_to", "aiming_to"})
_GOAL_KINDS = frozenset({"goal"})

# LIRF trait slugs that name a stated goal/intention. memory_lirf's goal capture is light,
# but anything a teammate routes to one of these slugs is, by construction, a stated goal —
# we read it the same way. (Read-only: we never write these.)
_GOAL_TRAITS = frozenset({
    "goal", "goals", "intention", "plan", "plans", "working_on", "works_on",
    "aspiration", "wants_to", "trying_to",
})

# Progress / completion / decline cue lexicons — applied to the EVIDENCE TEXT a store
# carries for the loop (the verbatim snippet / source), never to a fresh inference. These
# decide whether a loop reads progressing / done / declined rather than plain open.
_PROGRESS_CUES = re.compile(
    r"\b(?:started|starting|begun|began|making\s+progress|working\s+on(?:\s+it)?|"
    r"under\s+way|underway|in\s+progress|halfway|got\s+going|kicked\s+off|"
    r"been\s+at\s+it|moving\s+forward|on\s+track)\b", re.I)

_DONE_CUES = re.compile(
    r"\b(?:done|finished|completed|complete|launched|shipped|wrapped\s+up|"
    r"pulled\s+it\s+off|accomplished|achieved|nailed\s+it|got\s+it\s+done|"
    r"finally\s+did\s+it|made\s+it\s+happen|it'?s\s+(?:done|live|out|shipped))\b", re.I)

_DECLINE_CUES = re.compile(
    r"\b(?:gave\s+up|giving\s+up|not\s+doing|won'?t\s+be\s+doing|decided\s+not\s+to|"
    r"changed\s+my\s+mind|dropped\s+(?:it|that)|scrapped|shelved|called\s+(?:it\s+)?off|"
    r"no\s+longer\s+(?:want|plan)|abandoned|backing\s+out|not\s+(?:gonna|going\s+to)\s+happen|"
    r"never\s+mind)\b", re.I)

# A target/date cue — what makes "a project named with a target" a tracked loop rather than
# a vague wish. Presence is recorded on the loop (it sharpens the resurface line) but is NOT
# required: a bare stated goal is still a loop.
_TARGET_CUE = re.compile(
    r"\b(?:by\s+\w+|in\s+(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december|q[1-4]|\d{4}|the\s+(?:spring|summer|fall|autumn|winter))|"
    r"next\s+(?:week|month|year|quarter)|this\s+(?:week|month|year|quarter)|"
    r"end\s+of\s+\w+|before\s+\w+|deadline|target)\b", re.I)


def _clean_intent(s: Any) -> str:
    """A readable surface phrase for the loop's intent (the thing they said they'd do).
    Trims whitespace/punctuation and a leading filler verb-particle; never empties to junk."""
    if s is None:
        return ""
    text = re.sub(r"\s+", " ", str(s).strip()).strip(" .,!?;:\"'")
    return text


def _ev_text(*parts: Any) -> str:
    """Join the textual evidence fragments a store carries (source snippet, object label)
    into one lowercase haystack the cue regexes scan. Pure string work, never a model."""
    bits = [str(p) for p in parts if p]
    return " ".join(bits)


def _status_from_evidence(ev_text: str, *, last_seen: Any,
                          now: Optional[float] = None) -> tuple[str, float]:
    """DERIVE a status + confidence from EVIDENCE only (Observed > Assumed).

    Precedence is by how decisive the signal is: an explicit decline or completion is the
    user RESOLVING the loop and wins; then a progress mention; then recency decides whether
    a still-open loop reads ``open`` (recent) or ``stalled`` (long silent). Confidence is
    higher for the explicit lexical signals than for the time-only ``stalled`` inference.

    Returns ``(status, confidence)``. Never raises.
    """
    hay = ev_text or ""
    # Decline and done are the user explicitly closing the loop — they archive it.
    if _DECLINE_CUES.search(hay):
        return DECLINED, 0.85
    if _DONE_CUES.search(hay):
        return DONE, 0.85
    if _PROGRESS_CUES.search(hay):
        return PROGRESSING, 0.7
    # No resolution/progress words: recency decides open vs stalled.
    days = _days_since(last_seen, now=now)
    if days is not None and days >= STALL_DAYS:
        # the longer the silence, the more confident the "stalled" read (capped)
        conf = min(0.8, 0.5 + 0.01 * (days - STALL_DAYS))
        return STALLED, conf
    return OPEN, 0.6


def _loop_key(subject: str, intent: str) -> str:
    """The STABLE identity of a loop across time, so the same commitment seen again is the
    same loop (not a duplicate), and the ledger can carry its whole history under one key.
    Normalised (lowercase, punctuation->space, collapsed) so a re-statement can't fork it."""
    subj = re.sub(r"[^a-z0-9]+", " ", str(subject or "").lower()).strip()
    obj = re.sub(r"[^a-z0-9]+", " ", str(intent or "").lower()).strip()
    return f"{subj}::{obj}"


def _loop_from_edge(e: dict, *, now: Optional[float] = None) -> Optional[dict]:
    """Build a loop dict from a world_state goal edge, or None if the edge isn't a stated
    commitment. The edge already passed world_state's never-infer capture, so its existence
    IS the 'stated' evidence; we only classify its status from the same source text."""
    if not isinstance(e, dict):
        return None
    pred = str(e.get("predicate", "")).strip().lower()
    kind = str(e.get("kind", "")).strip().lower()
    if pred not in _GOAL_PREDICATES and kind not in _GOAL_KINDS:
        return None
    intent = _clean_intent(e.get("object"))
    if not intent:
        return None
    subject = str(e.get("subject") or _SELF)
    stated_when = e.get("created") or e.get("updated")
    last_seen = e.get("updated") or e.get("created")
    src = e.get("source", "")
    ev_text = _ev_text(intent, src)
    status, conf = _status_from_evidence(ev_text, last_seen=last_seen, now=now)
    return {
        "key": _loop_key(subject, intent),
        "subject": subject,
        "intent": intent,
        "stated_when": stated_when,
        "last_seen": last_seen,
        "status": status,
        "confidence": round(float(conf), 3),
        "support": int(e.get("support", 1)),
        "has_target": bool(_TARGET_CUE.search(ev_text)),
        "source_kind": "world_edge",
        "evidence": {
            "predicate": pred or None,
            "kind": kind or None,
            "source": src or None,
            "support": int(e.get("support", 1)),
            "snippet": intent,
        },
    }


def _loop_from_row(r: dict, *, now: Optional[float] = None) -> list:
    """Build loop dict(s) from a LIRF goal/intention row. A list-valued goal trait yields one
    loop per stated item. Returns [] if the row isn't a goal trait. The row passed LIRF's
    never-infer capture, so it IS stated; we classify status from its evidence snippet."""
    if not isinstance(r, dict):
        return []
    trait = str(r.get("trait", "")).strip().lower()
    if trait not in _GOAL_TRAITS:
        return []
    subject = str(r.get("entity") or _SELF)
    stated_when = r.get("created") or r.get("updated")
    last_seen = r.get("updated") or r.get("created")
    src = r.get("source", "")
    # the evidence snippet a LIRF row carries (verbatim user words) is the richest cue text
    snippet = ""
    ev = r.get("evidence")
    if isinstance(ev, str):
        snippet = ev
    elif isinstance(ev, dict):
        snippet = str(ev.get("text") or ev.get("snippet") or "")
    raw_val = r.get("value")
    values = raw_val if isinstance(raw_val, list) else [raw_val]
    out = []
    for v in values:
        intent = _clean_intent(v)
        if not intent:
            continue
        ev_text = _ev_text(intent, snippet, src)
        status, conf = _status_from_evidence(ev_text, last_seen=last_seen, now=now)
        out.append({
            "key": _loop_key(subject, intent),
            "subject": subject,
            "intent": intent,
            "stated_when": stated_when,
            "last_seen": last_seen,
            "status": status,
            "confidence": round(float(conf), 3),
            "support": int(r.get("support", 1)),
            "has_target": bool(_TARGET_CUE.search(ev_text)),
            "source_kind": "lirf_row",
            "evidence": {
                "trait": trait,
                "source": src or None,
                "support": int(r.get("support", 1)),
                "snippet": snippet or intent,
            },
        })
    return out


def _read_world_edges(name: str) -> list:
    """Active world_state edges (read-only). [] if no store / not importable. Never raises."""
    if not (_HAVE_WORLD and _World is not None):
        return []
    try:
        return [e for e in _World.load(name).active() if isinstance(e, dict)]
    except Exception:
        return []


def _read_lirf_rows(name: str) -> list:
    """Active LIRF rows for the user (read-only). [] if no ledger / not importable. The goal
    filter happens in ``_loop_from_row``; here we just gather active rows. Never raises."""
    if not (_HAVE_LIRF and _Facts is not None):
        return []
    try:
        f = _Facts.load(name)
        # prefer the user-scoped accessor; fall back to all active rows
        if hasattr(f, "about"):
            return [r for r in f.about(_SELF) if isinstance(r, dict)]
        return [r for r in getattr(f, "rows", [])
                if isinstance(r, dict) and r.get("status", "active") == "active"]
    except Exception:
        return []


def detect_loops(name: str, *, now: Optional[float] = None) -> list:
    """ENTRY POINT — the explicitly-stated, unfinished commitments on record for ``name``.

    Reads the stores (world_state goal/``working_toward`` edges + LIRF goal/intention rows),
    NEVER infers, and returns one loop dict per distinct commitment. Each:

        {
          "key":         stable identity across time (subject::intent, normalised),
          "subject":     who holds the commitment (the user, "you"),
          "intent":      the thing they said they'd do (e.g. "launch VeraCall in March"),
          "stated_when": when it was first stated (ISO),
          "last_seen":   most recent time the store touched it (ISO),
          "status":      open / progressing / stalled / done / declined (from EVIDENCE),
          "confidence":  how sure the status read is,
          "support":     how many times it was corroborated,
          "has_target":  whether a date/target was stated (sharpens a resurface),
          "source_kind": world_edge | lirf_row,
          "evidence":    the grounding (predicate/trait, source, support, snippet),
        }

    The LEDGER is then consulted to OVERLAY any recorded resolution: if a loop was marked
    done/declined via ``mark_status``/``close``, that archived status wins over a freshly
    re-derived one (a closed loop stays closed — LAW 001, and never re-surfaced). Loops are
    de-duplicated by key (highest support / most decisive status kept) and returned
    best-first for resurfacing (stalled, with a target, well-corroborated, rise to the top).

    Read-only over every other store. Never raises — a missing store is simply no loops.
    """
    loops: dict = {}

    def _consider(loop: Optional[dict]):
        if not loop:
            return
        k = loop["key"]
        prev = loops.get(k)
        if prev is None:
            loops[k] = loop
            return
        # same commitment seen from two sources: keep the more decisive/­corroborated read.
        if _status_rank(loop["status"]) > _status_rank(prev["status"]) or (
                loop.get("support", 1) > prev.get("support", 1)):
            # preserve the earliest stated_when (the loop was opened the first time it was said)
            loop["stated_when"] = _earliest(prev.get("stated_when"), loop.get("stated_when"))
            loops[k] = loop
        else:
            prev["stated_when"] = _earliest(prev.get("stated_when"), loop.get("stated_when"))

    for e in _read_world_edges(name):
        _consider(_loop_from_edge(e, now=now))
    for r in _read_lirf_rows(name):
        for L in _loop_from_row(r, now=now):
            _consider(L)

    # OVERLAY the append-only ledger's recorded resolutions: a loop the user closed stays
    # closed (archived) regardless of what a re-derivation says, and its archive history is
    # attached for audit. This is where LAW 001's "resolved = archived, never re-opened by
    # silence" becomes real on the read path.
    history = ledger_history(name)
    for k, loop in loops.items():
        hist = history.get(k)
        if not hist:
            continue
        last = hist[-1]
        loop.setdefault("ledger_history", hist)
        # if the LATEST ledger word is a terminal/archived status, it wins.
        if last.get("status") in ARCHIVED_STATUSES:
            loop["status"] = last["status"]
            loop["archived"] = True
            loop["archived_at"] = last.get("at")
            loop["confidence"] = max(float(loop.get("confidence", 0.0)), 0.9)
        elif last.get("status") in STATUSES:
            # a non-terminal recorded status (e.g. an operator nudged it to progressing)
            # only upgrades decisiveness, never overrides a freshly-observed resolution.
            if _status_rank(loop["status"]) < _status_rank(last["status"]):
                loop["status"] = last["status"]

    ordered = sorted(loops.values(), key=_loop_sort_key)
    return ordered


def _earliest(a: Any, b: Any) -> Any:
    """The earlier of two ISO stamps (the loop was opened when first stated). Tolerates
    None / unparseable on either side."""
    ta, tb = _parse_ts(a), _parse_ts(b)
    if ta is None:
        return b if tb is not None else a
    if tb is None:
        return a
    return a if ta <= tb else b


def _status_rank(status: str) -> int:
    """Decisiveness order for de-dup: a resolved/archived read outranks an in-flight one, so
    when two sources disagree the more committed signal is kept. (Not a 'goodness' ordering.)"""
    return {OPEN: 0, PROGRESSING: 1, STALLED: 2, DONE: 3, DECLINED: 3}.get(status, 0)


def _loop_sort_key(loop: dict):
    """Best-first for RESURFACING: surface a stalled, targeted, well-corroborated, long-silent
    loop before a fresh or already-resolved one. Archived loops sink (never resurfaced)."""
    archived = 1 if loop.get("status") in ARCHIVED_STATUSES else 0
    stalled = 0 if loop.get("status") == STALLED else 1   # stalled first
    target = 0 if loop.get("has_target") else 1            # with a stated target first
    silent = _days_since(loop.get("last_seen")) or 0.0
    return (archived, stalled, target, -loop.get("support", 1), -silent, loop.get("intent", ""))


# ===========================================================================
# RANK — order loops by how worth-surfacing they are, with the Meaning Engine as a
# SOFT multiplier. A loop is NEVER created by significance (Observed > Assumed: it must be
# stated); significance only nudges the ORDER, so a stalled commitment about something that
# also matters in the user's life rises above an equally-stalled trivial one.
# ===========================================================================

def _significance_index(name: str) -> dict:
    """A ``{topic_token: score}`` view of the Meaning Engine's significance, read defensively.
    {} if meaning isn't importable/usable. Never raises — significance is a nice-to-have here."""
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
        score = float(item.get("score", 0.0) or 0.0)
        for tok in re.sub(r"[^a-z0-9]+", " ", subj).split():
            idx[tok] = max(idx.get(tok, 0.0), score)
    return idx


def rank_loops(name: str, *, now: Optional[float] = None) -> list:
    """``detect_loops`` re-ordered with the Meaning Engine as a soft boost. Each loop gains a
    ``rank`` (its base worth-surfacing weight times a small significance multiplier). Returns
    loops best-first. Read-only; if meaning is unavailable this is just ``detect_loops``."""
    loops = detect_loops(name, now=now)
    sig = _significance_index(name)
    for L in loops:
        base = 0.0
        if L.get("status") == STALLED:
            base += 2.0
        elif L.get("status") == OPEN:
            base += 1.0
        elif L.get("status") == PROGRESSING:
            base += 0.5
        if L.get("has_target"):
            base += 0.5
        base += 0.1 * float(L.get("support", 1))
        # significance multiplier: 1.0 + (matched significance, capped) — only nudges order.
        boost = 0.0
        if sig:
            toks = re.sub(r"[^a-z0-9]+", " ", str(L.get("intent", "")).lower()).split()
            boost = max((sig.get(t, 0.0) for t in toks), default=0.0)
        L["rank"] = round(base * (1.0 + min(0.5, boost)), 4)
    loops.sort(key=lambda L: (1 if L.get("status") in ARCHIVED_STATUSES else 0, -L.get("rank", 0.0)))
    return loops


# ===========================================================================
# THE PACING BUDGET — read DEFENSIVELY from caps, exactly like curiosity. The budget
# governs HOW OFTEN ``resurface`` offers a check-in (frequency only, never content), so
# Vera reaches for a stalled thread sparingly. minimal=rarely, balanced=sometimes,
# deep=readily. This is the #1-product-rule made operational: a gentle offer, never a nag.
# ===========================================================================
_BUDGETS = ("minimal", "balanced", "deep")
_DEFAULT_BUDGET = "balanced"

_BUDGET_RATE = {
    "minimal": 0.20,    # rarely — only the most clearly-stalled, sparingly
    "balanced": 0.55,   # sometimes
    "deep": 1.00,       # readily — whenever a worthy stalled loop is due
}

# The minimum number of days between two resurfacings of the SAME loop. Even at the deep
# budget, a loop offered today is not offered again tomorrow — pacing is a hard floor, not
# just a probability. This is what keeps "gentle" from sliding into "nagging".
RESURFACE_COOLDOWN_DAYS = 21.0


def read_budget(name: str) -> str:
    """The user's resurfacing budget for ``name`` — read defensively from ``caps`` (a
    ``caps.loops(name)`` helper, then a ``"loops"`` key, then a generic ``"curiosity"`` key
    so resurfacing inherits the same restraint dial if no loops-specific one exists). Anything
    unrecognised / absent / erroring -> "balanced". Always returns one of ``_BUDGETS``."""
    try:
        from . import caps as _caps  # local import: defensive, no hard dep
        for helper in ("loops", "curiosity"):
            fn = getattr(_caps, helper, None)
            if callable(fn):
                v = fn(name)
                if isinstance(v, str) and v.strip().lower() in _BUDGETS:
                    return v.strip().lower()
        blob = _caps.load(name) if hasattr(_caps, "load") else {}
        if isinstance(blob, dict):
            for key in ("loops", "curiosity"):
                v = blob.get(key)
                if isinstance(v, str) and v.strip().lower() in _BUDGETS:
                    return v.strip().lower()
    except Exception:
        pass
    return _DEFAULT_BUDGET


def _budget_allows(name: str, loop: dict, budget: str) -> bool:
    """The FREQUENCY decision for one loop under a budget. Deterministic (hash of name +
    loop key) so the SAME loop yields the SAME decision on re-eval within a budget — a
    check-in doesn't flicker turn to turn. A more clearly-stalled (longer-silent, targeted)
    loop clears the bar a little more readily. Content is NEVER touched here; purely how-often."""
    rate = _BUDGET_RATE.get(budget, _BUDGET_RATE[_DEFAULT_BUDGET])
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    h = hashlib.sha256(f"{name}::{loop.get('key','')}".encode("utf-8")).hexdigest()
    draw = int(h[:8], 16) / 0xFFFFFFFF
    boost = 0.0
    if loop.get("has_target"):
        boost += 0.15
    silent = _days_since(loop.get("last_seen")) or 0.0
    boost += min(0.20, 0.005 * max(0.0, silent - STALL_DAYS))
    return draw < min(1.0, rate + boost)


# ===========================================================================
# RESURFACE — at most ONE gentle, OPTIONAL check-in on a stalled open loop. Warm,
# in-character, never nagging, never a done/declined loop, never the same loop too often.
# ===========================================================================

# Warm, optional templates. Each is a complete in-character line — no scaffold tags, no
# "according to my memory", no disclaimer. They OFFER the thread and explicitly leave the
# door open ("if it's still in the picture" / "no pressure"), honouring the #1 product rule.
# {intent} is the thing they said they'd do; {ago} a soft time phrase.
_RESURFACE_TEMPLATES = (
    "A {ago} back you mentioned wanting to {intent} — is that still in the picture?",
    "I remember you said you wanted to {intent}. No pressure at all — just wondering how that's sitting with you these days.",
    "You'd talked about wanting to {intent} {ago} ago. Still something you're hoping to get to?",
    "That thing you mentioned — {intent} — has it found its moment yet, or is it still on the someday list?",
)

# A loop whose intent ALREADY reads like a full clause ("launch VeraCall in March") slots
# straight into "wanting to {intent}". We don't re-grammar it; we trust the stored phrase.


def _soft_ago(last_seen: Any) -> str:
    """A gentle, non-clinical time phrase for how long ago a loop went quiet ("while",
    "month", "couple months", "while"). Never an exact day count — warmth over precision."""
    days = _days_since(last_seen)
    if days is None:
        return "while"
    if days < 30:
        return "while"
    if days < 75:
        return "month or so"
    if days < 200:
        return "couple of months"
    return "while back"


def _resurface_line(loop: dict) -> str:
    """Render ONE warm, optional check-in for a loop. Deterministic per loop key (so the
    same loop reads the same way), no scaffold tag, no disclaimer, never breaks character."""
    intent = _clean_intent(loop.get("intent")) or "that thing you were hoping to do"
    ago = _soft_ago(loop.get("last_seen"))
    h = hashlib.sha256(f"tmpl::{loop.get('key','')}".encode("utf-8")).hexdigest()
    tmpl = _RESURFACE_TEMPLATES[int(h[:4], 16) % len(_RESURFACE_TEMPLATES)]
    return tmpl.format(intent=intent, ago=ago)


def resurface(name: str, *, budget: Optional[str] = None,
              now: Optional[float] = None) -> Optional[str]:
    """ENTRY POINT — at most ONE gentle, optional check-in on a stalled open loop, or ``None``.

    Picks the top STALLED loop that is (a) not archived (never a done/declined loop), (b) past
    its resurface cooldown (never the same loop too often), and (c) cleared by the pacing
    budget this turn (so Vera offers a thread sparingly, never nags). Returns a warm,
    in-character line — no scaffold tags, no "according to my memory", no character break — or
    ``None`` when nothing is due / the budget says stay quiet.

    DOES NOT record the resurfacing — the caller does that via ``mark_resurfaced`` ONLY if the
    line is actually surfaced to the user (so a prepared-but-unshown check-in doesn't burn the
    loop's cooldown). The #1 product rule lives here: this is an offer, always optional, never
    a demand. Never raises; returns ``None`` on any failure or when it should stay quiet."""
    try:
        loops = rank_loops(name, now=now)
    except Exception:
        return None
    budget = (budget or read_budget(name)).strip().lower()
    if budget not in _BUDGETS:
        budget = _DEFAULT_BUDGET

    last_resurfaced = _last_resurfaced_index(name)
    ref = now if now is not None else datetime.now(timezone.utc).timestamp()

    for loop in loops:
        if loop.get("status") != STALLED:
            continue
        if loop.get("status") in ARCHIVED_STATUSES or loop.get("archived"):
            continue  # belt-and-suspenders: never resurface a resolved loop
        # cooldown: not the same loop too often
        prev = last_resurfaced.get(loop["key"])
        if prev is not None:
            since = _days_since(prev, now=ref)
            if since is not None and since < RESURFACE_COOLDOWN_DAYS:
                continue
        # pacing budget: stay quiet unless this loop is due under the budget
        if not _budget_allows(name, loop, budget):
            continue
        line = _resurface_line(loop)
        if not line:
            continue
        # stash the chosen loop key so a caller that then calls mark_resurfaced records the
        # right loop without re-deriving (mirrors curiosity.next_question/_question).
        loop["_resurfaced_line"] = line
        resurface._last_choice = {"name": name, "key": loop["key"], "line": line}  # type: ignore[attr-defined]
        return line
    return None


def last_resurface_choice() -> Optional[dict]:
    """The loop ``resurface`` last chose (``{name, key, line}``), so a caller can mark exactly
    that loop resurfaced. None if ``resurface`` hasn't returned a line yet this process."""
    return getattr(resurface, "_last_choice", None)


# ===========================================================================
# THE LEDGER — append-only .anima/{name}.loops.jsonl. The ONLY thing this module writes.
# Every event (a loop's first sighting, a resurfacing, a status change/resolution) is a new
# line; nothing is ever rewritten or removed. A resolved loop is ARCHIVED here as a fresh
# status line, never deleted — LAW 001 made concrete for commitments.
# ===========================================================================

def ledger_path(name: str) -> Path:
    """The append-only loops ledger for ``name``. One JSON object per line, never rewritten —
    exactly like the continuity (LAW 001) and curiosity (LAW 002) ledgers."""
    return STORE / f"{name}.loops.jsonl"


def _append(name: str, rec: dict) -> Optional[dict]:
    """Append one event to the loops ledger, durably (fsync). Append-only, never truncate or
    overwrite (LAW 001). Returns the written record, or None on a write failure (a ledger
    write is best-effort and must never crash a turn — but a success is durable)."""
    if not isinstance(rec, dict):
        return None
    try:
        p = ledger_path(name)
        secure_store.append_jsonl(p, rec)
    except Exception:
        return None
    return rec


def read_ledger(name: str) -> list:
    """Every event in the loops ledger, oldest->newest (read-only). Tolerates a missing or
    partially-corrupt ledger: an unparseable line is kept visible as ``{"_unparsed": ...}``
    rather than dropped (Unknown > Lost), never silently skipped into oblivion."""
    p = ledger_path(name)
    if not p.exists():
        return []
    out: list = []
    try:
        lines = secure_store.read_jsonl_lines(p)
    except Exception:
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append({"_unparsed": line})  # a corrupt line is information; keep it
    return out


def ledger_history(name: str) -> dict:
    """The ledger folded into ``{loop_key: [status events oldest->newest]}`` — the audit spine
    of each loop's life. Only ``status``-kind events (a first-sighting / resolution / nudge)
    are included; resurfacing events are tracked separately. Read-only; never raises."""
    hist: dict = {}
    for rec in read_ledger(name):
        if not isinstance(rec, dict):
            continue
        if rec.get("event") != "status":
            continue
        k = rec.get("key")
        if not isinstance(k, str) or not k:
            continue
        hist.setdefault(k, []).append(rec)
    return hist


def _last_resurfaced_index(name: str) -> dict:
    """``{loop_key: last_resurfaced_iso}`` from the ledger's resurface events — the cooldown
    clock the pacing reads so the same loop isn't offered too often. Read-only; never raises."""
    idx: dict = {}
    for rec in read_ledger(name):
        if isinstance(rec, dict) and rec.get("event") == "resurfaced":
            k, at = rec.get("key"), rec.get("at")
            if isinstance(k, str) and k:
                idx[k] = at
    return idx


def mark_resurfaced(name: str, loop_or_key: Any, *, line: str = "") -> Optional[dict]:
    """ENTRY POINT — record that a loop's gentle check-in was actually surfaced to the user,
    append-only. After this, ``resurface`` won't offer the SAME loop again until the cooldown
    passes (pacing — never nag). Accepts a loop dict or a bare key. Returns the written record,
    or None on a bad input / write failure (best-effort; never raises)."""
    key = loop_or_key.get("key") if isinstance(loop_or_key, dict) else loop_or_key
    if not isinstance(key, str) or not key:
        return None
    rec = {
        "law": _LAW_ID,
        "event": "resurfaced",
        "at": _now(),
        "key": key,
        "line": (line or (loop_or_key.get("_resurfaced_line", "") if isinstance(loop_or_key, dict) else ""))[:500],
    }
    return _append(name, rec)


def mark_status(name: str, loop_or_key: Any, status: str, *,
                note: str = "", confidence: Optional[float] = None) -> Optional[dict]:
    """ENTRY POINT — record a STATUS change for a loop, append-only (LAW 001: a resolution is
    a NEW line + the prior lines stay; nothing is rewritten or deleted). Use this to archive a
    loop the user finished (``status=done``) or dropped (``status=declined``): the loop stays
    on disk forever, and ``detect_loops`` will surface it as archived and never resurface it.

    ``status`` must be one of the closed vocabulary. Accepts a loop dict or a bare key. Returns
    the written record, or None on a bad status / input / write failure. Never raises."""
    status = (status or "").strip().lower()
    if status not in STATUSES:
        return None
    key = loop_or_key.get("key") if isinstance(loop_or_key, dict) else loop_or_key
    intent = loop_or_key.get("intent", "") if isinstance(loop_or_key, dict) else ""
    subject = loop_or_key.get("subject", _SELF) if isinstance(loop_or_key, dict) else _SELF
    if not isinstance(key, str) or not key:
        return None
    rec = {
        "law": _LAW_ID,
        "event": "status",
        "at": _now(),
        "key": key,
        "status": status,
        "subject": subject,
        "intent": intent,
        "archived": status in ARCHIVED_STATUSES,
        "note": (note or "")[:500],
    }
    if confidence is not None:
        try:
            rec["confidence"] = round(float(confidence), 3)
        except (TypeError, ValueError):
            pass
    return _append(name, rec)


def close(name: str, loop_or_key: Any, *, resolution: str = DONE,
          note: str = "") -> Optional[dict]:
    """ENTRY POINT — ARCHIVE a loop as resolved (``done`` by default, or ``declined``). A thin,
    intention-revealing wrapper over ``mark_status`` for the common case "this loop is closed".
    LAW 001: this ARCHIVES — a new status line — it does NOT delete; the loop and its whole
    history remain on disk and are never resurfaced again. Returns the written record or None."""
    resolution = (resolution or DONE).strip().lower()
    if resolution not in ARCHIVED_STATUSES:
        resolution = DONE
    return mark_status(name, loop_or_key, resolution, note=note)


def record_detected(name: str, loops: Optional[list] = None) -> list:
    """OPTIONAL — append a first-sighting ``status`` line for any currently-detected loop NOT
    yet in the ledger, so its existence is durably stamped the moment it's known (a loop, once
    stated, is tracked forever — even if the live store later changes). Idempotent: a loop
    already in the ledger is not re-stamped. Returns the records written ([] if none). This is
    the only writer ``detect_loops`` callers may want to invoke to make tracking permanent."""
    loops = loops if loops is not None else detect_loops(name)
    seen = set(ledger_history(name).keys())
    written = []
    for L in loops:
        if not isinstance(L, dict):
            continue
        k = L.get("key")
        if not isinstance(k, str) or not k or k in seen:
            continue
        rec = mark_status(name, L, L.get("status", OPEN),
                          note="first sighting (loop opened)",
                          confidence=L.get("confidence"))
        if rec:
            written.append(rec)
            seen.add(k)
    return written


# ===========================================================================
# RENDER — the human-readable AUDIT SURFACE. What loops Vera is holding, their status,
# and which (if any) is due for a gentle check-in. The Dream-Engine counterpart to
# curiosity.render / world_state.render. Read-only; never raises.
# ===========================================================================

_STATUS_GLYPH = {
    OPEN: "○ open",
    PROGRESSING: "◐ progressing",
    STALLED: "◔ stalled",
    DONE: "● done (archived)",
    DECLINED: "✕ declined (archived)",
}


def render(name: str) -> str:
    """The human-readable audit surface: the open loops on record, each with status and
    provenance, the archived (resolved) ones kept visible below, and the single check-in (if
    any) currently due. Mirrors the sibling engines' render. Read-only; never raises."""
    try:
        loops = rank_loops(name)
    except Exception:
        loops = []
    budget = read_budget(name)
    live = [L for L in loops if L.get("status") not in ARCHIVED_STATUSES]
    archived = [L for L in loops if L.get("status") in ARCHIVED_STATUSES]

    out = [f"Open loops {name} is holding ({len(live)} live, {len(archived)} archived; "
           f"resurface budget: {budget}):"]
    if not live:
        out.append("  (no open loops yet — they appear when you state a goal or intention)")
    for L in live:
        glyph = _STATUS_GLYPH.get(L.get("status"), L.get("status", "?"))
        tgt = " · has a stated target" if L.get("has_target") else ""
        out.append(
            f"  • [{glyph}] {L.get('intent','?')}\n"
            f"      stated {L.get('stated_when','?')} · last seen {L.get('last_seen','?')}"
            f" · corroborated {L.get('support',1)}x{tgt}")
    if archived:
        out.append(f"\n  Archived ({len(archived)} — resolved, kept forever, never re-surfaced; LAW 001):")
        for L in archived:
            glyph = _STATUS_GLYPH.get(L.get("status"), L.get("status", "?"))
            out.append(f"    {glyph}: {L.get('intent','?')}"
                       + (f" (at {L.get('archived_at')})" if L.get("archived_at") else ""))

    try:
        due = resurface(name)
    except Exception:
        due = None
    out.append("")
    if due:
        out.append(f"  Gentle check-in due (optional): \"{due}\"")
    else:
        out.append("  No check-in due right now (nothing stalled-and-due, or the budget says rest).")
    return "\n".join(out)


__all__ = [
    # status vocabulary
    "OPEN", "PROGRESSING", "STALLED", "DONE", "DECLINED", "STATUSES", "ARCHIVED_STATUSES",
    # detect / rank
    "detect_loops", "rank_loops",
    # resurface
    "resurface", "read_budget", "last_resurface_choice",
    # ledger (the only writers, all append-only)
    "ledger_path", "read_ledger", "ledger_history",
    "mark_resurfaced", "mark_status", "close", "record_detected",
    # audit + law
    "render", "law",
]


# ===========================================================================
# SELF-TEST — run directly: `python3 -m anima.loops`. No model, no network; writes only to
# a throwaway store it cleans up (NEVER the real Vera.*). Mirrors the sibling organs'
# ok(label, cond) harness and the curiosity STORE-redirect gotcha (redirect the currently-
# executing module AND, under -m, the package copy too, so no write leaks to real .anima).
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

    # Redirect EVERY store this module touches into a throwaway temp dir, exactly like
    # scripts/test_continuity.py and curiosity._selftest. Under `python3 -m anima.loops`
    # THIS function runs in the __main__ module, whose bare STORE is a SEPARATE binding from
    # anima.loops.STORE — so redirect the currently-executing module AND the package copy.
    _cur = sys.modules[__name__]
    _mods = [_cur]
    try:
        import anima.loops as _pkg  # the package copy, if distinct
        if _pkg is not _cur:
            _mods.append(_pkg)
    except Exception:
        pass

    td = tempfile.mkdtemp(prefix="anima-loops-self-")
    tp = Path(td)
    saved = [(m, getattr(m, "STORE", None)) for m in _mods]
    for _m in _mods:
        _m.STORE = tp

    name = "loops_self_" + secrets.token_hex(3)
    try:
        # --- law resolves to LAW 001 (constitution constant or fallback literal) ---
        ok("law: resolves to NEVER LOSE CONTINUITY",
           "NEVER LOSE CONTINUITY" in law())

        # --- status derivation from EVIDENCE only ---
        ok("status: a long-silent stated goal reads 'stalled'",
           _status_from_evidence("launch veracall in march",
                                 last_seen="2026-01-01T00:00:00Z",
                                 now=datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())[0] == STALLED)
        ok("status: a completion cue reads 'done'",
           _status_from_evidence("finally launched veracall", last_seen=_now())[0] == DONE)
        ok("status: a decline cue reads 'declined'",
           _status_from_evidence("decided not to do veracall", last_seen=_now())[0] == DECLINED)
        ok("status: a fresh stated goal reads 'open'",
           _status_from_evidence("launch veracall", last_seen=_now())[0] == OPEN)

        # --- detect from a synthetic world goal edge ---
        long_ago = datetime(2026, 1, 5, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        fake_edge = {
            "id": "e1", "kind": "goal", "subject": "you", "predicate": "working_toward",
            "object": "launch veracall in march", "confidence": 0.9, "support": 1,
            "source": "chat 2026-01-05", "created": long_ago, "updated": long_ago,
            "status": "active", "history": [],
        }
        L = _loop_from_edge(fake_edge,
                            now=datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())
        ok("detect: a stated working_toward edge becomes an open loop",
           L is not None and L["intent"] == "launch veracall in march")
        ok("detect: that long-silent loop reads 'stalled'", L and L["status"] == STALLED)
        ok("detect: a stated target is recognised on the loop", L and L["has_target"] is True)

        # --- detect NEVER fabricates: a non-goal edge yields no loop ---
        not_goal = dict(fake_edge, kind="problem", predicate="stressed_by", object="work")
        ok("detect: a non-goal edge produces NO loop (never fabricate)",
           _loop_from_edge(not_goal) is None)

        # --- resurface: warm, contextual, no scaffold/disclaimer, single ---
        line = _resurface_line(L)
        low = line.lower()
        ok("resurface: the line names the stated intent (contextual)",
           "veracall" in low)
        ok("resurface: warm + optional phrasing (offers, never demands)",
           any(p in low for p in ("still", "no pressure", "wondering", "someday", "moment")))
        ok("resurface: no scaffold tag / no 'according to my memory' / no character break",
           "[" not in line and "according to my memory" not in low
           and "i'm just an ai" not in low and "as an ai" not in low)

        # --- the LEDGER: append-only, status history, archive-not-delete (LAW 001) ---
        rec_open = mark_status(name, L, OPEN, note="first sighting")
        ok("ledger: a status event is written", rec_open is not None)
        rec_prog = mark_status(name, L, PROGRESSING, note="user said they started")
        rec_done = close(name, L, resolution=DONE, note="user said they shipped it")
        ok("ledger: close() archives as 'done' (not a delete)",
           rec_done is not None and rec_done["status"] == DONE and rec_done["archived"] is True)
        hist = ledger_history(name).get(L["key"], [])
        ok("LAW 001: the full status history SURVIVES append-only (open->progressing->done)",
           [h["status"] for h in hist] == [OPEN, PROGRESSING, DONE])
        ok("LAW 001: nothing was deleted — every prior line is still on disk",
           len(read_ledger(name)) >= 3)
        raw_disk = ledger_path(name).read_text(encoding="utf-8")
        ok("LAW 001: the ledger FILE on disk still contains every status (archived, not erased)",
           raw_disk.count('"event": "status"') >= 3 and '"status": "open"' in raw_disk)

        # --- detect OVERLAYS the archived resolution: a closed loop reads done + never resurfaces ---
        # build a live store that re-derives the SAME loop key, then confirm the ledger wins.
        # (we simulate the live store via a monkeypatched reader so the self-test stays
        # dependency-free — it asserts the OVERLAY logic, which is what matters here.)
        global _read_world_edges
        _orig_reader = _read_world_edges

        def _fake_reader(_name, _edge=fake_edge):
            return [dict(_edge, updated=long_ago)]

        _read_world_edges = _fake_reader  # type: ignore[assignment]
        try:
            detected = detect_loops(name,
                                    now=datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())
            same = [d for d in detected if d["key"] == L["key"]]
            ok("detect+ledger: the closed loop is surfaced as ARCHIVED (ledger overlay wins)",
               len(same) == 1 and same[0]["status"] == DONE and same[0].get("archived") is True)
            ok("resurface: an archived (done) loop is NEVER resurfaced",
               resurface(name, budget="deep",
                         now=datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()) is None)
        finally:
            _read_world_edges = _orig_reader  # type: ignore[assignment]

        # --- resurface picks a STALLED, non-archived loop and pacing returns at most one ---
        _read_world_edges = _fake_reader  # type: ignore[assignment]
        try:
            name2 = "loops_self2_" + secrets.token_hex(3)
            now_jun = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
            r1 = resurface(name2, budget="deep", now=now_jun)
            ok("resurface: a stalled open loop IS resurfaceable (one warm line)",
               isinstance(r1, str) and "veracall" in r1.lower())
            # pacing: once recorded, the SAME loop is not offered again (cooldown floor)
            choice = last_resurface_choice()
            ok("resurface: exposes its chosen loop key for mark_resurfaced", choice and choice.get("key"))
            mark_resurfaced(name2, choice["key"], line=r1)
            r2 = resurface(name2, budget="deep", now=now_jun)
            ok("pacing: the SAME loop is NOT resurfaced again within cooldown (never nag)",
               r2 is None)
            # and far in the future (past cooldown) it may surface again — still tracked forever
            future = datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp()
            r3 = resurface(name2, budget="deep", now=future)
            ok("pacing: past the cooldown the loop can gently surface again (still tracked, never lost)",
               isinstance(r3, str))
        finally:
            _read_world_edges = _orig_reader  # type: ignore[assignment]

        # --- a minimal budget stays silent far more than deep (frequency, not content) ---
        _read_world_edges = _fake_reader  # type: ignore[assignment]
        try:
            now_jun = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
            silent_min = sum(1 for i in range(40)
                             if resurface(f"loops_bud_min_{i}", budget="minimal", now=now_jun) is None)
            silent_deep = sum(1 for i in range(40)
                              if resurface(f"loops_bud_deep_{i}", budget="deep", now=now_jun) is None)
            ok(f"budget: minimal stays silent more than deep ({silent_min}/40 vs {silent_deep}/40)",
               silent_min > silent_deep)
            ok("budget: deep almost always offers when a stalled loop is due",
               silent_deep <= 2)
        finally:
            _read_world_edges = _orig_reader  # type: ignore[assignment]

        # --- render is human-readable + shows status + the law ---
        _read_world_edges = _fake_reader  # type: ignore[assignment]
        try:
            rep = render("loops_render_" + secrets.token_hex(3))
            ok("render: audit surface shows the resurface budget", "budget:" in rep)
            ok("render: audit surface labels open loops with a status", "stalled" in rep.lower())
        finally:
            _read_world_edges = _orig_reader  # type: ignore[assignment]

        # --- detect never raises with NO stores at all (degrades to empty) ---
        ok("robust: detect_loops on an empty/unknown name yields a list, never raises",
           isinstance(detect_loops("nobody_" + secrets.token_hex(3)), list))
        ok("robust: resurface on an empty name yields None, never raises",
           resurface("nobody_" + secrets.token_hex(3)) is None)

    finally:
        for fp in glob.glob(str(STORE / "loops_self*")) + glob.glob(str(STORE / "loops_*")) \
                + glob.glob(str(STORE / "nobody_*")):
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
    print("ALL LOOPS SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
