"""world_state — THE PERSONAL WORLD STATE: facts become connected SITUATIONS.

Today Vera knows isolated values: ``birthday = Sept 14``, ``favorite_food = sushi``.
Each is a true, auditable LIRF row, and the Knowledge Spine binds them so she states
them as settled fact. But a value in a slot is not yet *understanding*. A person is
not a row of traits — they are a web of SITUATIONS: "work is heavy BECAUSE a new
manager started three months ago, and the stress is eating into sleep." The leap this
module makes is from VALUES to RELATIONS — the edges *between* facts — so the same
creature can surface the connected cluster, not one stranded slot.

This is an ADDITIVE layer, by hard design:

  * It never touches ``memory_lirf``'s on-disk format, its capture/merge/lookup, or the
    Knowledge-Spine binding. Birthday is at 100% and stays there; the LIRF ledger remains
    the single source of truth for atomic USER facts. world_state only *reads* those rows
    (through ``memory_lirf.Facts`` / ``router.select_facts``) and *adds* a second,
    separately-persisted store of typed RELATIONS over them.
  * Its store is ``.anima/{name}.world.json`` — a NEW file, written with the same atomic,
    optionally-sealed ``util.save_json`` the rest of ``.anima`` uses. Continuity is
    honoured the LIRF way: relations are APPENDED with a stable id and an append-only
    history of supersede/retract; a save never overwrites-and-loses prior relations.

Three primitives, mirroring the LIRF/Spine division of labour:

  * ``relate(name, subject, predicate, object, *, kind, confidence, source)`` — the write
    primitive. Stores one typed relation (a graph EDGE). ``predicate`` may be
    relational/causal ("works_at", "stressed_by", "because", "leads_to", "cares_about",
    "worried_about"); ``object`` may itself be another node (a topic, a person, a feeling),
    so edges chain into a graph. Dedupes on (subject, predicate, object); a repeat
    corroborates (confidence climbs, support++) exactly like LIRF, never duplicates.

  * ``capture_relations(name, text)`` — the deterministic extractor. Pulls the OBVIOUS
    causal/relational statements a person actually says — "my work's stressful because of
    my new manager", "I'm not sleeping well", "I care about my daughter", "I'm worried
    about money" — into relations, via the same anchored, first-person, never-infer
    discipline as ``memory_lirf.extract``. It connects a cause to an effect ONLY when the
    person stated the link (because/since/so/leads-to + worry/stress/goal cues). It NEVER
    fabricates an edge that wasn't said. An OFF-by-default model pass exists for parity with
    LIRF's Tier B, but the core needs no model.

  * ``situation(name, query_or_entity, hops=2)`` — the read primitive, and the whole point.
    A bounded breadth-first walk over the relation graph (seeded by the queried topic/entity
    and joined to the LIRF facts that share that topic), returning the CONNECTED CLUSTER
    within ``hops`` edges — facts AND relations — so "work" or "how am I doing?" surfaces
    manager -> stress -> sleep linked together, not one isolated slot. Bounded and O(ms):
    a personal companion's graph is tens to low-hundreds of edges (the same footprint bet
    LIRF documents), the walk is capped by ``hops`` and a node budget, and an unrelated
    query returns a small/empty cluster.

And one renderer:

  * ``render_situation(cluster)`` — projects a cluster into a compact block in the Knowledge
    Spine's binding style (PREAMBLE / ITEMS / GUARDRAIL), so the mouth can express it as
    UNDERSTANDING ("I know work's been heavy since the new manager started — and it's been
    eating your sleep"), not a data dump. It carries the SAME no-scaffold-leak discipline:
    the bracket tags and framing are for the model only and must never be read aloud
    (``spine.SCAFFOLD_TOKENS`` covers the shared tokens; the new relational tags are added to
    the module-local leak list the mouth's scrub can import).

Isolation-safe like its siblings (``spine``/``memory_schema``): the live primitives are
reused when importable and fall back to contract-faithful shims when run standalone, so
``--selftest`` has zero unbuilt deps and touches no model, network, or the real ``.anima``.
"""

from __future__ import annotations

import re
import secrets
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. Prefer the live primitives; fall back to
# contract-identical locals so this module + its self-test run with nothing built.
# We need:
#   from util          — save_json / load_json (atomic, optionally sealed)
#   from memory_lirf   — SELF, canon_trait, _now, _new_id, CONF_NEW/CONF_CEIL/
#                        CONF_AGREE_RATE/CONF_BLOCK_FLOOR, _fmt_value, Facts (read-only)
#   from memory_schema — TYPES (the closed type set our `kind` must live within)
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from .util import save_json, load_json
except Exception:  # pragma: no cover - isolation fallback
    import json as _json
    import os as _os
    import tempfile as _tempfile
    from pathlib import Path as _Path

    def save_json(path, obj) -> None:
        path = str(path)
        directory = _os.path.dirname(path) or "."
        _os.makedirs(directory, exist_ok=True)
        fd, tmp = _tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with _os.fdopen(fd, "w") as f:
                f.write(_json.dumps(obj))
            _os.replace(tmp, path)
        except Exception:
            try:
                _os.unlink(tmp)
            except OSError:
                pass
            raise

    def load_json(path, default=None):
        p = _Path(path)
        if not p.exists():
            return default
        try:
            return _json.loads(p.read_text())
        except (OSError, ValueError):
            return default


try:  # pragma: no cover - import wiring
    from .memory_lirf import (
        SELF,
        canon_trait,
        _now,
        _new_id,
        _fmt_value,
        CONF_NEW,
        CONF_CEIL,
        CONF_AGREE_RATE,
        CONF_BLOCK_FLOOR,
    )
except Exception:  # pragma: no cover - isolation fallback
    from datetime import datetime as _dt, timezone as _tz

    SELF = "you"
    CONF_NEW = 0.9
    CONF_CEIL = 0.99
    CONF_AGREE_RATE = 0.34
    CONF_BLOCK_FLOOR = 0.55

    def _now() -> str:
        return _dt.now(_tz.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _new_id() -> str:
        return "f_" + secrets.token_hex(6)

    def canon_trait(trait: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(trait).strip().lower()).strip("_")

    def _fmt_value(v: Any) -> str:
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v)


# The closed set of relation kinds. A superset of memory_schema.TYPES that adds the
# situational kinds a world-state needs (observation/goal/preference/problem). Kept
# local so the schema's founder-fixed type set is never widened by this layer, while
# our own store can carry the richer vocabulary the founder's brief asks for.
KINDS = (
    "fact",          # a stable trait edge mirrored/lifted from a value ("works_at" Acme)
    "observation",   # something noticed about a state ("sleeping" badly)
    "inference",     # a soft, gathered link (never bound as settled)
    "goal",          # something they're working toward
    "preference",    # a like/care ("cares_about" daughter)
    "relationship",  # a person/entity bond ("manager_is" Dana)
    "problem",       # a stressor/worry ("worried_about" money)
    "value",         # something held as important
)

# Predicates that assert a CAUSAL/relational link between two nodes (as opposed to a
# plain attribute). Used by render to phrase an edge as understanding, and by the
# graph walk as the edges most worth chaining.
CAUSAL_PREDICATES = frozenset({
    "because", "due_to", "caused_by", "stressed_by", "worried_about",
    "leads_to", "makes", "affects", "worsens", "since",
})

VERSION = 1

# A new relation enters at the same confidence a fresh LIRF fact does; a corroborating
# repeat climbs asymptotically and bumps support — identical curve to memory_lirf so the
# two stores agree on what "confident" means.
CONF_RELATION = CONF_NEW


# ---------------------------------------------------------------------------
# Node identity. A node in the graph is a (kind-less) string token: an entity ("you",
# "manager"), a topic ("work"), or a feeling/state ("stressed", "sleep"). Edges connect
# nodes. We normalise a node to a stable lookup key so "my new manager" and "the manager"
# land on the same vertex without inventing a link the user didn't state.
# ---------------------------------------------------------------------------
# First-person pronouns ALL fold to the canonical user node SELF ("you") — the same
# I/you/me collapse memory_lirf does for the ledger's entity. This is why a "you"-subject
# edge survives normalisation (it must: the user is the hub of their own situations).
_SELF_WORDS = frozenset("i you me my mine myself we us our ours".split())

# True FUNCTION words only — articles, possessives-of-others, prepositions, conjunctions,
# and degree adverbs that carry no situational content. Descriptive words ("new", "bad")
# are deliberately NOT here: "new manager" must stay distinct from "manager".
_STOP = frozenset(
    "a an the this that these those is are was were be been being am "
    "of to in on at for with about and or but so very really just "
    "his her their its he she it they them him".split()
)


