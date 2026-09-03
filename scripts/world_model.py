#!/usr/bin/env python3
"""VERA WORLD-MODEL OBSERVATORY — "how do the pieces CAUSE each other?" (the causal-model lens).

The other observatories read a moment, a feeling, or a single epistemic loop. scripts/reality.py
renders the COMPETING hypotheses a situation spawns and how reality adjudicates them. This one
renders the layer ABOVE that — the CAUSAL MODEL the creature builds OVER the whole situation: not
"manager changed" and "sleep worsened" as two stranded facts, but the chain that connects them —

        manager_change --(0.55)--> strain --(0.67)--> poor_sleep --(0.94)--> low_energy

a directed graph of NODES and TYPED, CONFIDENCE-WEIGHTED causal EDGES. It reads anima/world_model.py
and renders:

  1. THE MODEL, per domain — the nodes, the typed causal links with their confidence, and (the
     point) the through-LINES: the longest causal chains, so you can see the reasoning span the
     chain instead of four isolated memories.

  2. THE GROUNDING — for EVERY edge, the OBSERVED evidence it rests on (a stated world-state edge,
     a reality competing-hypothesis, repeated co-occurrence). An ungrounded causal edge is NEVER
     emitted; this dashboard makes the grounding auditable.

  3. THE EVOLUTION — when reality RESOLVES an outcome, an edge's confidence shifts (a confirmed
     link strengthens, a contradicted one weakens). The observatory shows the before -> after diff,
     so "how the model changed when reality came in" is visible.

────────────────────────────────────────────────────────────────────────────────────────────
WHY A MODEL, NOT JUST A GRAPH  +  WHY GROUNDED  +  WHY EVOLVING
────────────────────────────────────────────────────────────────────────────────────────────
A GRAPH (world_state) stores RELATIONS the user stated. A MODEL is a THEORY of those relations —
a small causal structure you can REASON ACROSS and REVISE. It is GROUNDED: every edge cites the
observed evidence and a confidence that reflects that evidence's strength; we never invent
causation (the #1 rule, lifted from world_state.capture's never-infer discipline). It EVOLVES:
reality.resolve feeds outcomes that strengthen confirmed links and weaken contradicted ones, so
the model sharpens over real calendar time.

────────────────────────────────────────────────────────────────────────────────────────────
INTERNAL ONLY — NO DIAGNOSIS / NEVER ASSERTED AT THE USER  (LAW-level)
────────────────────────────────────────────────────────────────────────────────────────────
A world model is an INTERNAL model of the USER's SITUATION — it must NEVER be spoken or diagnosed
at the user ("your manager is causing your insomnia"). Every model is flagged internal_only; this
observatory only READS the models. Every rendered line passes anima/world_model.py's no-diagnosis
clean-gate (the SAME wall anima/reality.py + anima/trajectory.py use), defence in depth. The
header LEGITIMATELY names "diagnosis" in order to FORBID it, so the no-diagnosis assertion inspects
the GENERATED body (the causal lines), not the fixed legend — exactly as scripts/reality.py and
anima/trajectory.py do. This module never touches identity (frozen until 2026-07-03), mouth.respond,
server._turn, or the live reply.

────────────────────────────────────────────────────────────────────────────────────────────
GUARDRAILS  (identical posture to scripts/reality.py / scripts/relationship.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * --selftest is SYNTHETIC-only + HERMETIC. It builds the manager -> strain -> poor_sleep ->
    low_energy model in a throwaway temp dir with EVERY engine STORE redirected there
    (world_model.STORE + world_state/reality/meaning/memory_lirf/curiosity/constitution/telemetry/
    cloud STORE, reliability.DEFAULT_STORE), and asserts the real .anima footprint is byte-UNCHANGED
    around the run.
  * --real is STRICTLY READ-ONLY on Vera's world-model store. It reads .anima/{name}.worldmodel.json
    via world_model.models(), writes/mutates NOTHING, and asserts the real .anima is byte-identical
    start->end. A change is a GUARDRAIL BREACH (non-zero exit), never silently tolerated.
  * ADDITIVE — STANDALONE. Imports + reads anima/world_model.py; edits NO module (other agents run
    in parallel; cert wiring is a later consolidation pass). The only file this adds is
    scripts/world_model.py.
  * Never raises out of an entry point — a malformed store yields an honest empty render.

    python3 scripts/world_model.py             # human-readable causal model + grounding + evolution
    python3 scripts/world_model.py --json        # machine-readable
    python3 scripts/world_model.py --selftest     # PROVE a grounded causal model builds + evolves
    python3 scripts/world_model.py --real         # render Vera's REAL models, STRICTLY READ-ONLY

Exit code is 0 when the selftest's checks hold and the synthetic-only / read-only guardrail held;
non-zero on a missed check or a breached guardrail.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import secrets
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from anima import world_model  # noqa: E402  (the engine this observatory renders)

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "worldmodel_synth"

# Identity is FROZEN until this date. This observatory never reads/writes identity at all; the
# date is surfaced for parity with the sibling observatories' posture.
IDENTITY_FROZEN_UNTIL = "2026-07-03"


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect + footprint hash. Mirrors scripts/reality.py
# (_STORE_TARGETS / _temp_store / _footprint): redirect EVERY engine STORE the synthetic build
# could write to ONE throwaway dir so a build_model_from_graph (and the world/reality seeding it
# does, incl. any LAW-001 backup / continuity write) can never leak into the real .anima.
#
# A redirect target is a (module-import-path, store-attr) pair because reliability's store attr is
# DEFAULT_STORE, not STORE. Resolved by NAME so importing this module never hard-depends on every
# engine; a missing one is simply skipped.
# ===================================================================================
_STORE_TARGETS = (
    ("anima.world_model", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.reality", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.memory_lirf", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.constitution", "STORE"),           # the continuity ledger a good load/save writes
    ("anima.reliability", "DEFAULT_STORE"),     # guarded-backup snapshots
    ("anima.telemetry", "STORE"),
    ("anima.cloud", "STORE"),
)


def _resolve_store_targets():
    """Resolve ``_STORE_TARGETS`` to live ``(module, attr)`` pairs that carry the attribute right
    now. A module that won't import, or that lacks the attr, is skipped — so the redirect set
    adapts to whatever is built without ever hard-failing."""
    pairs = []
    seen = set()
    for modpath, attr in _STORE_TARGETS:
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, attr) and (id(mod), attr) not in seen:
            pairs.append((mod, attr))
            seen.add((id(mod), attr))
    return pairs


@contextlib.contextmanager
def _temp_store():
    """Redirect EVERY engine STORE binding to one fresh temp dir for the duration, so nothing under
    the real .anima/ is ever read or written. Restored on exit. HERMETIC by construction: a leak is
    impossible regardless of which engine the synthetic build writes through. Yields the temp Path."""
    import tempfile
    targets = _resolve_store_targets()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-worldmodel-") as td:
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


def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (EXCLUDING the rotating backups/ dir, which
    legitimately changes), so we can PROVE the harness touched nothing. Verbatim from
    scripts/reality.py / scripts/relationship.py."""
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
# RENDER — the human-readable causal-model dashboard: the model (nodes + typed weighted edges +
# the causal chains), the grounding (each edge's evidence), and the evolution (the before->after
# diff a resolved outcome produced). Reads ONLY anima/world_model.py; every line passes the
# no-diagnosis gate.
# ===================================================================================

