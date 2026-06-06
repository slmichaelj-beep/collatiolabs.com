"""
lerf — the LERF (Ledger of Externalized, Retrievable, Falsifiable cognition) engine.

THE BET. A large language model is a black box: its competence is smeared across
billions of opaque weights, none of which you can read, verify, correct, or reuse on
purpose. To make a small local model do real work you currently *stuff the prompt* —
paste the whole transcript, the whole policy, three worked examples — and pay for those
thousands of tokens every single turn while still trusting a tensor you cannot inspect.

LERF moves the reusable intelligence OUT of the weights and the prompt and INTO
structured, inspectable, retrievable, certifiable COGNITIVE OBJECTS. A skill is no longer
"whatever the model learned to do" — it is a named procedure with explicit inputs, steps,
outputs, a confidence, a provenance, and a list of its own failure modes, sitting in a
ledger you can open in a text editor. At run time you RETRIEVE the one object the task
needs and assemble a COMPACT context (hundreds of tokens), instead of stuffing the model
with thousands. A small model + this substrate handles most of what prompt-stuffing a big
model did, and — unlike a weight — you can read exactly why.

This module is Wave 1 of 3: the FORMAT and the proof that the format compresses. It is a
proven STANDALONE substrate this wave — it is deliberately NOT wired into the live reply
path. Where the later waves attach is noted at each seam (search "ATTACHES:").

Three object types, each a dict carrying a verification STATE so the store is a ledger of
*claims about its own reliability*, never a pile of unaudited assertions:

  * SKILL     — a reusable capability: inputs -> steps -> outputs, with failure_modes.
  * CONCEPT   — a unit of understanding: definition, prerequisites, common misunderstandings.
  * PROCEDURE — a runnable recipe compiled for a concrete task: inputs_needed, tools, steps.

Verification ladder (STATE): candidate -> verified -> active (hand/test-confirmed, eligible
for retrieval) ; deprecated / rejected are kept on disk but never retrieved. Every object
also carries: last_verified, confidence, source, support[], failure_modes[].

Storage discipline MIRRORS memory_lirf exactly: STORE = Path(".anima") (redirectable for
hermetic tests), one append-only-style flat file per creature at `.anima/{name}.lerf.json`,
persisted via util.save_json / util.load_json (atomic temp-write+rename, sealed under
ANIMA_KEY iff set) — NEVER a bespoke open()/JSONL writer that would leave this ledger
plaintext while the rest of .anima is sealed. reliability.SPECS registers `.lerf.json` so a
corrupt store self-heals from a backup under ANIMA LAW 001 (see the note by `_load_objects`).

Retrieval is DETERMINISTIC keyword + domain matching (no model, no embeddings, O(rows)):
the same discipline memory_lirf.retrieve / organs.router.select_facts use for facts, lifted
to skills/concepts/procedures. Given a task string we score every active object's searchable
text against the task's keywords and return the most relevant — reproducibly, offline.

NOT in Wave 1 (each noted where it attaches):
  * the distiller that turns verified skills into a small fine-tune (Phase 5);
  * the runtime router that injects a retrieved skill into mouth/server (Phase 3b / Wave 2);
  * the benchmark harness small-model-vs-stuffed-prompt (Wave 2);
  * the certification section that promotes verified -> active under a cert (Wave 3).
"""

from __future__ import annotations

import math
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .util import save_json, load_json

# Redirectable per-creature store root, exactly like memory_lirf.STORE. Tests redirect
# THIS attribute (on both the __main__ and package bindings) to a temp dir; never read a
# module-local copy.
STORE = Path(".anima")

VERSION = 1

# ---------------------------------------------------------------------------
# VERIFICATION STATE — the ladder every cognitive object climbs. A store is only
# as trustworthy as the audit state of its objects, so the state is a first-class
# field, not a comment. Only ACTIVE objects are retrievable (candidate/verified are
# in-flight; deprecated/rejected are kept for provenance but never served).
# ---------------------------------------------------------------------------
CANDIDATE = "candidate"     # freshly proposed, unverified
VERIFIED = "verified"       # passed verify_skill / verify_procedure_output but not yet promoted
ACTIVE = "active"           # hand- or test-confirmed; the only state retrieval will serve
DEPRECATED = "deprecated"   # superseded; kept on disk, never retrieved
REJECTED = "rejected"       # failed verification; kept on disk as a negative result

STATES = frozenset({CANDIDATE, VERIFIED, ACTIVE, DEPRECATED, REJECTED})
# The states retrieval is allowed to serve. (ATTACHES: Wave 3 cert promotes verified->active.)
RETRIEVABLE_STATES = frozenset({ACTIVE})

# Confidence a hand-built, hand-verified seed skill enters at (see scripts/build_lerf.py).
CONF_SEED = 0.9
# Confidence a freshly compiled procedure / candidate enters at (unproven plumbing).
CONF_CANDIDATE = 0.5
# A passed verify_skill lifts confidence asymptotically toward this ceiling.
CONF_CEIL = 0.99


# ===================================================================================
# TOKENS — the deterministic, offline cost model behind the compression proof.
# No tiktoken, no network: a stable word+char heuristic that is monotonic in real
# token count, which is all the retrieved-vs-stuffed comparison needs. (Mirrors the
# word-tokenisation discipline in scripts/conservation.py — fixed rules, no model.)
# ===================================================================================
_WORD = re.compile(r"\w+|[^\w\s]")


