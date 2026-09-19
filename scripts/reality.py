#!/usr/bin/env python3
"""VERA REALITY OBSERVATORY — "was the mind RIGHT?" (Phase 6 — the EPISTEMIC-loop dashboard).

The other observatories freeze a moment and ask what happened to it. scripts/mri.py watches a
single TURN cross eleven stages. scripts/experience.py scores a single FEELING.
scripts/evolution.py diffs the brain across CALENDAR TIME. This one renders the deepest loop a
thirty-year companion must hold — the one that turns a good memory into genuine LEARNING, and
does it as REASONING (not fortune-telling):

    observation -> HYPOTHESIS(es, COMPETING) -> prediction -> outcome -> SURPRISE -> learning
                                                                                  -> MODEL REVISION

It reads the per-creature reality LEDGER (anima/reality.py) and renders:

  1. THE LOOP, per creature — the grounded HYPOTHESES (with the evidence they rest on); the
     HYPOTHESIS COMPETITIONS (the rival explanations a situation spawns, each weighted, and
     which one reality is FAVORING + why); the predictions and their status; and the RESOLVED
     loops where reality came back, the SURPRISE was computed, and (on a surprising outcome) a
     MODEL REVISION reweighted the competing hypotheses.

  2. THE CALIBRATION DASHBOARD — accuracy over RESOLVED predictions, overall and PER CATEGORY:
     which prediction KINDS Vera is reliable about and which she is not, a Brier-style
     calibration score (how well her stated confidence matched reality), the MEAN SURPRISE (how
     often reality blindsided the model), and how many MODEL REVISIONS the surprises triggered.

────────────────────────────────────────────────────────────────────────────────────────────
WHY HYPOTHESIS, NOT BELIEF  +  WHY COMPETITION  +  WHY SURPRISE
────────────────────────────────────────────────────────────────────────────────────────────
A BELIEF implies commitment + conflict-resolution this system does not yet have; it forms
HYPOTHESES — tagged, evidence-anchored, REVISABLE (they may one day GRADUATE to beliefs, not
built yet). A naive model spawns ONE explanation and treats it as truth; reality offers MANY,
so a situation tracks a SET of COMPETING hypotheses with prior confidences, and an outcome
ADJUDICATES them (supported strengthened, contradicted weakened, renormalised). SURPRISE — high
when confident-and-wrong or doubtful-and-right — is the gradient that DRIVES the learning: a
high-surprise outcome triggers a MODEL REVISION of the weights. Without surprise this is
scorekeeping; with it, it learns.

────────────────────────────────────────────────────────────────────────────────────────────
THE HONEST TIME-GATING NOTE  (stated up front, in the header, and in the report)
────────────────────────────────────────────────────────────────────────────────────────────
Real LEARNING accrues only as real OUTCOMES arrive over real CALENDAR TIME — the SAME wall as
longitudinal certification and the Evolution Observatory. You cannot score a future you have
not lived. So the deep calibration + surprise payoff DEEPENS ON ITS OWN as the calendar turns.

But the INSTRUMENT works NOW: the machinery — form / resolve / adjudicate / calibrate, including
COMPETITION, SURPRISE and MODEL REVISION — is live, and this observatory PROVES it end-to-end on
a SYNTHETIC time-series (Day-1 "my manager changed" -> COMPETING stress hypotheses + a
sleep-decline prediction from the leader with a ~14-day horizon; Day-14 "I've barely slept" ->
outcome adjudicates the competition + computes surprise), closing the loop with
prediction_correct=True and a calibration update. Build the lens today; it sharpens every night
you sleep her.

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
# RENDER — the human-readable EPISTEMIC-loop dashboard: the loop (hypotheses + competitions +
# predictions + resolved-with-surprise) + the calibration board. Reads ONLY anima/reality.py's
# loop()/calibrate(); every line passes the no-diagnosis gate.
# ===================================================================================

def _clean(s: str) -> str:
    """Run a line through reality.py's no-diagnosis clean-gate; substitute a neutral note if it
    ever trips (defence in depth — this is internal model-state, never a user-facing claim)."""
    return reality._safe_statement(s, "    (an internal model note)")


def _render_competition(comp: dict) -> list:
    """Render ONE hypothesis competition — the rival explanations, each weighted, and which one
    reality is FAVORING. The whole point of fix #2: reasoning, not one-shot fortune-telling."""
    out = []
    cands = comp.get("candidates") or {}
    leader = comp.get("leader")
    cat = comp.get("category", "?")
    n = len(cands)
    shape = "single candidate" if comp.get("single_candidate") or n == 1 else f"{n} competing"
    out.append(_clean(f"    [{cat}]  HYPOTHESIS COMPETITION ({shape})  —  reality is favoring: "
                      f"{leader or '(none yet)'}"))
    for key, v in sorted(cands.items(), key=lambda kv: -float(kv[1].get("weight", 0.0))):
        w = float(v.get("weight", 0.0))
        p = float(v.get("prior", w))
        bar = _weight_bar(w)
        arrow = "  ⟵ reality favors this" if key == leader else ""
        out.append(_clean(f"        - {key:<16} {bar} {w:.2f}  (prior {p:.2f})  "
                          f"{v.get('claim', '')}{arrow}"))
    return out