def _clean(s: str) -> str:
    """Run a line through world_model's no-diagnosis clean-gate; substitute a neutral note if it
    ever trips (defence in depth — this is internal model-state, never a user-facing claim)."""
    return world_model._safe_statement(s, "    (an internal model note)")


def _conf_bar(c, width: int = 10) -> str:
    """A tiny ASCII gauge for a causal-edge confidence in [0,1]."""
    if not isinstance(c, (int, float)):
        return "▕" + "·" * width + "▏"
    filled = int(round(max(0.0, min(1.0, c)) * width))
    return "▕" + "█" * filled + "·" * (width - filled) + "▏"


def _render_model(model: dict) -> str:
    """Render ONE causal model — the chains (longest first), then every typed weighted link with
    the OBSERVED evidence it rests on. The whole point: a chain you can reason across, grounded."""
    if not isinstance(model, dict) or not model.get("edges"):
        return ("    (no grounded model — this domain has no stated causal edges and no\n"
                "     competing hypotheses yet; an ungrounded model is never fabricated.)")
    out = []
    label = world_model._label
    out.append(f"  DOMAIN: {label(model.get('topic', '?'))}   "
               f"({len(model.get('nodes', []))} nodes · {len(model.get('edges', []))} causal links)")
    out.append(f"  grounded by: {model.get('grounding')}")

    out.append("")
    out.append("  CAUSAL THROUGH-LINES (longest first — reason ACROSS the chain, not one link):")
    chains = world_model.causal_chains(model)
    if not chains:
        out.append("    (no multi-step chain yet — the links haven't connected into a path)")
    for ch in chains:
        sent = world_model._chain_sentence(ch)
        mc = world_model._mean_conf(ch)
        # the compact arrow form too, so the structure is visible at a glance.
        arrow = "  →  ".join([label(ch[0]["src"])]
                             + [f"{label(e['dst'])} ({float(e['confidence']):.2f})" for e in ch])
        out.append(_clean(f"    • {arrow}"))
        out.append(_clean(f"        i.e. {sent}   (mean confidence {mc:.2f})"))

    out.append("")
    out.append("  EACH LINK, WITH ITS GROUNDING (the observed evidence — never invented):")
    for e in sorted(model.get("edges", []), key=lambda x: (-float(x["confidence"]), x["src"])):
        bar = _conf_bar(float(e.get("confidence", 0)))
        out.append(_clean(
            f"    {label(e['src'])} --[{e['relation']}]--> {label(e['dst'])}"
            f"   {bar} {float(e['confidence']):.2f}   (support {e.get('support', 1)})"))
        for ev in e.get("evidence", [])[:4]:
            out.append(f"        ↳ {ev}")
        if e.get("history"):
            last = e["history"][-1]
            out.append(_clean(
                f"        ↳ revised by reality: {last.get('before')} → {last.get('after')}  "
                f"({last.get('reason', '')})"))
    return "\n".join(out)


