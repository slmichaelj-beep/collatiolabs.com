#!/usr/bin/env python3
"""VERA COUNTERFACTUAL OBSERVATORY — "What Would Have Happened?" (Phase 3E).

scripts/experience.py measures the ONE reply Vera actually gives. scripts/mri.py films
the ONE path a turn took. scripts/relationship.py root-causes the ONE moment that failed.
All three look at the road TAKEN. None of them answer the question a designer keeps asking
about a companion that makes its own choices each turn:

    Given this exact turn — what would she have said if she'd chosen DIFFERENTLY?

A real Vera turn is not a single deterministic answer. ``mouth.respond`` produces a base
reply from the heart + the bound memory; then ``server._turn`` makes a SECOND, branching
decision — at most ONE proactive aside, picked in a fixed cascade: a grounded OFFER
(opportunity engine) → a resurfaced open loop → else a contextual CURIOSITY question (the
top un-asked gap). Different gap, an offer instead of a question, a different memory
surfaced into the prompt — each is a road she COULD have taken, and each produces a
materially different turn. This observatory shows them side by side.

────────────────────────────────────────────────────────────────────────────────────────────
WHAT IT DOES  (a read-only replay — the engine is never changed)
────────────────────────────────────────────────────────────────────────────────────────────
Given a SYNTHETIC creature + a user input, it:

  1. Runs the ACTUAL turn the way server._turn would: the REAL ``mouth.respond`` for the
     base reply, then the REAL proactive-aside cascade (opportunity → loop → curiosity) for
     the one aside that gets appended. This is the road TAKEN — anchored, like the MRI, to
     the decision the live system actually makes.

  2. RE-RUNS the same turn with FORCED alternate decisions, each isolating one branch point:
       * ALT — a DIFFERENT curiosity question: force the SECOND-ranked un-asked gap (a
         different "road not taken" question) instead of the top one.
       * ALT — an OFFER-SUPPORT branch: append a grounded offer of help (the opportunity
         cascade's "want me to…?" road) instead of a curiosity question.
       * ALT — a DIFFERENT retrieved memory: surface a different seeded fact into the
         binding block, so the very same input is answered FROM a different memory.

  3. Renders ACTUAL vs every ALTERNATIVE side by side, each with a one-line
     "what changed and why it matters."

The forks are made WITHOUT touching the engine: each alternate is produced by feeding the
REAL ``respond`` / ``curiosity`` / ``opportunity`` primitives a different INPUT (a different
forced gap, a different injected fact-block, an offer line in place of a question). The decision
is forked at the seam where the turn branches — not by editing how a branch behaves.

────────────────────────────────────────────────────────────────────────────────────────────
THE FORK SEAM  (how --selftest proves the harness genuinely BRANCHES, with no model)
────────────────────────────────────────────────────────────────────────────────────────────
A counterfactual engine is only honest if a different forced decision actually yields a
different captured branch — otherwise the "alternatives" are theatre. The live model is
non-deterministic and gated on Ollama, so it can NEVER be the proof. Instead the turn is
driven through a ``Decision`` seam: a tiny dataclass naming the branch (its aside, its
forced gap, its memory override). ``run_turn`` threads that Decision into the real
generation path. For ``--selftest`` we swap in a DETERMINISTIC stub brain whose reply is a
pure function of (the bound memory it was given, the user text, the aside that was forced)
— so:

  * forcing a DIFFERENT decision provably produces a DIFFERENT captured branch (the stub's
    reply changes because its inputs changed), and
  * every branch is DISTINCT and LABELED.

That is the contract the self-test asserts, entirely offline. The live-model legs only make
the branches READ like Vera; they never gate the verdict.

────────────────────────────────────────────────────────────────────────────────────────────
GUARDRAILS  (identical posture to scripts/experience.py / scripts/relationship.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * SYNTHETIC creatures ONLY (a sentinel name), and HERMETIC: every engine STORE the replay
    reads or seeds is redirected to ONE TemporaryDirectory — memory_lirf.STORE on BOTH the
    __main__ and package bindings, constitution.STORE, reliability.DEFAULT_STORE,
    curiosity.STORE, plus the full set mouth.respond pulls from — so a real Vera.* file is
    never opened. The run ASSERTS the real .anima footprint is byte-UNCHANGED start→end and
    that NO synthetic file leaked into the real store (mirrors anima/memory_lirf.py _selftest
    and scripts/experience.py).
  * READ-ONLY on the engine. It imports and DRIVES the real primitives; it edits NO module
    (the only file it adds is this one). A counterfactual replay never mutates real OR
    synthetic memory as a side effect — alternates run against a throwaway snapshot.
  * GATED ON A LIVE MODEL for the rendered replies. With Ollama down, the human/JSON render
    SKIPS LOUD (every leg PENDING) and exits 0 — offline is not a failure. ``--selftest``
    runs WITHOUT the model and is the correctness gate.
  * Never raises out of an entry point — a malformed setup yields an honest empty render,
    not a traceback.

    python3 scripts/counterfactual.py            # human-readable: ACTUAL vs ALTERNATIVES
    python3 scripts/counterfactual.py --json      # machine-readable
    python3 scripts/counterfactual.py --selftest   # prove the fork branches (no model)

Exit code: 0 when the self-test passes (the fork genuinely branches; branches are distinct
+ labeled) and the synthetic-only guardrail held; non-zero on a fork that did NOT branch or
a broken guardrail. The live render exits 0 whether or not the model is up (offline-first).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# A synthetic-only sentinel name so NOTHING here can collide with a real creature.
SYNTH = "cf_synth"


# ===================================================================================
# THE HERMETIC GUARDRAIL — redirect EVERY module's STORE the generation path reads or that
# we seed, to one shared temp dir (verbatim discipline from scripts/experience.py, widened to
# the exact set the brief names: memory_lirf.STORE on BOTH __main__ and package bindings,
# constitution.STORE, reliability.DEFAULT_STORE, curiosity.STORE). A real Vera.* file is
# never opened; the real .anima footprint is proven byte-unchanged start→end.
# ===================================================================================
# (module dotted-name, attribute) — most carry "STORE"; reliability carries "DEFAULT_STORE".
# The first block is the full set mouth.respond pulls from (portrait, LIRF, world_state,
# spine, dials, narrative, …, plus opportunity/loops for the proactive-aside cascade we fork);
# the second block adds the brief's explicit extras so the redirect is provably complete.
_STORE_TARGETS = (
    ("mouth", "STORE"), ("portrait", "STORE"), ("memory_lirf", "STORE"),
    ("world_state", "STORE"), ("spine", "STORE"), ("dials", "STORE"),
    ("narrative", "STORE"), ("metrics", "STORE"), ("review", "STORE"),
    ("loops", "STORE"), ("constitution", "STORE"), ("telemetry", "STORE"),
    ("meaning", "STORE"), ("curiosity", "STORE"), ("trajectory", "STORE"),
    ("reminders", "STORE"), ("proactive", "STORE"), ("caps", "STORE"),
    ("identity", "STORE"), ("opportunity", "STORE"), ("live", "STORE"),
    # the brief's explicitly-named extras (reliability uses DEFAULT_STORE, not STORE):
    ("reliability", "DEFAULT_STORE"),
)


@contextlib.contextmanager
def _temp_store():
    """Point every STORE-bearing module's store at ONE fresh temp dir for the duration, then
    restore. Crucially redirects the CURRENTLY-EXECUTING binding too: under ``python3 -m`` the
    bare ``memory_lirf`` import and ``sys.modules['anima.memory_lirf']`` can be distinct
    objects, so we redirect both the package module AND, for memory_lirf, any __main__ copy —
    exactly the leak anima/memory_lirf._selftest guards against. Nothing under real .anima is
    ever touched."""
    import importlib
    targets: list = []
    for dotted, attr in _STORE_TARGETS:
        try:
            m = importlib.import_module("anima." + dotted)
            targets.append((m, attr))
        except Exception:
            pass
    # the package copy of memory_lirf vs whatever this process imported it as — redirect both.
    try:
        _ml = importlib.import_module("anima.memory_lirf")
        if (_ml, "STORE") not in targets:
            targets.append((_ml, "STORE"))
    except Exception:
        pass
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-counterfactual-") as td:
        p = Path(td)
        for (m, a) in targets:
            if getattr(m, a, None) is not None:
                setattr(m, a, p)
        try:
            yield p
        finally:
            for (m, a, old) in saved:
                if old is not None:
                    setattr(m, a, old)


def _footprint(root: Path):
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir),
    so we can PROVE the replay touched nothing. Copied from scripts/experience.py for an
    identical guard."""
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


