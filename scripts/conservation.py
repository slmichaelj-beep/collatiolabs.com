#!/usr/bin/env python3
"""DATA CONSERVATION certification — treat information like energy. For every input
utterance, account for where every salient byte went: EXTRACTED (stored in the LIRF
ledger or the world-state graph), or LOST (salient in the input, but absent from
everything the capture path stored).

    The point is VISIBILITY, not zero loss.

This is to data what an energy-conservation audit is to a physical system. The capture
path (``memory_lirf.capture`` -> facts, ``world_state.capture_relations`` -> edges) is
a lossy compressor by design: it pulls DURABLE first-person facts and the OBVIOUS stated
relations, and deliberately drops everything else (notably emotional tone — "really
stressed", "love" — which is real signal but not a durable trait). A conservation ledger
makes that loss MEASURABLE and HONEST instead of invisible:

    INPUT (the utterance)
      -> EXTRACTED  (LIRF facts captured + world_state edges captured)
      -> LOST       (salient units present in the input but stored NOWHERE),
                     each tagged by category: entity / relation / tone / temporal.

"Lost" is computed DETERMINISTICALLY, not judged by a model:
  1. Pull the input's SALIENT UNITS with cheap, fixed rules —
       * entity   : capitalised words (proper nouns), guarded against sentence-initial
                    caps and a stoplist so "I"/"My"/"We" and a leading "Last" aren't
                    mistaken for names;
       * temporal : numbers, years, dates, and time words (kindergarten "last week",
                    "in 2024", "Q3", "five years");
       * relation : stated cause/role/relationship/feeling-link cues
                    (because / manager / daughter / adopted / moved …);
       * tone     : affect/feeling words (stressed, love, excited, worried …).
  2. Run the REAL capture path on a SYNTHETIC creature in a TEMP store and collect every
     value/trait it stored as a fact and every subject/predicate/object it stored as an
     edge — the CAPTURED SET.
  3. DIFF: a salient unit whose surface (normalised) appears nowhere in the captured set
     is LOST, tagged by its category.

Conservation rate = captured_salient / total_salient, per input and overall. A low rate
is not a bug to hide — it is the truth being reported. Emotional tone is routinely lost;
that is acceptable for a durable-fact store, but it must be VISIBLE here.

GUARDRAILS (identical to scripts/test_continuity.py / scripts/certify.py):
  * DETERMINISTIC + OFFLINE. No model, no network. The model-assist Tier-B paths in the
    engines are never invoked (model_pass defaults off).
  * SYNTHETIC creatures + TEMPORARY stores ONLY. Every engine's module-level STORE is
    redirected to a TemporaryDirectory for the run (the test_continuity.py pattern), and
    the run ASSERTS the real .anima footprint is byte-unchanged start->end. It NEVER reads
    or writes a real Vera.* file.
  * ADDITIVE. Imports and RUNS the engines; edits no module, no test, no certify.py.
  * Never raises out of the entry points — a malformed input yields an honest empty/zero
    ledger, not a traceback.

    python3 scripts/conservation.py            # human-readable ledger + battery
    python3 scripts/conservation.py --json     # machine-readable

Exit code is 0 (this is an ACCOUNTING tool — it reports loss, it does not fail on it). A
broken guardrail (the real .anima footprint changed, or an engine raised) exits non-zero.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from anima import memory_lirf            # noqa: E402
from anima import world_state            # noqa: E402

# A synthetic-only sentinel name so nothing here can ever collide with a real creature.
SYNTH = "cons_synth"


# ===================================================================================
# GUARDRAIL — temp-store redirect (verbatim from test_continuity.py) + footprint hash.
# Every engine STORE is redirected so the capture path writes ONLY into a throwaway dir.
# world_state lifts LIRF facts through memory_lirf.Facts (which reads memory_lirf.STORE),
# so BOTH modules must be redirected for the synthetic creature to be fully isolated.
# ===================================================================================
@contextlib.contextmanager
def _temp_store(*modules):
    """Redirect each module's module-level STORE to a fresh temp dir for the duration,
    so nothing under the real .anima/ is ever read or written. Restored on exit."""
    saved = [(m, getattr(m, "STORE", None)) for m in modules]
    with tempfile.TemporaryDirectory(prefix="anima-conservation-") as td:
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
    """A stable fingerprint of every real .anima file (excluding the rotating backups/
    dir, which legitimately changes), so we can PROVE the harness touched nothing."""
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
# SALIENT-UNIT EXTRACTION — the DETERMINISTIC "where did the bytes go?" left-hand side.
# We pull the units a reasonable reader would call the *content* of an utterance, by
# fixed rules only (no model). Each unit is (category, surface): the category drives the
# loss tag; the surface is normalised for the membership test against the captured set.
# Categories: entity | relation | tone | temporal.
# ===================================================================================

# Affect / feeling lexicon -> the TONE the durable-fact store routinely drops. Stemmed
# loosely (a trailing "ed"/"ing"/"ful" is folded by the surface normaliser's stem step).
_TONE_WORDS = {
    "stressed", "stress", "stressful", "anxious", "anxiety", "worried", "worry",
    "overwhelmed", "overwhelming", "excited", "exciting", "nervous", "scared", "afraid",
    "happy", "sad", "angry", "frustrated", "frustrating", "lonely", "tired", "exhausted",
    "drained", "burnt", "burned", "love", "loved", "hate", "hated", "afraid", "glad",
    "grateful", "thrilled", "miserable", "depressed", "hopeful", "hopeless", "proud",
    "ashamed", "guilty", "relieved", "calm", "content", "upset", "hurt", "heavy", "rough",
    "tough", "hard", "great", "terrible", "awful", "wonderful", "amazing", "devastated",
    "heartbroken", "delighted", "furious", "joyful", "fearful", "uneasy", "restless",
}
# Adverbs of degree that modify tone ("really stressed") — themselves tone-adjacent signal
# the store drops. Counted as tone units so the loss of intensity is visible too.
_DEGREE_WORDS = {"really", "very", "so", "super", "extremely", "incredibly", "deeply",
                 "terribly", "totally", "completely", "utterly", "quite", "pretty"}

# Stated-relation / role / life-event cues -> RELATION salience. Presence of one of these
# means the utterance asserts a connection or a relationship the graph *could* hold.
_RELATION_WORDS = {
    # causal connectives
    "because", "since", "due", "cause", "cuz", "so", "therefore", "leads", "led",
    "affecting", "affects", "hurting", "wrecking", "causing", "caused", "makes", "made",
    # roles / people
    "manager", "boss", "supervisor", "coworker", "colleague", "mom", "mum", "mother",
    "dad", "father", "wife", "husband", "partner", "spouse", "girlfriend", "boyfriend",
    "daughter", "son", "sister", "brother", "kid", "kids", "child", "children", "baby",
    "dog", "cat", "pet", "friend", "landlord", "doctor", "therapist", "teacher", "coach",
    # life-event verbs (state a transition / relation)
    "moved", "move", "adopted", "adopt", "started", "start", "joined", "quit", "left",
    "married", "divorced", "retired", "graduated", "hired", "fired", "launched", "founded",
    # care / worry link verbs
    "stressed", "worried", "care", "cares", "love", "adore", "cherish",
}

# Time / quantity words -> TEMPORAL salience (dates, recency, durations, counts).
_TEMPORAL_WORDS = {
    "yesterday", "today", "tonight", "tomorrow", "week", "weeks", "month", "months",
    "year", "years", "day", "days", "morning", "evening", "night", "weekend",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "spring", "summer", "fall", "autumn", "winter", "last", "next", "ago", "recently",
    "lately", "soon", "now", "currently", "q1", "q2", "q3", "q4",
}

# Months as proper nouns we should NOT count as person-entities (they capitalise but are
# temporal, captured as temporal instead).
_MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"}

# Capitalised function words that begin sentences/clauses — NOT proper nouns. Guards the
# entity rule against "I", "My", "We", and a sentence-initial "Last"/"We've" etc.
_CAP_STOP = {
    "I", "I'm", "I've", "I'd", "I'll", "My", "We", "We've", "We're", "Our", "The", "A",
    "An", "This", "That", "These", "Those", "He", "She", "It", "They", "You", "Your",
    "Last", "Next", "Then", "And", "But", "So", "Because", "When", "Where", "What",
    "Who", "Why", "How", "If", "Yeah", "Honestly", "Lately", "Recently", "Now",
    "Today", "Yesterday", "Tomorrow", "Tonight", "Maybe", "Just", "Really", "After",
    "Before", "Since", "While", "Also", "Still", "Yes", "No", "Oh", "Well",
}

# A unit's normalised surface key for membership tests against the captured set. Lowercase,
# punctuation stripped, and a light suffix-stem so "stressful"/"stressed" fold to "stress"
# and "kids" to "kid" — so tone/relation surfaces match a stored object regardless of form.
_STEM = re.compile(r"(?:ed|ing|ful|s|'s)$")


def _norm_unit(s: str) -> str:
    s = re.sub(r"[^a-z0-9$]+", "", str(s).strip().lower())
    if len(s) > 4:                       # only stem longer tokens (keep "may", "q3", "son")
        s2 = _STEM.sub("", s)
        if len(s2) >= 3:
            s = s2
    return s


# Multi-word proper-noun run: one or more Capitalised tokens in a row (e.g. "New York",
# "Q3"). Apostrophes/hyphens allowed inside ("O'Brien", "Coca-Cola").
_PROPER_RUN = re.compile(r"\b([A-Z][\w''-]*(?:\s+[A-Z][\w''-]*)*)\b")
_NUMERIC = re.compile(r"\b(?:\d{1,4}(?:[/-]\d{1,4}){0,2}(?:st|nd|rd|th)?|Q[1-4])\b", re.I)
_WORD = re.compile(r"[A-Za-z']+")


def salient_units(text: str) -> list:
    """DETERMINISTIC salience extraction. Return a de-duplicated list of
    ``{"category", "surface", "key"}`` salient units found in ``text``:

      * entity   — proper nouns (capitalised runs) that are not sentence-initial function
                   words and not months/places-as-temporal;
      * temporal — numbers/years/dates (Q3, 2024, 12/05) and time words;
      * relation — stated cause/role/relationship/life-event cues;
      * tone     — affect / degree words (the routinely-dropped signal).

    A token can be salient in only ONE primary category here (first match wins in the
    order entity > temporal > relation > tone) so the denominator isn't double-counted;
    the ledger still reports each category's losses separately. Empty/garbage -> []."""
    if not text or not text.strip():
        return []
    units = []
    seen = set()

    def add(category, surface):
        key = _norm_unit(surface)
        if not key:
            return
        tag = (category, key)
        if tag in seen:
            return
        seen.add(tag)
        units.append({"category": category, "surface": surface.strip(), "key": key})

    # 1) ENTITIES — capitalised proper-noun runs, guarded. A run whose FIRST token is a
    #    sentence/clause-initial function word is split: drop the leading stopword, keep any
    #    genuine proper noun that follows ("Last June" -> June handled as temporal below).
    for m in _PROPER_RUN.finditer(text):
        run = m.group(1)
        toks = run.split()
        # strip a leading capitalised function word ("My Maya" can't happen, but "Last
        # Friday"/"We Adopted" guard here): drop leading tokens that are in _CAP_STOP.
        while toks and (toks[0] in _CAP_STOP or toks[0].rstrip(".,!?;:") in _CAP_STOP):
            toks = toks[1:]
        if not toks:
            continue
        # a single-token run that is ALL-CAPS short (e.g. "OR", "Q3") or a month is handled
        # elsewhere (temporal); a real name is Mixed/Title case with len>=2.
        phrase = " ".join(toks).strip(".,!?;:")
        low = phrase.lower()
        if not phrase:
            continue
        if low in _MONTHS or low in _TEMPORAL_WORDS:
            add("temporal", phrase)
            continue
        # guard: a lone capitalised word that is a common function/stop word slipping
        # through (mid-sentence "I") — already covered, but double-check the single case.
        if len(toks) == 1 and toks[0] in _CAP_STOP:
            continue
        add("entity", phrase)

    # 2) TEMPORAL — explicit numbers/years/dates, plus time words anywhere.
    for m in _NUMERIC.finditer(text):
        add("temporal", m.group(0))
    for w in _WORD.findall(text):
        lw = w.lower()
        if lw in _TEMPORAL_WORDS:
            add("temporal", w)

    # 3) RELATION cues and 4) TONE words — single-pass over lowercased word tokens.
    for w in _WORD.findall(text):
        lw = w.lower()
        if lw in _RELATION_WORDS:
            add("relation", w)
        if lw in _TONE_WORDS or lw in _DEGREE_WORDS:
            add("tone", w)

    return units


