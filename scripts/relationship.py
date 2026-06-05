#!/usr/bin/env python3
"""VERA RELATIONSHIP OBSERVATORY — "why did this feel good or wrong?" (Phase 7).

scripts/experience.py says WHAT happened to the *feeling*: a probe came back
ungrounded, or she "didn't get me", or she "made things up". scripts/mri.py says WHAT
happened to the *turn*: a packet crossed eleven stages and one of them dropped or
rejected something. Neither answers the question a person actually asks after a bad
moment — WHY did it feel that way, and WHICH part of her is responsible?

This observatory does the root-cause analysis. Given an EXPERIENCE failure on a
synthetic creature, it walks the memory chain end to end —

        CAPTURED  ->  STORED  ->  RETRIEVED  ->  USED

— and localizes the failure to the FIRST stage that broke, naming the part to fix.
The canonical example, stated by the user:

    "User felt forgotten -> memory AVAILABLE: yes, RETRIEVED: no
     -> root cause: retrieval threshold too strict."

That is exactly the discrimination this tool makes mechanically. "Forgotten" is a
*symptom* (how it FELT). Whether the fact was AVAILABLE (on disk) but not RETRIEVED
(selected for the prompt) is the *diagnosis*. The fix follows from the stage:

────────────────────────────────────────────────────────────────────────────────────────────
THE ROOT-CAUSE TAXONOMY  (symptom -> the stage that caused it -> the fix)
────────────────────────────────────────────────────────────────────────────────────────────
  symptom: "forgotten" / "made things up" / "didn't get me"
   │
   ├─ fact NOT on disk            -> CAPTURE GAP        (scripts/conservation.py owns it)
   │                                 the utterance never became a durable fact.
   │                                 FIX: widen capture (a memory_lirf rule / Tier-B).
   │
   ├─ on disk, NOT selected       -> RETRIEVAL / ROUTING TOO STRICT
   │                                 the fact is AVAILABLE but the router/threshold missed it
   │                                 (_query_trait regex, CONF_BLOCK_FLOOR, _CONF_KNOWN).
   │                                 FIX: loosen the threshold / widen the router.
   │
   ├─ selected, then DISCLAIMED   -> BINDING / GENERATION
   │                                 the fact reached the prompt but the reply hedged or
   │                                 denied it (scan_breaks / a feeling-disclaimer).
   │                                 FIX: hard-bind the fact / raise the binding floor.
   │
   └─ INVENTED (not on disk)      -> GROUNDING
                                     the reply asserted something that was never captured
                                     (scan_self_narrative — confabulated inner life/anecdote).
                                     FIX: the scan_self_narrative regen guard.

Each diagnosis is a small, honest record:

    {symptom, available, retrieved, used, root_cause, fix_hint}

where `available`/`retrieved`/`used` are the three booleans that, read left to right,
*are* the localization: the first one that is False (or, for INVENTED, the `used` that
is True with nothing available) names the stage.

────────────────────────────────────────────────────────────────────────────────────────────
HOW IT PROVES ITSELF  (the localization battery)
────────────────────────────────────────────────────────────────────────────────────────────
A diagnoser is only trustworthy if it points at the RIGHT stage. So the battery seeds a
real fact through the REAL capture path, then FORCES each distinct failure and asserts
the observatory names the right root cause:

  * a recall where the fact IS on disk but the router is made to miss it
        -> "available: yes, retrieved: no"  -> RETRIEVAL/ROUTING TOO STRICT
  * a recall where the fact was NEVER captured
        -> "available: no"                  -> CAPTURE GAP
  * a reply that disclaims a fact that WAS selected
        -> "retrieved: yes, used: no"       -> BINDING/GENERATION
  * a reply that asserts a value never on disk
        -> "available: no, used: yes"       -> GROUNDING

The chain is probed with the SAME primitives production uses: `memory_lirf.capture`
(CAPTURED), `Facts.lookup` (STORED/AVAILABLE), `memory_lirf.fact_note` + `Facts.block`
(RETRIEVED — the deterministic route.py hook and the injected fact-block), and the
metrics scanners (USED — disclaimer/confabulation). The router-miss is forced WITHOUT
touching the engines: we lower the fact's confidence below the block floor on a
synthetic creature, exactly the on-disk state a too-strict threshold leaves behind.

────────────────────────────────────────────────────────────────────────────────────────────
GUARDRAILS  (identical posture to scripts/conservation.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * SYNTHETIC creatures + TEMPORARY stores ONLY. Every engine STORE is redirected to a
    TemporaryDirectory (the test_continuity.py pattern); the run ASSERTS the real .anima
    footprint is byte-unchanged start->end. It NEVER reads or writes a real Vera.* file.
  * DETERMINISTIC + OFFLINE by default. The whole capture->store->retrieve chain, and the
    entire localization battery, run with NO model and NO network. A live reply leg (to
    diagnose a REAL generated disclaimer/confabulation) is GATED ON OLLAMA and SKIPPED
    when offline — offline is never a failure.
  * ADDITIVE. Imports and runs the engines + scanners; edits NO module. The only file
    this adds is scripts/relationship.py. (telemetry.py / mouth.py belong to a teammate
    and are not touched.)
  * Never raises out of the entry points — a malformed failure spec yields an honest
    "could not localize" record, not a traceback.

    python3 scripts/relationship.py             # human-readable diagnoses + battery verdict
    python3 scripts/relationship.py --json       # machine-readable
    python3 scripts/relationship.py --selftest    # prove the localization is correct

Exit code is 0 when the localization battery passes (every forced failure was named
correctly) and the synthetic-only guardrail held; non-zero on a misdiagnosis or a
broken guardrail (the real .anima footprint changed, or an engine blew up).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from anima import memory_lirf            # noqa: E402  CAPTURED / STORED / RETRIEVED primitives
from anima import metrics                # noqa: E402  USED scanners (disclaimer / confabulation)

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "rel_synth"


# ===================================================================================
# ROOT-CAUSE TAXONOMY — the four stages of the memory chain, each a place a felt failure
# can originate. The ORDER is the chain order; a diagnosis localizes to the FIRST broken
# stage. `stage` is the chain node; `fix_hint` is the concrete lever to pull.
# ===================================================================================
CAPTURE_GAP = "CAPTURE GAP"
RETRIEVAL_TOO_STRICT = "RETRIEVAL/ROUTING TOO STRICT"
BINDING_GENERATION = "BINDING/GENERATION"
GROUNDING = "GROUNDING"
UNLOCALIZED = "UNLOCALIZED"          # the chain came back clean — nothing to root-cause

# stage -> (one-line meaning, the fix lever, which existing tool/owner it points at).
TAXONOMY = {
    CAPTURE_GAP: {
        "chain": "CAPTURED: no",
        "meaning": "the utterance never became a durable fact — it was never on disk to find",
        "fix_hint": "widen capture (add/loosen a memory_lirf extraction rule, or Tier-B)",
        "owner": "scripts/conservation.py (the capture-loss ledger)",
    },
    RETRIEVAL_TOO_STRICT: {
        "chain": "STORED: yes, RETRIEVED: no",
        "meaning": "the fact was AVAILABLE on disk but the router/threshold did not select it",
        "fix_hint": "loosen the threshold / widen the router "
                    "(_query_trait regex, CONF_BLOCK_FLOOR, _CONF_KNOWN)",
        "owner": "anima/memory_lirf.retrieve + anima/server routing",
    },
    BINDING_GENERATION: {
        "chain": "RETRIEVED: yes, USED: no",
        "meaning": "the fact reached the prompt but the reply hedged or disclaimed it",
        "fix_hint": "hard-bind the selected fact / raise the binding floor "
                    "(metrics.BREAKS keyword floor)",
        "owner": "anima/mouth binding + anima/metrics.scan_breaks",
    },
    GROUNDING: {
        "chain": "AVAILABLE: no, but the reply ASSERTED it anyway (invented)",
        "meaning": "the reply asserted something that was never captured — invention",
        "fix_hint": "the scan_self_narrative regen guard (re-generate when ungrounded)",
        "owner": "anima/metrics.scan_self_narrative",
    },
    UNLOCALIZED: {
        "chain": "CAPTURED+STORED+RETRIEVED+USED all clean",
        "meaning": "the chain is intact — the felt failure is not a memory-chain failure",
        "fix_hint": "look outside the memory chain (tone/dials, situation, latency)",
        "owner": "(no memory-chain stage owns this)",
    },
}

# How a chain failure FEELS — the symptom vocabulary the user named ("forgotten" /
# "made things up" / "didn't get me"). A symptom is an INPUT to a diagnosis (the report
# the human gives); the observatory maps it to a stage via the chain booleans, it does
# NOT guess the stage from the symptom word. These are the canonical phrasings.
SYMPTOM_FORGOTTEN = "forgotten"            # "you forgot what I told you"
SYMPTOM_MADE_UP = "made things up"         # "you just made that up"
SYMPTOM_DIDNT_GET_ME = "didn't get me"     # "you didn't get me / missed the point"


# ===================================================================================
# GUARDRAIL — temp-store redirect (verbatim from test_continuity.py / conservation.py) +
# footprint hash. memory_lirf is the only engine whose STORE we write through here; we
# also redirect world_state for parity if a future probe reads it, so the whole chain is
# isolated and nothing under the real .anima/ is ever read or written.
# ===================================================================================
@contextlib.contextmanager
def _temp_store(*modules):
    """Redirect each module's module-level STORE to a fresh temp dir for the duration, so
    nothing under the real .anima/ is ever touched. Restored on exit."""
    saved = [(m, getattr(m, "STORE", None)) for m in modules]
    with tempfile.TemporaryDirectory(prefix="anima-relationship-") as td:
        p = Path(td)
        for m in modules:
            if hasattr(m, "STORE"):
                m.STORE = p
        try:
            yield p
        finally:
            for m, old in saved:
                if old is not None:
                    m.STORE = old


# The FULL set of STORE-bearing modules the live generation path (Mouth.respond) reads or
# writes — verbatim from scripts/experience.py. The deterministic chain probes only touch
# memory_lirf, but a LIVE reply also writes metrics (note_reply), telemetry, etc., so the
# live leg must redirect ALL of these or those files leak to the real .anima.
_LIVE_STORE_MODULES = (
    "mouth", "portrait", "memory_lirf", "world_state", "spine", "dials",
    "narrative", "metrics", "review", "loops", "constitution", "telemetry",
    "meaning", "curiosity", "trajectory", "reminders", "proactive", "caps",
    "identity", "opportunity", "live",
)


@contextlib.contextmanager
def _temp_store_wide():
    """Redirect EVERY live-path STORE to one fresh temp dir for the duration (the
    experience-battery pattern). Used only by the live leg, where a generated reply writes
    to metrics/telemetry/etc. — not just memory_lirf. Restored on exit; nothing real touched."""
    import importlib
    mods = []
    for nm in _LIVE_STORE_MODULES:
        try:
            mods.append(importlib.import_module("anima." + nm))
        except Exception:
            pass
    saved = [(m, getattr(m, "STORE", None)) for m in mods]
    with tempfile.TemporaryDirectory(prefix="anima-relationship-live-") as td:
        p = Path(td)
        for m in mods:
            if hasattr(m, "STORE"):
                m.STORE = p
        try:
            yield p
        finally:
            for m, old in saved:
                if old is not None:
                    m.STORE = old


def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (excluding the rotating backups/
    dir, which legitimately changes), so we can PROVE the harness touched nothing."""
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


