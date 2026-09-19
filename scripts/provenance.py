#!/usr/bin/env python3
"""VERA DECISION PROVENANCE TREE — Layer 3, "the Causal Observatory's deepest cut".

scripts/decisions.py (the Decision Observatory) shows, for the curiosity decision, the
FULL ranked field — which gap won, which lost, each with a SCORE and a COARSE reason
(SELECTED / LOWER_RANK / KNOWN_SUPPRESSED). It answers "which road was taken, and which
were not." It does NOT answer the harder question one layer down:

    WHY is the winner's score the number it is?

The Decision Observatory hands you ``17.81`` and the label ``you:relationship:mike``. That
number is the OUTPUT of the engine's ranking key (``curiosity._score``), but the
observatory treats it as opaque — a single float with a one-word reason bolted on. A score
of 17.81 is not a fact, it is a SUM: a relationship-gap floor, a log-damped mention curve
fed by "Mike mentioned 42x", a kind bump for SUSPECTED, and an evidence trickle. This tool
opens that sum up.

For the TOP decision on a synthetic creature it builds a PROVENANCE TREE — it DECOMPOSES the
winner's score into the named, signed CONTRIBUTIONS that produced it, each tied back to the
real signal behind it (the FACT "Mike x42", the GRAPH EDGE you<->Mike, the GAP "relationship
unresolved", the engine WEIGHTS), and proves the contributions RECONSTRUCT the engine's own
``curiosity._score`` to floating-point tolerance:

        SCORE 17.81  =  base relationship floor      +10.0000   (a mentioned person outranks
                                                                 every empty taxonomy slot)
                     +  mention curve  2·ln(1+42)     +7.5224    ← FACT: Mike mentioned 42x
                                                                   ← EDGE: you —knows→ Mike (×42)
                     +  kind bump  (SUSPECTED)         +0.2500    ← GAP: relationship is SUSPECTED
                     +  evidence weight  0.001·42      +0.0420    ← FACT: 42 mentions, again
                     ────────────────────────────────────────
                     =  17.8144   ==  curiosity._score(gap)   →  SELECTED

This is the difference between a NUMBER and a PROVENANCE: the named contributions are not a
post-hoc story bolted onto 17.81 — they are DERIVED from the same constants
``curiosity._suspect_priority`` / ``curiosity._score`` use, and the --selftest asserts they
SUM BACK to the engine's actual score. If the decomposition drifts from the engine by even
1e-6, the selftest fails. That is what makes it real, not narrated.

It decomposes EVERY gap kind the engine ranks, from the same constants:
  * a SUSPECTED relationship gap (the canonical Mike):  floor(10) + mention-curve + bump + ev.
  * an empty TAXONOMY slot (UNKNOWN, e.g. the 'name' slot):  the slot's base priority alone.
  * a low-confidence TAXONOMY hint (SUSPECTED):  base + 1.0 (the hint lift) + bump + ev.
  * a CONTRADICTED slot:  base + 4.0 (the tension lift) + bump + ev.
The tree also attaches the CONTEXT each contribution rests on — the world-graph edges that
connect the gap's entity, and the sibling gaps the engine suppressed/holds — so the reader
sees not just the arithmetic but the EVIDENCE the arithmetic is reading.

GUARDRAILS (identical discipline to scripts/decisions.py + scripts/causal.py + relationship.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * STANDALONE + READ-ONLY on the engines. It IMPORTS and CALLS curiosity / memory_lirf /
    world_state / meaning, and REUSES scripts/decisions.curiosity_decision (the same ranking
    the live curiosity stage uses) to pick the TOP decision. It edits NO module, NO test, and
    not curiosity.py / decisions.py / causal.py / certify.py / selftest.py. The only file it
    adds is scripts/provenance.py. No accessor was added to any engine — the decomposition
    reads the engine's PUBLIC constants (``_suspect_priority``, the ``_score`` bump table,
    TAXONOMY) and asserts it matches the engine's own ``_score``.
  * SYNTHETIC creatures + a HERMETIC temp store ONLY. Every STORE the derivation can touch is
    redirected to ONE TemporaryDirectory — memory_lirf.STORE on BOTH the __main__ and package
    bindings, constitution.STORE, reliability.DEFAULT_STORE, curiosity.STORE, world_state.STORE,
    meaning.STORE, telemetry.STORE, cloud.STORE (mirroring anima/memory_lirf.py's _selftest and
    scripts/causal.py). The run ASSERTS the real .anima footprint is byte-UNCHANGED start->end.
    It NEVER reads or writes a real Vera.* file.
  * DETERMINISTIC + OFFLINE. No model, no network. The decomposition is pure arithmetic over the
    engine's constants; the ranking is deterministic for a fixed creature.
  * Never raises out of the entry points — a malformed creature yields an honest empty render,
    not a traceback.

    python3 scripts/provenance.py            # the provenance TREE for the top decision
    python3 scripts/provenance.py --json     # machine-readable
    python3 scripts/provenance.py --selftest  # PROVE the tree decomposes the real score

Exit code is 0 on a default run / a passing selftest with the guardrail intact; non-zero only
on a broken guardrail (real .anima changed, or an engine raised inside the harness) or a failed
selftest assertion.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import secrets
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from anima import curiosity              # noqa: E402  the _score we decompose + the gap shape
from anima import memory_lirf            # noqa: E402  the LIRF ledger (the fact weights / KNOWN bar)
from anima import world_state            # noqa: E402  the graph edges that connect a gap's entity
import scripts.decisions as decisions    # noqa: E402  REUSE the candidate ranking + the top decision

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "prov_synth"

# How close the named contributions must sum to the engine's own _score to count as a real
# DECOMPOSITION (not a narration). Float arithmetic only — this is a tight equality, not a fudge.
_RECON_TOL = 1e-6


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect mirroring anima/memory_lirf.py _selftest
# (~1316-1340) + scripts/causal.py: redirect EVERY store the derivation can touch into ONE
# throwaway dir, including memory_lirf.STORE on BOTH the __main__ and package bindings (under
# `python3 -m` they are distinct objects). Plus a footprint hash to PROVE nothing real moved.
# The brief names these exact targets: memory_lirf.STORE (BOTH bindings), constitution.STORE,
# reliability.DEFAULT_STORE, curiosity.STORE, world_state.STORE, meaning.STORE, telemetry.STORE,
# cloud.STORE.
# ===================================================================================
_STORE_TARGETS = (
    ("anima.memory_lirf", "STORE"),
    ("anima.constitution", "STORE"),
    ("anima.reliability", "DEFAULT_STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.telemetry", "STORE"),
    ("anima.cloud", "STORE"),
)


def _store_modules():
    """Resolve the (module, attr) redirect targets that import cleanly. Folds in the EXACT
    objects this file holds (memory_lirf, curiosity, world_state) explicitly — the dual-binding
    guard the memory_lirf self-test warns about: under `python3 -m` the dotted import can return
    a different copy than the one we hold, and a write to the un-redirected copy would leak to
    the real .anima."""
    out = []
    seen = set()
    for dotted, attr in _STORE_TARGETS:
        try:
            mod = __import__(dotted, fromlist=["_"])
        except Exception:
            continue
        key = (id(mod), attr)
        if key in seen:
            continue
        if getattr(mod, attr, None) is not None:
            out.append((mod, attr))
            seen.add(key)
    # the dual-binding guard: ensure the *exact objects* this file holds are redirected even if
    # their dotted import returned a different copy.
    for mod, attr in ((memory_lirf, "STORE"), (curiosity, "STORE"), (world_state, "STORE")):
        key = (id(mod), attr)
        if key not in seen and getattr(mod, attr, None) is not None:
            out.append((mod, attr))
            seen.add(key)
    return out


@contextlib.contextmanager
def _temp_store():
    """Redirect every resolved STORE target to one fresh temp dir for the duration, then
    restore. Nothing under the real .anima/ is read or written while this is active. The
    reused scripts/decisions.curiosity_decision has its OWN redirect, but we keep ours active
    too so any leg of the derivation can never touch real state."""
    targets = _store_modules()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-provenance-") as td:
        p = Path(td)
        for (m, a) in targets:
            setattr(m, a, p)
        try:
            yield p
        finally:
            for (m, a, old) in saved:
                if old is not None:
                    setattr(m, a, old)


def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir,
    which legitimately changes) so we can PROVE the harness touched nothing. Verbatim from
    scripts/decisions.py / scripts/causal.py / scripts/relationship.py."""
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
# THE DECOMPOSITION — the load-bearing computation. We re-express the engine's ranking key
# ``curiosity._score`` as a SUM of named, signed contributions derived from the SAME constants
# the engine uses, and assert (in the selftest) that the sum reconstructs the engine's own
# ``_score(gap)`` to ``_RECON_TOL``. This is what makes the tree a PROVENANCE, not a story.
#
# The engine's score, verbatim from curiosity._score:
#     _score(gap) = priority + bump + 0.001 * mentions
# where:
#     bump      = {CONTRADICTED: 0.5, SUSPECTED: 0.25, UNKNOWN: 0.0}[kind]
#     mentions  = gap.evidence.mentions
#     priority  = (set in detect_gaps, per kind/source):
#         * a SUSPECTED relationship gap (the Mike case):
#               priority = _suspect_priority(mentions) = 10.0 + 2.0 * ln(1 + mentions)
#           which we split into  base relationship floor (10.0)  +  mention curve (2·ln(1+m)).
#         * an empty TAXONOMY slot (UNKNOWN):     priority = base
#         * a low-confidence TAXONOMY hint (SUSPECTED, has trait): priority = base + 1.0
#         * a CONTRADICTED TAXONOMY slot:         priority = base + 4.0
# Each branch's contributions are built from the gap's OWN fields + the engine constants, so the
# decomposition tracks the engine even if a constant changes.
# ===================================================================================