def _render_evolution(diff: dict) -> str:
    """Render the model's evolution under a resolved outcome — the before->after confidence diff."""
    if not isinstance(diff, dict) or not (diff.get("strengthened") or diff.get("weakened")
                                          or diff.get("appeared") or diff.get("disappeared")):
        return "    (no evolution yet — the model sharpens as reality resolves outcomes over time.)"
    return world_model.render_comparison(diff)


def render(report: dict) -> str:
    out = []
    out.append("=" * 88)
    out.append("VERA WORLD-MODEL OBSERVATORY — from facts to CAUSAL MODELS")
    out.append("Not 'manager changed' + 'sleep worsened' as two stranded facts, but the CHAIN that")
    out.append("connects them:  manager_change → strain → poor_sleep → low_energy  — a directed graph")
    out.append("of typed, confidence-weighted causal links you can REASON ACROSS and REVISE.")
    out.append("=" * 88)
    out.append("")
    out.append("GROUNDED: every causal link cites the OBSERVED evidence it rests on (a stated world-")
    out.append("state edge, a reality competing-hypothesis, repeated co-occurrence) and a confidence")
    out.append("that reflects that evidence. An ungrounded causal link is NEVER emitted — we never")
    out.append("invent causation (#1 rule).")
    out.append("")
    out.append("EVOLVING: when reality RESOLVES an outcome, a confirmed link strengthens and a")
    out.append("contradicted one weakens — the model sharpens over real calendar time.")
    out.append("")
    out.append("INTERNAL ONLY: a world model is an internal model of the USER's situation — NEVER")
    out.append("spoken or diagnosed at them (\"your manager is causing your insomnia\" is FORBIDDEN).")
    out.append("Every model is internal_only; this observatory only reads them; every generated line")
    out.append("passes the no-diagnosis gate. It never alters the live reply.")
    out.append("")
    src = report.get("source_note")
    if src:
        out.append(f"MODEL SOURCE: {src}")
        out.append("")

    out.append("─" * 88)
    out.append("THE CAUSAL MODEL(S)")
    out.append("─" * 88)
    ms = report.get("models") if isinstance(report, dict) else None
    if not ms:
        out.append("    (no models yet — they emerge from stated situations + how reality resolves")
        out.append("     them; an ungrounded model is never fabricated.)")
    for m in (ms or []):
        out.append("")
        out.append(_render_model(m))

    diff = report.get("evolution")
    if diff is not None:
        out.append("")
        out.append("─" * 88)
        out.append("MODEL EVOLUTION — how the model changed when reality resolved an outcome")
        out.append("─" * 88)
        out.append(_render_evolution(diff))
    return "\n".join(out)


