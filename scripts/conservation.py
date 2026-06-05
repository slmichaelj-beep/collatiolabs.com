#!/usr/bin/env python3
"""CONSERVATION OBSERVATORY (Phase 3C) — treat information like energy across the WHOLE
pipeline. NOTHING disappears silently: every stage's loss is measured AND attributed.

    The point is VISIBILITY, not zero loss.

This began as a per-INPUT ledger (input -> EXTRACTED -> LOST). That base is KEPT intact as
the Detected/Captured/Dropped foundation. The observatory extends it DOWN THE PIPELINE so a
salient unit is followed from the words to the reply, and the stage where it falls out is
named:

    DETECTED   (salient units a reasonable reader would call the *content* of the utterance)
      -> CAPTURED   (credited by the live capture path in memory — facts + world edges)
      -> STORED     (survives Facts.save/World.save and a reload FROM DISK)
      -> RETRIEVED  (resurfaces as a retrieval CANDIDATE — selected LIRF rows / Facts.block,
                     the world_state.situation() cluster, curiosity candidate gaps)
      -> USED        (actually lands in the assembled PROMPT block — spine.bind + the
                      Facts.block fallback + world_state.render_situation; the READ-ONLY
                      mouth signal)
      -> COMPRESSED  (its MEANING survives the nightly rollup — review.daily_review's
                      what_to_remember + descriptive dimensions; Compressed > Forgotten)
    DROPPED        (Detected but never Captured — the original "lost", attributed to a stage)

From those counts the observatory computes five explicit RATES (per battery):

    Capture Rate     detected  -> captured     (does the extractor SEE the salient unit?)
    Storage Rate     captured  -> stored        (does it SURVIVE persistence to disk?)
    Retrieval Rate   stored    -> retrieved     (can it be FETCHED back as a candidate?)
    Usage Rate       retrieved -> used          (does it make it into the PROMPT/reply?)
    Meaning Retention overall significance preserved end-to-end (meaning.significance over
                      the stored graph vs the salient signal that mattered)

and an END-TO-END RETENTION % (detected -> used) with a 95% TARGET verdict. The current
overall baseline is ~85%; the battery reports where it actually lands.

Everything is DETERMINISTIC, not model-judged:
  1. Pull the input's SALIENT UNITS with cheap, fixed rules —
       * entity   : capitalised words (proper nouns), guarded against sentence-initial
                    caps and a stoplist so "I"/"My"/"We" and a leading "Last" aren't
                    mistaken for names;
       * temporal : numbers, years, dates, and time words ("last week", "in 2024", "Q3");
       * relation : stated cause/role/relationship/life-event cues
                    (because / manager / daughter / adopted / moved …);
       * tone     : affect/feeling words (stressed, love, excited, worried …).
  2. Run the REAL pipeline on a SYNTHETIC creature in a TEMP store and, at each stage,
     collect the normalised surfaces that stage carries — the CAPTURED / STORED /
     RETRIEVED / USED sets.
  3. DIFF at every stage: a salient unit whose surface appears in a stage's set is KEPT
     there; one that doesn't is LOST AT THAT STAGE, tagged by its category. The stage that
     first loses a unit is the one credited with the drop.

A low rate is not a bug to hide — it is the truth being reported. Emotional tone is
routinely lost at CAPTURE (it is not a durable trait); that is acceptable, but it must be
VISIBLE and ATTRIBUTED here.

GUARDRAILS (identical to scripts/test_continuity.py / scripts/certify.py / experience.py):
  * DETERMINISTIC + OFFLINE. No model, no network. The model-assist Tier-B paths in the
    engines are never invoked (model_pass defaults off). The mouth/prompt signal is read
    WITHOUT a brain — only the deterministic binding blocks are assembled.
  * SYNTHETIC creatures + TEMPORARY stores ONLY. HERMETIC: every engine STORE the pipeline
    now writes is redirected to one TemporaryDirectory for the run — memory_lirf.STORE on
    BOTH the __main__ and package bindings, world_state.STORE, curiosity.STORE,
    constitution.STORE, reliability.DEFAULT_STORE, meaning.STORE, review.STORE — so a good
    Facts.load (which also writes a continuity ledger + a guarded backup) can never leak
    into the real .anima. The run ASSERTS the real .anima footprint is byte-unchanged
    start->end. It NEVER reads or writes a real Vera.* file.
  * ADDITIVE. Imports and RUNS the engines; edits no module, no test, no certify.py.
  * Never raises out of the entry points — a malformed input yields an honest empty/zero
    ledger, not a traceback.

    python3 scripts/conservation.py            # human-readable observatory + battery
    python3 scripts/conservation.py --json     # machine-readable
    python3 scripts/conservation.py --selftest # asserts stage accounting is conserved

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

# The downstream pipeline stages (retrieval / usage / compression / meaning). Imported
# best-effort: the base ledger never needs them, and a stage whose module won't import
# degrades to "credited-nothing" (the honest accounting) instead of crashing the tool.
try:                                     # noqa: E402
    from anima import curiosity as _curiosity
except Exception:                        # pragma: no cover - isolation
    _curiosity = None
try:                                     # noqa: E402
    from anima import meaning as _meaning
except Exception:                        # pragma: no cover - isolation
    _meaning = None
try:                                     # noqa: E402
    from anima import review as _review
except Exception:                        # pragma: no cover - isolation
    _review = None
try:                                     # noqa: E402
    from anima import spine as _spine
except Exception:                        # pragma: no cover - isolation
    _spine = None

# A synthetic-only sentinel name so nothing here can ever collide with a real creature.
SYNTH = "cons_synth"


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect + footprint hash. Mirrors the pattern in
# anima/memory_lirf.py _selftest (~lines 1316-1346) and scripts/experience.py: redirect
# EVERY module STORE the full pipeline now touches to ONE throwaway dir, so a good
# Facts.load (which ALSO writes a {name}.continuity.jsonl via constitution.STORE and a
# guarded backup via reliability.DEFAULT_STORE) can never leak into the real .anima.
#
# A redirect target is a (module, attr) pair because reliability's store attr is
# DEFAULT_STORE, not STORE. The set is resolved by NAME so importing this module never
# hard-depends on every downstream engine; a missing one is simply skipped.
# ===================================================================================

# (module-import-path, store-attribute-name) for every binding the pipeline may write.
_STORE_TARGETS = (
    ("anima.memory_lirf", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.review", "STORE"),
    ("anima.constitution", "STORE"),           # the continuity ledger a good load writes
    ("anima.reliability", "DEFAULT_STORE"),     # guarded-backup snapshots
)


def _resolve_store_targets():
    """Resolve ``_STORE_TARGETS`` to live ``(module, attr)`` pairs that actually carry the
    attribute right now. A module that won't import, or that lacks the attr, is skipped —
    so the redirect set adapts to whatever is built without ever hard-failing. Also pins the
    __main__ binding of this script's own ``memory_lirf``/``world_state`` imports (they are
    the SAME module objects as the package copies here, but resolving by name keeps the set
    correct even if that ever stops being true)."""
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
    ``STORE`` attr, so the original call-sites keep working while the full hermetic set is
    always applied. HERMETIC by construction: a leak is impossible regardless of which engine
    the pipeline ends up writing."""
    targets = _resolve_store_targets()
    for m in extra_modules:                      # honour legacy positional modules too
        if hasattr(m, "STORE") and (m, "STORE") not in targets:
            targets.append((m, "STORE"))
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-conservation-") as td:
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
# THE FULL PIPELINE — DETECTED -> CAPTURED -> STORED -> RETRIEVED -> USED -> COMPRESSED.
# Each stage produces a (content, structural) surface-set pair, scored against the same
# salient units by the same _is_captured rule the base ledger uses. The whole pipeline runs
# on ONE synthetic creature inside ONE hermetic temp store so every stage sees a consistent
# on-disk state and nothing leaks. Every stage is best-effort: an engine that raises yields
# empty sets for its side (that stage then shows captured-nothing — the honest accounting),
# never a traceback out of the tool.
# ===================================================================================

