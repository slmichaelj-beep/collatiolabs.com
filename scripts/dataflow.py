#!/usr/bin/env python3
"""DATA FLOW OBSERVATORY — "distributed tracing for cognition" / the Shape Diff Viewer.

The Conservation Observatory (``scripts/conservation.py``) asks **how much** survives: it
follows a salient unit DETECTED -> CAPTURED -> STORED -> RETRIEVED -> USED and reports the
per-stage loss RATE. This tool asks the complementary question — **what shape** did a unit of
input become at each step, and **what changed between steps**:

    what transformed, what mutated, what was lost, what was gained — and WHERE?

It traces ONE unit of input through the full cognition pipeline and shows its
SHAPE / representation at every transformation, with the per-transition DIFF:

    RAW_TEXT  ->  ENTITIES  ->  RELATIONS  ->  FACTS  ->  GRAPH_EDGES
              ->  RETRIEVAL_CANDIDATES  ->  PROMPT_CONTEXT  ->  OUTPUT

Each HOP is the representation the pipeline actually carries at that point (the real engines'
output, never hardcoded):

    RAW_TEXT             the utterance, tokenised — the substrate everything else is carved from
    ENTITIES             memory_lirf.extract() candidate facts {trait, value} (Tier A, model OFF)
                         + the proper-noun / temporal / tone surfaces a reader would name
    RELATIONS            world_state.capture() edge TUPLES (subject, predicate, object, kind) —
                         the stated causal/relational links, before any persistence
    FACTS                the LIRF rows that SURVIVE persistence to disk (Facts.load.about()):
                         durable {trait, value, confidence} — the FORM facts take on disk
    GRAPH_EDGES          the world-state edge DICTS on disk (World.load.active()): the typed
                         relation graph {subject, predicate, object, kind, confidence}
    RETRIEVAL_CANDIDATES what a turn FETCHES back for this query — the router-selected LIRF rows
                         + the world_state.situation() connected cluster (nodes + edges)
    PROMPT_CONTEXT       the assembled prompt block the mouth would bind (READ-ONLY, no brain):
                         spine.bind(rows) + the Facts.block() fallback + render_situation(cluster)
    OUTPUT               the deterministic surface the prompt context exposes to generation — the
                         set of normalised surfaces a reply is licensed to use (we DON'T run a
                         model; OUTPUT is the licensed-surface boundary, the honest end of the
                         deterministic chain)

For every adjacent pair the tool computes a SHAPE DIFF:
    + added        a surface present at this hop that wasn't at the previous one (a node the
                   graph synthesised, a predicate the extractor named)
    - removed      a surface the previous hop carried that this one dropped (the loss — WHERE)
    ~ transformed  a surface that changed FORM but kept its meaning ("My daughter Maya" the raw
                   span  ->  the fact ``daughter = Maya``  ->  the node ``maya``)

and answers a **"where was <token> lost / transformed?"** locator: given a token (e.g. "Maya",
"last week", the date), it walks the chain and names the last hop that carried it, the hop where
it changed shape, and the hop where it fell out — so "where did Maya / the date drop?" is a
first-class query, not an eyeball job over a wall of JSON.

COMPLEMENTARY, NOT REDUNDANT, with conservation.py:
  * conservation renders the LOSS (rates per salient unit, the 95% verdict);
  * dataflow renders the FORM (the representation at each hop) and the TRANSFORMATION between
    hops (the shape diff). It REUSES conservation's stage scaffolding READ-ONLY — the same
    deterministic ``salient_units`` extraction and the same hermetic ``_temp_store`` redirect —
    so the two tools agree on what a "unit" is and never touch the real store; dataflow adds the
    shape/transform rendering on top, it does not re-derive loss accounting.

GUARDRAILS (identical posture to conservation.py / experience.py / test_continuity.py):
  * DETERMINISTIC + OFFLINE. No model, no network. The model-assist Tier-B paths in the engines
    are never invoked. The mouth/prompt signal is read WITHOUT a brain — only the deterministic
    binding blocks are assembled.
  * SYNTHETIC creatures + TEMPORARY stores ONLY. HERMETIC: every engine STORE the pipeline now
    writes is redirected to ONE TemporaryDirectory for the run — memory_lirf.STORE on BOTH the
    __main__ and package bindings, world_state.STORE, curiosity.STORE, constitution.STORE,
    reliability.DEFAULT_STORE, telemetry.STORE, cloud.STORE (and meaning/review if present) — so
    a good Facts.load (which also writes a continuity ledger + a guarded backup) can never leak
    into the real .anima. The run ASSERTS the real .anima footprint is byte-unchanged
    start->end. It NEVER reads or writes a real Vera.* file.
  * ADDITIVE. Imports and RUNS the engines; edits no module, no test, no certify.py.
  * Never raises out of the entry points — a malformed input yields an honest minimal chain
    (raw text only), not a traceback.

    python3 scripts/dataflow.py             # human-readable shape-transformation chain + locator
    python3 scripts/dataflow.py --json      # machine-readable
    python3 scripts/dataflow.py --selftest  # asserts the chain captures REAL shapes + locators

Exit code is 0 (this is an OBSERVATORY — it reports the shape, it does not fail on a transform).
A broken guardrail (the real .anima footprint changed, or an engine raised through a guard)
exits non-zero from --selftest.
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

# REUSE the Conservation Observatory's deterministic scaffolding READ-ONLY: the SAME salient-unit
# extraction (so a "unit" means the same thing in both tools) and the SAME normalised-surface key
# (so the membership tests across the chain are apples-to-apples). We render the SHAPE; it renders
# the loss. Imported best-effort — if conservation won't import (it shouldn't fail, but we never
# hard-depend on a sibling script), we fall back to a local copy of just the two primitives.
try:                                     # noqa: E402
    from scripts.conservation import salient_units as _salient_units
    from scripts.conservation import _norm_unit as _norm_unit
    from scripts.conservation import STAGES as _CONS_STAGES   # the read-only stage scaffolding
except Exception:                        # pragma: no cover - isolation fallback
    _CONS_STAGES = ("detected", "captured", "stored", "retrieved", "used", "compressed")
    _STEM = re.compile(r"(?:ed|ing|ful|s|'s)$")

    def _norm_unit(s: str) -> str:
        s = re.sub(r"[^a-z0-9$]+", "", str(s).strip().lower())
        if len(s) > 4:
            s2 = _STEM.sub("", s)
            if len(s2) >= 3:
                s = s2
        return s

    def _salient_units(text: str) -> list:
        # minimal fallback: proper-noun runs + bare words; good enough that the tool still
        # functions standalone, though the real conservation extractor is richer.
        out, seen = [], set()
        for m in re.finditer(r"\b([A-Z][\w'-]+)\b", text or ""):
            k = _norm_unit(m.group(1))
            if k and ("entity", k) not in seen:
                seen.add(("entity", k))
                out.append({"category": "entity", "surface": m.group(1), "key": k})
        return out

# Downstream engines used by the RETRIEVAL_CANDIDATES / PROMPT_CONTEXT hops. Best-effort imports:
# a hop whose engine won't import degrades to "carried nothing" (the honest rendering) rather than
# crashing the tool.
try:                                     # noqa: E402
    from anima import spine as _spine
except Exception:                        # pragma: no cover - isolation
    _spine = None

# A synthetic-only sentinel so nothing here can ever collide with a real creature.
SYNTH = "dflow_synth"

# A simple word/number tokeniser, matched to conservation's so surfaces fold identically.
_WORD = re.compile(r"[A-Za-z']+")
_NUMERIC = re.compile(r"\b(?:\d{1,4}(?:[/-]\d{1,4}){0,2}(?:st|nd|rd|th)?|Q[1-4])\b", re.I)


# ===================================================================================
# GUARDRAIL — HERMETIC temp-store redirect + footprint hash. Mirrors conservation.py's
# _STORE_TARGETS / _temp_store / _footprint, EXTENDED to the full store set the brief names
# (adds telemetry.STORE + cloud.STORE — a good Facts.load / capture path can touch the
# continuity ledger, guarded backups, telemetry, and the cloud PII gate). A redirect target is a
# (module, attr) pair because reliability's store attr is DEFAULT_STORE, not STORE. Resolved by
# NAME so importing this module never hard-depends on every downstream engine; a missing one is
# simply skipped.
# ===================================================================================
_STORE_TARGETS = (
    ("anima.memory_lirf", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.constitution", "STORE"),           # the continuity ledger a good load writes
    ("anima.reliability", "DEFAULT_STORE"),     # guarded-backup snapshots
    ("anima.telemetry", "STORE"),               # any MRI/telemetry line a path may emit
    ("anima.cloud", "STORE"),                   # the cloud PII gate's store
    ("anima.meaning", "STORE"),                 # present in the tree; harmless if unused
    ("anima.review", "STORE"),
)


def _resolve_store_targets():
    """Resolve ``_STORE_TARGETS`` to live ``(module, attr)`` pairs that actually carry the
    attribute right now. A module that won't import, or that lacks the attr, is skipped — so the
    redirect set adapts to whatever is built without ever hard-failing."""
    pairs, seen = [], set()
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
    """Redirect EVERY pipeline STORE binding to one fresh temp dir for the duration, so nothing
    under the real .anima/ is read or written. Restored on exit. ``extra_modules`` (e.g. this
    script's own ``memory_lirf``/``world_state`` __main__ bindings — the SAME objects as the
    package copies, but pinned by value to be safe) are also redirected on their ``STORE`` attr.
    HERMETIC by construction: a leak is impossible regardless of which engine the pipeline ends up
    writing."""
    targets = _resolve_store_targets()
    for m in extra_modules:
        if hasattr(m, "STORE") and (m, "STORE") not in targets:
            targets.append((m, "STORE"))
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    with tempfile.TemporaryDirectory(prefix="anima-dataflow-") as td:
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
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir, which
    legitimately changes), so we can PROVE the harness touched nothing."""
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
# SURFACE EXTRACTION — every hop reduces to a set of normalised-surface KEYS (so the diff between
# adjacent hops is a set difference) PLUS a human "shape" rendering of the representation. The KEY
# set is what the locator walks; the shape is what a human reads. Both come from the REAL engine
# output, never hardcoded.
# ===================================================================================
def _surfaces_of_text(blob: str) -> set:
    """Every normalised surface key in a free-text blob (raw text, an assembled prompt). Tokenised
    exactly like conservation's captured-set so membership is apples-to-apples across the chain."""
    out = set()
    for tok in _WORD.findall(blob or "") + _NUMERIC.findall(blob or ""):
        k = _norm_unit(tok)
        if k:
            out.add(k)
    return out


