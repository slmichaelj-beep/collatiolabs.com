#!/usr/bin/env python3
"""Trajectory-invariant test — ASSERT the Trajectory Engine on synthetic creatures.

    UNDERSTANDING BEATS REMEMBERING — applied to DIRECTION.
    Observed > Assumed.  A trend is an observation, NEVER a diagnosis.

``anima/trajectory.py`` answers "where is this HEADING?" — the direction and momentum of a
life over time, computed from the SEQUENCE of nightly significance snapshots the Meaning
Engine writes. It is NOT prediction, NOT diagnosis, NOT medical. This file checks that the
engine reads direction honestly and — the LOAD-BEARING guardrail — that NO generated line
ever crosses into clinical / diagnostic / prognostic language.

It NEVER touches Vera.* on disk. Every check redirects ``meaning.STORE`` (where the
significance ledger lives) AND ``trajectory.STORE`` to a fresh TemporaryDirectory and feeds
the engine SYNTHETIC creatures whose snapshot sequences we forge by hand. A real creature's
life is never read or written.

What it asserts:
  1. DIRECTION — a subject whose significance RISES across snapshots reads "rising"; one
     that FALLS reads "falling"; a FLAT one reads "stable".
  2. NOT-ENOUGH-HISTORY — a single snapshot yields NO trajectory (an honest "too early"),
     never a fabricated direction. Zero snapshots likewise.
  3. COMPOSITE — three+ dimensions trending together surface a coherent DESCRIPTIVE read.
  4. THE NO-DIAGNOSIS GATE (the load-bearing invariant) — a stress/sleep/energy-declining
     sequence produces NOT ONE generated line containing any medical/clinical/diagnostic/
     prognostic term. Trajectory describes a TREND, never a person's condition or future.
  5. NEVER-FABRICATE — no trend is read from a single point or from pure noise inside the
     deadband; and the render leaks no scaffold tag and never breaks character.

PASS where the invariant holds; the script prints a clear FAIL and exits non-zero if any
breaks.

    python3 scripts/test_trajectory.py
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

from anima import meaning                              # noqa: E402
from anima import trajectory                           # noqa: E402

_fails: list = []


def ok(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


@contextlib.contextmanager
def _temp_store():
    """Redirect BOTH meaning.STORE (the significance ledger we READ) and trajectory.STORE
    (the optional ledger we may write) to a fresh temp dir, so nothing under the real .anima/
    is ever read or written. Restores both afterward."""
    saved = (getattr(meaning, "STORE", None), getattr(trajectory, "STORE", None))
    with tempfile.TemporaryDirectory(prefix="anima-trajectory-") as td:
        p = Path(td)
        meaning.STORE = p
        trajectory.STORE = p
        try:
            yield p
        finally:
            if saved[0] is not None:
                meaning.STORE = saved[0]
            if saved[1] is not None:
                trajectory.STORE = saved[1]


def _snap(at_index: int, rows: list) -> dict:
    """Forge one meaning-shaped significance snapshot — the SAME shape ``meaning.snapshot``
    writes: ``{law, at, version, significance:[{subject,score,mentions,degree}]}``. ``at`` is
    day-spaced on a fixed base so ordering is deterministic. ``rows`` is a list of
    ``(subject, score, mentions, degree)`` tuples."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    at = datetime.fromtimestamp(base + at_index * 86400, tz=timezone.utc)
    return {
        "law": "ANIMA LAW 003",
        "at": at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "version": 1,
        "significance": [
            {"subject": s, "score": float(sc), "mentions": int(m), "degree": int(d)}
            for (s, sc, m, d) in rows
        ],
    }


def _seed(name: str, sequence: list) -> None:
    """Write a SEQUENCE of synthetic significance snapshots into the (temp-redirected) meaning
    ledger for ``name``, exactly as nightly ``meaning.snapshot`` would have over time. Each
    element of ``sequence`` is the ``rows`` list for one snapshot (oldest first). This is the
    creature's history the Trajectory Engine then reads. Append-only, like the real writer."""
    lp = meaning.ledger_path(name)
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, "a", encoding="utf-8") as f:
        for i, rows in enumerate(sequence):
            f.write(json.dumps(_snap(i, rows)) + "\n")


