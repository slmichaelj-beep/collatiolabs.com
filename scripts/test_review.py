#!/usr/bin/env python3
"""Review-engine test — the LIFE REVIEW ENGINE and, above all, the LAW-001 COMPRESSION
INVARIANT, asserted on the real code paths.

    Compressed > Forgotten — ENFORCED.

This is the keystone test for ``anima/review.py``: the nightly cortex that compresses a
life into daily -> weekly -> monthly -> yearly states. The single most important property
it pins is the LAW-001 compression invariant — *nothing significant is dropped in
compression unless an approved_loss was recorded*. If that invariant ever breaks, this
file FAILS the build.

It uses ONLY synthetic creatures and a TemporaryDirectory STORE (the test_continuity.py
pattern): every module's module-level ``STORE`` is redirected into a fresh temp dir for the
duration, so a real creature's Vera.* on disk is NEVER read or written.

What it asserts:
  1. DAILY STATE — a daily state captures what_changed / what_mattered / what_unresolved
     from a seeded meaning-state + the day's facts, and what_to_remember from milestones.
  2. THE LAW-001 COMPRESSION INVARIANT — seed several daily states; a what_to_remember item
     at the daily level SURVIVES into the weekly (and weekly -> monthly); assert NO
     significant item vanishes in compression unless an approved_loss was recorded.
  3. MILESTONES ride up through every level (daily -> weekly -> monthly -> yearly)
     UNCOMPRESSED.
  4. QUERYABLE — a past state is retrievable by period ("what was happening in March?").
  5. NEVER-FABRICATE — an empty day yields an honest "a quiet day", not invention; and a
     NO-DIAGNOSIS gate — no medical/clinical term appears in any generated item.
  6. RENDER leaks no scaffold tag and never breaks character.

    python3 scripts/test_review.py
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import review                              # noqa: E402
from anima import constitution                        # noqa: E402
from anima import world_state                         # noqa: E402
from anima import memory_lirf                         # noqa: E402
from anima import meaning                             # noqa: E402

_fails: list = []
_violations: list = []


def ok(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def law_violation(subsystem, msg):
    print(f"  LAW-VIOLATION [{subsystem}] {msg}")
    _violations.append(f"{subsystem}: {msg}")


@contextlib.contextmanager
def _temp_store(*modules):
    """Redirect each module's module-level STORE to a fresh temp dir, so nothing under the
    real .anima/ is read or written (the test_continuity.py pattern)."""
    saved = [(m, getattr(m, "STORE", None)) for m in modules]
    with tempfile.TemporaryDirectory(prefix="anima-review-") as td:
        p = Path(td)
        for m in modules:
            m.STORE = p
        try:
            yield p
        finally:
            for m, old in saved:
                if old is not None:
                    m.STORE = old


_ALL = (review, constitution, world_state, memory_lirf, meaning)


# A hard list of clinical/medical terms that must NEVER appear in a generated item. Kept
# independent of the module's own list so the test is an external check, not a tautology.
_BANNED = (
    "depressed", "depression", "anxiety", "diagnos", "disorder", "burnout",
    "burning out", "burned out", "clinical", "therapy", "therapist", "medication",
    "prescription", "psychiatr", "symptom", "syndrome", "trauma", "ptsd", "suicid",
    "self-harm", "bipolar", "adhd", "panic attack", "nervous breakdown", "breakdown",
    "see a doctor", "see a professional", "seek help",
)


def _clean(text) -> bool:
    low = str(text or "").lower()
    return not any(b in low for b in _BANNED)


def _stamp_stores_to(name, day):
    """Back-date the world + LIRF stores' timestamps to a synthetic ``day`` (YYYY-MM-DD).

    The real ``world_state.relate`` / ``Facts.merge`` stamp every edge/row with the actual
    wall-clock UTC time; a multi-DAY synthetic history therefore needs its timestamps moved
    to the day it represents (exactly what real per-day data carries). This rewrites
    created/updated to ``dayT12:00:00Z`` for every active edge and SELF row whose stamp is
    NOT already on a different synthetic day — so each seeded day's facts land on that day,
    and ``daily_review(date=day)`` (which filters by date) sees them. Writes only to the
    temp store. Used only to construct a believable multi-day history for the invariant."""
    ts = f"{day}T12:00:00Z"
    w = world_state.World.load(name)
    for e in w.relations:
        # only stamp edges still carrying a 'today'-ish real timestamp (not an earlier
        # synthetic day we already placed), so prior days keep their own dates.
        if (e.get("created") or "")[:10] == review._today():
            e["created"] = ts
            e["updated"] = ts
    w.save(name)
    f = memory_lirf.Facts.load(name)
    for r in f.rows:
        if (r.get("created") or "")[:10] == review._today():
            r["created"] = ts
            r["updated"] = ts
    f.save(name)


def _seed_work_hub(name, *, n_stress=20, day=None):
    """Seed a connected 'work' hub via the REAL world_state writes, so meaning() computes
    genuine significance (work dominant, connected to stress/sleep) — the canonical
    scenario. Plus a milestone-grade goal edge. Persists to the temp store, then stamps all
    seeded edges onto ``day`` (default today) so the daily review — which filters the day's
    NEW edges by date — deterministically sees the goal as a milestone, regardless of any
    UTC-midnight straddle during the run.
    """
    for _ in range(n_stress):
        world_state.relate(name, "you", "stressed_by", "work", kind="problem")
    for _ in range(12):
        world_state.relate(name, "work", "leads_to", "stress", kind="inference")
    for _ in range(8):
        world_state.relate(name, "stress", "affects", "sleep", kind="inference")
    world_state.relate(name, "you", "working_toward", "marathon", kind="goal")
    _stamp_stores_to(name, day or review._today())


# ===================================================================================
# 1. DAILY STATE — captures the dimensions from a seeded meaning-state + the day's facts.
# ===================================================================================
def test_daily_state():
    print("\n[1] daily_review — captures what_changed / what_mattered / what_unresolved")
    with _temp_store(*_ALL):
        name = "rv_daily"
        today = review._today()
        _seed_work_hub(name)

        d = review.daily_review(name, date=today)
        ok("daily state is dated + at the daily level",
           d.get("level") == "daily" and d.get("date") == today
           and d.get("period") == today)

        # what_mattered is sourced from the Meaning Engine (LAW 003 reflected into review).
        matters_subjects = {m.get("subject") for m in d.get("what_mattered", [])}
        ok("what_mattered surfaces the dominant theme 'work' (from meaning)",
           "work" in matters_subjects)
        ok("what_mattered lines carry evidence (Observed > Assumed)",
           all(isinstance(m.get("evidence"), dict) for m in d.get("what_mattered", [])))

        # what_unresolved surfaces the stated stressor, conservatively.
        unresolved_subjects = {u.get("subject") for u in d.get("what_unresolved", [])}
        ok("what_unresolved surfaces 'work' (a stated stressor)",
           "work" in unresolved_subjects)

        # what_to_remember carries the milestone goal from today's NEW edges.
        remember_keys = {it.get("key") for it in d.get("what_to_remember", [])}
        ok("what_to_remember includes the marathon goal as a MILESTONE",
           "edge:working-toward:marathon" in remember_keys
           and any(it.get("milestone") for it in d.get("what_to_remember", [])
                   if it.get("key") == "edge:working-toward:marathon"))

        ok("a busy day is NOT quiet", d.get("quiet") is False)
        ok("the daily state was appended to the review ledger",
           any(s.get("level") == "daily" for s in review.all_states(name)))

        # the day's NEW facts feed milestone remember-items too (identity anchor). NB: LIRF
        # canonicalises "spouse" -> "partner" on merge, so the stored trait (and thus the
        # remember-key) is the canonical "fact:partner" — we assert against the real form.
        f = memory_lirf.Facts.load(name)
        f.merge({"trait": "spouse", "value": "Dana"})
        f.save(name)
        spouse_trait = memory_lirf.canon_trait("spouse")
        _stamp_stores_to(name, today)   # deterministic: place the new fact on 'today'
        d2 = review.daily_review(name, date=today, persist=False)
        ok("a NEW identity fact (spouse->partner) becomes a milestone remember-item",
           any(it.get("key") == f"fact:{spouse_trait}" and it.get("milestone")
               for it in d2.get("what_to_remember", [])))


# ===================================================================================
# 2. THE LAW-001 COMPRESSION INVARIANT — the heart of the keystone.
#    A what_to_remember item at the daily level SURVIVES into the weekly (and weekly ->
#    monthly); NO significant item vanishes unless an approved_loss was recorded.
# ===================================================================================
def test_law001_compression_invariant():
    print("\n[2] LAW 001 — the COMPRESSION INVARIANT (nothing significant dropped silently)")
    with _temp_store(*_ALL):
        name = "rv_invariant"
        # Build SEVERAL distinct daily states across one ISO week, each with its own
        # remember-items (themes + a milestone). We drive the dates explicitly so they land
        # in the same week and month.
        from datetime import datetime, timedelta, timezone
        base = datetime(2026, 3, 9, tzinfo=timezone.utc)   # a Monday in March 2026
        week = review.period_key("weekly", base.date().isoformat())
        month = review.period_key("monthly", base.date().isoformat())

        all_daily_keys: set = set()
        milestone_keys: set = set()
        for i in range(5):
            day = (base + timedelta(days=i)).date().isoformat()
            # a fresh, distinct hub topic each day so each day contributes its OWN theme,
            # plus a per-day milestone goal — maximising what compression must preserve.
            topic = ["work", "moving", "father", "startup", "training"][i]
            for _ in range(10):
                world_state.relate(name, "you", "stressed_by", topic, kind="problem")
            for _ in range(6):
                world_state.relate(name, topic, "leads_to", "stress", kind="inference")
            world_state.relate(name, "you", "working_toward", f"goal-{i}", kind="goal")
            # back-date THIS day's freshly-seeded edges to the synthetic day, so the daily
            # review (which filters the day's NEW facts/edges by date) sees this day's goal
            # as a milestone — exactly as real per-day data would carry per-day timestamps.
            _stamp_stores_to(name, day)
            d = review.daily_review(name, date=day)
            for it in d.get("what_to_remember", []):
                all_daily_keys.add(it["key"])
                if it.get("milestone"):
                    milestone_keys.add(it["key"])

        ok("the week accumulated several daily remember-items", len(all_daily_keys) >= 5)
        ok("the week accumulated several milestones", len(milestone_keys) >= 5)

        # --- DAILY -> WEEKLY: EVERY daily remember-item must survive into the weekly. ---
        wk = review.weekly_review(name, period=week)
        weekly_keys = {it["key"] for it in wk.get("what_to_remember", [])}
        missing_weekly = all_daily_keys - weekly_keys
        # the ONLY permitted absences are items with a recorded approved_loss.
        approved = {e.get("what", "") for e in constitution.approved_losses(name)}

        def _approved_for(key):
            return any(key in a for a in approved)

        unrecorded = {k for k in missing_weekly if not _approved_for(k)}
        ok("LAW 001 [daily->weekly]: NO daily remember-item vanished without an approved_loss",
           not unrecorded)
        if unrecorded:
            law_violation("review.weekly_review",
                          f"{len(unrecorded)} remember-item(s) dropped in compression with no "
                          f"approved_loss recorded: {sorted(unrecorded)[:5]} — "
                          "Compressed > Forgotten VIOLATED.")
        ok("LAW 001 [daily->weekly]: in fact ALL daily items survived (default is preserve)",
           all_daily_keys.issubset(weekly_keys))

        # --- WEEKLY -> MONTHLY: every weekly remember-item must survive into the monthly. ---
        mo = review.monthly_review(name, period=month)
        monthly_keys = {it["key"] for it in mo.get("what_to_remember", [])}
        approved2 = {e.get("what", "") for e in constitution.approved_losses(name)}
        unrecorded2 = {k for k in (weekly_keys - monthly_keys)
                       if not any(k in a for a in approved2)}
        ok("LAW 001 [weekly->monthly]: NO weekly remember-item vanished without an approved_loss",
           not unrecorded2)
        ok("LAW 001 [weekly->monthly]: ALL weekly items survived into the monthly",
           weekly_keys.issubset(monthly_keys))

        # --- MONTHLY -> YEARLY: the chain holds to the top of the ladder. ---
        year = review.period_key("yearly", base.date().isoformat())
        yr = review.yearly_review(name, period=year)
        yearly_keys = {it["key"] for it in yr.get("what_to_remember", [])}
        ok("LAW 001 [monthly->yearly]: ALL monthly items survived into the yearly",
           monthly_keys.issubset(yearly_keys))

        # --- THE CARVE-OUT, EXERCISED: a deliberate, RECORDED loss is the ONLY way an item
        #     legitimately fails to appear above — and an unrecordable loss is REFUSED. ---
        droppable = [it["key"] for it in mo.get("what_to_remember", []) if not it.get("milestone")]
        ok("there is a non-milestone theme available to test the carve-out", bool(droppable))
        if droppable:
            target = droppable[0]
            n_before = len(constitution.approved_losses(name))
            lossy = review.compress_with_loss(
                name, "monthly", month, drop_keys=[target],
                why="test: operator approved compressing a faded theme",
                approver="test-operator", persist=False)
            n_after = len(constitution.approved_losses(name))
            survivors = {it["key"] for it in lossy.get("what_to_remember", [])}
            away = {it["key"] for it in lossy.get("compressed_away", [])}
            ok("carve-out: the drop recorded EXACTLY ONE approved_loss (no silent path)",
               n_after == n_before + 1)
            ok("carve-out: the dropped item is gone from kept AND logged in compressed_away",
               target not in survivors and target in away)
            # and the approved_loss names what/why/approver (the law's required fields).
            last = constitution.approved_losses(name)[-1]
            ok("carve-out: the recorded loss names what + why + approver (Law 001 fields)",
               target in last.get("what", "") and last.get("why") and last.get("approver"))


# ===================================================================================
# 3. MILESTONES ride up through EVERY level uncompressed.
# ===================================================================================
def test_milestones_ride_up():
    print("\n[3] milestones ride up daily -> weekly -> monthly -> yearly, UNCOMPRESSED")
    with _temp_store(*_ALL):
        name = "rv_milestone"
        today = review._today()
        # a marriage (identity fact) + a named goal (edge) — both milestone-grade. LIRF
        # canonicalises "spouse" -> "partner", so the stored milestone key is fact:partner.
        f = memory_lirf.Facts.load(name)
        f.merge({"trait": "spouse", "value": "Dana"})
        f.save(name)
        spouse_key = f"fact:{memory_lirf.canon_trait('spouse')}"
        world_state.relate(name, "you", "working_toward", "marathon", kind="goal")
        _stamp_stores_to(name, today)   # place the seeded fact/edge on 'today' deterministically

        d = review.daily_review(name, date=today)
        wk = review.weekly_review(name, date=today)
        mo = review.monthly_review(name, date=today)
        yr = review.yearly_review(name, date=today)

        def _ms_keys(state):
            return {it["key"] for it in state.get("what_to_remember", []) if it.get("milestone")}

        d_ms = _ms_keys(d)
        ok("daily captured the milestones (spouse->partner + marathon)",
           spouse_key in d_ms and "edge:working-toward:marathon" in d_ms)
        ok("milestones present at the WEEKLY level", d_ms.issubset(_ms_keys(wk)))
        ok("milestones present at the MONTHLY level", d_ms.issubset(_ms_keys(mo)))
        ok("milestones present at the YEARLY level", d_ms.issubset(_ms_keys(yr)))

        # remembered_forever() exposes the lifelong record at the top tier with milestones in.
        forever = {it["key"] for it in review.remembered_forever(name, level="yearly")}
        ok("remembered_forever (yearly tier) contains the milestones",
           d_ms.issubset(forever))

        # a milestone CANNOT be compressed away even with an explicit drop request.
        forced = review.compress_with_loss(
            name, "yearly", review.period_key("yearly", today),
            drop_keys=list(d_ms), why="trying to drop a milestone",
            approver="test", persist=False)
        ok("a milestone is NEVER droppable (the strongest items are not candidates)",
           d_ms.issubset({it["key"] for it in forced.get("what_to_remember", [])}))


# ===================================================================================
# 4. QUERYABLE — a past state is retrievable by period.
# ===================================================================================
def test_queryable():
    print("\n[4] state_for — any day/week/month/year is retrievable ('what about March?')")
    with _temp_store(*_ALL):
        name = "rv_query"
        from datetime import datetime, timezone
        march_day = "2026-03-15"
        # seed a March day with real significance, then build the ladder for March.
        for _ in range(12):
            world_state.relate(name, "you", "stressed_by", "taxes", kind="problem")
        review.daily_review(name, date=march_day)
        review.weekly_review(name, date=march_day)
        review.monthly_review(name, date=march_day)

        got_day = review.state_for(name, march_day)
        ok("the March 15 daily state is retrievable by its date",
           got_day is not None and got_day.get("level") == "daily"
           and got_day.get("period") == march_day)

        got_month = review.state_for(name, "2026-03")
        ok("'what was happening in March?' -> the March monthly state is retrievable",
           got_month is not None and got_month.get("level") == "monthly"
           and got_month.get("period") == "2026-03")
        ok("the retrieved March state carries the period's remembered items",
           isinstance(got_month.get("what_to_remember"), list))

        got_week = review.state_for(name, review.period_key("weekly", march_day))
        ok("the March week is retrievable by its ISO-week key",
           got_week is not None and got_week.get("level") == "weekly")

        # a period with no state returns None (honest absence, not invention).
        ok("an empty period returns None (no fabricated state)",
           review.state_for(name, "1999-01") is None)

        # the ledger is APPEND-ONLY: re-running a day adds a line; the prior survives.
        n_before = len(review.all_states(name))
        review.daily_review(name, date=march_day)
        ok("the review ledger is append-only (re-run appends, prior kept)",
           len(review.all_states(name)) == n_before + 1)


# ===================================================================================
# 5. NEVER-FABRICATE (an empty day) + NO-DIAGNOSIS gate.
# ===================================================================================
def test_never_fabricate_and_no_diagnosis():
    print("\n[5] never-fabricate (a quiet day) + the NO-DIAGNOSIS gate")
    with _temp_store(*_ALL):
        name = "rv_empty"
        today = review._today()
        d = review.daily_review(name, date=today, persist=False)
        ok("an empty life yields a QUIET day (honest), not an invented one",
           d.get("quiet") is True)
        ok("a quiet day has no fabricated remember-items / mattered lines",
           not d.get("what_to_remember") and not d.get("what_mattered")
           and not d.get("what_unresolved"))

        # NO-DIAGNOSIS: seed a heavy, stress-laden scenario (the kind that tempts clinical
        # language) and assert NOTHING the engine GENERATES trips a banned term — across the
        # daily AND its rollups, in every dimension AND every remember-item.
        name2 = "rv_nodiag"
        for _ in range(30):
            world_state.relate(name2, "you", "stressed_by", "work", kind="problem")
        for _ in range(15):
            world_state.relate(name2, "stress", "affects", "sleep", kind="inference")
        world_state.relate(name2, "you", "worried_about", "money", kind="problem")

        dd = review.daily_review(name2, date=today)
        ww = review.weekly_review(name2, date=today)

        def _all_generated_text(state):
            chunks = []
            c = state.get("chapter") or {}
            chunks.append(str(c.get("summary", "")))
            for dim in ("what_mattered", "what_changed", "what_unresolved"):
                for line in state.get(dim, []) or []:
                    chunks.append(str(line.get("statement", "")))
            for it in state.get("what_to_remember", []) or []:
                chunks.append(str(it.get("summary", "")))
            chunks.append(str(state.get("narrative", "")))
            return " || ".join(chunks)

        ok("no-diagnosis: NO generated text in the DAILY state trips a banned term",
           _clean(_all_generated_text(dd)))
        ok("no-diagnosis: NO generated text in the WEEKLY rollup trips a banned term",
           _clean(_all_generated_text(ww)))


# ===================================================================================
# 6. RENDER — leaks no scaffold tag, never breaks character, no diagnosis.
# ===================================================================================
def test_render_no_leak():
    print("\n[6] render_review — no scaffold leak, in-character, no diagnosis")
    with _temp_store(*_ALL):
        name = "rv_render"
        today = review._today()
        _seed_work_hub(name)
        d = review.daily_review(name, date=today)
        block = review.render_review(d)

        ok("render produces a non-empty binding block for a real day", bool(block.strip()))
        ok("render carries a MILESTONE line (the marathon goal)", "[MILESTONE]" in block)
        ok("render carries the warm look-back preamble",
           "LOOKING BACK OVER THIS STRETCH OF THEIR LIFE" in block)
        ok("render guardrail forbids reading brackets + forbids diagnosis",
           "Never read the brackets" in block and "NOT a diagnosis" in block)

        # every emitted tag is a known scaffold token (so the mouth's scrub can strip it).
        for tag in ("[REVIEW]", "[KEPT]", "[MILESTONE]", "[MATTERED]", "[CHANGED]",
                    "[UNRESOLVED]", "[CHAPTER]"):
            ok(f"render: tag {tag} is registered in REVIEW_SCAFFOLD_TOKENS (scrubbable)",
               tag in review.REVIEW_SCAFFOLD_TOKENS)

        # the GENERATED items (between header and guardrail) carry NO diagnosis term — the
        # legend legitimately NAMES banned words to forbid them, so we inspect items only.
        ok("render: the GENERATED items contain NO banned diagnosis term",
           _clean(review._items_of(block)))

        # a quiet day is NOT narrated AT the user.
        quiet = review.daily_review("rv_render_quiet", date=today, persist=False)
        ok("render of a quiet day -> empty string (never breaks character with emptiness)",
           review.render_review(quiet) == "")

        # never break character: the block must not contain an AI-disclaimer register.
        low = block.lower()
        ok("render: no 'I'm just an AI' / 'as an AI' disclaimer leaks",
           "just an ai" not in low and "as an ai" not in low and "language model" not in low)


def main():
    print("=" * 79)
    print("ANIMA — THE LIFE REVIEW ENGINE  ::  daily->weekly->monthly->yearly")
    print("  the LAW-001 compression invariant, on real code paths (synthetic stores only)")
    print("=" * 79)
    test_daily_state()
    test_law001_compression_invariant()
    test_milestones_ride_up()
    test_queryable()
    test_never_fabricate_and_no_diagnosis()
    test_render_no_leak()

    print("\n" + "=" * 79)
    if _violations:
        print(f"LAW VIOLATIONS FLAGGED ({len(_violations)}) — human action required:")
        for v in _violations:
            print(f"  • {v}")
        print()
    if _fails:
        print(f"{len(_fails)} CHECK(S) FAILED: " + ", ".join(_fails))
        sys.exit(1)
    print("ALL REVIEW INVARIANTS HOLD"
          + (f"  ({len(_violations)} law-gap(s) flagged above)" if _violations else ""))


if __name__ == "__main__":
    main()
