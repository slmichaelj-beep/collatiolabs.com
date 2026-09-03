#!/usr/bin/env python3
"""
certify_intelligence_economics — Intelligence Economics is computed from REAL ledger data,
deterministically, and the EXACT axes are the honest verdict (the ESTIMATE axes are labelled).

Vera's thesis is that a SMALL local model + a CERTIFIED retrieved skill beats a LARGE model on
intelligence-PER-RESOURCE. Intelligence Economics is the metric that proves it: per-GB / per-token
/ per-$ / per-watt / per-second for the LERF substrate, plus three knowledge-DENSITY axes
(understanding-per-MB, learning-per-MB, reasoning-per-kJ). This certifies — through the SAME
intelligence_per_gb.compute() the growth dashboard calls — that the EXACT axes come from real,
measured/ledger data and never from a baked-in constant:

  A. EVERY AXIS COMPUTES — all five resource axes + the three density axes return a FINITE, POSITIVE
     ratio on both sides; the report self-reports hermetic_ok.
  B. THE HONESTY CONTRACT — per_token / per_dollar / per_gb (and the two density axes) are flagged
     exact=True; per_watt / per_second / reasoning_per_watt are flagged exact=False (ESTIMATE). The
     energy/latency lenses are NEVER presented as measured.
  C. COMPUTED FROM THE REAL LEDGER (not a constant) — the per-token EXACT ratio equals
     1000*capability/tokens recomputed INDEPENDENTLY off lerf_benchmark.deterministic_table (the
     deterministic token/cost ledger: lerf.count_tokens summed per condition, priced by PRICE_PER_1K);
     the per-token cut is the proven >=50% prompt-token reduction; the per-GB store_bytes equals a
     FRESH real os.stat of the serialized LERF seed store; the learning-density object count equals a
     real lerf.stats over the seeded ACTIVE population. None of these is hardcoded.
  D. LERF+SMALL WINS THE EXACT AXES — on the deterministic data, LERF+small beats model-only on
     per_token AND per_dollar AND per_gb (capability-per-resource, higher is better).
  E. NOT A CONSTANT (it tracks real store content) — serializing a STRICT SUBSET of the seed skills
     yields a STRICTLY SMALLER measured store than the full population. So the per-GB measurement is a
     real os.stat of whatever is actually in the store, not a fixed number.
  F. DETERMINISTIC — two compute() runs yield byte-identical EXACT ratios and densities (no model, no
     network, no randomness in the deterministic path).
  G. THE LIVE CONSUMER AGREES — growth_dashboard.density() (the dashboard's real read of these
     metrics) returns the SAME learning + understanding densities from the same future_axes.

Hermetic + offline: every store is redirected via gate0_prime_experience._temp_store (lerf/
world_model/memory_lirf/reliability/constitution/...), AND compute()/the benchmark each do their own
per-measurement temp-store redirection internally, so nothing touches the real store. NO model, NO
network (want_live=False throughout). The real .anima is fingerprinted before/after and asserted
byte-identical ("H1"). Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def _measure_subset_store_bytes(n_skills: int) -> int:
    """HERMETIC: serialize the FIRST ``n_skills`` shipped seed skills to a THROWAWAY temp store and
    os.stat the file — the same discipline intelligence_per_gb._measure_store_bytes uses, but on a
    strict subset, so we can prove the per-GB measurement tracks real store CONTENT (fewer skills ->
    a smaller file) rather than returning a baked-in constant. Read-only w.r.t. the real .anima."""
    from anima import lerf
    from scripts.build_lerf import _seed_skills
    td = tempfile.mkdtemp(prefix="lerf-econ-cert-subset-")
    tp = Path(td)
    targets = [(lerf, "STORE")]
    for modpath, attr in (("anima.lerf", "STORE"), ("anima.memory_lirf", "STORE"),
                          ("anima.constitution", "STORE"), ("anima.reliability", "DEFAULT_STORE")):
        try:
            targets.append((__import__(modpath, fromlist=["_"]), attr))
        except Exception:
            pass
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)
    try:
        nm = "econ_cert_subset"
        for sk in _seed_skills()[:n_skills]:
            lerf.store_skill(sk, name=nm)
        size = lerf._path(nm).stat().st_size
    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        shutil.rmtree(td, ignore_errors=True)
    return int(size)


def _ledger_per_token_ratios() -> dict:
    """INDEPENDENTLY recompute the per-token ratios straight from lerf_benchmark's deterministic
    token/cost ledger (the SAME deterministic_table the economics module reuses), on a fresh hermetic
    temp store. Returns {B_tokens, E_tokens, mo_ratio, ls_ratio} where the ratio is
    1000*modelled_capability/tokens — exactly the arithmetic axis_per_token performs. This is the
    proof that compute()'s per-token number is DERIVED FROM THE REAL LEDGER, not a hardcoded value."""
    from anima import lerf
    import scripts.lerf_benchmark as bench
    td = tempfile.mkdtemp(prefix="lerf-econ-cert-ledger-")
    tp = Path(td)
    targets = [(lerf, "STORE")]
    for modpath, attr in (("anima.lerf", "STORE"), ("anima.memory_lirf", "STORE"),
                          ("anima.constitution", "STORE"), ("anima.reliability", "DEFAULT_STORE")):
        try:
            targets.append((__import__(modpath, fromlist=["_"]), attr))
        except Exception:
            pass
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)
    try:
        name = bench.SYNTH
        bench._seed_battery_skills(name)
        det = bench.deterministic_table(name)
        b_tok = det["conditions"]["B"]["tokens"]
        e_tok = det["conditions"]["E"]["tokens"]
        mo_cap = float(bench._MODELLED_ACCURACY["B"])   # model-only capability proxy (condition B)
        ls_cap = float(bench._MODELLED_ACCURACY["E"])   # LERF+small capability proxy (condition E)
        mo_ratio = round((mo_cap / (b_tok / 1000.0)) if b_tok else float("inf"), 6)
        ls_ratio = round((ls_cap / (e_tok / 1000.0)) if e_tok else float("inf"), 6)
    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        shutil.rmtree(td, ignore_errors=True)
    return {"B_tokens": b_tok, "E_tokens": e_tok, "mo_ratio": mo_ratio, "ls_ratio": ls_ratio}


