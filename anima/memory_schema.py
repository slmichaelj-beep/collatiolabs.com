"""
memory_schema — the single, canonical memory object EVERY subsystem uses.

This is the universal contract for the moonshot substrate. The hard rule: **no
organ, no engine, no telemetry sink ever invents its own memory format.** When an
organ wants to contribute something it knows — a mood, a value, a bond, a scored
option — it builds exactly THIS object via `make()` and nothing else. The event
bus carries it, the Coordinator reasons over it, telemetry records its id, and the
LIRF ledger persists it. One object, one shape, end to end.

The shape is founder-fixed (10 keys, exact):

    id          str    — "f_" + token_hex(6)            (reuse memory_lirf._new_id)
    type        str    — fact|value|relationship|narrative|agency
    subject     str    — entity it's ABOUT  (SELF="you", or "vera", "mom", …)
    predicate   str    — the trait/relation slug         (canon_trait-normalised)
    value       Any    — the asserted value              (str | list | scalar)
    confidence  float  — 0.0..1.0, closed interval, validated
    sources     list   — provenance: where it came from  ("chat 2026-06-03", organ)
    support     list   — corroboration: evidence ids that back it (≥0)
    updated     str    — ISO8601-Z                       (reuse memory_lirf._now)
    lirf        str    — one-line human rendering        (cached output of to_lirf)

Why a SEPARATE module from memory_lirf (and not just its row dict): memory_lirf is
the *ledger* — capture, merge, history, lookup, all tied to its on-disk row with an
`entity`/`trait`/`support:int` shape and an append-only `history[]`. This module is
the *interlingua* spoken on the bus. The two are bridged, not merged:

  * `from_lirf_row(row)`     maps a live ledger row  → canonical Memory
  * `to_lirf_candidate(mem)` maps a canonical Memory → the `cand` LIRF.merge() eats

The one real friction — the founder's `support` is a LIST (corroborating evidence
ids) while a live LIRF row's `support` is an INT count — is reconciled HERE, at the
boundary, with zero change forced on the ledger's on-disk format: `from_lirf_row`
expands the int into a list of synthetic corroboration ids; `to_lirf_candidate`
collapses back to what merge() expects. The ledger stays exactly as it is on disk.

Anchored to existing conventions: reuses `memory_lirf._now` / `_new_id` / `SELF` /
`canon_trait`; serialises with stdlib json (persisted by callers via `util.save_json`,
atomic + optionally sealed). `validate()` returns the same `(ok, reason)` tuple shape
as `identity.validate()`. Dependency-light, local, importable in isolation.
"""

from __future__ import annotations

import json
from datetime import datetime

# Canonical helpers live in memory_lirf — reuse them so the ledger and the bus speak
# the SAME id/timestamp/entity/slug vocabulary. Fall back to identical local copies
# only when imported standalone (e.g. `python3 anima/memory_schema.py --selftest`,
# where the package-relative import isn't on the path); the fallbacks are byte-for-byte
# the same logic, so behaviour is identical either way.
try:  # pragma: no cover - exercised both ways depending on entry point
    from .memory_lirf import _new_id, _now, canon_trait, SELF