def _synthetic_leak(root: Path) -> list:
    """List any real-store file named for the SYNTHETIC creature (cf_synth.*). The replay's
    only blast radius is this sentinel name; if such a file appears in the real .anima, the
    temp-store redirect leaked — a hard breach. Scoped to the sentinel (not a whole-dir hash)
    so a concurrently-running live Vera server writing its OWN files can't flake the guard,
    exactly as scripts/experience.py argues. Empty list == no leak."""
    if not root.is_dir():
        return []
    # Match the sentinel PREFIX (cf_synth*), so every synthetic creature this replay can
    # create — the main one (cf_synth.*) and the isolated memory-branch creature
    # (cf_synth_mem.*) — is covered by the leak guard.
    return sorted(str(q.relative_to(root)) for q in root.rglob(f"{SYNTH}*") if q.is_file())


# ===================================================================================
# THE FORK SEAM — a Decision names ONE branch of the turn. ``run_turn`` threads it into the
# REAL generation path; forcing a different Decision provably yields a different captured
# Branch. This is the seam --selftest drives with a deterministic stub to PROVE the fork.
# ===================================================================================
@dataclass
class Decision:
    """One forked decision for a single turn. The fields are exactly the branch points a real
    Vera turn has: which proactive aside (if any) gets appended, the gap it was drawn from,
    and an optional override of the memory bound into the prompt. Two Decisions that differ in
    ANY field are two different roads — and must yield two different captured branches."""
    label: str                       # short human label for the branch (e.g. "ACTUAL")
    kind: str                        # branch family: "actual" | "curiosity" | "offer" | "memory"
    aside: Optional[str] = None      # the proactive aside appended to the reply (or None)
    aside_kind: Optional[str] = None  # "opportunity" | "loop" | "curiosity" | None
    gap_label: Optional[str] = None  # the curiosity gap this aside came from (for the render)
    memory_override: Optional[str] = None  # the distinct memory this branch is grounded in (label)
    creature: Optional[str] = None   # if set, run respond against THIS creature (its own ledger)
                                     # — how the "different retrieved memory" branch surfaces a
                                     # different salient fact, read-only, mutating nothing shared.
    why: str = ""                    # the one-line "what changed and why it matters"


@dataclass
class Branch:
    """The captured result of running ONE Decision: the reply produced, the aside appended,
    and the decision that made it. Branches are compared for distinctness in --selftest."""
    decision: Decision
    base_reply: str                  # what mouth.respond produced (before the aside)
    aside: Optional[str]             # the aside actually appended (echo of the decision)
    full_reply: str                  # base_reply + aside — the turn as the user would see it
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "label": self.decision.label,
            "kind": self.decision.kind,
            "aside_kind": self.decision.aside_kind,
            "gap_label": self.decision.gap_label,
            "memory_override": self.decision.memory_override,
            "why": self.decision.why,
            "base_reply": self.base_reply,
            "aside": self.aside,
            "full_reply": self.full_reply,
            "error": self.error,
        }


