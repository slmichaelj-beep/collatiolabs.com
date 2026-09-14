#!/usr/bin/env python3
"""VERA DECISION OBSERVATORY — the "WHY VIEWER" (Phase 3D): the roads NOT taken.

    Today we can see the path Vera CHOSE. This shows the paths she REJECTED — each with
    its score, its confidence, and the concrete reason it lost.

scripts/mri.py films a turn and, at the curiosity stage, records WHICH gap she asked. But
a single "selected" label hides the actual decision: of the whole ranked field of things
she could have wondered about, WHY did THIS one win and the others lose? A real decision is
the runner-up that scored 0.2 lower, the gap she already asked (Law 002), the fact she
already KNOWS (so it never even becomes a question), and the one the budget held back this
turn. This observatory re-derives that FULL ranked candidate set on a synthetic creature and
renders it as SELECTED vs REJECTED, every rejection carrying a machine-readable reason.

It covers the two observable decision points in the live system:

  1. CURIOSITY — "which gap to ask?" (the clearest one). The curiosity engine
     (anima/curiosity.py) ranks every knowledge GAP by signal strength; ``next_question``
     surfaces the TOP un-asked gap (budget permitting) and the rest are rejected. We re-run
     the engine's OWN ranking (``detect_gaps`` / ``candidate_gaps`` / ``_score`` /
     ``asked_keys`` / ``_is_known_row``) and attach, to each candidate,
     ``{score, confidence, reason, status}`` — where the REASON is exactly the engine's:
       * SELECTED          — the top-ranked un-asked gap the budget let through.
       * LOWER_RANK        — a real un-asked gap that simply scored below the winner.
       * ALREADY_ASKED     — surfaced before; Law 002 never re-asks it (it's in the ledger).
       * KNOWN_SUPPRESSED  — the slot's fact is already a confident KNOWN row, so the engine
                             produces NO gap for it at all. Shown EXPLICITLY as
                             rejected-because-known, never merely absent (Law 002: never
                             re-discover the known).
       * BUDGET_HELD       — it WAS the top gap, but the pacing budget kept curiosity silent
                             this turn (frequency, not content).
       * UNPHRASEABLE      — the gap could not be turned into a safe in-character question.

  2. PROACTIVE ASIDE — "which voice speaks the one aside?" (covered when observable). The
     live turn (anima/server.py) offers at most ONE gentle aside per casual turn, trying, in
     strict order, OPPORTUNITY > OPEN-LOOP > CURIOSITY — the first that fires wins; the rest
     are passed over. We re-derive that ladder in the same order and show which fired and
     which were passed over, each with the reason (fired / nothing-due / pre-empted by a
     higher tier / gated off).

GUARDRAILS (identical discipline to scripts/curiosity_quality.py + scripts/relationship.py):
  * STANDALONE + READ-ONLY on the engines. It IMPORTS and CALLS curiosity/opportunity/loops;
    it edits no module, no test, and not mouth.py / certify.py / conservation.py /
    isolation.py / counterfactual.py. The curiosity engine already exposes its ranked
    candidates (``candidate_gaps``/``detect_gaps``), so NO accessor was added to curiosity.py.
  * SYNTHETIC creatures + a HERMETIC temp store ONLY. Every STORE the decision derivation
    can touch is redirected to one TemporaryDirectory for the run — curiosity.STORE,
    memory_lirf.STORE (BOTH the __main__ and package bindings), constitution.STORE,
    reliability.DEFAULT_STORE, world_state/opportunity/loops/meaning/trajectory/reminders
    STORE — mirroring anima/memory_lirf.py's _selftest. The run ASSERTS the real .anima
    footprint is byte-UNCHANGED start->end. It NEVER reads or writes a real Vera.* file.
  * DETERMINISTIC + OFFLINE. No model, no network. (The curiosity engine's model-refine pass
    and LIRF's Tier-B are never invoked.) The ranking is deterministic for a fixed creature.
  * Never raises out of the entry points — a malformed creature yields an honest empty
    render, not a traceback.

    python3 scripts/decisions.py            # human-readable SELECTED vs REJECTED + the aside
    python3 scripts/decisions.py --json     # machine-readable
    python3 scripts/decisions.py --selftest  # prove the why-view is faithful + deterministic

Exit code is 0 on a default run / a passing selftest with the guardrail intact; non-zero
only on a broken guardrail (real .anima changed, or an engine raised inside the harness) or
a failed selftest assertion.
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

from anima import curiosity              # noqa: E402  the ranking + gap shape + KNOWN/asked bars
from anima import memory_lirf            # noqa: E402  the LIRF ledger = what is KNOWN (suppresses)

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "dec_synth"

# Machine-readable rejection reasons (the "why it lost"). Stable strings so a consumer (an
# MRI viewer, a test) can branch on them without parsing prose.
SELECTED = "SELECTED"
LOWER_RANK = "LOWER_RANK"
ALREADY_ASKED = "ALREADY_ASKED"
KNOWN_SUPPRESSED = "KNOWN_SUPPRESSED"
BUDGET_HELD = "BUDGET_HELD"
UNPHRASEABLE = "UNPHRASEABLE"

# One-line human gloss for each reason — what to SHOW next to a rejected candidate.
REASON_GLOSS = {
    SELECTED: "chosen — the top-ranked gap the budget let through",
    LOWER_RANK: "scored below the selected gap this turn",
    ALREADY_ASKED: "already asked before — Law 002 never re-asks it",
    KNOWN_SUPPRESSED: "already a confident KNOWN fact — never re-discovered (Law 002)",
    BUDGET_HELD: "was the top gap, but the pacing budget kept curiosity silent this turn",
    UNPHRASEABLE: "could not be phrased as a safe in-character question",
}


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect mirroring anima/memory_lirf.py _selftest
# (~1316-1340): redirect EVERY store the decision derivation can touch into ONE throwaway
# dir, including memory_lirf.STORE on BOTH the __main__ and package bindings (under
# `python3 -m` they are distinct objects). Plus a footprint hash to PROVE nothing real moved.
# ===================================================================================
# (module dotted-path, STORE attribute name). curiosity writes its Asked Ledger to
# curiosity.STORE; it reads LIRF facts via memory_lirf (memory_lirf.STORE), whose load path
# also writes a continuity ledger (constitution.STORE) + guarded backups
# (reliability.DEFAULT_STORE); the aside ladder reads world_state/opportunity/loops/meaning/
# trajectory/reminders. Redirecting all of them is the only way a synthetic creature is fully
# isolated regardless of which leg of the derivation runs.
_STORE_TARGETS = (
    ("anima.curiosity", "STORE"),
    ("anima.memory_lirf", "STORE"),
    ("anima.constitution", "STORE"),
    ("anima.reliability", "DEFAULT_STORE"),
    ("anima.world_state", "STORE"),
    ("anima.opportunity", "STORE"),
    ("anima.loops", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.trajectory", "STORE"),
    ("anima.reminders", "STORE"),
)


def _store_modules():
    """Resolve the (module, attr) redirect targets that import cleanly. Includes BOTH the
    package ``anima.memory_lirf`` AND the currently-executing module if this file were ever
    run as the package's __main__ — but here memory_lirf is always imported, so we also fold
    in ``sys.modules['anima.curiosity']`` / ``['anima.memory_lirf']`` explicitly to be safe
    against the dual-binding trap the memory_lirf self-test warns about."""
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
    # the dual-binding guard: ensure the *exact objects* this file holds (curiosity,
    # memory_lirf) are redirected even if their dotted import returned a different copy.
    for mod, attr in ((curiosity, "STORE"), (memory_lirf, "STORE")):
        key = (id(mod), attr)
        if key not in seen and getattr(mod, attr, None) is not None:
            out.append((mod, attr))
            seen.add(key)
    return out


@contextlib.contextmanager
def _temp_store():
    """Redirect every resolved STORE target to one fresh temp dir for the duration, then
    restore. Nothing under the real .anima/ is read or written while this is active."""
    targets = _store_modules()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-decisions-") as td:
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
    which legitimately changes) so we can PROVE the harness touched nothing."""
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
# CONFIDENCE — a single 0..1 number per candidate, derived from the engine's OWN state so it
# can never drift. For a candidate that maps to a stored LIRF row (a SUSPECTED hint, a
# KNOWN-suppressed slot) it is that row's confidence; for a pure UNKNOWN/relationship gap
# (nothing on disk) there is no stored confidence, so we surface the engine's RANK signal as
# a normalised proxy — higher score == the engine is more sure this is worth asking. The two
# are labelled distinctly in the render so a reader never confuses "fact confidence" with
# "worth-asking confidence".
# ===================================================================================
def _row_confidence(name: str, trait: str):
    """The stored LIRF confidence for SELF/``trait`` (0..1), or None if there is no row.
    Read-only; reuses the engine's own salience-sorted view so it matches what suppresses
    the gap."""
    if not trait:
        return None
    try:
        facts = memory_lirf.Facts.load(name)
        known = curiosity._known_traits(facts)
    except Exception:
        return None
    row = known.get(curiosity.canon_trait(trait))
    if not isinstance(row, dict):
        return None
    try:
        return float(row.get("confidence", 0.0))
    except (TypeError, ValueError):
        return None