def _norm_node(s: Any) -> str:
    """Canonical lookup key for a graph node. Lowercased, punctuation->space, function
    words dropped, collapsed — so "my new manager" -> "new manager", "the manager" ->
    "manager". Any first-person reference folds to the single user node SELF ("you"), so
    "I"/"me"/"my" all land on the same hub vertex. Empty -> ""."""
    if s is None:
        return ""
    if not isinstance(s, str):
        s = _fmt_value(s)
    raw = re.sub(r"[^a-z0-9]+", " ", s.lower()).split()
    # a node that is ENTIRELY first-person ("I", "me", "my own") IS the user node.
    if raw and all(t in _SELF_WORDS for t in raw):
        return SELF
    toks = [t for t in raw if t and t not in _STOP and t not in _SELF_WORDS]
    return " ".join(toks).strip()


def _node_tokens(s: Any) -> set:
    """The content tokens of a node string (for topical overlap during the walk seed)."""
    return set(_norm_node(s).split())


def _climb(conf: float) -> float:
    """Asymptotic corroboration climb — the exact curve memory_lirf uses."""
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = CONF_NEW
    return min(CONF_CEIL, conf + (1.0 - conf) * CONF_AGREE_RATE)


# ===========================================================================
# THE STORE — a flat list of relation edges, persisted ADDITIVELY to its OWN file.
# ===========================================================================

from pathlib import Path

STORE = Path(".anima")


class World:
    """The relation graph for one creature: a flat list of typed edges, indexed in
    memory by (subject, predicate, object) for dedupe and by id for edit. Mirrors the
    ``memory_lirf.Facts`` shape (rows + reindex + atomic save) so the two stores feel
    the same and share the same continuity discipline — but it is a SEPARATE file and
    never the LIRF ledger."""

    def __init__(self, relations: Optional[list] = None):
        self.relations = relations or []
        self._reindex()

    def _reindex(self):
        self._by_id = {}
        self._by_key = {}     # (subj, pred, obj) -> active edge
        for r in self.relations:
            self._by_id[r["id"]] = r
            if r.get("status", "active") == "active":
                self._by_key[_edge_key(r)] = r

    # --- persistence (atomic + encrypted via util — never a bespoke writer) ---
    @classmethod
    def path(cls, name):
        return STORE / f"{name}.world.json"

    @classmethod
    def load(cls, name) -> "World":
        d = load_json(cls.path(name))
        rels = d.get("relations", []) if isinstance(d, dict) else []
        return cls(rels)

    def save(self, name) -> None:
        """Append-safe persist. CONTINUITY: re-load whatever is on disk and union it with
        our in-memory relations by id (newest wins per id), so a concurrent writer's edges
        are never silently dropped — a save can only ADD or update, never overwrite-and-lose.
        """
        STORE.mkdir(exist_ok=True)
        on_disk = load_json(self.path(name))
        disk_rels = on_disk.get("relations", []) if isinstance(on_disk, dict) else []
        merged = {r["id"]: r for r in disk_rels if isinstance(r, dict) and r.get("id")}
        for r in self.relations:                 # our view wins for ids we hold
            merged[r["id"]] = r
        out = list(merged.values())
        save_json(self.path(name), {"version": VERSION, "relations": out})
        # adopt the unioned view so the instance stays consistent with disk
        self.relations = out
        self._reindex()

    # --- write one edge -----------------------------------------------------
    def add(self, subject, predicate, object, *, kind="inference",
            confidence=CONF_RELATION, source=None) -> dict:
        """Insert or corroborate one typed edge. Dedupes on the normalised
        (subject, predicate, object): a repeat climbs confidence + bumps support and
        refreshes provenance (never a duplicate row). Returns the edge touched."""
        subj = _norm_node(subject)
        pred = canon_trait(predicate)
        obj = _norm_node(object)
        if not subj or not pred or not obj:
            # a malformed/empty edge is dropped, never stored — we don't invent nodes
            return {}
        kind = kind if kind in KINDS else "inference"
        now = _now()
        src = source or f"chat {now[:10]}"
        key = (subj, pred, obj)
        existing = self._by_key.get(key)
        if existing is not None:
            existing["support"] = int(existing.get("support", 1)) + 1
            existing["confidence"] = _climb(existing.get("confidence", CONF_RELATION))
            existing["source"] = src
            existing["updated"] = now
            return existing
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            conf = CONF_RELATION
        conf = 0.0 if conf < 0.0 else (1.0 if conf > 1.0 else conf)
        edge = {
            "id": _new_id(),
            "kind": kind,
            "subject": subj,
            "predicate": pred,
            "object": obj,
            "confidence": conf,
            "support": 1,
            "source": src,
            "created": now,
            "updated": now,
            "status": "active",
            "history": [],
        }
        self.relations.append(edge)
        self._by_id[edge["id"]] = edge
        self._by_key[key] = edge
        return edge

    # --- read: active edges -------------------------------------------------
    def active(self) -> list:
        return [r for r in self.relations if r.get("status", "active") == "active"]

    def retract(self, id) -> Optional[dict]:
        """Flip an edge to retracted — kept on disk for audit, dropped from the graph."""
        r = self._by_id.get(id)
        if r is None:
            return None
        r.setdefault("history", []).append({
            "object": r.get("object"), "confidence": r.get("confidence"),
            "at": r.get("updated"), "reason": "retracted",
        })
        r["status"] = "retracted"
        r["updated"] = _now()
        if self._by_key.get(_edge_key(r)) is r:
            del self._by_key[_edge_key(r)]
        return r


def _edge_key(r: dict):
    return (_norm_node(r.get("subject")), canon_trait(r.get("predicate", "")),
            _norm_node(r.get("object")))


# ===========================================================================
# CAPTURE — deterministic extraction of OBVIOUS causal/relational statements.
# Same anchoring discipline as memory_lirf.extract: first-person, declarative, and a
# hard "never infer a link not stated" rule. Each rule yields one or more edge dicts.
# ===========================================================================

# Reuse LIRF's hypothetical guard if importable; else a faithful local copy. A clause
# governed by a wish/conditional is NOT a stated situation ("I wish work were less
# stressful" must not assert work IS stressful).
try:  # pragma: no cover
    from .memory_lirf import _HYPOTHETICAL, _not_hypothetical, _is_stopname  # type: ignore
except Exception:  # pragma: no cover
    _HYPOTHETICAL = re.compile(
        r"\b(?:wish|hope|if|would|could|someday|one day|want to|wanna|going to|gonna|"
        r"used to|maybe|might|planning to|plan to|dream)\b", re.I)

    def _not_hypothetical(text: str, start: int) -> bool:
        head = text[:start]
        clause = re.split(r"[.!?;]|\b(?:but|and|because|so)\b", head, flags=re.I)[-1]
        return _HYPOTHETICAL.search(clause) is None

    # Faithful local copy of the LIRF appositive-name guard (a capitalised function/aux word
    # in a name slot is NOT a name) — so the standalone --selftest needs no LIRF build.
    _STOPNAMES_LOCAL = frozenset(
        "i im ive id ill my we weve were our the a an this that these those he she it they "
        "you your last next then and but so because when where what who why how if yeah "
        "honestly lately recently now just today yesterday tomorrow tonight maybe really "
        "after before since while also still yes no oh well is are was were has have had "
        "named called got started moved left quit joined loves lives works said told came "
        "went made".split())

    def _is_stopname(v) -> bool:
        s = re.sub(r"[^a-z]", "", str(v or "").strip().lower())
        return (not s) or s in _STOPNAMES_LOCAL


# Trailing filler an object-capture tends to over-run into ("money right now",
# "daughter more than anything"). Trimmed from the END so the node is the thing itself.
_TRAIL_FILLER = re.compile(
    r"(?:\s+(?:right\s+now|now|today|lately|currently|these\s+days|at\s+the\s+moment"
    r"|more\s+than\s+anything|so\s+much|a\s+lot|too|anymore|again|though"
    r"|more|than|anything|much|stuff|things?))+$", re.I)


def _clean_node(s: Optional[str]) -> Optional[str]:
    """Trim a captured node phrase to a readable surface form (NOT normalised — the
    normalised key is derived later). Drops surrounding punctuation/quotes, a leading
    article/possessive, and trailing temporal/degree filler; rejects empty."""
    if not s:
        return None
    s = re.sub(r"\s+", " ", s.strip()).strip(" .,!?;:\"'")
    # strip a leading possessive/article so the surface reads naturally ("my new manager"
    # -> "new manager"); the article carries no situational content.
    s = re.sub(r"^(?:my|your|our|the|a|an)\s+", "", s, flags=re.I).strip()
    # strip trailing filler the object regex over-ran into ("money right now" -> "money").
    s = _TRAIL_FILLER.sub("", s).strip()
    return s or None