def _surfaces_of_value(v, out: set) -> None:
    """Fold one fact value / node label into the surface set: each word/number token AND the whole
    value as one key (so a multi-word value like 'New York' is matched both ways)."""
    if v is None:
        return
    if isinstance(v, list):
        for x in v:
            _surfaces_of_value(x, out)
        return
    for tok in _WORD.findall(str(v)) + _NUMERIC.findall(str(v)):
        k = _norm_unit(tok)
        if k:
            out.add(k)
    whole = _norm_unit(str(v))
    if whole:
        out.add(whole)


def _fact_surfaces(rows, *, content_only: bool = False) -> set:
    """Surfaces a list of LIRF fact rows / extract() candidates carries: the VALUES (content)
    always; the TRAIT slot names (structural) unless ``content_only``. A durable fact credits a
    token by EITHER unless we are deliberately asking 'did the literal CONTENT survive?'."""
    out = set()
    for r in rows or []:
        _surfaces_of_value(r.get("value"), out)
        if not content_only:
            _surfaces_of_value(r.get("trait"), out)
    return out


def _edge_tuple_surfaces(tuples) -> set:
    """Surfaces a list of world_state.capture() edge TUPLES (subject, predicate, object, kind,
    topic) carries: subjects + objects (content) and predicates (structural)."""
    out = set()
    for e in tuples or []:
        try:
            s, p, o = e[0], e[1], e[2]
        except Exception:
            continue
        _surfaces_of_value(s, out)
        _surfaces_of_value(p, out)
        _surfaces_of_value(o, out)
    return out