def _rank_confidence(score: float, top_score: float) -> float:
    """A normalised 'worth-asking' confidence in [0,1] from a gap's rank score, relative to
    the strongest gap this turn. Pure + deterministic; only a presentation proxy for gaps
    with no stored fact confidence (an empty slot, an unknown relationship)."""
    if top_score <= 0:
        return 0.0
    return max(0.0, min(1.0, float(score) / float(top_score)))


# ===================================================================================
# THE CURIOSITY DECISION — re-derive the FULL ranked candidate field + SELECTED/REJECTED.
# ===================================================================================
def curiosity_decision(name: str, *, budget: str = "deep",
                       recent_text=None) -> dict:
    """Re-derive curiosity's "which gap to ask?" decision for ``name`` as SELECTED vs
    REJECTED, each candidate carrying ``{score, confidence, reason, status, question}``.

    The candidate field is the UNION of:
      * every OPEN gap (``candidate_gaps`` — detected AND not yet asked), ranked by the
        engine's own ``_score``; the top one the budget lets through is SELECTED, the rest
        are LOWER_RANK (or BUDGET_HELD, if the top gap itself was held);
      * every ALREADY-ASKED gap (a gap whose key is in the Asked Ledger) — shown as a
        rejected candidate with reason ALREADY_ASKED (Law 002), so the road not-taken is
        VISIBLE, not silently gone;
      * every KNOWN-SUPPRESSED taxonomy slot (a slot whose fact is a confident KNOWN row, so
        the engine produces NO gap) — shown as a rejected candidate with reason
        KNOWN_SUPPRESSED, so 'already known' is rendered explicitly, never merely absent.

    Deterministic for a fixed creature (the engine's ranking is a pure total order, and the
    budget gate is a deterministic per-(name,gap) draw). Read-only; never raises."""
    out = {
        "name": name, "budget": budget, "decision": "curiosity:which gap to ask",
        "selected": None, "rejected": [], "candidates": [],
    }
    try:
        open_gaps = curiosity.candidate_gaps(name) or []      # detected AND un-asked, ranked
    except Exception:
        open_gaps = []
    try:
        all_gaps = curiosity.detect_gaps(name) or []          # detected (KNOWN already removed)
    except Exception:
        all_gaps = []
    try:
        asked = curiosity.asked_keys(name) or set()
    except Exception:
        asked = set()

    # The engine's score for ranking + the top score for the rank-confidence proxy.
    def _score(g):
        try:
            return float(curiosity._score(g))
        except Exception:
            return float(g.get("priority", 0.0)) if isinstance(g, dict) else 0.0

    top_score = max((_score(g) for g in open_gaps), default=0.0)

    # Which open gap (if any) does next_question ACTUALLY surface under this budget? That is
    # the ground-truth SELECTED — we ask the engine, never re-implement the budget gate.
    try:
        sel_question = curiosity.next_question(name, recent_text=recent_text, budget=budget)
    except Exception:
        sel_question = None
    # The top open gap is the one next_question considers first.
    top_gap = open_gaps[0] if open_gaps else None
    # next_question stashes the rendered question on the gap it chose; match by that.
    selected_key = None
    if sel_question and top_gap is not None:
        selected_key = curiosity._gap_key(top_gap)

    def _candidate(g, *, status, reason, score=None):
        sc = _score(g) if score is None else score
        trait = g.get("trait", "") if isinstance(g, dict) else ""
        fact_conf = _row_confidence(name, trait)
        conf = fact_conf if fact_conf is not None else _rank_confidence(sc, top_score)
        try:
            q = curiosity.generate_question(g) if isinstance(g, dict) else ""
        except Exception:
            q = ""
        return {
            "label": _gap_label(g),
            "slot": g.get("slot", "") if isinstance(g, dict) else "",
            "kind": g.get("kind", "") if isinstance(g, dict) else "",
            "score": round(float(sc), 4),
            "confidence": round(float(conf), 4),
            "confidence_kind": ("fact" if fact_conf is not None else "worth_asking"),
            "status": status,
            "reason": reason,
            "reason_gloss": REASON_GLOSS.get(reason, reason),
            "question": q,
            "gap_key": curiosity._gap_key(g) if isinstance(g, dict) else "",
        }

    candidates = []

    # --- the OPEN gaps (ranked). Top one is SELECTED iff next_question surfaced it; else the
    #     top was BUDGET_HELD and everything is rejected. Runners-up are LOWER_RANK. --------
    for i, g in enumerate(open_gaps):
        if i == 0:
            if sel_question:
                c = _candidate(g, status="selected", reason=SELECTED)
                # carry the EXACT question the engine chose (post-bias/safe-fallback)
                c["question"] = sel_question
                out["selected"] = c
            else:
                # the top gap exists but the budget held curiosity silent this turn
                c = _candidate(g, status="rejected", reason=BUDGET_HELD)
                out["rejected"].append(c)
        else:
            c = _candidate(g, status="rejected", reason=LOWER_RANK)
            out["rejected"].append(c)
        candidates.append(c)

    # --- the ALREADY-ASKED gaps (Law 002): detected, but their key is in the ledger. Render
    #     them as rejected candidates so the road not-taken is visible, not silently absent. -
    open_keys = {curiosity._gap_key(g) for g in open_gaps}
    for g in all_gaps:
        k = curiosity._gap_key(g)
        if k in asked and k not in open_keys:
            c = _candidate(g, status="rejected", reason=ALREADY_ASKED)
            out["rejected"].append(c)
            candidates.append(c)

    # --- the KNOWN-SUPPRESSED slots: a confident KNOWN fact means the engine produces NO gap.
    #     Surface each explicitly as rejected-because-known (NOT merely absent). -------------
    for c in _known_suppressed_candidates(name):
        out["rejected"].append(c)
        candidates.append(c)

    out["candidates"] = candidates
    return out