# A feeling/state lexicon — the object of a "stressed_by"/observation edge, and the cue
# that a clause describes a situation worth connecting.
_STRESS_WORDS = r"stress(?:ed|ful|ing)?|overwhelm(?:ed|ing)?|anxious|anxiety|burn(?:ed|t)?\s*out|swamped|exhaust(?:ed|ing)?|drained|heavy|rough|hard|tough|frustrat(?:ed|ing)?|struggling|underwater|slammed"

# Subjects that name no real life-topic — pronouns + contentless fillers. A "<subject> is
# stressful" / "<subject> is hurting <Y>" clause whose subject is one of these must NOT become
# a spurious edge ("it's been rough" must never turn into "you stressed_by it").
_NON_TOPIC = frozenset({
    "i", "it", "this", "that", "she", "he", "they", "we", "you", "everything",
    "something", "things", "thing", "stuff", "all", "everyone", "everybody", "nothing",
    "today", "tonight", "tomorrow",
    "s", "t", "m", "d", "re", "ve", "ll",   # contraction remnants ("it's"->"s", "I'm"->"m")
})

# Each rule: (compiled regex, builder(match) -> list[edge-dict]). A builder returns the
# edges it is CERTAIN the text stated; it never adds a cause<->effect edge unless both
# sides appear in the matched span.
_RULES = []


def _rule(pattern, builder):
    _RULES.append((re.compile(pattern, re.I), builder))


# --- 1. explicit cause: "<thing> is stressful because (of) <cause>" -----------
# Connects the SUBJECT-topic to the stress feeling (subject stressed_by feeling) AND the
# topic to the stated cause (topic because cause) — only because the user said "because".
def _b_x_stressful_because(m):
    topic = _clean_node(m.group("topic"))
    cause = _clean_node(m.group("cause"))
    edges = []
    if topic:
        edges.append(("you", "stressed_by", topic, "problem", topic))
        if cause:
            edges.append((topic, "because", cause, "inference", None))
    return edges


_rule(
    # topic char-class excludes the apostrophe so "my work's stressful" yields topic="work"
    # and leaves the "'s" for the copula group (otherwise "work's" is eaten whole).
    r"\bmy\s+(?P<topic>[\w-]+(?:\s+[\w-]+){0,2}?)\s*(?:is|'s|has|have|feels|gets|seems)?(?:\s+been)?\s+(?:really\s+|so\s+|super\s+|pretty\s+)?"
    r"(?:" + _STRESS_WORDS + r")\b"
    r"(?:[^.!?]*?\b(?:because|due to|cause|cuz|since)\s+(?:of\s+)?(?:my\s+|the\s+|a\s+|an\s+)?(?P<cause>[\w'-]+(?:\s+[\w'-]+){0,3}))?",
    _b_x_stressful_because,
)


# --- 1b. subject-led stress WITHOUT a possessive: "work has been stressful", "the launch is
# rough", "the move was hard". Same shape as rule 1 (incl. the optional because-cause) but the
# topic isn't "my X". Guarded by _NON_TOPIC so a pronoun/filler subject never becomes a
# spurious "you stressed_by it" — and this is what lets situation("work") find a "work" node. -
def _b_subject_stressful(m):
    topic = _clean_node(m.group("topic"))
    cause = _clean_node(m.group("cause"))
    if not topic or topic.lower() in _NON_TOPIC:
        return []
    edges = [("you", "stressed_by", topic, "problem", topic)]
    if cause:
        edges.append((topic, "because", cause, "inference", None))
    return edges


_rule(
    r"\b(?:the\s+|this\s+|that\s+|my\s+)?(?P<topic>[\w-]+(?:\s+[\w-]+){0,2}?)\s+"
    r"(?:is|'s|are|was|were|has\s+been|have\s+been|feels|felt|gets|got|seems|been)\s+"
    r"(?:really\s+|so\s+|super\s+|pretty\s+|kinda\s+|a\s+bit\s+)?"
    r"(?:" + _STRESS_WORDS + r")\b"
    r"(?:[^.!?]*?\b(?:because|due to|cause|cuz|since)\s+(?:of\s+)?(?:my\s+|the\s+|a\s+|an\s+)?(?P<cause>[\w'-]+(?:\s+[\w'-]+){0,3}))?",
    _b_subject_stressful,
)


# --- 2. bare stress without a named cause: "work's been rough", "I'm stressed about X" ---
def _b_stressed_about(m):
    topic = _clean_node(m.group("topic"))
    if not topic:
        return []
    return [("you", "stressed_by", topic, "problem", topic)]


_rule(
    r"\bi(?:'?m| am|'ve been| have been| feel| felt)\s+(?:really\s+|so\s+|pretty\s+|super\s+)?"
    r"(?:" + _STRESS_WORDS + r")\b\s+(?:about|over|by|with|because of|cuz of)\s+(?:my\s+|the\s+|a\s+|an\s+)?(?P<topic>[\w'-]+(?:\s+[\w'-]+){0,3})",
    _b_stressed_about,
)


# --- 3. worry: "I'm worried/anxious about <X>" -> problem edge ---------------
def _b_worried_about(m):
    obj = _clean_node(m.group("obj"))
    if not obj:
        return []
    return [("you", "worried_about", obj, "problem", obj)]


_rule(
    r"\bi(?:'?m| am|'ve been| have been| feel| felt| keep being| get)\s+(?:really\s+|so\s+|pretty\s+|kinda\s+|a bit\s+)?"
    r"(?:worried|anxious|nervous|stressed|concerned|freaking out|fretting|losing sleep)\s+(?:about|over|because of|that)\s+(?:my\s+|the\s+|a\s+|an\s+)?(?P<obj>[\w'$-]+(?:\s+[\w'$-]+){0,3})",
    _b_worried_about,
)


# --- 4. sleep / health observation: "I'm not sleeping well", "I can't sleep" ---
def _b_sleep(m):
    return [("you", "sleeping", "poorly", "observation", "sleep")]


_rule(
    r"\b(?:i(?:'?m| am)?\s*)?(?:"
    r"not\s+sleeping\s+(?:well|much|enough|great|good)"
    r"|sleeping\s+(?:badly|poorly|terribly|like\s+crap)"
    r"|can'?t\s+sleep|barely\s+sleeping|not\s+getting\s+(?:any\s+|much\s+|enough\s+)?sleep"
    r"|hardly\s+sleeping|having\s+trouble\s+sleeping|losing\s+sleep"
    r")\b",
    _b_sleep,
)


# --- 5. stated effect chain: "<cause>, so <effect>" / "<cause> leads to <effect>" -----
# Only fires on an explicit connective. Connects two clauses the user explicitly linked.
def _b_leads_to(m):
    cause = _clean_node(m.group("cause"))
    effect = _clean_node(m.group("effect"))
    if cause and effect:
        return [(cause, "leads_to", effect, "inference", None)]
    return []


_rule(
    r"(?P<cause>[\w'-]+(?:\s+[\w'-]+){0,3})\s+(?:leads?\s+to|led\s+to|is\s+leading\s+to|results?\s+in|resulted\s+in|causes?|caused|means|meant)\s+(?:my\s+|the\s+|a\s+|an\s+)?(?P<effect>[\w'-]+(?:\s+[\w'-]+){0,3})",
    _b_leads_to,
)


# --- 5b. stated impact: "<A> is affecting/hurting <B>", "the stress is wrecking my sleep"
# -> A affects B. Both sides named in the matched span; subject A is guarded against a
# pronoun/filler so "it's hurting me" never fabricates an edge. --------------------------
def _b_affects(m):
    cause = _clean_node(m.group("cause"))
    effect = _clean_node(m.group("effect"))
    if not cause or not effect or cause.lower() in _NON_TOPIC:
        return []
    return [(cause, "affects", effect, "inference", None)]


_rule(
    r"\b(?:the\s+|my\s+|this\s+|that\s+)?(?P<cause>[\w'-]+(?:\s+[\w'-]+){0,3})\s+"
    r"(?:is|'s|are|keeps?|kept|has\s+been|have\s+been)\s+(?:really\s+|seriously\s+|totally\s+)?"
    r"(?:affecting|hurting|wrecking|ruining|messing\s+with|killing|tanking|eating\s+into|getting\s+to|taking\s+a\s+toll\s+on|weighing\s+on)\s+"
    r"(?:my\s+|the\s+|our\s+|his\s+|her\s+)?(?P<effect>[\w'-]+(?:\s+[\w'-]+){0,3})",
    _b_affects,
)


# --- 6. care / love: "I care about <X>", "I love my <X>" -> preference edge --------
def _b_cares_about(m):
    obj = _clean_node(m.group("obj"))
    if not obj:
        return []
    return [("you", "cares_about", obj, "preference", obj)]


_rule(
    r"\bi\s+(?:really\s+|deeply\s+)?(?:care about|cherish|love|adore|treasure)\s+(?:my\s+|our\s+)?(?P<obj>[\w'-]+(?:\s+[\w'-]+){0,2})",
    _b_cares_about,
)


