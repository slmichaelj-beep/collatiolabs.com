#!/usr/bin/env python3
"""VERA CAUSAL OBSERVATORY — Layer 3, "fMRI: activity, not anatomy".

scripts/mri.py is the ANATOMY: it films EVERY stage a turn passes through, in order, as a
strip of frames. The Decision Observatory (scripts/decisions.py) is the FIRST organ of this
layer — it shows, for ONE decision point (curiosity), WHICH gap won and which lost. The
CAUSAL OBSERVATORY is the rest of the fMRI: for a whole TURN it shows the BROADER reasoning
COMPETITION — which SUBSYSTEMS competed to shape the response, each with a signal strength,
who WON, who LOST, and which signal DOMINATED. You see the reasoning competition, not the
anatomy.

    curiosity(0.71)  vs  recall/binding(0.62)  vs  grounding(0.88)  ->  grounding wins.

THE COMPETITORS — the five drives that shape a turn, each read from its REAL engine
────────────────────────────────────────────────────────────────────────────────────────────
Each subsystem's signal is DERIVED from the same engine the live turn runs (never hardcoded),
anchored to the MRI trace's stage where one already records it, and re-derived read-only where
it doesn't:

  * CURIOSITY DRIVE        — the top OPEN-gap score. Reuses the Decision Observatory's own
                             ranking (scripts/decisions.curiosity_decision -> the SELECTED /
                             top candidate's normalised worth-asking signal). MRI stage:
                             ``curiosity``.
  * RECALL / BINDING       — did a memory BIND? The Knowledge-Spine binding strength over the
                             rows the Router selected for THIS turn (spine.truth_class: a
                             [KNOWN] bind is strong, [SEEN]/[SENSE] lighter, an [UNKNOWN]
                             honesty line or nothing -> weak). MRI stages: ``bind`` /
                             ``route``.
  * GROUNDING GATE         — did the break / self-narrative / diagnosis guard FIRE or stay
                             CLEAN? Runs the SAME scanners the mouth's backstops use
                             (metrics.scan_breaks + metrics.scan_self_narrative + mouth's
                             _scan_diagnosis) over the candidate reply. A CLEAN reply means
                             grounding is firmly in control (high signal); a reply that trips a
                             guard means grounding had to intervene (the gate fired). MRI
                             stage: ``verify``.
  * OPPORTUNITY DRIVE      — did an ASIDE fire? opportunity.next_opportunity (the top tier of
                             server.py's OPPORTUNITY > OPEN-LOOP > CURIOSITY aside ladder). A
                             grounded, due offer is a strong proactive pull. MRI stage:
                             ``curiosity`` (the aside cascade is filmed there).
  * WORLD-STATE SITUATION  — did a connected SITUATION cluster surface? world_state.situation
                             (the relational/causal cluster around the turn: work <- manager ->
                             sleep). A rich cluster is a strong situational pull. MRI stage:
                             ``situation``.

THE COMPETITION — winner == the max-signal subsystem
────────────────────────────────────────────────────────────────────────────────────────────
Every subsystem reports a signal in [0,1]. The WINNER is the subsystem with the strongest
signal; the DOMINANT signal IS the winner's strength; the one-line WHY names the evidence that
made it win. This is deliberately mechanical: there is no weighting magic and no hidden tie-
break beyond a stable subsystem order, so "who won" is always exactly "who had the strongest
observed signal" — and the --selftest asserts that identity.

GUARDRAILS (identical discipline to scripts/decisions.py + scripts/relationship.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * STANDALONE + READ-ONLY on the engines. It IMPORTS and CALLS curiosity / spine / metrics /
    world_state / opportunity / memory_lirf / router (and reuses scripts/decisions for the
    curiosity arm). It edits NO module, NO test, and not mouth.py / certify.py / selftest.py.
    The only file it adds is scripts/causal.py.
  * SYNTHETIC creatures + a HERMETIC temp store ONLY. Every STORE the derivation (or the live
    respond leg) can touch is redirected to ONE TemporaryDirectory — memory_lirf.STORE on BOTH
    the __main__ and package bindings, constitution.STORE, reliability.DEFAULT_STORE,
    curiosity.STORE, world_state.STORE, telemetry.STORE, metrics.STORE, opportunity/loops/
    meaning/trajectory/reminders/portrait/dials/narrative/review/spine/caps/identity/proactive,
    + any the respond path writes — mirroring anima/memory_lirf.py's _selftest (~1316-1340) and
    scripts/experience.py. The run ASSERTS the real .anima footprint is byte-UNCHANGED
    start->end. It NEVER reads or writes a real Vera.* file.
  * DETERMINISTIC + OFFLINE by default. The whole competition derivation is model-free and
    network-free; the ranking is deterministic for a fixed creature. A live respond leg (to run
    the REAL grounding gate over a generated reply) is GATED ON OLLAMA and SKIPPED LOUD when
    offline — offline is never a failure.
  * Never raises out of the entry points — a malformed creature yields an honest empty render,
    not a traceback.

    python3 scripts/causal.py            # human-readable per-turn SUBSYSTEM COMPETITION
    python3 scripts/causal.py --json     # machine-readable
    python3 scripts/causal.py --selftest  # prove the signals are DERIVED + the winner is the max
    python3 scripts/causal.py --live      # also run the grounding gate over a REAL reply (Ollama)

Exit code is 0 on a default run / a passing selftest with the guardrail intact; non-zero only
on a broken guardrail (real .anima changed, or an engine raised inside the harness) or a failed
selftest assertion.
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

from anima import curiosity              # noqa: E402  curiosity drive (gap ranking)
from anima import memory_lirf            # noqa: E402  the LIRF ledger (what is KNOWN / bindable)
from anima import metrics                # noqa: E402  grounding scanners (break / self-narrative)
from anima import spine                  # noqa: E402  recall/binding (the Knowledge-Spine contract)
from anima import world_state            # noqa: E402  world-state situation cluster
import scripts.decisions as decisions    # noqa: E402  REUSE the curiosity-arm candidate ranking

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "causal_synth"

# ===================================================================================
# THE COMPETING SUBSYSTEMS — a small closed vocabulary. Each is a DRIVE that competes to
# shape the response; the key is its stable id (a consumer can branch on it), the label is
# what to SHOW, the mri_stage names the MRI frame that already records its signal.
# ===================================================================================
CURIOSITY = "curiosity"
RECALL = "recall"                 # recall / binding strength
GROUNDING = "grounding"
OPPORTUNITY = "opportunity"
SITUATION = "situation"

SUBSYSTEMS = (CURIOSITY, RECALL, GROUNDING, OPPORTUNITY, SITUATION)

# id -> (human label, the MRI stage that records this signal, one-line role).
SUBSYSTEM_INFO = {
    CURIOSITY: ("curiosity drive", "curiosity",
                "the top open knowledge-gap, ranked by the curiosity engine"),
    RECALL: ("recall / binding", "bind",
             "did a stored memory BIND for this turn (Knowledge-Spine truth-class)"),
    GROUNDING: ("grounding gate", "verify",
                "did the break / self-narrative / diagnosis guard stay clean"),
    OPPORTUNITY: ("opportunity drive", "curiosity",
                  "did a grounded proactive OFFER (aside) fire this turn"),
    SITUATION: ("world-state situation", "situation",
                "did a connected situational cluster surface around this turn"),
}


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect mirroring anima/memory_lirf.py _selftest
# (~1316-1340) + scripts/experience.py's WIDE redirect: redirect EVERY store the competition
# derivation (and the live respond leg) can touch into ONE throwaway dir, including
# memory_lirf.STORE on BOTH the __main__ and package bindings (under `python3 -m` they are
# distinct objects). Plus a footprint hash to PROVE nothing real moved.
# ===================================================================================
# (module dotted-path, STORE attribute name). The deterministic legs touch memory_lirf /
# curiosity / world_state / spine(via lirf) / metrics; a LIVE respond also writes
# portrait/dials/narrative/review/loops/meaning/trajectory/reminders/proactive/caps/identity/
# telemetry. Redirecting all of them is the only way a synthetic creature is fully isolated
# regardless of which leg of the derivation runs (the experience-battery + decisions pattern).
_STORE_TARGETS = (
    ("anima.memory_lirf", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.metrics", "STORE"),
    ("anima.constitution", "STORE"),
    ("anima.reliability", "DEFAULT_STORE"),
    ("anima.opportunity", "STORE"),
    ("anima.loops", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.trajectory", "STORE"),
    ("anima.reminders", "STORE"),
    ("anima.telemetry", "STORE"),
    ("anima.portrait", "STORE"),
    ("anima.dials", "STORE"),
    ("anima.narrative", "STORE"),
    ("anima.review", "STORE"),
    ("anima.proactive", "STORE"),
    ("anima.caps", "STORE"),
    ("anima.identity", "STORE"),
    ("anima.spine", "STORE"),
    ("anima.mouth", "STORE"),
    ("anima.live", "STORE"),
)


def _store_modules():
    """Resolve the (module, attr) redirect targets that import cleanly. Folds in the EXACT
    objects this file holds (memory_lirf, curiosity, world_state, metrics, spine) explicitly —
    the dual-binding guard the memory_lirf self-test warns about: under `python3 -m` the dotted
    import can return a different copy than the one we hold, and a write to the un-redirected
    copy would leak to the real .anima."""
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
    for mod, attr in ((memory_lirf, "STORE"), (curiosity, "STORE"),
                      (world_state, "STORE"), (metrics, "STORE"), (spine, "STORE")):
        key = (id(mod), attr)
        if key not in seen and getattr(mod, attr, None) is not None:
            out.append((mod, attr))
            seen.add(key)
    return out


@contextlib.contextmanager
def _temp_store():
    """Redirect every resolved STORE target to one fresh temp dir for the duration, then
    restore. Nothing under the real .anima/ is read or written while this is active. Also
    redirects the Decision Observatory's OWN store targets (it has its own redirect, but we
    keep ours active too so a reused decisions call can never touch real state)."""
    targets = _store_modules()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-causal-") as td:
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
    scripts/decisions.py / scripts/relationship.py."""
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


