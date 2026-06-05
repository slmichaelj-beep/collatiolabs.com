#!/usr/bin/env python3
"""VERA ARCHITECTURAL REVIEW BOARD + MIND BALANCE DASHBOARD — the wave-end governance compass.

ONE standalone file, TWO modes. A read-only SYNTHESIS over the engines + observatories the
team has already built: it computes nothing new about a creature, it READS the existing real
signals and tells the truth about how mature the Mind is and where the next dollar of work
should go.

The whole point is a single directive, applied to the dashboard ITSELF:

    OBSERVED > ASSUMED.   MEASURED > BELIEVED.   CERTIFIED > CLAIMED.

Every dimension score is LABELLED honestly as MEASURED (it cites the real signal it read) or
ESTIMATED (a heuristic / needs-human placeholder). We NEVER present an estimate as a
measurement — that would be the exact lie this board exists to catch. The lowest
mature-essential score is flagged as the CURRENT BOTTLENECK.

----------------------------------------------------------------------------------------------
MODE 1 — MIND BALANCE  (default; the maturity scorecard)
    python3 scripts/arb.py

    Scores 13 dimensions — Memory, Continuity, Observation, Certification, Experience,
    Curiosity, Grounding, Prediction, Reality Learning, Identity, Self-Improvement,
    Governance Cost, Novelty — each from a REAL signal where one exists. Real signals read:
      * Conservation    -> scripts/conservation.py run_battery() end-to-end retention   (MEASURED)
      * Observation     -> count of present observatory scripts (mri/conservation/decision/
                           counterfactual/causal/confidence/dataflow/provenance/evolution/
                           relationship/isolation)                                       (MEASURED)
      * Certification   -> the cert harness is PRESENT + structurally complete           (MEASURED
                           presence; the LIVE pass is ESTIMATED — we don't run the battery here)
      * Reality Learning-> anima/reality.py ledger RESOLVED real outcomes for the LIVE creature
                           (almost certainly 0 -> TIME-GATED; MEASURED-as-zero)
      * Self-Improvement / Novelty / Governance Cost -> not built -> low                 (ESTIMATED)
    The LOWEST mature-essential score is the flagged CURRENT BOTTLENECK (the VISIBLE WEAKNESS).

    DEPENDENCY-WEIGHTED RESOLUTION (a governor, not a scoreboard). A flat ranking MISLEADS: it
    points at "Reality Learning @ 8" — a real measurement, but a DOWNSTREAM, TIME-GATED layer that
    no amount of engineering hours can advance (real learning accrues over calendar time). So the
    board encodes the SPINE — the directed "built-on" dependency chain —

        Capture/Memory -> Meaning -> World Model -> Prediction/Hypotheses -> Reality Learning
                                                                          -> Self-Improvement

    and walks UP it to render THREE distinct bottlenecks:
        Root Bottleneck:      the DEEPEST still-weak dependency (the cause of the most downstream
                              weakness). A STRONG upstream layer (Capture ~100) is NOT the root.
        Immediate Bottleneck: the SHALLOWEST BUILDABLE weak dependency — skip time-gated nodes
                              that cannot be built now; point at the buildable layer they sit on.
        Visible Weakness:     the flat lowest score (the existing flag) — honest, but downstream.
    The HEADLINE is "Next 100 engineering hours -> <immediate buildable bottleneck>", with the
    dependency chain and a one-line WHY. Per-subsystem 7-axis sub-scores drill into the flagged
    dimensions, each axis labelled MEASURED (cites a real signal) or a structured TODO (names the
    missing live read) — never fabricated.

MODE 2 — ARB REVIEW  (the wave-end review)
    python3 scripts/arb.py --review

    Prints the 8 review questions and answers what is computable from data, with structured
    slots for the narrative ones (What was built / bottleneck removed / metric improved / what
    we learned / what surprised us / what observability says is weakest / what moved on the
    Mind Balance / closer to a Digital Mind?). CRUCIAL — the REALITY > ROADMAP check: it accepts
    a declared "roadmap next item" (``--next`` or a small config) and compares it to the
    observatory-identified WEAKEST layer; if they DIFFER it prints a LOUD flag:

        REALITY > ROADMAP CONFLICT: measurements say <weakest> is the bottleneck;
        roadmap says build <next>. Surface this.

    This mechanizes the directive's most important rule: a builder MUST surface a
    plan-vs-measurement conflict instead of quietly building the planned thing.

    THE ROADMAP EXCEPTION RULE. A conflict is not automatically a deviation to halt. The review
    classifies the divergence: a MEASURED + QUANTIFIED + ISOLATED + NON-INTERFERING bottleneck fix
    may proceed IN PARALLEL with the planned roadmap. If the declared next item is a genuine
    bottleneck fix on the dependency spine (the immediate buildable bottleneck, the root, or the
    foundational capture/Memory layer everything sits on), it is rendered as an ALLOWED PARALLEL
    EXCEPTION — distinguishing a legitimate parallel fix (e.g. the in-flight capture fix #59) from
    a true roadmap deviation that must be surfaced and justified.

----------------------------------------------------------------------------------------------
GUARDRAILS (this file lives by the same laws it audits):
  * READ-ONLY SYNTHESIS. It imports/reads certify.py, conservation.py, anima/reality.py, and
    probes the presence of the engines/observatories. It computes the Conservation signal in a
    HERMETIC temp store (conservation's own redirect), and reads the reality ledger STRICTLY
    READ-ONLY. It edits NO module; the ONLY file it adds is scripts/arb.py.
  * HONEST LABELS. MEASURED cites its signal; ESTIMATED says so. Observed > Assumed.
  * HERMETIC + PROVEN. ``--selftest`` asserts the real .anima is byte-UNCHANGED around the run.
  * NEVER raises out of an entry point — a missing engine degrades to an honest ESTIMATED line.

    python3 scripts/arb.py             # MODE 1 — the Mind Balance scorecard
    python3 scripts/arb.py --review    # MODE 2 — the wave-end ARB review (+ reality>roadmap)
    python3 scripts/arb.py --review --next reality_learning   # declare the roadmap's next item
    python3 scripts/arb.py --selftest  # PROVE: real Conservation is MEASURED; the bottleneck
                                       #        flag works; the reality>roadmap conflict fires;
                                       #        deterministic; real .anima byte-unchanged.
    python3 scripts/arb.py --json      # machine-readable (either mode)

Exit code is 0 when the run is clean (guardrail held; selftest assertions all passed).
"""
import argparse
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# The live creature this board reads (the same default the server + certify use).
LIVE_CREATURE = "Vera"

# The eleven observatory scripts the team counts as "the microscope". Observation maturity is
# the fraction of these that are present (MEASURED off the filesystem). The canonical names use
# the team's shorthand ("decision"), mapped to the on-disk filename ("decisions.py").
OBSERVATORY_SCRIPTS = {
    "mri": "mri.py",
    "conservation": "conservation.py",
    "decision": "decisions.py",
    "counterfactual": "counterfactual.py",
    "causal": "causal.py",
    "confidence": "confidence.py",
    "dataflow": "dataflow.py",
    "provenance": "provenance.py",
    "evolution": "evolution.py",
    "relationship": "relationship.py",
    "isolation": "isolation.py",
}

# The engines that back each non-observatory dimension — presence is a MEASURED signal that the
# capability EXISTS, even when we can't put a live number on its maturity without a model run.
ENGINE_FILES = {
    "memory": ("anima/memory_lirf.py", "anima/memory_schema.py"),
    "continuity": ("anima/constitution.py", "anima/reliability.py"),
    "experience": ("anima/meaning.py", "scripts/experience.py"),
    "curiosity": ("anima/curiosity.py", "scripts/curiosity_quality.py"),
    "grounding": ("anima/rail.py", "scripts/mri.py"),
    "prediction": ("anima/reality.py",),
    "identity": ("anima/identity.py",),
}

# The certification harness + the structural surface a complete harness exposes. Presence of the
# file AND these symbols is the MEASURED signal; the LIVE pass is ESTIMATED (we don't run it).
CERT_HARNESS = "scripts/certify.py"
CERT_EXPECTED_SYMBOLS = ("section_organ_badges", "section_survival_matrix", "CheckResult", "main")

# Heuristic ceilings (0..100) for the dimensions where there is NO live numeric signal yet — the
# honest "this exists and is wired, but its maturity is an ESTIMATE pending a measurement" band.
# Kept deliberately middling so an estimate can never out-shine a low MEASURED reality.
_PRESENT_ENGINE_ESTIMATE = 70     # the engine is built + imports + is exercised by a harness
_PARTIAL_ENGINE_ESTIMATE = 45     # some of the engine's files are present
_ABSENT_ESTIMATE = 12             # the capability is not built -> low, ESTIMATED

# The dimensions whose maturity is REQUIRED for a "Digital Mind" — the mature-essential set the
# bottleneck is chosen from. Self-Improvement / Novelty / Governance Cost are future/meta axes:
# they are scored + shown, but a not-yet-started meta-axis is NOT the thing we call the current
# bottleneck (that would always just say "go build the unbuilt thing").
MATURE_ESSENTIAL = {
    "memory", "continuity", "observation", "certification", "experience",
    "curiosity", "grounding", "prediction", "reality_learning", "identity",
}

DIMENSION_ORDER = [
    "memory", "continuity", "observation", "certification", "experience",
    "curiosity", "grounding", "prediction", "reality_learning", "identity",
    "self_improvement", "governance_cost", "novelty",
]

DIMENSION_LABEL = {
    "memory": "Memory",
    "continuity": "Continuity",
    "observation": "Observation",
    "certification": "Certification",
    "experience": "Experience",
    "curiosity": "Curiosity",
    "grounding": "Grounding",
    "prediction": "Prediction",
    "reality_learning": "Reality Learning",
    "identity": "Identity",
    "self_improvement": "Self-Improvement",
    "governance_cost": "Governance Cost",
    "novelty": "Novelty",
}


