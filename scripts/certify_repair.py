#!/usr/bin/env python3
"""
certify_repair — the CONVERSATION-REPAIR killer test, end-to-end through the REAL server._turn.

This is the cert the Program Reality Audit + Pattern Observatory demanded for the #1 WALLPAPER
(`conversation_repair`). It proves the *anchorless correction* path live, not just that code exists:

  A. THE WALLPAPER (reproduced) — on the normal capture path, "scratch that — not Rex, his name is
     Atlas" lifts NOTHING: dog_name LINGERS on Rex and Atlas is LOST. (This is the bug, asserted.)

  B. THE FIX (the seam) — the same utterance through server._turn rebinds the slot: dog_name is
     SUPERSEDED to Atlas, the old value Rex is preserved in history[] (reason "user-corrected"), the
     labelled confirmation ships through the SAME #1-rule final_output_gate as every reply (backend
     "repair:supersede", no LLM, no second return path), and the Whole-System MRI records the seam.

It also proves the seam is SAFE: a normal turn never triggers it (no hijack), and a correction whose
rejected value isn't on record resolves to nothing (honest fall-through, no spurious write).

Hermetic: every store is redirected to a temp dir via gate0_prime_experience._temp_store (which
redirects `memory_lirf` among others). The REAL .anima is never read or written. No model is needed —
the deterministic seam short-circuits BEFORE the LLM. Exit 0 == CERTIFIED, 1 == FAIL.
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

_REPAIR_STAGES = {"repair_correction_detected", "deterministic_repair_reply", "final_gate"}
_SUPERSEDE_REASONS = {"user-corrected", "superseded", "user-edited"}


def _dog(name, server, memory_lirf):
    """The active dog_name value on disk for `name` (None if absent)."""
    return memory_lirf.Facts.load(name).value_of("dog_name")


def _dog_row(name, memory_lirf):
    f = memory_lirf.Facts.load(name)
    return f.lookup(memory_lirf.SELF, "dog_name")


def main() -> int:
    import anima.server as server
    from anima import memory_lirf, repair, telemetry, mouth

    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("CONVERSATION-REPAIR killer test (through anima.server._turn)")
    print("=" * 64)
    with _temp_store():
        # ---- A. reproduce the WALLPAPER on the normal capture path -------------------------
        nb = "RepairBug0"
        server._ensure(nb, 64)
        memory_lirf.capture(nb, "my dog's name is Rex")
        before_bug = _dog(nb, server, memory_lirf)
        memory_lirf.capture(nb, "scratch that — not Rex, his name is Atlas")   # normal path, no seam
        lingered = _dog(nb, server, memory_lirf)
        print(f"  [A] normal capture: seeded dog_name={before_bug!r} -> after correction={lingered!r}")
        ck("WALLPAPER reproduced: anchorless correction LINGERS on Rex (Atlas lost on the bare path)",
           before_bug == "Rex" and lingered == "Rex")

        # ---- B. the seam, end-to-end through the real _turn --------------------------------
        nf = "RepairFix0"
        server._ensure(nf, 64)
        memory_lirf.capture(nf, "my dog's name is Rex")
        ck("[B] seed: dog_name == Rex before the correction", _dog(nf, server, memory_lirf) == "Rex")

        prompt = "scratch that — not Rex, his name is Atlas"
        res = server._turn(nf, prompt, voice=False)
        reply = (res or {}).get("reply", "")
        backend = (res or {}).get("backend", "")
        print(f"  [B] _turn reply: {reply!r}")
        print(f"  [B] backend: {backend!r}")

        ck("backend == repair:supersede", backend == "repair:supersede")
        ck("reply names the corrected value (Atlas)", "atlas" in reply.lower())
        ck("reply labels it as an update/correction",
           any(w in reply.lower() for w in ("updated", "correction", "corrected", "from rex")))
        ck("reply non-empty (output integrity)", bool(reply.strip()))

        # SAME #1-rule final gate every reply uses — shipped == certified final text (no second path).
        raw = repair.confirmation("dog_name", "Rex", "Atlas")
        ck("shipped == certified final text (through final_output_gate, no second path)",
           reply == mouth.final_output_gate(raw))
        ck("response completeness guard passes", mouth.response_complete(reply))

        # the ledger was actually rebound: Atlas active, Rex preserved in history (audit spine).
        after = _dog(nf, server, memory_lirf)
        row = _dog_row(nf, memory_lirf)
        hist_vals = [(h.get("value"), h.get("reason")) for h in (row or {}).get("history", [])]
        print(f"  [B] dog_name after: {after!r}   history: {hist_vals}")
        ck("SUPERSEDED: dog_name is now Atlas (active)", after == "Atlas")
        ck("dog_name row status == active", (row or {}).get("status") == "active")
        ck("old value Rex preserved in history[] with a supersede reason (LAW-001, nothing deleted)",
           any(v == "Rex" and (r in _SUPERSEDE_REASONS) for v, r in hist_vals))

        # the Whole-System MRI recorded the deterministic repair seam for this turn.
        tr = telemetry.last_trace(nf) or {}
        stages = {s.get("stage") for s in (tr.get("stages") or [])}
        ck(f"MRI records the repair seam {sorted(_REPAIR_STAGES)}", _REPAIR_STAGES <= stages)

        # ---- C. a SECOND correction supersedes again (idempotent rebind) ------------------
        res2 = server._turn(nf, "actually, not Atlas — his name is Cooper", voice=False)
        ck("second correction backend == repair:supersede",
           (res2 or {}).get("backend") == "repair:supersede")
        after2 = _dog(nf, server, memory_lirf)
        row2 = _dog_row(nf, memory_lirf)
        hist2 = [h.get("value") for h in (row2 or {}).get("history", [])]
        ck("SUPERSEDED again: dog_name is now Cooper", after2 == "Cooper")
        ck("both prior values (Rex, Atlas) preserved in history[]",
           "Rex" in hist2 and "Atlas" in hist2)

        # ---- C2. the TRANSCRIPTION / restate form (the contract names it explicitly) -------
        nt = "RepairTx0"
        server._ensure(nt, 64)
        memory_lirf.capture(nt, "my dog's name is Rex")
        res_tx = server._turn(nt, "that transcription was wrong, I said Atlas", voice=False)
        ck("transcription correction backend == repair:supersede (no model)",
           (res_tx or {}).get("backend") == "repair:supersede")
        ck("transcription correction supersedes: dog_name == Atlas",
           _dog(nt, server, memory_lirf) == "Atlas")

        # ---- D. NO HIJACK + honest fall-through -------------------------------------------
        ck("normal chat -> classify_repair False (no hijack)",
           not repair.classify_repair("how are you feeling today?"))
        ck("a fresh statement -> classify_repair False (not a correction)",
           not repair.classify_repair("my dog is Rex"))
        ck("a question -> classify_repair False",
           not repair.classify_repair("what's my dog's name?"))
        # correction whose rejected value isn't on record -> resolves to nothing, writes nothing.
        n_before = _dog(nf, server, memory_lirf)
        out_none = repair.repair(nf, "scratch that — not Zoltan, his name is Atlas")
        ck("unknown rejected value -> repair() returns None (honest fall-through)", out_none is None)
        ck("no spurious write: dog_name unchanged after an unresolvable correction",
           _dog(nf, server, memory_lirf) == n_before == "Cooper")

    print()
    print("  RESULT:  WALLPAPER (LINGERS->Rex)  ->  SEAM (SUPERSEDED->Atlas->Cooper)")
    ok = not fails
    print("CONVERSATION-REPAIR CERT: " + ("CERTIFIED" if ok else f"FAIL ({len(fails)})"))
    if not ok:
        for f in fails:
            print("   - " + f)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