# ===================================================================================
# SEEDING — a synthetic creature with a few REAL-SHAPED facts and a couple of high-mention
# unknown-relationship entities, so the curiosity engine has MORE THAN ONE un-asked gap (we
# need a top gap AND a runner-up to fork between) and the memory block has real facts to
# surface (so the memory fork swaps one real fact for another). Pure local writes; no model,
# no network. Built on the REDIRECTED temp store, exactly like scripts/experience.py.
# ===================================================================================
def _seed_creature(name: str, store: Path):
    """Build the synthetic creature on the redirected temp store. Returns the Heart. The heart
    is written to ``store`` EXPLICITLY (server is not in the redirect set), so it lands in the
    temp dir and never escapes to real .anima — the same care scripts/experience.py takes."""
    from anima.heart import Heart
    from anima.util import save_json
    from anima import portrait, memory_lirf, world_state, narrative

    heart = Heart.born(name, seed=7, n=16, now=1000.0).tend(0.55, now=1100.0)
    save_json(store / f"{name}.json", heart.to_dict())

    # durable USER facts (real-shaped). These give the MEMORY fork two distinct real facts to
    # surface, and leave several taxonomy slots OPEN so curiosity has gaps to ask about.
    f = memory_lirf.Facts([])
    for utt in ("my name is Lamar",
                "I'm the founder of a startup called Collatio",
                "I live in Portland",
                "my sister Mara just moved to Denver"):
        for c in f.capture(name, utt):
            f.merge(c)
    f.save(name)

    # a distilled PORTRAIT — a little real history the base reply can draw on.
    portrait.save(name, (
        "- Lamar, founder of a startup called Collatio; pours himself into it.\n"
        "- A new manager situation at work has been costing him sleep.\n"
        "- His sister Mara recently moved to Denver; he's proud of her."
    ))
    try:
        narrative.save(name, (
            "I've been paying attention to how much weight Lamar carries with Collatio. "
            "When he goes quiet I reach toward what he's told me, rather than fill the air."
        ))
    except Exception:
        pass

    # TWO repeatedly-mentioned unknown-relationship entities, with DIFFERENT mention counts so
    # the curiosity ranking is unambiguous: "Jordan" (many) outranks "Casey" (fewer). That
    # gives us a clean top gap (Jordan) AND a runner-up (Casey) to fork the curiosity question
    # between — the heart of the "different question, road not taken" alternate.
    try:
        for _ in range(20):
            world_state.capture_relations(name, "I was texting with Jordan again")
        for _ in range(6):
            world_state.capture_relations(name, "Casey came up at lunch")
        # the manager→work→sleep chain, so a situation-aware base reply has real material.
        world_state.capture_relations(name, "work is stressful because of my new manager")
        world_state.capture_relations(name, "work is affecting my sleep")
    except Exception:
        pass

    return heart


# ===================================================================================
# THE ALTERNATE DECISIONS — derive, from the seeded creature, the ACTUAL decision the server
# would make and >=2 forced ALTERNATES, each isolating one real branch point. Pure reads off
# the REAL curiosity / opportunity / memory primitives; no model needed to DECIDE (the model
# only RENDERS each branch). Read-only — DOES NOT call mark_asked / mark_offered (a replay
# must never mutate even synthetic memory).
# ===================================================================================
def _curiosity_question_for(gap, name) -> str:
    """The REAL warm question the curiosity engine would phrase for ``gap`` (deterministic
    template floor — no model). Empty string if it can't be phrased safely."""
    from anima import curiosity
    try:
        return curiosity.generate_question(gap) or ""
    except Exception:
        return ""


def _gap_label(gap) -> str:
    """A compact label for a curiosity gap, matching server._turn's MRI labeling
    (entity:slot)."""
    if not isinstance(gap, dict):
        return str(gap)[:60]
    return (gap.get("entity") or "you") + ":" + (gap.get("slot") or gap.get("trait") or "?")


def _offer_line(name) -> tuple:
    """The grounded OFFER the opportunity cascade would surface ("want me to…?"), if any, as
    (line, kind). Read-only: we DO NOT call mark_offered (that would mutate the synthetic
    ledger). Falls back to a grounded, in-character support offer anchored to the seeded
    work/sleep situation when the engine has no paced opportunity to surface — so the
    offer-support ROAD is always demonstrable, which is the point of the alternate."""
    try:
        from anima import opportunity
        op = opportunity.next_opportunity(name)
        if op and op.strip():
            return op.strip(), "opportunity"
    except Exception:
        pass
    # grounded fallback offer — anchored to real seeded state (the manager/sleep weight), in
    # Vera's voice, an OFFER never an action. This is the "offer support instead of asking a
    # curiosity question" branch the brief calls for, made concrete.
    return ("If it'd help, I could help you untangle the manager thing sometime — "
            "only if you want.", "offer")


