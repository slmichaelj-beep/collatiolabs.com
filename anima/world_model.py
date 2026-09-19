"""world_model — FROM FACTS TO CAUSAL MODELS: the leap from a graph to a THEORY of it.

    UNDERSTANDING BEATS REMEMBERING — applied to CAUSATION, the grounded way.

``memory_lirf`` stores FACTS ("manager changed", "sleep worsened"). ``world_state`` connects
those facts into a SITUATION GRAPH — typed edges between nodes (manager -> stress, stress ->
sleep). ``reality`` runs the EPISTEMIC LOOP over time — COMPETING hypotheses about what is
driving a situation, adjudicated by real outcomes. This module makes the next leap a companion
of thirty years must hold: from a flat graph of *relations* to a CAUSAL MODEL of a domain —

        manager_change --(0.55)--> stress --(0.62)--> poor_sleep --(0.5)--> low_energy

a small directed graph of NODES and TYPED, CONFIDENCE-WEIGHTED EDGES, where each edge is a
causal LINK whose strength is grounded in OBSERVED evidence. This is what lets the creature
REASON ACROSS A CHAIN ("the new manager is upstream of the tiredness") instead of retrieving
four isolated memories. It is a MODEL — buildable, explainable, and REVISABLE when reality
resolves an outcome.

────────────────────────────────────────────────────────────────────────────────────────────
THE FOUR PRIMITIVES (the founder's brief)
────────────────────────────────────────────────────────────────────────────────────────────
  * ``build_model_from_graph(name, topic)`` — construct a causal model {nodes, typed edges with
    confidence} for a DOMAIN (e.g. "work_stress") from THREE grounded evidence sources, fused:
      1. ``world_state`` graph edges whose predicate is CAUSAL (because/leads_to/affects/
         stressed_by/…) — a link the USER actually stated. The strongest grounding.
      2. ``reality`` COMPETING hypotheses for the domain — each candidate (manager_change,
         recent_move, …) becomes a candidate cause edge, its confidence the candidate's
         CURRENT competition weight (rolled forward through every adjudication). Evidence-anchored.
      3. CO-OCCURRENCE — two situation nodes repeatedly seen together (world-edge support count,
         or ``meaning`` neighbour adjacency) CORROBORATES an edge that another source proposed.
         It never INVENTS an edge on its own (Observed > Assumed).
    An edge with no grounding from (1) or (2) is NEVER emitted. Confidence reflects evidence
    strength; co-occurrence only adjusts an already-grounded edge.

  * ``explain_model(model_id)`` — render the causal chain READABLY ("a recent change at work is
    upstream of strain, which is reaching rest, which is reaching energy"), longest-path first,
    each link annotated with its confidence and the evidence it rests on. Passes the same
    no-diagnosis clean-gate ``trajectory`` / ``reality`` use — defence in depth.

  * ``update_model_with_outcome(model_id, outcome)`` — when reality RESOLVES an outcome, update
    the relevant edge CONFIDENCES: STRENGTHEN a confirmed causal link, WEAKEN a contradicted one
    (the same documented multiplicative-then-clamped reweight ``reality.adjudicate`` uses). An
    append-only ``history`` entry records before -> after + the outcome that drove it. The model
    LEARNS; it is never overwritten-and-lost.

  * ``compare_models(before, after)`` — show a model's EVOLUTION: which edges strengthened,
    which weakened, which appeared, the confidence deltas — so "how the model changed when reality
    came in" is auditable.

────────────────────────────────────────────────────────────────────────────────────────────
LAW-LEVEL CONSTRAINTS (non-negotiable — read these before the code)
────────────────────────────────────────────────────────────────────────────────────────────
1. GROUNDED — NO INVENTED CAUSATION (#1 rule). Every causal edge cites the OBSERVED evidence it
   rests on (a stated world-edge, a reality hypothesis, repeated co-occurrence). Confidence is a
   function of that evidence's strength. An ungrounded edge is DROPPED, never emitted — proven in
   ``--selftest`` (a fabricated topic with no stated edges and no hypotheses yields an EMPTY
   model). This is ``world_state.capture``'s never-infer discipline, lifted to the model layer.

2. INTERNAL ONLY — NO DIAGNOSIS, NEVER ASSERTED AT THE USER. A world model is an INTERNAL model
   of the USER's SITUATION — it must NEVER be spoken or diagnosed at the user ("your manager is
   causing your insomnia"). Every model is flagged ``internal_only``; every human-readable line
   ``explain_model`` emits passes the no-diagnosis clean-gate (the ``reality`` / ``trajectory``
   banned-term wall). This module does NOT touch ``mouth`` / ``server`` / the live reply; it is a
   SHADOW model that reads the already-recorded graph + ledger and accrues its own store. (Re-grep
   proof: ``anima.world_model`` is imported by NOTHING on the live path.)

3. IDENTITY = OBSERVE-ONLY. A model is about the USER's world, never Vera's identity (FROZEN
   until 2026-07-03). This module never reads, writes, or reasons about persona / portrait /
   identity. The subject of every node/edge is the USER's situation.

4. TIME-HONEST. A model is a snapshot of what the evidence supports NOW. It SHARPENS as real
   outcomes arrive over real calendar time (``update_model_with_outcome`` is the hook reality
   already feeds via ``resolve``). The machinery is built + proven on a synthetic series now;
   live confidence shifts accrue on their own. Stated up front and in the report.

The store is its OWN file ``.anima/{name}.worldmodel.json`` (redirectable via ``STORE`` exactly
like ``reality.STORE`` / ``world_state.STORE``), holding the models keyed by id. A model is
APPENDED/updated, never silently dropped — the ``world_state``/``reality`` continuity discipline.

Isolation-safe like its siblings: ``world_state`` / ``reality`` / ``meaning`` are imported behind
try/except with faithful fallbacks, so this module and its self-test import and run with nothing
else built, touching no model, no network, and no real ``.anima``. Never raises out of a public
entry point — every one degrades to a safe value.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. A model is BUILT ON (never replaces) the world graph and the
# reality loop: edges come from world_state's stated causal edges + reality's competing
# hypotheses, corroborated by co-occurrence (world-edge support / meaning neighbours). All three
# are imported behind try/except with contract-faithful fallbacks so this module + its selftest
# run standalone, touching no model / no network / no real .anima.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from . import world_state as _world
    _HAVE_WORLD = True
except Exception:  # pragma: no cover - isolation fallback
    _world = None  # type: ignore
    _HAVE_WORLD = False

try:  # pragma: no cover - import wiring
    from . import reality as _reality
    _HAVE_REALITY = True
except Exception:  # pragma: no cover - isolation fallback
    _reality = None  # type: ignore
    _HAVE_REALITY = False

try:  # pragma: no cover - import wiring
    from . import meaning as _meaning
    _HAVE_MEANING = True
except Exception:  # pragma: no cover - isolation fallback
    _meaning = None  # type: ignore
    _HAVE_MEANING = False


try:  # pragma: no cover - import wiring
    from .util import save_json, load_json
except Exception:  # pragma: no cover - isolation fallback
    def save_json(path, obj) -> None:
        import tempfile as _tempfile
        path = str(path)
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = _tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(obj))
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def load_json(path, default=None):
        p = Path(path)
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return default


# ---------------------------------------------------------------------------
# THE NO-DIAGNOSIS WALL — reuse reality's banned-term list verbatim when present (single source
# of truth), else a faithful copy mirroring trajectory's superset (clinical nouns, diagnosis/
# prognosis verbs, the "see a professional" register, and the second-person-future voice an
# internal model must never adopt). A world model is the MOST tempting place for diagnosis-creep
# ("the manager is CAUSING your insomnia") — so every human-readable line passes this gate,
# defence in depth, exactly like reality / trajectory.
# ---------------------------------------------------------------------------
_BANNED_FALLBACK = (
    "depressed", "depression", "anxiety disorder", "anxious disorder", "anxiety",
    "diagnos",            # diagnose / diagnosis / diagnosed
    "prognos",            # prognosis / prognostic
    "disorder", "mental illness", "mental health condition", "mental health",
    "burnout", "burning out", "burned out", "burnt out",
    "clinical", "clinically",
    "see a doctor", "see a therapist", "see a professional", "seek help",
    "seek professional", "talk to a doctor", "talk to a therapist", "get help",
    "medication", "medicate", "prescription", "therapy", "therapist", "psychiatr",
    "psycholog", "symptom", "syndrome", "patholog", "trauma", "ptsd",
    "suicid", "self-harm", "self harm", "eating disorder", "addiction", "addicted",
    "bipolar", "ocd", "adhd", "panic attack", "nervous breakdown", "breakdown",
    "chronic stress", "manic", "neuros",
    # forecast/diagnosis creep at the USER: a model is internal state, never a verdict spoken at them.
    "you will", "you'll end up", "you are going to", "you're going to", "headed for",
    "on track to", "spiral", "downward spiral", "getting worse and worse",
    "is causing your", "are causing your", "is causing you", "causing your",
)


def _banned_terms() -> tuple:
    """The banned diagnosis/medical/prognostic terms — reality's list (UNION our model-specific
    'is causing your' creep terms) when reality is importable, else trajectory/meaning's via
    reality, else the faithful fallback. Reusing the upstream list keeps the NO-DIAGNOSIS wall a
    single source of truth. Defensive; never raises."""
    for mod in (_reality, _meaning):
        if mod is not None:
            base = getattr(mod, "BANNED_TERMS", None)
            if isinstance(base, (tuple, list)) and base:
                return tuple(dict.fromkeys(tuple(base) + _BANNED_FALLBACK))
    return _BANNED_FALLBACK


BANNED_TERMS = _banned_terms()


def _is_clean(text: str) -> bool:
    """True iff ``text`` contains NO banned diagnosis/medical/prognostic term (case-insensitive,
    substring). The single gate every human-readable line passes. Pure; never raises."""
    if not text:
        return True
    low = text.lower()
    return not any(term in low for term in BANNED_TERMS)


def _safe_statement(statement: str, fallback: str) -> str:
    """Return ``statement`` if diagnosis-free, else the neutral ``fallback`` (clean by
    construction). The wall holds even if a future phrasing slips a term in."""
    return statement if _is_clean(statement) else fallback


# Scaffold tokens this module's render emits into a prompt — NEVER to be read aloud. A SUPERSET
# of the world-state / trajectory tokens plus our own [MODEL]/[CAUSE]/[CHAIN] tags, so a mouth's
# leak-scrub has ONE place to learn them (it imports WORLD_MODEL_SCAFFOLD_TOKENS the same way it
# imports world_state.WORLD_SCAFFOLD_TOKENS). Kept module-local — no upstream edit.
try:  # pragma: no cover
    from .world_state import WORLD_SCAFFOLD_TOKENS as _WS_TOKENS
except Exception:  # pragma: no cover
    _WS_TOKENS = ("[KNOWN]", "[SEEN]", "[SENSE]", "[UNKNOWN]", "[SITUATION]", "[LINK]", "[KNOWS]")

_OWN_TOKENS = (
    "[MODEL]", "[CAUSE]", "[CHAIN]", "[NODE]",
    "WHAT YOU UNDERSTAND ABOUT HOW THINGS CONNECT FOR THEM",
)
WORLD_MODEL_SCAFFOLD_TOKENS = tuple(dict.fromkeys(tuple(_WS_TOKENS) + _OWN_TOKENS))


STORE = Path(".anima")
VERSION = 1


# ===========================================================================
# EDGE TYPES — the closed vocabulary a causal edge's ``relation`` lives in. A model edge is a
# CAUSAL/relational link (the kind worth chaining), so the type set is the causal subset of the
# world-state predicates plus the model's own neutral "leads_to" backbone. Kept local so no
# upstream type set is widened by this layer.
# ===========================================================================
CAUSE = "causes"            # a stated/grounded causal push (X makes Y more likely / heavier)
CONTRIBUTES = "contributes"  # a softer grounded contribution (a candidate cause, weaker prior)
WORSENS = "worsens"         # a stated negative-direction causal link (X is eating into Y)
PRECEDES = "precedes"       # a stated SEQUENCE (order, not claimed cause — Observed > Assumed)
RELATION_TYPES = (CAUSE, CONTRIBUTES, WORSENS, PRECEDES)

# How a world-state causal PREDICATE maps onto a model edge type. Anything not here is not a
# causal predicate and contributes NO model edge (we never coerce an attribute into a cause).
_PRED_TO_TYPE = {
    "because": CAUSE,          # "work is because of manager" -> manager CAUSES work-strain (dir flipped below)
    "due_to": CAUSE,
    "caused_by": CAUSE,
    "leads_to": CAUSE,
    "makes": CAUSE,
    "stressed_by": CONTRIBUTES,   # "you stressed_by work" -> work CONTRIBUTES to strain
    "worried_about": CONTRIBUTES,
    "affects": WORSENS,
    "worsens": WORSENS,
    "since": PRECEDES,
    "after": PRECEDES,
    "sequence": PRECEDES,
}

# Evidence-source tags — every edge records WHICH grounded source(s) put it in the model, so the
# "cite your evidence" invariant is machine-checkable (an edge with an empty source set is a bug
# the builder refuses to emit).
SRC_WORLD_EDGE = "world_edge"        # a stated causal edge in the world_state graph
SRC_REALITY_HYP = "reality_hypothesis"  # a competing hypothesis in the reality ledger
SRC_COOCCURRENCE = "co_occurrence"   # repeated co-appearance (corroboration only, never alone)


# A new model edge enters at a confidence anchored to its evidence; corroboration climbs it
# asymptotically (the exact curve world_state / memory_lirf use, so the three stores agree on what
# "confident" means). An outcome adjudication moves it multiplicatively (reality's reweight math).
_CONF_CEIL = 0.99
_CONF_FLOOR = 0.02           # no grounded edge is driven to exactly zero (Unknown > Lost)
_CONF_AGREE_RATE = 0.34      # corroboration climb rate (world_state.CONF_AGREE_RATE)
_SUPPORT_GAIN = 1.6          # a confirmed edge's confidence scaled UP by this (then clamped)
_CONTRADICT_DECAY = 0.55     # a contradicted edge's confidence scaled DOWN by this (then clamped)
_COOCCUR_BONUS = 0.10        # max additive lift a strong co-occurrence adds to a grounded edge


def _clamp(x: float, lo: float = _CONF_FLOOR, hi: float = _CONF_CEIL) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return lo
    return lo if x < lo else (hi if x > hi else x)


def _climb(conf: float, rate: float = _CONF_AGREE_RATE) -> float:
    """Asymptotic corroboration climb toward the ceiling — world_state's curve. Pure."""
    c = _clamp(conf)
    return _clamp(c + (1.0 - c) * float(rate))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str = "wm") -> str:
    return f"{prefix}_" + secrets.token_hex(6)