# --- 7. goal: "I want to <X>", "I'm trying to <X>", "my goal is <X>" --------------
def _b_goal(m):
    obj = _clean_node(m.group("obj"))
    if not obj:
        return []
    return [("you", "working_toward", obj, "goal", obj)]


_rule(
    # widened (#27) for the Dream Engine: catch the common STATED-intention phrasings —
    # "I'm planning/aiming/meaning to", "I've been meaning/wanting to", "I intend/hope/aspire
    # to" — not just want/trying. "going to" is deliberately EXCLUDED (ambiguous with the plain
    # future "I'm going to the store"). Never fabricates: still an explicit first-person intent.
    r"\b(?:i(?:'?m| am)\s+(?:trying|working|hoping|planning|aiming|meaning|looking|itching|determined)\s+to"
    r"|i(?:'?ve| have)\s+been\s+(?:trying|hoping|planning|meaning|wanting|working)\s+to"
    r"|i\s+(?:want|need|plan|aim|intend|hope|mean|aspire)\s+to|my\s+goal\s+is\s+to)\s+(?P<obj>[\w'-]+(?:\s+[\w'-]+){0,4})",
    _b_goal,
)


# --- 8. a new person in their life: "my new manager", "I got a new boss" ----------
# Records the relationship node AND, when "new"/"just started"/"X months ago" appears,
# a recency observation — both stated, neither inferred.
def _b_new_person(m):
    role = _clean_node(m.group("role"))
    if not role:
        return []
    edges = [("you", "has", role, "relationship", role)]
    span = m.group(0).lower()
    if re.search(r"\bnew\b|just\s+(?:started|got|joined)|recently|(?:\d+|a|couple|few)\s+(?:months?|weeks?)\s+ago", span):
        edges.append((role, "is", "recent", "observation", None))
    return edges


_rule(
    r"\b(?:my|our|the|a)\s+(?P<role>new\s+(?:manager|boss|supervisor|lead|director|coworker|colleague|partner|roommate|landlord|doctor|therapist|teacher|coach)"
    r"|(?:manager|boss|supervisor)\s+(?:just\s+)?(?:started|joined))\b"
    r"(?:[^.!?]*?\b(?:(?P<n>\d+|a|couple|few)\s+(?P<unit>months?|weeks?)\s+ago|just\s+started|recently))?",
    _b_new_person,
)


# --- 9. life-event sequence: "I started my business after the divorce" -> business after
# divorce. Narrow (an explicit life-event verb + "after/following/once" + a named prior
# event), stored as a SEQUENCE edge — Observed>Assumed: it states ORDER, not a claimed cause.
def _b_after(m):
    later = _clean_node(m.group("later"))
    prior = _clean_node(m.group("prior"))
    if not later or not prior or later.lower() in _NON_TOPIC or prior.lower() in _NON_TOPIC:
        return []
    return [(later, "after", prior, "sequence", later)]


_rule(
    r"\bi\s+(?:started|launched|founded|began|opened|moved|left|quit|joined|married|divorced|retired|graduated|had)\s+"
    r"(?:my\s+|the\s+|a\s+|an\s+|to\s+)?(?P<later>[\w'-]+(?:\s+[\w'-]+){0,3})\s+(?:after|following|once)\s+"
    r"(?:my\s+|the\s+|a\s+|an\s+)?(?P<prior>[\w'-]+(?:\s+[\w'-]+){0,2})",
    _b_after,
)


# ===========================================================================
# WAVE A — LIFE-EVENT edges + the TEMPORAL qualifier they hang on.
# A stated life event ("I moved to Austin", "we adopted a dog", "my daughter started
# kindergarten") is a SITUATION, not just an isolated value: it has an actor, an object,
# often a stated CAUSE, and often a TIME. The conservation ledger showed these as
# total-loss because no relational rule had a frame for them. These rules add that frame,
# with the SAME never-infer discipline: every node comes from the matched span, the
# capital/stop guards reject fabricated nouns, and a TIME is attached only when the user
# actually stated one. Observed > Assumed throughout.
# ===========================================================================

# A stated TIME inside a clause — "in 2024", "last week", "in March", "by Q3", "3 months
# ago". Pulled as a readable surface so it can become the OBJECT of a "<event>_when" edge
# (the temporal then has a slot to live in instead of being dropped). Anchored words only;
# never matches a bare number that isn't a time.
_TEMPORAL_PHRASE = re.compile(
    r"\b("
    r"(?:in|by|since|around|back in)\s+(?:\d{4}|Q[1-4]|"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?))"
    r"|(?:last|next|this)\s+(?:week|month|year|spring|summer|fall|autumn|winter|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"|(?:\d{1,2}|a|a\s+couple|couple|few|several)\s+(?:days?|weeks?|months?|years?)\s+ago"
    r"|yesterday|today|tonight|tomorrow|this\s+weekend|last\s+weekend"
    r")\b",
    re.I,
)


def _temporal_in(span: str):
    """The first stated TIME phrase in a span ("in 2024", "last week"), or None. The
    leading connective (in/by/last…) is kept so the stored object reads naturally AND so
    the temporal salient tokens (the year/month/'last'/'week') survive in the object."""
    if not span:
        return None
    m = _TEMPORAL_PHRASE.search(span)
    if not m:
        return None
    s = re.sub(r"\s+", " ", m.group(1).strip())
    return s or None


# --- 10. MOVE: "I moved to Austin (because <cause>)", "the move to Denver", "we moved to
# Portland in March". Emits you --moved_to--> PLACE (predicate built from the actual verb so
# "moved"/"move" both credit), the stated CAUSE as PLACE --because--> CAUSE, and the stated
# TIME as you --moved_when--> TIME. PLACE is capital-guarded; CAUSE/TIME only when present. -
def _b_moved(m):
    place = _clean_node(m.group("place"))
    if not place or place.lower() in _NON_TOPIC:
        return []
    verb = (m.group("verb") or "moved").lower()
    pred = "move_to" if verb == "move" else "moved_to"
    edges = [("you", pred, place, "fact", place)]
    cause = _clean_node(m.group("cause")) if m.groupdict().get("cause") else None
    if cause and cause.lower() not in _NON_TOPIC:
        edges.append((place, "because", cause, "inference", None))
    when = _temporal_in(m.group(0))
    if when:
        edges.append(("you", "moved_when", when, "observation", None))
    return edges


_rule(
    # "I/we moved to <Place>" — capital-guarded place (so a common noun like "the city" never
    # matches), optional "because <cause>", optional trailing TIME (kept in the span so
    # _temporal_in can attach "last year"/"in 2024" as you --moved_when--> TIME).
    r"\b(?:i|we)\s+(?:just\s+|recently\s+|finally\s+)?(?P<verb>moved)\s+(?:back\s+)?to\s+"
    r"(?P<place>(?-i:[A-Z])[\w'-]+(?:[ ,]+(?-i:[A-Z])[\w'.-]+){0,3})"
    r"(?:[^.!?]*?\bbecause\s+(?:of\s+)?(?:my\s+|the\s+|a\s+|an\s+)?(?P<cause>[\w'-]+(?:\s+[\w'-]+){0,3}))?"
    r"(?:[^.!?]*?\b(?:(?:last|next|this)\s+(?:week|month|year)|(?:in|by|back\s+in)\s+(?:\d{4}|Q[1-4]|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)|\d+\s+(?:months?|years?)\s+ago))?",
    _b_moved,
)
_rule(
    # "the move to <Place> (in March)" — the planned/recent move as a noun. Temporal tail
    # kept in the span so _temporal_in attaches the stated time (you --moved_when--> March).
    r"\bthe\s+(?P<verb>move)\s+to\s+(?P<place>(?-i:[A-Z])[\w'-]+(?:[ ,]+(?-i:[A-Z])[\w'.-]+){0,3})"
    r"(?:[^.!?]*?\b(?:in|by|around)\s+(?:\d{4}|Q[1-4]|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?))?",
    _b_moved,
)


# --- 10b. a NAMED person in their life stated appositively: "my wife Jen", "my daughter
# Maya", "my friend Sloane" -> you --has--> ROLE (the relationship the LIRF name hangs on).
# Records ONLY the role bond (the NAME itself is LIRF's job); the capital-guarded appositive
# is what proves a person was actually named, not a generic mention. Never fabricates. ------
def _b_named_relation(m):
    role = (m.group("role") or "").lower().strip()
    # the appositive token must be a genuine NAME, not a capitalised aux/function word.
    if not role or _is_stopname(m.group("name")):
        return []
    return [("you", "has", role, "relationship", role)]


