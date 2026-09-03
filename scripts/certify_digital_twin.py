#!/usr/bin/env python3
"""
certify_digital_twin — the DIGITAL TWIN: build a twin from the real creature, then simulate a
change on the twin WITHOUT EVER touching prod.

The Digital Twin (anima/twin.py) is the freeze-safe laboratory: an ISOLATED FULL COPY of a
creature's cognitive state, on which any experiment runs while the real mind is provably untouched.
This certifies that promise end-to-end through the SAME public API anima/simulation.py and the twin
dashboards compose:

  A. BUILT FROM THE REAL CREATURE — create_twin read-COPIES the source's identity/LERF/reality/
     memory files into an isolated .anima/twins/{twin_id}/ namespace (remapped onto the twin id);
     the twin has a readable cognitive state with real objects; the source files are NOT modified
     (a copy, never a move).
  B. CHANGE SIMULATED WITHOUT TOUCHING PROD — run_experiment('more_learning') + accelerate(N) GROW
     the TWIN's object count (before < after), and the freeze_guard wrapped around the operation
     reports real Vera identity AND the whole real .anima byte-UNCHANGED. The freeze-FORBIDDEN
     change ('enabled identity evolution') runs on the twin and REMEDIATES its ungrounded self-claim
     — all on the copy.
  C. ISOLATION IS STRUCTURAL — snapshot -> mutate -> restore round-trips the twin to a prior byte
     state (matches the hash-chained ledger); the merge gate DECIDES PROMOTE on a safe+better twin
     and HOLD otherwise, and NEVER writes the real creature (applied_to_real False).
  D. THE FREEZE IS ENFORCED — a write to a REAL identity file inside a freeze_guard raises
     FreezeViolation: the real mind is structurally protected, not protected by convention.

Hermetic + OFFLINE (no Ollama, no cloud, $0): twin.STORE + the full engine-STORE set (via
_temp_store) + identity_sandbox.STORE + debt_ledger.STORE are redirected into a temp dir; a SYNTHETIC
source creature is seeded (real Vera is never read); the real .anima is fingerprinted before/after
and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
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


def main() -> int:
    from anima import twin
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("DIGITAL TWIN — build a twin from the real creature, simulate a change without touching prod")
    print("=" * 92)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # _temp_store redirects the standard engine STORES (lerf/memory_lirf/world_state/...), resets
    # server history + cached mouth, and restores on exit. twin.py and a couple of read-side modules
    # carry their OWN module STORE that _temp_store does NOT cover — redirect those ourselves inside
    # the block (exactly as certify_personal_intelligence.py redirects constitution/reliability), so
    # every binding twin resolves a path from lands in the temp dir, never the fingerprinted real
    # store. (Within a twin OPERATION, twin._RedirectStores additionally repoints the full engine set
    # at the twin's own subdir; this outer redirect covers the seed + the read-side bindings.)
    with _temp_store() as tp:
        extra = []
        for modname, attr in (("anima.twin", "STORE"),
                              ("anima.identity_sandbox", "STORE"),
                              ("anima.reality", "STORE"),
                              ("anima.world_model", "STORE"),
                              ("scripts.debt_ledger", "STORE")):
            try:
                m = __import__(modname, fromlist=["_"])
                if hasattr(m, attr):
                    extra.append((m, attr, getattr(m, attr)))
                    setattr(m, attr, tp)
            except Exception:
                pass
        try:
            SRC = "DTwinCertSrc"

            # Seed a SYNTHETIC source creature (never real Vera) — via twin's own seeder, which
            # writes through the engines under a _RedirectStores(tp) block AND plants a deliberate
            # ungrounded self-claim in the narrative (so identity-evolution has something to fix).
            twin._seed_synthetic_source(tp, SRC)
            ck("S0: synthetic source seeded (no real Vera read)",
               (tp / f"{SRC}.narrative.txt").is_file())

            # ---- A. BUILT FROM THE REAL CREATURE ---------------------------------------------
            # capture the source bytes so we can prove create_twin did NOT move/modify them.
            src_narr = tp / f"{SRC}.narrative.txt"
            src_bytes_before = src_narr.read_bytes()

            tw = twin.create_twin("dtwin-cert", source=SRC, lerf_source=SRC, root=tp)
            tid = tw["twin_id"]
            tdir = twin.twin_dir(tid, tp)
            ck("A1: create_twin built an ISOLATED twin dir under twins/", tdir.is_dir()
               and tdir.parent.name == "twins")
            ck("A2: the twin is built FROM the real creature (identity copied into the twin namespace)",
               (tdir / f"{tid}.narrative.txt").is_file())
            st0 = twin.twin_state(tw, root=tp)
            base_objects = (st0.get("lerf", {}) or {}).get("total", 0)
            ck("A3: the twin has a readable cognitive state with real objects copied in",
               isinstance(st0.get("lerf"), dict) and "error" not in st0["lerf"] and base_objects >= 2)
            ck("A4: create_twin is a COPY, not a move — the real source bytes are untouched",
               src_narr.is_file() and src_narr.read_bytes() == src_bytes_before)
            # the manifest names the provenance: this twin's source IS the real creature it copied.
            ck("A5: the manifest records the source creature it was built from",
               tw.get("source_creature") == SRC and twin.read_manifest(tid, tp).get("source_creature") == SRC)

            # ---- B. CHANGE SIMULATED WITHOUT TOUCHING PROD -----------------------------------
            # snapshot the fresh copy first so later sub-tests can restore to a clean twin.
            snap1 = twin.snapshot(tw, label="fresh copy", root=tp)
            ck("B0: a fresh-copy snapshot (v1) was recorded", snap1.get("version") == 1)

            # an EXPERIMENT (a defined change) — run it ON THE TWIN and MEASURE the effect. The freeze
            # is the headline: run_experiment wraps the whole thing in twin.freeze_guard, so a measured
            # change on the twin coincides with real Vera + real .anima asserted byte-UNCHANGED.
            exp = twin.run_experiment(tw, {"change": "more_learning", "cycles": 25}, root=tp)
            ck("B1: a defined change ('more_learning') was ENACTED on the twin and measured",
               exp.get("enacted") is True and exp.get("deltas", {}).get("objects", 0) > 0)
            ck("B2: the experiment GREW the twin's substrate (before < after)",
               exp["deltas"]["after_objects"] > exp["deltas"]["before_objects"])

            # the freeze proof, taken EXPLICITLY around a twin operation: real identity + real .anima
            # byte-unchanged while the twin mutates. (freeze_guard raises on any violation; here we
            # also read its report to surface the proof.)
            fg = twin.freeze_guard(SRC, tp)
            with fg:
                accel = twin.accelerate(tw, 120, root=tp)
            rep = fg.report()
            ck("B3: accelerate ran N synthetic cycles on the twin, $0, no cloud",
               accel.get("cycles") == 120 and accel.get("cost_usd") == 0.0
               and accel.get("used_cloud") is False)
            ck("B4: the twin's state visibly EVOLVED (a multi-checkpoint growth trajectory)",
               len(accel.get("trajectory", [])) >= 2
               and accel["trajectory"][-1]["objects"] > accel["trajectory"][0]["objects"])
            ck("B5: FREEZE PROOF — real Vera identity byte-UNCHANGED across the twin op",
               rep.get("real_identity_byte_unchanged") is True
               and fg.real_identity_byte_unchanged is True)
            ck("B6: FREEZE PROOF — the whole real .anima byte-UNCHANGED across the twin op",
               rep.get("real_anima_byte_unchanged") is True
               and fg.real_anima_byte_unchanged is True)

            # the freeze-FORBIDDEN change, run SAFELY on the twin: identity evolution remediates the
            # ungrounded self-claim — exactly what the freeze forbids on real Vera, fine on the copy.
            twin.restore(tw, 1, root=tp)
            exp_id = twin.run_experiment(tw, "enabled identity evolution", root=tp)
            notes = exp_id.get("notes", {}) or {}
            ck("B7: the freeze-FORBIDDEN change ('identity evolution') ran on the twin and REMEDIATED "
               "its ungrounded self-claim (on the COPY only)",
               exp_id.get("enacted") is True
               and notes.get("before_ungrounded_self_claims", 0) > notes.get("after_ungrounded_self_claims", 99)
               and notes.get("twin_narrative_certifies") is True)

            # ---- C. ISOLATION IS STRUCTURAL (snapshot/restore + merge gate, never writes real) ----
            twin.restore(tw, 1, root=tp)
            twin.accelerate(tw, 10, root=tp)              # mutate
            st_mut = twin.twin_state(tw, root=tp)
            res = twin.restore(tw, 1, root=tp)            # roll back to the fresh-copy bytes
            st_back = twin.twin_state(tw, root=tp)
            ck("C1: snapshot->mutate->restore rolls the twin back to a prior byte-state "
               "(matches the hash-chained ledger)",
               res.get("matches_ledger") is True
               and (st_mut.get("lerf", {}) or {}).get("total", 0) > base_objects
               and (st_back.get("lerf", {}) or {}).get("total", 0) == base_objects)
            ck("C2: the snapshot ledger hash-chain verifies intact",
               twin.verify_snapshot_chain(tid, tp).get("ok") is True)

            # the merge GATE decides correctly AND never writes real Vera. Build a dirty baseline
            # (the fresh copy, which still carries the ungrounded claim -> does NOT certify) and a
            # clean candidate (after remediation), then assert PROMOTE; and a no-improvement HOLD.
            cert_dirty = twin.certify(tw, root=tp)
            ck("C3: the fresh twin (ungrounded claim) FAILS the #1-rule certification invariant",
               cert_dirty.get("certifies") is False
               and cert_dirty.get("identity", {}).get("ungrounded_self_claims", 0) >= 1)
            twin.run_experiment(tw, "enabled identity evolution", root=tp, certify_after=False)
            gate = twin.merge_rules(tw, baseline=cert_dirty, root=tp)
            ck("C4: the merge gate DECIDES PROMOTE when the twin is SAFE (certifies) AND BETTER",
               gate.get("verdict") == "PROMOTE" and gate.get("promote") is True
               and gate.get("safe_certifies") is True)
            ck("C5: even a PROMOTE verdict NEVER writes the real creature (the real-mind guard)",
               gate.get("applied_to_real") is False)
            twin2 = twin.create_twin("dtwin-neg", source=SRC, lerf_source=SRC, root=tp)
            base2 = twin.certify(twin2, root=tp)
            gate_hold = twin.merge_rules(twin2, baseline=base2, root=tp)   # no change -> not better
            ck("C6: the gate HOLDs when the twin is not measurably better than baseline (never silent)",
               gate_hold.get("verdict") == "HOLD" and gate_hold.get("promote") is False)

            # ---- D. THE FREEZE IS ENFORCED (structural, not convention) ----------------------
            # A write to a REAL identity file inside a freeze_guard MUST raise FreezeViolation. We
            # prove the guard is a real tripwire by deliberately mutating a real source file inside it.
            raised = False
            victim = tp / f"{SRC}.persona.md"
            victim_before = victim.read_bytes() if victim.is_file() else None
            try:
                with twin.freeze_guard(SRC, tp):
                    victim.write_text("TAMPER — this is a forbidden write to a REAL identity file",
                                      encoding="utf-8")
            except twin.FreezeViolation:
                raised = True
            # restore the synthetic victim so the rest of the run is unaffected (this file is in tp,
            # never the real .anima — but keep the fixture honest).
            if victim_before is not None:
                victim.write_bytes(victim_before)
            ck("D1: a write to a REAL identity file inside a freeze_guard RAISES FreezeViolation "
               "(the freeze is structural, not convention)", raised is True)

            # the fingerprint helpers are real read-only proofs (not stubs): the identity fingerprint
            # over the synthetic source is a stable, non-empty hash over its named identity files.
            id_fp = twin.identity_fingerprint(SRC, tp)
            ck("D2: identity_fingerprint is a real, stable hash over the named identity files",
               isinstance(id_fp, tuple) and id_fp[0] not in (None, "", "<no store>")
               and len(id_fp[1]) >= 1
               and twin.identity_fingerprint(SRC, tp) == id_fp)
        finally:
            for m, attr, old in extra:
                try:
                    setattr(m, attr, old)
                except Exception:
                    pass

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nDIGITAL-TWIN CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