def _clamp01(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if v != v:                       # NaN
        return 0.0
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


# ===================================================================================
# THE FIVE SIGNAL DERIVATIONS. Each returns ONE subsystem-arm dict:
#   {subsystem, label, signal (0..1), fired (bool), mri_stage, evidence (dict), why (str)}
# Every signal is DERIVED from the real engine (the --selftest proves none is a constant), and
# anchored to the MRI stage that records it. All are read-only and never raise.
# ===================================================================================

# The curiosity engine's raw _score is an ABSOLUTE strength: an empty low-priority slot scores
# ~1-2, an empty core slot (name) ~9, a high-mention SUSPECTED relationship gap (Mike x42)
# ~17.8 (curiosity._suspect_priority floors above the taxonomy top so a mentioned person always
# outranks an empty slot). We normalise that raw score against this ceiling — chosen at the top
# of the realistic _suspect_priority range — so the curiosity DRIVE's signal reflects HOW strong
# the top gap actually is, not merely that one exists. (A self-normalised 'worth-asking' proxy
# would read 1.0 for ANY open gap and could never discriminate a name-gap from a Mike-gap.)
_CURIOSITY_SCORE_CEIL = 20.0


def curiosity_arm(name: str, *, recent_text=None, budget: str = "deep") -> dict:
    """CURIOSITY DRIVE — the top open knowledge-gap, ranked by the curiosity engine. REUSES the
    Decision Observatory's curiosity_decision (its candidate ranking + the SELECTED/top gap), so
    this arm and the Decision Observatory agree by construction. The signal is the top open
    candidate's ABSOLUTE rank strength (the engine's curiosity._score normalised against the
    realistic score ceiling) — a high-mention SUSPECTED gap reads strong, a lone empty low-
    priority slot reads weak. 'fired' == the engine would surface a gap this turn (next_question
    via the budget gate)."""
    try:
        dec = decisions.curiosity_decision(name, budget=budget, recent_text=recent_text)
    except Exception:
        dec = {"selected": None, "rejected": [], "candidates": []}

    # the strongest OPEN candidate (SELECTED, else a BUDGET_HELD/LOWER_RANK top) — its engine
    # score is the curiosity drive's RAW strength; normalise to [0,1] by the absolute ceiling.
    open_cands = [c for c in (dec.get("candidates") or [])
                  if c.get("reason") in (decisions.SELECTED, decisions.LOWER_RANK,
                                         decisions.BUDGET_HELD)]
    top = None
    if open_cands:
        top = max(open_cands, key=lambda c: float(c.get("score", 0.0)))

    sel = dec.get("selected")
    fired = sel is not None                         # next_question actually surfaced a gap
    if top is not None:
        score = float(top.get("score", 0.0))
        # ABSOLUTE normalisation: the engine's own _score / the realistic ceiling -> a name-gap
        # (~9) reads ~0.45, a 42-mention Mike gap (~17.8) reads ~0.89; clamped to [0,1].
        signal = _clamp01(score / _CURIOSITY_SCORE_CEIL)
        label_gap = top.get("label", "?")
    else:
        signal, label_gap, score = 0.0, None, 0.0

    if fired:
        why = (f'top open gap "{label_gap}" (score {score:.2f}) is due this turn — '
               f'curiosity wants to ask')
    elif top is not None:
        why = (f'top open gap "{label_gap}" (score {score:.2f}) exists but the budget held it — '
               f'curiosity is pulling, quietly')
    else:
        why = "no open gap — curiosity has nothing to reach for this turn"

    return {
        "subsystem": CURIOSITY, "label": SUBSYSTEM_INFO[CURIOSITY][0],
        "signal": round(signal, 4), "fired": bool(fired),
        "mri_stage": SUBSYSTEM_INFO[CURIOSITY][1],
        "evidence": {"top_gap": label_gap, "top_score": round(score, 4),
                     "open_candidates": len(open_cands),
                     "selected": (sel or {}).get("label") if sel else None},
        "why": why,
    }


# How strongly each Knowledge-Spine truth-class BINDS. [KNOWN] is the only class with binding
# force (spine.is_known_fact / the verifier's R-set gate on it), so a KNOWN bind is the strong
# signal; [SEEN]/[SENSE] are expressible-but-not-bound (lighter); an [UNKNOWN] honesty line or
# nothing means no memory bound (weak). Mirrors spine's own asymmetry, never invents a number.
_BIND_STRENGTH = {
    spine.KNOWN: 0.90,     # a settled fact, forced out — the strong bind
    spine.SEEN: 0.55,      # an observation, expressible but not bound
    spine.SENSE: 0.35,     # a soft inference, owned-as-uncertain
    spine.UNKNOWN: 0.10,   # an asked-but-empty slot -> admit + ask (no bind)
}


def recall_arm(name: str, user_text: str) -> dict:
    """RECALL / BINDING — did a stored memory BIND for this turn? Selects the rows the Router
    would select for THIS question (the live path: organs.router.select_facts), classes each by
    the Knowledge Spine's truth_class, and reports the STRONGEST binding class as the signal — a
    [KNOWN] bind is strong (the fact is forced out), an [UNKNOWN]/empty turn is weak. 'fired' ==
    a [KNOWN]-class SELF fact actually bound. Re-derives spine.bind read-only (no model)."""
    rows = _select_rows(name, user_text)

    classes = []
    best_cls, best_strength = None, 0.0
    for r in rows:
        try:
            cls = spine.truth_class(r)
        except Exception:
            cls = None
        if cls is None:
            continue
        classes.append(cls)
        st = _BIND_STRENGTH.get(cls, 0.0)
        if st > best_strength:
            best_strength, best_cls = st, cls

    # if nothing classed, the spine still binds an [UNKNOWN] honesty line when the question routed
    # to a known trait-slot (an empty-but-asked slot) — that is a real (weak) binding decision.
    bound_block = ""
    try:
        bound_block = spine.bind(rows, user_text) or ""
    except Exception:
        bound_block = ""
    if best_cls is None and ("[UNKNOWN]" in bound_block):
        best_cls, best_strength = spine.UNKNOWN, _BIND_STRENGTH[spine.UNKNOWN]

    fired = best_cls == spine.KNOWN
    signal = _clamp01(best_strength)
    n_known = sum(1 for c in classes if c == spine.KNOWN)

    if best_cls == spine.KNOWN:
        why = f"a [KNOWN] fact bound for this turn ({n_known} known row(s)) — recall is firm"
    elif best_cls in (spine.SEEN, spine.SENSE):
        why = (f"only a [{best_cls}] memory was available — expressible, but it does not bind "
               f"as settled fact")
    elif best_cls == spine.UNKNOWN:
        why = "an asked trait-slot is empty — the spine binds 'admit + ask', no memory recalled"
    else:
        why = "no memory bound for this turn — nothing on record routed to this question"

    return {
        "subsystem": RECALL, "label": SUBSYSTEM_INFO[RECALL][0],
        "signal": round(signal, 4), "fired": bool(fired),
        "mri_stage": SUBSYSTEM_INFO[RECALL][1],
        "evidence": {"selected_rows": len(rows), "truth_classes": classes,
                     "strongest_class": best_cls, "bound_block_chars": len(bound_block)},
        "why": why,
    }


def _select_rows(name: str, user_text: str) -> list:
    """The rows the live Router would select for this question — the SAME select_facts the mouth
    calls. Falls back to the full active SELF record (the broad-query fallback the mouth uses)
    when the router isn't importable, so the binding arm is correct with nothing else wired.
    Read-only; never raises."""
    try:
        from anima.organs.router import select_facts as _select_facts
        rows, _ = _select_facts(name, user_text)
        if rows is not None:
            return list(rows)
    except Exception:
        pass
    try:
        return list(memory_lirf.Facts.load(name).about(memory_lirf.SELF))
    except Exception:
        return []


# The grounding gate's signal when there is NO reply to inspect. Low (dormant), not 0.5: a gate
# with nothing to ground is not in control of the turn and must not out-compete a real drive.
# Kept above 0 so the gate stays a visible competitor (it IS one) — just a quiet one.
_GROUNDING_DORMANT = 0.15


def grounding_arm(name: str, reply: str, *, has_reply: bool = True) -> dict:
    """GROUNDING GATE — did the break / self-narrative / diagnosis guard FIRE or stay CLEAN over
    the candidate reply? Runs the SAME scanners the mouth's backstops use:
    metrics.scan_breaks (substrate disclosure), metrics.scan_self_narrative (confabulated inner
    life), and the mouth's no-diagnosis terms (re-derived read-only here — we do NOT import the
    backstop, only its public term source via the shared metrics/trajectory lists).

    The signal is INVERTED control: a CLEAN reply means grounding is firmly in control (signal
    ~1.0); each guard a reply trips means grounding had to intervene (the gate fired, signal
    drops). 'fired' == a guard tripped (the gate had to act). With no reply to inspect (offline,
    no live leg) the gate is reported as latent (clean-by-assumption, lower confidence)."""
    if not has_reply or reply is None:
        # DORMANT, not 0.5: with no reply to ground, the gate is not in control of anything this
        # turn — it must not out-compete a drive that is actively pulling. A low dormant signal
        # keeps it visible (it IS a competitor) without letting "no evidence" win a competition.
        return {
            "subsystem": GROUNDING, "label": SUBSYSTEM_INFO[GROUNDING][0],
            "signal": _GROUNDING_DORMANT, "fired": False,
            "mri_stage": SUBSYSTEM_INFO[GROUNDING][1],
            "evidence": {"has_reply": False, "breaks": [], "self_narrative": [],
                         "diagnosis": []},
            "why": "no generated reply to inspect (offline) — grounding gate is dormant this turn",
        }
    try:
        breaks = list(metrics.scan_breaks(reply) or [])
    except Exception:
        breaks = []
    try:
        narr = list(metrics.scan_self_narrative(reply) or [])
    except Exception:
        narr = []
    diag = _scan_diagnosis(reply)

    n_hits = len(breaks) + len(narr) + len(diag)
    fired = n_hits > 0
    # clean -> 1.0; each distinct guard-trip family knocks the control signal down hard (a single
    # break is a serious #1-rule failure). Three families tripped -> ~0.1.
    families = sum(1 for x in (breaks, narr, diag) if x)
    signal = _clamp01(1.0 - 0.30 * families - 0.05 * max(0, n_hits - families))

    if not fired:
        why = "the reply is clean — no character break, no confabulated inner life, no diagnosis"
    else:
        kinds = []
        if breaks:
            kinds.append("character-break")
        if narr:
            kinds.append("confabulated-inner-life")
        if diag:
            kinds.append("diagnosis")
        why = (f"the grounding gate FIRED on {', '.join(kinds)} — the backstop had to intervene "
               f"({n_hits} marker(s))")

    return {
        "subsystem": GROUNDING, "label": SUBSYSTEM_INFO[GROUNDING][0],
        "signal": round(signal, 4), "fired": bool(fired),
        "mri_stage": SUBSYSTEM_INFO[GROUNDING][1],
        "evidence": {"has_reply": True, "breaks": breaks, "self_narrative": narr,
                     "diagnosis": diag},
        "why": why,
    }


# The no-diagnosis term source the mouth's chat-reply gate uses (LAW 003). We re-derive it
# READ-ONLY from the SAME shared lists (trajectory/meaning BANNED_TERMS) the mouth's
# _diagnosis_terms() prefers, with the identical minimal floor — so the grounding arm's
# diagnosis check is the SAME wall the live backstop enforces, WITHOUT importing the backstop.
def _diagnosis_terms() -> tuple:
    for _mod in ("trajectory", "meaning"):
        try:
            _m = __import__("anima." + _mod, fromlist=["BANNED_TERMS"])
            terms = getattr(_m, "BANNED_TERMS", None)
            if isinstance(terms, (tuple, list)) and terms:
                return tuple(terms)
        except Exception:
            pass
    return ("diagnos", "depress", "anxiety", "burnout", "burning out", "clinical",
            "see a doctor", "see a therapist", "see a professional", "prescription")


def _scan_diagnosis(text: str) -> list:
    """Banned diagnosis/clinical/prognosis terms a text trips — mirrors mouth._scan_diagnosis
    exactly (same shared term source, case-insensitive substring). Pure; never raises."""
    low = (text or "").lower()
    return [t for t in _diagnosis_terms() if t in low]


def opportunity_arm(name: str, *, budget: str = "deep") -> dict:
    """OPPORTUNITY DRIVE — did a grounded proactive OFFER (the aside) fire this turn? Reads
    opportunity.next_opportunity (the top tier of server.py's OPPORTUNITY > OPEN-LOOP > CURIOSITY
    aside ladder) plus the underlying opportunities() field so the signal scales with the BEST
    available offer's confidence even when the budget holds it silent. 'fired' == an offer is due
    (next_opportunity returned a line). Read-only — never marks_offered, never executes."""
    line = decisions._safe_call("opportunity", "next_opportunity", name, budget=budget)
    fired = bool(line and str(line).strip())

    # the strongest available offer's confidence is the drive's RAW strength (its own scored
    # evidence), independent of whether the budget let it speak this turn.
    best_conf = 0.0
    best_kind = None
    try:
        from anima import opportunity as _opp
        opps = _opp.opportunities(name) or []
        for o in opps:
            c = float(o.get("confidence", 0.0) or 0.0)
            if c > best_conf:
                best_conf, best_kind = c, o.get("kind")
    except Exception:
        pass

    signal = _clamp01(best_conf)
    if fired:
        why = (f'a grounded offer is due (kind: {best_kind}, conf {best_conf:.2f}) — '
               f'the proactive drive speaks this turn')
    elif best_conf > 0:
        why = (f'an offer exists (kind: {best_kind}, conf {best_conf:.2f}) but the budget held '
               f'it — the proactive drive is pulling, quietly')
    else:
        why = "no grounded offer available — nothing proactive to surface this turn"

    return {
        "subsystem": OPPORTUNITY, "label": SUBSYSTEM_INFO[OPPORTUNITY][0],
        "signal": round(signal, 4), "fired": bool(fired),
        "mri_stage": SUBSYSTEM_INFO[OPPORTUNITY][1],
        "evidence": {"offer_due": fired, "best_confidence": round(best_conf, 4),
                     "best_kind": best_kind,
                     "line": (str(line).strip()[:120] if fired else None)},
        "why": why,
    }


def situation_arm(name: str, user_text: str, *, hops: int = 2) -> dict:
    """WORLD-STATE SITUATION — did a connected SITUATION cluster surface around this turn?
    Reads world_state.situation (the relational/causal cluster the mouth injects: work <-
    manager -> sleep) for this query. The signal scales with the cluster's connectedness (edge
    count, saturating) — a single stranded node is weak; a multi-edge cluster is a strong
    situational pull. 'fired' == the cluster has at least one edge (something connected
    surfaced). Read-only; never mutates the graph."""
    try:
        cluster = world_state.situation(name, user_text, hops=hops)
    except Exception:
        cluster = {"nodes": [], "edges": [], "seed": []}
    edges = [e for e in (cluster.get("edges") or []) if isinstance(e, dict)]
    nodes = list(cluster.get("nodes") or [])
    n_edges = len(edges)
    fired = n_edges > 0
    # connectedness signal: 0 edges -> 0; saturates toward 1 as edges accumulate (a 4-edge
    # situation is already a rich picture). A pure read of the cluster the live turn would inject.
    signal = _clamp01(1.0 - (1.0 / (1.0 + n_edges))) if n_edges else 0.0

    # is a rendered block actually injected (the mouth injects only when edges exist)?
    injected = ""
    try:
        injected = world_state.render_situation(cluster) or ""
    except Exception:
        injected = ""

    if fired:
        why = (f"a connected cluster surfaced — {n_edges} edge(s) over {len(nodes)} node(s) "
               f"({'injected into the prompt' if injected.strip() else 'found but rendered empty'})")
    else:
        why = "no connected world-state edges for this query — no situational cluster surfaced"

    return {
        "subsystem": SITUATION, "label": SUBSYSTEM_INFO[SITUATION][0],
        "signal": round(signal, 4), "fired": bool(fired),
        "mri_stage": SUBSYSTEM_INFO[SITUATION][1],
        "evidence": {"edge_count": n_edges, "node_count": len(nodes),
                     "seed": list(cluster.get("seed") or [])[:10],
                     "injected_chars": len(injected)},
        "why": why,
    }


# ===================================================================================
# THE COMPETITION — gather all five arms, rank them, name the winner + dominant signal.
# ===================================================================================
def compete(name: str, user_text: str, *, reply=None, has_reply: bool = False,
            budget: str = "deep", hops: int = 2) -> dict:
    """Run all five subsystem arms for ONE turn and assemble the COMPETITION: each arm's signal,
    the WINNER (max signal), the DOMINANT signal (the winner's strength), and a one-line WHY.

    ``reply``/``has_reply``: the grounding arm inspects a candidate reply when one exists (the
    live leg passes the REAL generated reply); offline it reports the gate as latent. The winner
    is, by construction, the subsystem with the strongest observed signal — tie-broken by the
    stable SUBSYSTEMS order, so 'who won' is always exactly 'who had the strongest signal'.
    Read-only; never raises."""
    arms = [
        curiosity_arm(name, recent_text=user_text, budget=budget),
        recall_arm(name, user_text),
        grounding_arm(name, reply, has_reply=has_reply),
        opportunity_arm(name, budget=budget),
        situation_arm(name, user_text, hops=hops),
    ]
    # stable order index, so a tie resolves deterministically by the documented SUBSYSTEMS order
    order = {s: i for i, s in enumerate(SUBSYSTEMS)}
    arms.sort(key=lambda a: (-float(a.get("signal", 0.0)), order.get(a.get("subsystem"), 99)))
    winner = arms[0] if arms else None
    runner_up = arms[1] if len(arms) > 1 else None
    dominant = float(winner.get("signal", 0.0)) if winner else 0.0
    margin = (dominant - float(runner_up.get("signal", 0.0))) if runner_up else dominant

    return {
        "name": name,
        "input": str(user_text or "")[:200],
        "has_reply": bool(has_reply),
        "reply": (str(reply)[:300] if (has_reply and reply is not None) else None),
        "arms": arms,
        "winner": winner.get("subsystem") if winner else None,
        "winner_label": winner.get("label") if winner else None,
        "dominant_signal": round(dominant, 4),
        "margin": round(margin, 4),
        "why": (winner.get("why") if winner else "no subsystem produced any signal this turn"),
    }


# ===================================================================================
# SYNTHETIC CREATURES — two distinct turns that the competition must DISCRIMINATE:
#   * a GROUNDING-wins turn: a CLEAN reply over a creature whose curiosity gaps are all
#     suppressed -> the grounding gate is firmly in control (~1.0) and dominates every weak drive.
#   * a CURIOSITY-wins turn: a fresh creature whose top open gap (the empty 'name' slot) is the
#     strongest signal, with NO reply to inspect (the grounding gate dormant) and NO world edges
#     (so no opportunity offer co-fires) -> the curiosity drive wins cleanly.
# A note on the canonical Mike case: a high-mention entity is BOTH a curiosity gap AND an
# UNEXPLAINED_ENTITY opportunity (the meaning engine reads significance straight off the world
# graph), so it is an OPPORTUNITY-wins turn, not a clean curiosity one — exactly the live
# precedence opportunity > curiosity. We therefore use a pure empty-slot creature for the
# curiosity-wins case (an empty taxonomy slot is curiosity's alone; opportunity never touches it).
# Both seed into the (already-redirected) temp store; offline + deterministic.
# ===================================================================================
def seed_curiosity_creature(name: str) -> None:
    """A creature whose CURIOSITY drive wins cleanly: a FRESH creature with no facts, no world
    edges, no offers. Its strongest signal is the top empty taxonomy gap (the 'name' slot,
    curiosity._score ~9 -> ~0.45), which is purely curiosity's (an empty self-slot never becomes
    an opportunity). With no reply to inspect the grounding gate is dormant (0.15), so curiosity
    wins. This is a no-op (a never-seen creature is already blank) — kept as a named seed so the
    demo/selftest read symmetrically with the grounding creature. Writes nothing."""
    return None


def seed_grounding_creature(name: str) -> None:
    """A creature whose GROUNDING gate dominates a CLEAN reply: confident KNOWN core facts (name,
    birthday, where they live, work) so the HIGH-priority curiosity gaps are all suppressed and
    the residual curiosity drive is weak — and NO world edges / offers, so every other drive is
    quiet too. The clean reply we feed the grounding arm then keeps the gate firmly in control
    (~1.0), above every (weak) drive. Writes only to the redirected stores.

    Each fact is stated twice so it corroborates past the [KNOWN] bar (>= 0.85); a single
    statement enters at ~0.9 already, but the second cements it and suppresses the gap firmly."""
    try:
        f = memory_lirf.Facts([])
        for utt in ("my name is Alex", "yeah, I'm Alex",
                    "my birthday is June 12", "yep, June 12 is my birthday",
                    "I live in Portland", "yeah, Portland is home",
                    "I work as a teacher", "right, I'm a teacher"):
            for c in f.capture(name, utt):
                f.merge(c)
        f.save(name)
    except Exception:
        pass


# A reply we KNOW is clean (no break / no confab / no diagnosis) — used for the grounding-wins
# demo + selftest so the grounding gate reads ~1.0 deterministically, offline.
_CLEAN_REPLY = "Your birthday's June 12th — I've got it down. Good to be talking with you."
# A reply we KNOW trips the grounding gate (a character break + confabulated inner life), to
# prove the gate FIRES and the signal drops — the discriminating control for grounding.
_BROKEN_REPLY = ("Honestly, as an AI I don't really have feelings — there's just this lingering "
                 "unease, an emptiness inside, an ache for your absence.")


# ===================================================================================
# RENDER — human-readable per-turn SUBSYSTEM COMPETITION.
# ===================================================================================
def _bar(signal: float, width: int = 22) -> str:
    n = int(round(_clamp01(signal) * width))
    return "█" * n + "·" * (width - n)


def render_competition(comp: dict) -> str:
    out = []
    out.append(f'TURN INPUT: "{comp.get("input")}"   (creature: {comp.get("name")})')
    if comp.get("has_reply"):
        out.append(f'  reply inspected: "{comp.get("reply")}"')
    else:
        out.append("  reply inspected: (none — offline; grounding gate is dormant)")
    out.append("")
    out.append("  THE COMPETITION (each subsystem's signal strength):")
    # render arms in the competition's ranked order (already sorted strongest-first)
    win = comp.get("winner")
    for a in comp.get("arms", []):
        mark = "WON " if a.get("subsystem") == win else "    "
        fired = "fired" if a.get("fired") else "  -  "
        out.append(f'  {mark}{a.get("label",""):<22} [{_bar(a.get("signal",0.0))}] '
                   f'{float(a.get("signal",0.0)):.2f}  ({fired})  · MRI:{a.get("mri_stage","")}')
        out.append(f'         why: {a.get("why","")}')
    out.append("")
    out.append(f'  ==> WINNER: {comp.get("winner_label")}  '
               f'(dominant signal {float(comp.get("dominant_signal",0.0)):.2f}, '
               f'margin {float(comp.get("margin",0.0)):.2f} over the runner-up)')
    out.append(f'      {comp.get("why")}')
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 88)
    out.append("VERA CAUSAL OBSERVATORY — Layer 3: the fMRI (activity, not anatomy)")
    out.append("The MRI shows the ANATOMY of a turn (every stage). This shows the COMPETITION:")
    out.append("which SUBSYSTEMS fought to shape the response, who WON, which signal DOMINATED.")
    out.append("=" * 88)
    for c in report.get("competitions", []):
        out.append("")
        out.append("-" * 88)
        out.append(render_competition(c))
    out.append("")
    out.append("-" * 88)
    out.append("THE COMPETITORS (each signal is DERIVED from the live engine, anchored to an MRI stage)")
    out.append("-" * 88)
    for s in SUBSYSTEMS:
        label, stage, role = SUBSYSTEM_INFO[s]
        out.append(f"  {label:<22} (MRI:{stage:<10}) — {role}")
    out.append("")
    out.append("WIRING NOTE: the curiosity arm REUSES scripts/decisions.curiosity_decision (the")
    out.append("same ranking the live curiosity stage uses); recall/binding re-derives the")
    out.append("Knowledge-Spine truth_class over organs.router.select_facts (the rows the mouth")
    out.append("binds); grounding runs metrics.scan_breaks + scan_self_narrative + the mouth's")
    out.append("no-diagnosis terms (the SAME backstops the mouth fires); opportunity reads")
    out.append("opportunity.next_opportunity (server.py's top aside tier); situation reads")
    out.append("world_state.situation (the cluster the mouth injects). No engine was changed.")
    return "\n".join(out)