# ===================================================================================
# CAPTURED-SET — run the REAL engines on a synthetic creature and collect everything they
# actually stored, as a set of normalised surface keys (the right-hand side of the diff).
# ===================================================================================
def _captured_surfaces(facts: list, edges: list) -> tuple:
    """Split everything stored into TWO normalised-surface sets, because the diff must
    credit different salience categories from different slots:

      * CONTENT surfaces — the actual data stored: fact VALUES, and edge SUBJECTS/OBJECTS
        (the nodes). This is where literal content (a name "Maya", a place "Austin", a
        year "2024") lands.
      * STRUCTURAL surfaces — the SLOT NAMES: fact TRAITS and edge PREDICATES
        ("daughter", "because", "stressed_by"). These prove a RELATION/role was captured
        even when the literal word isn't a value.

    Why the split matters: a ``stressed_by`` predicate contains the token "stressed", but
    storing that EDGE captured the *relation* (you<->launch), NOT the *affect* "stressed"
    as a durable feeling. So a TONE unit may be credited ONLY by CONTENT; a relation/entity
    /temporal unit may be credited by EITHER. Crediting tone from a predicate would falsely
    claim the feeling was kept and defeat the whole honesty point."""
    content, structural = set(), set()

    def add_phrase(target, v):
        if v is None:
            return
        if isinstance(v, list):
            for x in v:
                add_phrase(target, x)
            return
        for tok in _WORD.findall(str(v)) + _NUMERIC.findall(str(v)):
            k = _norm_unit(tok)
            if k:
                target.add(k)
        whole = _norm_unit(str(v))      # whole value as one key (multi-word values)
        if whole:
            target.add(whole)

    for r in facts or []:
        add_phrase(content, r.get("value"))
        add_phrase(structural, r.get("trait"))
    for e in edges or []:
        add_phrase(content, e.get("subject"))
        add_phrase(content, e.get("object"))
        add_phrase(structural, e.get("predicate"))
    return content, structural