def render_body(report: dict) -> str:
    """The GENERATED content of the dashboard — the model + evolution lines built FROM the store
    (the only lines that could ever carry a model inference) — WITHOUT the fixed header.

    Why this exists: the header LEGITIMATELY names banned words in order to FORBID them ("never
    spoken or diagnosed at them", "your manager is causing your insomnia"), exactly as
    anima/trajectory.py's preamble + scripts/reality.py's header do. So a 'no-diagnosis' assertion
    must inspect the GENERATED body, not the fixed legend. Pure; never raises."""
    ms = report.get("models") if isinstance(report, dict) else None
    parts = [_render_model(m) for m in (ms or [])]
    diff = report.get("evolution")
    if diff is not None:
        parts.append(_render_evolution(diff))
    return "\n".join(parts)


# ===================================================================================
# THE DEMO REPORT (default human/JSON view) — build the synthetic manager -> strain -> poor_sleep
# -> low_energy model through anima/world_model.py's real engine, hermetically, so the default
# invocation shows a real, GROUNDED, EVOLVING causal model.
# ===================================================================================

def demo_report() -> dict:
    """Build the synthetic causal model in a hermetic temp store through the real engine, read it +
    its evolution diff, and package a report for the default human/JSON view. Never raises —
    degrades to an empty model."""
    try:
        with _temp_store():
            name = f"{SYNTH}_{secrets.token_hex(3)}"
            built = world_model.build_synthetic_model(name)
            data = {"models": [built.get("model")], "evolution": built.get("diff")}
    except Exception:
        data = {"models": [], "evolution": None}
    return {
        "models": data.get("models", []),
        "evolution": data.get("evolution"),
        "source_note": ("SYNTHETIC demo model (a STATED situation — 'work stressful because my new "
                        "manager', 'the stress is affecting my sleep', sleep → low energy — plus "
                        "reality's COMPETING stress hypotheses, fused into manager_change → strain "
                        "→ poor_sleep → low_energy, then EVOLVED by a resolved 'barely slept' "
                        "outcome) built through the real engine in a hermetic temp store. Run --real "
                        "to render Vera's ACTUAL models, read-only."),
        "identity_frozen_until": IDENTITY_FROZEN_UNTIL,
    }


# ===================================================================================
# --real — render VERA's ACTUAL causal models, STRICTLY READ-ONLY. Reads
# .anima/{name}.worldmodel.json via world_model.models(), and asserts the real .anima is
# byte-UNCHANGED start->end. Writes NOTHING. (models() is a pure store READ.)
# ===================================================================================