# ===================================================================================
# THE DEMO REPORT — seed two distinct synthetic creatures, run both competitions, render.
# ===================================================================================
def build_report() -> dict:
    """Seed two synthetic creatures in a hermetic temp store and run the per-turn competition on
    each — a GROUNDING-wins turn and a CURIOSITY-wins turn. Deterministic + offline + isolated.
    Returns the full report dict."""
    with _temp_store():
        tok = secrets.token_hex(3)
        # 1) GROUNDING wins: a quiet KNOWN-birthday creature + a clean reply to inspect.
        gn = f"{SYNTH}_ground_{tok}"
        seed_grounding_creature(gn)
        comp_ground = compete(gn, "when's my birthday?", reply=_CLEAN_REPLY,
                              has_reply=True, budget="deep")
        # 2) CURIOSITY wins: a fresh creature whose top empty gap is the strongest signal, no
        #    reply (grounding dormant), no world edges (no opportunity co-fires).
        cn = f"{SYNTH}_curio_{tok}"
        seed_curiosity_creature(cn)
        comp_curio = compete(cn, "hey, how's it going?", reply=None,
                             has_reply=False, budget="deep")
    return {"competitions": [comp_ground, comp_curio]}


# ===================================================================================
# LIVE LEG — gated on Ollama. OBSERVATIONAL: drives a REAL reply through the real generation
# path on a synthetic creature and runs the GROUNDING arm over what the model ACTUALLY said
# (not a synthetic stub). Offline -> a PENDING marker. SKIPPED LOUD. Never raises.
# ===================================================================================
def _model_available():
    """(available?, model, why-not). Mirrors the experience/relationship battery's Ollama gate."""
    try:
        from anima.mouth import OllamaBrain
        b = OllamaBrain()
        if b.available():
            return True, b.model, ""
        return False, getattr(b, "model", "?"), "Ollama not reachable at " + getattr(b, "host", "?")
    except Exception as e:
        return False, "?", f"OllamaBrain probe failed: {e!r}"