# The pipeline stages, in order. DROPPED is not a stage but the residual (Detected minus
# Captured); it is attributed to "capture" since that is where an un-captured unit fell out.
STAGES = ("detected", "captured", "stored", "retrieved", "used", "compressed")


def _row_surfaces(rows) -> tuple:
    """Split a list of LIRF row dicts into (content, structural) surface sets — fact VALUES
    are content, fact TRAITS are structural — reusing the base ledger's _captured_surfaces
    accounting so a row credits a unit identically wherever it appears in the pipeline."""
    return _captured_surfaces(rows or [], [])


def _edge_surfaces(edges) -> tuple:
    """Split a list of world-edge dicts into (content, structural) surface sets — edge
    SUBJECT/OBJECT are content, edge PREDICATE is structural."""
    return _captured_surfaces([], edges or [])


def _merge_surface_sets(*pairs) -> tuple:
    """Union several (content, structural) pairs into one (content, structural) pair."""
    content, structural = set(), set()
    for c, s in pairs:
        content |= (c or set())
        structural |= (s or set())
    return content, structural


def _surfaces_from_text(blob: str) -> set:
    """Every normalised surface key present in a free-text block (the assembled prompt). Used
    for the USED stage: a stored/retrieved unit is USED iff its surface literally appears in
    the prompt the mouth would assemble. Tokenised like the captured-set so the membership
    test is apples-to-apples."""
    out = set()
    if not blob:
        return out
    for tok in _WORD.findall(blob) + _NUMERIC.findall(blob):
        k = _norm_unit(tok)
        if k:
            out.add(k)
    return out


def _select_rows(name: str, text: str):
    """The LIRF rows a turn would RETRIEVE for this query — the router's selection when
    importable (the real retrieval path), else the full active ledger (the broad-query
    fallback the mouth itself uses). Read-only; [] on any failure."""
    try:
        from anima.organs.router import select_facts as _select_facts
        rows, _ = _select_facts(name, text)
        if rows is not None:
            return list(rows)
    except Exception:
        pass
    try:
        return list(memory_lirf.Facts.load(name).about())
    except Exception:
        return []