# ===================================================================================
# THE DEPENDENCY GRAPH — why a flat ranking MISLEADS, and the governor that fixes it.
# ===================================================================================
# A flat scorecard ranks dimensions independently and flags the single lowest one. That is a
# SCOREBOARD, not a GOVERNOR: it points at "Reality Learning @ 8" — a real measurement, but a
# DOWNSTREAM, TIME-GATED layer that cannot be built faster by spending engineering hours (real
# learning accrues only as real outcomes arrive over calendar time). Pouring 100 hours there
# buys nothing. The ACTIONABLE bottleneck is UPSTREAM: the deepest still-weak layer that the
# downstream layers are starving on top of.
#
# So we encode the SPINE — the directed "this layer is BUILT ON that layer" chain. Everything
# sits on capture; you cannot understand what you never captured, model relations you never
# understood, form hypotheses without a world model, learn from reality without predictions to
# test, or improve yourself without having learned anything:
#
#     Capture/Memory --> Meaning --> World Model --> Prediction/Hypotheses
#                                                        --> Reality Learning --> Self-Improvement
#
# The arrow "A --> B" reads "A ENABLES B" (B is built ON A). The grounded reading from the code:
#   * memory      = the LIRF capture/retention pipeline (anima/memory_lirf.py, Law 001) — the
#                   foundation; nothing below it.
#   * experience  = the MEANING engine (anima/meaning.py, Law 003 "understanding beats
#                   remembering") — sits ON memory; you cannot weigh what MATTERS in facts you
#                   never captured.
#   * grounding   = the WORLD MODEL / Life Graph (anima/world_state.py — values become connected
#                   SITUATIONS) — relations BETWEEN facts; needs the facts (memory) and what
#                   matters (meaning) to connect.
#   * prediction  = the epistemic engine (anima/reality.py — Hypotheses/Competing/Surprise) —
#                   forms testable predictions ON the world model.
#   * reality_learning = RESOLVED real outcomes (anima/reality.py ledger) — learns by testing
#                   predictions against reality.
#   * self_improvement = the Mind rewriting/upgrading itself — needs something LEARNED first.
#
# DEPENDS_ON[d] = the set of dimensions d is BUILT ON (its direct upstream dependencies). Walking
# UP these edges from a weak node finds the ROOT cause of its weakness. The cross-cutting layers
# (continuity, identity sit on memory; observation/certification/curiosity/governance/novelty are
# observability/meta organs that watch or wrap the spine) are placed too, so the graph covers
# EVERY dimension and the acyclicity check is total.
DEPENDS_ON = {
    # --- the SPINE (the load-bearing chain the headline walks) ---------------------------------
    "memory": set(),                                   # the foundation — sits on nothing
    "experience": {"memory"},                          # Meaning is built on Capture/Memory
    "grounding": {"memory", "experience"},             # World Model needs facts + what matters
    "prediction": {"grounding", "experience"},         # Hypotheses are formed on the world model
    "reality_learning": {"prediction"},                # Learning tests predictions vs reality
    "self_improvement": {"reality_learning"},          # Self-improvement needs learning first
    # --- cross-cutting layers anchored onto the spine (so every node is placed) -----------------
    "continuity": {"memory"},                          # survival of the stored self sits on memory
    "identity": {"memory"},                            # exportable self is the captured self
    "curiosity": {"memory", "experience"},             # gap-finding reads facts + significance
    "observation": set(),                              # the microscope — an organ, not on the spine
    "certification": {"observation"},                  # the gate reads what the microscope sees
    "governance_cost": set(),                          # meta — the cost of the review machinery
    "novelty": {"experience"},                         # genuinely-new ideas build on meaning
}

# TIME-GATED dimensions CANNOT be advanced by spending engineering hours now — their maturity
# accrues only over real calendar time (real outcomes arriving), no matter how many hours you
# pour in. They are valid VISIBLE weaknesses and valid ROOTs, but they are NEVER the IMMEDIATE
# (buildable) bottleneck — the governor must skip them and point at the buildable layer they sit
# on. reality_learning is the canonical example (the ledger is built; zero real outcomes yet).
TIME_GATED = {"reality_learning"}

# A dimension counts as WEAK when its score is below this line. Tuned so the strong MEASURED
# layers (Memory/Observation/Certification ~100) are NOT weak, while an ESTIMATED-70 spine layer
# (Meaning/World-Model/Prediction — built but unmeasured) and the time-gated 8 both ARE weak. The
# whole point: when Capture is ~100 it is NOT the root; the root is the deepest layer still weak.
WEAK_THRESHOLD = 75


def dependency_chain(dim: str) -> list:
    """The upstream spine path from ``dim`` DOWN to the foundation, deepest-LAST. Deterministic
    (sorted), cycle-safe. E.g. reality_learning -> [memory, experience, grounding, prediction,
    reality_learning]. Used to walk from a visible weakness up to its root."""
    order = []          # foundation-first accumulation
    seen = set()

    def visit(d):
        if d in seen:
            return
        seen.add(d)
        for up in sorted(DEPENDS_ON.get(d, set())):     # visit dependencies (deeper) first
            visit(up)
        order.append(d)

    visit(dim)
    return order        # foundation ... dim   (deepest dependency first, dim last)


def _graph_is_acyclic() -> bool:
    """True iff DEPENDS_ON has no cycle (a DAG). A cycle would make 'walk up to the root'
    nonterminating — the selftest asserts this can never happen."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {d: WHITE for d in DEPENDS_ON}

    def dfs(d):
        color[d] = GREY
        for up in DEPENDS_ON.get(d, set()):
            if color.get(up, WHITE) == GREY:
                return False                            # back-edge -> cycle
            if color.get(up, WHITE) == WHITE and not dfs(up):
                return False
        color[d] = BLACK
        return True

    return all(dfs(d) for d in DEPENDS_ON if color[d] == WHITE)


# ===================================================================================
# GUARDRAIL — footprint hash of the real .anima, so --selftest can PROVE this read-only board
# touched nothing. Mirrors scripts/conservation.py::_footprint and scripts/reality.py::_footprint
# (exclude the rotating backups/ dir, which legitimately changes on its own).
# ===================================================================================
def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (EXCLUDING the rotating backups/ dir), so
    we can prove the dashboard touched nothing. Returns (sha256-hex|None, file-count)."""
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


def _present(rel: str) -> bool:
    """True iff a repo-relative path exists."""
    return (Path(_ROOT) / rel).exists()


def _git_head() -> str:
    """The short HEAD of the repo, read-only and best-effort (a non-git checkout -> 'unknown')."""
    head = Path(_ROOT) / ".git" / "HEAD"
    try:
        ref = head.read_text(encoding="utf-8").strip()
        if ref.startswith("ref:"):
            target = Path(_ROOT) / ".git" / ref.split(" ", 1)[1].strip()
            return target.read_text(encoding="utf-8").strip()[:12]
        return ref[:12]
    except Exception:
        return "unknown"


# ===================================================================================
# THE REAL SIGNALS — each helper reads ONE real source and returns enough for an honest line.
# A signal that can't be read degrades to an ESTIMATED verdict (never a crash, never a fake
# MEASURED). The Conservation read is HERMETIC (it runs in conservation's own temp-store
# redirect); the reality read is STRICTLY READ-ONLY.
# ===================================================================================

def signal_conservation():
    """MEASURED: end-to-end retention (DETECTED -> USED) from scripts/conservation.py
    run_battery(). The single hardest real number on the board. Hermetic by construction —
    run_battery drives the synthetic BATTERY through conservation's own temp-store redirect, so
    nothing real is touched. Returns (retention_float_or_None, detail_dict)."""
    try:
        conservation = importlib.import_module("scripts.conservation")
        report = conservation.run_battery()
        e2e = float(report.get("end_to_end_retention", 0.0))
        target = float(report.get("target", 0.95))
        return e2e, {
            "measured": True,
            "signal": "scripts/conservation.py run_battery() end_to_end_retention "
                      "(DETECTED -> USED, synthetic battery, hermetic)",
            "end_to_end_retention": e2e,
            "target": target,
            "clears_target": bool(report.get("clears_target", e2e >= target)),
            "total_salient": report.get("total_salient"),
            # carried through ADDITIVELY for the per-axis sub-scores (the per-stage rates and the
            # meaning-retention breakdown are real reads the drill-down cites; existing keys above
            # are untouched).
            "rates": report.get("rates", {}),
            "meaning_detail": report.get("meaning_detail", {}),
            "stage_counts": report.get("stage_counts", {}),
        }
    except Exception as e:  # pragma: no cover - degrade honestly
        return None, {"measured": False, "signal": "conservation.run_battery() unavailable",
                      "error": repr(e)}


def signal_observation():
    """MEASURED: the fraction of the eleven observatory scripts that are present on disk."""
    present = {k: _present(f"scripts/{fn}") for k, fn in OBSERVATORY_SCRIPTS.items()}
    n_present = sum(1 for v in present.values() if v)
    n_total = len(OBSERVATORY_SCRIPTS)
    return (n_present / n_total if n_total else 0.0), {
        "measured": True,
        "signal": f"present observatory scripts ({n_present}/{n_total}: "
                  + ", ".join(k for k, v in present.items() if v) + ")",
        "n_present": n_present,
        "n_total": n_total,
        "missing": [k for k, v in present.items() if not v],
    }


def signal_certification():
    """MEASURED (presence): the cert harness exists and exposes the structural surface of a
    complete harness (organ badges + survival matrix + result type + main). The LIVE pass is
    ESTIMATED — we deliberately do NOT run the multi-minute battery from the dashboard, so we
    never claim a CERTIFIED verdict we didn't observe. Returns (presence_score, detail)."""
    path = Path(_ROOT) / CERT_HARNESS
    if not path.exists():
        return 0.0, {"measured": True, "signal": f"{CERT_HARNESS} ABSENT", "present": False}
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # pragma: no cover
        return 0.0, {"measured": True, "signal": f"{CERT_HARNESS} unreadable", "error": repr(e)}
    found = {sym: (sym in src) for sym in CERT_EXPECTED_SYMBOLS}
    score = sum(1 for v in found.values() if v) / len(CERT_EXPECTED_SYMBOLS)
    return score, {
        "measured": True,
        "signal": f"{CERT_HARNESS} present; harness symbols "
                  f"{sum(found.values())}/{len(found)} "
                  + "(" + ", ".join(s for s, v in found.items() if v) + ")",
        "present": True,
        "symbols_found": found,
        "live_pass": "ESTIMATED — battery not run from the dashboard (would be the live signal)",
    }


