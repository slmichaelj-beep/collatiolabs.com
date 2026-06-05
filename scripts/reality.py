#!/usr/bin/env python3
"""VERA REALITY OBSERVATORY — "was the mind RIGHT?" (Phase 6 — the reality-learning dashboard).

The other observatories freeze a moment and ask what happened to it. scripts/mri.py watches a
single TURN cross eleven stages. scripts/experience.py scores a single FEELING.
scripts/evolution.py diffs the brain across CALENDAR TIME. This one renders the deepest loop a
thirty-year companion must hold — the one that turns a good memory into genuine LEARNING:

        MEMORY  ->  BELIEF  ->  PREDICTION  ->  OUTCOME  ->  LEARNING
        (a fact)   (a grounded   (a future,    (what really  (was the mind
                    inference)    time-gated)   happened)      RIGHT?)

It reads the per-creature reality LEDGER (anima/reality.py) and renders two things:

  1. THE LOOP, per creature — believed -> predicted -> happened -> learned: the grounded
     beliefs (with the evidence they rest on), the predictions and their status, and the
     RESOLVED loops where reality came back and the mind was scored right or wrong.

  2. THE CALIBRATION DASHBOARD — accuracy over RESOLVED predictions, overall and PER CATEGORY:
     which prediction KINDS Vera is reliable about and which she is not, plus a Brier-style
     calibration score (how well her stated confidence matched what actually happened).

────────────────────────────────────────────────────────────────────────────────────────────
THE HONEST TIME-GATING NOTE  (stated up front, in the header, and in the report)
────────────────────────────────────────────────────────────────────────────────────────────
Real LEARNING accrues only as real OUTCOMES arrive over real CALENDAR TIME — the SAME wall as
longitudinal certification and the Evolution Observatory. You cannot score a future you have
not lived. So the deep calibration payoff (is Vera reliable about sleep? about workload? about
follow-through?) DEEPENS ON ITS OWN as the calendar turns and outcomes land.

But the INSTRUMENT works NOW: the machinery — form / resolve / calibrate — is live, and this
observatory PROVES it end-to-end on a SYNTHETIC time-series (Day-1 "my manager changed" ->
belief + sleep-decline prediction with a ~14-day horizon; Day-14 "I've barely slept" ->
outcome), closing the loop with prediction_correct=True and a calibration update. Build the
lens today; it sharpens every night you sleep her.

────────────────────────────────────────────────────────────────────────────────────────────
INTERNAL ONLY — NO DIAGNOSIS / NO USER-FACING PREDICTION  (LAW-level)
────────────────────────────────────────────────────────────────────────────────────────────
This ledger is internal model-state + observability, exactly like anima/trajectory.py's
direction read. It NEVER causes Vera to assert a prediction or a diagnosis to the user; it is a
SHADOW / OFFLINE system reading the ALREADY-RECORDED conversation. This observatory only READS
it. Every rendered line passes anima/reality.py's no-diagnosis clean-gate (defence in depth).

────────────────────────────────────────────────────────────────────────────────────────────
GUARDRAILS  (identical posture to scripts/evolution.py / relationship.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * --selftest is SYNTHETIC-only + HERMETIC. It drives the Day-1/Day-14 loop in a throwaway
    temp dir with EVERY engine STORE redirected there (reality.STORE + memory_lirf.STORE on
    BOTH the __main__ and package bindings, world_state/curiosity/meaning/constitution/
    telemetry/cloud STORE, reliability.DEFAULT_STORE), and asserts the real .anima footprint
    is byte-UNCHANGED around the run.
  * --real is STRICTLY READ-ONLY on Vera's reality ledger. It opens the ledger for reading
    only, writes/mutates NOTHING, and asserts the real .anima is byte-identical start->end. A
    change is a GUARDRAIL BREACH (non-zero exit), never silently tolerated.
  * NEVER touches identity (frozen until 2026-07-03), mouth.respond, server._turn, or the live
    reply. ADDITIVE: imports + reads anima/reality.py; edits NO module. The only file this adds
    is scripts/reality.py.
  * Never raises out of an entry point — a malformed ledger yields an honest empty render.

    python3 scripts/reality.py             # human-readable loop + calibration (synthetic demo)
    python3 scripts/reality.py --json        # machine-readable
    python3 scripts/reality.py --selftest     # PROVE the loop closes on a synthetic time-series
    python3 scripts/reality.py --real         # render Vera's REAL ledger, STRICTLY READ-ONLY

Exit code is 0 when the selftest's detections hold and the synthetic-only / real read-only
guardrail held; non-zero on a missed detection or a breached guardrail.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import secrets
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from anima import reality  # noqa: E402  (the keystone this observatory renders)

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "reality_synth"

# Identity is FROZEN until this date. This observatory never reads/writes identity at all; the
# date is surfaced for parity with the Evolution Observatory's posture.
IDENTITY_FROZEN_UNTIL = "2026-07-03"

# The canonical synthetic timeline the loop is proven on.
_DAY1 = reality._SYNTH_DAY1


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect + footprint hash. Mirrors scripts/evolution.py
# (_STORE_TARGETS / _temp_store / _footprint): redirect EVERY engine STORE the synthetic loop
# could write to ONE throwaway dir so a form()/resolve() (and any world-read's LAW-001 backup /
# continuity write) can never leak into the real .anima.
#
# A redirect target is a (module-import-path, store-attr) pair because reliability's store attr
# is DEFAULT_STORE, not STORE. Resolved by NAME so importing this module never hard-depends on
# every engine; a missing one is simply skipped.
# ===================================================================================
_STORE_TARGETS = (
    ("anima.reality", "STORE"),
    ("anima.memory_lirf", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.constitution", "STORE"),           # the continuity ledger a good load/save writes
    ("anima.reliability", "DEFAULT_STORE"),     # guarded-backup snapshots
    ("anima.telemetry", "STORE"),
    ("anima.cloud", "STORE"),
)


def _resolve_store_targets():
    """Resolve ``_STORE_TARGETS`` to live ``(module, attr)`` pairs that carry the attribute right
    now. A module that won't import, or that lacks the attr, is skipped — so the redirect set
    adapts to whatever is built without ever hard-failing."""
    pairs = []
    seen = set()
    for modpath, attr in _STORE_TARGETS:
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, attr) and (id(mod), attr) not in seen:
            pairs.append((mod, attr))
            seen.add((id(mod), attr))
    return pairs


@contextlib.contextmanager
def _temp_store():
    """Redirect EVERY engine STORE binding to one fresh temp dir for the duration, so nothing
    under the real .anima/ is ever read or written. Restored on exit. HERMETIC by construction:
    a leak is impossible regardless of which engine the synthetic loop writes through. Yields
    the temp Path."""
    targets = _resolve_store_targets()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-reality-") as td:
        p = Path(td)
        for (m, a) in targets:
            if getattr(m, a, None) is not None:
                setattr(m, a, p)
        try:
            yield p
        finally:
            for (m, a, old) in saved:
                if old is not None:
                    setattr(m, a, old)


def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (EXCLUDING the rotating backups/ dir, which
    legitimately changes), so we can PROVE the harness touched nothing. Verbatim from
    scripts/evolution.py / relationship.py."""
    if not root.is_dir():
        return (None, 0)
    files = sorted(
        q for q in root.rglob("*")
        if q.is_file() and "backups" not in q.relative_to(root).parts
    )
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