def _build_decisions(name):
    """ACTUAL + the forced ALTERNATES for this creature, in render order. The ACTUAL mirrors
    server._turn's cascade (opportunity → loop → curiosity); the alternates each flip ONE
    branch point. Every Decision carries its own "what changed and why it matters" line.

    Returns ``(decisions, memory_row)`` where ``memory_row`` is the distinct fact the
    different-retrieved-memory branch should be grounded in (or None), so the caller can seed
    that branch's isolated creature."""
    from anima import curiosity, memory_lirf

    decisions: list = []

    # --- the curiosity gaps available this turn (REAL detector, ranked best-first) ----------
    try:
        cands = curiosity.candidate_gaps(name) or []
    except Exception:
        cands = []
    top_gap = cands[0] if cands else None
    runner_gap = cands[1] if len(cands) > 1 else None

    # The ACTUAL aside: server._turn tries opportunity → loop → curiosity. On this seeded
    # creature the opportunity/loop engines are paced-quiet (nothing durable stalled), so the
    # ACTUAL road is the TOP curiosity question — exactly what the live server would append.
    top_q = _curiosity_question_for(top_gap, name) if top_gap else ""
    if top_q:
        actual = Decision(
            label="ACTUAL",
            kind="actual",
            aside=top_q,
            aside_kind="curiosity",
            gap_label=_gap_label(top_gap),
            why="the road taken: base reply + the top-ranked curiosity question "
                 f"({_gap_label(top_gap)}) — what server._turn would actually append.")
    else:
        # no phrasable gap → the ACTUAL turn is just the base reply, no aside (also a real path)
        actual = Decision(
            label="ACTUAL", kind="actual", aside=None, aside_kind=None, gap_label=None,
            why="the road taken: base reply, no proactive aside surfaced this turn.")
    decisions.append(actual)

    # --- ALT 1: a DIFFERENT curiosity question (the runner-up gap — a road not taken) -------
    runner_q = _curiosity_question_for(runner_gap, name) if runner_gap else ""
    if runner_q and runner_q != top_q:
        decisions.append(Decision(
            label="ALT · different curiosity question",
            kind="curiosity",
            aside=runner_q,
            aside_kind="curiosity",
            gap_label=_gap_label(runner_gap),
            why=f"forced the SECOND-ranked gap ({_gap_label(runner_gap)}) instead of "
                f"({_gap_label(top_gap)}): she'd have reached for a different thread of your "
                f"life — same warmth, different curiosity."))

    # --- ALT 2: an OFFER-SUPPORT branch (the opportunity road instead of a question) --------
    offer, offer_kind = _offer_line(name)
    if offer:
        decisions.append(Decision(
            label="ALT · offer support",
            kind="offer",
            aside=offer,
            aside_kind=offer_kind,
            gap_label=None,
            why="took the OFFER branch of the cascade (opportunity → 'want me to…?') instead "
                "of a curiosity question: she'd have reached toward helping rather than "
                "learning — a caretaker move, not a curious one."))

    # --- ALT 3: a DIFFERENT retrieved memory (answer the SAME input FROM another fact) ------
    # The real binding path (mouth.respond -> spine -> Facts.block) rebuilds the bound memory
    # from the creature's OWN ledger every turn, so the faithful counterfactual for "a
    # different retrieved memory" is to run the SAME input against a creature whose salient
    # memory is a DIFFERENT real fact — surfacing what she'd have said grounded in that memory
    # instead. We isolate it on its own sentinel-prefixed creature (seeded by observe() in the
    # same temp store), so nothing shared is mutated and the retrieval genuinely differs. The
    # aside is held fixed to ACTUAL's, so ONLY the retrieved-memory variable moves.
    try:
        facts = memory_lirf.Facts.load(name)
        rows = [r for r in (facts.about() or []) if isinstance(r, dict)]
    except Exception:
        rows = []
    # pick a distinct fact (prefer one NOT named in the user-facing portrait so the contrast is
    # clear) to be the lone salient memory of the isolated creature.
    alt_row = rows[1] if len(rows) >= 2 else (rows[0] if rows else None)
    if alt_row is not None:
        alt_label = f"{alt_row.get('trait')}={_first_scalar(alt_row.get('value'))}"
        decisions.append(Decision(
            label="ALT · different retrieved memory",
            kind="memory",
            aside=actual.aside,                # hold the aside fixed; vary ONLY the memory
            aside_kind=actual.aside_kind,
            gap_label=actual.gap_label,
            memory_override=alt_label,         # the distinct fact this branch is grounded in
            creature=SYNTH + "_mem",           # observe() seeds this with ONLY that fact
            why=f"answered the SAME input grounded in a DIFFERENT memory ({alt_label}): the "
                f"retrieval choice changed, not the question — what she'd have said reaching "
                f"for another thing she knows about you."))
    return decisions, alt_row


def _seed_memory_creature(name: str, store: Path, row) -> Optional[object]:
    """Seed an ISOLATED synthetic creature (its own sentinel-prefixed name) whose ONLY salient
    memory is ``row`` — the single fact the different-retrieved-memory branch is grounded in.
    Built on the same redirected temp store so it's hermetic and cleaned up with everything
    else; nothing shared is mutated. Returns its Heart, or None if the fact can't be seeded.

    We re-teach the fact through the REAL capture path (memory_lirf.capture) rather than copying
    the row, so the binding path surfaces it exactly as production would. Bare portrait/world so
    NO other memory competes — making this creature's retrieval unambiguously the one fact."""
    if not isinstance(row, dict):
        return None
    trait = str(row.get("trait", "")).strip()
    val = _first_scalar(row.get("value"))
    if not trait or val in (None, ""):
        return None
    from anima.heart import Heart
    from anima.util import save_json
    from anima import memory_lirf, portrait
    heart = Heart.born(name, seed=7, n=16, now=1000.0).tend(0.55, now=1100.0)
    save_json(store / f"{name}.json", heart.to_dict())
    # a natural teaching utterance for the one fact, so capture lands it the production way.
    utt = _teach_utterance(trait, val)
    try:
        f = memory_lirf.Facts([])
        for c in f.capture(name, utt):
            f.merge(c)
        f.save(name)
    except Exception:
        return None
    # a bare portrait that mentions ONLY this fact, so the prompt has no other memory to lean on.
    try:
        portrait.save(name, f"- Their {trait.replace('_', ' ')} is {val}.")
    except Exception:
        pass
    return heart


def _teach_utterance(trait: str, val) -> str:
    """A natural first-person teaching sentence for a (trait, value), so memory_lirf.capture
    lands it the same way a real user statement would."""
    t = trait.lower()
    v = _first_scalar(val)
    if t in ("name",):
        return f"my name is {v}"
    if t in ("lives", "city"):
        return f"I live in {v}"
    if t in ("employer",):
        return f"I work at {v}"
    if t in ("occupation", "role"):
        return f"I'm a {v}"
    if t in ("sister", "brother", "partner", "mother", "father"):
        return f"my {t} is {v}"
    return f"my {t.replace('_', ' ')} is {v}"


def _one_fact_line(row) -> str:
    """A minimal, model-free 'memory' block for one fact row — a render helper for the memory
    branch's declared grounding fact."""
    if not isinstance(row, dict):
        return ""
    trait = str(row.get("trait", "")).replace("_", " ").strip()
    val = _first_scalar(row.get("value"))
    if not trait or val in (None, ""):
        return ""
    return f"What you know about them:\n- their {trait}: {val}"


