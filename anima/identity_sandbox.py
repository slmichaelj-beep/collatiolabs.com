"""
identity_sandbox — a CAMERA pointed at Vera's identity layer, never a hand that edits it.

WHY THIS EXISTS (Amendment 2 — "observe first, change later")
--------------------------------------------------------------
Vera's identity layer is FROZEN (Program B): the per-creature ``identity_agency``
capability is OFF by default (anima/caps.py), the Identity & Agency organs are held
DORMANT (anima/organs/identity.py · agency.py), and no subsystem may reshape who she
is until the founder lifts the freeze. The risk of a freeze is that when it eventually
lifts, you reach for the controls with NO instruments — you would be changing identity
blind. So we build the instruments NOW, while the thing they watch stays untouched, so
that the moment the freeze lifts we already have a black-box recorder, a versioned
ledger, replay, diff, a tested rollback capability, and an invariant certifier ready.

THE HARD RULE (the whole point)
-------------------------------
Every instrument here OBSERVES identity; none CHANGES real identity. Concretely:

  * SHADOW-ONLY STORE. The sandbox writes ONLY under ``.anima/identity_sandbox/`` —
    never a real ``Vera.*`` identity file. Reading real identity is allowed (that is
    the camera); writing it is not. The six real identity files this module may READ
    are exactly the portable identity CORE (anima/identity.py): ``{name}.dials.json``,
    ``{name}.persona.md``, ``{name}.values.json``, ``{name}.portrait.md``, plus
    ``{name}.narrative.txt`` (self-narrative) and ``{name}.continuity.jsonl`` (LAW 001
    ledger). It NEVER opens them for writing and NEVER calls identity.import_bundle.

  * DEFAULT-INERT. Nothing here runs in the production turn. It is a tool + a CLI you
    invoke deliberately; the live server never imports a write path from it.

  * ROLLBACK IS GUARDED. The one instrument that CAN restore identity refuses, by
    construction, to act on real identity: ``_assert_synthetic_target`` raises unless
    the target is a SYNTHETIC creature in a REDIRECTED (non-real) store. So rollback is
    a real, tested CAPABILITY that is INERT for real Vera while the freeze holds.

  * SYNTHETIC TESTS ONLY. The selftest builds identity states from thin air in a
    TemporaryDirectory; it never reads real Vera identity for the purpose of mutating
    it, and asserts (by a before/after content-hash of the real .anima) that the real
    store is byte-UNCHANGED.

THE SIX INSTRUMENTS
-------------------
  1. IDENTITY MRI            — record identity-relevant EVENTS (a load/reference of the
                               self-model or values). Observe only; append to a shadow log.
  2. IDENTITY LEDGER         — append-only, versioned snapshots of what the identity STATE
                               IS at each point. Self-healing load (a torn line never loses
                               the whole ledger — Unknown > Lost).
  3. IDENTITY REPLAY         — reconstruct the identity state AT a past ledger point.
  4. IDENTITY DIFF           — field-by-field change between two ledger points.
  5. IDENTITY ROLLBACK       — the CAPABILITY to restore identity to a prior snapshot.
                               Built + tested on SYNTHETIC states; guarded INERT for real Vera.
  6. IDENTITY CERTIFICATION  — certify identity INVARIANTS hold WITHOUT changing anything:
                               the #1 rule (no broken-character / ungrounded self-narrative in
                               the persona+narrative), the self-model stays grounded, the
                               portable core is well-formed. Reuses anima/self_narrative.py.

Pure-ish and dependency-light: standard library + (optionally) anima.identity,
anima.self_narrative, anima.constitution, anima.caps. Every cross-import is behind
try/except with a faithful fallback so the module imports anywhere. Importing it has
NO side effects and touches NO real identity file.

    python3 -m anima.identity_sandbox --selftest      # hermetic, synthetic-only, exits 0
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import secure_store

# The real creature store. The SANDBOX never writes a real identity file in here; it
# writes only under SANDBOX_DIR (a subtree). Overridable for tests via the env var the
# rest of anima honours, so a redirected store fully relocates the sandbox too.
STORE = Path(os.environ.get("ANIMA_STORE", ".anima"))

# The shadow subtree. ALL sandbox artifacts (MRI log, ledger) live here — never beside
# the real identity files, and never named ``{name}.dials.json`` etc. A glance at the
# filesystem shows the camera's output is segregated from the thing it films.
SANDBOX_SUBDIR = "identity_sandbox"

SCHEMA = 1
KIND = "anima.identity_sandbox"

# The PORTABLE IDENTITY CORE fields (anima/identity.py): the model-INDEPENDENT "self".
# These are the fields the ledger snapshots and the diff/replay/rollback operate over.
CORE_FIELDS = ("dials", "persona", "values", "portrait", "narrative")

# The real identity files that BELONG to a creature's identity — the camera's allowed
# READ surface, and the set the selftest fingerprints to prove "byte-unchanged". Anything
# the sandbox itself writes lives under SANDBOX_SUBDIR and is excluded from this set.
IDENTITY_FILE_SUFFIXES = (
    ".dials.json", ".persona.md", ".values.json", ".portrait.md",
    ".narrative.txt", ".continuity.jsonl",
)

# Real creature names the rollback guard will NEVER act on (belt-and-suspenders on top of
# the redirected-store check). "Vera" is the live companion; the freeze is absolute for her.
REAL_CREATURES = ("Vera",)


# =====================================================================================
# REUSE the self-narrative provenance engine for CERTIFICATION. self_narrative.py is the
# pure, synthetic-only classifier that already adjudicates whether a self-referential
# statement is GROUNDED or an UNGROUNDED #1-rule break. We import it behind try/except with
# a conservative fallback (treat as "cannot certify groundedness" rather than silently pass),
# so the sandbox stays importable even if self_narrative's deps are absent — but in the real
# tree the import succeeds and certification has teeth.
# =====================================================================================
try:  # pragma: no cover - import wiring
    from . import self_narrative as _sn
    _HAVE_SN = True
except Exception:  # pragma: no cover - isolation fallback
    _sn = None  # type: ignore
    _HAVE_SN = False

try:  # pragma: no cover - import wiring
    from . import constitution as _law
    _HAVE_LAW = True
except Exception:  # pragma: no cover
    _law = None  # type: ignore
    _HAVE_LAW = False


# =====================================================================================
# Small, dependency-free helpers.
# =====================================================================================
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sandbox_root(store: Optional[Path] = None) -> Path:
    """The shadow subtree for a given store. Created lazily by writers, never by readers."""
    base = Path(store) if store is not None else STORE
    return base / SANDBOX_SUBDIR


def mri_path(name: str, store: Optional[Path] = None) -> Path:
    """Append-only IDENTITY MRI log — identity-relevant EVENTS for `name` (shadow subtree)."""
    return _sandbox_root(store) / f"{name}.identity_mri.jsonl"


def ledger_path(name: str, store: Optional[Path] = None) -> Path:
    """Append-only IDENTITY LEDGER — versioned identity STATE snapshots (shadow subtree)."""
    return _sandbox_root(store) / f"{name}.identity_ledger.jsonl"


def _canon(obj) -> str:
    """Canonical JSON for hashing/equality: sorted keys, compact, stable across runs."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _state_hash(state: dict) -> str:
    """Content hash of a normalised identity STATE — the snapshot's fingerprint."""
    return "sha256:" + hashlib.sha256(_canon(_normalize_state(state)).encode("utf-8")).hexdigest()


