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
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import constitution                      # noqa: E402
from anima import memory_lirf                        # noqa: E402
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
        # Deleted, that snapshot is gone for good unless copied off first — note it.
        for i in range(3):
            reliability.backup(name, store=store, keep=2, ts=f"20260604-12000{i+1}")
        kept = reliability._existing_snapshots(store)
        ok("rotation keeps exactly `keep` newest snapshots", len(kept) == 2)
        rotated_out = "20260604-120000" not in kept
        if rotated_out:
            law_violation(
                "reliability._rotate (anima/reliability.py:453-462)",
                "snapshots beyond keep=14 are shutil.rmtree'd with no cold-archive and no "
                "approved_loss() (tension with Archived>Deleted). The LIVE ledger is never "
                "lost (it's the source of truth + every newer snapshot), so this is LOW "
                "severity, but old snapshots vanish silently. FIX: move pruned snapshots to "
                "a cold backups/archive/ OR record approved_loss() on prune.")
        ok("[note] oldest snapshot rotated out of the hot backups dir", rotated_out)


def main():
    print("=" * 79)
    print("ANIMA LAW 001 — NEVER LOSE CONTINUITY  ::  invariant test on real code paths")
    print("=" * 79)
    test_constitution()
    test_lirf_retract_keeps_row()
    test_lirf_merge_keeps_history()
    test_portrait_consolidate_lossy()
    test_backup_preserves()

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