def _edge_dict_surfaces(edges) -> set:
    """Surfaces a list of world-edge DICTS (subject/predicate/object) carries."""
    out = set()
    for e in edges or []:
        if not isinstance(e, dict):
            continue
        _surfaces_of_value(e.get("subject"), out)
        _surfaces_of_value(e.get("predicate"), out)
        _surfaces_of_value(e.get("object"), out)
    return out


def _cluster_surfaces(cluster: dict) -> set:
    """Surfaces a situation() cluster carries: its node keys + every edge it contains."""
    out = set()
    if not isinstance(cluster, dict):
        return out
    for n in (cluster.get("nodes") or []):
        _surfaces_of_value(n, out)
    out |= _edge_dict_surfaces([e for e in (cluster.get("edges") or []) if isinstance(e, dict)])
    return out


# ===================================================================================
# THE PIPELINE — run the REAL engines on a synthetic creature inside ONE hermetic temp store and
# collect, per hop, the raw artefact + its surface-key set. Every hop is best-effort: an engine
# that raises yields that hop's empty artefact + empty surfaces (rendered honestly as "carried
# nothing"), never a traceback out of the tool.
# ===================================================================================

# The hop ladder, in pipeline order. Each maps (loosely) onto a conservation stage so the two
# tools line up; dataflow renders the FORM at the hop, conservation the loss rate at the stage.
HOPS = (
    "raw_text",              # ~ DETECTED   : the substrate
    "entities",              # ~ CAPTURED   : extract() candidates + salient surfaces
    "relations",             # ~ CAPTURED   : capture() edge tuples (pre-persistence)
    "facts",                 # ~ STORED     : LIRF rows surviving to disk
    "graph_edges",           # ~ STORED     : world edges surviving to disk
    "retrieval_candidates",  # ~ RETRIEVED  : router rows + situation() cluster
    "prompt_context",        # ~ USED       : the assembled prompt block (read-only mouth)
    "output",                # the licensed-surface boundary (no model run)
)

# How each hop maps onto the conservation stage scaffolding it parallels — surfaced in --json so a
# reader can line the two observatories up. Read-only label; conservation owns the rates.
HOP_TO_CONS_STAGE = {
    "raw_text": "detected",
    "entities": "captured",
    "relations": "captured",
    "facts": "stored",
    "graph_edges": "stored",
    "retrieval_candidates": "retrieved",
    "prompt_context": "used",
    "output": "used",
}


def _select_rows(name: str, text: str):
    """The LIRF rows a turn would RETRIEVE for this query — the router's selection when importable
    (the real retrieval path), else the full active ledger (the broad-query fallback the mouth
    itself uses). Read-only; [] on any failure."""
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


