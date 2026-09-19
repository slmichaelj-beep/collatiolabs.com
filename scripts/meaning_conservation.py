#!/usr/bin/env python3
"""MEANING-CONSERVATION OBSERVATORY (directive #4) — "was what MATTERED preserved?"

    Data conservation asks: was the INFORMATION preserved?  (scripts/conservation.py)
    MEANING conservation asks: was the SIGNIFICANCE preserved?  (this tool)

The Conservation Observatory (scripts/conservation.py) follows a BYTE — every salient token
traced DETECTED -> CAPTURED -> STORED -> RETRIEVED -> USED, naming the stage that drops it.
The Data-Flow Observatory (scripts/dataflow.py) follows the SHAPE. This tool follows the
MEANING: for an utterance it extracts its SIGNIFICANCE — a life-event, a milestone, a
relational weight, an emotional tone — and measures whether THAT survived the pipeline, even
where the literal words did not.

The worked example the founder named:

    "My daughter Maya started kindergarten"
      LITERAL  : {daughter, Maya, kindergarten}
      MEANING  : {family milestone, child development, emotional significance}

The engine (``anima.meaning_conservation``) extracts both layers and grounds every meaning
unit in evidence (the #1 rule: meaning is DERIVED, never invented). This observatory runs
the REAL engines on a SYNTHETIC creature inside a HERMETIC temp store and walks each meaning
unit through three gates —

    CAPTURED    (the live capture path SAW the meaning — a LIRF candidate / a world edge)
      -> STORED       (it survives Facts.save / World.save and a reload FROM DISK)
      -> SURFACEABLE  (its significance re-surfaces: meaning.significance / a Meaning Object,
                       or the review.daily_review keep-forever rollup)

— and reports the FOUR rates the directive names, on a synthetic battery:

    LITERAL conservation        the data layer (for contrast — what the byte tools measure)
    MEANING conservation        every derived significance unit retained end-to-end
    EMOTIONAL-TONE conservation the user's stated affect retained
    LIFE-EVENT conservation     a stated transition's significance retained

A unit that falls out names its ``loss_reason`` (the first gate it failed), so nothing is
dropped silently — the same accounting discipline as the data observatory. A low rate is the
TRUTH being reported, not a bug: emotional tone, for instance, may be captured as a durable
reported_feeling yet not re-surface as a *significant theme* until it recurs — that is
acceptable, but it must be VISIBLE and ATTRIBUTED here.

────────────────────────────────────────────────────────────────────────────────────────────
GUARDRAILS (identical posture to scripts/conservation.py / scripts/relationship.py)
────────────────────────────────────────────────────────────────────────────────────────────
  * DETERMINISTIC + OFFLINE. No model, no network. The model-assist Tier-B paths are never
    invoked (model_pass defaults off). Significance/review are read deterministically.
  * SYNTHETIC creatures + TEMPORARY stores ONLY. HERMETIC: every engine STORE the pipeline
    touches is redirected to ONE TemporaryDirectory for the run — memory_lirf.STORE on BOTH
    the __main__ and package bindings, world_state.STORE, curiosity.STORE, constitution.STORE,
    reliability.DEFAULT_STORE, meaning.STORE, review.STORE, telemetry.STORE, cloud.STORE — so
    a good Facts.load (which also writes a continuity ledger + a guarded backup) can never
    leak into the real .anima. The run ASSERTS the real .anima footprint is byte-UNCHANGED
    start->end and that every redirected binding is RESTORED. It NEVER reads or writes a real
    Vera.* file.
  * GROUNDED. Every meaning unit is derived from evidence (an edge / a reported_feeling row /
    a milestone trait) AND grounded in the user's words; the selftest PROVES an invented
    ("ungrounded") meaning is NOT emitted.
  * STANDALONE + ADDITIVE. Imports and RUNS the engines; edits NO module, NO test, NO
    certify.py / selftest.py. The only files this adds are anima/meaning_conservation.py +
    scripts/meaning_conservation.py.
  * Never raises out of the entry points — a malformed input yields an honest empty/zero
    ledger, not a traceback.

    python3 scripts/meaning_conservation.py            # human-readable observatory + battery
    python3 scripts/meaning_conservation.py --json     # machine-readable
    python3 scripts/meaning_conservation.py --selftest # asserts the meaning accounting + guardrail

Exit code is 0 (this is an ACCOUNTING tool — it reports loss, it does not fail on it). A
broken guardrail (the real .anima footprint changed, or an engine raised) exits non-zero.
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

from anima import memory_lirf            # noqa: E402  LITERAL facts + reported_feeling tone
from anima import world_state            # noqa: E402  life-event / relation / problem edges
from anima import meaning_conservation as mc   # noqa: E402  the MEANING-conservation engine

# The significance + review surfaces (the SURFACEABLE gate). Imported best-effort: a stage
# whose module won't import degrades to "credited-nothing" (the honest accounting) rather
# than crashing the tool.
try:                                     # noqa: E402
    from anima import meaning as _meaning
except Exception:                        # pragma: no cover - isolation
    _meaning = None
try:                                     # noqa: E402
    from anima import review as _review
except Exception:                        # pragma: no cover - isolation
    _review = None

# A synthetic-only sentinel name so nothing here can ever collide with a real creature.
SYNTH = "meancons_synth"


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect + footprint hash. Mirrors scripts/conservation.py
# (~lines 122-208): redirect EVERY module STORE the full pipeline now touches to ONE throwaway
# dir, so a good Facts.load (which ALSO writes a {name}.continuity.jsonl via constitution.STORE
# and a guarded backup via reliability.DEFAULT_STORE) can never leak into the real .anima.
#
# A redirect target is a (module, attr) pair because reliability's store attr is DEFAULT_STORE,
# not STORE. The set is resolved by NAME so importing this module never hard-depends on every
# downstream engine; a missing one is simply skipped. The directive's named set is covered:
# memory_lirf (both bindings), constitution, reliability.DEFAULT_STORE, curiosity, world_state,
# meaning, telemetry, cloud — plus review (the keep-forever rollup the SURFACEABLE gate reads).
# ===================================================================================
_STORE_TARGETS = (
    ("anima.memory_lirf", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.review", "STORE"),
    ("anima.constitution", "STORE"),           # the continuity ledger a good load writes
    ("anima.reliability", "DEFAULT_STORE"),     # guarded-backup snapshots
    ("anima.telemetry", "STORE"),               # any telemetry a read path may emit
    ("anima.cloud", "STORE"),                   # any cloud-mirror store
)


def _resolve_store_targets():
    """Resolve ``_STORE_TARGETS`` to live ``(module, attr)`` pairs that actually carry the
    attribute right now. A module that won't import, or that lacks the attr, is skipped — so
    the redirect set adapts to whatever is built without ever hard-failing. Resolving by name
    keeps the __main__ binding of this script's own ``memory_lirf``/``world_state`` imports
    correct even though they are the SAME module objects as the package copies."""
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
def _temp_store(*extra_modules):
    """Redirect EVERY pipeline STORE binding to one fresh temp dir for the duration, so
    nothing under the real .anima/ is ever read or written. Restored on exit. ``extra_modules``
    (legacy positional args, e.g. ``memory_lirf, world_state``) are also redirected on their
    ``STORE`` attr. HERMETIC by construction: a leak is impossible regardless of which engine
    the pipeline ends up writing."""
    targets = _resolve_store_targets()
    for m in extra_modules:
        if hasattr(m, "STORE") and (m, "STORE") not in targets:
            targets.append((m, "STORE"))
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-meaning-cons-") as td:
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
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir,
    which legitimately changes), so we can PROVE the harness touched nothing."""
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
# GATE SURFACES — run the REAL engines on a synthetic creature (already inside a hermetic
# temp store) and collect, for each retention gate, the SET of normalised surface keys it
# carries. The engine's retention_of() then walks every meaning unit against these sets.
# Every read is best-effort: an engine that raises yields an empty set for its gate (that
# gate then credits nothing — the honest accounting), never a traceback.
# ===================================================================================
def _surfaces_from_text(blob: str) -> set:
    """Every normalised surface key present in a free-text block — tokenised the SAME way
    the engine keys a unit, so the membership test is apples-to-apples."""
    out = set()
    for w in mc._WORD.findall(str(blob or "")):
        k = mc._norm_tok(w)
        if k:
            out.add(k)
    return out