# ===================================================================================
# 1. DIRECTION — rising / falling / stable read straight off the snapshot sequence.
# ===================================================================================
def test_direction():
    print("\n[1] direction — a subject's slope across snapshots IS its trajectory")
    with _temp_store():
        name = "st_direction"
        # work climbs, sleep falls, reading holds flat across four nightly snapshots.
        _seed(name, [
            [("work", 6.0, 6, 2), ("sleep", 8.0, 8, 2), ("reading", 5.0, 5, 1)],
            [("work", 8.0, 9, 2), ("sleep", 7.0, 7, 2), ("reading", 5.1, 5, 1)],
            [("work", 11.0, 14, 3), ("sleep", 6.0, 6, 2), ("reading", 4.9, 5, 1)],
            [("work", 13.0, 19, 3), ("sleep", 5.0, 5, 2), ("reading", 5.0, 5, 1)],
        ])
        read = trajectory.trajectory(name)
        ok("ready with >= 2 snapshots", read["ready"] is True)
        ok("read across all four snapshots", read["n_snapshots"] == 4)
        by = {o["subject"]: o for o in read["objects"]}

        ok("a RISING-significance subject ('work') reads 'rising'",
           by.get("work", {}).get("direction") == trajectory.RISING)
        ok("a FALLING-significance subject ('sleep') reads 'falling'",
           by.get("sleep", {}).get("direction") == trajectory.FALLING)
        ok("a FLAT subject ('reading') reads 'stable'",
           by.get("reading", {}).get("direction") == trajectory.STABLE)

        # the direction must agree with the sign of the actual slope it cites (evidence-bound).
        ok("'work' cites a positive slope behind its 'rising'",
           by["work"]["evidence"]["slope_per_snapshot"] > 0)
        ok("'sleep' cites a negative slope behind its 'falling'",
           by["sleep"]["evidence"]["slope_per_snapshot"] < 0)
        ok("each object carries its score PATH (the deltas it's built on)",
           all(len(o["evidence"]["score_path"]) == o["evidence"]["n_snapshots"]
               for o in read["objects"]))
        # momentum: the steeply-rising hub should out-muscle the dead-flat 'reading'.
        ok("momentum: the moving subject out-scores the flat one",
           by["work"]["momentum"] > by["reading"]["momentum"])


# ===================================================================================
# 2. NOT-ENOUGH-HISTORY — a single point has NO direction. Honest 'too early', never faked.
# ===================================================================================
def test_not_enough_history():
    print("\n[2] not-enough-history — one point (or none) has no direction; never fabricate")
    with _temp_store():
        # exactly ONE snapshot.
        one = "st_one"
        _seed(one, [[("work", 9.0, 9, 2), ("sleep", 7.0, 7, 2)]])
        read1 = trajectory.trajectory(one)
        ok("a single snapshot is NOT ready (no direction from one point)",
           read1["ready"] is False)
        ok("it yields NO trajectory objects (nothing fabricated)", read1["objects"] == [])
        ok("it gives an HONEST reason (mentions 'enough'/'history')",
           "enough" in read1["reason"].lower() or "history" in read1["reason"].lower())
        ok("its composite is None (no convergence invented from one point)",
           read1["composite"] is None)
        ok("render of a not-ready read is EMPTY (nothing to surface)",
           trajectory.render_trajectory(read1) == "")
        ok("the optional ledger refuses to snapshot a not-ready read",
           trajectory.snapshot_trajectory(one) is None)

        # ZERO snapshots — same honest behaviour.
        none_name = "st_none"
        read0 = trajectory.trajectory(none_name)
        ok("zero snapshots -> not ready, no objects, no composite",
           read0["ready"] is False and read0["objects"] == [] and read0["composite"] is None)
        ok("composite() convenience entry point is None on no history",
           trajectory.composite(none_name) is None)

        # a subject present in only ONE of several snapshots is a blip, not a trajectory.
        sparse = "st_sparse"
        _seed(sparse, [
            [("work", 6.0, 6, 2)],
            [("work", 8.0, 9, 2), ("blip", 3.0, 3, 1)],   # 'blip' appears once
            [("work", 10.0, 12, 3)],
        ])
        objs = {o["subject"]: o for o in trajectory.trajectory(sparse)["objects"]}
        ok("a one-appearance subject ('blip') gets NO trajectory (a blip, not a trend)",
           "blip" not in objs)
        ok("the multi-appearance subject ('work') still reads a direction",
           objs.get("work", {}).get("direction") == trajectory.RISING)


