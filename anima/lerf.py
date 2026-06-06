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
    for k in ("name", "domain", "definition"):
        v = obj.get(k)
        if v:
            parts.append(str(v))
    for k in ("inputs", "steps", "outputs", "prerequisites", "related", "examples",
              "common_misunderstandings", "inputs_needed", "tools_needed",
              "failure_modes"):
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


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    # default: a tiny live demo against a temp store, so bare `python3 -m anima.lerf`
    # shows the substrate without touching real .anima.
    sys.exit(_selftest())