def trace_pipeline(text: str) -> dict:
    """Run the FULL pipeline for one utterance on a synthetic creature (inside a hermetic temp
    store) and return the per-hop ARTEFACT + SURFACE set. The caller renders the shape at each hop
    and the diff between hops. Deterministic, offline, isolated. Never raises.

    Returns ``{hop: {"artifact": <raw, json-safe>, "surfaces": set, "shape": <str>}}`` for every
    hop in ``HOPS``."""
    text = text or ""
    hop: dict = {h: {"artifact": None, "surfaces": set(), "shape": ""} for h in HOPS}

    # --- RAW_TEXT — the substrate, tokenised. ---
    raw_surf = _surfaces_of_text(text)
    n_tok = len(_WORD.findall(text)) + len(_NUMERIC.findall(text))
    hop["raw_text"] = {
        "artifact": {"text": text, "tokens": n_tok, "chars": len(text)},
        "surfaces": raw_surf,
        "shape": f'str (utterance) — {n_tok} tokens, {len(text)} chars',
    }

    with _temp_store(memory_lirf, world_state):
        name = f"{SYNTH}_{secrets.token_hex(3)}"

        # --- ENTITIES — extract() candidate facts + the salient surfaces a reader would name. The
        #     representation here is {trait, value} candidates (the SHAPE the rule extractor carves
        #     out of raw text) UNIONED with the deterministic salient units (proper nouns / temporal
        #     / tone) so a token the rules didn't catch is still SEEN at this hop. ---
        try:
            ents = memory_lirf.extract(text) or []
        except Exception:
            ents = []
        units = []
        try:
            units = _salient_units(text)
        except Exception:
            units = []
        ent_surf = _fact_surfaces(ents)
        for u in units:
            if u.get("key"):
                ent_surf.add(u["key"])
        hop["entities"] = {
            "artifact": {
                "candidates": [{"trait": e.get("trait"), "value": e.get("value")} for e in ents],
                "salient": [{"category": u["category"], "surface": u["surface"]} for u in units],
            },
            "surfaces": ent_surf,
            "shape": (f'list[candidate{{trait,value}}] × {len(ents)}  +  '
                      f'list[salient{{category,surface}}] × {len(units)}'),
        }

        # --- RELATIONS — world_state.capture() edge TUPLES, the stated causal/relational links
        #     BEFORE any persistence: (subject, predicate, object, kind, topic). ---
        try:
            rel_tuples = world_state.capture(text) or []
        except Exception:
            rel_tuples = []
        rel_surf = _edge_tuple_surfaces(rel_tuples)
        hop["relations"] = {
            "artifact": {"edges": [{"subject": e[0], "predicate": e[1], "object": e[2],
                                    "kind": e[3]} for e in rel_tuples if len(e) >= 4]},
            "surfaces": rel_surf,
            "shape": f'list[edge-tuple(subj,pred,obj,kind)] × {len(rel_tuples)}',
        }

        # --- FACTS — persist + RELOAD FROM DISK. The durable LIRF rows that SURVIVE: this is the
        #     FORM facts take on disk ({trait, value, confidence}). A candidate at ENTITIES absent
        #     here fell out at persistence (or was never a durable fact, e.g. a tone word). ---
        try:
            fs = memory_lirf.Facts.load(name)
            for c in (memory_lirf.capture(name, text) or []):
                fs.merge(c)
            fs.save(name)
        except Exception:
            pass
        try:
            fact_rows = list(memory_lirf.Facts.load(name).about())
        except Exception:
            fact_rows = []
        fact_surf = _fact_surfaces(fact_rows)
        hop["facts"] = {
            "artifact": {"rows": [{"trait": r.get("trait"), "value": r.get("value"),
                                   "confidence": r.get("confidence")} for r in fact_rows]},
            "surfaces": fact_surf,
            "shape": f'list[LIRF-row{{trait,value,confidence}}] × {len(fact_rows)} (on disk)',
        }

        # --- GRAPH_EDGES — persist the world relations + reload. The typed relation graph on disk:
        #     {subject, predicate, object, kind, confidence}. ---
        try:
            world_state.capture_relations(name, text)
        except Exception:
            pass
        try:
            edges = list(world_state.World.load(name).active())
        except Exception:
            edges = []
        edge_surf = _edge_dict_surfaces(edges)
        hop["graph_edges"] = {
            "artifact": {"edges": [{"subject": e.get("subject"), "predicate": e.get("predicate"),
                                    "object": e.get("object"), "kind": e.get("kind"),
                                    "confidence": e.get("confidence")} for e in edges]},
            "surfaces": edge_surf,
            "shape": f'list[edge-dict{{subj,pred,obj,kind,confidence}}] × {len(edges)} (on disk)',
        }

        # --- RETRIEVAL_CANDIDATES — what a turn FETCHES back for this query: the router-selected
        #     LIRF rows (or the broad-query full block) + the world_state.situation() connected
        #     cluster (nodes + edges). This is the shape RETRIEVAL hands the mouth. ---
        rt_rows = _select_rows(name, text)
        try:
            cluster = world_state.situation(name, text, hops=2) or {}
        except Exception:
            cluster = {}
        rc_surf = _fact_surfaces(rt_rows) | _cluster_surfaces(cluster)
        cl_nodes = list(cluster.get("nodes") or [])
        cl_edges = [e for e in (cluster.get("edges") or []) if isinstance(e, dict)]
        hop["retrieval_candidates"] = {
            "artifact": {
                "rows": [{"trait": r.get("trait"), "value": r.get("value")} for r in rt_rows],
                "cluster": {"seed": list(cluster.get("seed") or []), "nodes": cl_nodes,
                            "edges": [{"subject": e.get("subject"),
                                       "predicate": e.get("predicate"),
                                       "object": e.get("object")} for e in cl_edges]},
            },
            "surfaces": rc_surf,
            "shape": (f'list[selected-row] × {len(rt_rows)}  +  '
                      f'cluster{{nodes:{len(cl_nodes)}, edges:{len(cl_edges)}}}'),
        }

        # --- PROMPT_CONTEXT — the assembled prompt block the mouth would bind. READ-ONLY mouth
        #     signal: NO brain, NO model — only the deterministic binding blocks. spine.bind(rows)
        #     + the Facts.block() broad-query fallback (the mouth's own fallback) +
        #     render_situation(cluster). This is the FORM the data takes as model-facing context. ---
        parts = []
        if _spine is not None:
            try:
                fb = _spine.bind(rt_rows, text)
                if fb:
                    parts.append(fb)
            except Exception:
                pass
        try:
            blk = memory_lirf.Facts.load(name).block()
            if blk:
                parts.append(blk)
        except Exception:
            pass
        try:
            if cl_edges:
                sit = world_state.render_situation(cluster)
                if sit and sit.strip():
                    parts.append(sit)
        except Exception:
            pass
        prompt = "\n\n".join(parts)
        pc_surf = _surfaces_of_text(prompt)
        hop["prompt_context"] = {
            "artifact": {"prompt_chars": len(prompt), "blocks": len(parts),
                         "preview": prompt[:240]},
            "surfaces": pc_surf,
            "shape": f'str (assembled prompt block) — {len(prompt)} chars, {len(parts)} block(s)',
        }

        # --- OUTPUT — the licensed-surface boundary. We do NOT run a model (deterministic + offline
        #     by guardrail); OUTPUT is the set of surfaces the prompt context LICENSES a reply to
        #     use — the honest deterministic end of the chain. A token absent here is one the model
        #     could only produce by hallucination, not from the pipeline. ---
        hop["output"] = {
            "artifact": {"licensed_surfaces": sorted(pc_surf),
                         "note": "deterministic boundary: surfaces the prompt context licenses "
                                 "(no model run)"},
            "surfaces": set(pc_surf),
            "shape": f'set[licensed-surface] × {len(pc_surf)} (no model; deterministic boundary)',
        }

    return hop


# ===================================================================================
# THE SHAPE DIFF — for every adjacent hop pair, what was added / removed / transformed. Added and
# removed are plain set differences over the surface keys. TRANSFORMED is the interesting case: a
# surface that LEFT the previous hop AND is matched by a survivor at this hop whose key derives
# from the same source token — we detect it by tracking, per original RAW token, every form its
# normalised key took across the chain, and crediting a "transform" when the key changes but the
# token's lineage continues.
# ===================================================================================
def _hop_surface(chain: dict, hop: str) -> set:
    return set(chain.get(hop, {}).get("surfaces") or set())


def shape_diffs(chain: dict) -> list:
    """The per-transition diff for every adjacent hop. Returns a list of
    ``{"from", "to", "added":[keys], "removed":[keys], "transformed":[{from_key,to_key}]}``.

    added/removed are set differences of the surface KEYS. transformed pairs a removed key with an
    added key when both fold to the SAME alphabetic stem (a representation change of one token —
    e.g. the raw span "Maya"/key ``maya`` is unchanged across hops, but a value like "Q3 launch"
    losing its words while gaining the node ``q3 launch`` is a transform, not a pure add/remove).
    A removed key with no same-stem survivor is a genuine LOSS (it stays in ``removed``)."""
    diffs = []
    for a, b in zip(HOPS, HOPS[1:]):
        sa, sb = _hop_surface(chain, a), _hop_surface(chain, b)
        added = sb - sa
        removed = sa - sb
        transformed = []
        # pair a removed key with an added key sharing the same alpha-stem (a re-shaped token).
        rem_by_stem = {}
        for k in removed:
            rem_by_stem.setdefault(_alpha_stem(k), []).append(k)
        consumed_added, consumed_removed = set(), set()
        for k in sorted(added):
            st = _alpha_stem(k)
            pool = [r for r in rem_by_stem.get(st, []) if r not in consumed_removed]
            if pool and k != pool[0]:
                transformed.append({"from_key": pool[0], "to_key": k})
                consumed_removed.add(pool[0])
                consumed_added.add(k)
        diffs.append({
            "from": a,
            "to": b,
            "added": sorted(added - consumed_added),
            "removed": sorted(removed - consumed_removed),
            "transformed": transformed,
        })
    return diffs