def _render_loop(data: dict) -> str:
    """The per-creature loop block: observation → hypotheses (competing) → predicted → happened
    → SURPRISE → learned → MODEL REVISION."""
    if not isinstance(data, dict):
        data = {}
    out = []
    out.append("─" * 88)
    out.append("THE LOOP — observation → hypotheses (competing) → predicted → happened → SURPRISE → learned")
    out.append("─" * 88)

    hyps = data.get("hypotheses", [])
    out.append(f"HYPOTHESES — grounded, REVISABLE inferences about the USER's world "
               f"(each cites its evidence): {len(hyps)}")
    if not hyps:
        out.append("    (none yet — a hypothesis forms only from a turn that carries REAL evidence)")
    for h in hyps[-10:]:
        ev = h.get("evidence", {}) or {}
        key = h.get("candidate_key")
        tag = f"{h.get('category')}/{key}" if key else f"{h.get('category')}"
        out.append(_clean(
            f"    • [{tag}]  {h.get('claim')}"
            f"   (conf {float(h.get('confidence', 0)):.2f})"))
        cite = f'"{str(ev.get("turn", ""))[:72]}"'
        if ev.get("world"):
            cite += f"   +{ev['world']}"
        out.append(f"        ↳ grounded in: {cite}")

    comps = data.get("competitions", [])
    out.append("")
    out.append(f"HYPOTHESIS COMPETITIONS — the RIVAL explanations reality is adjudicating: {len(comps)}")
    if not comps:
        out.append("    (none yet — a competition forms when a situation has more than one explanation)")
    for comp in comps[-6:]:
        out.extend(_render_competition(comp))

    preds = data.get("predictions", [])
    open_n = len(data.get("open", []))
    resolved = data.get("resolved", [])
    out.append("")
    out.append(f"PREDICTIONS — a leading hypothesis about a FUTURE outcome, with a horizon: {len(preds)}  "
               f"(open {open_n} · resolved {len(resolved)})")
    if not preds:
        out.append("    (none yet — a prediction forms only when a hypothesis implies a checkable future)")
    for p in preds[-8:]:
        status = str(p.get("status", reality.OPEN)).upper()
        out.append(_clean(
            f"    • [{p.get('category')}]  {p.get('claim')}"
            f"   (conf {float(p.get('confidence', 0)):.2f} · horizon {p.get('horizon_days')}d · {status})"))
        if status == "OPEN":
            out.append(f"        ⏳ waiting on reality — deadline ~{p.get('deadline', '?')}")

    out.append("")
    out.append("RESOLVED LOOPS — reality came back, SURPRISE was computed, the model was revised:")
    if not resolved:
        out.append("    (none yet — real learning accrues as real outcomes arrive over real")
        out.append("     calendar time; the machinery is live and waiting.)")
    for r in resolved:
        p = r.get("prediction", {}) or {}
        o = r.get("outcome", {}) or {}
        l = r.get("learning", {}) or {}
        mark = "✓ RIGHT" if l.get("prediction_correct") else "✗ WRONG"
        out.append(_clean(
            f"    {mark}  [{p.get('category')}]   SURPRISE {l.get('surprise')}"))
        out.append(_clean(
            f"        hypothesised (conf {l.get('predicted_confidence')})  →  "
            f"happened: \"{str(o.get('observed', ''))[:52]}\""))
        rev = r.get("revision")
        if rev is not None:
            sup = rev.get("supported")
            con = rev.get("contradicted") or []
            if sup:
                what = f"strengthened '{sup}'"
            elif con:
                what = "weakened " + ", ".join(repr(c) for c in con)
            else:
                what = "reweighted the field"
            out.append(_clean(
                f"        ↳ MODEL REVISION (high surprise): {what} — "
                f"weights {_compact(rev.get('before_weights'))} → {_compact(rev.get('after_weights'))}"))
        else:
            out.append("        ↳ low surprise — the outcome CONFIRMED the model (no major revision)")
    return "\n".join(out)