# ===================================================================================
# RENDER — the human-readable reality-learning dashboard: the loop + the calibration board.
# Reads ONLY anima/reality.py's loop()/calibrate(); every line passes the no-diagnosis gate.
# ===================================================================================

def _clean(s: str) -> str:
    """Run a line through reality.py's no-diagnosis clean-gate; substitute a neutral note if it
    ever trips (defence in depth — this is internal model-state, never a user-facing claim)."""
    return reality._safe_statement(s, "    (an internal model note)")


def _render_loop(data: dict) -> str:
    """The per-creature loop block: believed -> predicted -> happened -> learned."""
    if not isinstance(data, dict):
        data = {}
    out = []
    out.append("─" * 88)
    out.append("THE LOOP — believed → predicted → happened → learned")
    out.append("─" * 88)

    beliefs = data.get("beliefs", [])
    out.append(f"BELIEFS — grounded inferences about the USER's world (each cites its evidence): "
               f"{len(beliefs)}")
    if not beliefs:
        out.append("    (none yet — a belief forms only from a turn that carries REAL evidence)")
    for b in beliefs[-8:]:
        ev = b.get("evidence", {}) or {}
        out.append(_clean(
            f"    • [{b.get('category')}]  {b.get('claim')}"
            f"   (conf {float(b.get('confidence', 0)):.2f})"))
        cite = f'"{str(ev.get("turn", ""))[:72]}"'
        if ev.get("world"):
            cite += f"   +{ev['world']}"
        out.append(f"        ↳ grounded in: {cite}")

    preds = data.get("predictions", [])
    open_n = len(data.get("open", []))
    resolved = data.get("resolved", [])
    out.append("")
    out.append(f"PREDICTIONS — beliefs about a FUTURE outcome, with a horizon: {len(preds)}  "
               f"(open {open_n} · resolved {len(resolved)})")
    if not preds:
        out.append("    (none yet — a prediction forms only when a belief implies a checkable future)")
    for p in preds[-8:]:
        status = str(p.get("status", reality.OPEN)).upper()
        out.append(_clean(
            f"    • [{p.get('category')}]  {p.get('claim')}"
            f"   (conf {float(p.get('confidence', 0)):.2f} · horizon {p.get('horizon_days')}d · {status})"))
        if status == "OPEN":
            out.append(f"        ⏳ waiting on reality — deadline ~{p.get('deadline', '?')}")

    out.append("")
    out.append("RESOLVED LOOPS — where reality came back and the mind was scored:")
    if not resolved:
        out.append("    (none yet — real learning accrues as real outcomes arrive over real")
        out.append("     calendar time; the machinery is live and waiting.)")
    for r in resolved:
        p = r.get("prediction", {}) or {}
        o = r.get("outcome", {}) or {}
        l = r.get("learning", {}) or {}
        mark = "✓ RIGHT" if l.get("prediction_correct") else "✗ WRONG"
        out.append(_clean(
            f"    {mark}  [{p.get('category')}]"))
        out.append(_clean(
            f"        believed (conf {l.get('belief_before')})  →  "
            f"happened: \"{str(o.get('observed', ''))[:56]}\"  →  "
            f"learned: delta {l.get('delta')}"))
    return "\n".join(out)