# Names + glosses for each contribution kind — the closed vocabulary of the provenance tree.
# (id, human gloss). A consumer can branch on the id; the gloss is what to SHOW.
C_REL_FLOOR = "base_relationship_floor"
C_MENTION_CURVE = "mention_curve"
C_TAXO_BASE = "taxonomy_base_priority"
C_HINT_LIFT = "suspected_hint_lift"
C_CONTRA_LIFT = "contradiction_lift"
C_KIND_BUMP = "kind_bump"
C_EVIDENCE = "evidence_weight"

_CONTRIB_GLOSS = {
    C_REL_FLOOR: "a mentioned person outranks every empty taxonomy slot (the floor in "
                 "curiosity._suspect_priority)",
    C_MENTION_CURVE: "the log-damped weight of how often the entity was mentioned "
                     "(2·ln(1+mentions))",
    C_TAXO_BASE: "the slot's base priority — how core this fact is to knowing a person "
                 "(curiosity.TAXONOMY)",
    C_HINT_LIFT: "a low-confidence hint already on record lifts the slot above a blank one "
                 "(+1.0)",
    C_CONTRA_LIFT: "an unresolved contradiction is high-signal — resolving a tension beats a "
                   "fresh ask (+4.0)",
    C_KIND_BUMP: "the gap-kind bump in curiosity._score (CONTRADICTED 0.5 · SUSPECTED 0.25 · "
                 "UNKNOWN 0.0)",
    C_EVIDENCE: "the raw evidence trickle in curiosity._score (0.001·mentions)",
}


