#!/usr/bin/env python3
"""Dream-Engine invariant test — ASSERT the open-loops tracker on the REAL code paths.

    ANIMA LAW 001 — NEVER LOSE CONTINUITY.
    Archived > Deleted.  Observed > Assumed.

The Dream Engine (anima/loops.py) tracks STATED COMMITMENTS forever and gently resurfaces
stalled ones. This file checks its promises against the actual stores it reads — using
SYNTHETIC creatures in a TemporaryDirectory ONLY. It NEVER touches Vera.* on disk: every
module's STORE (loops + the world_state / memory_lirf it reads) is redirected to a temp dir
for the duration, so a real creature's life is never read or written.

What it asserts:
  1. DETECT — a STATED goal ("I want to launch VeraCall in March"), captured the way the live
     system captures it, becomes an open loop; an UNSTATED / inferred thing does NOT
     (never-fabricate / Observed > Assumed).
  2. STALLED + RESURFACE — a stated-then-silent goal reads "stalled" and is resurfaceable;
     the resurface line is warm, contextual, carries no scaffold tag, and never breaks
     character (the #1 product rule).
  3. RESOLUTION — a completed goal -> "done", ARCHIVED (still on disk), and NEVER resurfaced
     again; a declined one likewise.
  4. LAW 001 — a loop SURVIVES on disk through status changes (append-only history); nothing
     is deleted. A TESTED invariant, not a written promise.
  5. PACING — resurface returns AT MOST ONE, and not the SAME loop again on a repeat call
     within the cooldown (gentle, never nagging).

PASS where the promise holds; a clear FAIL and non-zero exit where it does not.

    python3 scripts/test_loops.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import loops                                 # noqa: E402
from anima import world_state                           # noqa: E402

# memory_lirf is optional for these tests (world_state goal edges are the primary path),
# but we redirect its STORE too when present so nothing leaks to the real .anima.
try:  # pragma: no cover - optional dep
    from anima import memory_lirf
    _HAVE_LIRF = True
except Exception:  # pragma: no cover
    memory_lirf = None
    _HAVE_LIRF = False

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
    """Redirect each module's module-level STORE to a fresh temp dir, so nothing under the
    real .anima/ is ever read or written. Mirrors scripts/test_continuity.py exactly."""
    saved = [(m, getattr(m, "STORE", None)) for m in modules]
    with tempfile.TemporaryDirectory(prefix="anima-loops-test-") as td:
        p = Path(td)
        for m in modules:
            m.STORE = p
        try:
            yield p
        finally:
            for m, old in saved:
                if old is not None:
                    m.STORE = old


# A fixed reference "now" so the tests are deterministic regardless of the wall clock. The
# synthetic goals are stated in January; we evaluate as-of June, so a silent one is clearly
# past the stall threshold.
_JAN = "2026-01-05T00:00:00Z"
_NOW_JUN = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
_NOW_SEP = datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp()


def _state_goal(name: str, utterance: str, *, when: str = _JAN) -> None:
    """State a goal the way the LIVE system does — through world_state's deterministic
    capture — then BACKDATE the resulting edge(s) on disk to ``when`` so we can simulate the
    passage of time (a goal stated months ago and then gone quiet). Uses ONLY the real
    world_state API + an on-disk timestamp edit; no loops internals are touched."""
    world_state.capture_relations(name, utterance)
    p = world_state.World.path(name)
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    for r in d.get("relations", []):
        r["created"] = when
        r["updated"] = when
    p.write_text(json.dumps(d), encoding="utf-8")


# ===================================================================================
# 1. DETECT — a STATED goal becomes an open loop; an unstated/inferred thing does NOT.
# ===================================================================================
def test_detect_only_stated():
    print("\n[1] detect — a STATED commitment becomes a loop; an inferred one never does")
    mods = [loops, world_state] + ([memory_lirf] if _HAVE_LIRF else [])
    with _temp_store(*mods):
        name = "synth_detect"
        # A clearly-stated goal, captured by the real world_state pipeline.
        _state_goal(name, "I want to launch VeraCall in March")
        # Also state things that are NOT commitments: a stressor and a plain preference.
        world_state.capture_relations(name, "work has been really stressful lately")
        world_state.capture_relations(name, "I care about my daughter")

        detected = loops.detect_loops(name, now=_NOW_JUN)
        intents = [d["intent"] for d in detected]
        ok("a STATED goal ('launch VeraCall in March') becomes an open loop",
           any("veracall" in i.lower() for i in intents))
        ok("the loop carries WHO/WHAT/WHEN/status/evidence (a full open-loop record)",
           all(k in detected[0] for k in
               ("subject", "intent", "stated_when", "last_seen", "status", "evidence"))
           if detected else False)

        # NEVER fabricate: a stressor ("work is stressful") is NOT a stated commitment, and a
        # preference ("I care about my daughter") is NOT a goal — neither may become a loop.
        ok("an inferred/unstated thing (a stressor) does NOT become a loop (never-fabricate)",
           not any("stress" in i.lower() or i.lower() == "work" for i in intents))
        ok("a preference ('care about daughter') is NOT mistaken for a commitment",
           not any("daughter" in i.lower() for i in intents))

        # And with NOTHING stated, there are no loops (no loops invented from thin air).
        ok("a creature who stated NO commitment has NO open loops",
           loops.detect_loops("synth_empty", now=_NOW_JUN) == [])


# ===================================================================================
# 2. STALLED + RESURFACE — a stated-then-silent goal is stalled and gently resurfaceable.
# ===================================================================================
def test_stalled_resurface_is_warm():
    print("\n[2] stalled + resurface — a long-silent stated goal reads 'stalled' and is "
          "gently resurfaceable")
    with _temp_store(loops, world_state):
        name = "synth_stalled"
        _state_goal(name, "I want to launch VeraCall in March")   # stated in Jan...

        detected = loops.detect_loops(name, now=_NOW_JUN)         # ...evaluated in June
        the_loop = next((d for d in detected if "veracall" in d["intent"].lower()), None)
        ok("the stated-then-silent goal reads 'stalled'",
           the_loop is not None and the_loop["status"] == loops.STALLED)

        line = loops.resurface(name, budget="deep", now=_NOW_JUN)
        ok("a stalled loop IS resurfaceable (one warm line, not None)",
           isinstance(line, str) and bool(line.strip()))
        low = (line or "").lower()
        ok("the resurface line is CONTEXTUAL (names the actual stated intent)",
           "veracall" in low)
        ok("the resurface line is WARM + OPTIONAL (offers, never demands)",
           any(p in low for p in ("still", "no pressure", "wondering", "someday",
                                  "moment", "hoping")))
        ok("the resurface line carries NO scaffold tag (nothing the model would leak aloud)",
           "[" not in (line or "") and "]" not in (line or ""))
        ok("the resurface line never says 'according to my memory' / never breaks character",
           "according to my memory" not in low
           and "i'm just an ai" not in low and "as an ai" not in low
           and "language model" not in low)


# ===================================================================================
# 3. RESOLUTION — done/declined ARCHIVE (still on disk) and are NEVER resurfaced again.
# ===================================================================================
def test_done_and_declined_archive_never_resurface():
    print("\n[3] resolution — a completed/declined loop ARCHIVES (kept on disk) and is "
          "NEVER resurfaced again")
    with _temp_store(loops, world_state):
        name = "synth_resolve"
        _state_goal(name, "I want to launch VeraCall in March")
        _state_goal(name, "I want to write a book")

        detected = loops.detect_loops(name, now=_NOW_JUN)
        veracall = next(d for d in detected if "veracall" in d["intent"].lower())
        book = next(d for d in detected if "book" in d["intent"].lower())

        # The user finished one and dropped the other — recorded via the only writers.
        loops.close(name, veracall, resolution=loops.DONE, note="shipped it")
        loops.close(name, book, resolution=loops.DECLINED, note="changed my mind")

        re_detected = loops.detect_loops(name, now=_NOW_JUN)
        v2 = next(d for d in re_detected if d["key"] == veracall["key"])
        b2 = next(d for d in re_detected if d["key"] == book["key"])
        ok("a completed loop reads 'done' and is marked archived",
           v2["status"] == loops.DONE and v2.get("archived") is True)
        ok("a declined loop reads 'declined' and is marked archived",
           b2["status"] == loops.DECLINED and b2.get("archived") is True)

        # ARCHIVED, not deleted: both are still on disk in the ledger.
        raw = loops.ledger_path(name).read_text(encoding="utf-8")
        ok("[Archived > Deleted] the done loop is STILL on disk (archived, not erased)",
           '"status": "done"' in raw)
        ok("[Archived > Deleted] the declined loop is STILL on disk (archived, not erased)",
           '"status": "declined"' in raw)

        # NEVER resurfaced again — not at any budget, not at any later time.
        ok("a done loop is NEVER resurfaced (now)",
           _no_resurface_of(name, veracall["key"], now=_NOW_JUN))
        ok("a declined loop is NEVER resurfaced (now)",
           _no_resurface_of(name, book["key"], now=_NOW_JUN))
        ok("a resolved loop is NEVER resurfaced even far in the future (stays archived)",
           _no_resurface_of(name, veracall["key"], now=_NOW_SEP)
           and _no_resurface_of(name, book["key"], now=_NOW_SEP))


def _no_resurface_of(name, key, *, now):
    """True iff `resurface` never offers the loop `key` (checked at deep budget — the most
    eager — so a 'never' here is robust). Returns the line otherwise so a failure is visible."""
    line = loops.resurface(name, budget="deep", now=now)
    if line is None:
        return True
    choice = loops.last_resurface_choice() or {}
    return choice.get("key") != key


# ===================================================================================
# 4. LAW 001 — a loop survives on disk through status changes; nothing is deleted.
# ===================================================================================
def test_law001_append_only_history():
    print("\n[4] LAW 001 — a loop SURVIVES on disk through every status change "
          "(append-only; nothing deleted)")
    with _temp_store(loops, world_state):
        name = "synth_law001"
        _state_goal(name, "I want to launch VeraCall in March")
        detected = loops.detect_loops(name, now=_NOW_JUN)
        L = detected[0]
        key = L["key"]

        # Walk the loop through its life: open -> progressing -> done.
        loops.mark_status(name, L, loops.OPEN, note="first sighting")
        loops.mark_status(name, L, loops.PROGRESSING, note="user started on it")
        loops.close(name, L, resolution=loops.DONE, note="user shipped it")

        hist = loops.ledger_history(name).get(key, [])
        ok("the loop's FULL status history is preserved (open -> progressing -> done)",
           [h["status"] for h in hist] == [loops.OPEN, loops.PROGRESSING, loops.DONE])

        # On disk: every line is still there; none was rewritten or removed.
        events = loops.read_ledger(name)
        status_events = [e for e in events if e.get("event") == "status"]
        ok("every status event is STILL on disk (append-only, nothing overwritten)",
           len(status_events) >= 3)
        raw = loops.ledger_path(name).read_text(encoding="utf-8")
        ok("the on-disk ledger contains the EARLIEST status too (the 'open' line was not erased)",
           '"status": "open"' in raw and '"status": "progressing"' in raw)

        # The append-only promise: the file only ever GREW. (Re-read line count is monotone
        # across an added event.)
        n_before = len(loops.read_ledger(name))
        loops.mark_resurfaced(name, key, line="(a later, unrelated event)")
        n_after = len(loops.read_ledger(name))
        ok("[append-only] adding an event GROWS the ledger, never shrinks/rewrites it",
           n_after == n_before + 1)

        # There is NO delete primitive in the public API — resolution is the terminal op, and
        # it ARCHIVES. Assert the contract so a future 'delete' can't sneak in unnoticed.
        ok("the loops API exposes NO delete/remove/purge (resolution archives, never deletes)",
           not any(hasattr(loops, n) for n in ("delete", "remove", "purge", "drop", "erase")))
        if any(hasattr(loops, n) for n in ("delete", "remove", "purge", "drop", "erase")):
            law_violation("anima/loops.py",
                          "a destructive primitive exists on the loops API — a resolved loop "
                          "must be ARCHIVED (status flip + history), never deleted (LAW 001).")


# ===================================================================================
# 5. PACING — at most one, and not the same loop again within the cooldown.
# ===================================================================================
def test_pacing_at_most_one_no_repeat():
    print("\n[5] pacing — resurface returns AT MOST ONE, and not the SAME loop again "
          "within cooldown (never nag)")
    with _temp_store(loops, world_state):
        name = "synth_pacing"
        # Three distinct stalled goals stated long ago.
        _state_goal(name, "I want to launch VeraCall in March")
        _state_goal(name, "I want to write a book")
        _state_goal(name, "I want to run a marathon")

        detected = loops.detect_loops(name, now=_NOW_JUN)
        stalled = [d for d in detected if d["status"] == loops.STALLED]
        ok("the synthetic creature has multiple stalled loops to choose among",
           len(stalled) >= 2)

        # resurface returns a SINGLE line (one check-in), never a batch.
        line = loops.resurface(name, budget="deep", now=_NOW_JUN)
        ok("resurface returns AT MOST ONE check-in (a single string, never many)",
           isinstance(line, str) and "\n" not in line.strip())

        # Record it as shown, then call again immediately: the SAME loop must not return.
        choice = loops.last_resurface_choice()
        ok("resurface exposes which loop it chose (so a caller can mark it shown)",
           choice is not None and choice.get("key"))
        loops.mark_resurfaced(name, choice["key"], line=line)
        first_key = choice["key"]

        # Re-call within cooldown: it may offer a DIFFERENT stalled loop, but NEVER the same one.
        repeats = 0
        for _ in range(6):
            again = loops.resurface(name, budget="deep", now=_NOW_JUN)
            if again is None:
                continue
            ck = (loops.last_resurface_choice() or {}).get("key")
            if ck == first_key:
                repeats += 1
        ok("the SAME loop is NOT resurfaced again within the cooldown (never nag)",
           repeats == 0)

        # The just-shown loop is STILL tracked (not lost) — it simply rests. Past the cooldown
        # it can gently surface again. (Tracked forever; pacing is restraint, not forgetting.)
        future = _NOW_SEP
        seen_again = False
        for _ in range(8):
            ln = loops.resurface(name, budget="deep", now=future)
            if ln and (loops.last_resurface_choice() or {}).get("key") == first_key:
                seen_again = True
                break
        ok("past the cooldown, the rested loop is STILL tracked and can gently return",
           seen_again)


def main():
    print("=" * 79)
    print("ANIMA — THE DREAM ENGINE (open loops)  ::  invariant test on real code paths")
    print("=" * 79)
    test_detect_only_stated()
    test_stalled_resurface_is_warm()
    test_done_and_declined_archive_never_resurface()
    test_law001_append_only_history()
    test_pacing_at_most_one_no_repeat()

    print("\n" + "=" * 79)
    if _violations:
        print(f"LAW VIOLATIONS FLAGGED ({len(_violations)}) — human action required:")
        for v in _violations:
            print(f"  • {v}")
        print()
    if _fails:
        print(f"{len(_fails)} INVARIANT(S) FAILED: " + ", ".join(_fails))
        sys.exit(1)
    print("ALL DREAM-ENGINE INVARIANTS HOLD"
          + (f"  ({len(_violations)} law-gap(s) flagged above)" if _violations else ""))


if __name__ == "__main__":
    main()