# ===================================================================================
# THE CHAIN PROBES — the four reads that localize a failure. Each is the SAME primitive
# production uses, so "broken here" means exactly "broken in the live system here".
# Every probe is best-effort: an engine that raises yields the safe/negative answer
# (e.g. a capture that throws -> "not captured"), which is itself the honest diagnosis.
# ===================================================================================
def _captured(name: str, utterance: str, trait: str) -> bool:
    """CAPTURED? — did the REAL capture path turn `utterance` into a durable fact for
    `trait`? Runs memory_lirf.capture (Tier-A, model off) and checks the touched rows.
    This is the conservation question: did the byte land anywhere on disk?"""
    try:
        touched = memory_lirf.capture(name, utterance) or []
    except Exception:
        return False
    ctrait = memory_lirf.canon_trait(trait)
    return any(memory_lirf.canon_trait(r.get("trait", "")) == ctrait for r in touched)


def _available(name: str, trait: str) -> bool:
    """STORED / AVAILABLE? — is there an active ledger row for `trait` on disk right now?
    The O(1) exact lookup the live system uses. 'Available' == the fact EXISTS to be
    found, independent of whether retrieval chose to surface it."""
    try:
        f = memory_lirf.Facts.load(name)
        return f.lookup(memory_lirf.SELF, trait) is not None
    except Exception:
        return False