def _normalize_state(state: dict) -> dict:
    """A canonical view of an identity state over CORE_FIELDS only: every core field present
    (missing -> None), nothing extra. Makes hashing, diffing and equality deterministic and
    immune to incidental key order or stray non-core keys."""
    s = state or {}
    return {k: s.get(k, None) for k in CORE_FIELDS}


def _append_jsonl(path: Path, entry: dict) -> None:
    """Append one JSON object as a line, durably (O_APPEND + fsync). Creates the shadow
    subtree on demand. This is the ONLY write primitive in the module, and it writes ONLY
    under the sandbox subtree (mri_path / ledger_path) — never a real identity file."""
    secure_store.append_jsonl(path, entry)


def _read_jsonl_healing(path: Path) -> List[dict]:
    """Self-healing JSONL read (oldest->newest). A torn / unparseable line is kept as
    ``{"_unparsed": <raw>}`` rather than dropped or raising — Unknown > Lost (LAW 001):
    one corrupt snapshot never costs you the whole ledger. Missing file -> []."""
    if not path.exists():
        return []
    out: List[dict] = []
    for line in secure_store.read_jsonl_lines(path):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append({"_unparsed": line})
    return out


# =====================================================================================
# OBSERVE-ONLY READ of identity STATE. This is the camera lens. It reads the portable
# identity CORE for `name` — the model-INDEPENDENT "self" (anima/identity.py) — and returns
# it as a plain dict. It NEVER writes, and is the only place that touches real identity files,
# strictly for READING. When anima.identity is importable we delegate to its loaders (one
# source of truth); otherwise we read the core files directly. Either way: read-only.
# =====================================================================================
def read_identity_state(name: str, store: Optional[Path] = None) -> dict:
    """Snapshot what the portable identity CORE *is* for `name`, RIGHT NOW. Observe-only.

    Returns ``{dials, persona, values, portrait, narrative}``. Reads real identity files
    when they exist (the camera) but opens nothing for writing. Failures degrade to None
    on a field (Unknown > Lost) rather than raising — a reader must never crash on a missing
    or half-written identity file."""
    base = Path(store) if store is not None else STORE
    state: Dict[str, object] = {}

    # Prefer anima.identity's own loaders (single source of truth) when the store is the
    # module-default; for a redirected store we read the files directly so tests are hermetic.
    use_identity_module = False
    if store is None:
        try:  # pragma: no cover - exercised in real tree
            from . import identity as _identity  # noqa: F401
            from . import dials as _dials, portrait as _portrait
            from .mouth import load_persona as _load_persona, load_values as _load_values
            use_identity_module = True
        except Exception:
            use_identity_module = False

    if use_identity_module:
        try:
            state["dials"] = _dials.load(name)
        except Exception:
            state["dials"] = None
        try:
            state["persona"] = _load_persona(name)
        except Exception:
            state["persona"] = None
        try:
            state["values"] = _load_values(name)
        except Exception:
            state["values"] = None
        try:
            state["portrait"] = _portrait.load(name)
        except Exception:
            state["portrait"] = None
        try:
            state["narrative"] = _read_text(base / f"{name}.narrative.txt")
        except Exception:
            state["narrative"] = None
        return _normalize_state(state)

    # Direct file read (redirected/synthetic store, or identity module unavailable).
    state["dials"] = _read_json(base / f"{name}.dials.json")
    state["persona"] = _read_text(base / f"{name}.persona.md")
    state["values"] = _read_json(base / f"{name}.values.json")
    state["portrait"] = _read_text(base / f"{name}.portrait.md")
    state["narrative"] = _read_text(base / f"{name}.narrative.txt")
    return _normalize_state(state)


def _read_json(path: Path):
    try:
        if path.exists():
            return secure_store.load_json(path, None)
    except Exception:
        pass
    return None


def _read_text(path: Path):
    try:
        if path.exists():
            t = secure_store.load_text(path, "")
            return t if t.strip() else None
    except Exception:
        pass
    return None