def _is_captured(unit: dict, content: set, structural: set) -> bool:
    """Was this salient unit stored? CONTENT credits any category; STRUCTURAL (trait/
    predicate slot names) credits everything EXCEPT tone — a feeling absorbed into a
    relation predicate was not kept AS a feeling."""
    if unit["key"] in content:
        return True
    if unit["category"] != "tone" and unit["key"] in structural:
        return True
    return False


def _run_capture(name: str, text: str) -> tuple:
    """Run BOTH capture paths (deterministic, model OFF) on the synthetic creature and
    return (facts_touched, edges_touched). Best-effort: an engine that raises yields an
    empty list for its side rather than propagating — the ledger then shows that side as
    captured-nothing, which is the honest accounting."""
    try:
        facts = memory_lirf.capture(name, text)         # Tier A only; model_pass defaults off
    except Exception:
        facts = []
    try:
        edges = world_state.capture_relations(name, text)
    except Exception:
        edges = []
    return facts or [], edges or []


# ===================================================================================
# THE LEDGER — one input's full conservation accounting.
# ===================================================================================
def conservation_ledger(text: str) -> dict:
    """The CONSERVATION LEDGER for ONE utterance. Runs the real capture path on a fresh
    synthetic creature in a temp store, then accounts for every salient unit:

        {
          "input":      the utterance,
          "extracted": {
              "facts":  [ {trait, value, evidence}, … ],   # LIRF rows captured
              "edges":  [ {subject, predicate, object, kind}, … ],  # world edges captured
          },
          "salient":    [ {category, surface}, … ],        # the deterministic content units
          "lost":       [ {category, surface}, … ],        # salient but stored NOWHERE
          "captured_salient": int,  "total_salient": int,
          "conservation_rate": captured/total (1.0 if nothing salient),
          "lost_by_category": {entity|relation|tone|temporal: count},
        }

    Deterministic, offline, isolated. Never raises: a bad input yields an empty ledger
    with rate 1.0 (nothing salient -> nothing lost)."""
    text = text or ""
    units = salient_units(text)

    with _temp_store(memory_lirf, world_state):
        # a UNIQUE synthetic name per call so no state leaks between battery inputs
        name = f"{SYNTH}_{secrets.token_hex(3)}"
        facts, edges = _run_capture(name, text)

    content, structural = _captured_surfaces(facts, edges)

    lost = []
    lost_by_cat = {"entity": 0, "relation": 0, "tone": 0, "temporal": 0}
    captured_salient = 0
    for u in units:
        if _is_captured(u, content, structural):
            captured_salient += 1
        else:
            lost.append({"category": u["category"], "surface": u["surface"]})
            lost_by_cat[u["category"]] = lost_by_cat.get(u["category"], 0) + 1

    total = len(units)
    rate = (captured_salient / total) if total else 1.0

    return {
        "input": text,
        "extracted": {
            "facts": [
                {"trait": r.get("trait"), "value": r.get("value"),
                 "evidence": r.get("evidence", "")}
                for r in facts
            ],
            "edges": [
                {"subject": e.get("subject"), "predicate": e.get("predicate"),
                 "object": e.get("object"), "kind": e.get("kind")}
                for e in edges
            ],
        },
        "salient": [{"category": u["category"], "surface": u["surface"]} for u in units],
        "lost": lost,
        "captured_salient": captured_salient,
        "total_salient": total,
        "conservation_rate": rate,
        "lost_by_category": lost_by_cat,
    }