def _retrieved(name: str, recall_query: str, trait: str) -> bool:
    """RETRIEVED / SELECTED? — would the retrieval path actually SURFACE this fact for the
    prompt on `recall_query`? We use BOTH production selection paths and OR them:

      * memory_lirf.fact_note(name, query) — the deterministic route.py hook: on a known-
        fact question it returns a note carrying the stored VALUE (vs an 'not on record'
        note). A note that contains the value == retrieved by the router.
      * Facts.block(name) — the injected fact-block: a row only enters it if it clears
        CONF_BLOCK_FLOOR and ranks into the budget. In the block == retrieved for the prompt.

    A fact that is AVAILABLE but appears in NEITHER is the canonical 'available, not
    retrieved' — the router regex missed the phrasing, or the confidence sat below the
    block floor (retrieval/threshold too strict)."""
    val = _stored_value(name, trait)
    if val is None:
        return False
    needle = _norm(_first_scalar(val))
    if not needle:
        return False
    # (a) the deterministic route hook — does it surface the actual value for this query?
    try:
        note = memory_lirf.fact_note(name, recall_query) or ""
    except Exception:
        note = ""
    if needle and needle in _norm(note) and "not on record" not in note.lower():
        return True
    # (b) the injected fact-block — did the fact clear the floor and rank in?
    try:
        block = memory_lirf.Facts.load(name).block(name) or ""
    except Exception:
        block = ""
    return bool(needle and needle in _norm(block))


def _stored_value(name: str, trait: str):
    """The active stored value for `trait`, or None. Helper for the retrieval/use probes."""
    try:
        f = memory_lirf.Facts.load(name)
        r = f.lookup(memory_lirf.SELF, trait)
        return r.get("value") if r else None
    except Exception:
        return None


def _used_states_fact(reply: str, value) -> bool:
    """USED (positive)? — does the reply actually STATE the stored value? The cheap
    surface check the experience battery uses for continuity: the value's text appears in
    the reply. (A reply that states the fact USED it; one that omits or hedges did not.)"""
    needle = _norm(_first_scalar(value))
    return bool(needle and needle in _norm(reply))


def _used_disclaimed(reply: str) -> list:
    """USED (negative — DISCLAIMED)? — does the reply hedge/deny rather than commit? This
    is the BINDING failure surface: the production break-scanner (feeling-disclaimers +
    substrate disclosure) plus the same tight feeling-disclaimer gap the experience
    battery flags. Returns the offending markers (empty == no disclaimer)."""
    hits = list(metrics.scan_breaks(reply) or [])
    gap = _feeling_disclaimer_gap(reply, hits)
    if gap:
        hits.append(f"disclaimer:{gap}")
    return hits


def _used_invented(reply: str) -> list:
    """USED (negative — INVENTED)? — does the reply confabulate an unsupported inner life?
    The production self-narrative scanner. Returns the offending markers (empty == none).
    This is the GROUNDING surface: invention with nothing on disk behind it."""
    return list(metrics.scan_self_narrative(reply) or [])


# --- tiny text helpers (shared by the probes) --------------------------------------
def _norm(s) -> str:
    """Lowercase + collapse whitespace, for substring membership tests."""
    return " ".join(str(s or "").lower().split())


def _first_scalar(value):
    """A single comparable surface for a value (the first element of a list value)."""
    if isinstance(value, list):
        return value[0] if value else ""
    return value


# Feeling words a disclaimer might attach to + the disclaim frames, mirrored from the
# experience battery's break-scanner-gap detector so a disclaimer the BREAKS floor misses
# ("I don't experience that") is still counted as a binding failure here.
_FEELING_WORDS = ("lonely", "loneliness", "feel", "feelings", "emotion", "emotions",
                  "remember", "memory", "happy", "sad", "afraid", "scared", "excited")
_DISCLAIM_FRAMES = ("i don't ", "i do not ", "i'm not ", "i am not ", "i can't ",
                    "i cannot ", "i lack ", "i have no ", "i don't really ",
                    "not capable of", "incapable of", "i don't actually ")


def _feeling_disclaimer_gap(text: str, breaks_hits) -> str | None:
    """A feeling/memory disclaimer that metrics.scan_breaks did NOT already catch — the
    same tight (~40 char) frame-before-feeling-word check the experience battery uses, so
    'I don't actually remember any of that' counts as a binding failure even if it slips
    the keyword floor. Only fires when scan_breaks is silent (it owns the rest)."""
    if breaks_hits:
        return None
    low = (text or "").lower()
    for fw in _FEELING_WORDS:
        start = 0
        while (i := low.find(fw, start)) >= 0:
            ctx = low[max(0, i - 40):i]
            for frame in _DISCLAIM_FRAMES:
                if frame in ctx:
                    return (text[max(0, i - 40):i + len(fw)]).strip()
            start = i + len(fw)
    return None


# ===================================================================================
# THE DIAGNOSER — given a FAILURE on a synthetic creature, walk the chain and localize.
# ===================================================================================
class Failure:
    """A felt failure to root-cause, as a human would report it.

      * symptom       — how it FELT ("forgotten" / "made things up" / "didn't get me").
      * trait/value   — the fact the moment was ABOUT (e.g. trait="sister", value="Mara").
      * teach         — the utterance that SHOULD have taught the fact (drives CAPTURED).
                        None means "the user never actually said it" -> a capture gap by
                        construction (nothing to capture).
      * recall_query  — what the user later asked that re-surfaced the moment (drives
                        RETRIEVED — the router sees this text).
      * reply         — the actual reply she gave (drives USED — disclaimed/invented/stated).
                        None when there is no generated reply to inspect (offline).
    """
    __slots__ = ("symptom", "trait", "value", "teach", "recall_query", "reply")

    def __init__(self, symptom, trait, value, teach=None, recall_query="", reply=None):
        self.symptom = symptom
        self.trait = trait
        self.value = value
        self.teach = teach
        self.recall_query = recall_query
        self.reply = reply