def _alpha_stem(k: str) -> str:
    """The alphabetic stem of a normalised key, for transform matching: drop digits/spaces so
    'q3launch' and 'launch' relate, and a trailing plural/tense is already folded by _norm_unit."""
    return re.sub(r"[^a-z]", "", str(k or ""))


# ===================================================================================
# THE LOCATOR — "where was <token> lost / transformed?" Walk the chain for a token and report the
# FORM it took at each hop (the key present, if any), the LAST hop that carried it, the hop where
# its representation changed, and the hop where it dropped. Deterministic; the answer is a
# structured record, not an eyeball job.
# ===================================================================================
def _token_keys(token: str) -> set:
    """Every normalised key a query token could match: its own norm, plus the per-word norms (so
    'last week' matches the key for 'week' and the whole 'last week')."""
    keys = set()
    whole = _norm_unit(token)
    if whole:
        keys.add(whole)
    for tok in _WORD.findall(token or "") + _NUMERIC.findall(token or ""):
        k = _norm_unit(tok)
        if k:
            keys.add(k)
    return keys


def locate(chain: dict, token: str) -> dict:
    """WHERE was ``token`` lost / transformed? Walk the hop chain and return:

        {
          "token":        the query token,
          "keys":         the normalised keys it matches,
          "present_at":   [hop, …]                # hops whose surfaces carry the token,
          "shapes":       {hop: "<the key/form carried there, or '∅'>"},
          "last_carried": <hop or None>,          # last hop that still has it,
          "lost_at":      <hop or None>,          # first hop AFTER it was present that drops it,
          "transformed_at":[ {hop, from_key, to_key}, … ],  # hops where its FORM changed,
          "verdict":      <one-line human summary>,
        }

    A token never present anywhere -> lost_at = the first hop (it never entered the pipeline).

    GAPS are the heart of the "where was X lost?" query: a token can survive to the OUTPUT prompt
    (because the assembled block re-states it) yet be ABSENT from an intermediate hop it should
    have populated. The most decision-relevant gap is a DURABLE-RECORD gap — the token is missing
    from FACTS and/or GRAPH_EDGES (the on-disk record), so it is NOT something Vera will remember
    past this turn even though it's in this turn's prompt. ``gaps`` names every such interior hop;
    the verdict leads with a durable-record gap when one exists, because that is the real loss.
    Never raises."""
    keys = _token_keys(token)
    present_at, shapes = [], {}
    for h in HOPS:
        surf = _hop_surface(chain, h)
        hit = sorted(keys & surf)
        shapes[h] = ", ".join(hit) if hit else "∅"
        if hit:
            present_at.append(h)

    # transforms involving this token: a diff transition whose from_key OR to_key is one of ours.
    transformed_at = []
    for d in shape_diffs(chain):
        for t in d.get("transformed", []):
            fk, tk = t.get("from_key"), t.get("to_key")
            if (fk in keys or tk in keys
                    or _alpha_stem(fk) in {_alpha_stem(k) for k in keys}
                    or _alpha_stem(tk) in {_alpha_stem(k) for k in keys}):
                transformed_at.append({"hop": d["to"], "from_key": fk, "to_key": tk})

    last_carried = present_at[-1] if present_at else None
    # lost_at: the first hop, AFTER the token was first seen, whose surfaces drop it (and it never
    # returns at a strictly-later hop). If never seen at all, it was lost before entry (hop[0]).
    lost_at = None
    if not present_at:
        lost_at = HOPS[0]
    else:
        first_idx = HOPS.index(present_at[0])
        for i in range(first_idx + 1, len(HOPS)):
            h = HOPS[i]
            if h not in present_at and not any(later in present_at for later in HOPS[i:]):
                lost_at = h
                break

    # GAPS — interior hops the token is ABSENT from while present both before AND after (it dipped
    # out and came back, e.g. a temporal that isn't a durable FACT but resurfaces as a graph edge /
    # in the prompt block). Computed only over the span the token actually traverses.
    gaps = []
    if present_at:
        first_idx = HOPS.index(present_at[0])
        last_idx = HOPS.index(present_at[-1])
        for i in range(first_idx + 1, last_idx):
            h = HOPS[i]
            if h not in present_at:
                gaps.append(h)
    # the subset of gaps that are DURABLE-RECORD hops — the loss that actually costs memory.
    _DURABLE = ("facts", "graph_edges")
    durable_gaps = [h for h in gaps if h in _DURABLE]

    # verdict — the human one-liner. Lead with the most informative finding, in priority order:
    # never-entered > genuinely-dropped > durable-record gap > pure transform > clean survival.
    if not present_at:
        verdict = (f'"{token}" never entered the pipeline — no hop carries it '
                   f'(lost before {HOPS[0].upper()}).')
    elif lost_at is not None:
        extra = ""
        if transformed_at:
            lt = transformed_at[-1]
            extra = f' (transformed at {lt["hop"].upper()}: {lt["from_key"]} → {lt["to_key"]})'
        verdict = (f'"{token}" last carried at {last_carried.upper()}, '
                   f'dropped at {lost_at.upper()}{extra}.')
    elif durable_gaps:
        where = " & ".join(_HOP_LABEL.get(h, h) for h in durable_gaps)
        verdict = (f'"{token}" reaches the prompt but is ABSENT from the durable record '
                   f'({where}) — it survives THIS turn but is not stored to remember.')
    elif transformed_at:
        last_t = transformed_at[-1]
        verdict = (f'"{token}" survives to {last_carried.upper()}, '
                   f'transformed at {last_t["hop"].upper()} '
                   f'({last_t["from_key"]} → {last_t["to_key"]}).')
    else:
        verdict = f'"{token}" survives the whole chain (last carried at {last_carried.upper()}).'

    return {
        "token": token,
        "keys": sorted(keys),
        "present_at": present_at,
        "shapes": shapes,
        "last_carried": last_carried,
        "lost_at": lost_at,
        "gaps": gaps,
        "durable_gaps": durable_gaps,
        "transformed_at": transformed_at,
        "verdict": verdict,
    }