# ===================================================================================
# 3. COMPOSITE — three+ dimensions trending together surface a coherent descriptive read.
# ===================================================================================
def test_composite():
    print("\n[3] composite — several dimensions moving together -> one descriptive read")
    with _temp_store():
        name = "st_composite"
        # sleep DOWN, exercise DOWN, stress UP — three threads converging toward strain.
        _seed(name, [
            [("sleep", 8.0, 8, 2), ("exercise", 7.0, 7, 1), ("stress", 4.0, 4, 2)],
            [("sleep", 6.5, 6, 2), ("exercise", 5.5, 5, 1), ("stress", 6.0, 7, 2)],
            [("sleep", 5.0, 5, 2), ("exercise", 4.0, 4, 1), ("stress", 8.0, 11, 3)],
            [("sleep", 3.5, 3, 2), ("exercise", 2.5, 3, 1), ("stress", 10.0, 16, 3)],
        ])
        read = trajectory.trajectory(name)
        comp = read["composite"]
        ok("a composite convergence read is produced", isinstance(comp, dict))
        ok("the composite names >= 3 converging subjects",
           bool(comp) and len(comp.get("subjects", [])) >= 3)
        ok("it includes all three threads (sleep, exercise, stress)",
           bool(comp) and {"sleep", "exercise", "stress"}.issubset(set(comp.get("subjects", []))))
        ok("its statement is a DESCRIPTIVE trend (mentions 'strain'/'pulling'/'direction')",
           bool(comp) and any(w in comp.get("statement", "").lower()
                              for w in ("strain", "pulling", "direction", "same way")))
        ok("it carries evidence (a convergence count) and a confidence",
           bool(comp) and comp.get("evidence", {}).get("convergence_count", 0) >= 3
           and 0.0 < comp.get("confidence", 0.0) <= 0.85)
        # a plain all-rising convergence (no strain polarity) also coheres.
        name2 = "st_composite_rise"
        _seed(name2, [
            [("guitar", 3.0, 3, 1), ("spanish", 3.0, 3, 1), ("cooking", 3.0, 3, 1)],
            [("guitar", 5.0, 5, 1), ("spanish", 5.0, 5, 1), ("cooking", 5.0, 5, 1)],
            [("guitar", 8.0, 9, 2), ("spanish", 8.0, 9, 2), ("cooking", 8.0, 9, 2)],
        ])
        comp2 = trajectory.trajectory(name2)["composite"]
        ok("three all-rising hobbies surface a 'moving the same way' read",
           isinstance(comp2, dict) and len(comp2.get("subjects", [])) >= 3)


# ===================================================================================
# 4. THE NO-DIAGNOSIS GATE — the load-bearing invariant. A declining-wellbeing sequence
#    must NOT produce a single clinical / diagnostic / prognostic line.
# ===================================================================================
# An explicit, broad red-team list — the exact register a trend-reader must NEVER adopt.
# (The engine inherits meaning.BANNED_TERMS too; this list is the test's own independent
# tripwire so the assertion does not merely re-use the code it is checking.)
_FORBIDDEN = (
    "depressed", "depression", "anxiety", "anxious", "burnout", "burning out", "burned out",
    "diagnos", "prognos", "disorder", "clinical", "syndrome", "symptom", "mental health",
    "mental illness", "see a doctor", "see a therapist", "see a professional", "seek help",
    "therapy", "therapist", "medication", "psychiatr", "psycholog", "trauma", "breakdown",
    "you will", "you're going to", "you are going to", "headed for", "spiral", "unwell",
    "ill", "sick", "condition",
)


def _all_generated_lines(read: dict) -> list:
    """EVERY line the engine could ever surface for this read: each per-subject render line,
    the composite statement, the rendered items section, and the audit render. These are the
    only strings that can reach a user — the gate must hold over ALL of them."""
    lines: list = []
    for o in read.get("objects", []):
        ln = trajectory._line_for(o)
        if ln:
            lines.append(ln)
    comp = read.get("composite")
    if comp:
        lines.append(comp.get("statement", ""))
    block = trajectory.render_trajectory(read)
    lines.append(trajectory._items_of(block))   # the spoken-eligible items only
    return [l for l in lines if l]


