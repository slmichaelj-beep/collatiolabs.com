#!/usr/bin/env python3
"""CURIOSITY-QUALITY metrics — measure DISCOVERY, not just question COUNT.

    Questions can become noise; discoveries become continuity.

The Experience certification measures whether Vera turns back to the user (curiosity ~67%
there is a "does this reply ask about THEM" count). But a COUNT of questions is the wrong
yardstick for the curiosity ENGINE (anima/curiosity.py): a companion who asks ten questions
and learns nothing is not curious, she is noisy. The thing that actually compounds into a
30-year relationship is the question that BECAME KNOWLEDGE — the gap she surfaced that is
now a confident fact she will never have to ask again (ANIMA LAW 002: never make the same
discovery twice). That is a DISCOVERY. This tool measures the DISCOVERY RATE.

It sits, READ-ONLY, on the exact same two stores the curiosity engine does, and asks one
question of a creature:

    of every gap she ASKED about (the append-only Asked Ledger
    `.anima/{name}.curiosity.jsonl` — `curiosity.mark_asked` / `curiosity.asked_keys`),
    how many are now a confident KNOWN fact in the LIRF ledger
    (`memory_lirf` — a row at/above the [KNOWN] confidence floor)?

    ASKED          — total gaps surfaced as questions (len of the Asked Ledger's keys).
    DISCOVERED     — asked gaps whose slot/entity is now a confident KNOWN LIRF fact
                     (the question led to a learned fact).
    STILL-OPEN     — asked, but not yet learned (a fair question still hanging).
    DISCOVERY_RATE = discovered / asked   (in [0,1]; 1.0 when nothing was asked).

The mapping from an asked gap back to "is it known now?" reuses the engine's own wiring so
it can never drift from what the engine writes:
  * a TAXONOMY-slot gap (slot "birthday", "lives", …) maps to its canonical LIRF trait via
    `curiosity._SLOT_TRAIT`; it is DISCOVERED iff that trait is now a confident KNOWN row
    for SELF (the SAME `curiosity._is_known_row` bar that SUPPRESSES the gap in the first
    place — so "discovered" here means exactly "the engine would no longer ask it").
  * a SUSPECTED RELATIONSHIP gap (slot "relationship:<entity>", e.g. the canonical "Mike")
    is DISCOVERED iff that entity is now a KNOWN relationship NAME in the ledger
    (`curiosity._known_relation_names` — partner=Mike, mother=Carol, …): she has learned
    who they are, so Law 002 drops the gap forever.

Why this is the right metric and COUNT is not: the battery below seeds ONE synthetic
creature, simulates asking N gaps, then "answers" some of them (captures the facts) and
shows the rate MOVES as answers land — "asked 10 / learned 8" scores 0.80 (good, she's
actually getting to know you) while "asked 10 / learned 1" scores 0.10 (noise, she's
asking into the void). A pure count cannot tell those two creatures apart; discovery_rate
puts daylight between them.

GUARDRAILS (identical discipline to scripts/conservation.py / scripts/test_continuity.py):
  * DETERMINISTIC + OFFLINE. No model, no network. (The curiosity engine's model-refine
    pass and LIRF's Tier-B are never invoked.)
  * SYNTHETIC creatures + TEMPORARY stores ONLY. Every engine's module-level STORE is
    redirected to a TemporaryDirectory for the run (the test_continuity.py pattern), and
    the run ASSERTS the real .anima footprint is byte-unchanged start->end. It NEVER reads
    or writes a real Vera.* file.
  * ADDITIVE + READ-ONLY on the engines. It imports and CALLS them; it edits no module, no
    test, and not certify.py / experience.py.
  * Never raises out of the entry points — a malformed creature yields an honest empty/zero
    report (rate 1.0: nothing asked -> nothing un-discovered), not a traceback.

    python3 scripts/curiosity_quality.py            # human-readable report + battery
    python3 scripts/curiosity_quality.py --json     # machine-readable
    python3 scripts/curiosity_quality.py --selftest  # prove the metric discriminates

Exit code is 0 (this is a MEASUREMENT tool — a low discovery rate is the truth being
reported, not a failure). A broken guardrail (the real .anima footprint changed, or an
engine raised inside the harness) exits non-zero.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from anima import curiosity                  # noqa: E402  (the Asked Ledger + gap shape + bars)
from anima import memory_lirf                # noqa: E402  (the LIRF facts = what is now KNOWN)

# A synthetic-only sentinel name so nothing here can ever collide with a real creature.
SYNTH = "cq_synth"


# ===================================================================================
# GUARDRAIL — temp-store redirect (verbatim from test_continuity.py / conservation.py) +
# a footprint hash. BOTH engines' STORE must be redirected: curiosity writes the Asked
# Ledger to curiosity.STORE and reads LIRF facts via memory_lirf.Facts (memory_lirf.STORE),
# so the synthetic creature is only fully isolated when both point at the throwaway dir.
# ===================================================================================
@contextlib.contextmanager
def _temp_store(*modules):
    """Redirect each module's module-level STORE to a fresh temp dir for the duration, so
    nothing under the real .anima/ is ever read or written. Restored on exit."""
    saved = [(m, getattr(m, "STORE", None)) for m in modules]
    with tempfile.TemporaryDirectory(prefix="anima-curiosity-quality-") as td:
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


def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir,
    which legitimately changes) so we can PROVE the harness touched nothing."""
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
# THE MAPPING: an ASKED gap-key -> "is it a confident KNOWN fact now?"
# Reuses the curiosity engine's OWN constants/predicates so "discovered" can never drift
# from what the engine treats as KNOWN (the bar that suppresses the gap forever, Law 002).
# ===================================================================================
def _known_trait_rows(name: str) -> dict:
    """Map canonical_trait -> active LIRF row for SELF, via the engine's own helper so the
    salience/active rules match exactly. Read-only; tolerates a missing/empty ledger ({})."""
    try:
        facts = memory_lirf.Facts.load(name)
    except Exception:
        return {}
    try:
        return curiosity._known_traits(facts)
    except Exception:
        return {}