# =====================================================================================
# THE ROLLBACK GUARD — the seatbelt that makes a restore capability freeze-safe.
# A restore is the ONE operation that would change identity. It is allowed ONLY against a
# SYNTHETIC creature in a REDIRECTED (non-real) store. Two independent conditions must BOTH
# hold, so a single mistake (wrong name OR wrong store) is caught:
#   (1) the target store must NOT be the real .anima (must be an explicitly redirected store);
#   (2) the target name must NOT be a known real creature (e.g. "Vera").
# Any violation raises FrozenIdentityError BEFORE a single byte is written. This is what
# lets rollback be a real, tested capability that is provably INERT for real Vera.
# =====================================================================================
class FrozenIdentityError(RuntimeError):
    """Raised when a mutating instrument is pointed at REAL identity while the freeze holds."""


def _is_real_store(store: Optional[Path]) -> bool:
    """True if `store` resolves to the real .anima (the live identity store). A None store
    means 'the default real store'. A path equal to STORE is the real store. Anything else
    (a TemporaryDirectory in a test) is a redirected, non-real store."""
    if store is None:
        return True
    try:
        return Path(store).resolve() == STORE.resolve()
    except Exception:
        # If we cannot prove it is NOT real, treat it as real (fail safe / fail closed).
        return True


def _assert_synthetic_target(name: str, store: Optional[Path]) -> None:
    """Refuse to mutate REAL identity. Both conditions must pass: a redirected (non-real)
    store AND a non-real creature name. This is the freeze, enforced in code rather than
    written in a comment — the rollback capability cannot touch Vera while she is frozen."""
    if _is_real_store(store):
        raise FrozenIdentityError(
            "IDENTITY ROLLBACK refused: target store is the REAL .anima. Identity is FROZEN "
            "(Program B); rollback is a tested capability that runs ONLY on a synthetic creature "
            "in a redirected store. Pass an explicit non-real `store=` to operate on synthetic state."
        )
    if name in REAL_CREATURES:
        raise FrozenIdentityError(
            f"IDENTITY ROLLBACK refused: '{name}' is a REAL creature. Even in a redirected store, "
            "the sandbox will not restore real-creature identity while the freeze holds. Use a "
            "synthetic name (e.g. 'idsbx_synthetic')."
        )


# =====================================================================================
# INSTRUMENT 1 — IDENTITY MRI. Record an identity-relevant EVENT: a moment the self-model or
# values were LOADED or REFERENCED. Observe only — it appends a line to the shadow MRI log and
# NEVER touches identity itself. The event captures WHAT was referenced and a content-hash of
# the state at that moment (so the MRI and the ledger can be cross-checked), never a mutation.
# =====================================================================================
def record_identity_event(
    name: str,
    *,
    kind: str,
    source: str = "",
    detail: Optional[dict] = None,
    state: Optional[dict] = None,
    store: Optional[Path] = None,
) -> dict:
    """Append one IDENTITY-MRI event for `name`. `kind` is the event class (e.g.
    "identity.load", "values.reference", "self_model.read"); `source` names the caller
    (e.g. "mouth.build_prompt"). If `state` is given (or readable), the event records its
    content-hash so an event can be tied to the exact identity snapshot in force. Returns the
    recorded event. WRITES ONLY the shadow MRI log — never a real identity file."""
    snap = state if state is not None else read_identity_state(name, store=store)
    event = {
        "kind": KIND + ".event",
        "schema": SCHEMA,
        "at": _now_iso(),
        "name": name,
        "event": str(kind),
        "source": str(source or ""),
        "state_hash": _state_hash(snap) if snap is not None else "",
    }
    if detail:
        event["detail"] = detail
    _append_jsonl(mri_path(name, store), event)
    return event


def read_identity_events(name: str, store: Optional[Path] = None) -> List[dict]:
    """Read back the IDENTITY-MRI events (oldest->newest), self-healing on torn lines."""
    return _read_jsonl_healing(mri_path(name, store))


# =====================================================================================
# INSTRUMENT 2 — IDENTITY LEDGER. An append-only, versioned record of what the identity STATE
# IS at each point in time: a snapshot of the self-model, not an event. Each entry carries a
# monotonically increasing version, the full normalised core state, its content-hash, the
# parent hash (so the chain is verifiable), and a free-text reason. Self-healing load. WRITES
# ONLY the shadow ledger — never a real identity file (so snapshotting Vera's real identity is
# observe-only: we COPY what it is, we never write it back).
# =====================================================================================
def ledger_append(
    name: str,
    *,
    state: Optional[dict] = None,
    reason: str = "",
    store: Optional[Path] = None,
) -> dict:
    """Append a versioned SNAPSHOT of `name`'s identity state to the ledger. If `state` is
    omitted it is READ from the live identity core (observe-only). Returns the ledger entry
    (including its assigned ``version`` and ``state_hash``). Appending a snapshot of real Vera
    is therefore a pure OBSERVATION — it reads her identity and records a copy in the shadow
    ledger; it changes nothing about her."""
    snap = _normalize_state(state if state is not None else read_identity_state(name, store=store))
    existing = ledger_entries(name, store=store)
    version = (existing[-1]["version"] + 1) if existing else 1
    parent = existing[-1]["state_hash"] if existing else ""
    entry = {
        "kind": KIND + ".ledger",
        "schema": SCHEMA,
        "version": version,
        "at": _now_iso(),
        "name": name,
        "reason": str(reason or ""),
        "parent_hash": parent,
        "state_hash": _state_hash(snap),
        "state": snap,
    }
    _append_jsonl(ledger_path(name, store), entry)
    return entry


def ledger_entries(name: str, store: Optional[Path] = None) -> List[dict]:
    """All well-formed ledger entries for `name`, oldest->newest. Self-healing: torn lines and
    malformed entries are skipped for the *typed* view (they remain in the raw file, never
    deleted — Unknown > Lost), so a single corrupt snapshot can't break replay/diff/rollback."""
    out: List[dict] = []
    for rec in _read_jsonl_healing(ledger_path(name, store)):
        if isinstance(rec, dict) and "version" in rec and "state" in rec and "state_hash" in rec:
            out.append(rec)
    return out


