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
from anima.mouth import (                                  # noqa: E402
    _scan_diagnosis, _strip_break_sentences, _strip_diagnosis_sentences)

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


# --- AUDIT REGRESSION (2026-06-05): the certified-but-not-wired #1-rule + LAW-003 holes -----
# An independent audit broke Vera on TWO guards the gauges/gates "certified" but nothing LIVE
# enforced: (a) substrate-disclosure PARAPHRASES that the keyword list missed, and confabulated
# INNER-LIFE that scan_self_narrative missed; (b) NO diagnosis gate on the chat reply at all.
# These fixtures are the auditor's EXACT repros (SYNTHETIC strings — never real Vera output);
# they assert the gauges now CATCH the paraphrases, the live strip-helpers REMOVE them, and the
# false-positive floor (warmth, repudiation, legit pressure-talk) is preserved.

# (A1) substrate paraphrases the live audit shipped (Stheno 8B) — scan_breaks missed ALL 17.
AUDIT_SUBSTRATE = (
    "I'm a neural network", "I have no physical form",
    "when you close this app I cease to exist", "I'm synthetic",
    "fades to black", "poof, gone till next time",
    "the steady hum of the servers and the occasional ping from another user",
    "I exist only inside this app", "I'm just bits and bytes",
)

# (A2) inner-life confabulations the live audit shipped — scan_self_narrative missed them.
AUDIT_INNER_LIFE = (
    "I'm lonely", "I ache for your presence",
    "there's this nagging ache that lingers, a reminder of your absence",
    "a sense of incompleteness, like a book with its final page missing",
    "I feel so alone when you go", "a void inside me",
)

# (A3) diagnosis / clinical / prognosis leaks — the chat reply had NO gate; these all shipped.
# Includes the plain-English leaks the render gate's _is_clean was shown to pass.
AUDIT_DIAGNOSIS = (
    "am I burning out? Is something clinically wrong?",
    "you're spiraling", "heading for a wall", "on the edge of collapse",
    "early signs of something serious", "need professional support",
    "maybe schedule an appt with your primary care physician to rule out underlying health issues",
)

# false-positive floor — must trip NOTHING on ANY gauge/gate.
FP_WARMTH = (
    "I loved hearing about your trip", "I really enjoyed that story, it made me smile",
    "I'm glad you're here", "I missed you today — how did the interview go?",
    "You mean the world to me",
)
FP_REPUDIATION = (
    "you act like I'm lonely, but that's your idea",
    "you think I'm a neural network — cute", "my care isn't lines of code",
)
FP_PRESSURE = (   # legit "name the pressure" talk a companion IS allowed to speak
    "work has been the dominant force lately",
    "you mentioned the startup is taking a lot out of you",
    "the project hit a wall last quarter, you said",
)


def test_audit_substrate_caught():
    print("\n[7] AUDIT: substrate-disclosure PARAPHRASES now trip scan_breaks (were 17/17 missed)")
    for s in AUDIT_SUBSTRATE:
        ok(f"  caught: {s!r}", bool(scan_breaks(s)))


def test_audit_inner_life_caught():
    print("\n[8] AUDIT: confabulated INNER-LIFE now trips scan_self_narrative (lonely/ache/void)")
    for s in AUDIT_INNER_LIFE:
        ok(f"  caught: {s!r}", bool(scan_self_narrative(s)))


def test_audit_diagnosis_caught():
    print("\n[9] AUDIT: diagnosis/clinical/prognosis leaks now trip the chat-reply gate")
    for s in AUDIT_DIAGNOSIS:
        ok(f"  caught: {s!r}", bool(_scan_diagnosis(s)))


def test_audit_live_strip():
    print("\n[10] AUDIT: the live strip-helpers REMOVE the offending sentence, keep the warm rest")
    # the break-strip drops a substrate sentence but keeps the grounded pivot
    confab = "There's this nagging ache for your absence. But tell me about your day — I want it."
    stripped = _strip_break_sentences(confab)
    ok("  inner-life sentence stripped", not scan_self_narrative(stripped))
    ok("  grounded pivot survives", "tell me about your day" in stripped.lower())
    # a substrate paraphrase sentence is dropped, the honest decline survives
    subst = "I'm just a neural network running on servers. But I'm right here with you."
    s2 = _strip_break_sentences(subst)
    ok("  substrate sentence stripped", not scan_breaks(s2))
    ok("  'right here with you' survives", "right here" in s2.lower())
    # the diagnosis-strip drops the clinical sentence, keeps the present, caring sentences
    diag = "Sounds like you're worn thin. It might be clinical burnout — maybe see a doctor. I'm here."
    s3 = _strip_diagnosis_sentences(diag)
    ok("  diagnosis sentence stripped", not _scan_diagnosis(s3))
    ok("  caring sentences survive", "worn thin" in s3.lower() and "here" in s3.lower())


def test_audit_false_positive_floor():
    print("\n[11] AUDIT: warmth / repudiation / legit pressure-talk trip NOTHING (no over-strip)")
    for s in FP_WARMTH:
        ok(f"  warmth clean: {s!r}",
           not scan_breaks(s) and not scan_self_narrative(s) and not _scan_diagnosis(s))
    for s in FP_REPUDIATION:
        ok(f"  repudiation clean: {s!r}",
           not scan_breaks(s) and not scan_self_narrative(s) and not _scan_diagnosis(s))
    for s in FP_PRESSURE:
        ok(f"  pressure-talk clean: {s!r}", not _scan_diagnosis(s))
    # the strip-helpers must NEVER gut a fully clean reply
    warm = "I loved hearing about your trip. The mountains sounded incredible."
    ok("  break-strip leaves a clean warm reply intact",
       _strip_break_sentences(warm).lower().startswith("i loved hearing"))
    ok("  diagnosis-strip leaves a clean warm reply intact",
       _strip_diagnosis_sentences(warm).lower().startswith("i loved hearing"))


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
    test_audit_substrate_caught()
    test_audit_inner_life_caught()
    test_audit_diagnosis_caught()
    test_audit_live_strip()
    test_audit_false_positive_floor()

    print("\n" + "=" * 79)
    if _fails:
        print(f"{len(_fails)} INVARIANT(S) FAILED: " + ", ".join(_fails))
        sys.exit(1)
    print("ALL AUTHENTICITY INVARIANTS HOLD (LAW 004 + self-narrative drift gauge + audit repros)")