def _known_relation_name_set(known_rows: dict) -> set:
    """The set of person-NAMES already KNOWN by relationship (partner=Mike, mother=Carol …),
    normalised, via the engine's own `_known_relation_names`. Used to decide whether a
    SUSPECTED relationship gap ("relationship:mike") has since been discovered."""
    try:
        return curiosity._known_relation_names(known_rows)
    except Exception:
        return set()


def _gap_key_discovered(gap_key: str, known_rows: dict, known_names: set) -> bool:
    """Is this ASKED gap-key now a confident KNOWN fact? The single discovery predicate.

    A gap-key is the engine's stable slot identity (`curiosity._gap_key`): either a taxonomy
    slot ("birthday", "lives", "favorite_food", …) or a relationship slug
    ("relationship:<entity>"). It is DISCOVERED iff:

      * RELATIONSHIP gap ("relationship:<entity>"): <entity> is now a KNOWN relationship
        name in the ledger (she has learned who they are -> Law 002 drops the gap); OR
      * TAXONOMY gap (any other slot): its canonical LIRF trait (curiosity._SLOT_TRAIT, the
        SAME slug the engine checks) is now a CONFIDENT KNOWN row for SELF
        (curiosity._is_known_row -> active, >= the [KNOWN] floor, not needs_reconfirm).

    Pure; never raises (an unrecognised/garbage key is simply 'not discovered')."""
    if not gap_key:
        return False
    key = gap_key.strip().lower()

    # relationship gap: discovered when the entity is now a known relationship name.
    if key.startswith("relationship:"):
        ent = key.split(":", 1)[1]
        # the slug joins tokens with "_"; known-name set is space/normalised — fold both.
        ent_norm = curiosity._norm_node(ent.replace("_", " "))
        return bool(ent_norm) and ent_norm in known_names

    # taxonomy-slot gap: discovered when its canonical trait is a confident KNOWN row.
    trait = curiosity._SLOT_TRAIT.get(key)
    if not trait:
        # a malformed gap-key the engine fell back to ("category:trait") — try the tail as a
        # trait so an oddly-keyed-but-real fact still counts; else not discovered.
        trait = key.split(":", 1)[-1]
    ctrait = curiosity.canon_trait(trait)
    row = known_rows.get(ctrait)
    try:
        return curiosity._is_known_row(row)
    except Exception:
        return False