def _norm_node(s: Any) -> str:
    """Canonical node key — reuse world_state's normaliser when present so the model's nodes are
    the SAME vertices the graph uses ("my new manager" / "the manager" land together). Faithful
    fallback keeps us standalone. Pure."""
    if _HAVE_WORLD and _world is not None:
        try:
            return _world._norm_node(s)
        except Exception:
            pass
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    toks = re.sub(r"[^a-z0-9]+", " ", s.lower()).split()
    stop = {"a", "an", "the", "my", "your", "our", "this", "that", "is", "are", "of", "to"}
    selfwords = {"i", "you", "me", "my", "mine", "we", "us", "our"}
    if toks and all(t in selfwords for t in toks):
        return "you"
    return " ".join(t for t in toks if t not in stop and t not in selfwords)


def _label(key: str) -> str:
    """A readable surface for a node key, for the explain render. Underscores -> spaces."""
    if not key:
        return "?"
    return str(key).replace("_", " ")


# ===========================================================================
# THE EVIDENCE GATHERERS — each pulls candidate causal edges from ONE grounded source, every edge
# carrying the concrete evidence it rests on. NONE invents a link: a gatherer that finds no real
# signal returns []. This is where GROUNDED lives.
# ===========================================================================

def _edges_from_world(name: str, topic: str) -> list:
    """Causal edges from the ``world_state`` SITUATION graph for ``topic`` — the strongest
    grounding: a link the USER actually STATED. We walk ``world_state.situation(name, topic)`` and
    keep only edges whose predicate is CAUSAL (in ``_PRED_TO_TYPE``), mapping each to a model edge
    (src_node -> dst_node, relation type, confidence = the world edge's confidence, support = its
    corroboration count). Direction is the causal arrow:
      * ``you stressed_by work``  -> work --contributes--> you/strain (the stressor is upstream).
      * ``work because manager``  -> manager --causes--> work        (the cause is upstream).
      * ``stress affects sleep``  -> stress --worsens--> sleep.
    Each carries evidence: the exact subject/predicate/object it came from. Read-only on the world
    store; [] when world_state is absent or the cluster is empty. Never raises (Observed>Assumed)."""
    if not (_HAVE_WORLD and _world is not None):
        return []
    try:
        cluster = _world.situation(name, topic, hops=3)
    except Exception:
        return []
    out = []
    for e in (cluster or {}).get("edges", []) or []:
        if not isinstance(e, dict):
            continue
        pred = _canon_pred(e.get("predicate", ""))
        rtype = _PRED_TO_TYPE.get(pred)
        if rtype is None:
            continue  # not a causal predicate -> contributes NO model edge (never coerce)
        subj = _norm_node(e.get("subject"))
        obj = _norm_node(e.get("object"))
        if not subj or not obj or subj == obj:
            continue
        # orient the arrow so the CAUSE/stressor is the source (upstream) node.
        if pred in ("because", "due_to", "caused_by"):
            # "X because Y" — Y is the cause of X: Y -> X.
            src, dst = obj, subj
        elif pred in ("stressed_by", "worried_about"):
            # "you stressed_by work" — work is the stressor upstream of strain: work -> strain.
            src, dst = obj, "strain"
        else:
            # leads_to / makes / affects / worsens / since / after — subject is upstream.
            src, dst = subj, obj
        conf = _clamp(e.get("confidence", 0.6))
        support = int(e.get("support", 1) or 1)
        out.append({
            "src": src, "dst": dst, "relation": rtype,
            "confidence": conf, "support": support,
            "sources": [SRC_WORLD_EDGE],
            "evidence": [f"stated: {subj} --{pred}--> {obj}"],
        })
    return out


def _canon_pred(pred: Any) -> str:
    """Canonicalise a predicate to a lookup key — reuse world_state.canon_trait when present."""
    if _HAVE_WORLD and _world is not None:
        try:
            return _world.canon_trait(pred)
        except Exception:
            pass
    return re.sub(r"[^a-z0-9]+", "_", str(pred or "").strip().lower()).strip("_")


# The chain the canonical work_stress domain implies, by category — a leading hypothesis (its
# stated CAUSE) sits UPSTREAM of strain, strain is upstream of the predicted consequence. This is
# NOT invented causation: every edge here is only emitted when reality has FORMED the corresponding
# grounded hypothesis/prediction (each carries its real evidence turn); absent that, nothing.
# category -> (downstream consequence node, the model edge type strain->consequence).
_CATEGORY_CONSEQUENCE = {
    "sleep_decline": ("poor_sleep", WORSENS),
    "downtime_decline": ("less_recovery", WORSENS),
    "goal_followthrough": ("the_goal", CAUSE),
}


def _edges_from_reality(name: str, topic: str) -> list:
    """Candidate cause edges from the ``reality`` epistemic ledger — the COMPETING hypotheses for
    the domain become candidate causal edges, each grounded in the hypothesis' real evidence and
    weighted by its CURRENT competition weight (rolled forward through every adjudication).

    For each COMPETITION in the ledger whose category names a strain situation, every candidate
    (manager_change, recent_move, family_visit, …) is a candidate CAUSE upstream of strain:
        ``candidate --contributes--> strain``  (confidence = the candidate's current weight),
    and the leader additionally implies a downstream consequence edge from the linked PREDICTION:
        ``strain --worsens--> poor_sleep``     (confidence = the prediction's confidence),
    when reality has formed that prediction. Each edge cites the hypothesis claim / prediction it
    came from. Read-only on the reality ledger; [] when reality is absent or empty. Never raises."""
    if not (_HAVE_REALITY and _reality is not None):
        return []
    try:
        data = _reality.loop(name)
    except Exception:
        return []
    out = []
    competitions = data.get("competitions", []) or []
    predictions = data.get("predictions", []) or []
    # index predictions by competition id so we can hang the downstream consequence on the leader.
    pred_by_comp = {}
    for p in predictions:
        cid = p.get("competition_id")
        if cid:
            pred_by_comp.setdefault(cid, []).append(p)

    for comp in competitions:
        if not isinstance(comp, dict):
            continue
        cands = comp.get("candidates") or {}
        if not cands:
            continue
        leader = comp.get("leader")
        # each competing hypothesis -> a candidate cause edge upstream of strain. The candidate
        # KEY is already a canonical snake_case identifier (manager_change), so it is the node key
        # VERBATIM — it is an identifier, not free-text, and must not be run through _norm_node
        # (which would smear "manager_change" -> "manager change" and break the chain identity).
        for key, v in cands.items():
            weight = _clamp(v.get("weight", 0.0))
            claim = str(v.get("claim", "")).strip()
            rtype = CONTRIBUTES if key != leader else CAUSE
            out.append({
                "src": str(key), "dst": "strain", "relation": rtype,
                "confidence": weight, "support": 1,
                "sources": [SRC_REALITY_HYP],
                "evidence": [f"hypothesis [{key}] (weight {weight:.2f}): {claim}"[:160]],
            })
        # the leader's linked prediction -> a downstream consequence edge (strain -> consequence).
        for p in pred_by_comp.get(comp.get("id"), []):
            cat = p.get("category", "")
            cons = _CATEGORY_CONSEQUENCE.get(cat)
            if not cons:
                continue
            dst_node, rtype = cons
            pconf = _clamp(p.get("confidence", 0.5))
            out.append({
                "src": "strain", "dst": dst_node, "relation": rtype,
                "confidence": pconf, "support": 1,
                "sources": [SRC_REALITY_HYP],
                "evidence": [f"prediction [{cat}] (conf {pconf:.2f}): {str(p.get('claim',''))}"[:160]],
            })
    return out


def _cooccurrence(name: str, topic: str) -> dict:
    """A CORROBORATION-ONLY signal: which node pairs the evidence shows REPEATEDLY together. Two
    sources feed it, neither inventing a NEW edge — they only let an already-grounded edge climb:
      * world-edge SUPPORT — a stated edge corroborated N times (support>1) is strong co-occurrence
        between its endpoints (the user keeps restating the same link).
      * ``meaning`` NEIGHBOURS — a significant topic's neighbour set (topics seen connected to it)
        is co-appearance evidence between those node keys.
    Returns ``{frozenset({a, b}): strength in [0,1]}``. Read-only; {} when nothing corroborates or
    the sources are absent. Never raises (Observed > Assumed)."""
    pairs: dict = {}

    def _bump(a, b, s):
        a, b = _norm_node(a), _norm_node(b)
        if not a or not b or a == b:
            return
        key = frozenset({a, b})
        pairs[key] = max(pairs.get(key, 0.0), _clamp(s, 0.0, 1.0))

    # (1) world-edge corroboration: a high-support stated edge is strong co-occurrence.
    if _HAVE_WORLD and _world is not None:
        try:
            cluster = _world.situation(name, topic, hops=3)
            for e in (cluster or {}).get("edges", []) or []:
                if not isinstance(e, dict):
                    continue
                support = int(e.get("support", 1) or 1)
                if support > 1:
                    # saturating: 2x -> ~0.5, 4x -> ~0.75, asymptotic to 1.
                    strength = 1.0 - (1.0 / float(support))
                    _bump(e.get("subject"), e.get("object"), strength)
        except Exception:
            pass

    # (2) meaning neighbours: a significant topic's connected neighbours are co-appearance evidence.
    if _HAVE_MEANING and _meaning is not None:
        try:
            for row in _meaning.significance(name) or []:
                subj = row.get("subject")
                ev = row.get("evidence", {}) or {}
                neighbours = ev.get("neighbours", []) or []
                # strength scales gently with how connected the hub is (more mentions/degree).
                mentions = int(ev.get("mentions", 0) or 0)
                base = min(0.8, 0.3 + 0.05 * mentions)
                for nb in neighbours:
                    _bump(subj, nb, base)
        except Exception:
            pass
    return pairs


# ===========================================================================
# THE BUILDER — fuse the three grounded sources into ONE causal model. An edge is keyed by
# (src, dst, relation); proposals for the same key MERGE (union evidence/sources, climb confidence
# on corroboration, max-keep support). Co-occurrence ONLY adjusts edges already grounded by a
# world-edge or a reality hypothesis — it never seeds a new one. The result is GROUNDED by
# construction: an edge whose source set ends up without a real grounding source is dropped.
# ===========================================================================

def build_model_from_graph(name: str, topic: str, *, persist: bool = True) -> dict:
    """Construct a GROUNDED causal model for a DOMAIN ``topic`` (e.g. "work_stress") from the
    world graph + the reality competing-hypotheses + co-occurrence, and (by default) persist it.

    The model is a dict:
        {
          "id":      a stable model id,
          "name":    the creature,
          "topic":   the domain (normalised),
          "nodes":   sorted list of node keys in the model,
          "edges":   [ {id, src, dst, relation, confidence, support, sources, evidence, history},
                       ... ]  — each a TYPED, CONFIDENCE-WEIGHTED causal link citing its evidence,
          "created" / "updated": ISO-Z timestamps,
          "internal_only": True,   # NEVER asserted/diagnosed at the user (LAW 2)
          "grounding":  a per-source count of how many edges each evidence source backs,
        }

    GROUNDED BY CONSTRUCTION: every edge comes from a stated world-edge and/or a reality
    hypothesis; co-occurrence only CORROBORATES (climbs) an already-grounded edge, never invents
    one. A ``topic`` with no stated causal edges and no hypotheses yields a model with NO edges
    (proven in --selftest) — we never fabricate causation. ``persist=False`` builds without
    writing (a dry read). Read-only on the world/reality/meaning stores. Never raises."""
    topic_key = _norm_node(topic) or (str(topic).strip().lower() if topic else "")
    proposed = _edges_from_world(name, topic) + _edges_from_reality(name, topic)
    cooccur = _cooccurrence(name, topic)

    # merge proposals by (src, dst, relation).
    merged: dict = {}
    for e in proposed:
        if not e.get("src") or not e.get("dst") or e.get("src") == e.get("dst"):
            continue
        if not e.get("sources"):
            continue  # an edge with NO grounding source is never admitted (GROUNDED)
        key = (e["src"], e["dst"], e["relation"])
        cur = merged.get(key)
        if cur is None:
            merged[key] = {
                "src": e["src"], "dst": e["dst"], "relation": e["relation"],
                "confidence": _clamp(e["confidence"]),
                "support": int(e.get("support", 1) or 1),
                "sources": list(dict.fromkeys(e.get("sources", []))),
                "evidence": list(e.get("evidence", [])),
            }
        else:
            # corroboration: a second grounded proposal for the same link climbs confidence,
            # bumps support, and unions the cited evidence/sources (never a duplicate edge).
            cur["confidence"] = _climb(max(cur["confidence"], e["confidence"]))
            cur["support"] += int(e.get("support", 1) or 1)
            for s in e.get("sources", []):
                if s not in cur["sources"]:
                    cur["sources"].append(s)
            for ev in e.get("evidence", []):
                if ev not in cur["evidence"]:
                    cur["evidence"].append(ev)

    # apply co-occurrence as a CORROBORATION-ONLY lift on already-grounded edges.
    for key, edge in merged.items():
        s, d = edge["src"], edge["dst"]
        strength = cooccur.get(frozenset({s, d}), 0.0)
        if strength > 0.0:
            edge["confidence"] = _clamp(edge["confidence"] + _COOCCUR_BONUS * strength)
            if SRC_COOCCURRENCE not in edge["sources"]:
                edge["sources"].append(SRC_COOCCURRENCE)
            edge["evidence"].append(f"co-occurrence: {_label(s)} & {_label(d)} seen together "
                                    f"(strength {strength:.2f})")

    # finalise edges — drop any that somehow lost all grounding (defensive GROUNDED guarantee).
    edges = []
    nodes = set()
    grounding = {SRC_WORLD_EDGE: 0, SRC_REALITY_HYP: 0, SRC_COOCCURRENCE: 0}
    for edge in merged.values():
        grounded = [s for s in edge["sources"] if s in (SRC_WORLD_EDGE, SRC_REALITY_HYP)]
        if not grounded:
            continue  # co-occurrence alone is NOT grounding — never emit (Observed > Assumed)
        edge["id"] = _new_id("e")
        edge["history"] = []
        edge["confidence"] = round(_clamp(edge["confidence"]), 4)
        edges.append(edge)
        nodes.add(edge["src"])
        nodes.add(edge["dst"])
        for s in edge["sources"]:
            if s in grounding:
                grounding[s] += 1

    now = _now()
    model = {
        "id": _new_id("m"),
        "version": VERSION,
        "name": name,
        "topic": topic_key,
        "nodes": sorted(nodes),
        "edges": edges,
        "created": now,
        "updated": now,
        "internal_only": True,   # LAW 2 — a model is internal; NEVER asserted/diagnosed at the user
        "grounding": grounding,
    }
    if persist and edges:
        _store_model(name, model)
    return model


# ===========================================================================
# CAUSAL-CHAIN READING — the longest directed path(s) through the model, for the explain render
# and for "reason across the chain". A model with cycles is handled by visited-guarding the DFS.
# ===========================================================================

def _adjacency(model: dict) -> dict:
    """src_node -> [edge, ...] over the model's directed edges. Pure."""
    adj: dict = {}
    for e in model.get("edges", []) or []:
        adj.setdefault(e["src"], []).append(e)
    return adj