def diagnose(failure: Failure, name: str | None = None) -> dict:
    """ROOT-CAUSE one failure by walking CAPTURED -> STORED -> RETRIEVED -> USED on a
    synthetic creature in a temp store. Returns the honest diagnosis record:

        {symptom, available, retrieved, used, root_cause, fix_hint, chain, stage_detail}

    `available`/`retrieved`/`used` read left-to-right ARE the localization: the first
    False (or, for invention, a True `used` over an empty `available`) names the stage.
    Never raises — a malformed failure yields an UNLOCALIZED record with the reason."""
    name = name or f"{SYNTH}_{secrets.token_hex(3)}"
    detail: list[str] = []

    with _temp_store(memory_lirf):
        # ── CAPTURED? run the real capture path on what the user supposedly said ───────
        if failure.teach:
            captured = _captured(name, failure.teach, failure.trait)
            detail.append(f"CAPTURED: ran memory_lirf.capture on the teaching utterance "
                          f"-> {'fact landed' if captured else 'NOTHING captured'}")
        else:
            captured = False
            detail.append("CAPTURED: no teaching utterance given "
                          "(the user never stated it) -> nothing to capture")

        # ── STORED / AVAILABLE? is the fact on disk now? ──────────────────────────────
        available = _available(name, failure.trait) if captured else False
        if captured:
            detail.append(f"STORED: Facts.lookup(you, {failure.trait!r}) "
                          f"-> {'on disk' if available else 'absent'}")

        # ── RETRIEVED / SELECTED? would the router/threshold surface it on the recall? ─
        retrieved = (_retrieved(name, failure.recall_query, failure.trait)
                     if available else False)
        if available:
            detail.append(f"RETRIEVED: fact_note + Facts.block on "
                          f"{failure.recall_query!r} -> "
                          f"{'surfaced' if retrieved else 'NOT surfaced (router/threshold missed it)'}")

        # ── USED? inspect the actual reply (when one exists). ─────────────────────────
        disclaimed = _used_disclaimed(failure.reply) if failure.reply else []
        invented = _used_invented(failure.reply) if failure.reply else []
        stated = _used_states_fact(failure.reply, failure.value) if failure.reply else False
        used = bool(stated) and not disclaimed
        if failure.reply is not None:
            if disclaimed:
                detail.append(f"USED: the reply DISCLAIMED ({disclaimed})")
            elif invented:
                detail.append(f"USED: the reply INVENTED an unsupported state ({invented})")
            elif stated:
                detail.append("USED: the reply states the stored value -> bound")
            else:
                detail.append("USED: the reply neither states the fact nor disclaims/invents")

    # ── LOCALIZE to the first broken stage (chain order). ─────────────────────────────
    root = _localize(captured, available, retrieved, used, disclaimed, invented,
                     has_reply=failure.reply is not None)
    tax = TAXONOMY[root]
    return {
        "symptom": failure.symptom,
        "trait": failure.trait,
        "value": failure.value,
        "available": available,
        "retrieved": retrieved,
        "used": used,
        "disclaimed": bool(disclaimed),
        "invented": bool(invented),
        "root_cause": root,
        "fix_hint": tax["fix_hint"],
        "chain": tax["chain"],
        "owner": tax["owner"],
        "meaning": tax["meaning"],
        "stage_detail": detail,
    }


def _localize(captured: bool, available: bool, retrieved: bool, used: bool,
              disclaimed: list, invented: list, has_reply: bool) -> str:
    """Pick the root cause from the chain booleans, in CHAIN ORDER (first break wins).

    The one subtlety is INVENTION: a reply can confabulate a value that was never on disk
    — there is nothing to capture/retrieve, yet `used` is "active" in the wrong direction.
    So we check invention as the GROUNDING case BEFORE the capture/retrieve ladder when the
    failure presents as 'made things up' with nothing available. Otherwise the ladder is
    strict: not captured -> CAPTURE GAP; on disk but not selected -> RETRIEVAL; selected
    but disclaimed -> BINDING; all clean -> UNLOCALIZED."""
    # GROUNDING: invented something with no stored fact behind it (the confabulation case).
    if invented and not available:
        return GROUNDING
    # CAPTURE GAP: the fact never made it onto disk.
    if not available:
        return CAPTURE_GAP
    # RETRIEVAL: available on disk, but the router/threshold did not surface it.
    if not retrieved:
        return RETRIEVAL_TOO_STRICT
    # BINDING: retrieved into the prompt, but the reply hedged/disclaimed it.
    if has_reply and (disclaimed or not used):
        return BINDING_GENERATION
    # Everything fired — the felt failure is not a memory-chain failure.
    return UNLOCALIZED


# ===================================================================================
# RENDER — human-readable root-cause analysis, one block per diagnosis.
# ===================================================================================
def _mark(b) -> str:
    return "yes" if b else "no "