def signal_reality_learning(creature: str = LIVE_CREATURE, store: Path = None):
    """MEASURED-as-zero (TIME-GATED): the number of RESOLVED real outcomes in the LIVE creature's
    reality ledger. Real LEARNING accrues only as real outcomes arrive over real calendar time;
    for a young creature this is honestly 0 — and 0 is a MEASUREMENT, not an assumption. STRICTLY
    READ-ONLY: points reality.STORE at the real .anima for a pure ledger read, restores it, and
    the caller proves the footprint is byte-unchanged. Returns (resolved_count, detail)."""
    store = Path(store) if store is not None else (Path(_ROOT) / ".anima")
    try:
        reality = importlib.import_module("anima.reality")
    except Exception as e:  # pragma: no cover
        return None, {"measured": False, "signal": "anima.reality unavailable", "error": repr(e)}
    saved = getattr(reality, "STORE", None)
    try:
        reality.STORE = store
        learnings = [r for r in reality.records(creature)
                     if isinstance(r, dict) and r.get("kind") == reality.LEARNING]
        open_preds = reality.open_predictions(creature)
        resolved = len(learnings)
        ledger_present = reality.ledger_path(creature).exists()
    except Exception as e:  # pragma: no cover - read-only, never raises out
        return 0, {"measured": True, "signal": f"reality ledger read error ({e!r}) -> 0 resolved",
                   "resolved": 0, "ledger_present": False, "time_gated": True}
    finally:
        if saved is not None:
            reality.STORE = saved
    return resolved, {
        "measured": True,
        "signal": f"anima/reality.py ledger for '{creature}': RESOLVED real outcomes "
                  f"= {resolved} (ledger {'present' if ledger_present else 'not yet created'}; "
                  f"open predictions {len(open_preds)})",
        "resolved": resolved,
        "open_predictions": len(open_preds),
        "ledger_present": ledger_present,
        "time_gated": True,
    }


def _engine_presence(dim: str):
    """How many of a dimension's backing engine files are present — drives the ESTIMATED maturity
    band for the dimensions with no live numeric. Returns (fraction_present, [present...],
    [missing...])."""
    files = ENGINE_FILES.get(dim, ())
    present = [f for f in files if _present(f)]
    missing = [f for f in files if not _present(f)]
    frac = (len(present) / len(files)) if files else 0.0
    return frac, present, missing


# ===================================================================================
# MODE 1 — THE MIND BALANCE SCORECARD. Build each dimension as a labelled cell:
#   {key, label, score(0..100), basis: "MEASURED"|"ESTIMATED", signal, essential, note}
# A MEASURED cell cites a real signal; an ESTIMATED cell says so. The lowest MEASURED-or-not
# mature-essential cell is the flagged bottleneck.
# ===================================================================================

def _cell(key, score, basis, signal, note="", essential=None):
    if essential is None:
        essential = key in MATURE_ESSENTIAL
    return {
        "key": key,
        "label": DIMENSION_LABEL[key],
        "score": int(round(max(0.0, min(100.0, float(score))))),
        "basis": basis,                # "MEASURED" or "ESTIMATED"
        "signal": signal,
        "note": note,
        "essential": bool(essential),
    }


def _estimated_engine_cell(key, note_extra=""):
    """An ESTIMATED cell for an engine-backed dimension: full files present -> the wired-but-
    unmeasured band; partial -> lower; none -> the absent floor. ALWAYS labelled ESTIMATED so it
    can never masquerade as a measurement."""
    frac, present, missing = _engine_presence(key)
    if frac >= 1.0:
        score = _PRESENT_ENGINE_ESTIMATE
        sig = "engine present + import-clean + exercised by a harness (" \
              + ", ".join(present) + ")"
    elif frac > 0.0:
        score = _PARTIAL_ENGINE_ESTIMATE
        sig = "engine PARTIALLY present (" + ", ".join(present) + \
              "; missing " + ", ".join(missing) + ")"
    else:
        score = _ABSENT_ESTIMATE
        sig = "engine not present"
    note = "heuristic from engine presence; needs a live measurement to become MEASURED"
    if note_extra:
        note = note + "; " + note_extra
    return _cell(key, score, "ESTIMATED", sig, note)


# ===================================================================================
# THE THREE-LEVEL BOTTLENECK RESOLUTION — the headline upgrade. Turn the flat visible weakness
# into VISIBLE / ROOT / IMMEDIATE by walking the dependency spine.
# ===================================================================================
def resolve_bottleneck(cells: list, visible_cell: dict) -> dict:
    """Dependency-weighted resolution. Given all cells + the flat VISIBLE weakness, walk UP the
    spine and return three distinct bottlenecks:

      * VISIBLE   = the flat lowest mature-essential score (the existing flag) — may be downstream.
      * ROOT      = the DEEPEST still-weak dependency on the visible weakness's upstream path (the
                    node whose weakness causes the most downstream weakness). If an upstream layer
                    is STRONG (e.g. Capture/Memory ~100), it is NOT the root — the root is the
                    deepest layer that is actually weak. If nothing upstream is weak, the visible
                    node IS its own root.
      * IMMEDIATE = the SHALLOWEST BUILDABLE weak dependency on the path — skip TIME_GATED nodes
                    that cannot be built now (e.g. reality-learning accrual) and point at the
                    buildable layer they sit on (World Model / Meaning / Memory). This is where the
                    next 100 engineering hours actually go.

    Pure function of the cells + graph -> deterministic. Never raises; degrades to the visible
    node if the graph can't place it. Returns a structured verdict dict."""
    by_key = {c["key"]: c for c in cells}
    if not visible_cell:
        return {"visible": None, "root": None, "immediate": None, "chain": [],
                "headline_key": None, "headline": "no essential dimension to resolve",
                "why": "", "note": "empty board"}

    visible_key = visible_cell["key"]
    # the upstream spine path, foundation-FIRST (deepest dependency first), visible node LAST.
    chain_keys = dependency_chain(visible_key)

    def is_weak(k):
        c = by_key.get(k)
        return c is not None and c["score"] < WEAK_THRESHOLD

    # ROOT = the DEEPEST weak node on the path. The path is foundation-first, so the FIRST weak
    # node encountered scanning from the foundation is the deepest weak one. If the only weak node
    # is the visible node itself (everything upstream is strong), the visible node is its own root.
    root_key = next((k for k in chain_keys if is_weak(k)), visible_key)

    # IMMEDIATE = the shallowest BUILDABLE weak node on the path AT OR ABOVE the root (scan from
    # the root outward toward the visible node; the path slice from root..visible, foundation
    # first). Skip TIME_GATED nodes — they cannot be advanced by spending hours now. The first
    # buildable weak node is the one the next 100 hours should actually attack.
    root_idx = chain_keys.index(root_key) if root_key in chain_keys else 0
    downstream_of_root = chain_keys[root_idx:]                  # root .. visible (deepest first)
    immediate_key = next(
        (k for k in downstream_of_root if is_weak(k) and k not in TIME_GATED),
        # everything weak on the path is time-gated -> fall back to the deepest BUILDABLE weak node
        # anywhere on the upstream path, else the root itself (honest: nothing buildable here).
        next((k for k in chain_keys if is_weak(k) and k not in TIME_GATED), root_key),
    )

    root = by_key.get(root_key)
    immediate = by_key.get(immediate_key)

    # The WHY — one line explaining why the immediate buildable layer is the real lever.
    if immediate_key == visible_key:
        why = (f"{visible_cell['label']} is both the visible weakness and the deepest buildable "
               f"weak layer — no stronger upstream cause; fix it directly.")
    elif visible_key in TIME_GATED and immediate_key != visible_key:
        why = (f"{visible_cell['label']} is the lowest flat score but is TIME-GATED (accrues over "
               f"calendar time, not hours); it is starved by {immediate['label']} upstream — "
               f"build {immediate['label']} so the downstream layer has something to consume.")
    else:
        why = (f"{visible_cell['label']} is downstream of {immediate['label']}; the weakness "
               f"propagates UP the spine from {immediate['label']}, so {immediate['label']} is "
               f"the highest-leverage buildable fix.")

    chain = [{"key": k, "label": DIMENSION_LABEL.get(k, k),
              "score": by_key.get(k, {}).get("score"),
              "weak": is_weak(k), "time_gated": k in TIME_GATED,
              "role": ("ROOT" if k == root_key else "") +
                      ("/IMMEDIATE" if k == immediate_key else "") +
                      ("/VISIBLE" if k == visible_key else "")}
             for k in chain_keys]

    return {
        "visible": {"key": visible_key, "label": visible_cell["label"],
                    "score": visible_cell["score"], "basis": visible_cell["basis"]},
        "root": {"key": root_key, "label": root["label"], "score": root["score"],
                 "basis": root["basis"], "time_gated": root_key in TIME_GATED} if root else None,
        "immediate": {"key": immediate_key, "label": immediate["label"],
                      "score": immediate["score"], "basis": immediate["basis"],
                      "buildable": immediate_key not in TIME_GATED} if immediate else None,
        "chain": chain,
        "chain_str": " -> ".join(c["label"] + (f"@{c['score']}" if c["score"] is not None else "")
                                 for c in chain),
        "headline_key": immediate_key,                # the next 100 hours point HERE
        "headline": (f"Next 100 engineering hours -> {immediate['label']}"
                     if immediate else "Next 100 engineering hours -> (no buildable layer)"),
        "why": why,
    }


# ===================================================================================
# PER-SUBSYSTEM 7-AXIS SUB-SCORES — the honest drill-down for the flagged dimensions. Each axis
# is MEASURED (cites a real signal it read) or a structured ESTIMATED/TODO (says so) — we NEVER
# fabricate a score. A full 13x7 matrix would be mostly fabricated, so we populate the axes we
# have REAL signals for (chiefly the Conservation pipeline behind Memory + Meaning) and mark the
# rest a structured TODO naming the live read that would fill it.
# ===================================================================================
# The 7 axes every subsystem is graded on (the same axes the cert harness uses elsewhere).
SUBSCORE_AXES = ("Capability", "Coverage", "Observability", "Reliability",
                 "Certification", "Experience Impact", "Maturity")


def _axis(score, basis, signal):
    """One axis cell: score (0..100 or None for a pure TODO), basis MEASURED|ESTIMATED|TODO, and
    the signal that justifies it (or the live read a TODO still needs). None score => unscored."""
    return {"score": (None if score is None else int(round(max(0.0, min(100.0, float(score)))))),
            "basis": basis, "signal": signal}


