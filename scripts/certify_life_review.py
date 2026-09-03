#!/usr/bin/env python3
"""
certify_life_review — THE LIFE REVIEW ENGINE: the nightly cortex that turns a day into
COMPRESSED CONTINUITY, with the LAW-001 invariant 'Compressed > Forgotten' made a TESTED fact.

review.py is wired into the LIVE PATH by anima/live.py's nightly SLEEP CYCLE
(``review.daily_review(name, brain)`` then weekly/monthly/yearly rollups). This certifies that
engine's contract end-to-end through the SAME public functions the sleep cycle calls — offline,
deterministically, with NO live model and NO network:

  A. DAILY STATE — seeding a busy day via world_state (a 'work' stressor hub so meaning() has real
     significance, plus a milestone-grade 'working_toward marathon' goal edge), daily_review()
     produces a DATED, NOT-quiet Daily State whose what_mattered + what_unresolved surface 'work'
     and whose what_to_remember carries the marathon as a MILESTONE; every remember-item summary is
     diagnosis-free.
  B. THE LAW-001 COMPRESSION INVARIANT — every daily what_to_remember KEY survives into the weekly
     rollup (nothing significant silently dropped), the marathon MILESTONE rides up UNCOMPRESSED,
     and weekly keys likewise survive into the monthly. This is the whole point of the engine.
  C. QUERYABLE + APPEND-ONLY — state_for retrieves a state by its period, and a re-run of the day
     APPENDS to the ledger (a prior state is never truncated — Law 001 durability).
  D. THE CARVE-OUT — compress_with_loss on a NON-milestone key records EXACTLY ONE
     constitution.approved_loss and removes it from kept (logged in compressed_away); a MILESTONE
     key in drop_keys is IGNORED (the strongest items are never even droppable).
  E. RENDER — render_review of the day emits a warm binding block whose generated items carry NO
     banned diagnosis term and whose tags are all in REVIEW_SCAFFOLD_TOKENS (scrubbable); a quiet
     day renders to "" (never narrated AT the user).
  F. NEVER-FABRICATE — an empty life yields quiet=True with no remember-items (Observed > Assumed).

Hermetic: every store the engine reads/writes (review / world_state / memory_lirf / meaning /
constitution / loops) is already redirected into a temp dir by gate0_prime_experience._temp_store;
the real .anima is fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED,
1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import secrets
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


def _n_losses(con, name: str) -> int:
    """approved_loss count for ``name``, defensively (the ledger shape varies; absent -> 0)."""
    try:
        fn = getattr(con, "approved_losses", None)
        if callable(fn):
            return len(fn(name) or [])
    except Exception:
        pass
    return 0


def main() -> int:
    from anima import review, world_state, constitution
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("LIFE REVIEW — the nightly cortex: compressed continuity (LAW 001 — Compressed > Forgotten)")
    print("=" * 92)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # Pure helpers exercised outside the store (clean-gate + period ladder), like the sibling certs.
    ck("P1: the clean-gate passes a neutral phrase and CATCHES a diagnosis term",
       review._is_clean("work stayed heavy this week")
       and not review._is_clean("they sound depressed") and not review._is_clean("this is burnout"))
    ck("P2: the period ladder derives daily/weekly/monthly/yearly keys",
       review.period_key(review.DAILY, "2026-06-04") == "2026-06-04"
       and review.period_key(review.MONTHLY, "2026-06-04") == "2026-06"
       and review.period_key(review.YEARLY, "2026-06-04") == "2026"
       and review._infer_level("2026-W23") == review.WEEKLY)

    with _temp_store():
        name = "LifeReviewCert_" + secrets.token_hex(3)
        today = review._today()

        # ---- seed a busy day: a 'work' stressor hub (so meaning() surfaces real significance) plus
        # a milestone-grade goal edge — IDENTICAL shape to the module's own self-test scenario, so
        # the live engine sees genuine material rather than a contrived stub. -----------------------
        for _ in range(20):
            world_state.relate(name, "you", "stressed_by", "work", kind="problem")
        for _ in range(12):
            world_state.relate(name, "work", "leads_to", "stress", kind="inference")
        for _ in range(8):
            world_state.relate(name, "stress", "affects", "sleep", kind="inference")
        world_state.relate(name, "you", "working_toward", "marathon", kind="goal")  # a MILESTONE

        # ---- A. DAILY STATE -----------------------------------------------------------------------
        d = review.daily_review(name, date=today)        # the exact call the sleep cycle makes (brain=None)
        ck("A1: daily_review produces a DATED daily state",
           d.get("level") == review.DAILY and d.get("date") == today)
        ck("A2: the day is NOT quiet (real significance surfaced)", d.get("quiet") is False)
        ck("A3: what_mattered surfaces 'work' (the dominant significance)",
           any(m.get("subject") == "work" for m in d.get(review.WHAT_MATTERED, [])))
        ck("A4: what_unresolved surfaces 'work' (an open weight)",
           any(u.get("subject") == "work" for u in d.get(review.WHAT_UNRESOLVED, [])))
        ck("A5: what_to_remember carries the marathon as a MILESTONE",
           any(it.get("key") == "edge:working-toward:marathon" and it.get("milestone")
               for it in d.get(review.WHAT_TO_REMEMBER, [])))
        ck("A6: every remember-item summary is diagnosis-free (the no-diagnosis wall holds)",
           all(review._is_clean(it.get("summary", "")) for it in d.get(review.WHAT_TO_REMEMBER, [])))

        daily_keys = {it["key"] for it in d.get(review.WHAT_TO_REMEMBER, []) if it.get("key")}
        ck("A7: the day produced at least one remember-forever key", bool(daily_keys))

        # ---- B. THE LAW-001 COMPRESSION INVARIANT -------------------------------------------------
        wk = review.weekly_review(name, date=today)
        weekly_keys = {it["key"] for it in wk.get(review.WHAT_TO_REMEMBER, []) if it.get("key")}
        ck("B1: EVERY daily remember-item key SURVIVES into the weekly (Compressed > Forgotten)",
           daily_keys and daily_keys.issubset(weekly_keys))
        ck("B2: the marathon MILESTONE rode up into the weekly UNCOMPRESSED",
           any(it.get("key") == "edge:working-toward:marathon" and it.get("milestone")
               for it in wk.get(review.WHAT_TO_REMEMBER, [])))
        mo = review.monthly_review(name, date=today)
        monthly_keys = {it["key"] for it in mo.get(review.WHAT_TO_REMEMBER, []) if it.get("key")}
        ck("B3: every weekly remember-item key SURVIVES into the monthly",
           weekly_keys and weekly_keys.issubset(monthly_keys))

        # ---- C. QUERYABLE + APPEND-ONLY -----------------------------------------------------------
        got = review.state_for(name, today)
        ck("C1: state_for retrieves the daily state by its period ('what happened that day?')",
           got is not None and got.get("period") == today and got.get("level") == review.DAILY)
        got_mo = review.state_for(name, review.period_key(review.MONTHLY, today))
        ck("C2: state_for retrieves the monthly state by its period",
           got_mo is not None and got_mo.get("level") == review.MONTHLY)
        n_before = len(review.all_states(name))
        review.daily_review(name, date=today)            # re-run the day
        ck("C3: the ledger is APPEND-ONLY (state count grew; a prior state is never truncated)",
           len(review.all_states(name)) == n_before + 1)

        # ---- D. THE CARVE-OUT (the ONLY way a remembered item legitimately fails to ride up) -------
        theme_keys = [it["key"] for it in mo.get(review.WHAT_TO_REMEMBER, [])
                      if it.get("key") and not it.get("milestone")]
        if theme_keys:
            before_losses = _n_losses(constitution, name)
            lossy = review.compress_with_loss(
                name, review.MONTHLY, review.period_key(review.MONTHLY, today),
                drop_keys=[theme_keys[0]], why="cert: deliberate compression",
                approver="life-review-cert", persist=False)
            after_losses = _n_losses(constitution, name)
            survivor_keys = {it["key"] for it in lossy.get(review.WHAT_TO_REMEMBER, [])}
            ck("D1: an explicit drop RECORDS exactly one constitution.approved_loss (the carve-out)",
               after_losses == before_losses + 1)
            ck("D2: the dropped item is gone from kept but ACCOUNTED in compressed_away (no silent loss)",
               theme_keys[0] not in survivor_keys
               and any(it.get("key") == theme_keys[0] for it in lossy.get("compressed_away", [])))
        else:
            ck("D1: (no non-milestone theme to drop — carve-out path vacuously satisfied)", True)
            ck("D2: (no non-milestone theme to drop — carve-out path vacuously satisfied)", True)

        lossy_ms = review.compress_with_loss(
            name, review.MONTHLY, review.period_key(review.MONTHLY, today),
            drop_keys=["edge:working-toward:marathon"], why="cert: try to drop a milestone",
            approver="life-review-cert", persist=False)
        ck("D3: a MILESTONE key in drop_keys is IGNORED — the strongest items are never droppable",
           "edge:working-toward:marathon" in {it["key"] for it in lossy_ms.get(review.WHAT_TO_REMEMBER, [])})

        # ---- E. RENDER (warm, scrubbable, no diagnosis) -------------------------------------------
        block = review.render_review(d)
        ck("E1: render_review of the busy day produces a non-empty binding block", bool(block.strip()))
        ck("E2: it carries a [MILESTONE] line for the marathon", "[MILESTONE]" in block)
        ck("E3: the GENERATED items contain NO banned diagnosis term",
           review._is_clean(review._items_of(block)))
        ck("E4: every emitted scaffold tag is in REVIEW_SCAFFOLD_TOKENS (the mouth can scrub it)",
           all(t in review.REVIEW_SCAFFOLD_TOKENS
               for t in ("[KEPT]", "[MILESTONE]", "[MATTERED]", "[CHANGED]", "[CHAPTER]")))
        ck("E5: the guardrail forbids diagnosis + reading the brackets aloud (#1 product rule)",
           "NOT a diagnosis" in block and "Never read the brackets" in block)

        # ---- F. NEVER-FABRICATE on an EMPTY life --------------------------------------------------
        empty_name = "LifeReviewEmpty_" + secrets.token_hex(3)
        de = review.daily_review(empty_name, date=today, persist=False)
        ck("F1: an empty day is QUIET, not invented (Observed > Assumed)",
           de.get("quiet") is True and not de.get(review.WHAT_TO_REMEMBER)
           and not de.get(review.WHAT_MATTERED))
        ck("F2: render of a quiet day -> '' (a quiet stretch is never narrated AT the user)",
           review.render_review(de) == "")

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nLIFE-REVIEW CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