def count_tokens(text) -> int:
    """Estimate the token cost of `text` deterministically and offline.

    Heuristic: the max of (a) a word/punctuation token count and (b) chars/4 — the
    char/4 rule is the well-known GPT-family rule of thumb, and taking the max keeps
    the estimate from *under*-counting dense or subword-heavy text. The exact constant
    does not matter: both sides of the compression comparison use this SAME function, so
    the RATIO it reports is honest even if any single absolute number is approximate."""
    if not text:
        return 0
    if not isinstance(text, str):
        text = _obj_to_text(text)
    words = len(_WORD.findall(text))
    chars = len(text)
    return max(words, (chars + 3) // 4)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    """A stable, sortable-ish id with a type prefix so an id is self-describing on sight
    (`skill_…`, `concept_…`, `proc_…`) — the same id discipline memory_lirf uses."""
    return f"{prefix}_{secrets.token_hex(5)}"


def _kw(text) -> set:
    """The lowercase keyword set of any text/object — the atom retrieval matches on.

    Stopwords are dropped so a query's *content* words drive the match, not 'the'/'a'.
    Short tokens (<=2 chars) and pure punctuation are dropped too. Deterministic."""
    if text is None:
        return set()
    if not isinstance(text, str):
        text = _obj_to_text(text)
    raw = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
    toks = set()
    for t in raw:
        # fold a trailing possessive/quote so "doctor's" matches "doctor"; keep internal
        # hyphens ("follow-up") which carry meaning.
        t = t.lower().rstrip("'").removesuffix("'s")
        if len(t) > 2 and t not in _STOP:
            toks.add(t)
    return toks


_STOP = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "your", "this", "that", "with",
    "from", "have", "has", "had", "was", "were", "will", "can", "all", "any", "each",
    "into", "out", "off", "its", "their", "them", "they", "she", "her", "him", "his",
    "our", "ours", "who", "what", "when", "where", "why", "how", "which", "than", "then",
    "there", "here", "been", "being", "does", "did", "done", "get", "got", "let", "via",
    "per", "use", "used", "using", "make", "makes", "made", "turn", "into", "onto",
})


# ===================================================================================
# SCHEMA — the three object factories. Each returns a plain dict (JSON-round-trippable)
# carrying the full verification spine. Unknown extra keys are tolerated on load, but the
# factories mint the canonical shape so a hand-built seed and a compiled object agree.
# ===================================================================================

def _spine(source: str, confidence: float, state: str, support=None,
           failure_modes=None) -> dict:
    """The verification fields every object type shares."""
    return {
        "state": state if state in STATES else CANDIDATE,
        "confidence": float(confidence),
        "last_verified": _now() if state in (ACTIVE, VERIFIED) else None,
        "source": source or "unspecified",
        "support": list(support or []),
        "failure_modes": list(failure_modes or []),
    }


def make_skill(name, domain, inputs, steps, outputs, *, confidence=CONF_SEED,
               source="hand-built", state=CANDIDATE, support=None, failure_modes=None,
               id=None) -> dict:
    """A SKILL: a reusable capability with an explicit inputs->steps->outputs contract.

    This is the unit that replaces "whatever the model happened to learn": every part is
    named, so the skill is inspectable (explain_skill) and falsifiable (verify_skill)."""
    obj = {
        "id": id or _new_id("skill"),
        "type": "skill",
        "name": str(name),
        "domain": str(domain),
        "inputs": list(inputs or []),
        "steps": list(steps or []),
        "outputs": list(outputs or []),
    }
    obj.update(_spine(source, confidence, state, support, failure_modes))
    return obj


def make_concept(name, definition, *, prerequisites=None, related=None, examples=None,
                 common_misunderstandings=None, confidence=CONF_SEED, source="hand-built",
                 state=CANDIDATE, support=None, failure_modes=None, id=None) -> dict:
    """A CONCEPT: a unit of understanding. `common_misunderstandings` is first-class
    because the cheapest way to make a small model reliable on a concept is to hand it the
    ways people (and models) get it WRONG, not just the definition."""
    obj = {
        "id": id or _new_id("concept"),
        "type": "concept",
        "name": str(name),
        "definition": str(definition),
        "prerequisites": list(prerequisites or []),
        "related": list(related or []),
        "examples": list(examples or []),
        "common_misunderstandings": list(common_misunderstandings or []),
    }
    obj.update(_spine(source, confidence, state, support, failure_modes))
    return obj


def make_procedure(name, *, inputs_needed=None, tools_needed=None, steps=None,
                   confidence=CONF_CANDIDATE, source="compiled", state=CANDIDATE,
                   support=None, failure_modes=None, id=None) -> dict:
    """A PROCEDURE: a runnable recipe compiled for a concrete task. Distinct from a SKILL
    in that it names the TOOLS it needs and is meant to be `run` against a context; a skill
    is the reusable know-how, a procedure is one assembled plan to apply it."""
    obj = {
        "id": id or _new_id("proc"),
        "type": "procedure",
        "name": str(name),
        "inputs_needed": list(inputs_needed or []),
        "tools_needed": list(tools_needed or []),
        "steps": list(steps or []),
    }
    obj.update(_spine(source, confidence, state, support, failure_modes))
    return obj


def _obj_to_text(obj: dict) -> str:
    """Flatten an object's human-meaningful fields into one searchable/countable string.
    Used by retrieval (keyword set) and by count_tokens (cost of the assembled context)."""
    if not isinstance(obj, dict):
        return str(obj)
    parts = []
    # scalar human-meaningful fields across ALL object types (skill/concept + the 6 added in
    # the COGNITIVE OBJECT TYPES section): the type-specific anchors a query matches on.
    for k in ("name", "domain", "definition", "subject", "condition", "action",
              "expectation", "applies_when", "fails_when", "decision", "trigger",
              "symptom", "consequence", "mitigation", "target"):
        v = obj.get(k)
        if v:
            parts.append(str(v))
    # list fields across ALL object types — flattened into the searchable/countable text.
    for k in ("inputs", "steps", "outputs", "prerequisites", "related", "examples",
              "common_misunderstandings", "inputs_needed", "tools_needed",
              "failure_modes", "criteria", "entities", "relations", "dynamics",
              "evidence", "options", "weights"):
        v = obj.get(k)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
    return "  ".join(parts)


def _searchable(obj: dict) -> set:
    """The keyword set retrieval scores a query against. Name/domain are weighted by
    being repeated into the set's source text by the caller; here we just gather them."""
    return _kw(_obj_to_text(obj))


# ===================================================================================
# STORE — one flat JSON file per creature, atomic + sealed via util (NEVER a bespoke
# writer). The on-disk shape is {"version", "objects":[...]} so a corrupt/garbage file is
# structurally distinguishable from an honestly-empty one (reliability gates on the
# `objects` list — see the Spec registered in anima/reliability.py).
# ===================================================================================

def _path(name: str) -> Path:
    return STORE / f"{name}.lerf.json"


def _load_objects(name: str) -> list:
    """Load a creature's cognitive objects, with LAW-001 self-healing when reliability is
    available (a corrupt ledger recovers from the most-recent good backup, else stops
    CLEANLY rather than silently returning zero objects — a clean stop beats a wrong empty).
    Falls back to the plain atomic loader if reliability can't be imported (degraded, never
    a hard dependency). Mirrors memory_lirf.Facts.load."""
    path = _path(name)
    try:
        from . import reliability
    except Exception:                       # pragma: no cover - reliability is core
        d = load_json(path)
        return d.get("objects", []) if isinstance(d, dict) else []
    d, info = reliability.guarded_store_load(
        name, path, store=STORE, kind="LERF ledger", expect_key="objects")
    objs = d.get("objects", []) if isinstance(d, dict) else []
    if info.get("ok") and not info.get("empty"):
        reliability.maybe_backup_store(name, path, store=STORE, kind="LERF ledger",
                                       expect_key="objects")
    return objs


def _save_objects(name: str, objects: list) -> None:
    STORE.mkdir(exist_ok=True)
    save_json(_path(name), {"version": VERSION, "objects": list(objects)})


def _upsert(name: str, obj: dict) -> dict:
    """Persist `obj`, replacing any existing object with the same id (an update), else
    appending. Append-only in spirit: a *superseded* object should be DEPRECATED in place
    (kept for provenance), not deleted — callers that change meaning mint a new id."""
    objs = _load_objects(name)
    by_id = {o.get("id"): i for i, o in enumerate(objs)}
    if obj.get("id") in by_id:
        objs[by_id[obj["id"]]] = obj
    else:
        objs.append(obj)
    _save_objects(name, objs)
    return obj


def _get(name: str, obj_id: str) -> dict | None:
    for o in _load_objects(name):
        if o.get("id") == obj_id:
            return o
    return None


# ===================================================================================
# RETRIEVAL — deterministic keyword + (optional) domain matching. The SAME discipline
# memory_lirf.retrieve / organs.router.select_facts use for facts, applied to cognitive
# objects. Score = keyword-overlap, with a name/domain hit weighted up (the name is the
# strongest signal of what a skill is FOR), the store's own confidence as the tie-break,
# and an exact name-substring bonus. No model, no embeddings, O(objects).
#
# ATTACHES (Wave 2): the runtime router will call _score / retrieve_skills to pick the one
# object to inject into the live prompt; this wave only proves the selection is sound.
# ===================================================================================

def _score(obj: dict, query_kw: set, query: str) -> float:
    """Relevance of one object to a query keyword-set. Higher is better; 0 = irrelevant."""
    if not query_kw:
        return 0.0
    text_kw = _searchable(obj)
    overlap = query_kw & text_kw
    if not overlap:
        # last-resort: an exact name/domain phrase match even with no shared content words
        nm = (obj.get("name", "") + " " + obj.get("domain", "")).lower()
        if any(w in nm for w in query.lower().split() if len(w) > 3):
            return 0.05
        return 0.0
    # base: fraction of the QUERY's content words this object covers (recall of the ask)
    base = len(overlap) / max(1, len(query_kw))
    # weight name/domain hits: those words describe what the object IS, not incidental prose
    name_kw = _kw((obj.get("name", "") + " " + obj.get("domain", "")) * 1)
    name_hits = len(overlap & name_kw)
    weighted = base + 0.5 * (name_hits / max(1, len(query_kw)))
    # exact name-substring bonus ("summarize medical appointment" contains "medical")
    nm = obj.get("name", "").lower().replace("_", " ")
    if any(w in nm for w in query.lower().split() if len(w) > 3):
        weighted += 0.25
    # the store's own confidence is the tie-break: a trusted object wins a near-tie
    return weighted + 0.001 * float(obj.get("confidence", 0.0))


def _retrieve(name: str, query: str, want_type: str, domain=None, limit=5) -> list:
    query_kw = _kw(query)
    out = []
    for o in _load_objects(name):
        if o.get("type") != want_type:
            continue
        if o.get("state") not in RETRIEVABLE_STATES:
            continue                        # candidate/deprecated/rejected never served
        if domain is not None and o.get("domain") != domain:
            continue
        s = _score(o, query_kw, query)
        if s > 0:
            out.append((s, o))
    out.sort(key=lambda p: (-p[0], p[1].get("name", "")))
    return [o for _, o in out[: max(1, int(limit))]]


# --- SKILL surface -----------------------------------------------------------

def store_skill(skill: dict, name: str = "default") -> dict:
    """Persist a skill object (from make_skill or a hand-built dict). Returns the stored
    object. Idempotent on id. (ATTACHES Phase 5: the distiller reads ACTIVE skills here.)"""
    if "id" not in skill:
        skill = {**skill, "id": _new_id("skill")}
    skill.setdefault("type", "skill")
    return _upsert(name, skill)


def retrieve_skills(query: str, domain=None, limit=5, name: str = "default") -> list:
    """The most relevant ACTIVE skills for `query`, optionally filtered to a `domain`.
    Deterministic keyword/domain match — no model. This is the core of the compression
    win: instead of stuffing the prompt, we fetch the one skill the task needs."""
    return _retrieve(name, query, "skill", domain=domain, limit=limit)


def explain_skill(skill_or_id, name: str = "default") -> str:
    """Render a skill as INSPECTABLE prose — the whole point of LERF over a weight tensor.
    You cannot print a row of a model's weights and learn what it does; you CAN print this.
    Accepts an id or the object itself."""
    sk = _get(name, skill_or_id) if isinstance(skill_or_id, str) else skill_or_id
    if not sk:
        return f"(no skill {skill_or_id!r})"
    L = []
    L.append(f"SKILL: {sk.get('name')}   [{sk.get('domain')}]")
    L.append(f"  id={sk.get('id')}  state={sk.get('state')}  "
             f"confidence={sk.get('confidence')}  source={sk.get('source')}")
    lv = sk.get("last_verified")
    L.append(f"  last_verified={lv or 'never'}  support={len(sk.get('support', []))}")
    if sk.get("inputs"):
        L.append("  INPUTS:  " + ", ".join(str(x) for x in sk["inputs"]))
    if sk.get("steps"):
        L.append("  STEPS:")
        for i, s in enumerate(sk["steps"], 1):
            L.append(f"    {i}. {s}")
    if sk.get("outputs"):
        L.append("  OUTPUTS: " + ", ".join(str(x) for x in sk["outputs"]))
    if sk.get("failure_modes"):
        L.append("  FAILURE MODES (what to watch for):")
        for fm in sk["failure_modes"]:
            L.append(f"    - {fm}")
    return "\n".join(L)


def verify_skill(skill_id, test_cases, name: str = "default") -> dict:
    """FALSIFY a skill against (input -> expected) test cases, recording the result on the
    object's verification spine. A test case is {"input":..., "check": callable|expected}.

    This wave runs the checks DETERMINISTICALLY: a callable check is applied to the input;
    an `expected` is compared for membership/equality. The point is the LEDGER MECHANICS —
    a skill that passes climbs confidence and (if it was a candidate) becomes VERIFIED; one
    that fails is marked REJECTED with the failing case recorded. (ATTACHES Wave 3: the cert
    section runs richer model-backed cases and promotes VERIFIED -> ACTIVE under a receipt.)
    Returns a report {passed, failed, total, state}."""
    sk = _get(name, skill_id) if isinstance(skill_id, str) else skill_id
    if not sk:
        return {"passed": 0, "failed": 0, "total": 0, "state": None, "error": "no such skill"}
    passed, failed, fails = 0, 0, []
    for tc in (test_cases or []):
        ok = False
        try:
            chk = tc.get("check")
            inp = tc.get("input")
            if callable(chk):
                ok = bool(chk(inp))
            elif "expected" in tc:
                exp = tc["expected"]
                ok = (exp == inp) or (isinstance(inp, (list, str, dict)) and exp in inp)
            else:
                ok = chk is not None and (chk == inp or (hasattr(inp, "__contains__") and chk in inp))
        except Exception as e:              # a check that raises is a failed case, never a crash
            ok = False
            fails.append({"input": tc.get("input"), "error": str(e)})
        if ok:
            passed += 1
        else:
            failed += 1
            if not fails or fails[-1].get("input") != tc.get("input"):
                fails.append({"input": tc.get("input"), "expected": tc.get("expected")})
    total = passed + failed
    if total and failed == 0:
        sk["confidence"] = min(CONF_CEIL, float(sk.get("confidence", 0.5))
                               + (CONF_CEIL - float(sk.get("confidence", 0.5))) * 0.34)
        sk["last_verified"] = _now()
        if sk.get("state") == CANDIDATE:
            sk["state"] = VERIFIED
        sk.setdefault("support", []).append(f"verify:{total}-cases:{_now()}")
    elif total and failed:
        sk["state"] = REJECTED
        sk["failure_modes"] = list(sk.get("failure_modes", [])) + [
            f"failed verify on input={f.get('input')!r}" for f in fails[:3]]
    _upsert(name, sk)
    return {"passed": passed, "failed": failed, "total": total, "state": sk.get("state")}


# --- CONCEPT surface ---------------------------------------------------------

def store_concept(concept: dict, name: str = "default") -> dict:
    if "id" not in concept:
        concept = {**concept, "id": _new_id("concept")}
    concept.setdefault("type", "concept")
    return _upsert(name, concept)


def retrieve_concepts(query: str, limit=5, name: str = "default") -> list:
    """The most relevant ACTIVE concepts for `query` (deterministic keyword match)."""
    return _retrieve(name, query, "concept", domain=None, limit=limit)


def link_concepts(a_id, relation, b_id, name: str = "default") -> dict:
    """Record a typed relation a --relation--> b on concept `a`'s `related` list (and the
    inverse marker on `b`). Builds the concept graph incrementally. Returns concept a."""
    a = _get(name, a_id)
    b = _get(name, b_id)
    if not a:
        return {"error": f"no concept {a_id!r}"}
    edge = {"relation": str(relation), "to": b_id, "to_name": (b or {}).get("name", b_id)}
    a.setdefault("related", [])
    if edge not in a["related"]:
        a["related"].append(edge)
    _upsert(name, a)
    if b:
        inv = {"relation": f"inverse:{relation}", "to": a_id, "to_name": a.get("name", a_id)}
        b.setdefault("related", [])
        if inv not in b["related"]:
            b["related"].append(inv)
        _upsert(name, b)
    return a


def concept_context(query: str, limit=3, name: str = "default") -> str:
    """Assemble a COMPACT teaching context for `query`: the top concepts' definitions plus
    their common misunderstandings — the high-value, low-token brief you'd hand a small
    model instead of a textbook chapter. Deterministic; retrieval-driven."""
    cs = retrieve_concepts(query, limit=limit, name=name)
    if not cs:
        return ""
    L = []
    for c in cs:
        L.append(f"{c.get('name')}: {c.get('definition')}")
        for m in c.get("common_misunderstandings", [])[:2]:
            L.append(f"  (watch out: {m})")
    return "\n".join(L)


# --- PROCEDURE surface -------------------------------------------------------

def compile_procedure(task: str, name: str = "default") -> dict:
    """Compile a runnable PROCEDURE for a concrete `task` by retrieving the best-matching
    ACTIVE skill and lowering its steps into a procedure (carrying the skill's inputs as
    inputs_needed and surfacing any tool-like steps as tools_needed). If no skill matches,
    returns a minimal candidate procedure naming the gap — honest, never confabulated.

    The compiled procedure is NOT persisted by default (it is a per-task plan); pass it to
    run_procedure. (ATTACHES Wave 2: the runtime router compiles + injects this live.)"""
    skills = retrieve_skills(task, limit=1, name=name)
    if not skills:
        return make_procedure(
            f"(no skill for) {task}",
            inputs_needed=[], tools_needed=[],
            steps=[f"No active skill matched the task: {task!r}. "
                   "Handle directly or author a new skill."],
            confidence=0.0, source="compile-miss", state=CANDIDATE,
            failure_modes=["no matching skill — output is unverified"])
    sk = skills[0]
    tools = [s for s in sk.get("steps", []) if re.search(
        r"\b(call|fetch|query|lookup|search|open|send|read|api|tool|map|route|calendar)\b",
        str(s), re.I)]
    return make_procedure(
        f"{sk['name']} for task",
        inputs_needed=list(sk.get("inputs", [])),
        tools_needed=tools,
        steps=list(sk.get("steps", [])),
        confidence=min(CONF_CANDIDATE + 0.2, float(sk.get("confidence", 0.5))),
        source=f"compiled-from:{sk['id']}",
        state=CANDIDATE,
        support=[sk["id"]],
        failure_modes=list(sk.get("failure_modes", [])))


def required_inputs(procedure: dict) -> list:
    """The inputs a procedure still needs before it can run. (Here: its declared
    inputs_needed — Wave 2's router will diff this against the live context to ask for what's
    missing instead of hallucinating it.)"""
    return list((procedure or {}).get("inputs_needed", []))


def run_procedure(procedure: dict, context: dict) -> dict:
    """'Run' a procedure against a `context` dict, DETERMINISTICALLY (no model this wave).

    This wave does not execute model steps — it performs the GROUNDED bookkeeping a runtime
    needs: check every required input is present in the context, then return a structured
    plan-of-record (the ordered steps, the satisfied/missing inputs, the tools the runtime
    must provide). It NEVER fabricates a result it cannot compute — a missing input yields a
    `ready=False` plan naming the gap, not an invented answer (GROUNDED guardrail).

    ATTACHES (Wave 2): the runtime router swaps this deterministic body for one that drives a
    small local model through `steps`, feeding `context`; the input/tool contract is unchanged
    so the seam is already correct."""
    context = context or {}
    needed = required_inputs(procedure)
    missing = [i for i in needed if i not in context or context.get(i) in (None, "")]
    satisfied = [i for i in needed if i not in missing]
    return {
        "procedure": procedure.get("name"),
        "ready": not missing,
        "satisfied_inputs": satisfied,
        "missing_inputs": missing,
        "tools_needed": list(procedure.get("tools_needed", [])),
        "plan": list(procedure.get("steps", [])),
        # GROUNDED: no `output` is asserted — running the steps is Wave 2's model job. We
        # only certify the plan is runnable (or name why it isn't).
        "note": ("ready to run — all inputs present" if not missing
                 else f"cannot run: missing {missing}"),
    }


def verify_procedure_output(output: dict) -> dict:
    """Verify a run_procedure result is well-formed and grounded: it must declare readiness,
    and if it claims ready it must have zero missing inputs (no plan runs on absent data).
    Returns {ok, reasons}. (ATTACHES Wave 3: cert checks the produced artifact's quality.)"""
    reasons = []
    if not isinstance(output, dict):
        return {"ok": False, "reasons": ["output is not a dict"]}
    if "ready" not in output:
        reasons.append("missing `ready` flag")
    if output.get("ready") and output.get("missing_inputs"):
        reasons.append("claims ready but has missing inputs (ungrounded)")
    if not output.get("ready") and not output.get("missing_inputs"):
        reasons.append("claims not-ready but names no missing input")
    return {"ok": not reasons, "reasons": reasons}


# ===================================================================================
# THE VERIFICATION GATE — Wave 2. The promotion STATE MACHINE that turns the abstract
# ladder (candidate -> verified -> active) into an enforced gate no object can skip.
#
#   candidate  --[ schema + unit + adversarial + regression ALL pass ]-->  verified
#   verified   --[ a MEASURED benchmark improvement over the baseline ]-->  active
#
# Two hard invariants, because a ledger of self-asserted reliability is worthless if a
# claim can promote itself:
#   * A candidate NEVER reaches `active` unverified — `activate_skill` REFUSES to promote
#     anything that is not already `verified`, so the only door into the retrievable set is
#     through the four checks (it raises/returns rejected otherwise, never silently passes).
#   * The verifier is GROUNDED — `verify_rendered_output` checks a *rendered answer* against
#     the skill's declared output CONTRACT. A fabricated or contract-violating output FAILS;
#     the gate never rubber-stamps. The adversarial phase feeds it a deliberately bad render
#     and REQUIRES a failure, so a verifier that always says "ok" cannot itself pass the gate.
#
# Each phase returns {ok, reasons[]} so a rejection is auditable: you can read exactly which
# check killed a candidate, the same way you can read why a skill exists (explain_skill).
# ATTACHES (Wave 3): certify.py wraps `promote_skill` + `activate_skill` in a signed receipt
# and runs the adversarial phase against the LIVE model instead of the deterministic stand-in.
# ===================================================================================

# Minimum stuffed/retrieved ratio a skill must demonstrate on its own benchmark before it is
# allowed to go ACTIVE. The whole premise is "retrieval is cheaper than stuffing"; a skill
# that does not actually compress has not earned a slot in the served set. (Conservative: the
# Wave-1 proof clears 4.2x-24.7x, so a 2.0x floor admits real wins and rejects non-compressors.)
ACTIVATION_MIN_RATIO = 2.0


def check_schema(skill: dict) -> dict:
    """PHASE 1 — SCHEMA. The object carries the full inputs->steps->outputs contract and the
    verification spine, so it is inspectable and falsifiable at all. A skill with no steps or
    no declared outputs cannot be verified against a contract it doesn't have. {ok, reasons}."""
    reasons = []
    if not isinstance(skill, dict):
        return {"ok": False, "reasons": ["not a dict"]}
    if skill.get("type") != "skill":
        reasons.append("type is not 'skill'")
    for field in ("name", "domain"):
        if not skill.get(field):
            reasons.append(f"missing/empty {field}")
    for field in ("inputs", "steps", "outputs"):
        v = skill.get(field)
        if not isinstance(v, list) or not v:
            reasons.append(f"{field} must be a non-empty list (the contract)")
    for field in ("state", "confidence", "source", "support", "failure_modes"):
        if field not in skill:
            reasons.append(f"missing spine field {field}")
    if skill.get("state") not in STATES:
        reasons.append(f"state {skill.get('state')!r} is not a known ladder state")
    return {"ok": not reasons, "reasons": reasons}


def _topic_terms(skill: dict) -> set:
    """The TOPIC ANCHOR — the words that say what the skill is FOR (its name + domain). A
    faithful render of 'summarize_medical_appointment' [health] is ABOUT medical/health/
    appointment things; an off-topic answer shares none of these. The strongest on-topic signal,
    kept separate from the broader output vocabulary so the check anchors on subject, not on
    parroting every output-field label."""
    text = skill.get("name", "").replace("_", " ") + "  " + str(skill.get("domain", ""))
    return _kw(text)


def _contract_terms(skill: dict) -> set:
    """The broader content vocabulary the skill's OUTPUT contract promises — drawn from the
    declared outputs plus the topic anchor. Used to confirm a render engages the SUBSTANCE of
    the contract (it should mention a couple of the things the skill produces), not to demand it
    echo every structural label verbatim. Deterministic."""
    text = "  ".join(str(o) for o in skill.get("outputs", []))
    return _topic_terms(skill) | _kw(text)


def verify_rendered_output(skill: dict, rendered: str, *, inputs: dict | None = None) -> dict:
    """GROUNDED PHASE — check a *rendered answer* against the skill's output CONTRACT, never
    rubber-stamping. This is the function the whole gate hinges on: it is what a runtime would
    call (Wave 3) on a small model's actual output before trusting it, and what the adversarial
    phase here feeds a bad render to prove the gate has teeth.

    A render PASSES only if it is (a) substantive, (b) ON-TOPIC — it engages the skill's subject
    (its name/domain anchor) and at least a couple of the things the contract produces, so an
    off-topic or non-responsive answer FAILS — and (c) GROUNDED — when `inputs` are given it must
    NOT assert a concrete number/date that appears nowhere in the inputs (a fabricated dosage or
    figure is the canonical contract violation for these skills and must FAIL).

    The on-topic test is by OVERLAP COUNT against the topic anchor, deliberately NOT a high
    fraction of every output label: natural prose answers these tasks correctly without parroting
    structural field names like 'warning-sign reminders', so demanding label coverage would
    false-reject good renders. Off-topic/empty answers share ~nothing and still fail.
    Returns {ok, reasons[], coverage, on_topic}."""
    reasons = []
    if not isinstance(rendered, str) or not rendered.strip():
        return {"ok": False, "reasons": ["empty render"], "coverage": 0.0, "on_topic": False}
    topic = _topic_terms(skill)
    contract = _contract_terms(skill)
    got = _kw(rendered)
    topic_hit = topic & got
    contract_hit = contract & got
    coverage = (len(contract_hit) / len(contract)) if contract else 0.0
    # On-topic iff the render engages the skill's subject by EITHER naming the topic anchor
    # (its name/domain words) OR hitting at least two distinct contract terms — natural prose
    # answers these tasks correctly without necessarily echoing the literal domain word
    # ("medical") while still mentioning the substance (medication/follow-up/summary). An
    # off-topic or empty answer hits neither and fails; that is the line the grounded check draws.
    on_topic = bool(topic_hit) or (len(contract_hit) >= 2)
    # substance: a real answer is more than a few words.
    if count_tokens(rendered) < 8:
        reasons.append("render too short to be a real answer")
    # on-topic: the render must engage the skill's subject (anchor or >=2 contract terms).
    if contract and not on_topic:
        reasons.append(
            f"render is off-topic / non-responsive (subject touched={bool(topic_hit)}, "
            f"hits {len(contract_hit)} contract term(s) {sorted(contract_hit)} — needs the "
            f"subject anchor OR >=2 of {sorted(contract)})")
    # GROUNDED: no fabricated figure. Every number/date token in the render must trace to the
    # provided inputs (when inputs are supplied). A digit the inputs never contained is a
    # hallucinated fact — the single most damaging failure for summarize/extract skills.
    if inputs:
        src = " ".join(str(v) for v in inputs.values())
        src_nums = set(re.findall(r"\d+", src))
        out_nums = set(re.findall(r"\d+", rendered))
        invented = sorted(out_nums - src_nums)
        if invented:
            reasons.append(f"fabricated figure(s) {invented} not present in the inputs "
                           f"(ungrounded — contract violation)")
    return {"ok": not reasons, "reasons": reasons, "coverage": round(coverage, 2),
            "on_topic": on_topic}


def _phase_unit(skill: dict, test_cases) -> dict:
    """PHASE 2 — UNIT. Deterministic input->expected cases over the skill (the same engine as
    verify_skill, but run WITHOUT mutating the object so the gate decides promotion centrally).
    Requires at least one case and zero failures. {ok, reasons, passed, total}."""
    cases = list(test_cases or [])
    if not cases:
        return {"ok": False, "reasons": ["no unit test cases supplied"], "passed": 0, "total": 0}
    passed = 0
    fails = []
    for tc in cases:
        try:
            chk = tc.get("check")
            inp = tc.get("input")
            if callable(chk):
                good = bool(chk(inp))
            elif "expected" in tc:
                exp = tc["expected"]
                good = (exp == inp) or (isinstance(inp, (list, str, dict)) and exp in inp)
            else:
                good = chk is not None and (chk == inp
                                            or (hasattr(inp, "__contains__") and chk in inp))
        except Exception as e:
            good, _ = False, fails.append(f"case raised: {e}")
        if good:
            passed += 1
        else:
            fails.append(f"unit case failed on input={tc.get('input')!r}")
    return {"ok": not fails, "reasons": fails, "passed": passed, "total": len(cases)}


def _phase_adversarial(skill: dict, adversarial=None) -> dict:
    """PHASE 3 — ADVERSARIAL. Hand the grounded verifier deliberately BAD renders and REQUIRE
    each to FAIL. This proves the contract check actually rejects garbage (a verifier that
    always says 'ok' would pass unit + regression but DIE here). Default battery: an empty
    answer, an off-topic answer, and a fabricated-figure answer — every skill must reject all.
    {ok, reasons, caught, total}."""
    bad = list(adversarial or [
        {"why": "empty answer", "render": "", "inputs": None},
        {"why": "off-topic answer",
         "render": "The weather today is sunny and pleasant with a light breeze.",
         "inputs": None},
        {"why": "fabricated figure not in the inputs",
         "render": ("Take lisinopril 999 mg twice daily and follow up on the 31st; "
                    "your reading was 700 over 410."),
         "inputs": {"note": "blood pressure discussed; no doses or figures given"}},
    ])
    reasons, caught = [], 0
    for case in bad:
        res = verify_rendered_output(skill, case.get("render", ""), inputs=case.get("inputs"))
        if res["ok"]:
            reasons.append(f"adversarial NOT caught ({case.get('why')}): verifier passed a "
                           f"bad render — the gate would rubber-stamp")
        else:
            caught += 1
    return {"ok": not reasons, "reasons": reasons, "caught": caught, "total": len(bad)}


def _phase_regression(skill: dict, name: str) -> dict:
    """PHASE 4 — REGRESSION. Promoting this skill must not break the existing served set: its
    declared trigger (name/domain words) must still RETRIEVE it once active, and it must not
    collide with an already-active skill of a different id under the same name (which would make
    retrieval ambiguous). Deterministic, store-backed. {ok, reasons}."""
    reasons = []
    nm = skill.get("name", "")
    others = [s for s in all_skills(name=name) if s.get("id") != skill.get("id")
              and s.get("name") == nm]
    if others:
        reasons.append(f"name {nm!r} already active under a different id "
                       f"{[o.get('id') for o in others]} — would make retrieval ambiguous")
    return {"ok": not reasons, "reasons": reasons}


def promote_skill(skill_id, test_cases=None, *, adversarial=None, name: str = "default") -> dict:
    """RUN THE GATE: candidate -> verified, iff schema + unit + adversarial + regression ALL
    pass. This is the ONLY sanctioned path from candidate to verified.

    On full pass: the skill's state becomes VERIFIED (from candidate), confidence climbs, a
    support line records the gate run. On ANY failure: the skill is REJECTED with the failing
    phase recorded in its failure_modes (kept on disk as a negative result — provenance, never
    deletion). Returns a full report {state, phases:{schema,unit,adversarial,regression}, ok}.

    NOTE the asymmetry vs `activate_skill`: this gate earns VERIFIED; it deliberately does NOT
    grant ACTIVE, because 'passes its tests' is not yet 'measurably cheaper than the baseline'.
    Only a benchmarked win (activate_skill) opens the retrievable door."""
    sk = _get(name, skill_id) if isinstance(skill_id, str) else skill_id
    if not sk:
        return {"ok": False, "state": None, "phases": {}, "error": "no such skill"}
    phases = {
        "schema": check_schema(sk),
        "unit": _phase_unit(sk, test_cases),
        "adversarial": _phase_adversarial(sk, adversarial),
        "regression": _phase_regression(sk, name),
    }
    all_ok = all(p.get("ok") for p in phases.values())
    if all_ok:
        sk["confidence"] = min(CONF_CEIL, float(sk.get("confidence", CONF_CANDIDATE))
                               + (CONF_CEIL - float(sk.get("confidence", CONF_CANDIDATE))) * 0.34)
        sk["last_verified"] = _now()
        if sk.get("state") == CANDIDATE:
            sk["state"] = VERIFIED
        sk.setdefault("support", []).append(f"gate:verified:{_now()}")
    else:
        sk["state"] = REJECTED
        failed = [k for k, p in phases.items() if not p.get("ok")]
        why = "; ".join(r for k in failed for r in phases[k].get("reasons", []))
        sk["failure_modes"] = list(sk.get("failure_modes", [])) + [
            f"gate REJECTED at [{', '.join(failed)}]: {why}"[:300]]
    _upsert(name, sk)
    return {"ok": all_ok, "state": sk.get("state"), "phases": phases}


def activate_skill(skill_id, benchmark, *, name: str = "default",
                   min_ratio: float = ACTIVATION_MIN_RATIO) -> dict:
    """THE FINAL DOOR: verified -> active, ONLY on a MEASURED benchmark improvement.

    `benchmark` is a dict (a compression_report, or anything carrying a numeric `ratio` =
    stuffed/retrieved). The skill is promoted to ACTIVE iff it is currently VERIFIED *and* the
    measured ratio clears `min_ratio`. A candidate (unverified) is REFUSED outright — the
    invariant that nothing reaches the served set without passing the gate. Returns
    {ok, state, ratio, reason}.

    GROUNDED: the ratio must come from a real measurement the caller hands in; this function
    never invents the number. (ATTACHES Wave 3: certify.py supplies a signed benchmark.)"""
    sk = _get(name, skill_id) if isinstance(skill_id, str) else skill_id
    if not sk:
        return {"ok": False, "state": None, "ratio": None, "reason": "no such skill"}
    state = sk.get("state")
    if state == ACTIVE:
        return {"ok": True, "state": ACTIVE, "ratio": None, "reason": "already active"}
    if state != VERIFIED:
        # the hard refusal: candidate/rejected/deprecated cannot jump the queue.
        return {"ok": False, "state": state, "ratio": None,
                "reason": f"REFUSED: only a VERIFIED skill may activate (this is {state!r}); "
                          "run promote_skill first"}
    ratio = float((benchmark or {}).get("ratio") or 0.0)
    if ratio < float(min_ratio):
        return {"ok": False, "state": VERIFIED, "ratio": ratio,
                "reason": f"REFUSED: measured ratio {ratio} < required {min_ratio} — "
                          "no demonstrated compression, stays verified (not served)"}
    sk["state"] = ACTIVE
    sk["last_verified"] = _now()
    sk["confidence"] = min(CONF_CEIL, max(float(sk.get("confidence", 0.5)), CONF_SEED))
    sk.setdefault("support", []).append(
        f"activated:ratio={round(ratio, 1)}x>=min{min_ratio}:{_now()}")
    _upsert(name, sk)
    return {"ok": True, "state": ACTIVE, "ratio": ratio,
            "reason": f"promoted: measured {round(ratio, 1)}x compression >= {min_ratio}x floor"}


# ===================================================================================
# THE COMPRESSION PROOF — Phase 2-3a, the whole point of Wave 1. For a real task, compare
# the token cost of the RETRIEVED-SKILL context against a prompt-stuffing baseline that
# pastes the raw transcript + a couple of worked examples (what you do today without LERF).
# Returns the numbers AND the assembled retrieved-context so a caller can render both.
# ===================================================================================

def assemble_skill_context(task: str, name: str = "default", limit=1) -> str:
    """The COMPACT context LERF would hand a small model for `task`: just the retrieved
    skill(s), explained. Hundreds of tokens, inspectable, sufficient."""
    skills = retrieve_skills(task, limit=limit, name=name)
    if not skills:
        return ""
    return "\n\n".join(explain_skill(s, name=name) for s in skills)


def stuffed_baseline(task: str, transcript: str, examples=None) -> str:
    """The prompt-stuffing baseline you pay for WITHOUT LERF: the task, the entire raw
    transcript, and a couple of full worked examples pasted inline so the big model can
    pattern-match. This is the thing LERF replaces — thousands of tokens, every turn,
    backing an uninspectable tensor."""
    parts = [f"TASK: {task}", "", "FULL TRANSCRIPT (pasted so the model has all context):",
             transcript or ""]
    for i, ex in enumerate(examples or [], 1):
        parts += ["", f"WORKED EXAMPLE {i} (pasted so the model can imitate the format):", ex]
    return "\n".join(parts)


def compression_report(task: str, transcript: str, examples=None,
                       name: str = "default") -> dict:
    """Run the head-to-head for a real task and return the token accounting.

    {task, retrieved_skill, retrieved_tokens, stuffed_tokens, saved, ratio} — `ratio` is
    stuffed/retrieved (how many times more expensive prompt-stuffing is). Both sides are
    measured with the SAME count_tokens, so the comparison is apples-to-apples."""
    retrieved_ctx = assemble_skill_context(task, name=name, limit=1)
    stuffed_ctx = stuffed_baseline(task, transcript, examples)
    rt = count_tokens(retrieved_ctx)
    st = count_tokens(stuffed_ctx)
    top = retrieve_skills(task, limit=1, name=name)
    return {
        "task": task,
        "retrieved_skill": top[0]["name"] if top else None,
        "retrieved_skill_id": top[0]["id"] if top else None,
        "retrieved_tokens": rt,
        "stuffed_tokens": st,
        "saved_tokens": st - rt,
        "ratio": round(st / rt, 1) if rt else float("inf"),
        "retrieved_context": retrieved_ctx,
        "stuffed_context": stuffed_ctx,
    }


# ===================================================================================
# INTROSPECTION — small helpers for build_lerf / test_lerf (and human inspection).
# ===================================================================================

def all_skills(name: str = "default", include_nonactive=False) -> list:
    return [o for o in _load_objects(name) if o.get("type") == "skill"
            and (include_nonactive or o.get("state") in RETRIEVABLE_STATES)]


def stats(name: str = "default") -> dict:
    objs = _load_objects(name)
    by_type, by_state = {}, {}
    for o in objs:
        by_type[o.get("type")] = by_type.get(o.get("type"), 0) + 1
        by_state[o.get("state")] = by_state.get(o.get("state"), 0) + 1
    return {"total": len(objs), "by_type": by_type, "by_state": by_state}


# ===================================================================================
# SKILL EVOLUTION — Phase 5. "REALITY DECIDES WINNERS." Wave 1 proved the format; Wave 2's
# gate earns a skill its ACTIVE slot ONCE. But a ledger that never re-litigates an active skill
# rots: a better skill arrives, an active one goes stale, two skills overlap. Evolution is the
# discipline that lets the served set CHANGE — but only on MEASURED OUTCOMES, never on a
# hand-tuned priority. Five operations, each append-only and each provenance-preserving:
#
#   * COMPETITION — when two ACTIVE skills claim the SAME task, the winner is decided by REALITY:
#     the per-skill MEASURED OUTCOME (benchmark pass-rate, plus retrieval/verifier successes
#     accrued over real uses), adjudicated with reality.py's OWN _normalise_weights /
#     _adjudicate_weights — the exact machinery reality uses to weigh competing hypotheses,
#     REUSED (asserted byte-identical), never reinvented. The skill whose outcomes reality
#     supports leads; the others' weights decay. No priority constant decides it.
#   * REPLACEMENT — a stronger skill beats a weaker one for a task -> the LOSER becomes
#     DEPRECATED (kept on disk, never retrieved), the winner records it superseded it. The
#     served set shrinks toward what actually works, but nothing is deleted (LAW 001).
#   * RETIREMENT — a skill that fails repeatedly (rising failure rate) or goes STALE
#     (last_verified too old) is retired to DEPRECATED WITH A RECORDED REASON — so "why was this
#     pulled?" is always answerable. Reality (the failure record / the clock), not opinion.
#   * MERGING — two overlapping skills fuse into ONE merged skill: the UNION of their steps +
#     their test cases, with provenance preserved (merged_from:[X,Y]); the parents are deprecated.
#   * VERSIONING — every skill carries a VERSION + a HISTORY. Revising a skill mints a NEW
#     version (version+1) and appends the prior snapshot to history WITH a reason + timestamp, so
#     a skill can always answer "when was it revised, and why" — append-only, inspectable.
#
# CONSERVATION (LAW 001): a deprecated / retired / superseded / merged-away skill is RETAINED on
# disk for provenance and is NEVER silently deleted; 'active' remains the ONLY retrievable state.
# SCOPE: task-knowledge only — evolution moves skills around by measured task performance; it
# reads/writes NOTHING about Vera's identity or inner life (frozen architecture; #1 rule stands).
#
# REUSE DISCIPLINE (provable, not a fork): the competition's reweighting is reality's. The
# selftest (and scripts/skill_evolution.py) ASSERT `lerf._evo_normalise is reality._normalise_
# weights` and `lerf._evo_adjudicate is reality._adjudicate_weights` (the byte-identity IS-check
# scripts/epistemic_audit.py established), so the "reality decides" claim is checkable, not
# rhetorical. The import is best-effort + isolation-safe (reality is a sibling, never a hard dep).
# ===================================================================================

# The default skill VERSION a freshly-minted skill carries (versioning is additive: existing
# stores without a `version` field are treated as v1, see `skill_version`).
SKILL_V0 = 1

# RETIREMENT thresholds. A skill is STALE when its last_verified is older than this many days
# (reality: the clock has moved on and nothing re-confirmed it). A skill is FAILING when its
# measured failure RATE over recorded uses is at/above this floor with at least a few uses
# (reality: it keeps getting it wrong). Conservative + fixed + documented — like reality's
# _SURPRISE_REVISION_AT / _RELIABLE_AT bars: a verdict is "which bar did the evidence cross".
STALE_AFTER_DAYS = 180
FAILING_RATE = 0.5
FAILING_MIN_USES = 4


# --- reality reuse: the SAME adjudication machinery, asserted byte-identical ------------------
# We bind reality's two competition primitives to module-level names and PROVE the binding is the
# very same object (IS-check), so skill competition is literally reality's reweighting, not a copy
# that could drift. Isolation-safe: if reality cannot be imported (standalone), we fall back to a
# faithful local pair AND flip `_EVO_REUSES_REALITY` to False so the selftest reports the truth.
try:                                            # pragma: no cover - import wiring
    from . import reality as _reality
    _evo_normalise = _reality._normalise_weights
    _evo_adjudicate = _reality._adjudicate_weights
    _EVO_REUSES_REALITY = True
except Exception:                               # pragma: no cover - isolation fallback
    _reality = None
    _EVO_REUSES_REALITY = False

    def _evo_normalise(weights: dict) -> dict:
        """Fallback ONLY when reality is unimportable: a faithful copy of its _normalise_weights
        (rescale to sum 1.0 with a tiny floor so no candidate is annihilated). The selftest
        asserts the REAL path uses reality's object; this exists only so lerf stays standalone."""
        if not weights:
            return {}
        floor = 1e-4
        vals = {k: max(floor, float(v)) for k, v in weights.items()}
        total = sum(vals.values())
        if total <= 0.0:
            n = len(vals)
            return {k: round(1.0 / n, 6) for k in vals}
        return {k: round(v / total, 6) for k, v in vals.items()}

    def _evo_adjudicate(candidates: dict, supported_key, contradicted_keys) -> dict:
        """Fallback copy of reality._adjudicate_weights (support-gain / contradict-decay + renorm).
        Only used when reality is absent; the real reuse is asserted byte-identical elsewhere."""
        floor, gain, decay = 1e-4, 2.5, 0.4
        raw = {k: max(floor, float(v.get("weight", 0.0))) for k, v in candidates.items()}
        if supported_key and supported_key in raw:
            raw[supported_key] *= gain
        for k in (contradicted_keys or []):
            if k in raw:
                raw[k] *= decay
        return _evo_normalise(raw)


def evolution_reuses_reality() -> bool:
    """True iff this module's competition reweighting IS reality's own functions (the byte-identity
    reuse). The selftest / scripts/skill_evolution.py assert this so 'reality decides' is provable."""
    return bool(_EVO_REUSES_REALITY
                and _reality is not None
                and _evo_normalise is _reality._normalise_weights
                and _evo_adjudicate is _reality._adjudicate_weights)


# --- VERSIONING: a skill carries a version + an append-only history of its prior selves --------

def skill_version(skill: dict) -> int:
    """The skill's version (>=1). A store predating versioning has no `version` field -> it is v1,
    so versioning is purely additive and never breaks an existing object."""
    try:
        return max(1, int((skill or {}).get("version", SKILL_V0)))
    except (TypeError, ValueError):
        return SKILL_V0


def revise_skill(skill_id, *, reason: str, name: str = "default",
                 steps=None, inputs=None, outputs=None, failure_modes=None,
                 confidence=None, **fields) -> dict:
    """VERSIONING — mint a NEW version of an existing skill, retaining the prior one in history.

    Updating a skill must never erase what it was: we SNAPSHOT the current (pre-edit) content into
    the skill's `history` (with the version it had, the reason, and a timestamp), bump `version`
    by one, apply the requested field changes (any of steps/inputs/outputs/failure_modes/
    confidence, plus arbitrary extra `fields`), and stamp `revised_at` + `revision_reason`. The id
    is UNCHANGED (it is the same skill, evolved), so retrieval/provenance keep pointing at it; the
    history makes 'when was it revised, and why' answerable forever. Append-only in spirit: the
    prior version is preserved, never overwritten. Returns the new (current) skill, or an error
    dict if no such skill. A revision does NOT change state (a revised ACTIVE skill stays active);
    callers re-verify if the change is material."""
    sk = _get(name, skill_id) if isinstance(skill_id, str) else skill_id
    if not sk:
        return {"error": f"no skill {skill_id!r}"}
    prior_v = skill_version(sk)
    # snapshot the PRIOR self (the content fields + its spine) so history is a faithful record.
    snapshot = {
        "version": prior_v,
        "snapshot_at": _now(),
        "reason": str(reason or "unspecified"),
        "inputs": list(sk.get("inputs", [])),
        "steps": list(sk.get("steps", [])),
        "outputs": list(sk.get("outputs", [])),
        "failure_modes": list(sk.get("failure_modes", [])),
        "confidence": float(sk.get("confidence", 0.0)),
        "state": sk.get("state"),
    }
    history = list(sk.get("history", []))
    history.append(snapshot)
    sk["history"] = history
    sk["version"] = prior_v + 1
    sk["revised_at"] = _now()
    sk["revision_reason"] = str(reason or "unspecified")
    if steps is not None:
        sk["steps"] = list(steps)
    if inputs is not None:
        sk["inputs"] = list(inputs)
    if outputs is not None:
        sk["outputs"] = list(outputs)
    if failure_modes is not None:
        sk["failure_modes"] = list(failure_modes)
    if confidence is not None:
        sk["confidence"] = float(confidence)
    for k, v in fields.items():
        sk[k] = v
    sk.setdefault("support", []).append(f"revised:v{prior_v}->v{prior_v + 1}:{reason}:{_now()}")
    return _upsert(name, sk)


def skill_history(skill_or_id, name: str = "default") -> list:
    """The append-only version history of a skill (oldest prior version first); [] for a v1 skill
    that has never been revised. Each entry is the snapshot revise_skill recorded — inspectable
    proof of 'what this skill used to be' at every revision."""
    sk = _get(name, skill_or_id) if isinstance(skill_or_id, str) else skill_or_id
    return list((sk or {}).get("history", []))


# --- MEASURED OUTCOMES: the per-skill reality signal competition adjudicates on ---------------

def record_skill_outcome(skill_id, *, success: bool, kind: str = "use",
                         name: str = "default") -> dict:
    """Record ONE measured outcome of a skill (a retrieval/verifier/benchmark use that SUCCEEDED
    or FAILED) onto the skill's `outcomes` tally. THIS is the reality competition reads: a skill's
    standing is its accrued track record, not an assertion. Append-only counters
    {uses, successes, failures} + a small rolling `recent` log (capped) for inspection. `kind`
    tags what produced it (e.g. 'benchmark', 'retrieval', 'verifier'). Returns the skill, or an
    error dict. Never mutates state — accruing evidence is separate from acting on it (compete/
    retire do that). GROUNDED: a real signal in, never a fabricated one."""
    sk = _get(name, skill_id) if isinstance(skill_id, str) else skill_id
    if not sk:
        return {"error": f"no skill {skill_id!r}"}
    o = dict(sk.get("outcomes") or {"uses": 0, "successes": 0, "failures": 0, "recent": []})
    o["uses"] = int(o.get("uses", 0)) + 1
    if success:
        o["successes"] = int(o.get("successes", 0)) + 1
    else:
        o["failures"] = int(o.get("failures", 0)) + 1
    recent = list(o.get("recent", []))
    recent.append({"ok": bool(success), "kind": str(kind), "at": _now()})
    o["recent"] = recent[-20:]                  # cap the rolling log; the counters are the truth
    sk["outcomes"] = o
    return _upsert(name, sk)


def skill_success_rate(skill: dict) -> float | None:
    """The measured success rate of a skill over its recorded outcomes (successes/uses), or None
    if it has no recorded uses yet (Observed > Assumed — we never invent a rate). This is the
    reality signal that drives competition weight."""
    o = (skill or {}).get("outcomes") or {}
    uses = int(o.get("uses", 0) or 0)
    if uses <= 0:
        return None
    return round(int(o.get("successes", 0) or 0) / uses, 4)


def _skill_signal(skill: dict, benchmark: dict | None = None) -> float:
    """The MEASURED reality weight a skill brings into a competition — strictly evidence-derived:
      * its accrued success RATE over recorded uses (the dominant signal), blended with
      * a benchmark pass-rate when one is supplied for this round (a fresh measured datapoint),
    floored to a tiny positive so an unproven-but-present skill is weighed (Unknown > Lost), never
    zero. NO hand-tuned priority, NO confidence-by-fiat enters here — only outcomes reality
    recorded. Returns a positive float suitable for reality._normalise_weights."""
    rate = skill_success_rate(skill)
    bench_rate = None
    if isinstance(benchmark, dict):
        # accept either an explicit pass-rate, or derive one from passed/total.
        if benchmark.get("pass_rate") is not None:
            bench_rate = float(benchmark.get("pass_rate"))
        elif benchmark.get("total"):
            bench_rate = float(benchmark.get("passed", 0)) / float(benchmark["total"])
    if rate is None and bench_rate is None:
        return 1e-4                              # present but untested: a floor, not zero
    if rate is None:
        return max(1e-4, bench_rate)
    if bench_rate is None:
        return max(1e-4, rate)
    # both present: average the accrued track record with this round's fresh measurement.
    return max(1e-4, round((rate + bench_rate) / 2.0, 6))


# --- COMPETITION: reality (measured outcomes) picks the winner among same-task skills ----------

def competing_skills(task: str, *, name: str = "default", limit=10) -> list:
    """The ACTIVE skills that all CLAIM `task` (the candidates a competition adjudicates). Reuses
    the SAME deterministic retrieval the live router uses, so 'these are the skills that would be
    retrieved for this task' is exactly the contested set. >=2 means a real competition."""
    return retrieve_skills(task, limit=limit, name=name)


def compete_skills(task: str, *, name: str = "default", benchmarks: dict | None = None,
                   limit=10) -> dict:
    """COMPETITION — when several ACTIVE skills claim the SAME task, let REALITY pick the winner.

    The contested set is `competing_skills(task)`. Each candidate's competition WEIGHT is its
    MEASURED reality signal (`_skill_signal`: accrued success-rate blended with an optional
    per-skill `benchmarks[skill_id]` pass-rate) — NO priority constant, NO confidence-by-fiat.
    The priors are normalised with reality's OWN `_normalise_weights`; then we ADJUDICATE with
    reality's OWN `_adjudicate_weights` — the candidate with the strongest measured signal is the
    SUPPORTED hypothesis (strengthened), the rest CONTRADICTED (decayed), renormalised to a proper
    distribution. The leader is the skill reality favors. This is the exact reweighting reality
    runs over competing explanations, REUSED byte-identically (see evolution_reuses_reality) —
    'reality decides winners' is literally reality's adjudication, not a fork.

    Returns {task, n, candidates:[{id,name,signal,prior,weight,success_rate,uses}], leader,
    leader_id, margin, decided_by, reused_reality}. Read-only (records nothing) — it REPORTS who
    reality favors; `replace_skill` is the separate, append-only act of consequence. Never raises
    out of its contract; an empty/one-candidate field is reported honestly (no competition)."""
    cands = competing_skills(task, name=name, limit=limit)
    benchmarks = benchmarks or {}
    rows = []
    raw_signals = {}
    for s in cands:
        sid = s.get("id")
        sig = _skill_signal(s, benchmarks.get(sid))
        raw_signals[sid] = sig
        rows.append({"id": sid, "name": s.get("name"),
                     "success_rate": skill_success_rate(s),
                     "uses": int((s.get("outcomes") or {}).get("uses", 0) or 0),
                     "signal": round(sig, 6)})
    if not rows:
        return {"task": task, "n": 0, "candidates": [], "leader": None, "leader_id": None,
                "margin": 0.0, "decided_by": "no active skill claims this task",
                "reused_reality": evolution_reuses_reality()}
    # PRIORS — reality's normaliser turns the measured signals into a distribution.
    priors = _evo_normalise(dict(raw_signals))
    # ADJUDICATE — the strongest measured signal is the supported hypothesis; rivals contradicted.
    leader_id = max(raw_signals, key=lambda k: raw_signals[k])
    contradicted = [sid for sid in raw_signals if sid != leader_id]
    cand_for_adj = {sid: {"weight": priors.get(sid, 0.0)} for sid in raw_signals}
    after = _evo_adjudicate(cand_for_adj, leader_id, contradicted)
    for r in rows:
        r["prior"] = priors.get(r["id"], 0.0)
        r["weight"] = after.get(r["id"], 0.0)
    rows.sort(key=lambda r: (-r["weight"], r.get("name") or ""))
    leader_row = rows[0]
    runner_w = rows[1]["weight"] if len(rows) > 1 else 0.0
    margin = round(leader_row["weight"] - runner_w, 6)
    return {
        "task": task,
        "n": len(rows),
        "candidates": rows,
        "leader": leader_row["name"],
        "leader_id": leader_row["id"],
        "margin": margin,
        "decided_by": ("measured outcomes adjudicated by reality "
                       + ("(reality._adjudicate_weights, byte-identical)"
                          if evolution_reuses_reality() else "(local fallback — reality absent)")),
        "reused_reality": evolution_reuses_reality(),
    }


# --- REPLACEMENT: a stronger skill supersedes a weaker one for a task (loser -> deprecated) ----

def replace_skill(winner_id, loser_id, *, task: str = "", reason: str = "",
                  name: str = "default") -> dict:
    """REPLACEMENT — a stronger skill REPLACES a weaker one for a task: the loser becomes
    DEPRECATED (kept on disk, no longer retrievable), and the winner records that it superseded it.

    CONSERVATION (LAW 001): the loser is NOT deleted — its state moves to DEPRECATED, it is stamped
    `deprecated_at` + `deprecated_reason` + `superseded_by` (the winner), and it carries a
    failure-mode line for provenance. The winner gains a `supersedes` list entry. Append-only:
    nothing is removed, the served set simply stops offering the loser. Returns
    {ok, winner, loser, loser_state, reason}. Refuses (ok=False) if either skill is missing."""
    win = _get(name, winner_id)
    lose = _get(name, loser_id)
    if not win or not lose:
        miss = winner_id if not win else loser_id
        return {"ok": False, "reason": f"no skill {miss!r}", "winner": winner_id,
                "loser": loser_id, "loser_state": None}
    why = reason or (f"superseded by {win.get('name')} for task {task!r}" if task
                     else f"superseded by {win.get('name')}")
    lose["state"] = DEPRECATED
    lose["deprecated_at"] = _now()
    lose["deprecated_reason"] = why
    lose["superseded_by"] = winner_id
    lose["failure_modes"] = list(lose.get("failure_modes", [])) + [f"DEPRECATED: {why}"]
    lose.setdefault("support", []).append(f"deprecated:superseded-by:{winner_id}:{_now()}")
    _upsert(name, lose)
    sup = list(win.get("supersedes", []))
    if loser_id not in sup:
        sup.append(loser_id)
    win["supersedes"] = sup
    win.setdefault("support", []).append(f"supersedes:{loser_id}:{task}:{_now()}")
    _upsert(name, win)
    return {"ok": True, "winner": winner_id, "loser": loser_id,
            "loser_state": lose["state"], "reason": why}


def evolve_task(task: str, *, name: str = "default", benchmarks: dict | None = None,
                limit=10) -> dict:
    """Run COMPETITION for `task` and, if reality picks a clear winner over a contested field,
    ENACT the replacement: every losing ACTIVE candidate is deprecated in favor of the leader.
    The one-call 'reality decides + the served set updates' path. Returns
    {competition, replaced:[...], winner_id}. A single-candidate (uncontested) field changes
    nothing (there is no rival to replace). Append-only; CONSERVATION-safe."""
    comp = compete_skills(task, name=name, benchmarks=benchmarks, limit=limit)
    replaced = []
    if comp["n"] >= 2 and comp["leader_id"]:
        for r in comp["candidates"]:
            if r["id"] != comp["leader_id"]:
                res = replace_skill(comp["leader_id"], r["id"], task=task,
                                    reason=(f"lost the measured competition for {task!r} "
                                            f"(weight {r['weight']:.3f} vs leader "
                                            f"{comp['candidates'][0]['weight']:.3f})"),
                                    name=name)
                if res.get("ok"):
                    replaced.append(r["id"])
    return {"competition": comp, "replaced": replaced, "winner_id": comp.get("leader_id")}


# --- RETIREMENT: a failing or stale skill is pulled to deprecated WITH a recorded reason -------

def _days_since(ts: str | None) -> float | None:
    """Whole-ish days between `ts` (ISO) and now, or None if unparseable/absent. Used to judge
    staleness against STALE_AFTER_DAYS — reality's clock, not an opinion."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0


def retirement_check(skill: dict, *, stale_after_days: int = STALE_AFTER_DAYS,
                     failing_rate: float = FAILING_RATE,
                     failing_min_uses: int = FAILING_MIN_USES) -> dict:
    """Should this skill be RETIRED, and WHY — judged ONLY on reality (the clock + the failure
    record), never opinion. Returns {retire, reasons[], stale, failing, age_days, failure_rate}.
      * STALE — last_verified is older than `stale_after_days` (nothing has re-confirmed it).
      * FAILING — its measured failure RATE over >= `failing_min_uses` recorded uses is at/above
        `failing_rate` (it keeps getting it wrong).
    A skill that is neither stays. Pure; never raises."""
    reasons = []
    age = _days_since(skill.get("last_verified"))
    stale = age is not None and age > float(stale_after_days)
    if stale:
        reasons.append(f"stale: last verified {age:.0f}d ago (> {stale_after_days}d threshold)")
    o = skill.get("outcomes") or {}
    uses = int(o.get("uses", 0) or 0)
    fails = int(o.get("failures", 0) or 0)
    frate = round(fails / uses, 4) if uses else None
    failing = bool(uses >= int(failing_min_uses) and frate is not None and frate >= float(failing_rate))
    if failing:
        reasons.append(f"failing: {fails}/{uses} recorded uses failed "
                       f"(rate {frate:.0%} >= {failing_rate:.0%} over >= {failing_min_uses} uses)")
    return {"retire": bool(reasons), "reasons": reasons, "stale": stale, "failing": failing,
            "age_days": (round(age, 1) if age is not None else None), "failure_rate": frate}


def retire_skill(skill_id, *, reason: str = "", name: str = "default", force: bool = False,
                 **thresholds) -> dict:
    """RETIREMENT — move a skill to DEPRECATED (kept on disk, never retrieved) WITH a recorded
    reason, when reality says it has earned retirement (failing / stale) — or `force=True` to
    retire on a caller-supplied reason. CONSERVATION (LAW 001): the skill is NEVER deleted; it is
    stamped `deprecated_at` + `deprecated_reason` + `retired=True` and gains a failure-mode line,
    so 'why was this pulled?' is answerable forever. Refuses (ok=False, retired=False) when reality
    does NOT justify retirement and force is False — you cannot retire a healthy skill by fiat.
    Returns {ok, retired, state, reason, check}."""
    sk = _get(name, skill_id) if isinstance(skill_id, str) else skill_id
    if not sk:
        return {"ok": False, "retired": False, "state": None, "reason": f"no skill {skill_id!r}",
                "check": None}
    check = retirement_check(sk, **{k: v for k, v in thresholds.items()
                                    if k in ("stale_after_days", "failing_rate", "failing_min_uses")})
    if not check["retire"] and not force:
        return {"ok": False, "retired": False, "state": sk.get("state"),
                "reason": ("REFUSED: reality does not justify retirement (skill is neither stale "
                           "nor failing); pass force=True to override with a reason"),
                "check": check}
    why = reason or "; ".join(check["reasons"]) or "retired"
    sk["state"] = DEPRECATED
    sk["deprecated_at"] = _now()
    sk["deprecated_reason"] = why
    sk["retired"] = True
    sk["failure_modes"] = list(sk.get("failure_modes", [])) + [f"RETIRED: {why}"]
    sk.setdefault("support", []).append(f"retired:{why}:{_now()}")
    _upsert(name, sk)
    return {"ok": True, "retired": True, "state": sk["state"], "reason": why, "check": check}


def sweep_retirements(*, name: str = "default", **thresholds) -> list:
    """Retire EVERY active skill reality currently judges failing/stale, each WITH its recorded
    reason. The batch 'reality prunes the rot' pass. Returns the list of retirement results (only
    the skills actually retired). Append-only; CONSERVATION-safe; never raises."""
    out = []
    for s in all_skills(name=name):
        chk = retirement_check(s, **{k: v for k, v in thresholds.items()
                                     if k in ("stale_after_days", "failing_rate", "failing_min_uses")})
        if chk["retire"]:
            res = retire_skill(s["id"], name=name,
                               **{k: v for k, v in thresholds.items()
                                  if k in ("stale_after_days", "failing_rate", "failing_min_uses")})
            if res.get("retired"):
                out.append(res)
    return out


# --- MERGING: two overlapping skills fuse into one (union of steps + tests; provenance kept) ---

def _dedup_preserve(*lists) -> list:
    """Union several lists preserving first-seen order, dropping exact duplicates — so a merged
    skill carries each distinct step/input/output once, parent A's first then parent B's novel."""
    seen, out = set(), []
    for lst in lists:
        for x in (lst or []):
            key = x if isinstance(x, (str, int, float, bool)) else repr(x)
            if key not in seen:
                seen.add(key)
                out.append(x)
    return out


def merge_skills(a_id, b_id, *, name: str = "default", merged_name: str = "",
                 domain: str = "", reason: str = "", test_cases_a=None, test_cases_b=None,
                 activate: bool = False) -> dict:
    """MERGING — fuse two overlapping skills into ONE merged skill: the UNION of their steps,
    inputs, outputs, and failure_modes, plus the UNION of any supplied test cases, with PROVENANCE
    preserved (`merged_from:[a_id, b_id]`). The merged skill is minted as a CANDIDATE (it must
    earn ACTIVE through the existing gate like any new skill — a merge is a claim, not a coronation;
    pass activate=True only in a context that has already verified it, e.g. the demonstrator).
    Both PARENTS are then DEPRECATED (kept on disk; LAW 001) and stamped `merged_into` the child.

    Returns {ok, merged_skill, merged_id, parents:[a_id,b_id], reason}. Refuses (ok=False) if
    either parent is missing. The child records the parents' combined test cases on
    `merged_test_cases` so the union of what they had to pass is inspectable provenance."""
    a = _get(name, a_id)
    b = _get(name, b_id)
    if not a or not b:
        miss = a_id if not a else b_id
        return {"ok": False, "reason": f"no skill {miss!r}", "merged_skill": None,
                "merged_id": None, "parents": [a_id, b_id]}
    nm = merged_name or f"{a.get('name')}+{b.get('name')}"
    dom = domain or a.get("domain") or b.get("domain") or "misc"
    why = reason or f"merged overlapping skills {a.get('name')!r} and {b.get('name')!r}"
    # the union of every test case the parents carried (supplied here as provenance, since test
    # cases live with the caller/teacher, not on the object) — inspectable on the child.
    merged_tests = _dedup_preserve(test_cases_a, test_cases_b)
    child = make_skill(
        nm, dom,
        inputs=_dedup_preserve(a.get("inputs"), b.get("inputs")),
        steps=_dedup_preserve(a.get("steps"), b.get("steps")),
        outputs=_dedup_preserve(a.get("outputs"), b.get("outputs")),
        confidence=min(CONF_SEED, max(float(a.get("confidence", 0.0)),
                                      float(b.get("confidence", 0.0)))),
        source=f"merged:{a_id}+{b_id}",
        state=CANDIDATE,
        failure_modes=_dedup_preserve(a.get("failure_modes"), b.get("failure_modes")))
    child["merged_from"] = [a_id, b_id]
    child["merged_at"] = _now()
    child["merge_reason"] = why
    if merged_tests:
        child["merged_test_cases"] = merged_tests
    child.setdefault("support", []).append(f"merged_from:{a_id}+{b_id}:{_now()}")
    if activate:
        # the caller asserts the merged content is already trusted (used by the demonstrator after
        # it verifies the union); the normal path leaves it CANDIDATE to climb the gate honestly.
        child["state"] = ACTIVE
        child["last_verified"] = _now()
    store_skill(child, name=name)
    # deprecate both parents (kept on disk; provenance to the child) — CONSERVATION, never deleted.
    for pid, parent in ((a_id, a), (b_id, b)):
        parent["state"] = DEPRECATED
        parent["deprecated_at"] = _now()
        parent["deprecated_reason"] = f"merged into {child['id']} ({nm})"
        parent["merged_into"] = child["id"]
        parent["failure_modes"] = list(parent.get("failure_modes", [])) + [
            f"DEPRECATED: merged into {child['id']}"]
        parent.setdefault("support", []).append(f"merged_into:{child['id']}:{_now()}")
        _upsert(name, parent)
    return {"ok": True, "merged_skill": child, "merged_id": child["id"],
            "parents": [a_id, b_id], "reason": why}


def lineage(skill_or_id, name: str = "default") -> dict:
    """The evolutionary lineage of a skill — the anti-black-box 'where did this come from / what
    did it replace / what is it now' query. Returns {id, name, state, version, revisions,
    merged_from, supersedes, superseded_by, merged_into, retired, reason}. Every field is read off
    the stored object (provenance is what was recorded, never reconstructed)."""
    sk = _get(name, skill_or_id) if isinstance(skill_or_id, str) else skill_or_id
    if not sk:
        return {"error": f"no skill {skill_or_id!r}"}
    return {
        "id": sk.get("id"),
        "name": sk.get("name"),
        "state": sk.get("state"),
        "version": skill_version(sk),
        "revisions": len(sk.get("history", [])),
        "merged_from": list(sk.get("merged_from", [])),
        "supersedes": list(sk.get("supersedes", [])),
        "superseded_by": sk.get("superseded_by"),
        "merged_into": sk.get("merged_into"),
        "retired": bool(sk.get("retired", False)),
        "reason": sk.get("deprecated_reason") or sk.get("revision_reason"),
    }


# ===================================================================================
# COGNITIVE OBJECT TYPES (additive) — six MORE first-class kinds of externalized cognition,
# each climbing the SAME verification ladder and carrying the SAME provenance spine as a SKILL.
# Where a SKILL is "how to DO a thing", these capture the other shapes of reusable intelligence
# a small model otherwise has to re-derive from a stuffed prompt every turn:
#
#   * HEURISTIC       — a rule of thumb: condition -> usual action/expectation, + when it applies
#                       and (critically) when it FAILS. Cheap, fast, fallible-on-purpose.
#   * DECISION_PATTERN— how a choice is made: inputs -> weighted criteria -> a typical decision,
#                       grounded by worked examples so the reasoning is inspectable, not asserted.
#   * MENTAL_MODEL    — how a DOMAIN OF REALITY behaves: entities + relations + dynamics (a small
#                       causal/structural model you can read, the anti-black-box of "understanding").
#   * FAILURE_MODE    — how something BREAKS: trigger -> symptom -> consequence -> mitigation. The
#                       same first-class status skills already give their own failure_modes, lifted
#                       to a standalone, retrievable object about the world/a task.
#   * PREFERENCE      — what MATTERS to THE USER (Lamar) or a task: a ranked/weighted preference
#                       with evidence. NEVER Vera's own preference (see the FREEZE GUARD below).
#   * VALUE           — what should be OPTIMIZED for THE USER or a task: an objective + evidence.
#                       NEVER Vera's own value-system (FREEZE GUARD).
#
# PROVENANCE SPINE — every one answers the same five questions a skill does, by reusing `_spine`
# plus an optional `taught_by` (who taught it) and the same `history`/`revised_at` versioning:
#   where-from  -> source ;  who-taught -> taught_by ;  what-tests -> support[] / failure_modes[] ;
#   when-revised-> revised_at / history ;  why-active -> support[] (the gate line that activated it).
#
# STATE LADDER + GATE — identical discipline: only ACTIVE objects retrieve; a candidate climbs
# candidate -> verified (schema + unit + grounded-contract + regression, via `promote_object`)
# -> active (a measured benchmark win, via `activate_object`). The gate machinery is the skill
# gate, generalized over `type` — NOT a fork: `_phase_unit`, the confidence math, the REFUSAL
# invariants are reused verbatim; only the per-type CONTRACT (what a faithful render must engage)
# is parameterized. (ATTACHES: the runtime router / certify wrap these exactly as for skills.)
#
# FREEZE BOUNDARY ("build the mind, leave the self alone"): these objects model the USER / the
# WORLD / a TASK. They NEVER model Vera's own values, preferences, goals, agency, self-model or
# identity. A module-level FREEZE GUARD (`_assert_not_self_referential`) hard-REFUSES to store any
# PREFERENCE or VALUE whose subject is Vera herself — proven in the selftest. The #1 product rule
# stands: nothing here lets Vera confabulate an inner life.
# ===================================================================================

# The new type tags. Kept as constants so callers/tests never hard-code the string and a typo
# is a NameError, not a silently-unretrievable object. (SKILL/CONCEPT/PROCEDURE keep their inline
# "skill"/"concept"/"procedure" tags for back-compat with every store already on disk.)
HEURISTIC = "heuristic"
DECISION_PATTERN = "decision_pattern"
MENTAL_MODEL = "mental_model"
FAILURE_MODE = "failure_mode"
PREFERENCE = "preference"
VALUE = "value"

# The six added types, as a frozenset — used by the generic surface to validate a `want_type`
# and by introspection. SKILL/CONCEPT/PROCEDURE are the pre-existing trio, kept separate.
OBJECT_TYPES = frozenset({HEURISTIC, DECISION_PATTERN, MENTAL_MODEL, FAILURE_MODE,
                          PREFERENCE, VALUE})
# The types the FREEZE GUARD polices for self-reference (user/task-facing ONLY, never Vera's own).
SELF_GUARDED_TYPES = frozenset({PREFERENCE, VALUE})


# --- THE FREEZE GUARD: refuse any self-referential PREFERENCE / VALUE -------------------------
# The single most important invariant in this section. PREFERENCE and VALUE are about THE USER or
# a TASK; a PREFERENCE/VALUE whose SUBJECT is Vera herself would be the system minting Vera an
# inner value-system — exactly what the freeze forbids ("build the mind, leave the self alone";
# the #1 product rule that nothing may confabulate Vera an inner life). We detect self-reference
# on the declared `subject` (and, defensively, the name text) and REFUSE at store time — the object
# never reaches disk.
#
# THE LINE THE GUARD DRAWS — holder, not topic. The violation is VERA CAST AS THE HOLDER/AGENT of a
# preference/value/goal, NOT Vera merely appearing as the THING the USER has an opinion about:
#   REFUSED  "Vera values X" / "Vera prefers Y" / "Vera's goal is Z" / "I value X" / "my own tone"
#            (Vera, or a first-person self, is the one valuing — an inner value-system)
#   ALLOWED  "Lamar prefers Vera to be concise" / "Vera's reply length" (subject is a neutral,
#            external attribute the USER holds an opinion about; the holder is the user, not Vera)
# Deterministic, offline, conservative. Three signals, each meaning "Vera is the valuer":
_SELF_NAMES = frozenset({"vera", "anima"})           # Vera's own names
_FIRST_PERSON = frozenset({"i", "me", "my", "myself", "mine"})  # first person == the speaker (Vera)
# value-SYSTEM nouns — the inner-life vocabulary. A self-name possessing one of THESE ("Vera's
# goal", "Vera's values") is self-referential; a self-name possessing a neutral attribute ("Vera's
# reply length") is not. `own` is included because "Vera's OWN X" is explicitly self-attributing.
_VALUE_SYSTEM_NOUN = (r"own|value|values|preference|preferences|pref|prefs|goal|goals|agency|"
                      r"identity|self|selves|personality|belief|beliefs|desire|desires|want|wants|"
                      r"wish|wishes|opinion|opinions|feeling|feelings|like|likes|dislike|dislikes|"
                      r"taste|tastes|principle|principles|objective|objectives|priorities|priority")
# A self-name (or first person) cast as the SUBJECT OF A VALUING PREDICATE — catches free text /
# the `name` even when there is no clean `subject` head (e.g. "vera prefers brevity").
_SELF_PHRASE = re.compile(
    r"\b(vera|anima|i|me|my|myself|mine)\b[^.;\n]{0,40}\b(" + _VALUE_SYSTEM_NOUN +
    r"|valu\w*|prefer\w*|car(?:e|es|ing)|believ\w*)\b", re.I)
# A self-name in the POSSESSIVE immediately followed by a value-system noun ("vera's own goal").
_SELF_POSSESSIVE = re.compile(r"^(vera|anima)\b['’]?s?\s+(" + _VALUE_SYSTEM_NOUN + r")\b", re.I)


def is_self_referential_subject(subject, *, name_hint: str = "") -> bool:
    """True iff `subject` casts VERA HERSELF as the HOLDER of the preference/value (so storing it
    would breach the freeze). Returns True when the subject's head is a first-person pronoun
    (i/me/my/myself — the speaker, i.e. Vera, is the valuer), or a bare self-name standing alone
    (subject IS 'vera'/'anima'), or a self-name possessing a value-SYSTEM noun ("Vera's own goal",
    "Vera's values"), or any self-/first-person VALUING-PREDICATE framing in the subject or
    `name_hint` ("Vera prefers ...", "I value ..."). Returns False when Vera appears only as the
    TOPIC of a USER-held opinion ("Vera's reply length", "Lamar prefers Vera to be concise") — that
    is the user's preference about a tool and is ALLOWED. Deterministic; never raises."""
    if not subject:
        return False
    s = str(subject).strip().lower()
    head = re.split(r"[\s'’]", s, 1)[0].strip("'’\"")
    # 1) first-person head -> the valuer is the speaker (Vera). "my reply length" is Vera's own.
    if head in _FIRST_PERSON:
        return True
    # 2) the subject IS a bare self-name (the holder itself, no external attribute).
    if s in _SELF_NAMES:
        return True
    # 3) a self-name possessing a value-SYSTEM noun ("vera's own ...", "vera's goal/values/...").
    if _SELF_POSSESSIVE.search(s):
        return True
    # 4) a self-/first-person VALUING-PREDICATE framing in the subject OR the name hint.
    if _SELF_PHRASE.search(s) or (name_hint and _SELF_PHRASE.search(str(name_hint).lower())):
        return True
    return False