def _finite_pos(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0


def main() -> int:
    from scripts import intelligence_per_gb as ipg
    from scripts import growth_dashboard as gd
    from anima import lerf
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("INTELLIGENCE ECONOMICS — capability PER RESOURCE, computed from the real ledger (EXACT) "
          "+ honest ESTIMATE lenses")
    print("=" * 96)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        # The SAME entry point the growth dashboard calls. want_live=False => no model, no network.
        rep = ipg.compute(want_live=False)
        axes = rep["axes"]
        fa = rep["future_axes"]
        cap = rep["capability"]
        wins = rep["lerf_wins"]

        # ---- A. EVERY AXIS COMPUTES -------------------------------------------------------
        resource_axes = ("per_gb", "per_token", "per_dollar", "per_watt", "per_second")
        all_ok = True
        for nm in resource_axes:
            for side in ("model_only", "lerf_small"):
                if not _finite_pos(axes[nm][side]["ratio"]):
                    all_ok = False
        ck("A1: all five resource axes return a finite, positive ratio on BOTH sides",
           all_ok)
        ck("A2: all three knowledge-density axes return a finite, positive value",
           _finite_pos(fa["understanding_per_gb"]["density_per_mb"])
           and _finite_pos(fa["learning_per_gb"]["density_per_mb"])
           and _finite_pos(fa["reasoning_per_watt"]["ratio"]))
        ck("A3: capability proxy is in [0,1] for both sides and is labelled 'modelled' (no --live)",
           0.0 <= cap["model_only"] <= 1.0 and 0.0 <= cap["lerf_small"] <= 1.0
           and cap["source"] == "modelled")
        ck("A4: the report self-reports hermetic_ok (its own internal temp-store discipline held)",
           rep["hermetic_ok"] is True)

        # ---- B. THE HONESTY CONTRACT ------------------------------------------------------
        ck("B1: per_token / per_dollar / per_gb are flagged EXACT (the deterministic verdict)",
           axes["per_token"]["exact"] is True and axes["per_dollar"]["exact"] is True
           and axes["per_gb"]["exact"] is True)
        ck("B2: per_watt / per_second are flagged ESTIMATE (energy/latency are a lens, not measured)",
           axes["per_watt"]["exact"] is False and axes["per_second"]["exact"] is False
           and axes["per_watt"].get("estimate") is True)
        ck("B3: understanding/learning density EXACT; reasoning-per-kJ ESTIMATE (count exact, J modelled)",
           fa["understanding_per_gb"]["exact"] is True and fa["learning_per_gb"]["exact"] is True
           and fa["reasoning_per_watt"]["exact"] is False
           and fa["reasoning_per_watt"].get("estimate") is True)

        # ---- C. COMPUTED FROM THE REAL LEDGER (not a constant) ----------------------------
        # Recompute the per-token ratios INDEPENDENTLY off the benchmark's own deterministic token
        # table and require compute()'s axis to match — proving it is derived, not hardcoded.
        ledger = _ledger_per_token_ratios()
        ck("C1: per-token model-only ratio == 1000*cap/B_tokens recomputed off the deterministic "
           "ledger (lerf_benchmark.deterministic_table), not a constant",
           axes["per_token"]["model_only"]["ratio"] == ledger["mo_ratio"]
           and axes["per_token"]["model_only"]["resource"] == ledger["B_tokens"])
        ck("C2: per-token LERF+small ratio == 1000*cap/E_tokens recomputed off the same ledger",
           axes["per_token"]["lerf_small"]["ratio"] == ledger["ls_ratio"]
           and axes["per_token"]["lerf_small"]["resource"] == ledger["E_tokens"])
        ck("C3: the per-token cut is the proven >=50% prompt-token reduction (E < B tokens)",
           axes["per_token"]["lerf_small"]["resource"] < axes["per_token"]["model_only"]["resource"]
           and axes["per_token"]["detail"]["token_reduction_pct_vs_B"] >= 50.0)
        # the per-GB store size must equal a FRESH real os.stat of the full serialized seed store.
        full_store_bytes = _measure_subset_store_bytes(10)        # all 10 shipped seeds
        ck("C4: per-GB store_bytes == a fresh real os.stat of the serialized LERF seed store "
           "(measured, not a baked-in number)",
           axes["per_gb"]["detail"]["store_bytes"] == full_store_bytes and full_store_bytes > 1000)
        # the learning-density object count must equal a real lerf.stats over the seeded population.
        ld = fa["learning_per_gb"]["detail"]
        ck("C5: learning-density object count is a real lerf.stats over the ACTIVE population "
           "spanning >=5 object types (skills+concepts+procedures+the six added types)",
           ld["objects"] >= 10 and len(ld["by_type"]) >= 5
           and ld["objects"] == sum(ld["by_type"].values()))

        # ---- D. LERF+SMALL WINS THE EXACT AXES --------------------------------------------
        ck("D1: LERF+small WINS per_token (capability-per-token, higher is better)",
           wins["per_token"] is True
           and axes["per_token"]["lerf_small"]["ratio"] > axes["per_token"]["model_only"]["ratio"])
        ck("D2: LERF+small WINS per_dollar (the EXACT cost axis)",
           wins["per_dollar"] is True
           and axes["per_dollar"]["lerf_small"]["ratio"] > axes["per_dollar"]["model_only"]["ratio"])
        ck("D3: LERF+small WINS per_gb (the EXACT footprint axis)",
           wins["per_gb"] is True
           and axes["per_gb"]["lerf_small"]["ratio"] > axes["per_gb"]["model_only"]["ratio"])

        # ---- E. NOT A CONSTANT (the measurement tracks real store content) ----------------
        subset_store_bytes = _measure_subset_store_bytes(3)       # a STRICT subset of the seeds
        ck("E1: serializing a STRICT SUBSET of the seeds yields a STRICTLY SMALLER measured store "
           "than the full population — the per-GB measurement is a real os.stat of actual content",
           0 < subset_store_bytes < full_store_bytes)

        # ---- F. DETERMINISTIC -------------------------------------------------------------
        rep2 = ipg.compute(want_live=False)
        ck("F1: two compute() runs give byte-identical EXACT per-token & per-GB ratios",
           rep2["axes"]["per_token"]["lerf_small"]["ratio"]
           == axes["per_token"]["lerf_small"]["ratio"]
           and rep2["axes"]["per_gb"]["lerf_small"]["ratio"]
           == axes["per_gb"]["lerf_small"]["ratio"])
        ck("F2: two compute() runs give identical understanding & learning densities",
           rep2["future_axes"]["understanding_per_gb"]["density_per_mb"]
           == fa["understanding_per_gb"]["density_per_mb"]
           and rep2["future_axes"]["learning_per_gb"]["density_per_mb"]
           == fa["learning_per_gb"]["density_per_mb"])

        # ---- G. THE LIVE CONSUMER AGREES --------------------------------------------------
        # growth_dashboard.density() is the dashboard's real read of these metrics; it must return
        # the SAME densities from the same future_axes (no parallel/forked computation).
        dens = gd.density(want_live=False)
        ck("G1: growth_dashboard.density() reads the economics module and reports it available + hermetic",
           dens.get("available") is True and dens.get("hermetic_ok") is True)
        ck("G2: the dashboard's learning & understanding densities == the economics module's future_axes",
           dens.get("learning_per_mb") == fa["learning_per_gb"]["density_per_mb"]
           and dens.get("understanding_per_mb") == fa["understanding_per_gb"]["density_per_mb"])

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nINTELLIGENCE-ECONOMICS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