def _render_calibration(cal: dict) -> str:
    """The calibration dashboard: accuracy over time, reliable vs unreliable prediction kinds,
    the mean SURPRISE, and how many MODEL REVISIONS the surprises have triggered."""
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
    ms = cal.get("mean_surprise")
    out.append(f"              mean SURPRISE {ms:.3f}   ·   MODEL REVISIONS triggered: "
               f"{cal.get('revisions', 0)}   (high-surprise outcomes that moved the model)")
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
        if c.get("mean_surprise") is not None:
            line += f"   [surprise {c['mean_surprise']:.2f}]"
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


def _weight_bar(w, width: int = 10) -> str:
    """A tiny ASCII gauge for a competing-hypothesis weight in [0,1]."""
    if not isinstance(w, (int, float)):
        return " " * (width + 2)
    filled = int(round(max(0.0, min(1.0, w)) * width))
    return "▕" + "█" * filled + "·" * (width - filled) + "▏"


def _compact(weights, top: int = 3) -> str:
    """A compact 'k:0.62 k:0.21' fragment of the strongest weights, for the revision line."""
    if not isinstance(weights, dict) or not weights:
        return "{}"
    items = sorted(weights.items(), key=lambda kv: -float(kv[1]))[:top]
    return "{" + ", ".join(f"{k}:{float(v):.2f}" for k, v in items) + "}"