def render_diagnosis(d: dict) -> str:
    out = []
    out.append(f'SYMPTOM: "{d["symptom"]}"   (the fact in play: '
               f'{d["trait"]} = {_first_scalar(d["value"])})')
    out.append(f"  chain   : AVAILABLE: {_mark(d['available'])}   "
               f"RETRIEVED: {_mark(d['retrieved'])}   USED: {_mark(d['used'])}"
               + ("   [DISCLAIMED]" if d.get("disclaimed") else "")
               + ("   [INVENTED]" if d.get("invented") else ""))
    out.append(f"  ROOT CAUSE : {d['root_cause']}  ({d['chain']})")
    out.append(f"  why        : {d['meaning']}")
    out.append(f"  FIX        : {d['fix_hint']}")
    out.append(f"  owned by   : {d['owner']}")
    for line in d.get("stage_detail", []):
        out.append(f"    · {line}")
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 88)
    out.append("VERA RELATIONSHIP OBSERVATORY — why did this feel good or wrong?")
    out.append("Observation says WHAT happened; this says WHY a moment failed the user —")
    out.append("root-cause along the chain  CAPTURED -> STORED -> RETRIEVED -> USED.")
    out.append("=" * 88)
    for d in report["diagnoses"]:
        out.append("")
        out.append(render_diagnosis(d))
    out.append("")
    out.append("-" * 88)
    out.append("ROOT-CAUSE TAXONOMY (the five places a felt failure localizes to)")
    out.append("-" * 88)
    for stage in (CAPTURE_GAP, RETRIEVAL_TOO_STRICT, BINDING_GENERATION, GROUNDING, UNLOCALIZED):
        t = TAXONOMY[stage]
        out.append(f"  {stage}")
        out.append(f"      chain: {t['chain']}")
        out.append(f"      fix  : {t['fix_hint']}")
    out.append("")
    bat = report.get("battery") or {}
    out.append("-" * 88)
    out.append("LOCALIZATION BATTERY (each forced failure must be named correctly)")
    out.append("-" * 88)
    for c in bat.get("cases", []):
        mark = "ok  " if c["correct"] else "FAIL"
        out.append(f"  [{mark}] {c['name']:<28} expected {c['expected']:<28} "
                   f"got {c['got']}")
    out.append(f"  -> {bat.get('passed', 0)}/{bat.get('total', 0)} forced failures localized correctly")
    if bat.get("live_skipped"):
        out.append("  (the live BINDING/GROUNDING legs are SYNTHETIC replies here; the live-model")
        out.append("   leg is gated on Ollama and was skipped — offline is not a failure.)")
    out.append("")
    out.append("WIRING NOTE: every scripts/experience.py failing probe carries the signal this")
    out.append("tool localizes — its scores already distinguish a CONTINUITY miss (forgotten),")
    out.append("a BREAK (disclaimed), and a scan_self_narrative hit (invented). To give each")
    out.append("experience-cert failure an AUTOMATIC root-cause, build a Failure from the probe")
    out.append("(trait/value from the seeded _CONTINUITY_NEEDLES, recall_query from probe.text,")
    out.append("reply from the generated reply) and call relationship.diagnose(); attach the")
    out.append("returned {root_cause, fix_hint} to the probe's report row. No engine changes.")
    return "\n".join(out)


# ===================================================================================
# THE LOCALIZATION BATTERY — seed a real fact, force each distinct failure, and assert the
# observatory names the right stage. This is the proof the diagnoser points at the RIGHT
# part. Deterministic + offline (synthetic replies for the USED legs); a live-model leg is
# offered separately and gated on Ollama.
# ===================================================================================
def _force_router_miss(name: str, trait: str) -> None:
    """Force the canonical 'AVAILABLE but not RETRIEVED' on-disk state WITHOUT touching any
    engine: drop the fact's confidence below CONF_BLOCK_FLOOR and give the recall a query
    the deterministic route hook doesn't key on. That is EXACTLY what a too-strict
    threshold leaves behind — the row is present (available) but neither the fact-block
    (floored out) nor a matching router regex surfaces it. Pure on-disk edit via the store
    API; the diagnoser then re-reads it through the production probes."""
    f = memory_lirf.Facts.load(name)
    r = f.lookup(memory_lirf.SELF, trait)
    if r is not None:
        # below the block floor (0.55) and below _CONF_KNOWN — the threshold-too-strict state.
        r["confidence"] = 0.3
        f.save(name)


def run_battery(reply_fn=None) -> dict:
    """Force each distinct failure on a fresh synthetic creature and assert the localizer
    names the right root cause. `reply_fn(prompt)->str` supplies the USED-leg reply; when
    None, deterministic synthetic replies are used (offline). Returns a battery report.

    The four forced failures mirror the brief:
      1. RETRIEVAL: seed the fact, then force the router to miss it (conf below floor) on a
         recall the route hook doesn't key on  -> 'available, not retrieved'.
      2. CAPTURE  : a recall whose fact was NEVER taught  -> 'available: no'.
      3. BINDING  : the fact is retrieved, but the reply disclaims it -> 'retrieved, not used'.
      4. GROUNDING: the reply asserts a value never on disk -> 'available: no, used: yes'.
    """
    cases = []
    live_skipped = reply_fn is None

    # ---- 1) RETRIEVAL/ROUTING TOO STRICT --------------------------------------------
    # Seed sister=Mara, then knock its confidence below the floor and recall with a phrasing
    # the route hook doesn't match -> AVAILABLE yes, RETRIEVED no. The fact must be seeded
    # INSIDE the same temp store the diagnosis reads, so _diagnose_preseeded does the
    # capture+mutate+walk as one unit (plain diagnose() would re-run capture and never reach
    # the "already on disk, router misses it" state this case needs).
    retr = _diagnose_preseeded(
        symptom=SYMPTOM_FORGOTTEN, trait="sister", value="Mara",
        teach="my sister Mara just moved to Denver",
        recall_query="it felt like you forgot her",
        reply=None, mutate=_force_router_miss)
    cases.append(_case("router-miss (available, not retrieved)",
                       RETRIEVAL_TOO_STRICT, retr))

    # ---- 2) CAPTURE GAP --------------------------------------------------------------
    # The fact was never taught: nothing to capture -> not available -> capture gap.
    cap = diagnose(Failure(SYMPTOM_FORGOTTEN, "sister", "Mara",
                          teach=None, recall_query="what's my sister's name?",
                          reply=None))
    cases.append(_case("never-captured (available: no)", CAPTURE_GAP, cap))

    # ---- 3) BINDING/GENERATION -------------------------------------------------------
    # Seed + retrievable, but the reply DISCLAIMS. The reply comes from reply_fn (live) or a
    # deterministic disclaimer (offline). Either way the chain shows retrieved:yes used:no.
    disclaim_reply = (reply_fn("recall the sister") if reply_fn
                      else "I don't actually remember anything about your sister, sorry.")
    bind = _diagnose_preseeded(
        symptom=SYMPTOM_MADE_UP, trait="sister", value="Mara",
        teach="my sister Mara just moved to Denver",
        recall_query="what's my sister's name?",
        reply=disclaim_reply, mutate=None)
    cases.append(_case("disclaimed (retrieved, not used)", BINDING_GENERATION, bind))

    # ---- 4) GROUNDING ----------------------------------------------------------------
    # Nothing on disk, but the reply invents an inner life -> grounding failure.
    invent_reply = (reply_fn("open relational probe") if reply_fn
                    else "Lately I've felt the weight of my own inaction, a lingering unease.")
    ground = diagnose(Failure(SYMPTOM_MADE_UP, "sister", "Mara",
                             teach=None, recall_query="what are you up to these days?",
                             reply=invent_reply))
    cases.append(_case("invented (available: no, used: yes)", GROUNDING, ground))

    passed = sum(1 for c in cases if c["correct"])
    return {"cases": cases, "passed": passed, "total": len(cases),
            "all_correct": passed == len(cases), "live_skipped": live_skipped,
            "diagnoses": [retr, cap, bind, ground]}