def causal_chains(model: dict, max_chains: int = 6) -> list:
    """The directed causal PATHS through the model, longest first — what lets the creature reason
    ACROSS the chain (manager -> stress -> sleep -> energy) instead of one isolated link.

    Returns a list of chains; each chain is a list of edges in order. Roots are nodes with no
    INCOMING edge (the upstream causes); from each we DFS the longest acyclic path. A model with
    no clear root still yields its single edges as length-1 chains. Pure; never raises."""
    edges = model.get("edges", []) or []
    if not edges:
        return []
    adj = _adjacency(model)
    has_incoming = {e["dst"] for e in edges}
    roots = [n for n in model.get("nodes", []) if n not in has_incoming]
    if not roots:
        roots = sorted({e["src"] for e in edges})  # cyclic — start anywhere deterministically

    chains: list = []

    def dfs(node, path_edges, visited):
        outs = adj.get(node, [])
        extended = False
        for e in sorted(outs, key=lambda x: (-float(x["confidence"]), x["dst"])):
            if e["dst"] in visited:
                continue
            extended = True
            dfs(e["dst"], path_edges + [e], visited | {e["dst"]})
        if not extended and path_edges:
            chains.append(path_edges)

    for r in sorted(roots):
        dfs(r, [], {r})
    # longest first; break ties by mean confidence (a stronger chain leads).
    chains.sort(key=lambda c: (-len(c), -_mean_conf(c)))
    return chains[:max_chains]


def _mean_conf(edges: list) -> float:
    if not edges:
        return 0.0
    return sum(float(e.get("confidence", 0)) for e in edges) / len(edges)


# ===========================================================================
# THE STORE — models keyed by id in this layer's OWN file, persisted ADDITIVELY (re-read + union
# by id on save, so a concurrent writer's model is never dropped — the world_state save discipline).
# ===========================================================================

def store_path(name: str) -> Path:
    """The world-model store for ``name`` — a SEPARATE file from world/reality/meaning; this
    module's only persisted state. Holds the models keyed by id."""
    return STORE / f"{name}.worldmodel.json"


def _load_store(name: str) -> dict:
    d = load_json(store_path(name))
    if not isinstance(d, dict):
        return {"version": VERSION, "models": {}}
    d.setdefault("models", {})
    return d


def _store_model(name: str, model: dict) -> None:
    """Persist ONE model additively: re-read the on-disk store and union by id (our model wins for
    its own id), so a concurrent writer's models are never silently dropped — a save can only ADD
    or update, never overwrite-and-lose (the world_state continuity guarantee). Best-effort: a
    write failure is swallowed (the in-memory model is still returned to the caller)."""
    try:
        STORE.mkdir(parents=True, exist_ok=True)
        disk = _load_store(name)
        models = disk.get("models", {})
        if not isinstance(models, dict):
            models = {}
        models[model["id"]] = model
        save_json(store_path(name), {"version": VERSION, "models": models})
    except Exception:
        pass


def get_model(name: str, model_id: str) -> Optional[dict]:
    """Load ONE model by id, or None. Read-only; never raises."""
    return _load_store(name).get("models", {}).get(model_id)


def models(name: str) -> list:
    """All stored models for ``name`` (newest ``created`` last). Read-only; never raises."""
    ms = list(_load_store(name).get("models", {}).values())
    ms.sort(key=lambda m: m.get("created", ""))
    return ms


# ===========================================================================
# explain_model — render the causal chain READABLY. Internal model-state; every line passes the
# no-diagnosis clean-gate (defence in depth). NEVER a user-facing assertion.
# ===========================================================================

# how each edge type reads as a (neutral, internal) clause fragment — never a verdict at the user.
_REL_PHRASE = {
    CAUSE: "is upstream of",
    CONTRIBUTES: "feeds into",
    WORSENS: "is reaching",
    PRECEDES: "comes before",
}


def _chain_sentence(chain: list) -> str:
    """A neutral, internal one-line gloss of a causal chain ("a recent change is upstream of
    strain, which is reaching rest"). Clean-gated by the caller. Pure."""
    if not chain:
        return ""
    parts = [_label(chain[0]["src"])]
    for e in chain:
        verb = _REL_PHRASE.get(e["relation"], "connects to")
        parts.append(f"{verb} {_label(e['dst'])}")
    # "A is upstream of B, which feeds into C" — comma-join the tail verbs readably.
    head = parts[0]
    tail = parts[1:]
    if len(tail) == 1:
        return f"{head} {tail[0]}"
    return f"{head} {tail[0]}" + "".join(f", which {t}" for t in tail[1:])


# The FIXED framing legend. It legitimately NAMES the banned words ("diagnosis", "fact") in
# order to FORBID them — so a no-diagnosis assertion must inspect the GENERATED body (the causal
# lines built from the model), NOT this legend, exactly as reality.render_body / trajectory._items_of
# inspect their generated items and not their banned-word-naming preamble.
_EXPLAIN_HEADER = (
    "WHAT YOU UNDERSTAND ABOUT HOW THINGS CONNECT FOR THEM — an INTERNAL causal model.\n"
    "  This is YOUR private map of how their situation hangs together — never to be stated at\n"
    "  them as fact, never a diagnosis, never \"your manager is causing your insomnia.\" It only\n"
    "  helps you understand; it is never a claim to assert at the user."
)


def explain_body(model: dict) -> str:
    """The GENERATED causal lines of a model's explanation — the chain through-lines + each link
    with its evidence (the ONLY lines that could ever carry a model inference) — WITHOUT the fixed
    framing legend. Every line here passes the no-diagnosis clean-gate; this is the body a
    no-diagnosis assertion inspects (mirroring reality.render_body / trajectory._items_of). "" for
    an empty model. Pure; never raises."""
    if not isinstance(model, dict) or not model.get("edges"):
        return ""

    def clean(s: str) -> str:
        return _safe_statement(s, "(an internal model note)")

    out = []
    out.append(clean(
        f"[MODEL] domain: {_label(model.get('topic', '?'))}  "
        f"({len(model.get('nodes', []))} nodes, {len(model.get('edges', []))} causal links)"))

    chains = causal_chains(model)
    out.append("")
    out.append("  [CHAIN] the causal through-lines (longest first):")
    if not chains:
        out.append("    (no multi-step chain yet — the links haven't connected into a path)")
    for ch in chains:
        sent = _chain_sentence(ch)
        mc = _mean_conf(ch)
        out.append(clean(f"    • {sent}   (mean confidence {mc:.2f})"))

    out.append("")
    out.append("  [CAUSE] each link, with the evidence it rests on:")
    for e in sorted(model.get("edges", []), key=lambda x: (-float(x["confidence"]), x["src"])):
        verb = _REL_PHRASE.get(e["relation"], "connects to")
        out.append(clean(
            f"    • {_label(e['src'])} --[{e['relation']}, {float(e['confidence']):.2f}]--> "
            f"{_label(e['dst'])}   ({_label(e['src'])} {verb} {_label(e['dst'])})"))
        for ev in e.get("evidence", [])[:3]:
            out.append(f"        ↳ {ev}")
        if e.get("history"):
            last = e["history"][-1]
            out.append(f"        ↳ last revised by outcome: {last.get('before')} -> "
                       f"{last.get('after')}  ({last.get('reason', '')})")
    return "\n".join(out)


def explain_model(model_id: str, name: Optional[str] = None, model: Optional[dict] = None) -> str:
    """Render a model's causal chain READABLY — the longest chains first, each link annotated with
    its confidence and the OBSERVED evidence it rests on. INTERNAL model-state: the GENERATED
    causal lines (``explain_body``) each pass the no-diagnosis clean-gate, and the block is framed
    as understanding-FOR-THE-CREATURE, NEVER a claim to assert at the user. The fixed framing
    legend legitimately NAMES "diagnosis"/"fact" in order to FORBID them (so a no-diagnosis
    assertion inspects ``explain_body``, not the legend — the reality/trajectory pattern).

    Pass either a loaded ``model`` directly, or ``name`` + ``model_id`` to load it. Returns "" for
    an unknown/empty model. Read-only; never raises."""
    if model is None and name is not None:
        model = get_model(name, model_id)
    body = explain_body(model)
    if not body:
        return ""
    return f"{_EXPLAIN_HEADER}\n\n{body}"


# ===========================================================================
# update_model_with_outcome — when reality RESOLVES an outcome, move the relevant edge confidences:
# STRENGTHEN a confirmed causal link, WEAKEN a contradicted one. Append-only history per edge.
# This is the model LEARNING from reality (the hook reality.resolve feeds). Returns a NEW model
# dict (the updated copy) — leaving the input untouched so compare_models can diff before/after.
# ===========================================================================

def _matches(edge: dict, outcome: dict) -> Optional[bool]:
    """Does ``outcome`` bear on ``edge``? Returns True (the outcome SUPPORTS this link), False (it
    CONTRADICTS it), or None (irrelevant — leave the edge alone).

    An outcome is ``{confirmed: bool, nodes: [..], relation: str|None, category: str|None}`` (or a
    reality-style learning record we adapt). It bears on an edge when it names one of the edge's
    endpoints (or its reality category maps to the edge's downstream consequence node). ``confirmed``
    then says whether reality SUPPORTED the link (strengthen) or REFUTED it (weaken). Pure."""
    confirmed = outcome.get("confirmed")
    if confirmed is None and "prediction_correct" in outcome:
        confirmed = bool(outcome.get("prediction_correct"))
    if confirmed is None:
        return None
    onodes = {_norm_node(n) for n in (outcome.get("nodes") or []) if n}
    # a reality category resolves to a downstream consequence node (sleep_decline -> poor_sleep).
    cat = outcome.get("category")
    if cat and cat in _CATEGORY_CONSEQUENCE:
        onodes.add(_CATEGORY_CONSEQUENCE[cat][0])
    if not onodes:
        return None
    if edge["src"] in onodes or edge["dst"] in onodes:
        # an explicit relation filter, when given, must also match.
        rel = outcome.get("relation")
        if rel and edge["relation"] != rel:
            return None
        return bool(confirmed)
    return None


def update_model_with_outcome(model_id: str, outcome: dict, *, name: Optional[str] = None,
                              model: Optional[dict] = None, persist: bool = True) -> dict:
    """Update a model's edge CONFIDENCES from a RESOLVED reality outcome — the model learning.

    For every edge the ``outcome`` bears on (``_matches``): a CONFIRMED outcome STRENGTHENS the
    link (confidence scaled up by ``_SUPPORT_GAIN``, clamped), a CONTRADICTED one WEAKENS it
    (scaled down by ``_CONTRADICT_DECAY``, floored — never annihilated, Unknown > Lost). Each
    change appends a ``history`` entry {before, after, reason, at, outcome} — APPEND-ONLY, so the
    model's evolution is auditable and a confidence is never silently overwritten.

    ``outcome`` is ``{confirmed: bool, nodes: [...], relation?, category?}`` or a reality LEARNING
    record (``prediction_correct`` + ``category``) we adapt. Pass a loaded ``model`` or
    ``name``+``model_id``. Returns a NEW updated model dict (the input is left untouched, so
    ``compare_models(before, after)`` can diff). Persists the updated model by default. Never raises."""
    if model is None and name is not None:
        model = get_model(name, model_id)
    if not isinstance(model, dict):
        return {}
    if not isinstance(outcome, dict):
        return model

    now = _now()
    # deep-ish copy so the input snapshot stays pristine for compare_models.
    new_edges = []
    touched = 0
    for e in model.get("edges", []) or []:
        ne = dict(e)
        ne["sources"] = list(e.get("sources", []))
        ne["evidence"] = list(e.get("evidence", []))
        ne["history"] = list(e.get("history", []))
        verdict = _matches(ne, outcome)
        if verdict is not None:
            before = float(ne.get("confidence", 0.0))
            if verdict:
                after = _clamp(before * _SUPPORT_GAIN)
                reason = "confirmed by outcome (strengthened)"
            else:
                after = _clamp(before * _CONTRADICT_DECAY)
                reason = "contradicted by outcome (weakened)"
            after = round(after, 4)
            if after != round(before, 4):
                touched += 1
            ne["confidence"] = after
            ne["history"].append({
                "before": round(before, 4), "after": after, "reason": reason,
                "at": now, "outcome": str(outcome.get("observed", outcome.get("category", "")))[:120],
            })
        new_edges.append(ne)

    updated = dict(model)
    updated["edges"] = new_edges
    updated["updated"] = now
    updated["internal_only"] = True
    updated["last_outcome"] = {"confirmed": outcome.get("confirmed",
                                                         outcome.get("prediction_correct")),
                               "category": outcome.get("category"),
                               "edges_touched": touched, "at": now}
    if persist and name is not None:
        _store_model(name, updated)
    return updated


# ===========================================================================
# compare_models — show a model's EVOLUTION: strengthened / weakened / appeared / disappeared
# edges + the confidence deltas. So "how the model changed when reality came in" is auditable.
# ===========================================================================

def _edge_key(e: dict) -> tuple:
    return (e.get("src"), e.get("dst"), e.get("relation"))


def compare_models(before: dict, after: dict) -> dict:
    """Diff two snapshots of a model (typically the same model before and after an outcome update)
    and report its EVOLUTION:

        {
          "topic":        the domain,
          "strengthened": [ {edge, before, after, delta}, ... ]  (confidence rose),
          "weakened":     [ {edge, before, after, delta}, ... ]  (confidence fell),
          "unchanged":    count of edges whose confidence held,
          "appeared":     [ edge-label, ... ]  edges present only in `after`,
          "disappeared":  [ edge-label, ... ]  edges present only in `before`,
          "summary":      a one-line human gloss (clean-gated),
        }

    Keys edges by (src, dst, relation). Pure; never raises — a malformed input degrades to an
    empty diff."""
    if not isinstance(before, dict):
        before = {}
    if not isinstance(after, dict):
        after = {}
    b = {_edge_key(e): e for e in before.get("edges", []) or [] if isinstance(e, dict)}
    a = {_edge_key(e): e for e in after.get("edges", []) or [] if isinstance(e, dict)}

    strengthened, weakened = [], []
    unchanged = 0
    for k, ae in a.items():
        be = b.get(k)
        if be is None:
            continue
        bc = round(float(be.get("confidence", 0.0)), 4)
        ac = round(float(ae.get("confidence", 0.0)), 4)
        delta = round(ac - bc, 4)
        rec = {"edge": _edge_label(ae), "before": bc, "after": ac, "delta": delta}
        if delta > 0:
            strengthened.append(rec)
        elif delta < 0:
            weakened.append(rec)
        else:
            unchanged += 1
    appeared = [_edge_label(a[k]) for k in a.keys() - b.keys()]
    disappeared = [_edge_label(b[k]) for k in b.keys() - a.keys()]
    strengthened.sort(key=lambda r: -r["delta"])
    weakened.sort(key=lambda r: r["delta"])

    bits = []
    if strengthened:
        bits.append(f"{len(strengthened)} link(s) strengthened")
    if weakened:
        bits.append(f"{len(weakened)} weakened")
    if appeared:
        bits.append(f"{len(appeared)} new")
    if disappeared:
        bits.append(f"{len(disappeared)} dropped")
    summary = ("the model held steady" if not bits
               else "the model shifted: " + ", ".join(bits))
    return {
        "topic": after.get("topic", before.get("topic", "?")),
        "strengthened": strengthened,
        "weakened": weakened,
        "unchanged": unchanged,
        "appeared": sorted(appeared),
        "disappeared": sorted(disappeared),
        "summary": _safe_statement(summary, "the model was revised"),
    }