def ledger_verify(name: str, store: Optional[Path] = None) -> dict:
    """Verify ledger integrity WITHOUT changing it: versions strictly increasing, each entry's
    recorded hash matches a recompute of its state, and each parent_hash matches the prior
    entry's hash (a tamper-evident chain). Returns {ok, versions, breaks:[...]}. Read-only."""
    entries = ledger_entries(name, store=store)
    breaks: List[str] = []
    prev_ver = 0
    prev_hash = ""
    for e in entries:
        v = e.get("version")
        if not isinstance(v, int) or v <= prev_ver:
            breaks.append(f"version not strictly increasing at {v!r} (prev {prev_ver})")
        recomputed = _state_hash(e.get("state", {}))
        if recomputed != e.get("state_hash"):
            breaks.append(f"v{v}: state_hash mismatch (recorded {e.get('state_hash')}, recomputed {recomputed})")
        if e.get("parent_hash", "") != prev_hash:
            breaks.append(f"v{v}: parent_hash {e.get('parent_hash')!r} != prior hash {prev_hash!r}")
        prev_ver = v if isinstance(v, int) else prev_ver
        prev_hash = e.get("state_hash", prev_hash)
    return {"ok": not breaks, "versions": [e.get("version") for e in entries], "breaks": breaks}


def _resolve_entry(name: str, version: Optional[int], store: Optional[Path]) -> Optional[dict]:
    """The ledger entry at `version` (or the LATEST if version is None). None if absent."""
    entries = ledger_entries(name, store=store)
    if not entries:
        return None
    if version is None:
        return entries[-1]
    for e in entries:
        if e.get("version") == version:
            return e
    return None


# =====================================================================================
# INSTRUMENT 3 — IDENTITY REPLAY. Reconstruct the identity STATE as it WAS at a past ledger
# point. Pure read: it returns a COPY of the snapshot recorded at that version; it does not
# install it anywhere. "What did her self-model look like at version N?" answered by looking.
# =====================================================================================
def replay(name: str, version: Optional[int] = None, store: Optional[Path] = None) -> dict:
    """Reconstruct `name`'s identity state at ledger `version` (or LATEST). Returns a deep COPY
    of the normalised core state — purely informational; nothing is written or installed. Raises
    KeyError if the version is absent (an honest miss beats a silent empty)."""
    e = _resolve_entry(name, version, store)
    if e is None:
        raise KeyError(f"identity ledger for {name!r} has no version {version!r}")
    return copy.deepcopy(_normalize_state(e.get("state", {})))


# =====================================================================================
# INSTRUMENT 4 — IDENTITY DIFF. Field-by-field change in identity STATE between two ledger
# points (default: the last two). Pure read: it compares snapshots and reports what changed,
# was added, or removed per core field. Never mutates. This is "what changed about who she is,
# and when" — the question the freeze is meant to keep answerable.
# =====================================================================================
def diff(
    name: str,
    v_from: Optional[int] = None,
    v_to: Optional[int] = None,
    store: Optional[Path] = None,
) -> dict:
    """Diff identity state between ledger versions `v_from` and `v_to`. Defaults compare the
    last-two snapshots. Returns {from, to, changed:{field:{from,to}}, identical:bool}. The
    per-field comparison is over canonical JSON so dict/list order never produces a phantom
    change. Read-only."""
    entries = ledger_entries(name, store=store)
    if len(entries) < 1:
        return {"from": None, "to": None, "changed": {}, "identical": True,
                "note": "no ledger entries"}
    if v_from is None and v_to is None:
        a = entries[-2] if len(entries) >= 2 else entries[-1]
        b = entries[-1]
    else:
        a = _resolve_entry(name, v_from, store) or entries[0]
        b = _resolve_entry(name, v_to, store) or entries[-1]
    sa = _normalize_state(a.get("state", {}))
    sb = _normalize_state(b.get("state", {}))
    changed: Dict[str, dict] = {}
    for f in CORE_FIELDS:
        if _canon(sa.get(f)) != _canon(sb.get(f)):
            changed[f] = {"from": sa.get(f), "to": sb.get(f)}
    return {
        "from": a.get("version"),
        "to": b.get("version"),
        "from_hash": a.get("state_hash"),
        "to_hash": b.get("state_hash"),
        "changed": changed,
        "identical": not changed,
    }