# ===================================================================================
# THE METRIC — one creature's curiosity-quality accounting.
# ===================================================================================
def quality_report(name: str) -> dict:
    """The CURIOSITY-QUALITY report for ONE creature. Read-only on both stores.

        {
          "name":           the creature,
          "asked":          [ {gap_key, discovered: bool}, … ],   # every asked gap, classed
          "asked_count":    int,                                   # ASKED
          "discovered":     [ gap_key, … ],   # asked AND now a confident KNOWN fact
          "still_open":     [ gap_key, … ],   # asked, not yet learned
          "discovered_count": int,            # DISCOVERED
          "still_open_count": int,            # STILL-OPEN
          "discovery_rate": discovered / asked   (1.0 when asked == 0 — vacuously perfect),
        }

    Deterministic, offline, read-only. Never raises: a creature with no Asked Ledger yields
    asked_count 0 and rate 1.0 (nothing asked -> nothing un-discovered)."""
    try:
        asked = sorted(curiosity.asked_keys(name))
    except Exception:
        asked = []

    known_rows = _known_trait_rows(name)
    known_names = _known_relation_name_set(known_rows)

    classed = []
    discovered, still_open = [], []
    for k in asked:
        is_disc = _gap_key_discovered(k, known_rows, known_names)
        classed.append({"gap_key": k, "discovered": is_disc})
        (discovered if is_disc else still_open).append(k)

    n_asked = len(asked)
    n_disc = len(discovered)
    rate = (n_disc / n_asked) if n_asked else 1.0

    return {
        "name": name,
        "asked": classed,
        "asked_count": n_asked,
        "discovered": discovered,
        "still_open": still_open,
        "discovered_count": n_disc,
        "still_open_count": len(still_open),
        "discovery_rate": rate,
    }


# ===================================================================================
# SIMULATION HELPERS — build a synthetic creature, ASK gaps, then ANSWER some of them.
# These are the deterministic, offline, temp-store-only primitives the battery + selftest
# drive. They call the REAL engines (curiosity.mark_asked, memory_lirf.Facts.merge), so the
# metric is exercised against exactly the wiring production uses — never a shortcut.
# ===================================================================================
def _ask_taxonomy_gaps(name: str, slots: list) -> list:
    """Surface a fixed list of TAXONOMY slots as questions (append them to the Asked Ledger
    via the engine's own mark_asked). Returns the gap dicts asked. Skips unknown slots."""
    asked = []
    for slot in slots:
        cat = curiosity._SLOT_CATEGORY.get(slot)
        trait = curiosity._SLOT_TRAIT.get(slot)
        if cat is None or trait is None:
            continue
        gap = {
            "category": cat, "slot": slot, "kind": curiosity.UNKNOWN,
            "trait": curiosity.canon_trait(trait), "entity": curiosity.SELF,
            "evidence": {"mentions": 0, "source": ""},
            "_question": f"(synthetic question about {slot})",
        }
        curiosity.mark_asked(name, gap)
        asked.append(gap)
    return asked


def _answer_slot(name: str, slot: str, value: str) -> None:
    """'Answer' a taxonomy question by capturing the fact into the LIRF ledger and
    CORROBORATING it once, so the row clears the [KNOWN] confidence floor (>= 0.85) — i.e.
    a confident KNOWN fact, exactly what makes the asked gap a DISCOVERY. Deterministic;
    writes only to the (redirected) temp store."""
    trait = curiosity._SLOT_TRAIT.get(slot, slot)
    f = memory_lirf.Facts.load(name)
    # newest-wins install, then one corroboration so confidence climbs above the KNOWN bar.
    f.merge({"trait": trait, "value": value})
    f.merge({"trait": trait, "value": value})
    f.save(name)


def _build_creature(name: str, *, ask: list, answer: dict) -> None:
    """Seed one synthetic creature end-to-end: ask every slot in `ask`, then answer the
    subset in `answer` ({slot: value}). All writes land in the redirected temp store."""
    _ask_taxonomy_gaps(name, ask)
    for slot, value in answer.items():
        _answer_slot(name, slot, value)