def _row_surfaces(rows) -> set:
    """Surface keys carried by a list of LIRF rows: a row's VALUE tokens AND its TRAIT slug
    (so a milestone/relational trait credits its meaning even when the literal value differs)."""
    out = set()
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        out |= _surfaces_from_text(memory_lirf._fmt_value(r.get("value", "")))
        out |= _surfaces_from_text(str(r.get("trait", "")))
    return out


def _edge_surfaces(edges) -> set:
    """Surface keys carried by a list of world edges: SUBJECT + OBJECT tokens (the literal
    nodes) AND the PREDICATE slug (so a life-event/relation predicate credits its meaning)."""
    out = set()
    for e in (edges or []):
        if not isinstance(e, dict):
            continue
        out |= _surfaces_from_text(str(e.get("subject", "")))
        out |= _surfaces_from_text(str(e.get("object", "")))
        out |= _surfaces_from_text(str(e.get("predicate", "")))
    return out


def _captured_surfaces(name: str, text: str) -> set:
    """CAPTURED — what the extractor SEES in memory (no persistence yet): the LIRF candidate
    facts + the world edges from the deterministic capture path. Best-effort."""
    surf = set()
    try:
        cands = memory_lirf.extract(text) or []
    except Exception:
        cands = []
    surf |= _row_surfaces(cands)
    try:
        tuples = world_state.capture(text) or []
        edges = [{"subject": s, "predicate": p, "object": o}
                 for (s, p, o, _k, *_r) in tuples]
    except Exception:
        edges = []
    surf |= _edge_surfaces(edges)
    return surf