def _run_pipeline(name: str, text: str) -> dict:
    """Run the FULL pipeline for one utterance on the synthetic creature (already inside a
    hermetic temp store) and return the per-stage surface sets + the raw artefacts each stage
    produced. The caller diffs these against the salient units to attribute every loss.

    Returns a dict:
        {
          "captured":  {"facts": [...], "edges": [...], "content": set, "structural": set},
          "stored":    {"facts": [...], "edges": [...], "content": set, "structural": set},
          "retrieved": {"rows": [...], "cluster": {...}, "gaps": [...],
                        "content": set, "structural": set},
          "used":      {"prompt": str, "surfaces": set},
          "compressed":{"remember": [...], "surfaces": set, "review": {...}},
        }
    Every stage is guarded; a failure yields that stage's empty artefacts + empty sets.
    """
    out: dict = {}

    # --- CAPTURED — what the extractor SEES in memory (no persistence yet). LIRF candidates
    #     come from extract() (capture() without a merge), world edges from capture() too. ---
    try:
        cap_facts = memory_lirf.extract(text) or []
    except Exception:
        cap_facts = []
    try:
        cap_edge_tuples = world_state.capture(text) or []
        # capture() returns (subject, predicate, object, kind, topic) tuples — shape them as
        # edge dicts so the surface split sees the same fields the stored edges carry.
        cap_edges = [{"subject": s, "predicate": p, "object": o, "kind": k}
                     for (s, p, o, k, _t) in cap_edge_tuples]
    except Exception:
        cap_edges = []
    cap_content, cap_struct = _merge_surface_sets(_row_surfaces(cap_facts),
                                                  _edge_surfaces(cap_edges))
    out["captured"] = {"facts": cap_facts, "edges": cap_edges,
                       "content": cap_content, "structural": cap_struct}

    # --- STORED — actually persist and RELOAD FROM DISK. This is the real storage path:
    #     merge LIRF candidates + save; capture_relations persists world edges; then load the
    #     ledger and graph back and read what SURVIVED. A unit captured-in-memory but absent
    #     after a round-trip fell out at STORAGE. ---
    st_facts, st_edges = [], []
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
    try:
        st_facts = list(memory_lirf.Facts.load(name).about())
    except Exception:
        st_facts = []
    try:
        st_edges = list(world_state.World.load(name).active())
    except Exception:
        st_edges = []
    st_content, st_struct = _merge_surface_sets(_row_surfaces(st_facts),
                                                _edge_surfaces(st_edges))
    out["stored"] = {"facts": st_facts, "edges": st_edges,
                     "content": st_content, "structural": st_struct}

    # --- RETRIEVED — what resurfaces as a CANDIDATE for this query: the selected LIRF rows
    #     (router selection, or the full block fallback), the world_state.situation() cluster
    #     edges, and the curiosity candidate gaps (a gap proves the unit is still tracked as
    #     something to surface). A stored unit that no retrieval path returns fell out at
    #     RETRIEVAL. ---
    rt_rows = _select_rows(name, text)
    rt_cluster = {}
    try:
        rt_cluster = world_state.situation(name, text, hops=2) or {}
    except Exception:
        rt_cluster = {}
    rt_cluster_edges = [e for e in (rt_cluster.get("edges") or []) if isinstance(e, dict)]
    rt_gaps = []
    if _curiosity is not None:
        try:
            rt_gaps = list(_curiosity.candidate_gaps(name))
        except Exception:
            rt_gaps = []
    # gap surfaces: a gap names an entity/slot/trait/hint the unit lives under -> structural
    # so it can credit a relation/entity/temporal (never tone — a gap is not a feeling kept).
    gap_content, gap_struct = set(), set()
    for g in rt_gaps:
        if not isinstance(g, dict):
            continue
        for fld in ("entity", "slot", "trait"):
            for tok in _WORD.findall(str(g.get(fld) or "")):
                k = _norm_unit(tok)
                if k:
                    gap_struct.add(k)
        hint = (g.get("evidence") or {}).get("hint") if isinstance(g.get("evidence"), dict) else None
        for tok in _WORD.findall(str(hint or "")) + _NUMERIC.findall(str(hint or "")):
            k = _norm_unit(tok)
            if k:
                gap_content.add(k)
    rt_content, rt_struct = _merge_surface_sets(
        _row_surfaces(rt_rows), _edge_surfaces(rt_cluster_edges), (gap_content, gap_struct))
    out["retrieved"] = {"rows": rt_rows, "cluster": rt_cluster, "gaps": rt_gaps,
                        "content": rt_content, "structural": rt_struct}

    # --- USED — what actually lands in the assembled PROMPT block. This is the READ-ONLY
    #     mouth signal: NO brain, NO model — only the deterministic binding blocks the mouth
    #     assembles. spine.bind(selected rows, query) + the Facts.block() broad-query fallback
    #     (exactly the mouth's own fallback) + world_state.render_situation(cluster). A
    #     retrieved unit whose surface never appears in that prompt fell out at USAGE. ---
    prompt_parts = []
    if _spine is not None:
        try:
            fb = _spine.bind(rt_rows, text)
            if fb:
                prompt_parts.append(fb)
        except Exception:
            pass
    try:                                              # the mouth's broad-query block fallback
        blk = memory_lirf.Facts.load(name).block()
        if blk:
            prompt_parts.append(blk)
    except Exception:
        pass
    try:
        if rt_cluster_edges:
            sit = world_state.render_situation(rt_cluster)
            if sit and sit.strip():
                prompt_parts.append(sit)
    except Exception:
        pass
    prompt = "\n\n".join(prompt_parts)
    out["used"] = {"prompt": prompt, "surfaces": _surfaces_from_text(prompt)}

    # --- COMPRESSED — does the unit's MEANING survive the nightly rollup? review.daily_review
    #     distils the day into what_to_remember + descriptive dimensions (the rollup that lets
    #     the words be discarded while the MEANING is kept — Compressed > Forgotten). We read
    #     every surface those review lines carry; a stored unit whose meaning the review keeps
    #     is COMPRESSED-safe, one it silently drops is flagged. ---
    review_state, comp_surfaces = {}, set()
    if _review is not None:
        try:
            review_state = _review.daily_review(name, persist=False) or {}
        except Exception:
            review_state = {}
    comp_text_bits = []
    for it in (review_state.get("what_to_remember") or []):
        if isinstance(it, dict):
            comp_text_bits.append(str(it.get("summary", "")))
            ev = it.get("evidence") or {}
            if isinstance(ev, dict):
                comp_text_bits.append(" ".join(str(v) for v in ev.values()))
    for dim in ("what_mattered", "what_changed", "what_unresolved"):
        for line in (review_state.get(dim) or []):
            if isinstance(line, dict):
                comp_text_bits.append(str(line.get("subject", "")))
                comp_text_bits.append(str(line.get("statement", "")))
    chap = review_state.get("chapter") or {}
    if isinstance(chap, dict):
        comp_text_bits.append(str(chap.get("summary", "")))
        for th in (chap.get("themes") or []):
            comp_text_bits.append(str(th))
    comp_surfaces = _surfaces_from_text("\n".join(comp_text_bits))
    out["compressed"] = {"remember": review_state.get("what_to_remember") or [],
                         "surfaces": comp_surfaces, "review": review_state}

    return out