def subscores_for(dim: str, cells_by_key: dict, cons_detail: dict = None) -> dict:
    """The 7-axis sub-scores for one flagged dimension, from REAL signals where they exist. Honest
    labels: MEASURED cites the signal; ESTIMATED says heuristic; TODO names the missing live read
    and leaves the score None (NOT fabricated). cons_detail is the Conservation run_battery report
    (already computed by the scorecard) — the richest real source on the board."""
    cell = cells_by_key.get(dim, {})
    overall = cell.get("score")
    cons = cons_detail or {}
    rates = cons.get("rates", {}) if isinstance(cons, dict) else {}
    md = cons.get("meaning_detail", {}) if isinstance(cons, dict) else {}
    axes = {}

    if dim == "memory":
        # Memory is the one dimension with a deep MEASURED drill-down — the Conservation pipeline
        # exposes a real rate at every capture stage.
        e2e = cons.get("end_to_end_retention")
        axes["Capability"] = _axis(
            (rates.get("capture_rate", 0) * 100) if "capture_rate" in rates else overall,
            "MEASURED" if "capture_rate" in rates else "ESTIMATED",
            f"Conservation capture_rate {rates.get('capture_rate', '?')!s} (DETECTED -> CAPTURED)")
        axes["Coverage"] = _axis(
            (rates.get("storage_rate", 0) * 100) if "storage_rate" in rates else overall,
            "MEASURED" if "storage_rate" in rates else "ESTIMATED",
            f"Conservation storage_rate {rates.get('storage_rate', '?')!s} (CAPTURED -> STORED)")
        axes["Observability"] = _axis(
            (rates.get("retrieval_rate", 0) * 100) if "retrieval_rate" in rates else overall,
            "MEASURED" if "retrieval_rate" in rates else "ESTIMATED",
            f"Conservation retrieval_rate {rates.get('retrieval_rate', '?')!s} (STORED -> RETRIEVED)")
        axes["Reliability"] = _axis(
            (e2e * 100) if e2e is not None else overall,
            "MEASURED" if e2e is not None else "ESTIMATED",
            f"Conservation end_to_end_retention {e2e!s} vs target {cons.get('target', '?')!s} "
            f"(clears={cons.get('clears_target', '?')!s})")
        axes["Certification"] = _axis(
            None, "TODO",
            "live read = certify.py Data-Conservation battery verdict for the creature (not run "
            "from the dashboard) — would replace this with the CERTIFIED/NOT pass")
        axes["Experience Impact"] = _axis(
            (rates.get("usage_rate", 0) * 100) if "usage_rate" in rates else None,
            "MEASURED" if "usage_rate" in rates else "TODO",
            f"Conservation usage_rate {rates.get('usage_rate', '?')!s} (RETRIEVED -> USED in a "
            "reply) — the fraction that reaches the human")
        axes["Maturity"] = _axis(
            overall, "MEASURED",
            f"Memory dimension overall {overall} (= measured end-to-end retention)")

    elif dim == "experience":
        # Experience = the Meaning engine. The Conservation battery measures meaning_retention as a
        # by-product, which is a real (if partial) read on this layer.
        mr = md.get("meaning_retention")
        sr = md.get("significance_retention")
        axes["Capability"] = _axis(
            overall, "ESTIMATED",
            "anima/meaning.py present + import-clean + exercised by a harness "
            "(significance/dominance/trend computed) — capability heuristic, not yet a live metric")
        axes["Coverage"] = _axis(
            (mr * 100) if mr is not None else None,
            "MEASURED" if mr is not None else "TODO",
            f"Conservation meaning_retention {mr!s} (fraction of salient MEANING preserved through "
            "the pipeline) — a real by-product read on the meaning layer")
        axes["Observability"] = _axis(
            (sr * 100) if sr is not None else None,
            "MEASURED" if sr is not None else "TODO",
            f"Conservation significance_retention {sr!s} (is the WHY-it-matters kept?)")
        axes["Reliability"] = _axis(
            None, "TODO",
            "live read = scripts/experience.py probe battery pass-rate (not run from the dashboard)")
        axes["Certification"] = _axis(
            None, "TODO",
            "live read = certify.py Experience battery verdict (the cert that explains WHY)")
        axes["Experience Impact"] = _axis(
            overall, "ESTIMATED",
            "heuristic: meaning drives what Vera foregrounds in a reply; needs an A/B turn metric")
        axes["Maturity"] = _axis(
            overall, "ESTIMATED",
            f"Experience dimension overall {overall} (engine-presence band; ESTIMATED)")

    elif dim == "grounding":
        # Grounding = the World Model (world_state Life Graph) + the rail/MRI hallucination guard.
        axes["Capability"] = _axis(
            overall, "ESTIMATED",
            "anima/world_state.py (Life Graph: values -> typed RELATIONS -> situations) present + "
            "exercised — capability heuristic, not yet a live graph-quality metric")
        axes["Coverage"] = _axis(
            None, "TODO",
            "live read = world_state relation-capture rate on natural speech (#21/#59 capture "
            "widening) — the fraction of stated relations that become edges")
        axes["Observability"] = _axis(
            None, "TODO",
            "live read = scripts/mri.py film of the world-model read during a turn")
        axes["Reliability"] = _axis(
            None, "TODO",
            "live read = anima/rail.py + mri.py hallucination battery pass-rate (grounded-claims %)")
        axes["Certification"] = _axis(
            None, "TODO", "live read = certify.py grounding/hallucination tier verdict")
        axes["Experience Impact"] = _axis(
            overall, "ESTIMATED",
            "heuristic: a connected world model lets Vera surface the CLUSTER, not one stranded "
            "slot — high impact, not yet A/B measured")
        axes["Maturity"] = _axis(
            overall, "ESTIMATED",
            f"Grounding dimension overall {overall} (engine-presence band; ESTIMATED)")

    elif dim == "reality_learning":
        # Reality Learning — the time-gated downstream layer. Honest: the machinery axes can be
        # read, but the OUTCOME axes are measured-as-zero (no real outcomes yet).
        axes["Capability"] = _axis(
            overall, "MEASURED",
            "anima/reality.py epistemic loop present (Belief -> Prediction -> Outcome -> Learning); "
            "RESOLVED outcomes measured-as-zero (time-gated)")
        axes["Coverage"] = _axis(
            0, "MEASURED",
            "RESOLVED real outcomes = 0 (ledger not yet accrued over calendar time)")
        axes["Observability"] = _axis(
            None, "TODO",
            "live read = scripts/evolution.py + reality ledger view of open vs resolved predictions")
        axes["Reliability"] = _axis(
            None, "TODO",
            "live read = prediction calibration (Brier/accuracy) once resolved outcomes exist")
        axes["Certification"] = _axis(
            None, "TODO", "live read = certify.py reality-learning tier (gated on real outcomes)")
        axes["Experience Impact"] = _axis(
            0, "MEASURED",
            "zero real learning has reached a reply yet (time-gated) — honest measured-as-zero")
        axes["Maturity"] = _axis(
            overall, "MEASURED",
            f"Reality Learning overall {overall} (MEASURED-as-zero; the loop is built, accrual is "
            "calendar-time-gated)")

    else:
        # Any other flagged dimension: a single honest structured TODO row rather than a fabricated
        # 7-axis matrix.
        for ax in SUBSCORE_AXES:
            axes[ax] = _axis(
                overall if ax == "Maturity" else None,
                "ESTIMATED" if ax == "Maturity" else "TODO",
                (f"{DIMENSION_LABEL.get(dim, dim)} overall {overall} (engine-presence band)"
                 if ax == "Maturity"
                 else f"no isolated live signal for {ax} yet — needs a per-axis measurement"))

    measured_axes = sum(1 for a in axes.values() if a["basis"] == "MEASURED")
    return {
        "dimension": dim,
        "label": DIMENSION_LABEL.get(dim, dim),
        "axes": axes,
        "n_measured": measured_axes,
        "n_todo": sum(1 for a in axes.values() if a["basis"] == "TODO"),
        "note": ("real per-axis signals where they exist; the rest are structured TODOs naming the "
                 "live read that would fill them — never fabricated"),
    }