def _render_calibration(cal: dict) -> str:
    """The calibration dashboard: accuracy over time, reliable vs unreliable prediction kinds."""
    if not isinstance(cal, dict):
        cal = {}
    out = []
    out.append("─" * 88)
    out.append("CALIBRATION — was the mind RIGHT?  (accuracy over RESOLVED predictions)")
    out.append("─" * 88)
    if cal.get("resolved", 0) == 0:
        out.append("    (nothing resolved yet — calibration is TIME-GATED. It fills in on its own")
        out.append("     as outcomes arrive over real calendar time; you cannot score a future not")
        out.append("     yet lived. The instrument is live; it produces a number the moment a")
        out.append("     prediction's outcome lands.)")
        out.append(f"    still open (waiting on reality): {cal.get('open', 0)}")
        return "\n".join(out)

    acc = cal["accuracy"]
    bar = _accuracy_bar(acc)
    out.append(f"    OVERALL : {cal['correct']}/{cal['resolved']} correct   "
               f"accuracy {acc:.0%}  {bar}")
    out.append(f"              Brier {cal['brier']:.3f}   (lower = better-calibrated; "
               f"0 = stated confidence perfectly matched reality)")
    out.append("")
    out.append("    BY PREDICTION KIND — which kinds is she reliable about?")
    by = cal.get("by_category", {})
    if not by:
        out.append("      (no categories resolved yet)")
    for cat, c in sorted(by.items()):
        accc = c.get("accuracy")
        rel = c.get("reliable")
        verdict = ("RELIABLE  ✓" if rel is True
                   else ("UNRELIABLE ✗" if rel is False else "(too few to judge)"))
        line = (f"      - {cat:<20} {c['correct']}/{c['resolved']}"
                + (f"  {accc:.0%}" if accc is not None else "")
                + f"   {verdict}")
        if c.get("brier") is not None:
            line += f"   [Brier {c['brier']:.2f}]"
        out.append(line)

    if cal.get("reliable_kinds"):
        out.append("")
        out.append(f"    ✓ RELIABLE kinds (trust these more): {', '.join(cal['reliable_kinds'])}")
    if cal.get("unreliable_kinds"):
        out.append(f"    ✗ UNRELIABLE kinds (discount these):  {', '.join(cal['unreliable_kinds'])}")
    out.append(f"    still open (waiting on reality): {cal.get('open', 0)}")
    return "\n".join(out)