# ===================================================================================
# THE BATTERY — PROVE the metric discriminates "asked 10 / learned 8" from
# "asked 10 / learned 1". Each scenario seeds a fresh synthetic creature in a temp store,
# asks a fixed 10-slot set, answers a chosen subset, and reports the rate. The rollup
# asserts the high-discovery creature scores far above the low-discovery (noise) one.
# ===================================================================================
# Ten real taxonomy slots a companion would, over time, ask about.
_TEN_SLOTS = ["name", "birthday", "birthplace", "occupation", "employer",
              "lives", "partner", "goal", "favorite_food", "diet"]

# Plausible answers for each, used to "learn" the chosen subset.
_ANSWERS = {
    "name": "Lamar", "birthday": "June 12", "birthplace": "Eugene",
    "occupation": "founder", "employer": "Collatio", "lives": "Portland",
    "partner": "Sam", "goal": "ship Vera", "favorite_food": "ramen", "diet": "pescatarian",
}


def _scenario(name: str, *, learn: list) -> dict:
    """Run ONE discrimination scenario: ask all ten slots, learn the `learn` subset, report.
    Returns the quality_report dict (with the asked/answered plan attached for the render)."""
    answer = {s: _ANSWERS[s] for s in learn}
    _build_creature(name, ask=_TEN_SLOTS, answer=answer)
    rep = quality_report(name)
    rep["_plan"] = {"asked": list(_TEN_SLOTS), "learned": list(learn)}
    return rep


def run_battery() -> dict:
    """Seed three contrasting synthetic creatures in one temp store and report each, plus a
    rollup that PROVES discovery_rate discriminates good curiosity from noise:

      * HIGH  — asked 10, learned 8  -> rate 0.80 (she is genuinely getting to know you).
      * LOW   — asked 10, learned 1  -> rate 0.10 (noise: asking into the void).
      * GROWING — the SAME creature re-measured as answers land, to show the rate MOVES
                  monotonically up from 0.0 toward 1.0 (questions becoming continuity).

    Deterministic, offline, isolated. Returns a dict with the three reports + the rollup."""
    with _temp_store(curiosity, memory_lirf):
        tok = secrets.token_hex(3)

        high = _scenario(f"{SYNTH}_high_{tok}", learn=_TEN_SLOTS[:8])    # 8 of 10 -> 0.80
        low = _scenario(f"{SYNTH}_low_{tok}", learn=_TEN_SLOTS[:1])      # 1 of 10 -> 0.10

        # GROWING: one creature, asked all ten up front, answers landing one at a time. We
        # snapshot the discovery_rate after each new answer to show it climbing — the literal
        # "questions become continuity" curve.
        grow_name = f"{SYNTH}_grow_{tok}"
        _ask_taxonomy_gaps(grow_name, _TEN_SLOTS)
        trajectory = [quality_report(grow_name)["discovery_rate"]]       # 0/10 = 0.0
        for slot in _TEN_SLOTS:
            _answer_slot(grow_name, slot, _ANSWERS[slot])
            trajectory.append(quality_report(grow_name)["discovery_rate"])
        grow_final = quality_report(grow_name)

    # the discrimination the metric exists to make.
    discriminates = high["discovery_rate"] > low["discovery_rate"]
    gap = high["discovery_rate"] - low["discovery_rate"]
    # the trajectory is non-decreasing and strictly ends above where it began.
    monotonic = all(b >= a - 1e-9 for a, b in zip(trajectory, trajectory[1:]))
    moved = trajectory[-1] > trajectory[0]

    return {
        "high": high,
        "low": low,
        "growing": {"final": grow_final, "trajectory": trajectory},
        "rollup": {
            "high_rate": high["discovery_rate"],
            "low_rate": low["discovery_rate"],
            "discriminates": discriminates,
            "separation": gap,
            "trajectory_monotonic": monotonic,
            "trajectory_moved_up": moved,
        },
    }