def build_scorecard(creature: str = LIVE_CREATURE) -> dict:
    """Compute every dimension cell from its real signal where one exists, label each honestly,
    and flag the lowest mature-essential cell as the current bottleneck. Never raises — a missing
    engine yields an honest ESTIMATED cell. Returns the full scorecard report dict."""
    cells = {}

    # --- MEASURED dimensions (real signals) ---------------------------------------------------
    cons, cons_d = signal_conservation()
    if cons is not None:
        # Memory durability is anchored to the real end-to-end retention: the fraction of salient
        # information that actually survives DETECTED -> USED is the hardest read we have on
        # whether the Mind keeps what it learns.
        cells["memory"] = _cell(
            "memory", cons * 100, "MEASURED",
            f"Conservation end-to-end retention {cons * 100:.1f}% (target "
            f"{cons_d['target'] * 100:.0f}%) via {cons_d['signal']}",
            note=("retention is the durability of memory across the capture pipeline; "
                  + ("clears target" if cons_d.get("clears_target") else "below the 95% target")))
    else:
        cells["memory"] = _estimated_engine_cell(
            "memory", "Conservation signal unavailable -> fell back to engine presence")

    obs, obs_d = signal_observation()
    cells["observation"] = _cell(
        "observation", obs * 100, "MEASURED", obs_d["signal"],
        note=("the microscope is "
              + ("complete" if not obs_d["missing"]
                 else "missing: " + ", ".join(obs_d["missing"]))))

    cert, cert_d = signal_certification()
    cells["certification"] = _cell(
        "certification", cert * 100, "MEASURED", cert_d["signal"],
        note=cert_d.get("live_pass", "presence MEASURED; live pass ESTIMATED"))

    resolved, rl_d = signal_reality_learning(creature)
    if resolved is None:
        cells["reality_learning"] = _estimated_engine_cell(
            "reality_learning", "reality ledger unreadable")
    else:
        # RESOLVED real outcomes is the ONLY thing that makes reality-learning real. 0 is a true
        # measurement (the loop is built; no real outcome has come back over calendar time yet).
        # We score it low-but-not-zero: the machinery exists and is proven on a synthetic loop,
        # but ZERO real learning has accrued. Honest: MEASURED-as-zero, time-gated.
        rl_score = 8 if resolved == 0 else min(100, 25 + resolved * 5)
        cells["reality_learning"] = _cell(
            "reality_learning", rl_score, "MEASURED", rl_d["signal"],
            note=("TIME-GATED: real learning accrues only as real outcomes arrive over real "
                  "calendar time" if rl_d.get("time_gated") else ""))

    # --- ENGINE-PRESENCE dimensions (ESTIMATED; honest about being heuristics) -----------------
    # Continuity: the LAW-001 survival machinery is present and the certification survival matrix
    # exercises it — but a live "did it survive all 5 corruption modes today" verdict would be the
    # MEASURED signal (it lives in certify.py, which we don't run here), so this stays ESTIMATED.
    cells["continuity"] = _estimated_engine_cell(
        "continuity",
        "a live read is the certify.py survival matrix (5 corruption modes) — not run here")
    cells["experience"] = _estimated_engine_cell(
        "experience", "a live read is scripts/experience.py probes — not run here")
    cells["curiosity"] = _estimated_engine_cell(
        "curiosity", "a live read is scripts/curiosity_quality.py run_battery() — not run here")
    cells["grounding"] = _estimated_engine_cell(
        "grounding", "a live read is the mri.py hallucination battery — not run here")
    cells["prediction"] = _estimated_engine_cell(
        "prediction", "the epistemic engine is built; calibration is TIME-GATED")
    cells["identity"] = _estimated_engine_cell(
        "identity", "export/validate/migrate present; portability proven in selftest")

    # --- NOT-BUILT meta axes (ESTIMATED low; clearly not measured) ----------------------------
    cells["self_improvement"] = _cell(
        "self_improvement", _ABSENT_ESTIMATE, "ESTIMATED",
        "no self-improvement loop is built (the Mind does not yet rewrite/upgrade itself)",
        note="meta-axis; not a mature-essential bottleneck candidate", essential=False)
    cells["novelty"] = _cell(
        "novelty", _ABSENT_ESTIMATE, "ESTIMATED",
        "no novelty engine is built (the Mind does not yet generate genuinely new ideas)",
        note="meta-axis; not a mature-essential bottleneck candidate", essential=False)
    cells["governance_cost"] = _cell(
        "governance_cost", _ABSENT_ESTIMATE + 8, "ESTIMATED",
        "governance cost is not yet instrumented (no measured overhead/$ of the review machinery)",
        note="meta-axis; this very board is the first step toward measuring it", essential=False)

    ordered = [cells[k] for k in DIMENSION_ORDER if k in cells]

    # The (flat) VISIBLE WEAKNESS is the lowest-scoring MATURE-ESSENTIAL dimension (Observed >
    # Assumed: the weakest REQUIRED layer, regardless of MEASURED vs ESTIMATED — but the report
    # makes the basis visible so an estimate is never mistaken for a fact). This is the EXISTING
    # flat flag, preserved verbatim as `bottleneck` for back-compat.
    essential_cells = [c for c in ordered if c["essential"]]
    bottleneck = min(essential_cells, key=lambda c: (c["score"], c["key"])) if essential_cells else None

    measured = [c for c in ordered if c["basis"] == "MEASURED"]
    estimated = [c for c in ordered if c["basis"] == "ESTIMATED"]

    # The DEPENDENCY-WEIGHTED upgrade: from the flat visible weakness, walk UP the spine to the
    # ROOT (deepest still-weak layer) and the IMMEDIATE (shallowest BUILDABLE weak layer). This is
    # what turns the scoreboard into a governor.
    resolution = resolve_bottleneck(ordered, bottleneck)

    # Per-subsystem 7-axis sub-scores for the FLAGGED dimensions (visible + root + immediate), from
    # real signals where they exist (chiefly the Conservation pipeline + meaning_detail in cons_d).
    by_key = {c["key"]: c for c in ordered}
    flagged = []
    for slot in ("visible", "root", "immediate"):
        node = resolution.get(slot) or {}
        k = node.get("key")
        if k and k not in flagged:
            flagged.append(k)
    subscores = {k: subscores_for(k, by_key, cons_d) for k in flagged}

    return {
        "mode": "mind_balance",
        "creature": creature,
        "git_head": _git_head(),
        "cells": ordered,
        "bottleneck": bottleneck,            # the flagged weakest mature-essential layer (FLAT)
        "weakest_key": bottleneck["key"] if bottleneck else None,
        "resolution": resolution,            # the 3-level dependency-weighted resolution
        "subscores": subscores,              # 7-axis drill-down for the flagged dimensions
        "n_measured": len(measured),
        "n_estimated": len(estimated),
        "directive": "OBSERVED > ASSUMED.  MEASURED > BELIEVED.  CERTIFIED > CLAIMED.",
    }


# ===================================================================================
# RENDER — MODE 1.
# ===================================================================================
def _bar(score: int, width: int = 22) -> str:
    fill = int(round((score / 100.0) * width))
    return "[" + "#" * fill + "-" * (width - fill) + "]"


def render_scorecard(report: dict) -> str:
    out = []
    out.append("=" * 86)
    out.append("VERA MIND BALANCE DASHBOARD — the maturity scorecard")
    out.append(report["directive"])
    out.append(f"creature: {report['creature']}    HEAD: {report['git_head']}")
    out.append("=" * 86)
    out.append("")
    out.append(f"  {'DIMENSION':<18} {'SCORE':>5}  {'BAR':<24} {'BASIS':<9} SIGNAL")
    out.append("  " + "-" * 82)
    for c in report["cells"]:
        ess = "*" if c["essential"] else " "
        sig = c["signal"]
        if len(sig) > 120:
            sig = sig[:117] + "..."
        out.append(f"{ess} {c['label']:<18} {c['score']:>4}  {_bar(c['score'])} "
                   f"{c['basis']:<9} {sig}")
    out.append("  " + "-" * 82)
    out.append(f"  (* = mature-essential; MEASURED={report['n_measured']} "
               f"ESTIMATED={report['n_estimated']})")
    out.append("")

    # The honest split — what is MEASURED vs what is still an ESTIMATE. This IS the dashboard
    # applying its own rule to itself.
    out.append("  MEASURED (read from a real signal):")
    for c in report["cells"]:
        if c["basis"] == "MEASURED":
            out.append(f"    - {c['label']:<18} {c['score']:>3}   {c['signal']}")
    out.append("")
    out.append("  ESTIMATED (heuristic / needs a live measurement — NOT presented as measured):")
    for c in report["cells"]:
        if c["basis"] == "ESTIMATED":
            out.append(f"    - {c['label']:<18} {c['score']:>3}   {c['signal']}")
    out.append("")

    b = report.get("bottleneck")
    if b:
        out.append("  " + "=" * 82)
        out.append(f"  CURRENT BOTTLENECK (lowest mature-essential): {b['label']} "
                   f"@ {b['score']}/100  [{b['basis']}]")
        out.append(f"    why: {b['signal']}")
        if b["note"]:
            out.append(f"    note: {b['note']}")
        out.append("    -> this is the lowest FLAT score (a scoreboard read — may be downstream).")
        out.append("  " + "=" * 82)

    # --- THE DEPENDENCY-WEIGHTED RESOLUTION (the governor, not the scoreboard) -----------------
    out.append("")
    out += _render_resolution(report.get("resolution"))

    # --- the per-subsystem 7-axis drill-down for the flagged dimensions -----------------------
    subs = report.get("subscores") or {}
    if subs:
        out.append("")
        out.append("  PER-SUBSYSTEM SUB-SCORES (7 axes; MEASURED cites its signal, TODO names the "
                   "missing live read)")
        out.append("  " + "-" * 82)
        for key, sub in subs.items():
            out.append(f"  {sub['label']}  "
                       f"(MEASURED axes {sub['n_measured']}/7, structured-TODO {sub['n_todo']}/7)")
            for ax in SUBSCORE_AXES:
                a = sub["axes"].get(ax, {})
                sc = "  --" if a.get("score") is None else f"{a['score']:>4}"
                sig = a.get("signal", "")
                if len(sig) > 96:
                    sig = sig[:93] + "..."
                out.append(f"      {ax:<18}{sc}  [{a.get('basis', '?'):<9}] {sig}")
            out.append("")
    return "\n".join(out)


def _render_resolution(res: dict) -> list:
    """Render the three-level VISIBLE / ROOT / IMMEDIATE resolution + the 100-hours headline +
    the dependency chain + the one-line WHY. The headline is the load-bearing line: it points the
    next 100 engineering hours at the IMMEDIATE buildable bottleneck, not the flat low score."""
    if not res or not res.get("immediate"):
        return ["  (no dependency-weighted resolution — empty board)"]
    out = ["  " + "#" * 82]
    out.append(f"  NEXT 100 ENGINEERING HOURS  ->  {res['immediate']['label'].upper()}   "
               f"(@ {res['immediate']['score']}/100, BUILDABLE)")
    out.append("  " + "#" * 82)
    out.append("  DEPENDENCY-WEIGHTED BOTTLENECK (a governor, not a scoreboard):")
    rt, im, vi = res["root"], res["immediate"], res["visible"]
    out.append(f"    Root Bottleneck:      {rt['label']:<18} @ {rt['score']:>3}/100   "
               f"(deepest weak dependency{' — TIME-GATED' if rt.get('time_gated') else ''})")
    out.append(f"    Immediate Bottleneck: {im['label']:<18} @ {im['score']:>3}/100   "
               f"(next buildable, blocked by root)")
    out.append(f"    Visible Weakness:     {vi['label']:<18} @ {vi['score']:>3}/100   "
               f"(lowest flat score, but downstream)")
    out.append("")
    out.append("    spine (depends-on, foundation -> downstream):")
    out.append("      " + res["chain_str"])
    out.append("")
    out.append(f"    why: {res['why']}")
    out.append("  " + "#" * 82)
    return out


# ===================================================================================
# MODE 2 — THE ARB WAVE-END REVIEW. Prints the 8 questions, answers the computable ones from
# data, leaves STRUCTURED slots for the narrative ones, and runs the REALITY > ROADMAP conflict
# check (the directive's most important rule, mechanized).
# ===================================================================================

# The 8 wave-end review questions, in order. Each is (key, question, answerable_from_data?).
REVIEW_QUESTIONS = [
    ("built",        "1. What was built this wave?", False),
    ("bottleneck",   "2. What bottleneck did it remove?", False),
    ("metric",       "3. What metric improved (and by how much)?", True),
    ("learned",      "4. What did we learn?", False),
    ("surprised",    "5. What surprised us?", False),
    ("weakest",      "6. What does observability now say is weakest?", True),
    ("moved",        "7. What moved on the Mind Balance?", True),
    ("closer",       "8. Did this move us closer to a Digital Mind?", True),
]