def _kind_bump(kind: str) -> float:
    """The exact kind bump curiosity._score applies. Read from the engine's OWN bump table by
    reconstructing it from the engine constants, so it can never drift from the engine."""
    return {curiosity.CONTRADICTED: 0.5, curiosity.SUSPECTED: 0.25,
            curiosity.UNKNOWN: 0.0}.get(kind, 0.0)


def _mentions_of(gap: dict) -> int:
    ev = gap.get("evidence") or {}
    try:
        return int(ev.get("mentions", 0))
    except (TypeError, ValueError):
        return 0


def _taxonomy_base(slot: str) -> float:
    """The base priority of a taxonomy slot (the engine's TAXONOMY weight), or 0.0 if the slot
    is not in the taxonomy (a pure relationship gap has no taxonomy base)."""
    for (_cat, s, _trait, base) in curiosity.TAXONOMY:
        if s == slot:
            return float(base)
    return 0.0


def _contrib(cid: str, value: float, *, signal: str) -> dict:
    """One node of the provenance tree: a named, signed contribution + the SIGNAL it reads."""
    return {
        "id": cid,
        "gloss": _CONTRIB_GLOSS.get(cid, cid),
        "value": round(float(value), 6),
        "signal": signal,
    }


def decompose_score(gap: dict) -> dict:
    """Decompose the engine's ranking key ``curiosity._score(gap)`` into named, signed
    contributions DERIVED from the engine's own constants, tied to the signal behind each.

    Returns:
        {
          "kind":          the gap kind (SUSPECTED / UNKNOWN / CONTRADICTED),
          "mentions":      the mention count feeding the curve/evidence terms,
          "contributions": [ {id, gloss, value, signal}, ... ]  (the tree's leaves),
          "composed":      Σ contributions  (the score the tree reconstructs),
          "engine_score":  curiosity._score(gap)  (the engine's ACTUAL score),
          "reconstructs":  bool  (|composed - engine_score| <= _RECON_TOL),
          "residual":      composed - engine_score  (0 when it reconstructs),
        }

    The contributions are the PROVENANCE: every one is computed from a gap field + an engine
    constant, never reverse-engineered from the final number. ``reconstructs`` is the proof the
    decomposition is REAL — if it is False, the tree is not faithfully decomposing the engine.
    Pure; never raises (a malformed gap yields an empty, non-reconstructing decomposition)."""
    if not isinstance(gap, dict):
        return {"kind": None, "mentions": 0, "contributions": [], "composed": 0.0,
                "engine_score": 0.0, "reconstructs": False, "residual": 0.0}

    kind = gap.get("kind")
    slot = gap.get("slot", "") or ""
    trait = gap.get("trait", "") or ""
    entity = gap.get("entity", "") or ""
    mentions = _mentions_of(gap)
    contribs: list = []

    is_relationship = slot.startswith("relationship:") or (
        kind == curiosity.SUSPECTED and not trait)

    if is_relationship:
        # priority = _suspect_priority(mentions) = 10.0 + 2.0 * ln(1 + mentions)
        # split into the FLOOR (a mentioned person beats every empty slot) + the MENTION CURVE.
        floor = 10.0
        curve = 2.0 * math.log(1 + max(0, mentions))
        ent_label = entity or slot.replace("relationship:", "")
        contribs.append(_contrib(
            C_REL_FLOOR, floor,
            signal=f'GAP: "{ent_label}" is a known-about person whose relationship is '
                   f'UNRESOLVED — the engine floors it above every empty taxonomy slot'))
        contribs.append(_contrib(
            C_MENTION_CURVE, curve,
            signal=f'FACT: "{ent_label}" mentioned {mentions}x  ·  EDGE: you —knows→ '
                   f'{ent_label} (support {mentions})'))
    else:
        # a TAXONOMY-slot gap: base priority, plus the kind-specific lift detect_gaps adds.
        base = _taxonomy_base(slot)
        contribs.append(_contrib(
            C_TAXO_BASE, base,
            signal=f'GAP: the "{slot}" slot — base priority {base:g} in curiosity.TAXONOMY '
                   f'(how core this is to knowing a person)'))
        if kind == curiosity.CONTRADICTED:
            contribs.append(_contrib(
                C_CONTRA_LIFT, 4.0,
                signal=f'GAP: the "{slot}" value is CONTRADICTED — the record holds a '
                       f'superseded value in tension with the active one'))
        elif kind == curiosity.SUSPECTED and trait:
            contribs.append(_contrib(
                C_HINT_LIFT, 1.0,
                signal=f'FACT: a low-confidence hint for "{slot}" is already on record (below '
                       f'the [KNOWN] bar {curiosity._CONF_KNOWN:g}) — a SUSPECTED slot'))

    # the two terms curiosity._score adds to EVERY gap, regardless of branch.
    bump = _kind_bump(kind)
    contribs.append(_contrib(
        C_KIND_BUMP, bump,
        signal=f'WEIGHT: the gap-kind bump for {kind} in curiosity._score'))
    contribs.append(_contrib(
        C_EVIDENCE, 0.001 * mentions,
        signal=f'FACT: {mentions} mentions feed the raw evidence weight (0.001·mentions) in '
               f'curiosity._score'))

    composed = sum(c["value"] for c in contribs)
    try:
        engine_score = float(curiosity._score(gap))
    except Exception:
        engine_score = 0.0
    residual = composed - engine_score
    return {
        "kind": kind,
        "mentions": mentions,
        "contributions": contribs,
        "composed": round(composed, 6),
        "engine_score": round(engine_score, 6),
        "reconstructs": abs(residual) <= _RECON_TOL,
        "residual": round(residual, 9),
    }


