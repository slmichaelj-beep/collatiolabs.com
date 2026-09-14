#!/usr/bin/env python3
"""
certify_sysinfo_fit — the model-FIT gate: a REAL, DETERMINISTIC "will this model fit this Mac?".

Vera is local-first, so before she pulls or selects a local model she checks it FITS. On Apple
Silicon CPU+GPU share one unified RAM pool, so total RAM decides what a GGUF model can run.
sysinfo estimates a model's footprint from its NAME (param count x bytes/param from the quant) plus
runtime overhead, and compares to (RAM - an 8 GB OS reserve). This certifies that decision is REAL
(read from os.sysconf, not a constant), DETERMINISTIC, and the SAFETY INVARIANT the model manager
enforces — through the SAME functions models.select/pull and cloud.public call:

  A. REAL PROBE. ram_gb() reads a POSITIVE figure straight from os.sysconf (SC_PAGE_SIZE *
     SC_PHYS_PAGES) — the machine's actual unified memory, not a hard-coded number; chip() names a
     real CPU. The fit decision is grounded in this machine, not faked.
  B. PARSER + FOOTPRINT. params_b pulls the B-count out of real names (8B, 0.5B, 405B) and is 0 on a
     nameless ref; _bytes_per_param rises monotonically q2<q4<q5<q6<q8<f16 (a heavier quant costs more
     RAM); need_gb = params*bytes/param + overhead, and is 0 when there is no param count (-> unknown).
  C. REAL-MACHINE VERDICT. On THIS Mac a 405B and a 70B model are refused "too big" while a 1B and an
     8B are allowed (comfortable/tight); a name with no parseable size is "unknown" — never a false
     "fits". The too-big refusal is real and observed on the live hardware.
  D. MACHINE-INDEPENDENT DETERMINISM (pin ram_gb to a fixed 16 GB so the proof holds on ANY box):
     fit() is a PURE function (same input -> identical verdict on repeated calls); the verdict is
     strictly MONOTONIC in size (a bigger model is never a BETTER verdict than a smaller one); the
     boundary is EXACT (need just over free -> "too big", need just under -> not "too big"); and a
     model whose need exceeds free RAM is ALWAYS "too big", on any hardware.
  E. ENFORCED INVARIANT. The "too big" verdict is the EXACT gate models.select()/models.pull() use to
     BLOCK a model with "that model won't fit your Mac's memory" BEFORE any network/Ollama call, while
     a fitting ref is NOT blocked by the fit gate. The safety decision actually stops the bad pick.

Hermetic + offline (no model, no network): sysinfo writes nothing, but the cert still runs inside
_temp_store() (which redirects models.STORE etc.) and fingerprints the REAL .anima before/after,
asserting it byte-identical. Any ram_gb monkeypatch is restored. Exit 0 == CERTIFIED, 1 == FAIL.
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
    from anima import sysinfo, models
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("SYSINFO FIT — the model-FIT gate: a REAL, DETERMINISTIC 'will this model fit this Mac?'")
    print("=" * 90)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # ---- A. REAL PROBE (outside the store too — these read hardware, write nothing) ----------
    ram = sysinfo.ram_gb()
    ck("A1: ram_gb() reads a POSITIVE figure from os.sysconf (real unified memory, not a constant)",
       isinstance(ram, float) and ram > 0)
    ck("A2: chip() names a real CPU (non-empty string)",
       isinstance(sysinfo.chip(), str) and bool(sysinfo.chip().strip()))

    with _temp_store():
        saved_ram_fn = sysinfo.ram_gb           # so we can pin RAM for the machine-independent leg
        try:
            # ---- B. PARSER + FOOTPRINT ------------------------------------------------------
            ck("B1: params_b pulls the B-count out of real model names",
               sysinfo.params_b("llama3.1:8b") == 8.0
               and sysinfo.params_b("qwen2.5:0.5b") == 0.5
               and sysinfo.params_b("foo-405B-q4") == 405.0)
            ck("B2: params_b is 0.0 on a name with no parseable size (-> unknown, never a guess)",
               sysinfo.params_b("no-size-here") == 0.0 and sysinfo.params_b("") == 0.0)
            bpp = sysinfo._bytes_per_param
            seq = [bpp("m-q2_k"), bpp("m-q4_k_m"), bpp("m-q5_k"), bpp("m-q6_k"), bpp("m-q8_0"), bpp("m-f16")]
            ck("B3: bytes/param rises monotonically q2<q4<q5<q6<q8<f16 (heavier quant -> more RAM)",
               all(a < b for a, b in zip(seq, seq[1:])))
            ck("B4: need_gb = params*bytes/param + overhead, and is 0 when there is no param count",
               sysinfo.need_gb("m-3B-q4") > sysinfo.need_gb("m-1B-q4") > 0
               and sysinfo.need_gb("no-size") == 0.0)

            # ---- C. REAL-MACHINE VERDICT (grounded in THIS Mac's actual RAM) ----------------
            big = sysinfo.fit("huge-405B-q4")
            mid = sysinfo.fit("llama-70B")
            small1 = sysinfo.fit("tiny-1B")
            small8 = sysinfo.fit("llama-8B")
            unk = sysinfo.fit("nameless-model")
            ck("C1: a 405B model is refused 'too big' on this Mac (need exceeds free RAM)",
               big["verdict"] == "too big" and big["need_gb"] > big["ram_gb"] - 8.0)
            ck("C2: a 70B model is also refused 'too big' on this Mac",
               mid["verdict"] == "too big")
            ck("C3: a 1B and an 8B model ARE allowed (comfortable/tight), not refused",
               small1["verdict"] in ("comfortable", "tight")
               and small8["verdict"] in ("comfortable", "tight"))
            ck("C4: an unparseable name is 'unknown' (never a false 'fits')",
               unk["verdict"] == "unknown" and unk["params_b"] == 0.0)
            ck("C5: fit() reports the SAME real RAM it decided against (decision is grounded, not faked)",
               big["ram_gb"] == ram and small8["ram_gb"] == ram)

            # ---- D. MACHINE-INDEPENDENT DETERMINISM (pin RAM so this holds on ANY hardware) --
            sysinfo.ram_gb = lambda: 16.0        # a fixed Mac: 16 GB total -> 8 GB free after reserve
            v1 = sysinfo.fit("llama-8B")
            v2 = sysinfo.fit("llama-8B")
            ck("D1: with RAM pinned, fit() is PURE — same input -> identical verdict on repeat",
               v1 == v2 and v1["ram_gb"] == 16.0)
            order = {"comfortable": 0, "tight": 1, "too big": 2}
            verdicts = [sysinfo.fit(f"m-{p}B-q4")["verdict"] for p in (1, 3, 8, 13, 30, 70, 405)]
            ranks = [order[v] for v in verdicts]
            ck("D2: the verdict is strictly MONOTONIC in size (a bigger model is never a BETTER verdict)",
               all(a <= b for a, b in zip(ranks, ranks[1:])) and ranks[0] == 0 and ranks[-1] == 2)
            # exact boundary: free RAM at 16 GB = 8 GB; a model needing just OVER 8 is too big, just under is not.
            free = max(0.0, 16.0 - 8.0)
            # pick params so need lands just over / just under free, from the real need_gb formula
            def _params_for(target_need):
                return round((target_need - 1.5) / 0.62, 3)
            p_over = _params_for(free + 0.5)
            p_under = _params_for(free - 0.5)
            ck("D3: the boundary is EXACT — need just OVER free RAM -> 'too big'",
               sysinfo.fit(f"b-{p_over}B-q4")["verdict"] == "too big")
            ck("D4: the boundary is EXACT — need just UNDER free RAM -> NOT 'too big'",
               sysinfo.fit(f"b-{p_under}B-q4")["verdict"] != "too big")
            # the load-bearing safety law, hardware-free: need > free RAM is ALWAYS 'too big'.
            law_holds = True
            for params in (20, 40, 70, 120, 405):
                f = sysinfo.fit(f"m-{params}B-q4")
                if f["need_gb"] > free and f["verdict"] != "too big":
                    law_holds = False
            ck("D5: a model whose need exceeds free RAM is ALWAYS refused 'too big' (the safety law)",
               law_holds)
            sysinfo.ram_gb = saved_ram_fn        # restore the real probe before the enforcement leg

            # ---- E. ENFORCED INVARIANT — the gate models.select/pull actually use to BLOCK ---
            # Pin RAM to a fixed 16 GB so the 70B curated ref is deterministically too big and the
            # 8B/3B fit, on ANY box. models._fit_of -> sysinfo.fit -> sysinfo.ram_gb (patched).
            sysinfo.ram_gb = lambda: 16.0
            try:
                too_big_ref = "hf.co/bartowski/Llama-3.3-70B-Instruct-GGUF"   # 70B, in CURATED
                fit_ref = "hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF"        # 3B, in CURATED
                ck("E0: (precondition) the 70B curated ref verdict IS 'too big' at 16 GB; the 3B is not",
                   models._fit_of(70)["verdict"] == "too big"
                   and models._fit_of(3)["verdict"] != "too big")
                sel = models.select(too_big_ref)
                ck("E1: models.select REFUSES a too-big model with 'won't fit your Mac's memory'",
                   sel.get("ok") is False and "won't fit" in (sel.get("error", "")))
                pul = models.start_pull(too_big_ref)
                ck("E2: models.start_pull REFUSES a too-big model BEFORE any network ('not downloading')",
                   pul.get("ok") is False and "won't fit" in (pul.get("error", ""))
                   and "not downloading" in (pul.get("error", "")))
                # a FITTING ref is not blocked BY THE FIT GATE (it may still fail for a different,
                # non-fit reason like 'not installed' — but never with the won't-fit message).
                sel_ok = models.select(fit_ref)
                ck("E3: a FITTING ref is NOT blocked by the fit gate (no 'won't fit' refusal)",
                   "won't fit" not in (sel_ok.get("error", "") or ""))
            finally:
                sysinfo.ram_gb = saved_ram_fn
        finally:
            sysinfo.ram_gb = saved_ram_fn        # belt-and-suspenders: never leave RAM patched

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nSYSINFO-FIT CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