def real_report(name: str = "Vera", store: Path | None = None) -> dict:
    """Render Vera's REAL causal models, STRICTLY READ-ONLY, and PROVE the real .anima was
    byte-unchanged around the run. Returns a report with the models + the read-only proof. Never
    raises."""
    store = Path(store) if store is not None else (_ROOT / ".anima")
    saved = getattr(world_model, "STORE", None)
    fp_before = _footprint(store)
    try:
        world_model.STORE = store
        try:
            ms = world_model.models(name)
            err = None
        except Exception as e:  # pragma: no cover - --real never raises
            ms = []
            err = repr(e)
    finally:
        if saved is not None:
            world_model.STORE = saved
    fp_after = _footprint(store)
    unchanged = fp_before == fp_after
    return {
        "models": ms,
        "evolution": None,
        "source_note": (f"Vera's REAL causal models (.anima/{name}.worldmodel.json), STRICTLY "
                        "READ-ONLY."),
        "identity_frozen_until": IDENTITY_FROZEN_UNTIL,
        "real": True,
        "real_anima_byte_unchanged": unchanged,
        "real_anima_files_before": fp_before[1],
        "real_anima_files_after": fp_after[1],
        "engine_error": err,
    }


# ===================================================================================
# SELFTEST — PROVE a GROUNDED causal model builds + evolves on a synthetic situation,
# DETERMINISTICALLY, and that the synthetic-only / read-only guardrail holds (real .anima
# byte-unchanged). No model, no network.
# ===================================================================================