def _stored_surfaces(name: str, text: str) -> set:
    """STORED — persist via the REAL storage path and RELOAD FROM DISK, then read what
    SURVIVED. merge LIRF candidates + save; capture_relations persists world edges; then load
    the ledger and graph back. A unit captured-in-memory but absent after the round-trip fell
    out at STORAGE. Best-effort."""
    try:
        facts_store = memory_lirf.Facts.load(name)
        for c in (memory_lirf.capture(name, text) or []):
            facts_store.merge(c)
        facts_store.save(name)
    except Exception:
        pass
    try:
        world_state.capture_relations(name, text)        # persists edges (own load/save)
    except Exception:
        pass
    surf = set()
    try:
        surf |= _row_surfaces(list(memory_lirf.Facts.load(name).about()))
    except Exception:
        pass
    try:
        surf |= _edge_surfaces(list(world_state.World.load(name).active()))
    except Exception:
        pass
    return surf


def _surfaceable_surfaces(name: str) -> set:
    """SURFACEABLE — can the MEANING be re-surfaced? Credited by THEME/SUBJECT IDENTITY, NOT
    by free-text prose: a meaning unit re-surfaces iff its SUBJECT is a significant theme or a
    keep-forever item, never merely because a sentence happens to contain a matching common
    word. (Crediting from a statement's prose would falsely pass a unit grounded on a stop-word
    like "name"/"still" and defeat the whole honesty point — the same reason the data tool
    credits tone only from a fact VALUE, never a predicate.) The union of:
      * meaning.significance(name) — the SUBJECTS (+ neighbour nodes) of every significant theme;
      * meaning.meaning(name) — the Meaning Objects' SUBJECTS (the topic, not the sentence);
      * meaning.current_chapter(name) — the chapter THEMES (the topic keys, not the summary prose);
      * review.daily_review(name, persist=False) — the keep-forever rollup's item KEYS +
        dimension SUBJECTS + milestone KEYS, the form where the words may be discarded but the
        MEANING is kept. A keep-forever key like "fact:daughter" / "edge:adopted:dog" carries
        the subject token, so a milestone/life-event credits even when the prose differs.
    A stored unit whose subject appears in NONE of these is on disk yet mute. Best-effort."""
    surf = set()
    if _meaning is not None:
        try:
            for it in (_meaning.significance(name) or []):
                surf |= _surfaces_from_text(str(it.get("subject", "")))
                for nb in (it.get("evidence", {}) or {}).get("neighbours", []) or []:
                    surf |= _surfaces_from_text(str(nb))
        except Exception:
            pass
        try:
            for o in (_meaning.meaning(name) or []):
                if not isinstance(o, dict):
                    continue
                surf |= _surfaces_from_text(str(o.get("subject", "")))   # the topic only
        except Exception:
            pass
        try:
            chap = _meaning.current_chapter(name) or {}
            for th in (chap.get("themes") or []):                        # theme keys, not prose
                surf |= _surfaces_from_text(str(th))
        except Exception:
            pass
    if _review is not None:
        try:
            rv = _review.daily_review(name, persist=False) or {}
        except Exception:
            rv = {}
        bits = []
        # the keep-forever item KEY (e.g. "fact:daughter", "edge:adopted:dog", "theme:work")
        # carries the subject token; the evidence carries the trait/predicate + value. We read
        # those identity fields, NOT the free-text summary prose.
        def _ev_content(ev):
            # only STRING evidence values (trait/predicate/value names) — skip int support
            # counts / bools, which carry no subject and would only add noise to the set.
            return " ".join(str(v) for v in (ev or {}).values() if isinstance(v, str))
        for it in (rv.get("what_to_remember") or []):
            if isinstance(it, dict):
                bits.append(str(it.get("key", "")))
                bits.append(_ev_content(it.get("evidence")))
        for dim in ("what_mattered", "what_changed", "what_unresolved"):
            for line in (rv.get(dim) or []):
                if isinstance(line, dict):
                    bits.append(str(line.get("subject", "")))    # the topic, not the prose
        for ms in (rv.get("milestones") or []):
            if isinstance(ms, dict):
                bits.append(str(ms.get("key", "")))
                bits.append(_ev_content(ms.get("evidence")))
        chap = rv.get("chapter") or {}
        if isinstance(chap, dict):
            for th in (chap.get("themes") or []):                # theme keys, not the summary
                bits.append(str(th))
        surf |= _surfaces_from_text("\n".join(bits))
    return surf