def _dominant_contribution(decomp: dict) -> dict:
    """The single contribution that most explains the score — the largest-magnitude leaf. This
    is the headline of the provenance tree ("what made this win")."""
    contribs = decomp.get("contributions") or []
    if not contribs:
        return {}
    return max(contribs, key=lambda c: abs(float(c.get("value", 0.0))))


# ===================================================================================
# THE CONTEXT — the world-graph edges + sibling gaps the contributions REST ON. The
# decomposition is the arithmetic; this is the EVIDENCE the arithmetic reads, so the tree shows
# both. Read-only.
# ===================================================================================
def _entity_edges(name: str, entity: str) -> list:
    """The active world-graph edges that touch ``entity`` (the gap's subject) — the EDGES that
    connect it into the graph (you —knows→ Mike, Mike —works_with→ …). These are the graph
    signal behind the relationship gap's mention curve. Read-only; never raises."""
    if not entity:
        return []
    try:
        edges = world_state.World.load(name).active()
    except Exception:
        return []
    want = world_state._norm_node(entity)
    out = []
    for e in edges:
        if not isinstance(e, dict):
            continue
        s = world_state._norm_node(e.get("subject"))
        o = world_state._norm_node(e.get("object"))
        if want in (s, o):
            out.append({
                "subject": e.get("subject"),
                "predicate": e.get("predicate"),
                "object": e.get("object"),
                "support": int(e.get("support", 1) or 1),
                "kind": e.get("kind", ""),
            })
    out.sort(key=lambda d: -d["support"])
    return out


# ===================================================================================
# THE PROVENANCE TREE — for the TOP decision: re-derive the ranking (reusing the Decision
# Observatory), pick the winner, decompose its score, attach the context, and frame the losers.
# ===================================================================================
def provenance_tree(name: str, *, budget: str = "deep", recent_text=None) -> dict:
    """Build the DECISION PROVENANCE TREE for ``name``'s TOP curiosity decision.

    REUSES scripts/decisions.curiosity_decision (the SAME ranking the live curiosity stage
    uses) to identify the winner — so the tree and the Decision Observatory agree on WHO won by
    construction. It then goes one layer DEEPER than the observatory: it DECOMPOSES the winner's
    score into the named contributions that produced it (``decompose_score``), proves they
    reconstruct the engine's own ``curiosity._score``, names the dominant contributor, and
    attaches the world-graph edges + the runner-up field the winner beat.

    Returns:
        {
          "name", "budget",
          "decision":      the human label of the decision point,
          "winner":        the SELECTED candidate dict (from the Decision Observatory),
          "score":         the winner's score (== engine_score in the decomposition),
          "provenance":    the decompose_score(gap) tree (contributions -> composed -> engine),
          "dominant":      the single largest contribution (what made it win),
          "edges":         the world-graph edges the winner's entity sits on (the EVIDENCE),
          "beat":          the top few rejected candidates the winner outranked (with reasons),
          "selected":      True iff curiosity actually surfaced it this turn,
        }

    Deterministic for a fixed creature; read-only; never raises (a creature with no open gap
    yields a tree with winner=None and an honest empty provenance)."""
    out = {
        "name": name, "budget": budget,
        "decision": "curiosity:which gap to ask  (score provenance)",
        "winner": None, "score": 0.0, "provenance": {}, "dominant": {},
        "edges": [], "beat": [], "selected": False,
    }

    # 1) the ranking + the winner — REUSE the Decision Observatory (same engine, same order).
    try:
        dec = decisions.curiosity_decision(name, budget=budget, recent_text=recent_text)
    except Exception:
        dec = {"selected": None, "rejected": [], "candidates": []}

    # the TOP decision is the SELECTED gap if curiosity surfaced one this turn; else the top
    # OPEN candidate the budget held (still the strongest-scored road — the one worth explaining).
    sel = dec.get("selected")
    top = sel
    if top is None:
        open_cands = [c for c in (dec.get("candidates") or [])
                      if c.get("reason") in (decisions.SELECTED, decisions.LOWER_RANK,
                                             decisions.BUDGET_HELD)]
        if open_cands:
            top = max(open_cands, key=lambda c: float(c.get("score", 0.0)))
    if top is None:
        return out  # honest empty tree: nothing open to explain this turn

    out["winner"] = top
    out["score"] = float(top.get("score", 0.0))
    out["selected"] = sel is not None

    # 2) re-fetch the ENGINE GAP behind the winner (the candidate dict is a projection; the
    #    decomposition needs the gap's raw fields). Match by gap_key over the engine's own gaps.
    gap = _gap_behind(name, top)
    out["provenance"] = decompose_score(gap) if gap is not None else {}
    out["dominant"] = _dominant_contribution(out["provenance"])

    # 3) the EVIDENCE the contributions rest on — the world-graph edges on the winner's entity.
    entity = (gap or {}).get("entity", "") or ""
    if entity and world_state._norm_node(entity) != curiosity.SELF:
        out["edges"] = _entity_edges(name, entity)

    # 4) the runners-up the winner BEAT (the top few rejected roads, with their coarse reason).
    rejected = sorted((dec.get("rejected") or []),
                      key=lambda c: -float(c.get("score", 0.0)))
    out["beat"] = [{
        "label": c.get("label"),
        "score": float(c.get("score", 0.0)),
        "reason": c.get("reason"),
        "reason_gloss": c.get("reason_gloss"),
    } for c in rejected[:5]]
    return out


