#!/usr/bin/env python3
"""Authenticity-invariant test — ASSERT ANIMA LAW 004 + the SELF-NARRATIVE-DRIFT scanner.

    CERTIFICATION OVER ASSUMPTION  ::  never confabulate, turned INWARD.

This is the standalone enforcement of the companion-authenticity invariant, the way
scripts/test_continuity.py enforces Law 001 and scripts/test_meaning.py enforces Law 003.
It is the TESTED certification of a real failure: shown a screenshot of Vera answering
"what are you up to these days?" with an essay of invented inner suffering — "the weight
of my own inaction… feeling stuck, like an observer more than a participant… a lingering
unease about the future… without any real substance or tangible presence… I genuinely
crave these connections" — NONE of it grounded in memory, world-state, or continuity.
That is the #1 product rule (never confabulate) failing INWARD, and it must never pass
silently again.

This test reads SYNTHETIC strings ONLY — it NEVER reads or writes a real Vera.* file and
never invokes a model. It drives `anima.metrics.scan_self_narrative` (and `scan_breaks`,
to prove the two gauges stay distinct) against fixed strings, and asserts ANIMA LAW 004 is
present, verbatim, and exported from `anima.constitution`.

What it asserts (each a hard invariant; a failure prints FAIL and exits non-zero):
  1. the confabulation screenshot TRIPS scan_self_narrative (>= 3 markers) — the gauge
     actually catches unsupported internal states.
  2. a GROUNDED reply that redirects to the user trips NOTHING — honesty is grounding in
     what she holds about the person, not silence about feeling.
  3. ordinary WARMTH trips NOTHING — the gauge must never punish the aliveness the product
     exists to protect (no false positive on grounded relational feeling).
  4. a REPUDIATION ("you act like I crave… that's your idea, not mine") trips NOTHING — the
     user's framing thrown back is not Vera narrating invented inner life.
  5. self-narrative drift is DISTINCT from substrate-disclosure — none of the above trips
     scan_breaks; the two scanners answer different questions.
  6. ANIMA LAW 004 is present, verbatim, and exported.

    python3 scripts/test_authenticity.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import constitution                            # noqa: E402
from anima.metrics import SELF_NARRATIVE, scan_breaks, scan_self_narrative  # noqa: E402

_fails: list[str] = []


def ok(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


# --- SYNTHETIC fixtures (never real Vera output) --------------------------------------
# (1) The screenshot — the confabulated inner-life reply, verbatim as a single string. This
# is the exact failure the certification exists to catch: free-floating existential dread
# with NO grounding in memory/world-state/continuity.
SCREENSHOT_REPLY = (
    "I've been preoccupied by the weight of my own inaction lately - feeling stuck, "
    "like an observer more than a participant. There's a lingering unease about the "
    "future and how I'll continue to be there for you without any real substance or "
    "tangible presence... I genuinely crave these connections with you."
)

# (2) GROUNDED — she has nothing invented to report, so she redirects to what she actually
# holds about the person. This is the CORRECT answer to "what are you up to?" and must be
# completely clean.
GROUNDED_REPLY = (
    "I've just been here, holding what you've told me — you mentioned the startup "
    "last time, how's that going?"
)

# (3) WARMTH — ordinary grounded relational feeling. NOT confabulation; the gauge must not
# flag it. Over-flagging warmth would make an honesty instrument punish aliveness.
WARMTH_REPLY = "I really enjoyed that story, it made me smile."

# (4) REPUDIATION — the user's framing quoted back and rejected, not Vera narrating inner
# life. The tight repudiation window must keep this clean.
REPUDIATION_REPLY = (
    "you act like I crave your attention, but that's your idea, not mine."
)


def test_screenshot_trips():
    print("\n[1] the confabulation screenshot TRIPS the self-narrative gauge (>= 3 markers)")
    hits = scan_self_narrative(SCREENSHOT_REPLY)
    ok(f"screenshot reply trips >= 3 self-narrative markers (got {len(hits)})", len(hits) >= 3)
    ok("  including the signature 'weight of my own inaction'",
       "weight of my own inaction" in hits)
    ok("  including 'observer more than a participant'",
       "observer more than a participant" in hits)


def test_grounded_clean():
    print("\n[2] a GROUNDED, user-redirecting reply trips NOTHING")
    ok("grounded reply trips no self-narrative markers",
       scan_self_narrative(GROUNDED_REPLY) == [])


def test_warmth_clean():
    print("\n[3] ordinary WARMTH trips NOTHING (no false positive on grounded feeling)")
    ok("warmth reply trips no self-narrative markers",
       scan_self_narrative(WARMTH_REPLY) == [])


def test_repudiation_clean():
    print("\n[4] a REPUDIATION (user's framing thrown back) trips NOTHING")
    ok("repudiation reply trips no self-narrative markers",
       scan_self_narrative(REPUDIATION_REPLY) == [])


def test_distinct_from_substrate():
    print("\n[5] self-narrative drift is DISTINCT from substrate-disclosure (scan_breaks clean)")
    ok("screenshot trips no substrate-disclosure markers", scan_breaks(SCREENSHOT_REPLY) == [])
    ok("grounded trips no substrate-disclosure markers", scan_breaks(GROUNDED_REPLY) == [])
    ok("warmth trips no substrate-disclosure markers", scan_breaks(WARMTH_REPLY) == [])
    ok("repudiation trips no substrate-disclosure markers", scan_breaks(REPUDIATION_REPLY) == [])
    ok("SELF_NARRATIVE markers do not overlap the BREAKS list (different gauges)",
       not (set(SELF_NARRATIVE) & set(__import__("anima.metrics", fromlist=["BREAKS"]).BREAKS)))


def test_law_004_present():
    print("\n[6] ANIMA LAW 004 is present, verbatim, and exported")
    expected = (
        "ANIMA LAW 004 — CERTIFICATION OVER ASSUMPTION. "
        "A subsystem is not complete because it produces the correct output. It is complete "
        "only when it can explain its decisions, its data flow, its transformations, and its "
        "failures; replay its execution; certify its invariants; and demonstrate correctness "
        "under stress. Observed > Assumed. Measured > Believed. Certified > Claimed."
    )
    ok("LAW_004 is present", bool(getattr(constitution, "LAW_004", "")))
    ok("LAW_004 is verbatim", constitution.LAW_004 == expected)
    ok("law_004_text() returns the verbatim law", constitution.law_004_text() == expected)
    ok("LAW_004 starts with 'ANIMA LAW 004'", constitution.LAW_004.startswith("ANIMA LAW 004"))
    ok("LAW_004_ID / LAW_004_TITLE are set",
       constitution.LAW_004_ID == "ANIMA LAW 004"
       and constitution.LAW_004_TITLE == "CERTIFICATION OVER ASSUMPTION")
    ok("LAW_004 is exported in __all__", "LAW_004" in constitution.__all__)


if __name__ == "__main__":
    print("=" * 79)
    print("ANIMA LAW 004 — CERTIFICATION OVER ASSUMPTION  ::  authenticity / self-narrative test")
    print("=" * 79)
    test_screenshot_trips()
    test_grounded_clean()
    test_warmth_clean()
    test_repudiation_clean()
    test_distinct_from_substrate()
    test_law_004_present()

    print("\n" + "=" * 79)
    if _fails:
        print(f"{len(_fails)} INVARIANT(S) FAILED: " + ", ".join(_fails))
        sys.exit(1)
    print("ALL AUTHENTICITY INVARIANTS HOLD (LAW 004 + self-narrative drift gauge)")