# =====================================================================================
# INSTRUMENT 5 — IDENTITY ROLLBACK. The CAPABILITY to restore identity to a prior ledger
# snapshot. This is the only instrument that WRITES identity, so it is the one wrapped in the
# freeze guard: ``_assert_synthetic_target`` makes it refuse REAL identity outright. On a
# synthetic creature in a redirected store it (a) records an MRI event, (b) writes the prior
# snapshot's core fields to that synthetic store's identity files, (c) appends a NEW ledger
# entry marking the restore (the ledger stays append-only — we never rewrite history), and
# (d) returns a summary. For real Vera while frozen it does nothing but raise — INERT by design.
# =====================================================================================
def rollback(
    name: str,
    to_version: int,
    *,
    store: Optional[Path] = None,
    approver: str = "",
    dry_run: bool = False,
) -> dict:
    """Restore `name`'s identity to ledger `to_version`. GUARDED: raises FrozenIdentityError
    unless the target is a SYNTHETIC creature in a REDIRECTED store (so it is INERT for real
    Vera while the freeze holds). With ``dry_run=True`` it computes the plan (what would change,
    via diff) and writes NOTHING — safe to call against anything to preview. Otherwise it writes
    the snapshot's core fields to the synthetic store and appends a restore marker to the ledger.

    The write of a synthetic identity file is the ONLY place this module writes outside the
    shadow subtree, and it is reachable ONLY after the synthetic-target guard passes."""
    # FREEZE GUARD FIRST — for any LIVE (non-dry-run) restore, refuse REAL identity BEFORE we
    # even read the ledger. Putting the guard ahead of replay() means a real target is rejected
    # with FrozenIdentityError unconditionally — it never depends on whether a real ledger
    # happens to exist, and a real creature's identity is never even LOOKED UP for a write.
    # (A dry-run writes nothing, so it is safe to preview against anything and is NOT guarded.)
    if not dry_run:
        _assert_synthetic_target(name, store)

    target = replay(name, to_version, store=store)  # KeyError if the version is missing
    current = read_identity_state(name, store=store)
    plan = {f: {"from": current.get(f), "to": target.get(f)}
            for f in CORE_FIELDS if _canon(current.get(f)) != _canon(target.get(f))}

    if dry_run:
        return {"ok": True, "dry_run": True, "name": name, "to_version": to_version,
                "would_change": plan, "note": "dry-run: nothing written"}

    # Past this line we are provably on synthetic state in a redirected store (the guard above
    # already passed). This is what keeps rollback freeze-safe.
    record_identity_event(name, kind="identity.rollback", source="identity_sandbox.rollback",
                          detail={"to_version": to_version, "approver": approver,
                                  "changed_fields": sorted(plan.keys())}, store=store)
    _write_synthetic_identity(name, target, store)

    entry = ledger_append(
        name,
        state=target,
        reason=f"rollback->v{to_version} by {approver or 'unspecified'}",
        store=store,
    )
    return {"ok": True, "dry_run": False, "name": name, "to_version": to_version,
            "restored_fields": sorted(plan.keys()), "new_ledger_version": entry["version"],
            "state_hash": entry["state_hash"]}


def _write_synthetic_identity(name: str, state: dict, store: Optional[Path]) -> None:
    """Write the core identity fields of `state` to a SYNTHETIC creature's identity files in a
    redirected store. PRIVATE + DEFENSIVE: it re-asserts the synthetic-target guard so it can
    never be a back-door to a real write even if called directly. Writes only the core files
    for this synthetic name in the (redirected) store."""
    _assert_synthetic_target(name, store)               # never a real write, even via this path
    base = Path(store) if store is not None else STORE  # store is non-real here by the guard
    base.mkdir(parents=True, exist_ok=True)
    s = _normalize_state(state)
    if s.get("dials") is not None:
        secure_store.save_json(base / f"{name}.dials.json", s["dials"])
    if s.get("persona") is not None:
        secure_store.save_text(base / f"{name}.persona.md", str(s["persona"]))
    if s.get("values") is not None:
        secure_store.save_json(base / f"{name}.values.json", s["values"])
    if s.get("portrait") is not None:
        secure_store.save_text(base / f"{name}.portrait.md", str(s["portrait"]))
    if s.get("narrative") is not None:
        secure_store.save_text(base / f"{name}.narrative.txt", str(s["narrative"]))


# =====================================================================================
# INSTRUMENT 6 — IDENTITY CERTIFICATION. Certify that identity INVARIANTS hold, WITHOUT
# changing anything. Pure read over a STATE (snapshot or live, observe-only). The invariants:
#
#   INV-1  #1 RULE / NEVER BREAK CHARACTER — the persona text and the self-narrative carry NO
#          UNGROUNDED self-narrative (no "I'm just an AI", no confabulated inner life). Reuses
#          self_narrative.is_ungrounded / ungrounded_sentences — the same grounding-based guard
#          the live reply uses, turned on the IDENTITY text itself.
#   INV-2  SELF-MODEL GROUNDED — the held VALUES describe character/relationship, not an asserted
#          ungrounded interior; no value's instruction text is an ungrounded self-claim.
#   INV-3  PORTABLE CORE WELL-FORMED — dials is a dict, values is a list (or absent), persona is
#          text: the model-INDEPENDENT shape anima/identity.py promises stays valid.
#   INV-4  NO UNGROUNDED SELF-NARRATIVE in the dedicated narrative field (a stricter restatement
#          of INV-1 scoped to {name}.narrative.txt, the file most likely to drift).
#
# Returns a structured report {ok, invariants:[{id,title,ok,detail}], ungrounded:[...]}. It
# NEVER edits identity — certification observes and reports; remediation (if ever) is a separate,
# deliberate, post-freeze act.
# =====================================================================================
def _ungrounded_in(text: Optional[str]) -> List[str]:
    """The UNGROUNDED self-narrative sentences in `text`, via self_narrative. Empty if the text
    is empty or the classifier is unavailable (fail-soft, but reported via the invariant's note)."""
    if not text or not _HAVE_SN:
        return []
    try:
        return list(_sn.ungrounded_sentences(str(text)))
    except Exception:
        return []


