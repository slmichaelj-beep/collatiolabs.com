#!/usr/bin/env python3
"""Opportunity-Engine invariant test — ASSERT the proactive OFFER engine on REAL code paths.

    OFFER, NOT ACTION.  Observed > Assumed.  Warm + optional, never nagging.

The Opportunity Engine (anima/opportunity.py) answers "what would HELP?" as a gentle,
optional OFFER grounded in observed patterns. It is where Vera turns from reactive to
proactive. Its ONE non-negotiable invariant is that an opportunity is a PROPOSAL, never an
action: it READS the life signals and APPENDS to its own offer ledger, and it EXECUTES
NOTHING. If the user says "yes", the acting flows through route.py's existing
draft→confirm→execute gate on their explicit next turn — not here.

This file checks those promises against the actual engines the opportunity engine reads —
using SYNTHETIC creatures in a TemporaryDirectory ONLY. It NEVER touches Vera.* on disk:
every module's STORE (opportunity + the loops / meaning / curiosity / world_state it reads)
is redirected to a temp dir for the duration, so a real creature's life is never read or
written.

What it asserts:
  1. GROUNDED OFFER vs SILENCE — a STALLED, significant project surfaces a milestone-plan
     OFFER; a sparse/quiet life surfaces NOTHING (never-fabricate — no generic tips).
  2. OFFER-NOT-ACTION (load-bearing) — generating + pacing + offering executes NOTHING: with
     every host_access/route/calendar/reminder executor monkeypatched to blow up, NONE fire;
     the opportunity only reads + appends to its OWN ledger; the offer is a proposal STRING.
  3. NEVER RE-OFFER — after mark_offered, the same opportunity isn't offered again (paced);
     a declined one isn't nagged.
  4. THE #1 PRODUCT RULE — offers are warm + optional (a soft, declinable framing); no
     scaffold tag; no character break; NO diagnosis.
  5. PACING — at most one per call; the budget controls frequency.

PASS where the promise holds; a clear FAIL and non-zero exit where it does not.

    python3 scripts/test_opportunity.py
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

from anima import opportunity                            # noqa: E402
from anima import world_state                            # noqa: E402
from anima import loops                                  # noqa: E402

# meaning / curiosity are the grounding engines; redirect their STORE too when present so
# nothing leaks to the real .anima. (The opportunity engine degrades gracefully without
# them, but the realistic creature needs them to produce significance + suspected gaps.)
try:  # pragma: no cover - optional dep
    from anima import meaning
    _HAVE_MEANING = True
except Exception:  # pragma: no cover
    meaning = None
    _HAVE_MEANING = False
try:  # pragma: no cover - optional dep
    from anima import curiosity
    _HAVE_CURIOSITY = True
except Exception:  # pragma: no cover
    curiosity = None
    _HAVE_CURIOSITY = False

_fails: list[str] = []
_violations: list[str] = []


def ok(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def law_violation(subsystem, msg):
    """Flag a place where the invariant is violated by current code (not a test bug)."""
    print(f"  INVARIANT-VIOLATION [{subsystem}] {msg}")
    _violations.append(f"{subsystem}: {msg}")


def _store_modules():
    mods = [opportunity, world_state, loops]
    if _HAVE_MEANING:
        mods.append(meaning)
    if _HAVE_CURIOSITY:
        mods.append(curiosity)
    return mods


@contextlib.contextmanager
def _temp_store(*modules):
    """Redirect each module's module-level STORE to a fresh temp dir, so nothing under the
    real .anima/ is ever read or written. Mirrors scripts/test_loops.py exactly."""
    saved = [(m, getattr(m, "STORE", None)) for m in modules]
    with tempfile.TemporaryDirectory(prefix="anima-opp-test-") as td:
        p = Path(td)
        for m in modules:
            if hasattr(m, "STORE"):
                m.STORE = p
        try:
            yield p
        finally:
            for m, old in saved:
                if old is not None:
                    m.STORE = old


# A fixed reference "now" so the tests are deterministic regardless of the wall clock. The
# synthetic goal is stated in January; we evaluate as-of June, so it is clearly past the
# stall threshold and reads stalled.
_JAN = "2026-01-05T00:00:00Z"
_NOW_JUN = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
_NOW_AUG = datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp()


def _seed_stalled_significant_project(name: str) -> None:
    """Build a SYNTHETIC creature with a STALLED, SIGNIFICANT project, the way the live system
    would have it on disk: a stated goal (captured through the real world_state pipeline) that
    has gone quiet, plus enough corroborating mentions/connections that the Meaning Engine
    reads the topic as significant. Then BACKDATE every edge to January so it reads stalled
    as-of-June. Uses ONLY the real world_state API + an on-disk timestamp edit; no opportunity
    internals are touched."""
    # the stated commitment (creates a working_toward goal edge)
    world_state.capture_relations(name, "I want to launch the podcast in March")
    # make the podcast MATTER: corroborate it and connect it to other nodes (significance =
    # frequency + connectivity).
    W = world_state.World.load(name)
    for _ in range(5):
        W.add("you", "working_on", "podcast", kind="goal", source="chat")
    W.add("podcast", "needs", "editing", kind="fact", source="chat")
    W.add("podcast", "about", "music", kind="fact", source="chat")
    W.save(name)
    # backdate so the loop is long-silent (stalled) as of June.
    p = world_state.World.path(name)
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    for r in d.get("relations", []):
        r["created"] = _JAN
        r["updated"] = _JAN
    p.write_text(json.dumps(d), encoding="utf-8")


# ===================================================================================
# 1. GROUNDED OFFER vs SILENCE — a stalled significant project surfaces a milestone-plan
#    offer; a sparse/quiet life surfaces NOTHING (never-fabricate).
# ===================================================================================
def test_grounded_offer_and_silence():
    print("\n[1] grounded offer vs silence — a stalled significant project OFFERS a plan; a "
          "sparse life offers NOTHING")
    with _temp_store(*_store_modules()):
        name = "synth_opp_stalled"
        _seed_stalled_significant_project(name)

        opps = opportunity.opportunities(name, now=_NOW_JUN)
        stalled = [o for o in opps if o["kind"] == opportunity.STALLED_PROJECT]
        ok("a STALLED, significant project surfaces a STALLED_PROJECT opportunity",
           len(stalled) >= 1)
        if stalled:
            o = stalled[0]
            low = o["offer"].lower()
            ok("the opportunity carries kind/trigger/offer/confidence/evidence (a full object)",
               all(k in o for k in ("kind", "trigger", "offer", "confidence", "evidence")))
            ok("the offer is GROUNDED in the actual project (names it, not a generic tip)",
               "podcast" in low)
            ok("the offer proposes MILESTONE/plan help ('want me to help sketch a plan?')",
               any(p in low for p in ("milestone", "plan", "first steps", "step", "map",
                                      "path", "break it")))
            ok("the trigger states the OBSERVED pattern (stalled + significant)",
               "stalled" in o["trigger"].lower())
            ok("confidence is in (0,1) and evidence cites the source engines",
               0.0 < float(o["confidence"]) < 1.0
               and "loops" in str(o["evidence"].get("source", "")))

        # SILENCE: a sparse/quiet life has nothing stated, significant, or often-mentioned —
        # so there is NOTHING to offer. The engine must NOT invent a generic tip.
        quiet = "synth_opp_quiet"
        world_state.capture_relations(quiet, "I had toast this morning")
        sparse = opportunity.opportunities(quiet, now=_NOW_JUN)
        ok("a sparse/quiet life yields NO opportunities (never-fabricate; no generic tips)",
           sparse == [])
        ok("next_opportunity on a sparse life is None (stays silent)",
           opportunity.next_opportunity(quiet, budget="deep", now=_NOW_JUN) is None)
        ok("a totally empty creature yields NO opportunities",
           opportunity.opportunities("synth_opp_empty", now=_NOW_JUN) == [])


# ===================================================================================
# 2. OFFER-NOT-ACTION (load-bearing) — generating/pacing/offering EXECUTES NOTHING.
#    We arm a tripwire on every executor an action would touch and prove NONE fire.
# ===================================================================================
class _Tripped(Exception):
    pass


def test_offer_is_never_an_action():
    print("\n[2] OFFER-NOT-ACTION — generating + pacing + offering executes NOTHING "
          "(no host/route/calendar/reminder side effects)")
    with _temp_store(*_store_modules()):
        name = "synth_opp_noact"
        _seed_stalled_significant_project(name)

        tripped: dict = {"hit": None}

        def _tripwire(label):
            def boom(*a, **k):
                tripped["hit"] = label
                raise _Tripped(label)
            return boom

        # Monkeypatch EVERY executor an "action" would route through: the host_access
        # primitives (calendar/reminder/note/imessage), and route's execute/prepare/pending.
        # An OFFER must touch NONE of them.
        patched = []
        try:
            from anima import host_access as _ha
            for fn in ("create_reminder", "create_event", "create_note", "append_to_note",
                       "complete_reminder", "send_imessage", "list_reminders", "list_events"):
                if hasattr(_ha, fn):
                    patched.append((_ha, fn, getattr(_ha, fn)))
                    setattr(_ha, fn, _tripwire(f"host_access.{fn}"))
        except Exception:
            pass
        try:
            from anima import route as _rt
            for fn in ("route", "_host_execute", "_host_prepare", "_pending_set"):
                if hasattr(_rt, fn):
                    patched.append((_rt, fn, getattr(_rt, fn)))
                    setattr(_rt, fn, _tripwire(f"route.{fn}"))
        except Exception:
            pass

        try:
            # Drive the WHOLE proactive path against the armed tripwires.
            opps = opportunity.opportunities(name, now=_NOW_JUN)
            line = opportunity.next_opportunity(name, budget="deep", now=_NOW_JUN)
            ch = opportunity.last_opportunity_choice()
            if ch:
                opportunity.mark_offered(name, ch["key"], line=ch["line"],
                                         confidence=ch.get("confidence"))
                # even recording the user's "yes" must NOT execute anything here.
                opportunity.mark_response(name, ch["key"], "accepted", note="yes please")
            _ = opportunity.render(name)
            ok("no host_access / route executor fired during generate + pace + offer + accept",
               tripped["hit"] is None)
            if tripped["hit"] is not None:
                law_violation("anima/opportunity.py",
                              f"an executor ({tripped['hit']}) was called by the opportunity "
                              f"engine — an opportunity must OFFER, never ACT. Acting belongs to "
                              f"route.py's confirm-gate on the user's explicit yes.")
            # the offer itself must be a plain proposal STRING, not a callable/side-effecting obj.
            if opps:
                ok("an opportunity's 'offer' is a proposal STRING (a proposal, not a callable)",
                   isinstance(opps[0]["offer"], str) and not callable(opps[0]["offer"]))
            ok("next_opportunity returns a STRING offer or None (never an action handle)",
               line is None or isinstance(line, str))
        finally:
            for obj, fn, orig in patched:
                setattr(obj, fn, orig)

        # The ONLY thing the engine wrote is its OWN offer ledger — and only OFFER/response
        # events, never an action event. Prove it by inspecting what landed on disk.
        ledger = opportunity.ledger_path(name)
        ok("the engine wrote ONLY its own offer ledger (.offers.jsonl exists)",
           ledger.exists())
        events = opportunity.read_ledger(name)
        ok("the ledger holds only OFFER/response events (offered/accepted/declined), no actions",
           all(e.get("event") in ("offered", "accepted", "declined") for e in events if isinstance(e, dict))
           and not any(e.get("event") in ("executed", "sent", "did", "performed", "created")
                       for e in events if isinstance(e, dict)))

        # Structural: the public API exposes NO execute/act/send/do primitive — there is no
        # door to perform anything, by construction.
        ok("the opportunity API exposes NO execute/send/do/act/run/perform/apply primitive",
           not any(hasattr(opportunity, n) for n in
                   ("execute", "send", "do", "act", "run", "perform", "apply", "fulfill")))
        if any(hasattr(opportunity, n) for n in ("execute", "send", "do", "act", "run")):
            law_violation("anima/opportunity.py",
                          "an action primitive exists on the opportunity API — an opportunity "
                          "must only ever OFFER; acting flows through route.py's confirm-gate.")


# ===================================================================================
# 3. NEVER RE-OFFER — after mark_offered the same opportunity isn't offered again; a
#    declined one isn't nagged. (Append-only ledger; pacing.)
# ===================================================================================
def test_never_reoffer_and_decline_respected():
    print("\n[3] never re-offer — after mark_offered the same offer isn't repeated; a decline "
          "is respected (not nagged)")
    with _temp_store(*_store_modules()):
        name = "synth_opp_reoffer"
        _seed_stalled_significant_project(name)

        first = opportunity.next_opportunity(name, budget="deep", now=_NOW_JUN)
        ok("an un-offered grounded opportunity IS offered (one warm line)",
           isinstance(first, str) and bool(first.strip()))
        ch = opportunity.last_opportunity_choice()
        ok("next_opportunity exposes which opportunity it chose (so a caller can mark it shown)",
           ch is not None and ch.get("key"))
        key = ch["key"]
        opportunity.mark_offered(name, key, line=first, confidence=ch.get("confidence"))

        # Re-call within pacing: the SAME opportunity (by key) must NOT be offered again.
        repeats = 0
        for _ in range(6):
            again = opportunity.next_opportunity(name, budget="deep", now=_NOW_JUN)
            if again is None:
                continue
            ck = (opportunity.last_opportunity_choice() or {}).get("key")
            if ck == key:
                repeats += 1
        ok("the SAME opportunity is NOT offered again after mark_offered (gentle, never naggy)",
           repeats == 0)

        # Decline it -> respected: NOT re-offered even at deep budget, even later (within the
        # reconsider cooldown). A "no" is honored, not nagged around.
        opportunity.decline(name, key, note="not right now")
        nagged = 0
        for when in (_NOW_JUN, _NOW_AUG):
            for _ in range(4):
                ln = opportunity.next_opportunity(name, budget="deep", now=when)
                if ln and (opportunity.last_opportunity_choice() or {}).get("key") == key:
                    nagged += 1
        ok("a DECLINED opportunity is NEVER nagged (respected through the cooldown)",
           nagged == 0)

        # Append-only: the offer AND the decline are both on disk; the file only grew.
        n_before = len(opportunity.read_ledger(name))
        opportunity.mark_offered(name, "some_other::thing", line="(an unrelated later event)")
        n_after = len(opportunity.read_ledger(name))
        ok("[append-only] adding an event GROWS the ledger, never shrinks/rewrites it",
           n_after == n_before + 1)
        raw = opportunity.ledger_path(name).read_text(encoding="utf-8")
        ok("[append-only] the on-disk ledger contains BOTH the offer and the decline",
           '"event": "offered"' in raw and '"event": "declined"' in raw)


# ===================================================================================
# 4. THE #1 PRODUCT RULE — warm + optional, no scaffold tag, no character break, NO diagnosis.
# ===================================================================================
def test_offers_are_warm_optional_no_diagnosis():
    print("\n[4] #1 product rule — every offer is warm + optional, no scaffold tag, no "
          "character break, NO diagnosis")
    with _temp_store(*_store_modules()):
        name = "synth_opp_warm"
        _seed_stalled_significant_project(name)
        # also seed an often-mentioned, significant but UNEXPLAINED entity (a place) and a
        # DECLINING thread, so we scrutinise all three kinds of offer language.
        W = world_state.World.load(name)
        for _ in range(6):
            W.add("you", "went_to", "the lighthouse", kind="event", source="chat")
        W.add("the lighthouse", "near", "the coast", kind="fact", source="chat")
        W.save(name)

        opps = opportunity.opportunities(name, now=_NOW_JUN)
        offers = [o["offer"] for o in opps]
        ok("there is at least one offer to scrutinise", len(offers) >= 1)

        OPTIONAL_CUES = ("want", "if you", "if it", "only if", "no pressure", "no rush",
                         "happy to", "up to you", "your call", "no worries", "okay too",
                         "no judgment", "would you like", "if you'd like")
        for off in offers:
            low = off.lower()
            ok(f"offer is warm + OPTIONAL (a soft, declinable framing): \"{off[:38]}...\"",
               any(p in low for p in OPTIONAL_CUES))
            ok("offer carries NO scaffold tag (nothing the model would read aloud)",
               "[" not in off and "]" not in off)
            ok("offer never breaks character / never disclaims being an AI",
               "according to my memory" not in low and "i'm just an ai" not in low
               and "as an ai" not in low and "language model" not in low)
            ok("offer carries NO diagnosis / clinical language (NO medical framing)",
               not any(w in low for w in ("disorder", "diagnos", "depress", "anxiety",
                                          "symptom", "condition", "mental health", "therapy",
                                          "therapist", "you should see a")))

        # render_opportunity is the seam the mouth narrates: clean, tag-free, still warm.
        if opps:
            line = opportunity.render_opportunity(opps[0])
            ok("render_opportunity yields a clean, tag-free, warm line",
               isinstance(line, str) and bool(line) and "[" not in line and "]" not in line)


# ===================================================================================
# 5. PACING — at most one per call; the budget controls frequency.
# ===================================================================================
def test_pacing_at_most_one_budget_controls_frequency():
    print("\n[5] pacing — at most ONE offer per call; the budget controls frequency")
    with _temp_store(*_store_modules()):
        name = "synth_opp_pace"
        _seed_stalled_significant_project(name)

        line = opportunity.next_opportunity(name, budget="deep", now=_NOW_JUN)
        ok("next_opportunity returns AT MOST ONE offer (a single string, never a batch)",
           line is None or (isinstance(line, str) and "\n" not in line.strip()))

        # Frequency: across many fresh creatures each holding a grounded opportunity, a minimal
        # budget stays silent far more often than a deep one (frequency, not content). Each
        # creature is independent so the deterministic per-(name,key) gate varies.
        def seed(nm):
            world_state.capture_relations(nm, "I want to launch the podcast in March")
            Wn = world_state.World.load(nm)
            for _ in range(5):
                Wn.add("you", "working_on", "podcast", kind="goal", source="chat")
            Wn.add("podcast", "needs", "editing", kind="fact", source="chat")
            Wn.save(nm)
            pn = world_state.World.path(nm)
            dn = json.loads(pn.read_text(encoding="utf-8"))
            for r in dn.get("relations", []):
                r["created"] = _JAN
                r["updated"] = _JAN
            pn.write_text(json.dumps(dn), encoding="utf-8")

        N = 30
        silent_min = silent_deep = 0
        for i in range(N):
            nm_min = f"synth_opp_bm_{i}"
            nm_deep = f"synth_opp_bd_{i}"
            seed(nm_min)
            seed(nm_deep)
            if opportunity.next_opportunity(nm_min, budget="minimal", now=_NOW_JUN) is None:
                silent_min += 1
            if opportunity.next_opportunity(nm_deep, budget="deep", now=_NOW_JUN) is None:
                silent_deep += 1
        ok(f"minimal stays silent MORE than deep ({silent_min}/{N} vs {silent_deep}/{N})",
           silent_min > silent_deep)
        ok("deep almost always offers when a grounded opportunity exists",
           silent_deep <= max(2, N // 10))


def main():
    print("=" * 79)
    print("ANIMA — THE OPPORTUNITY ENGINE (proactive offers)  ::  invariant test on real "
          "code paths")
    print("=" * 79)
    test_grounded_offer_and_silence()
    test_offer_is_never_an_action()
    test_never_reoffer_and_decline_respected()
    test_offers_are_warm_optional_no_diagnosis()
    test_pacing_at_most_one_budget_controls_frequency()

    print("\n" + "=" * 79)
    if _violations:
        print(f"INVARIANT VIOLATIONS FLAGGED ({len(_violations)}) — human action required:")
        for v in _violations:
            print(f"  • {v}")
        print()
    if _fails:
        print(f"{len(_fails)} INVARIANT(S) FAILED: " + ", ".join(_fails))
        sys.exit(1)
    print("ALL OPPORTUNITY-ENGINE INVARIANTS HOLD"
          + (f"  ({len(_violations)} flagged above)" if _violations else ""))


if __name__ == "__main__":
    main()