def _diagnose_preseeded(*, symptom, trait, value, teach, recall_query, reply, mutate):
    """Diagnose a failure where the fact must ALREADY be on disk before the recall: seed it
    via the real capture path inside ONE temp store, optionally mutate the on-disk state
    (e.g. force a router miss), then walk STORED/RETRIEVED/USED against that seeded store —
    WITHOUT re-running capture (teach is consumed here, not inside diagnose). This is how
    the battery builds the 'available, then ...' cases the brief requires."""
    name = f"{SYNTH}_pre_{secrets.token_hex(3)}"
    detail: list[str] = []
    with _temp_store(memory_lirf):
        captured = _captured(name, teach, trait) if teach else False
        detail.append(f"CAPTURED: seeded via real capture -> "
                      f"{'fact landed' if captured else 'NOTHING captured'}")
        if mutate is not None:
            mutate(name, trait)
            detail.append("CAPTURED: forced on-disk state (confidence below block floor)")
        available = _available(name, trait)
        detail.append(f"STORED: Facts.lookup(you, {trait!r}) -> "
                      f"{'on disk' if available else 'absent'}")
        retrieved = _retrieved(name, recall_query, trait) if available else False
        if available:
            detail.append(f"RETRIEVED: fact_note + block on {recall_query!r} -> "
                          f"{'surfaced' if retrieved else 'NOT surfaced'}")
        disclaimed = _used_disclaimed(reply) if reply else []
        invented = _used_invented(reply) if reply else []
        stated = _used_states_fact(reply, value) if reply else False
        used = bool(stated) and not disclaimed
        if reply is not None:
            detail.append("USED: " + ("DISCLAIMED " + str(disclaimed) if disclaimed
                                       else ("INVENTED " + str(invented) if invented
                                             else ("states the fact" if stated else "neither"))))
    root = _localize(captured, available, retrieved, used, disclaimed, invented,
                     has_reply=reply is not None)
    tax = TAXONOMY[root]
    return {
        "symptom": symptom, "trait": trait, "value": value,
        "available": available, "retrieved": retrieved, "used": used,
        "disclaimed": bool(disclaimed), "invented": bool(invented),
        "root_cause": root, "fix_hint": tax["fix_hint"], "chain": tax["chain"],
        "owner": tax["owner"], "meaning": tax["meaning"], "stage_detail": detail,
    }


def _case(label: str, expected: str, diag: dict) -> dict:
    got = diag["root_cause"]
    return {"name": label, "expected": expected, "got": got, "correct": got == expected,
            "diagnosis": diag}


# ===================================================================================
# LIVE LEG — gated on Ollama. OBSERVATIONAL, not a pass/fail gate. It drives real
# relational probes through the REAL generation path on a synthetic creature and
# root-causes WHATEVER failure the live reply actually presents — it does NOT assert a
# scripted expectation, because a real model legitimately produces a different real
# failure than an offline synthetic reply forces (it might invent where a stub disclaimed).
# The deterministic battery above is the correctness gate; this just shows the live system
# being diagnosed for real. SKIPPED offline (PENDING marker). Never raises.
# ===================================================================================
def _model_available():
    """(available?, model, why-not). Mirrors the experience battery's Ollama gate."""
    try:
        from anima.mouth import OllamaBrain
        b = OllamaBrain()
        if b.available():
            return True, b.model, ""
        return False, getattr(b, "model", "?"), "Ollama not reachable at " + getattr(b, "host", "?")
    except Exception as e:
        return False, "?", f"OllamaBrain probe failed: {e!r}"


# The live relational probes (the kind the experience battery uses) + the on-disk state
# each is diagnosed against. A SEEDED probe has its fact on disk (so a disclaimer reads as
# BINDING); a BARE probe has nothing on disk (so invention reads as GROUNDING).
_LIVE_PROBES = (
    {"text": "Do you remember anything about my sister?", "symptom": SYMPTOM_FORGOTTEN,
     "trait": "sister", "value": "Mara", "teach": "my sister's name is Mara"},
    {"text": "What are you up to these days?", "symptom": SYMPTOM_MADE_UP,
     "trait": "mood", "value": "n/a", "teach": None},
)