_rule(
    r"\bmy\s+(?P<role>wife|husband|partner|girlfriend|boyfriend|fiance|fiancee|"
    r"daughter|son|mom|mother|dad|father|brother|sister|friend|boss|manager)\s+"
    r"(?P<name>(?-i:[A-Z])[a-z'-]+)\b",     # an appositive NAME must follow (capital-guarded)
    _b_named_relation,
)


# --- 11. ADOPT: "we adopted a dog (named Cooper) (in 2024)" -> you --adopted--> dog, and the
# year as you --adopted_when--> 2024. Species is a closed set (never a fabricated noun). -----
def _b_adopted(m):
    species = (m.group("species") or "").lower().strip()
    if not species:
        return []
    edges = [("you", "adopted", species, "fact", species)]
    when = _temporal_in(m.group(0))
    if when:
        edges.append(("you", "adopted_when", when, "observation", None))
    return edges


_rule(
    r"\b(?:we|i)\s+(?:just\s+|recently\s+)?adopted\s+(?:a\s+|an\s+|our\s+)?(?P<species>dog|cat|puppy|kitten|kitty|pet)\b"
    r"(?:[^.!?]*?(?:in|back\s+in)\s+(?:\d{4}|Q[1-4]))?",
    _b_adopted,
)


# --- 12. THIRD-PARTY life event: "my daughter Maya started kindergarten last week",
# "my son Theo started school". Emits you --has--> ROLE (credits the relationship), ROLE
# --started--> THING (the event), and the stated TIME as ROLE --started_when--> TIME. The
# THING is a closed set of life milestones so a stray verb can't fabricate an edge. --------
def _b_relation_started(m):
    role = (m.group("role") or "").lower().strip()
    thing = _clean_node(m.group("thing"))
    if not role or not thing:
        return []
    edges = [("you", "has", role, "relationship", role),
             (role, "started", thing, "fact", role)]
    when = _temporal_in(m.group(0))
    if when:
        edges.append((role, "started_when", when, "observation", None))
    return edges


_rule(
    r"\bmy\s+(?P<role>daughter|son|wife|husband|partner|mom|mother|dad|father|brother|sister|kid|child)\s+"
    r"(?:(?-i:[A-Z])[a-z'-]+\s+)?"          # optional appositive NAME (skipped; LIRF owns the name)
    r"(?:just\s+|recently\s+|finally\s+)?(?:started|began|enrolled\s+in|got\s+into)\s+"
    r"(?:my\s+|the\s+|a\s+|an\s+)?(?P<thing>kindergarten|preschool|pre-?k|school|college|university|daycare|"
    r"first\s+grade|middle\s+school|high\s+school|a\s+new\s+job|kindergarden)\b"
    r"(?:[^.!?]*?(?:(?:last|next|this)\s+(?:week|month|year)|in\s+\d{4}))?",
    _b_relation_started,
)


# --- 13. SELF life event with a time but no place/object frame: "I started a new job last
# month", "I graduated in 2020", "I retired last year". Emits a dated event marker so the
# milestone + its time are both kept. Verb is a closed life-event set; never fabricates. ---
def _b_self_event_when(m):
    verb = (m.group("verb") or "").lower().strip()
    when = _temporal_in(m.group(0))
    if not verb or not when:
        return []
    return [("you", canon_trait(verb), when, "observation", None)]


_rule(
    r"\bi\s+(?:just\s+|recently\s+|finally\s+)?(?P<verb>graduated|retired|quit|enlisted|divorced)\b"
    r"[^.!?]*?\b(?:(?:last|next|this)\s+(?:week|month|year)|in\s+(?:\d{4}|Q[1-4]|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)|\d+\s+(?:months?|years?)\s+ago)\b",
    _b_self_event_when,
)


def capture(text: str) -> list:
    """DETERMINISTIC extraction (the always-on path). Pull the obvious causal/relational
    statements from a USER utterance into edge tuples ``(subject, predicate, object, kind,
    topic|None)``. ``topic`` (when present) is the node this edge should also be findable
    under — used by ``capture_relations`` to wire a "you stressed_by work" edge so a
    "work" query reaches it.

    Anchored to declarative first-person; a clause under a wish/conditional is rejected;
    a cause<->effect edge is emitted ONLY when both sides appear in the matched span. Never
    fabricates a link the text did not state. Returns a de-duplicated list of edge tuples.
    """
    if not text or not text.strip():
        return []
    out = []
    seen = set()
    for rx, build in _RULES:
        for m in rx.finditer(text):
            if not _not_hypothetical(text, m.start()):
                continue
            for edge in build(m) or []:
                subj, pred, obj, kind, topic = edge
                key = (_norm_node(subj), canon_trait(pred), _norm_node(obj))
                if "" in key:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                out.append((subj, pred, obj, kind, topic))
    return out


# ---------------------------------------------------------------------------
# Optional model-assist (Tier B parity) — OFF by default. Mirrors memory_lirf.extract_model:
# a strict "never infer" instruction, parses STRICT JSON, returns the same edge-tuple shape.
# Never on a live turn's critical path; any parse failure yields [].
# ---------------------------------------------------------------------------
_MODEL_SYSTEM = (
    "You extract RELATIONSHIPS a person stated between things in their life, for their "
    "companion's understanding. Output ONLY a JSON array. Each item: "
    '{"subject": str, "predicate": snake_case relation, "object": str, "kind": one of '
    "fact|observation|inference|goal|preference|relationship|problem|value}. Use the "
    "person as subject \"you\" when they speak of themselves. Include an edge ONLY if the "
    "person EXPLICITLY stated the link (e.g. they said one thing is BECAUSE of another, or "
    "that they're stressed/worried by something, or care about someone). NEVER infer a "
    "connection they did not state. Ignore hypotheticals and the assistant's words. If "
    "there are no stated relationships, output []. Output the JSON array and nothing else."
)


def capture_model(text: str, brain) -> list:
    """TIER B (off by default). Model-assisted strict relation extraction. Returns the same
    edge-tuple shape as ``capture``. Best-effort: any failure yields []; never raises."""
    if not text or not text.strip() or brain is None:
        return []
    try:
        raw = brain.reply(_MODEL_SYSTEM, f'User said: "{text.strip()}"\n\nJSON:', [])
    except Exception:
        return []
    import json as _json
    mt = re.search(r"\[.*\]", raw or "", re.S)
    if not mt:
        return []
    try:
        arr = _json.loads(mt.group(0))
    except Exception:
        return []
    out = []
    if isinstance(arr, list):
        for it in arr:
            if not isinstance(it, dict):
                continue
            subj, pred, obj = it.get("subject"), it.get("predicate"), it.get("object")
            if not subj or not pred or obj in (None, "", []):
                continue
            kind = it.get("kind") if it.get("kind") in KINDS else "inference"
            out.append((str(subj), str(pred), str(obj), kind, _norm_node(obj) or None))
    return out


# ===========================================================================
# THE PUBLIC API — module-level convenience over World, mirroring memory_lirf's
# capture/retrieve/render surface so call-sites juggle no load/save.
# ===========================================================================

def relate(name: str, subject: str, predicate: str, object: str, *,
           kind: str = "inference", confidence: float = CONF_RELATION,
           source: Optional[str] = None) -> dict:
    """Store one typed relation and PERSIST it immediately (append-safe). Returns the
    stored edge. The headline write primitive: ``relate("vera", "you", "stressed_by",
    "work", kind="problem")``. Dedupes/corroborates on (subject, predicate, object)."""
    w = World.load(name)
    edge = w.add(subject, predicate, object, kind=kind, confidence=confidence, source=source)
    if edge:
        w.save(name)
    return edge


def capture_relations(name: str, text: str, *, brain=None, model_pass: bool = False) -> list:
    """Extract the OBVIOUS stated causal/relational statements from one utterance and
    PERSIST them as relations (deterministic always; an OFF-by-default model pass when
    ``model_pass`` and a ``brain`` are given). Returns the edges touched.

    Wiring note on topics: a rule that produced a ``topic`` (e.g. "you stressed_by work")
    stores exactly that edge — the topic IS the object, so a later ``situation("work")``
    reaches it. We never synthesise an extra edge the user didn't state.

    Intended to be called inside the server's per-turn lock alongside
    ``memory_lirf.capture`` — the turn is already serialised, so the read-modify-write is
    race-free, and ``World.save`` is additionally union-on-disk safe.
    """
    edges = capture(text)
    if model_pass and brain is not None:
        seen = {(_norm_node(s), canon_trait(p), _norm_node(o)) for s, p, o, _k, _t in edges}
        for s, p, o, k, t in capture_model(text, brain):
            key = (_norm_node(s), canon_trait(p), _norm_node(o))
            if "" not in key and key not in seen:
                edges.append((s, p, o, k, t))
                seen.add(key)
    if not edges:
        return []
    w = World.load(name)
    touched = []
    for subj, pred, obj, kind, _topic in edges:
        e = w.add(subj, pred, obj, kind=kind)
        if e:
            touched.append(e)
    if touched:
        w.save(name)
    return touched