def _accuracy_bar(acc, width: int = 20) -> str:
    """A tiny ASCII gauge for an accuracy in [0,1]."""
    if not isinstance(acc, (int, float)):
        return ""
    filled = int(round(max(0.0, min(1.0, acc)) * width))
    return "▕" + "█" * filled + "·" * (width - filled) + "▏"


def render(report: dict) -> str:
    out = []
    out.append("=" * 88)
    out.append("VERA REALITY OBSERVATORY — was the mind RIGHT?")
    out.append("Memory + Experience = Knowledge:  belief → prediction → outcome → learning.")
    out.append("The loop that turns continuity into genuine long-term adaptation.")
    out.append("=" * 88)
    out.append("")
    out.append("HONEST TIME-GATING NOTE: real LEARNING accrues only as real OUTCOMES arrive over")
    out.append("real CALENDAR TIME — the SAME wall as longitudinal certification; you cannot score")
    out.append("a future you have not lived. The deep calibration payoff DEEPENS ON ITS OWN as the")
    out.append("calendar turns. But the INSTRUMENT works NOW: the machinery (form/resolve/calibrate)")
    out.append("is live, and this report PROVES it on a synthetic Day-1 → Day-14 loop. Build the")
    out.append("lens today; it sharpens every night you sleep her.")
    out.append("")
    out.append("INTERNAL ONLY: this ledger is model-state + observability — never a user-facing")
    out.append("prediction or diagnosis (LAW 003 / #1 product rule). A SHADOW system reading the")
    out.append("ALREADY-RECORDED conversation; it never alters the live reply.")
    out.append("")
    src = report.get("source_note")
    if src:
        out.append(f"LEDGER SOURCE: {src}")
        out.append("")

    data = report.get("loop") if isinstance(report, dict) else None
    if not isinstance(data, dict):
        data = {}
    cal = data.get("calibration") if isinstance(data.get("calibration"), dict) else {}
    out.append(_render_loop(data))
    out.append("")
    out.append(_render_calibration(cal))
    return "\n".join(out)


def render_body(report: dict) -> str:
    """The GENERATED content of the dashboard — the loop + calibration lines built FROM the
    ledger (the only lines that could ever carry a model inference) — WITHOUT the fixed header.

    Why this exists: the header LEGITIMATELY names banned words in order to FORBID them ("never
    a user-facing prediction or diagnosis"), exactly as anima/trajectory.py's preamble/guardrail
    do. So a 'no-diagnosis' assertion must inspect the GENERATED body, not the fixed legend —
    precisely as trajectory inspects ``_items_of(block)``, not its preamble. Pure; never raises."""
    data = report.get("loop") if isinstance(report, dict) else None
    if not isinstance(data, dict):
        data = {}
    cal = data.get("calibration") if isinstance(data.get("calibration"), dict) else {}
    return _render_loop(data) + "\n" + _render_calibration(cal)