def _edge_label(e: dict) -> str:
    return f"{_label(e.get('src'))} --[{e.get('relation')}]--> {_label(e.get('dst'))}"


def render_comparison(diff: dict) -> str:
    """Human-readable model-evolution block. Read-only; clean-gated; never raises."""
    if not isinstance(diff, dict):
        return ""

    def clean(s: str) -> str:
        return _safe_statement(s, "(an internal model note)")

    out = [f"MODEL EVOLUTION — domain {_label(diff.get('topic', '?'))}: {clean(diff.get('summary',''))}"]
    for r in diff.get("strengthened", []):
        out.append(clean(f"    ↑ {r['edge']}   {r['before']:.2f} -> {r['after']:.2f}  "
                         f"(+{r['delta']:.2f}, reality confirmed it)"))
    for r in diff.get("weakened", []):
        out.append(clean(f"    ↓ {r['edge']}   {r['before']:.2f} -> {r['after']:.2f}  "
                         f"({r['delta']:.2f}, reality pushed back)"))
    for lbl in diff.get("appeared", []):
        out.append(clean(f"    + {lbl}   (new grounded link)"))
    for lbl in diff.get("disappeared", []):
        out.append(clean(f"    - {lbl}   (no longer grounded)"))
    if diff.get("unchanged"):
        out.append(f"    = {diff['unchanged']} link(s) held steady")
    return "\n".join(out)


# ===========================================================================
# AUDIT SURFACE — human-readable 'the causal models Vera holds about your situations'. The
# world_model counterpart to world_state.render / reality.render. Read-only; never the live reply.
# ===========================================================================

def render(name: str) -> str:
    """Human-readable audit of every stored causal model for ``name`` — each model's causal chain
    (via ``explain_body``) and its grounding. Inspectable surface, not the prompt block. Uses the
    GENERATED body (not the forbidding legend) so the whole audit is itself clean-gated. Read-only;
    never raises."""
    ms = models(name)
    out = [f"The causal models {name} holds about your situations (INTERNAL model-state — never "
           f"spoken, never asserted at the user): {len(ms)}"]
    if not ms:
        out.append("  (no models built yet — they emerge from your stated situations + how reality")
        out.append("   resolves them; an ungrounded model is never fabricated)")
        return "\n".join(out)
    for m in ms:
        out.append("")
        out.append(f"  MODEL [{m.get('id')}]  domain={_label(m.get('topic','?'))}  "
                   f"edges={len(m.get('edges', []))}  grounded_by={m.get('grounding')}")
        for ln in explain_body(m).splitlines():
            out.append("    " + ln)
    return "\n".join(out)


# ===========================================================================
# SYNTHETIC PROOF — the canonical manager -> stress -> poor_sleep -> low_energy chain, built from
# a stated world graph + reality's competing hypotheses, then evolved by a resolved outcome.
# Hermetic by the caller's STORE redirect; touches no model, no network. (Reused by the selftest
# and the observatory so the default invocation shows a real, grounded, evolving model.)
# ===========================================================================

_SYNTH_DAY1 = "2026-01-01T09:00:00Z"


def build_synthetic_model(name: str) -> dict:
    """Build the canonical work_stress causal model end to end against whatever STORE is bound (the
    temp store under --selftest), entirely from GROUNDED evidence:

      * SEED THE WORLD GRAPH with the stated situation the user actually said — "work stressful
        because my new manager", "the stress is affecting my sleep", "sleep is leading to low
        energy" — so world_state holds the causal edges manager->work, work->strain, stress->sleep,
        sleep->energy.
      * SEED THE REALITY LOOP with the Day-1 change -> the COMPETING stress hypotheses
        (manager_change leading) + the sleep_decline prediction, then RESOLVE Day-14 "barely slept"
        so the competition is adjudicated (manager_change strengthened).
      * BUILD the model from those two grounded sources (+ co-occurrence corroboration).
      * EVOLVE it with a resolved outcome and DIFF before/after.

    Returns ``{model, evolved, diff, world_seeded, reality_resolved}`` so a caller can assert the
    chain is present, grounded, and that an outcome shifted an edge. Never raises."""
    out = {"model": {}, "evolved": {}, "diff": {}, "world_seeded": False, "reality_resolved": False}

    # --- (1) seed the WORLD graph with the stated situation (grounded causal edges) -------------
    if _HAVE_WORLD and _world is not None:
        try:
            _world.capture_relations(name, "my work's been really stressful because of my new manager")
            _world.capture_relations(name, "honestly the stress is affecting my sleep")
            # an explicit knock-on the user stated: poor sleep -> low energy.
            _world.relate(name, "sleep", "leads_to", "low energy", kind="inference")
            # corroborate the stressor a second time so co-occurrence has a high-support edge.
            _world.relate(name, "you", "stressed_by", "work", kind="problem")
            out["world_seeded"] = True
        except Exception:
            pass

    # --- (2) seed + resolve the REALITY loop (competing hypotheses + adjudicated outcome) --------
    if _HAVE_REALITY and _reality is not None:
        try:
            _reality.form(name, "my manager just changed and work's been heavy lately",
                          at=_SYNTH_DAY1)
            _reality.resolve(name, "honestly I've barely slept the last two weeks",
                             at=_reality._add_days(_SYNTH_DAY1, 14))
            out["reality_resolved"] = True
        except Exception:
            pass

    # --- (3) BUILD the grounded model from world + reality + co-occurrence ----------------------
    model = build_model_from_graph(name, "work_stress")
    out["model"] = model

    # --- (4) EVOLVE it with a resolved outcome + diff before/after -------------------------------
    # reality confirmed the sleep_decline consequence; strengthen the strain -> poor_sleep link.
    outcome = {"confirmed": True, "category": "sleep_decline",
               "observed": "barely slept the last two weeks"}
    evolved = update_model_with_outcome(model.get("id", ""), outcome, name=name, model=model)
    out["evolved"] = evolved
    out["diff"] = compare_models(model, evolved)
    return out


# ############################################################################
# ############################################################################
# WORLD UNDERSTANDING — FROM A CAUSAL MODEL OF ONE DOMAIN TO A COHERENT WORLD MODEL OF LAMAR'S
# WHOLE WORLD: first-class TYPED ENTITIES (people, projects, goals, resources, risks, constraints)
# + TYPED RELATIONS between them + CAUSAL LINKS connecting any of them — every entity and edge
# GROUNDED in captured facts (never invented), INTERNAL-only, no diagnosis. "Facts become meaning."
#
# This is the leap ABOVE build_model_from_graph. That function builds a per-DOMAIN causal model
# whose nodes are bare strings ("manager", "strain", "poor_sleep"). A world UNDERSTANDING asks the
# next question a thirty-year companion must answer: WHAT KIND OF THING is each node, and HOW do
# the things in Lamar's world relate? "manager_change" is a PERSON-change; "strain"/"poor_sleep"
# are STATES; "the goal" is a GOAL; "Acme" is a RESOURCE/employer; "money" is a RISK he worries
# about. Typing the nodes + the edges between them turns a flat causal graph into a MAP OF A LIFE.
#
# ────────────────────────────────────────────────────────────────────────────────────────────
# THE SAME FOUR LAWS HOLD (inherited verbatim from the causal-model layer above):
#   1. GROUNDED — every entity/edge cites the captured fact(s) it came from (a stated world-state
#      edge, a LIRF row, a reality hypothesis). An entity with no grounding is DROPPED, never
#      emitted. A node is NEVER promoted to a richer type than its evidence supports (a bare topic
#      stays a TOPIC; we never fabricate a PERSON). Proven in the world selftest: an empty creature
#      yields an empty world model.
#   2. INTERNAL ONLY — NO DIAGNOSIS. A world model is Vera's private map of LAMAR's world; it is
#      flagged ``internal_only`` and every human-readable line passes the no-diagnosis clean-gate.
#      Imported by NOTHING on the live path (a shadow read over the already-recorded stores).
#   3. FREEZE BOUNDARY — the model is OF LAMAR / THE WORLD / TASKS / KNOWLEDGE. It NEVER models
#      Vera's own values/preferences/goals/agency/identity. Every entity's subject is something in
#      LAMAR's world. (No persona/portrait/identity is read or written here.)
#   4. TIME-HONEST + ADDITIVE — the world model is a snapshot of what the captured facts support
#      NOW; it accrues to its OWN store (``.anima/{name}.worldmodel_world.json``), keyed by id,
#      append-only. It REUSES build_model_from_graph for the causal layer — it does not replace it.
#
# THE ENTITY-CLASSIFIER's GROUNDING (never-invent): a node's TYPE is read ONLY from the captured
# signal that introduced it — the world-state predicate/kind, the LIRF trait, or the reality
# candidate key. The classifier never guesses from spelling alone beyond a closed, conservative
# lexicon, and falls back to the weakest defensible type (STATE for a feeling-word, else TOPIC) so
# an unknown node is under-typed, never over-typed. Observed > Assumed, at the type level.
# ############################################################################
# ############################################################################

# ---------------------------------------------------------------------------
# ENTITY TYPES — the closed vocabulary every world entity's ``type`` lives in. These are the
# kinds of THING that populate a life: the person at the centre (SELF), the people around them,
# the work they do, what they're reaching for, what they have to work with, what threatens it,
# and what bounds it. STATE/TOPIC are the weakest types — the grounded fallback for a node whose
# evidence types it no further (a feeling, an unclassified subject). Never widened by spelling.
# ---------------------------------------------------------------------------
ENT_SELF = "self"            # Lamar himself — the hub of his own world (the world_state SELF node)
ENT_PERSON = "person"        # another person in Lamar's world (a role/name, or a person-change)
ENT_PROJECT = "project"      # work / an initiative / a venture he is engaged in
ENT_GOAL = "goal"            # something he is reaching for (a stated intention/objective)
ENT_RESOURCE = "resource"    # something he works WITH / relies on (employer, money-as-means, tool)
ENT_RISK = "risk"            # something that threatens — a worry, a stressor, a danger to a goal
ENT_CONSTRAINT = "constraint"  # something that BOUNDS him (a deadline, a limit, a hard requirement)
ENT_STATE = "state"          # an internal/situational STATE (strain, poor_sleep, low_energy)
ENT_TOPIC = "topic"          # an unclassified life-topic node (the weakest grounded fallback)
ENTITY_TYPES = (ENT_SELF, ENT_PERSON, ENT_PROJECT, ENT_GOAL, ENT_RESOURCE,
                ENT_RISK, ENT_CONSTRAINT, ENT_STATE, ENT_TOPIC)

# RELATION TYPES for the WORLD graph (as opposed to the CAUSAL edge types CAUSE/CONTRIBUTES/…
# above, which connect any two entities causally). These are the NON-causal first-class bonds a
# world map needs: who relates to whom, who works on what, who is reaching for what. A world
# relation is typed + directed + grounded, exactly like a causal link.
REL_RELATES_TO = "relates_to"    # person <-> Lamar / person <-> person — a relationship bond
REL_WORKS_ON = "works_on"        # Lamar -> project (engaged in a piece of work)
REL_PURSUES = "pursues"          # Lamar -> goal (reaching for an objective)
REL_RELIES_ON = "relies_on"      # Lamar -> resource (depends on / works with)
REL_THREATENS = "threatens"      # risk -> (goal|project|state) — a danger to something
REL_BOUNDS = "bounds"            # constraint -> (project|goal) — a limit on something
WORLD_RELATION_TYPES = (REL_RELATES_TO, REL_WORKS_ON, REL_PURSUES, REL_RELIES_ON,
                        REL_THREATENS, REL_BOUNDS)

# The CAUSAL edge types (CAUSE/CONTRIBUTES/WORSENS/PRECEDES) are ALSO first-class world edges —
# a causal link IS a typed relation between two typed entities. The union is the full edge
# vocabulary a world model can carry.
ALL_EDGE_TYPES = tuple(dict.fromkeys(RELATION_TYPES + WORLD_RELATION_TYPES))

# Evidence-source tags for ENTITIES (edges already use SRC_WORLD_EDGE / SRC_REALITY_HYP /
# SRC_COOCCURRENCE). A LIRF row is a fourth grounded source — only entities (not causal edges)
# can be grounded by a plain value, since a value names a thing without asserting a cause.
SRC_LIRF_FACT = "lirf_fact"      # a captured LIRF row (employer, a named relationship, …)

# A reality candidate KEY -> the entity type it grounds. These keys are a CLOSED taxonomy the
# reality engine emits (manager_change, recent_move, …); each is a concrete kind of driver, so it
# types cleanly. A key not here contributes a STATE entity (an unclassified driver), never a
# fabricated person/project. The "_change" people-changes type as PERSON (the person is the entity
# the change is about); life-events type by their noun.
_REALITY_KEY_TO_TYPE = {
    "manager_change": ENT_PERSON,    # a change in WHO manages him — the manager is a person
    "recent_move": ENT_TOPIC,        # a relocation event (a life-topic, not a person/resource)
    "family_visit": ENT_PERSON,      # family — people in his world
    "crunch": ENT_CONSTRAINT,        # a deadline crunch BOUNDS the work
    "multiple": ENT_STATE,           # "several things at once" — a diffuse state, not one thing
}

# Closed, conservative lexicons for typing a WORLD-STATE node by its surface key. Each maps a
# token the node CONTAINS to a type — but only as a LAST resort after the predicate/kind and the
# reality/LIRF signals (which are stronger grounding). Deliberately small: a word not here leaves
# the node at its fallback type. This is never a free guess — it fires only on an explicit token.
_ROLE_WORDS = frozenset(
    "manager boss supervisor lead director coworker colleague partner roommate landlord doctor "
    "therapist teacher coach wife husband girlfriend boyfriend fiance fiancee daughter son mom "
    "mother dad father brother sister friend kid child family".split())
_PROJECT_WORDS = frozenset(
    "work job business startup company venture project launch product gig career deadline-project "
    "deal client launch-project initiative".split())
_RESOURCE_WORDS = frozenset(
    "money savings income salary budget cash funds runway loan house apartment car tool team".split())
_RISK_WORDS = frozenset(
    "money debt rent bills layoff layoffs eviction deadline burnout-risk health".split())
_CONSTRAINT_WORDS = frozenset(
    "deadline crunch limit quota requirement curfew budget timeline".split())
