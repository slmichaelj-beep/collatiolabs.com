#!/usr/bin/env python3
"""Curiosity-invariant test — ASSERT ANIMA LAW 002 on the real curiosity.py code paths.

    NEVER MAKE THE SAME DISCOVERY TWICE.

This is the standalone enforcement of Law 002, the way scripts/test_continuity.py is the
enforcement of Law 001. It drives anima.curiosity against SYNTHETIC creatures whose LIRF
ledger and world_state graph live entirely in a TemporaryDirectory — it NEVER reads or
writes a real Vera.* file. Every module-level STORE the engine and its dependencies touch
(curiosity, memory_lirf, world_state) is redirected to a fresh temp dir for the duration of
each test, exactly like test_continuity.py redirects STORE for the subsystems it checks.

What it asserts (each a hard invariant; a failure prints FAIL and exits non-zero):
  1. test_no_redundant_discovery — THE LAW 002 INVARIANT. A KNOWN birthday in LIRF means the
     engine NEVER produces a question targeting birthday (detect / generate / next_question).
  2. test_never_reask — after mark_asked(gap), next_question never returns that gap again;
     and once a gap becomes KNOWN it is never asked (it's been discovered).
  3. test_gap_detection — a high-mention world_state entity with an unknown relationship is a
     SUSPECTED gap; a fully-KNOWN category yields no gap for that slot.
  4. test_contradiction — a superseded LIRF value surfaces as a CONTRADICTED gap.
  5. test_question_relevance — generated questions reference the gap's entity (not canned),
     contain no scaffold tags, and never disclaim AI-ness.
  6. test_budget — minimal returns None more often than deep over a fixed gap set.

    python3 scripts/test_curiosity.py
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import curiosity                              # noqa: E402
from anima import memory_lirf                            # noqa: E402
from anima import world_state                            # noqa: E402

_fails: list[str] = []


def ok(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


@contextlib.contextmanager
def _temp_store(*modules):
    """Redirect each module's module-level STORE to a fresh temp dir, so nothing under the
    real .anima/ is ever read or written (mirrors test_continuity._temp_store)."""
    saved = [(m, getattr(m, "STORE", None)) for m in modules]
    with tempfile.TemporaryDirectory(prefix="anima-curiosity-") as td:
        p = Path(td)
        for m in modules:
            m.STORE = p
        try:
            yield p
        finally:
            for m, old in saved:
                if old is not None:
                    m.STORE = old


# -- synthetic-creature helpers (write ONLY into the redirected temp stores) -----------

def _seed_fact(name, *utterances):
    """Capture+merge a battery of user utterances into the LIRF ledger and persist. The
    STORE is already redirected, so this only ever writes the temp dir."""
    f = memory_lirf.Facts([])
    for u in utterances:
        for c in f.capture(name, u):
            f.merge(c)
    f.save(name)
    return f


def _seed_entity(name, entity, n, predicate="knows"):
    """Mention an entity ``n`` times in the world_state graph (unknown relationship), so it
    accrues ``support`` == n — the SUSPECTED-gap signal."""
    w = world_state.World([])
    for _ in range(n):
        w.add("you", predicate, entity, kind="relationship")
    w.save(name)
    return w


# ======================================================================================
# 1. THE LAW 002 INVARIANT — a KNOWN birthday is NEVER asked about. The headline test.
# ======================================================================================
def test_no_redundant_discovery():
    print("\n[1] LAW 002 — a KNOWN birthday is NEVER surfaced as a question (no re-discovery)")
    with _temp_store(curiosity, memory_lirf, world_state):
        name = "st_law002_" + secrets.token_hex(3)
        # seed a solidly-KNOWN birthday (stated + corroborated -> confidence >= 0.85)
        _seed_fact(name, "my birthday is June 12", "yep, June 12 is my birthday")
        row = memory_lirf.Facts.load(name).lookup(memory_lirf.SELF, "birthday")
        ok("setup: birthday is stored KNOWN (confidence >= 0.85)",
           row is not None and float(row["confidence"]) >= curiosity._CONF_KNOWN)

        # (a) DETECT: no gap whose slot/trait is birthday
        gaps = curiosity.detect_gaps(name)
        ok("[detect] a KNOWN birthday produces NO birthday gap",
           all(g.get("slot") != "birthday" and g.get("trait") != "birthday" for g in gaps))

        # (b) GENERATE: not a single phrased question mentions 'birthday' — THE KEY NUMBER
        questions = [q for q in (curiosity.generate_question(g) for g in gaps) if q]
        birthday_qs = [q for q in questions if re.search(r"\bbirthday\b", q, re.I)]
        ok(f"[generate] 0 of {len(questions)} generated questions reference the KNOWN "
           f"birthday (key number = {len(birthday_qs)})",
           len(birthday_qs) == 0)

        # (c) NEXT_QUESTION: many deep draws never yield a birthday question
        asked_birthday = False
        for _ in range(50):
            q = curiosity.next_question(name, budget="deep")
            if q and re.search(r"\bbirthday\b", q, re.I):
                asked_birthday = True
                break
        ok("[next_question] 50 deep draws NEVER ask about the KNOWN birthday",
           not asked_birthday)

        # and the inverse sanity: an UNKNOWN slot (the user's goal) IS askable, proving the
        # suppression is specific to the KNOWN fact, not a dead engine.
        ok("control: an UNKNOWN slot still produces a gap (engine is alive, just disciplined)",
           any(g.get("kind") == curiosity.UNKNOWN for g in gaps))


# ======================================================================================
# 2. NEVER RE-ASK — mark_asked retires a gap forever; a discovered gap is never asked.
# ======================================================================================
def test_never_reask():
    print("\n[2] never re-ask — mark_asked retires a gap forever; a discovered gap drops")
    with _temp_store(curiosity, memory_lirf, world_state):
        name = "st_reask_" + secrets.token_hex(3)
        _seed_entity(name, "Mike", 42)

        # Mike is a candidate before being asked
        before = curiosity.candidate_gaps(name)
        mike_before = [g for g in before if world_state._norm_node(g.get("entity", "")) == "mike"]
        ok("Mike is a candidate gap BEFORE being asked", len(mike_before) == 1)

        # surface + record it
        gap = mike_before[0]
        gap["_question"] = curiosity.generate_question(gap)
        rec = curiosity.mark_asked(name, gap)
        ok("mark_asked returns an append-only ledger record",
           isinstance(rec, dict) and rec.get("law") == "ANIMA LAW 002")

        # never a candidate again
        after = curiosity.candidate_gaps(name)
        ok("[Law 002] after mark_asked, Mike is NEVER a candidate again",
           all(world_state._norm_node(g.get("entity", "")) != "mike" for g in after))

        # next_question never returns the Mike question again, at ANY number of deep draws
        reasked = False
        for _ in range(40):
            q = curiosity.next_question(name, budget="deep")
            if q and "Mike" in q:
                reasked = True
                break
        ok("[Law 002] next_question (deep) never re-asks the asked Mike gap", not reasked)

        # the ledger is APPEND-ONLY (Law 001): asking a second gap grows the file, never
        # truncates the Mike record out of it.
        n1 = len(curiosity.ledger_path(name).read_text().splitlines())
        other = next((g for g in curiosity.candidate_gaps(name)), None)
        if other is not None:
            other["_question"] = curiosity.generate_question(other)
            curiosity.mark_asked(name, other)
        n2 = len(curiosity.ledger_path(name).read_text().splitlines())
        ok("[Law 001] the Asked Ledger is append-only (grows, never shrinks)", n2 >= n1 and n2 == n1 + 1)
        ok("[Law 001] the original Mike record still on disk after a later append",
           '"gap_key": "relationship:mike"' in curiosity.ledger_path(name).read_text())

        # --- once a gap BECOMES KNOWN it is dropped from candidates forever ---
        name2 = "st_discovered_" + secrets.token_hex(3)
        gaps_pre = curiosity.detect_gaps(name2)
        ok("a fresh creature has an UNKNOWN 'lives' gap",
           any(g.get("slot") == "lives" for g in gaps_pre))
        _seed_fact(name2, "I live in Portland", "yeah, Portland is home")  # now KNOWN
        ok("[Law 002] once 'lives' is KNOWN it is NEVER a gap again (discovered)",
           all(g.get("slot") != "lives" for g in curiosity.detect_gaps(name2)))


# ======================================================================================
# 3. GAP DETECTION — a high-mention unknown entity is SUSPECTED; a KNOWN category isn't.
# ======================================================================================
def test_gap_detection():
    print("\n[3] gap detection — SUSPECTED on a many-mention unknown entity; none on KNOWN")
    with _temp_store(curiosity, memory_lirf, world_state):
        name = "st_detect_" + secrets.token_hex(3)
        _seed_entity(name, "Mike", 42)        # high-mention, unknown relationship
        _seed_entity(name, "Quinn", 1)        # one passing mention -> below the floor

        gaps = curiosity.detect_gaps(name)
        mike = [g for g in gaps if world_state._norm_node(g.get("entity", "")) == "mike"]
        ok("a 42-mention unknown-relationship entity -> exactly one SUSPECTED gap",
           len(mike) == 1 and mike[0]["kind"] == curiosity.SUSPECTED)
        ok("the SUSPECTED gap carries the mention evidence (42)",
           (mike[0].get("evidence") or {}).get("mentions") == 42)
        ok("a 1-mention entity (Quinn) does NOT clear the mention floor",
           all(world_state._norm_node(g.get("entity", "")) != "quinn" for g in gaps))

        # PRIORITY: the many-mention SUSPECTED outranks an empty 'favorite food' UNKNOWN
        food = [g for g in gaps if g.get("slot") == "favorite_food"]
        ok("PRIORITY: Mike (x42) outranks the empty 'favorite food' slot",
           food and curiosity._score(mike[0]) > curiosity._score(food[0]))
        ok("PRIORITY: Mike is the single top-ranked gap overall",
           world_state._norm_node(gaps[0].get("entity", "")) == "mike")

        # a fully-KNOWN category yields NO gap for that slot (the inverse)
        name2 = "st_detect_known_" + secrets.token_hex(3)
        _seed_fact(name2, "my name is Dana", "right, I'm Dana",
                   "my birthday is March 3", "yeah March 3 is my birthday")
        gaps2 = curiosity.detect_gaps(name2)
        ok("a KNOWN 'name' slot produces NO name gap",
           all(g.get("slot") != "name" for g in gaps2))
        ok("a KNOWN 'birthday' slot produces NO birthday gap",
           all(g.get("slot") != "birthday" for g in gaps2))
        # but other unfilled categories are still open (engine isn't silenced wholesale)
        ok("other unfilled slots remain open gaps",
           any(g.get("kind") == curiosity.UNKNOWN for g in gaps2))


# ======================================================================================
# 4. CONTRADICTION — a superseded LIRF value surfaces as a CONTRADICTED gap.
# ======================================================================================
def test_contradiction():
    print("\n[4] contradiction — a superseded LIRF value -> CONTRADICTED gap")
    with _temp_store(curiosity, memory_lirf, world_state):
        name = "st_contra_" + secrets.token_hex(3)
        # state one value, then supersede it: history holds the displaced value
        _seed_fact(name, "I live in Portland", "actually I live in Seattle now")
        row = memory_lirf.Facts.load(name).lookup(memory_lirf.SELF, "lives")
        ok("setup: the active value is the newest (Seattle) with Portland in history",
           row and "seattle" in curiosity._fmt_value(row["value"]).lower()
           and any("portland" in curiosity._fmt_value(h.get("value", "")).lower()
                   for h in row.get("history", [])))

        gaps = curiosity.detect_gaps(name)
        contra = [g for g in gaps if g.get("slot") == "lives"
                  and g.get("kind") == curiosity.CONTRADICTED]
        ok("a superseded 'lives' value -> exactly one CONTRADICTED gap", len(contra) == 1)
        ok("the CONTRADICTED gap carries both the old and new values",
           contra and (contra[0].get("evidence") or {}).get("old")
           and (contra[0].get("evidence") or {}).get("new"))

        # the clarify question names BOTH values, warmly, without accusing
        q = curiosity.generate_question(contra[0]) if contra else ""
        ok("the clarify question names both Seattle and Portland",
           "Seattle" in q and "Portland" in q)
        ok("the clarify question is warm + clean (no scaffold, no AI-disclaimer)",
           not curiosity._looks_unsafe(q))
        ok("a CONTRADICTED tension is high-priority (outranks a bare UNKNOWN food slot)",
           contra and curiosity._score(contra[0]) > max(
               (curiosity._score(g) for g in gaps if g.get("slot") == "favorite_food"),
               default=0.0))


# ======================================================================================
# 5. QUESTION RELEVANCE — anchored to the entity, no scaffold tags, never disclaims AI.
# ======================================================================================
def test_question_relevance():
    print("\n[5] question relevance — contextual, no scaffold leak, never breaks character")
    with _temp_store(curiosity, memory_lirf, world_state):
        name = "st_relev_" + secrets.token_hex(3)
        _seed_entity(name, "Mike", 30)

        gaps = curiosity.detect_gaps(name)
        mike = [g for g in gaps if world_state._norm_node(g.get("entity", "")) == "mike"][0]
        mq = curiosity.generate_question(mike)
        ok("the SUSPECTED question NAMES the entity the user mentioned (Mike, not canned)",
           "Mike" in mq)
        ok("the SUSPECTED question is the contextual 'how do you know each other' shape",
           re.search(r"know each other|who (?:they|she|he) (?:are|is)", mq, re.I) is not None)
        ok("the SUSPECTED question is NOT the banned canned 'favorite color' ask",
           "favorite color" not in mq.lower())

        # EVERY generated question across the taxonomy is clean + in-character
        all_q = [curiosity.generate_question(g) for g in gaps]
        all_q = [q for q in all_q if q]
        ok("every generated question is non-empty and passes the safety gate",
           all_q and all(not curiosity._looks_unsafe(q) for q in all_q))
        # no scaffold token leaks into ANY question
        leaks = [q for q in all_q
                 for tok in curiosity.CURIOSITY_SCAFFOLD_TOKENS if tok and tok in q]
        ok("NO scaffold tag ([KNOWN]/[SUSPECTED]/[SITUATION]/…) leaks into any question",
           len(leaks) == 0)
        # no question breaks character (the #1 product rule)
        bad = [q for q in all_q if curiosity._BREAK_CHARACTER.search(q)]
        ok("NO question breaks character (no 'as an AI', 'text-based', etc.)", len(bad) == 0)
        # questions are warm/optional: none reads like an interrogation demand
        ok("questions read as warm invitations (contain a '?', none ALL-CAPS shouty)",
           all("?" in q and q.upper() != q for q in all_q))


# ======================================================================================
# 6. BUDGET — minimal returns None MORE OFTEN than deep over a fixed gap set.
# ======================================================================================
def test_budget():
    print("\n[6] budget — minimal stays silent more than deep (frequency, not content)")
    with _temp_store(curiosity, memory_lirf, world_state):
        base = "st_budget_" + secrets.token_hex(3)
        trials = 80
        none_min = none_deep = 0
        # distinct creature names give the deterministic per-(name,gap) frequency draw a
        # spread; each creature has the same UNKNOWN-gap taxonomy (no stores seeded).
        for i in range(trials):
            nm = f"{base}_{i}"
            if curiosity.next_question(nm, budget="minimal") is None:
                none_min += 1
            if curiosity.next_question(nm, budget="deep") is None:
                none_deep += 1
        ok(f"minimal returns None MORE OFTEN than deep "
           f"(minimal None={none_min}/{trials}, deep None={none_deep}/{trials})",
           none_min > none_deep)
        ok("deep almost always speaks when a good gap exists",
           none_deep <= trials // 5)
        ok("minimal is genuinely sparing (silent on a clear majority of turns)",
           none_min >= trials // 2)

        # content is identical regardless of budget — budget gates frequency, not wording.
        nm = f"{base}_content"
        # force a surfaced question under deep, capture it; the SAME gap under any budget
        # that DOES surface must produce the same string.
        qd = curiosity.next_question(nm, budget="deep")
        top = curiosity.candidate_gaps(nm)[0]
        ok("budget governs FREQUENCY only — the surfaced question is the gap's own text",
           qd == curiosity.generate_question(top))

        # the budget is read defensively (no caps key present -> 'balanced')
        ok("budget defaults to 'balanced' when caps has no curiosity setting",
           curiosity.read_budget(nm) == "balanced")


def main():
    print("=" * 79)
    print("ANIMA LAW 002 — NEVER MAKE THE SAME DISCOVERY TWICE  ::  invariant test")
    print("=" * 79)
    test_no_redundant_discovery()
    test_never_reask()
    test_gap_detection()
    test_contradiction()
    test_question_relevance()
    test_budget()

    print("\n" + "=" * 79)
    if _fails:
        print(f"{len(_fails)} INVARIANT(S) FAILED: " + ", ".join(_fails))
        sys.exit(1)
    print("ALL CURIOSITY INVARIANTS HOLD (LAW 002 enforced)")


if __name__ == "__main__":
    main()