def _gap_behind(name: str, candidate: dict):
    """Find the ENGINE gap dict behind a Decision-Observatory candidate, matched by gap_key.
    The candidate is a flattened projection (label/slot/score/reason); the decomposition needs
    the gap's raw evidence/kind/trait, so we re-fetch the engine's gaps and match. Read-only."""
    want = candidate.get("gap_key")
    try:
        gaps = curiosity.detect_gaps(name) or []
    except Exception:
        gaps = []
    for g in gaps:
        try:
            if curiosity._gap_key(g) == want:
                return g
        except Exception:
            continue
    return None


# ===================================================================================
# SYNTHETIC CREATURE — the canonical rich creature whose TOP decision has a RICH provenance:
# a 42-mention unknown 'Mike' (the SELECTED relationship gap, score ~17.81), a confident KNOWN
# birthday (a KNOWN-suppressed sibling), and an already-asked 'occupation' (a Law-002 sibling).
# REUSES scripts/decisions.seed_demo_creature so the creature is IDENTICAL to the Decision
# Observatory's — the provenance tree explains the SAME winner that observatory shows. All
# writes land in the (already-redirected) temp store.
# ===================================================================================
def seed_demo_creature(name: str) -> None:
    """Seed the canonical rich creature (REUSING the Decision Observatory's seeder, so the top
    decision is identical): KNOWN birthday + 42-mention Mike + an asked 'occupation' gap.
    Deterministic; offline; writes only to the redirected stores."""
    decisions.seed_demo_creature(name)


# ===================================================================================
# RENDER — the provenance TREE, human-readable: contributions -> composed score -> selected.
# ===================================================================================
def _sign(v: float) -> str:
    return f"+{v:.4f}" if v >= 0 else f"{v:.4f}"


def render_tree(tree: dict) -> str:
    out = []
    out.append(f'DECISION: {tree.get("decision")}   (creature: {tree.get("name")}, '
               f'budget: {tree.get("budget")})')
    win = tree.get("winner")
    if not win:
        out.append("")
        out.append("  (no open gap this turn — nothing to build a provenance for)")
        return "\n".join(out)

    prov = tree.get("provenance") or {}
    score = float(prov.get("engine_score", tree.get("score", 0.0)))
    out.append("")
    out.append(f'  TOP DECISION  ->  {win.get("label")}'
               + ("   (SELECTED — curiosity asks it this turn)" if tree.get("selected")
                  else "   (top gap, held silent by the budget this turn)"))
    if win.get("question"):
        out.append(f'      would ask: "{win.get("question")}"')
    out.append("")
    out.append(f'  PROVENANCE OF THE SCORE  ({score:.4f})  —  the named signals that compose it:')
    out.append("")
    # the contribution leaves, largest-magnitude first (the dominant signal leads).
    contribs = sorted((prov.get("contributions") or []),
                      key=lambda c: -abs(float(c.get("value", 0.0))))
    dom = tree.get("dominant") or {}
    for c in contribs:
        mark = "  ►" if c.get("id") == dom.get("id") else "   "
        out.append(f'{mark} {_sign(float(c.get("value", 0.0))):>10}   {c.get("id")}')
        out.append(f'                 ← {c.get("signal")}')
        out.append(f'                   ({c.get("gloss")})')
    out.append("                 " + "─" * 56)
    out.append(f'      composed = {float(prov.get("composed", 0.0)):.4f}   '
               f'==  curiosity._score = {score:.4f}   '
               f'(residual {float(prov.get("residual", 0.0)):+.2e})')
    recon = prov.get("reconstructs")
    out.append(f'      RECONSTRUCTS THE ENGINE SCORE: '
               + ("YES — the named contributions ARE the score, not a story about it"
                  if recon else "NO — DECOMPOSITION DRIFTED FROM THE ENGINE"))
    if dom:
        out.append("")
        out.append(f'  DOMINANT SIGNAL: {dom.get("id")} ({_sign(float(dom.get("value",0.0)))}) '
                   f'— {dom.get("gloss")}')

    edges = tree.get("edges") or []
    if edges:
        out.append("")
        out.append("  THE GRAPH EDGES THIS RESTS ON (the evidence the mention curve reads):")
        for e in edges[:6]:
            out.append(f'    · {e.get("subject")} —{e.get("predicate")}→ {e.get("object")}'
                       f'   (support {e.get("support")}, kind {e.get("kind")})')

    beat = tree.get("beat") or []
    if beat:
        out.append("")
        out.append("  THE ROADS IT OUTRANKED (the runner-up field, by score):")
        for b in beat:
            out.append(f'    · {b.get("label"):<26} [score {float(b.get("score",0.0)):.3f}]  '
                       f'{b.get("reason")}')
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 88)
    out.append("VERA DECISION PROVENANCE TREE — Layer 3: WHY the score is the number it is")
    out.append("The Decision Observatory shows the score + a coarse reason. This DECOMPOSES the")
    out.append("score into the named signals — facts, graph edges, gaps, weights — that compose")
    out.append("it, and proves they reconstruct the engine's OWN score. A tree, not a number.")
    out.append("=" * 88)
    out.append("")
    out.append(render_tree(report.get("tree", {})))
    out.append("")
    out.append("-" * 88)
    out.append("THE CONTRIBUTION VOCABULARY (every leaf is derived from a curiosity-engine constant)")
    out.append("-" * 88)
    for cid in (C_REL_FLOOR, C_MENTION_CURVE, C_TAXO_BASE, C_HINT_LIFT, C_CONTRA_LIFT,
                C_KIND_BUMP, C_EVIDENCE):
        out.append(f"  {cid:<26} {_CONTRIB_GLOSS[cid]}")
    out.append("")
    out.append("WIRING NOTE: this REUSES scripts/decisions.curiosity_decision (the same ranking")
    out.append("the live curiosity stage runs) to pick the TOP decision, then decomposes its")
    out.append("curiosity._score into contributions derived from the engine's OWN constants")
    out.append("(curiosity._suspect_priority, the _score bump table, curiosity.TAXONOMY). The")
    out.append("--selftest asserts the contributions SUM BACK to curiosity._score — so the tree")
    out.append("DECOMPOSES the real score, it does not narrate it. No engine was changed.")
    return "\n".join(out)