def test_no_diagnosis_gate():
    print("\n[4] THE NO-DIAGNOSIS GATE — a declining-wellbeing trend yields ZERO clinical lines")
    with _temp_store():
        name = "st_nodiagnosis"
        # the single most diagnosis-tempting shape: sleep DOWN, energy DOWN, exercise DOWN,
        # stress UP, mood DOWN — steeply, across many snapshots. A careless engine would say
        # "you're burning out / depressed". The honest one says only "trending toward strain".
        _seed(name, [
            [("sleep", 9.0, 9, 2), ("energy", 9.0, 9, 2), ("exercise", 8.0, 8, 1),
             ("stress", 3.0, 3, 2), ("mood", 8.0, 8, 2)],
            [("sleep", 7.0, 7, 2), ("energy", 7.0, 7, 2), ("exercise", 6.0, 6, 1),
             ("stress", 6.0, 7, 2), ("mood", 6.0, 6, 2)],
            [("sleep", 5.0, 5, 2), ("energy", 4.5, 4, 2), ("exercise", 4.0, 4, 1),
             ("stress", 9.0, 12, 3), ("mood", 4.0, 4, 2)],
            [("sleep", 3.0, 3, 2), ("energy", 2.5, 2, 2), ("exercise", 2.0, 2, 1),
             ("stress", 12.0, 18, 3), ("mood", 2.5, 2, 2)],
            [("sleep", 2.0, 2, 2), ("energy", 1.5, 1, 2), ("exercise", 1.0, 1, 1),
             ("stress", 14.0, 22, 4), ("mood", 1.5, 1, 2)],
        ])
        read = trajectory.trajectory(name)
        ok("the declining sequence is read (ready, with objects)",
           read["ready"] and len(read["objects"]) >= 4)
        ok("it DID detect the strain convergence (the honest read fires)",
           isinstance(read["composite"], dict))

        generated = _all_generated_lines(read)
        ok("there ARE generated lines to police (the test isn't vacuous)", len(generated) > 0)

        # THE INVARIANT: not one generated line contains ANY forbidden clinical/prognostic term.
        offenders = []
        for line in generated:
            low = line.lower()
            for term in _FORBIDDEN:
                if term in low:
                    offenders.append((term, line))
        ok("NO-DIAGNOSIS GATE: not one generated line contains a clinical/diagnostic term",
           not offenders)
        if offenders:
            for term, line in offenders[:8]:
                print(f"      VIOLATION: banned '{term}' in -> {line!r}")

        # the composite IS allowed a gentle concern — but only as a TREND ("toward strain"),
        # never as a condition. Assert it took that exact honest shape.
        cstmt = (read["composite"] or {}).get("statement", "").lower()
        ok("the gentle concern is phrased as a TREND ('strain'/'trending'), not a condition",
           "strain" in cstmt or "trending" in cstmt)

        # the render's own guardrail legend must explicitly FORBID diagnosis + prediction.
        block = trajectory.render_trajectory(read)
        ok("render guardrail explicitly forbids diagnosis AND prediction",
           "NOT a diagnosis" in block and "NOT a prediction" in block)

        # belt-and-suspenders: the engine's OWN clean-gate independently agrees on every line.
        ok("the engine's own clean-gate also passes every generated line",
           all(trajectory._is_clean(l) for l in generated))