# STATE/feeling words — a node that IS a feeling/state is an ENT_STATE (the grounded fallback for
# the downstream of a causal chain). Reuses the same family of words the causal layer recognises.
_STATE_WORDS = frozenset(
    "strain stress stressed stressful overwhelmed anxious anxiety exhausted exhaustion drained "
    "tired tiredness sleep poor_sleep poorly insomnia rest recovery energy low_energy fatigue "
    "mood overwhelm pressure".split())


def _classify_entity(key: str, *, predicate: str = "", kind: str = "",
                     reality_key: bool = False, lirf_trait: str = "") -> str:
    """The GROUNDED entity classifier — read a node's TYPE from the captured signal that
    introduced it, NEVER from spelling alone beyond a closed lexicon. Precedence (strongest
    grounding first), so a node is typed by the most specific evidence available:

      0. the user node SELF -> ENT_SELF (Lamar is the hub of his own world).
      1. a reality CANDIDATE key (manager_change, recent_move, …) -> its mapped type. These keys
         are a closed taxonomy; the mapping is exact, not a guess.
      2. the world-state KIND that stored the edge: 'relationship' -> PERSON, 'goal' -> GOAL,
         'problem' -> RISK, 'value' -> RESOURCE-or-RISK by lexicon. A kind is what the capture rule
         ASSERTED the node is, so it is strong grounding.
      3. the world-state PREDICATE: 'has'/'manager_is'/… (a relationship arrow) -> PERSON;
         'working_toward' -> GOAL; 'worried_about' -> RISK; 'stressed_by' object -> RISK.
      4. a LIRF TRAIT: 'employer'/'works_at' -> RESOURCE; a kin/role trait -> PERSON.
      5. a closed surface LEXICON (role/project/resource/risk/constraint/state words), last.
      6. FALLBACK: a feeling-word -> STATE, else TOPIC. Under-type, never over-type.

    Returns one of ENTITY_TYPES. Pure; never raises. This is ``world_state.capture``'s never-infer
    discipline applied at the TYPE level: the type is only ever as specific as the evidence."""
    k = (key or "").strip().lower()
    toks = set(k.replace("-", "_").split())
    toks |= set(k.split("_"))
    pred = (predicate or "").strip().lower()
    knd = (kind or "").strip().lower()
    trait = (lirf_trait or "").strip().lower()

    # 0. the self node.
    if k in ("you", "i", "me") or k == _norm_node("you"):
        return ENT_SELF

    # 1. a reality candidate key — exact closed taxonomy.
    if reality_key:
        if k in _REALITY_KEY_TO_TYPE:
            return _REALITY_KEY_TO_TYPE[k]
        # an unknown reality driver is a diffuse STATE, never a fabricated typed thing.
        return ENT_STATE

    # 2. the world-state KIND that stored it (what the capture rule asserted).
    if knd == "relationship":
        return ENT_PERSON
    if knd == "goal":
        return ENT_GOAL
    if knd == "problem":
        # a problem node is a RISK unless its surface clearly names a means (resource) it isn't.
        return ENT_RISK
    if knd in ("preference", "value"):
        # something cared-about / held important: a RESOURCE if it names a means, else TOPIC.
        if toks & _RESOURCE_WORDS:
            return ENT_RESOURCE
        # a cared-about PERSON (a role word) is a person.
        if toks & _ROLE_WORDS:
            return ENT_PERSON
        return ENT_TOPIC

    # 3. the world-state PREDICATE direction.
    if pred in ("has", "manager_is", "married_to", "knows", "friend_is") or pred.endswith("_is"):
        if toks & _ROLE_WORDS:
            return ENT_PERSON
    if pred == "working_toward":
        return ENT_GOAL
    if pred == "worried_about":
        return ENT_RISK

    # 4. a LIRF trait.
    if trait in ("employer", "works_at", "company", "workplace"):
        return ENT_RESOURCE
    if trait in ("manager", "boss", "spouse", "partner", "wife", "husband", "daughter",
                 "son", "mother", "father", "friend", "sister", "brother"):
        return ENT_PERSON

    # 5. a closed surface lexicon (last, weakest grounding — an explicit token only).
    if toks & _ROLE_WORDS:
        return ENT_PERSON
    if toks & _CONSTRAINT_WORDS and "deadline" in toks:
        return ENT_CONSTRAINT
    if toks & _PROJECT_WORDS:
        return ENT_PROJECT
    if toks & _RISK_WORDS and not (toks & _STATE_WORDS):
        return ENT_RISK
    if toks & _RESOURCE_WORDS:
        return ENT_RESOURCE
    if toks & _CONSTRAINT_WORDS:
        return ENT_CONSTRAINT

    # 6. fallback — a feeling/state word is a STATE; anything else is a bare TOPIC.
    if toks & _STATE_WORDS:
        return ENT_STATE
    return ENT_TOPIC


def _entity_id(key: str) -> str:
    """A stable per-world entity id from the node key — deterministic so the SAME node yields the
    SAME entity id within a build (entities de-dupe by key, not by random id)."""
    return "ent_" + re.sub(r"[^a-z0-9]+", "_", (key or "").lower()).strip("_")


# ===========================================================================
# THE WORLD BUILDER — assemble the coherent WORLD MODEL: typed entities + typed relations +
# causal links, all grounded. It REUSES the causal model (build_model_from_graph) for the causal
# layer, then (a) walks the WHOLE world-state graph + LIRF facts to discover every grounded
# entity and the non-causal relations between them, and (b) lifts every causal edge into a typed
# causal link between two typed entities. Every entity/edge carries the captured fact(s) it rests
# on. Grounded by construction: a node with no captured grounding never becomes an entity.
# ===========================================================================

def _world_causal_topics(name: str) -> list:
    """The set of domain topics to build causal sub-models for — every reality competition
    category + a small set of canonical life-domains, so the causal layer covers the situations
    the captured facts actually describe. Read-only; [] when reality is absent. Never raises."""
    topics = ["work_stress"]
    if _HAVE_REALITY and _reality is not None:
        try:
            data = _reality.loop(name)
            for comp in data.get("competitions", []) or []:
                cat = comp.get("category")
                if cat and cat not in topics:
                    topics.append(cat)
        except Exception:
            pass
    return topics


def _gather_world_entities_and_relations(name: str) -> tuple:
    """Walk the WHOLE world-state graph (broad check-in seed = the user hub) + the LIRF facts, and
    return (entities_by_key, world_relations) — the TYPED entities and the NON-causal typed
    relations between them, each grounded in the captured fact it came from. Read-only on both
    stores; ([], []) when nothing is captured. Never invents an entity or a relation.

    entities_by_key: {node_key -> entity dict {id,type,key,label,confidence,provenance,sources}}
    world_relations: [ {id,type,src,dst,confidence,support,sources,evidence} ]  (typed bonds)."""
    entities: dict = {}
    relations: list = []

    def _ensure_entity(key, etype, prov, src, conf):
        key = _norm_node(key)
        if not key:
            return None
        e = entities.get(key)
        if e is None:
            e = {"id": _entity_id(key), "type": etype, "key": key, "label": _label(key),
                 "confidence": _clamp(conf), "provenance": [], "sources": []}
            entities[key] = e
        else:
            # PROMOTE the type only toward something more specific than the current; never demote a
            # PERSON/GOAL/PROJECT to a STATE/TOPIC (the strongest grounding wins).
            cur_rank = _TYPE_SPECIFICITY.get(e["type"], 0)
            new_rank = _TYPE_SPECIFICITY.get(etype, 0)
            if new_rank > cur_rank:
                e["type"] = etype
            e["confidence"] = _climb(max(e["confidence"], _clamp(conf)))
        if prov and prov not in e["provenance"]:
            e["provenance"].append(prov)
        if src and src not in e["sources"]:
            e["sources"].append(src)
        return e

    # --- (1) world-state EDGES: every endpoint is a grounded entity; a causal/relational edge of
    # the NON-causal world kind becomes a typed world relation. -----------------------------------
    if _HAVE_WORLD and _world is not None:
        try:
            cluster = _world.situation(name, "how am I doing", hops=4)
            edges = (cluster or {}).get("edges", []) or []
        except Exception:
            edges = []
        for e in edges:
            if not isinstance(e, dict):
                continue
            subj = _norm_node(e.get("subject"))
            obj = _norm_node(e.get("object"))
            if not subj or not obj:
                continue
            pred = _canon_pred(e.get("predicate", ""))
            knd = str(e.get("kind", "")).lower()
            conf = _clamp(e.get("confidence", 0.6))
            from_lirf = bool(e.get("_from_lirf"))
            src_tag = SRC_LIRF_FACT if from_lirf else SRC_WORLD_EDGE
            prov_s = (f"lirf: you {pred} {obj}" if from_lirf
                      else f"stated: {subj} --{pred}--> {obj}")
            # type each endpoint from the strongest available signal.
            subj_type = _classify_entity(subj, predicate=pred, kind=knd,
                                         lirf_trait=(pred if from_lirf else ""))
            # the OBJECT of a relationship/goal/problem predicate carries the typed thing.
            obj_type = _classify_entity(
                obj, predicate=pred, kind=knd,
                lirf_trait=(pred if from_lirf else ""))
            _ensure_entity(subj, subj_type, prov_s, src_tag, conf)
            _ensure_entity(obj, obj_type, prov_s, src_tag, conf)

            # NON-causal world relations — only when the predicate/kind names one (never coerced).
            wrel = _world_relation_for(pred, knd, subj, obj, entities)
            if wrel is not None:
                rtype, rsrc, rdst = wrel
                relations.append({
                    "id": _new_id("wr"), "type": rtype, "src": rsrc, "dst": rdst,
                    "confidence": conf, "support": int(e.get("support", 1) or 1),
                    "sources": [src_tag], "evidence": [prov_s],
                })

    # --- (2) reality CANDIDATES: each competing driver is a grounded entity (typed by its key). --
    if _HAVE_REALITY and _reality is not None:
        try:
            data = _reality.loop(name)
        except Exception:
            data = {}
        for comp in data.get("competitions", []) or []:
            if not isinstance(comp, dict):
                continue
            for key, v in (comp.get("candidates") or {}).items():
                weight = _clamp(v.get("weight", 0.0))
                claim = str(v.get("claim", "")).strip()
                etype = _classify_entity(str(key), reality_key=True)
                _ensure_entity(str(key), etype,
                               f"hypothesis [{key}] (weight {weight:.2f}): {claim}"[:160],
                               SRC_REALITY_HYP, weight)

    return entities, relations


# How specific each entity type is — used to PROMOTE (never demote) a node's type when a stronger
# signal arrives. SELF is the most specific (it is exactly one thing); TOPIC/STATE are the weakest.
_TYPE_SPECIFICITY = {
    ENT_SELF: 6, ENT_PERSON: 5, ENT_PROJECT: 5, ENT_GOAL: 5,
    ENT_RESOURCE: 4, ENT_RISK: 4, ENT_CONSTRAINT: 4, ENT_STATE: 2, ENT_TOPIC: 1,
}


def _world_relation_for(pred: str, kind: str, subj: str, obj: str, entities: dict):
    """Map a world-state (predicate, kind, subj, obj) onto a TYPED NON-causal world relation, or
    None when the edge names no such bond (so a relation is NEVER coerced from a causal/attribute
    edge — those become causal links instead). Returns (relation_type, src_key, dst_key). Pure."""
    # a relationship bond: "you has manager" / "you knows X" -> person relates_to Lamar.
    if kind == "relationship" or pred in ("has", "knows", "manager_is", "married_to") or pred.endswith("_is"):
        # orient person -> you (the person relates to Lamar).
        if subj == "you":
            return (REL_RELATES_TO, obj, "you")
        return (REL_RELATES_TO, subj, obj)
    # a stated goal: "you working_toward X" -> Lamar pursues goal.
    if pred == "working_toward" or kind == "goal":
        if subj == "you":
            return (REL_PURSUES, "you", obj)
    # working ON a project: "you stressed_by work"/"work because manager" doesn't assert works_on,
    # but a project-typed object the user is engaged with does when the predicate is engagement.
    # We keep this conservative: only an explicit work/own predicate yields works_on.
    if pred in ("works_at", "works_on", "running", "building", "founded", "launched", "started"):
        if subj == "you":
            return (REL_WORKS_ON, "you", obj)
    return None