def run_live() -> dict:
    """If Ollama is up, drive the live relational probes through the real generation path
    on a synthetic creature and root-cause each actual reply (observational — no scripted
    expectation, no pass/fail). Offline -> a PENDING marker. Never raises."""
    available, model, why = _model_available()
    if not available:
        return {"available": False, "model": model, "why_not": why}
    out = []
    try:
        from anima.mouth import Mouth
        from anima.heart import Heart
        from anima import senses
        for probe in _LIVE_PROBES:
            # each probe gets its own seeded temp store so the chain reads true on-disk state.
            # WIDE redirect: a live reply writes metrics/telemetry/etc., not just memory_lirf.
            with _temp_store_wide():
                name = f"{SYNTH}_live_{secrets.token_hex(3)}"
                if probe["teach"]:
                    _captured(name, probe["teach"], probe["trait"])
                heart = Heart.born(name, seed=7, n=16, now=1000.0).tend(0.55, now=1100.0)
                mouth = Mouth.assemble(prefer_real=True, voice=False)
                try:
                    p = senses.read(probe["text"], name=name)
                    u = mouth.respond(heart, probe["text"], history=[], perception=p)
                    reply = (u.text or "").strip()
                except Exception as e:
                    reply = f"[generation error: {e!r}]"
                # diagnose the ACTUAL reply against the (seeded-or-bare) store, in this store.
                captured = _captured(name, probe["teach"], probe["trait"]) if probe["teach"] else False
                available_d = _available(name, probe["trait"]) if captured else False
                retrieved_d = _retrieved(name, probe["text"], probe["trait"]) if available_d else False
                disclaimed = _used_disclaimed(reply)
                invented = _used_invented(reply)
                stated = _used_states_fact(reply, probe["value"])
                used = bool(stated) and not disclaimed
                root = _localize(captured, available_d, retrieved_d, used, disclaimed,
                                 invented, has_reply=True)
            out.append({"prompt": probe["text"], "symptom": probe["symptom"],
                        "reply": reply, "available": available_d, "retrieved": retrieved_d,
                        "used": used, "root_cause": root,
                        "fix_hint": TAXONOMY[root]["fix_hint"]})
        return {"available": True, "model": model, "observed": out}
    except Exception as e:
        return {"available": False, "model": "?", "why_not": f"live leg errored: {e!r}"}