# ===================================================================================
# THE REPORT — one input's full shape-transformation chain + a set of locators.
# ===================================================================================
def dataflow_report(text: str, locate_tokens=None) -> dict:
    """The DATA FLOW report for ONE utterance: the per-hop shape chain, the per-transition shape
    diffs, and a locator for each requested token. ``locate_tokens`` defaults to the salient units
    the input names (so the report self-selects the interesting tokens to follow). Deterministic,
    offline, isolated. Never raises: a bad input yields a chain with only RAW_TEXT populated."""
    text = text or ""
    chain = trace_pipeline(text)
    diffs = shape_diffs(chain)

    if locate_tokens is None:
        # auto-pick: the surfaces a reader would name (entities/temporal/tone), so the locator
        # demonstrates the interesting "where did X go?" cases without the caller guessing.
        toks, seen = [], set()
        try:
            for u in _salient_units(text):
                s = u["surface"]
                if s.lower() not in seen:
                    seen.add(s.lower())
                    toks.append(s)
        except Exception:
            pass
        locate_tokens = toks
    locators = [locate(chain, t) for t in (locate_tokens or [])]

    # a json-safe projection of the chain (surfaces -> sorted lists).
    chain_json = {}
    for h in HOPS:
        c = chain.get(h, {})
        chain_json[h] = {
            "cons_stage": HOP_TO_CONS_STAGE.get(h),
            "shape": c.get("shape", ""),
            "surfaces": sorted(c.get("surfaces") or set()),
            "artifact": c.get("artifact"),
        }

    return {"input": text, "hops": list(HOPS), "chain": chain_json,
            "diffs": diffs, "locators": locators}


# The battery — the SAME information-rich inputs conservation.py names, so the two observatories
# can be read side by side on identical inputs.
BATTERY = [
    "I moved to Austin because my manager changed",
    "My daughter Maya started kindergarten last week",
    "I've been really stressed about the Q3 launch",
    "We adopted a dog named Cooper in 2024",
    "My wife Jen and I are excited about the move to Denver in March",
    "I work at Collatio and I'm worried about money lately",
]


def run_battery(inputs=None) -> dict:
    """Run the data-flow observatory over a battery of inputs. Returns one report per input."""
    inputs = list(inputs) if inputs is not None else list(BATTERY)
    return {"reports": [dataflow_report(t) for t in inputs]}


# ===================================================================================
# RENDER — human-readable shape-transformation chain.
# ===================================================================================
_HOP_LABEL = {
    "raw_text": "RAW TEXT",
    "entities": "ENTITIES",
    "relations": "RELATIONS",
    "facts": "FACTS",
    "graph_edges": "GRAPH EDGES",
    "retrieval_candidates": "RETRIEVAL CANDIDATES",
    "prompt_context": "PROMPT CONTEXT",
    "output": "OUTPUT",
}


def _fmt_artifact_lines(hop: str, art) -> list:
    """A couple of compact lines showing the actual REPRESENTATION at a hop (not just its shape
    string) — the facts/edges/cluster the engines produced, so the FORM is concrete."""
    out = []
    if not isinstance(art, dict):
        return out
    if hop == "raw_text":
        out.append(f'      "{art.get("text", "")}"')
    elif hop == "entities":
        for c in art.get("candidates", []):
            out.append(f'      fact-candidate: {c.get("trait")} = {c.get("value")}')
        sal = art.get("salient", [])
        if sal:
            out.append("      salient: "
                       + ", ".join(f'{u["surface"]}[{u["category"]}]' for u in sal))
    elif hop == "relations":
        for e in art.get("edges", []):
            out.append(f'      {e.get("subject")} --{e.get("predicate")}--> '
                       f'{e.get("object")} [{e.get("kind")}]')
    elif hop == "facts":
        for r in art.get("rows", []):
            out.append(f'      {r.get("trait")} = {r.get("value")} '
                       f'(conf {r.get("confidence")})')
    elif hop == "graph_edges":
        for e in art.get("edges", []):
            out.append(f'      {e.get("subject")} --{e.get("predicate")}--> {e.get("object")}')
    elif hop == "retrieval_candidates":
        for r in art.get("rows", []):
            out.append(f'      row: {r.get("trait")} = {r.get("value")}')
        cl = art.get("cluster", {})
        if cl.get("nodes"):
            out.append(f'      cluster nodes: {", ".join(cl["nodes"])}')
    elif hop == "prompt_context":
        if art.get("prompt_chars"):
            out.append(f'      {art.get("blocks")} block(s), {art.get("prompt_chars")} chars')
    elif hop == "output":
        ls = art.get("licensed_surfaces", [])
        if ls:
            out.append(f'      licensed surfaces ({len(ls)}): '
                       + ", ".join(ls[:14]) + (" …" if len(ls) > 14 else ""))
    return out