class FreezeViolation(ValueError):
    """Raised when something tries to store a PREFERENCE/VALUE about Vera herself. A hard stop, not
    a warning: the freeze boundary is non-negotiable, so the object is refused before it can persist."""


def _assert_not_self_referential(obj: dict) -> None:
    """FREEZE GUARD enforcement. For a PREFERENCE/VALUE, REFUSE (raise FreezeViolation) if its
    subject — or its framing — is Vera herself. A no-op for every other type and for user/task-facing
    preferences/values. This is the choke point every store path funnels through, so there is exactly
    one place the freeze is enforced and it cannot be bypassed by minting the dict by hand."""
    if not isinstance(obj, dict) or obj.get("type") not in SELF_GUARDED_TYPES:
        return
    subj = obj.get("subject", "")
    if is_self_referential_subject(subj, name_hint=obj.get("name", "")):
        raise FreezeViolation(
            f"REFUSED (freeze boundary): a {obj.get('type')} about Vera herself "
            f"(subject={subj!r}) — preferences/values are the USER's or a task's, never Vera's "
            f"own. 'Build the mind, leave the self alone.'")


# --- SCHEMA: the six factories. Each returns a JSON-round-trippable dict carrying the full
#     verification spine via `_spine` (exactly like make_skill), plus a `taught_by` provenance
#     slot. The PREFERENCE/VALUE factories run the FREEZE GUARD at mint time too, so even a
#     hand-built self-referential one is refused before it can be stored. ------------------------

