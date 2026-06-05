#!/usr/bin/env python3
"""Continuity-invariant test — ASSERT ANIMA LAW 001 on the real code paths.

    NEVER LOSE CONTINUITY.
    Unknown > Lost.  Compressed > Forgotten.  Archived > Deleted.  Observed > Assumed.

Unlike a written law, this file *checks* the law against the actual subsystems that
drop, clear, overwrite, or delete data — using temporary/synthetic stores only. It
NEVER touches Vera.* on disk: every subsystem's STORE is redirected to a TemporaryDirectory
for the duration of the check, so a real creature's life is never read or written.

What it asserts:
  1. constitution.approved_loss — a discard is recordable only with what/why/approver,
     the record is append-only, and an un-approved loss is REFUSED.
  2. memory_lirf.retract — a retracted fact still EXISTS on disk (status='retracted'),
     never hard-deleted; survives a reload.  [Archived > Deleted]
  3. memory_lirf.merge — a superseded value survives in history[]; nothing overwritten
     into oblivion.  [Compressed > Forgotten / Archived > Deleted]
  4. portrait.consolidate — consolidate clears the raw chat log after distilling, but
     clear_log() now ARCHIVES the raw turns to chat.archive.jsonl first. We assert (a)
     a faithful portrait keeps the fact, and (b) even a LOSSY portrait no longer loses
     anything: the dropped fact survives in the archive.  [Compressed > Forgotten]
  5. reliability.backup — a snapshot PRESERVES live state byte-for-byte and restore can
     bring it back.  [Archived > Deleted]

PASS where the law holds; the script prints a clear FAIL and a LAW-VIOLATION flag where
it does not, and exits non-zero if any hard invariant breaks.

    python3 scripts/test_continuity.py
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import constitution                      # noqa: E402
from anima import memory_lirf                        # noqa: E402
from anima import world_state                         # noqa: E402
from anima import portrait                           # noqa: E402
from anima import reliability                        # noqa: E402

_fails: list[str] = []
_violations: list[str] = []


def ok(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def law_violation(subsystem, msg):
    """Flag a place where the LAW is violated by current code (not a test bug)."""
    print(f"  LAW-VIOLATION [{subsystem}] {msg}")
    _violations.append(f"{subsystem}: {msg}")


@contextlib.contextmanager
def _temp_store(*modules):
    """Redirect each module's module-level STORE (and constitution.STORE) to a fresh
    temp dir, so nothing under the real .anima/ is ever read or written."""
    saved = [(m, getattr(m, "STORE", None)) for m in modules]
    with tempfile.TemporaryDirectory(prefix="anima-continuity-") as td:
        p = Path(td)
        for m in modules:
            m.STORE = p
        try:
            yield p
        finally:
            for m, old in saved:
                if old is not None:
                    m.STORE = old


# ===================================================================================
# 1. THE LAW ITSELF — approved_loss is real, not decorative.
# ===================================================================================
def test_constitution():
    print("\n[1] constitution — approved_loss makes 'discard requires approval' real")
    # verbatim law present and intact
    ok("law text is the verbatim LAW 001",
       constitution.LAW_001.startswith("ANIMA LAW 001 — NEVER LOSE CONTINUITY")
       and "Unknown > Lost. Compressed > Forgotten. Archived > Deleted." in constitution.LAW_001)
    ok("four corollaries are present in order",
       constitution.COROLLARIES == ("Unknown > Lost.", "Compressed > Forgotten.",
                                     "Archived > Deleted.", "Observed > Assumed."))

    with _temp_store(constitution):
        name = " st_continuity"
        # an UN-approved loss is refused (no silent path)
        refused = False
        try:
            constitution.approved_loss(subsystem="x", what="", why="", approver="", name=name)
        except ValueError:
            refused = True
        ok("an un-explained loss is REFUSED (ValueError, no record written)",
           refused and not constitution.continuity_log_path(name).exists())

        # a properly-approved loss is recorded, append-only
        e1 = constitution.approved_loss(
            subsystem="portrait.consolidate", what="raw chat.jsonl (3 turns)",
            why="distilled to portrait", approver="sleep-cycle/operator", name=name)
        ok("an approved loss returns a stamped record",
           e1["law"] == "ANIMA LAW 001" and e1["approver"] == "sleep-cycle/operator" and e1["at"])
        constitution.approved_loss(
            subsystem="reliability._rotate", what="snapshot 20240101-000000",
            why="beyond keep=14", approver="reliability.backup", name=name)
        log = constitution.approved_losses(name)
        ok("the continuity ledger is append-only (both losses recorded, in order)",
           len(log) == 2 and log[0]["what"].startswith("raw chat") and "snapshot" in log[1]["what"])


# ===================================================================================
# 2. memory_lirf.retract — retracted fact still exists on disk.  [Archived > Deleted]
# ===================================================================================
def test_lirf_retract_keeps_row():
    print("\n[2] memory_lirf.retract — a retracted fact is KEPT on disk, never hard-deleted")
    with _temp_store(memory_lirf) as store:
        name = "st_retract"
        f = memory_lirf.Facts([])
        row = f.merge({"trait": "birthday", "value": "June 11"})
        bid = row["id"]
        f.retract(bid)
        # in memory: status flips, row remains
        ok("retract flips status to 'retracted' (row not removed from rows[])",
           any(r["id"] == bid and r["status"] == "retracted" for r in f.rows))
        ok("retract drops it from the ACTIVE lookup index (excluded from recall)",
           f.lookup(memory_lirf.SELF, "birthday") is None)
        # on disk: save persists ALL rows incl. retracted; survives reload
        f.save(name)
        raw = (store / f"{name}.lirf.json").read_text()
        ok("the .lirf.json on disk still CONTAINS the retracted value (not erased)",
           "June 11" in raw and "retracted" in raw)
        g = memory_lirf.Facts.load(name)
        ok("retracted row SURVIVES a reload from disk",
           any(r["id"] == bid and r["status"] == "retracted" for r in g.rows))


# ===================================================================================
# 3. memory_lirf.merge — superseded value survives in history[].  [Compressed>Forgotten]
# ===================================================================================
def test_lirf_merge_keeps_history():
    print("\n[3] memory_lirf.merge (newest-wins) — the displaced value SURVIVES in history[]")
    with _temp_store(memory_lirf) as store:
        name = "st_merge"
        f = memory_lirf.Facts([])
        f.merge({"trait": "city", "value": "Portland"})
        f.merge({"trait": "city", "value": "Seattle", "correction": True})
        r = f.lookup(memory_lirf.SELF, "city")
        ok("newest value wins in the active row", r["value"] == "Seattle")
        ok("the OLD value is preserved in history[] (not overwritten away)",
           any(h["value"] == "Portland" for h in r["history"]))
        f.save(name)
        raw = (store / f"{name}.lirf.json").read_text()
        ok("the superseded value is on disk too (history persists)", "Portland" in raw)
        g = memory_lirf.Facts.load(name)
        r2 = g.lookup(memory_lirf.SELF, "city")
        ok("history survives reload (full audit spine intact)",
           any(h["value"] == "Portland" for h in r2["history"]))


# ===================================================================================
# 4. portrait.consolidate — does NOT destroy a fact the portrait failed to capture.
#    This is the LAW's hardest test for Vera: distil-then-clear is Compressed>Forgotten
#    ONLY IF the meaning was captured first. We prove the gap on a controlled fake brain.
# ===================================================================================
class _FakeBrain:
    """A stand-in language model for portrait.consolidate. `reply()` returns a fixed
    'distilled portrait' that we control, so we can construct the exact failure case:
    a real fact in the raw log that the portrait DROPS."""
    def __init__(self, distilled):
        self._distilled = distilled

    def reply(self, system, user, history):
        return self._distilled


def test_portrait_consolidate_lossy():
    print("\n[4] portrait.consolidate — clearing the raw log AFTER distilling")
    with _temp_store(portrait, constitution) as store:
        name = "st_portrait"
        # raw log contains a load-bearing fact: the user's sister's name is Mara.
        portrait.log_turn(name, "my sister Mara just had a baby", "congratulations!")
        portrait.log_turn(name, "I work at Acme as a welder", "that's solid work")
        chat = portrait.log_path(name)
        ok("raw chat log exists before consolidate", chat.exists())

        # CASE A — a faithful portrait that captures the fact: clearing the raw log is
        # legitimate compression (Compressed > Forgotten holds).
        good = _FakeBrain("- works at Acme as a welder\n- has a sister named Mara who just had a baby")
        portrait.consolidate(name, good)
        port = portrait.load(name)
        ok("[A] consolidate distils into the portrait", "Acme" in port)
        ok("[A] the captured fact (Mara) SURVIVES in the portrait after the raw log is cleared",
           "Mara" in port)
        ok("[A] consolidate cleared the raw log (by design)", not chat.exists())

        # CASE B — the once-law-violating case, NOW CLOSED. A LOSSY portrait drops the
        # sister entirely; consolidate still clears the live chat log — BUT clear_log()
        # now APPENDS the raw turns to a permanent chat.archive.jsonl first, so the fact
        # the portrait omitted SURVIVES in the archive. Compressed > Forgotten holds.
        portrait.log_turn(name, "my sister Mara is moving to Denver in March", "exciting move")
        lossy = _FakeBrain("- works at Acme as a welder")           # drops Mara/Denver
        raw_before = portrait.read_transcript(name)
        ok("[B] raw log held the fact before consolidate", "Denver" in raw_before)
        portrait.consolidate(name, lossy)
        port2 = portrait.load(name)
        ok("[B] consolidate cleared the live raw log (by design)",
           not portrait.log_path(name).exists())
        ok("[B] the dropped fact (Denver) is NOT in the lossy portrait", "Denver" not in port2)
        # THE FIX: the raw turns were archived BEFORE the live log was cleared, so nothing
        # the portrait omitted is actually gone.
        archive = portrait._archive_path(name)
        archived_text = archive.read_text() if archive.exists() else ""
        ok("[B-FIX] clear_log archived the raw turns first (chat.archive.jsonl exists)",
           archive.exists())
        ok("[B-FIX] the fact the portrait OMITTED survives in the archive (Compressed>Forgotten holds)",
           "Denver" in archived_text)
        # Nothing was silently lost, so no approved_loss was needed and none was recorded.
        ok("[B-FIX] no silent loss → no approved_loss entry was required",
           len(constitution.approved_losses(name)) == 0)


# ===================================================================================
# 5. reliability.backup — a snapshot PRESERVES live state.  [Archived > Deleted]
# ===================================================================================
def test_backup_preserves():
    print("\n[5] reliability.backup — a snapshot preserves live state byte-for-byte")
    with tempfile.TemporaryDirectory(prefix="anima-backup-") as td:
        store = Path(td)
        name = "st_backup"
        # write a synthetic live HEART file (the Self — a SPEC'd, required critical file)
        live = store / f"{name}.json"
        payload = '{"name":"st_backup","seed":7,"n":3,"unrest":0.1,"birth_ts":1.0,"last_tick":2.0}'
        live.write_text(payload)
        res = reliability.backup(name, store=store, keep=14, ts="20260604-120000")
        snap = Path(res["dir"]) / f"{name}.json"
        ok("backup created a snapshot of the live heart (the Self)", snap.exists())
        ok("the snapshot is byte-identical to the live file", snap.read_text() == payload)

        # FIX (was a gap): the LIRF ledger (.lirf.json — the most rigorous, append-only
        # fact store) is now in reliability.SPECS, so backup() snapshots it and restore()
        # can bring it back. The strongest fact store finally has redundancy.
        lirf_backed_up = any(s.filename(name).endswith(".lirf.json") for s in reliability.SPECS)
        ok("[FIX] the LIRF ledger .lirf.json IS covered by backup SPECS (redundancy on corruption)",
           lirf_backed_up)
        archive_backed_up = any(s.filename(name).endswith(".chat.archive.jsonl") for s in reliability.SPECS)
        ok("[FIX] the raw chat archive .chat.archive.jsonl IS covered by backup SPECS",
           archive_backed_up)

        # rotation past keep deletes the OLDEST snapshot from the hot dir. Per Archived>
        # Deleted, that prune is a sanctioned but bounded loss — it must be ACCOUNTED, not
        # silent. _rotate now records a constitution.approved_loss naming exactly which
        # snapshot ids it pruned and why (snapshot rotation, keep=N) BEFORE any rmtree.
        # The continuity ledger lives beside the store, so point constitution.STORE there
        # to read back what _rotate recorded into THIS temp store.
        _saved_cstore = constitution.STORE
        constitution.STORE = store
        try:
            losses_before = len(constitution.approved_losses(name))
            for i in range(3):
                reliability.backup(name, store=store, keep=2, ts=f"20260604-12000{i+1}")
            kept = reliability._existing_snapshots(store)
            ok("rotation keeps exactly `keep` newest snapshots", len(kept) == 2)
            rotated_out = "20260604-120000" not in kept
            ok("oldest snapshot rotated out of the hot backups dir", rotated_out)

            # THE FIX (was a flagged law-gap): the pruned snapshots are no longer rmtree'd
            # silently. Every rotation that drops a snapshot records an approved_loss that
            # NAMES the pruned id(s) and the bound (keep=N) — Accounted, not silent.
            losses = constitution.approved_losses(name)
            ok("[FIX] rotation RECORDED an approved_loss for the pruned snapshot(s) (not silent rmtree)",
               len(losses) > losses_before)
            rot_losses = [e for e in losses if e.get("subsystem") == "reliability._rotate"]
            ok("[FIX] the rotation loss is attributed to reliability._rotate under LAW 001",
               bool(rot_losses) and rot_losses[-1]["law"] == "ANIMA LAW 001"
               and rot_losses[-1]["approver"] == "reliability.backup")
            ok("[FIX] the recorded loss NAMES the exact snapshot id that was pruned (auditable)",
               any("20260604-120000" in e["what"]
                   or "20260604-120000" in (e.get("detail", {}).get("pruned") or [])
                   for e in rot_losses))
            ok("[FIX] the recorded loss states the rotation bound keep=N (why)",
               any("keep=" in e["why"] or e.get("detail", {}).get("keep") is not None
                   for e in rot_losses))
            # The bound still holds: rotation does NOT retain snapshots unboundedly.
            ok("[FIX] rotation is still BOUNDED (keep enforced, dir cannot grow without limit)",
               len(reliability._existing_snapshots(store)) == 2)
        finally:
            constitution.STORE = _saved_cstore


# ===================================================================================
# 6. THE SILENT-LOSS BUG, CLOSED. Facts.load / World.load on a CORRUPT store must NEVER
#    silently return 0 rows: they recover from the latest good backup if one exists, else
#    fail LOUDLY (flagged-empty) and record an approved_loss. A corrupt load must NEVER
#    overwrite a good backup, and a CLEAN store must load byte-identically (happy path
#    unchanged). This is the auditor's 5-mode repro, run on the real load paths.
#    [Unknown > Lost — a clean stop beats a silently-wrong empty store]
# ===================================================================================
# The five ways a JSON store dies on disk. `null` is the sneaky one: valid JSON that decodes
# to Python None, which the old raw util.load_json silently read as 0 rows.
_CORRUPTION_MODES = {
    "truncate": b'{"version":1,"rows":[{"id":"f_x","entity":"you","trait":"birthday"',
    "empty":    b"",
    "garbage":  b"\xff\xfe\x00\x01\x02 not valid utf-8",
    "oops":     b"oops",
    "null":     b"null",
}


def _seed_lirf(name):
    """A synthetic creature with facts incl. a birthday (the auditor's seed)."""
    f = memory_lirf.Facts([])
    for c in f.capture(name, "my birthday is June 11"):
        f.merge(c)
    for c in f.capture(name, "I live in Portland"):
        f.merge(c)
    f.save(name)
    return f


def test_lirf_corrupt_load_recovers_or_fails_loud():
    print("\n[6] memory_lirf.Facts.load — a CORRUPT ledger recovers or fails LOUD, never silent 0 rows")
    # --- 6a: clean load is byte-identical (happy path unchanged) ---
    with _temp_store(memory_lirf, constitution) as store:
        name = "st_clean"
        _seed_lirf(name)
        before = (store / f"{name}.lirf.json").read_bytes()
        with contextlib.redirect_stderr(io.StringIO()) as buf:
            g = memory_lirf.Facts.load(name)
        after = (store / f"{name}.lirf.json").read_bytes()
        ok("[6a] clean load returns the real rows (birthday preserved)",
           g.value_of("birthday") == "June 11" and len(g.rows) == 2)
        ok("[6a] clean load is NOT flagged-empty", not getattr(g, "_load_flagged_empty", False))
        ok("[6a] clean load does NOT rewrite the good file (byte-identical)", after == before)
        ok("[6a] clean load is silent on stderr (no recovery noise)", buf.getvalue() == "")

    # --- 6b: WITH a good backup, every mode RECOVERS and never clobbers the backup ---
    for mode, corrupt in _CORRUPTION_MODES.items():
        with _temp_store(memory_lirf, constitution) as store:
            name = "st_recover"
            _seed_lirf(name)
            reliability.backup(name, store=store, ts="20260101-000000")
            good_bk = (store / "backups" / "20260101-000000" / f"{name}.lirf.json").read_bytes()
            (store / f"{name}.lirf.json").write_bytes(corrupt)              # corrupt the LIVE file
            with contextlib.redirect_stderr(io.StringIO()):
                g = memory_lirf.Facts.load(name)
            ok(f"[6b:{mode}] corrupt ledger RECOVERS from backup (rows back, NOT silent 0)",
               len(g.rows) == 2 and g.value_of("birthday") == "June 11")
            bk_now = (store / "backups" / "20260101-000000" / f"{name}.lirf.json").read_bytes()
            ok(f"[6b:{mode}] the corrupt load did NOT clobber the good backup",
               bk_now == good_bk)

    # --- 6c: WITHOUT a backup, every mode fails LOUD (flagged-empty) + records approved_loss ---
    for mode, corrupt in _CORRUPTION_MODES.items():
        with _temp_store(memory_lirf, constitution) as store:
            name = "st_loud"
            _seed_lirf(name)
            if (store / "backups").exists():
                shutil.rmtree(store / "backups")        # ensure NO good backup exists
            (store / f"{name}.lirf.json").write_bytes(corrupt)
            with contextlib.redirect_stderr(io.StringIO()):
                g = memory_lirf.Facts.load(name)
            flagged = getattr(g, "_load_flagged_empty", False)
            losses = constitution.approved_losses(name)
            ok(f"[6c:{mode}] no backup -> flagged-empty (a clean STOP, never a silent 0-rows)",
               flagged and len(g.rows) == 0)
            ok(f"[6c:{mode}] the unrecoverable loss is RECORDED via approved_loss (not silent)",
               len(losses) >= 1 and losses[-1]["law"] == "ANIMA LAW 001")


def test_world_corrupt_load_recovers_or_fails_loud():
    print("\n[7] world_state.World.load — a CORRUPT relation store recovers or fails LOUD")
    rels_modes = dict(_CORRUPTION_MODES)
    rels_modes["truncate"] = b'{"version":1,"relations":[{"id":"f_x"'   # truncate the right container

    def _seed_world(name):
        w = world_state.World([])
        w.add("you", "stressed_by", "work", kind="problem")
        w.add("work", "because", "new manager")
        w.save(name)

    # clean load unchanged
    with _temp_store(world_state, memory_lirf, constitution) as store:
        name = "stw_clean"
        _seed_world(name)
        with contextlib.redirect_stderr(io.StringIO()) as buf:
            w = world_state.World.load(name)
        ok("[7a] clean world load returns the real relations", len(w.active()) == 2)
        ok("[7a] clean world load is NOT flagged-empty", not getattr(w, "_load_flagged_empty", False))
        ok("[7a] clean world load is silent on stderr", buf.getvalue() == "")

    # with a backup -> recover; without -> flagged-empty + approved_loss
    for mode, corrupt in rels_modes.items():
        with _temp_store(world_state, memory_lirf, constitution) as store:
            name = "stw_recover"
            _seed_world(name)
            b = reliability.backup(name, store=store, ts="20260101-000000")
            ok(f"[7b:{mode}] .world.json is covered by backup SPECS (was the missing redundancy)",
               f"{name}.world.json" in b["files"])
            (store / f"{name}.world.json").write_bytes(corrupt)
            with contextlib.redirect_stderr(io.StringIO()):
                w = world_state.World.load(name)
            ok(f"[7b:{mode}] corrupt world store RECOVERS from backup (NOT silent 0)",
               len(w.active()) == 2)

    for mode, corrupt in rels_modes.items():
        with _temp_store(world_state, memory_lirf, constitution) as store:
            name = "stw_loud"
            _seed_world(name)
            if (store / "backups").exists():
                shutil.rmtree(store / "backups")
            (store / f"{name}.world.json").write_bytes(corrupt)
            with contextlib.redirect_stderr(io.StringIO()):
                w = world_state.World.load(name)
            ok(f"[7c:{mode}] no backup -> flagged-empty world store (clean STOP, not silent)",
               getattr(w, "_load_flagged_empty", False) and len(w.active()) == 0)
            ok(f"[7c:{mode}] the world-store loss is RECORDED via approved_loss",
               len(constitution.approved_losses(name)) >= 1)


def test_atomic_write_fsyncs():
    print("\n[8] util._atomic_write — durability barrier (flush + fsync) before publish")
    import inspect
    from anima import util
    src = inspect.getsource(util._atomic_write)
    ok("[8] _atomic_write calls f.flush() before os.replace", "f.flush()" in src)
    ok("[8] _atomic_write calls os.fsync(...) before os.replace", "os.fsync(" in src)
    # and it still actually writes correctly (round-trip)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.json"
        util.save_json(p, {"rows": [1, 2, 3]})
        ok("[8] _atomic_write still round-trips content correctly",
           util.load_json(p) == {"rows": [1, 2, 3]})


def main():
    print("=" * 79)
    print("ANIMA LAW 001 — NEVER LOSE CONTINUITY  ::  invariant test on real code paths")
    print("=" * 79)
    test_constitution()
    test_lirf_retract_keeps_row()
    test_lirf_merge_keeps_history()
    test_portrait_consolidate_lossy()
    test_backup_preserves()
    test_lirf_corrupt_load_recovers_or_fails_loud()
    test_world_corrupt_load_recovers_or_fails_loud()
    test_atomic_write_fsyncs()

    print("\n" + "=" * 79)
    if _violations:
        print(f"LAW VIOLATIONS FLAGGED ({len(_violations)}) — human action required:")
        for v in _violations:
            print(f"  • {v}")
        print()
    if _fails:
        print(f"{len(_fails)} INVARIANT(S) FAILED: " + ", ".join(_fails))
        sys.exit(1)
    print("ALL CONTINUITY INVARIANTS HOLD"
          + (f"  ({len(_violations)} law-gap(s) flagged above for the human to close)"
             if _violations else ""))


if __name__ == "__main__":
    main()