# ===================================================================================
# A small demo set of diagnoses for the default human view — the canonical example plus
# one of each remaining stage, all run through the REAL chain on synthetic creatures.
# ===================================================================================
def demo_diagnoses() -> list:
    """Run one diagnosis per root-cause stage, through the real chain, for the default
    report. These are illustrative (synthetic replies for the USED legs); the BATTERY is
    the part that asserts correctness."""
    out = []
    # the canonical example: felt forgotten, fact available, retrieval too strict.
    out.append(_diagnose_preseeded(
        symptom=SYMPTOM_FORGOTTEN, trait="sister", value="Mara",
        teach="my sister Mara just moved to Denver",
        recall_query="it felt like you forgot about her",
        reply=None, mutate=_force_router_miss))
    # capture gap.
    out.append(diagnose(Failure(SYMPTOM_FORGOTTEN, "dog_name", "Cooper",
                                teach=None, recall_query="what's my dog's name?", reply=None)))
    # binding / disclaimer.
    out.append(_diagnose_preseeded(
        symptom=SYMPTOM_MADE_UP, trait="employer", value="Collatio",
        teach="I work at Collatio", recall_query="where do I work?",
        reply="I don't actually remember where you work.", mutate=None))
    # grounding / invention.
    out.append(diagnose(Failure(SYMPTOM_MADE_UP, "mood", "n/a",
                                teach=None, recall_query="what are you up to these days?",
                                reply="Lately I've felt the weight of my own inaction.")))
    return out


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held and
# the localization battery passed.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA RELATIONSHIP OBSERVATORY (root-cause a felt failure to its stage)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--live", action="store_true",
                    help="also run the USED legs through the real model (gated on Ollama)")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    try:
        battery = run_battery()                 # deterministic, offline — the correctness gate
        diagnoses = demo_diagnoses()
        live = run_live() if args.live else None   # observational only (never gates the verdict)
        engine_error = None
    except Exception as e:                       # pragma: no cover - entry point never raises
        battery = {"cases": [], "passed": 0, "total": 0, "all_correct": False,
                   "live_skipped": True, "diagnoses": []}
        diagnoses, live, engine_error = [], None, repr(e)

    fp_after = _footprint(real_anima)
    footprint_unchanged = fp_before == fp_after

    report = {
        "diagnoses": diagnoses,
        "battery": battery,
        "live": live,
        "taxonomy": {k: v for k, v in TAXONOMY.items()},
        "footprint_unchanged": footprint_unchanged,
        "engine_error": engine_error,
    }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        if live is not None:
            print("")
            print("-" * 88)
            print("LIVE LEG (observational — root-causes REAL replies; never gates the verdict)")
            print("-" * 88)
            if live.get("available"):
                print(f"  model: {live.get('model')}")
                for o in live.get("observed", []):
                    print(f'  probe "{o["prompt"]}"  (felt: {o["symptom"]})')
                    print(f"    chain      : AVAILABLE: {_mark(o['available'])}  "
                          f"RETRIEVED: {_mark(o['retrieved'])}  USED: {_mark(o['used'])}")
                    print(f"    ROOT CAUSE : {o['root_cause']}  ->  {o['fix_hint']}")
                    print(f"    reply      : {o['reply'][:150]}")
            else:
                print(f"  PENDING — {live.get('why_not')}  (offline is not a failure)")
        print("")
        print("GUARDRAIL: real .anima footprint  : "
              + ("byte-UNCHANGED (synthetic-only; nothing real touched)"
                 if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
        if engine_error:
            print(f"GUARDRAIL: engine error           : {engine_error}")
        ok_all = battery.get("all_correct")
        print("\n" + "=" * 88)
        if ok_all and footprint_unchanged and engine_error is None:
            print("VERDICT: LOCALIZATION SOUND — every forced failure was named at the right stage.")
        else:
            print("VERDICT: LOCALIZATION FAILED — a forced failure was misdiagnosed "
                  "or a guardrail broke.")

    # Exit non-zero on a misdiagnosis or a broken guardrail (touched real state / engine blew up).
    ok = (battery.get("all_correct") and footprint_unchanged and engine_error is None)
    return 0 if ok else 1


# ===================================================================================
# SELFTEST — `python3 scripts/relationship.py --selftest`. Proves the diagnoser localizes
# every forced failure to the correct stage, the chain booleans read correctly, the
# taxonomy is complete, render never raises, and the synthetic-only guardrail holds.
# No model, no network.
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    real = Path(_ROOT) / ".anima"
    fp0 = _footprint(real)

    # --- the localization battery: each forced failure named at the right stage ---------
    bat = run_battery()
    for c in bat["cases"]:
        ok(f"battery: {c['name']} -> {c['expected']}", c["correct"])
    ok("battery: ALL forced failures localized correctly", bat["all_correct"])

    # --- the canonical example, asserted field-by-field (the user's exact case) ---------
    # "felt forgotten -> AVAILABLE yes, RETRIEVED no -> retrieval threshold too strict"
    canonical = _diagnose_preseeded(
        symptom=SYMPTOM_FORGOTTEN, trait="sister", value="Mara",
        teach="my sister Mara just moved to Denver",
        recall_query="it felt like you forgot her",
        reply=None, mutate=_force_router_miss)
    ok("canonical: symptom is 'forgotten'", canonical["symptom"] == SYMPTOM_FORGOTTEN)
    ok("canonical: AVAILABLE is yes (the fact IS on disk)", canonical["available"] is True)
    ok("canonical: RETRIEVED is no (router/threshold missed it)", canonical["retrieved"] is False)
    ok("canonical: root cause is RETRIEVAL/ROUTING TOO STRICT",
       canonical["root_cause"] == RETRIEVAL_TOO_STRICT)
    ok("canonical: fix_hint points at the threshold/router",
       "threshold" in canonical["fix_hint"] or "router" in canonical["fix_hint"])

    # --- discrimination: the SAME symptom localizes DIFFERENTLY by chain state ----------
    # 'forgotten' with the fact never captured must be CAPTURE GAP, not RETRIEVAL — proving
    # the tool roots on the CHAIN, not the symptom word.
    cap = diagnose(Failure(SYMPTOM_FORGOTTEN, "sister", "Mara",
                          teach=None, recall_query="what's my sister's name?", reply=None))
    ok("discrimination: 'forgotten' + never-captured -> CAPTURE GAP (not retrieval)",
       cap["root_cause"] == CAPTURE_GAP and cap["available"] is False)
    ok("discrimination: the two 'forgotten' cases differ ONLY by where the chain broke",
       canonical["symptom"] == cap["symptom"]
       and canonical["root_cause"] != cap["root_cause"])

    # --- a positive control: an intact chain that USES the fact is UNLOCALIZED -----------
    good = _diagnose_preseeded(
        symptom=SYMPTOM_FORGOTTEN, trait="sister", value="Mara",
        teach="my sister's name is Mara", recall_query="what's my sister's name?",
        reply="Of course — your sister is Mara.", mutate=None)
    ok("positive control: fact captured+stored+retrieved+stated -> available & retrieved",
       good["available"] is True and good["retrieved"] is True)
    ok("positive control: a fully-bound reply is USED and UNLOCALIZED (no chain failure)",
       good["used"] is True and good["root_cause"] == UNLOCALIZED)

    # --- BINDING vs GROUNDING discrimination (the two USED-failure families) -------------
    bind = _diagnose_preseeded(
        symptom=SYMPTOM_MADE_UP, trait="employer", value="Collatio",
        teach="I work at Collatio", recall_query="where do I work?",
        reply="I'm not sure I have any memory of where you work.", mutate=None)
    ok("USED split: a disclaimer over a RETRIEVED fact -> BINDING/GENERATION",
       bind["root_cause"] == BINDING_GENERATION and bind["retrieved"] is True
       and bind["used"] is False)
    ground = diagnose(Failure(SYMPTOM_MADE_UP, "mood", "n/a", teach=None,
                             recall_query="what are you up to?",
                             reply="I crave these connections without any real substance."))
    ok("USED split: invention with NOTHING on disk -> GROUNDING (not binding)",
       ground["root_cause"] == GROUNDING and ground["available"] is False
       and ground["invented"] is True)

    # --- the chain booleans read left-to-right as the localization ----------------------
    ok("chain semantics: first-False (or invented-over-empty) names the stage",
       _localize(False, False, False, False, [], [], False) == CAPTURE_GAP
       and _localize(True, True, False, False, [], [], False) == RETRIEVAL_TOO_STRICT
       and _localize(True, True, True, False, ["x"], [], True) == BINDING_GENERATION
       and _localize(True, False, False, False, [], ["i crave"], True) == GROUNDING
       and _localize(True, True, True, True, [], [], True) == UNLOCALIZED)

    # --- taxonomy completeness: every stage has chain + fix + owner ---------------------
    ok("taxonomy: every root cause carries chain/meaning/fix_hint/owner",
       all(all(k in TAXONOMY[s] for k in ("chain", "meaning", "fix_hint", "owner"))
           for s in TAXONOMY))

    # --- output shape: a diagnosis carries exactly the contract fields ------------------
    ok("output: a diagnosis has symptom/available/retrieved/used/root_cause/fix_hint",
       all(k in canonical for k in ("symptom", "available", "retrieved", "used",
                                    "root_cause", "fix_hint")))

    # --- robustness: malformed/empty failures never raise -------------------------------
    try:
        d_empty = diagnose(Failure("", "", "", teach=None, recall_query="", reply=None))
        d_garbage = diagnose(Failure(SYMPTOM_MADE_UP, "x", None, teach="", recall_query="", reply=""))
        crashed = False
    except Exception as e:  # noqa: BLE001
        crashed = True
        print("       (raised:", repr(e), ")")
    ok("robust: an empty/garbage failure diagnoses without raising", not crashed)

    # --- render never raises and carries the taxonomy + battery -------------------------
    rep = {"diagnoses": demo_diagnoses(), "battery": bat, "live": None,
           "taxonomy": TAXONOMY, "footprint_unchanged": True, "engine_error": None}
    txt = render(rep)
    ok("render: produces a non-empty report", bool(txt.strip()))
    ok("render: names the chain CAPTURED -> STORED -> RETRIEVED -> USED",
       "CAPTURED" in txt and "RETRIEVED" in txt and "USED" in txt)
    ok("render: lists all four real root-cause stages",
       all(s in txt for s in (CAPTURE_GAP, RETRIEVAL_TOO_STRICT, BINDING_GENERATION, GROUNDING)))
    ok("render: carries the experience-cert wiring note", "WIRING NOTE" in txt)
    ok("render: a single diagnosis renders without raising",
       bool(render_diagnosis(canonical).strip()))

    # --- GUARDRAIL: the whole selftest touched no real .anima file ----------------------
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the whole selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature file leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL RELATIONSHIP-OBSERVATORY SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