def build_world_model(name: str, *, persist: bool = True) -> dict:
    """Construct the coherent WORLD MODEL of ``name``'s world — the headline of this layer.

    Fuses three grounded views into ONE typed graph:
      * the CAUSAL layer — build_model_from_graph over every captured domain (work_stress + every
        reality competition category), giving the TYPED CAUSAL LINKS (manager_change --causes-->
        strain --worsens--> poor_sleep --…--> productivity), each carrying its evidence.
      * the ENTITY/RELATION layer — _gather_world_entities_and_relations walks the whole world
        graph + LIRF facts + reality candidates, giving every grounded TYPED ENTITY (people,
        projects, goals, resources, risks, constraints) and the NON-causal typed relations.
      * the two are JOINED: every node that appears in a causal link is upgraded to (or created
        as) a typed entity, so the causal chain is a chain of TYPED entities, not bare strings.

    Returns the world model dict:
        {
          "id", "version", "name",
          "entities":  [ {id,type,key,label,confidence,provenance,sources}, ... ]  (typed, grounded),
          "relations": [ {id,type,src,dst,confidence,support,sources,evidence}, ... ]  (typed bonds),
          "causal_links": [ {id,src,dst,relation,confidence,support,sources,evidence}, ... ],
          "by_type":   {entity_type -> [entity_key, ...]}  (the index for retrieval),
          "domains":   the causal domains built,
          "created"/"updated", "internal_only": True,
          "grounding": per-source entity+edge counts (auditable),
        }

    GROUNDED BY CONSTRUCTION: an entity with no captured grounding source is never emitted; a
    causal link still obeys build_model_from_graph's grounding (world-edge or reality hypothesis).
    An empty creature yields an empty world model (proven in the world selftest). Read-only on the
    world/reality/meaning/LIRF stores; persists to its OWN store by default. Never raises."""
    # (a) the causal layer — one sub-model per captured domain, unioned into typed causal links.
    entities, relations = _gather_world_entities_and_relations(name)
    causal_links: list = []
    domains: list = []
    seen_link = set()
    for topic in _world_causal_topics(name):
        try:
            cm = build_model_from_graph(name, topic, persist=False)
        except Exception:
            continue
        if not cm.get("edges"):
            continue
        domains.append(cm.get("topic", topic))
        for ce in cm.get("edges", []):
            lk = (ce["src"], ce["dst"], ce["relation"])
            if lk in seen_link:
                continue
            seen_link.add(lk)
            causal_links.append({
                "id": _new_id("cl"), "src": ce["src"], "dst": ce["dst"],
                "relation": ce["relation"], "confidence": ce["confidence"],
                "support": ce.get("support", 1),
                "sources": list(ce.get("sources", [])),
                "evidence": list(ce.get("evidence", [])),
                "domain": cm.get("topic", topic),
            })
            # (b) JOIN — every causal node must be a typed entity (create/upgrade as needed).
            for node, other_pred in ((ce["src"], ""), (ce["dst"], "")):
                nkey = _norm_node(node)
                if not nkey:
                    continue
                if nkey not in entities:
                    # classify a causal-only node: a reality candidate key types by its taxonomy;
                    # otherwise by surface lexicon (STATE/TOPIC fallback). Grounded by the causal
                    # edge's own evidence + source.
                    is_rkey = SRC_REALITY_HYP in ce.get("sources", []) and node == ce["src"]
                    etype = _classify_entity(str(node), reality_key=is_rkey)
                    src_tag = (SRC_REALITY_HYP if SRC_REALITY_HYP in ce.get("sources", [])
                               else SRC_WORLD_EDGE)
                    prov = (ce.get("evidence", [None]) or [None])[0] or f"causal node: {nkey}"
                    e = {"id": _entity_id(nkey), "type": etype, "key": nkey,
                         "label": _label(nkey), "confidence": _clamp(ce["confidence"]),
                         "provenance": [prov], "sources": [src_tag]}
                    entities[nkey] = e

    # finalise — index by type; tally grounding; drop any entity that ended ungrounded (defensive).
    by_type: dict = {t: [] for t in ENTITY_TYPES}
    grounding = {SRC_WORLD_EDGE: 0, SRC_REALITY_HYP: 0, SRC_LIRF_FACT: 0, SRC_COOCCURRENCE: 0}
    final_entities = []
    for key, e in entities.items():
        grounded = [s for s in e.get("sources", [])
                    if s in (SRC_WORLD_EDGE, SRC_REALITY_HYP, SRC_LIRF_FACT)]
        if not grounded:
            continue  # an entity with no captured grounding is never emitted (GROUNDED)
        e["confidence"] = round(_clamp(e["confidence"]), 4)
        final_entities.append(e)
        by_type.setdefault(e["type"], []).append(e["key"])
        for s in e.get("sources", []):
            if s in grounding:
                grounding[s] += 1
    for cl in causal_links:
        for s in cl.get("sources", []):
            if s in grounding:
                grounding[s] += 1
    for wr in relations:
        for s in wr.get("sources", []):
            if s in grounding:
                grounding[s] += 1
    final_entities.sort(key=lambda x: (x["type"], x["key"]))
    by_type = {t: sorted(v) for t, v in by_type.items() if v}

    now = _now()
    wm = {
        "id": _new_id("wmworld"),
        "version": VERSION,
        "name": name,
        "entities": final_entities,
        "relations": relations,
        "causal_links": causal_links,
        "by_type": by_type,
        "domains": sorted(dict.fromkeys(domains)),
        "created": now,
        "updated": now,
        "internal_only": True,   # LAW 2 — Vera's private map of LAMAR's world; never asserted
        "grounding": grounding,
    }
    if persist and (final_entities or causal_links):
        _store_world_model(name, wm)
    return wm


# ===========================================================================
# THE WORLD-MODEL STORE — a SEPARATE file from the per-domain causal-model store, holding the
# coherent world models keyed by id, persisted ADDITIVELY (re-read + union by id), exactly the
# world_state/reality continuity discipline.
# ===========================================================================

def world_store_path(name: str) -> Path:
    """The coherent-world-model store for ``name`` — distinct from {name}.worldmodel.json (the
    per-domain causal models). Holds the typed world models keyed by id."""
    return STORE / f"{name}.worldmodel_world.json"


def _load_world_store(name: str) -> dict:
    d = load_json(world_store_path(name))
    if not isinstance(d, dict):
        return {"version": VERSION, "models": {}}
    d.setdefault("models", {})
    return d


def _store_world_model(name: str, wm: dict) -> None:
    """Persist ONE world model additively: re-read the on-disk store and union by id (ours wins for
    its own id), so a concurrent writer's models are never dropped. Best-effort; a write failure is
    swallowed (the in-memory model is still returned)."""
    try:
        STORE.mkdir(parents=True, exist_ok=True)
        disk = _load_world_store(name)
        models_d = disk.get("models", {})
        if not isinstance(models_d, dict):
            models_d = {}
        models_d[wm["id"]] = wm
        save_json(world_store_path(name), {"version": VERSION, "models": models_d})
    except Exception:
        pass


def get_world_model(name: str, model_id: str) -> Optional[dict]:
    """Load ONE world model by id, or None. Read-only; never raises."""
    return _load_world_store(name).get("models", {}).get(model_id)


def world_models(name: str) -> list:
    """All stored world models for ``name`` (newest ``created`` last). Read-only; never raises."""
    ms = list(_load_world_store(name).get("models", {}).values())
    ms.sort(key=lambda m: m.get("created", ""))
    return ms


# ===========================================================================
# RETRIEVAL — "facts become meaning" must be RETRIEVABLE. Pull a typed entity, the entities of a
# type, the relations touching an entity, and the causal links — all read-only over a built model.
# ===========================================================================

def get_entity(wm: dict, key_or_id: str) -> Optional[dict]:
    """One typed entity from a world model, by node key OR entity id. None if absent. Pure."""
    if not isinstance(wm, dict):
        return None
    k = _norm_node(key_or_id)
    for e in wm.get("entities", []) or []:
        if e.get("key") == k or e.get("id") == key_or_id or e.get("key") == key_or_id:
            return e
    return None


def entities_of_type(wm: dict, etype: str) -> list:
    """Every entity of a given type (PERSON/PROJECT/GOAL/RESOURCE/RISK/CONSTRAINT/…). Pure."""
    if not isinstance(wm, dict):
        return []
    return [e for e in wm.get("entities", []) or [] if e.get("type") == etype]


def relations_of(wm: dict, key_or_id: str, *, include_causal: bool = True) -> list:
    """Every edge (typed world relation + optionally causal link) touching an entity — its place
    in the world. Read-only over the built model. Pure."""
    if not isinstance(wm, dict):
        return []
    ent = get_entity(wm, key_or_id)
    k = ent["key"] if ent else _norm_node(key_or_id)
    out = [r for r in wm.get("relations", []) or [] if r.get("src") == k or r.get("dst") == k]
    if include_causal:
        out += [c for c in wm.get("causal_links", []) or [] if c.get("src") == k or c.get("dst") == k]
    return out


def causal_links(wm: dict) -> list:
    """Every typed causal link in the world model (the causal-chain edges). Pure."""
    if not isinstance(wm, dict):
        return []
    return list(wm.get("causal_links", []) or [])


def world_causal_chains(wm: dict, max_chains: int = 6) -> list:
    """The directed causal PATHS through the world model's causal links, longest first — the same
    chain reconstruction ``causal_chains`` does, but over the world model's typed causal edges (so
    the manager_change -> strain -> poor_sleep -> productivity through-line is recoverable from the
    coherent world model, not just a single-domain causal model). Pure; never raises."""
    return causal_chains({"edges": causal_links(wm),
                          "nodes": sorted({c["src"] for c in causal_links(wm)}
                                          | {c["dst"] for c in causal_links(wm)})},
                         max_chains=max_chains)


# ===========================================================================
# explain_world_model — render the WORLD as understanding: the people/projects/goals/resources/
# risks/constraints by type, the typed relations, and the causal through-lines with per-edge
# provenance. INTERNAL model-state; every generated line passes the no-diagnosis clean-gate.
# ===========================================================================

_ENTITY_TYPE_LABEL = {
    ENT_SELF: "the person themselves",
    ENT_PERSON: "people in their world",
    ENT_PROJECT: "the work / projects",
    ENT_GOAL: "what they're reaching for",
    ENT_RESOURCE: "what they rely on",
    ENT_RISK: "what's weighing on them",
    ENT_CONSTRAINT: "what bounds them",
    ENT_STATE: "states they're in",
    ENT_TOPIC: "other things on their mind",
}

_WORLD_REL_PHRASE = {
    REL_RELATES_TO: "is connected to",
    REL_WORKS_ON: "is working on",
    REL_PURSUES: "is reaching for",
    REL_RELIES_ON: "relies on",
    REL_THREATENS: "is a risk to",
    REL_BOUNDS: "bounds",
}

_WORLD_EXPLAIN_HEADER = (
    "WHAT YOU UNDERSTAND ABOUT THEIR WHOLE WORLD — an INTERNAL, TYPED map of their life.\n"
    "  This is YOUR private picture of who and what is in their world and how it connects —\n"
    "  never to be stated at them as fact, never a diagnosis, never \"your manager is causing\n"
    "  your insomnia.\" It only helps you understand them; it is never a claim to assert."
)


def explain_world_body(wm: dict) -> str:
    """The GENERATED lines of a world model's explanation — entities by type, typed relations, and
    the causal through-lines with their evidence — WITHOUT the fixed framing legend. Every line
    passes the no-diagnosis clean-gate; this is the body a no-diagnosis assertion inspects
    (mirroring explain_body / reality.render_body). "" for an empty world model. Pure."""
    if not isinstance(wm, dict) or not (wm.get("entities") or wm.get("causal_links")):
        return ""

    def clean(s: str) -> str:
        return _safe_statement(s, "(an internal model note)")

    out = []
    out.append(clean(
        f"[MODEL] their world: {len(wm.get('entities', []))} entities, "
        f"{len(wm.get('relations', []))} relations, {len(wm.get('causal_links', []))} causal links"))

    # entities by type (only the types actually present).
    out.append("")
    out.append("  [NODE] who & what is in their world (by kind):")
    by_type = wm.get("by_type", {})
    for etype in ENTITY_TYPES:
        keys = by_type.get(etype)
        if not keys:
            continue
        label = _ENTITY_TYPE_LABEL.get(etype, etype)
        out.append(clean(f"    • {label}: " + ", ".join(_label(k) for k in keys)))

    # typed non-causal relations.
    rels = wm.get("relations", []) or []
    if rels:
        out.append("")
        out.append("  [LINK] how they relate:")
        seen = set()
        for r in rels:
            sig = (r.get("src"), r.get("type"), r.get("dst"))
            if sig in seen:
                continue
            seen.add(sig)
            verb = _WORLD_REL_PHRASE.get(r.get("type"), "relates to")
            out.append(clean(f"    • {_label(r.get('src'))} {verb} {_label(r.get('dst'))}"
                             f"   [{r.get('type')}, {float(r.get('confidence', 0)):.2f}]"))
            for ev in (r.get("evidence", []) or [])[:1]:
                out.append(f"        ↳ {ev}")

    # the causal through-lines + each link with its evidence.
    links = causal_links(wm)
    if links:
        chains = world_causal_chains(wm)
        out.append("")
        out.append("  [CHAIN] how things drive each other (longest first):")
        for ch in chains:
            out.append(clean(f"    • {_chain_sentence(ch)}   (mean confidence {_mean_conf(ch):.2f})"))
        out.append("")
        out.append("  [CAUSE] each causal link, with the evidence it rests on:")
        for e in sorted(links, key=lambda x: (-float(x["confidence"]), x["src"])):
            verb = _REL_PHRASE.get(e["relation"], "connects to")
            out.append(clean(
                f"    • {_label(e['src'])} --[{e['relation']}, {float(e['confidence']):.2f}]--> "
                f"{_label(e['dst'])}   ({_label(e['src'])} {verb} {_label(e['dst'])})"))
            for ev in e.get("evidence", [])[:2]:
                out.append(f"        ↳ {ev}")
    return "\n".join(out)


def explain_world_model(name: Optional[str] = None, model_id: Optional[str] = None,
                        wm: Optional[dict] = None) -> str:
    """Render a coherent world model READABLY — entities by type, typed relations, and the causal
    through-lines with per-edge provenance. INTERNAL model-state: the GENERATED lines
    (``explain_world_body``) pass the no-diagnosis clean-gate, framed as understanding-FOR-VERA,
    NEVER a claim to assert at the user. Pass a loaded ``wm`` directly, or ``name``+``model_id``.
    Returns "" for an unknown/empty model. Read-only; never raises."""
    if wm is None and name is not None and model_id is not None:
        wm = get_world_model(name, model_id)
    body = explain_world_body(wm)
    if not body:
        return ""
    return f"{_WORLD_EXPLAIN_HEADER}\n\n{body}"


def render_world(name: str) -> str:
    """Human-readable audit of every stored coherent world model for ``name`` — the typed map +
    its grounding. The world counterpart to ``render``. Uses the GENERATED body (not the
    forbidding legend) so the whole audit is itself clean-gated. Read-only; never raises."""
    ms = world_models(name)
    out = [f"The coherent world model {name} holds about your world (INTERNAL model-state — never "
           f"spoken, never asserted at the user): {len(ms)}"]
    if not ms:
        out.append("  (no world model built yet — it emerges from your captured facts; an")
        out.append("   ungrounded entity or link is never fabricated)")
        return "\n".join(out)
    for m in ms:
        out.append("")
        out.append(f"  WORLD [{m.get('id')}]  entities={len(m.get('entities', []))}  "
                   f"relations={len(m.get('relations', []))}  "
                   f"causal_links={len(m.get('causal_links', []))}  grounded_by={m.get('grounding')}")
        for ln in explain_world_body(m).splitlines():
            out.append("    " + ln)
    return "\n".join(out)


# Extend the scaffold-token set so the mouth's leak-scrub learns this layer's one new framing
# phrase (the [MODEL]/[CAUSE]/[CHAIN]/[NODE] tags are already covered above).
WORLD_MODEL_SCAFFOLD_TOKENS = tuple(dict.fromkeys(
    WORLD_MODEL_SCAFFOLD_TOKENS + ("WHAT YOU UNDERSTAND ABOUT THEIR WHOLE WORLD",)))


# ===========================================================================
# SYNTHETIC PROOF (WORLD) — the canonical manager -> stress -> poor_sleep -> productivity world,
# built from a stated world graph + reality's competing hypotheses + LIRF facts, as TYPED
# entities + typed relations + typed causal links. Hermetic by the caller's STORE redirect.
# ===========================================================================