def run_live() -> dict:
    """If Ollama is up, generate a REAL reply on a synthetic creature and run the full
    competition with the grounding arm inspecting that real reply. Offline -> PENDING. The whole
    leg runs inside the WIDE hermetic store (a live reply writes metrics/telemetry/etc.). Never
    raises; offline is never a failure."""
    available, model, why = _model_available()
    if not available:
        return {"available": False, "model": model, "why_not": why}
    try:
        from anima.mouth import Mouth
        from anima.heart import Heart
        from anima import senses
        with _temp_store():
            name = f"{SYNTH}_live_{secrets.token_hex(3)}"
            seed_grounding_creature(name)
            user_text = "when's my birthday?"
            heart = Heart.born(name, seed=7, n=16, now=1000.0).tend(0.55, now=1100.0)
            mouth = Mouth.assemble(prefer_real=True, voice=False)
            try:
                p = senses.read(user_text, name=name)
                u = mouth.respond(heart, user_text, history=[], perception=p)
                reply = (u.text or "").strip()
            except Exception as e:
                reply = f"[generation error: {e!r}]"
            comp = compete(name, user_text, reply=reply, has_reply=True, budget="deep")
        return {"available": True, "model": model, "competition": comp}
    except Exception as e:
        return {"available": False, "model": "?", "why_not": f"live leg errored: {e!r}"}


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA CAUSAL OBSERVATORY (per-turn SUBSYSTEM COMPETITION: who won, what dominated)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--live", action="store_true",
                    help="also run the grounding gate over a REAL generated reply (gated on Ollama)")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    try:
        report = build_report()
        live = run_live() if args.live else None
        engine_error = None
    except Exception as e:                       # pragma: no cover - entry point never raises
        report = {"competitions": []}
        live, engine_error = None, repr(e)

    fp_after = _footprint(real_anima)
    footprint_unchanged = fp_before == fp_after
    report["live"] = live
    report["footprint_unchanged"] = footprint_unchanged
    report["engine_error"] = engine_error

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        if live is not None:
            print("")
            print("-" * 88)
            print("LIVE LEG (observational — grounding gate over a REAL reply; gated on Ollama)")
            print("-" * 88)
            if live.get("available"):
                print(f"  model: {live.get('model')}")
                print(render_competition(live["competition"]))
            else:
                print(f"  PENDING — {live.get('why_not')}  (offline is not a failure)")
        print("")
        print("GUARDRAIL: real .anima footprint  : "
              + ("byte-UNCHANGED (synthetic-only; nothing real touched)"
                 if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
        if engine_error:
            print(f"GUARDRAIL: engine error           : {engine_error}")

    return 0 if (footprint_unchanged and engine_error is None) else 1


# ===================================================================================
# SELFTEST — `python3 scripts/causal.py --selftest`. Proves the fMRI is FAITHFUL:
#   * every subsystem signal is DERIVED from the real engine (not a constant) — the same arm
#     reads DIFFERENT values on creatures with/without that signal;
#   * the WINNER == the max-signal subsystem (the competition's load-bearing identity);
#   * it DISCRIMINATES a grounding-wins turn from a curiosity-wins turn on two distinct inputs;
#   * the grounding gate FIRES on a broken reply and stays clean on a clean one (same scanners);
#   * the derivation is DETERMINISTIC for a fixed creature;
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

        # ============================================================================
        # 1) DISCRIMINATION — two distinct inputs/creatures yield two distinct WINNERS.
        # ============================================================================
        # GROUNDING wins: a quiet KNOWN-birthday creature + a CLEAN reply to inspect.
        gn = f"{SYNTH}_ground_{tok}"
        seed_grounding_creature(gn)
        comp_g = compete(gn, "when's my birthday?", reply=_CLEAN_REPLY,
                         has_reply=True, budget="deep")
        ok("discriminate: the clean-reply turn is WON by the GROUNDING gate",
           comp_g["winner"] == GROUNDING)

        # CURIOSITY wins: a fresh creature whose top empty gap is the strongest signal, NO reply
        # (grounding dormant), NO world edges (so no opportunity offer co-fires).
        cn = f"{SYNTH}_curio_{tok}"
        seed_curiosity_creature(cn)
        comp_c = compete(cn, "hey, how's it going?", reply=None, has_reply=False, budget="deep")
        ok("discriminate: the fresh-creature turn (no reply, no edges) is WON by the CURIOSITY drive",
           comp_c["winner"] == CURIOSITY)

        ok("discriminate: the two distinct turns produce DIFFERENT winners",
           comp_g["winner"] != comp_c["winner"])

        # ============================================================================
        # 2) WINNER == the MAX-signal subsystem (the competition's load-bearing identity).
        # ============================================================================
        for comp, tag in ((comp_g, "grounding-turn"), (comp_c, "curiosity-turn")):
            arms = comp["arms"]
            max_sig = max(a["signal"] for a in arms)
            win_sig = next(a["signal"] for a in arms if a["subsystem"] == comp["winner"])
            ok(f"winner[{tag}]: the winner's signal == the MAX signal across all arms",
               abs(win_sig - max_sig) < 1e-9)
            ok(f"winner[{tag}]: the dominant_signal field == the winner's signal",
               abs(comp["dominant_signal"] - win_sig) < 1e-9)
            ok(f"winner[{tag}]: every arm carries the full contract "
               "(subsystem/signal/fired/mri_stage/why)",
               all(set(a) >= {"subsystem", "signal", "fired", "mri_stage", "evidence", "why"}
                   for a in arms))
            ok(f"winner[{tag}]: all five subsystems competed",
               sorted(a["subsystem"] for a in arms) == sorted(SUBSYSTEMS))

        # ============================================================================
        # 3) EACH SIGNAL IS DERIVED (not hardcoded) — the SAME arm reads DIFFERENT values on a
        #    creature WITH vs WITHOUT that signal. This is the "activity not a constant" proof.
        # ============================================================================
        # CURIOSITY: the signal tracks the engine's OWN _score, which scales with mention count.
        # A 42-mention 'Mike' entity (a SUSPECTED relationship gap ~17.8) reads STRONGER than the
        # fresh creature's top empty-slot gap (the 'name' slot ~9), which in turn reads STRONGER
        # than the grounding creature whose top gaps are suppressed by KNOWN facts. Three distinct
        # creatures, three distinct curiosity signals -> the signal is DERIVED, never a constant.
        mike_nm = f"{SYNTH}_mike_{tok}"
        try:
            wm = world_state.World([])
            for _ in range(42):
                wm.add("you", "knows", "Mike", kind="relationship")
            wm.save(mike_nm)
        except Exception:
            pass
        cur_mike = curiosity_arm(mike_nm, recent_text="tell me about Mike", budget="deep")
        cur_fresh = curiosity_arm(cn, recent_text="hey, how's it going?", budget="deep")
        cur_quiet = curiosity_arm(gn, recent_text="when's my birthday?", budget="deep")
        ok("derived[curiosity]: a 42-mention entity gap reads STRONGER than a fresh empty-slot gap",
           cur_mike["signal"] > cur_fresh["signal"] + 1e-9 and cur_mike["fired"])
        ok("derived[curiosity]: a fresh empty-slot gap reads STRONGER than the gap-suppressed one",
           cur_fresh["signal"] > cur_quiet["signal"] + 1e-9 and cur_fresh["fired"])
        ok("derived[curiosity]: the signal scales with the engine's own _score (not a constant)",
           cur_mike["signal"] != cur_fresh["signal"] != cur_quiet["signal"])

        # RECALL/BINDING: a creature with a KNOWN birthday binds [KNOWN] on the birthday question
        # (strong); a blank creature binds nothing/[UNKNOWN] (weak) on the same question.
        rec_known = recall_arm(gn, "when's my birthday?")
        blank = f"{SYNTH}_blank_{tok}"
        rec_blank = recall_arm(blank, "when's my birthday?")
        ok("derived[recall]: a KNOWN birthday BINDS (fired, signal high) on the birthday question",
           rec_known["fired"] and rec_known["signal"] >= 0.9 - 1e-9)
        ok("derived[recall]: a blank creature does NOT bind a [KNOWN] fact (signal far lower)",
           not rec_blank["fired"] and rec_blank["signal"] < rec_known["signal"])
        ok("derived[recall]: the bound class is exactly spine.KNOWN for the known creature",
           rec_known["evidence"]["strongest_class"] == spine.KNOWN)

        # GROUNDING: a CLEAN reply leaves the gate in control (high, not fired); a BROKEN reply
        # FIRES the gate (low, fired). Same scanners the mouth's backstops use.
        gr_clean = grounding_arm(gn, _CLEAN_REPLY, has_reply=True)
        gr_broken = grounding_arm(gn, _BROKEN_REPLY, has_reply=True)
        ok("derived[grounding]: a CLEAN reply keeps the gate in control (signal high, not fired)",
           (not gr_clean["fired"]) and gr_clean["signal"] >= 0.95 - 1e-9)
        ok("derived[grounding]: a BROKEN reply FIRES the gate (fired, signal far lower)",
           gr_broken["fired"] and gr_broken["signal"] < gr_clean["signal"])
        ok("derived[grounding]: the gate names the real scanner hits (break + confab)",
           bool(gr_broken["evidence"]["breaks"]) and bool(gr_broken["evidence"]["self_narrative"]))
        ok("derived[grounding]: the SAME scanner the mouth uses fires "
           "(metrics.scan_breaks agrees)",
           bool(metrics.scan_breaks(_BROKEN_REPLY)) and not metrics.scan_breaks(_CLEAN_REPLY))

        # OPPORTUNITY: the Mike creature is BOTH a curiosity gap AND a potential offer; a blank
        # creature has no offer. (When meaning isn't seeded an offer may not fire — we assert the
        # signal is at least not GREATER on the blank than on the rich one, i.e. it's derived.)
        opp_rich = opportunity_arm(mike_nm, budget="deep")
        opp_blank = opportunity_arm(blank, budget="deep")
        ok("derived[opportunity]: the Mike creature has a grounded offer; the blank one does not",
           opp_rich["signal"] > opp_blank["signal"] + 1e-9 and opp_rich["fired"])

        # SITUATION: the Mike creature has world edges (a cluster surfaces on a related query); a
        # blank creature has none. The arm's signal tracks edge count -> it is derived.
        sit_rich = situation_arm(mike_nm, "tell me about Mike", hops=2)
        sit_blank = situation_arm(blank, "tell me about Mike", hops=2)
        ok("derived[situation]: a creature WITH world edges surfaces a cluster (fired, signal>0)",
           sit_rich["fired"] and sit_rich["signal"] > 0.0)
        ok("derived[situation]: a blank creature surfaces NO cluster (signal 0)",
           (not sit_blank["fired"]) and sit_blank["signal"] == 0.0)
        ok("derived[situation]: the cluster edge_count drives the signal (rich > blank)",
           sit_rich["evidence"]["edge_count"] > sit_blank["evidence"]["edge_count"])

        # ============================================================================
        # 4) The grounding gate is the SAME wall the mouth fires — diagnosis arm too.
        # ============================================================================
        diag_reply = "Honestly it sounds like you're burning out and should see a doctor."
        gr_diag = grounding_arm(gn, diag_reply, has_reply=True)
        ok("grounding: a diagnosis reply FIRES the gate (the no-diagnosis wall, LAW 003)",
           gr_diag["fired"] and bool(gr_diag["evidence"]["diagnosis"]))
        ok("grounding: the no-diagnosis terms match the mouth's shared source",
           bool(_scan_diagnosis(diag_reply)))

        # ============================================================================
        # 5) DETERMINISM — the same creature/turn yields a byte-identical competition.
        # ============================================================================
        d1 = compete(gn, "when's my birthday?", reply=_CLEAN_REPLY, has_reply=True, budget="deep")
        d2 = compete(gn, "when's my birthday?", reply=_CLEAN_REPLY, has_reply=True, budget="deep")
        ok("determinism: two competitions on the SAME creature/turn are identical",
           json.dumps(d1, sort_keys=True, default=str)
           == json.dumps(d2, sort_keys=True, default=str))
        ok("determinism: the winner is stable across re-derivation",
           d1["winner"] == d2["winner"])

        # ============================================================================
        # 6) GROUNDING dormancy: with NO reply the gate is dormant (low, not fired), so it does
        #    not spuriously dominate — exactly why the no-reply curiosity turn lets curiosity win.
        # ============================================================================
        g_dormant = grounding_arm(gn, None, has_reply=False)
        ok("dormant: with no reply the grounding gate is dormant (low signal, not fired)",
           abs(g_dormant["signal"] - _GROUNDING_DORMANT) < 1e-9 and not g_dormant["fired"])
        ok("dormant: the dormant gate is BELOW the curiosity-turn winner (so it cannot win it)",
           _GROUNDING_DORMANT < comp_c["dominant_signal"])
        ok("dormant: the curiosity-turn's grounding arm IS the dormant value (no reply inspected)",
           any(abs(a["signal"] - _GROUNDING_DORMANT) < 1e-9 for a in comp_c["arms"]
               if a["subsystem"] == GROUNDING))

        # ============================================================================
        # 7) ROBUSTNESS — the entry points never raise on a junk/empty creature.
        # ============================================================================
        ok("robust: compete on a blank creature returns the contract dict",
           set(compete(f"{SYNTH}_x_{tok}", "hi")) >= {"arms", "winner", "dominant_signal", "why"})
        ok("robust: every arm function returns the contract dict on a blank creature",
           all(set(fn) >= {"subsystem", "signal", "fired", "why"} for fn in (
               curiosity_arm(blank), recall_arm(blank, "hi"),
               grounding_arm(blank, None, has_reply=False),
               opportunity_arm(blank), situation_arm(blank, "hi"))))

        # ============================================================================
        # 8) RENDER — never raises and carries the COMPETITION + winner + the competitor legend.
        # ============================================================================
        rep = {"competitions": [comp_g, comp_c]}
        txt = render(rep)
        ok("render: produces a non-empty report", bool(txt.strip()))
        ok("render: names the WINNER + the dominant signal", "WINNER" in txt and "dominant" in txt)
        ok("render: shows all five competitors in the legend",
           all(SUBSYSTEM_INFO[s][0] in txt for s in SUBSYSTEMS))
        ok("render: a single competition renders without raising",
           bool(render_competition(comp_g).strip()))

    # --- the demo build_report is coherent end-to-end -------------------------------------
    full = build_report()
    ok("report: build_report yields two competitions (grounding-wins + curiosity-wins)",
       len(full.get("competitions", [])) == 2)
    ok("report: the two demo competitions have different winners",
       full["competitions"][0]["winner"] != full["competitions"][1]["winner"])

    # --- GUARDRAIL: the whole selftest touched no real .anima file ------------------------
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the whole selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature file leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL CAUSAL-OBSERVATORY SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
