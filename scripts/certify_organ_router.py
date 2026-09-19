#!/usr/bin/env python3
"""
certify_organ_router — ORGAN 3 (the Router): query-aware memory SELECTION + cheapest-sufficient path.

The predicted next bottleneck: once the fact store grows, injecting the blanket top-N (Facts.block dumps
the highest-salience rows regardless of the question) BURIES the one relevant row and blows the token
budget. The Router moves the decision from "dump everything we trust" to "inject ONLY what THIS turn
asks about". This certifies that contract through the SAME functions server._turn calls (router.route +
router.select_facts, anima/server.py lines 581/596), against a REAL captured LIRF store (not hand-built
rows) and the REAL memory_lirf._Q_TRAITS table fact_note routes on:

  A. QUERY-AWARE SELECTION — RELEVANT IN. A birthday is CAPTURED through memory_lirf.capture (a durable
     LIRF row that survives reload) alongside a HIGH-SALIENCE corroborated dog and a city.
     router.select_facts("when is my birthday?") selects the birthday row, the injected block carries its
     real value + the canonical "do not re-ask" header, and the birthday is the TOP selection. An alias
     ("date of birth") routes to the same birthday row via the same table. A value-word question
     ("do I live in Portland?") selects the lives row by overlapping its stored value.
  B. IRRELEVANT OUT (the buried-fact + budget guard). The birthday question does NOT select the dog; an
     UNRELATED question ("what's the weather like?") selects ZERO rows and yields an EMPTY block (nothing
     to inject); the injected block never carries the dog's value.
  C. SALIENCE NEVER MANUFACTURES RELEVANCE. The dog is the HIGHEST-salience fact in the store (heavily
     corroborated); an unrelated question ("tell me a joke") still does NOT select it — relevance gates
     selection, LIRF salience only breaks ties AMONG relevant facts. score_fact returns 0.0 on no topical
     connection. Budget caps the selection and selection is deterministic (same inputs -> same order).
  D. THE ROUTING DECISION — cheapest sufficient path. router.route over the REAL store returns a
     RouteDecision whose memory_ids carry the selected birthday row id and model="local": a selected
     fact is LOCAL STANDING, so the Mac answers and we do NOT reach out — even though that is the
     cheapest privacy-preserving path, not a fallback. A turn with NO local standing + a cloud brain
     available, and an explicit needs_cloud, each escalate local->cloud:<model>. route() is deterministic
     and RouteDecision.as_decision() projects a Decision-shaped object for the bus.
  E. SELFTEST. anima.organs.router --selftest passes in-process (the module's own 25-check isolation
     proof: hand-built rows, no store on disk, route.py absent -> no capability).

Hermetic + offline (no model, no network): memory_lirf STORE is redirected by _temp_store; the
reliability backup store is redirected here too; the real .anima is fingerprinted before/after and
asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
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


def main() -> int:
    from anima import memory_lirf
    from anima.organs import router
    from anima.memory_lirf import SELF

    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("ORGAN ROUTER — query-aware memory SELECTION (relevant in, irrelevant out) + cheapest path")
    print("=" * 90)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        # also redirect the reliability backup store (a guarded-load side effect _temp_store doesn't
        # cover by name) so even snapshots land in the temp dir — belt-and-suspenders for .anima safety.
        extra = []
        try:
            import anima.reliability as _rel
            extra.append((_rel, "DEFAULT_STORE", getattr(_rel, "DEFAULT_STORE", None)))
            if getattr(_rel, "DEFAULT_STORE", None) is not None:
                _rel.DEFAULT_STORE = tp
        except Exception:
            pass
        try:
            N = "RouterCert"

            # Seed a REAL multi-fact store through the production capture path — durable LIRF rows that
            # survive reload, NOT hand-built dicts. The dog is captured THREE times so it is the
            # HIGHEST-salience row in the store (the adversarial distractor selection must reject).
            for t in ("my birthday is September 14",
                      "i live in Portland, Oregon",
                      "my dog's name is Biscuit",
                      "my dog's name is Biscuit",
                      "my dog's name is Biscuit"):
                memory_lirf.capture(N, t)
            rows_all = {r.get("trait"): r for r in memory_lirf.Facts.load(N).about(SELF)}
            on_disk = (memory_lirf.STORE / f"{N}.lirf.json").exists()
            bday_row = rows_all.get("birthday")
            dog_row = rows_all.get("dog_name")
            from anima.memory_lirf import _salience
            ck("S0: capture persisted a real birthday + dog + lives store (durable on disk)",
               on_disk and bday_row is not None and dog_row is not None
               and rows_all.get("lives") is not None)
            ck("S0b: the DOG is the highest-salience row (the adversarial distractor)",
               _salience(dog_row) > _salience(bday_row))
            bday_id = bday_row.get("id")

            # ---- A. QUERY-AWARE SELECTION — RELEVANT IN (production select_facts) ------------
            sel, block = router.select_facts(N, "when is my birthday?")
            sel_traits = [r.get("trait") for r in sel]
            ck("A1: 'when is my birthday?' selects the birthday row (the relevant fact)",
               "birthday" in sel_traits)
            ck("A2: the birthday is the TOP selection (most relevant)",
               bool(sel) and sel[0].get("trait") == "birthday")
            ck("A3: the injected block carries the birthday value",
               "September 14" in block)
            ck("A4: the block uses the canonical 'do not re-ask' header (the familiar inject shape)",
               "do not re-ask" in block)
            # alias precision through the SAME _Q_TRAITS table fact_note routes on
            sel_dob, _ = router.select_facts(N, "remind me my date of birth")
            ck("A5: an alias ('date of birth') resolves to the SAME birthday row (alias precision)",
               "birthday" in [r.get("trait") for r in sel_dob]
               and "dog_name" not in [r.get("trait") for r in sel_dob])
            # value-word overlap: naming the stored VALUE (not the trait) still hits
            sel_val, _ = router.select_facts(N, "do I live in Portland?")
            ck("A6: a question naming a stored VALUE selects that fact (Portland -> lives)",
               "lives" in [r.get("trait") for r in sel_val])

            # ---- B. IRRELEVANT OUT — the buried-fact + budget guard --------------------------
            ck("B1: the birthday question does NOT select the dog (the buried-fact failure)",
               "dog_name" not in sel_traits)
            ck("B2: the injected block never carries the dog's value",
               "Biscuit" not in block)
            sel_u, block_u = router.select_facts(N, "what's the weather like today?")
            ck("B3: an UNRELATED question selects ZERO facts (does not drag in the store)",
               len(sel_u) == 0)
            ck("B4: an unrelated question yields an EMPTY block (nothing to inject)", block_u == "")

            # ---- C. SALIENCE NEVER MANUFACTURES RELEVANCE -----------------------------------
            sel_joke, _ = router.select_facts(N, "tell me a joke")
            ck("C1: the HIGHEST-salience fact (the dog) is NOT selected by an unrelated question",
               "dog_name" not in [r.get("trait") for r in sel_joke])
            # score_fact is 0.0 on no topical connection (the gate that keeps unrelated facts out)
            from anima.organs.router import score_fact, _tokens, _asked_traits
            q = "tell me a joke"
            ck("C2: score_fact returns 0.0 for a fact with no topical connection to the question",
               score_fact(dog_row, _tokens(q), _asked_traits(q)) == 0.0)
            # budget caps + determinism (over the real store)
            sel_b, _ = router.select_facts(N, "when is my birthday?", budget=1)
            ck("C3: budget caps the number of selected facts", len(sel_b) <= 1)
            s1 = [r.get("id") for r in router.select_facts(N, "when is my birthday?")[0]]
            s2 = [r.get("id") for r in router.select_facts(N, "when is my birthday?")[0]]
            ck("C4: selection is deterministic (same inputs -> same order)", s1 == s2)

            # ---- D. THE ROUTING DECISION — cheapest sufficient path -------------------------
            d_local = router.route(N, "when is my birthday?", {})
            ck("D1: route() returns a RouteDecision", isinstance(d_local, router.RouteDecision))
            ck("D2: a selected fact carries its id in the decision's memory_ids",
               bday_id in list(d_local.memory_ids))
            ck("D3: a selected fact gives LOCAL STANDING -> stays local (no escalation, can answer here)",
               d_local.model == "local" and d_local.escalation == "")
            ck("D4: even with a cloud brain available, a selected fact STILL stays local (no reach-out)",
               router.route(N, "when is my birthday?",
                            {"cloud_on": True, "cloud_model": "claude"}).model == "local")
            d_esc = router.route(N, "what's the latest news?",
                                 {"cloud_on": True, "cloud_model": "claude"})
            ck("D5: no local standing + cloud available -> escalates local->cloud:<model>",
               d_esc.model == "cloud:claude" and d_esc.escalation == "local→cloud")
            d_needs = router.route(N, "anything",
                                   {"cloud_on": True, "needs_cloud": True, "cloud_model": "claude"})
            ck("D6: an explicit needs_cloud escalates local->cloud:<model>",
               d_needs.model == "cloud:claude" and d_needs.escalation == "local→cloud")
            ck("D7: route() is deterministic (same inputs -> same decision)",
               router.route(N, "when is my birthday?", {}) == router.route(N, "when is my birthday?", {}))
            proj = d_local.as_decision()
            has_model = (getattr(proj, "model", None) == "local") if not isinstance(proj, dict) \
                else (proj.get("model") == "local")
            ck("D8: RouteDecision.as_decision() projects a Decision-shaped object (drops onto the bus)",
               has_model)

            # ---- E. SELFTEST — the module's own isolation proof (in-process) ----------------
            rc = router._selftest()
            ck("E1: anima.organs.router --selftest passes in-process (25 checks)", rc == 0)
        finally:
            for m, attr, old in extra:
                if old is not None:
                    setattr(m, attr, old)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nORGAN-ROUTER CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