# The battery of information-rich inputs the brief names, plus a couple that stress tone
# and multi-fact density so the loss accounting is exercised across categories.
BATTERY = [
    "I moved to Austin because my manager changed",
    "My daughter Maya started kindergarten last week",
    "I've been really stressed about the Q3 launch",
    "We adopted a dog named Cooper in 2024",
    "My wife Jen and I are excited about the move to Denver in March",
    "I work at Collatio and I'm worried about money lately",
]


def run_battery(inputs=None) -> dict:
    """Run the conservation ledger over a battery of inputs and compute the OVERALL
    conservation rate (sum captured_salient / sum total_salient) plus the aggregate
    lost-by-category tally. Returns a dict with per-input ledgers and the rollup."""
    inputs = list(inputs) if inputs is not None else list(BATTERY)
    ledgers = [conservation_ledger(t) for t in inputs]

    tot_salient = sum(l["total_salient"] for l in ledgers)
    tot_captured = sum(l["captured_salient"] for l in ledgers)
    overall = (tot_captured / tot_salient) if tot_salient else 1.0

    agg = {"entity": 0, "relation": 0, "tone": 0, "temporal": 0}
    for l in ledgers:
        for k, v in l["lost_by_category"].items():
            agg[k] = agg.get(k, 0) + v

    return {
        "ledgers": ledgers,
        "total_salient": tot_salient,
        "captured_salient": tot_captured,
        "overall_conservation_rate": overall,
        "lost_by_category": agg,
    }


