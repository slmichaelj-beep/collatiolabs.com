#!/usr/bin/env python3
"""
certify_world_model — FROM CAPTURED FACTS TO A GROUNDED, RETRIEVABLE CAUSAL MODEL (internal-only).

world_model is the leap from a flat graph of remembered facts to a CAUSAL MODEL of a domain. This
certifies that contract end-to-end through the SAME public functions the engine + its observatory
call — hermetically, offline (no live model, no network):

  A. FACTS -> MODEL — from captured situation-facts ("work's stressful because of my new manager",
     "the stress is affecting my sleep", sleep -> low energy) plus a seeded+resolved reality
     competition (manager_change leading, sleep_decline confirmed), build_model_from_graph builds a
     NON-EMPTY causal model carrying the manager_change -> strain -> poor_sleep -> low/energy chain,
     flagged internal_only (LAW 2).
  B. GROUNDED — NO INVENTED CAUSATION (#1 rule): EVERY edge carries a world-edge or reality-
     hypothesis grounding source AND >=1 concrete piece of evidence; >=1 edge comes from a STATED
     world-graph edge and >=1 from a reality COMPETING HYPOTHESIS; NO edge rests on co-occurrence
     alone (corroboration only). The model records a per-source grounding tally.
  C. NEGATIVE — an UNGROUNDED domain (photosynthesis) and an UNRELATED topic on the real creature
     yield ZERO fabricated edges/nodes (never invent).
  D. RETRIEVABLE — causal_chains yields a >=3-hop through-line from an upstream cause to a downstream
     consequence; the built model ROUND-TRIPS by id through its OWN .worldmodel.json store
     (get_model); a SECOND build is ADDED, not overwritten (additive continuity).
  E. LEARNS — a CONFIRMED sleep_decline outcome STRENGTHENS strain->poor_sleep with an append-only
     history entry (before->after); a CONTRADICTED one WEAKENS it (floored, never annihilated); the
     input snapshot is left untouched; compare_models reports the strengthened link.
  F. INTERNAL-ONLY + NO DIAGNOSIS — explain_model names it an INTERNAL model; every GENERATED body
     line passes the no-diagnosis clean-gate; and anima.world_model is imported by NOTHING in
     server.py / route.py / mouth.py (the shadow-model invariant: it never speaks at the user).

Hermetic: every store (world_model/world_state/reality/meaning/memory_lirf via _temp_store, plus
constitution/reliability redirected here) points at a temp dir; the real .anima is fingerprinted
before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def _edge(model: dict, src: str, dst: str):
    return next((e for e in model.get("edges", []) if e["src"] == src and e["dst"] == dst), None)


def main() -> int:
    from anima import world_model as wm
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("WORLD MODEL — captured facts -> a grounded, retrievable causal model (internal-only)")
    print("=" * 84)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # F-static (pure, store-free): the no-diagnosis clean-gate + the shadow-model import invariant.
    ck("F0: the no-diagnosis clean-gate clears a neutral causal phrase and CATCHES a diagnosis",
       wm._is_clean("a recent change is upstream of strain, which is reaching rest")
       and not wm._is_clean("your manager is causing your insomnia")
       and not wm._is_clean("you will spiral"))
    # The SHADOW-model invariant is about IMPORTS, not incidental substrings: server.py mentions the
    # bare string "world_model" only as a TRACE DICT KEY (it counts world_STATE edges, not this
    # module) — that is not a wire. So we check for an actual IMPORT of anima.world_model.
    import re as _re
    _IMPORT_PATTERNS = (
        _re.compile(r"^\s*import\s+world_model\b", _re.M),
        _re.compile(r"^\s*from\s+\.\s+import\s+[^\n]*\bworld_model\b", _re.M),
        _re.compile(r"^\s*from\s+\.world_model\s+import\b", _re.M),
        _re.compile(r"^\s*from\s+anima\s+import\s+[^\n]*\bworld_model\b", _re.M),
        _re.compile(r"^\s*from\s+anima\.world_model\s+import\b", _re.M),
        _re.compile(r"\banima\.world_model\b", _re.M),
        _re.compile(r"\bimport_module\(\s*['\"][^'\"]*world_model['\"]", _re.M),
    )
    server_src = (ROOT / "anima" / "server.py").read_text()
    route_src = (ROOT / "anima" / "route.py").read_text()
    mouth_src = (ROOT / "anima" / "mouth.py").read_text()
    shadow = not any(p.search(s) for s in (server_src, route_src, mouth_src) for p in _IMPORT_PATTERNS)
    ck("F1: anima.world_model is IMPORTED by NOTHING on the live reply path "
       "(server/route/mouth) — a SHADOW model, never asserted at the user", shadow)

    with _temp_store() as tp:
        # also redirect the stores _temp_store doesn't cover (guarded-load side effects + the
        # world/reality/meaning substrate stores), matching the selftest's redirect set. Restore in
        # finally so nothing leaks into the real tree.
        extra = []
        for modname, attr in (("anima.world_model", "STORE"),
                              ("anima.world_state", "STORE"),
                              ("anima.reality", "STORE"),
                              ("anima.meaning", "STORE"),
                              ("anima.memory_lirf", "STORE"),
                              ("anima.constitution", "STORE"),
                              ("anima.reliability", "DEFAULT_STORE")):
            try:
                m = __import__(modname, fromlist=["_"])
                if getattr(m, attr, None) is not None:
                    extra.append((m, attr, getattr(m, attr)))
                    setattr(m, attr, tp)
            except Exception:
                pass
        try:
            import secrets
            N = "WMCert_" + secrets.token_hex(3)

            # ---- A. FACTS -> MODEL -----------------------------------------------------
            # build_synthetic_model seeds the WORLD graph (capture_relations of the stated
            # situation) + the REALITY loop (form the competing hypotheses, resolve Day-14), then
            # builds the grounded model — the SAME helper the observatory uses. This is the
            # captured-facts -> causal-model path, run for real.
            built = wm.build_synthetic_model(N)
            model = built["model"]
            ck("A1: the captured facts were laid down (world graph seeded + reality resolved)",
               built["world_seeded"] and built["reality_resolved"])
            ck("A2: build_model_from_graph built a NON-EMPTY causal model from those facts",
               isinstance(model, dict) and len(model.get("edges", [])) > 0
               and len(model.get("nodes", [])) > 1)
            ck("A3: the model is flagged internal_only (LAW 2 — never asserted at the user)",
               model.get("internal_only") is True)
            ck("A4: the causal CHAIN spans the situation (a manager node, a strain node, a sleep "
               "node, an energy node)",
               any("manager" in n for n in model.get("nodes", []))
               and "strain" in model.get("nodes", [])
               and any("sleep" in n for n in model.get("nodes", []))
               and any("energy" in n for n in model.get("nodes", [])))

            # ---- B. GROUNDED — NO INVENTED CAUSATION -----------------------------------
            edges = model.get("edges", [])
            ck("B1: EVERY edge carries a grounding source (a stated world-edge or a reality hypothesis)",
               all(any(s in (wm.SRC_WORLD_EDGE, wm.SRC_REALITY_HYP) for s in e.get("sources", []))
                   for e in edges))
            ck("B2: EVERY edge cites at least one concrete piece of evidence",
               all(len(e.get("evidence", [])) >= 1 for e in edges))
            ck("B3: at least one link comes from a STATED world-graph edge",
               any(wm.SRC_WORLD_EDGE in e.get("sources", []) for e in edges))
            ck("B4: at least one link comes from a reality COMPETING HYPOTHESIS",
               any(wm.SRC_REALITY_HYP in e.get("sources", []) for e in edges))
            ck("B5: the manager_change hypothesis became a grounded cause UPSTREAM of strain",
               any(e["src"] == "manager_change" and e["dst"] == "strain"
                   and wm.SRC_REALITY_HYP in e.get("sources", []) for e in edges))
            ck("B6: NO edge rests on co-occurrence ALONE (corroboration only, never grounding)",
               all(set(e.get("sources", [])) != {wm.SRC_COOCCURRENCE} for e in edges))
            grounding = model.get("grounding", {})
            ck("B7: the model records a per-source grounding tally (auditable)",
               isinstance(grounding, dict)
               and grounding.get(wm.SRC_REALITY_HYP, 0) >= 1
               and (grounding.get(wm.SRC_WORLD_EDGE, 0)
                    + grounding.get(wm.SRC_REALITY_HYP, 0)) >= len(edges))

            # ---- C. NEGATIVE — an UNGROUNDED domain emits NO fabricated causation -------
            # use a FRESH, never-seeded creature: with no stated edges AND no reality competitions
            # in the ledger, the model must come back empty (the reality gatherer walks the WHOLE
            # ledger, so a seeded creature would surface its competitions for any topic — exactly
            # why this proof needs a clean slate, matching the module selftest).
            ungrounded_name = "WMCert_empty_" + secrets.token_hex(3)
            ung = wm.build_model_from_graph(ungrounded_name, "photosynthesis", persist=False)
            ck("C1: a creature with no stated edges + no hypotheses yields ZERO edges (never invent)",
               len(ung.get("edges", [])) == 0 and len(ung.get("nodes", [])) == 0)
            unrel = wm.build_model_from_graph(N, "astronomy", persist=False)
            ck("C2: an unrelated topic on the REAL creature still emits no ungrounded causation",
               all(any(s in (wm.SRC_WORLD_EDGE, wm.SRC_REALITY_HYP) for s in e.get("sources", []))
                   for e in unrel.get("edges", [])))

            # ---- D. RETRIEVABLE — chain readout + durable round-trip + additive --------
            chains = wm.causal_chains(model)
            longest = chains[0] if chains else []
            ck("D1: causal_chains reads back a multi-hop through-line (>= 3 links) — reasoning "
               "ACROSS the chain, not four isolated memories",
               bool(longest) and len(longest) >= 3)
            ck("D2: the through-line runs from an upstream cause to a downstream consequence",
               bool(longest)
               and ("manager" in longest[0]["src"] or "work" in longest[0]["src"]
                    or "stress" in longest[0]["src"])
               and ("energy" in longest[-1]["dst"] or "sleep" in longest[-1]["dst"]))
            loaded = wm.get_model(N, model.get("id", ""))
            ck("D3: the built model ROUND-TRIPS by id through its OWN .worldmodel.json store "
               "(persisted + retrievable)",
               loaded is not None and loaded.get("id") == model.get("id")
               and len(loaded.get("edges", [])) == len(model.get("edges", [])))
            ck("D4: the store is the module's OWN file (.worldmodel.json), not a shared store",
               wm.store_path(N).exists() and wm.store_path(N).name.endswith(".worldmodel.json"))
            m2 = wm.build_model_from_graph(N, "work_stress")
            all_ids = {m["id"] for m in wm.models(N)}
            ck("D5: a SECOND model is ADDED, not overwritten (additive continuity)",
               model.get("id") in all_ids and m2.get("id") in all_ids and len(all_ids) >= 2)

            # ---- E. LEARNS — a resolved outcome shifts an edge, append-only ------------
            evolved = built["evolved"]
            b_edge = _edge(model, "strain", "poor_sleep")
            a_edge = _edge(evolved, "strain", "poor_sleep")
            ck("E1: the strain -> poor_sleep edge exists to be updated", b_edge is not None
               and a_edge is not None)
            ck("E2: a CONFIRMED sleep_decline outcome STRENGTHENED that edge's confidence",
               bool(b_edge) and bool(a_edge) and a_edge["confidence"] > b_edge["confidence"])
            ck("E3: the shift is recorded APPEND-ONLY in the edge history (before -> after)",
               bool(a_edge) and len(a_edge.get("history", [])) >= 1
               and a_edge["history"][-1]["before"] == b_edge["confidence"]
               and a_edge["history"][-1]["after"] == a_edge["confidence"])
            ck("E4: the input model snapshot is left UNTOUCHED (so before/after can be diffed)",
               bool(b_edge) and not b_edge.get("history"))
            contra = wm.update_model_with_outcome(
                model.get("id", ""),
                {"confirmed": False, "category": "sleep_decline", "observed": "sleeping great"},
                model=model, persist=False)
            c_edge = _edge(contra, "strain", "poor_sleep")
            ck("E5: a CONTRADICTED outcome WEAKENS the edge instead (floored, never annihilated)",
               bool(c_edge) and bool(b_edge) and c_edge["confidence"] < b_edge["confidence"]
               and c_edge["confidence"] >= wm._CONF_FLOOR)
            diff = built["diff"]
            ck("E6: compare_models reports the strengthened link (the evolution is auditable)",
               any("poor" in r["edge"] and "sleep" in r["edge"]
                   for r in diff.get("strengthened", []))
               and all(r["delta"] > 0 for r in diff.get("strengthened", [])))

            # ---- F. INTERNAL-ONLY + NO DIAGNOSIS (the rendered model never diagnoses) ---
            block = wm.explain_model(model.get("id", ""), model=model)
            body = wm.explain_body(model)
            ck("F2: explain_model renders the model as an INTERNAL causal model (the chain + cause "
               "sections), not a user-facing assertion",
               "INTERNAL causal model" in block and "[MODEL]" in block
               and "[CHAIN]" in block and "[CAUSE]" in block)
            ck("F3: NOT ONE generated body line trips a banned diagnosis/medical/prognostic term",
               bool(body.strip()) and all(wm._is_clean(ln) for ln in body.splitlines()))
            ck("F4: the explanation forbids asserting the model at the user, by construction",
               "never to be stated at" in block and "never a claim to assert at the user" in block)
        finally:
            for m, attr, old in extra:
                if old is not None:
                    setattr(m, attr, old)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nWORLD-MODEL CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