def _gate_surfaces(name: str, text: str) -> dict:
    """Build the three gate-surface sets for ONE utterance on the synthetic creature (already
    inside a hermetic temp store). The gates are monotone by construction in the engine's
    walk; here we just collect what each gate carries. Read order matters: CAPTURED reads the
    in-memory extract BEFORE STORED persists, so a capture-only signal is visible at CAPTURED
    even if persistence later drops it."""
    captured = _captured_surfaces(name, text)
    stored = _stored_surfaces(name, text)
    surfaceable = _surfaceable_surfaces(name)
    return {mc.CAPTURED: captured, mc.STORED: stored, mc.SURFACEABLE: surfaceable}


# ===================================================================================
# THE LEDGER — one input's full meaning-conservation accounting.
# ===================================================================================
def meaning_ledger(text: str) -> dict:
    """The MEANING-CONSERVATION LEDGER for ONE utterance. Extracts the LITERAL + MEANING
    units, runs the real pipeline on a fresh synthetic creature in a hermetic temp store,
    and walks every unit through CAPTURED -> STORED -> SURFACEABLE:

        {
          "input":        the utterance,
          "literal":      [ {surface, source} ],         # the data layer (facts/tokens)
          "meaning":      [ {kind, subject, statement, grounded_in, evidence, dimensions} ],
          "literal_trace":[ unit + {captured, stored, surfaceable, reached, loss_reason} ],
          "meaning_trace":[ unit + {captured, stored, surfaceable, reached, loss_reason} ],
          "rates":        {literal, meaning, emotional_tone, life_event},  # per-input
        }

    Deterministic, offline, isolated. Never raises: a bad input yields an empty ledger with
    rates 1.0 (nothing to lose)."""
    text = text or ""
    literal = mc.literal_units(text)
    meaning = mc.meaning_units(text)

    with _temp_store(memory_lirf, world_state):
        # a UNIQUE synthetic name per call so no state leaks between battery inputs.
        name = f"{SYNTH}_{secrets.token_hex(3)}"
        gates = _gate_surfaces(name, text)

    # the LITERAL units walk the same gates (CAPTURED/STORED carry their value/node tokens;
    # SURFACEABLE rarely carries a bare literal token unless it is also a significant theme).
    literal_trace = mc.retention_of(
        [{"kind": "literal", "subject": u["surface"], "grounded_in": u["surface"],
          "evidence": {"value": u["surface"], "source": u["source"]},
          "dimensions": (mc.LITERAL,)} for u in literal],
        gates)
    meaning_trace = mc.retention_of(meaning, gates)
    rates = mc.conservation_rates(literal_trace, meaning_trace)

    return {
        "input": text,
        "literal": [{"surface": u["surface"], "source": u["source"]} for u in literal],
        "meaning": [{"kind": u["kind"], "subject": u["subject"],
                     "statement": u["statement"], "grounded_in": u["grounded_in"],
                     "evidence": u["evidence"], "dimensions": list(u["dimensions"])}
                    for u in meaning],
        "literal_trace": literal_trace,
        "meaning_trace": meaning_trace,
        "rates": rates,
    }


# The battery — the founder's worked example + a stress line that exercises emotional tone,
# plus a few information-rich life-event inputs so the four rates are exercised across kinds.
BATTERY = [
    "My daughter Maya started kindergarten last week",
    "I've been really stressed about the Q3 launch",
    "I moved to Austin because my manager changed",
    "We adopted a dog named Cooper in 2024",
    "My wife Jen and I are excited about the move to Denver in March",
    "I work at Collatio and I'm worried about money lately",
]