def render(report: dict) -> str:
    out = []
    out.append("=" * 88)
    out.append("VERA REALITY OBSERVATORY — was the mind RIGHT?")
    out.append("Memory + Experience = Knowledge:  hypotheses (competing) → prediction → outcome →")
    out.append("SURPRISE → learning → MODEL REVISION.  The loop that turns continuity into REASONING.")
    out.append("=" * 88)
    out.append("")
    out.append("HONEST TIME-GATING NOTE: real LEARNING accrues only as real OUTCOMES arrive over")
    out.append("real CALENDAR TIME — the SAME wall as longitudinal certification; you cannot score")
    out.append("a future you have not lived. The deep calibration + SURPRISE payoff DEEPENS ON ITS")
    out.append("OWN as the calendar turns. But the INSTRUMENT works NOW: the machinery (form/resolve/")
    out.append("adjudicate/calibrate — competition + surprise + model revision) is live, and this")
    out.append("report PROVES it on a synthetic Day-1 → Day-14 loop. Build the lens today.")
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
# the REAL form/resolve engine, hermetically, so the default invocation shows a real closed loop
# with a real adjudicated competition + a computed surprise.
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
        data = {"hypotheses": [], "competitions": [], "predictions": [], "resolved": [],
                "open": [], "revisions": [], "calibration": reality.calibrate("none")}
    return {
        "loop": data,
        "source_note": ("SYNTHETIC demo loop (Day-1 'my manager changed' spawns COMPETING stress "
                        "hypotheses → leader predicts sleep-decline → Day-14 'I've barely slept' "
                        "adjudicates the competition + computes surprise) driven through the real "
                        "form/resolve engine in a hermetic temp store. Run --real to render Vera's "
                        "ACTUAL reality ledger, read-only."),
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
            data = {"hypotheses": [], "competitions": [], "predictions": [], "resolved": [],
                    "open": [], "revisions": [], "calibration": reality.calibrate(name)}
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
# SELFTEST — PROVE the epistemic loop closes on a synthetic time-series, DETERMINISTICALLY, and
# that the synthetic-only / read-only guardrail holds (real .anima byte-unchanged). No model, no
# network.
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

    # === the LOOP CLOSED: COMPETING hypotheses + a prediction formed, then resolved correct ====
    ok("loop: Day-1 spawned COMPETING hypotheses + a future prediction",
       sum(1 for r in built_a["formed"] if r["kind"] == reality.HYPOTHESIS) >= 3
       and any(r["kind"] == reality.COMPETITION for r in built_a["formed"])
       and any(r["kind"] == reality.PREDICTION for r in built_a["formed"]))
    ok("loop: Day-14 resolved exactly one prediction", len(built_a["learnings"]) == 1)
    ok("LOOP CLOSES: prediction_correct=True (the mind was RIGHT on the synthetic series)",
       bool(built_a["learnings"]) and built_a["learnings"][0]["prediction_correct"] is True)

    # === COMPETING HYPOTHESES — rival explanations, weighted, adjudicated by reality ===========
    comp_b = built_a["competition_before"]
    comp_a = built_a["competition_after"]
    ok("COMPETING: the stress_risk situation offered rival explanations (>= 3 candidates)",
       comp_b is not None and len(comp_b["candidates"]) >= 3
       and {"manager_change", "recent_move", "family_visit"}.issubset(set(comp_b["candidates"])))
    ok("COMPETING: each candidate carried a PRIOR weight, normalised to sum ~1",
       comp_b is not None
       and abs(sum(v["weight"] for v in comp_b["candidates"].values()) - 1.0) < 1e-4)
    ok("COMPETING: manager_change led the competition before the outcome",
       comp_b is not None and comp_b["leader"] == "manager_change")
    ok("ADJUDICATED: the outcome STRENGTHENED the supported hypothesis (manager_change)",
       comp_a is not None
       and comp_a["candidates"]["manager_change"]["weight"]
       > comp_b["candidates"]["manager_change"]["weight"])
    ok("ADJUDICATED: the outcome WEAKENED a rival (recent_move)",
       comp_a is not None
       and comp_a["candidates"]["recent_move"]["weight"]
       < comp_b["candidates"]["recent_move"]["weight"])
    ok("ADJUDICATED: the re-weighted competition still sums to ~1 (renormalised)",
       comp_a is not None and abs(sum(v["weight"] for v in comp_a["candidates"].values()) - 1.0) < 1e-4)

    # === the assembled loop read carries hypothesised -> happened -> SURPRISE -> learned =======
    ok("loop read: one RESOLVED loop assembled (prediction→outcome→learning joined)",
       len(data_a["resolved"]) == 1
       and data_a["resolved"][0]["outcome"] is not None
       and data_a["resolved"][0]["prediction"]["status"] == reality.CONFIRMED)
    ok("loop read: the resolved prediction is the sleep_decline category",
       data_a["resolved"][0]["prediction"]["category"] == "sleep_decline")
    ok("loop read: the grounded hypotheses cite their evidence (the Day-1 turn)",
       any("manager" in str(h.get("evidence", {}).get("turn", "")).lower()
           for h in data_a["hypotheses"]))
    ok("loop read: SURPRISE was computed on the resolved learning",
       "surprise" in data_a["resolved"][0]["learning"]
       and 0.0 <= data_a["resolved"][0]["learning"]["surprise"] <= 1.0)

    # === CALIBRATION UPDATED: 1/1 correct on sleep_decline, + the surprise/revision telemetry ==
    cal = data_a["calibration"]
    ok("CALIBRATION UPDATES: overall 1 resolved, 1 correct, accuracy 1.0",
       cal["resolved"] == 1 and cal["correct"] == 1 and cal["accuracy"] == 1.0)
    ok("calibration: per-kind accuracy recorded for sleep_decline",
       cal["by_category"].get("sleep_decline", {}).get("accuracy") == 1.0)
    ok("calibration: a Brier score AND a mean SURPRISE are computed",
       isinstance(cal.get("brier"), float) and isinstance(cal.get("mean_surprise"), float))

    # === DETERMINISM: the loop's shape is identical across two independent hermetic runs =====
    def _shape(data):
        cal = data["calibration"]
        comp = (data["competitions"] or [{}])[0]
        return {
            "n_hypotheses": len(data["hypotheses"]),
            "n_competitions": len(data["competitions"]),
            "n_predictions": len(data["predictions"]),
            "n_resolved": len(data["resolved"]),
            "leader": comp.get("leader"),
            "candidate_keys": sorted((comp.get("candidates") or {}).keys()),
            "resolved_categories": sorted(r["prediction"]["category"] for r in data["resolved"]),
            "resolved_correct": sorted(r["learning"]["prediction_correct"] for r in data["resolved"]),
            "surprise": sorted(round(r["learning"]["surprise"], 4) for r in data["resolved"]),
            "accuracy": cal["accuracy"], "correct": cal["correct"], "resolved": cal["resolved"],
        }
    ok("DETERMINISM: two independent hermetic runs produce the same loop shape",
       json.dumps(_shape(data_a), sort_keys=True) == json.dumps(_shape(data_b), sort_keys=True))

    # === a CONFIDENT-WRONG case triggers a MODEL REVISION (the surprise-driven learning) =======
    with _temp_store():
        nm = f"{SYNTH}_{secrets.token_hex(3)}"
        f_cw = reality.form(nm, "my manager just changed", at=_DAY1)
        comp_cw = next((r for r in f_cw if r["kind"] == reality.COMPETITION), None)
        before_cw = {k: v["weight"] for k, v in comp_cw["candidates"].items()}
        l_cw = reality.resolve(nm, "actually I've been sleeping great, fully rested",
                               at=reality._add_days(_DAY1, 14))
        data_cw = reality.loop(nm)
        cal_cw = data_cw["calibration"]
        revs_cw = [r for r in data_cw["revisions"]]
        comp_cw_after = (data_cw["competitions"] or [{}])[0]
    ok("MODEL REVISION: a confident prediction proven WRONG is HIGH-surprise",
       bool(l_cw) and l_cw[0]["prediction_correct"] is False
       and l_cw[0]["surprise"] >= reality._SURPRISE_REVISION_AT)
    ok("MODEL REVISION: the high-surprise outcome triggered a MODEL REVISION",
       cal_cw["revisions"] == 1 and len(revs_cw) == 1 and revs_cw[0].get("major") is True)
    ok("MODEL REVISION: it recorded before_weights -> after_weights",
       "before_weights" in revs_cw[0] and "after_weights" in revs_cw[0])
    ok("MODEL REVISION: the contradicted leader was WEAKENED by the revision (weights shifted)",
       comp_cw_after.get("candidates", {}).get("manager_change", {}).get("weight", 1.0)
       < before_cw["manager_change"])

    # === a DOUBTFUL-RIGHT case is also HIGH-surprise (the symmetric gradient) ==================
    with _temp_store():
        nm = f"{SYNTH}_{secrets.token_hex(3)}"
        low_pred = {
            "kind": reality.PREDICTION, "id": reality._new_id("p"), "version": reality.VERSION,
            "category": "sleep_decline", "claim": "rest may be affected",
            "confidence": 0.11, "horizon_days": 14, "formed_at": _DAY1,
            "deadline": reality._add_days(_DAY1, 14), "status": reality.OPEN,
            "hypothesis_id": None, "competition_id": None,
            "evidence": {"turn": "synthetic doubtful prediction"}, "internal_only": True,
        }
        reality._append(nm, low_pred)
        l_dr = reality.resolve(nm, "honestly I've barely slept the last two weeks",
                               at=reality._add_days(_DAY1, 14))
    ok("SURPRISE (doubtful-right): a doubtful (0.11) prediction proven TRUE is HIGH-surprise",
       bool(l_dr) and l_dr[0]["prediction_correct"] is True
       and abs(l_dr[0]["surprise"] - 0.89) < 1e-6)

    # === RENDER: non-empty, names the loop stages + competition + surprise, no diagnosis ======
    rep = demo_report()
    txt = render(rep)
    ok("render: produces a non-empty dashboard", bool(txt.strip()))
    ok("render: names the epistemic loop stages (hypotheses → predicted → SURPRISE → learned)",
       "hypotheses" in txt.lower() and "predicted" in txt.lower()
       and "SURPRISE" in txt and "learned" in txt.lower())
    ok("render: shows the HYPOTHESES / COMPETITIONS / PREDICTIONS / RESOLVED LOOPS sections",
       "HYPOTHESES" in txt and "HYPOTHESIS COMPETITION" in txt
       and "PREDICTIONS" in txt and "RESOLVED LOOPS" in txt)
    ok("render: shows which hypothesis reality is FAVORING in the competition",
       "reality is favoring: manager_change" in txt)
    ok("render: shows the CALIBRATION dashboard with reliable/unreliable framing + surprise",
       "CALIBRATION" in txt and "reliable" in txt.lower() and "mean SURPRISE" in txt)
    ok("render: carries the honest TIME-GATING note",
       "CALENDAR TIME" in txt and "DEEPENS ON ITS" in txt)
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

    # === the RENAME: the dashboard speaks HYPOTHESES, never the old 'belief' vocabulary ========
    body = render_body(rep)
    ok("RENAME: the rendered body uses HYPOTHESIS/HYPOTHESES, not 'belief'",
       "HYPOTHES" in body.upper() and "belief" not in body.lower())

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
        description="VERA REALITY OBSERVATORY — the observation→hypotheses(competing)→prediction"
                    "→outcome→SURPRISE→learning→model-revision loop + the calibration dashboard "
                    "(was the mind RIGHT?).")
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