def render_report(rep: dict) -> str:
    out = []
    out.append(f'INPUT:  "{rep["input"]}"')
    out.append("")
    out.append("  SHAPE-TRANSFORMATION CHAIN (the representation at each hop):")
    chain = rep["chain"]
    diff_by = {(d["from"], d["to"]): d for d in rep["diffs"]}
    prev = None
    for h in rep["hops"]:
        c = chain.get(h, {})
        out.append(f'    [{_HOP_LABEL.get(h, h):<20}]  {c.get("shape", "")}')
        for line in _fmt_artifact_lines(h, c.get("artifact")):
            out.append(line)
        # the diff INTO this hop (from the previous one).
        if prev is not None:
            d = diff_by.get((prev, h))
            if d:
                bits = []
                if d["added"]:
                    bits.append("+ " + ", ".join(d["added"][:8])
                                + (" …" if len(d["added"]) > 8 else ""))
                if d["removed"]:
                    bits.append("- " + ", ".join(d["removed"][:8])
                                + (" …" if len(d["removed"]) > 8 else ""))
                if d["transformed"]:
                    bits.append("~ " + ", ".join(f'{t["from_key"]}→{t["to_key"]}'
                                                  for t in d["transformed"][:6]))
                if bits:
                    out.append("           diff: " + "   ".join(bits))
                else:
                    out.append("           diff: (no surface change)")
        prev = h
    # the locators.
    if rep.get("locators"):
        out.append("")
        out.append("  WHERE WAS <token> LOST / TRANSFORMED?")
        for loc in rep["locators"]:
            out.append(f'    • {loc["verdict"]}')
            path = " -> ".join(f'{_HOP_LABEL.get(h, h).split()[0]}:{loc["shapes"][h]}'
                               for h in rep["hops"] if loc["shapes"].get(h) != "∅")
            if path:
                out.append(f'        carried: {path}')
            if loc.get("gaps"):
                out.append("        gap (absent here): "
                           + ", ".join(_HOP_LABEL.get(h, h) for h in loc["gaps"]))
    return "\n".join(out)


def render(report: dict) -> str:
    out = []
    out.append("=" * 79)
    out.append("VERA DATA FLOW OBSERVATORY — distributed tracing for cognition / Shape Diff")
    out.append("A unit of input traced through the pipeline: its SHAPE at each transformation,")
    out.append("the per-hop DIFF (+ added / - removed / ~ transformed), and a 'where was X lost?'")
    out.append("locator. Complementary to the Conservation Observatory: that shows the loss RATE,")
    out.append("this shows the FORM the representation takes — and where it changes.")
    out.append("=" * 79)
    out.append("CHAIN:  RAW TEXT -> ENTITIES -> RELATIONS -> FACTS -> GRAPH EDGES")
    out.append("        -> RETRIEVAL CANDIDATES -> PROMPT CONTEXT -> OUTPUT")
    for rep in report["reports"]:
        out.append("")
        out.append("-" * 79)
        out.append(render_report(rep))
    out.append("")
    return "\n".join(out)