def _known_suppressed_candidates(name: str) -> list:
    """For every TAXONOMY slot whose canonical trait is a confident KNOWN row for SELF, build
    a rejected-because-known candidate. This is what makes 'already known' VISIBLE in the
    why-view rather than an unexplained absence. Uses the engine's OWN ``_is_known_row`` bar
    (the same bar that suppresses the gap), so a slot shown here is exactly one the engine
    would refuse to ask. Read-only; never raises."""
    out = []
    try:
        facts = memory_lirf.Facts.load(name)
        known = curiosity._known_traits(facts)
    except Exception:
        return out
    seen_slots = set()
    for (cat, slot, trait, _base) in curiosity.TAXONOMY:
        if slot in seen_slots:
            continue
        seen_slots.add(slot)
        ctrait = curiosity.canon_trait(trait)
        row = known.get(ctrait)
        try:
            is_known = curiosity._is_known_row(row)
        except Exception:
            is_known = False
        if not is_known:
            continue
        try:
            conf = float(row.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        out.append({
            "label": f"you:{slot}",
            "slot": slot,
            "kind": curiosity.KNOWN,
            "score": 0.0,            # a known slot is not ranked — it never enters the race
            "confidence": round(conf, 4),
            "confidence_kind": "fact",
            "status": "rejected",
            "reason": KNOWN_SUPPRESSED,
            "reason_gloss": REASON_GLOSS[KNOWN_SUPPRESSED],
            "question": "",          # by construction the engine phrases NO question for it
            "gap_key": slot,
            "known_value": curiosity._fmt_value(row.get("value", "")),
        })
    return out


def _gap_label(g) -> str:
    """A compact 'entity:slot' label for a gap, mirroring server.py's MRI ``_gap_label`` so
    the observatory's labels match the live trace's."""
    if not isinstance(g, dict):
        return str(g)[:60]
    return (g.get("entity") or "you") + ":" + (g.get("slot") or g.get("trait") or "?")


# ===================================================================================
# THE PROACTIVE-ASIDE DECISION — re-derive server.py's OPPORTUNITY > OPEN-LOOP > CURIOSITY
# ladder in the SAME order. The first tier that produces a line FIRES; the lower tiers are
# PASSED OVER (pre-empted). A tier that produces nothing is 'nothing due'. Read-only — we do
# NOT call mark_offered / mark_resurfaced / mark_asked (no ledger writes; pure observation).
# ===================================================================================
_ASIDE_TIERS = ("opportunity", "open-loop", "curiosity")


def aside_decision(name: str, *, recent_text=None, budget: str = "deep") -> dict:
    """Re-derive 'which voice speaks the one aside?' as SELECTED vs PASSED-OVER, in the live
    order OPPORTUNITY > OPEN-LOOP > CURIOSITY. Each tier carries its line (if any) and the
    reason it fired / was passed over / found nothing due. Read-only; never raises.

    Mirrors anima/server.py's aside block ordering exactly, but writes NO ledger (it does not
    call mark_offered/mark_resurfaced/mark_asked), so it is pure observation."""
    out = {"name": name, "decision": "aside:which voice speaks",
           "selected": None, "tiers": []}

    # tier 1 — OPPORTUNITY ("want me to…?", a grounded optional OFFER).
    opp_line = _safe_call("opportunity", "next_opportunity", name, budget=budget)
    # tier 2 — OPEN-LOOP (resurface a stalled commitment, "you wanted X — still?").
    loop_line = _safe_call("loops", "resurface", name, budget=budget)
    # tier 3 — CURIOSITY (a contextual question, Law 002).
    try:
        cur_line = curiosity.next_question(name, recent_text=recent_text, budget=budget)
    except Exception:
        cur_line = None

    lines = {"opportunity": opp_line, "open-loop": loop_line, "curiosity": cur_line}

    fired = None
    for tier in _ASIDE_TIERS:
        line = lines.get(tier)
        has = bool(line and str(line).strip())
        if fired is None and has:
            status, reason = "FIRED", "highest tier with something to say — speaks the aside"
            fired = tier
        elif fired is not None and has:
            status, reason = ("PASSED_OVER",
                              f"had something to say, but '{fired}' (a higher tier) already fired")
        elif fired is None and not has:
            status, reason = "NOTHING_DUE", "nothing grounded/due at this tier this turn"
        else:  # fired is not None and not has
            status, reason = "NOTHING_DUE", "nothing due at this tier (a higher tier fired anyway)"
        row = {"tier": tier, "status": status, "reason": reason,
               "line": (str(line).strip() if has else None)}
        out["tiers"].append(row)
        if status == "FIRED":
            out["selected"] = row
    return out


def _safe_call(mod_name: str, fn_name: str, name: str, **kw):
    """Call ``anima.<mod>.<fn>(name, **kw)`` if importable; return its result or None on any
    failure. Used so the aside ladder degrades gracefully if a tier's engine isn't built."""
    try:
        mod = __import__("anima." + mod_name, fromlist=[fn_name])
        fn = getattr(mod, fn_name, None)
        if not callable(fn):
            return None
        return fn(name, **kw)
    except Exception:
        return None


# ===================================================================================
# SYNTHETIC CREATURE — seed a deterministic creature whose curiosity decision is RICH:
# a high-mention unknown person (the canonical 'Mike' — the top gap), a confident KNOWN
# fact (so a slot is KNOWN-SUPPRESSED), an already-asked gap (so Law 002 shows a rejection),
# and the empty taxonomy slots (the LOWER_RANK field). All writes land in the temp store.
# ===================================================================================
def seed_demo_creature(name: str) -> None:
    """Seed one synthetic creature end-to-end inside the (already-redirected) temp store:

      * KNOWN birthday   — captured + corroborated to a confident KNOWN fact -> the birthday
                           slot is KNOWN-SUPPRESSED (rejected-because-known, never asked).
      * high-mention Mike — 42 unknown-relationship mentions -> the canonical SUSPECTED gap,
                           the engine's top-ranked candidate (the SELECTED, at deep budget).
      * an already-asked 'occupation' gap -> a rejected ALREADY_ASKED candidate (Law 002).
      * the remaining empty slots -> the LOWER_RANK runner-up field.

    Deterministic; offline; writes only to the redirected stores. Tolerant of an engine that
    isn't built (it simply seeds fewer signals)."""
    # KNOWN birthday (confident -> suppresses the birthday gap).
    try:
        f = memory_lirf.Facts([])
        for c in f.capture(name, "my birthday is June 12"):
            f.merge(c)
        for c in f.capture(name, "yep, June 12 is my birthday"):
            f.merge(c)
        f.save(name)
    except Exception:
        pass
    # high-mention unknown 'Mike' (the top SUSPECTED gap).
    try:
        from anima import world_state as _ws
        w = _ws.World([])
        for _ in range(42):
            w.add("you", "knows", "Mike", kind="relationship")
        w.save(name)
    except Exception:
        pass
    # an already-asked 'occupation' gap (Law 002 -> ALREADY_ASKED rejection).
    try:
        gap = {
            "category": curiosity._SLOT_CATEGORY.get("occupation", "work"),
            "slot": "occupation", "kind": curiosity.UNKNOWN,
            "trait": curiosity.canon_trait("occupation"), "entity": curiosity.SELF,
            "evidence": {"mentions": 0, "source": ""},
            "_question": "(synthetic) what do you do for work?",
        }
        curiosity.mark_asked(name, gap)
    except Exception:
        pass


# ===================================================================================
# RENDER — human-readable SELECTED vs REJECTED, plus the aside ladder.
# ===================================================================================
def _conf_tag(c: dict) -> str:
    kind = c.get("confidence_kind", "worth_asking")
    return f"{c.get('confidence', 0.0):.2f} {('fact-conf' if kind == 'fact' else 'worth-asking')}"


def render_curiosity(dec: dict) -> str:
    out = []
    out.append(f'DECISION: {dec.get("decision")}   (creature: {dec.get("name")}, '
               f'budget: {dec.get("budget")})')
    sel = dec.get("selected")
    if sel:
        out.append("")
        out.append(f'  SELECTED  ->  {sel["label"]}   '
                   f'[score {sel["score"]:.3f} · conf {_conf_tag(sel)}]')
        out.append(f'      reason : {sel["reason"]} — {sel["reason_gloss"]}')
        if sel.get("question"):
            out.append(f'      asks   : "{sel["question"]}"')
    else:
        out.append("")
        out.append("  SELECTED  ->  (none — curiosity stayed silent this turn)")
    rej = dec.get("rejected") or []
    out.append("")
    out.append(f"  REJECTED  ({len(rej)} roads not taken):")
    if not rej:
        out.append("      (none)")
    for c in rej:
        head = (f'    · {c["label"]:<26} [score {c["score"]:.3f} · conf {_conf_tag(c)}]  '
                f'{c["reason"]}')
        out.append(head)
        out.append(f'        why: {c["reason_gloss"]}')
        if c.get("reason") == KNOWN_SUPPRESSED and c.get("known_value"):
            out.append(f'        known: "{c["known_value"]}"  (so it is never asked)')
        elif c.get("question"):
            out.append(f'        would have asked: "{c["question"]}"')
    return "\n".join(out)


def render_aside(dec: dict) -> str:
    out = []
    out.append(f'DECISION: {dec.get("decision")}   (creature: {dec.get("name")})')
    out.append("  ladder: OPPORTUNITY  >  OPEN-LOOP  >  CURIOSITY   (first to fire wins)")
    sel = dec.get("selected")
    out.append("")
    if sel:
        out.append(f'  SELECTED  ->  {sel["tier"].upper()} fired the aside')
        if sel.get("line"):
            out.append(f'      says: "{sel["line"]}"')
    else:
        out.append("  SELECTED  ->  (no aside this turn — every tier had nothing due)")
    out.append("")
    out.append("  the full ladder:")
    for row in dec.get("tiers", []):
        mark = {"FIRED": "==>", "PASSED_OVER": "   ", "NOTHING_DUE": "   "}.get(row["status"], "   ")
        out.append(f'  {mark} {row["tier"].upper():<12} {row["status"]:<12} — {row["reason"]}')
        if row.get("line"):
            out.append(f'          line: "{row["line"]}"')
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 88)
    out.append("VERA DECISION OBSERVATORY — the WHY VIEWER (Phase 3D): the roads NOT taken")
    out.append("We can see the path she CHOSE. This shows the paths she REJECTED — each with")
    out.append("its score, its confidence, and the concrete reason it lost.")
    out.append("=" * 88)
    out.append("")
    out.append("-" * 88)
    out.append("DECISION POINT 1 — CURIOSITY: which gap to ask?  (the clearest decision)")
    out.append("-" * 88)
    out.append(render_curiosity(report["curiosity"]))
    out.append("")
    out.append("-" * 88)
    out.append("DECISION POINT 2 — PROACTIVE ASIDE: which voice speaks the one aside?")
    out.append("-" * 88)
    out.append(render_aside(report["aside"]))
    out.append("")
    out.append("-" * 88)
    out.append("REJECTION VOCABULARY (every rejected candidate carries one machine-readable reason)")
    out.append("-" * 88)
    for r in (SELECTED, LOWER_RANK, ALREADY_ASKED, KNOWN_SUPPRESSED, BUDGET_HELD, UNPHRASEABLE):
        out.append(f"  {r:<18} {REASON_GLOSS[r]}")
    out.append("")
    out.append("WIRING NOTE: this re-derives the SAME ranking the live curiosity stage uses")
    out.append("(anima/curiosity.candidate_gaps/detect_gaps/_score) and the SAME aside ladder")
    out.append("anima/server.py runs (opportunity > loop > curiosity). The MRI's")
    out.append('alternative(\"curiosity:which gap to surface\") records the selected+rejected')
    out.append("for a REAL turn; this observatory shows the FULL field for a synthetic one,")
    out.append("with the reason each loser lost. No engine was changed to build it.")
    return "\n".join(out)