def _stage_credits(unit: dict, stage: str, stages: dict) -> bool:
    """Is this salient unit carried at ``stage``? CONTENT credits any category; STRUCTURAL
    (trait/predicate/slot names) credits everything EXCEPT tone (a feeling absorbed into a
    relation predicate/gap was not kept AS a feeling — same rule the base ledger uses). The
    USED and COMPRESSED stages carry only a flat surface set, so a tone unit can be credited
    there only by that set (it would only be present if the literal feeling word made it into
    the prompt / the review text, which is the honest signal)."""
    if stage in ("used", "compressed"):
        return unit["key"] in stages.get(stage, set())
    content = stages.get(stage + "_content", set())
    structural = stages.get(stage + "_structural", set())
    if unit["key"] in content:
        return True
    if unit["category"] != "tone" and unit["key"] in structural:
        return True
    return False


def _attribute_pipeline(units: list, pipe: dict) -> dict:
    """Walk every salient unit DOWN the pipeline and attribute the stage at which it (first)
    fell out, building the per-stage counts + the loss attribution.

    The stage ladder is monotone by accounting: a unit is "present at stage N" only if it was
    present at stage N-1 AND this stage credits it. The FIRST stage that fails to carry a unit
    that its predecessor carried is the stage credited with that unit's loss — so every lost
    unit is blamed on exactly one stage, and the counts conserve (kept@stage + cumulative
    losses up to and incl. stage == detected).

    Returns:
        {
          "stage_counts":   {stage: units still carried at this stage},
          "lost_at":        {stage: [ {category, surface}, … ]},  # first lost HERE
          "unit_trace":     [ {category, surface, reached: last-stage-carried}, … ],
        }
    """
    # flatten the surface sets onto the keys _stage_credits expects.
    stages = {}
    for st in ("captured", "stored", "retrieved"):
        stages[st + "_content"] = pipe.get(st, {}).get("content", set())
        stages[st + "_structural"] = pipe.get(st, {}).get("structural", set())
    stages["used"] = pipe.get("used", {}).get("surfaces", set())
    stages["compressed"] = pipe.get("compressed", {}).get("surfaces", set())

    ladder = ("captured", "stored", "retrieved", "used", "compressed")
    stage_counts = {"detected": len(units)}
    for st in ladder:
        stage_counts[st] = 0
    lost_at = {st: [] for st in ("capture",) + ladder}   # 'capture' == detected->captured drop
    unit_trace = []

    for u in units:
        reached = "detected"
        carried = True
        for st in ladder:
            if carried and _stage_credits(u, st, stages):
                stage_counts[st] += 1
                reached = st
            else:
                if carried:
                    # first stage that dropped it. The detected->captured boundary is named
                    # 'capture' so the verdict reads "dropped at CAPTURE", matching the rates.
                    blame = "capture" if st == "captured" else st
                    lost_at[blame].append({"category": u["category"], "surface": u["surface"]})
                carried = False
        unit_trace.append({"category": u["category"], "surface": u["surface"], "reached": reached})

    return {"stage_counts": stage_counts, "lost_at": lost_at, "unit_trace": unit_trace}


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

    The OBSERVATORY additions (additive — the base fields above are unchanged) attach the
    full pipeline accounting under ``pipeline``:

        "pipeline": {
          "stage_counts": {detected, captured, stored, retrieved, used, compressed},
          "lost_at":      {capture|stored|retrieved|used|compressed: [ {category, surface} ]},
          "unit_trace":   [ {category, surface, reached} ],   # the last stage each unit hit
          "stored":   {facts:[…], edges:[…]},   # what SURVIVED to disk
          "used":     {prompt_chars:int},        # the assembled-prompt size (READ-ONLY)
          "compressed": {remember:[…]},          # the review's keep-forever items
        }

    Deterministic, offline, isolated. Never raises: a bad input yields an empty ledger
    with rate 1.0 (nothing salient -> nothing lost)."""
    text = text or ""
    units = salient_units(text)

    # The WHOLE pipeline runs inside ONE hermetic temp store on ONE synthetic creature, so
    # every stage (capture -> store -> retrieve -> use -> compress) sees a consistent on-disk
    # state and nothing leaks. The legacy ``facts``/``edges`` (CAPTURED-in-memory) are kept
    # verbatim so the base ledger fields are byte-identical to the pre-observatory tool.
    with _temp_store(memory_lirf, world_state):
        # a UNIQUE synthetic name per call so no state leaks between battery inputs
        name = f"{SYNTH}_{secrets.token_hex(3)}"
        facts, edges = _run_capture(name, text)         # base: CAPTURED (in memory)
        # the pipeline reuses a FRESH creature so the persistence round-trip is clean and the
        # base capture above never pre-pollutes the STORED stage's ledger.
        pname = f"{SYNTH}_{secrets.token_hex(3)}"
        pipe = _run_pipeline(pname, text)

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

    attrib = _attribute_pipeline(units, pipe)

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
        "pipeline": {
            "stage_counts": attrib["stage_counts"],
            "lost_at": attrib["lost_at"],
            "unit_trace": attrib["unit_trace"],
            "stored": {
                "facts": [
                    {"trait": r.get("trait"), "value": r.get("value")}
                    for r in pipe.get("stored", {}).get("facts", [])
                ],
                "edges": [
                    {"subject": e.get("subject"), "predicate": e.get("predicate"),
                     "object": e.get("object")}
                    for e in pipe.get("stored", {}).get("edges", [])
                ],
            },
            "used": {"prompt_chars": len(pipe.get("used", {}).get("prompt", "") or "")},
            "compressed": {
                "remember": [
                    {"key": it.get("key"), "summary": it.get("summary")}
                    for it in pipe.get("compressed", {}).get("remember", [])
                    if isinstance(it, dict)
                ],
            },
        },
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


# The 95% target the observatory grades the battery against (the Phase-3C bar; the current
# overall baseline is ~85%). Kept as a module constant so the verdict reads from one place.
TARGET = 0.95


def _safe_rate(num: int, den: int) -> float:
    """A stage-transition rate num/den, with the honest convention that an EMPTY upstream
    (nothing reached this stage) is a perfect 1.0 — there was nothing to lose, so the stage
    didn't lose anything. Keeps a sparse battery from reading as 0% at a downstream stage."""
    return (num / den) if den else 1.0