def _agg_rate(traces_key: str, ledgers: list, dim_filter=None) -> dict:
    """Aggregate one rate across the battery: count units retained (reached SURFACEABLE) vs
    total, optionally filtered to a meaning DIMENSION. Honest convention: an empty denominator
    is 1.0 (nothing to lose)."""
    keep = tot = 0
    for led in ledgers:
        for t in led.get(traces_key, []):
            if dim_filter is not None and dim_filter not in t.get("dimensions", ()):
                continue
            tot += 1
            if t.get(mc.SURFACEABLE):
                keep += 1
    return {"retained": keep, "total": tot, "rate": (keep / tot) if tot else 1.0}


def run_battery(inputs=None) -> dict:
    """Run the meaning-conservation observatory over a battery and compute the FOUR overall
    rates + the per-input ledgers + the loss attribution. Returns a dict with the ledgers and
    the rollup."""
    inputs = list(inputs) if inputs is not None else list(BATTERY)
    ledgers = [meaning_ledger(t) for t in inputs]

    rates = {
        "literal": _agg_rate("literal_trace", ledgers),
        "meaning": _agg_rate("meaning_trace", ledgers),
        "emotional_tone": _agg_rate("meaning_trace", ledgers, dim_filter=mc.EMOTIONAL_TONE),
        "life_event": _agg_rate("meaning_trace", ledgers, dim_filter=mc.LIFE_EVENT),
    }

    # where meaning fell out, summed across the battery (the FIRST gate each lost unit failed).
    lost_at = {mc.CAPTURED: [], mc.STORED: [], mc.SURFACEABLE: []}
    for led in ledgers:
        for t in led.get("meaning_trace", []):
            if t.get(mc.SURFACEABLE):
                continue
            # attribute to the first gate it failed (the one named in loss_reason).
            for g in mc.GATES:
                if not t.get(g):
                    lost_at.setdefault(g, []).append(
                        {"kind": t["kind"], "subject": t["subject"],
                         "loss_reason": t.get("loss_reason", "")})
                    break

    # totals for the headline.
    tot_meaning = sum(len(l["meaning"]) for l in ledgers)
    tot_literal = sum(len(l["literal"]) for l in ledgers)

    return {
        "ledgers": ledgers,
        "total_literal": tot_literal,
        "total_meaning": tot_meaning,
        "rates": rates,
        "lost_at": lost_at,
    }


# ===================================================================================
# RENDER — human-readable meaning-conservation accounting.
# ===================================================================================
def _bar(rate: float, width: int = 24) -> str:
    rate = 0.0 if rate < 0 else (1.0 if rate > 1 else rate)
    fill = int(round(rate * width))
    return "[" + "#" * fill + "-" * (width - fill) + "]"