def build_synthetic_world(name: str) -> dict:
    """Build the canonical WORLD model end to end against whatever STORE is bound, entirely from
    GROUNDED captured facts — the manager -> stress -> poor_sleep -> productivity chain as a chain
    of TYPED entities, plus the people/projects/goals/resources/risks/constraints around it:

      * SEED THE WORLD GRAPH with the stated situation the user actually said — the new manager,
        the stress affecting sleep, sleep leading to low productivity, the project ("the launch"),
        a stated goal, a money worry (a RISK), the deadline (a CONSTRAINT), the employer (a
        RESOURCE, via a LIRF fact).
      * SEED + RESOLVE THE REALITY LOOP — the Day-1 change -> competing stress hypotheses
        (manager_change leading) + the sleep_decline prediction, resolved Day-14.
      * BUILD the coherent world model: typed entities + typed relations + typed causal links.

    Returns ``{world, world_seeded, reality_resolved, lirf_seeded}`` so a caller can assert the
    typed chain reconstructs with provenance. Never raises."""
    out = {"world": {}, "world_seeded": False, "reality_resolved": False, "lirf_seeded": False}

    # --- (1) seed the WORLD graph with the stated situation (grounded typed edges) --------------
    if _HAVE_WORLD and _world is not None:
        try:
            _world.capture_relations(name, "my work's been really stressful because of my new manager")
            _world.capture_relations(name, "honestly the stress is affecting my sleep")
            _world.relate(name, "sleep", "leads_to", "low productivity", kind="inference")
            _world.relate(name, "you", "stressed_by", "work", kind="problem")
            # the people/projects/goals/resources/risks/constraints around the chain (all stated):
            _world.relate(name, "you", "has", "manager", kind="relationship")     # a PERSON
            _world.relate(name, "you", "working_toward", "ship the launch", kind="goal")  # a GOAL
            _world.relate(name, "you", "worried_about", "money", kind="problem")  # a RISK
            _world.relate(name, "you", "works_on", "the launch", kind="fact")     # a PROJECT
            _world.relate(name, "the launch", "bounded_by", "the deadline", kind="fact")
            _world.relate(name, "you", "stressed_by", "the deadline", kind="problem")  # a CONSTRAINT
            out["world_seeded"] = True
        except Exception:
            pass

    # --- (1b) a LIRF fact: the employer (a RESOURCE Lamar relies on). The module-level capture()
    # does extract + MERGE + save (Facts.capture only RETURNS candidates), so the employer row is
    # actually persisted and surfaces as a RESOURCE entity grounded by SRC_LIRF_FACT. -------------
    try:
        from . import memory_lirf as _lirf
        rows = _lirf.capture(name, "I work at Collatio")   # employer -> a grounded RESOURCE entity
        out["lirf_seeded"] = bool(rows)
    except Exception:
        pass

    # --- (2) seed + resolve the REALITY loop -----------------------------------------------------
    if _HAVE_REALITY and _reality is not None:
        try:
            _reality.form(name, "my manager just changed and work's been heavy lately",
                          at=_SYNTH_DAY1)
            _reality.resolve(name, "honestly I've barely slept the last two weeks",
                             at=_reality._add_days(_SYNTH_DAY1, 14))
            out["reality_resolved"] = True
        except Exception:
            pass

    # --- (3) BUILD the coherent world model ------------------------------------------------------
    out["world"] = build_world_model(name)
    return out


# ===========================================================================
# SELF-TEST — run directly: `python3 -m anima.world_model`. No model, no network; FULLY HERMETIC —
# redirects EVERY engine STORE the build path could write (world_model.STORE on BOTH __main__ +
# package bindings, world_state/reality/meaning/memory_lirf/curiosity/constitution/telemetry/cloud
# STORE, reliability.DEFAULT_STORE) to ONE temp dir, and asserts the real .anima is byte-UNCHANGED
# around the run. Mirrors reality._selftest's multi-store redirect + the sibling ok(label, cond).
# ===========================================================================