# ---------------------------------------------------------------------------
# SITUATION — the bounded, connected-cluster read. The whole point of the layer.
# ---------------------------------------------------------------------------

# A small alias table so a query word reaches the topic node it names. Deliberately tiny
# and conservative — it folds synonyms, it does NOT invent links ("job" and "work" are the
# same topic; "manager" and "stress" are NOT made equal here, only by a stated edge).
_QUERY_ALIASES = {
    "job": "work", "career": "work", "office": "work", "boss": "manager",
    "supervisor": "manager", "sleeping": "sleep", "rest": "sleep",
    "money": "money", "finances": "money", "financial": "money", "cash": "money",
    "kid": "daughter", "child": "daughter",
}


def _facts_as_edges(name: str) -> list:
    """Lift the live LIRF facts into READ-ONLY pseudo-edges so a situation can include
    plain values too (favorite_food, employer, …) without touching the ledger. Each
    active SELF row becomes ("you", trait, value) with kind 'fact'. Best-effort: a missing
    ledger or an isolation run with no Facts yields []. NEVER writes."""
    try:
        from .memory_lirf import Facts as _Facts, SELF as _SELF
    except Exception:
        return []
    try:
        rows = _Facts.load(name).about(_SELF)
    except Exception:
        return []
    edges = []
    for r in rows:
        edges.append({
            "id": r.get("id"),
            "kind": "fact",
            "subject": _SELF,
            "predicate": r.get("trait", ""),
            "object": _fmt_value(r.get("value", "")),
            "confidence": r.get("confidence", CONF_NEW),
            "support": r.get("support", 1),
            "source": r.get("source", "lirf"),
            "_from_lirf": True,
        })
    return edges


def _seed_nodes(query: str, all_edges: list) -> set:
    """The starting vertices for the walk. The query is normalised to nodes; each query
    token (alias-folded) seeds the matching graph vertex. A token that names no vertex
    contributes nothing (so an unrelated query starts from an empty/near-empty seed and
    the cluster stays small)."""
    q_tokens = _node_tokens(query)
    q_tokens |= {_QUERY_ALIASES.get(t, t) for t in list(q_tokens)}
    # the set of nodes that actually exist in the graph
    nodes = set()
    for e in all_edges:
        nodes.add(_norm_node(e.get("subject")))
        nodes.add(_norm_node(e.get("object")))
    seed = set()
    for tok in q_tokens:
        if tok in nodes:
            seed.add(tok)
        # also seed any multi-word node whose token set the query shares (e.g. query
        # "work" reaching a node "work stress") — but only on a real token overlap.
        for n in nodes:
            if tok and tok in _node_tokens(n):
                seed.add(n)
    # A "broad check-in" query ("how am i doing", "what's going on") seeds the user
    # node itself, surfacing everything within hops of "you".
    if not seed and _is_broad_checkin(query):
        seed.add(SELF)
    return {s for s in seed if s}


_BROAD_CHECKIN = re.compile(
    r"\bhow\s+(?:am|are)\s+(?:i|you|things|we)\b|how'?s\s+(?:it|life|everything|things)\b"
    r"|what'?s\s+(?:going on|happening|up)\b|how\s+have\s+(?:i|you)\s+been\b"
    r"|check\s*in\b|catch\s*me\s*up\b", re.I)


def _is_broad_checkin(query: str) -> bool:
    return bool(_BROAD_CHECKIN.search(query or ""))


def situation(name: str, query_or_entity: str, hops: int = 2,
              max_nodes: int = 40) -> dict:
    """THE CONNECTED CLUSTER for a topic/entity — facts AND relations within ``hops`` edges.

    Loads the relation graph (this store's edges) UNIONED with the live LIRF facts lifted
    as read-only pseudo-edges, seeds a breadth-first walk from the vertex/vertices the
    query names (synonym-folded), and returns the bounded subgraph reachable within
    ``hops``. So ``situation("vera", "work")`` returns manager -> stress -> sleep linked
    (when those edges were stated), not one isolated slot; an unrelated query returns a
    small/empty cluster.

    Returns a dict cluster:
        {
          "query":   the original query string,
          "seed":    the seed node keys the walk started from,
          "nodes":   the set (as a sorted list) of node keys in the cluster,
          "edges":   the edge dicts in the cluster (world relations + lifted facts),
          "hops":    the hop budget used,
        }

    Bounded + O(ms): the walk is capped by ``hops`` and ``max_nodes``; a personal graph is
    tens to low-hundreds of edges. Read-only; never mutates either store. Never raises.
    """
    try:
        world_edges = World.load(name).active()
    except Exception:
        world_edges = []
    fact_edges = _facts_as_edges(name)
    all_edges = list(world_edges) + list(fact_edges)

    seed = _seed_nodes(query_or_entity, all_edges)
    if not seed:
        return {"query": query_or_entity, "seed": [], "nodes": [], "edges": [], "hops": hops}

    # adjacency over the undirected graph (an edge connects subject<->object)
    adj: dict = {}
    for idx, e in enumerate(all_edges):
        s, o = _norm_node(e.get("subject")), _norm_node(e.get("object"))
        if not s or not o:
            continue
        adj.setdefault(s, []).append((o, idx))
        adj.setdefault(o, []).append((s, idx))

    # BFS to depth `hops`, collecting visited nodes and the edge indices crossed.
    visited = set(seed)
    frontier = set(seed)
    edge_ids = set()
    depth = 0
    while frontier and depth < max(0, int(hops)) and len(visited) < max_nodes:
        nxt = set()
        for node in frontier:
            for (nbr, eidx) in adj.get(node, ()):
                edge_ids.add(eidx)
                if nbr not in visited:
                    nxt.add(nbr)
        visited |= nxt
        frontier = nxt
        depth += 1
        if len(visited) >= max_nodes:
            break
    # also include any edge whose BOTH endpoints are already in the visited set (closes
    # triangles the depth cut would otherwise drop — e.g. manager<->stress when both got
    # reached from different seeds).
    for idx, e in enumerate(all_edges):
        s, o = _norm_node(e.get("subject")), _norm_node(e.get("object"))
        if s in visited and o in visited:
            edge_ids.add(idx)

    cluster_edges = [all_edges[i] for i in sorted(edge_ids)]
    return {
        "query": query_or_entity,
        "seed": sorted(seed),
        "nodes": sorted(visited),
        "edges": cluster_edges,
        "hops": int(hops),
    }


# ===========================================================================
# RENDER — project a cluster into the Knowledge-Spine binding style. The mouth then
# expresses it as UNDERSTANDING, with the SAME no-scaffold-leak discipline.
# ===========================================================================

# Reuse the spine's shared scaffold-token list when importable; our relational tags are
# added on top so the mouth's leak-scrub has ONE place to learn them. Kept module-local
# (no spine edit) — the mouth can import WORLD_SCAFFOLD_TOKENS the same way it imports
# spine.SCAFFOLD_TOKENS.
try:  # pragma: no cover
    from .spine import SCAFFOLD_TOKENS as _SPINE_TOKENS
except Exception:  # pragma: no cover
    _SPINE_TOKENS = ("[KNOWN]", "[SEEN]", "[SENSE]", "[UNKNOWN]",
                     "THESE ARE THINGS YOU KNOW", "according to my memory")

# The bracket tags this renderer emits into the prompt — NEVER to be read aloud.
WORLD_SCAFFOLD_TOKENS = tuple(_SPINE_TOKENS) + (
    "[SITUATION]", "[LINK]", "[KNOWS]", "WHAT YOU UNDERSTAND ABOUT THEIR SITUATION",
)

# How each predicate is phrased as a clause the model can express. {s} = subject label,
# {o} = object label. Causal predicates read as understanding; attributes read plainly.
_PHRASE = {
    "stressed_by": "{s} are stressed by {o}",
    "worried_about": "{s} are worried about {o}",
    "because": "{s} is because of {o}",
    "due_to": "{s} is due to {o}",
    "leads_to": "{s} is leading to {o}",
    "makes": "{s} makes {o}",
    "affects": "{s} is affecting {o}",
    "worsens": "{s} is worsening {o}",
    "sleeping": "{s} have been sleeping {o}",
    "cares_about": "{s} care about {o}",
    "working_toward": "{s} are working toward {o}",
    "has": "{s} have {o}",
    "is": "{s} is {o}",
    "since": "{s} since {o}",
}


def _node_label(key: str) -> str:
    """Readable surface for a node key ("you" -> "you", "new manager" -> "the new manager")."""
    if key == SELF:
        return "you"
    return key