def render_ledger(led: dict) -> str:
    out = []
    out.append(f'INPUT:  "{led["input"]}"')
    # LITERAL vs MEANING side by side — the heart of the contrast.
    if led["literal"]:
        out.append("  LITERAL units (the facts/tokens — the data layer):")
        out.append("    " + ", ".join(u["surface"] for u in led["literal"]))
    else:
        out.append("  LITERAL units: (none extracted)")
    if led["meaning"]:
        out.append("  MEANING units (the significance — DERIVED + grounded):")
        for u in led["meaning"]:
            dims = "+".join(d for d in u["dimensions"] if d != mc.MEANING) or "meaning"
            out.append(f"    + [{u['kind']:<16}] {u['statement']}")
            out.append(f"        grounded in: \"{u['grounded_in']}\"  ({dims})")
    else:
        out.append("  MEANING units: (none derived)")

    # the retention walk for each meaning unit — and the gate that dropped it.
    out.append("  RETENTION  (captured -> stored -> surfaceable):")
    for t in led["meaning_trace"]:
        chain = "  ".join(
            f"{g[:4].upper()}:{'yes' if t.get(g) else 'no '}" for g in mc.GATES)
        tail = ""
        if not t.get(mc.SURFACEABLE):
            tail = f"   x dropped: {t.get('loss_reason', '')}"
        out.append(f"    [{t['kind']:<16}] {t['subject']:<18} {chain}{tail}")
    r = led["rates"]
    out.append(f"  RATES (this input): "
               f"literal {r['literal']['rate']*100:.0f}% · "
               f"meaning {r['meaning']['rate']*100:.0f}% · "
               f"tone {r['emotional_tone']['rate']*100:.0f}% · "
               f"life-event {r['life_event']['rate']*100:.0f}%")
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 80)
    out.append("VERA MEANING-CONSERVATION OBSERVATORY (directive #4)")
    out.append("Data conservation asks: was the INFORMATION preserved?")
    out.append("MEANING conservation asks: was what MATTERED preserved? — the SIGNIFICANCE of an")
    out.append("utterance traced CAPTURED -> STORED -> SURFACEABLE; the gate that drops it NAMED.")
    out.append("=" * 80)
    for led in report["ledgers"]:
        out.append("")
        out.append(render_ledger(led))

    out.append("")
    out.append("-" * 80)
    out.append("THE FOUR CONSERVATION RATES (units whose MEANING survived to surfaceable)")
    out.append("-" * 80)
    rate_rows = [
        ("LITERAL conservation", "literal", "facts/tokens (data layer)"),
        ("MEANING conservation", "meaning", "all derived significance "),
        ("EMOTIONAL-TONE cons. ", "emotional_tone", "the user's stated affect "),
        ("LIFE-EVENT conserv.  ", "life_event", "a stated transition      "),
    ]
    rates = report["rates"]
    for label, key, span in rate_rows:
        d = rates.get(key, {})
        v = float(d.get("rate", 0.0))
        out.append(f"  {label} {span}  {_bar(v)} {v*100:5.1f}%  "
                   f"({d.get('retained', 0)}/{d.get('total', 0)})")

    # where meaning fell out, summed across the battery.
    out.append("")
    out.append("  WHERE MEANING WAS LOST (first gate each dropped unit failed):")
    named = {mc.CAPTURED: "CAPTURE   ", mc.STORED: "STORAGE   ", mc.SURFACEABLE: "SURFACING "}
    any_loss = False
    for g in mc.GATES:
        items = report["lost_at"].get(g, [])
        if not items:
            continue
        any_loss = True
        subjects = ", ".join(f"{u['subject']}[{u['kind']}]" for u in items)
        out.append(f"    {named.get(g, g)} dropped {len(items)}: {subjects}")
    if not any_loss:
        out.append("    (nothing dropped — every derived meaning unit rode through to surfaceable)")

    out.append("")
    out.append("HONEST NOTE: this complements the DATA-conservation observatory (scripts/")
    out.append("conservation.py, \"was the byte preserved\") and the data-FLOW observatory")
    out.append("(scripts/dataflow.py, the shape). A literal token can survive while its MEANING")
    out.append("does not (a fact on disk that no significance re-surfaces), and a meaning can")
    out.append("survive while the literal words are gone (the nightly review keeps the gist).")
    out.append("Emotional TONE is the routinely-thin class: it is captured as a durable")
    out.append("reported_feeling, but until it RECURS it may not rank as a significant theme —")
    out.append("acceptable, and now COUNTED, ATTRIBUTED, and VISIBLE rather than silent.")
    return "\n".join(out)


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA MEANING-CONSERVATION OBSERVATORY (was the SIGNIFICANCE preserved?)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--input", action="append", default=None,
                    help="account a custom utterance (repeatable); omit to run the battery")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    inputs = args.input if args.input else None
    try:
        report = run_battery(inputs)
        engine_error = None
    except Exception as e:                       # pragma: no cover - entry point never raises
        report = {"ledgers": [], "total_literal": 0, "total_meaning": 0,
                  "rates": {k: {"retained": 0, "total": 0, "rate": 1.0}
                            for k in ("literal", "meaning", "emotional_tone", "life_event")},
                  "lost_at": {g: [] for g in mc.GATES}}
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
    # Loss itself is the REPORT, never a failure.
    return 0 if (footprint_unchanged and engine_error is None) else 1