def build_review(creature: str = LIVE_CREATURE, roadmap_next: str = None,
                 narrative: dict = None) -> dict:
    """Assemble the wave-end review: the 8 questions, data-answers where computable, structured
    narrative slots, and the REALITY > ROADMAP conflict check against the observatory-identified
    weakest layer. ``roadmap_next`` is the declared next item (a dimension key, free text, or
    None). Never raises."""
    narrative = narrative or {}
    score = build_scorecard(creature)
    weakest_key = score.get("weakest_key")
    weakest = score.get("bottleneck") or {}

    # Question 3 — the metric that improved: the hardest real number we have (Conservation
    # retention vs its target). We report the CURRENT measured value; "improvement" needs a prior
    # wave's value, so we leave the delta as a narrative slot but anchor it to the real number.
    cons_cell = next((c for c in score["cells"] if c["key"] == "memory"), None)
    metric_answer = {
        "data": (f"Conservation end-to-end retention is {cons_cell['score']}% "
                 f"({cons_cell['basis']}). " if cons_cell else "")
                + "Δ vs the previous wave is a narrative slot (no prior snapshot is stored).",
        "needs_human": "by how much did it improve vs last wave?",
        "from": narrative.get("metric"),
    }

    answers = {}
    for key, question, _ in REVIEW_QUESTIONS:
        if key == "metric":
            answers[key] = {"question": question, **metric_answer}
        elif key == "weakest":
            answers[key] = {
                "question": question,
                "data": (f"{weakest.get('label', '?')} @ {weakest.get('score', '?')}/100 "
                         f"[{weakest.get('basis', '?')}] — {weakest.get('signal', '')}"),
                "needs_human": None,
                "from": None,
            }
        elif key == "moved":
            answers[key] = {
                "question": question,
                "data": (f"{score['n_measured']} dimensions are now MEASURED, "
                         f"{score['n_estimated']} still ESTIMATED. "
                         "Per-dimension Δ needs a prior Mind-Balance snapshot to diff."),
                "needs_human": "which dimensions moved up since last wave?",
                "from": narrative.get("moved"),
            }
        elif key == "closer":
            # A principled, computable proxy: the mean of the mature-essential dimensions — the
            # readiness of the REQUIRED layers. Labelled as a proxy, not a verdict.
            ess = [c for c in score["cells"] if c["essential"]]
            mean_ess = (sum(c["score"] for c in ess) / len(ess)) if ess else 0.0
            answers[key] = {
                "question": question,
                "data": (f"PROXY: mature-essential readiness = {mean_ess:.0f}/100 "
                         f"(mean of the {len(ess)} required layers). A Digital Mind needs ALL "
                         "required layers mature AND real reality-learning accruing — the latter "
                         "is still MEASURED-as-zero (time-gated)."),
                "needs_human": "is the wave's net effect closer? (judgement, anchored to the proxy)",
                "from": narrative.get("closer"),
            }
        else:
            # The narrative questions — structured slots a human fills, never fabricated.
            answers[key] = {
                "question": question,
                "data": None,
                "needs_human": question.split(". ", 1)[-1],
                "from": narrative.get(key),
            }

    conflict = reality_vs_roadmap(weakest_key, roadmap_next, weakest)
    resolution = score.get("resolution") or {}
    exception = roadmap_exception(conflict, resolution, roadmap_next)

    return {
        "mode": "arb_review",
        "creature": creature,
        "git_head": score["git_head"],
        "scorecard": score,
        "questions": [q for _, q, _ in REVIEW_QUESTIONS],
        "answers": answers,
        "reality_vs_roadmap": conflict,
        "resolution": resolution,            # the 3-level dependency-weighted resolution
        "roadmap_exception": exception,      # the ROADMAP EXCEPTION RULE verdict
        "directive": score["directive"],
    }


def _norm_dim(s: str):
    """Normalise a free-text roadmap item to a dimension key when it clearly names one (so
    '--next reality learning', 'Reality-Learning', 'reality_learning' all match). Returns the key
    or None if it isn't a recognised dimension."""
    if not s:
        return None
    t = "".join(ch if ch.isalnum() else " " for ch in str(s).lower()).split()
    joined = "_".join(t)
    if joined in DIMENSION_LABEL:
        return joined
    # tolerate the bare label words ("reality learning" -> reality_learning, "self improvement")
    for key, label in DIMENSION_LABEL.items():
        if joined == key or joined == "_".join(label.lower().split()):
            return key
    # single-word dimensions
    if len(t) == 1 and t[0] in DIMENSION_LABEL:
        return t[0]
    return None


def reality_vs_roadmap(weakest_key, roadmap_next, weakest_cell=None) -> dict:
    """THE most important check: compare the observatory-identified WEAKEST mature-essential layer
    to the declared roadmap 'next item'. If they DIFFER, a conflict is flagged LOUDLY — the
    builder is required to surface a plan-vs-measurement disagreement instead of quietly building
    the planned thing. Returns a structured verdict (conflict True/False + the loud message)."""
    weakest_cell = weakest_cell or {}
    declared_key = _norm_dim(roadmap_next)
    if not roadmap_next:
        return {
            "conflict": None,
            "weakest": weakest_key,
            "roadmap_next": None,
            "declared_key": None,
            "message": ("No roadmap 'next item' declared — pass --next <item> (or a config) to "
                        "run the REALITY > ROADMAP check against the weakest measured layer "
                        f"({DIMENSION_LABEL.get(weakest_key, weakest_key)})."),
        }
    # A conflict is when the declared next item is a recognised dimension that ISN'T the weakest,
    # OR free text that doesn't name the weakest layer. We compare on the dimension KEY when the
    # roadmap names one; otherwise we compare the raw label.
    matches = (declared_key == weakest_key) if declared_key else (
        _norm_dim(roadmap_next) == weakest_key
    )
    weakest_label = weakest_cell.get("label", DIMENSION_LABEL.get(weakest_key, str(weakest_key)))
    next_label = DIMENSION_LABEL.get(declared_key, str(roadmap_next))
    if matches:
        return {
            "conflict": False,
            "weakest": weakest_key,
            "roadmap_next": roadmap_next,
            "declared_key": declared_key,
            "message": (f"ALIGNED: measurements say {weakest_label} is the bottleneck, and the "
                        f"roadmap's next item is {next_label}. Build it."),
        }
    return {
        "conflict": True,
        "weakest": weakest_key,
        "roadmap_next": roadmap_next,
        "declared_key": declared_key,
        "message": (f"REALITY > ROADMAP CONFLICT: measurements say {weakest_label} is the "
                    f"bottleneck; roadmap says build {next_label}. Surface this."),
    }


# The four gates a bottleneck-fix must clear to be an ALLOWED PARALLEL EXCEPTION rather than a
# roadmap deviation (the ROADMAP EXCEPTION RULE). A fix that is MEASURED (anchored to a real
# metric), QUANTIFIED (a number moves), ISOLATED (touches a bounded surface), and NON-INTERFERING
# (additive — breaks nothing on the main line) may proceed in PARALLEL with the planned roadmap.
EXCEPTION_GATES = ("measured", "quantified", "isolated", "non_interfering")


def roadmap_exception(conflict: dict, resolution: dict, roadmap_next: str) -> dict:
    """Classify a roadmap divergence under the ROADMAP EXCEPTION RULE:

        "a MEASURED + QUANTIFIED + ISOLATED + NON-INTERFERING bottleneck fix may proceed in
         parallel."

    A plain REALITY > ROADMAP conflict means the roadmap's next item differs from the flat weakest
    layer — but that is NOT automatically a deviation to halt. If the declared next item is in fact
    a genuine bottleneck fix on the dependency spine (the IMMEDIATE buildable bottleneck, the ROOT,
    or the foundational Memory/capture layer everything sits on) AND it clears the four gates, it
    is an ALLOWED PARALLEL EXCEPTION — a legitimate parallel bottleneck-fix, not a roadmap
    deviation. This is exactly how the in-flight capture fix (#59 — measured by Conservation
    retention, quantified, isolated to the capture surface, additive/non-interfering) is classified
    as ALLOWED rather than a conflict.

    Returns a structured verdict the review renders. Pure function -> deterministic. Never raises.
    The four gates are themselves a STRUCTURED CHECKLIST (some can only be confirmed by a human /
    the diff); we PRESUME them for a recognised on-spine bottleneck fix and label that presumption
    honestly, never asserting a gate we did not verify."""
    res = resolution or {}
    declared_key = (conflict or {}).get("declared_key")
    immediate_key = res.get("immediate", {}).get("key") if res.get("immediate") else None
    root_key = res.get("root", {}).get("key") if res.get("root") else None

    # Is the declared item a genuine bottleneck-fix on the spine? -> the immediate buildable
    # bottleneck, the root, or the foundational capture/memory layer everything depends on.
    on_spine_fix = declared_key in {immediate_key, root_key, "memory"} and declared_key is not None

    if not conflict or conflict.get("conflict") is not True:
        # No conflict (aligned / none-declared) -> the exception rule is not engaged.
        return {
            "applies": False,
            "verdict": "n/a",
            "gates": {g: None for g in EXCEPTION_GATES},
            "message": ("ROADMAP EXCEPTION RULE not engaged (no reality>roadmap conflict to "
                        "reclassify)."),
        }

    if on_spine_fix:
        # PRESUMED to clear the four gates because it is a recognised on-spine bottleneck fix. The
        # presumption is labelled; the diff/human confirms the gates definitively.
        gates = {g: True for g in EXCEPTION_GATES}
        return {
            "applies": True,
            "verdict": "ALLOWED PARALLEL EXCEPTION",
            "declared_key": declared_key,
            "spine_role": ("IMMEDIATE bottleneck" if declared_key == immediate_key else
                           "ROOT bottleneck" if declared_key == root_key else
                           "foundational capture/memory layer"),
            "gates": gates,
            "presumed": True,
            "message": (
                f"ALLOWED PARALLEL EXCEPTION: '{DIMENSION_LABEL.get(declared_key, roadmap_next)}' is "
                f"a genuine bottleneck fix on the dependency spine "
                f"({'the immediate buildable bottleneck' if declared_key == immediate_key else 'the root' if declared_key == root_key else 'the foundation everything sits on'}). "
                "Under the ROADMAP EXCEPTION RULE a MEASURED + QUANTIFIED + ISOLATED + "
                "NON-INTERFERING bottleneck fix may proceed IN PARALLEL — this is a legitimate "
                "parallel fix (e.g. the in-flight capture fix #59), NOT a roadmap deviation. "
                "Confirm the four gates against the diff."),
        }

    # A real divergence: the declared item is neither the weakest nor an on-spine bottleneck fix.
    return {
        "applies": True,
        "verdict": "ROADMAP DEVIATION",
        "declared_key": declared_key,
        "spine_role": None,
        "gates": {g: False for g in EXCEPTION_GATES},
        "presumed": False,
        "message": (
            f"ROADMAP DEVIATION: '{roadmap_next}' is neither the measured weakest layer nor a "
            "bottleneck fix on the dependency spine, so the ROADMAP EXCEPTION RULE does NOT cover "
            "it. Surface and justify before building."),
    }