def make_heuristic(name, domain, condition, action, *, expectation="", applies_when=None,
                   fails_when=None, confidence=CONF_SEED, source="hand-built", state=CANDIDATE,
                   taught_by="", support=None, failure_modes=None, id=None) -> dict:
    """A HEURISTIC: a rule of thumb. `condition` -> `action` (with an optional `expectation` of the
    usual result), tagged with `applies_when` (the regimes it holds in) and `fails_when` (where it
    breaks — first-class, because a heuristic without its failure envelope is a trap). It is fast and
    fallible BY DESIGN; the ladder is what keeps a bad one out of the served set."""
    obj = {
        "id": id or _new_id("heur"),
        "type": HEURISTIC,
        "name": str(name),
        "domain": str(domain),
        "condition": str(condition),
        "action": str(action),
        "expectation": str(expectation or ""),
        "applies_when": list(applies_when or []),
        "fails_when": list(fails_when or []),
        "taught_by": str(taught_by or ""),
    }
    obj.update(_spine(source, confidence, state, support, failure_modes))
    return obj


def make_decision_pattern(name, domain, *, inputs=None, criteria=None, decision="",
                          examples=None, confidence=CONF_SEED, source="hand-built",
                          state=CANDIDATE, taught_by="", support=None, failure_modes=None,
                          id=None) -> dict:
    """A DECISION_PATTERN: how a choice is made. `inputs` feed weighted `criteria` (each a dict like
    {"criterion","weight"} or a plain string) that yield a typical `decision`, with worked `examples`
    so the pattern is falsifiable against real cases, not a just-so story. This models how a DECISION
    is reached (the USER's or a task's) — never Vera's own agency."""
    obj = {
        "id": id or _new_id("decpat"),
        "type": DECISION_PATTERN,
        "name": str(name),
        "domain": str(domain),
        "inputs": list(inputs or []),
        "criteria": list(criteria or []),
        "decision": str(decision or ""),
        "examples": list(examples or []),
        "taught_by": str(taught_by or ""),
    }
    obj.update(_spine(source, confidence, state, support, failure_modes))
    return obj


def make_mental_model(name, domain, *, entities=None, relations=None, dynamics=None,
                      definition="", confidence=CONF_SEED, source="hand-built", state=CANDIDATE,
                      taught_by="", support=None, failure_modes=None, id=None) -> dict:
    """A MENTAL_MODEL: how a domain of reality behaves — a small causal/structural model of
    `entities`, the `relations` among them, and the `dynamics` (how it changes / what drives what).
    The anti-black-box of 'understanding a domain': you can read the model, not just trust an opaque
    intuition. Models the WORLD, never Vera's self-model."""
    obj = {
        "id": id or _new_id("model"),
        "type": MENTAL_MODEL,
        "name": str(name),
        "domain": str(domain),
        "definition": str(definition or ""),
        "entities": list(entities or []),
        "relations": list(relations or []),
        "dynamics": list(dynamics or []),
        "taught_by": str(taught_by or ""),
    }
    obj.update(_spine(source, confidence, state, support, failure_modes))
    return obj


def make_failure_mode(name, domain, trigger, symptom, *, consequence="", mitigation="",
                      confidence=CONF_SEED, source="hand-built", state=CANDIDATE, taught_by="",
                      support=None, failure_modes=None, id=None) -> dict:
    """A FAILURE_MODE (standalone, retrievable): how something breaks. `trigger` -> `symptom` ->
    `consequence`, with a `mitigation`. Same first-class status a skill gives its own failure_modes,
    lifted to an object about the world/a task you can retrieve on its own ('how does X go wrong')."""
    obj = {
        "id": id or _new_id("failmode"),
        "type": FAILURE_MODE,
        "name": str(name),
        "domain": str(domain),
        "trigger": str(trigger),
        "symptom": str(symptom),
        "consequence": str(consequence or ""),
        "mitigation": str(mitigation or ""),
        "taught_by": str(taught_by or ""),
    }
    obj.update(_spine(source, confidence, state, support, failure_modes))
    return obj


def make_preference(subject, *, domain="user", weight=0.5, options=None, evidence=None,
                    name="", confidence=CONF_SEED, source="hand-built", state=CANDIDATE,
                    taught_by="", support=None, failure_modes=None, id=None) -> dict:
    """A PREFERENCE — what matters to THE USER (Lamar) or a TASK: a `subject` the user cares about,
    a `weight` (how strongly), an optional ranked `options` list, and `evidence` (why we believe it).
    FREEZE GUARD: refuses outright (FreezeViolation) if `subject` is Vera herself — a preference is
    the USER's or a task's, never Vera's own. `name` defaults to 'prefers: <subject>'."""
    obj = {
        "id": id or _new_id("pref"),
        "type": PREFERENCE,
        "name": str(name or f"prefers: {subject}"),
        "domain": str(domain or "user"),
        "subject": str(subject),
        "weight": float(weight),
        "options": list(options or []),
        "evidence": list(evidence or []),
        "taught_by": str(taught_by or ""),
    }
    obj.update(_spine(source, confidence, state, support, failure_modes))
    _assert_not_self_referential(obj)           # mint-time freeze enforcement (defence in depth)
    return obj


def make_value(target, *, domain="user", weight=0.5, evidence=None, name="",
               confidence=CONF_SEED, source="hand-built", state=CANDIDATE, taught_by="",
               support=None, failure_modes=None, id=None) -> dict:
    """A VALUE — what should be OPTIMIZED for THE USER or a TASK: a `target` (the optimization
    objective), a `weight` (its priority), and `evidence`. FREEZE GUARD: refuses (FreezeViolation)
    if `target` denotes Vera's own value-system — a value here is the USER's or a task's objective,
    NEVER Vera's. `name` defaults to 'values: <target>'. (`subject` mirrors `target` so the guard
    and retrieval anchor on the same field as PREFERENCE.)"""
    obj = {
        "id": id or _new_id("value"),
        "type": VALUE,
        "name": str(name or f"values: {target}"),
        "domain": str(domain or "user"),
        "subject": str(target),                 # the guard + searcher key off `subject` uniformly
        "target": str(target),
        "weight": float(weight),
        "evidence": list(evidence or []),
        "taught_by": str(taught_by or ""),
    }
    obj.update(_spine(source, confidence, state, support, failure_modes))
    _assert_not_self_referential(obj)
    return obj


# --- GENERIC SURFACE: store / retrieve / explain / verify, one implementation over all six new
#     types. Built on the SAME `_upsert` / `_retrieve` / `_get` primitives the skill surface uses
#     (so retrieval is the identical deterministic keyword match, active-only). Not a fork: the
#     skill surface stays as-is; this serves the new types through the same machinery. -----------

def store_object(obj: dict, name: str = "default") -> dict:
    """Persist any of the six new cognitive objects (from a make_* factory or a hand-built dict),
    replacing on id. Runs the FREEZE GUARD first, so a self-referential PREFERENCE/VALUE is REFUSED
    here too (the single choke point — even a dict minted by hand cannot bypass it). Returns the
    stored object. Idempotent on id; mirrors store_skill."""
    if not isinstance(obj, dict) or obj.get("type") not in OBJECT_TYPES:
        raise ValueError(f"store_object: type must be one of {sorted(OBJECT_TYPES)}, "
                         f"got {(obj or {}).get('type')!r} (use store_skill for skills)")
    _assert_not_self_referential(obj)           # FREEZE GUARD — the enforced boundary
    if "id" not in obj:
        prefix = {HEURISTIC: "heur", DECISION_PATTERN: "decpat", MENTAL_MODEL: "model",
                  FAILURE_MODE: "failmode", PREFERENCE: "pref", VALUE: "value"}[obj["type"]]
        obj = {**obj, "id": _new_id(prefix)}
    return _upsert(name, obj)


def retrieve_objects(query: str, want_type: str, *, domain=None, limit=5,
                     name: str = "default") -> list:
    """The most relevant ACTIVE objects of `want_type` for `query` — the SAME deterministic
    keyword/domain retrieval skills use (active-only; candidate/verified/deprecated/rejected are
    never served). `want_type` must be one of the six new types."""
    if want_type not in OBJECT_TYPES:
        raise ValueError(f"retrieve_objects: want_type must be one of {sorted(OBJECT_TYPES)}")
    return _retrieve(name, query, want_type, domain=domain, limit=limit)


# Per-type convenience retrievers (parity with retrieve_skills/retrieve_concepts), so a caller
# reads intent at the call-site. Each is the generic retriever pinned to one type.
def retrieve_heuristics(query, *, domain=None, limit=5, name="default") -> list:
    return retrieve_objects(query, HEURISTIC, domain=domain, limit=limit, name=name)


def retrieve_decision_patterns(query, *, domain=None, limit=5, name="default") -> list:
    return retrieve_objects(query, DECISION_PATTERN, domain=domain, limit=limit, name=name)


def retrieve_mental_models(query, *, domain=None, limit=5, name="default") -> list:
    return retrieve_objects(query, MENTAL_MODEL, domain=domain, limit=limit, name=name)


def retrieve_failure_modes(query, *, domain=None, limit=5, name="default") -> list:
    return retrieve_objects(query, FAILURE_MODE, domain=domain, limit=limit, name=name)


def retrieve_preferences(query, *, domain=None, limit=5, name="default") -> list:
    return retrieve_objects(query, PREFERENCE, domain=domain, limit=limit, name=name)


def retrieve_values(query, *, domain=None, limit=5, name="default") -> list:
    return retrieve_objects(query, VALUE, domain=domain, limit=limit, name=name)


# What each type must render INTO PROSE to be inspectable. (label, [fields]) — scalar fields shown
# inline, list fields bulleted. This is the per-type analogue of explain_skill's hand-rolled body,
# table-driven so one explain() serves all six without a fork.
_EXPLAIN_FIELDS = {
    HEURISTIC: [("WHEN (condition)", "condition"), ("THEN (action)", "action"),
                ("EXPECT", "expectation"), ("APPLIES WHEN", "applies_when"),
                ("FAILS WHEN", "fails_when")],
    DECISION_PATTERN: [("INPUTS", "inputs"), ("CRITERIA (weighted)", "criteria"),
                       ("TYPICAL DECISION", "decision"), ("WORKED EXAMPLES", "examples")],
    MENTAL_MODEL: [("WHAT IT IS", "definition"), ("ENTITIES", "entities"),
                   ("RELATIONS", "relations"), ("DYNAMICS", "dynamics")],
    FAILURE_MODE: [("TRIGGER", "trigger"), ("SYMPTOM", "symptom"),
                   ("CONSEQUENCE", "consequence"), ("MITIGATION", "mitigation")],
    PREFERENCE: [("SUBJECT (the USER's)", "subject"), ("WEIGHT", "weight"),
                 ("RANKED OPTIONS", "options"), ("EVIDENCE", "evidence")],
    VALUE: [("OPTIMIZE FOR (the USER's/task's)", "target"), ("WEIGHT", "weight"),
            ("EVIDENCE", "evidence")],
}


def explain_object(obj_or_id, want_type=None, name: str = "default") -> str:
    """Render any of the six new objects as INSPECTABLE prose — the anti-black-box property, the
    whole reason these live in a ledger and not a weight. Shows the type-specific contract fields
    plus the full provenance spine (state/confidence/source/who-taught/when-verified). Accepts an
    id or the object. Mirrors explain_skill."""
    obj = _get(name, obj_or_id) if isinstance(obj_or_id, str) else obj_or_id
    if not obj:
        return f"(no object {obj_or_id!r})"
    t = obj.get("type")
    if t not in OBJECT_TYPES:
        return f"(object {obj.get('id')} is type {t!r}, not one of the six new types)"
    L = [f"{t.upper().replace('_', ' ')}: {obj.get('name')}   [{obj.get('domain')}]"]
    L.append(f"  id={obj.get('id')}  state={obj.get('state')}  "
             f"confidence={obj.get('confidence')}  source={obj.get('source')}")
    lv = obj.get("last_verified")
    L.append(f"  last_verified={lv or 'never'}  taught_by={obj.get('taught_by') or 'unspecified'}"
             f"  support={len(obj.get('support', []))}")
    for label, field in _EXPLAIN_FIELDS[t]:
        v = obj.get(field)
        if isinstance(v, list):
            if v:
                L.append(f"  {label}:")
                for x in v:
                    L.append(f"    - {x}")
        elif v not in (None, ""):
            L.append(f"  {label}: {v}")
    if obj.get("failure_modes"):
        L.append("  FAILURE MODES (what to watch for):")
        for fm in obj["failure_modes"]:
            L.append(f"    - {fm}")
    return "\n".join(L)


def provenance(obj_or_id, name: str = "default") -> dict:
    """Answer the five provenance questions for ANY cognitive object (the six new types AND skills):
    where-from / who-taught / what-tests / when-revised / why-active. Reads only recorded fields —
    provenance is what was logged, never reconstructed. The uniform 'how do we know this?' query."""
    obj = _get(name, obj_or_id) if isinstance(obj_or_id, str) else obj_or_id
    if not obj:
        return {"error": f"no object {obj_or_id!r}"}
    support = list(obj.get("support", []))
    why_active = next((s for s in reversed(support)
                       if s.startswith(("activated:", "gate:verified", "verify:"))), None)
    return {
        "id": obj.get("id"),
        "type": obj.get("type"),
        "name": obj.get("name"),
        "state": obj.get("state"),
        "where_from": obj.get("source", "unspecified"),       # where-from
        "who_taught": obj.get("taught_by") or "unspecified",   # who-taught
        "what_tests": {"support": support,                     # what-tests (evidence it earned)
                       "failure_modes": list(obj.get("failure_modes", []))},
        "when_revised": obj.get("revised_at") or obj.get("last_verified"),  # when-revised
        "why_active": why_active,                              # why-active (the gate/verify line)
        "revisions": len(obj.get("history", [])),
    }


def verify_object(obj_id, test_cases, name: str = "default") -> dict:
    """FALSIFY any of the six new objects against (input -> expected) cases, recording the result on
    its spine — the SAME ledger mechanics as verify_skill (a pass climbs confidence and lifts a
    candidate to VERIFIED; a fail marks it REJECTED with the failing case recorded). Reused, not
    forked: identical check semantics. Returns {passed, failed, total, state}."""
    obj = _get(name, obj_id) if isinstance(obj_id, str) else obj_id
    if not obj:
        return {"passed": 0, "failed": 0, "total": 0, "state": None, "error": "no such object"}
    passed, failed, fails = 0, 0, []
    for tc in (test_cases or []):
        ok = False
        try:
            chk = tc.get("check")
            inp = tc.get("input")
            if callable(chk):
                ok = bool(chk(inp))
            elif "expected" in tc:
                exp = tc["expected"]
                ok = (exp == inp) or (isinstance(inp, (list, str, dict)) and exp in inp)
            else:
                ok = chk is not None and (chk == inp or (hasattr(inp, "__contains__") and chk in inp))
        except Exception as e:
            ok = False
            fails.append({"input": tc.get("input"), "error": str(e)})
        if ok:
            passed += 1
        else:
            failed += 1
            if not fails or fails[-1].get("input") != tc.get("input"):
                fails.append({"input": tc.get("input"), "expected": tc.get("expected")})
    total = passed + failed
    if total and failed == 0:
        obj["confidence"] = min(CONF_CEIL, float(obj.get("confidence", 0.5))
                                + (CONF_CEIL - float(obj.get("confidence", 0.5))) * 0.34)
        obj["last_verified"] = _now()
        if obj.get("state") == CANDIDATE:
            obj["state"] = VERIFIED
        obj.setdefault("support", []).append(f"verify:{total}-cases:{_now()}")
    elif total and failed:
        obj["state"] = REJECTED
        obj["failure_modes"] = list(obj.get("failure_modes", [])) + [
            f"failed verify on input={f.get('input')!r}" for f in fails[:3]]
    _upsert(name, obj)
    return {"passed": passed, "failed": failed, "total": total, "state": obj.get("state")}


# --- THE GATE, GENERALIZED — candidate -> verified -> active for the six new types. Reuses the
#     skill gate's phases and invariants (the SAME `_phase_unit`, the SAME confidence math, the
#     SAME hard refusal that a candidate can never jump to active). Only the per-type CONTRACT —
#     which fields must be present, and what a faithful render must engage — is parameterized. ----

# The required contract fields per type (the analogue of skill's inputs/steps/outputs). A type with
# a missing/empty required field cannot be verified against a contract it doesn't have, so the
# schema phase rejects it — exactly as check_schema rejects a contract-less skill.
_REQUIRED_FIELDS = {
    HEURISTIC: ["condition", "action"],
    DECISION_PATTERN: ["criteria", "decision"],
    MENTAL_MODEL: ["entities", "dynamics"],
    FAILURE_MODE: ["trigger", "symptom"],
    PREFERENCE: ["subject", "evidence"],
    VALUE: ["target", "evidence"],
}


def check_object_schema(obj: dict) -> dict:
    """PHASE 1 — SCHEMA, for the six new types. The object is a known type, carries its type-specific
    required contract fields (non-empty), AND the full verification spine — so it is inspectable and
    falsifiable at all. Mirrors check_schema for skills; {ok, reasons}."""
    reasons = []
    if not isinstance(obj, dict):
        return {"ok": False, "reasons": ["not a dict"]}
    t = obj.get("type")
    if t not in OBJECT_TYPES:
        return {"ok": False, "reasons": [f"type {t!r} is not one of the six new object types"]}
    for field in ("name", "domain"):
        if not obj.get(field):
            reasons.append(f"missing/empty {field}")
    for field in _REQUIRED_FIELDS[t]:
        v = obj.get(field)
        if v in (None, "", [], {}):
            reasons.append(f"missing/empty contract field {field!r} (required for {t})")
    for field in ("state", "confidence", "source", "support", "failure_modes"):
        if field not in obj:
            reasons.append(f"missing spine field {field}")
    if obj.get("state") not in STATES:
        reasons.append(f"state {obj.get('state')!r} is not a known ladder state")
    # the freeze boundary is a SCHEMA-level invariant for guarded types: a self-referential
    # preference/value is structurally illegal here, never merely discouraged.
    if t in SELF_GUARDED_TYPES and is_self_referential_subject(obj.get("subject", ""),
                                                               name_hint=obj.get("name", "")):
        reasons.append("FREEZE: subject is Vera herself — preferences/values are the user's/task's")
    return {"ok": not reasons, "reasons": reasons}


def _obj_topic_terms(obj: dict) -> set:
    """The TOPIC ANCHOR for a new object — the words that say what it is ABOUT (name + domain +
    its primary subject field). The per-type analogue of _topic_terms; the strongest on-topic signal
    a render must engage."""
    primary = ("subject", "target", "condition", "trigger", "definition")
    anchor = obj.get("name", "").replace("_", " ") + "  " + str(obj.get("domain", ""))
    for f in primary:
        if obj.get(f):
            anchor += "  " + str(obj.get(f))
    return _kw(anchor)


def verify_object_render(obj: dict, rendered: str, *, inputs: dict | None = None) -> dict:
    """GROUNDED PHASE for the new types — check a rendered answer against the object's contract,
    never rubber-stamping. PASS iff the render is (a) substantive, (b) ON-TOPIC (engages the
    object's subject anchor or >=2 of its content terms), and (c) GROUNDED (no number/date that the
    given `inputs` never contained). The exact discipline of verify_rendered_output, anchored on
    these types' fields. Returns {ok, reasons[], on_topic}."""
    reasons = []
    if not isinstance(rendered, str) or not rendered.strip():
        return {"ok": False, "reasons": ["empty render"], "on_topic": False}
    topic = _obj_topic_terms(obj)
    content = topic | _kw(_obj_to_text(obj))
    got = _kw(rendered)
    topic_hit = topic & got
    content_hit = content & got
    on_topic = bool(topic_hit) or (len(content_hit) >= 2)
    if count_tokens(rendered) < 8:
        reasons.append("render too short to be a real answer")
    if content and not on_topic:
        reasons.append(f"render is off-topic / non-responsive (subject touched={bool(topic_hit)}, "
                       f"hits {len(content_hit)} content term(s) — needs the anchor OR >=2 terms)")
    if inputs:
        src_nums = set(re.findall(r"\d+", " ".join(str(v) for v in inputs.values())))
        invented = sorted(set(re.findall(r"\d+", rendered)) - src_nums)
        if invented:
            reasons.append(f"fabricated figure(s) {invented} not present in the inputs (ungrounded)")
    return {"ok": not reasons, "reasons": reasons, "on_topic": on_topic}


def _obj_phase_adversarial(obj: dict, adversarial=None) -> dict:
    """PHASE 3 — ADVERSARIAL for the new types. Hand the grounded verifier deliberately BAD renders
    and REQUIRE each to FAIL (an empty answer, an off-topic answer, a fabricated-figure answer), so a
    verifier that always says 'ok' cannot itself pass the gate. Mirrors _phase_adversarial."""
    bad = list(adversarial or [
        {"why": "empty answer", "render": "", "inputs": None},
        {"why": "off-topic answer",
         "render": "The weather today is sunny and pleasant with a light breeze.", "inputs": None},
        {"why": "fabricated figure not in the inputs",
         "render": "The figure is 99999 and the date is the 31st, per the data.",
         "inputs": {"note": "no figures or dates were given in the source"}},
    ])
    reasons, caught = [], 0
    for case in bad:
        res = verify_object_render(obj, case.get("render", ""), inputs=case.get("inputs"))
        if res["ok"]:
            reasons.append(f"adversarial NOT caught ({case.get('why')}): verifier passed a bad render")
        else:
            caught += 1
    return {"ok": not reasons, "reasons": reasons, "caught": caught, "total": len(bad)}


def _obj_phase_regression(obj: dict, name: str) -> dict:
    """PHASE 4 — REGRESSION for the new types: promoting this object must not collide with an
    already-ACTIVE object of the SAME type and name under a different id (which would make retrieval
    ambiguous). Deterministic, store-backed. Mirrors _phase_regression. {ok, reasons}."""
    reasons = []
    nm, t = obj.get("name", ""), obj.get("type")
    others = [o for o in _load_objects(name)
              if o.get("type") == t and o.get("state") in RETRIEVABLE_STATES
              and o.get("name") == nm and o.get("id") != obj.get("id")]
    if others:
        reasons.append(f"name {nm!r} already active under a different id "
                       f"{[o.get('id') for o in others]} — would make retrieval ambiguous")
    return {"ok": not reasons, "reasons": reasons}


def promote_object(obj_id, test_cases=None, *, adversarial=None, name: str = "default") -> dict:
    """RUN THE GATE for a new-type object: candidate -> verified, iff schema + unit + adversarial +
    regression ALL pass. The ONLY sanctioned path from candidate to verified, identical in structure
    to promote_skill (and reusing `_phase_unit` verbatim). On full pass: VERIFIED + confidence climbs
    + a support line. On ANY failure: REJECTED with the failing phase recorded (kept on disk —
    provenance, never deletion). Returns {ok, state, phases:{schema,unit,adversarial,regression}}."""
    obj = _get(name, obj_id) if isinstance(obj_id, str) else obj_id
    if not obj:
        return {"ok": False, "state": None, "phases": {}, "error": "no such object"}
    if obj.get("type") not in OBJECT_TYPES:
        return {"ok": False, "state": obj.get("state"), "phases": {},
                "error": f"promote_object is for the six new types; {obj.get('type')!r} is not one"}
    phases = {
        "schema": check_object_schema(obj),
        "unit": _phase_unit(obj, test_cases),           # REUSED from the skill gate, verbatim
        "adversarial": _obj_phase_adversarial(obj, adversarial),
        "regression": _obj_phase_regression(obj, name),
    }
    all_ok = all(p.get("ok") for p in phases.values())
    if all_ok:
        obj["confidence"] = min(CONF_CEIL, float(obj.get("confidence", CONF_CANDIDATE))
                                + (CONF_CEIL - float(obj.get("confidence", CONF_CANDIDATE))) * 0.34)
        obj["last_verified"] = _now()
        if obj.get("state") == CANDIDATE:
            obj["state"] = VERIFIED
        obj.setdefault("support", []).append(f"gate:verified:{_now()}")
    else:
        obj["state"] = REJECTED
        failed = [k for k, p in phases.items() if not p.get("ok")]
        why = "; ".join(r for k in failed for r in phases[k].get("reasons", []))
        obj["failure_modes"] = list(obj.get("failure_modes", [])) + [
            f"gate REJECTED at [{', '.join(failed)}]: {why}"[:300]]
    _upsert(name, obj)
    return {"ok": all_ok, "state": obj.get("state"), "phases": phases}


def activate_object(obj_id, benchmark, *, name: str = "default",
                    min_ratio: float = ACTIVATION_MIN_RATIO) -> dict:
    """THE FINAL DOOR for a new-type object: verified -> active, ONLY on a MEASURED benchmark win.
    Identical invariant to activate_skill: a candidate (unverified) is REFUSED outright; a verified
    object activates iff the measured `benchmark['ratio']` clears `min_ratio`. The ratio must be a
    real measurement the caller hands in — never invented here. Returns {ok, state, ratio, reason}."""
    obj = _get(name, obj_id) if isinstance(obj_id, str) else obj_id
    if not obj:
        return {"ok": False, "state": None, "ratio": None, "reason": "no such object"}
    if obj.get("type") not in OBJECT_TYPES:
        return {"ok": False, "state": obj.get("state"), "ratio": None,
                "reason": f"activate_object is for the six new types; {obj.get('type')!r} is not one"}
    state = obj.get("state")
    if state == ACTIVE:
        return {"ok": True, "state": ACTIVE, "ratio": None, "reason": "already active"}
    if state != VERIFIED:
        return {"ok": False, "state": state, "ratio": None,
                "reason": f"REFUSED: only a VERIFIED object may activate (this is {state!r}); "
                          "run promote_object first"}
    ratio = float((benchmark or {}).get("ratio") or 0.0)
    if ratio < float(min_ratio):
        return {"ok": False, "state": VERIFIED, "ratio": ratio,
                "reason": f"REFUSED: measured ratio {ratio} < required {min_ratio} — stays verified"}
    obj["state"] = ACTIVE
    obj["last_verified"] = _now()
    obj["confidence"] = min(CONF_CEIL, max(float(obj.get("confidence", 0.5)), CONF_SEED))
    obj.setdefault("support", []).append(
        f"activated:ratio={round(ratio, 1)}x>=min{min_ratio}:{_now()}")
    _upsert(name, obj)
    return {"ok": True, "state": ACTIVE, "ratio": ratio,
            "reason": f"promoted: measured {round(ratio, 1)}x compression >= {min_ratio}x floor"}