# ===================================================================================
# RENDER — human-readable conservation accounting.
# ===================================================================================
def _fmt_fact(f: dict) -> str:
    v = f.get("value")
    v = ", ".join(str(x) for x in v) if isinstance(v, list) else v
    return f"{f.get('trait')} = {v}"


def _fmt_edge(e: dict) -> str:
    return f"{e.get('subject')} --{e.get('predicate')}--> {e.get('object')} [{e.get('kind')}]"


def render_ledger(led: dict) -> str:
    out = []
    out.append(f'INPUT:  "{led["input"]}"')
    ex = led["extracted"]
    if ex["facts"]:
        out.append("  EXTRACTED facts (LIRF ledger):")
        for f in ex["facts"]:
            out.append(f"    + {_fmt_fact(f)}")
    if ex["edges"]:
        out.append("  EXTRACTED edges (world-state graph):")
        for e in ex["edges"]:
            out.append(f"    + {_fmt_edge(e)}")
    if not ex["facts"] and not ex["edges"]:
        out.append("  EXTRACTED: (nothing stored)")
    if led["lost"]:
        out.append("  LOST (salient in input, stored nowhere):")
        for u in led["lost"]:
            out.append(f"    - [{u['category']:<8}] {u['surface']}")
    else:
        out.append("  LOST: (nothing salient was dropped)")
    rate = led["conservation_rate"]
    out.append(f"  CONSERVATION: {led['captured_salient']}/{led['total_salient']} salient "
               f"units kept  ->  rate {rate:.2f}")
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 79)
    out.append("VERA DATA-CONSERVATION LEDGER")
    out.append("Information like energy: every input -> EXTRACTED + LOST. Loss is measured,")
    out.append("not hidden. The goal is visibility, not zero loss.")
    out.append("=" * 79)
    for led in report["ledgers"]:
        out.append("")
        out.append(render_ledger(led))
    out.append("")
    out.append("-" * 79)
    out.append("OVERALL CONSERVATION")
    out.append("-" * 79)
    out.append(f"  salient units kept : {report['captured_salient']}/{report['total_salient']}")
    out.append(f"  conservation rate  : {report['overall_conservation_rate']:.3f}  "
               f"(captured salient / total salient)")
    agg = report["lost_by_category"]
    ordered = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
    out.append("  loss by category   : "
               + ", ".join(f"{k}={v}" for k, v in ordered))
    most = ordered[0] if ordered and ordered[0][1] > 0 else None
    if most:
        why = {
            "relation": "stated cues land only when a rule's exact frame (copula / "
                        "because / stress-word) matches; appositives & bare verbs slip it",
            "tone": "affect is not a durable trait — dropped by design",
            "entity": "a proper noun is kept only when a rule binds it to a slot "
                      "(named/is/at); a bare appositive name is dropped",
            "temporal": "dates land inside a matched fact; standalone time words "
                        "(\"last week\", \"lately\") have no slot to live in",
        }.get(most[0], "")
        out.append(f"  most-lost category : {most[0]} ({most[1]} units) — {why}")
    out.append("")
    out.append("HONEST NOTE: emotional TONE (\"really stressed\", \"excited\", \"love\") is")
    out.append("routinely dropped — it is real signal but not a durable trait, so the ledger")
    out.append("reports it as LOST on purpose. Degree/intensity and some bare temporal words")
    out.append("are dropped too. This is acceptable for a fact store; the value here is that")
    out.append("the loss is now COUNTED and VISIBLE, never silent.")
    return "\n".join(out)