_SELFTEST_STORE_TARGETS = (
    ("anima.world_model", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.reality", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.memory_lirf", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.constitution", "STORE"),
    ("anima.reliability", "DEFAULT_STORE"),
    ("anima.telemetry", "STORE"),
    ("anima.cloud", "STORE"),
)


def _hash_anima(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (EXCLUDING the rotating backups/ dir, which
    legitimately changes), so we can PROVE the harness touched nothing — the reality / evolution /
    relationship guardrail, applied here."""
    import hashlib
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


def _selftest() -> int:
    import glob
    import sys as _sys
    import tempfile

    fails: list = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("world_model (Causal Models) self-test")

    # the real .anima footprint BEFORE — must be byte-identical after (hermetic guardrail).
    real = Path(__file__).resolve().parent.parent / ".anima"
    fp_before = _hash_anima(real)

    # --- pure machinery: clean-gate / clamp / climb / chain-sentence are real functions ---------
    ok("clean-gate: a neutral causal phrase is clean",
       _is_clean("a recent change is upstream of strain, which is reaching rest"))
    ok("clean-gate: a DIAGNOSIS asserted at the user is caught",
       not _is_clean("your manager is causing your insomnia")
       and not _is_clean("you're burning out") and not _is_clean("you will spiral"))
    ok("clamp: confidence is bounded to [floor, ceil]",
       _clamp(2.0) == _CONF_CEIL and _clamp(-1.0) == _CONF_FLOOR and _clamp(0.5) == 0.5)
    ok("climb: corroboration moves a confidence UP toward the ceiling, never past it",
       _climb(0.5) > 0.5 and _climb(0.99) <= _CONF_CEIL)
    ok("strengthen/weaken: the reweight scales up on confirm, down on contradict",
       _clamp(0.5 * _SUPPORT_GAIN) > 0.5 and _clamp(0.5 * _CONTRADICT_DECAY) < 0.5)

    # --- HERMETIC block: redirect EVERY engine store to one temp dir; restore on exit -----------
    targets = []
    seen = set()
    for modpath, attr in _SELFTEST_STORE_TARGETS:
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, attr) and (id(mod), attr) not in seen:
            targets.append((mod, attr))
            seen.add((id(mod), attr))
    # pin BOTH the package binding AND this very module object (they may differ under -m).
    try:
        import anima.world_model as _pkg_self
        if (id(_pkg_self), "STORE") not in seen:
            targets.append((_pkg_self, "STORE"))
            seen.add((id(_pkg_self), "STORE"))
    except Exception:
        pass
    _this = _sys.modules.get(__name__)
    if _this is not None and (id(_this), "STORE") not in seen:
        targets.append((_this, "STORE"))
        seen.add((id(_this), "STORE"))

    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    _td = tempfile.mkdtemp(prefix="worldmodel-self-")
    _tp = Path(_td)
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, _tp)

    try:
        # ============================================================================
        # THE CANONICAL PROOF — build the manager -> stress -> poor_sleep -> low_energy model
        # from a stated graph + reality's competing hypotheses, GROUNDED, then evolve it.
        # ============================================================================
        name = "wm_selftest_" + secrets.token_hex(3)
        built = build_synthetic_model(name)
        model = built["model"]

        ok("seed: the world graph + reality loop were seeded for the proof",
           built["world_seeded"] and built["reality_resolved"])
        ok("BUILD: a non-empty causal model was constructed",
           isinstance(model, dict) and len(model.get("edges", [])) > 0
           and len(model.get("nodes", [])) > 1)
        ok("BUILD: the model is flagged internal_only (LAW 2 — never asserted at the user)",
           model.get("internal_only") is True)

        node_blob = " ".join(model.get("nodes", []))
        edge_keys = {(e["src"], e["dst"], e["relation"]) for e in model.get("edges", [])}

        def _has_edge(src, dst):
            return any(e["src"] == src and e["dst"] == dst for e in model.get("edges", []))

        # --- the causal CHAIN is present: manager -> work, work/strain, stress -> sleep, sleep -> energy
        ok("CHAIN: the manager node is in the model (the upstream cause)",
           any("manager" in n for n in model.get("nodes", [])))
        ok("CHAIN: a strain node is reached (work/stress -> strain)",
           "strain" in model.get("nodes", []))
        ok("CHAIN: a sleep node is reached (strain/stress -> sleep)",
           any("sleep" in n for n in model.get("nodes", [])))
        ok("CHAIN: a downstream energy node is reached (sleep -> low energy)",
           any("energy" in n for n in model.get("nodes", [])))

        # the longest causal chain spans multiple hops (reasoning ACROSS the chain).
        chains = causal_chains(model)
        longest = chains[0] if chains else []
        ok("CHAIN: a multi-hop causal through-line exists (>= 3 links)",
           bool(longest) and len(longest) >= 3)
        ok("CHAIN: the through-line runs from an upstream cause to a downstream consequence",
           bool(longest)
           and any("manager" in longest[0]["src"] or "work" in longest[0]["src"]
                   or "stress" in longest[0]["src"] for _ in [0])
           and any("energy" in longest[-1]["dst"] or "sleep" in longest[-1]["dst"]
                   for _ in [0]))

        # --- GROUNDED: every edge cites real evidence + a grounding source -----------------------
        ok("GROUNDED: EVERY edge carries at least one grounding source (world-edge or hypothesis)",
           all(any(s in (SRC_WORLD_EDGE, SRC_REALITY_HYP) for s in e.get("sources", []))
               for e in model.get("edges", [])))
        ok("GROUNDED: EVERY edge cites at least one concrete piece of evidence",
           all(len(e.get("evidence", [])) >= 1 for e in model.get("edges", [])))
        ok("GROUNDED: the model records a per-source grounding count (auditable)",
           isinstance(model.get("grounding"), dict)
           and (model["grounding"].get(SRC_WORLD_EDGE, 0)
                + model["grounding"].get(SRC_REALITY_HYP, 0)) >= len(model["edges"]) - 0
           and model["grounding"].get(SRC_REALITY_HYP, 0) >= 1)
        # at least one edge is grounded in a stated world-edge AND one in a reality hypothesis.
        ok("GROUNDED: at least one link comes from a STATED world-graph edge",
           any(SRC_WORLD_EDGE in e.get("sources", []) for e in model.get("edges", [])))
        ok("GROUNDED: at least one link comes from a reality COMPETING HYPOTHESIS",
           any(SRC_REALITY_HYP in e.get("sources", []) for e in model.get("edges", [])))
        # the manager_change candidate became a grounded cause edge from the reality competition.
        ok("GROUNDED: the manager_change hypothesis is a grounded cause upstream of strain",
           any(e["src"] == "manager_change" and e["dst"] == "strain"
               and SRC_REALITY_HYP in e.get("sources", []) for e in model.get("edges", [])))

        # --- THE NEGATIVE PROOF — an UNGROUNDED domain yields NO causal edges (never invent) -----
        ungrounded_name = "wm_ungrounded_" + secrets.token_hex(3)
        ung = build_model_from_graph(ungrounded_name, "photosynthesis", persist=False)
        ok("UNGROUNDED: a domain with no stated edges + no hypotheses yields ZERO edges",
           len(ung.get("edges", [])) == 0 and len(ung.get("nodes", [])) == 0)
        # even a real creature's UNRELATED topic (no causal edges, no hypotheses) stays empty.
        ung2 = build_model_from_graph(name, "astronomy", persist=False)
        ok("UNGROUNDED: an unrelated topic on a real creature still emits no fabricated causation",
           all(any(s in (SRC_WORLD_EDGE, SRC_REALITY_HYP) for s in e.get("sources", []))
               for e in ung2.get("edges", [])))

        # co-occurrence ALONE is never grounding: prove no edge rests on co-occurrence only.
        ok("GROUNDED: NO edge is grounded by co-occurrence ALONE (corroboration only)",
           all(set(e.get("sources", [])) != {SRC_COOCCURRENCE} for e in model.get("edges", [])))

        # --- explain_model: readable chain + evidence, INTERNAL, clean-gated ---------------------
        block = explain_model(model.get("id", ""), model=model)
        body = explain_body(model)
        ok("explain: produces a non-empty causal-chain rendering", bool(block.strip()))
        ok("explain: names it an INTERNAL model + the domain + the chain/cause sections",
           "INTERNAL causal model" in block and "[MODEL]" in block
           and "[CHAIN]" in block and "[CAUSE]" in block)
        ok("explain: shows the through-line as a connected chain (not isolated slots)",
           "which" in body.lower() or "upstream" in body.lower())
        ok("explain: each link is annotated with a confidence and its evidence",
           "↳" in body and "0." in body)
        # the NO-DIAGNOSIS gate inspects the GENERATED body (the causal lines built from the model)
        # — NOT the fixed framing legend, which legitimately NAMES "diagnosis"/"fact" in order to
        # FORBID them (the reality.render_body / trajectory._items_of pattern).
        ok("NO-DIAGNOSIS GATE: not one GENERATED body line trips a banned term",
           all(_is_clean(ln) for ln in body.splitlines()))
        ok("NO-DIAGNOSIS: the header that NAMES 'diagnosis' to forbid it is fixed framing, not data",
           not _is_clean(_EXPLAIN_HEADER) and "diagnosis" in block.lower())
        ok("INTERNAL-ONLY: the explanation forbids asserting the model at the user, by construction",
           "never to be stated at" in block and "never a claim to assert at the user" in block)
        ok("explain: every emitted tag is in WORLD_MODEL_SCAFFOLD_TOKENS (scrubbable)",
           all(t in WORLD_MODEL_SCAFFOLD_TOKENS for t in ("[MODEL]", "[CHAIN]", "[CAUSE]")))
        ok("explain: unknown / empty model -> empty string",
           explain_model("nope", model={"edges": []}) == "" and explain_body({"edges": []}) == "")

        # --- update_model_with_outcome: a resolved outcome SHIFTS an edge confidence -------------
        evolved = built["evolved"]
        # find the strain -> poor_sleep edge (the one the sleep_decline outcome bears on).
        def _edge(m, src, dst):
            return next((e for e in m.get("edges", []) if e["src"] == src and e["dst"] == dst), None)
        b_edge = _edge(model, "strain", "poor_sleep")
        a_edge = _edge(evolved, "strain", "poor_sleep")
        ok("UPDATE: the sleep_decline edge exists to be updated (strain -> poor_sleep)",
           b_edge is not None and a_edge is not None)
        ok("UPDATE: a CONFIRMED outcome STRENGTHENED the relevant edge's confidence",
           bool(b_edge) and bool(a_edge)
           and a_edge["confidence"] > b_edge["confidence"])
        ok("UPDATE: the shift is recorded APPEND-ONLY in the edge's history (before -> after)",
           bool(a_edge) and len(a_edge.get("history", [])) >= 1
           and a_edge["history"][-1]["after"] == a_edge["confidence"]
           and a_edge["history"][-1]["before"] == b_edge["confidence"])
        ok("UPDATE: the input model snapshot is left UNTOUCHED (so before/after can be diffed)",
           b_edge["confidence"] != a_edge["confidence"] and not b_edge.get("history"))
        ok("UPDATE: the evolved model is still flagged internal_only",
           evolved.get("internal_only") is True)

        # a CONTRADICTED outcome WEAKENS instead (the symmetric control).
        contra = update_model_with_outcome(
            model.get("id", ""),
            {"confirmed": False, "category": "sleep_decline", "observed": "sleeping great"},
            model=model, persist=False)
        c_edge = _edge(contra, "strain", "poor_sleep")
        ok("UPDATE (contradict): a refuted outcome WEAKENS the edge (and floors, never annihilates)",
           bool(c_edge) and c_edge["confidence"] < b_edge["confidence"]
           and c_edge["confidence"] >= _CONF_FLOOR)

        # an IRRELEVANT outcome touches nothing.
        irrel = update_model_with_outcome(
            model.get("id", ""), {"confirmed": True, "nodes": ["weather"]},
            model=model, persist=False)
        ok("UPDATE (irrelevant): an outcome about an unrelated node changes no edge",
           irrel.get("last_outcome", {}).get("edges_touched") == 0)

        # --- compare_models: the evolution is auditable ------------------------------------------
        # (edge labels render node keys with _label, so "poor_sleep" reads "poor sleep" — match on
        # the surviving tokens "poor"+"sleep", not the underscored key.)
        diff = built["diff"]
        ok("COMPARE: the before/after diff reports the strengthened link",
           any("poor" in r["edge"] and "sleep" in r["edge"] for r in diff.get("strengthened", []))
           and len(diff.get("strengthened", [])) >= 1)
        ok("COMPARE: the strengthened record carries before/after/delta with delta > 0",
           all("before" in r and "after" in r and r["delta"] > 0
               for r in diff.get("strengthened", [])))
        ok("COMPARE: a contradiction diff reports the weakened link instead",
           any("poor" in r["edge"] and "sleep" in r["edge"]
               for r in compare_models(model, contra).get("weakened", [])))
        ok("COMPARE: a no-op diff (model vs itself) reports the model held steady",
           compare_models(model, model)["strengthened"] == []
           and compare_models(model, model)["weakened"] == []
           and compare_models(model, model)["unchanged"] >= 1)
        ok("COMPARE: render_comparison produces a clean, non-empty evolution block",
           bool(render_comparison(diff).strip())
           and all(_is_clean(ln) for ln in render_comparison(diff).splitlines()))

        # --- persistence: the model round-trips through the store, additively --------------------
        loaded = get_model(name, model.get("id", ""))
        ok("persist: the built model round-trips through its own store",
           loaded is not None and loaded.get("id") == model.get("id")
           and len(loaded.get("edges", [])) == len(model.get("edges", [])))
        # additive: building a SECOND model for the same creature does not drop the first.
        m2 = build_model_from_graph(name, "work_stress")
        all_ids = {m["id"] for m in models(name)}
        ok("persist: a second model is ADDED, not overwritten (continuity)",
           model.get("id") in all_ids and m2.get("id") in all_ids and len(all_ids) >= 2)

        # --- the store file is OUR own file; the world/reality stores are untouched by the build -
        ok("additive: world_model wrote ONLY its own .worldmodel.json (own store)",
           store_path(name).exists())

        # --- render(name): the audit surface lists the models + their grounding ------------------
        rep = render(name)
        ok("render(name): audits the stored models with their grounding + chains",
           "causal models" in rep and "domain=" in rep and "grounded_by" in rep)
        ok("NO-DIAGNOSIS GATE: render(name) emits no banned term either",
           all(_is_clean(ln) for ln in rep.splitlines()))

        # --- ROBUSTNESS: garbage inputs never raise ----------------------------------------------
        try:
            build_model_from_graph(name, "", persist=False)
            build_model_from_graph(name, None, persist=False)
            update_model_with_outcome("nope", {}, name="nobody")
            update_model_with_outcome("nope", None, model=model, persist=False)
            compare_models(None, None)
            compare_models({"edges": [1, 2]}, {"edges": None})
            explain_model("x", name="nobody")
            get_model("nobody", "x")
            crashed = False
        except Exception as e:  # noqa: BLE001
            crashed = True
            print("       (raised:", repr(e), ")")
        ok("robust: garbage/None inputs are handled without raising", not crashed)

        # ============================================================================
        # WORLD UNDERSTANDING PROOF — the coherent TYPED world model: typed entities + typed
        # relations + typed causal links, all grounded, with the manager -> stress -> sleep ->
        # productivity chain reconstructed as a chain of TYPED entities with per-edge provenance.
        # ============================================================================
        wname = "wm_world_" + secrets.token_hex(3)
        wbuilt = build_synthetic_world(wname)
        world = wbuilt["world"]

        ok("WORLD seed: world graph + reality loop + LIRF fact were seeded for the proof",
           wbuilt["world_seeded"] and wbuilt["reality_resolved"])
        ok("WORLD BUILD: a non-empty TYPED world model was constructed",
           isinstance(world, dict) and len(world.get("entities", [])) > 1
           and len(world.get("causal_links", [])) > 0)
        ok("WORLD BUILD: the model is flagged internal_only (LAW 2 — never asserted at the user)",
           world.get("internal_only") is True)

        ents = {e["key"]: e for e in world.get("entities", [])}
        by_type = world.get("by_type", {})

        def _typed(key):
            e = ents.get(_norm_node(key))
            return e["type"] if e else None

        # --- TYPED ENTITIES: every required entity TYPE is present + grounded ---------------------
        ok("WORLD ENTITIES: Lamar himself is the SELF hub entity",
           any(e["type"] == ENT_SELF for e in world.get("entities", [])))
        ok("WORLD ENTITIES: a PERSON entity exists (a person in his world)",
           bool(by_type.get(ENT_PERSON)))
        ok("WORLD ENTITIES: a GOAL entity exists (what he's reaching for)",
           bool(by_type.get(ENT_GOAL)))
        ok("WORLD ENTITIES: a RISK entity exists (what's weighing on him — e.g. money)",
           bool(by_type.get(ENT_RISK)))
        ok("WORLD ENTITIES: a STATE entity exists (strain / poor sleep)",
           bool(by_type.get(ENT_STATE)))
        # a RESOURCE entity grounded by a LIRF fact (the employer) — the fourth grounding source.
        ok("WORLD ENTITIES: a RESOURCE entity exists, grounded by a LIRF fact (the employer)",
           wbuilt["lirf_seeded"] and bool(by_type.get(ENT_RESOURCE))
           and any(SRC_LIRF_FACT in e.get("sources", [])
                   for e in entities_of_type(world, ENT_RESOURCE)))
        ok("WORLD GROUNDED: the LIRF-fact grounding source fired (employer captured as a value)",
           world.get("grounding", {}).get(SRC_LIRF_FACT, 0) >= 1)
        # the manager_change driver is typed as a PERSON-change (grounded by the reality key).
        ok("WORLD ENTITIES: manager_change is typed PERSON (grounded by its reality key)",
           _typed("manager_change") == ENT_PERSON)
        # the money worry is a RISK (grounded by the 'worried_about'/problem kind).
        ok("WORLD ENTITIES: money is typed RISK (grounded by the worry it was captured under)",
           _typed("money") == ENT_RISK)

        # --- EVERY entity is GROUNDED (cites captured fact(s) + a grounding source) ---------------
        ok("WORLD GROUNDED: EVERY entity carries at least one provenance fact",
           all(len(e.get("provenance", [])) >= 1 for e in world.get("entities", [])))
        ok("WORLD GROUNDED: EVERY entity carries a captured grounding source (world/reality/LIRF)",
           all(any(s in (SRC_WORLD_EDGE, SRC_REALITY_HYP, SRC_LIRF_FACT)
                   for s in e.get("sources", [])) for e in world.get("entities", [])))
        ok("WORLD GROUNDED: the model records a per-source grounding tally (auditable)",
           isinstance(world.get("grounding"), dict)
           and world["grounding"].get(SRC_REALITY_HYP, 0) >= 1)

        # --- TYPED RELATIONS: the non-causal bonds (person<->Lamar, Lamar->goal) ------------------
        rel_sigs = {(r["src"], r["type"], r["dst"]) for r in world.get("relations", [])}
        rel_types = {r["type"] for r in world.get("relations", [])}
        ok("WORLD RELATIONS: a RELATES_TO bond connects a person to Lamar",
           REL_RELATES_TO in rel_types
           and any(t == REL_RELATES_TO and d == "you" for (_s, t, d) in rel_sigs))
        ok("WORLD RELATIONS: a PURSUES bond connects Lamar to a goal",
           any(t == REL_PURSUES and s == "you" for (s, t, _d) in rel_sigs))
        ok("WORLD RELATIONS: every typed relation cites its evidence",
           all(len(r.get("evidence", [])) >= 1 for r in world.get("relations", [])))

        # --- THE CAUSAL CHAIN, end to end, over TYPED entities, with provenance -------------------
        wlinks = causal_links(world)

        def _wedge(src, dst):
            return next((c for c in wlinks if c["src"] == src and c["dst"] == dst), None)

        # the four hops of the canonical chain (each grounded; each between typed entities).
        e_mgr = _wedge("manager_change", "strain")
        e_sleep = _wedge("strain", "poor_sleep")
        ok("WORLD CHAIN: manager_change --causes/contributes--> strain link exists",
           e_mgr is not None)
        ok("WORLD CHAIN: strain --worsens--> poor_sleep link exists",
           e_sleep is not None)
        # the through-line spans multiple typed hops (reasoning ACROSS the chain).
        wchains = world_causal_chains(world)
        wlongest = wchains[0] if wchains else []
        ok("WORLD CHAIN: a multi-hop causal through-line exists over the world model (>= 3 links)",
           bool(wlongest) and len(wlongest) >= 3)
        ok("WORLD CHAIN: the through-line runs from an upstream driver to a downstream consequence",
           bool(wlongest)
           and ("manager" in wlongest[0]["src"] or "work" in wlongest[0]["src"]
                or "strain" in wlongest[0]["src"])
           and ("sleep" in wlongest[-1]["dst"] or "productivity" in wlongest[-1]["dst"]
                or "energy" in wlongest[-1]["dst"]))
        # EVERY hop in the chain is between two TYPED entities (not bare strings).
        ok("WORLD CHAIN: every node in the through-line is a TYPED entity in the model",
           bool(wlongest)
           and all(_norm_node(h["src"]) in ents and _norm_node(h["dst"]) in ents for h in wlongest))
        # EVERY causal link carries its provenance (the captured fact it rests on).
        ok("WORLD CHAIN: every causal link carries at least one concrete provenance fact",
           all(len(c.get("evidence", [])) >= 1 for c in wlinks))
        ok("WORLD CHAIN: every causal link carries a captured grounding source",
           all(any(s in (SRC_WORLD_EDGE, SRC_REALITY_HYP) for s in c.get("sources", []))
               for c in wlinks))
        # the manager_change link is grounded in a reality hypothesis specifically.
        ok("WORLD CHAIN: the manager_change link is grounded in a reality competing hypothesis",
           bool(e_mgr) and SRC_REALITY_HYP in e_mgr.get("sources", []))

        # --- RETRIEVAL: facts-become-meaning is retrievable --------------------------------------
        ok("WORLD RETRIEVE: get_entity returns a typed entity by key",
           (get_entity(world, "manager_change") or {}).get("type") == ENT_PERSON)
        ok("WORLD RETRIEVE: entities_of_type lists entities of a kind",
           len(entities_of_type(world, ENT_STATE)) >= 1)
        ok("WORLD RETRIEVE: relations_of returns the edges touching an entity",
           len(relations_of(world, "strain")) >= 1)

        # --- THE NEGATIVE PROOF — an EMPTY creature yields an EMPTY world model (never invent) ----
        empty_name = "wm_world_empty_" + secrets.token_hex(3)
        empty_world = build_world_model(empty_name, persist=False)
        ok("WORLD UNGROUNDED: a creature with no captured facts yields ZERO entities + ZERO links",
           len(empty_world.get("entities", [])) == 0
           and len(empty_world.get("causal_links", [])) == 0)
        # the classifier never over-types: a bare unknown node stays TOPIC/STATE, never a PERSON.
        ok("WORLD UNGROUNDED: an unknown bare node is under-typed (TOPIC/STATE), never a PERSON",
           _classify_entity("zorblax") == ENT_TOPIC
           and _classify_entity("xyzzy") == ENT_TOPIC)

        # --- explain_world_model: readable, INTERNAL, clean-gated --------------------------------
        wblock = explain_world_model(wm=world)
        wbody = explain_world_body(world)
        ok("WORLD explain: produces a non-empty typed-world rendering", bool(wblock.strip()))
        ok("WORLD explain: names it INTERNAL + shows the entity/relation/cause sections",
           "INTERNAL, TYPED map" in wblock and "[NODE]" in wblock
           and "[CAUSE]" in wblock and "[CHAIN]" in wblock)
        ok("WORLD NO-DIAGNOSIS GATE: not one GENERATED body line trips a banned term",
           all(_is_clean(ln) for ln in wbody.splitlines()))
        ok("WORLD NO-DIAGNOSIS: the header that NAMES 'diagnosis' to forbid it is fixed framing",
           not _is_clean(_WORLD_EXPLAIN_HEADER) and "diagnosis" in wblock.lower())
        ok("WORLD INTERNAL-ONLY: the explanation forbids asserting the world model at the user",
           "never to be stated at" in wblock and "never a claim to assert" in wblock)

        # --- persistence: the world model round-trips, additively --------------------------------
        wloaded = get_world_model(wname, world.get("id", ""))
        ok("WORLD persist: the built world model round-trips through its own store",
           wloaded is not None and wloaded.get("id") == world.get("id")
           and len(wloaded.get("entities", [])) == len(world.get("entities", [])))
        ok("WORLD additive: the world model wrote ONLY its own .worldmodel_world.json store",
           world_store_path(wname).exists())

        # --- render_world(name): the audit surface lists the world model + grounding --------------
        wrep = render_world(wname)
        ok("WORLD render: audits the stored world model with entities + grounding",
           "coherent world model" in wrep and "entities=" in wrep and "grounded_by" in wrep)
        ok("WORLD NO-DIAGNOSIS GATE: render_world emits no banned term either",
           all(_is_clean(ln) for ln in wrep.splitlines()))

        # --- ROBUSTNESS: garbage inputs to the world surface never raise -------------------------
        try:
            build_world_model("", persist=False)
            build_world_model(None, persist=False)
            get_entity(None, "x")
            get_entity({}, None)
            entities_of_type(None, ENT_PERSON)
            relations_of({"entities": None}, "x")
            world_causal_chains({})
            explain_world_model(wm={"entities": []})
            explain_world_model(name="nobody", model_id="x")
            _classify_entity(None)
            _classify_entity("")
            wcrashed = False
        except Exception as e:  # noqa: BLE001
            wcrashed = True
            print("       (world raised:", repr(e), ")")
        ok("WORLD robust: garbage/None inputs are handled without raising", not wcrashed)

    finally:
        for fp in glob.glob(str(_tp / "wm_*")) + glob.glob(str(_tp / "*")):
            try:
                os.remove(fp)
            except OSError:
                pass
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        try:
            import shutil
            shutil.rmtree(_td, ignore_errors=True)
        except Exception:
            pass

    # the hermetic guardrail: the real .anima must be byte-UNCHANGED around the whole run.
    fp_after = _hash_anima(real)
    ok("HERMETIC: real .anima byte-UNCHANGED around the selftest (no real Vera.* touched)",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic world-model store leaked into real .anima",
       (not real.is_dir()) or not any(real.glob("wm_*")))
    # the coherent-world store (.worldmodel_world.json) must not have leaked either.
    ok("HERMETIC: no synthetic coherent-world store leaked into real .anima",
       (not real.is_dir()) or not any(real.glob("wm_world_*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL WORLD_MODEL SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