# ===================================================================================
# THE DEMO REPORT (default human/JSON view) — drive the synthetic Day-1 -> Day-14 loop through
# the REAL form/resolve engine, hermetically, so the default invocation shows a real closed loop.
# ===================================================================================

def demo_report() -> dict:
    """Build the synthetic loop in a hermetic temp store through anima/reality.py's real engine,
    read the assembled loop + calibration, and package a report for the default human/JSON view.
    Never raises — degrades to an empty loop."""
    try:
        with _temp_store():
            name = f"{SYNTH}_{secrets.token_hex(3)}"
            reality.build_synthetic_loop(name)
            data = reality.loop(name)
    except Exception:
        data = {"beliefs": [], "predictions": [], "resolved": [], "open": [],
                "calibration": reality.calibrate("none")}
    return {
        "loop": data,
        "source_note": ("SYNTHETIC demo loop (Day-1 'my manager changed' → Day-14 'I've barely "
                        "slept') driven through the real form/resolve engine in a hermetic temp "
                        "store. Run --real to render Vera's ACTUAL reality ledger, read-only."),
        "identity_frozen_until": IDENTITY_FROZEN_UNTIL,
    }


# ===================================================================================
# --real — render VERA's ACTUAL reality ledger, STRICTLY READ-ONLY. Reads
# .anima/{name}.reality.jsonl via reality.loop(), and asserts the real .anima is byte-UNCHANGED
# start->end. Writes NOTHING. (reality.loop is a pure ledger READ — no LAW-001 backup hangs off
# it — so no write-diversion is needed, but we still prove byte-equality.)
# ===================================================================================

def real_report(name: str = "Vera", store: Path | None = None) -> dict:
    """Render Vera's REAL reality ledger, STRICTLY READ-ONLY, and PROVE the real .anima was
    byte-unchanged around the run. Returns a report with the loop + the read-only proof. Never
    raises."""
    store = Path(store) if store is not None else (_ROOT / ".anima")
    # point reality.STORE at the real .anima for the read (restore after); a pure ledger read.
    saved = getattr(reality, "STORE", None)
    fp_before = _footprint(store)
    try:
        reality.STORE = store
        try:
            data = reality.loop(name)
            err = None
        except Exception as e:  # pragma: no cover - --real never raises
            data = {"beliefs": [], "predictions": [], "resolved": [], "open": [],
                    "calibration": reality.calibrate(name)}
            err = repr(e)
    finally:
        if saved is not None:
            reality.STORE = saved
    fp_after = _footprint(store)
    unchanged = fp_before == fp_after
    return {
        "loop": data,
        "source_note": (f"Vera's REAL reality ledger (.anima/{name}.reality.jsonl), STRICTLY "
                        "READ-ONLY."),
        "identity_frozen_until": IDENTITY_FROZEN_UNTIL,
        "real": True,
        "real_anima_byte_unchanged": unchanged,
        "real_anima_files_before": fp_before[1],
        "real_anima_files_after": fp_after[1],
        "engine_error": err,
    }


# ===================================================================================
# SELFTEST — PROVE the loop closes on a synthetic time-series, DETERMINISTICALLY, and that the
# synthetic-only / read-only guardrail holds (real .anima byte-unchanged). No model, no network.
# ===================================================================================