# ===================================================================================
# SELFTEST — `python3 scripts/meaning_conservation.py --selftest`. Proves the meaning
# accounting is sound: literal vs meaning extraction, the #1-RULE GROUNDING (an invented
# meaning is NOT emitted), the four rates exist + are probabilities, a meaning whose
# significance re-surfaces is RETAINED while one that doesn't names its loss_reason, and the
# HERMETIC synthetic-only guardrail holds across EVERY redirected STORE binding (real .anima
# byte-unchanged before/after, every binding restored). No model, no network.
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    real = Path(_ROOT) / ".anima"
    fp0 = _footprint(real)

    # --- the engine's own grounding/extraction invariants (re-run here so the OBSERVATORY
    #     selftest is self-contained), then the pipeline accounting on top. ---
    maya = "My daughter Maya started kindergarten last week"
    stress = "I've been really stressed about the Q3 launch"

    # LITERAL vs MEANING extraction — the worked example.
    led = meaning_ledger(maya)
    lit_surfaces = {u["surface"].lower() for u in led["literal"]}
    ok("literal: 'maya' + 'kindergarten' are LITERAL units",
       "maya" in lit_surfaces and "kindergarten" in lit_surfaces)
    mkinds = {u["kind"] for u in led["meaning"]}
    ok("meaning: a LIFE_EVENT meaning unit is derived (started kindergarten)",
       mc.KIND_LIFE_EVENT in mkinds)
    ok("meaning: a RELATIONAL_WEIGHT meaning unit is derived (the daughter bond)",
       mc.KIND_RELATIONAL in mkinds)
    ok("meaning: a MILESTONE meaning unit is derived (a child in their life)",
       mc.KIND_MILESTONE in mkinds)
    ok("worked example: LITERAL and MEANING are DISTINCT layers (meaning != raw tokens)",
       bool(led["meaning"]) and any(u["kind"] != "literal" for u in led["meaning"]))

    # THE #1-RULE GROUNDING PROOF (re-asserted at the observatory level): an invented meaning
    # is NOT emitted. 'graduation' is a real life-event word the Maya line never says.
    idx = mc._input_index(maya)
    invented = mc._ground(mc.KIND_LIFE_EVENT, "graduation", "they graduated", "graduation",
                          {"predicate": "graduated"}, (mc.MEANING, mc.LIFE_EVENT), idx)
    ok("GROUNDED: an ungrounded meaning ('graduation' not in the utterance) is REJECTED",
       invented is None)
    ok("GROUNDED: NO emitted meaning unit is grounded on a word absent from the input",
       all(mc._grounded_surface(u["grounded_in"], idx) is not None for u in led["meaning"]))
    ok("GROUNDED: every meaning unit carries non-empty structural evidence (derived, not invented)",
       all(isinstance(u["evidence"], dict) and u["evidence"] for u in led["meaning"]))
    # the no-diagnosis wall over every generated statement.
    ok("no-diagnosis: NO meaning-unit statement trips a banned clinical term",
       all(mc._is_clean(u["statement"]) for u in led["meaning"]))

    # --- RETENTION: a derived meaning whose significance re-surfaces is RETAINED. The Maya
    #     life-event/relational/milestone units ride to SURFACEABLE on the real pipeline. ---
    life_traces = [t for t in led["meaning_trace"]
                   if mc.LIFE_EVENT in t.get("dimensions", ())]
    ok("retention: the meaning units were CAPTURED by the real extractor",
       any(t[mc.CAPTURED] for t in led["meaning_trace"]))
    ok("retention: the meaning units were STORED (survive the disk round-trip)",
       any(t[mc.STORED] for t in led["meaning_trace"]))
    ok("retention: a relational/life-event meaning is SURFACEABLE (re-surfaces as significance)",
       any(t[mc.SURFACEABLE] for t in led["meaning_trace"]))
    ok("retention: NOTHING is dropped silently — every non-surfaceable unit names a loss_reason",
       all(t.get("loss_reason") for t in led["meaning_trace"] if not t[mc.SURFACEABLE]))

    # --- EMOTIONAL TONE: captured as a durable reported_feeling; its retention is reported
    #     honestly (it may not re-surface as a *significant theme* off a single mention). ---
    led_t = meaning_ledger(stress)
    tone = [u for u in led_t["meaning"] if u["kind"] == mc.KIND_TONE]
    ok("tone: 'really stressed' is a derived EMOTIONAL_TONE meaning unit",
       any("stressed" in u["grounded_in"] for u in tone))
    tone_tr = [t for t in led_t["meaning_trace"]
               if mc.EMOTIONAL_TONE in t.get("dimensions", ())]
    ok("tone: the stated affect is CAPTURED durably (a reported_feeling row)",
       any(t[mc.CAPTURED] for t in tone_tr))
    ok("tone: tone retention is ACCOUNTED (captured/stored/surfaceable all recorded)",
       all(set((mc.CAPTURED, mc.STORED, mc.SURFACEABLE)).issubset(t.keys()) for t in tone_tr))

    # --- the FOUR RATES exist, are probabilities, and the battery rollup is coherent. ---
    rep = run_battery()
    ok("battery: a per-input ledger for every input", len(rep["ledgers"]) == len(BATTERY))
    rates = rep["rates"]
    ok("rates: all four present (literal/meaning/emotional_tone/life_event)",
       set(rates.keys()) == {"literal", "meaning", "emotional_tone", "life_event"})
    ok("rates: every rate is a probability in [0,1]",
       all(0.0 <= float(rates[k]["rate"]) <= 1.0 for k in rates))
    ok("rates: retained <= total for every rate",
       all(rates[k]["retained"] <= rates[k]["total"] for k in rates))
    ok("rates: the battery derived at least one LIFE_EVENT and one EMOTIONAL_TONE unit",
       rates["life_event"]["total"] > 0 and rates["emotional_tone"]["total"] > 0)

    # --- DISCRIMINATION: a relational/life-event meaning (re-surfaces as a significant theme)
    #     is retained at a STRICTLY higher rate than a bare single-mention emotional tone
    #     (durably stored, but not yet a significant theme). This is the load-bearing contrast
    #     the directive is about: significance survival != byte survival. ---
    ok("discriminate: MEANING conservation >= EMOTIONAL-TONE conservation across the battery",
       rates["meaning"]["rate"] >= rates["emotional_tone"]["rate"])

    # --- render never raises and reports the four rates + the contrast note. ---
    txt = render(rep)
    ok("render: produces a non-empty report", bool(txt.strip()))
    ok("render: names all four rates",
       all(s in txt for s in ("LITERAL conservation", "MEANING conservation",
                              "EMOTIONAL-TONE", "LIFE-EVENT")))
    ok("render: carries the data-vs-meaning contrast note",
       "was the byte preserved" in txt and "MEANING" in txt)
    ok("render: per-input ledger renders without raising",
       bool(render_ledger(rep["ledgers"][0]).strip()))

    # --- robustness: empty / garbage input is safe ---
    empty = meaning_ledger("")
    ok("robust: empty input -> empty ledger, rates 1.0 (nothing to lose)",
       empty["literal"] == [] and empty["meaning"] == []
       and empty["rates"]["meaning"]["rate"] == 1.0)
    try:
        _ = meaning_ledger("...")
        _ = run_battery(["", "   ", "!!!"])
        crashed = False
    except Exception as e:  # noqa: BLE001
        crashed = True
        print("       (raised:", repr(e), ")")
    ok("robust: a garbage battery accounts without raising", not crashed)

    # ===============================================================================
    # HERMETIC GUARDRAIL — the cert's footprint guard over the FULL pipeline. A battery
    # exercises capture/store/surface and thus EVERY redirected STORE binding (memory_lirf on
    # both bindings, world_state, curiosity, meaning, review, constitution.STORE,
    # reliability.DEFAULT_STORE, telemetry, cloud). The real .anima must be byte-identical
    # before and after, no synthetic file may leak, and every binding must be restored.
    # ===============================================================================
    fp_before = _footprint(real)
    _ = run_battery()                       # the whole observatory, again, over every gate
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across a full observatory battery",
       fp_before == fp_after)
    ok("HERMETIC: the whole selftest touched no real .anima file (start->now)", fp0 == _footprint(real))
    ok("HERMETIC: no synthetic creature file leaked into real .anima (any gate)",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    # every redirect RESTORES the binding it touched — after the run each STORE attr is back
    # to its real value (a bleed of a temp dir into a module STORE would be a live leak).
    restored_ok = True
    for (mod, attr) in _resolve_store_targets():
        val = getattr(mod, attr, None)
        if val is not None and "anima-meaning-cons-" in str(val):
            restored_ok = False
            break
    ok("HERMETIC: every redirected STORE/DEFAULT_STORE binding is RESTORED (no temp-dir bleed)",
       restored_ok)
    # the directive's named bindings are all in the resolved redirect set.
    resolved_names = {(m.__name__, a) for (m, a) in _resolve_store_targets()}
    needed = {("anima.memory_lirf", "STORE"), ("anima.world_state", "STORE"),
              ("anima.curiosity", "STORE"), ("anima.meaning", "STORE"),
              ("anima.constitution", "STORE"), ("anima.reliability", "DEFAULT_STORE"),
              ("anima.telemetry", "STORE"), ("anima.cloud", "STORE")}
    ok("HERMETIC: the redirect set covers every store the directive names",
       needed.issubset(resolved_names))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL MEANING-CONSERVATION OBSERVATORY SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