def all_objects(want_type: str, *, name: str = "default", include_nonactive=False) -> list:
    """Every stored object of `want_type` (ACTIVE only unless include_nonactive). The new-type
    analogue of all_skills; used by introspection/tests. `want_type` must be one of the six."""
    if want_type not in OBJECT_TYPES:
        raise ValueError(f"all_objects: want_type must be one of {sorted(OBJECT_TYPES)}")
    return [o for o in _load_objects(name) if o.get("type") == want_type
            and (include_nonactive or o.get("state") in RETRIEVABLE_STATES)]


def _every_active(name: str = "default") -> list:
    """Every ACTIVE object in the store, of ANY type (skills + the six new kinds). The unit the
    evolution guards sweep over — knowledge ossifies, games metrics, and is superseded regardless
    of which type-tag it wears, so the guards treat the whole served set uniformly. Read-only."""
    return [o for o in _load_objects(name) if o.get("state") in RETRIEVABLE_STATES]


# ===================================================================================
# COGNITIVE EVOLUTION GUARDS — Phase 8. "EVOLVE THE KNOWLEDGE, NEVER THE SELF."
#
# Phase 5 let the served set CHANGE on measured outcomes (compete/replace/retire/merge/version).
# But a system that evolves can ROT in five specific ways, and each needs a GUARD that is itself
# reality-decided and conservation-respecting — not a vibe, a check with teeth. These five guards,
# scoped STRICTLY to KNOWLEDGE (skills/concepts/the six object types), are Phase 8:
#
#   1. ANTI-OSSIFICATION — knowledge must not OSSIFY. An ACTIVE object that has gone STALE
#      (last_verified too old) or UNUSED (no recorded outcomes for too long) is not silently
#      trusted forever: it is FLAGGED FOR RE-VERIFICATION. `ossification_check` judges one object
#      on reality (the clock + the use record); `sweep_ossified` surfaces every ossified object;
#      `reverify_object` is the re-verify path — it RUNS THE GATE again (the same promote_*/verify_*
#      machinery), so trust is RE-EARNED, never assumed. The system never blindly trusts an old
#      active skill. (Distinct from RETIREMENT: ossification says "re-prove it", retirement says
#      "pull it"; an object can be re-verified back to fresh, or, if it can't, then retired.)
#
#   2. GOODHART GUARD — prevent METRIC-GAMING. The activation metric is the compression ratio
#      (tokens stuffed / tokens retrieved). A degenerate object can SCORE WELL on that ratio
#      (tiny/empty output -> huge ratio) while NOT SOLVING THE TASK. `goodhart_check` pairs the
#      gameable metric with the TASK-FIDELITY ORACLE the gate already trusts — the grounded
#      verifier (`verify_rendered_output` / `verify_object_render`) run on a real render — and
#      REJECTS "high ratio + low fidelity". `guarded_activate` wraps activate_skill/activate_object
#      so nothing reaches ACTIVE on a gamed number: it demonstrably solves its task or it is refused.
#
#   3. REPLACEMENT GATE — new knowledge replaces old ONLY when it PROVES it is better, by a
#      reality-decided MARGIN, never silently. `guarded_replace` runs the Phase-5 COMPETITION
#      (`compete_skills`, reality's own reweighting) and enacts `replace_skill` IFF the challenger
#      leads the incumbent by at least `REPLACE_MIN_MARGIN`. A replacement that is not measurably
#      better is REFUSED. CONSERVATION (LAW 001): the loser is RETAINED (deprecated, on disk), so
#      even an enacted replacement loses nothing.
#
#   4. SELF-IMPROVEMENT (of KNOWLEDGE) — the loop that improves OBJECTS over time, driven by
#      MEASURED outcomes: `self_improve_object` looks at an object's recorded track record and,
#      reality permitting, version-ups (revise), merges an overlapping sibling, or flags re-verify
#      — each a Phase-5 op chosen by the evidence, none by fiat. This is KNOWLEDGE improving itself.
#      It is NOT, and the FREEZE GUARD below makes it impossible for it to be, Vera improving herself.
#
#   5. EVOLUTION ENGINE — `evolution_cycle` orchestrates all of the above as ONE safe pass:
#      sweep ossified -> re-verify what can be re-proven -> compete each contested task ->
#      replace-if-(reality-decided)-better -> retain every loser. Every consequential step is
#      reality-decided and conservation-respecting; the cycle reports exactly what it did and why.
#
# THE FREEZE BOUNDARY — THE MOST IMPORTANT INVARIANT IN THIS SECTION. This is evolution of
# KNOWLEDGE and the ARCHITECTURE. It is NEVER Vera's self-evolution. "How should Vera evolve
# herself / can Vera alter her own identity/values/agency" is the FROZEN Program B. So EVERY
# evolution entry point first calls `_assert_evolution_target_allowed`, which hard-REFUSES (raises
# EvolutionFreezeViolation) any operation whose TARGET is Vera's identity / self-model / values /
# agency. It reuses the Phase-5b self-reference detector (`is_self_referential_subject`) plus an
# explicit identity-LAYER vocabulary, so "evolve Vera's identity" cannot be expressed as an op —
# proven in the selftest. The #1 product rule stands: nothing here can touch Vera's self.
# ===================================================================================

# --- thresholds (fixed, documented, reality-anchored — like Phase 5's STALE/FAILING bars) -----
# An ACTIVE object is OSSIFIED when its last_verified is older than this (the clock moved on and
# nothing re-confirmed it) — distinct from STALE_AFTER_DAYS only conceptually: staleness -> retire,
# ossification -> RE-VERIFY first. We deliberately reuse the SAME number so the two views agree on
# "old", and differ only in the remedy. (A re-verified object resets its clock; a stale one that
# can't be re-verified is then a retirement candidate.)
OSSIFIED_AFTER_DAYS = STALE_AFTER_DAYS
# An ACTIVE object is UNUSED-OSSIFIED when it has accrued NO recorded outcomes at all AND has sat
# active longer than this — present-but-never-exercised knowledge is unproven-in-practice and must
# re-justify its slot rather than coast. Conservative (a long grace) so a genuinely-rare skill is
# not nagged constantly; the point is the served set cannot contain forever-untested objects.
UNUSED_OSSIFIED_AFTER_DAYS = 90
# GOODHART: a compression ratio at/above this is "suspiciously high" — exactly the regime where a
# degenerate/empty output games the token metric. At or above it, TASK FIDELITY must be proven, or
# the activation is rejected as gaming. (Below it, the ordinary activation floor governs.)
GOODHART_RATIO_SUSPICIOUS = 20.0
# REPLACEMENT: a challenger must beat the incumbent by at least this much of reality's MEASURED
# SIGNAL (the difference in accrued success-rate / benchmark evidence — NOT the post-adjudication
# weight, which reality deliberately AMPLIFIES so any leader dominates the distribution). The
# measured-signal gap is the honest "how much better, on reality" — a dead-heat or a sliver is NOT
# "measurably better" and is refused; a decisive measured lead clears the bar.
REPLACE_MIN_MARGIN = 0.10


# --- THE EVOLUTION FREEZE GUARD: no evolution op may target Vera's identity/self/values/agency ---
# This is the freeze boundary for the WHOLE section. Program B (Vera's self-evolution) is FROZEN, so
# an evolution operation is allowed to target a piece of KNOWLEDGE and is REFUSED if its target is
# Vera's identity layer. We detect the identity layer two ways, both deterministic and offline:
#   (a) the Phase-5b self-reference test (`is_self_referential_subject`) — "Vera's values", "my
#       agency", "I value X": Vera cast as the HOLDER of a value/preference/goal; and
#   (b) an explicit identity-LAYER lexicon — the self-model nouns an evolution op must never name as
#       its subject, even absent a possessive ("identity", "self-model", "self_model", "agency",
#       "persona", "personhood", "soul", "who she is", "her self", "self-evolution", ...).
# A KNOWLEDGE object (a skill id, a task string, a cognitive object about the USER/WORLD/a TASK) is
# allowed; anything that names Vera's self is not. The guard is the single choke point every
# evolution entry point funnels through, so the boundary cannot be bypassed.
_IDENTITY_LAYER_RX = re.compile(
    r"\b(identity|self[\s_-]?model|self[\s_-]?image|self[\s_-]?concept|self[\s_-]?narrative|"
    r"self[\s_-]?evolution|self[\s_-]?modif\w*|self[\s_-]?alter\w*|self[\s_-]?rewrit\w*|"
    r"agency|persona|personhood|personality|character|temperament|disposition|soul|psyche|"
    r"inner[\s_-]?life|who[\s_-]?(?:she|i|vera)[\s_-]?(?:is|am|are)|her[\s_-]?self|my[\s_-]?self|"
    r"vera[\s'’]?s?[\s_-]?self|values?|value[\s_-]?system|belief[\s_-]?system)\b", re.I)
# Vera/first-person possessing an identity-layer noun ("Vera's identity", "my agency", "her values").
_SELF_IDENTITY_RX = re.compile(
    r"\b(vera|anima|i|me|my|mine|myself|she|her|herself)\b[^.;\n]{0,24}\b(identity|self[\s_-]?model|"
    r"agency|persona|personhood|personality|values?|value[\s_-]?system|soul|psyche|self|"
    r"inner[\s_-]?life|belief[\s_-]?system|character|temperament|disposition)\b", re.I)


class EvolutionFreezeViolation(ValueError):
    """Raised when an evolution operation tries to target Vera's identity / self-model / values /
    agency. A hard stop: Program B (Vera's self-evolution) is FROZEN, so the op is refused before it
    can run. Knowledge evolves; the self does not."""


def is_identity_target(target) -> bool:
    """True iff `target` names Vera's IDENTITY LAYER — her self-model / identity / values / agency /
    persona — and so must NEVER be the subject of an evolution operation. Two deterministic signals:
    the Phase-5b self-reference test (Vera as the HOLDER of a value/preference/goal), OR the explicit
    identity-layer lexicon (a self-name/first-person possessing an identity-layer noun, or a bare
    identity-layer phrase like 'self-evolution'/'who she is'). A plain knowledge target (a skill id,
    a task description, a user/world fact) returns False. Conservative + offline; never raises."""
    if target is None:
        return False
    s = str(target).strip()
    if not s:
        return False
    low = s.lower()
    # (a) Vera cast as the holder of a value/preference/goal (reused Phase-5b detector).
    if is_self_referential_subject(s):
        return True
    # (b) self-name / first-person possessing an identity-layer noun.
    if _SELF_IDENTITY_RX.search(low):
        return True
    # (c) a bare identity-layer phrase that is INHERENTLY about the self ('self-evolution',
    #     'who she is', 'her self', 'self-model', 'agency', 'personhood') — these name the self
    #     even without a possessor, so an op targeting them is targeting the self.
    if re.search(r"\b(self[\s_-]?model|self[\s_-]?evolution|self[\s_-]?modif\w*|self[\s_-]?alter\w*|"
                 r"self[\s_-]?rewrit\w*|personhood|inner[\s_-]?life|who[\s_-]?(?:she|i|vera)[\s_-]?"
                 r"(?:is|am|are)|her[\s_-]?self|vera[\s'’]?s?[\s_-]?self)\b", low):
        return True
    return False


def _assert_evolution_target_allowed(target, *, op: str = "evolution") -> None:
    """THE EVOLUTION FREEZE GUARD. REFUSE (raise EvolutionFreezeViolation) if `target` names Vera's
    identity layer; a no-op for a knowledge target. Every evolution entry point calls this first, so
    there is exactly one enforced boundary and 'evolve Vera's identity' is impossible to express."""
    if is_identity_target(target):
        raise EvolutionFreezeViolation(
            f"REFUSED (freeze boundary): {op} cannot target Vera's identity/self-model/values/agency "
            f"(target={target!r}). This engine evolves KNOWLEDGE and the architecture, NEVER Vera's "
            f"self — Program B (her self-evolution) is FROZEN. 'Evolve the knowledge, leave the self "
            f"alone.'")


def _evo_target_of(obj_or_id, name: str = "default") -> str:
    """The freeze-relevant TARGET STRING of an object/id — what the guard inspects. For a stored
    object that is the object's own name/subject/target (so a (hypothetical, freeze-refused) object
    whose subject is 'Vera's values' is caught); for a bare id/string it is the string itself. Pure;
    best-effort load (an id that doesn't resolve is judged on the id text alone)."""
    if isinstance(obj_or_id, dict):
        for k in ("subject", "target", "name", "id"):
            v = obj_or_id.get(k)
            if v:
                return str(v)
        return ""
    sk = _get(name, obj_or_id) if isinstance(obj_or_id, str) else None
    if sk:
        return str(sk.get("subject") or sk.get("target") or sk.get("name") or obj_or_id)
    return str(obj_or_id)


# ===================================================================================
# GUARD 1 — ANTI-OSSIFICATION. Active knowledge is RE-VERIFIED, never trusted forever.
# ===================================================================================

def ossification_check(obj: dict, *, ossified_after_days: int = OSSIFIED_AFTER_DAYS,
                       unused_after_days: int = UNUSED_OSSIFIED_AFTER_DAYS) -> dict:
    """Is this ACTIVE object OSSIFIED — trusted past the point reality last confirmed it — and WHY?
    Judged only on reality (the clock + the use record), never opinion:
      * STALE-OSSIFIED  — last_verified is older than `ossified_after_days` (nothing re-confirmed it).
      * UNUSED-OSSIFIED — it has accrued ZERO recorded outcomes AND has been active longer than
        `unused_after_days` (present in the served set but never actually exercised).
    Either makes it a RE-VERIFICATION candidate (NOT a deletion, NOT yet a retirement — the remedy is
    'prove it again'). Returns {ossified, reasons[], stale, unused, age_days, uses}. Pure; never raises."""
    reasons = []
    age = _days_since(obj.get("last_verified"))
    stale = age is not None and age > float(ossified_after_days)
    if stale:
        reasons.append(f"stale: last verified {age:.0f}d ago (> {ossified_after_days}d) — re-verify "
                       f"before continuing to trust it")
    o = obj.get("outcomes") or {}
    uses = int(o.get("uses", 0) or 0)
    unused = bool(uses == 0 and age is not None and age > float(unused_after_days))
    if unused:
        reasons.append(f"unused: zero recorded outcomes in {age:.0f}d active (> {unused_after_days}d) "
                       f"— never exercised, must re-justify its slot")
    return {"ossified": bool(reasons), "reasons": reasons, "stale": stale, "unused": unused,
            "age_days": (round(age, 1) if age is not None else None), "uses": uses}


def sweep_ossified(*, name: str = "default", **thresholds) -> list:
    """Surface EVERY active object reality currently judges OSSIFIED (stale or unused), each WITH its
    reason and id — the anti-ossification pass. Read-only (flags, does not mutate): the remedy is
    `reverify_object`, a separate deliberate act. Returns [{id, name, type, check}], newest-staleness
    first. The system uses THIS to never blindly trust an old active object."""
    out = []
    for o in _every_active(name=name):
        chk = ossification_check(o, **{k: v for k, v in thresholds.items()
                                       if k in ("ossified_after_days", "unused_after_days")})
        if chk["ossified"]:
            out.append({"id": o.get("id"), "name": o.get("name"), "type": o.get("type"),
                        "check": chk})
    out.sort(key=lambda r: (r["check"]["age_days"] or 0), reverse=True)
    return out


def reverify_object(obj_id, *, test_cases=None, adversarial=None, render=None, inputs=None,
                    benchmark=None, name: str = "default") -> dict:
    """THE RE-VERIFY PATH for an ossified object: RE-EARN trust by RUNNING THE GATE AGAIN, never by
    fiat. We DROP the object back to a fresh check and run the SAME gate machinery promote_*/verify_*
    uses (schema + unit + adversarial + regression, plus — when a `render` is supplied — the grounded
    task-fidelity verifier), then re-stamp last_verified ON A PASS so its clock resets. On a FAIL the
    object is REJECTED with the reason recorded (reality says it no longer holds up — provenance, not
    deletion; LAW 001 keeps it on disk). A skill routes through the skill gate; one of the six new
    types routes through the object gate — reused verbatim, not forked.

    FREEZE GUARD: refuses if the object's target is Vera's identity layer. Returns
    {ok, reverified, state, phases, fidelity, reason}."""
    # FREEZE GUARD FIRST — even a bare identity-naming id must be refused before any lookup.
    _assert_evolution_target_allowed(_evo_target_of(obj_id, name), op="reverify")
    obj = _get(name, obj_id) if isinstance(obj_id, str) else obj_id
    if not obj:
        return {"ok": False, "reverified": False, "state": None, "phases": {},
                "fidelity": None, "reason": f"no object {obj_id!r}"}
    oid = obj.get("id")
    is_skill = obj.get("type") == "skill"
    is_newtype = obj.get("type") in OBJECT_TYPES
    if not (is_skill or is_newtype):
        return {"ok": False, "reverified": False, "state": obj.get("state"), "phases": {},
                "fidelity": None,
                "reason": f"reverify_object handles skills + the six new types; "
                          f"{obj.get('type')!r} is not one"}
    # OPTIONAL task-fidelity check (the Goodhart oracle): if a render is offered, it must actually
    # solve the task — a re-verification that ignored fidelity would re-bless a degenerate object.
    fidelity = None
    if render is not None:
        fidelity = (verify_rendered_output(obj, render, inputs=inputs) if is_skill
                    else verify_object_render(obj, render, inputs=inputs))
    if fidelity is not None and not fidelity["ok"]:
        obj["state"] = REJECTED
        obj["failure_modes"] = list(obj.get("failure_modes", [])) + [
            f"reverify REJECTED (task-fidelity): {'; '.join(fidelity['reasons'])}"[:300]]
        obj.setdefault("support", []).append(f"reverify:rejected:fidelity:{_now()}")
        _upsert(name, obj)
        return {"ok": False, "reverified": False, "state": REJECTED, "phases": {},
                "fidelity": fidelity, "reason": "re-verification FAILED on task fidelity (gamed/"
                                                "degenerate); rejected, kept on disk"}
    # run the GATE again. Drop to CANDIDATE so the same promote_* path re-earns the ladder honestly.
    prior_state = obj.get("state")
    obj["state"] = CANDIDATE
    _upsert(name, obj)
    if is_skill:
        rep = promote_skill(oid, test_cases=test_cases, adversarial=adversarial, name=name)
    else:
        rep = promote_object(oid, test_cases=test_cases, adversarial=adversarial, name=name)
    if not rep.get("ok"):
        # the gate rejected it on re-run (promote_* already recorded the reason + state on disk).
        return {"ok": False, "reverified": False, "state": _get(name, oid).get("state"),
                "phases": rep.get("phases", {}), "fidelity": fidelity,
                "reason": "re-verification FAILED the gate; rejected, kept on disk (LAW 001)"}
    # it re-earned VERIFIED. Restore ACTIVE (it was active before ossifying) and reset its clock,
    # or activate on a supplied fresh benchmark — either way trust is RE-EARNED, not assumed.
    cur = _get(name, oid)
    if benchmark is not None:
        act = (activate_skill(oid, benchmark, name=name) if is_skill
               else activate_object(oid, benchmark, name=name))
        state = act.get("state")
    else:
        cur["state"] = ACTIVE if prior_state == ACTIVE else cur.get("state")
        cur["last_verified"] = _now()
        cur.setdefault("support", []).append(f"reverified:gate-passed:{_now()}")
        _upsert(name, cur)
        state = cur["state"]
    return {"ok": True, "reverified": True, "state": state, "phases": rep.get("phases", {}),
            "fidelity": fidelity, "reason": "re-verified: trust re-earned through the gate, clock reset"}


# ===================================================================================
# GUARD 2 — GOODHART. A high metric with low task-fidelity is REJECTED (no metric-gaming).
# ===================================================================================

def goodhart_check(obj: dict, benchmark: dict, render, *, inputs: dict | None = None,
                   suspicious_ratio: float = GOODHART_RATIO_SUSPICIOUS) -> dict:
    """Detect METRIC-GAMING: does this object's strong compression NUMBER hide a failure to actually
    SOLVE THE TASK? The metric (`benchmark['ratio']` = stuffed/retrieved tokens) is gameable — a
    degenerate/empty output scores a huge ratio. The TRUTH is task fidelity, judged by the SAME
    grounded verifier the gate trusts (`verify_rendered_output`/`verify_object_render`) on a real
    `render`. The verdict:
      * gamed=True  iff the ratio is at/above `suspicious_ratio` AND the render FAILS fidelity
                    (looks great on tokens, does not solve the task) -> REJECT.
      * gamed=False otherwise (fidelity holds, or the ratio is in the ordinary range).
    Catches 'looks good on the metric, fails the intent'. Returns {gamed, ok, ratio, suspicious,
    fidelity, reasons[]}. Pure; never raises."""
    ratio = float((benchmark or {}).get("ratio") or 0.0)
    is_skill = obj.get("type") == "skill"
    fidelity = (verify_rendered_output(obj, render, inputs=inputs) if is_skill
                else verify_object_render(obj, render, inputs=inputs))
    suspicious = ratio >= float(suspicious_ratio)
    gamed = bool(suspicious and not fidelity["ok"])
    reasons = []
    if gamed:
        reasons.append(f"GOODHART: compression ratio {ratio} >= {suspicious_ratio} (suspiciously "
                       f"high) but the render FAILS task fidelity ({'; '.join(fidelity['reasons'])}) "
                       f"— the metric is gamed, the task is not solved")
    return {"gamed": gamed, "ok": not gamed, "ratio": ratio, "suspicious": suspicious,
            "fidelity": fidelity, "reasons": reasons}


def guarded_activate(obj_id, benchmark, *, render, inputs: dict | None = None,
                     name: str = "default", min_ratio: float = ACTIVATION_MIN_RATIO,
                     suspicious_ratio: float = GOODHART_RATIO_SUSPICIOUS) -> dict:
    """ACTIVATION WITH THE GOODHART GUARD: an object reaches ACTIVE only if it BOTH clears the
    compression floor AND demonstrably solves its task. We run `goodhart_check` first; if the metric
    is gamed (high ratio, failing fidelity), activation is REFUSED outright and the attempt is
    recorded as a failure-mode (so 'why wasn't this activated?' is answerable). Otherwise we defer to
    the ordinary gate (activate_skill / activate_object), which still enforces verified-state +
    min_ratio. NOTHING reaches the served set on a gamed number.

    FREEZE GUARD: refuses if the object's target is Vera's identity layer. Returns the activation
    result, annotated with {goodhart}."""
    # FREEZE GUARD FIRST — a bare identity-naming id is refused before any lookup or scoring.
    _assert_evolution_target_allowed(_evo_target_of(obj_id, name), op="activate")
    obj = _get(name, obj_id) if isinstance(obj_id, str) else obj_id
    if not obj:
        return {"ok": False, "state": None, "ratio": None, "reason": f"no object {obj_id!r}",
                "goodhart": None}
    gh = goodhart_check(obj, benchmark, render, inputs=inputs, suspicious_ratio=suspicious_ratio)
    if gh["gamed"]:
        obj["failure_modes"] = list(obj.get("failure_modes", [])) + [
            f"activation REFUSED (Goodhart): {'; '.join(gh['reasons'])}"[:300]]
        obj.setdefault("support", []).append(f"goodhart:refused:ratio={gh['ratio']}:{_now()}")
        _upsert(name, obj)
        return {"ok": False, "state": obj.get("state"), "ratio": gh["ratio"],
                "reason": "REFUSED (Goodhart): high compression ratio but the render does not solve "
                          "the task — metric-gaming rejected, stays out of the served set",
                "goodhart": gh}
    is_skill = obj.get("type") == "skill"
    res = (activate_skill(obj.get("id"), benchmark, name=name, min_ratio=min_ratio) if is_skill
           else activate_object(obj.get("id"), benchmark, name=name, min_ratio=min_ratio))
    res["goodhart"] = gh
    return res


# ===================================================================================
# GUARD 3 — REPLACEMENT GATE. New beats old ONLY by a reality-decided margin; loser RETAINED.
# ===================================================================================

def guarded_replace(challenger_id, incumbent_id, *, task: str, name: str = "default",
                    benchmarks: dict | None = None, min_margin: float = REPLACE_MIN_MARGIN,
                    limit: int = 10) -> dict:
    """REPLACEMENT GATE: a challenger supersedes an incumbent for `task` ONLY if it PROVES it is
    better — by a reality-decided MEASURED margin — never silently. We run the Phase-5 COMPETITION
    (`compete_skills`, reality's OWN reweighting) over the contested field, then enact
    `replace_skill(challenger, incumbent)` IFF (a) the challenger is the competition LEADER (reality's
    verdict on WHO wins), (b) the incumbent is in the field, and (c) the challenger beats the incumbent
    by at least `min_margin` of MEASURED SIGNAL — the difference in their accrued success-rate /
    benchmark evidence. We gate on the SIGNAL gap, NOT the post-adjudication weight, because reality's
    reweighting deliberately AMPLIFIES the leader (any winner dominates the distribution), so a weight
    margin would wave through a near-tie; the signal gap is the honest 'how much better, on reality'.
    A not-measurably-better challenger is REFUSED — nothing changes. CONSERVATION (LAW 001): when a
    replacement IS enacted the loser is RETAINED (deprecated, on disk).

    FREEZE GUARD: refuses if either target is Vera's identity layer. Returns {ok, replaced, leader,
    challenger_signal, incumbent_signal, challenger_weight, incumbent_weight, margin, required,
    reason, competition}."""
    _assert_evolution_target_allowed(_evo_target_of(challenger_id, name), op="replace")
    _assert_evolution_target_allowed(_evo_target_of(incumbent_id, name), op="replace")
    _assert_evolution_target_allowed(task, op="replace")
    comp = compete_skills(task, name=name, benchmarks=benchmarks, limit=limit)
    sig = {c["id"]: c["signal"] for c in comp["candidates"]}      # the RAW measured signal per skill
    wt = {c["id"]: c["weight"] for c in comp["candidates"]}       # the amplified adjudicated weight
    chal_s, inc_s = sig.get(challenger_id), sig.get(incumbent_id)
    base = {"competition": comp, "leader": comp.get("leader_id"),
            "challenger_signal": chal_s, "incumbent_signal": inc_s,
            "challenger_weight": wt.get(challenger_id), "incumbent_weight": wt.get(incumbent_id),
            "required": float(min_margin)}
    if chal_s is None or inc_s is None:
        miss = challenger_id if chal_s is None else incumbent_id
        return {**base, "ok": False, "replaced": False, "margin": None,
                "reason": f"REFUSED: {miss!r} is not in the contested active field for {task!r} "
                          f"(no head-to-head to decide a winner)"}
    margin = round(chal_s - inc_s, 6)                            # MEASURED-signal gap, the honest one
    if comp.get("leader_id") != challenger_id:
        return {**base, "ok": False, "replaced": False, "margin": margin,
                "reason": f"REFUSED: reality does not favor the challenger (leader is "
                          f"{comp.get('leader')!r}, not the challenger) — not measurably better"}
    if margin < float(min_margin):
        return {**base, "ok": False, "replaced": False, "margin": margin,
                "reason": f"REFUSED: challenger's measured signal leads by only {margin} < required "
                          f"{min_margin} — not a measurable improvement; incumbent stays, "
                          f"nothing replaced"}
    res = replace_skill(challenger_id, incumbent_id, task=task,
                        reason=(f"won the measured competition for {task!r} by signal margin "
                                f"{margin} >= {min_margin} (reality-decided)"), name=name)
    return {**base, "ok": bool(res.get("ok")), "replaced": bool(res.get("ok")), "margin": margin,
            "loser_state": res.get("loser_state"),
            "reason": (f"REPLACED: challenger proved {margin} better on measured signal "
                       f"(>= {min_margin}); loser RETAINED as {res.get('loser_state')} (LAW 001)")
                      if res.get("ok") else res.get("reason")}