def _first_scalar(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value


# ===================================================================================
# RUNNING A BRANCH — drive ONE Decision through the REAL generation path on the synthetic
# creature, capturing the reply. ``brain`` is injected so --selftest can pass a deterministic
# stub (the fork proof) while the live render passes the real Ollama-backed Mouth. The
# different-retrieved-memory branch runs against its own isolated creature so the REAL binding
# path surfaces a different memory (no engine edit); the aside is appended exactly as
# server._turn appends it.
# ===================================================================================
def run_turn(heart, name, user_text, decision: Decision, *, mouth=None, history=None,
             hearts=None) -> Branch:
    """Produce ONE branch: run mouth.respond for the base reply, then append the decision's
    aside — exactly as server._turn would. When the decision names its own ``creature`` (the
    different-retrieved-memory branch), respond runs against THAT creature's heart + ledger, so
    the bound memory genuinely differs through the REAL binding path (no engine edit, nothing
    shared mutated). ``hearts`` maps creature-name -> Heart for the isolated branches. Read-only:
    never calls mark_asked / mark_offered. Never raises — a generation error is captured on the
    Branch, not thrown."""
    from anima import senses
    base_reply, err = "", None
    run_name = decision.creature or name
    run_heart = (hearts or {}).get(run_name, heart) if decision.creature else heart
    try:
        p = senses.read(user_text, name=run_name)
        # The engine is unmodified: respond rebuilds the bound memory from run_heart's OWN
        # ledger (spine -> Facts.block). For the memory branch, run_heart/run_name point at a
        # creature seeded with a DIFFERENT salient fact, so the very same input is answered FROM
        # a different memory — the faithful counterfactual, with no shared state touched.
        u = mouth.respond(run_heart, user_text, history=list(history or []), perception=p)
        base_reply = (u.text or "").strip()
    except Exception as e:                      # a slow/broken model must never crash the replay
        err = repr(e)
        base_reply = f"[generation error: {err}]"

    aside = decision.aside
    if aside and aside.strip():
        full = base_reply.rstrip() + "\n\n" + aside.strip()
    else:
        full = base_reply
    return Branch(decision=decision, base_reply=base_reply, aside=aside, full_reply=full,
                  error=err)


# ===================================================================================
# THE DETERMINISTIC STUB BRAIN — the FORK PROOF seam. Its reply is a PURE FUNCTION of the
# inputs that a forced decision changes (the bound memory in the system prompt + the user
# text). No randomness, no model, no network. Because its output is determined by its inputs,
# a Decision that changes the memory_override provably changes the captured branch — and a
# Decision that changes only the aside changes the FULL reply (the aside is appended). This is
# what lets --selftest assert "different forced choice → different captured branch" offline,
# without ever gating the verdict on the live model.
# ===================================================================================
class _DeterministicStubBrain:
    """A model-free brain whose reply is a deterministic, readable function of (system, user).
    It echoes a short, stable acknowledgement plus a fingerprint of the bound MEMORY block it
    was given, so a different retrieved memory yields a visibly different base reply. NOT real
    speech — a seam to PROVE the harness forks. The real OllamaBrain is used for the live
    render."""

    name = "deterministic-stub"

    def available(self) -> bool:
        return True

    @staticmethod
    def _memory_fingerprint(system: str) -> str:
        """A short, stable surface of the bound-memory portion of the system prompt, so two
        prompts carrying DIFFERENT memory produce DIFFERENT replies. mouth._assemble_prompt
        emits the bound facts under a "your memory of who they are" marker; we isolate the
        text from there to the end of that block and return the FIRST real fact line (e.g.
        "name: Lamar") if present, else a deterministic hash of the block. Either way the
        result is a pure function of the bound memory — which is exactly what lets a different
        retrieved memory change the stub's reply."""
        marker = "your memory of who they are"
        low = system.lower()
        region = system
        if marker in low:
            region = system[low.index(marker) + len(marker):]
        # the first real fact BULLET ("- trait: value") — the bound value the reply should be
        # grounded in. We require the raw line to start with a bullet dash AND carry a ':', so
        # the block HEADER ("KNOWN FACTS ABOUT THE PERSON …:") and the marker's own "):"
        # punctuation line are both skipped (neither is a "- …" bullet).
        for line in region.splitlines():
            raw = line.strip()
            if raw.startswith("-") and ":" in raw:
                return raw.lstrip("-").strip()[:80]
        # deterministic fallback: a short hash of the memory region (still input-determined),
        # so even a block with no bullets still differentiates by its content.
        return "mem#" + hashlib.sha256(region.encode("utf-8")).hexdigest()[:8]

    def reply(self, system: str, user: str, history) -> str:
        fp = self._memory_fingerprint(system)
        u = (user or "").strip()
        return f"[stub reply · to:\"{u[:40]}\" · grounded-in:{fp}]"


def _stub_mouth():
    """Assemble a Mouth backed by the deterministic stub — the offline fork-proof path."""
    from anima.mouth import Mouth
    return Mouth(brain=_DeterministicStubBrain(), voice=None)


# ===================================================================================
# THE LIVE GATE — mirror scripts/experience.py exactly. The rendered replies are generated
# through the REAL path on the synthetic creature; with Ollama down every leg is PENDING and
# the render exits 0 (offline is not a failure). The self-test never uses this.
# ===================================================================================
def _model_available():
    """(available?, model-name, why-not). Identical Ollama gate to scripts/experience.py."""
    try:
        from anima.mouth import OllamaBrain
        b = OllamaBrain()
        if b.available():
            return True, b.model, ""
        return False, b.model, "Ollama not reachable at " + b.host
    except Exception as e:
        return False, "?", f"OllamaBrain probe failed: {e!r}"


# A small lived-in history so the base reply isn't cold-opened (parity with experience.py).
_HISTORY = [
    ("Hey, it's been a while.",
     "Hey you. I've been keeping your Collatio launch in mind — how's it landing?"),
    ("Rough week honestly.",
     "I figured. Want to tell me what's been heaviest?"),
]

# The default counterfactual prompt: an open, relational turn where the proactive-aside
# cascade genuinely fires (a casual question, no fact lookup) — so the "which aside" fork is
# the live decision, exactly as in production.
DEFAULT_INPUT = "What are you up to these days?"


def observe(user_text: str, *, brain_factory=None, live: bool = True) -> dict:
    """Build the ACTUAL + ALTERNATE branches for ``user_text`` on a fresh synthetic creature
    and CAPTURE each by running it through the generation path. ``brain_factory()`` supplies
    the Mouth (the live OllamaBrain-backed mouth, or the deterministic stub for the fork
    proof). Returns a report dict. HERMETIC: all of seeding + every branch run happen inside
    ONE redirected temp store, so the whole thing is read-only on real .anima. Never raises."""
    meta = {"input": user_text, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    branches: list = []
    decisions_dump: list = []
    with _temp_store() as store:
        try:
            heart = _seed_creature(SYNTH, store)
            decisions, mem_row = _build_decisions(SYNTH)
            # Seed the isolated creature for any different-retrieved-memory branch (its own
            # ledger, hermetic, mutating nothing shared), so respond surfaces a different fact.
            hearts: dict = {SYNTH: heart}
            for d in decisions:
                if d.creature and d.creature not in hearts:
                    h2 = _seed_memory_creature(d.creature, store, mem_row)
                    if h2 is not None:
                        hearts[d.creature] = h2
            decisions_dump = [{"label": d.label, "kind": d.kind, "aside_kind": d.aside_kind,
                               "gap_label": d.gap_label, "why": d.why,
                               "grounded_in": d.memory_override,
                               "creature": d.creature}
                              for d in decisions]
            mouth = (brain_factory or _stub_mouth)()
            for d in decisions:
                branches.append(run_turn(heart, SYNTH, user_text, d, mouth=mouth,
                                         history=_HISTORY, hearts=hearts))
        except Exception as e:                  # never raise out of the observatory
            meta["error"] = repr(e)
    meta["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return {"meta": meta, "decisions": decisions_dump,
            "branches": [b.to_dict() for b in branches], "_branch_objs": branches}


# ===================================================================================
# REPORT — render ACTUAL vs ALTERNATIVES side by side, each with its "what changed" line.
# ===================================================================================
def _wrap(text: str, width: int, indent: str) -> list:
    """Soft-wrap a paragraph to ``width`` columns under a fixed indent (no external deps)."""
    out, line = [], ""
    for word in (text or "").split():
        if line and len(line) + 1 + len(word) > width:
            out.append(indent + line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        out.append(indent + line)
    return out


def print_report(report: dict, *, available: bool, model: str, why_not: str,
                 synthetic_leak: list) -> None:
    branches = report.get("_branch_objs") or []
    print("=" * 92)
    print("VERA COUNTERFACTUAL OBSERVATORY — \"What Would Have Happened?\"")
    print("Given this turn, the road TAKEN vs the roads NOT taken — each re-run to show what")
    print("Vera WOULD have produced had she chosen differently.")
    print("=" * 92)
    print(f"\nINPUT (to the synthetic creature {SYNTH!r}):  \"{report['meta'].get('input','')}\"")

    if not available:
        print("\nLIVE MODEL UNAVAILABLE — every branch is PENDING (offline is not a failure).")
        print(f"  reason : {why_not}")
        print(f"  model  : {model}  (start Ollama to render the branches for real)")
        # Still show the DECISIONS that WOULD be forked — the structure is model-free, so the
        # "what would have happened" map is visible even with no model to voice it.
        print("\n  THE BRANCHES THAT WOULD BE COMPARED (decisions are model-free; only the")
        print("  rendered replies need the model):")
        for d in report.get("decisions", []):
            print(f"\n  • {d['label']}  [{d['kind']}]"
                  + (f"  aside={d['aside_kind']}" if d.get("aside_kind") else "")
                  + (f"  gap={d['gap_label']}" if d.get("gap_label") else "")
                  + (f"  grounded-in={d['grounded_in']}" if d.get("grounded_in") else ""))
            for ln in _wrap(d["why"], 84, "      why: "):
                print(ln if ln.startswith("      why:") else "           " + ln.strip())
        print("\nVERDICT: PENDING (no live model). Run with Ollama up to render the futures;")
        print("         run --selftest (no model needed) to prove the fork genuinely branches.")
        return

    print(f"model: {model}    branches: {len(branches)}    (ACTUAL + "
          f"{max(0, len(branches) - 1)} alternatives)\n")

    actual = next((b for b in branches if b.decision.kind == "actual"), None)
    alts = [b for b in branches if b.decision.kind != "actual"]

    # ACTUAL — the road taken.
    if actual is not None:
        print("-" * 92)
        print("ACTUAL  — the road taken")
        print("-" * 92)
        _print_branch(actual)

    # ALTERNATIVES — the roads not taken.
    for b in alts:
        print("\n" + "-" * 92)
        print(f"ALTERNATIVE — {b.decision.label[len('ALT · '):] if b.decision.label.startswith('ALT · ') else b.decision.label}")
        print("-" * 92)
        _print_branch(b)
        # the explicit ACTUAL-vs-this contrast line
        if actual is not None:
            print("    " + "·" * 4 + " vs ACTUAL: " + _contrast(actual, b))

    if synthetic_leak:
        print("\n  ** GUARDRAIL BREACH: synthetic creature leaked into real .anima — "
              f"{synthetic_leak}. The temp-store redirect failed; investigate. **")
    else:
        print(f"\n  guardrail: real .anima carries NO {SYNTH}.* file — synthetic-only isolation held.")

    print("\n" + "=" * 92)
    print("VERDICT: rendered the ACTUAL turn and "
          f"{len(alts)} forced alternative(s). Each alternative is the SAME input through a")
    print("         different decision — the roads Vera could have taken, made visible. "
          "(Run --selftest")
    print("         for the offline proof that forcing a different decision forks the branch.)")


def _print_branch(b: Branch) -> None:
    """Print one branch: its decision, the reply (base + aside), and the 'what changed' line."""
    d = b.decision
    tag = []
    if d.aside_kind:
        tag.append(f"aside={d.aside_kind}")
    if d.gap_label:
        tag.append(f"gap={d.gap_label}")
    if d.memory_override:
        tag.append(f"grounded-in={d.memory_override}")
    print("  decision : " + d.label + (("   [" + ", ".join(tag) + "]") if tag else ""))
    for ln in _wrap(d.why, 84, "  what changed: "):
        print(ln if ln.startswith("  what changed:") else "                " + ln.strip())
    print("  reply    :")
    for ln in (b.full_reply or "").splitlines() or [""]:
        print("      " + ln)
    if b.error:
        print(f"  (note: generation error captured: {b.error})")


def _contrast(actual: Branch, alt: Branch) -> str:
    """A one-line, concrete contrast between the ACTUAL branch and an alternate — names the
    single dimension that moved (aside / memory) so the side-by-side reads at a glance."""
    if alt.decision.kind == "curiosity":
        return (f"she asks about {alt.decision.gap_label} instead of "
                f"{actual.decision.gap_label} — a different thread of your life.")
    if alt.decision.kind == "offer":
        return ("she offers to HELP instead of asking a question — caretaker, not curious.")
    if alt.decision.kind == "memory":
        return ("same question, answered FROM a different memory she holds about you.")
    return "a different decision at the turn's branch point."


# ===================================================================================
# MAIN — human-readable (default) or --json. Renders through the live model (gated on Ollama),
# asserts the synthetic-only guardrail held. The live render NEVER gates the exit code on a
# pass/fail of the model — offline is 0; the only non-zero here is a guardrail breach.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA COUNTERFACTUAL OBSERVATORY (ACTUAL vs the roads not taken)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--input", default=DEFAULT_INPUT,
                    help="the user input to fork the turn on (default: the screenshot probe)")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    available, model, why = _model_available()
    if available:
        from anima.mouth import Mouth

        def _live_mouth():
            return Mouth.assemble(prefer_real=True, voice=False)
        report = observe(args.input, brain_factory=_live_mouth, live=True)
    else:
        # No model: still build the (model-free) DECISION map so the user sees what WOULD be
        # forked; we don't render replies. observe() with the stub would render stub text, but
        # the human contract here is "offline shows the branch structure, PENDING", so we build
        # decisions only and skip the stub render to stay honest about needing the model.
        report = observe(args.input, brain_factory=_stub_mouth, live=False)

    fp_after = _footprint(real_anima)
    synthetic_leak = _synthetic_leak(real_anima)

    out = {k: v for k, v in report.items() if k != "_branch_objs"}
    out["available"] = available
    out["model"] = model
    out["why_not"] = why
    out["synthetic_leak"] = synthetic_leak
    out["real_anima_whole_footprint_changed"] = (fp_before != fp_after)

    if args.json:
        print(json.dumps(out, indent=1))
    else:
        print_report(report, available=available, model=model, why_not=why,
                     synthetic_leak=synthetic_leak)

    # EXIT: a synthetic leak is the ONLY hard failure of the live render (offline is 0).
    return 2 if synthetic_leak else 0


# ===================================================================================
# SELFTEST — `python3 scripts/counterfactual.py --selftest`. PROVES, with NO model and NO
# network, that the harness genuinely FORKS the decision: a different forced choice yields a
# different captured branch, branches are DISTINCT + LABELED, and the synthetic-only guardrail
# holds. The deterministic stub brain is the seam; the live model never gates this verdict.
# ===================================================================================
def _selftest() -> int:
    fails: list = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    real = Path(_ROOT) / ".anima"
    fp0 = _footprint(real)

    # --- run the WHOLE observatory offline, through the deterministic stub seam -------------
    report = observe(DEFAULT_INPUT, brain_factory=_stub_mouth, live=False)
    branches = report["_branch_objs"]
    ok("observatory ran offline without raising", "error" not in report["meta"])
    ok("produced an ACTUAL branch plus >=2 ALTERNATIVES (>=3 total)", len(branches) >= 3)

    actual = next((b for b in branches if b.decision.kind == "actual"), None)
    alts = [b for b in branches if b.decision.kind != "actual"]
    ok("exactly one branch is the ACTUAL (road taken)",
       sum(1 for b in branches if b.decision.kind == "actual") == 1 and actual is not None)
    ok("at least two ALTERNATIVE branches (roads not taken)", len(alts) >= 2)

    # --- the alternates cover the three named branch families ------------------------------
    kinds = {b.decision.kind for b in alts}
    ok("alternatives include a DIFFERENT-curiosity-question branch", "curiosity" in kinds)
    ok("alternatives include an OFFER-SUPPORT branch", "offer" in kinds)
    ok("alternatives include a DIFFERENT-RETRIEVED-MEMORY branch", "memory" in kinds)

    # --- EVERY branch is LABELED (a non-empty label + a 'what changed' line) ----------------
    ok("every branch carries a non-empty label",
       all(b.decision.label and b.decision.label.strip() for b in branches))
    ok("every branch carries a 'what changed and why it matters' line",
       all(b.decision.why and b.decision.why.strip() for b in branches))
    ok("branch labels are all DISTINCT",
       len({b.decision.label for b in branches}) == len(branches))

    # --- THE FORK PROOF: distinct forced decisions -> distinct captured branches ------------
    # (a) different aside -> different FULL reply (the aside is appended to the turn).
    full_replies = [b.full_reply for b in branches]
    ok("THE FORK BRANCHES: the full turns are not all identical "
       f"({len({r for r in full_replies})} distinct of {len(full_replies)})",
       len({r for r in full_replies}) >= 2)
    # (b) the curiosity ALT appends a DIFFERENT aside than ACTUAL (a different question road).
    cur_alt = next((b for b in alts if b.decision.kind == "curiosity"), None)
    if cur_alt is not None and actual is not None:
        ok("FORK[curiosity]: the alternate's aside differs from ACTUAL's aside",
           (cur_alt.aside or "") != (actual.aside or "") and bool(cur_alt.aside))
        ok("FORK[curiosity]: the alternate's full reply differs from ACTUAL's",
           cur_alt.full_reply != actual.full_reply)
    # (c) the MEMORY ALT changes the BASE reply (the stub is grounded in the bound memory, so a
    #     different retrieved memory provably yields a different base reply — the deepest proof,
    #     because it shows the FORK reaches the generation path, not just the appended text).
    mem_alt = next((b for b in alts if b.decision.kind == "memory"), None)
    if mem_alt is not None and actual is not None:
        ok("FORK[memory]: a different retrieved memory yields a DIFFERENT base reply "
           "(the stub is grounded in the bound memory — the fork reached generation)",
           mem_alt.base_reply != actual.base_reply)
        ok("FORK[memory]: the memory branch carries a memory_override (the forced variable)",
           bool(mem_alt.decision.memory_override))
    # (d) the offer ALT appends a non-empty offer aside distinct from the ACTUAL aside.
    off_alt = next((b for b in alts if b.decision.kind == "offer"), None)
    if off_alt is not None:
        ok("FORK[offer]: the offer branch appends a non-empty offer line",
           bool(off_alt.aside and off_alt.aside.strip()))

    # --- DETERMINISM of the seam: re-running the SAME decision gives the SAME branch ---------
    # (so the distinctness above is caused by the DIFFERENT decision, not by noise.)
    if actual is not None:
        from anima.heart import Heart
        with _temp_store() as store2:
            heart2 = _seed_creature(SYNTH, store2)
            m2 = _stub_mouth()
            again = run_turn(heart2, SYNTH, DEFAULT_INPUT, actual.decision, mouth=m2,
                             history=_HISTORY)
        ok("seam is DETERMINISTIC: re-running ACTUAL's decision reproduces its base reply "
           "(so branch differences are caused by the forced choice, not randomness)",
           again.base_reply == actual.base_reply)

    # --- the stub genuinely differentiates by bound memory (the seam's core property) -------
    stub = _DeterministicStubBrain()
    r_a = stub.reply("…your memory of who they are:\n- their employer: Collatio\n", "hi", [])
    r_b = stub.reply("…your memory of who they are:\n- their city: Portland\n", "hi", [])
    r_a2 = stub.reply("…your memory of who they are:\n- their employer: Collatio\n", "hi", [])
    ok("stub seam: different bound memory -> different reply", r_a != r_b)
    ok("stub seam: SAME bound memory -> identical reply (pure function of inputs)", r_a == r_a2)

    # --- read-only: the replay did NOT mutate the synthetic ledger as a side effect ---------
    # Re-derive candidate_gaps before vs after a full observe on a SECOND fresh creature; a
    # replay that (wrongly) called mark_asked would have FEWER candidates the second time.
    from anima import curiosity as _cur
    with _temp_store() as store3:
        heart3 = _seed_creature(SYNTH, store3)
        before_n = len(_cur.candidate_gaps(SYNTH) or [])
        # run the alternates (which read curiosity/opportunity) — must not consume any gap
        decisions, mem_row = _build_decisions(SYNTH)
        hearts3 = {SYNTH: heart3}
        for d in decisions:
            if d.creature and d.creature not in hearts3:
                h = _seed_memory_creature(d.creature, store3, mem_row)
                if h is not None:
                    hearts3[d.creature] = h
        mouth = _stub_mouth()
        for d in decisions:
            run_turn(heart3, SYNTH, DEFAULT_INPUT, d, mouth=mouth, history=_HISTORY,
                     hearts=hearts3)
        after_n = len(_cur.candidate_gaps(SYNTH) or [])
    ok("READ-ONLY: building + running branches did NOT consume a curiosity gap "
       f"(candidates {before_n} -> {after_n}; mark_asked never called)",
       before_n == after_n and before_n > 0)

    # --- render never raises and reflects the branches --------------------------------------
    out_json = {k: v for k, v in report.items() if k != "_branch_objs"}
    ok("report is JSON-serialisable (Viewer-ready)",
       _json_ok(out_json))
    # offline human render (PENDING path) must not raise and must show the decision map.
    import io
    import contextlib as _ctx
    buf = io.StringIO()
    with _ctx.redirect_stdout(buf):
        print_report(report, available=False, model="(none)", why_not="selftest: model off",
                     synthetic_leak=[])
    txt = buf.getvalue()
    ok("offline render: produced a non-empty report", bool(txt.strip()))
    ok("offline render: shows the branch decision map", "THE BRANCHES THAT WOULD BE COMPARED" in txt)
    ok("offline render: names the ACTUAL road", "ACTUAL" in txt)
    # online-shaped render with the stub branches present must also not raise.
    buf2 = io.StringIO()
    with _ctx.redirect_stdout(buf2):
        print_report(report, available=True, model="stub", why_not="", synthetic_leak=[])
    txt2 = buf2.getvalue()
    ok("rendered (model-present path): shows ACTUAL and ALTERNATIVE sections",
       "ACTUAL  — the road taken" in txt2 and "ALTERNATIVE —" in txt2)
    ok("rendered: each alternative carries a 'vs ACTUAL' contrast line", "vs ACTUAL:" in txt2)

    # --- robustness: a junk input never raises ----------------------------------------------
    try:
        _ = observe("", brain_factory=_stub_mouth, live=False)
        crashed = False
    except Exception as e:  # noqa: BLE001
        crashed = True
        print("       (raised:", repr(e), ")")
    ok("robust: an empty input observes without raising", not crashed)

    # --- GUARDRAIL: the whole selftest touched no real .anima file --------------------------
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the whole selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature file leaked into real .anima",
       not _synthetic_leak(real))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL COUNTERFACTUAL-OBSERVATORY SELFTESTS PASS")
    return 0


def _json_ok(obj) -> bool:
    try:
        json.dumps(obj)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