except Exception:  # pragma: no cover
    import re as _re
    import secrets as _secrets
    from datetime import timezone as _timezone

    SELF = "you"

    def _now() -> str:
        return (
            datetime.now(_timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _new_id() -> str:
        return "f_" + _secrets.token_hex(6)

    def canon_trait(trait: str) -> str:
        return _re.sub(r"[^a-z0-9]+", "_", str(trait).strip().lower()).strip("_")


SCHEMA_VERSION = 1

# The closed set of memory types. A type outside this set fails validate() — it means
# some organ tried to speak a dialect the substrate doesn't know.
TYPES = ("fact", "value", "relationship", "narrative", "agency")

# The exact 10 keys, in canonical order. validate() requires precisely these — no
# more (a stray key is a format leak), no fewer (a missing key is an incomplete object).
KEYS = (
    "id",
    "type",
    "subject",
    "predicate",
    "value",
    "confidence",
    "sources",
    "support",
    "updated",
    "lirf",
)


# ---------------------------------------------------------------------------
# Construction — the ONE blessed constructor. Organs call this, never a literal.
# ---------------------------------------------------------------------------

def make(
    *,
    type: str,
    subject: str,
    predicate: str,
    value,
    confidence: float,
    sources: list | None = None,
    support: list | None = None,
    id: str | None = None,
    updated: str | None = None,
) -> dict:
    """Build a canonical Memory.

    Fills `id` (_new_id), `updated` (_now), and empty lists where omitted; canonicalises
    `predicate` through `canon_trait`; clamps `confidence` into [0,1]; and ALWAYS sets
    `lirf = to_lirf(mem)` last so that field is never stale relative to the data.

    This is the only blessed constructor. Every organ's `_emit` funnels through here,
    which is what guarantees that everything on the bus is schema-valid by construction
    and that telemetry can always read a real `id`.
    """
    pred = canon_trait(predicate) if predicate is not None else ""
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        conf = 0.0
    # Closed-interval clamp: a contributor can't smuggle in 1.4 or -0.2.
    if conf < 0.0:
        conf = 0.0
    elif conf > 1.0:
        conf = 1.0

    mem = {
        "id": id or _new_id(),
        "type": str(type),
        "subject": str(subject),
        "predicate": pred,
        "value": value,
        "confidence": conf,
        # New lists every call — never alias a caller-passed list into the object.
        "sources": list(sources) if sources else [],
        "support": list(support) if support else [],
        "updated": updated or _now(),
        "lirf": "",  # set just below, so the cache reflects the final field values
    }
    mem["lirf"] = to_lirf(mem)
    return mem


# ---------------------------------------------------------------------------
# Validation — same (ok, reason) contract as identity.validate().
# ---------------------------------------------------------------------------

def _is_iso8601(s) -> bool:
    """True iff `s` parses as an ISO8601 timestamp. Accepts the `_now()` 'Z' form by
    normalising a trailing 'Z' to '+00:00' (Python <3.11 fromisoformat rejects 'Z')."""
    if not isinstance(s, str) or not s:
        return False
    probe = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        datetime.fromisoformat(probe)
        return True
    except ValueError:
        return False


def validate(mem: dict) -> tuple[bool, str]:
    """(ok, reason). Enforce the founder shape exactly.

    Checks, in order: it's a dict; it has *precisely* the 10 keys; types are correct;
    `type` is in the closed TYPES set; `confidence` is a real number in [0,1];
    `sources`/`support` are lists of str; `subject`/`predicate` are non-empty;
    `updated` parses as ISO8601. Same tuple shape as `identity.validate()` so callers
    can treat any validator uniformly.
    """
    if not isinstance(mem, dict):
        return (False, "not a memory dict")

    have = set(mem.keys())
    want = set(KEYS)
    missing = want - have
    if missing:
        return (False, "missing keys: " + ", ".join(sorted(missing)))
    extra = have - want
    if extra:
        return (False, "unexpected keys: " + ", ".join(sorted(extra)))

    if not isinstance(mem["id"], str) or not mem["id"]:
        return (False, "id must be a non-empty str")
    if not isinstance(mem["type"], str):
        return (False, "type must be a str")
    if mem["type"] not in TYPES:
        return (False, f"type must be one of {TYPES}, got {mem['type']!r}")
    if not isinstance(mem["subject"], str) or not mem["subject"].strip():
        return (False, "subject must be a non-empty str")
    if not isinstance(mem["predicate"], str) or not mem["predicate"].strip():
        return (False, "predicate must be a non-empty str")

    # confidence: a real number (reject bool, which is an int subclass) in [0,1].
    conf = mem["confidence"]
    if isinstance(conf, bool) or not isinstance(conf, (int, float)):
        return (False, "confidence must be a float")
    if not (0.0 <= float(conf) <= 1.0):
        return (False, f"confidence out of [0,1]: {conf}")

    for field in ("sources", "support"):
        seq = mem[field]
        if not isinstance(seq, list):
            return (False, f"{field} must be a list")
        if not all(isinstance(x, str) for x in seq):
            return (False, f"{field} must be a list of str")

    if not _is_iso8601(mem["updated"]):
        return (False, f"updated not ISO8601: {mem['updated']!r}")

    if not isinstance(mem["lirf"], str):
        return (False, "lirf must be a str")

    return (True, "ok")


# ---------------------------------------------------------------------------
# Rendering — the canonical one-line view. The `lirf` field caches this.
# ---------------------------------------------------------------------------

def _fmt_value(v) -> str:
    """Compact, readable rendering of a value (lists become 'a, b, c')."""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def to_lirf(mem: dict) -> str:
    """The canonical single-line rendering of a Memory, e.g.

        you · birthday = 1990-06-11  (conf 0.97, x3)

    Deterministic and lossy-but-readable: this is the string injected into a prompt
    memory-block and shown verbatim in telemetry. The `lirf` FIELD on the object caches
    exactly this output (set by `make`), so renders are stable and never recomputed mid-flight.

    Built defensively (plain `.get`) so it can render a partially-formed dict for a
    telemetry/debug line even before `validate()` would pass.
    """
    subject = mem.get("subject", "?")
    predicate = mem.get("predicate", "?")
    value = _fmt_value(mem.get("value", ""))
    conf = mem.get("confidence", 0.0)
    try:
        conf_s = f"{float(conf):.2f}"
    except (TypeError, ValueError):
        conf_s = str(conf)
    times = len(mem.get("support") or [])
    tail = f"  (conf {conf_s}, x{times})" if times else f"  (conf {conf_s})"
    return f"{subject} · {predicate} = {value}{tail}"


# ---------------------------------------------------------------------------
# Serialisation — stdlib json; callers persist via util.save_json (atomic+sealed).
# ---------------------------------------------------------------------------

def to_json(mem: dict) -> str:
    """Serialise to a JSON string. Sorted keys + UTF-8 passthrough for stable, diffable
    output. Persisted to disk by callers through `util.save_json` (atomic, optionally
    encrypted) — this function never touches the filesystem itself."""
    return json.dumps(mem, ensure_ascii=False, sort_keys=True)


def from_json(s: str) -> dict:
    """Parse a JSON string into a Memory and validate it. Raises ValueError on malformed
    JSON or on a payload that doesn't satisfy the schema — a bad memory must never enter
    the system silently."""
    try:
        mem = json.loads(s)
    except (ValueError, TypeError) as e:
        raise ValueError(f"memory_schema.from_json: malformed JSON: {e}") from e
    ok, why = validate(mem)
    if not ok:
        raise ValueError(f"memory_schema.from_json: invalid memory: {why}")
    return mem


# ---------------------------------------------------------------------------
# Bridge to the live ledger — so LIRF rows ARE canonical Memories, round-trippable.
# ---------------------------------------------------------------------------

# Map a LIRF row's type-less shape onto a canonical `type`. The ledger captures USER
# facts; a row about a non-SELF entity is a relationship, everything else is a fact.
def _infer_type(row: dict) -> str:
    subject = row.get("entity", SELF)
    if subject and subject != SELF:
        return "relationship"
    return "fact"


def from_lirf_row(row: dict) -> dict:
    """Map a live `memory_lirf` row → canonical Memory.

        entity      -> subject
        trait       -> predicate
        value       -> value
        confidence  -> confidence
        [source]    -> sources           (singular str promoted to a 1-element list)
        support:int -> support:list      (int count expanded to synthetic corro*ids*)
        updated     -> updated

    The support-int→list expansion is the reconciliation the founder spec calls out:
    a row corroborated N times becomes N synthetic ids derived from the row id
    (`{id}#c0 … {id}#c{N-1}`), so the canonical object carries a real *list* without
    forcing the ledger to start tracking evidence ids on disk today. When LIRF later
    tracks real evidence ids, this is the one function that changes. The `id` is reused
    so the SAME memory is addressable in both worlds, and `lirf` is freshly stamped.
    """
    rid = row.get("id") or _new_id()

    src = row.get("source")
    sources = [src] if isinstance(src, str) and src else (list(src) if isinstance(src, list) else [])

    raw_support = row.get("support", 0)
    try:
        n = int(raw_support)
    except (TypeError, ValueError):
        n = 0
    if n < 0:
        n = 0
    support = [f"{rid}#c{i}" for i in range(n)]

    return make(
        type=_infer_type(row),
        subject=row.get("entity", SELF) or SELF,
        predicate=row.get("trait", "") or "",
        value=row.get("value"),
        confidence=row.get("confidence", 0.0),
        sources=sources,
        support=support,
        id=rid,
        updated=row.get("updated"),
    )


def to_lirf_candidate(mem: dict) -> dict:
    """Inverse of `from_lirf_row`: canonical Memory → the `cand` dict `LIRF.merge()`
    expects.

    merge() reads: {entity, trait, value, source, evidence, correction?}. This is how an
    Observation's payload gets persisted into the ledger: an organ emits a Memory onto
    the bus, and when the Coordinator elects to remember it, THIS adapter hands it to
    `LIRF.merge()`. The support *list* is collapsed back — merge() owns the int count and
    re-derives it on fold — so no second format crosses the boundary.

        subject       -> entity
        predicate     -> trait
        value         -> value
        sources[0]    -> source           (first provenance entry; merge defaults if empty)
        sources[1:]   -> evidence         (carried as a readable provenance trail)
    """
    sources = mem.get("sources") or []
    source = sources[0] if sources else ""
    # Anything beyond the primary source is carried as the verbatim-evidence trail the
    # ledger stores; join so merge()'s single `evidence` string field stays satisfied.
    evidence = "; ".join(sources[1:]) if len(sources) > 1 else ""
    cand = {
        "entity": mem.get("subject", SELF),
        "trait": mem.get("predicate", ""),
        "value": mem.get("value"),
        "source": source,
        "evidence": evidence,
    }
    return cand


# ---------------------------------------------------------------------------
# Self-test — proves the component in isolation. Mirrors memory_lirf._selftest's
# `ok(label, cond)` harness exactly. Run: python3 anima/memory_schema.py --selftest
# ---------------------------------------------------------------------------

def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # --- make(): produces the exact 10-key founder shape, valid by construction ---
    m = make(
        type="value",
        subject="you",
        predicate="Current Mood",  # deliberately messy: must canonicalise
        value="warm",
        confidence=0.3,
        sources=["stub"],
        support=[],
    )
    ok("make: exactly the 10 founder keys", set(m.keys()) == set(KEYS))
    ok("make: id is f_-prefixed", isinstance(m["id"], str) and m["id"].startswith("f_"))
    ok("make: predicate canon_trait-normalised", m["predicate"] == "current_mood")
    ok("make: updated is ISO8601-Z", _is_iso8601(m["updated"]) and m["updated"].endswith("Z"))
    ok("make: lirf field is non-empty + equals to_lirf(m)", m["lirf"] and m["lirf"] == to_lirf(m))
    ok("make: validate() passes on a freshly-made memory", validate(m)[0])
    ok("make: fresh lists not aliased", m["sources"] == ["stub"] and m["support"] == [])

    # --- confidence is clamped into the closed interval [0,1] ---
    hi = make(type="fact", subject="you", predicate="x", value=1, confidence=1.4)
    lo = make(type="fact", subject="you", predicate="x", value=1, confidence=-0.5)
    ok("make: confidence > 1 clamped to 1.0", hi["confidence"] == 1.0)
    ok("make: confidence < 0 clamped to 0.0", lo["confidence"] == 0.0)

    # --- validate(): rejects every way a memory can be malformed ---
    ok("validate: rejects non-dict", validate(["not", "a", "dict"])[0] is False)

    bad_missing = dict(m)
    del bad_missing["lirf"]
    ok("validate: rejects missing key", validate(bad_missing)[0] is False)

    bad_extra = dict(m)
    bad_extra["sneaky"] = 1
    ok("validate: rejects unexpected key (format leak)", validate(bad_extra)[0] is False)

    bad_type = dict(m); bad_type["type"] = "vibe"
    ok("validate: rejects type outside closed set", validate(bad_type)[0] is False)

    bad_conf = dict(m); bad_conf["confidence"] = 1.5
    ok("validate: rejects confidence out of [0,1]", validate(bad_conf)[0] is False)

    bad_bool = dict(m); bad_bool["confidence"] = True
    ok("validate: rejects bool confidence", validate(bad_bool)[0] is False)

    bad_src = dict(m); bad_src["sources"] = [1, 2, 3]
    ok("validate: rejects non-str in sources", validate(bad_src)[0] is False)

    bad_sup = dict(m); bad_sup["support"] = "x3"
    ok("validate: rejects non-list support", validate(bad_sup)[0] is False)

    bad_subj = dict(m); bad_subj["subject"] = "   "
    ok("validate: rejects blank subject", validate(bad_subj)[0] is False)

    bad_pred = dict(m); bad_pred["predicate"] = ""
    ok("validate: rejects blank predicate", validate(bad_pred)[0] is False)

    bad_time = dict(m); bad_time["updated"] = "yesterday"
    ok("validate: rejects non-ISO8601 updated", validate(bad_time)[0] is False)

    good = validate(m)
    ok("validate: accepts a good memory with reason 'ok'", good == (True, "ok"))

    # --- to_lirf(): deterministic, shows subject/predicate/value/conf/support count ---
    m3 = make(type="fact", subject="you", predicate="birthday", value="1990-06-11",
              confidence=0.97, sources=["chat"], support=["e1", "e2", "e3"])
    line = to_lirf(m3)
    ok("to_lirf: contains subject/predicate/value", "you" in line and "birthday" in line and "1990-06-11" in line)
    ok("to_lirf: shows confidence", "0.97" in line)
    ok("to_lirf: shows support count x3", "x3" in line)
    ok("to_lirf: deterministic (same input -> same output)", to_lirf(m3) == line)
    ok("to_lirf: list value rendered comma-joined",
       "a, b" in to_lirf(make(type="fact", subject="you", predicate="likes",
                              value=["a", "b"], confidence=0.5)))

    # --- to_json / from_json round-trip, and from_json rejects bad input ---
    s = to_json(m)
    back = from_json(s)
    ok("json: round-trips to an equal memory", back == m)
    ok("json: from_json raises on malformed JSON",
       _raises(lambda: from_json("{not json")))
    ok("json: from_json raises on schema-invalid payload",
       _raises(lambda: from_json(json.dumps({"id": "f_x", "type": "fact"}))))

    # --- bridge: LIRF row -> Memory, the support int->list reconciliation ---
    row = {
        "id": "f_abc123",
        "entity": "you",
        "trait": "birthday",
        "value": "June 11",
        "confidence": 0.93,
        "support": 3,            # INT in the live ledger
        "source": "chat 2026-06-03",
        "updated": "2026-06-03T12:00:00Z",
    }
    fm = from_lirf_row(row)
    ok("from_lirf_row: result is schema-valid", validate(fm)[0])
    ok("from_lirf_row: reuses the row id (same memory both worlds)", fm["id"] == "f_abc123")
    ok("from_lirf_row: entity->subject, trait->predicate",
       fm["subject"] == "you" and fm["predicate"] == "birthday")
    ok("from_lirf_row: source(str)->sources(list)", fm["sources"] == ["chat 2026-06-03"])
    ok("from_lirf_row: support int(3)->list of 3 corroboration ids",
       isinstance(fm["support"], list) and len(fm["support"]) == 3)
    ok("from_lirf_row: synthetic ids derive from row id", fm["support"][0] == "f_abc123#c0")
    ok("from_lirf_row: third-party entity -> type 'relationship'",
       from_lirf_row({**row, "entity": "mom"})["type"] == "relationship")

    # --- bridge: Memory -> cand dict that merge() expects (support list collapsed) ---
    cand = to_lirf_candidate(fm)
    ok("to_lirf_candidate: has the keys merge() reads",
       {"entity", "trait", "value", "source"} <= set(cand.keys()))
    ok("to_lirf_candidate: subject->entity, predicate->trait",
       cand["entity"] == "you" and cand["trait"] == "birthday")
    ok("to_lirf_candidate: sources[0]->source", cand["source"] == "chat 2026-06-03")
    ok("to_lirf_candidate: support list does NOT leak into cand", "support" not in cand)

    # --- the load-bearing round-trip: row -> Memory -> cand preserves the essentials ---
    ok("round-trip: row -> Memory -> cand keeps entity/trait/value",
       cand["entity"] == row["entity"] and cand["trait"] == row["trait"]
       and cand["value"] == row["value"])

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print(f"ALL MEMORY_SCHEMA SELFTESTS PASS ({_PASS_COUNT[0]} checks)")
    return 0


# tiny helpers used only by the self-test
_PASS_COUNT = [0]


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


if __name__ == "__main__":
    import sys

    # count total checks for the summary line by wrapping print of "ok"/"FAIL"
    _orig = print

    def _counting_print(*a, **k):  # noqa: ANN001
        if a and isinstance(a[0], str) and (a[0].startswith("  ok") or a[0].startswith("  FAIL")):
            _PASS_COUNT[0] += 1
        _orig(*a, **k)

    import builtins as _b
    _b.print = _counting_print
    try:
        rc = _selftest()
    finally:
        _b.print = _orig
    sys.exit(rc)