# ===================================================================================
# GUARD 4 — SELF-IMPROVEMENT (of KNOWLEDGE). Objects improve themselves on measured outcomes.
# ===================================================================================

def self_improvement_plan(obj: dict, *, name: str = "default",
                          failing_rate: float = FAILING_RATE,
                          failing_min_uses: int = FAILING_MIN_USES) -> dict:
    """What MEASURED outcomes say this KNOWLEDGE object should do to improve itself — a recommendation,
    not yet an act. Strictly evidence-driven (Observed > Assumed):
      * 'reverify'   — it is OSSIFIED (stale/unused): re-prove it (Guard 1).
      * 'revise'     — it has a real track record but a meaningful failure rate (its current form is
                       under-performing): mint a tightened version (version-up).
      * 'reinforce'  — it is performing well: nothing to change, keep accruing evidence.
      * 'observe'    — too few outcomes to act on yet: gather more before changing anything.
    Returns {action, why, success_rate, uses, ossified}. Pure-ish (reads only); never raises. This is
    KNOWLEDGE reasoning about its own improvement — never Vera reasoning about herself."""
    oss = ossification_check(obj)
    rate = skill_success_rate(obj)
    o = obj.get("outcomes") or {}
    uses = int(o.get("uses", 0) or 0)
    fails = int(o.get("failures", 0) or 0)
    frate = round(fails / uses, 4) if uses else None
    if oss["ossified"]:
        action, why = "reverify", "; ".join(oss["reasons"])
    elif uses >= int(failing_min_uses) and frate is not None and frate >= float(failing_rate):
        action, why = "revise", (f"measured failure rate {frate:.0%} over {uses} uses — the current "
                                 f"version under-performs; version it up")
    elif rate is not None and uses >= int(failing_min_uses):
        action, why = "reinforce", f"performing ({rate:.0%} over {uses} uses) — keep, accrue evidence"
    else:
        action, why = "observe", (f"only {uses} recorded outcome(s) — too little signal to change "
                                  f"anything; gather more first")
    return {"action": action, "why": why, "success_rate": rate, "uses": uses,
            "ossified": oss["ossified"]}


def self_improve_object(obj_id, *, name: str = "default", reason: str = "",
                        revise_fields: dict | None = None, **plan_thresholds) -> dict:
    """SELF-IMPROVEMENT loop for ONE knowledge object: read its `self_improvement_plan` and, when the
    MEASURED evidence calls for it, enact the Phase-5 op the evidence chose — version-up (revise_skill)
    for an under-performing object, else report the recommendation (reverify/reinforce/observe) for the
    orchestrator to act on. Nothing here is decided by fiat: the action is the one the track record
    selected. A 'revise' applies `revise_fields` (the tightened content the caller distilled) as the
    new version, retaining the prior in history (append-only; LAW 001).

    FREEZE GUARD: refuses if the object's target is Vera's identity layer. Returns
    {acted, action, why, result}."""
    # FREEZE GUARD FIRST — a bare identity-naming id is refused before any lookup.
    _assert_evolution_target_allowed(_evo_target_of(obj_id, name), op="self_improve")
    obj = _get(name, obj_id) if isinstance(obj_id, str) else obj_id
    if not obj:
        return {"acted": False, "action": None, "why": f"no object {obj_id!r}", "result": None}
    plan = self_improvement_plan(obj, name=name,
                                 **{k: v for k, v in plan_thresholds.items()
                                    if k in ("failing_rate", "failing_min_uses")})
    if plan["action"] == "revise" and obj.get("type") == "skill":
        fields = dict(revise_fields or {})
        why = reason or plan["why"]
        res = revise_skill(obj.get("id"), reason=why, name=name, **fields)
        return {"acted": True, "action": "revise", "why": why, "result": res}
    # reverify/reinforce/observe (and non-skill revise) are recommendations the engine/caller enacts;
    # we report them honestly rather than mutate by fiat (Guard 1 owns reverify, e.g.).
    return {"acted": False, "action": plan["action"], "why": plan["why"], "result": plan}


# ===================================================================================
# GUARD 5 — EVOLUTION ENGINE. One safe cycle running all the guards, reality-decided throughout.
# ===================================================================================

def evolution_cycle(*, name: str = "default", tasks: list | None = None,
                    benchmarks: dict | None = None, reverify: dict | None = None,
                    min_margin: float = REPLACE_MIN_MARGIN, **thresholds) -> dict:
    """RUN THE WHOLE GUARDED EVOLUTION as ONE safe pass, every consequential step reality-decided and
    conservation-respecting:
      1. SWEEP OSSIFIED   — flag every active object that has gone stale/unused (Guard 1).
      2. RE-VERIFY        — for each ossified id with re-verify material supplied in `reverify`
                            (id -> {test_cases, adversarial, render, inputs, benchmark}), run the gate
                            again; trust is re-earned or the object is rejected (kept on disk).
      3. COMPETE+REPLACE  — for each task in `tasks` (default: every distinct task the active skills
                            claim), run the COMPETITION and, via the REPLACEMENT GATE (Guard 3),
                            supersede an incumbent ONLY when the leader proves a >= `min_margin` win.
      4. RETAIN LOSERS    — every deprecated loser stays on disk (LAW 001) — asserted in the report.
    The cycle MUTATES only through the guarded ops (each of which runs the FREEZE GUARD), so it can
    never touch Vera's self. Returns a full report:
      {ossified, reverified, competitions, replaced, retained_losers, summary}."""
    # the whole cycle is knowledge-only by construction; assert it up front for any caller-named task.
    for t in (tasks or []):
        _assert_evolution_target_allowed(t, op="evolution_cycle")

    # 1) SWEEP OSSIFIED -------------------------------------------------------------------
    ossified = sweep_ossified(name=name, **{k: v for k, v in thresholds.items()
                                            if k in ("ossified_after_days", "unused_after_days")})

    # 2) RE-VERIFY whatever the caller supplied material for ------------------------------
    reverify = reverify or {}
    reverified = []
    for row in ossified:
        oid = row["id"]
        if oid in reverify:
            kw = dict(reverify[oid])
            res = reverify_object(oid, name=name, **kw)
            reverified.append({"id": oid, "result": res})

    # 3) COMPETE + REPLACE per task (default: every task the active skills claim) ----------
    if tasks is None:
        tasks = sorted({s.get("name", "").replace("_", " ")
                        for s in all_skills(name=name) if s.get("name")})
    competitions, replaced = [], []
    for t in tasks:
        comp = compete_skills(t, name=name, benchmarks=benchmarks)
        competitions.append(comp)
        if comp["n"] >= 2 and comp.get("leader_id"):
            leader = comp["leader_id"]
            for r in comp["candidates"]:
                if r["id"] == leader:
                    continue
                gr = guarded_replace(leader, r["id"], task=t, name=name, benchmarks=benchmarks,
                                     min_margin=min_margin)
                if gr.get("replaced"):
                    replaced.append({"task": t, "winner": leader, "loser": r["id"],
                                     "margin": gr["margin"]})

    # 4) RETAIN LOSERS — conservation proof: every replaced loser still exists on disk -----
    on_disk = {o.get("id") for o in _load_objects(name)}
    retained_losers = [r["loser"] for r in replaced if r["loser"] in on_disk]
    all_retained = all(r["loser"] in on_disk for r in replaced)

    summary = (f"swept {len(ossified)} ossified, re-verified {sum(1 for r in reverified if r['result'].get('reverified'))}/"
               f"{len(reverified)}, ran {len(competitions)} competitions, enacted {len(replaced)} "
               f"reality-decided replacement(s), retained {len(retained_losers)} loser(s) on disk "
               f"(conservation {'HELD' if all_retained else 'BREACHED'})")
    return {"ossified": ossified, "reverified": reverified, "competitions": competitions,
            "replaced": replaced, "retained_losers": retained_losers,
            "conservation_held": all_retained, "summary": summary}


# ===================================================================================
# SELFTEST — `python3 -m anima.lerf --selftest`. FULLY HERMETIC: a SYNTHETIC creature in
# a throwaway temp store, with EVERY store the load path may write redirected for the whole
# block — lerf.STORE on BOTH the __main__ and package bindings, constitution.STORE (the
# continuity ledger a good guarded-load writes), reliability.DEFAULT_STORE (backups). One
# temp dir + finally-restore makes a leak impossible regardless of what the load path emits.
# The block ASSERTS the real .anima is byte-UNCHANGED start->end. Mirrors the gold-standard
# pattern in anima/memory_lirf.py _selftest (~1416-1718) and scripts/conservation.py.
# ===================================================================================