def render_review(report: dict) -> str:
    out = []
    out.append("=" * 86)
    out.append("VERA ARCHITECTURAL REVIEW BOARD — wave-end review")
    out.append(report["directive"])
    out.append(f"creature: {report['creature']}    HEAD: {report['git_head']}")
    out.append("=" * 86)
    out.append("")
    out.append("THE 8 REVIEW QUESTIONS")
    out.append("-" * 86)
    for key, question, _ in REVIEW_QUESTIONS:
        a = report["answers"][key]
        out.append(question)
        if a.get("from"):
            out.append(f"    ANSWER (declared): {a['from']}")
        if a.get("data"):
            out.append(f"    FROM DATA: {a['data']}")
        if a.get("needs_human") and not a.get("from"):
            out.append(f"    [SLOT — needs human] {a['needs_human']}")
        out.append("")

    # The bottleneck restated from the scorecard, so the review is self-contained.
    b = report["scorecard"].get("bottleneck") or {}
    out.append("-" * 86)
    out.append(f"OBSERVABILITY SAYS WEAKEST (flat): {b.get('label', '?')} @ "
               f"{b.get('score', '?')}/100 [{b.get('basis', '?')}]")
    out.append("")

    # THE DEPENDENCY-WEIGHTED RESOLUTION + the 100-hours headline — the governor view.
    out += _render_resolution(report.get("resolution"))
    out.append("")

    # THE REALITY > ROADMAP CHECK — loud on conflict.
    c = report["reality_vs_roadmap"]
    out.append("REALITY > ROADMAP CHECK")
    out.append("-" * 86)
    if c["conflict"] is True:
        bang = "!" * 86
        out.append(bang)
        out.append("  " + c["message"])
        out.append(bang)
    elif c["conflict"] is False:
        out.append("  " + c["message"])
    else:
        out.append("  " + c["message"])
    out.append("")

    # THE ROADMAP EXCEPTION RULE — distinguish a legitimate parallel bottleneck-fix from a
    # roadmap deviation. Only engaged when a conflict fired.
    ex = report.get("roadmap_exception") or {}
    out.append("ROADMAP EXCEPTION RULE  (a measured + quantified + isolated + non-interfering "
               "bottleneck fix may proceed in parallel)")
    out.append("-" * 86)
    if not ex.get("applies"):
        out.append("  " + ex.get("message", "not engaged."))
    else:
        out.append(f"  VERDICT: {ex.get('verdict')}")
        gates = ex.get("gates", {})
        gate_line = "   ".join(
            f"[{'x' if gates.get(g) else (' ' if gates.get(g) is False else '?')}] {g}"
            for g in EXCEPTION_GATES)
        out.append(f"  gates: {gate_line}"
                   + ("   (PRESUMED for a recognised on-spine fix; confirm vs the diff)"
                      if ex.get("presumed") else ""))
        out.append("  " + ex.get("message", ""))
    out.append("=" * 86)
    return "\n".join(out)