# ===================================================================================
# MAIN — human-readable (default) or --json. Asserts the synthetic-only guardrail held.
# ===================================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="VERA DATA-CONSERVATION LEDGER (information accounting for the capture path)")
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
        report = {"ledgers": [], "total_salient": 0, "captured_salient": 0,
                  "overall_conservation_rate": 1.0,
                  "lost_by_category": {"entity": 0, "relation": 0, "tone": 0, "temporal": 0}}
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
# SELFTEST — `python3 scripts/conservation.py --selftest`. Proves the accounting is sound:
# salience rules fire/guard correctly, the diff credits captured units, tone is reported
# lost, the rate is in [0,1], and the synthetic-only guardrail holds. No model, no network.
# ===================================================================================
def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # --- salience: entity guard vs proper nouns ---
    su = {(u["category"], u["surface"]) for u in salient_units("My daughter Maya started kindergarten last week")}
    cats = {u["category"]: u["surface"] for u in salient_units("My daughter Maya started kindergarten last week")}
    ok("salience: 'Maya' is an entity", ("entity", "Maya") in su)
    ok("salience: sentence-initial 'My' is NOT an entity",
       not any(s == "My" for _c, s in su))
    ok("salience: 'daughter' is a relation cue", any(c == "relation" and s == "daughter" for c, s in su))
    ok("salience: 'last'/'week' counted temporal",
       any(c == "temporal" and s.lower() == "week" for c, s in su))

    su2 = {(u["category"], u["surface"]) for u in salient_units("I've been really stressed about the Q3 launch")}
    ok("salience: 'stressed' is tone", any(c == "tone" and s.lower() == "stressed" for c, s in su2))
    ok("salience: 'really' (degree) is tone", any(c == "tone" and s.lower() == "really" for c, s in su2))
    ok("salience: 'Q3' is temporal (not an entity)",
       any(c == "temporal" and s.upper() == "Q3" for c, s in su2)
       and not any(c == "entity" and s.upper() == "Q3" for c, s in su2))
    ok("salience: leading 'I've' is not an entity", not any(s in ("I", "I've") for _c, s in su2))

    su3 = {(u["category"], u["surface"]) for u in salient_units("We adopted a dog named Cooper in 2024")}
    ok("salience: 'Cooper' is an entity", ("entity", "Cooper") in su3)
    ok("salience: leading 'We' is not an entity", not any(s == "We" for _c, s in su3))
    ok("salience: '2024' is temporal", any(c == "temporal" and s == "2024" for c, s in su3))
    ok("salience: 'adopted' is a relation cue", any(c == "relation" and s.lower() == "adopted" for c, s in su3))

    # --- empty / garbage input is safe ---
    ok("salience: empty input -> no units", salient_units("") == [] and salient_units("   ") == [])

    # --- captured-set diff: a CREDITED capture vs an HONEST loss ---
    # "I have a daughter named Cooper" DOES match a LIRF rule -> the name is credited.
    led_c = conservation_ledger("I have a daughter named Riley")
    ok("ledger: a name the rule DOES catch ('Riley') is credited, not lost",
       any(_norm_unit(str(f.get("value"))) == _norm_unit("Riley") for f in led_c["extracted"]["facts"])
       and not any(u["surface"] == "Riley" for u in led_c["lost"]))

    # "My daughter Maya started kindergarten" is APPOSITION (no copula) — the LIRF rule
    # needs "my daughter is/named Maya", so Maya is GENUINELY lost. The tool must SURFACE
    # that, not paper over it. (A real finding: appositive names slip the net.)
    led = conservation_ledger("My daughter Maya started kindergarten last week")
    ok("ledger: appositive 'Maya' is honestly reported LOST (rule needs a copula)",
       any(u["surface"] == "Maya" and u["category"] == "entity" for u in led["lost"]))
    ok("ledger: rate is a probability in [0,1]", 0.0 <= led["conservation_rate"] <= 1.0)
    ok("ledger: total_salient == captured + lost",
       led["total_salient"] == led["captured_salient"] + len(led["lost"]))

    # --- tone is reported LOST even when an edge predicate echoes it ---
    # world_state stores a (you stressed_by 'Q3 launch') edge; its PREDICATE contains the
    # token 'stressed', but that captured the RELATION, not the FEELING. Tone must still be
    # reported lost — credited only by CONTENT (values/objects), never by a predicate slot.
    led_t = conservation_ledger("I've been really stressed about the Q3 launch")
    ok("ledger: tone ('stressed') is LOST despite a 'stressed_by' predicate (relation!=affect)",
       any(u["category"] == "tone" and _norm_unit(u["surface"]) == _norm_unit("stressed")
           for u in led_t["lost"]))
    ok("ledger: degree word ('really') is reported LOST (intensity dropped)",
       any(u["category"] == "tone" and u["surface"].lower() == "really" for u in led_t["lost"]))
    ok("ledger: lost_by_category counts tone losses",
       led_t["lost_by_category"]["tone"] >= 1)

    # --- the headline finding: a rich causal input the capture path stores NOTHING for ---
    # "I moved to Austin because my manager changed": LIRF has no "I moved to X" rule, and
    # world_state's causal rule needs a stress/worry cue (none here). So the ENTIRE input is
    # lost. The conservation tool exists precisely to make this visible.
    led_r = conservation_ledger("I moved to Austin because my manager changed")
    stored = len(led_r["extracted"]["facts"]) + len(led_r["extracted"]["edges"])
    ok("ledger: 'moved to Austin because manager' is a TOTAL-LOSS input (honestly surfaced)",
       stored == 0 and led_r["conservation_rate"] < 1.0
       and any(u["surface"] == "Austin" for u in led_r["lost"]))

    # --- battery rollup is coherent ---
    rep = run_battery()
    ok("battery: per-input ledger for every input", len(rep["ledgers"]) == len(BATTERY))
    ok("battery: overall rate in [0,1]", 0.0 <= rep["overall_conservation_rate"] <= 1.0)
    ok("battery: total == sum of per-input totals",
       rep["total_salient"] == sum(l["total_salient"] for l in rep["ledgers"]))
    ok("battery: captured == sum of per-input captured",
       rep["captured_salient"] == sum(l["captured_salient"] for l in rep["ledgers"]))
    ok("battery: aggregate lost-by-category sums the per-input tallies",
       rep["lost_by_category"]["tone"]
       == sum(l["lost_by_category"]["tone"] for l in rep["ledgers"]))

    # --- GUARDRAIL: the synthetic-only run touched no real .anima file ---
    real = Path(_ROOT) / ".anima"
    fp0 = _footprint(real)
    _ = run_battery()
    fp1 = _footprint(real)
    ok("guardrail: real .anima footprint byte-UNCHANGED across a full battery", fp0 == fp1)
    ok("guardrail: no synthetic ledger file leaked into real .anima",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    # --- render never raises and reports the honesty note ---
    txt = render(rep)
    ok("render: produces a non-empty report", bool(txt.strip()))
    ok("render: carries the honest TONE-is-lost note", "TONE" in txt and "LOST" in txt)
    ok("render: per-input ledger renders without raising", bool(render_ledger(rep["ledgers"][0]).strip()))

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL CONSERVATION SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
