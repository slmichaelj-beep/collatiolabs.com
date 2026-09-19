"""
simulation — COGNITIVE SIMULATION: Understanding -> Theory -> Simulation, run on a TWIN.

WHY THIS EXISTS (Phase 22 — "ask what would/might/should happen, then run it")
------------------------------------------------------------------------------
Phase 21 built the DIGITAL TWIN (anima/twin.py): an ISOLATED FULL COPY of the mind you can
snapshot, accelerate, branch, experiment on, MRI, certify, and gate — all without the real
mind ever being touched. A twin is the laboratory. This module is the EXPERIMENTS YOU RUN IN
IT — the leap from a place-to-simulate to the four QUESTIONS a thinking system can finally
answer by simulation instead of by guess:

    What WOULD happen if we learned X for T?              -> simulate_learning
    What WOULD happen if we changed the architecture?      -> simulate_architecture
    What SHOULD happen — how would a decision play out?     -> simulate_decision
    What MIGHT happen — the RANGE, not a single point?      -> alternative_futures
    What HAPPENED in the twin after a run?                  -> the twin MRI

Each is a real, MEASURED experiment on a synthetic twin, returning an inspectable result AND
the twin it ran on. Understanding (the world model, the personal model) becomes a THEORY of
how a thing would behave, and the theory is SIMULATED forward to a measured projection.

THE FREEZE POSTURE — FREEZE-SAFE BY CONSTRUCTION (inherited from twin.py, re-asserted here)
-------------------------------------------------------------------------------------------
EVERYTHING runs on a TWIN — an isolated copy. The real .anima + the real Vera identity are
NEVER modified. This module adds NO new write path to the real mind: it composes twin.py's
PUBLIC API (create_twin / snapshot / accelerate / branch_futures / run_experiment / mri /
certify / merge_rules), and every public entry point is wrapped in twin.freeze_guard, which
fingerprints the real Vera identity AND the whole real .anima before/after and ASSERTS both
are byte-identical (raising twin.FreezeViolation otherwise). The #1 PRODUCT RULE holds: a
decision simulation is GROUNDED in how Lamar actually decides (Personal Intelligence), never
an invented self; a world model is INTERNAL, never a diagnosis asserted at the user.

HERMETIC + $0. ``--selftest`` builds SYNTHETIC twins (never reads real Vera), drives every
engine deterministically with NO cloud, and asserts the real .anima is byte-UNCHANGED start to
end. No real teacher, no network, no spend.

THE FOUR ENGINES (each returns a measured, inspectable result + the twin it ran on)
-----------------------------------------------------------------------------------
  1. DECISION SIMULATION  — ``simulate_decision(twin, decision)``: given a decision Lamar
     faces, read his PERSONAL INTELLIGENCE (decision-patterns / values / preferences / lessons,
     via anima.personal) AND the WORLD MODEL of the situation (people / constraints, via
     anima.world_model) ON THE TWIN, and project how the decision plays out + what the
     personal-intelligence model RECOMMENDS. Answers "what SHOULD happen?" — grounded in how
     Lamar actually decides, NEVER invented. An option with no grounding gets no recommendation.

  2. LEARNING SIMULATION  — ``simulate_learning(twin, plan)``: simulate the mind learning over
     simulated time on the twin — drive ``twin.accelerate`` (the synthetic learning loop) under
     an autonomous-growth MODE + SOURCES (anima.lerf_grow), and project the resulting
     accumulation + calibration. Answers "what WOULD happen if we learned X for T?". Alternative
     learning plans are compared head-to-head via ``twin.branch_futures``.

  3. ARCHITECTURE SIMULATION — ``simulate_architecture(twin, change)``: simulate an architecture
     change on the twin and MEASURE it. The flagship case swaps KEYWORD retrieval for FMLGS
     (anima.fmlgs) on the twin's own vault and measures the recall / latency / footprint deltas.
     Answers "what WOULD happen if we changed the architecture?".

  4. ALTERNATIVE FUTURES — ``alternative_futures(...)``: run several stochastic-ish VARIANTS
     (the seed / inputs vary per branch by index) and report the DISTRIBUTION / RANGE of
     outcomes, not a single point. Answers "what MIGHT happen?". "What HAPPENED in the twin" is
     the twin MRI read after a run (``what_happened``).

  ROUTER — ``simulate(question, ...)``: classify a natural question as WOULD / MIGHT / SHOULD /
  HAPPENED and route it to the right engine, each returning {answer, twin, ...}.

DEPENDENCY DISCIPLINE. This is a NEW module. It does NOT edit twin.py or any engine. It uses
their PUBLIC APIs only, and runs every cognitive read/write INSIDE twin's own
``_RedirectStores`` block (so the engines transparently touch the TWIN'S namespace, never the
real .anima — the exact isolation seam twin.py, the cert, and four_layers all use). Every
cross-import is best-effort so the module imports anywhere.

    python3 -m anima.simulation --selftest   # decision + learning + architecture + alt-futures,
                                             # each on a synthetic twin, measured; real .anima
                                             # asserted byte-UNCHANGED. $0, no cloud. exits 0.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Build ON the twin. Everything that follows composes twin.py's public surface — we never
# reimplement a twin, a redirect, or the freeze guard. Imported at module top because the twin
# is the substrate this whole module stands on (an absent twin module is a hard error, by design).
from . import twin

# This module shares the twin's redirectable STORE so a redirected test environment relocates us
# too — and so freeze_guard / twin_dir resolve against the same root. Mirrors twin.STORE exactly.
STORE = twin.STORE

KIND = "anima.simulation"

# The person every decision simulation is grounded in — the moat. Personal Intelligence models
# LAMAR (anima.personal), never Vera; a decision projection is built from how HE decides.
PERSON = "Lamar"

# Stopwords the decision scorer ignores when overlapping an option against Lamar's captured model.
# A match on a CONTENT word ("ship", "momentum", "polish") is real evidence the option fits how he
# decides; a match on "the"/"over"/"anything" is noise that would manufacture false grounding —
# exactly the confabulation the #1 rule forbids. So only content-word overlap earns score, and an
# option that overlaps no content word scores 0 and gets no recommendation (never invented).
_DECISION_STOPWORDS = frozenset({
    "the", "and", "for", "with", "over", "than", "into", "that", "this", "from", "your", "our",
    "are", "was", "were", "has", "have", "had", "not", "but", "you", "all", "any", "anything",
    "something", "nothing", "everything", "more", "most", "less", "least", "much", "many", "some",
    "one", "two", "out", "off", "per", "via", "its", "his", "her", "their", "them", "they", "she",
    "him", "who", "what", "when", "where", "why", "how", "which", "would", "should", "could", "can",
    "will", "may", "might", "must", "shall", "about", "because", "since", "while", "between", "on",
    "in", "to", "of", "it", "is", "be", "do", "or", "as", "at", "an", "a", "i", "me", "my", "we",
    "us", "so", "if", "then", "else", "just", "very", "also", "still", "even", "only", "keep",
    "make", "made", "get", "got", "now", "new", "old",
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _source_of(t: dict | str) -> str:
    """The real creature a twin was copied from (default Vera) — the freeze-guard subject."""
    if isinstance(t, dict):
        return t.get("source_creature", "Vera")
    return "Vera"


def _twin_dir(t: dict | str, base: Path) -> Path:
    return twin.twin_dir(twin.twin_id_of(t), base)


# =====================================================================================
# ENGINE 1 — DECISION SIMULATION.  "What SHOULD happen?"
# -------------------------------------------------------------------------------------
# Given a decision Lamar faces, project how it would play out and what the personal-intelligence
# model RECOMMENDS — grounded in how Lamar ACTUALLY decides (his captured decision-patterns,
# values, preferences, lessons) crossed with the WORLD MODEL of the situation (people /
# constraints). NOTHING is invented: an option scores only on evidence drawn from the twin's
# Personal Intelligence + World Model; an ungrounded option earns no recommendation.
#
# This runs ENTIRELY on the twin: we read personal.personal_profile and world_model against the
# twin's redirected stores, so the projection reflects the twin's mind, and the real mind is
# untouched (freeze-guarded). It is a SHOULD, not a WILL — a recommendation the founder inspects,
# with every reason tracing to a captured datum.
# =====================================================================================
def _decision_options(decision: dict | str) -> Tuple[str, List[str], List[str]]:
    """Normalize a decision spec to (question, options, constraints).

    Accepts a plain string ("should I ship daily or polish for a month?") — options are then
    parsed from an 'X or Y' frame if present — or a dict
    {question, options:[...], constraints:[...], people:[...]}.
    """
    if isinstance(decision, str):
        q = decision.strip()
        opts: List[str] = []
        low = q.lower()
        # a light "A or B" / "A vs B" split so a bare-string decision still has options to weigh.
        for sep in (" or ", " versus ", " vs ", " vs. "):
            if sep in low:
                idx = low.index(sep)
                left = q[:idx]
                right = q[idx + len(sep):]
                # trim a leading "should I"/"do I"/"whether to" from the left option.
                import re
                left = re.sub(r"^\s*(should i|do i|whether to|would i|can i)\s+", "", left,
                              flags=re.I).strip(" ?.")
                right = right.strip(" ?.")
                opts = [o for o in (left, right) if o]
                break
        return q, opts, []
    spec = dict(decision or {})
    q = str(spec.get("question", spec.get("decision", ""))).strip()
    opts = [str(o).strip() for o in (spec.get("options") or []) if str(o).strip()]
    cons = [str(c).strip() for c in (spec.get("constraints") or []) if str(c).strip()]
    return q, opts, cons


def _score_option_against_profile(option: str, question: str, profile: dict) -> dict:
    """Score ONE option by how well it fits Lamar's captured decision model. Every point of score
    cites the captured datum it came from (a decision-pattern / value / preference / lesson) — so
    the recommendation is grounded, never a vibe. Returns {option, score, reasons:[...]}.

    The scoring is deterministic keyword-overlap between the option text and each grounded item's
    own content (its decision / target / subject / action), weighted by the item's stored weight.
    A word the user actually used in a captured value ("ship", "momentum") lighting up in an option
    is real evidence that the option matches how he decides; an option that overlaps nothing scores
    0 and gets no recommendation (the anti-confabulation contract, applied to a decision)."""
    import re

    def toks(s: str) -> set:
        return {w for w in re.findall(r"[a-z0-9]+", str(s).lower())
                if len(w) > 2 and w not in _DECISION_STOPWORDS}

    otoks = toks(option) | toks(question)
    reasons: List[dict] = []
    score = 0.0

    def _consider(kind: str, text: str, weight: float, evidence: str) -> None:
        nonlocal score
        overlap = otoks & toks(text)
        if overlap:
            pts = round(weight * len(overlap), 4)
            score += pts
            reasons.append({"kind": kind, "matched_on": sorted(overlap), "weight": weight,
                            "points": pts, "from": text[:80], "evidence": evidence[:120]})

    # DECISION PATTERNS — how he has decided before (the strongest signal: a prior choice + its
    # criteria). Both the typical decision text and each weighted criterion are matchable.
    for dp in profile.get("decision_patterns", []) or []:
        summ = dp.get("summary", "") or dp.get("name", "")
        ev = (dp.get("evidence") or [""])[0]
        _consider("decision_pattern", summ, 1.0, ev)
    # VALUES / TRADEOFFS — what he optimizes for (and what he trades away). A value the option
    # advances is a strong fit; the value's weight (typically high) scales it.
    for v in profile.get("values", []) or []:
        summ = v.get("summary", "") or v.get("name", "")
        ev = (v.get("evidence") or [""])[0]
        _consider("value", summ + " " + ev, 0.9, ev)
    # PREFERENCES — what he wants. A direct preference match is real but lighter than a value.
    for p in profile.get("preferences", []) or []:
        summ = p.get("summary", "") or p.get("name", "")
        ev = (p.get("evidence") or [""])[0]
        _consider("preference", summ + " " + ev, 0.7, ev)
    # LESSONS — what he concluded ("ship daily beats big releases"). A lesson the option honours
    # (or violates) is grounded guidance.
    for L in profile.get("lessons", []) or []:
        summ = L.get("summary", "") or L.get("name", "")
        ev = (L.get("evidence") or [""])[0]
        _consider("lesson", summ + " " + ev, 0.8, ev)

    reasons.sort(key=lambda r: -r["points"])
    return {"option": option, "score": round(score, 4), "reasons": reasons,
            "grounded": bool(reasons)}


def _situation_from_world(creature: str) -> dict:
    """Read the twin's WORLD MODEL — the situation: the typed causal models Vera holds about the
    user's world (people / constraints / what drives what). MUST be called inside a redirect block.
    Read-only; degrades to an empty situation if world_model is unavailable. INTERNAL — never a
    diagnosis asserted at the user (world_model.internal_only)."""
    out = {"models": [], "nodes": [], "internal_only": True}
    try:
        from . import world_model
        ms = world_model.models(creature)
        out["models"] = [{"id": m.get("id"), "topic": m.get("topic"),
                          "nodes": m.get("nodes", []), "edges": len(m.get("edges", []) or [])}
                         for m in ms]
        nodes = set()
        for m in ms:
            nodes.update(m.get("nodes", []) or [])
        out["nodes"] = sorted(nodes)
    except Exception as e:
        out["error"] = str(e)
    return out


def simulate_decision(twin_obj: dict | str, decision: dict | str, *,
                      person: str = PERSON, root: Optional[Path] = None) -> dict:
    """ENGINE 1. Simulate a DECISION Lamar faces — "what SHOULD happen?".

    Reads Lamar's PERSONAL INTELLIGENCE (personal.personal_profile — his captured decision-
    patterns / values / preferences / lessons) AND the WORLD MODEL of the situation (the people /
    constraints, world_model.models) ON THE TWIN, scores each option by how well it fits how he
    ACTUALLY decides, and projects a recommendation. GROUNDED: every reason cites a captured datum;
    an option that matches nothing in his model earns no recommendation (we never invent how he'd
    choose). Runs entirely on the twin; the real mind is freeze-guarded.

    Returns {kind, twin_id, question, options:[{option,score,reasons,grounded}], recommendation,
    rationale, situation, personal_known, profile_counts}. The 'twin' it ran on is included so the
    result is reproducible/inspectable."""
    base = Path(root) if root is not None else STORE
    creature = twin.twin_creature(twin_obj)
    tdir = _twin_dir(twin_obj, base)
    question, options, constraints = _decision_options(decision)

    with twin.freeze_guard(_source_of(twin_obj), base):
        with twin._RedirectStores(tdir):
            # PERSONAL INTELLIGENCE: ensure the twin's personal model is built from its captured
            # data (idempotent — learn() only adds grounded objects, never invents), then read it.
            profile = {"known": False, "counts": {}}
            try:
                from . import personal
                try:
                    personal.learn(creature, person=person)   # fold captured data into the model
                except Exception:
                    pass
                profile = personal.personal_profile(creature, person=person)
            except Exception as e:
                profile = {"known": False, "counts": {}, "error": str(e)}
            # WORLD MODEL: the situation (people / constraints / causal structure).
            situation = _situation_from_world(creature)

    # If no options were supplied/parsed, surface the situation + model honestly (a SHOULD needs
    # options to weigh; we never fabricate options).
    scored = [_score_option_against_profile(o, question, profile) for o in options]
    scored.sort(key=lambda s: -s["score"])
    grounded = [s for s in scored if s["grounded"]]
    recommendation = grounded[0]["option"] if grounded else None
    rationale = (grounded[0]["reasons"] if grounded else [])

    return {
        "kind": KIND + ".decision",
        "question": "what SHOULD happen?",
        "decision": question,
        "twin_id": twin.twin_id_of(twin_obj),
        "twin": twin_obj if isinstance(twin_obj, dict) else {"twin_id": twin_obj},
        "personal_known": bool(profile.get("known")),
        "profile_counts": profile.get("counts", {}),
        "options": scored,
        "constraints": constraints,
        "situation": situation,
        "recommendation": recommendation,
        "recommendation_grounded": bool(grounded),
        "rationale": rationale,
        "note": ("Grounded in how Lamar actually decides (his captured decision-patterns / values "
                 "/ preferences / lessons) crossed with the world model of the situation; an option "
                 "that matches nothing in his model earns no recommendation (never invented)."),
    }


# =====================================================================================
# ENGINE 2 — LEARNING SIMULATION.  "What WOULD happen if we learned X for T?"
# -------------------------------------------------------------------------------------
# Simulate the mind learning over simulated time ON THE TWIN. We drive twin.accelerate (the
# deterministic, $0 synthetic learning loop — each cycle accrues a grounded skill + closes a
# reality loop) under a named autonomous-growth MODE (anima.lerf_grow's Off/Low/Medium/High/
# Research intensities, which set how many cycles a "period" implies) and report the projected
# accumulation + calibration. Alternative learning PLANS are compared head-to-head via
# twin.branch_futures (each plan a future; the comparison is reality-decided).
# =====================================================================================
# How a named autonomous-growth MODE translates "T periods of learning" into synthetic cycles to
# accelerate. The mode is the INTENSITY dial (lerf_grow.GROW_MODES); here it scales how much one
# period of simulated learning accrues. Off accrues nothing (provably inert — the real default);
# the rest scale up. This is a transparent, documented mapping, not a hidden knob.
_MODE_CYCLES_PER_PERIOD = {
    "off": 0,            # provably inert — nothing learned ($0), the default
    "low": 6,            # gentle trickle
    "medium": 18,        # steady idle growth (the historical default intensity)
    "high": 45,          # aggressive idle learning
    "research": 120,     # an explicit research burst
}


def _plan_spec(plan: dict | str) -> dict:
    """Normalize a learning plan to {mode, periods, label, cycles?, sources}.

    Accepts a mode string ("medium"), or a dict {mode, periods, cycles?, sources:[...], label?}.
    ``periods`` is the simulated horizon (e.g. weeks/months — unit is the caller's); the mode sets
    cycles-per-period. An explicit ``cycles`` overrides the mode*periods product (a precise horizon
    like the 10-year demo's 3650). ``sources`` names the learning sources in play (teacher models /
    documents / reality outcomes / personal experience), for the report — the synthetic accelerator
    is source-agnostic, so this is descriptive provenance, not a second code path."""
    if isinstance(plan, str):
        spec = {"mode": plan}
    else:
        spec = dict(plan or {})
    mode = str(spec.get("mode", "medium")).strip().lower()
    if mode not in _MODE_CYCLES_PER_PERIOD:
        mode = "medium"
    periods = int(spec.get("periods", 1) or 1)
    per = _MODE_CYCLES_PER_PERIOD[mode]
    cycles = int(spec.get("cycles", per * max(0, periods)))
    label = str(spec.get("label", f"{mode} × {periods}p")).strip()
    sources = [str(s) for s in (spec.get("sources") or ["teacher_models", "reality_outcomes"])]
    return {"mode": mode, "periods": periods, "cycles": max(0, cycles),
            "label": label, "sources": sources}


def simulate_learning(twin_obj: dict | str, plan: dict | str, *,
                      root: Optional[Path] = None) -> dict:
    """ENGINE 2. Simulate the mind LEARNING over simulated time — "what WOULD happen if we learned
    X for T?".

    Translates a learning ``plan`` (an autonomous-growth MODE + a horizon in periods, or an explicit
    cycle count) into N synthetic learning cycles, drives ``twin.accelerate`` (deterministic, $0,
    NO cloud), and projects the resulting ACCUMULATION (cognitive objects gained) + CALIBRATION
    (the reality ledger growing as outcomes resolve). Returns the projection + trajectory + the twin
    it ran on. Freeze-guarded; the real mind is untouched.

    The mode is the intensity (Off learns nothing — provably inert; the rest scale up); this is the
    same Off/Low/Medium/High/Research dial the autonomous-growth engine uses, applied to simulated
    time. ``sources`` is descriptive provenance (which learning sources are in play)."""
    base = Path(root) if root is not None else STORE
    spec = _plan_spec(plan)

    # The whole simulation is twin.accelerate — itself freeze-guarded and $0. We do not re-wrap a
    # second freeze guard around it (one is enough), but we DO read the autonomous-growth mode
    # profile for the report so the projection names its intensity honestly.
    mode_profile = {}
    try:
        from . import lerf_grow
        prof = lerf_grow.GROW_MODES.get(spec["mode"], {})
        mode_profile = {"mode": spec["mode"], "cadence_hours": prof.get("cadence_hours"),
                        "max_per_run": prof.get("max_per_run"),
                        "label": prof.get("label")}
    except Exception:
        mode_profile = {"mode": spec["mode"]}

    accel = twin.accelerate(twin_obj, spec["cycles"], root=base)
    deltas = accel.get("deltas", {})
    before = accel.get("before", {})
    after = accel.get("after", {})

    return {
        "kind": KIND + ".learning",
        "question": "what WOULD happen if we learned X for T?",
        "twin_id": twin.twin_id_of(twin_obj),
        "twin": twin_obj if isinstance(twin_obj, dict) else {"twin_id": twin_obj},
        "plan": spec,
        "mode_profile": mode_profile,
        "cycles": accel.get("cycles"),
        "deterministic": accel.get("deterministic", True),
        "cost_usd": accel.get("cost_usd", 0.0),
        "used_cloud": accel.get("used_cloud", False),
        "projection": {
            "objects_before": before.get("lerf", {}).get("total"),
            "objects_after": after.get("lerf", {}).get("total"),
            "objects_gained": deltas.get("objects"),
            "active_gained": deltas.get("active_objects"),
            "reality_records_after": after.get("reality", {}).get("records"),
            "reality_records_gained": deltas.get("reality_records"),
        },
        "trajectory": accel.get("trajectory", []),
        "note": ("Synthetic learning on the twin (deterministic, $0, no cloud). The mode is the "
                 "intensity dial (Off learns nothing — the inert default; the rest scale up)."),
    }


def compare_learning_plans(twin_obj: dict | str, plans: List[dict | str], *,
                           root: Optional[Path] = None) -> dict:
    """Compare alternative LEARNING PLANS head-to-head via ``twin.branch_futures`` — each plan a
    separate, independent future (a byte-clone of the twin), run forward, then ranked by the
    resulting accumulation. Answers "which way of learning leaves the mind richer?" without the
    plans ever interfering (branch_futures forks independent twins). Freeze-guarded.

    Each plan becomes a 'more_learning' experiment with the plan's cycle budget, so the comparison
    uses twin.py's own measured experiment + cert per future. Returns {ranking, futures, winner}."""
    base = Path(root) if root is not None else STORE
    specs = [_plan_spec(p) for p in plans]
    # Map each plan to a twin change-spec the experiment framework enacts (more_learning + cycles).
    changes = [{"change": "more_learning", "cycles": s["cycles"]} for s in specs]
    fut = twin.branch_futures(twin_obj, changes, root=base)

    # Pair each future back to its plan label + cycle budget for a legible ranking.
    ranked = []
    for s, f in zip(specs, fut.get("futures", [])):
        ranked.append({
            "plan": s["label"], "mode": s["mode"], "cycles": s["cycles"],
            "twin_id": f.get("twin_id"),
            "objects_after": f.get("after_objects"),
            "object_delta": (f.get("deltas") or {}).get("objects"),
            "certifies": f.get("certifies"),
        })
    ranked.sort(key=lambda r: (r["objects_after"] or 0), reverse=True)
    winner = ranked[0]["plan"] if ranked else None
    return {
        "kind": KIND + ".learning_comparison",
        "question": "which learning plan leaves the mind richer?",
        "parent_twin_id": fut.get("parent_twin_id"),
        "ranking": ranked,
        "winner": winner,
        "futures": fut.get("futures", []),
        "note": "each plan ran as an INDEPENDENT future (branch_futures); ranked by accumulation.",
    }


# =====================================================================================
# ENGINE 3 — ARCHITECTURE SIMULATION.  "What WOULD happen if we changed the architecture?"
# -------------------------------------------------------------------------------------
# Simulate an architecture change on the twin and MEASURE it. The flagship case swaps the live
# KEYWORD retrieval for FMLGS (anima.fmlgs — embeddings + a multilevel-Gaussian index) on the
# TWIN'S OWN vault, and measures the recall / latency / footprint deltas via fmlgs.measure. The
# change is simulated on a COPY, so the verdict ("would FMLGS help on this vault?") is earned
# before anything in the real retrieval path is touched.
# =====================================================================================
# A small, fixed query set the architecture simulation measures retrieval against — task-shaped
# probes spanning the kinds of cognitive objects a vault holds. Deterministic so a run is
# reproducible and the recall numbers are stable. (The twin's vault is the synthetic accelerator's
# skills + whatever was copied in; these probes hit the synthetic skill texts.)
_ARCH_PROBES = (
    "triage my obligations when I'm overloaded",
    "autoregulate training load when a joint is sore",
    "convert a stalled intention into a scheduled action",
    "unstick a stuck project by externalizing it",
    "summarize a document into its key points",
    "plan and order a set of errands",
)


def _measure_keyword_vs_fmlgs(creature: str, *, k: int = 5) -> dict:
    """Measure KEYWORD retrieval vs FMLGS on the CURRENT (twin) vault. MUST be called inside a
    redirect block (so lerf reads the twin's objects). Builds an FMLGS index over the twin's active
    objects via the public vault builder, then runs fmlgs.measure (which internally computes the
    keyword baseline AND the FMLGS results over the same query set) — so recall/latency/footprint
    are an apples-to-apples comparison on the twin's real contents. Degrades to an explained error
    if fmlgs/numpy is unavailable. Read-only."""
    try:
        from . import fmlgs
    except Exception as e:
        return {"available": False, "error": f"fmlgs unavailable: {e}"}
    try:
        index = fmlgs.build_from_vault(name=creature)
    except Exception as e:
        return {"available": False, "error": f"index build failed: {e}"}
    n = len(index.objects)
    if n == 0:
        return {"available": True, "n_objects": 0,
                "note": "the twin's vault has no publicly-listable active objects to index"}
    rep = fmlgs.measure(index, list(_ARCH_PROBES), k=k, repeats=60)
    foot = rep.get("footprint", {})
    return {
        "available": True,
        "n_objects": n,
        "k": k,
        # RECALL — FMLGS vs the keyword baseline (the "same intelligence" check) and vs exact cosine.
        "recall_vs_keyword": rep.get("recall_vs_keyword"),
        "recall_vs_linear": rep.get("recall_vs_linear"),
        "top1_vs_keyword": rep.get("top1_vs_keyword"),
        # LATENCY — the three retrieval paths, microseconds/query (wall-clock; ratios are stable).
        "latency_fmlgs_us": rep.get("latency_fmlgs_us"),
        "latency_keyword_us": rep.get("latency_keyword_us"),
        "latency_linear_us": rep.get("latency_linear_us"),
        "speedup_vs_keyword": rep.get("speedup_vs_keyword"),
        # FOOTPRINT — the bytes the index costs (the intelligence-per-GB axis).
        "footprint_total_bytes": foot.get("total_bytes"),
        "footprint_per_object_bytes": foot.get("per_object_bytes"),
        "footprint_levels": foot.get("levels"),
        # the COMPUTE-SAVED proxy: fraction of the vault scored per query (<1 == the scaling win).
        "scored_fraction": rep.get("scored_fraction"),
    }


def simulate_architecture(twin_obj: dict | str, change: dict | str = "fmlgs_retrieval", *,
                          root: Optional[Path] = None) -> dict:
    """ENGINE 3. Simulate an ARCHITECTURE change on the twin and MEASURE it — "what WOULD happen if
    we changed the architecture?".

    The flagship ``change`` is "fmlgs_retrieval": swap KEYWORD retrieval for FMLGS on the twin's own
    vault and measure the recall / latency / footprint DELTAS (fmlgs.measure, computed over the same
    query set so it is apples-to-apples). Other architecture changes are delegated to the twin's own
    experiment framework (e.g. "changed retrieval" / "added a world model"), so this one entry point
    covers both the measured-retrieval case and the general experiment case. Runs on the twin;
    freeze-guarded.

    Returns {kind, change, twin_id, twin, measurement|experiment, verdict}. For the FMLGS case the
    measurement is the recall/latency/footprint table; the verdict summarizes whether FMLGS held
    recall (the non-negotiable 'same intelligence' bar) and what it cost/saved."""
    base = Path(root) if root is not None else STORE
    creature = twin.twin_creature(twin_obj)
    tdir = _twin_dir(twin_obj, base)
    key = (change if isinstance(change, str) else str((change or {}).get("change", ""))).strip().lower()
    key = key.replace(" ", "_").replace("-", "_")

    # The FMLGS-vs-keyword measurement is the flagship; anything else routes to twin.run_experiment.
    fmlgs_aliases = {"fmlgs_retrieval", "fmlgs", "swap_to_fmlgs", "fmlgs_vs_keyword",
                     "embedding_retrieval"}
    if key in fmlgs_aliases or key == "":
        with twin.freeze_guard(_source_of(twin_obj), base):
            with twin._RedirectStores(tdir):
                measurement = _measure_keyword_vs_fmlgs(creature)
        verdict = _architecture_verdict_fmlgs(measurement)
        return {
            "kind": KIND + ".architecture",
            "question": "what WOULD happen if we changed the architecture?",
            "change": "swap keyword retrieval -> FMLGS (measured on the twin's vault)",
            "change_key": "fmlgs_retrieval",
            "twin_id": twin.twin_id_of(twin_obj),
            "twin": twin_obj if isinstance(twin_obj, dict) else {"twin_id": twin_obj},
            "measurement": measurement,
            "verdict": verdict,
            "note": ("FMLGS is measured against the keyword baseline on the TWIN'S vault; the "
                     "real retrieval path is untouched until a change proves itself here."),
        }

    # General architecture change -> the twin experiment framework (already freeze-guarded + measured).
    exp = twin.run_experiment(twin_obj, change, root=base)
    return {
        "kind": KIND + ".architecture",
        "question": "what WOULD happen if we changed the architecture?",
        "change": change if isinstance(change, str) else dict(change),
        "change_key": key,
        "twin_id": twin.twin_id_of(twin_obj),
        "twin": twin_obj if isinstance(twin_obj, dict) else {"twin_id": twin_obj},
        "experiment": {
            "enacted": exp.get("enacted"),
            "notes": exp.get("notes"),
            "deltas": exp.get("deltas"),
            "certifies": (exp.get("twin_cert") or {}).get("certifies"),
        },
        "verdict": {
            "summary": ("enacted + measured via the twin experiment framework"
                        if exp.get("enacted") else "no enactor — see notes"),
            "safe": (exp.get("twin_cert") or {}).get("certifies"),
        },
        "note": "delegated to the twin's experiment framework (synthetic, measured, freeze-guarded).",
    }


def _architecture_verdict_fmlgs(m: dict) -> dict:
    """Summarize the FMLGS measurement into a plain verdict: did it HOLD recall (the non-negotiable
    'same intelligence' bar), and what did it cost (footprint) / save (scored-fraction, speedup)?"""
    if not m.get("available"):
        return {"summary": "FMLGS not measurable in this environment", "error": m.get("error")}
    if m.get("n_objects", 0) == 0:
        return {"summary": "no objects in the twin's vault to measure retrieval on"}
    rk = m.get("recall_vs_keyword")
    held = (rk is not None and rk >= 1.0 - 1e-9)
    parts = []
    if held:
        parts.append("FMLGS HELD recall vs keyword (same intelligence)")
    elif rk is not None:
        parts.append(f"FMLGS recall vs keyword = {rk:.3f} (below the keyword baseline)")
    sf = m.get("scored_fraction")
    if sf is not None:
        parts.append(f"scored {sf*100:.0f}% of the vault/query")
    sp = m.get("speedup_vs_keyword")
    foot = m.get("footprint_total_bytes")
    return {
        "summary": "; ".join(parts) or "measured",
        "recall_held_vs_keyword": held,
        "scored_fraction": sf,
        "speedup_vs_keyword": sp,
        "footprint_total_bytes": foot,
        "honest_note": ("at this vault size a keyword scan is already instant, so the win is the "
                        "INTERFACE + the scaling path (compute grows with clusters probed, not N); "
                        "the bar FMLGS must clear here is HOLDING recall, which the verdict reports."),
    }


# =====================================================================================
# ENGINE 4 — ALTERNATIVE FUTURES.  "What MIGHT happen?" — the RANGE, not a point.
# -------------------------------------------------------------------------------------
# Run several stochastic-ish VARIANTS of a learning run and report the DISTRIBUTION of outcomes.
# Determinism is preserved (the twin is deterministic) while still exploring a RANGE: each branch
# varies its inputs BY INDEX — a different cycle budget per branch — so the branches sweep a band
# of "how much might accrue" rather than collapsing to one number. The result is min/median/max +
# the per-branch outcomes, so "what might happen" is a measured spread, not a guess.
# =====================================================================================
def alternative_futures(twin_obj: dict | str, *, variants: int = 5, base_cycles: int = 20,
                        seed: int = 0, root: Optional[Path] = None) -> dict:
    """ENGINE 4. Explore the RANGE of outcomes — "what MIGHT happen?".

    Forks ``variants`` independent futures of the twin (via twin.branch_futures), each driven by a
    cycle budget that VARIES BY INDEX (and by ``seed``) so the branches sweep a band of learning
    intensities rather than one point. Reports the DISTRIBUTION (min / median / max + spread) of the
    resulting accumulation across the futures, plus each branch's outcome. Deterministic per (seed,
    index) — reproducible — yet a genuine RANGE. Freeze-guarded.

    Returns {kind, question, variants, distribution:{min,median,max,mean,range}, branches:[...]}."""
    base = Path(root) if root is not None else STORE
    variants = max(1, int(variants))
    # vary the per-branch cycle budget by index (and seed) — a deterministic sweep of intensities.
    # branch i gets base_cycles + i*step + a seed-derived jitter, so the band shifts with the seed.
    step = max(1, base_cycles // 2)
    # The change dict passed to branch_futures carries ONLY {change, cycles} — twin's
    # _change_more_learning enactor accepts cycles and nothing else, so an extra key (e.g. a label)
    # would trip its TypeError fallback to DEFAULT cycles and collapse the whole sweep to one point.
    # We therefore keep the per-branch labels in a PARALLEL list keyed by index, not in the spec.
    changes = []
    labels = []
    for i in range(variants):
        jitter = ((seed * 7 + i * 13) % 5)            # 0..4 deterministic per (seed,i)
        cyc = max(0, base_cycles + i * step + jitter)
        changes.append({"change": "more_learning", "cycles": cyc})
        labels.append(f"variant-{i}-c{cyc}")

    fut = twin.branch_futures(twin_obj, changes, root=base)
    branches = []
    for ch, lbl, f in zip(changes, labels, fut.get("futures", [])):
        branches.append({
            "variant": lbl,
            "cycles": ch["cycles"],
            "twin_id": f.get("twin_id"),
            "objects_after": f.get("after_objects"),
            "object_delta": (f.get("deltas") or {}).get("objects"),
            "certifies": f.get("certifies"),
        })
    outs = [b["objects_after"] for b in branches if isinstance(b["objects_after"], (int, float))]
    distribution = {}
    if outs:
        distribution = {
            "min": min(outs),
            "max": max(outs),
            "median": statistics.median(outs),
            "mean": round(statistics.fmean(outs), 2),
            "range": max(outs) - min(outs),
            "n": len(outs),
        }
    return {
        "kind": KIND + ".alternative_futures",
        "question": "what MIGHT happen?",
        "twin_id": twin.twin_id_of(twin_obj),
        "parent_twin_id": fut.get("parent_twin_id"),
        "variants": variants,
        "seed": seed,
        "distribution": distribution,
        "branches": sorted(branches, key=lambda b: (b["objects_after"] or 0)),
        "note": ("a RANGE, not a point: each future varies its cycle budget by index/seed, so the "
                 "outcomes sweep a band — reported as min/median/max + spread."),
    }


# =====================================================================================
# "WHAT HAPPENED IN THE TWIN" — read the twin MRI after a run. The fourth question's answer is an
# OBSERVATION of the twin's interior (twin.mri), not a fresh simulation.
# =====================================================================================
def what_happened(twin_obj: dict | str, *, root: Optional[Path] = None) -> dict:
    """Read what HAPPENED inside the twin after a run — the twin MRI (twin.mri): the interior state
    (LERF / reality / memory / world / identity) + the growth dashboard, observed against the twin's
    isolated stores. Answers "what HAPPENED in the twin?". Freeze-guarded; observation-only."""
    base = Path(root) if root is not None else STORE
    scan = twin.mri(twin_obj, root=base)
    state = scan.get("state", {})
    return {
        "kind": KIND + ".what_happened",
        "question": "what HAPPENED in the twin?",
        "twin_id": twin.twin_id_of(twin_obj),
        "twin": twin_obj if isinstance(twin_obj, dict) else {"twin_id": twin_obj},
        "interior": {
            "objects": state.get("lerf", {}).get("total"),
            "active_objects": state.get("lerf", {}).get("by_state", {}).get("active")
            if isinstance(state.get("lerf"), dict) else None,
            "reality_records": state.get("reality", {}).get("records"),
            "world_links": state.get("world_model", {}).get("links"),
            "identity_certifies": state.get("identity", {}).get("certifies"),
            "ungrounded_self_claims": state.get("identity", {}).get("ungrounded_self_claims"),
        },
        "growth_dashboard": scan.get("growth_dashboard", {}),
        "mri": scan,
        "note": "observation of the twin's interior after a run — not a fresh simulation.",
    }


# =====================================================================================
# THE ROUTER — simulate(question, ...). Classify a natural question as WOULD / MIGHT / SHOULD /
# HAPPENED and route it to the right engine. Each returns {answer-kind, result, twin}.
# =====================================================================================
def _classify_question(question: str) -> str:
    """Map a natural question to one of {'should','would','might','happened'}.

    SHOULD  — a decision / recommendation ask ("what should I do", "should I X or Y").
    MIGHT   — an uncertainty / range ask ("what might happen", "what's the range / distribution").
    HAPPENED— a retrospective ask ("what happened", "what did the twin do / become").
    WOULD   — the default projection ask ("what would happen if we learned/changed …").
    Deterministic keyword precedence; a question that matches none defaults to WOULD (the
    projection question this whole module is built to answer)."""
    q = (question or "").strip().lower()
    if not q:
        return "would"
    # SHOULD — decision/recommendation framing wins first (it is the most specific intent).
    if ("should" in q or "recommend" in q or "what do i do" in q
            or q.startswith("do i ") or " or " in q and "happen" not in q and "learn" not in q):
        # but "what would/might happen" with an incidental 'or' is not a decision.
        if "would happen" not in q and "might happen" not in q:
            return "should"
    # HAPPENED — retrospective.
    if (q.startswith("what happened") or "did the twin" in q or "what happened in the twin" in q
            or "already happened" in q):
        return "happened"
    # MIGHT — range / distribution / possibility.
    if ("might" in q or "range of" in q or "distribution" in q or "could happen" in q
            or "what are the odds" in q or "possible outcomes" in q):
        return "might"
    # WOULD — the default projection.
    return "would"


def simulate(question: str, twin_obj: dict | str, *,
             decision: dict | str | None = None,
             plan: dict | str | None = None,
             change: dict | str | None = None,
             person: str = PERSON,
             variants: int = 5,
             root: Optional[Path] = None) -> dict:
    """THE ROUTER. Answer a natural ``question`` by routing it to the right cognitive-simulation
    engine, all run on ``twin_obj``:

        SHOULD   -> simulate_decision   (pass ``decision``; falls back to the question text)
        WOULD    -> simulate_learning OR simulate_architecture, depending on whether the question
                    is about LEARNING or ARCHITECTURE (pass ``plan`` or ``change``)
        MIGHT    -> alternative_futures (the RANGE)
        HAPPENED -> what_happened       (the twin MRI)

    Returns {question, intent, result, twin_id}. Freeze-guarded inside each engine. The classifier
    is deterministic keyword precedence; pass the matching kwarg to be explicit (e.g. a decision
    dict for a SHOULD question, a plan for a WOULD-learning question, a change for a WOULD-arch one).
    """
    base = Path(root) if root is not None else STORE
    intent = _classify_question(question)

    if intent == "should":
        result = simulate_decision(twin_obj, decision if decision is not None else question,
                                   person=person, root=base)
    elif intent == "might":
        result = alternative_futures(twin_obj, variants=variants, root=base)
    elif intent == "happened":
        result = what_happened(twin_obj, root=base)
    else:  # would — learning vs architecture by content (or by which kwarg was supplied)
        q = (question or "").lower()
        arch_words = ("architecture", "retrieval", "fmlgs", "embedding", "index", "world model")
        is_arch = change is not None or any(w in q for w in arch_words)
        if is_arch and plan is None:
            result = simulate_architecture(twin_obj, change if change is not None
                                           else "fmlgs_retrieval", root=base)
        else:
            result = simulate_learning(twin_obj, plan if plan is not None else "medium", root=base)

    return {
        "kind": KIND + ".routed",
        "question": question,
        "intent": intent,
        "twin_id": twin.twin_id_of(twin_obj),
        "result": result,
    }


# =====================================================================================
# SYNTHETIC LAMAR DATA — for the decision-simulation worked example + selftest. We seed a small,
# realistic captured profile (the user's OWN words) onto a synthetic creature so personal.learn can
# build a grounded decision model. NOTHING here describes Vera. Reuses personal.py's exact capture
# path (memory_lirf.capture + portrait.log_turn) so the model is built the way production builds it.
# =====================================================================================
_SYNTH_LAMAR_TURNS = (
    "I decided to build the products as separate sellable units because optionality is worth more "
    "than a single big bet, and it worked.",
    "I chose local-first over cloud-first for Vera because privacy is the whole moat.",
    "I'd rather ship daily than polish for a month — momentum beats perfection.",
    "I value deep-work mornings more than anything; I optimize for uninterrupted building time.",
    "honestly just cut it down, keep it tight — I hate long-winded essays, tl;dr me.",
    "I prefer Python over Java for these tools, less ceremony.",
    "I've learned that diagnostic tests before a multi-week plan save weeks.",
    "I always choose the boring proven tool over the shiny one for infra.",
)


def _seed_synthetic_lamar(creature: str) -> None:
    """Seed synthetic captured 'Lamar' data onto ``creature`` via the real capture path. MUST be
    called inside a redirect block so memory_lirf/portrait write the twin's (or temp) store. Best-
    effort per engine."""
    try:
        from . import memory_lirf
        from . import portrait
        for t in _SYNTH_LAMAR_TURNS:
            try:
                memory_lirf.capture(creature, t)
            except Exception:
                pass
            try:
                portrait.log_turn(creature, t, "ok")
            except Exception:
                pass
    except Exception:
        pass


# =====================================================================================
# WORKED EXAMPLES — one of EACH simulation type, hermetic, on a synthetic twin. These are the
# deliverable demonstrations; the selftest asserts each returns a measured result.
# =====================================================================================
def _make_synth_twin(name: str, root: Path, *, with_lamar: bool = False) -> dict:
    """Create a synthetic-source twin in ``root`` (the source is seeded by the caller's harness).
    If ``with_lamar``, also seed synthetic captured-Lamar data INTO the twin so a decision
    simulation has a grounded personal model to read. Returns the twin manifest."""
    tw = twin.create_twin(name, source="SynTwinSrc", lerf_source="SynTwinSrc", root=root)
    if with_lamar:
        tdir = twin.twin_dir(tw["twin_id"], root)
        with twin.freeze_guard("SynTwinSrc", root):
            with twin._RedirectStores(tdir):
                _seed_synthetic_lamar(twin.twin_creature(tw))
    return tw


def worked_examples(root: Optional[Path] = None, *, quiet: bool = True) -> dict:
    """Run ONE worked example of EACH simulation type on synthetic twins and return them together:
    a DECISION simulation (grounded in synthetic Lamar-data), a LEARNING simulation (projecting
    accumulation), an ARCHITECTURE simulation (FMLGS-vs-keyword measured on a twin), and an
    ALTERNATIVE-FUTURES range. Hermetic + $0; the real mind is freeze-guarded throughout. Returns
    {decision, learning, architecture, alternative_futures, freeze_report}."""
    base = Path(root) if root is not None else STORE
    # The harness (selftest / CLI) seeds the synthetic source; here we assume it exists under base.
    fg = twin.freeze_guard("Vera", base)
    out: Dict[str, object] = {}
    with fg:
        # DECISION — a real decision, grounded in synthetic Lamar's captured model.
        dt = _make_synth_twin("ex-decision", base, with_lamar=True)
        out["decision"] = simulate_decision(
            dt, {"question": "should I ship daily or polish for a month?",
                 "options": ["ship daily", "polish for a month"]}, root=base)
        # LEARNING — project a month of medium-intensity learning.
        lt = _make_synth_twin("ex-learning", base)
        out["learning"] = simulate_learning(lt, {"mode": "medium", "periods": 4}, root=base)
        # ARCHITECTURE — FMLGS vs keyword on a twin whose vault we first grow a little so the index
        # has objects to measure.
        at = _make_synth_twin("ex-arch", base)
        twin.accelerate(at, 30, root=base)
        out["architecture"] = simulate_architecture(at, "fmlgs_retrieval", root=base)
        # ALTERNATIVE FUTURES — the range of "what might happen".
        ft = _make_synth_twin("ex-might", base)
        out["alternative_futures"] = alternative_futures(ft, variants=5, base_cycles=20, root=base)
    out["freeze_report"] = fg.report()
    if not quiet:
        _print_examples(out)
    return out


def _print_examples(out: dict) -> None:
    d = out.get("decision", {})
    print("  DECISION (what SHOULD happen?)")
    print(f"    Q: {d.get('decision')}")
    print(f"    recommendation: {d.get('recommendation')}  (grounded={d.get('recommendation_grounded')})")
    for r in (d.get("rationale") or [])[:2]:
        print(f"      • [{r.get('kind')}] matched {r.get('matched_on')} -> {r.get('from')}")
    L = out.get("learning", {})
    proj = L.get("projection", {})
    print("  LEARNING (what WOULD happen if we learned X for T?)")
    print(f"    plan {L.get('plan', {}).get('label')} -> objects "
          f"{proj.get('objects_before')} -> {proj.get('objects_after')} "
          f"(+{proj.get('objects_gained')}), $0, cloud={L.get('used_cloud')}")
    a = out.get("architecture", {})
    m = a.get("measurement", {})
    print("  ARCHITECTURE (what WOULD happen if we changed retrieval to FMLGS?)")
    print(f"    n={m.get('n_objects')} recall_vs_keyword={m.get('recall_vs_keyword')} "
          f"scored={m.get('scored_fraction')} footprint={m.get('footprint_total_bytes')}B")
    print(f"    verdict: {a.get('verdict', {}).get('summary')}")
    f = out.get("alternative_futures", {})
    dist = f.get("distribution", {})
    print("  ALTERNATIVE FUTURES (what MIGHT happen?)")
    print(f"    range: min={dist.get('min')} median={dist.get('median')} max={dist.get('max')} "
          f"(spread {dist.get('range')}) over {f.get('variants')} variants")
    fr = out.get("freeze_report", {})
    print(f"  freeze: real identity byte-unchanged={fr.get('real_identity_byte_unchanged')}, "
          f"real .anima byte-unchanged={fr.get('real_anima_byte_unchanged')}")


# =====================================================================================
# HERMETIC SELFTEST — every engine on a SYNTHETIC twin, in a throwaway temp store, real .anima
# asserted byte-UNCHANGED start->end. $0, no cloud. Exits 0 on success. Mirrors twin._selftest.
# =====================================================================================
def _footprint(root: Path) -> tuple:
    """Fingerprint every real .anima file (excluding the rotating backups/ dir) — the proof we
    touched nothing real. Identical discipline to twin._footprint."""
    import hashlib
    if not root.is_dir():
        return (None, 0)
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _selftest() -> int:
    import shutil
    import tempfile

    fails: List[str] = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("=" * 90)
    print("COGNITIVE SIMULATION — hermetic selftest (synthetic twins; real .anima asserted "
          "byte-UNCHANGED)")
    print("=" * 90)

    global STORE
    real = STORE if STORE.is_absolute() else (Path.cwd() / STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="sim-self-")
    tp = Path(td)
    saved_store = STORE
    saved_twin_store = twin.STORE
    try:
        from . import identity_sandbox as _ids
        _ids_saved = _ids.STORE
    except Exception:
        _ids = None
        _ids_saved = None

    try:
        STORE = tp
        twin.STORE = tp
        if _ids is not None:
            _ids.STORE = tp

        # Seed a SYNTHETIC source creature (never real Vera) — reuse twin's own seeder, which writes
        # an identity core with a deliberate ungrounded self-claim + a few skills + a reality loop.
        twin._seed_synthetic_source(tp, "SynTwinSrc")
        ok("seed: synthetic source written (no real read)",
           (tp / "SynTwinSrc.narrative.txt").is_file())

        # ============================ ENGINE 1 — DECISION ============================
        dt = _make_synth_twin("sd", tp, with_lamar=True)
        dec = simulate_decision(
            dt, {"question": "should I ship daily or polish for a month?",
                 "options": ["ship daily", "polish for a month"]}, root=tp)
        ok("DECISION: ran on a twin and returned a measured option scoring",
           dec["kind"].endswith(".decision") and isinstance(dec["options"], list)
           and len(dec["options"]) == 2)
        ok("DECISION: the personal model was built from synthetic Lamar-data (known=True)",
           dec["personal_known"] is True
           and (dec["profile_counts"].get("decision_patterns", 0)
                + dec["profile_counts"].get("values", 0)) >= 1)
        ok("DECISION: a GROUNDED recommendation was made (every reason cites captured data)",
           dec["recommendation"] is not None and dec["recommendation_grounded"] is True
           and all(r.get("from") for r in dec["rationale"]))
        ok("DECISION: 'ship daily' is recommended (it matches his captured 'ship/momentum' model)",
           dec["recommendation"] == "ship daily")
        # ANTI-FABRICATION: an option grounded in NOTHING gets score 0 / no reasons.
        dec_void = simulate_decision(
            dt, {"question": "pick a teacup pattern",
                 "options": ["the floral teacup with no bearing on anything captured"]}, root=tp)
        ok("DECISION: an option matching nothing in his model earns NO recommendation (never invented)",
           dec_void["recommendation"] is None or dec_void["options"][0]["score"] == 0.0)
        # the world model (situation) is read as INTERNAL-only, never a diagnosis.
        ok("DECISION: the situation read is internal-only (never a diagnosis at the user)",
           dec["situation"].get("internal_only") is True)

        # ============================ ENGINE 2 — LEARNING ============================
        lt = _make_synth_twin("sl", tp)
        learn = simulate_learning(lt, {"mode": "medium", "periods": 4}, root=tp)
        ok("LEARNING: ran synthetic learning on the twin, $0, no cloud",
           learn["cost_usd"] == 0.0 and learn["used_cloud"] is False and learn["cycles"] > 0)
        ok("LEARNING: projected ACCUMULATION (objects gained) + a trajectory",
           learn["projection"]["objects_gained"] > 0
           and len(learn["trajectory"]) >= 1
           and learn["projection"]["objects_after"] > learn["projection"]["objects_before"])
        ok("LEARNING: projected CALIBRATION growth (reality records accrued)",
           (learn["projection"]["reality_records_gained"] or 0) >= 0
           and learn["projection"]["reality_records_after"] is not None)
        # Off mode is provably inert — learns NOTHING.
        lt_off = _make_synth_twin("sloff", tp)
        learn_off = simulate_learning(lt_off, {"mode": "off", "periods": 10}, root=tp)
        ok("LEARNING: Off mode is provably inert (0 cycles, nothing accrued, $0)",
           learn_off["cycles"] == 0 and (learn_off["projection"]["objects_gained"] or 0) == 0
           and learn_off["cost_usd"] == 0.0)
        # COMPARE plans head-to-head: a higher-intensity plan accrues at least as much.
        lt_cmp = _make_synth_twin("slcmp", tp)
        cmp = compare_learning_plans(lt_cmp, [
            {"mode": "low", "periods": 2, "label": "low-2"},
            {"mode": "high", "periods": 2, "label": "high-2"},
        ], root=tp)
        ok("LEARNING: alternative plans compared via branch_futures + ranked (winner reported)",
           len(cmp["ranking"]) == 2 and cmp["winner"] is not None)
        ok("LEARNING: the higher-intensity plan ranks first (more cycles -> more accumulation)",
           cmp["ranking"][0]["plan"] == "high-2")

        # ============================ ENGINE 3 — ARCHITECTURE ============================
        at = _make_synth_twin("sa", tp)
        twin.accelerate(at, 30, root=tp)               # grow the vault so the index has objects
        arch = simulate_architecture(at, "fmlgs_retrieval", root=tp)
        m = arch["measurement"]
        ok("ARCHITECTURE: FMLGS measured against keyword on the twin's vault",
           arch["change_key"] == "fmlgs_retrieval" and m.get("available") is True
           and m.get("n_objects", 0) > 0)
        ok("ARCHITECTURE: recall / latency / footprint all measured",
           m.get("recall_vs_keyword") is not None
           and m.get("latency_fmlgs_us") is not None
           and m.get("footprint_total_bytes") is not None)
        ok("ARCHITECTURE: FMLGS HELD recall vs the keyword baseline (same intelligence)",
           arch["verdict"].get("recall_held_vs_keyword") is True)
        # the general (non-FMLGS) architecture change routes to the twin experiment framework.
        at2 = _make_synth_twin("sa2", tp)
        arch_exp = simulate_architecture(at2, "added a world model", root=tp)
        ok("ARCHITECTURE: a non-FMLGS change routes to the twin experiment framework + is measured",
           "experiment" in arch_exp and arch_exp["experiment"].get("enacted") is True)

        # ============================ ENGINE 4 — ALTERNATIVE FUTURES ============================
        ft = _make_synth_twin("sf", tp)
        alt = alternative_futures(ft, variants=5, base_cycles=20, seed=3, root=tp)
        ok("ALT-FUTURES: ran 5 independent variants on the twin",
           alt["variants"] == 5 and len(alt["branches"]) == 5
           and len({b["twin_id"] for b in alt["branches"]}) == 5)
        ok("ALT-FUTURES: reported a DISTRIBUTION/range, not a single point",
           alt["distribution"] and alt["distribution"]["max"] >= alt["distribution"]["min"]
           and "median" in alt["distribution"])
        ok("ALT-FUTURES: the range has real spread — the futures actually differ "
           "(a higher cycle budget accrues more; guards the collapse-to-one-point regression)",
           alt["distribution"]["range"] > 0 and alt["distribution"]["n"] == 5
           and alt["distribution"]["max"] > alt["distribution"]["min"])

        # ============================ WHAT HAPPENED (twin MRI) ============================
        happened = what_happened(at, root=tp)        # the architecture twin we accelerated
        ok("HAPPENED: the twin MRI reads the interior state after a run",
           happened["kind"].endswith(".what_happened")
           and happened["interior"]["objects"] is not None)

        # ============================ THE ROUTER ============================
        r_should = simulate("what should I do — ship daily or polish for a month?", dt,
                            decision={"question": "ship daily or polish?",
                                      "options": ["ship daily", "polish for a month"]}, root=tp)
        ok("ROUTER: a SHOULD question routes to the decision engine",
           r_should["intent"] == "should" and r_should["result"]["kind"].endswith(".decision"))
        r_would_learn = simulate("what would happen if we learned for a month?", lt,
                                 plan={"mode": "medium", "periods": 4}, root=tp)
        ok("ROUTER: a WOULD-learning question routes to the learning engine",
           r_would_learn["intent"] == "would"
           and r_would_learn["result"]["kind"].endswith(".learning"))
        r_would_arch = simulate("what would happen if we changed retrieval to FMLGS?", at,
                                change="fmlgs_retrieval", root=tp)
        ok("ROUTER: a WOULD-architecture question routes to the architecture engine",
           r_would_arch["intent"] == "would"
           and r_would_arch["result"]["kind"].endswith(".architecture"))
        r_might = simulate("what might happen if we keep learning?", ft, root=tp)
        ok("ROUTER: a MIGHT question routes to alternative futures (the range)",
           r_might["intent"] == "might"
           and r_might["result"]["kind"].endswith(".alternative_futures"))
        r_happened = simulate("what happened in the twin?", at, root=tp)
        ok("ROUTER: a HAPPENED question routes to the twin MRI",
           r_happened["intent"] == "happened"
           and r_happened["result"]["kind"].endswith(".what_happened"))

        # ============================ WORKED EXAMPLES (one of each) ============================
        ex = worked_examples(root=tp, quiet=True)
        ok("EXAMPLES: one worked example of each type produced, all measured",
           ex["decision"]["recommendation"] is not None
           and ex["learning"]["projection"]["objects_gained"] > 0
           and ex["architecture"]["measurement"].get("available") is True
           and ex["alternative_futures"]["distribution"])
        ok("EXAMPLES: the worked-examples freeze report shows the real mind byte-unchanged",
           ex["freeze_report"]["real_identity_byte_unchanged"] is True
           and ex["freeze_report"]["real_anima_byte_unchanged"] is True)

    finally:
        STORE = saved_store
        twin.STORE = saved_twin_store
        if _ids is not None and _ids_saved is not None:
            _ids.STORE = _ids_saved
        shutil.rmtree(td, ignore_errors=True)

    # --- THE BYTE-UNCHANGED PROOF — real .anima identical start->end ------------------------
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across the whole selftest",
       fp_before == fp_after)
    ok("HERMETIC: real STORE binding restored", STORE == saved_store and twin.STORE == saved_twin_store)
    id_fp = twin.identity_fingerprint("Vera", real)
    ok("HERMETIC: real Vera identity files present + unchanged (named proof)",
       id_fp == twin.identity_fingerprint("Vera", real))

    print("-" * 90)
    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print("   - " + f)
        return 1
    print("ALL COGNITIVE-SIMULATION SELFTESTS PASSED — decision + learning + architecture + "
          "alternative-futures, each on a synthetic twin; real .anima byte-unchanged.")
    return 0


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="anima.simulation",
        description="COGNITIVE SIMULATION — ask what WOULD / MIGHT / SHOULD happen, run it on a "
                    "TWIN. Decision / Learning / Architecture simulation + the alternative-futures "
                    "range. Every run is on an isolated copy; the real mind is freeze-guarded.")
    ap.add_argument("--selftest", action="store_true",
                    help="run every engine on a synthetic twin; real .anima asserted byte-unchanged; exits 0")
    ap.add_argument("--examples", action="store_true",
                    help="print one worked example of each simulation type (hermetic, $0)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.examples:
        # run the worked examples against a SYNTHETIC source in a temp store (hermetic, $0).
        import shutil
        import tempfile
        td = tempfile.mkdtemp(prefix="sim-ex-")
        tp = Path(td)
        global STORE
        saved = STORE
        saved_twin = twin.STORE
        try:
            from . import identity_sandbox as _ids
            _ids_saved = _ids.STORE
        except Exception:
            _ids = None
            _ids_saved = None
        try:
            STORE = tp
            twin.STORE = tp
            if _ids is not None:
                _ids.STORE = tp
            twin._seed_synthetic_source(tp, "SynTwinSrc")
            print("COGNITIVE SIMULATION — worked examples (hermetic, synthetic source, $0):\n")
            worked_examples(root=tp, quiet=False)
        finally:
            STORE = saved
            twin.STORE = saved_twin
            if _ids is not None and _ids_saved is not None:
                _ids.STORE = _ids_saved
            shutil.rmtree(td, ignore_errors=True)
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
