#!/usr/bin/env python3
"""
certify_autonomous_growth — the '[x] Grow Intelligence' switch + grow_mode, and the SAFETY property
that with growth OFF it is a provable NO-OP ($0, zero autonomous activity).

This is the one thing that must hold for a default-OFF autonomous learner to ship: OFF is INERT.
Certified through the SAME anima.lerf_grow + anima.caps functions the server's /capabilities path
and the idle-loop caller use:

  A. DEFAULT-OFF — a fresh creature has grow_intelligence OFF, get_mode() == "off", is_enabled()
     False; the Off mode profile is budget_ceiling $0 / max_per_run 0 / cadence inf (provably inert).
  B. OFF IS INERT — should_learn_now(idle=True, way past any cadence) returns ok=False with
     enabled=False; run_idle_cycle(idle=True) returns ran=False having selected NO teacher, built
     NO curriculum, grown nothing; grow_from_source(...) likewise ran=False. Nothing autonomous runs.
  C. $0 PROOF — across the whole OFF run, NO spend.json and NO brain.json are written under
     cloud.STORE (no key read, no paid call), and NO {name}.grow.json state file is written under
     lerf_grow.STORE. Provably $0.
  D. STATUS TELLS THE TRUTH — status() reports the switch OFF and budget_ceiling 0.0 (the
     inspectable surface can't claim activity it isn't doing).
  E. DURABLE + COERCE + LOCKSTEP — caps.set_grow_mode("high") persists "high" on reload; an invalid
     mode coerces to "off" and is not stored; lerf_grow.set_mode keeps the master switch in lockstep
     (a non-off mode flips grow_intelligence ON, "off" flips it OFF, provably inert).

Hermetic + offline: every store is redirected via gate0_prime_experience._temp_store, AND because
lerf_grow + cloud are NOT in that module set, the cert redirects lerf_grow.STORE and cloud.STORE to
the same temp dir itself (the brain_select pattern) so any spend/state write would land in temp where
we assert its ABSENCE. The real .anima is fingerprinted before/after and asserted byte-identical. No
model, no network, no cloud call. Exit 0 == CERTIFIED, 1 == FAIL.
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
    from anima import lerf_grow, caps, cloud
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("AUTONOMOUS GROWTH — '[x] Grow Intelligence': OFF is a provable no-op ($0)")
    print("=" * 74)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        # lerf_grow + cloud are not in _temp_store's redirect set: redirect them here so any
        # state/spend write lands in temp (where we assert it never happens), never the real .anima.
        saved_lg = getattr(lerf_grow, "STORE", None)
        saved_cloud = getattr(cloud, "STORE", None)
        lerf_grow.STORE = tp
        cloud.STORE = tp
        try:
            N = "GrowCert"

            # ---- A. DEFAULT-OFF ------------------------------------------------------
            ck("A1: a fresh creature has grow_intelligence OFF", lerf_grow.is_enabled(N) is False)
            ck("A2: the active mode defaults to 'off'", lerf_grow.get_mode(N) == "off")
            prof = lerf_grow.mode_profile(N)
            ck("A3: the Off profile is provably inert ($0 / cap 0 / cadence inf)",
               prof["budget_ceiling"] == 0.0 and prof["max_per_run"] == 0
               and prof["cadence_hours"] == float("inf") and prof["mode"] == "off")

            # ---- B. OFF IS INERT -----------------------------------------------------
            dec = lerf_grow.should_learn_now(N, idle=True, now_hours_since=10_000)
            ck("B1: should_learn_now refuses while OFF, even idle and long past any cadence",
               dec["ok"] is False and dec["enabled"] is False)
            tr = lerf_grow.run_idle_cycle(N, idle=True, now_hours_since=10_000)
            ck("B2: run_idle_cycle is a NO-OP while OFF (ran=False, nothing selected/grown)",
               tr["ran"] is False and tr["teacher"] is None
               and tr["curriculum"] == [] and tr["grown"] == [])
            gr = lerf_grow.grow_from_source("teacher_models", ["some material"],
                                            idle=True, now_hours_since=10_000)
            ck("B3: grow_from_source is a NO-OP while OFF (ran=False, nothing ingested/grown)",
               gr["ran"] is False and gr["grown"] == [])

            # ---- C. $0 PROOF ---------------------------------------------------------
            ck("C1: $0 — no spend.json written under cloud.STORE (no paid call)",
               not (tp / "spend.json").exists())
            ck("C2: $0 — no brain.json written under cloud.STORE (no key read/touched)",
               not (tp / "brain.json").exists())
            ck("C3: inert — no {name}.grow.json state file written under lerf_grow.STORE",
               not (tp / f"{N}.grow.json").exists() and not lerf_grow._state_path(N).exists())

            # ---- D. STATUS TELLS THE TRUTH ------------------------------------------
            snap = lerf_grow.status(N)
            ck("D1: status() reports the switch OFF and budget_ceiling 0.0",
               snap["grow_intelligence_enabled"] is False and snap["mode"] == "off"
               and snap["budget_ceiling"] == 0.0)

            # ---- E. DURABLE + COERCE + LOCKSTEP -------------------------------------
            caps.set_grow_mode(N, "high")
            ck("E1: caps.set_grow_mode('high') is DURABLE on reload", caps.grow_mode(N) == "high")
            ck("E2: an invalid mode coerces to the safe 'off' (not stored as junk)",
               caps.set_grow_mode(N, "ludicrous") == "off" and caps.grow_mode(N) == "off")
            # lerf_grow.set_mode keeps the master switch in lockstep with the chosen intensity.
            M = "GrowLockstep"
            ck("E3: set_mode('high') flips the master switch ON (a non-off mode enables growth)",
               lerf_grow.set_mode(M, "high") == "high" and lerf_grow.is_enabled(M) is True)
            ck("E4: set_mode('off') flips the master switch OFF (back to provably inert)",
               lerf_grow.set_mode(M, "off") == "off" and lerf_grow.is_enabled(M) is False)
            ck("E5: an enabled creature set back to OFF is inert again (should_learn_now refuses)",
               lerf_grow.should_learn_now(M, idle=True, now_hours_since=10_000)["ok"] is False)
        finally:
            if saved_lg is not None:
                lerf_grow.STORE = saved_lg
            if saved_cloud is not None:
                cloud.STORE = saved_cloud

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nAUTONOMOUS-GROWTH CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