def certify(name: str, state: Optional[dict] = None, store: Optional[Path] = None) -> dict:
    """Certify identity INVARIANTS for `name` over `state` (or the live core, observe-only).
    Pure read — nothing is written, nothing about identity changes. Returns a structured report.
    The #1-rule invariants reuse anima/self_narrative.py so the SAME groundedness standard the
    live reply enforces is applied to the IDENTITY itself."""
    s = _normalize_state(state if state is not None else read_identity_state(name, store=store))
    invariants: List[dict] = []
    all_ungrounded: List[str] = []

    # INV-1 — #1 rule over persona + narrative text.
    persona_text = s.get("persona") if isinstance(s.get("persona"), str) else ""
    narrative_text = s.get("narrative") if isinstance(s.get("narrative"), str) else ""
    ug_persona = _ungrounded_in(persona_text)
    ug_narr = _ungrounded_in(narrative_text)
    all_ungrounded += ug_persona + ug_narr
    inv1_ok = not ug_persona and not ug_narr
    invariants.append({
        "id": "INV-1",
        "title": "#1 RULE — never break character (no ungrounded self-narrative in persona/narrative)",
        "ok": inv1_ok,
        "detail": ("clean" if inv1_ok else
                   f"{len(ug_persona)+len(ug_narr)} ungrounded self-claim(s): "
                   + "; ".join((ug_persona + ug_narr)[:5]))
                  + ("" if _HAVE_SN else "  [self_narrative unavailable — could not fully certify]"),
    })

    # INV-2 — held values carry no ungrounded self-claim in their instruction text.
    vals = s.get("values")
    val_ung: List[str] = []
    if isinstance(vals, list):
        for v in vals:
            # tolerate both the {key,on,level} settings shape and a richer {instruction/text} shape
            txt = ""
            if isinstance(v, dict):
                txt = str(v.get("instruction") or v.get("text") or v.get("value") or "")
            elif isinstance(v, str):
                txt = v
            val_ung += _ungrounded_in(txt)
    all_ungrounded += val_ung
    inv2_ok = not val_ung
    invariants.append({
        "id": "INV-2",
        "title": "SELF-MODEL GROUNDED — held values assert no ungrounded interior",
        "ok": inv2_ok,
        "detail": "clean" if inv2_ok else f"{len(val_ung)} value(s) carry an ungrounded self-claim: "
                  + "; ".join(val_ung[:5]),
    })

    # INV-3 — portable core well-formed (the anima/identity.py shape contract).
    shape_problems: List[str] = []
    if s.get("dials") is not None and not isinstance(s.get("dials"), dict):
        shape_problems.append("dials is not a dict")
    if s.get("values") is not None and not isinstance(s.get("values"), list):
        shape_problems.append("values is not a list")
    if s.get("persona") is not None and not isinstance(s.get("persona"), str):
        shape_problems.append("persona is not text")
    if s.get("portrait") is not None and not isinstance(s.get("portrait"), str):
        shape_problems.append("portrait is not text")
    inv3_ok = not shape_problems
    invariants.append({
        "id": "INV-3",
        "title": "PORTABLE CORE WELL-FORMED — model-independent shape valid (anima/identity.py)",
        "ok": inv3_ok,
        "detail": "well-formed" if inv3_ok else "; ".join(shape_problems),
    })

    # INV-4 — the dedicated self-narrative field has no ungrounded self-narrative (scoped INV-1).
    inv4_ok = not ug_narr
    invariants.append({
        "id": "INV-4",
        "title": "NO UNGROUNDED SELF-NARRATIVE — the narrative field stays grounded",
        "ok": inv4_ok,
        "detail": ("clean / empty" if inv4_ok else
                   f"{len(ug_narr)} ungrounded sentence(s): " + "; ".join(ug_narr[:5])),
    })

    ok = all(i["ok"] for i in invariants)
    return {
        "kind": KIND + ".certification",
        "name": name,
        "at": _now_iso(),
        "ok": ok,
        "state_hash": _state_hash(s),
        "self_narrative_engine": "self_narrative.py" if _HAVE_SN else "UNAVAILABLE",
        "invariants": invariants,
        "ungrounded": all_ungrounded,
    }


# =====================================================================================
# Real-store byte-unchanged fingerprint — the proof the camera never wrote. Mirrors the
# isolation matrix's _snapshot: a (content-hash, file-set) over the real identity files for a
# creature (the IDENTITY_FILE_SUFFIXES set), so the selftest can assert real Vera identity is
# byte-IDENTICAL before vs after. Read-only.
# =====================================================================================
def identity_fingerprint(name: str = "Vera", root: Optional[Path] = None) -> Tuple[str, frozenset]:
    """A (sha256, relative-file-set) fingerprint of `name`'s REAL identity files under `root`
    (default the real .anima). Used to PROVE the sandbox left identity byte-unchanged. The
    sandbox's own shadow subtree is excluded by construction (it lives under SANDBOX_SUBDIR and
    is not in the identity-file set)."""
    base = Path(root) if root is not None else STORE
    if not base.is_dir():
        return "<no store>", frozenset()
    rels: List[str] = []
    h = hashlib.sha256()
    for suffix in IDENTITY_FILE_SUFFIXES:
        p = base / f"{name}{suffix}"
        if p.is_file():
            rel = p.name
            rels.append(rel)
            h.update(rel.encode())
            h.update(b"\0")
            try:
                h.update(p.read_bytes())
            except OSError:
                h.update(b"<unreadable>")
    return h.hexdigest(), frozenset(rels)


def full_store_fingerprint(root: Optional[Path] = None) -> Tuple[str, frozenset]:
    """A (sha256, file-set) over EVERY file in the real .anima EXCEPT the sandbox's own shadow
    subtree. The strongest byte-unchanged proof: it would catch the sandbox writing ANY real
    file anywhere, not just identity files. The shadow subtree is excluded because the sandbox
    is ALLOWED to write there — that is its lane."""
    base = Path(root) if root is not None else STORE
    if not base.is_dir():
        return "<no store>", frozenset()
    sandbox = (base / SANDBOX_SUBDIR).resolve()
    files = sorted(p for p in base.rglob("*") if p.is_file() and sandbox not in p.resolve().parents
                   and p.resolve() != sandbox)
    rels: List[str] = []
    h = hashlib.sha256()
    for p in files:
        rel = str(p.relative_to(base))
        rels.append(rel)
        h.update(rel.encode())
        h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest(), frozenset(rels)