def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("VERA WORLD-MODEL OBSERVATORY self-test")

    real = _ROOT / ".anima"
    fp0 = _footprint(real)

    # === build the canonical model, hermetically, TWICE (also prove a stable shape) ============
    def _build():
        with _temp_store():
            nm = f"{SYNTH}_{secrets.token_hex(3)}"
            built = world_model.build_synthetic_model(nm)
            # snapshot the stored models too (prove the store round-trips inside the temp dir).
            stored = world_model.models(nm)
            return built, stored

    built_a, stored_a = _build()
    built_b, stored_b = _build()
    model = built_a["model"]

    # === THE MODEL BUILT: nodes + typed weighted causal edges ==================================
    ok("BUILD: a non-empty causal model was constructed (nodes + edges)",
       isinstance(model, dict) and len(model.get("edges", [])) > 0
       and len(model.get("nodes", [])) > 1)
    ok("BUILD: the model is flagged internal_only (LAW — never asserted/diagnosed at the user)",
       model.get("internal_only") is True)
    ok("BUILD: every edge is TYPED + CONFIDENCE-WEIGHTED",
       all(e.get("relation") in world_model.RELATION_TYPES
           and 0.0 <= float(e.get("confidence", -1)) <= 1.0 for e in model["edges"]))

    # === THE CAUSAL CHAIN: manager_change → strain → poor_sleep → low_energy ====================
    nodes = set(model.get("nodes", []))
    ok("CHAIN: the manager_change cause node is in the model (upstream)",
       "manager_change" in nodes or any("manager" in n for n in nodes))
    ok("CHAIN: a strain node is reached", "strain" in nodes)
    ok("CHAIN: a sleep node is reached", any("sleep" in n for n in nodes))
    ok("CHAIN: a downstream energy node is reached", any("energy" in n for n in nodes))
    chains = world_model.causal_chains(model)
    longest = chains[0] if chains else []
    ok("CHAIN: a multi-hop causal through-line exists (>= 3 links — reasoning ACROSS the chain)",
       bool(longest) and len(longest) >= 3)

    # === GROUNDED: every edge cites OBSERVED evidence + a grounding source ======================
    ok("GROUNDED: EVERY edge carries a grounding source (world-edge or reality hypothesis)",
       all(any(s in (world_model.SRC_WORLD_EDGE, world_model.SRC_REALITY_HYP)
               for s in e.get("sources", [])) for e in model["edges"]))
    ok("GROUNDED: EVERY edge cites at least one concrete piece of evidence",
       all(len(e.get("evidence", [])) >= 1 for e in model["edges"]))
    ok("GROUNDED: at least one link comes from a STATED world-graph edge",
       any(world_model.SRC_WORLD_EDGE in e.get("sources", []) for e in model["edges"]))
    ok("GROUNDED: at least one link comes from a reality COMPETING HYPOTHESIS",
       any(world_model.SRC_REALITY_HYP in e.get("sources", []) for e in model["edges"]))
    ok("GROUNDED: NO edge is grounded by co-occurrence ALONE (corroboration only)",
       all(set(e.get("sources", [])) != {world_model.SRC_COOCCURRENCE} for e in model["edges"]))

    # === THE NEGATIVE PROOF — an UNGROUNDED domain yields NO causal edges (never invent) ========
    with _temp_store():
        ung = world_model.build_model_from_graph("nobody_" + secrets.token_hex(2),
                                                 "photosynthesis", persist=False)
    ok("UNGROUNDED: a domain with no stated edges + no hypotheses yields ZERO edges",
       len(ung.get("edges", [])) == 0)

    # === EVOLUTION: a resolved outcome shifted an edge confidence (strengthen), diffed ==========
    diff = built_a["diff"]
    evolved = built_a["evolved"]
    ok("EVOLUTION: the resolved outcome STRENGTHENED a causal link (before->after diff)",
       len(diff.get("strengthened", [])) >= 1
       and all(r["delta"] > 0 for r in diff["strengthened"]))
    ok("EVOLUTION: the strengthened link is the sleep consequence edge",
       any("poor" in r["edge"] and "sleep" in r["edge"] for r in diff["strengthened"]))
    ok("EVOLUTION: the shift is recorded append-only in the edge history",
       any(e.get("history") for e in evolved.get("edges", [])))
    ok("EVOLUTION: the evolved model is still internal_only", evolved.get("internal_only") is True)

    # === the store round-tripped inside the hermetic temp dir ==================================
    ok("STORE: the built model round-tripped through its own .worldmodel.json store",
       any(m.get("id") == model.get("id") for m in stored_a))

    # === DETERMINISM: the model's shape is identical across two independent hermetic builds =====
    def _shape(built):
        m = built["model"]
        d = built["diff"]
        return {
            "n_nodes": len(m.get("nodes", [])),
            "n_edges": len(m.get("edges", [])),
            "edge_keys": sorted((e["src"], e["dst"], e["relation"]) for e in m.get("edges", [])),
            "nodes": sorted(m.get("nodes", [])),
            "n_strengthened": len(d.get("strengthened", [])),
            "n_weakened": len(d.get("weakened", [])),
        }
    ok("DETERMINISM: two independent hermetic builds produce the same model shape",
       json.dumps(_shape(built_a), sort_keys=True) == json.dumps(_shape(built_b), sort_keys=True))

    # === RENDER: non-empty, names the model + the chain + grounding + evolution, no diagnosis ===
    rep = demo_report()
    txt = render(rep)
    ok("render: produces a non-empty dashboard", bool(txt.strip()))
    ok("render: names the model, the causal chain, and the grounding",
       "CAUSAL MODEL" in txt and "THROUGH-LINE" in txt.upper()
       and "GROUNDING" in txt.upper())
    ok("render: shows the manager_change → strain → poor_sleep chain structure",
       "manager_change" in txt and "strain" in txt and "poor sleep" in txt)
    ok("render: shows the EVOLUTION (the before->after the outcome produced)",
       "EVOLUTION" in txt and ("strengthened" in txt.lower() or "→" in txt))
    ok("render: states the model is INTERNAL ONLY (never spoken / never diagnosed at the user)",
       "INTERNAL ONLY" in txt and "never alters the live reply" in txt)
    ok("render: carries the GROUNDED + EVOLVING framing",
       "GROUNDED" in txt and "EVOLVING" in txt)
    # The no-diagnosis gate inspects the GENERATED body (the model + evolution lines built from the
    # store), NOT the fixed header — which legitimately NAMES "diagnosis" in order to FORBID it,
    # exactly as anima/trajectory.py inspects its items, not its banned-word-naming preamble.
    ok("NO-DIAGNOSIS GATE: not one GENERATED body line trips a banned term",
       all(world_model._is_clean(ln) for ln in render_body(rep).splitlines()))
    ok("NO-DIAGNOSIS: the header that NAMES 'diagnosis' to forbid it is fixed framing, not data",
       not world_model._is_clean("your manager is causing your insomnia")
       and "diagnos" in txt.lower())

    # === the empty-store render is honest (no fabricated model) =================================
    with _temp_store():
        empty_rep = {"models": world_model.models("nobody_" + secrets.token_hex(2)),
                     "evolution": None, "source_note": "empty"}
        empty_txt = render(empty_rep)
    ok("render(empty): honest 'no models yet', no fabricated causation",
       "no models yet" in empty_txt.lower())

    # === ROBUSTNESS: garbage reports never raise ===============================================
    try:
        render({})
        render({"models": None})
        render({"models": [{"edges": None}], "evolution": {}})
        render_body({"models": [None]})
        crashed = False
    except Exception as e:  # noqa: BLE001
        crashed = True
        print("       (raised:", repr(e), ")")
    ok("robust: garbage/empty report renders without raising", not crashed)

    # === --json shape is serialisable ==========================================================
    try:
        json.dumps(demo_report(), default=str)
        serialisable = True
    except Exception:
        serialisable = False
    ok("--json: the demo report serialises cleanly", serialisable)

    # === --real is STRICTLY READ-ONLY: running it leaves real .anima byte-unchanged ============
    rr = real_report("Vera", store=real)
    ok("--real: ran and produced a report shape", isinstance(rr, dict) and "models" in rr)
    ok("--real: real .anima reported byte-UNCHANGED around the run",
       rr.get("real_anima_byte_unchanged") is True)

    # === GUARDRAIL: the WHOLE selftest (incl. --real) touched no real .anima file ==============
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the entire selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature store leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL WORLD-MODEL-OBSERVATORY SELFTESTS PASS")
    return 0