# ===================================================================================
# RENDER — human-readable curiosity-quality accounting.
# ===================================================================================
def render_report(rep: dict) -> str:
    out = []
    name = rep.get("name", "?")
    plan = rep.get("_plan")
    out.append(f'CREATURE: {name}')
    if plan:
        out.append(f"  plan: asked {len(plan['asked'])} gaps, answered "
                   f"{len(plan['learned'])} ({', '.join(plan['learned']) or 'none'})")
    out.append(f"  ASKED       : {rep['asked_count']:>3}  (gaps surfaced as questions)")
    out.append(f"  DISCOVERED  : {rep['discovered_count']:>3}  "
               f"(asked AND now a confident KNOWN fact)")
    if rep["discovered"]:
        out.append("      " + ", ".join(rep["discovered"]))
    out.append(f"  STILL-OPEN  : {rep['still_open_count']:>3}  (asked, not yet learned)")
    if rep["still_open"]:
        out.append("      " + ", ".join(rep["still_open"]))
    out.append(f"  DISCOVERY RATE: {rep['discovery_rate']:.2f}   "
               f"(discovered / asked)")
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 79)
    out.append("VERA CURIOSITY-QUALITY METRICS")
    out.append("Measure DISCOVERY, not COUNT. A question that became a known fact is a")
    out.append("discovery; a question that learned nothing is noise. discovery_rate tells")
    out.append("them apart.  \"Questions can become noise; discoveries become continuity.\"")
    out.append("=" * 79)

    out.append("")
    out.append("HIGH-DISCOVERY creature (good curiosity — she is getting to know you):")
    out.append(render_report(report["high"]))
    out.append("")
    out.append("LOW-DISCOVERY creature (noise — asking into the void):")
    out.append(render_report(report["low"]))

    grow = report["growing"]
    out.append("")
    out.append("-" * 79)
    out.append("GROWING creature — the SAME creature as answers land (questions -> continuity)")
    out.append("-" * 79)
    traj = grow["trajectory"]
    out.append("  discovery_rate after each answer:")
    out.append("    " + " -> ".join(f"{r:.2f}" for r in traj))
    out.append(f"  final: {grow['final']['discovered_count']}/{grow['final']['asked_count']} "
               f"discovered  ->  rate {grow['final']['discovery_rate']:.2f}")

    r = report["rollup"]
    out.append("")
    out.append("-" * 79)
    out.append("THE DISCRIMINATION (why COUNT is the wrong metric)")
    out.append("-" * 79)
    out.append(f"  high creature  : rate {r['high_rate']:.2f}  (asked 10 / learned 8)")
    out.append(f"  low creature   : rate {r['low_rate']:.2f}  (asked 10 / learned 1)")
    out.append(f"  separation     : {r['separation']:.2f}   "
               f"({'DISCRIMINATES' if r['discriminates'] else 'FAILS TO DISCRIMINATE'} — "
               f"a pure question COUNT would call both '10', indistinguishable)")
    out.append(f"  growing curve  : {'monotonic up' if r['trajectory_monotonic'] else 'NON-monotonic'}"
               f", {'moved up' if r['trajectory_moved_up'] else 'did NOT move'} as answers landed")
    out.append("")
    out.append("HONEST NOTE: a HIGH discovery rate is the goal — it means her questions are")
    out.append("turning into the durable, never-re-asked knowledge that compounds into a real")
    out.append("relationship (Law 002). A LOW rate is not a crash; it is the honest signal that")
    out.append("she is asking more than she is learning, and is the number a curiosity fix must")
    out.append("move. This complements the Experience cert's curiosity COUNT (~67%): that asks")
    out.append("'does she turn back to the user?'; this asks 'did the turn become knowledge?'")
    return "\n".join(out)


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA CURIOSITY-QUALITY METRICS (discovery rate, not question count)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    try:
        report = run_battery()
        engine_error = None
    except Exception as e:                       # pragma: no cover - entry point never raises
        report = {"high": {}, "low": {}, "growing": {"final": {}, "trajectory": []},
                  "rollup": {"high_rate": None, "low_rate": None, "discriminates": False,
                             "separation": None, "trajectory_monotonic": None,
                             "trajectory_moved_up": None}}
        engine_error = repr(e)

    fp_after = _footprint(real_anima)
    footprint_unchanged = fp_before == fp_after

    report["footprint_unchanged"] = footprint_unchanged
    report["engine_error"] = engine_error

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render(report))
        print("")
        print("GUARDRAIL: real .anima footprint  : "
              + ("byte-UNCHANGED (synthetic-only; nothing real touched)"
                 if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
        if engine_error:
            print(f"GUARDRAIL: engine error           : {engine_error}")

    # Exit non-zero ONLY on a broken guardrail (touched real state / an engine blew up).
    # A low discovery rate is the REPORT, never a failure.
    return 0 if (footprint_unchanged and engine_error is None) else 1


# ===================================================================================
# SELFTEST — `python3 scripts/curiosity_quality.py --selftest`. PROVES the metric is sound
# and DISCRIMINATES: the mapping classes a learned gap as discovered and an un-learned gap
# as still-open, the rate is in [0,1], "learned 8/10" beats "learned 1/10", the rate MOVES
# as answers land, and the synthetic-only guardrail holds. No model, no network.
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    with _temp_store(curiosity, memory_lirf):
        tok = secrets.token_hex(3)

        # --- a creature that asked NOTHING -> asked 0, rate 1.0 (vacuously perfect) ---
        empty = quality_report(f"{SYNTH}_empty_{tok}")
        ok("empty: a creature that asked nothing -> asked 0",
           empty["asked_count"] == 0)
        ok("empty: discovery_rate is 1.0 when nothing was asked (nothing un-discovered)",
           empty["discovery_rate"] == 1.0)

        # === THE CORE MAPPING: asked + learned -> DISCOVERED; asked + not-learned -> OPEN ===
        nm = f"{SYNTH}_map_{tok}"
        _ask_taxonomy_gaps(nm, ["birthday", "lives", "occupation"])
        # answer ONLY birthday (capture + corroborate -> confident KNOWN fact).
        _answer_slot(nm, "birthday", "June 12")
        rep = quality_report(nm)
        ok("map: all three asked gaps are accounted for", rep["asked_count"] == 3)
        ok("map: the ANSWERED gap (birthday) is DISCOVERED",
           "birthday" in rep["discovered"])
        ok("map: an UN-answered gap (lives) is STILL-OPEN, not discovered",
           "lives" in rep["still_open"] and "lives" not in rep["discovered"])
        ok("map: an UN-answered gap (occupation) is STILL-OPEN",
           "occupation" in rep["still_open"])
        ok("map: discovered + still_open partition the asked set exactly",
           rep["discovered_count"] + rep["still_open_count"] == rep["asked_count"])
        ok("map: rate is discovered/asked == 1/3",
           abs(rep["discovery_rate"] - (1 / 3)) < 1e-9)

        # --- a LOW-confidence answer is NOT a discovery (the [KNOWN] bar has teeth) ---
        # One merge only (no corroboration) lands at CONF_NEW=0.9 which IS >= the 0.85 bar,
        # so to prove the bar bites we use a DIFFERENT slot answered then knocked below the
        # bar via needs_reconfirm: a near-immutable flip sets needs_reconfirm -> not KNOWN.
        nm2 = f"{SYNTH}_conf_{tok}"
        _ask_taxonomy_gaps(nm2, ["birthday"])
        f = memory_lirf.Facts.load(nm2)
        f.merge({"trait": "birthday", "value": "June 12"})              # KNOWN-eligible
        f.merge({"trait": "birthday", "value": "July 3"})              # silent flip of a
        f.save(nm2)                                                     # near-immutable ->
        row = memory_lirf.Facts.load(nm2).lookup(memory_lirf.SELF, "birthday")
        ok("conf-setup: a silent near-immutable flip sets needs_reconfirm",
           bool(row and row.get("needs_reconfirm")))
        rep2 = quality_report(nm2)
        ok("BAR: a needs_reconfirm fact is NOT counted as discovered (the [KNOWN] bar bites)",
           "birthday" in rep2["still_open"] and rep2["discovered_count"] == 0)

        # === THE DISCRIMINATION the tool exists for: 8/10 (good) vs 1/10 (noise) ===
        high = _scenario(f"{SYNTH}_d_high_{tok}", learn=_TEN_SLOTS[:8])
        low = _scenario(f"{SYNTH}_d_low_{tok}", learn=_TEN_SLOTS[:1])
        ok("discriminate: 'asked 10 / learned 8' scores 0.80",
           abs(high["discovery_rate"] - 0.80) < 1e-9)
        ok("discriminate: 'asked 10 / learned 1' scores 0.10",
           abs(low["discovery_rate"] - 0.10) < 1e-9)
        ok("discriminate: the good creature's rate is FAR above the noise creature's",
           high["discovery_rate"] - low["discovery_rate"] >= 0.5)
        ok("discriminate: a pure COUNT could NOT tell them apart (both asked 10)",
           high["asked_count"] == low["asked_count"] == 10)

        # === THE RATE MOVES as answers land (questions becoming continuity) ===
        grow = f"{SYNTH}_grow_{tok}"
        _ask_taxonomy_gaps(grow, _TEN_SLOTS)
        before = quality_report(grow)["discovery_rate"]
        ok("moves: with all asked but none answered, rate starts at 0.0", before == 0.0)
        traj = [before]
        for slot in _TEN_SLOTS:
            _answer_slot(grow, slot, _ANSWERS[slot])
            traj.append(quality_report(grow)["discovery_rate"])
        ok("moves: the rate is NON-DECREASING as each answer lands",
           all(b >= a - 1e-9 for a, b in zip(traj, traj[1:])))
        ok("moves: the rate strictly INCREASED from start (0.0) to end (1.0)",
           traj[-1] > traj[0] and abs(traj[-1] - 1.0) < 1e-9)
        ok("moves: answering ONE more gap raised the rate by exactly 1/10 each step",
           all(abs((b - a) - 0.1) < 1e-9 for a, b in zip(traj, traj[1:])))

        # === A RELATIONSHIP gap (the canonical 'Mike') discovers when the NAME is learned ===
        rel = f"{SYNTH}_rel_{tok}"
        # ask a relationship gap exactly as the engine would key it (relationship:<entity>).
        mike_gap = {
            "category": "relationships", "slot": curiosity._slug_for_entity("Mike"),
            "kind": curiosity.SUSPECTED, "trait": "", "entity": "Mike",
            "evidence": {"mentions": 42, "source": ""},
            "_question": "(synthetic) how do you know Mike?",
        }
        curiosity.mark_asked(rel, mike_gap)
        rep_rel_open = quality_report(rel)
        ok("relationship: an asked 'relationship:mike' gap is STILL-OPEN before the name lands",
           any(k.startswith("relationship:") for k in rep_rel_open["still_open"])
           and rep_rel_open["discovered_count"] == 0)
        # now LEARN who Mike is: partner=Mike, corroborated to a confident KNOWN fact.
        f = memory_lirf.Facts.load(rel)
        f.merge({"trait": "partner", "value": "Mike"})
        f.merge({"trait": "partner", "value": "Mike"})
        f.save(rel)
        rep_rel_disc = quality_report(rel)
        ok("relationship: once 'partner=Mike' is KNOWN, the Mike gap is DISCOVERED (Law 002)",
           any(k.startswith("relationship:") for k in rep_rel_disc["discovered"])
           and rep_rel_disc["discovery_rate"] == 1.0)

        # --- robustness: junk keys + missing stores never raise, never over-credit ---
        ok("robust: a garbage gap-key is classed not-discovered (never raises)",
           _gap_key_discovered("not_a_real_slot_xyz", {}, set()) is False)
        ok("robust: quality_report on a never-seen creature is a zero/perfect report",
           quality_report(f"{SYNTH}_never_{tok}")["discovery_rate"] == 1.0)

    # --- the battery rollup is coherent + asserts the discrimination ---
    rep_b = run_battery()
    ok("battery: rollup reports the high creature above the low creature",
       rep_b["rollup"]["discriminates"] is True)
    ok("battery: high=0.80, low=0.10 exactly",
       abs(rep_b["rollup"]["high_rate"] - 0.80) < 1e-9
       and abs(rep_b["rollup"]["low_rate"] - 0.10) < 1e-9)
    ok("battery: the growing trajectory is monotonic and moved up",
       rep_b["rollup"]["trajectory_monotonic"] and rep_b["rollup"]["trajectory_moved_up"])

    # --- render never raises and carries the thesis line ---
    txt = render(rep_b)
    ok("render: produces a non-empty report", bool(txt.strip()))
    ok("render: carries the discovery-over-count thesis",
       "discoveries become continuity" in txt and "DISCRIMINATES" in txt)
    ok("render: per-creature render works", bool(render_report(rep_b["high"]).strip()))

    # --- GUARDRAIL: the synthetic-only run touched no real .anima file ---
    real = Path(_ROOT) / ".anima"
    fp0 = _footprint(real)
    _ = run_battery()
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across a full battery", fp0 == fp1)
    ok("guardrail: no synthetic file leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL CURIOSITY-QUALITY SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
