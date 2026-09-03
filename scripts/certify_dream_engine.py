#!/usr/bin/env python3
"""
certify_dream_engine — THE DREAM ENGINE live path: a stated intention becomes a tracked open loop,
its status is derived from evidence over time, a stalled loop gently resurfaces in a real reply, and
a resolved loop is ARCHIVED (never deleted) — ANIMA LAW 001 made concrete for stated commitments.

Proves the open-loops / stated-commitment contract end-to-end through the SAME functions the server's
per-turn proactive-aside block calls (loops.resurface / last_resurface_choice / mark_resurfaced), with
the loop SEEDED through the SAME real capture layer the turn-lock runs (world_state.capture_relations):

  A. STATED INTENTION -> TRACKED OPEN LOOP — world_state.capture_relations(name, "I want to launch
     VeraCall in March") persists a real working_toward goal edge (no model), and loops.detect_loops
     then surfaces it as exactly ONE tracked open loop whose intent is what was said. Grounded, never
     inferred: a non-goal utterance ("the weather is nice") yields NO loop.
  B. STATUS FROM EVIDENCE — _status_from_evidence reads open / progressing / stalled / done / declined
     from the evidence text + recency only (a long-silent stated goal -> stalled; a completion cue ->
     done; a decline cue -> declined; a fresh goal -> open).
  C. RESURFACE IS WARM + OPTIONAL + IN-CHARACTER — the stalled loop yields one warm line that names the
     intent, offers (never demands), and carries NO scaffold tag / "according to my memory" / "I'm just
     an AI" character break.
  D. THE SERVER'S EXACT ASIDE SEQUENCE + PACING — resurface -> last_resurface_choice -> mark_resurfaced
     (the verbatim sequence in server._turn) records the resurfacing append-only, and the SAME loop is
     then NOT resurfaced again within the 21-day cooldown (never nag).
  E. LAW 001 LEDGER — mark_status open->progressing then close() archives 'done' as a NEW line
     (archived=True) while the full prior history stays on disk; detect_loops OVERLAYS that archive so
     the loop reads done and is NEVER resurfaced again (Archived > Deleted).
  F. MODULE SELFTEST — `python3 -m anima.loops` passes (the engine's own dependency-free proof).

Hermetic + offline (no model, no network): loops.STORE + every other store are redirected to a temp
dir via _temp_store(); the real .anima is fingerprinted before/after and asserted byte-identical. Exit
0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import loops, world_state
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("DREAM ENGINE — a stated intention becomes a tracked open loop, stalls, resurfaces, archives")
    print("=" * 92)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # _status_from_evidence is a pure function — exercise it outside the store too (B, partly).
    now_jun = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
    ck("B0: a fresh stated goal with no resolution cue reads 'open'",
       loops._status_from_evidence("launch veracall", last_seen=loops._now())[0] == loops.OPEN)

    with _temp_store():
        N = "DreamCert"

        # ---- A. STATED INTENTION -> TRACKED OPEN LOOP (through the REAL capture layer) -------
        # The SAME deterministic capture the server's turn-lock calls alongside memory_lirf.capture.
        touched = world_state.capture_relations(N, "I want to launch VeraCall in March")
        ck("A1: the real capture layer persists a working_toward goal edge from the stated intention",
           any(str(e.get("predicate")) == "working_toward" for e in touched))
        # now_jun is months after capture (created "now"), so the loop reads as recent/open here; the
        # point of A is that the STATED thing became a TRACKED loop, grounded in what was said.
        detected = loops.detect_loops(N)
        veracall = [L for L in detected if "veracall" in L.get("intent", "").lower()]
        ck("A2: loops.detect_loops surfaces exactly ONE tracked open loop for the stated intention",
           len(veracall) == 1)
        ck("A3: the loop's intent is the thing the user SAID (grounded surface phrase)",
           bool(veracall) and "veracall" in veracall[0]["intent"].lower()
           and "launch" in veracall[0]["intent"].lower())
        ck("A4: the loop is grounded in a real source (world_edge), never inferred",
           bool(veracall) and veracall[0].get("source_kind") == "world_edge"
           and bool(veracall[0].get("evidence")))
        # Observed > Assumed: a NON-goal utterance produces NO loop.
        world_state.capture_relations(N, "the weather is nice today")
        again = loops.detect_loops(N)
        ck("A5: a non-goal utterance adds NO loop (grounded only in stated commitments)",
           len(again) == len(detected))

        # ---- B. STATUS FROM EVIDENCE (over time) --------------------------------------------
        ck("B1: a long-silent stated goal reads 'stalled' (the resurface candidate)",
           loops._status_from_evidence("launch veracall in march",
                                       last_seen="2026-01-01T00:00:00Z", now=now_jun)[0] == loops.STALLED)
        ck("B2: a completion cue reads 'done'",
           loops._status_from_evidence("finally launched veracall", last_seen=loops._now())[0] == loops.DONE)
        ck("B3: a decline cue reads 'declined'",
           loops._status_from_evidence("decided not to do veracall", last_seen=loops._now())[0] == loops.DECLINED)

        # ---- C. RESURFACE IS WARM + OPTIONAL + IN-CHARACTER ---------------------------------
        # Build a long-silent (stalled) loop deterministically from a synthetic stated edge, exactly
        # the shape world_state writes, so detect/resurface read a real stalled commitment.
        long_ago = "2026-01-05T00:00:00Z"
        stalled_loop = loops._loop_from_edge({
            "kind": "goal", "subject": "you", "predicate": "working_toward",
            "object": "launch veracall in march", "support": 1, "source": "chat 2026-01-05",
            "created": long_ago, "updated": long_ago, "status": "active",
        }, now=now_jun)
        ck("C0: that long-silent stated edge becomes a STALLED open loop with its target recognised",
           stalled_loop is not None and stalled_loop["status"] == loops.STALLED
           and stalled_loop.get("has_target") is True)
        line = loops._resurface_line(stalled_loop)
        low = (line or "").lower()
        ck("C1: the resurface line names the stated intent (contextual, grounded)",
           "veracall" in low)
        ck("C2: it OFFERS, never demands (warm + optional phrasing — the #1 product rule)",
           any(p in low for p in ("still", "no pressure", "wondering", "someday", "moment")))
        ck("C3: no scaffold tag / no 'according to my memory' / no character break",
           "[" not in line and "according to my memory" not in low
           and "i'm just an ai" not in low and "as an ai" not in low)

        # ---- D. THE SERVER'S EXACT ASIDE SEQUENCE + PACING ----------------------------------
        # A creature for whom a stalled loop re-derives every turn (monkeypatch the world reader to the
        # same long-silent edge), so resurface picks it — mirrors server._turn's proactive-aside block.
        _orig_reader = loops._read_world_edges

        def _fake_reader(_name, _edge={"kind": "goal", "subject": "you",
                                       "predicate": "working_toward", "object": "launch veracall in march",
                                       "support": 1, "source": "chat 2026-01-05",
                                       "created": long_ago, "updated": long_ago, "status": "active"}):
            return [dict(_edge)]

        loops._read_world_edges = _fake_reader  # type: ignore[assignment]
        try:
            M = "DreamCertServer"
            # --- VERBATIM server._turn aside sequence ---
            rl = loops.resurface(M, now=now_jun)               # 1) at most one stalled check-in
            ck("D1: resurface returns one warm check-in for the stalled loop (server's aside)",
               isinstance(rl, str) and "veracall" in rl.lower())
            ch = loops.last_resurface_choice()                 # 2) the chosen loop key, for marking
            ck("D2: last_resurface_choice exposes the chosen loop (server reads it to mark)",
               isinstance(ch, dict) and bool(ch.get("key")))
            rec = loops.mark_resurfaced(M, ch, line=rl) if ch else None  # 3) record append-only (never re-nag)
            ck("D3: mark_resurfaced records the resurfacing append-only", rec is not None)
            rl2 = loops.resurface(M, now=now_jun)              # same turn-window: cooldown holds
            ck("D4: the SAME loop is NOT resurfaced again within the 21-day cooldown (never nag)",
               rl2 is None)
            future = datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp()
            rl3 = loops.resurface(M, now=future)               # past cooldown: may gently surface again
            ck("D5: past the cooldown the loop can gently surface again (still tracked forever)",
               isinstance(rl3, str))
        finally:
            loops._read_world_edges = _orig_reader  # type: ignore[assignment]

        # ---- E. LAW 001 LEDGER — archive, never delete; overlay wins ------------------------
        K = "DreamCertLedger"
        loops._read_world_edges = _fake_reader  # type: ignore[assignment]
        try:
            base = loops.detect_loops(K, now=now_jun)
            target = next(L for L in base if "veracall" in L["intent"].lower())
            loops.mark_status(K, target, loops.OPEN, note="first sighting")
            loops.mark_status(K, target, loops.PROGRESSING, note="user said they started")
            done = loops.close(K, target, resolution=loops.DONE, note="user said they shipped it")
            ck("E1: close() ARCHIVES the loop as 'done' (a status flip, archived=True) — not a delete",
               done is not None and done["status"] == loops.DONE and done["archived"] is True)
            hist = loops.ledger_history(K).get(target["key"], [])
            ck("E2: LAW 001 — the full status history SURVIVES append-only (open->progressing->done)",
               [h["status"] for h in hist] == [loops.OPEN, loops.PROGRESSING, loops.DONE])
            raw_disk = loops.ledger_path(K).read_text(encoding="utf-8")
            ck("E3: every prior status line is still on the ledger FILE (archived, never erased)",
               raw_disk.count('"event": "status"') >= 3 and '"status": "open"' in raw_disk)
            re_detected = loops.detect_loops(K, now=now_jun)
            same = [d for d in re_detected if d["key"] == target["key"]]
            ck("E4: detect_loops OVERLAYS the archive — the closed loop reads done + archived (ledger wins)",
               len(same) == 1 and same[0]["status"] == loops.DONE and same[0].get("archived") is True)
            ck("E5: an archived (done) loop is NEVER resurfaced again (Archived > Deleted)",
               loops.resurface(K, budget="deep", now=now_jun) is None)
        finally:
            loops._read_world_edges = _orig_reader  # type: ignore[assignment]

    # ---- F. MODULE SELFTEST (the engine's own dependency-free proof) -------------------------
    cp = subprocess.run([sys.executable, "-m", "anima.loops"],
                        cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    ck("F1: `python3 -m anima.loops` selftest passes (exit 0 + ALL LOOPS SELFTESTS PASS)",
       cp.returncode == 0 and "ALL LOOPS SELFTESTS PASS" in (cp.stdout or ""))

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nDREAM-ENGINE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