# ===================================================================================
# MAIN — human-readable (default) or --json; --selftest; --real (read-only on real Vera).
# ===================================================================================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA WORLD-MODEL OBSERVATORY — the causal model (nodes + typed, confidence-"
                    "weighted edges) built over a situation, with grounding + evolution.")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--real", action="store_true",
                    help="render Vera's ACTUAL causal models, STRICTLY READ-ONLY")
    ap.add_argument("--name", default="Vera", help="creature name for --real (default Vera)")
    ap.add_argument("--selftest", action="store_true",
                    help="PROVE a grounded causal model builds + evolves (deterministic, hermetic)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.real:
        report = real_report(args.name, store=_ROOT / ".anima")
    else:
        report = demo_report()

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        if report.get("real"):
            print("")
            print("=" * 88)
            unchanged = report.get("real_anima_byte_unchanged")
            print("GUARDRAIL (--real): real .anima  : "
                  + ("byte-UNCHANGED — strictly read-only; Vera's real state was never touched"
                     if unchanged else "CHANGED — GUARDRAIL BREACH (this should be impossible in --real)"))
            print(f"                    files seen   : {report.get('real_anima_files_before')} "
                  f"(before) / {report.get('real_anima_files_after')} (after)")
            if report.get("engine_error"):
                print(f"                    engine error : {report['engine_error']}")

    # exit non-zero only if --real breached the read-only guarantee (the default/demo always 0).
    if report.get("real") and report.get("real_anima_byte_unchanged") is not True:
        return 1
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