def _meaning_retention(ledgers: list) -> dict:
    """MEANING RETENTION — overall SIGNIFICANCE preserved end-to-end. A salient unit is not
    just a token; the question Law-003 asks is whether the unit that MATTERED still carries
    weight after the round-trip. We proxy this two ways and report both, taking the gentler
    (a unit's meaning is retained if EITHER its literal surface survived to USED, OR the topic
    it belongs to surfaced as a significant theme in the COMPRESSED review):

      * surface retention   — detected units whose literal surface reached USED.
      * significance retention — detected units whose meaning the nightly review kept
        (its surface appears in what_to_remember / the dimensions / the chapter).

    The reported ``meaning_retention`` is the fraction of detected units retained by EITHER
    path — significance is allowed to rescue a unit whose literal token didn't make the
    prompt (its MEANING was still kept), which is exactly the Law-003 stance: understanding
    beats verbatim remembering."""
    det = used = comp = either = 0
    for led in ledgers:
        trace = {(_u["category"], _u["surface"]): _u
                 for _u in led.get("pipeline", {}).get("unit_trace", [])}
        comp_surf = set()
        # rebuild the compressed-surface membership from the unit_trace's reached marker:
        # a unit "reached" used/compressed means its surface survived that far.
        for u in led.get("salient", []):
            det += 1
            tr = trace.get((u["category"], u["surface"]))
            reached = (tr or {}).get("reached", "detected")
            ladder_index = {"detected": 0, "captured": 1, "stored": 2, "retrieved": 3,
                            "used": 4, "compressed": 5}
            ri = ladder_index.get(reached, 0)
            hit_used = ri >= 4
            hit_comp = ri >= 5
            if hit_used:
                used += 1
            if hit_comp:
                comp += 1
            if hit_used or hit_comp:
                either += 1
    return {
        "detected": det,
        "surface_retained": used,
        "significance_retained": comp,
        "either_retained": either,
        "meaning_retention": _safe_rate(either, det),
        "surface_retention": _safe_rate(used, det),
        "significance_retention": _safe_rate(comp, det),
    }