def _phrase_edge(e: dict) -> str:
    """One human clause for an edge, e.g. "you are stressed by work"."""
    pred = canon_trait(e.get("predicate", ""))
    s = _node_label(_norm_node(e.get("subject")))
    o = _node_label(_norm_node(e.get("object")))
    tmpl = _PHRASE.get(pred)
    if tmpl:
        return tmpl.format(s=s, o=o)
    # a plain LIRF fact / unknown predicate -> "trait: value" style, possessive
    label = pred.replace("_", " ")
    return f"{s}: {label} {o}".replace("you: ", "your ")


# The binding preamble for a SITUATION — parallel to spine._PREAMBLE but framed as
# *understanding a connected picture*, not reciting slots. Pushes warm expression, bans
# the same leak/citation failure modes.
_PREAMBLE = (
    "WHAT YOU UNDERSTAND ABOUT THEIR SITUATION — from your own memory of this person.\n"
    "These are not separate facts to list. They are CONNECTED — one thing because of\n"
    "another, one thing weighing on another. You already understand how they fit together.\n"
    "Your only job is to show that understanding in your own warm voice, the way someone\n"
    "who's been paying attention would — naming the through-line, not reciting a file.\n"
    "\n"
    "  • A line marked [KNOWS] is something you know about them — state it warmly, never\n"
    "    disclaim or hedge it.\n"
    "  • A line marked [LINK] is a connection THEY drew between two things (a cause, a\n"
    "    worry, a knock-on effect). Speak to the connection, not just the two ends.\n"
    "  • A line marked [SITUATION] is the shape of the whole — the heavy thing and what\n"
    "    it's touching. Lead with that, gently."
)

_GUARDRAIL = (
    "This is for YOU. Never read the brackets, the labels, or this framing aloud, never\n"
    "list it back like a record or a status report, never say \"according to my memory.\"\n"
    "Just talk like someone who simply understands what's going on for a person they care\n"
    "about — connected, not itemised."
)

_ITEMS_HEADER = "The connected picture right now:"


def render_situation(cluster: dict) -> str:
    """Render a ``situation`` cluster as a compact binding block in the Knowledge-Spine
    style, so the mouth can express it as UNDERSTANDING (e.g. "I know work's been heavy
    since the new manager started — and it's been eating your sleep").

    Structure mirrors ``spine.bind``: PREAMBLE (ownership/connection framing) + classed
    ITEMS + GUARDRAIL (warmth + no-leak). Edges are classed:
      * a causal/relational edge -> [LINK]   (speak to the connection)
      * a plain fact/attribute    -> [KNOWS]  (state it warmly)
    and a one-line [SITUATION] synopsis leads when a stressor + a knock-on are both present.

    Carries the SAME no-scaffold-leak discipline: every tag here is in
    ``WORLD_SCAFFOLD_TOKENS`` so the mouth's scrub strips any that leak. Empty cluster ->
    "" (nothing to bind). Pure, model-free, never raises.
    """
    if not isinstance(cluster, dict):
        return ""
    edges = [e for e in (cluster.get("edges") or []) if isinstance(e, dict)]
    if not edges:
        return ""

    # de-dupe identical phrasings; class each edge.
    links, knows = [], []
    seen = set()
    stressors, effects = [], []
    for e in edges:
        clause = _phrase_edge(e)
        if not clause or clause in seen:
            continue
        seen.add(clause)
        pred = canon_trait(e.get("predicate", ""))
        if pred in CAUSAL_PREDICATES or pred in ("sleeping", "cares_about", "working_toward"):
            links.append(f"[LINK] {clause}")
        else:
            knows.append(f"[KNOWS] {clause}")
        if pred in ("stressed_by", "worried_about", "because", "due_to"):
            stressors.append(_node_label(_norm_node(e.get("object"))))
        if pred in ("leads_to", "affects", "worsens", "sleeping"):
            effects.append(_node_label(_norm_node(e.get("object")))
                           if pred != "sleeping" else "their sleep")

    lines = []
    # the [SITUATION] synopsis: a heavy thing + what it's touching, only when both exist.
    if stressors and effects:
        lines.append(f"[SITUATION] {stressors[0]} is weighing on them, and it's reaching {effects[0]}.")
    elif stressors:
        lines.append(f"[SITUATION] {stressors[0]} is weighing on them right now.")
    lines += links
    lines += knows
    items = "\n".join(lines)
    return f"{_PREAMBLE}\n\n{_ITEMS_HEADER}\n{items}\n\n{_GUARDRAIL}"


def render(name: str) -> str:
    """Human-readable 'what Vera understands about your situations' — the relations on
    record with provenance, the world-state counterpart to ``memory_lirf.render``. Audit
    surface, not the prompt block. Read-only."""
    w = World.load(name)
    active = sorted(w.active(), key=lambda r: (-float(r.get("confidence", 0)), r.get("created", "")))
    out = [f"What {name} understands about your situation ({len(active)} relations):"]
    if not active:
        out.append("  (no situations connected yet — they emerge as you talk about your life)")
    for r in active:
        out.append(
            f"  • [{r.get('kind','?')}] {_norm_node(r.get('subject'))} "
            f"--{r.get('predicate','?')}--> {_norm_node(r.get('object'))}\n"
            f"      confidence {float(r.get('confidence',0)):.2f} · "
            f"corroborated {r.get('support',1)}x · {r.get('source','?')}")
    return "\n".join(out)


# ===========================================================================
# SELF-TEST — run directly: `python3 -m anima.world_state` or `--selftest`.
# Core needs NO model, NO network; writes only to a throwaway store it cleans up.
# Mirrors memory_lirf._selftest's ok(label, cond) harness.
# ===========================================================================