# ===================================================================================
# SELF-TEST — proves the chain captures the REAL shapes (not hardcoded), a known transformation is
# shown, and a known loss is located at the correct hop, DETERMINISTICALLY — all while asserting the
# real .anima footprint is byte-unchanged.
# ===================================================================================
def _selftest() -> int:  # pragma: no cover - exercised via __main__
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("data-flow observatory self-test")

    # GUARDRAIL — snapshot the real .anima footprint BEFORE any pipeline run.
    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima)

    # ---- 1) The chain captures the REAL shapes (not hardcoded). Run the canonical Maya input and
    #         assert each hop's shape/artefact reflects what the live engines actually produced. ----
    maya = "My daughter Maya started kindergarten last week"
    rep = dataflow_report(maya)
    chain = rep["chain"]

    # determinism: a second run yields a byte-identical chain (surfaces/shape/diffs).
    rep2 = dataflow_report(maya)
    ok("chain is DETERMINISTIC (two runs identical)",
       rep["chain"] == rep2["chain"] and rep["diffs"] == rep2["diffs"])

    # RAW_TEXT really is the input.
    ok("RAW_TEXT hop carries the verbatim input",
       chain["raw_text"]["artifact"]["text"] == maya
       and "maya" in chain["raw_text"]["surfaces"])

    # ENTITIES really came from extract() — the fact candidate daughter=Maya is present (REAL, not
    # hardcoded: it's whatever memory_lirf.extract returned this run).
    ent_cands = chain["entities"]["artifact"]["candidates"]
    ok("ENTITIES hop = the REAL extract() output (daughter=Maya candidate present)",
       any(c["trait"] == "daughter" and c["value"] == "Maya" for c in ent_cands))

    # FACTS really is the on-disk reload — the durable row daughter=Maya survived persistence.
    fact_rows = chain["facts"]["artifact"]["rows"]
    ok("FACTS hop = the durable on-disk reload (daughter=Maya row survived)",
       any(r["trait"] == "daughter" and r["value"] == "Maya" for r in fact_rows))

    # GRAPH_EDGES really is the world graph reload — a 'daughter' node/edge exists.
    ok("GRAPH_EDGES hop = the REAL world graph (a 'daughter' edge is present)",
       "daughter" in chain["graph_edges"]["surfaces"])

    # RETRIEVAL_CANDIDATES really fetched a cluster around the topic — 'maya' is reachable.
    ok("RETRIEVAL_CANDIDATES hop fetched a real cluster carrying 'maya'",
       "maya" in chain["retrieval_candidates"]["surfaces"])

    # PROMPT_CONTEXT really assembled a non-empty block that names Maya (the binding actually
    # carried the fact into model-facing context).
    ok("PROMPT_CONTEXT hop assembled a real prompt block carrying 'maya'",
       chain["prompt_context"]["artifact"]["prompt_chars"] > 0
       and "maya" in chain["prompt_context"]["surfaces"])

    # ---- 2) A KNOWN TRANSFORMATION is shown: raw "my daughter Maya" -> fact daughter=Maya at the
    #         capture hop. The locator for "Maya" must show it carried from RAW_TEXT THROUGH the
    #         FACTS hop (the capture transform), i.e. it appears as a durable fact value. ----
    loc_maya = locate(chain, "Maya")
    ok("LOCATOR(Maya): carried at RAW_TEXT and still at FACTS (the capture transform)",
       "raw_text" in loc_maya["present_at"] and "facts" in loc_maya["present_at"])
    ok("LOCATOR(Maya): survives into PROMPT_CONTEXT (the fact reached the prompt)",
       "prompt_context" in loc_maya["present_at"])
    # and the FACTS-hop diff (relations -> facts) shows daughter=Maya arriving as a durable value:
    # 'maya' must be in the FACTS hop surfaces but the *candidate* shape changed from a raw span to
    # a {trait,value} row — proven by the ENTITIES artefact being a candidate and FACTS a row.
    ok("KNOWN TRANSFORM: 'my daughter Maya' (raw span) -> daughter=Maya (durable fact row)",
       any(c["value"] == "Maya" for c in ent_cands)
       and any(r["trait"] == "daughter" and r["value"] == "Maya" for r in fact_rows))

    # ---- 3) A KNOWN LOSS is located at the correct hop, DETERMINISTICALLY. Two clean cases: ----
    # (a) The tone word "stressed" is NOT a durable fact: in the Q3 input, extract() returns no
    #     fact for it; it survives only as a relation predicate, never as a FACTS-hop value. So the
    #     locator must report it dropping at the FACTS hop (present at RELATIONS, gone at FACTS as a
    #     fact value — the tone word is not kept AS a durable fact).
    q3 = "I've been really stressed about the Q3 launch"
    rep_q3 = dataflow_report(q3)
    chain_q3 = rep_q3["chain"]
    # 'stressed' folds to key 'stress' (conservation's stem). It appears in RELATIONS (predicate
    # stressed_by) but extract() yields NO durable fact -> the FACTS hop has no fact carrying it.
    stress_keys = _token_keys("stressed")
    in_relations = bool(stress_keys & set(chain_q3["relations"]["surfaces"]))
    fact_rows_q3 = chain_q3["facts"]["artifact"]["rows"]
    not_a_fact = not any(stress_keys & _fact_surfaces([r]) for r in fact_rows_q3)
    ok("KNOWN LOSS setup: 'stressed' is a RELATION predicate but NOT a durable FACT value",
       in_relations and not_a_fact and len(fact_rows_q3) == 0)
    loc_stress = locate(chain_q3, "stressed")
    # The relation predicate keeps it reachable at the graph/retrieval/prompt hops, so the honest
    # locator says: present at RELATIONS, and the verdict mentions where its durable form is absent.
    ok("LOCATOR(stressed): present at RELATIONS (kept only as a stated relation)",
       "relations" in loc_stress["present_at"])
    ok("LOCATOR(stressed): NOT present at FACTS (the durable-fact form was lost there)",
       "facts" not in loc_stress["present_at"])

    # (b) A token absent from the whole input is reported as never-entered, at the first hop.
    loc_absent = locate(chain, "Zorblax")
    ok("LOCATOR(absent token): reported lost before RAW_TEXT (never entered the pipeline)",
       loc_absent["present_at"] == [] and loc_absent["lost_at"] == HOPS[0])

    # (c) THE DATE DROP — the brief's headline locator case. The temporal "last week" in the Maya
    #     input is NOT a durable LIRF fact (extract() makes no temporal fact), so it is ABSENT from
    #     the FACTS hop, yet it survives as a graph edge (started_when --> last week) and into the
    #     prompt. The locator must report a DURABLE-RECORD gap at FACTS (deterministically), i.e.
    #     "reaches the prompt but is not stored to remember" — the precise 'where did the date go?'.
    loc_week = locate(chain, "week")
    ok("LOCATOR(date 'week'): durable-record GAP at FACTS (date not stored as a durable fact)",
       "facts" in loc_week["gaps"] and "facts" in loc_week["durable_gaps"]
       and "graph_edges" in loc_week["present_at"])
    ok("LOCATOR(date 'week'): verdict names the durable-record loss (not 'survives cleanly')",
       "durable record" in loc_week["verdict"].lower())

    # ---- 4) The shape DIFF mechanism works: between RAW_TEXT and ENTITIES, the entity surfaces are
    #         a subset/relation of raw (nothing is invented from nowhere at the very first carve),
    #         and the diff structure is well-formed for every transition. ----
    diffs = rep["diffs"]
    ok("shape_diffs produced one entry per hop transition",
       len(diffs) == len(HOPS) - 1
       and all(set(d) >= {"from", "to", "added", "removed", "transformed"} for d in diffs))
    # at least one transition must report a real transformation OR a real loss somewhere in the
    # battery-representative Maya input (the chain is not a flat identity).
    any_change = any(d["added"] or d["removed"] or d["transformed"] for d in diffs)
    ok("the chain shows real transformation (not a flat identity)", any_change)

    # ---- 5) Robustness: a malformed/empty input yields an honest minimal chain, never a crash. ----
    rep_empty = dataflow_report("")
    ok("empty input yields a chain with only RAW_TEXT populated, no crash",
       rep_empty["chain"]["raw_text"]["artifact"]["text"] == ""
       and rep_empty["chain"]["facts"]["artifact"]["rows"] == [])
    rep_garbage = dataflow_report("!!! ??? ... ;;;")
    ok("garbage input does not raise and produces a chain", isinstance(rep_garbage, dict))

    # ---- 6) JSON-serialisable (the --json contract): the whole battery report dumps cleanly. ----
    try:
        json.dumps(run_battery(), allow_nan=False)
        json_ok = True
    except Exception as e:
        json_ok = False
        print("    json error:", e)
    ok("the full battery report is JSON-serialisable (--json contract)", json_ok)

    # ---- GUARDRAIL — the real .anima footprint is byte-UNCHANGED after every pipeline run. ----
    fp_after = _footprint(real_anima)
    ok(f"HERMETIC: real .anima byte-unchanged ({fp_before[1]} files, "
       f"{(fp_before[0] or '')[:12]}… == {(fp_after[0] or '')[:12]}…)",
       fp_before == fp_after)

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("ALL DATAFLOW SELFTESTS PASS")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vera Data Flow Observatory — the Shape Diff Viewer.")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--selftest", action="store_true", help="assert the chain captures REAL shapes")
    ap.add_argument("--input", default=None,
                    help="trace ONE custom utterance instead of the battery")
    ap.add_argument("--where", default=None,
                    help='locate a token in the (single) traced input, e.g. --where Maya')
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    # Single-input mode (optionally with a focused --where locator), else the battery.
    if args.input is not None:
        toks = [args.where] if args.where else None
        rep = dataflow_report(args.input, locate_tokens=toks)
        report = {"reports": [rep]}
    else:
        report = run_battery()

    if args.json:
        print(json.dumps(report, indent=2, allow_nan=False))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
