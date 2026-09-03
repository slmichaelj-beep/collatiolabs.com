#!/usr/bin/env python3
"""certify_continuity_law — ANIMA LAW 001 (NEVER LOSE CONTINUITY) proven as enforced code on the
LIVE load paths the turn actually uses.

A written law is decoration; an enforced one is architecture. This certifies the two halves of
LAW 001 the way the deployed creature relies on them — deterministically, offline, hermetically:

  A. THE LAW IS RECORD-OR-REFUSE — constitution.LAW_001 + the four corollaries are present
     verbatim; constitution.approved_loss REFUSES an unexplained loss (ValueError, and NO ledger
     file is written — there is no silent path) and RECORDS a properly-approved one to an
     append-only `<name>.continuity.jsonl` stamped with law/approver/at (read back in order).

  B. THE LIVE LIRF LOAD RECOVERS — the PRODUCTION read path memory_lirf.Facts.load (the one the
     live turn calls) self-heals: seed a real ledger (birthday=June 11), back it up, then corrupt
     the live .lirf.json on disk in all five ways a JSON store dies — truncate / empty / garbage /
     "oops" / the sneaky literal `null` (valid JSON, decodes to None, the old raw loader silently
     read as 0 rows). For EACH mode Facts.load restores the rows from the good backup (birthday
     back), is NOT flagged-empty, and NEVER clobbers the good backup.

  C. THE LIVE LIRF LOAD FAILS LOUD — with NO good backup, every corruption mode makes Facts.load
     return a clearly FLAGGED-EMPTY store (0 rows) AND record a constitution.approved_loss under
     LAW 001 — a clean, accounted STOP, never a silently-wrong empty store. Unknown > Lost.

  D. THE LIVE WORLD LOAD MIRRORS IT — world_state.World.load (the production relation-graph read)
     recovers from backup on corruption, and without a backup stops flagged-empty + records the
     loss. Same guarantee on the second memory store.

  E. THE HEART REFUSES TO FABRICATE — reliability.guarded_load (the Heart loader, line ~68 of the
     reliability docstring's own example) returns the rows on a clean heart and RAISES
     (RuntimeError, no silent default) when the heart is corrupt and no backup exists: for HER
     identity a loud stop beats a wrong guess.

Hermetic: every store (memory_lirf/world_state/constitution.STORE via _temp_store, plus
reliability.DEFAULT_STORE redirected here) points at a TemporaryDirectory; the real .anima is
fingerprinted before/after and asserted byte-identical. No live model, no network. Exit 0 ==
CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import shutil
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

# The five ways a JSON store dies on disk. `null` is the sneaky one: valid JSON that decodes to
# Python None, which a raw load_json silently reads as 0 rows (total silent memory loss).
_CORRUPTION_MODES = {
    "truncate": b'{"version":1,"rows":[{"id":"f_x","entity":"you","trait":"birthday"',
    "empty":    b"",
    "garbage":  b"\xff\xfe\x00\x01\x02 not valid utf-8",
    "oops":     b"oops",
    "null":     b"null",
}


def main() -> int:
    from anima import constitution, memory_lirf, world_state, reliability
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("CONTINUITY LAW — ANIMA LAW 001: record-or-refuse + the live loads never silently lose identity")
    print("=" * 98)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        # reliability.DEFAULT_STORE is NOT covered by _temp_store — redirect it (and restore in
        # finally) so backup()/latest_good_backup()/restore() resolve against the SAME temp dir the
        # production loaders pass as `store=<module>.STORE`.
        saved_rel_store = getattr(reliability, "DEFAULT_STORE", None)
        reliability.DEFAULT_STORE = tp
        try:
            # ---- A. THE LAW IS RECORD-OR-REFUSE ----------------------------------------------
            ck("A1: LAW_001 is present verbatim (NEVER LOSE CONTINUITY + the corollary line)",
               constitution.LAW_001.startswith("ANIMA LAW 001 — NEVER LOSE CONTINUITY")
               and "Unknown > Lost. Compressed > Forgotten. Archived > Deleted." in constitution.LAW_001)
            ck("A2: the four preservation corollaries are present, in order",
               constitution.COROLLARIES == ("Unknown > Lost.", "Compressed > Forgotten.",
                                            "Archived > Deleted.", "Observed > Assumed."))
            law_name = "st_continuity_law"
            refused = False
            try:
                constitution.approved_loss(subsystem="x", what="", why="", approver="", name=law_name)
            except ValueError:
                refused = True
            ck("A3: an UNEXPLAINED loss is REFUSED (ValueError) and writes NO ledger (no silent path)",
               refused and not constitution.continuity_log_path(law_name).exists())
            e1 = constitution.approved_loss(
                subsystem="portrait.consolidate", what="raw chat.jsonl (3 turns)",
                why="distilled to portrait", approver="sleep-cycle/operator", name=law_name)
            ck("A4: a PROPERLY-approved loss returns a stamped LAW-001 record",
               e1["law"] == "ANIMA LAW 001" and e1["approver"] == "sleep-cycle/operator" and e1["at"])
            constitution.approved_loss(
                subsystem="reliability._rotate", what="snapshot 20260101-000000",
                why="beyond keep=14", approver="reliability.backup", name=law_name)
            log = constitution.approved_losses(law_name)
            ck("A5: the continuity ledger is APPEND-ONLY (both losses recorded, oldest->newest)",
               len(log) == 2 and log[0]["what"].startswith("raw chat") and "snapshot" in log[1]["what"])

            # ---- B. THE LIVE LIRF LOAD RECOVERS (production memory_lirf.Facts.load) -----------
            def _seed_lirf(nm):
                f = memory_lirf.Facts([])
                for c in f.capture(nm, "my birthday is June 11"):
                    f.merge(c)
                for c in f.capture(nm, "I live in Portland"):
                    f.merge(c)
                f.save(nm)
                return f

            for mode, corrupt in _CORRUPTION_MODES.items():
                nm = "st_lirf_recover"
                _seed_lirf(nm)
                reliability.backup(nm, store=tp, ts="20260101-000000")
                good_bk = (tp / "backups" / "20260101-000000" / f"{nm}.lirf.json").read_bytes()
                (tp / f"{nm}.lirf.json").write_bytes(corrupt)            # corrupt the LIVE ledger
                with contextlib.redirect_stderr(io.StringIO()):
                    g = memory_lirf.Facts.load(nm)                       # THE PRODUCTION READ PATH
                ck(f"B[{mode}]: corrupt LIRF ledger RECOVERS via Facts.load (birthday back, NOT silent 0)",
                   len(g.rows) == 2 and g.value_of("birthday") == "June 11"
                   and not getattr(g, "_load_flagged_empty", False))
                bk_now = (tp / "backups" / "20260101-000000" / f"{nm}.lirf.json").read_bytes()
                ck(f"B[{mode}]: the corrupt load did NOT clobber the good backup",
                   bk_now == good_bk)
                # clean slate for the next mode so backups never accumulate across iterations
                shutil.rmtree(tp / "backups", ignore_errors=True)
                (tp / f"{nm}.lirf.json").unlink(missing_ok=True)
                (tp / f"{nm}.continuity.jsonl").unlink(missing_ok=True)

            # ---- C. THE LIVE LIRF LOAD FAILS LOUD (no backup -> flagged-empty + approved_loss) -
            for mode, corrupt in _CORRUPTION_MODES.items():
                nm = "st_lirf_loud"
                _seed_lirf(nm)
                shutil.rmtree(tp / "backups", ignore_errors=True)       # ensure NO good backup
                (tp / f"{nm}.continuity.jsonl").unlink(missing_ok=True)
                (tp / f"{nm}.lirf.json").write_bytes(corrupt)
                with contextlib.redirect_stderr(io.StringIO()):
                    g = memory_lirf.Facts.load(nm)                       # THE PRODUCTION READ PATH
                flagged = getattr(g, "_load_flagged_empty", False)
                losses = constitution.approved_losses(nm)
                ck(f"C[{mode}]: no backup -> Facts.load is FLAGGED-EMPTY (clean STOP, never a silent 0)",
                   flagged and len(g.rows) == 0)
                ck(f"C[{mode}]: the unrecoverable identity loss is RECORDED via approved_loss (LAW 001)",
                   len(losses) >= 1 and losses[-1]["law"] == "ANIMA LAW 001")
                (tp / f"{nm}.lirf.json").unlink(missing_ok=True)
                (tp / f"{nm}.continuity.jsonl").unlink(missing_ok=True)

            # ---- D. THE LIVE WORLD LOAD MIRRORS IT (production world_state.World.load) ---------
            def _seed_world(nm):
                w = world_state.World([])
                w.add("you", "stressed_by", "work", kind="problem")
                w.add("work", "because", "new manager")
                w.save(nm)

            wnm = "stw_recover"
            _seed_world(wnm)
            b = reliability.backup(wnm, store=tp, ts="20260101-000000")
            ck("D1: the .world.json relation store is covered by backup SPECS (redundancy exists)",
               f"{wnm}.world.json" in b["files"])
            (tp / f"{wnm}.world.json").write_bytes(b"null")             # the sneaky total-loss case
            with contextlib.redirect_stderr(io.StringIO()):
                w = world_state.World.load(wnm)                          # THE PRODUCTION READ PATH
            ck("D2: corrupt world store RECOVERS via World.load (relations back, NOT silent 0)",
               len(w.active()) == 2)
            shutil.rmtree(tp / "backups", ignore_errors=True)
            (tp / f"{wnm}.world.json").unlink(missing_ok=True)
            (tp / f"{wnm}.continuity.jsonl").unlink(missing_ok=True)

            wnm2 = "stw_loud"
            _seed_world(wnm2)
            shutil.rmtree(tp / "backups", ignore_errors=True)
            (tp / f"{wnm2}.continuity.jsonl").unlink(missing_ok=True)
            (tp / f"{wnm2}.world.json").write_bytes(b"oops")
            with contextlib.redirect_stderr(io.StringIO()):
                w2 = world_state.World.load(wnm2)                        # THE PRODUCTION READ PATH
            ck("D3: no backup -> World.load is FLAGGED-EMPTY (clean STOP, not a silent 0)",
               getattr(w2, "_load_flagged_empty", False) and len(w2.active()) == 0)
            ck("D4: the world-store loss is RECORDED via approved_loss (LAW 001)",
               len(constitution.approved_losses(wnm2)) >= 1
               and constitution.approved_losses(wnm2)[-1]["law"] == "ANIMA LAW 001")

            # ---- E. THE HEART REFUSES TO FABRICATE (reliability.guarded_load) -----------------
            # The Heart loader heals on a PARSE/finite failure (its corruption gate is _parse_json +
            # _finite_scan, not the memory-store shape gate). We corrupt with broken JSON — the exact
            # corruption reliability's own selftest uses ("{ broken") — so this exercises the heart
            # loader's real recovery seam.
            from anima.heart import Heart
            from anima.util import save_json
            hnm = "st_heart_guard"
            heart = Heart.born(hnm, seed=7, n=8, now=1000.0).tend(0.5, now=1100.0)
            save_json(tp / f"{hnm}.json", heart.to_dict())
            reliability.backup(hnm, store=tp, ts="20260101-000000")
            (tp / f"{hnm}.json").write_bytes(b"{ broken")               # corrupt the live heart
            with contextlib.redirect_stderr(io.StringIO()):
                healed = reliability.guarded_load(hnm, tp / f"{hnm}.json", store=tp)
            ck("E1: guarded_load SELF-HEALS the Heart from backup (a finite, real heart back)",
               isinstance(healed, dict) and healed.get("name") == hnm
               and reliability._finite_scan(healed) is None)

            hnm2 = "st_heart_noback"
            heart2 = Heart.born(hnm2, seed=3, n=8, now=1000.0).tend(0.5, now=1100.0)
            save_json(tp / f"{hnm2}.json", heart2.to_dict())
            shutil.rmtree(tp / "backups", ignore_errors=True)          # ensure NO good backup
            (tp / f"{hnm2}.json").write_bytes(b"{ broken")
            raised = False
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    reliability.guarded_load(hnm2, tp / f"{hnm2}.json", store=tp)
            except RuntimeError:
                raised = True
            ck("E2: with NO backup, guarded_load RAISES rather than fabricating her state (no silent default)",
               raised)
        finally:
            if saved_rel_store is not None:
                reliability.DEFAULT_STORE = saved_rel_store

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nCONTINUITY-LAW CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