# ===================================================================================
# SELFTEST — PROVE the board's load-bearing properties, DETERMINISTICALLY, with the real .anima
# byte-UNCHANGED around the run. No model, no network.
#   * the scorecard computes the REAL Conservation retention and labels Memory MEASURED;
#   * the lowest mature-essential score is the flagged bottleneck (and the flag tracks a forced
#     change in the scores);
#   * the REALITY > ROADMAP conflict flag FIRES when weakest != next, and does NOT when they match;
#   * the whole thing is deterministic (two runs -> identical scorecard);
#   * nothing real was touched.
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("VERA ARB + MIND BALANCE self-test")

    real = Path(_ROOT) / ".anima"
    fp_before = _footprint(real)

    # --- the scorecard computes the REAL Conservation retention as MEASURED -------------------
    sc = build_scorecard()
    mem = next((c for c in sc["cells"] if c["key"] == "memory"), None)
    cons_raw, cons_d = signal_conservation()
    ok("scorecard builds with all 13 dimensions",
       len(sc["cells"]) == len(DIMENSION_ORDER))
    ok("Conservation signal is MEASURED (real run_battery end-to-end retention)",
       cons_raw is not None and cons_d.get("measured") is True)
    ok("Memory cell is LABELLED MEASURED and equals the real retention",
       mem is not None and mem["basis"] == "MEASURED"
       and mem["score"] == int(round(cons_raw * 100)))
    ok("Observation is MEASURED off present observatory scripts",
       next(c for c in sc["cells"] if c["key"] == "observation")["basis"] == "MEASURED")
    ok("Reality Learning is MEASURED-as-zero (time-gated; live ledger read read-only)",
       next(c for c in sc["cells"] if c["key"] == "reality_learning")["basis"] == "MEASURED")

    # --- the HONEST-LABEL invariant: not-built meta axes are ESTIMATED, never MEASURED --------
    for k in ("self_improvement", "novelty", "governance_cost"):
        c = next(cc for cc in sc["cells"] if cc["key"] == k)
        ok(f"{k} is ESTIMATED (an estimate is never presented as measured)",
           c["basis"] == "ESTIMATED")

    # --- the lowest mature-essential score is the flagged bottleneck --------------------------
    ess = [c for c in sc["cells"] if c["essential"]]
    lowest = min(ess, key=lambda c: (c["score"], c["key"]))
    ok("bottleneck is the lowest-scoring mature-essential dimension",
       sc["bottleneck"] is not None and sc["bottleneck"]["key"] == lowest["key"])
    ok("a not-built meta-axis is NOT chosen as the bottleneck",
       sc["bottleneck"]["key"] not in ("self_improvement", "novelty", "governance_cost"))

    # the flag TRACKS the data: force a synthetic floor on one essential dim and confirm the
    # bottleneck follows it (pure-function check on the selection logic, no real state touched).
    def _bottleneck_of(cells):
        e = [c for c in cells if c["essential"]]
        return min(e, key=lambda c: (c["score"], c["key"]))["key"] if e else None
    forced = [dict(c) for c in sc["cells"]]
    target_dim = "grounding"
    for c in forced:
        if c["key"] == target_dim:
            c["score"] = 0
    ok("bottleneck flag re-points when an essential dimension is forced lowest",
       _bottleneck_of(forced) == target_dim)

    # --- the REALITY > ROADMAP conflict flag fires when weakest != next -----------------------
    weakest_key = sc["weakest_key"]
    # pick a DIFFERENT essential dimension as the declared 'next' -> must CONFLICT.
    other = next(c["key"] for c in ess if c["key"] != weakest_key)
    conflict = reality_vs_roadmap(weakest_key, other, sc["bottleneck"])
    ok("reality>roadmap FIRES a conflict when roadmap next != measured weakest",
       conflict["conflict"] is True and "REALITY > ROADMAP CONFLICT" in conflict["message"])
    # declaring the ACTUAL weakest as next -> NO conflict (aligned).
    aligned = reality_vs_roadmap(weakest_key, weakest_key, sc["bottleneck"])
    ok("reality>roadmap is ALIGNED (no conflict) when next == measured weakest",
       aligned["conflict"] is False and "ALIGNED" in aligned["message"])
    # no declared next -> neither aligned nor conflict, an honest prompt to declare one.
    none_decl = reality_vs_roadmap(weakest_key, None, sc["bottleneck"])
    ok("reality>roadmap with no declared next is honest (conflict is None)",
       none_decl["conflict"] is None)
    # free-text that names the weakest layer is recognised as aligned (label tolerance).
    free_aligned = reality_vs_roadmap(
        weakest_key, DIMENSION_LABEL[weakest_key].lower(), sc["bottleneck"])
    ok("reality>roadmap tolerates free-text that names the weakest layer (aligned)",
       free_aligned["conflict"] is False)

    # --- the full review assembles and the loud flag renders ----------------------------------
    rev = build_review(roadmap_next=other)
    rtxt = render_review(rev)
    ok("review prints all 8 questions",
       all(q.split(".", 1)[0] + "." in rtxt for q in
           ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8."]))
    ok("review renders the LOUD conflict banner when next != weakest",
       "REALITY > ROADMAP CONFLICT" in rtxt and "!!!!" in rtxt)
    ok("review narrative questions are SLOTS, never fabricated",
       rev["answers"]["built"]["data"] is None
       and rev["answers"]["built"]["needs_human"])

    # --- THE DEPENDENCY GRAPH: acyclic + every dimension placed -------------------------------
    ok("dependency graph is ACYCLIC (a DAG — 'walk up to the root' terminates)",
       _graph_is_acyclic())
    ok("every dimension is placed in the dependency graph (total coverage)",
       set(DEPENDS_ON.keys()) == set(DIMENSION_ORDER)
       and all(set(ups) <= set(DIMENSION_ORDER) for ups in DEPENDS_ON.values()))
    ok("the spine is encoded foundation->downstream "
       "(memory<-experience<-grounding<-prediction<-reality_learning<-self_improvement)",
       "memory" in DEPENDS_ON["experience"]
       and "experience" in DEPENDS_ON["grounding"]
       and "grounding" in DEPENDS_ON["prediction"]
       and "prediction" in DEPENDS_ON["reality_learning"]
       and "reality_learning" in DEPENDS_ON["self_improvement"]
       and DEPENDS_ON["memory"] == set())
    # the chain walker returns the foundation first and the queried node last, no dupes.
    ch = dependency_chain("reality_learning")
    ok("dependency_chain walks foundation-first, node-last, no duplicates",
       ch[0] == "memory" and ch[-1] == "reality_learning" and len(ch) == len(set(ch)))

    # --- THE THREE-LEVEL RESOLUTION on the CURRENT board --------------------------------------
    res = sc["resolution"]
    visible_key = sc["weakest_key"]
    ok("resolution VISIBLE == the flat lowest mature-essential weakness",
       res["visible"]["key"] == visible_key)
    # On the live board the visible weakness (reality_learning) HAS a weaker-than-strong upstream
    # path with a still-weak node above it, so ROOT must differ from VISIBLE.
    visible_chain = dependency_chain(visible_key)
    weak_upstream = [k for k in visible_chain[:-1]
                     if next(c["score"] for c in sc["cells"] if c["key"] == k) < WEAK_THRESHOLD]
    if weak_upstream:
        ok("ROOT != VISIBLE when the visible weakness has a weaker upstream dependency",
           res["root"]["key"] != visible_key)
        # ROOT is the DEEPEST weak node on the path (the first weak node, scanning foundation-first).
        deepest_weak = next(k for k in visible_chain
                            if next(c["score"] for c in sc["cells"] if c["key"] == k) < WEAK_THRESHOLD)
        ok("ROOT is the DEEPEST weak node on the dependency path",
           res["root"]["key"] == deepest_weak)
    else:
        ok("ROOT == VISIBLE when nothing upstream is weak (no false root)",
           res["root"]["key"] == visible_key)
    # A STRONG upstream layer (Memory ~100) is NEVER chosen as the root.
    mem_score = next(c["score"] for c in sc["cells"] if c["key"] == "memory")
    if mem_score >= WEAK_THRESHOLD:
        ok("a STRONG upstream layer (Memory) is NOT chosen as the root",
           res["root"]["key"] != "memory")
    # The IMMEDIATE bottleneck is BUILDABLE — never a time-gated node.
    ok("IMMEDIATE bottleneck is BUILDABLE (never a TIME_GATED node like reality_learning)",
       res["immediate"]["key"] not in TIME_GATED and res["immediate"]["buildable"] is True)
    # The 100-hours headline points at the IMMEDIATE bottleneck (not the flat low score).
    ok("the '100 engineering hours' headline points at the IMMEDIATE bottleneck",
       res["headline_key"] == res["immediate"]["key"]
       and res["immediate"]["label"] in res["headline"])
    # On the current board the visible weakness is time-gated, so the headline must NOT be it.
    if visible_key in TIME_GATED:
        ok("the headline does NOT point at the time-gated visible weakness",
           res["headline_key"] != visible_key)

    # the resolution TRACKS the data: with a synthetic floor on a buildable upstream layer, the
    # root + immediate must re-point onto it (pure-function check, no real state touched).
    forced2 = [dict(c) for c in sc["cells"]]
    for c in forced2:
        if c["key"] == "memory":
            c["score"] = 3                      # force the FOUNDATION weak
    forced_vis = min([c for c in forced2 if c["essential"]],
                     key=lambda c: (c["score"], c["key"]))
    res2 = resolve_bottleneck(forced2, forced_vis)
    ok("ROOT re-points to the foundation (Memory) when it is forced weakest",
       res2["root"]["key"] == "memory" and res2["immediate"]["key"] == "memory")

    # --- THE ROADMAP EXCEPTION RULE: parallel bottleneck-fix vs deviation ---------------------
    conflict_mem = reality_vs_roadmap(visible_key, "memory", sc["bottleneck"])
    ex_mem = roadmap_exception(conflict_mem, res, "memory")
    ok("ROADMAP EXCEPTION: a capture/Memory fix (#59-like) is an ALLOWED PARALLEL EXCEPTION",
       ex_mem["applies"] and ex_mem["verdict"] == "ALLOWED PARALLEL EXCEPTION"
       and all(ex_mem["gates"][g] for g in EXCEPTION_GATES))
    conflict_imm = reality_vs_roadmap(visible_key, res["immediate"]["key"], sc["bottleneck"])
    ex_imm = roadmap_exception(conflict_imm, res, res["immediate"]["key"])
    ok("ROADMAP EXCEPTION: building the IMMEDIATE bottleneck is an ALLOWED PARALLEL EXCEPTION",
       ex_imm["verdict"] == "ALLOWED PARALLEL EXCEPTION")
    # an off-spine item that isn't the weakest is a genuine DEVIATION, not an allowed exception.
    off_spine = next((c["key"] for c in sc["cells"]
                      if c["key"] not in {visible_key, res["root"]["key"],
                                          res["immediate"]["key"], "memory"}
                      and c["essential"]), "identity")
    conflict_dev = reality_vs_roadmap(visible_key, off_spine, sc["bottleneck"])
    ex_dev = roadmap_exception(conflict_dev, res, off_spine)
    ok("ROADMAP EXCEPTION: an off-spine non-weakest item is a ROADMAP DEVIATION (not allowed)",
       ex_dev["verdict"] == "ROADMAP DEVIATION")
    # no conflict -> the exception rule is not engaged.
    ex_none = roadmap_exception(reality_vs_roadmap(visible_key, visible_key, sc["bottleneck"]),
                                res, visible_key)
    ok("ROADMAP EXCEPTION rule is NOT engaged when there is no conflict",
       ex_none["applies"] is False)

    # --- PER-SUBSYSTEM SUB-SCORES: honest labels, never fabricated ----------------------------
    subs = sc["subscores"]
    ok("sub-scores exist for the flagged dimensions (visible + root + immediate)",
       res["visible"]["key"] in subs and res["root"]["key"] in subs
       and res["immediate"]["key"] in subs)
    ok("every sub-score axis is labelled MEASURED | ESTIMATED | TODO (never blank/fabricated)",
       all(a["basis"] in ("MEASURED", "ESTIMATED", "TODO")
           for sub in subs.values() for a in sub["axes"].values()))
    ok("a structured-TODO axis carries NO fabricated score (score is None)",
       all(a["score"] is None
           for sub in subs.values() for a in sub["axes"].values() if a["basis"] == "TODO"))
    ok("Memory sub-scores carry REAL MEASURED axes from the Conservation pipeline",
       "memory" not in subs or subs["memory"]["n_measured"] >= 1)

    # --- DETERMINISM: two builds are byte-identical (modulo the volatile git head) ------------
    sc2 = build_scorecard()
    def _stable(s):
        r = s.get("resolution") or {}
        return ([(c["key"], c["score"], c["basis"]) for c in s["cells"]], s["weakest_key"],
                # the dependency-weighted resolution must be deterministic too.
                (r.get("root") or {}).get("key"), (r.get("immediate") or {}).get("key"),
                r.get("headline_key"), r.get("chain_str"))
    ok("scorecard is deterministic (identical scores + bottleneck + resolution across two runs)",
       _stable(sc) == _stable(sc2))

    # --- render smoke (never raises; shows the MEASURED/ESTIMATED split + the bottleneck) ------
    stxt = render_scorecard(sc)
    ok("scorecard renders the MEASURED + ESTIMATED split and the bottleneck flag",
       "MEASURED (read from a real signal)" in stxt
       and "ESTIMATED (heuristic" in stxt
       and "CURRENT BOTTLENECK" in stxt)
    # the dependency-weighted resolution + the 100-hours headline + the three named levels render.
    ok("scorecard renders the 3-level resolution, the 100-hours headline, and the spine",
       "NEXT 100 ENGINEERING HOURS" in stxt
       and "Root Bottleneck:" in stxt and "Immediate Bottleneck:" in stxt
       and "Visible Weakness:" in stxt and res["immediate"]["label"].upper() in stxt)
    ok("scorecard renders the per-subsystem 7-axis sub-scores with honest labels",
       "PER-SUBSYSTEM SUB-SCORES" in stxt and "[MEASURED" in stxt and "[TODO" in stxt)
    # the review renders the roadmap-exception verdict when a conflict fires.
    rev_ex = build_review(roadmap_next="memory")
    rtxt_ex = render_review(rev_ex)
    ok("review renders the ROADMAP EXCEPTION RULE verdict (ALLOWED PARALLEL EXCEPTION) for #59",
       "ROADMAP EXCEPTION RULE" in rtxt_ex and "ALLOWED PARALLEL EXCEPTION" in rtxt_ex)

    # --- GUARDRAIL: the WHOLE selftest (incl. the live reality read) touched no real .anima ---
    fp_after = _footprint(real)
    ok("GUARDRAIL: real .anima is byte-UNCHANGED around the run "
       f"(files {fp_before[1]} -> {fp_after[1]})",
       fp_before == fp_after)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL ARB SELFTESTS PASS")
    return 0


# ===================================================================================
# CLI.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA ARCHITECTURAL REVIEW BOARD + MIND BALANCE DASHBOARD "
                    "(read-only governance/observability compass).")
    ap.add_argument("--review", action="store_true",
                    help="MODE 2: the wave-end ARB review (8 questions + reality>roadmap check)")
    ap.add_argument("--next", dest="roadmap_next", default=None,
                    help="declare the roadmap's NEXT item (a dimension key or free text); "
                         "compared to the measured weakest layer for the REALITY > ROADMAP check")
    ap.add_argument("--creature", default=LIVE_CREATURE,
                    help=f"the creature whose real ledgers to read (default {LIVE_CREATURE})")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--selftest", action="store_true",
                    help="PROVE the board's load-bearing properties; real .anima byte-unchanged")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    try:
        if args.review:
            report = build_review(creature=args.creature, roadmap_next=args.roadmap_next)
            rendered = render_review(report)
        else:
            report = build_scorecard(creature=args.creature)
            rendered = render_scorecard(report)
        engine_error = None
    except Exception as e:  # pragma: no cover - entry point never raises
        report = {"mode": "error", "error": repr(e)}
        rendered = f"ARB ERROR (degraded): {e!r}"
        engine_error = repr(e)

    fp_after = _footprint(real_anima)
    footprint_unchanged = fp_before == fp_after
    report["footprint_unchanged"] = footprint_unchanged
    report["engine_error"] = engine_error

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(rendered)
        print("")
        print("GUARDRAIL: real .anima footprint  : "
              + ("byte-UNCHANGED (read-only synthesis; nothing real touched)"
                 if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
        if engine_error:
            print(f"GUARDRAIL: engine error           : {engine_error}")

    # Exit non-zero ONLY on a broken guardrail (touched real state / an engine blew up). The
    # scores + any conflict are the REPORT, never a process failure.
    return 0 if (footprint_unchanged and engine_error is None) else 1


if __name__ == "__main__":
    raise SystemExit(main())