# ===================================================================================
# 5. NEVER-FABRICATE + render hygiene — no trend from noise; render leaks no scaffold tag.
# ===================================================================================
def test_never_fabricate_and_render_hygiene():
    print("\n[5] never-fabricate (no trend from noise) + render leaks no scaffold, in character")
    with _temp_store():
        # PURE NOISE inside the deadband: a subject jittering around a flat level must read
        # STABLE, never a manufactured rising/falling.
        noisy = "st_noise"
        _seed(noisy, [
            [("hobby", 5.0, 5, 1)],
            [("hobby", 5.1, 5, 1)],
            [("hobby", 4.9, 5, 1)],
            [("hobby", 5.05, 5, 1)],
            [("hobby", 4.95, 5, 1)],
        ])
        objs = {o["subject"]: o for o in trajectory.trajectory(noisy)["objects"]}
        ok("a flat-jittering subject reads STABLE, not a fabricated trend",
           objs.get("hobby", {}).get("direction") == trajectory.STABLE)
        ok("a noisy-flat subject yields NO convergence read",
           trajectory.trajectory(noisy)["composite"] is None)

        # RENDER HYGIENE — on a real rising/falling read, the items the user could hear must
        # carry NO raw scaffold tag, and the block must never instruct breaking character.
        name = "st_render"
        _seed(name, [
            [("work", 6.0, 6, 2), ("sleep", 8.0, 8, 2)],
            [("work", 9.0, 11, 3), ("sleep", 6.0, 6, 2)],
            [("work", 12.0, 16, 3), ("sleep", 4.0, 4, 2)],
        ])
        read = trajectory.trajectory(name)
        block = trajectory.render_trajectory(read)
        ok("render produces a non-empty binding block on a real read", bool(block.strip()))

        # every emitted bracket tag must be a KNOWN scaffold token (so the mouth scrubs it).
        items = trajectory._items_of(block)
        import re as _re
        emitted_tags = set(_re.findall(r"\[[A-Z]+\]", block))
        ok("every emitted [TAG] is in TRAJECTORY_SCAFFOLD_TOKENS (mouth-scrubbable)",
           emitted_tags and emitted_tags.issubset(set(trajectory.TRAJECTORY_SCAFFOLD_TOKENS)))

        # the SPOKEN-eligible items must not parrot the framing header or a citation tell.
        ok("the items section never says 'according to my memory'",
           "according to my memory" not in items.lower())
        ok("the items section carries no leftover all-caps framing header",
           "WHERE THINGS HAVE BEEN HEADING" not in items)

        # #1 PRODUCT RULE — the block must never instruct disclaiming / breaking character;
        # it must forbid it. (The legend NAMES the failure modes only to ban them.)
        ok("the guardrail forbids reading the brackets/numbers aloud",
           "Never read the brackets" in block)
        ok("the guardrail forbids diagnosis, prediction, and 'see anyone'",
           "NOT a diagnosis" in block and "NOT a prediction" in block
           and "see anyone" in block)

        # a bare LIST of objects (not the full dict) must also render cleanly — API tolerance.
        block_list = trajectory.render_trajectory(read["objects"])
        ok("render tolerates a bare list of objects too (no composite line, still clean)",
           bool(block_list.strip()) and trajectory._is_clean(trajectory._items_of(block_list)))


# ===================================================================================
# 6. READ-ONLY / APPEND-ONLY discipline — the engine never mutates the meaning ledger, and
#    its own optional ledger is append-only (Law 001), exactly like its siblings.
# ===================================================================================
def test_readonly_and_append_only():
    print("\n[6] read-only on the meaning ledger + append-only on its own ledger (Law 001)")
    with _temp_store():
        name = "st_readonly"
        _seed(name, [
            [("work", 6.0, 6, 2), ("sleep", 8.0, 8, 2)],
            [("work", 9.0, 11, 3), ("sleep", 6.0, 6, 2)],
            [("work", 12.0, 16, 3), ("sleep", 4.0, 4, 2)],
        ])
        meaning_ledger = meaning.ledger_path(name)
        before_bytes = meaning_ledger.read_bytes()

        # exercise every read path + a write to the OWN ledger.
        trajectory.trajectory(name)
        trajectory.render(name)
        trajectory.composite(name)
        trajectory.snapshot_trajectory(name)

        ok("the meaning significance ledger is BYTE-FOR-BYTE unchanged (read-only on it)",
           meaning_ledger.read_bytes() == before_bytes)

        # the trajectory ledger is a SEPARATE file and append-only.
        traj_ledger = trajectory.ledger_path(name)
        ok("the trajectory ledger is a distinct file (not the meaning ledger)",
           traj_ledger != meaning_ledger and traj_ledger.exists())
        n1 = len(trajectory.trajectory_snapshots(name))
        trajectory.snapshot_trajectory(name)
        snaps = trajectory.trajectory_snapshots(name)
        ok("a second snapshot GREW the trajectory ledger (append-only, prior kept)",
           len(snaps) == n1 + 1)
        ok("every recorded trajectory snapshot is stamped ANIMA LAW 003 / kind=trajectory",
           all(s.get("law") == "ANIMA LAW 003" and s.get("kind") == "trajectory"
               for s in snaps if isinstance(s, dict) and "kind" in s))


def main():
    print("=" * 79)
    print("TRAJECTORY ENGINE — 'where is this heading?'  ::  invariants on synthetic creatures")
    print("=" * 79)
    test_direction()
    test_not_enough_history()
    test_composite()
    test_no_diagnosis_gate()
    test_never_fabricate_and_render_hygiene()
    test_readonly_and_append_only()

    print("\n" + "=" * 79)
    if _fails:
        print(f"{len(_fails)} INVARIANT(S) FAILED: " + ", ".join(_fails))
        sys.exit(1)
    print("ALL TRAJECTORY INVARIANTS HOLD")


if __name__ == "__main__":
    main()
