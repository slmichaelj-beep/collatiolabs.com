#!/usr/bin/env python3
"""
certify_trajectory_engine — the Trajectory Engine: continuity-based DIRECTION, NEVER diagnosis.

trajectory asks "where is this HEADING?" — the DIRECTION + momentum of a life as it moves through
time — read as the SLOPE of a SEQUENCE of nightly significance snapshots (continuity). It is NOT
prediction and above all NOT diagnosis. This certifies that contract through the SAME functions the
nightly read and the live mouth reply-gate call:

  A. DIRECTION FROM CONTINUITY — seed the meaning significance ledger (trajectory's SOLE input; it
     owns no writer, so we write meaning's ledger directly, which is the real source) with a SEQUENCE
     where work RISES, sleep FALLS, reading is flat, exercise FALLS. trajectory(name) is ready
     (>=2 snapshots), reads the whole sequence, and composes per-subject directions FROM the slope:
     work=RISING, sleep=FALLING, reading=STABLE — each Trajectory Object citing the score_path/slope
     EVIDENCE it was built on (nothing invented).
  B. DESCRIPTIVE COMPOSITE — the convergence read names the strain direction DESCRIPTIVELY ("trending
     toward more strain", subjects include sleep + work), carries evidence + a confidence, and is clean.
  C. THE NO-DIAGNOSIS WALL (load-bearing) — EVERY generated line (each per-subject line + the composite
     statement + the rendered items) passes _is_clean; _is_clean CATCHES diagnosis/prognosis/referral
     phrasing; _safe_statement REPLACES a banned-term statement with its clean fallback; and
     render_trajectory's guardrail explicitly forbids diagnosis + prediction. Trajectory describes a
     TREND, never a person's condition.
  D. SAME WALL IS THE LIVE REPLY GATE — mouth._diagnosis_terms() IS trajectory.BANNED_TERMS (the widest
     list), mouth._strip_diagnosis_sentences drops a diagnosis sentence from a real chat reply while
     keeping the honest rest, and every trajectory scaffold tag is scrubbed by mouth._strip_scaffold_leak
     — so the wall trajectory builds is exactly the one enforced on every shipped reply.
  E. HONEST EMPTY / NEVER-FABRICATE — a life with < 2 snapshots is ready=False with an honest reason
     and NO objects; render of a not-ready read is ""; composite() of an empty life is None.

Hermetic + offline (no model, no network): _temp_store redirects EVERY store incl. meaning.STORE and
trajectory.STORE to a temp dir; the real .anima is fingerprinted before/after and asserted byte-
identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
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


def _snapshot(at_index: int, rows: list) -> dict:
    """Forge a meaning-shaped significance snapshot (the exact shape meaning.snapshot writes):
    {law, at, version, significance:[{subject,score,mentions,degree}]}. `at` is spaced by day on a
    fixed base so ordering is stable and the sequence is reproducible."""
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


def main() -> int:
    from anima import trajectory as T, meaning, mouth
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("TRAJECTORY ENGINE — continuity-based DIRECTION, NEVER diagnosis")
    print("=" * 66)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # ---- Pure-function facts (model-free), exercisable outside the store --------------------
    ck("C0a: _is_clean CATCHES diagnosis / prognosis / referral phrasing",
       (not T._is_clean("you sound depressed")) and (not T._is_clean("this is burnout"))
       and (not T._is_clean("you will spiral")) and (not T._is_clean("a poor prognosis"))
       and (not T._is_clean("you should see a therapist")))
    ck("C0b: _is_clean PASSES a neutral descriptive trend phrase",
       T._is_clean("stress has been climbing across the last few readings"))
    ck("C0c: _safe_statement REPLACES a banned-term statement with its clean fallback",
       T._safe_statement("you are clearly burning out", "work has been climbing across 4 readings")
       == "work has been climbing across 4 readings"
       and T._safe_statement("work has been climbing", "fb") == "work has been climbing")

    with _temp_store():
        N = "TrajCert"

        # ---- A. DIRECTION FROM CONTINUITY ---------------------------------------------------
        # Seed the meaning significance ledger DIRECTLY — trajectory owns no writer; meaning is the
        # real source it reads via meaning.snapshots(). _temp_store redirected meaning.STORE here, so
        # this lands in the temp dir, never the real .anima.
        seq = [
            [("work", 8.0, 8, 2), ("sleep", 7.0, 7, 2), ("reading", 4.0, 4, 1), ("exercise", 6.0, 6, 1)],
            [("work", 10.0, 12, 3), ("sleep", 6.0, 6, 2), ("reading", 4.1, 4, 1), ("exercise", 5.0, 5, 1)],
            [("work", 12.5, 17, 3), ("sleep", 5.0, 5, 2), ("reading", 3.9, 4, 1), ("exercise", 4.0, 4, 1)],
            [("work", 14.0, 22, 4), ("sleep", 4.0, 4, 2), ("reading", 4.0, 4, 1), ("exercise", 3.0, 3, 1)],
        ]
        lp = meaning.ledger_path(N)
        lp.parent.mkdir(parents=True, exist_ok=True)
        with open(lp, "a", encoding="utf-8") as f:
            for i, rows in enumerate(seq):
                f.write(json.dumps(_snapshot(i, rows)) + "\n")
        ck("A0: trajectory reads its input FROM the meaning continuity ledger (>=4 snapshots present)",
           len(meaning.snapshots(N)) == 4)

        read = T.trajectory(N)
        ck("A1: trajectory is ready once there are >= 2 snapshots", read["ready"] is True)
        ck("A2: it read the FULL snapshot sequence (continuity, not a single point)",
           read["n_snapshots"] == 4)
        by = {o["subject"]: o for o in read["objects"]}
        ck("A3: 'work' (rising significance) composes direction RISING",
           by.get("work", {}).get("direction") == T.RISING)
        ck("A4: 'sleep' (falling significance) composes direction FALLING",
           by.get("sleep", {}).get("direction") == T.FALLING)
        ck("A5: 'reading' (flat) composes direction STABLE — noise is not a trend",
           by.get("reading", {}).get("direction") == T.STABLE)
        ck("A6: EVERY object CITES the snapshot evidence it was built on (score_path + slope)",
           all(o["evidence"].get("score_path") and "slope_per_snapshot" in o["evidence"]
               and o["evidence"].get("score_deltas") for o in read["objects"]))
        ck("A7: every object's confidence is in (0, 0.9] — a trend is described, never certified",
           all(0.0 < o["confidence"] <= 0.9 for o in read["objects"]))

        # ---- B. DESCRIPTIVE COMPOSITE -------------------------------------------------------
        comp = read["composite"]
        ck("B1: a convergence read is produced (several threads moving together)",
           isinstance(comp, dict))
        ck("B2: it names the strain DIRECTION descriptively (sleep + work), not a condition",
           bool(comp) and "strain" in comp.get("statement", "").lower()
           and "sleep" in comp.get("subjects", []) and "work" in comp.get("subjects", []))
        ck("B3: the composite carries evidence + a real confidence",
           bool(comp) and comp.get("confidence", 0) > 0
           and comp.get("evidence", {}).get("convergence_count", 0) >= 2)
        ck("B4: the composite statement itself is diagnosis-free (clean-gate)",
           bool(comp) and T._is_clean(comp.get("statement", "")))

        # ---- C. THE NO-DIAGNOSIS WALL over EVERY generated line ------------------------------
        generated = []
        for o in read["objects"]:
            ln = T._line_for(o)
            if ln:
                generated.append(ln)
        if comp:
            generated.append(comp["statement"])
        block = T.render_trajectory(read)
        generated.append(T._items_of(block))
        ck("C1: NOT ONE generated line (subjects + composite + rendered items) trips a banned term",
           bool(generated) and all(T._is_clean(g) for g in generated))
        ck("C2: render produces a warm binding block that LEADS with the convergence line",
           bool(block.strip()) and "[CONVERGENCE]" in block)
        ck("C3: the render GUARDRAIL forbids diagnosis + prediction (the hard wall, stated)",
           "NOT a diagnosis" in block and "NOT a prediction" in block
           and "Never read the brackets" in block)
        ck("C4: the GENERATED items section contains NO banned term", T._is_clean(T._items_of(block)))

        # ---- D. THE SAME WALL IS THE LIVE CHAT-REPLY GATE -----------------------------------
        # mouth._diagnosis_terms() PREFERS trajectory.BANNED_TERMS — the wall trajectory builds IS the
        # wall enforced on every shipped reply.
        ck("D1: mouth._diagnosis_terms() IS trajectory.BANNED_TERMS (one source of truth)",
           tuple(mouth._diagnosis_terms()) == tuple(T.BANNED_TERMS))
        diag_reply = ("I'm really glad you told me about your week. It sounds like you're "
                      "burning out and you should see a therapist. I'm here with you either way.")
        stripped = mouth._strip_diagnosis_sentences(diag_reply)
        ck("D2: mouth._strip_diagnosis_sentences DROPS the diagnosis/referral sentence from a reply",
           "burning out" not in stripped.lower() and "see a therapist" not in stripped.lower())
        ck("D3: it keeps the honest, non-diagnostic rest of the reply (never empties a clean reply)",
           "glad you told me" in stripped.lower() and "here with you" in stripped.lower())
        # a realistic leaky reply: trajectory bracket tags slipped INLINE into warm sentences (the
        # exact shape render_trajectory emits). The scrub must excise the tags yet keep the words.
        leaky = ("[RISING] Work has been climbing for you lately. "
                 "[FALLING] Rest has been easing off. "
                 "[CONVERGENCE] A few things have been pulling the same direction.")
        scrubbed = mouth._strip_scaffold_leak(leaky)
        ck("D4: trajectory scaffold tags are scrubbed by mouth._strip_scaffold_leak, words kept (no leak)",
           all(t not in scrubbed for t in ("[TRAJECTORY]", "[RISING]", "[FALLING]",
                                           "[STABLE]", "[CONVERGENCE]"))
           and "climbing for you" in scrubbed and "easing off" in scrubbed)

        # ---- E. HONEST EMPTY / NEVER-FABRICATE ----------------------------------------------
        one = "TrajCertOne"
        lp1 = meaning.ledger_path(one)
        lp1.parent.mkdir(parents=True, exist_ok=True)
        with open(lp1, "a", encoding="utf-8") as f:
            f.write(json.dumps(_snapshot(0, [("work", 9.0, 9, 2)])) + "\n")
        one_read = T.trajectory(one)
        ck("E1: a SINGLE snapshot is NOT ready — one point has no direction (Observed > Assumed)",
           one_read["ready"] is False)
        ck("E2: it returns an honest reason and NO fabricated objects",
           "enough" in one_read["reason"].lower() and one_read["objects"] == [])
        ck("E3: render of a not-ready read is the empty string (nothing to bind)",
           T.render_trajectory(one_read) == "")
        empty = "TrajCertEmpty"
        empty_read = T.trajectory(empty)
        ck("E4: NO snapshots -> not ready, no objects, no composite (never invents a direction)",
           empty_read["ready"] is False and empty_read["objects"] == []
           and empty_read["composite"] is None)
        ck("E5: composite() of an empty life is None", T.composite(empty) is None)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nTRAJECTORY-ENGINE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