def run_battery(inputs=None) -> dict:
    """Run the conservation observatory over a battery of inputs and compute the OVERALL
    conservation rate, the per-stage ledger, the FIVE pipeline rates, the end-to-end
    retention, and the 95%-target verdict. Returns a dict with per-input ledgers + the
    rollup."""
    inputs = list(inputs) if inputs is not None else list(BATTERY)
    ledgers = [conservation_ledger(t) for t in inputs]

    tot_salient = sum(l["total_salient"] for l in ledgers)
    tot_captured = sum(l["captured_salient"] for l in ledgers)
    overall = (tot_captured / tot_salient) if tot_salient else 1.0

    agg = {"entity": 0, "relation": 0, "tone": 0, "temporal": 0}
    for l in ledgers:
        for k, v in l["lost_by_category"].items():
            agg[k] = agg.get(k, 0) + v

    # --- aggregate the PIPELINE: per-stage counts summed across the battery. ---
    stage_counts = {st: 0 for st in STAGES}
    lost_at = {st: [] for st in ("capture", "captured", "stored", "retrieved",
                                 "used", "compressed")}
    for l in ledgers:
        pl = l.get("pipeline", {})
        for st, n in (pl.get("stage_counts") or {}).items():
            stage_counts[st] = stage_counts.get(st, 0) + int(n)
        for st, items in (pl.get("lost_at") or {}).items():
            lost_at.setdefault(st, []).extend(items)

    # --- the FIVE RATES, each a stage transition over the whole battery. ---
    d = stage_counts.get("detected", 0)
    c = stage_counts.get("captured", 0)
    s = stage_counts.get("stored", 0)
    r = stage_counts.get("retrieved", 0)
    u = stage_counts.get("used", 0)
    mret = _meaning_retention(ledgers)
    rates = {
        "capture_rate": _safe_rate(c, d),       # detected -> captured
        "storage_rate": _safe_rate(s, c),       # captured -> stored
        "retrieval_rate": _safe_rate(r, s),     # stored -> retrieved
        "usage_rate": _safe_rate(u, r),         # retrieved -> used
        "meaning_retention": mret["meaning_retention"],   # significance preserved end-to-end
    }
    # END-TO-END retention: detected -> actually USED (the bottom-line pipeline survival).
    end_to_end = _safe_rate(u, d)

    return {
        "ledgers": ledgers,
        "total_salient": tot_salient,
        "captured_salient": tot_captured,
        "overall_conservation_rate": overall,
        "lost_by_category": agg,
        # observatory rollup
        "stage_counts": stage_counts,
        "lost_at": lost_at,
        "rates": rates,
        "meaning_detail": mret,
        "end_to_end_retention": end_to_end,
        "target": TARGET,
        "clears_target": end_to_end >= TARGET,
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

    # --- PIPELINE trace: the stage ladder for THIS input + where each unit fell out. ---
    pl = led.get("pipeline")
    if pl:
        sc = pl.get("stage_counts", {})
        ladder = " -> ".join(f"{st[:4].upper()} {sc.get(st, 0)}" for st in STAGES)
        out.append(f"  PIPELINE:     {ladder}")
        # name every unit that fell out, and the stage that dropped it (a salient unit that
        # silently vanished is the whole thing we refuse to allow).
        lost_at = pl.get("lost_at", {})
        any_drop = any(lost_at.get(st) for st in lost_at)
        if any_drop:
            label = {"capture": "CAPTURE  ", "stored": "STORAGE  ",
                     "retrieved": "RETRIEVAL", "used": "USAGE    ",
                     "compressed": "COMPRESS "}
            for st in ("capture", "stored", "retrieved", "used", "compressed"):
                for u in lost_at.get(st, []):
                    out.append(f"    × dropped @ {label.get(st, st):<9} "
                               f"[{u['category']:<8}] {u['surface']}")
    return "\n".join(out)


def _bar(rate: float, width: int = 24) -> str:
    """A tiny ASCII meter for a [0,1] rate, so the rates read at a glance."""
    rate = 0.0 if rate < 0 else (1.0 if rate > 1 else rate)
    fill = int(round(rate * width))
    return "[" + "#" * fill + "-" * (width - fill) + "]"


def render(report: dict) -> str:
    out = []
    out.append("=" * 79)
    out.append("VERA CONSERVATION OBSERVATORY (Phase 3C)")
    out.append("Information like energy across the WHOLE pipeline: every salient unit is")
    out.append("followed DETECTED -> CAPTURED -> STORED -> RETRIEVED -> USED -> COMPRESSED, and")
    out.append("the stage that drops it is NAMED. Nothing disappears silently.")
    out.append("=" * 79)
    for led in report["ledgers"]:
        out.append("")
        out.append(render_ledger(led))
    out.append("")
    out.append("-" * 79)
    out.append("OVERALL CONSERVATION (base ledger: detected -> captured)")
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

    # --- THE OBSERVATORY ROLLUP — the stage ledger, the five rates, the verdict. ---
    sc = report.get("stage_counts", {})
    rates = report.get("rates", {})
    if sc and rates:
        out.append("")
        out.append("-" * 79)
        out.append("CONSERVATION OBSERVATORY — full-pipeline stage ledger")
        out.append("-" * 79)
        out.append("  stage counts (salient units carried at each stage):")
        prev = None
        for st in STAGES:
            n = sc.get(st, 0)
            delta = "" if prev is None else f"  ({n - prev:+d} from previous)"
            out.append(f"    {st.upper():<11}: {n}{delta}")
            prev = n
        # the named drops, summed across the battery.
        lost_at = report.get("lost_at", {})
        out.append("  where loss occurred (stage that dropped each salient unit):")
        named = {"capture": "CAPTURE", "stored": "STORAGE", "retrieved": "RETRIEVAL",
                 "used": "USAGE", "compressed": "COMPRESSION"}
        any_loss = False
        for st in ("capture", "stored", "retrieved", "used", "compressed"):
            items = lost_at.get(st, [])
            if not items:
                continue
            any_loss = True
            surfaces = ", ".join(f"{u['surface']}[{u['category']}]" for u in items)
            out.append(f"    {named.get(st, st):<11} dropped {len(items)}: {surfaces}")
        if not any_loss:
            out.append("    (nothing dropped past capture — every captured unit rode through)")

        out.append("")
        out.append("  THE FIVE RATES:")
        rate_rows = [
            ("Capture Rate", "capture_rate", "detected  -> captured"),
            ("Storage Rate", "storage_rate", "captured  -> stored  "),
            ("Retrieval Rate", "retrieval_rate", "stored    -> retrieved"),
            ("Usage Rate", "usage_rate", "retrieved -> used    "),
            ("Meaning Retention", "meaning_retention", "significance kept e2e"),
        ]
        for label, key, span in rate_rows:
            v = float(rates.get(key, 0.0))
            out.append(f"    {label:<18} {span}  {_bar(v)} {v * 100:5.1f}%")

        e2e = float(report.get("end_to_end_retention", 0.0))
        target = float(report.get("target", TARGET))
        clears = bool(report.get("clears_target", False))
        out.append("")
        out.append(f"  END-TO-END RETENTION (detected -> used): {_bar(e2e)} {e2e * 100:.1f}%")
        verdict = "CLEARS" if clears else "BELOW"
        out.append(f"  95% TARGET VERDICT: {e2e * 100:.1f}% vs {target * 100:.0f}% target  "
                   f"->  {verdict} the bar"
                   + ("" if clears else f" (short by {(target - e2e) * 100:.1f} pts)"))
        md = report.get("meaning_detail", {})
        if md:
            out.append(f"  (meaning detail: surface-retained {md.get('surface_retention', 0) * 100:.1f}%, "
                       f"significance-retained {md.get('significance_retention', 0) * 100:.1f}%)")

    out.append("")
    out.append("HONEST NOTE: emotional TONE (\"really stressed\", \"excited\", \"love\") is")
    out.append("routinely dropped at CAPTURE — it is real signal but not a durable trait, so the")
    out.append("observatory reports + ATTRIBUTES it as lost on purpose. Degree/intensity and some")
    out.append("bare temporal words are dropped too. This is acceptable for a fact store; the")
    out.append("value here is that every stage's loss is now COUNTED, ATTRIBUTED, and VISIBLE —")
    out.append("never silent. A unit that survives to USED may still be the spine of the reply;")
    out.append("one whose MEANING the review keeps is preserved even if its literal token isn't.")
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
# lost, the rate is in [0,1], the FULL-PIPELINE stage accounting CONSERVES (kept + losses
# == detected at every stage), a high-retention input is discriminated from a low-retention
# one, and the HERMETIC synthetic-only guardrail holds across EVERY redirected STORE binding
# (real .anima byte-unchanged before/after). No model, no network.
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

    # "My daughter Maya started kindergarten" is APPOSITION (no copula). Wave A (#35) taught
    # the LIRF extractor an appositive-name rule, so 'Maya' is now CAPTURED, not lost — the
    # tool honestly reflects the improved capture. (Updated: appositive names no longer slip.)
    led = conservation_ledger("My daughter Maya started kindergarten last week")
    ok("ledger: appositive 'Maya' is now CAPTURED (Wave A appositive-name rule), not lost",
       not any(u["surface"] == "Maya" and u["category"] == "entity" for u in led["lost"]))
    ok("ledger: rate is a probability in [0,1]", 0.0 <= led["conservation_rate"] <= 1.0)
    ok("ledger: total_salient == captured + lost",
       led["total_salient"] == led["captured_salient"] + len(led["lost"]))

    # --- tone is now CAPTURED via a durable reported_feeling fact (Wave: tone widening) ---
    # PRECEDENT: exactly the Maya/Austin flip from commit d0fc93d — the tool always measured
    # actual loss; only the test's expectation was stale once the extractor widened. memory_lirf
    # now captures an explicit first-person feeling ("I've been really stressed") as a durable
    # reported_feeling row whose VALUE is the user's stated phrase "really stressed" — so BOTH
    # the affect ('stressed') AND its intensity ('really') survive as CONTENT and are credited.
    # RULE #1: that row records the USER *reported* a feeling (an OBSERVED fact grounded in their
    # words), NOT that Vera feels anything — the conservation tool credits tone ONLY from a fact
    # VALUE (never a predicate), so this credit is the genuine durable capture, not a relation
    # predicate masquerading as affect. The earlier 'stressed_by' predicate still does NOT credit
    # tone (relation != affect); the credit comes from the reported_feeling value.
    led_t = conservation_ledger("I've been really stressed about the Q3 launch")
    # the value is a phrase ("really stressed") — tokenise it the way the captured-set diff
    # does (word by word, stemmed) so the affect token is matched, not the collapsed phrase key.
    def _val_tokens(f):
        vals = f["value"] if isinstance(f.get("value"), list) else [f.get("value")]
        toks = set()
        for v in vals:
            for w in _WORD.findall(str(v)):
                k = _norm_unit(w)
                if k:
                    toks.add(k)
        return toks
    ok("ledger: a reported_feeling fact captures the affect ('really stressed') durably",
       any(f.get("trait") == "reported_feeling"
           and _norm_unit("stressed") in _val_tokens(f)
           and _norm_unit("really") in _val_tokens(f)
           for f in led_t["extracted"]["facts"]))
    ok("ledger: tone ('stressed') is now CAPTURED (reported_feeling value), not lost",
       not any(u["category"] == "tone" and _norm_unit(u["surface"]) == _norm_unit("stressed")
               for u in led_t["lost"]))
    ok("ledger: degree word ('really') is now CAPTURED (intensity kept in the value), not lost",
       not any(u["category"] == "tone" and u["surface"].lower() == "really"
               for u in led_t["lost"]))
    ok("ledger: no tone is lost for an explicit first-person feeling statement",
       led_t["lost_by_category"]["tone"] == 0)
    # RULE #1 GUARDRAIL, asserted: the durable record is grounded in the USER's words and never
    # claims a feeling FOR Vera. The captured value is a phrase the user literally used, and the
    # trait name itself ('reported_feeling') frames it as the user's report, not Vera's state.
    ok("ledger: RULE #1 — captured affect is GROUNDED in the user's words (value ⊆ input)",
       all(all(tok in "i've been really stressed about the q3 launch"
               for tok in str(v).lower().split())
           for f in led_t["extracted"]["facts"]
           if f.get("trait") == "reported_feeling"
           for v in (f["value"] if isinstance(f.get("value"), list) else [f.get("value")])))

    # --- once a TOTAL-LOSS input, now captured. Wave A (#35) added the "I moved to X" rule +
    # the move/cause world-state edge, so this rich causal input now stores facts + edges and
    # 'Austin' is CAPTURED. The conservation tool tracks the improvement honestly. ---
    led_r = conservation_ledger("I moved to Austin because my manager changed")
    stored = len(led_r["extracted"]["facts"]) + len(led_r["extracted"]["edges"])
    ok("ledger: 'moved to Austin because manager' now CAPTURES (Wave A move rule), not total-loss",
       stored > 0 and not any(u["surface"] == "Austin" for u in led_r["lost"]))

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

    # ===============================================================================
    # OBSERVATORY — the full-pipeline stage accounting, the five rates, and the verdict.
    # ===============================================================================

    # --- every per-input ledger now carries a pipeline block with all six stage counts. ---
    ok("pipeline: every input ledger has a pipeline block with all 6 stage counts",
       all(set((l.get("pipeline") or {}).get("stage_counts", {}).keys()) >= set(STAGES)
           for l in rep["ledgers"]))

    # --- THE STAGE-ACCOUNTING CONSERVATION INVARIANT. At EVERY stage, the units still
    #     carried PLUS every unit lost up to and including that stage must equal DETECTED.
    #     Nothing vanishes unaccounted; the ladder is monotone and exact. Checked per input
    #     AND on the aggregate. ---
    ladder = ("captured", "stored", "retrieved", "used", "compressed")
    # the loss bucket each ladder stage drains into (capture -> 'capture', else its own name).
    _blame_of = {"captured": "capture", "stored": "stored", "retrieved": "retrieved",
                 "used": "used", "compressed": "compressed"}

    def _conserved(stage_counts, lost_at):
        det = stage_counts.get("detected", 0)
        cum_loss = 0
        for st in ladder:
            cum_loss += len(lost_at.get(_blame_of[st], []))
            if stage_counts.get(st, 0) + cum_loss != det:
                return False, st
        return True, None

    per_input_conserved = True
    bad_stage = None
    for l in rep["ledgers"]:
        pl = l.get("pipeline", {})
        good, where = _conserved(pl.get("stage_counts", {}), pl.get("lost_at", {}))
        if not good:
            per_input_conserved = False
            bad_stage = where
            break
    ok("CONSERVATION [per-input]: kept@stage + cumulative-losses == detected at EVERY stage"
       + (f" (broke at {bad_stage})" if bad_stage else ""),
       per_input_conserved)

    agg_good, agg_where = _conserved(rep["stage_counts"], rep["lost_at"])
    ok("CONSERVATION [aggregate]: the battery's stage ladder conserves end to end"
       + (f" (broke at {agg_where})" if agg_where else ""),
       agg_good)

    # the ladder is MONOTONE NON-INCREASING — a stage can never carry MORE than its parent.
    sc = rep["stage_counts"]
    seq = [sc.get(st, 0) for st in STAGES]
    ok("CONSERVATION: stage counts are monotone non-increasing (no stage gains units)",
       all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1)))

    # detected == captured + dropped@capture, the base/observatory bridge.
    ok("CONSERVATION: detected == captured + dropped-at-capture (base ledger bridges in)",
       sc.get("detected", 0) == sc.get("captured", 0) + len(rep["lost_at"].get("capture", [])))

    # --- THE FIVE RATES exist, are probabilities, and equal the ratios they claim. ---
    rates = rep["rates"]
    ok("rates: all five present (capture/storage/retrieval/usage/meaning_retention)",
       set(rates.keys()) == {"capture_rate", "storage_rate", "retrieval_rate",
                             "usage_rate", "meaning_retention"})
    ok("rates: every rate is a probability in [0,1]",
       all(0.0 <= float(v) <= 1.0 for v in rates.values()))
    ok("rates: capture_rate == captured/detected",
       abs(rates["capture_rate"] - _safe_rate(sc["captured"], sc["detected"])) < 1e-9)
    ok("rates: storage_rate == stored/captured",
       abs(rates["storage_rate"] - _safe_rate(sc["stored"], sc["captured"])) < 1e-9)
    ok("rates: retrieval_rate == retrieved/stored",
       abs(rates["retrieval_rate"] - _safe_rate(sc["retrieved"], sc["stored"])) < 1e-9)
    ok("rates: usage_rate == used/retrieved",
       abs(rates["usage_rate"] - _safe_rate(sc["used"], sc["retrieved"])) < 1e-9)

    # --- END-TO-END retention + the 95% target verdict are coherent. ---
    e2e = rep["end_to_end_retention"]
    ok("verdict: end_to_end == used/detected, in [0,1]",
       0.0 <= e2e <= 1.0 and abs(e2e - _safe_rate(sc["used"], sc["detected"])) < 1e-9)
    ok("verdict: target is 0.95 and clears_target == (e2e >= target)",
       abs(rep["target"] - 0.95) < 1e-9 and rep["clears_target"] == (e2e >= rep["target"]))
    ok("verdict: render shows the 95% TARGET VERDICT line",
       "95% TARGET VERDICT" in txt and "END-TO-END RETENTION" in txt)
    ok("verdict: render shows the five named rates", "Capture Rate" in txt
       and "Storage Rate" in txt and "Retrieval Rate" in txt and "Usage Rate" in txt
       and "Meaning Retention" in txt)

    # --- NOTHING DISAPPEARS SILENTLY: every DROPPED unit is attributed to exactly ONE stage,
    #     and the attributed drops account for the full detected->used shortfall. ---
    total_attributed = sum(len(v) for v in rep["lost_at"].values())
    dropped_pre_used = sum(len(rep["lost_at"].get(st, []))
                           for st in ("capture", "stored", "retrieved", "used"))
    ok("attribution: detected - used == units dropped at-or-before USAGE (no silent loss)",
       sc["detected"] - sc["used"] == dropped_pre_used)
    ok("attribution: every lost unit is blamed on a stage (attributed >= detected-used)",
       total_attributed >= sc["detected"] - sc["used"])

    # --- DISCRIMINATION: a high-retention input vs a low-retention input. The fact-dense
    #     input rides to USED in full; the all-tone input is dropped at CAPTURE in full.
    #     The low example is deliberately kept GENUINELY LOST so the loss path stays exercised
    #     after the tone widening: it carries NO explicit first-person feeling frame ("I'm/I
    #     feel <affect>") and its affect words ('heavy'/'rough'/'exhausting') are outside the
    #     durable reported_feeling lexicon — so nothing is captured and it drops fully at
    #     CAPTURE, exactly the honest behaviour for tone with no slot. (The prior example,
    #     "I am really stressed ... lately", is now PARTLY captured — "really stressed" lands as
    #     a reported_feeling fact — so it no longer exercises a full-capture loss; this purer
    #     all-tone line restores that.) ---
    hi = conservation_ledger("My name is Sarah and I live in Portland")
    lo = conservation_ledger("everything feels heavy and rough and exhausting")
    hsc, lsc = hi["pipeline"]["stage_counts"], lo["pipeline"]["stage_counts"]
    hi_e2e = _safe_rate(hsc["used"], hsc["detected"])
    lo_e2e = _safe_rate(lsc["used"], lsc["detected"])
    ok(f"discriminate: high-retention input reaches USED in full (e2e={hi_e2e:.2f})",
       hsc["detected"] > 0 and hsc["used"] == hsc["detected"])
    ok(f"discriminate: low-retention all-tone input is dropped at CAPTURE (e2e={lo_e2e:.2f})",
       lsc["detected"] > 0 and lsc["used"] == 0
       and len(lo["pipeline"]["lost_at"].get("capture", [])) == lsc["detected"])
    ok("discriminate: high-retention e2e STRICTLY exceeds low-retention e2e",
       hi_e2e > lo_e2e)

    # ===============================================================================
    # HERMETIC GUARDRAIL — the cert's footprint guard, made explicit over the FULL pipeline.
    # A full battery exercises every stage (capture/store/retrieve/use/compress) and thus
    # EVERY redirected STORE binding (memory_lirf on both bindings, world_state, curiosity,
    # meaning, review, constitution.STORE, reliability.DEFAULT_STORE). The real .anima must be
    # byte-identical before and after, and no synthetic file may leak.
    # ===============================================================================
    fp_before = _footprint(real)
    _ = run_battery()                       # the whole observatory, again, over every stage
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across a full observatory battery",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic creature file leaked into real .anima (any stage)",
       (not real.is_dir())
       or not any(p.name.startswith(SYNTH) for p in real.glob(f"{SYNTH}*")))

    # the redirect set RESTORES every binding it touched — after the run, each STORE attr is
    # back to its real value (a bleed of a temp dir into a module STORE would be a live leak).
    restored_ok = True
    for (mod, attr) in _resolve_store_targets():
        val = getattr(mod, attr, None)
        if val is not None and "anima-conservation-" in str(val):
            restored_ok = False
            break
    ok("HERMETIC: every redirected STORE/DEFAULT_STORE binding is RESTORED (no temp-dir bleed)",
       restored_ok)

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