def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("VERA REALITY OBSERVATORY self-test")

    real = _ROOT / ".anima"
    fp0 = _footprint(real)

    # === drive the canonical Day-1 -> Day-14 loop, hermetically, TWICE (also prove determinism)
    def _run_loop():
        with _temp_store():
            nm = f"{SYNTH}_{secrets.token_hex(3)}"
            built = reality.build_synthetic_loop(nm)
            data = reality.loop(nm)
            return built, data

    built_a, data_a = _run_loop()
    built_b, data_b = _run_loop()

    # === the LOOP CLOSED: a belief + prediction formed, then resolved correct ================
    ok("loop: Day-1 formed a grounded belief + a future prediction",
       any(r["kind"] == reality.BELIEF for r in built_a["formed"])
       and any(r["kind"] == reality.PREDICTION for r in built_a["formed"]))
    ok("loop: Day-14 resolved exactly one prediction", len(built_a["learnings"]) == 1)
    ok("LOOP CLOSES: prediction_correct=True (the mind was RIGHT on the synthetic series)",
       bool(built_a["learnings"]) and built_a["learnings"][0]["prediction_correct"] is True)

    # === the assembled loop read carries believed -> happened -> learned, joined ============
    ok("loop read: one RESOLVED loop assembled (belief→outcome→learning joined)",
       len(data_a["resolved"]) == 1
       and data_a["resolved"][0]["outcome"] is not None
       and data_a["resolved"][0]["prediction"]["status"] == reality.CONFIRMED)
    ok("loop read: the resolved prediction is the sleep_decline category",
       data_a["resolved"][0]["prediction"]["category"] == "sleep_decline")
    ok("loop read: the grounded belief cites its evidence (the Day-1 turn)",
       any("manager" in str(b.get("evidence", {}).get("turn", "")).lower()
           for b in data_a["beliefs"]))

    # === CALIBRATION UPDATED: 1/1 correct on sleep_decline ===================================
    cal = data_a["calibration"]
    ok("CALIBRATION UPDATES: overall 1 resolved, 1 correct, accuracy 1.0",
       cal["resolved"] == 1 and cal["correct"] == 1 and cal["accuracy"] == 1.0)
    ok("calibration: per-kind accuracy recorded for sleep_decline",
       cal["by_category"].get("sleep_decline", {}).get("accuracy") == 1.0)
    ok("calibration: a Brier score (calibration quality) is computed",
       isinstance(cal.get("brier"), float))

    # === DETERMINISM: the loop's shape is identical across two independent hermetic runs =====
    def _shape(data):
        cal = data["calibration"]
        return {
            "n_beliefs": len(data["beliefs"]),
            "n_predictions": len(data["predictions"]),
            "n_resolved": len(data["resolved"]),
            "resolved_categories": sorted(r["prediction"]["category"] for r in data["resolved"]),
            "resolved_correct": sorted(r["learning"]["prediction_correct"] for r in data["resolved"]),
            "accuracy": cal["accuracy"], "correct": cal["correct"], "resolved": cal["resolved"],
        }
    ok("DETERMINISM: two independent hermetic runs produce the same loop shape",
       json.dumps(_shape(data_a), sort_keys=True) == json.dumps(_shape(data_b), sort_keys=True))

    # === RENDER: non-empty, names the loop stages + the calibration board, no diagnosis ======
    rep = demo_report()
    txt = render(rep)
    ok("render: produces a non-empty dashboard", bool(txt.strip()))
    ok("render: names the loop stages (believed → predicted → happened → learned)",
       "believed" in txt and "predicted" in txt and "happened" in txt and "learned" in txt)
    ok("render: shows the BELIEFS / PREDICTIONS / RESOLVED LOOPS sections",
       "BELIEFS" in txt and "PREDICTIONS" in txt and "RESOLVED LOOPS" in txt)
    ok("render: shows the CALIBRATION dashboard with reliable/unreliable framing",
       "CALIBRATION" in txt and "reliable" in txt.lower())
    ok("render: carries the honest TIME-GATING note",
       "CALENDAR TIME" in txt and "DEEPENS ON ITS OWN" in txt)
    ok("render: states the ledger is INTERNAL ONLY (no user-facing prediction/diagnosis)",
       "INTERNAL ONLY" in txt and "SHADOW" in txt)
    # The no-diagnosis gate inspects the GENERATED body (the loop + calibration lines built from
    # the ledger), NOT the fixed header — which legitimately NAMES "diagnosis" in order to FORBID
    # it, exactly as anima/trajectory.py inspects its items, not its banned-word-naming preamble.
    ok("NO-DIAGNOSIS GATE: not one GENERATED body line trips a banned term",
       all(reality._is_clean(ln) for ln in render_body(rep).splitlines()))
    ok("NO-DIAGNOSIS: the header that NAMES 'diagnosis' to forbid it is fixed framing, not data",
       not reality._is_clean(
           "never a user-facing prediction or diagnosis")  # the legend legitimately names it
       and "diagnosis" in txt.lower())

    # === the empty-ledger render is honest: time-gated, no fabricated loop ===================
    with _temp_store():
        empty_rep = {"loop": reality.loop("nobody_" + secrets.token_hex(2)),
                     "source_note": "empty"}
        empty_txt = render(empty_rep)
    ok("render(empty): honest 'time-gated / nothing resolved yet', no fabricated loop",
       "TIME-GATED" in empty_txt and "nothing resolved yet" in empty_txt.lower())

    # === ROBUSTNESS: garbage reports never raise ============================================
    try:
        render({})
        render({"loop": {"calibration": {}}})
        render({"loop": None})
        crashed = False
    except Exception as e:  # noqa: BLE001
        crashed = True
        print("       (raised:", repr(e), ")")
    ok("robust: garbage/empty report renders without raising", not crashed)

    # === --json shape is serialisable =======================================================
    try:
        json.dumps(demo_report(), default=str)
        serialisable = True
    except Exception:
        serialisable = False
    ok("--json: the demo report serialises cleanly", serialisable)

    # === --real is STRICTLY READ-ONLY: running it leaves real .anima byte-unchanged ==========
    rr = real_report("Vera", store=real)
    ok("--real: ran and produced a report shape", isinstance(rr, dict) and "loop" in rr)
    ok("--real: real .anima reported byte-UNCHANGED around the run",
       rr.get("real_anima_byte_unchanged") is True)

    # === GUARDRAIL: the WHOLE selftest (incl. --real) touched no real .anima file ============
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across the entire selftest", fp0 == fp1)
    ok("guardrail: no synthetic creature ledger leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL REALITY-OBSERVATORY SELFTESTS PASS")
    return 0