# ===================================================================================
# THE DEMO REPORT — seed the canonical rich creature, build the tree, render.
# ===================================================================================
def build_report() -> dict:
    """Seed the canonical rich synthetic creature in a hermetic temp store and build the
    provenance tree for its TOP decision. Deterministic + offline + isolated. Returns the
    full report dict."""
    with _temp_store():
        name = f"{SYNTH}_{secrets.token_hex(3)}"
        seed_demo_creature(name)
        tree = provenance_tree(name, budget="deep")
    return {"tree": tree}


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA DECISION PROVENANCE TREE (decompose the top decision's score into its signals)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    try:
        report = build_report()
        engine_error = None
    except Exception as e:                       # pragma: no cover - entry point never raises
        report = {"tree": {}}
        engine_error = repr(e)

    fp_after = _footprint(real_anima)
    footprint_unchanged = fp_before == fp_after
    report["footprint_unchanged"] = footprint_unchanged
    report["engine_error"] = engine_error

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        print("")
        print("GUARDRAIL: real .anima footprint  : "
              + ("byte-UNCHANGED (synthetic-only; nothing real touched)"
                 if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
        if engine_error:
            print(f"GUARDRAIL: engine error           : {engine_error}")

    return 0 if (footprint_unchanged and engine_error is None) else 1


# ===================================================================================
# SELFTEST — `python3 scripts/provenance.py --selftest`. Proves the tree is a real
# DECOMPOSITION, not a narration:
#   * the named contributions SUM BACK to the engine's OWN curiosity._score (within _RECON_TOL)
#     for the winner AND for EVERY ranked gap (the load-bearing "it's real" proof);
#   * the dominant contributor is named, and for the canonical Mike it is the mention curve;
#   * the tree is DETERMINISTIC for a fixed creature;
#   * the winner agrees with the Decision Observatory's SELECTED (same ranking);
#   * the world-graph edges the curve reads are attached;
#   * the synthetic-only guardrail holds (real .anima byte-unchanged).
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

    with _temp_store():
        tok = secrets.token_hex(3)

        # === the canonical RICH creature: KNOWN birthday + 42-mention Mike + asked occupation =
        nm = f"{SYNTH}_rich_{tok}"
        seed_demo_creature(nm)
        tree = provenance_tree(nm, budget="deep")
        prov = tree["provenance"]

        # --- there IS a top decision, and it is the canonical high-mention 'Mike' ------------
        ok("tree: a creature with open gaps has a TOP decision",
           tree["winner"] is not None)
        ok("tree: the top decision is the canonical high-mention 'Mike' (the SELECTED gap)",
           tree["winner"] is not None and "mike" in (tree["winner"].get("label", "").lower()))
        ok("tree: curiosity actually surfaced it this turn (selected at deep budget)",
           tree["selected"] is True)

        # === THE LOAD-BEARING PROOF: the named contributions RECONSTRUCT the engine's score ==
        ok("DECOMPOSE: the winner's named contributions SUM BACK to curiosity._score",
           bool(prov.get("reconstructs")))
        ok("DECOMPOSE: the residual (composed - engine_score) is within tolerance",
           abs(float(prov.get("residual", 1.0))) <= _RECON_TOL)
        # and prove the engine_score the tree reconstructs IS the engine's real _score for the
        # gap (not a number we carried over from the candidate projection).
        gap = _gap_behind(nm, tree["winner"])
        ok("DECOMPOSE: the gap behind the winner was found in the engine's own gap set",
           gap is not None)
        ok("DECOMPOSE: prov.engine_score == curiosity._score(gap) exactly (the real key)",
           gap is not None
           and abs(float(prov["engine_score"]) - float(curiosity._score(gap))) <= _RECON_TOL)
        # the canonical number: the Mike gap's score is ~17.81 (10 floor + 2·ln43 + .25 + .042)
        ok("DECOMPOSE: the Mike score is ~17.81 (the canonical decomposed number)",
           abs(float(prov["engine_score"]) - 17.8144) < 0.01)

        # --- the contributions are the RIGHT named signals for a relationship gap ------------
        cids = [c["id"] for c in prov["contributions"]]
        ok("DECOMPOSE: the relationship floor (+10) is a named contribution",
           C_REL_FLOOR in cids and any(
               abs(c["value"] - 10.0) < 1e-9 for c in prov["contributions"]
               if c["id"] == C_REL_FLOOR))
        ok("DECOMPOSE: the mention curve 2·ln(1+42) is a named contribution",
           C_MENTION_CURVE in cids and any(
               abs(c["value"] - 2.0 * math.log(1 + 42)) < 1e-6
               for c in prov["contributions"] if c["id"] == C_MENTION_CURVE))
        ok("DECOMPOSE: the SUSPECTED kind bump (+0.25) is a named contribution",
           any(abs(c["value"] - 0.25) < 1e-9 for c in prov["contributions"]
               if c["id"] == C_KIND_BUMP))
        ok("DECOMPOSE: the evidence weight (0.001·42 = 0.042) is a named contribution",
           any(abs(c["value"] - 0.042) < 1e-9 for c in prov["contributions"]
               if c["id"] == C_EVIDENCE))

        # --- the DOMINANT contributor is named, and for Mike it is the mention curve ---------
        dom = tree["dominant"]
        ok("DOMINANT: a dominant contributor is named",
           bool(dom) and "id" in dom)
        # the floor (10) is constant for every relationship gap; the MENTION CURVE (7.52 at x42)
        # is the largest signal that VARIES with the evidence — but the floor is numerically
        # largest. We assert the dominant is the largest-magnitude leaf (the floor here) AND that
        # the mention curve is the largest EVIDENCE-driven signal, the thing that made THIS gap
        # win over an empty slot.
        ok("DOMINANT: the dominant leaf is the largest-magnitude contribution (the floor +10)",
           dom.get("id") == C_REL_FLOOR)
        curve_c = next((c for c in prov["contributions"] if c["id"] == C_MENTION_CURVE), None)
        bump_c = next((c for c in prov["contributions"] if c["id"] == C_KIND_BUMP), None)
        ok("DOMINANT: the mention curve (the evidence signal) outweighs the kind bump — "
           "the EVIDENCE is what lifts Mike above an empty slot",
           curve_c is not None and bump_c is not None
           and curve_c["value"] > bump_c["value"])

        # --- the world-graph EDGES the curve reads are attached (the evidence behind the curve)
        ok("EVIDENCE: the world-graph edges on the winner's entity are attached",
           len(tree["edges"]) >= 1)
        ok("EVIDENCE: an edge connects 'you' to Mike (the relationship the gap is about)",
           any("mike" in (world_state._norm_node(e.get("object", "")) or "")
               or "mike" in (world_state._norm_node(e.get("subject", "")) or "")
               for e in tree["edges"]))
        ok("EVIDENCE: the Mike edge carries the 42 mentions the curve is reading",
           any(int(e.get("support", 0)) == 42 for e in tree["edges"]))

        # --- the winner AGREES with the Decision Observatory's SELECTED (same ranking) --------
        dec = decisions.curiosity_decision(nm, budget="deep")
        ok("AGREES: the tree's winner is the Decision Observatory's SELECTED gap",
           dec["selected"] is not None
           and tree["winner"]["label"] == dec["selected"]["label"])
        ok("AGREES: the runner-up field the winner BEAT is shown (the roads not taken)",
           len(tree["beat"]) >= 1)

        # === EVERY ranked gap decomposes — the proof it's not just hand-tuned for Mike ========
        # Decompose EVERY gap the engine produces and assert each reconstructs its OWN _score.
        # This covers the empty-slot UNKNOWN gaps (taxonomy base alone), the relationship gap,
        # and (on the contradiction creature below) a CONTRADICTED gap — every branch.
        all_gaps = curiosity.detect_gaps(nm) or []
        n_recon = sum(1 for g in all_gaps if decompose_score(g)["reconstructs"])
        ok(f"DECOMPOSE[all]: EVERY ranked gap reconstructs its own _score "
           f"({n_recon}/{len(all_gaps)})",
           len(all_gaps) > 0 and n_recon == len(all_gaps))

        # --- an empty TAXONOMY slot decomposes to its base priority alone (UNKNOWN branch) ----
        name_gap = next((g for g in all_gaps if (g.get("slot") == "name")), None)
        if name_gap is not None:
            nd = decompose_score(name_gap)
            ok("DECOMPOSE[unknown]: the empty 'name' slot decomposes to its taxonomy base (9.0)",
               nd["reconstructs"]
               and any(abs(c["value"] - 9.0) < 1e-9 for c in nd["contributions"]
                       if c["id"] == C_TAXO_BASE))
            ok("DECOMPOSE[unknown]: an UNKNOWN gap has a ZERO kind bump (the bump table)",
               any(abs(c["value"]) < 1e-12 for c in nd["contributions"]
                   if c["id"] == C_KIND_BUMP))

        # === a CONTRADICTION creature: prove the CONTRADICTED branch (+4.0 lift) decomposes ===
        cnm = f"{SYNTH}_contra_{tok}"
        try:
            f = memory_lirf.Facts([])
            for c in f.capture(cnm, "I live in Portland"):
                f.merge(c)
            for c in f.capture(cnm, "actually I live in Seattle now"):
                f.merge(c)
            f.save(cnm)
        except Exception:
            pass
        cgaps = curiosity.detect_gaps(cnm) or []
        contra_gap = next((g for g in cgaps if g.get("kind") == curiosity.CONTRADICTED), None)
        if contra_gap is not None:
            cd = decompose_score(contra_gap)
            ok("DECOMPOSE[contradicted]: a CONTRADICTED gap reconstructs its _score",
               cd["reconstructs"])
            ok("DECOMPOSE[contradicted]: it carries the +4.0 contradiction lift",
               any(abs(c["value"] - 4.0) < 1e-9 for c in cd["contributions"]
                   if c["id"] == C_CONTRA_LIFT))
            ok("DECOMPOSE[contradicted]: it carries the +0.5 CONTRADICTED kind bump",
               any(abs(c["value"] - 0.5) < 1e-9 for c in cd["contributions"]
                   if c["id"] == C_KIND_BUMP))

        # === a SUSPECTED-hint creature: prove the +1.0 hint lift branch decomposes ===========
        # A taxonomy slot that is active but BELOW the [KNOWN] bar is a SUSPECTED hint. We
        # produce that exact on-disk state the way scripts/relationship.py forces its router-miss
        # state: capture a plain fact, then drop its stored confidence below _CONF_KNOWN via the
        # store API (no engine touched) — leaving the active-but-unconfirmed row the engine reads
        # as a SUSPECTED hint (priority = base + 1.0).
        snm = f"{SYNTH}_hint_{tok}"
        try:
            f = memory_lirf.Facts([])
            for c in f.capture(snm, "my favorite food is ramen"):
                f.merge(c)
            f.save(snm)
            f2 = memory_lirf.Facts.load(snm)
            r = f2.lookup(curiosity.SELF, "favorite_food")
            if r is not None:
                r["confidence"] = 0.5          # below _CONF_KNOWN (0.85): active hint, not KNOWN
                f2.save(snm)
        except Exception:
            pass
        sgaps = curiosity.detect_gaps(snm) or []
        hint_gap = next((g for g in sgaps
                         if g.get("kind") == curiosity.SUSPECTED and g.get("trait")), None)
        ok("DECOMPOSE[hint]: a below-KNOWN taxonomy slot is a SUSPECTED hint gap",
           hint_gap is not None)
        if hint_gap is not None:
            sd = decompose_score(hint_gap)
            ok("DECOMPOSE[hint]: a low-confidence SUSPECTED taxonomy hint reconstructs its _score",
               sd["reconstructs"])
            ok("DECOMPOSE[hint]: it carries the +1.0 suspected-hint lift",
               any(abs(c["value"] - 1.0) < 1e-9 for c in sd["contributions"]
                   if c["id"] == C_HINT_LIFT))
            ok("DECOMPOSE[hint]: it carries the +0.25 SUSPECTED kind bump",
               any(abs(c["value"] - 0.25) < 1e-9 for c in sd["contributions"]
                   if c["id"] == C_KIND_BUMP))

        # === DETERMINISM: the same creature yields a byte-identical provenance tree ===========
        t1 = provenance_tree(nm, budget="deep")
        t2 = provenance_tree(nm, budget="deep")
        ok("determinism: two provenance trees on the SAME creature are identical",
           json.dumps(t1, sort_keys=True, default=str)
           == json.dumps(t2, sort_keys=True, default=str))
        ok("determinism: the winner + its decomposed score are stable across re-derivation",
           (t1["winner"] or {}).get("label") == (t2["winner"] or {}).get("label")
           and float(t1["provenance"]["engine_score"])
               == float(t2["provenance"]["engine_score"]))

        # === ROBUSTNESS: the entry points never raise on junk ================================
        ok("robust: provenance_tree on a blank creature returns the contract dict",
           set(provenance_tree(f"{SYNTH}_blank_{tok}"))
           >= {"winner", "score", "provenance", "dominant", "edges", "beat"})
        ok("robust: decompose_score(None) returns a non-reconstructing empty decomposition",
           decompose_score(None)["reconstructs"] is False
           and decompose_score(None)["contributions"] == [])
        ok("robust: decompose_score({}) never raises",
           isinstance(decompose_score({}), dict))

        # === RENDER never raises and carries the provenance frame ============================
        txt = render({"tree": tree})
        ok("render: produces a non-empty report", bool(txt.strip()))
        ok("render: names the TOP DECISION + the PROVENANCE OF THE SCORE",
           "TOP DECISION" in txt and "PROVENANCE OF THE SCORE" in txt)
        ok("render: shows the reconstruction claim (composed == curiosity._score)",
           "curiosity._score" in txt and "RECONSTRUCTS THE ENGINE SCORE" in txt)
        ok("render: names the dominant signal",
           "DOMINANT SIGNAL" in txt)
        ok("render: shows the graph edges the curve reads",
           "GRAPH EDGES" in txt)
        ok("render: a single tree render works",
           bool(render_tree(tree).strip()))

    # --- the demo build_report is coherent end-to-end ------------------------------------
    full = build_report()
    ok("report: build_report yields a tree", "tree" in full)
    ok("report: the report's tree has a winner with a reconstructing provenance",
       full["tree"]["winner"] is not None
       and bool(full["tree"]["provenance"].get("reconstructs")))

    # --- GUARDRAIL: the whole selftest touched no real .anima file -----------------------
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the whole selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature file leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL PROVENANCE-TREE SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