# ===================================================================================
# THE DEMO REPORT — seed one rich synthetic creature, derive both decisions, render.
# ===================================================================================
def build_report() -> dict:
    """Seed one synthetic creature in a hermetic temp store and derive BOTH decisions on it.
    Deterministic + offline + isolated. Returns the full report dict."""
    with _temp_store():
        name = f"{SYNTH}_{secrets.token_hex(3)}"
        seed_demo_creature(name)
        cur = curiosity_decision(name, budget="deep")
        asi = aside_decision(name, budget="deep")
    return {"curiosity": cur, "aside": asi}


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA DECISION OBSERVATORY (the WHY VIEWER: SELECTED vs REJECTED, with reasons)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    try:
        report = build_report()
        engine_error = None
    except Exception as e:                       # pragma: no cover - entry point never raises
        report = {"curiosity": {"selected": None, "rejected": [], "candidates": []},
                  "aside": {"selected": None, "tiers": []}}
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
# SELFTEST — `python3 scripts/decisions.py --selftest`. Proves the why-view is FAITHFUL:
#   * the SELECTED == the engine's top-ranked open gap (next_question's choice);
#   * EVERY rejected candidate carries a concrete machine-readable reason;
#   * a KNOWN/suppressed gap is shown as rejected-because-known (NOT merely absent);
#   * the ranking is DETERMINISTIC for a fixed creature;
#   * (aside) the ladder fires the highest tier with something to say, lower tiers passed over;
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

        # === a RICH creature: KNOWN birthday + 42-mention Mike + asked occupation =========
        nm = f"{SYNTH}_rich_{tok}"
        seed_demo_creature(nm)
        dec = curiosity_decision(nm, budget="deep")

        # --- SELECTED == the engine's top-ranked OPEN gap (next_question's actual choice) --
        open_gaps = curiosity.candidate_gaps(nm)
        top_label = _gap_label(open_gaps[0]) if open_gaps else None
        ok("selected: there IS a selection on a creature with open gaps",
           dec["selected"] is not None)
        ok("selected: the SELECTED candidate == the engine's top-ranked open gap",
           dec["selected"] is not None and dec["selected"]["label"] == top_label)
        ok("selected: at deep budget the top gap is the canonical high-mention 'Mike'",
           dec["selected"] is not None and "mike" in dec["selected"]["label"].lower())
        ok("selected: the selected reason is SELECTED",
           dec["selected"] and dec["selected"]["reason"] == SELECTED)
        ok("selected: it carries the actual question text (what she'd ask)",
           dec["selected"] and "Mike" in (dec["selected"].get("question") or ""))

        # --- the selected score is the MAX over all open candidates (it really won) --------
        open_scores = [c["score"] for c in dec["candidates"]
                       if c["reason"] in (SELECTED, LOWER_RANK, BUDGET_HELD)]
        ok("selected: the winner's score is >= every other open candidate's score",
           dec["selected"] is not None
           and all(dec["selected"]["score"] >= s - 1e-9 for s in open_scores))

        # --- EVERY rejected candidate carries a concrete machine-readable reason -----------
        rej = dec["rejected"]
        ok("rejected: there ARE rejected candidates (the roads not taken are shown)",
           len(rej) > 0)
        valid_reasons = {LOWER_RANK, ALREADY_ASKED, KNOWN_SUPPRESSED, BUDGET_HELD, UNPHRASEABLE}
        ok("rejected: EVERY rejected candidate carries a known machine-readable reason",
           all(c.get("reason") in valid_reasons for c in rej))
        ok("rejected: every rejected candidate carries score + confidence + gloss",
           all(("score" in c and "confidence" in c and c.get("reason_gloss")) for c in rej))

        # --- a KNOWN/suppressed gap is shown as rejected-because-known (NOT merely absent) --
        known_rej = [c for c in rej if c["reason"] == KNOWN_SUPPRESSED]
        ok("KNOWN: the confident-KNOWN birthday is shown as a REJECTED candidate",
           any(c["slot"] == "birthday" for c in known_rej))
        bday = next((c for c in known_rej if c["slot"] == "birthday"), None)
        ok("KNOWN: it is rejected-because-known (reason KNOWN_SUPPRESSED), not absent",
           bday is not None and bday["reason"] == KNOWN_SUPPRESSED)
        ok("KNOWN: a known slot carries NO question (the engine never phrases one)",
           bday is not None and not bday.get("question"))
        ok("KNOWN: it surfaces the known value + a fact-confidence above the [KNOWN] bar",
           bday is not None and bool(bday.get("known_value"))
           and bday["confidence"] >= curiosity._CONF_KNOWN and bday["confidence_kind"] == "fact")
        # and prove it is NOT in the open candidate field (the engine produced no gap for it)
        ok("KNOWN: the known birthday is absent from the OPEN gap field (engine suppressed it)",
           all("birthday" != (g.get("slot") or "") for g in curiosity.candidate_gaps(nm)))

        # --- an ALREADY-ASKED gap (occupation) is shown as a rejected ALREADY_ASKED road ---
        asked_rej = [c for c in rej if c["reason"] == ALREADY_ASKED]
        ok("LAW 002: the already-asked 'occupation' gap is shown as a rejected candidate",
           any(c["slot"] == "occupation" for c in asked_rej))
        ok("LAW 002: its reason is ALREADY_ASKED (Law 002 never re-asks)",
           all(c["reason"] == ALREADY_ASKED for c in asked_rej))
        ok("LAW 002: the asked 'occupation' is NOT in the open candidate field",
           all("occupation" != (g.get("slot") or "") for g in curiosity.candidate_gaps(nm)))

        # --- there are LOWER_RANK runners-up (the empty-slot field that lost on score) -----
        ok("LOWER_RANK: there are runner-up gaps rejected purely for scoring lower",
           any(c["reason"] == LOWER_RANK for c in rej))

        # --- DETERMINISM: the same creature yields byte-identical curiosity decisions ------
        d1 = curiosity_decision(nm, budget="deep")
        d2 = curiosity_decision(nm, budget="deep")
        ok("determinism: two derivations on the SAME creature are identical",
           json.dumps(d1, sort_keys=True, default=str)
           == json.dumps(d2, sort_keys=True, default=str))
        ok("determinism: the selected label is stable across re-derivation",
           (d1["selected"] or {}).get("label") == (d2["selected"] or {}).get("label"))
        ok("determinism: the rejected set (labels+reasons) is stable across re-derivation",
           [(c["label"], c["reason"]) for c in d1["rejected"]]
           == [(c["label"], c["reason"]) for c in d2["rejected"]])

        # --- BUDGET_HELD: a budget that holds the top gap silent -> the top gap is rejected
        #     with reason BUDGET_HELD (still a candidate, never silently vanished). On a
        #     fresh single-strong-gap creature, find a name where minimal stays silent. ------
        held_seen = False
        for i in range(80):
            bn = f"{SYNTH}_held_{tok}_{i}"
            # a blank creature has the empty-taxonomy UNKNOWN gaps; minimal often holds them.
            if curiosity.next_question(bn, budget="minimal") is None and curiosity.candidate_gaps(bn):
                bd = curiosity_decision(bn, budget="minimal")
                if bd["selected"] is None and any(c["reason"] == BUDGET_HELD for c in bd["rejected"]):
                    held_seen = True
                    # the held candidate is the engine's top open gap, just silenced this turn
                    top = curiosity.candidate_gaps(bn)[0]
                    held = next(c for c in bd["rejected"] if c["reason"] == BUDGET_HELD)
                    ok("BUDGET_HELD: the held candidate is the engine's TOP open gap",
                       held["label"] == _gap_label(top))
                    break
        ok("BUDGET_HELD: a budget that silences the top gap shows it as rejected (not absent)",
           held_seen)

        # === the ASIDE ladder: opportunity > open-loop > curiosity ========================
        # On the RICH creature, the 42-mention 'Mike' is BOTH a curiosity gap AND an
        # opportunity (an UNEXPLAINED_ENTITY: "you bring that up a lot — want me to…?"). The
        # higher OPPORTUNITY tier therefore FIRES and the CURIOSITY tier is PRE-EMPTED — which
        # is exactly the live precedence (server.py: opportunity > loop > curiosity). This is
        # the canonical "show which fired and which were passed over, with the reason" case.
        asi = aside_decision(nm, budget="deep")
        ok("aside: exactly one tier fires",
           sum(1 for t in asi["tiers"] if t["status"] == "FIRED") == 1)
        fired = [t for t in asi["tiers"] if t["status"] == "FIRED"]
        ok("aside: the OPPORTUNITY tier fires (Mike is an unexplained-entity offer)",
           len(fired) == 1 and fired[0]["tier"] == "opportunity")
        cur_tier = next(t for t in asi["tiers"] if t["tier"] == "curiosity")
        ok("aside: CURIOSITY is PASSED_OVER — it HAD a line but a higher tier pre-empted it",
           cur_tier["status"] == "PASSED_OVER" and bool(cur_tier.get("line")))
        ok("aside: the passed-over curiosity reason names the higher tier that won",
           "opportunity" in cur_tier["reason"])
        ok("aside: the fired tier carries the spoken line",
           asi["selected"] is not None and bool(asi["selected"].get("line")))
        ok("aside: every tier carries a status + a reason",
           all(t.get("status") and t.get("reason") for t in asi["tiers"]))
        # ladder ORDER is the live order (opportunity, open-loop, curiosity)
        ok("aside: the ladder is rendered in the live order opportunity > open-loop > curiosity",
           [t["tier"] for t in asi["tiers"]] == list(_ASIDE_TIERS))
        # determinism of the aside, too
        a2 = aside_decision(nm, budget="deep")
        ok("aside: the ladder decision is deterministic for a fixed creature",
           json.dumps(asi, sort_keys=True, default=str)
           == json.dumps(a2, sort_keys=True, default=str))

        # --- a creature where CURIOSITY is the one that fires (opp/loop have nothing due) ---
        # A KNOWN birthday alone seeds an empty-slot curiosity gap but NO opportunity (no
        # high-mention entity, no stalled loop) -> the lower CURIOSITY tier is the first with
        # something to say, so it fires. Proves the ladder isn't hard-wired to opportunity.
        cur_nm = f"{SYNTH}_curfire_{tok}"
        try:
            f = memory_lirf.Facts([])
            for c in f.capture(cur_nm, "my birthday is June 12"):
                f.merge(c)
            for c in f.capture(cur_nm, "yep, June 12 is my birthday"):
                f.merge(c)
            f.save(cur_nm)
        except Exception:
            pass
        casi = aside_decision(cur_nm, budget="deep")
        cfired = [t for t in casi["tiers"] if t["status"] == "FIRED"]
        ok("aside[curfire]: with no opportunity/loop due, the CURIOSITY tier fires",
           len(cfired) == 1 and cfired[0]["tier"] == "curiosity")
        ok("aside[curfire]: the higher tiers are NOTHING_DUE (nothing grounded at them)",
           all(t["status"] == "NOTHING_DUE"
               for t in casi["tiers"] if t["tier"] in ("opportunity", "open-loop")))

        # === a BLANK creature: a clean, honest decision (no known, no asked, ranked field) =
        blank = f"{SYNTH}_blank_{tok}"
        bdec = curiosity_decision(blank, budget="deep")
        ok("blank: a never-seen creature still produces a ranked candidate field",
           len(bdec["candidates"]) > 0)
        ok("blank: a blank creature has a selection (an empty-slot gap) or honest silence",
           bdec["selected"] is not None or bdec["candidates"])
        ok("blank: NO known-suppressed candidates on a creature with nothing known",
           not any(c["reason"] == KNOWN_SUPPRESSED for c in bdec["rejected"]))
        ok("blank: NO already-asked candidates on a creature that asked nothing",
           not any(c["reason"] == ALREADY_ASKED for c in bdec["rejected"]))

        # --- robustness: the entry points never raise on junk ------------------------------
        ok("robust: curiosity_decision on a blank creature returns the contract dict",
           set(curiosity_decision(f"{SYNTH}_x_{tok}")) >= {"selected", "rejected", "candidates"})
        ok("robust: aside_decision on a blank creature returns the contract dict",
           set(aside_decision(f"{SYNTH}_y_{tok}")) >= {"selected", "tiers"})

        # --- render never raises and carries the SELECTED/REJECTED frame -------------------
        rep = {"curiosity": dec, "aside": asi}
        txt = render(rep)
        ok("render: produces a non-empty report", bool(txt.strip()))
        ok("render: names both SELECTED and REJECTED", "SELECTED" in txt and "REJECTED" in txt)
        ok("render: shows the rejection vocabulary (every reason is documented)",
           all(r in txt for r in (LOWER_RANK, ALREADY_ASKED, KNOWN_SUPPRESSED, BUDGET_HELD)))
        ok("render: the aside ladder is shown (opportunity > open-loop > curiosity)",
           "OPPORTUNITY" in txt and "OPEN-LOOP" in txt and "CURIOSITY" in txt)
        ok("render: a single-decision render works",
           bool(render_curiosity(dec).strip()) and bool(render_aside(asi).strip()))

    # --- the demo build_report is coherent end-to-end ----------------------------------
    full = build_report()
    ok("report: build_report yields both decisions",
       "curiosity" in full and "aside" in full)
    ok("report: the report's curiosity decision has a SELECTED + REJECTED set",
       full["curiosity"]["selected"] is not None and len(full["curiosity"]["rejected"]) > 0)

    # --- GUARDRAIL: the whole selftest touched no real .anima file ---------------------
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the whole selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature file leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL DECISION-OBSERVATORY SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