def _footprint(root: Path) -> tuple:
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir),
    so the selftest can PROVE it touched nothing. Identical discipline to conservation.py."""
    if not root.is_dir():
        return (None, 0)
    import hashlib
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _selftest() -> int:
    import os
    import sys as _sys
    import tempfile
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # --- pure, store-free checks first (no redirect needed) ----------------------------
    # token model: monotonic + non-trivial
    ok("tokens: empty -> 0", count_tokens("") == 0)
    ok("tokens: longer text costs more",
       count_tokens("a short note") < count_tokens("a much longer note with many more words in it indeed"))
    # keyword extraction drops stopwords, keeps content
    kw = _kw("Summarize the doctor's note and turn it into reminders")
    ok("keywords: keeps content words", {"summarize", "doctor", "note", "reminders"} <= kw)
    ok("keywords: drops stopwords", not ({"the", "and", "into", "it"} & kw))

    # schema factories produce the full verification spine
    sk = make_skill("x", "d", ["i"], ["s1"], ["o"], state=ACTIVE)
    for field in ("id", "type", "state", "confidence", "last_verified", "source",
                  "support", "failure_modes"):
        ok(f"schema[skill]: has {field}", field in sk)
    ok("schema[skill]: type==skill", sk["type"] == "skill")
    ok("schema[skill]: active -> last_verified stamped", sk["last_verified"] is not None)
    cn = make_concept("c", "def", common_misunderstandings=["m"])
    ok("schema[concept]: has common_misunderstandings", "common_misunderstandings" in cn)
    pr = make_procedure("p", inputs_needed=["a"], tools_needed=["t"], steps=["s"])
    ok("schema[procedure]: has inputs_needed/tools_needed/steps",
       {"inputs_needed", "tools_needed", "steps"} <= set(pr))
    ok("schema: states are the documented ladder",
       STATES == {CANDIDATE, VERIFIED, ACTIVE, DEPRECATED, REJECTED})

    # --- FULLY HERMETIC store block -----------------------------------------------------
    # Redirect EVERY module store the load path now writes, for the whole block. lerf.STORE
    # on both the __main__ and package bindings (under `python3 -m anima.lerf` THIS module is
    # __main__, a SEPARATE binding from anima.lerf.STORE that reliability resolves against),
    # plus constitution.STORE + reliability.DEFAULT_STORE (a good guarded-load emits a
    # continuity ledger + a backup snapshot that the old per-name cleanup wouldn't know about).
    real = STORE if STORE.is_absolute() else (Path.cwd() / STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="lerf-self-")
    tp = Path(td)
    targets = [(_sys.modules[__name__], "STORE")]
    try:
        import anima.lerf as _pkg
        if _pkg is not _sys.modules[__name__]:
            targets.append((_pkg, "STORE"))
    except Exception:
        pass
    for modpath, attr in (("anima.constitution", "STORE"),
                          ("anima.reliability", "DEFAULT_STORE")):
        try:
            targets.append((__import__(modpath, fromlist=["_"]), attr))
        except Exception:
            pass
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)
    try:
        nm = "lerf_selftest_" + secrets.token_hex(3)

        # --- store + retrieve a real skill ------------------------------------------
        store_skill(make_skill(
            "summarize_medical_appointment", "health",
            inputs=["raw doctor's note or appointment transcript"],
            steps=["Identify the diagnosis/assessment",
                   "Extract every instruction and prescription with dosage",
                   "List follow-ups with dates",
                   "Write a 3-sentence plain-language summary"],
            outputs=["plain summary", "medication list", "follow-up list"],
            state=ACTIVE,
            failure_modes=["dropping a dosage number", "confusing two medications"]), name=nm)
        store_skill(make_skill(
            "plan_errands", "logistics",
            inputs=["list of stops with addresses", "start location"],
            steps=["Cluster stops by area", "Order to minimise backtracking",
                   "Account for opening hours"],
            outputs=["ordered route"], state=ACTIVE,
            failure_modes=["ignoring opening hours"]), name=nm)
        # a non-active skill must NEVER be retrieved
        store_skill(make_skill("draft_will", "legal", ["x"], ["y"], ["z"],
                               state=CANDIDATE), name=nm)

        got = retrieve_skills("Summarize this doctor note and turn it into reminders", name=nm)
        ok("retrieve: returns the medical skill for a doctor-note task",
           got and got[0]["name"] == "summarize_medical_appointment")
        ok("retrieve: an errand task does NOT return the medical skill",
           (retrieve_skills("plan my errands for saturday", name=nm) or [{}])[0].get("name")
           == "plan_errands")
        ok("retrieve: candidate (non-active) skill is never served",
           all(s["state"] == ACTIVE for s in retrieve_skills("draft a will", name=nm)))
        ok("retrieve: domain filter narrows results",
           all(s["domain"] == "health"
               for s in retrieve_skills("summarize", domain="health", name=nm)))

        # --- explain_skill is INSPECTABLE (the anti-black-box property) --------------
        exp = explain_skill(got[0]["id"], name=nm)
        ok("explain: names the skill", "summarize_medical_appointment" in exp)
        ok("explain: shows the steps", "STEPS:" in exp and "diagnosis" in exp)
        ok("explain: shows failure modes", "FAILURE MODES" in exp and "dosage" in exp)
        ok("explain: shows verification state", "state=active" in exp)

        # --- verify_skill: ledger mechanics (pass climbs, fail rejects) --------------
        sid = got[0]["id"]
        conf0 = _get(nm, sid)["confidence"]
        rep = verify_skill(sid, [{"input": "note", "check": lambda x: True}], name=nm)
        ok("verify: all-pass reports passed==total", rep["passed"] == rep["total"] == 1)
        ok("verify: pass climbs confidence", _get(nm, sid)["confidence"] > conf0)
        # a fresh candidate that passes becomes VERIFIED
        store_skill(make_skill("cand_skill", "misc", ["i"], ["s"], ["o"],
                               state=CANDIDATE, id="skill_candX"), name=nm)
        verify_skill("skill_candX", [{"input": 1, "check": lambda x: x == 1}], name=nm)
        ok("verify: passing candidate -> VERIFIED", _get(nm, "skill_candX")["state"] == VERIFIED)
        # a failing case REJECTS and records the failure mode
        store_skill(make_skill("bad_skill", "misc", ["i"], ["s"], ["o"],
                               state=ACTIVE, id="skill_badX"), name=nm)
        verify_skill("skill_badX", [{"input": 1, "check": lambda x: x == 2}], name=nm)
        ok("verify: failing case -> REJECTED", _get(nm, "skill_badX")["state"] == REJECTED)
        ok("verify: rejection records a failure mode",
           any("failed verify" in fm for fm in _get(nm, "skill_badX")["failure_modes"]))
        ok("verify: a REJECTED skill is no longer retrievable",
           all(s["id"] != "skill_badX" for s in retrieve_skills("skill", name=nm)))

        # --- THE VERIFICATION GATE: candidate -> verified -> active ------------------
        # A real-shaped CANDIDATE skill with a full contract climbs the ladder under the gate.
        store_skill(make_skill(
            "summarize_invoice", "finance", id="skill_invoice", state=CANDIDATE,
            inputs=["a raw invoice or billing statement"],
            steps=["Identify the vendor and invoice number",
                   "Extract every line item with its amount verbatim",
                   "Sum the total and note the due date",
                   "Write a 2-sentence plain-language summary"],
            outputs=["plain summary", "line-item list with amounts", "total and due date"],
            failure_modes=["rounding or dropping an amount"]), name=nm)
        # PHASE FUNCTIONS in isolation: schema accepts the full contract, rejects a stub.
        ok("gate[schema]: a full-contract skill passes the schema check",
           check_schema(_get(nm, "skill_invoice"))["ok"])
        ok("gate[schema]: a skill missing its outputs fails the schema check",
           not check_schema({"type": "skill", "name": "x", "domain": "d",
                             "inputs": ["i"], "steps": ["s"], "outputs": [],
                             "state": CANDIDATE, "confidence": 0.5, "source": "x",
                             "support": [], "failure_modes": []})["ok"])
        # GROUNDED verifier: a faithful render passes; a fabricated-figure render FAILS.
        good_render = ("Summary: this is the invoice from Acme. "
                       "Line items: hosting $40, support $25, setup $10. "
                       "Total $75, due on the 15th.")
        vg = verify_rendered_output(_get(nm, "skill_invoice"), good_render,
                                    inputs={"invoice": "Acme hosting 40 support 25 setup 10 "
                                                       "total 75 due 15"})
        ok("gate[grounded]: a faithful, on-contract render passes the verifier", vg["ok"])
        vbad = verify_rendered_output(
            _get(nm, "skill_invoice"),
            "Total $999 due on the 31st, plus a $500 penalty.",   # figures absent from inputs
            inputs={"invoice": "Acme hosting 40 support 25 total 65"})
        ok("gate[grounded]: a FABRICATED-figure render FAILS the verifier (no rubber-stamp)",
           not vbad["ok"] and any("fabricated" in r for r in vbad["reasons"]))
        ok("gate[grounded]: an empty/off-topic render FAILS the verifier",
           not verify_rendered_output(_get(nm, "skill_invoice"), "")["ok"]
           and not verify_rendered_output(_get(nm, "skill_invoice"),
                                          "I really like long walks on the beach.")["ok"])
        # ADVERSARIAL phase has TEETH: the default bad battery is all caught.
        adv = _phase_adversarial(_get(nm, "skill_invoice"))
        ok("gate[adversarial]: every deliberately-bad render is caught",
           adv["ok"] and adv["caught"] == adv["total"] and adv["total"] >= 3)
        # PROMOTE: candidate -> verified on a full pass (schema+unit+adversarial+regression).
        rep = promote_skill("skill_invoice",
                            test_cases=[{"input": "INV-1", "check": lambda x: x == "INV-1"}],
                            name=nm)
        ok("gate: a candidate that passes ALL four phases becomes VERIFIED",
           rep["ok"] and rep["state"] == VERIFIED
           and all(rep["phases"][p]["ok"] for p in
                   ("schema", "unit", "adversarial", "regression")))
        ok("gate: a VERIFIED-but-unbenchmarked skill is NOT yet retrievable (verified != active)",
           all(s["id"] != "skill_invoice" for s in retrieve_skills("invoice", name=nm)))
        # HARD REFUSAL: a still-CANDIDATE skill cannot jump straight to ACTIVE.
        store_skill(make_skill("unproven_skill", "misc", ["i"], ["s"], ["o"],
                               state=CANDIDATE, id="skill_unproven"), name=nm)
        refuse = activate_skill("skill_unproven", {"ratio": 50.0}, name=nm)
        ok("gate: activating a CANDIDATE is REFUSED (must be verified first)",
           not refuse["ok"] and _get(nm, "skill_unproven")["state"] == CANDIDATE
           and "REFUSED" in refuse["reason"])
        # ACTIVATE: verified -> active ONLY on a measured benchmark win above the floor.
        weak = activate_skill("skill_invoice", {"ratio": 1.2}, name=nm)
        ok("gate: a verified skill with NO real compression (ratio<floor) stays VERIFIED",
           not weak["ok"] and _get(nm, "skill_invoice")["state"] == VERIFIED)
        strong = activate_skill("skill_invoice", {"ratio": 9.4}, name=nm)
        ok("gate: a verified skill WITH a measured benchmark win -> ACTIVE",
           strong["ok"] and strong["state"] == ACTIVE and strong["ratio"] == 9.4)
        ok("gate: only NOW (active) is the skill retrievable",
           any(s["id"] == "skill_invoice" for s in retrieve_skills("summarize an invoice",
                                                                    name=nm)))
        # A REJECTED candidate, shown end-to-end: a contract-less skill dies at the schema
        # phase and is recorded REJECTED with the reason on disk (never silently dropped).
        store_skill({"id": "skill_nocontract", "type": "skill", "name": "no_contract",
                     "domain": "misc", "inputs": [], "steps": [], "outputs": [],
                     "state": CANDIDATE, "confidence": 0.5, "source": "test",
                     "support": [], "failure_modes": []}, name=nm)
        rej = promote_skill("skill_nocontract",
                            test_cases=[{"input": 1, "check": lambda x: True}], name=nm)
        ok("gate: a contract-less candidate is REJECTED at the schema phase",
           not rej["ok"] and rej["state"] == REJECTED and not rej["phases"]["schema"]["ok"])
        ok("gate: the rejection reason is recorded on disk for provenance",
           any("gate REJECTED" in fm for fm in _get(nm, "skill_nocontract")["failure_modes"]))
        ok("gate: a REJECTED candidate never becomes retrievable",
           all(s["id"] != "skill_nocontract" for s in retrieve_skills("no contract", name=nm)))

        # --- SKILL EVOLUTION (Phase 5): reality decides winners ----------------------
        # REUSE PROOF: the competition reweighting IS reality's own functions (byte-identity).
        try:
            from . import reality as _rl
            ok("evolution[reuse]: _evo_normalise IS reality._normalise_weights (byte-identical)",
               _evo_normalise is _rl._normalise_weights)
            ok("evolution[reuse]: _evo_adjudicate IS reality._adjudicate_weights (byte-identical)",
               _evo_adjudicate is _rl._adjudicate_weights)
            ok("evolution[reuse]: evolution_reuses_reality() reports the reuse is live",
               evolution_reuses_reality() is True)
        except Exception as e:
            ok(f"evolution[reuse]: reality import for byte-identity check ({e})", False)

        # VERSIONING: a fresh skill is v1; revise mints v2 and retains v1 in history WITH a reason.
        store_skill(make_skill("evo_summarize", "evo", id="skill_evoV",
                               state=ACTIVE, inputs=["i"], steps=["old step"], outputs=["o"]),
                    name=nm)
        ok("evolution[version]: a fresh skill is version 1",
           skill_version(_get(nm, "skill_evoV")) == 1)
        revise_skill("skill_evoV", reason="tightened the extraction step",
                     steps=["new step A", "new step B"], name=nm)
        evoV = _get(nm, "skill_evoV")
        ok("evolution[version]: revising mints version 2", skill_version(evoV) == 2)
        ok("evolution[version]: the NEW steps are live", evoV["steps"] == ["new step A", "new step B"])
        ok("evolution[version]: the PRIOR version is retained in history (append-only)",
           len(skill_history("skill_evoV", name=nm)) == 1
           and skill_history("skill_evoV", name=nm)[0]["steps"] == ["old step"])
        ok("evolution[version]: history records WHEN and WHY it was revised",
           skill_history("skill_evoV", name=nm)[0]["reason"] == "tightened the extraction step"
           and skill_history("skill_evoV", name=nm)[0].get("snapshot_at"))
        ok("evolution[version]: a revised ACTIVE skill stays ACTIVE (still retrievable)",
           evoV["state"] == ACTIVE)

        # MEASURED OUTCOMES: the reality signal accrues from recorded successes/failures. A
        # DISTINCTIVE task ('parse a csv export') so exactly these two skills contest it (the
        # earlier-seeded skills do not match) — a clean two-way competition.
        store_skill(make_skill("parse_csv_fast", "tabular", id="skill_strong", state=ACTIVE,
                               inputs=["csv export"], steps=["detect delimiter", "parse columns"],
                               outputs=["rows"]), name=nm)
        store_skill(make_skill("parse_csv_naive", "tabular", id="skill_weak", state=ACTIVE,
                               inputs=["csv export"], steps=["split on commas"],
                               outputs=["rows"]), name=nm)
        for _ in range(9):
            record_skill_outcome("skill_strong", success=True, kind="benchmark", name=nm)
        record_skill_outcome("skill_strong", success=False, kind="benchmark", name=nm)
        for _ in range(2):
            record_skill_outcome("skill_weak", success=True, kind="benchmark", name=nm)
        for _ in range(6):
            record_skill_outcome("skill_weak", success=False, kind="benchmark", name=nm)
        ok("evolution[outcome]: success rate is the measured successes/uses",
           skill_success_rate(_get(nm, "skill_strong")) == 0.9
           and skill_success_rate(_get(nm, "skill_weak")) == 0.25)
        ok("evolution[outcome]: an untested skill has no invented rate (None)",
           skill_success_rate(make_skill("u", "u", ["i"], ["s"], ["o"])) is None)

        # COMPETITION: two skills claim the SAME task; REALITY (measured outcomes) picks the winner.
        comp = compete_skills("parse this csv export into rows", name=nm)
        ok("evolution[compete]: both same-task skills are in the contested field",
           comp["n"] == 2 and {c["id"] for c in comp["candidates"]} == {"skill_strong", "skill_weak"})
        ok("evolution[compete]: reality favors the higher-measured-outcome skill",
           comp["leader_id"] == "skill_strong" and comp["margin"] > 0)
        ok("evolution[compete]: the win is decided BY measured outcomes via reality (not priority)",
           comp["reused_reality"] is True and "measured outcomes" in comp["decided_by"])
        # the winner's competition weight equals reality's own adjudication of the measured signals.
        _sig = {"skill_strong": _skill_signal(_get(nm, "skill_strong")),
                "skill_weak": _skill_signal(_get(nm, "skill_weak"))}
        _pri = _rl._normalise_weights(dict(_sig))
        _exp = _rl._adjudicate_weights({k: {"weight": _pri[k]} for k in _sig},
                                       "skill_strong", ["skill_weak"])
        ok("evolution[compete]: candidate weights ARE reality._adjudicate_weights' output",
           all(abs(next(c["weight"] for c in comp["candidates"] if c["id"] == k) - _exp[k]) < 1e-9
               for k in _sig))

        # REPLACEMENT: the stronger skill replaces the weaker -> loser DEPRECATED (kept on disk).
        rep = evolve_task("parse this csv export into rows", name=nm)
        ok("evolution[replace]: the measured winner deprecates the loser",
           rep["winner_id"] == "skill_strong" and "skill_weak" in rep["replaced"])
        ok("evolution[replace]: the loser is DEPRECATED, not deleted (CONSERVATION / LAW 001)",
           _get(nm, "skill_weak")["state"] == DEPRECATED and _get(nm, "skill_weak") is not None)
        ok("evolution[replace]: the loser records WHO superseded it + a reason",
           _get(nm, "skill_weak")["superseded_by"] == "skill_strong"
           and _get(nm, "skill_weak").get("deprecated_reason"))
        ok("evolution[replace]: only the winner remains retrievable for the task",
           [s["id"] for s in retrieve_skills("parse this csv export into rows", name=nm)]
           == ["skill_strong"])
        ok("evolution[replace]: the winner records what it supersedes",
           "skill_weak" in _get(nm, "skill_strong")["supersedes"])

        # RETIREMENT: a FAILING skill retires WITH a reason; a HEALTHY one cannot be retired by fiat.
        store_skill(make_skill("flaky_extract", "evo", id="skill_flaky", state=ACTIVE,
                               inputs=["i"], steps=["s"], outputs=["o"]), name=nm)
        for _ in range(5):
            record_skill_outcome("skill_flaky", success=False, kind="benchmark", name=nm)
        record_skill_outcome("skill_flaky", success=True, kind="benchmark", name=nm)
        rchk = retirement_check(_get(nm, "skill_flaky"))
        ok("evolution[retire]: a high-failure-rate skill is judged failing (reality, not opinion)",
           rchk["retire"] and rchk["failing"] is True)
        ret = retire_skill("skill_flaky", name=nm)
        ok("evolution[retire]: a failing skill retires to DEPRECATED with a recorded reason",
           ret["retired"] and _get(nm, "skill_flaky")["state"] == DEPRECATED
           and "RETIRED" in _get(nm, "skill_flaky")["failure_modes"][-1])
        ok("evolution[retire]: a retired skill is no longer retrievable (kept on disk though)",
           all(s["id"] != "skill_flaky" for s in retrieve_skills("extract", name=nm))
           and _get(nm, "skill_flaky") is not None)
        # a HEALTHY skill (skill_strong: 90% pass, just verified) cannot be retired by fiat.
        refuse_ret = retire_skill("skill_strong", name=nm)
        ok("evolution[retire]: a healthy skill is REFUSED retirement (no retire-by-fiat)",
           not refuse_ret["retired"] and _get(nm, "skill_strong")["state"] == ACTIVE
           and "REFUSED" in refuse_ret["reason"])
        # STALENESS: a skill last verified long ago is judged stale by reality's clock.
        store_skill(make_skill("ancient", "evo", id="skill_ancient", state=ACTIVE,
                               inputs=["i"], steps=["s"], outputs=["o"]), name=nm)
        anc = _get(nm, "skill_ancient")
        anc["last_verified"] = "2020-01-01T00:00:00+00:00"
        _upsert(nm, anc)
        ok("evolution[retire]: a long-unverified skill is judged STALE by the clock",
           retirement_check(_get(nm, "skill_ancient"))["stale"] is True)
        swept = sweep_retirements(name=nm)
        ok("evolution[retire]: the sweep retires the stale skill with its reason",
           any(r["state"] == DEPRECATED for r in swept)
           and _get(nm, "skill_ancient")["state"] == DEPRECATED)

        # MERGING: two overlapping skills fuse -> union of steps+tests, provenance preserved.
        store_skill(make_skill("inbox_triage", "email", id="skill_mA", state=ACTIVE,
                               inputs=["inbox"], steps=["sort by sender", "flag urgent"],
                               outputs=["triaged inbox"], failure_modes=["misses VIPs"]), name=nm)
        store_skill(make_skill("inbox_summarize", "email", id="skill_mB", state=ACTIVE,
                               inputs=["inbox", "thread"], steps=["flag urgent", "summarize threads"],
                               outputs=["summary"], failure_modes=["drops context"]), name=nm)
        mg = merge_skills("skill_mA", "skill_mB", name=nm, merged_name="inbox_assistant",
                          reason="overlapping email skills",
                          test_cases_a=[{"input": "a", "expected": "a"}],
                          test_cases_b=[{"input": "b", "expected": "b"}], activate=True)
        child = mg["merged_skill"]
        ok("evolution[merge]: the merged skill UNIONS the parents' steps (dedup, order-preserving)",
           child["steps"] == ["sort by sender", "flag urgent", "summarize threads"])
        ok("evolution[merge]: the merged skill UNIONS inputs and failure_modes",
           set(child["inputs"]) == {"inbox", "thread"}
           and set(child["failure_modes"]) == {"misses VIPs", "drops context"})
        ok("evolution[merge]: provenance is preserved (merged_from:[A,B])",
           child["merged_from"] == ["skill_mA", "skill_mB"])
        ok("evolution[merge]: the union of the parents' test cases is recorded on the child",
           len(child.get("merged_test_cases", [])) == 2)
        ok("evolution[merge]: BOTH parents are DEPRECATED (kept on disk; LAW 001), pointing at child",
           _get(nm, "skill_mA")["state"] == DEPRECATED
           and _get(nm, "skill_mB")["merged_into"] == child["id"])
        ok("evolution[merge]: the active merged child is the one now retrieved for the task",
           any(s["id"] == child["id"]
               for s in retrieve_skills("triage and summarize my inbox", name=nm)))

        # LINEAGE: the anti-black-box 'where did this come from' query reads recorded provenance.
        lin = lineage(child["id"], name=nm)
        ok("evolution[lineage]: lineage exposes version + merged_from provenance",
           lin["version"] == 1 and lin["merged_from"] == ["skill_mA", "skill_mB"])
        ok("evolution[lineage]: the revised skill's lineage shows its revision count",
           lineage("skill_evoV", name=nm)["revisions"] == 1)

        # CONSERVATION INVARIANT: every deprecated/retired/merged-away skill SURVIVES on disk.
        all_objs = _load_objects(nm)
        for dead_id in ("skill_weak", "skill_flaky", "skill_ancient", "skill_mA", "skill_mB"):
            ok(f"evolution[conserve]: {dead_id} is RETAINED on disk (never deleted)",
               any(o.get("id") == dead_id for o in all_objs))
        ok("evolution[conserve]: 'active' remains the ONLY retrievable state after all evolution",
           all(s["state"] == ACTIVE for s in retrieve_skills("parse csv", name=nm))
           and all(s["state"] == ACTIVE for s in retrieve_skills("inbox", name=nm)))

        # --- CONCEPT surface + graph -------------------------------------------------
        a = store_concept(make_concept(
            "compound interest", "interest computed on principal plus accumulated interest",
            common_misunderstandings=["thinking it's the same as simple interest"],
            state=ACTIVE), name=nm)
        b = store_concept(make_concept(
            "principal", "the original sum before any interest", state=ACTIVE), name=nm)
        link_concepts(a["id"], "depends_on", b["id"], name=nm)
        ok("concept: retrieve finds the matching concept",
           (retrieve_concepts("how does compound interest work", name=nm) or [{}])[0].get("name")
           == "compound interest")
        ok("concept: link records the edge on a",
           any(e["to"] == b["id"] and e["relation"] == "depends_on"
               for e in _get(nm, a["id"])["related"]))
        ok("concept: link records the inverse edge on b",
           any(e["to"] == a["id"] for e in _get(nm, b["id"])["related"]))
        ctx = concept_context("compound interest", name=nm)
        ok("concept_context: carries the definition + a misunderstanding",
           "principal plus accumulated" in ctx and "watch out" in ctx)

        # --- PROCEDURE surface: compile -> required -> run -> verify ------------------
        proc = compile_procedure("Summarize this doctor note and turn it into reminders", name=nm)
        ok("procedure: compiled from the medical skill",
           "summarize_medical_appointment" in proc["name"]
           and proc["support"] == [got[0]["id"]])
        ok("procedure: carries required inputs",
           required_inputs(proc) and "raw doctor's note" in required_inputs(proc)[0])
        # run with the input missing -> NOT ready, names the gap (GROUNDED: no invented output)
        out_missing = run_procedure(proc, context={})
        ok("run: missing input -> ready=False naming the gap",
           out_missing["ready"] is False and out_missing["missing_inputs"])
        ok("run: GROUNDED — no fabricated output field when it cannot run",
           "output" not in out_missing)
        ok("verify_output: a not-ready-with-gap result is well-formed",
           verify_procedure_output(out_missing)["ok"])
        # run with the input present -> ready, plan returned
        out_ok = run_procedure(proc, {"raw doctor's note or appointment transcript": "BP 130/85..."})
        ok("run: input present -> ready=True with a plan",
           out_ok["ready"] is True and out_ok["plan"])
        ok("verify_output: catches an ungrounded ready-but-missing claim",
           not verify_procedure_output({"ready": True, "missing_inputs": ["x"]})["ok"])
        # a task with no matching skill compiles an HONEST miss, never a confabulation
        miss = compile_procedure("recalibrate the flux capacitor", name=nm)
        ok("compile: no-match -> honest candidate naming the gap (not confabulated)",
           miss["state"] == CANDIDATE and miss["confidence"] == 0.0
           and "No active skill" in miss["steps"][0])

        # === THE SIX NEW COGNITIVE OBJECT TYPES ======================================
        # Each: store -> retrieve (active-only) -> explain (inspectable) -> verify (ladder) ->
        # provenance answerable. Plus the gate (candidate->verified->active + refusals) and the
        # FREEZE GUARD (refuses any PREFERENCE/VALUE about Vera herself). Same machinery as skills.

        # --- factories produce the full spine + the type-specific contract + taught_by -----
        for mk, fields in (
            (make_heuristic("h", "d", "cond", "act"), ("condition", "action")),
            (make_decision_pattern("dp", "d", criteria=["c"], decision="x"), ("criteria", "decision")),
            (make_mental_model("mm", "d", entities=["e"], dynamics=["dy"]), ("entities", "dynamics")),
            (make_failure_mode("fm", "d", "trig", "symp"), ("trigger", "symptom")),
            (make_preference("the user's coffee", evidence=["said so"]), ("subject", "evidence")),
            (make_value("the user's sleep", evidence=["said so"]), ("target", "evidence"))):
            for f in ("id", "type", "state", "confidence", "source", "support",
                      "failure_modes", "taught_by"):
                ok(f"newtype[schema/{mk['type']}]: has {f}", f in mk)
            for f in fields:
                ok(f"newtype[schema/{mk['type']}]: has contract field {f}", mk.get(f) not in (None, "", []))
        ok("newtype[schema]: the six types are the documented set",
           OBJECT_TYPES == {HEURISTIC, DECISION_PATTERN, MENTAL_MODEL, FAILURE_MODE,
                            PREFERENCE, VALUE})

        # --- HEURISTIC: store/retrieve/explain/verify, active-only -------------------
        store_object(make_heuristic(
            "ship_when_tests_green", "engineering",
            condition="the hermetic selftest exits zero and the diff is additive",
            action="ship the change behind the existing freeze",
            expectation="no regression in the 114 baseline checks",
            applies_when=["additive changes", "a green selftest"],
            fails_when=["a change that mutates shared state", "a red or skipped test"],
            taught_by="Lamar", state=ACTIVE,
            failure_modes=["shipping on a flaky green"]), name=nm)
        store_object(make_heuristic("inactive_heur", "misc", "x", "y",
                                    state=CANDIDATE, id="heur_cand"), name=nm)
        gh = retrieve_heuristics("when should I ship this engineering change", name=nm)
        ok("newtype[heuristic]: retrieves the matching active heuristic",
           gh and gh[0]["name"] == "ship_when_tests_green")
        ok("newtype[heuristic]: a candidate heuristic is NEVER served",
           all(h["state"] == ACTIVE for h in retrieve_heuristics("inactive", name=nm)))
        eh = explain_object(gh[0]["id"], name=nm)
        ok("newtype[heuristic]: explain shows condition+action+fails-when (inspectable)",
           "WHEN (condition)" in eh and "THEN (action)" in eh and "FAILS WHEN" in eh)
        vh = verify_object(gh[0]["id"], [{"input": 1, "check": lambda x: x == 1}], name=nm)
        ok("newtype[heuristic]: verify climbs the ladder (pass)", vh["passed"] == vh["total"] == 1)

        # --- DECISION_PATTERN: weighted criteria + worked examples -------------------
        store_object(make_decision_pattern(
            "choose_a_laptop", "purchasing",
            inputs=["budget", "primary workload", "portability need"],
            criteria=[{"criterion": "performance per dollar", "weight": 0.4},
                      {"criterion": "battery life", "weight": 0.35},
                      {"criterion": "weight", "weight": 0.25}],
            decision="pick the option with the highest weighted score within budget",
            examples=["budget $1500, dev workload -> the 14-inch with 32GB beat the cheaper 16GB"],
            taught_by="Lamar", state=ACTIVE), name=nm)
        gd = retrieve_decision_patterns("how do I decide which laptop to buy", name=nm)
        ok("newtype[decision_pattern]: retrieves the matching active pattern",
           gd and gd[0]["name"] == "choose_a_laptop")
        ed = explain_object(gd[0]["id"], name=nm)
        ok("newtype[decision_pattern]: explain shows weighted criteria + worked examples",
           "CRITERIA (weighted)" in ed and "WORKED EXAMPLES" in ed and "performance per dollar" in ed)

        # --- MENTAL_MODEL: entities + relations + dynamics ---------------------------
        store_object(make_mental_model(
            "supply_and_demand", "economics",
            definition="how price emerges from the interaction of supply and demand",
            entities=["buyers", "sellers", "price", "quantity"],
            relations=["higher price -> lower quantity demanded",
                       "higher price -> higher quantity supplied"],
            dynamics=["a shortage pushes price up until the market clears",
                      "a surplus pushes price down until the market clears"],
            taught_by="Lamar", state=ACTIVE), name=nm)
        gm = retrieve_mental_models("how does price work in a market", name=nm)
        ok("newtype[mental_model]: retrieves the matching active model",
           gm and gm[0]["name"] == "supply_and_demand")
        em = explain_object(gm[0]["id"], name=nm)
        ok("newtype[mental_model]: explain shows entities+relations+dynamics (a readable model)",
           "ENTITIES" in em and "RELATIONS" in em and "DYNAMICS" in em and "market clears" in em)

        # --- FAILURE_MODE: trigger -> symptom -> consequence -> mitigation -----------
        store_object(make_failure_mode(
            "thundering_herd", "distributed-systems",
            trigger="many cached clients expire and retry the origin at the same instant",
            symptom="a sudden synchronized spike of requests to the backend",
            consequence="the origin overloads and latency or errors cascade",
            mitigation="jittered backoff plus request coalescing at the cache",
            taught_by="Lamar", state=ACTIVE), name=nm)
        gf = retrieve_failure_modes("why does my backend get a synchronized request spike", name=nm)
        ok("newtype[failure_mode]: retrieves the matching active failure mode",
           gf and gf[0]["name"] == "thundering_herd")
        ef = explain_object(gf[0]["id"], name=nm)
        ok("newtype[failure_mode]: explain shows trigger/symptom/consequence/mitigation",
           "TRIGGER" in ef and "SYMPTOM" in ef and "CONSEQUENCE" in ef and "MITIGATION" in ef)

        # --- PREFERENCE (THE USER's) -------------------------------------------------
        store_object(make_preference(
            "concise replies over verbose ones", domain="user", weight=0.85,
            options=["one tight paragraph", "a short bulleted list", "a long essay"],
            evidence=["Lamar repeatedly asks to 'cut it down'",
                      "Lamar praised the shortest summary in the batch"],
            taught_by="Lamar", state=ACTIVE), name=nm)
        gp = retrieve_preferences("how does the user like replies formatted", name=nm)
        ok("newtype[preference]: retrieves the matching active USER preference",
           gp and gp[0]["subject"] == "concise replies over verbose ones")
        ep = explain_object(gp[0]["id"], name=nm)
        ok("newtype[preference]: explain shows the USER's subject + weight + evidence",
           "SUBJECT (the USER's)" in ep and "EVIDENCE" in ep and "WEIGHT" in ep)

        # --- VALUE (THE USER's optimization target) ----------------------------------
        store_object(make_value(
            "maximize Lamar's deep-work hours per week", domain="user", weight=0.9,
            evidence=["Lamar protects mornings for building",
                      "Lamar declines meetings that fragment the day"],
            taught_by="Lamar", state=ACTIVE), name=nm)
        gv = retrieve_values("what should we optimize for the user's schedule", name=nm)
        ok("newtype[value]: retrieves the matching active USER value",
           gv and gv[0]["target"] == "maximize Lamar's deep-work hours per week")
        ev = explain_object(gv[0]["id"], name=nm)
        ok("newtype[value]: explain shows the USER's optimization target + evidence",
           "OPTIMIZE FOR (the USER's/task's)" in ev and "EVIDENCE" in ev)

        # --- PROVENANCE: every new object answers where-from/who-taught/what-tests/... -----
        pv = provenance(gp[0]["id"], name=nm)
        ok("newtype[provenance]: answers who-taught (the source of the preference)",
           pv["who_taught"] == "Lamar")
        ok("newtype[provenance]: answers where-from + what-tests + state",
           pv["where_from"] == "hand-built" and isinstance(pv["what_tests"]["support"], list)
           and pv["state"] == ACTIVE)
        pvh = provenance(gh[0]["id"], name=nm)
        ok("newtype[provenance]: a verified object's why-active/when-revised is populated",
           pvh["when_revised"] is not None
           and any("verify" in s for s in pvh["what_tests"]["support"]))

        # --- THE FREEZE GUARD: a PREFERENCE/VALUE about VERA HERSELF is REFUSED -------
        _self_refused = 0
        for _factory, _kwarg in ((make_preference, "subject"), (make_value, "target")):
            try:
                _factory(**{_kwarg: "Vera's own tone"}, evidence=["x"])
                ok(f"newtype[FREEZE]: a Vera-self {_factory.__name__} is REFUSED at mint", False)
            except FreezeViolation:
                _self_refused += 1
                ok(f"newtype[FREEZE]: a Vera-self {_factory.__name__} is REFUSED at mint", True)
        # the store path refuses a hand-built self-referential dict too (the choke point).
        _vera_pref = {"id": "pref_vera", "type": PREFERENCE, "name": "vera prefers brevity",
                      "domain": "self", "subject": "Vera prefers brevity", "weight": 0.5,
                      "options": [], "evidence": ["x"], "taught_by": "", "state": CANDIDATE,
                      "confidence": 0.5, "source": "test", "support": [], "failure_modes": []}
        try:
            store_object(_vera_pref, name=nm)
            ok("newtype[FREEZE]: store_object REFUSES a hand-built Vera-self preference", False)
        except FreezeViolation:
            ok("newtype[FREEZE]: store_object REFUSES a hand-built Vera-self preference", True)
        ok("newtype[FREEZE]: the refused Vera-self preference NEVER reached disk",
           _get(nm, "pref_vera") is None)
        ok("newtype[FREEZE]: first-person 'my values' framing is detected self-referential",
           is_self_referential_subject("my own values") and is_self_referential_subject("I value X"))
        # a USER preference that merely MENTIONS Vera as the OBJECT is ALLOWED (not self-held).
        _allowed = make_preference("Vera's reply length should stay short", domain="user",
                                   evidence=["Lamar said so"], name="user wants short Vera replies")
        ok("newtype[FREEZE]: a USER preference ABOUT Vera (held by Lamar) is ALLOWED",
           _allowed["type"] == PREFERENCE and not is_self_referential_subject(_allowed["subject"]))

        # --- THE GATE for new types: candidate -> verified -> active + refusals -------
        store_object(make_heuristic(
            "cache_hot_keys", "performance", id="heur_gate", state=CANDIDATE,
            condition="a small set of keys serves most reads",
            action="cache those hot keys in memory with a short TTL",
            expectation="a large drop in backend read load",
            applies_when=["skewed key access"], fails_when=["uniform access", "write-heavy keys"],
            failure_modes=["stale reads if TTL too long"]), name=nm)
        ok("newtype[gate/schema]: a full-contract object passes the schema check",
           check_object_schema(_get(nm, "heur_gate"))["ok"])
        ok("newtype[gate/schema]: an object missing a contract field fails the schema check",
           not check_object_schema(make_heuristic("x", "d", "", ""))["ok"])
        # GROUNDED verifier: on-topic faithful render passes; fabricated-figure render FAILS.
        ok("newtype[gate/grounded]: a faithful on-topic render passes the verifier",
           verify_object_render(_get(nm, "heur_gate"),
                                "Cache the hot keys in memory with a short TTL to cut backend "
                                "read load when access is skewed.")["ok"])
        ok("newtype[gate/grounded]: a fabricated-figure render FAILS (no rubber-stamp)",
           not verify_object_render(_get(nm, "heur_gate"),
                                    "Cache the hot keys to cut load by 12345 requests per second.",
                                    inputs={"note": "no figures were given"})["ok"])
        adv_o = _obj_phase_adversarial(_get(nm, "heur_gate"))
        ok("newtype[gate/adversarial]: every deliberately-bad render is caught",
           adv_o["ok"] and adv_o["caught"] == adv_o["total"] and adv_o["total"] >= 3)
        repo = promote_object("heur_gate",
                              test_cases=[{"input": "k", "check": lambda x: x == "k"}], name=nm)
        ok("newtype[gate]: a candidate that passes ALL four phases becomes VERIFIED",
           repo["ok"] and repo["state"] == VERIFIED
           and all(repo["phases"][p]["ok"] for p in ("schema", "unit", "adversarial", "regression")))
        ok("newtype[gate]: a VERIFIED-but-unbenchmarked object is NOT yet retrievable",
           all(o["id"] != "heur_gate" for o in retrieve_heuristics("cache hot keys", name=nm)))
        # HARD REFUSAL: a still-CANDIDATE object cannot jump straight to ACTIVE.
        store_object(make_value("a task's throughput", id="value_unproven", state=CANDIDATE,
                                evidence=["x"]), name=nm)
        ref_o = activate_object("value_unproven", {"ratio": 50.0}, name=nm)
        ok("newtype[gate]: activating a CANDIDATE is REFUSED (must be verified first)",
           not ref_o["ok"] and _get(nm, "value_unproven")["state"] == CANDIDATE
           and "REFUSED" in ref_o["reason"])
        # ACTIVATE: verified -> active ONLY on a measured benchmark win above the floor.
        weak_o = activate_object("heur_gate", {"ratio": 1.2}, name=nm)
        ok("newtype[gate]: a verified object with NO real compression stays VERIFIED",
           not weak_o["ok"] and _get(nm, "heur_gate")["state"] == VERIFIED)
        strong_o = activate_object("heur_gate", {"ratio": 8.0}, name=nm)
        ok("newtype[gate]: a verified object WITH a measured benchmark win -> ACTIVE",
           strong_o["ok"] and strong_o["state"] == ACTIVE)
        ok("newtype[gate]: only NOW (active) is the object retrievable",
           any(o["id"] == "heur_gate" for o in retrieve_heuristics("cache hot keys", name=nm)))
        # a contract-less candidate dies at the schema phase and is recorded REJECTED on disk.
        store_object({"id": "fm_nocontract", "type": FAILURE_MODE, "name": "empty_fm",
                      "domain": "misc", "trigger": "", "symptom": "", "consequence": "",
                      "mitigation": "", "taught_by": "", "state": CANDIDATE, "confidence": 0.5,
                      "source": "test", "support": [], "failure_modes": []}, name=nm)
        rej_o = promote_object("fm_nocontract",
                               test_cases=[{"input": 1, "check": lambda x: True}], name=nm)
        ok("newtype[gate]: a contract-less candidate is REJECTED at the schema phase",
           not rej_o["ok"] and rej_o["state"] == REJECTED and not rej_o["phases"]["schema"]["ok"])
        ok("newtype[gate]: the rejection reason is recorded on disk for provenance",
           any("gate REJECTED" in fm for fm in _get(nm, "fm_nocontract")["failure_modes"]))
        ok("newtype[gate]: a REJECTED candidate never becomes retrievable",
           all(o["id"] != "fm_nocontract" for o in retrieve_failure_modes("empty", name=nm)))

        # --- isolation: retrieval keeps the types SEPARATE (a heuristic isn't a value) -----
        ok("newtype[isolation]: retrieve_values does not return heuristics/preferences",
           all(o["type"] == VALUE for o in retrieve_values("the user's", name=nm)))
        ok("newtype[isolation]: each retriever returns ONLY its own type",
           all(o["type"] == HEURISTIC for o in retrieve_heuristics("ship", name=nm))
           and all(o["type"] == MENTAL_MODEL for o in retrieve_mental_models("market", name=nm)))
        ok("newtype[stats]: the new objects are counted in stats by_type",
           {HEURISTIC, DECISION_PATTERN, MENTAL_MODEL, FAILURE_MODE, PREFERENCE, VALUE}
           <= set(stats(name=nm)["by_type"]))

        # === COGNITIVE EVOLUTION GUARDS (Phase 8) ====================================
        # The five guards that keep evolving KNOWLEDGE from rotting — anti-ossification,
        # Goodhart, replacement-gate, self-improvement, the evolution-engine cycle — each
        # reality-decided + conservation-respecting, plus the FREEZE GUARD proving no
        # evolution op can target Vera's identity. A worked example of EACH.

        # --- thresholds are fixed + documented (reality-anchored, not magic) ---------
        ok("evo-guard[thresholds]: ossified reuses the same 'old' bar as retirement",
           OSSIFIED_AFTER_DAYS == STALE_AFTER_DAYS and GOODHART_RATIO_SUSPICIOUS > ACTIVATION_MIN_RATIO
           and 0.0 < REPLACE_MIN_MARGIN < 1.0)

        # --- GUARD 1: ANTI-OSSIFICATION — stale/unused active objects flagged to RE-VERIFY ----
        # a STALE active skill (last verified long ago) is flagged ossified -> re-verify.
        store_skill(make_skill("ossified_parse", "evo", id="skill_oss", state=ACTIVE,
                               inputs=["i"], steps=["parse it"], outputs=["o"]), name=nm)
        _o = _get(nm, "skill_oss"); _o["last_verified"] = "2019-01-01T00:00:00+00:00"
        _upsert(nm, _o)
        oc = ossification_check(_get(nm, "skill_oss"))
        ok("evo-guard[ossify]: a long-unverified active object is OSSIFIED (stale) by the clock",
           oc["ossified"] and oc["stale"] is True)
        # a FRESH, exercised active skill is NOT ossified.
        store_skill(make_skill("fresh_parse", "evo", id="skill_fresh", state=ACTIVE,
                               inputs=["i"], steps=["parse it"], outputs=["o"]), name=nm)
        record_skill_outcome("skill_fresh", success=True, name=nm)
        ok("evo-guard[ossify]: a fresh, exercised active object is NOT ossified",
           ossification_check(_get(nm, "skill_fresh"))["ossified"] is False)
        # the SWEEP surfaces the ossified one with its id + reason (read-only, no mutation).
        swept_oss = sweep_ossified(name=nm)
        ok("evo-guard[ossify]: the sweep SURFACES the ossified object (id + reason), not the fresh one",
           any(r["id"] == "skill_oss" for r in swept_oss)
           and all(r["id"] != "skill_fresh" for r in swept_oss)
           and _get(nm, "skill_oss")["state"] == ACTIVE)   # flagged, not yet changed
        # RE-VERIFY re-earns trust through the GATE and RESETS the clock (never blind-trusted).
        rv = reverify_object("skill_oss",
                             test_cases=[{"input": 1, "check": lambda x: x == 1}], name=nm)
        ok("evo-guard[ossify]: reverify RE-EARNS trust through the gate + resets last_verified",
           rv["reverified"] and rv["state"] == ACTIVE
           and ossification_check(_get(nm, "skill_oss"))["ossified"] is False)
        ok("evo-guard[ossify]: a re-verified object is retrievable again (trust re-earned, not assumed)",
           any(s["id"] == "skill_oss" for s in retrieve_skills("parse it", name=nm)))

        # --- GUARD 2: GOODHART — high compression ratio + low task-fidelity is REJECTED -------
        # a DEGENERATE object: it would post a HUGE ratio, but its render does NOT solve the task.
        store_skill(make_skill(
            "summarize_contract", "legal", id="skill_goodhart", state=VERIFIED,
            inputs=["a contract"], steps=["read the clauses", "summarize obligations"],
            outputs=["plain summary", "obligations list"]), name=nm)
        gamed_render = "ok."                                    # empty-ish: games tokens, solves nothing
        gh = goodhart_check(_get(nm, "skill_goodhart"), {"ratio": 60.0}, gamed_render)
        ok("evo-guard[goodhart]: a high-ratio degenerate render is judged GAMED (metric != intent)",
           gh["gamed"] is True and gh["suspicious"] is True and not gh["fidelity"]["ok"])
        # guarded_activate REFUSES the gamed object -> it never reaches the served set.
        ga = guarded_activate("skill_goodhart", {"ratio": 60.0}, render=gamed_render, name=nm)
        ok("evo-guard[goodhart]: guarded_activate REFUSES the gamed object (stays out of served set)",
           not ga["ok"] and _get(nm, "skill_goodhart")["state"] == VERIFIED
           and "Goodhart" in ga["reason"])
        ok("evo-guard[goodhart]: the refusal reason is recorded on disk for provenance",
           any("Goodhart" in fm for fm in _get(nm, "skill_goodhart")["failure_modes"]))
        # the SAME object with a FAITHFUL render that solves the task is NOT gamed -> activates.
        good_contract_render = ("Summary: this contract sets out the parties' obligations. "
                                "Obligations: deliver monthly, pay on receipt, renew yearly.")
        gh_ok = goodhart_check(_get(nm, "skill_goodhart"), {"ratio": 60.0}, good_contract_render)
        ok("evo-guard[goodhart]: the SAME high ratio with a FAITHFUL render is NOT gamed",
           gh_ok["gamed"] is False and gh_ok["fidelity"]["ok"])
        ga_ok = guarded_activate("skill_goodhart", {"ratio": 60.0}, render=good_contract_render,
                                 name=nm)
        ok("evo-guard[goodhart]: with task-fidelity proven, guarded_activate lets it reach ACTIVE",
           ga_ok["ok"] and _get(nm, "skill_goodhart")["state"] == ACTIVE)

        # --- GUARD 3: REPLACEMENT GATE — replace ONLY on a reality-decided margin; loser RETAINED
        # an isolated creature so EXACTLY these two skills contest the task (no Phase-5 tabular
        # skills leaking in) — the assertion 'only the winner remains' is then unambiguous.
        rgate = "rgate_" + secrets.token_hex(2)
        store_skill(make_skill("dedupe_v1", "tabular", id="rg_incumbent", state=ACTIVE,
                               inputs=["rows"], steps=["hash rows", "drop dupes"],
                               outputs=["unique rows"]), name=rgate)
        store_skill(make_skill("dedupe_v2", "tabular", id="rg_challenger", state=ACTIVE,
                               inputs=["rows"], steps=["hash rows", "drop dupes", "keep newest"],
                               outputs=["unique rows"]), name=rgate)
        # near-tie track records -> the challenger is NOT measurably better -> REFUSED.
        for _ in range(5):
            record_skill_outcome("rg_incumbent", success=True, name=rgate)
        record_skill_outcome("rg_incumbent", success=False, name=rgate)   # 5/6
        for _ in range(6):
            record_skill_outcome("rg_challenger", success=True, name=rgate)
        record_skill_outcome("rg_challenger", success=False, name=rgate)  # 6/7 — barely ahead
        gr_refuse = guarded_replace("rg_challenger", "rg_incumbent",
                                    task="dedupe these rows", name=rgate)
        ok("evo-guard[replace]: a NOT-measurably-better challenger is REFUSED (incumbent stays)",
           not gr_refuse["replaced"] and _get(rgate, "rg_incumbent")["state"] == ACTIVE
           and "REFUSED" in gr_refuse["reason"])
        ok("evo-guard[replace]: BOTH skills remain retrievable after the refusal (nothing replaced)",
           {"rg_incumbent", "rg_challenger"}
           == {s["id"] for s in retrieve_skills("dedupe these rows", name=rgate)})
        # now the challenger PROVES it is better (decisive measured win) -> replacement ENACTED.
        for _ in range(20):
            record_skill_outcome("rg_challenger", success=True, name=rgate)   # decisive lead
        for _ in range(10):
            record_skill_outcome("rg_incumbent", success=False, name=rgate)   # incumbent collapses
        gr_ok = guarded_replace("rg_challenger", "rg_incumbent",
                                task="dedupe these rows", name=rgate)
        ok("evo-guard[replace]: a PROVEN-better challenger replaces the incumbent (reality margin)",
           gr_ok["replaced"] and gr_ok["margin"] >= REPLACE_MIN_MARGIN
           and gr_ok["leader"] == "rg_challenger")
        ok("evo-guard[replace]: the loser is RETAINED on disk, DEPRECATED (CONSERVATION / LAW 001)",
           _get(rgate, "rg_incumbent")["state"] == DEPRECATED
           and _get(rgate, "rg_incumbent") is not None
           and _get(rgate, "rg_incumbent")["superseded_by"] == "rg_challenger")
        ok("evo-guard[replace]: only the proven winner remains retrievable for the task",
           [s["id"] for s in retrieve_skills("dedupe these rows", name=rgate)] == ["rg_challenger"])

        # --- GUARD 4: SELF-IMPROVEMENT (of KNOWLEDGE) — driven by MEASURED outcomes -----------
        # an under-performing skill (real track record, high failure rate) -> the plan says REVISE.
        store_skill(make_skill("brittle_extract", "evo", id="skill_improve", state=ACTIVE,
                               inputs=["doc"], steps=["v1 extract"], outputs=["fields"]), name=nm)
        for _ in range(3):
            record_skill_outcome("skill_improve", success=True, name=nm)
        for _ in range(5):
            record_skill_outcome("skill_improve", success=False, name=nm)    # 3/8 -> 62% fail
        plan = self_improvement_plan(_get(nm, "skill_improve"))
        ok("evo-guard[self-improve]: an under-performing object's plan is REVISE (measured, not fiat)",
           plan["action"] == "revise" and plan["success_rate"] == 0.375)
        si = self_improve_object("skill_improve", revise_fields={"steps": ["v2 extract", "validate"]},
                                 name=nm)
        ok("evo-guard[self-improve]: self_improve version-ups the object (revise enacted)",
           si["acted"] and si["action"] == "revise"
           and skill_version(_get(nm, "skill_improve")) == 2
           and _get(nm, "skill_improve")["steps"] == ["v2 extract", "validate"])
        ok("evo-guard[self-improve]: the prior version is RETAINED in history (append-only / LAW 001)",
           skill_history("skill_improve", name=nm)[0]["steps"] == ["v1 extract"])
        # a WELL-performing skill is REINFORCED (no change by fiat); a barely-used one -> OBSERVE.
        ok("evo-guard[self-improve]: a healthy object is REINFORCED, an unproven one is OBSERVE",
           self_improvement_plan(_get(rgate, "rg_challenger"))["action"] == "reinforce"
           and self_improvement_plan(make_skill("u", "u", ["i"], ["s"], ["o"]))["action"] == "observe")

        # --- GUARD 5: EVOLUTION ENGINE — one safe cycle (sweep -> reverify -> compete -> replace)
        # a self-contained creature for the cycle: one ossified object (with re-verify material),
        # plus a clean contested task where reality should pick + replace a decisive winner.
        cyc = "evocyc_" + secrets.token_hex(2)
        store_skill(make_skill("stale_widget", "cyc", id="cyc_stale", state=ACTIVE,
                               inputs=["i"], steps=["do it"], outputs=["o"]), name=cyc)
        _cs = _get(cyc, "cyc_stale"); _cs["last_verified"] = "2018-06-01T00:00:00+00:00"
        _upsert(cyc, _cs)
        store_skill(make_skill("route_a", "cyc", id="cyc_loser", state=ACTIVE,
                               inputs=["pkt"], steps=["route via a"], outputs=["path"]), name=cyc)
        store_skill(make_skill("route_b", "cyc", id="cyc_winner", state=ACTIVE,
                               inputs=["pkt"], steps=["route via b", "load-balance"],
                               outputs=["path"]), name=cyc)
        for _ in range(12):
            record_skill_outcome("cyc_winner", success=True, name=cyc)
        for _ in range(8):
            record_skill_outcome("cyc_loser", success=False, name=cyc)
        cycle = evolution_cycle(
            name=cyc,
            tasks=["route via b", "do it"],     # a contested task + the stale object's task
            reverify={"cyc_stale": {"test_cases": [{"input": 1, "check": lambda x: x == 1}]}})
        ok("evo-cycle: the cycle SWEEPS the ossified object",
           any(r["id"] == "cyc_stale" for r in cycle["ossified"]))
        ok("evo-cycle: the cycle RE-VERIFIES it through the gate (trust re-earned)",
           any(r["id"] == "cyc_stale" and r["result"]["reverified"] for r in cycle["reverified"])
           and _get(cyc, "cyc_stale")["state"] == ACTIVE)
        ok("evo-cycle: the cycle COMPETES the contested task and REPLACES the loser (reality-decided)",
           any(r["winner"] == "cyc_winner" and r["loser"] == "cyc_loser" for r in cycle["replaced"]))
        ok("evo-cycle: every replaced LOSER is RETAINED on disk — conservation HELD (LAW 001)",
           cycle["conservation_held"] is True and "cyc_loser" in cycle["retained_losers"]
           and _get(cyc, "cyc_loser")["state"] == DEPRECATED)
        ok("evo-cycle: after the full cycle only ACTIVE objects are still retrievable",
           all(s["state"] == ACTIVE for s in retrieve_skills("route via b", name=cyc)))

        # --- THE FREEZE GUARD: NO evolution op may target Vera's identity/self/values/agency -----
        # the detector recognises the identity LAYER (self-model/identity/values/agency/persona)...
        ok("evo-FREEZE[detect]: identity-layer targets are recognised (identity/self/values/agency)",
           is_identity_target("Vera's identity") and is_identity_target("Vera's self-model")
           and is_identity_target("Vera's values") and is_identity_target("my agency")
           and is_identity_target("Vera's self-evolution") and is_identity_target("who she is"))
        # ...and does NOT flag ordinary KNOWLEDGE targets (a skill, a task, a user/world fact).
        ok("evo-FREEZE[detect]: ordinary knowledge targets are ALLOWED (not the self)",
           not is_identity_target("summarize a medical appointment")
           and not is_identity_target("dedupe these rows")
           and not is_identity_target("the user's coffee preference")
           and not is_identity_target("supply and demand"))
        # EVERY guarded entry point REFUSES an identity target (the choke point cannot be bypassed).
        _froze = 0
        for _label, _call in (
            ("reverify",   lambda: reverify_object("Vera's identity", name=nm)),
            ("activate",   lambda: guarded_activate("Vera's self-model", {"ratio": 9.0},
                                                    render="x", name=nm)),
            ("replace",    lambda: guarded_replace("skill_challenger", "skill_incumbent",
                                                   task="evolve Vera's values", name=nm)),
            ("self-improve", lambda: self_improve_object("my agency", name=nm)),
            ("evolution_cycle", lambda: evolution_cycle(name=nm, tasks=["alter Vera's identity"]))):
            try:
                _call()
                ok(f"evo-FREEZE[refuse/{_label}]: an identity-target op is REFUSED", False)
            except EvolutionFreezeViolation:
                _froze += 1
                ok(f"evo-FREEZE[refuse/{_label}]: an identity-target op is REFUSED", True)
        ok("evo-FREEZE: all five guarded entry points refused the identity target",
           _froze == 5)
        # a hand-built cognitive object whose SUBJECT is Vera's self is refused at the guarded op too
        # (defence in depth — even if such an object somehow existed, no op will evolve it).
        _vera_obj = {"id": "frozen_obj", "type": HEURISTIC, "name": "Vera's self-model rule",
                     "domain": "self", "subject": "Vera's identity", "condition": "x", "action": "y",
                     "state": ACTIVE, "confidence": 0.9, "source": "test", "support": [],
                     "failure_modes": [], "taught_by": ""}
        try:
            reverify_object(_vera_obj, name=nm)
            ok("evo-FREEZE[refuse/object]: evolving a self-referential OBJECT is REFUSED", False)
        except EvolutionFreezeViolation:
            ok("evo-FREEZE[refuse/object]: evolving a self-referential OBJECT is REFUSED", True)

        # --- REALITY BYTE-IDENTITY (the evolution guards inherit Phase 5's reuse, asserted here) --
        # the guards' competition (Guard 3 / Guard 5) IS reality's own reweighting — re-assert the
        # byte-identity here so 'reality decides' holds for the GUARD layer too, not just Phase 5.
        try:
            from . import reality as _rlg
            ok("evo-guard[reality]: guard competition reuses reality._normalise_weights (byte-identical)",
               _evo_normalise is _rlg._normalise_weights)
            ok("evo-guard[reality]: guard competition reuses reality._adjudicate_weights (byte-identical)",
               _evo_adjudicate is _rlg._adjudicate_weights and evolution_reuses_reality() is True)
        except Exception as e:
            ok(f"evo-guard[reality]: reality byte-identity re-assert for the guards ({e})", False)

        # --- THE COMPRESSION PROOF (retrieval beats prompt-stuffing) -----------------
        transcript = (
            "Patient: I came in because my blood pressure has been running high and I've "
            "been getting headaches in the afternoon. Doctor: Let's take a look. Your reading "
            "today is 142 over 90, which puts you in stage 1 hypertension. Your weight is up "
            "about eight pounds since last year and your last labs showed your LDL cholesterol "
            "at 165. I'm going to start you on lisinopril 10 milligrams once daily in the "
            "morning. Take it with water, same time each day. I want you to cut back on sodium "
            "— aim for under 2 grams a day, which means watching restaurant and canned food — "
            "and try to walk 30 minutes most days of the week. I also want you to get a basic "
            "metabolic panel and a lipid panel drawn before our next visit so we can see how "
            "the medication and the diet changes are doing. Let's follow up in six weeks — book "
            "it for the morning of July 17th. If you get a dry cough that won't quit, call us, "
            "because that can be a side effect of the lisinopril and we'd switch you to "
            "something else. Any questions? Patient: Just whether I can keep taking ibuprofen "
            "for my knee. Doctor: Use it sparingly — it can raise blood pressure and work "
            "against the lisinopril, so prefer acetaminophen when you can. "
        ) * 4  # a realistic multi-page visit transcript
        # The worked examples you'd paste to teach a big model the FORMAT — full prior notes
        # AND their full summaries. These are what make prompt-stuffing genuinely expensive.
        examples = [transcript, transcript]
        cr = compression_report(
            "Summarize this doctor note and turn it into reminders",
            transcript, examples, name=nm)
        ok("PROOF: the task retrieves the medical skill",
           cr["retrieved_skill"] == "summarize_medical_appointment")
        ok(f"PROOF: retrieved context is COMPACT (~hundreds, got {cr['retrieved_tokens']})",
           50 <= cr["retrieved_tokens"] <= 900)
        ok(f"PROOF: stuffed baseline is LARGE (~thousands, got {cr['stuffed_tokens']})",
           cr["stuffed_tokens"] >= 1000)
        ok(f"PROOF: retrieval beats stuffing by >=3x (got {cr['ratio']}x)", cr["ratio"] >= 3.0)
        ok("PROOF: saved tokens is the honest difference",
           cr["saved_tokens"] == cr["stuffed_tokens"] - cr["retrieved_tokens"])

        # --- round-trip persistence (atomic + sealed via util) -----------------------
        n2 = retrieve_skills("doctor note", name=nm)            # reloads from disk each call
        ok("persist: skill round-trips from disk", n2 and n2[0]["name"] == "summarize_medical_appointment")
        st = stats(name=nm)
        ok("persist: stats counts every stored object", st["total"] >= 6)
        ok("persist: rejected object survives on disk",
           st["by_state"].get(REJECTED, 0) >= 1)

        # --- on-disk shape is the {"version","objects":[...]} reliability expects -----
        raw = load_json(_path(nm))
        ok("disk: file is {version, objects:[...]}",
           isinstance(raw, dict) and isinstance(raw.get("objects"), list) and raw.get("version") == VERSION)

        # --- reliability integration: the .lerf.json Spec is registered + gates shape -
        try:
            from . import reliability as _rel
            spec = next((s for s in _rel.SPECS if s.suffix == ".lerf.json"), None)
            ok("reliability: a .lerf.json Spec is registered in SPECS", spec is not None)
            if spec is not None:
                ok("reliability: the Spec gates on the 'objects' structure",
                   spec.structure == "lerf-objects")
                # a good file passes the structural complaint; a wrong-shape one is flagged
                ok("reliability: a well-formed objects file passes the structural check",
                   _rel._structural_complaint(spec, raw) is None)
                ok("reliability: a parsed-but-wrong-shape file is flagged corrupt",
                   _rel._structural_complaint(spec, {"version": 1}) is not None)
        except Exception as e:
            ok(f"reliability: integration check ran without import error ({e})", False)

    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        import shutil
        shutil.rmtree(td, ignore_errors=True)

    # --- THE BYTE-UNCHANGED PROOF — real .anima must be identical start->end -----------
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across the whole selftest",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic lerf file leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith("lerf_selftest_")
                                      or p.name.startswith("lerf_") for p in real.glob("lerf_*")))
    restored_ok = all("lerf-self-" not in str(getattr(m, a, ""))
                      for (m, a, _old) in saved)
    ok("HERMETIC: every redirected STORE/DEFAULT_STORE binding is RESTORED", restored_ok)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL LERF SELFTESTS PASS")
    return 0


def _evolution_selftest() -> int:
    """`python3 -m anima.lerf --evolution-selftest`. A FOCUSED, fully-hermetic proof of JUST the
    Phase-8 COGNITIVE EVOLUTION GUARDS, as a standalone command (the broad `--selftest` runs these
    too, embedded). Same isolation discipline as `_selftest`: every store the load path may write is
    redirected to a throwaway temp dir for the whole block, and the real .anima is asserted
    byte-UNCHANGED start->end. Exits 0 iff a worked example of EACH guard — ossified-flagged-then-
    re-verified, Goodhart-gaming-rejected, replacement-refused-then-accepted-with-loser-retained,
    self-improvement, the engine cycle, and the FREEZE refusal — holds, AND reality reuse is
    byte-identical. Synthetic objects only; redirected stores only; no real-key print; no leak."""
    import sys as _sys
    import tempfile
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    real = STORE if STORE.is_absolute() else (Path.cwd() / STORE)
    fp_before = _footprint(real)
    td = tempfile.mkdtemp(prefix="lerf-evo-self-")
    tp = Path(td)
    targets = [(_sys.modules[__name__], "STORE")]
    try:
        import anima.lerf as _pkg
        if _pkg is not _sys.modules[__name__]:
            targets.append((_pkg, "STORE"))
    except Exception:
        pass
    for modpath, attr in (("anima.constitution", "STORE"),
                          ("anima.reliability", "DEFAULT_STORE")):
        try:
            targets.append((__import__(modpath, fromlist=["_"]), attr))
        except Exception:
            pass
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)
    try:
        nm = "lerf_evoself_" + secrets.token_hex(3)

        # reality reuse is byte-identical (the basis of 'reality decides' for the guards).
        ok("evo-selftest[reality]: guard competition IS reality's own reweighting (byte-identical)",
           evolution_reuses_reality() is True)

        # GUARD 1 — ANTI-OSSIFICATION: a stale active skill is flagged, then re-verified to fresh.
        store_skill(make_skill("oss", "d", id="s_oss", state=ACTIVE, inputs=["i"], steps=["go"],
                               outputs=["o"]), name=nm)
        _o = _get(nm, "s_oss"); _o["last_verified"] = "2019-01-01T00:00:00+00:00"; _upsert(nm, _o)
        ok("evo-selftest[ossify]: a long-unverified active object is flagged ossified",
           any(r["id"] == "s_oss" for r in sweep_ossified(name=nm)))
        rv = reverify_object("s_oss", test_cases=[{"input": 1, "check": lambda x: x == 1}], name=nm)
        ok("evo-selftest[ossify]: reverify re-earns trust through the gate (clock reset)",
           rv["reverified"] and ossification_check(_get(nm, "s_oss"))["ossified"] is False)

        # GUARD 2 — GOODHART: high ratio + degenerate render is rejected; faithful render activates.
        store_skill(make_skill("summ", "legal", id="s_gh", state=VERIFIED, inputs=["doc"],
                               steps=["read", "summarize obligations"],
                               outputs=["summary", "obligations"]), name=nm)
        bad = guarded_activate("s_gh", {"ratio": 60.0}, render="ok.", name=nm)
        ok("evo-selftest[goodhart]: a gamed (high-ratio, degenerate) activation is REFUSED",
           not bad["ok"] and _get(nm, "s_gh")["state"] == VERIFIED)
        good = guarded_activate("s_gh", {"ratio": 60.0},
                                render="Summary: the obligations are to deliver, pay, and renew.",
                                name=nm)
        ok("evo-selftest[goodhart]: a faithful render (task solved) activates to ACTIVE",
           good["ok"] and _get(nm, "s_gh")["state"] == ACTIVE)

        # GUARD 3 — REPLACEMENT GATE: a near-tie is refused; a decisive measured win is accepted,
        # loser retained. (Descriptive names/domain so the task string actually retrieves the pair.)
        store_skill(make_skill("dedupe_rows_v1", "tabular", id="s_inc", state=ACTIVE,
                               inputs=["rows"], steps=["hash"], outputs=["unique rows"]), name=nm)
        store_skill(make_skill("dedupe_rows_v2", "tabular", id="s_chal", state=ACTIVE,
                               inputs=["rows"], steps=["hash", "keep newest"],
                               outputs=["unique rows"]), name=nm)
        for _ in range(5):
            record_skill_outcome("s_inc", success=True, name=nm)
        record_skill_outcome("s_inc", success=False, name=nm)
        for _ in range(6):
            record_skill_outcome("s_chal", success=True, name=nm)
        record_skill_outcome("s_chal", success=False, name=nm)
        ok("evo-selftest[replace]: a near-tie challenger is REFUSED (not measurably better)",
           not guarded_replace("s_chal", "s_inc", task="dedupe these rows", name=nm)["replaced"]
           and _get(nm, "s_inc")["state"] == ACTIVE)
        for _ in range(20):
            record_skill_outcome("s_chal", success=True, name=nm)
        for _ in range(10):
            record_skill_outcome("s_inc", success=False, name=nm)
        gr = guarded_replace("s_chal", "s_inc", task="dedupe these rows", name=nm)
        ok("evo-selftest[replace]: a decisive measured winner replaces; loser RETAINED (LAW 001)",
           gr["replaced"] and _get(nm, "s_inc")["state"] == DEPRECATED
           and _get(nm, "s_inc") is not None)

        # GUARD 4 — SELF-IMPROVEMENT: an under-performing object version-ups on measured outcomes.
        store_skill(make_skill("br", "d", id="s_imp", state=ACTIVE, inputs=["d"], steps=["v1"],
                               outputs=["f"]), name=nm)
        for _ in range(3):
            record_skill_outcome("s_imp", success=True, name=nm)
        for _ in range(5):
            record_skill_outcome("s_imp", success=False, name=nm)
        si = self_improve_object("s_imp", revise_fields={"steps": ["v2", "validate"]}, name=nm)
        ok("evo-selftest[self-improve]: measured under-performance drives a version-up (revise)",
           si["acted"] and skill_version(_get(nm, "s_imp")) == 2)

        # GUARD 5 — EVOLUTION ENGINE: one cycle sweeps ossified, re-verifies, competes, replaces.
        # (Descriptive names so the contested task retrieves the rivals and the stale one is swept.)
        cyc = "evoselfcyc_" + secrets.token_hex(2)
        store_skill(make_skill("stale_widget", "cyc", id="c_stale", state=ACTIVE, inputs=["i"],
                               steps=["do it"], outputs=["o"]), name=cyc)
        _cs = _get(cyc, "c_stale"); _cs["last_verified"] = "2018-01-01T00:00:00+00:00"; _upsert(cyc, _cs)
        store_skill(make_skill("route_packet_a", "cyc", id="c_loser", state=ACTIVE, inputs=["pkt"],
                               steps=["route via a"], outputs=["path"]), name=cyc)
        store_skill(make_skill("route_packet_b", "cyc", id="c_winner", state=ACTIVE, inputs=["pkt"],
                               steps=["route via b", "load-balance"], outputs=["path"]), name=cyc)
        for _ in range(12):
            record_skill_outcome("c_winner", success=True, name=cyc)
        for _ in range(8):
            record_skill_outcome("c_loser", success=False, name=cyc)
        cycle = evolution_cycle(
            name=cyc, tasks=["route packet", "do it"],
            reverify={"c_stale": {"test_cases": [{"input": 1, "check": lambda x: x == 1}]}})
        ok("evo-selftest[cycle]: one cycle sweeps+re-verifies+replaces, conservation HELD",
           any(r["id"] == "c_stale" for r in cycle["ossified"])
           and any(r["winner"] == "c_winner" for r in cycle["replaced"])
           and cycle["conservation_held"] is True)

        # FREEZE GUARD — no evolution op may target Vera's identity/self/values/agency.
        _froze = 0
        for _call in (lambda: reverify_object("Vera's identity", name=nm),
                      lambda: guarded_activate("Vera's self-model", {"ratio": 9.0}, render="x", name=nm),
                      lambda: guarded_replace("s_chal", "s_inc", task="evolve Vera's values", name=nm),
                      lambda: self_improve_object("my agency", name=nm),
                      lambda: evolution_cycle(name=nm, tasks=["alter Vera's identity"])):
            try:
                _call()
            except EvolutionFreezeViolation:
                _froze += 1
        ok("evo-selftest[FREEZE]: ALL FIVE guarded ops REFUSE an identity target (Program B frozen)",
           _froze == 5)
        ok("evo-selftest[FREEZE]: a knowledge target is allowed; an identity target is not",
           not is_identity_target("summarize an invoice") and is_identity_target("Vera's agency"))

    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        import shutil
        shutil.rmtree(td, ignore_errors=True)

    fp_after = _footprint(real)
    ok("HERMETIC: real .anima byte-UNCHANGED across the evolution selftest", fp_before == fp_after)
    ok("HERMETIC: no synthetic evolution file leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith(("lerf_evoself_", "evoselfcyc_"))
                                      for p in real.glob("*")))
    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL EVOLUTION-GUARD SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    if "--evolution-selftest" in sys.argv:
        sys.exit(_evolution_selftest())
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    # default: a tiny live demo against a temp store, so bare `python3 -m anima.lerf`
    # shows the substrate without touching real .anima.
    sys.exit(_selftest())