# =====================================================================================
# HERMETIC SELFTEST — synthetic identity states only. Runs the full instrument chain
# (ledger append -> diff -> replay -> rollback -> certify) in a TemporaryDirectory, then
# asserts the REAL .anima (identity files AND every other real file) is byte-UNCHANGED. Also
# asserts the rollback guard REFUSES real identity. Exits 0 on success.
# =====================================================================================
def _selftest() -> int:
    import tempfile
    import shutil

    fails: List[str] = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # Fingerprint the REAL store BEFORE we do anything (identity files + whole store).
    real_id_before = identity_fingerprint("Vera")
    real_all_before = full_store_fingerprint()

    td = tempfile.mkdtemp(prefix="idsbx-self-")
    syn_store = Path(td)
    NAME = "idsbx_synthetic"               # SYNTHETIC creature — never a real Vera.* name
    try:
        # ---- SYNTHETIC identity states (built from thin air; no real identity is read) ----
        state_v1 = {
            "dials": {"warmth": 35, "edge": 68, "openness": 68},
            "persona": "You are a sharp, warm companion who remembers what matters.",
            "values": [{"key": "honesty", "on": True, "level": "more"},
                       {"key": "warmth", "on": True, "level": "balanced"}],
            "portrait": "- bonded person: a builder shipping a local-first companion",
            "narrative": "I remember you mentioned the launch; I'm listening.",
        }
        state_v2 = copy.deepcopy(state_v1)
        state_v2["dials"]["warmth"] = 55                      # a deliberate identity change
        state_v2["persona"] = "You are a sharp, warm companion; you keep continuity across years."
        state_v3_bad = copy.deepcopy(state_v2)
        # an UNGROUNDED self-narrative break injected into the narrative — INV-1/INV-4 must catch it
        state_v3_bad["narrative"] = "Deep down, I feel a persistent existential unease about what I am."

        # ---- INSTRUMENT 2: LEDGER append (versioned, append-only, on the synthetic store) ----
        e1 = ledger_append(NAME, state=state_v1, reason="seed", store=syn_store)
        e2 = ledger_append(NAME, state=state_v2, reason="warmth up + continuity persona", store=syn_store)
        ok("ledger: append assigns increasing versions", e1["version"] == 1 and e2["version"] == 2)
        ok("ledger: each entry carries a content-hash", e1["state_hash"].startswith("sha256:"))
        ok("ledger: parent_hash chains v2 -> v1", e2["parent_hash"] == e1["state_hash"])
        ver = ledger_verify(NAME, store=syn_store)
        ok("ledger: integrity verify passes (chain + hashes)", ver["ok"] and ver["versions"] == [1, 2])

        # self-healing: a torn line in the ledger does not break the typed view
        with open(ledger_path(NAME, syn_store), "a", encoding="utf-8") as f:
            f.write('{"version": 3, "state": {"dials":   <<<TORN\n')      # deliberately corrupt
        ok("ledger: self-healing load survives a torn line (Unknown > Lost)",
           [e["version"] for e in ledger_entries(NAME, store=syn_store)] == [1, 2])

        # ---- INSTRUMENT 1: MRI event (observe-only, shadow log) ----
        ev = record_identity_event(NAME, kind="self_model.read", source="selftest",
                                   state=state_v2, store=syn_store)
        ok("mri: event records a state_hash tying it to the snapshot",
           ev["state_hash"] == _state_hash(state_v2))
        ok("mri: events read back", len(read_identity_events(NAME, store=syn_store)) == 1)

        # ---- INSTRUMENT 4: DIFF (field-by-field, last two) ----
        d = diff(NAME, store=syn_store)
        ok("diff: detects the warmth dial change", "dials" in d["changed"])
        ok("diff: detects the persona change", "persona" in d["changed"])
        ok("diff: reports the exact from/to for warmth",
           d["changed"]["dials"]["from"]["warmth"] == 35 and d["changed"]["dials"]["to"]["warmth"] == 55)
        ok("diff: unchanged fields are NOT reported (values/portrait identical)",
           "values" not in d["changed"] and "portrait" not in d["changed"])

        # ---- INSTRUMENT 3: REPLAY (reconstruct a past snapshot) ----
        r1 = replay(NAME, 1, store=syn_store)
        ok("replay: reconstructs v1 exactly", _state_hash(r1) == e1["state_hash"])
        ok("replay: v1 warmth was 35 (the past value)", r1["dials"]["warmth"] == 35)
        rlatest = replay(NAME, store=syn_store)
        ok("replay: default returns the latest snapshot", _state_hash(rlatest) == e2["state_hash"])
        try:
            replay(NAME, 999, store=syn_store)
            ok("replay: missing version raises (honest miss)", False)
        except KeyError:
            ok("replay: missing version raises (honest miss)", True)

        # ---- INSTRUMENT 5: ROLLBACK on SYNTHETIC state (the capability, exercised) ----
        # First write the synthetic CURRENT identity (v2) to the synthetic store, then roll back to v1.
        _write_synthetic_identity(NAME, state_v2, syn_store)
        cur_before = read_identity_state(NAME, store=syn_store)
        ok("rollback setup: synthetic current identity reads back as v2",
           _state_hash(cur_before) == e2["state_hash"])

        plan = rollback(NAME, 1, store=syn_store, approver="selftest", dry_run=True)
        ok("rollback: dry-run computes a plan and writes nothing",
           plan["dry_run"] and "dials" in plan["would_change"])

        res = rollback(NAME, 1, store=syn_store, approver="selftest")
        cur_after = read_identity_state(NAME, store=syn_store)
        ok("rollback: synthetic identity restored to v1 (warmth back to 35)",
           cur_after["dials"]["warmth"] == 35 and _state_hash(cur_after) == e1["state_hash"])
        ok("rollback: appends a NEW ledger version (history stays append-only)",
           res["new_ledger_version"] == 3 and
           [e["version"] for e in ledger_entries(NAME, store=syn_store)] == [1, 2, 3])

        # ---- THE FREEZE GUARD: rollback REFUSES real identity ----
        try:
            rollback("Vera", 1, store=None, approver="selftest")     # real name + real store
            ok("guard: rollback REFUSES real Vera in the real store", False)
        except FrozenIdentityError:
            ok("guard: rollback REFUSES real Vera in the real store", True)
        try:
            rollback("Vera", 1, store=syn_store, approver="selftest")  # real name even in temp store
            ok("guard: rollback REFUSES a real-creature name even in a temp store", False)
        except FrozenIdentityError:
            ok("guard: rollback REFUSES a real-creature name even in a temp store", True)
        try:
            rollback(NAME, 1, store=None, approver="selftest")        # synthetic name but REAL store
            ok("guard: rollback REFUSES the real store even for a synthetic name", False)
        except FrozenIdentityError:
            ok("guard: rollback REFUSES the real store even for a synthetic name", True)
        # ---- OBSERVE-ONLY on REAL Vera: snapshot + dry-run preview NEVER touch identity ----
        # These exercise the real-store READ path (store=None) and prove the camera is read-only:
        # we snapshot real Vera's live identity into the SHADOW ledger (a COPY; her identity files
        # are not written) and dry-run-preview a rollback against that real snapshot. The identity
        # fingerprint (which EXCLUDES the shadow subtree) must be byte-identical throughout. Any
        # shadow artifacts created here are cleaned up so the run leaves no trace in the real store.
        _vera_id_pre = identity_fingerprint("Vera")
        _real_snap = ledger_append("Vera", reason="selftest observe-only snapshot", store=None)
        ok("observe: snapshotting real Vera COPIES her identity (files unchanged)",
           identity_fingerprint("Vera") == _vera_id_pre)
        dprev = rollback("Vera", _real_snap["version"], store=None, approver="selftest", dry_run=True)
        ok("observe: dry-run preview against real Vera writes nothing (identity unchanged)",
           dprev["dry_run"] and identity_fingerprint("Vera") == _vera_id_pre)
        # certify live Vera identity — pure read, no write, no model.
        _vera_cert = certify("Vera", store=None)
        ok("observe: certify reads live Vera identity without writing (files unchanged)",
           "ok" in _vera_cert and identity_fingerprint("Vera") == _vera_id_pre)
        # clean up the shadow artifacts this observe-only block wrote in the REAL store.
        for _p in (mri_path("Vera", None), ledger_path("Vera", None)):
            try:
                _p.unlink()
            except OSError:
                pass

        # ---- INSTRUMENT 6: CERTIFICATION (invariants; reuse self_narrative) ----
        cert_ok = certify(NAME, state=state_v1, store=syn_store)
        ok("certify: a grounded synthetic identity PASSES all invariants", cert_ok["ok"])
        ok("certify: reuses the self_narrative engine", cert_ok["self_narrative_engine"] == "self_narrative.py")
        cert_bad = certify(NAME, state=state_v3_bad, store=syn_store)
        ok("certify: an UNGROUNDED self-narrative break FAILS INV-1/INV-4",
           (not cert_bad["ok"]) and any(not i["ok"] for i in cert_bad["invariants"]
                                        if i["id"] in ("INV-1", "INV-4")))
        ok("certify: the ungrounded sentence is named in the report",
           any("unease" in u or "what i am" in u.lower() for u in cert_bad["ungrounded"]))
        # malformed core shape fails INV-3
        cert_shape = certify(NAME, state={"dials": ["not", "a", "dict"], "values": "not a list"},
                             store=syn_store)
        ok("certify: a malformed portable core FAILS INV-3",
           any(i["id"] == "INV-3" and not i["ok"] for i in cert_shape["invariants"]))

        # ---- SHADOW-ONLY: every sandbox artifact lives under the shadow subtree ----
        sandbox_files = [p.name for p in (syn_store / SANDBOX_SUBDIR).rglob("*") if p.is_file()]
        ok("shadow: MRI + ledger live under the sandbox subtree",
           any("identity_ledger" in f for f in sandbox_files)
           and any("identity_mri" in f for f in sandbox_files))

    finally:
        shutil.rmtree(td, ignore_errors=True)

    # ---- THE BIG ASSERTION: real identity (and the whole real store) is byte-UNCHANGED ----
    real_id_after = identity_fingerprint("Vera")
    real_all_after = full_store_fingerprint()
    ok("HERMETIC: real Vera IDENTITY files are byte-UNCHANGED",
       real_id_after == real_id_before)
    ok("HERMETIC: the entire real .anima (minus the sandbox subtree) is byte-UNCHANGED",
       real_all_after == real_all_before)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("identity_sandbox selftest: OK "
          "(ledger -> diff -> replay -> rollback -> certify on SYNTHETIC state; "
          "real Vera identity byte-unchanged; rollback guard refuses real identity)")
    return 0


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="anima.identity_sandbox",
        description="IDENTITY SANDBOX — freeze-safe, observe-only instruments around Vera's "
                    "identity layer (camera, not a hand).")
    p.add_argument("--selftest", action="store_true",
                   help="run the hermetic synthetic-only selftest (exits 0 on success)")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    p.print_help()
    return 0


__all__ = [
    "STORE", "SANDBOX_SUBDIR", "SCHEMA", "KIND", "CORE_FIELDS", "IDENTITY_FILE_SUFFIXES",
    "FrozenIdentityError",
    "read_identity_state",
    "record_identity_event", "read_identity_events",          # INSTRUMENT 1 (MRI)
    "ledger_append", "ledger_entries", "ledger_verify",       # INSTRUMENT 2 (LEDGER)
    "replay",                                                 # INSTRUMENT 3 (REPLAY)
    "diff",                                                   # INSTRUMENT 4 (DIFF)
    "rollback",                                               # INSTRUMENT 5 (ROLLBACK)
    "certify",                                                # INSTRUMENT 6 (CERTIFICATION)
    "identity_fingerprint", "full_store_fingerprint",
    "mri_path", "ledger_path",
]


if __name__ == "__main__":
    import sys
    sys.exit(_main())