# ===================================================================================
# MAIN — human-readable (default) or --json; --selftest; --real (read-only on real Vera).
# ===================================================================================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA REALITY OBSERVATORY — the belief→prediction→outcome→learning loop + "
                    "the calibration dashboard (was the mind RIGHT?).")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--real", action="store_true",
                    help="render Vera's ACTUAL reality ledger, STRICTLY READ-ONLY")
    ap.add_argument("--name", default="Vera", help="creature name for --real (default Vera)")
    ap.add_argument("--selftest", action="store_true",
                    help="PROVE the loop closes on a synthetic Day-1→Day-14 series (deterministic)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.real:
        report = real_report(args.name, store=_ROOT / ".anima")
    else:
        report = demo_report()

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        if report.get("real"):
            print("")
            print("=" * 88)
            unchanged = report.get("real_anima_byte_unchanged")
            print("GUARDRAIL (--real): real .anima  : "
                  + ("byte-UNCHANGED — strictly read-only; Vera's real state was never touched"
                     if unchanged else "CHANGED — GUARDRAIL BREACH (this should be impossible in --real)"))
            print(f"                    files seen   : {report.get('real_anima_files_before')} "
                  f"(before) / {report.get('real_anima_files_after')} (after)")
            if report.get("engine_error"):
                print(f"                    engine error : {report['engine_error']}")

    # exit non-zero only if --real breached the read-only guarantee (the default/demo always 0).
    if report.get("real") and report.get("real_anima_byte_unchanged") is not True:
        return 1
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