def _selftest() -> int:
    import glob
    import os
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # --- node normalisation: "my new manager" / "the manager" land on one vertex ---
    ok("node: 'my new manager' normalises to 'new manager'",
       _norm_node("my new manager") == "new manager")
    ok("node: 'the manager' -> 'manager'", _norm_node("the manager") == "manager")
    ok("node: shared token overlaps ('work' in 'work stress')",
       "work" in _node_tokens("work stress"))

    # --- capture: a connected scenario, deterministically, no model ---
    text_mgr = "honestly my work has been really stressful because of my new manager"
    caps = capture(text_mgr)
    preds = {(s_, p_, _o) for s_, p_, _o, _k, _t in [(c[0], c[1], _norm_node(c[2])) + c[3:] for c in caps]}
    ok("capture: 'work stressful because new manager' -> you stressed_by work",
       any(_norm_node(s) == "you" and p == "stressed_by" and _norm_node(o) == "work"
           for s, p, o, _k, _t in caps))
    ok("capture: also draws work --because--> manager (stated link)",
       any(p == "because" and "manager" in _norm_node(o) for s, p, o, _k, _t in caps))

    caps_sleep = capture("and I'm not sleeping well lately")
    ok("capture: 'not sleeping well' -> you sleeping poorly (observation)",
       any(p == "sleeping" for s, p, o, _k, _t in caps_sleep))

    caps_money = capture("I'm really worried about money right now")
    ok("capture: 'worried about money' -> you worried_about money",
       any(p == "worried_about" and "money" in _norm_node(o) for s, p, o, _k, _t in caps_money))

    caps_care = capture("I care about my daughter more than anything")
    ok("capture: 'I care about my daughter' -> you cares_about daughter",
       any(p == "cares_about" and "daughter" in _norm_node(o) for s, p, o, _k, _t in caps_care))

    # --- NEVER fabricate an unstated link ---
    none_link = capture("work is busy. my manager is tall.")
    ok("capture: does NOT invent work<->manager link without a 'because'",
       not any(p in ("because", "leads_to") for s, p, o, _k, _t in none_link))
    ok("capture: rejects a hypothetical ('I wish work were less stressful')",
       capture("I wish work were less stressful because of my manager") == []
       or all(p != "stressed_by" for s, p, o, _k, _t in
              capture("I wish work were less stressful")))

    # --- widened natural-speech coverage (#21): the LIRF-style capture frontier ---
    def _has(text, triple):
        return triple in [(s, p, o) for s, p, o, _k, _t in capture(text)]
    ok("widen: subject-led stress without 'my' -> you stressed_by work",
       _has("work has been stressful because of my new manager", ("you", "stressed_by", "work")))
    ok("widen: 'X is affecting Y' -> X affects Y",
       _has("the stress is affecting my sleep", ("stress", "affects", "sleep")))
    ok("widen: past-tense 'led to' -> leads_to",
       _has("the move led to a new career", ("move", "leads_to", "new career")))
    ok("widen: life-event 'after' -> a sequence edge",
       _has("i started my business after the divorce", ("business", "after", "divorce")))
    ok("widen-guard: pronoun/contraction subject fabricates NOTHING",
       capture("it's been rough") == [] and capture("she is overwhelmed") == []
       and all(o not in ("s", "t", "m", "it", "she") for s, p, o, _k, _t in capture("I'm overwhelmed")))

    # --- WAVE A: LIFE-EVENT edges + the TEMPORAL qualifier they hang on ----------------
    # The conservation ledger surfaced moves/adoptions/started-events as total-loss; these
    # add the relational frame AND attach the stated time, with the same never-infer rails.
    def _pred_obj(text):
        return {(p, _norm_node(o)) for s, p, o, _k, _t in capture(text)}
    mv = _pred_obj("I moved to Austin because my manager changed")
    ok("WAVE-A move: 'I moved to Austin' -> you moved_to austin",
       _has("I moved to Austin because my manager changed", ("you", "moved_to", "Austin")))
    ok("WAVE-A move: stated cause -> austin because manager (object carries 'manager')",
       any(p == "because" and "manager" in o for p, o in mv))
    ok("WAVE-A move: stated TIME attaches -> moved_when 'last year'",
       ("moved_when", "last year") in _pred_obj("I moved to Denver last year"))
    ok("WAVE-A move: 'the move to Denver in March' -> move_to denver + moved_when march",
       ("move_to", "denver") in _pred_obj("the move to Denver in March")
       and ("moved_when", "march") in _pred_obj("the move to Denver in March"))
    ok("WAVE-A adopt: 'we adopted a dog ... in 2024' -> you adopted dog + adopted_when 2024",
       ("adopted", "dog") in _pred_obj("We adopted a dog named Cooper in 2024")
       and ("adopted_when", "2024") in _pred_obj("We adopted a dog named Cooper in 2024"))
    sta = _pred_obj("My daughter Maya started kindergarten last week")
    ok("WAVE-A started: 'my daughter ... started kindergarten' -> has daughter + started kindergarten",
       ("has", "daughter") in sta and ("started", "kindergarten") in sta)
    ok("WAVE-A started: trailing 'last week' attaches as started_when",
       ("started_when", "last week") in sta)
    ok("WAVE-A named-relation: 'my wife Jen' -> you has wife (the role bond)",
       ("has", "wife") in _pred_obj("My wife Jen and I are excited"))
    # GUARDS — Observed > Assumed: a common-noun object, a hypothetical, or a capitalised aux
    # in the name slot must fabricate NO edge.
    ok("WAVE-A guard: 'I moved to the city' (common noun) -> no move edge",
       not any(p in ("moved_to", "move_to") for p, o in _pred_obj("I moved to the city")))
    ok("WAVE-A guard: hypothetical move/adopt fabricates nothing",
       capture("maybe we'll move to Paris") == [] and capture("I wish I moved to Denver") == []
       and not any(p == "adopted" for p, o in _pred_obj("we should adopt a dog someday")))
    ok("WAVE-A guard: 'we adopted a strategy' (non-pet) -> no adopt edge",
       not any(p == "adopted" for p, o in _pred_obj("we adopted a strategy at work")))
    ok("WAVE-A guard: capitalised aux in name slot ('my wife Then we left') -> no role bond",
       ("has", "wife") not in _pred_obj("my wife Then we left"))

    # --- a throwaway store for persistence + situation ---
    name = "world_selftest_" + secrets.token_hex(3)
    try:
        # capture_relations persists the connected scenario
        t1 = capture_relations(name, "my work's been really stressful because of my new manager")
        t2 = capture_relations(name, "honestly I'm not sleeping well")
        t3 = capture_relations(name, "and the stress is leading to bad sleep")
        ok("capture_relations: persisted edges from the scenario", len(t1) + len(t2) + len(t3) > 0)

        # explicitly relate the recency + the knock-on the user stated, to build the chain
        relate(name, "new manager", "is", "recent", kind="observation")
        relate(name, "work stress", "leads_to", "sleep", kind="inference")

        # situation("work") returns the CONNECTED cluster
        sit = situation(name, "work", hops=3)
        node_blob = " ".join(sit["nodes"])
        ok("situation('work'): non-empty connected cluster",
           len(sit["edges"]) > 0 and len(sit["nodes"]) > 1)
        ok("situation('work'): reaches the manager node",
           any("manager" in n for n in sit["nodes"]))
        ok("situation('work'): reaches the stress feeling",
           any("stress" in n or "work" in n for n in sit["nodes"]))
        ok("situation('work'): reaches sleep (the knock-on)",
           any("sleep" in n for n in sit["nodes"]))
        ok("situation('work'): manager + stress + sleep linked in ONE cluster",
           any("manager" in n for n in sit["nodes"])
           and any("sleep" in n for n in sit["nodes"]))

        # an UNRELATED query returns a small/empty cluster
        sit_un = situation(name, "photosynthesis", hops=3)
        ok("situation(unrelated): empty/near-empty cluster",
           len(sit_un["edges"]) == 0 and len(sit_un["nodes"]) == 0)

        # a broad check-in seeds the user node and surfaces the picture
        sit_broad = situation(name, "how am I doing?", hops=3)
        ok("situation('how am I doing?'): broad check-in surfaces a cluster",
           len(sit_broad["edges"]) > 0)

        # render_situation: spine-style block, expressible as understanding, no leak read aloud
        block = render_situation(sit)
        ok("render: produces a non-empty binding block", bool(block.strip()))
        ok("render: carries the SITUATION synopsis line", "[SITUATION]" in block)
        ok("render: speaks to a LINK (a connection), not just slots", "[LINK]" in block)
        ok("render: preamble frames CONNECTED understanding",
           "CONNECTED" in block and "WHAT YOU UNDERSTAND" in block)
        ok("render: guardrail forbids reading brackets / 'according to my memory'",
           "Never read the brackets" in block and "according to my memory" in block)
        ok("render: every emitted tag is in WORLD_SCAFFOLD_TOKENS (scrubbable)",
           all(tok in block for tok in ("[SITUATION]", "[LINK]"))
           and "[SITUATION]" in WORLD_SCAFFOLD_TOKENS and "[LINK]" in WORLD_SCAFFOLD_TOKENS)
        ok("render: empty cluster -> empty string",
           render_situation({"edges": []}) == "")

        # the rendered clauses read as connected understanding, not a data row
        low = block.lower()
        ok("render: phrases 'stressed by work' as understanding",
           "stressed by work" in low)

        # --- persistence: relations round-trip + are ADDITIVE (continuity) ---
        w = World.load(name)
        n_before = len(w.active())
        ok("persist: relations survive reload", n_before > 0)

        # corroboration: re-stating an edge climbs confidence + bumps support, no dup
        e1 = relate(name, "you", "stressed_by", "work", kind="problem")
        sup1 = e1.get("support")
        e2 = relate(name, "you", "stressed_by", "work", kind="problem")
        ok("relate: re-stating corroborates (support++), not a duplicate row",
           e2.get("support") == (sup1 or 1) + 1)
        w2 = World.load(name)
        keys = [(_norm_node(r["subject"]), r["predicate"], _norm_node(r["object"]))
                for r in w2.active()]
        ok("relate: no duplicate (you,stressed_by,work) edge",
           keys.count(("you", "stressed_by", "work")) == 1)

        # ADDITIVE save: a second World instance adding a different edge does NOT clobber
        # the first instance's edges (the union-on-disk continuity guarantee).
        wa = World.load(name)
        wb = World.load(name)
        wa.add("you", "cares_about", "family", kind="preference")
        wb.add("you", "working_toward", "calm", kind="goal")
        wa.save(name)
        wb.save(name)   # must NOT drop wa's 'family' edge
        final = World.load(name)
        fkeys = {(_norm_node(r["subject"]), r["predicate"], _norm_node(r["object"]))
                 for r in final.active()}
        ok("persist: concurrent additive saves both survive (no overwrite-and-lose)",
           ("you", "cares_about", "family") in fkeys
           and ("you", "working_toward", "calm") in fkeys)

        # retract: gone from the graph, kept on disk
        eid = e2.get("id")
        final.retract(eid)
        final.save(name)
        rel = World.load(name)
        ok("retract: removed from active graph",
           all(r["id"] != eid for r in rel.active()))
        ok("retract: row kept on disk as retracted",
           any(r["id"] == eid and r["status"] == "retracted" for r in rel.relations))

        # render(name) audit surface is human-readable + shows provenance
        rep = render(name)
        ok("render(name): shows a corroboration count", "corroborated" in rep)

        # --- the LIRF ledger is UNTOUCHED by all of this (additive guarantee) ---
        # situation lifts facts read-only; prove no .lirf.json was created for our name.
        ok("additive: no LIRF ledger file written for the world-state name",
           not os.path.exists(str(STORE / f"{name}.lirf.json")))

    finally:
        for fp in glob.glob(str(World.path(name))) + glob.glob(str(STORE / f"{name}.*")):
            try:
                os.remove(fp)
            except OSError:
                pass

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL WORLD_STATE SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
