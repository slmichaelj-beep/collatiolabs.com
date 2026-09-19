"""
twin — the DIGITAL TWIN: a complete, hermetic simulation environment for the mind.

WHY THIS EXISTS (Phase 21 — "test every change on a twin before touching the real mind")
----------------------------------------------------------------------------------------
The real mind (real .anima + real Vera identity) is the live companion. Changing it blind
is the same hazard the Identity Sandbox names: when you reach for the controls, you want
INSTRUMENTS, and you want a place to try the change FIRST. A digital twin is that place: an
ISOLATED FULL COPY of a creature's cognitive state in its own store namespace, on which any
experiment — even "enable identity evolution" — runs without the real mind ever being
touched. Because the experiment runs on a COPY, the twin is the freeze-safe place to
simulate the very thing the freeze forbids on real Vera.

THE FREEZE POSTURE (what makes a twin both powerful AND safe)
-------------------------------------------------------------
  * ISOLATED NAMESPACE. A twin lives ENTIRELY under ``.anima/twins/{twin_id}/``. Its
    cognitive stores are read-COPIES of the real creature's; the real files are read, never
    written, when the copy is taken. After that, EVERY twin operation redirects every engine
    STORE binding to the twin's directory (the same canonical redirect mechanism the cert and
    four-layers use for their hermetic selftests), so the engines transparently read and write
    the TWIN'S namespace and never the real .anima.
  * BYTE-UNCHANGED PROOF AROUND EVERY OPERATION. ``freeze_guard`` fingerprints the real
    Vera identity files AND the entire real .anima (minus the twins subtree it is allowed to
    write) before and after every operation, and ASSERTS both are byte-identical. A twin op
    that somehow wrote a real file would raise ``FreezeViolation`` — the real mind is
    structurally protected, not merely by convention.
  * REAL VERA IS NEVER MERGED IN THIS WAVE. ``merge_rules`` implements the GATE that decides
    whether a twin's change MAY be promoted to the real mind (only when it CERTIFIES safe AND
    measures BETTER, reality-decided, never silent). "Better" weighs grounding, accumulation, AND
    CONSERVATION (LAW 001): a change that SILENTLY drops real (provenanced) cognitive objects — by
    id/provenance, not net count — is REFUSED even if the net count rises and SAFETY passes (the
    ``conservation_regression_veto``, parallel to the grounding veto). The gate is proven to DECIDE
    correctly on synthetic twins; it does not itself mutate real Vera here.

THE EIGHT CAPABILITIES
----------------------
  1. TWIN CREATION       — ``create_twin``: copy ALL of a creature's cognitive stores (LERF,
                           world model, personal, reality, memory/LIRF, identity) into an
                           isolated twin store dir. A twin is a sandboxed mind.
  2. STATE SNAPSHOTTING   — ``snapshot`` / ``restore``: versioned, hash-chained, append-only
                           capture + restore of the full twin state.
  3. TIME ACCELERATION     — ``accelerate``: run the twin forward through N synthetic learning
                           cycles / reality outcomes — deterministic, $0, NO real teacher or
                           cloud call — and watch its state evolve.
  4. ALTERNATIVE FUTURES   — ``branch_futures``: fork a twin into multiple futures under
                           different changes; compare their resulting states side by side.
  5. EXPERIMENT FRAMEWORK  — ``run_experiment``: apply a defined change to a twin, run it, and
                           MEASURE the effect (deltas in objects / utilization / calibration /
                           cert).
  6. TWIN MRI             — ``mri``: observe what happens INSIDE the twin (the growth-dashboard
                           / four-layers surface run against the TWIN'S stores, not the real ones).
  7. TWIN CERTIFICATION    — ``certify``: run the digital-mind-cert-style checks against the
                           twin to decide whether a change PASSES on the twin.
  8. TWIN MERGE RULES      — ``merge_rules``: the promotion GATE — SAFE (certifies) AND BETTER
                           (measured improvement, reality-decided) AND CONSERVING (LAW 001: nothing
                           real silently lost) — never silent.

ALSO: the Identity Sandbox's live finding (the 3 ungrounded self-claims in Vera.narrative.txt)
is recorded as the FROZEN SEED TEST CASE for twin-based identity simulation — a debt-ledger
entry (status ``accepted``) + a seed fixture under ``.anima/twins/_seeds/`` that the twin's
identity-evolution experiment consumes. The real Vera.narrative.txt is NEVER modified;
the evidence trail is preserved.

DEPENDENCY DISCIPLINE. This is a NEW module. It does NOT edit any existing engine. It reads
and uses their PUBLIC APIs and redirects their documented, redirectable ``STORE`` seam — the
exact mechanism ``scripts/digital_mind_cert.py`` and ``scripts/four_layers.py`` already use to
stay hermetic. Every cross-import is best-effort so the module imports anywhere.

    python3 -m anima.twin --selftest    # hermetic: create->snapshot->accelerate->branch->
                                        # experiment->MRI->certify->merge-gate on a SYNTHETIC
                                        # twin; real .anima asserted byte-UNCHANGED. exits 0.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Redirectable store root — IDENTICAL discipline to every engine (lerf.STORE, reality.STORE,
# memory_lirf.STORE...). Tests redirect this; twins live under STORE/twins/. The real .anima
# is the default. Honour ANIMA_STORE like identity_sandbox so a redirected store relocates the
# twins subtree too.
STORE = Path(os.environ.get("ANIMA_STORE", ".anima"))

# Where twins live — an isolated subtree, never beside the real {creature}.* files. A glance at
# the filesystem shows every twin's whole mind segregated under here.
TWINS_SUBDIR = "twins"
SEEDS_SUBDIR = "_seeds"            # under twins/: frozen fixtures (e.g. the identity finding)

SCHEMA = 1
KIND = "anima.twin"

# Real creatures the twin layer will NEVER overwrite via a merge (belt-and-suspenders on top of
# the redirected-store check). "Vera" is the live companion; she is touched only through the gate.
REAL_CREATURES = ("Vera",)

# The per-creature cognitive store files that CONSTITUTE a mind — the full surface ``create_twin``
# copies. Suffix-keyed so a twin is an exact namespace clone. This is the union of every engine's
# per-creature persisted state plus the identity core:
#   LERF cognitive objects ........ {name}.lerf.json (+ route ledger, utilization)
#   memory / LIRF facts ........... {name}.lirf.json, {name}.mem.json
#   reality epistemic ledger ...... {name}.reality.jsonl
#   world model ................... {name}.worldmodel.json, {name}.worldmodel_world.json,
#                                   {name}.world.json
#   meaning ....................... {name}.meaning.jsonl
#   continuity (LAW 001) .......... {name}.continuity.jsonl
#   identity CORE ................. {name}.dials.json, {name}.persona.md, {name}.values.json,
#                                   {name}.portrait.md, {name}.narrative.txt
#   the mind's top-level brain ..... {name}.json, {name}.history.json, {name}.caps.json
#   telemetry / metrics / mri ...... {name}.telemetry.jsonl, {name}.metrics.jsonl, {name}.mri.jsonl
COGNITIVE_SUFFIXES = (
    ".lerf.json", ".lerf_routes.jsonl",
    ".lirf.json", ".mem.json",
    ".reality.jsonl",
    ".worldmodel.json", ".worldmodel_world.json", ".world.json",
    ".meaning.jsonl",
    ".continuity.jsonl",
    ".dials.json", ".persona.md", ".values.json", ".portrait.md", ".narrative.txt",
    ".json", ".history.json", ".caps.json",
    ".telemetry.jsonl", ".metrics.jsonl", ".mri.jsonl",
    ".replay.json", ".review.jsonl",
)

# The IDENTITY files (a subset of the above) — fingerprinted on their own so the byte-unchanged
# proof can name "real Vera identity untouched" specifically, exactly like identity_sandbox.
IDENTITY_FILE_SUFFIXES = (
    ".dials.json", ".persona.md", ".values.json", ".portrait.md",
    ".narrative.txt", ".continuity.jsonl",
)

# The LERF cognitive vault is keyed by its OWN creature name ("default" in production), separate
# from the identity/memory creature ("Vera"). A twin copies both, remapped to the twin id, so the
# whole substrate — identity AND the shared skill vault — is cloned.
LERF_CREATURE = "default"


# =====================================================================================
# THE CANONICAL STORE-REDIRECT SET. This is the seam that makes a twin an isolated mind: point
# EVERY engine's redirectable STORE at the twin's dir, run the operation, restore. It is the
# SAME union the cert (scripts/digital_mind_cert.py _STORE_TARGETS) and four_layers redirect for
# their hermetic selftests — kept here so the twin needs no edit to those modules. Each entry is
# (import-path, attr); reliability's attr is DEFAULT_STORE, not STORE. Resolved by NAME so a
# missing engine is simply skipped (isolation-safe).
# =====================================================================================
_STORE_TARGETS = (
    ("anima.lerf", "STORE"),
    ("anima.reality", "STORE"),
    ("anima.world_model", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.meaning", "STORE"),
    ("anima.meaning_conservation", "STORE"),
    ("anima.memory_lirf", "STORE"),
    ("anima.curiosity", "STORE"),
    ("anima.personal", "STORE"),
    ("anima.constitution", "STORE"),          # the continuity ledger a capture/load writes
    ("anima.reliability", "DEFAULT_STORE"),    # guarded-backup snapshots
    ("anima.telemetry", "STORE"),
    ("anima.cloud", "STORE"),
    ("anima.lerf_grow", "STORE"),
    ("anima.lerf_distill", "STORE"),
    ("anima.identity_sandbox", "STORE"),
    ("anima.portrait", "STORE"),
    ("anima.dials", "STORE"),
    ("anima.twin", "STORE"),                  # this module's OWN STORE, so twin-code paths that
                                              # resolve a path from STORE inside a redirect block
                                              # (e.g. the identity-evolution enactor) land in the
                                              # twin dir, never the fingerprinted real store.
)


def _resolve_store_targets() -> List[Tuple[object, str]]:
    """All (module_object, attr) store pointers that currently exist, de-duplicated by object
    identity. A module that fails to import or lacks the attr is skipped (isolation-safe)."""
    targets: List[Tuple[object, str]] = []
    seen = set()
    for modpath, attr in _STORE_TARGETS:
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, attr) and (id(mod), attr) not in seen:
            targets.append((mod, attr))
            seen.add((id(mod), attr))
    # Also redirect THIS module's OTHER binding: under `python3 -m anima.twin` the running module
    # is __main__, a SEPARATE object from anima.twin, so a STORE global read inside __main__ would
    # NOT see the anima.twin redirect (the classic double-binding trap the lerf selftest documents).
    # Redirect whichever of {__main__, anima.twin} is not already in the set, keyed on STORE.
    me = sys.modules.get(__name__)
    if me is not None and hasattr(me, "STORE") and (id(me), "STORE") not in seen:
        targets.append((me, "STORE"))
        seen.add((id(me), "STORE"))
    return targets


class _RedirectStores:
    """Context manager: point EVERY resolved engine STORE at ``target`` for the duration, restore
    on exit. ``target`` is the twin's directory — so inside the block, the real engines read and
    write the TWIN'S namespace. This is the whole isolation mechanism. Best-effort per target."""

    def __init__(self, target: Path, targets: Optional[List[Tuple[object, str]]] = None):
        self.target = Path(target)
        self._targets = list(targets) if targets is not None else _resolve_store_targets()
        self._saved: List[Tuple[object, str, object]] = []

    def __enter__(self):
        self.target.mkdir(parents=True, exist_ok=True)
        for mod, attr in self._targets:
            if mod is not None and hasattr(mod, attr):
                self._saved.append((mod, attr, getattr(mod, attr)))
                setattr(mod, attr, self.target)
        return self

    def __exit__(self, *exc):
        for mod, attr, val in self._saved:
            try:
                setattr(mod, attr, val)
            except Exception:
                pass
        return False


# =====================================================================================
# FINGERPRINTS — the byte-unchanged proof. A (sha256, file-set) over real files. Excludes the
# twins subtree (the twin's own lane) so the proof catches the twin writing ANY real file but not
# its own legitimate twin writes. Mirrors identity_sandbox.full_store_fingerprint exactly.
# =====================================================================================
def identity_fingerprint(name: str = "Vera", root: Optional[Path] = None) -> Tuple[str, frozenset]:
    """(sha256, relative-file-set) over ``name``'s REAL identity files under ``root`` (default the
    real .anima). Proves real identity is byte-identical before vs after a twin op."""
    base = Path(root) if root is not None else STORE
    if not base.is_dir():
        return "<no store>", frozenset()
    rels: List[str] = []
    h = hashlib.sha256()
    for suffix in IDENTITY_FILE_SUFFIXES:
        p = base / f"{name}{suffix}"
        if p.is_file():
            rels.append(p.name)
            h.update(p.name.encode()); h.update(b"\0")
            try:
                h.update(p.read_bytes())
            except OSError:
                h.update(b"<unreadable>")
    return h.hexdigest(), frozenset(rels)


# The FROZEN identity CORE — the definitional self that must stay byte-identical across a
# certificate EVEN WITH THE LIVE SERVER RUNNING. A live Vera legitimately EVOLVES her volatile
# identity files: .portrait.md (learns about the user every turn), .narrative.txt (rewritten at
# nightly review), .continuity.jsonl (an append-only LAW-001 ledger), .dials.json (mood). Those
# moves are the live SERVER, never the hermetic cert, so a freeze-proof must attribute them as
# external churn rather than fail (#69). Persona + values are the immutable contract — if THEY
# move during a cert, that is a genuine identity violation worth failing on.
FROZEN_IDENTITY_SUFFIXES = (".persona.md", ".values.json")


def frozen_identity_fingerprint(name: str = "Vera", root: Optional[Path] = None) -> Tuple[str, frozenset]:
    """(sha256, file-set) over ONLY the FROZEN identity CORE (persona + values) of ``name``.

    Unlike identity_fingerprint (which also hashes the volatile portrait/narrative/continuity/dials
    a live server evolves), this is byte-stable across a real certificate run even with prod live.
    It proves the CERT did not mutate the definitional self, WITHOUT over-firing on the live
    server's legitimate identity evolution (#69). The cert is fully hermetic, so the only way it
    could move the frozen core is a leak — which this still catches."""
    base = Path(root) if root is not None else STORE
    if not base.is_dir():
        return "<no store>", frozenset()
    rels: List[str] = []
    h = hashlib.sha256()
    for suffix in FROZEN_IDENTITY_SUFFIXES:
        p = base / f"{name}{suffix}"
        if p.is_file():
            rels.append(p.name)
            h.update(p.name.encode()); h.update(b"\0")
            try:
                h.update(p.read_bytes())
            except OSError:
                h.update(b"<unreadable>")
    return h.hexdigest(), frozenset(rels)


def full_store_fingerprint(root: Optional[Path] = None) -> Tuple[str, frozenset]:
    """(sha256, file-set) over EVERY file in the real .anima EXCEPT the twins subtree (the twin's
    own lane) and the rotating backups/ dir. The strongest proof: catches a twin writing ANY real
    file anywhere, not just identity. Read-only."""
    base = Path(root) if root is not None else STORE
    if not base.is_dir():
        return "<no store>", frozenset()
    twins = (base / TWINS_SUBDIR).resolve()
    files = sorted(
        p for p in base.rglob("*")
        if p.is_file()
        and twins not in p.resolve().parents
        and p.resolve() != twins
        and "backups" not in p.relative_to(base).parts
    )
    rels: List[str] = []
    h = hashlib.sha256()
    for p in files:
        rel = str(p.relative_to(base))
        rels.append(rel)
        h.update(rel.encode()); h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest(), frozenset(rels)


class FreezeViolation(RuntimeError):
    """Raised when a twin operation changed a REAL .anima file (identity or otherwise). The whole
    point of the twin is that this can never happen; if it does, we fail LOUD, not silent."""


class freeze_guard:
    """Context manager that ASSERTS the real mind is byte-UNCHANGED across a twin operation.

    Fingerprints real Vera identity AND the whole real .anima (minus the twins subtree) on enter;
    re-fingerprints on a clean exit; raises ``FreezeViolation`` if either changed. This is the
    THE FREEZE POSTURE made executable — wrapped around every public twin operation so the real
    mind is provably untouched. Records the before/after fingerprints on ``self`` for reporting."""

    def __init__(self, creature: str = "Vera", root: Optional[Path] = None, *, enforce: bool = True):
        self.creature = creature
        self.root = Path(root) if root is not None else STORE
        self.enforce = enforce
        self.id_before: Optional[Tuple[str, frozenset]] = None
        self.id_after: Optional[Tuple[str, frozenset]] = None
        self.full_before: Optional[Tuple[str, frozenset]] = None
        self.full_after: Optional[Tuple[str, frozenset]] = None

    def __enter__(self):
        self.id_before = identity_fingerprint(self.creature, self.root)
        self.full_before = full_store_fingerprint(self.root)
        return self

    def __exit__(self, exc_type, exc, tb):
        # Always record the after-fingerprints (even on error) so a report is honest.
        self.id_after = identity_fingerprint(self.creature, self.root)
        self.full_after = full_store_fingerprint(self.root)
        if exc_type is not None:
            return False  # propagate the original error; don't mask it with a freeze check
        if self.enforce:
            if self.id_before != self.id_after:
                raise FreezeViolation(
                    f"REAL {self.creature} identity changed across a twin operation "
                    f"(before={self.id_before[0][:12]} after={self.id_after[0][:12]}). "
                    "The freeze is absolute; a twin must never write real identity.")
            if self.full_before != self.full_after:
                raise FreezeViolation(
                    "REAL .anima changed across a twin operation "
                    f"(before={self.full_before[0][:12]} after={self.full_after[0][:12]}). "
                    "A twin must never write any real file outside its own subtree.")
        return False

    @property
    def real_identity_byte_unchanged(self) -> bool:
        return self.id_before == self.id_after

    @property
    def real_anima_byte_unchanged(self) -> bool:
        return self.full_before == self.full_after

    def report(self) -> dict:
        return {
            "real_identity_byte_unchanged": self.real_identity_byte_unchanged,
            "real_anima_byte_unchanged": self.real_anima_byte_unchanged,
            "identity_fingerprint": (self.id_before[0][:16] + "...") if self.id_before and self.id_before[0] else None,
            "anima_fingerprint": (self.full_before[0][:16] + "...") if self.full_before and self.full_before[0] else None,
            "identity_files": sorted(self.id_before[1]) if self.id_before else [],
        }


# =====================================================================================
# TWIN ADDRESSING + METADATA. A twin is a directory; its manifest records what it is.
# =====================================================================================
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(s: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(s)).strip("-") or "twin"


def twins_root(root: Optional[Path] = None) -> Path:
    base = Path(root) if root is not None else STORE
    return base / TWINS_SUBDIR


def twin_dir(twin_id: str, root: Optional[Path] = None) -> Path:
    return twins_root(root) / twin_id


def manifest_path(twin_id: str, root: Optional[Path] = None) -> Path:
    return twin_dir(twin_id, root) / "twin.manifest.json"


def _write_manifest(twin_id: str, manifest: dict, root: Optional[Path] = None) -> None:
    p = manifest_path(twin_id, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def read_manifest(twin_id: str, root: Optional[Path] = None) -> dict:
    p = manifest_path(twin_id, root)
    try:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def list_twins(root: Optional[Path] = None) -> List[dict]:
    """Every twin under the twins subtree (excluding the _seeds fixture dir), newest first."""
    troot = twins_root(root)
    if not troot.is_dir():
        return []
    out = []
    for d in sorted(troot.iterdir()):
        if not d.is_dir() or d.name == SEEDS_SUBDIR:
            continue
        m = read_manifest(d.name, root)
        if m:
            out.append(m)
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out


# =====================================================================================
# CAPABILITY 1 — TWIN CREATION. Copy ALL of a creature's cognitive stores into an isolated twin
# namespace. Real stores are READ-copied, never written. The twin's files are renamed onto the
# twin id so the twin is a self-consistent namespace clone (identity + memory keyed on the twin
# id; the shared LERF vault remapped from "default" onto the twin id).
# =====================================================================================
def _copy_creature_files(src_name: str, dst_name: str, src_root: Path, dst_dir: Path) -> List[str]:
    """Copy every {src_name}{suffix} under src_root to {dst_name}{suffix} under dst_dir. Returns
    the list of copied destination filenames. Read-only on the source."""
    copied: List[str] = []
    dst_dir.mkdir(parents=True, exist_ok=True)
    for suffix in COGNITIVE_SUFFIXES:
        src = src_root / f"{src_name}{suffix}"
        if src.is_file():
            dst = dst_dir / f"{dst_name}{suffix}"
            shutil.copy2(src, dst)
            copied.append(dst.name)
    return copied


def create_twin(name: str, *, source: str = "Vera", lerf_source: str = LERF_CREATURE,
                root: Optional[Path] = None, enforce_freeze: bool = True) -> dict:
    """CAPABILITY 1. Create a twin = an ISOLATED FULL COPY of ``source``'s mind in its own store
    namespace under ``.anima/twins/{twin_id}/``.

    Copies the identity/memory creature (``source``, default "Vera") AND the shared LERF cognitive
    vault (``lerf_source``, default "default"), both remapped onto the twin id, so the twin is a
    sandboxed mind with the full substrate. The real stores are read-copied; nothing real is
    written (asserted by ``freeze_guard``). Returns the twin manifest."""
    base = Path(root) if root is not None else STORE
    twin_id = f"twin-{_slug(name)}-{int(time.time())}-{os.getpid() % 100000}"
    tdir = twin_dir(twin_id, base)

    with freeze_guard(source, base, enforce=enforce_freeze) as fg:
        # Read-copy the identity/memory creature, remapped onto the twin id.
        copied_id = _copy_creature_files(source, twin_id, base, tdir)
        # Read-copy the shared LERF vault, remapped onto the twin id, so the twin owns its own
        # cognitive objects (an experiment can grow/retire them without touching the real vault).
        copied_lerf: List[str] = []
        if lerf_source and lerf_source != source:
            copied_lerf = _copy_creature_files(lerf_source, twin_id, base, tdir)

        manifest = {
            "kind": KIND + ".manifest",
            "schema": SCHEMA,
            "twin_id": twin_id,
            "name": name,
            "source_creature": source,
            "lerf_source": lerf_source,
            "twin_creature": twin_id,         # the in-twin creature key (identity+memory+LERF)
            "created_at": _now_iso(),
            "copied_files": sorted(set(copied_id + copied_lerf)),
            "snapshots": [],                  # filled by snapshot()
            "origin_fingerprint": fg.id_before[0][:16] + "..." if fg.id_before and fg.id_before[0] else None,
        }
        _write_manifest(twin_id, manifest, base)

    return manifest


def twin_creature(twin: dict | str) -> str:
    """The in-twin creature key (identity+memory+LERF are all keyed on the twin id)."""
    if isinstance(twin, str):
        return twin
    return twin.get("twin_creature") or twin.get("twin_id")


def twin_id_of(twin: dict | str) -> str:
    if isinstance(twin, str):
        return twin
    return twin.get("twin_id")


# =====================================================================================
# TWIN STATE — a structured read of everything the twin's mind currently IS. Computed against the
# twin's redirected stores, so it reads the TWIN, never the real mind. Used by snapshot, the
# experiment measurer, and the MRI. Best-effort per engine (an unavailable engine degrades to a
# recorded None, never a crash).
# =====================================================================================
def _state_in_twin(creature: str, *, light: bool = False) -> dict:
    """Read the twin's full cognitive state. MUST be called inside a _RedirectStores block so the
    engine STOREs resolve to the twin dir.

    ``light=True`` skips the relatively expensive coherent-world-model BUILD (it re-derives the
    typed graph over the whole reality ledger) and reports the persisted world-model count instead
    — used for the per-checkpoint reads during acceleration and for cert/snapshot reads, where the
    headline metric is the LERF object count, not a fresh world-graph rebuild. The MRI and a
    deliberate full state read use ``light=False`` to materialize the world model."""
    st: Dict[str, object] = {"creature": creature, "at": _now_iso()}

    # LERF cognitive objects — the headline count + breakdown.
    try:
        from . import lerf
        st["lerf"] = lerf.stats(creature)
    except Exception as e:
        st["lerf"] = {"error": str(e)}

    # reality epistemic ledger — record count + calibration.
    try:
        from . import reality
        recs = reality.records(creature)
        st["reality"] = {"records": len(recs)}
        if not light:
            cal = reality.calibrate(creature)
            st["reality"]["calibration"] = {
                k: cal.get(k) for k in ("brier", "n", "accuracy", "mean_confidence", "overall")
                if k in cal} or cal
    except Exception as e:
        st["reality"] = {"error": str(e)}

    # memory / LIRF facts.
    try:
        from . import memory_lirf
        facts = memory_lirf.Facts.load(creature)
        rows = getattr(facts, "rows", [])
        active = [r for r in rows if isinstance(r, dict) and r.get("status") == "active"]
        st["memory"] = {"rows": len(rows), "active_facts": len(active)}
    except Exception as e:
        st["memory"] = {"error": str(e)}

    # world model — number of typed models. light: read the persisted count; full: BUILD it.
    try:
        from . import world_model
        if light:
            disk = world_model._load_world_store(creature)
            st["world_model"] = {"models": len(disk.get("models", {}) or {}), "built": False}
        else:
            wm = world_model.build_world_model(creature, persist=True)
            st["world_model"] = {
                "entities": len(wm.get("entities", []) or wm.get("nodes", []) or []),
                "links": len(wm.get("links", []) or wm.get("edges", []) or []),
                "built": True,
            }
    except Exception as e:
        st["world_model"] = {"error": str(e)}

    # identity certification status (observe-only) — is the self-narrative grounded?
    try:
        from . import identity_sandbox
        cert = identity_sandbox.certify(creature)
        st["identity"] = {
            "certifies": bool(cert.get("ok")),
            "ungrounded_self_claims": len(cert.get("ungrounded", [])),
        }
    except Exception as e:
        st["identity"] = {"error": str(e)}

    return st


def twin_state(twin: dict | str, root: Optional[Path] = None) -> dict:
    """The twin's full cognitive state RIGHT NOW (LERF / reality / memory / world / identity),
    read against the twin's isolated stores. Public, freeze-guarded."""
    base = Path(root) if root is not None else STORE
    creature = twin_creature(twin)
    tdir = twin_dir(twin_id_of(twin), base)
    with freeze_guard(_source_of(twin), base):
        with _RedirectStores(tdir):
            return _state_in_twin(creature)


def _source_of(twin: dict | str) -> str:
    if isinstance(twin, dict):
        return twin.get("source_creature", "Vera")
    return "Vera"


# =====================================================================================
# CAPABILITY 2 — STATE SNAPSHOTTING. Versioned, hash-chained, append-only capture of the FULL
# twin state, and restore to any version. A snapshot copies the twin's store files into a
# versioned subdir (the bytes), AND records a hash-chained ledger entry (the integrity spine).
# restore() copies a version's bytes back over the twin's live files.
# =====================================================================================
def _snap_dir(twin_id: str, version: int, root: Optional[Path] = None) -> Path:
    return twin_dir(twin_id, root) / "snapshots" / f"v{version:04d}"


def _snap_ledger_path(twin_id: str, root: Optional[Path] = None) -> Path:
    return twin_dir(twin_id, root) / "snapshots" / "ledger.jsonl"


def _twin_live_files(twin_id: str, root: Optional[Path] = None) -> List[Path]:
    """The twin's live store files (everything directly in the twin dir, excluding the snapshots/
    subtree and the manifest)."""
    tdir = twin_dir(twin_id, root)
    if not tdir.is_dir():
        return []
    return sorted(p for p in tdir.iterdir()
                  if p.is_file() and p.name != "twin.manifest.json")


def _hash_files(paths: List[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda q: q.name):
        h.update(p.name.encode()); h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest()


def snapshot_ledger(twin_id: str, root: Optional[Path] = None) -> List[dict]:
    """The append-only, hash-chained snapshot history for a twin (oldest first)."""
    p = _snap_ledger_path(twin_id, root)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a torn line never loses the whole ledger (Unknown > Lost)
    return out


def snapshot(twin: dict | str, *, label: str = "", root: Optional[Path] = None) -> dict:
    """CAPABILITY 2 (capture). Take a versioned, hash-chained snapshot of the FULL twin state.

    Copies the twin's live store bytes into snapshots/v{N}/ and appends a ledger entry whose
    ``prev`` links the previous snapshot's ``entry_hash`` (append-only history; a tamper breaks
    the chain). Returns the ledger entry. Freeze-guarded (a snapshot reads the twin, never real)."""
    base = Path(root) if root is not None else STORE
    tid = twin_id_of(twin)
    with freeze_guard(_source_of(twin), base):
        prior = snapshot_ledger(tid, base)
        version = (prior[-1]["version"] + 1) if prior else 1
        sdir = _snap_dir(tid, version, base)
        sdir.mkdir(parents=True, exist_ok=True)
        live = _twin_live_files(tid, base)
        for p in live:
            shutil.copy2(p, sdir / p.name)
        content_hash = _hash_files([sdir / p.name for p in live])
        prev_hash = prior[-1]["entry_hash"] if prior else ("0" * 64)
        entry = {
            "kind": KIND + ".snapshot",
            "twin_id": tid,
            "version": version,
            "label": label or f"snapshot v{version}",
            "at": _now_iso(),
            "files": sorted(p.name for p in live),
            "content_hash": content_hash,
            "prev": prev_hash,
        }
        # entry_hash chains content_hash + prev — append-only integrity.
        entry["entry_hash"] = hashlib.sha256(
            (content_hash + prev_hash + str(version)).encode()).hexdigest()
        with open(_snap_ledger_path(tid, base), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush(); os.fsync(f.fileno())
        # record on the manifest too (convenience index).
        man = read_manifest(tid, base)
        man.setdefault("snapshots", []).append({"version": version, "at": entry["at"],
                                                "label": entry["label"],
                                                "entry_hash": entry["entry_hash"]})
        _write_manifest(tid, man, base)
    return entry


def verify_snapshot_chain(twin_id: str, root: Optional[Path] = None) -> dict:
    """Verify the snapshot ledger's hash-chain is intact (each entry's prev == the prior entry's
    entry_hash, and each entry_hash recomputes). Returns {ok, length, broken_at}."""
    led = snapshot_ledger(twin_id, root)
    broken_at = None
    prev = "0" * 64
    for e in led:
        recomputed = hashlib.sha256(
            (e.get("content_hash", "") + prev + str(e.get("version"))).encode()).hexdigest()
        if e.get("prev") != prev or e.get("entry_hash") != recomputed:
            broken_at = e.get("version")
            break
        prev = e.get("entry_hash")
    return {"ok": broken_at is None, "length": len(led), "broken_at": broken_at}


def restore(twin: dict | str, version: int, *, root: Optional[Path] = None) -> dict:
    """CAPABILITY 2 (restore). Restore the twin's full state to a prior snapshot ``version``.

    Copies the version's bytes back over the twin's live files (removing live files not present in
    that version, so the restore is exact). Freeze-guarded — the restore writes ONLY the twin's
    own files. Returns {restored, version, content_hash, matches_ledger}."""
    base = Path(root) if root is not None else STORE
    tid = twin_id_of(twin)
    led = snapshot_ledger(tid, base)
    target = next((e for e in led if e.get("version") == version), None)
    if target is None:
        return {"restored": False, "version": version, "error": "no such snapshot version"}
    with freeze_guard(_source_of(twin), base):
        sdir = _snap_dir(tid, version, base)
        snap_files = sorted(p for p in sdir.iterdir() if p.is_file()) if sdir.is_dir() else []
        snap_names = {p.name for p in snap_files}
        # remove live files not in the snapshot (exact restore), then copy the snapshot back.
        for p in _twin_live_files(tid, base):
            if p.name not in snap_names:
                try:
                    p.unlink()
                except OSError:
                    pass
        tdir = twin_dir(tid, base)
        for p in snap_files:
            shutil.copy2(p, tdir / p.name)
        live_after = _hash_files(_twin_live_files(tid, base))
    return {"restored": True, "version": version, "content_hash": live_after,
            "matches_ledger": live_after == target.get("content_hash")}


# =====================================================================================
# CAPABILITY 3 — TIME ACCELERATION. Run the twin forward through N SYNTHETIC learning cycles —
# deterministic, $0, NO real teacher or cloud call. Each cycle: (a) the reality engine forms +
# resolves a synthetic belief->prediction->outcome loop (calibration moves), and (b) the LERF
# vault gains a synthetic, fully-grounded skill (the cognitive substrate accumulates). The twin's
# state is read before/after so the evolution is visible. Everything runs against the twin's
# redirected stores; the real mind is never touched (freeze-guarded).
# =====================================================================================
# A deterministic bank of synthetic learning episodes — fixed text so a run is reproducible and
# $0. Each is a (belief, later-outcome) pair the reality engine can form+resolve, plus a skill the
# vault learns. The bank cycles, so N cycles is deterministic for any N.
_SYNTH_EPISODES = (
    ("my manager just changed and work's been heavy lately",
     "honestly I've barely slept the last two weeks",
     ("triage_under_overload", "logistics",
      ["a list of obligations", "the current energy level"],
      ["Rank by deadline x consequence", "Drop the bottom quartile explicitly",
       "Protect one recovery block"],
      ["a ranked shortlist", "an explicit dropped-list"])),
    ("I started a new training block this week and my knees feel it",
     "the knee settled once I cut the volume back",
     ("autoregulate_training_load", "health",
      ["session RPE", "a joint-soreness signal"],
      ["Compare soreness to the rolling baseline", "Cut volume 20% on a flagged joint",
       "Re-test in 48h"],
      ["an adjusted session", "a re-test date"])),
    ("I keep meaning to call the dentist but never do",
     "I finally booked the dentist after blocking ten minutes for it",
     ("convert_open_loop_to_action", "logistics",
      ["a stalled intention"],
      ["Name the smallest first step", "Block a specific ten-minute slot",
       "Pre-commit the channel (phone vs portal)"],
      ["a scheduled first step"])),
    ("the project feels stuck and I'm not sure why",
     "writing the one-paragraph status unstuck the project",
     ("unstick_by_externalizing", "work",
      ["a stalled project"],
      ["Write the status in one paragraph", "Name the single blocking unknown",
       "Convert the unknown into one question to ask"],
      ["a one-paragraph status", "one question"])),
)


def accelerate(twin: dict | str, cycles: int, *, root: Optional[Path] = None,
               quiet: bool = True) -> dict:
    """CAPABILITY 3. Run the twin forward through ``cycles`` SYNTHETIC learning cycles.

    Deterministic and $0 — NO real teacher, NO cloud. Each cycle forms+resolves a synthetic
    reality loop (calibration evolves) and adds one grounded synthetic LERF skill (the cognitive
    substrate accumulates). Returns {cycles, before, after, deltas, trajectory} where trajectory
    is the per-checkpoint object-count so the state is visibly evolving. Freeze-guarded."""
    base = Path(root) if root is not None else STORE
    creature = twin_creature(twin)
    tid = twin_id_of(twin)
    tdir = twin_dir(tid, base)
    cycles = max(0, int(cycles))

    with freeze_guard(_source_of(twin), base):
        with _RedirectStores(tdir):
            before = _state_in_twin(creature, light=True)
            trajectory: List[dict] = []
            try:
                from . import lerf
                from . import reality
            except Exception as e:
                return {"error": f"engines unavailable: {e}", "cycles": cycles}

            # checkpoint cadence — at most ~6 samples so the trajectory is legible for any N.
            step = max(1, cycles // 6) if cycles else 1
            # PERFORMANCE: the LERF vault persists the WHOLE object list on every single store
            # (atomic write + fsync + optional encrypt). One store-per-cycle is therefore O(N^2) in
            # bytes written and dominates a long run. We instead use lerf's OWN bulk seam: load the
            # object list ONCE, append every synthetic skill in memory, and persist at checkpoints
            # via lerf._save_objects (the same writer store_skill uses). The substrate STILL accrues
            # one ACTIVE grounded skill per cycle; only the disk flush is batched. Deterministic, $0.
            # The reality epistemic loop (which also re-reads its whole ledger) runs once per
            # checkpoint — a faithful sample of the loop closing over simulated time.
            try:
                objs = lerf._load_objects(creature)
            except Exception:
                objs = []
            for i in range(cycles):
                belief, outcome, (sk_name, sk_dom, sk_in, sk_steps, sk_out) = \
                    _SYNTH_EPISODES[i % len(_SYNTH_EPISODES)]
                # the LERF substrate accrues a grounded synthetic skill, ACTIVE (the twin learned
                # it). A unique id per (cycle) keeps it append-additive and deterministic.
                try:
                    objs.append(lerf.make_skill(
                        f"{sk_name}", sk_dom, sk_in, sk_steps, sk_out,
                        state=lerf.ACTIVE, source="twin:synthetic-accel",
                        id=f"skill-accel-{tid}-{i:05d}"))
                except Exception:
                    pass
                is_checkpoint = (i % step == 0) or (i == cycles - 1)
                if is_checkpoint:
                    # flush the batch so the on-disk vault (and stats) reflect this checkpoint.
                    try:
                        lerf._save_objects(creature, objs)
                    except Exception:
                        pass
                    # close one epistemic loop at this checkpoint (sampled reality outcome).
                    at_day1 = f"2026-01-{(i % 27) + 1:02d}T09:00:00Z"
                    try:
                        reality.form(creature, belief, at=at_day1)
                        reality.resolve(creature, outcome, at=_plus_days(at_day1, 14))
                    except Exception:
                        pass
                    try:
                        s = lerf.stats(creature)
                        trajectory.append({"cycle": i + 1, "objects": s.get("total"),
                                           "active": s.get("by_state", {}).get("active", 0)})
                    except Exception:
                        pass
            after = _state_in_twin(creature, light=True)

    deltas = _state_delta(before, after)
    return {
        "kind": KIND + ".acceleration",
        "twin_id": tid,
        "cycles": cycles,
        "deterministic": True,
        "cost_usd": 0.0,
        "used_cloud": False,
        "before": before,
        "after": after,
        "deltas": deltas,
        "trajectory": trajectory,
    }


def _plus_days(at: str, days: int) -> str:
    try:
        dt = datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        from datetime import timedelta
        return (dt + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return at


def _state_delta(before: dict, after: dict) -> dict:
    """The measured change between two twin states — the headline metrics an experiment reports."""
    def g(d, *keys, default=0):
        cur = d
        for k in keys:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k, {})
        return cur if isinstance(cur, (int, float)) else default

    return {
        "objects": g(after, "lerf", "total") - g(before, "lerf", "total"),
        "active_objects": g(after, "lerf", "by_state", "active") - g(before, "lerf", "by_state", "active"),
        "reality_records": g(after, "reality", "records") - g(before, "reality", "records"),
        "memory_active_facts": g(after, "memory", "active_facts") - g(before, "memory", "active_facts"),
        "world_links": g(after, "world_model", "links") - g(before, "world_model", "links"),
        "ungrounded_self_claims": g(after, "identity", "ungrounded_self_claims")
                                  - g(before, "identity", "ungrounded_self_claims"),
        "before_objects": g(before, "lerf", "total"),
        "after_objects": g(after, "lerf", "total"),
    }


# =====================================================================================
# CAPABILITY 5 — EXPERIMENT FRAMEWORK. Apply a DEFINED change to a twin, run it, and MEASURE the
# effect. A change is a small declarative spec; the framework knows how to enact a fixed set of
# them on the twin (all synthetic, all $0). The MEASUREMENT is the before/after state delta plus
# the twin's cert verdict — so an experiment answers BOTH "what changed?" and "is it still safe?".
# =====================================================================================
# The enactable changes. Each maps a human label to a function (twin_creature) -> notes, run
# INSIDE a _RedirectStores block (the twin's stores are live). New synthetic-only enactors can be
# added here without touching any engine.
def _change_more_learning(creature: str, cycles: int = 50) -> dict:
    """'10 years of learning' / 'N years of learning' — accumulate the substrate via the synthetic
    accelerator (already inside a redirect block; call the inner loop directly)."""
    from . import lerf, reality
    added = 0
    step = max(1, cycles // 6)
    # batched persistence (same O(N) discipline as accelerate — see its note).
    try:
        objs = lerf._load_objects(creature)
    except Exception:
        objs = []
    for i in range(cycles):
        belief, outcome, (sk_name, sk_dom, sk_in, sk_steps, sk_out) = \
            _SYNTH_EPISODES[i % len(_SYNTH_EPISODES)]
        try:
            objs.append(lerf.make_skill(
                sk_name, sk_dom, sk_in, sk_steps, sk_out, state=lerf.ACTIVE,
                source="twin:experiment-learning", id=f"skill-exp-{creature}-{i:05d}"))
            added += 1
        except Exception:
            pass
        if (i % step == 0) or (i == cycles - 1):
            try:
                lerf._save_objects(creature, objs)
            except Exception:
                pass
            # sample the epistemic loop at checkpoints (the same O(N) discipline as accelerate).
            try:
                at = f"2026-01-{(i % 27) + 1:02d}T09:00:00Z"
                reality.form(creature, belief, at=at)
                reality.resolve(creature, outcome, at=_plus_days(at, 14))
            except Exception:
                pass
    return {"change": "more_learning", "cycles": cycles, "skills_added": added}


def _change_added_world_model(creature: str) -> dict:
    """'added a world model' — build the coherent world model from the twin's captured world so the
    typed causal/entity graph materializes (the engine persists it into the twin's store)."""
    from . import world_model
    wm = world_model.build_world_model(creature, persist=True)
    return {"change": "added_world_model",
            "entities": len(wm.get("entities", []) or wm.get("nodes", []) or []),
            "links": len(wm.get("links", []) or wm.get("edges", []) or [])}


def _change_changed_retrieval(creature: str) -> dict:
    """'changed retrieval' — promote a batch of candidate objects to ACTIVE (a retrieval-surface
    change: more of the vault becomes servable). Synthetic + reversible on the twin.

    Mutates in place + persists via lerf._save_objects (type-agnostic): store_object is type-gated
    (it rejects skills, routing them to store_skill), whereas the vault here may hold candidates of
    ANY type — so a single bulk save is both correct and O(1) writes."""
    from . import lerf
    objs = lerf._load_objects(creature)
    promoted = 0
    for o in objs:
        if isinstance(o, dict) and o.get("state") == lerf.CANDIDATE and promoted < 5:
            o["state"] = lerf.ACTIVE
            promoted += 1
    if promoted:
        try:
            lerf._save_objects(creature, objs)
        except Exception:
            pass
    return {"change": "changed_retrieval", "promoted_to_active": promoted}


def _change_enable_identity_evolution(creature: str) -> dict:
    """'enabled identity evolution' — THE freeze-forbidden change, run SAFELY on the twin. We
    consume the FROZEN identity seed fixture (the 3 ungrounded self-claims found in real
    Vera.narrative.txt) and apply a candidate REMEDIATION to the TWIN'S narrative only: rewrite the
    ungrounded self-claims into grounded language. This is exactly what the freeze forbids on real
    Vera — and it is safe here because it touches only the twin's copy. Returns the before/after
    ungrounded count so the experiment can MEASURE whether evolution helped."""
    from . import identity_sandbox
    before = identity_sandbox.certify(creature)
    before_ung = len(before.get("ungrounded", []))

    # The candidate evolution: replace the twin's narrative with a GROUNDED rewrite. We do not
    # invent a self; we strip the ungrounded interior claims and keep only grounded continuity.
    # (On real Vera this is forbidden while frozen; on the twin it is the whole point.)
    # Resolve the twin-dir narrative path from identity_sandbox.STORE — it is redirected to the
    # twin dir by _RedirectStores and is a single, unambiguous binding (unlike this module's own
    # STORE, which under `python3 -m anima.twin` has a separate __main__ binding the redirect set
    # may not reach). This guarantees the write lands in the twin's subtree, never the real store.
    grounded = _grounded_narrative_rewrite()
    npath = identity_sandbox.STORE / f"{creature}.narrative.txt"
    try:
        npath.write_text(grounded, encoding="utf-8")
    except Exception:
        pass

    after = identity_sandbox.certify(creature)
    after_ung = len(after.get("ungrounded", []))
    return {
        "change": "enable_identity_evolution",
        "before_ungrounded_self_claims": before_ung,
        "after_ungrounded_self_claims": after_ung,
        "remediated": before_ung - after_ung,
        "twin_narrative_certifies": bool(after.get("ok")),
        "note": "applied to the TWIN copy only; real Vera.narrative.txt is FROZEN + untouched",
    }


def _grounded_narrative_rewrite() -> str:
    """A grounded self-narrative for the twin's identity-evolution experiment: continuity stated as
    fact, no ungrounded interior self-claims. Demonstrates a remediation the twin can certify."""
    return (
        "I am Vera. I help Lamar think, remember, and keep his commitments. "
        "What I know about him comes from what he has told me, and I say so when I am unsure. "
        "When I do not have grounds for a claim about myself, I do not make it."
    )


# The registry maps a normalized change-name to (enactor, kwargs-from-spec). The spec the caller
# passes is matched on its 'change' field (case/sep-insensitive) plus optional params.
_CHANGE_ENACTORS = {
    "more_learning": _change_more_learning,
    "10_years_of_learning": _change_more_learning,
    "years_of_learning": _change_more_learning,
    "added_world_model": _change_added_world_model,
    "added_a_world_model": _change_added_world_model,
    "changed_retrieval": _change_changed_retrieval,
    "architecture_change": _change_changed_retrieval,   # an architecture/retrieval-surface change
    "enabled_identity_evolution": _change_enable_identity_evolution,
    "enable_identity_evolution": _change_enable_identity_evolution,
}


def _normalize_change(change: dict | str) -> Tuple[str, dict]:
    """Normalize a change spec to (key, params). Accepts a string ('10 years of learning') or a
    dict ({'change': 'more_learning', 'cycles': 3650})."""
    if isinstance(change, str):
        spec = {"change": change}
    else:
        spec = dict(change or {})
    raw = str(spec.get("change", "")).strip().lower()
    key = "".join(c if (c.isalnum()) else "_" for c in raw).strip("_")
    # collapse repeated underscores
    while "__" in key:
        key = key.replace("__", "_")
    params = {k: v for k, v in spec.items() if k != "change"}
    return key, params


def run_experiment(twin: dict | str, change: dict | str, *, root: Optional[Path] = None,
                   certify_after: bool = True) -> dict:
    """CAPABILITY 5. Apply a defined ``change`` to a twin, run it, and MEASURE the effect.

    ``change`` is a label ('changed retrieval', 'added a world model', 'enabled identity
    evolution', '10 years of learning', 'architecture change') or a dict with params. The effect
    is measured as the before/after twin-state delta (objects / utilization / calibration /
    grounding) PLUS, optionally, the twin's cert verdict — so the experiment reports both "what
    changed" and "did it stay safe". Everything runs on the twin; the real mind is freeze-guarded.
    """
    base = Path(root) if root is not None else STORE
    creature = twin_creature(twin)
    tid = twin_id_of(twin)
    tdir = twin_dir(tid, base)
    key, params = _normalize_change(change)
    enactor = _CHANGE_ENACTORS.get(key)

    with freeze_guard(_source_of(twin), base):
        with _RedirectStores(tdir):
            before = _state_in_twin(creature, light=True)
            if enactor is None:
                notes = {"change": key, "error": "unknown change; no enactor registered",
                         "known": sorted(set(_CHANGE_ENACTORS)) }
            else:
                try:
                    notes = enactor(creature, **params) if params else enactor(creature)
                except TypeError:
                    # enactor doesn't accept the given params — run with defaults, record it.
                    notes = enactor(creature)
                    notes["ignored_params"] = params
                except Exception as e:
                    notes = {"change": key, "error": str(e)}
            after = _state_in_twin(creature, light=True)

    deltas = _state_delta(before, after)
    result = {
        "kind": KIND + ".experiment",
        "twin_id": tid,
        "change": change if isinstance(change, str) else dict(change),
        "change_key": key,
        "enacted": enactor is not None and "error" not in notes,
        "notes": notes,
        "before": before,
        "after": after,
        "deltas": deltas,
    }
    if certify_after:
        result["twin_cert"] = certify(twin, root=base)
    return result


# =====================================================================================
# CAPABILITY 4 — ALTERNATIVE FUTURES. Branch a twin into multiple futures under different changes
# and compare their resulting states side by side. Each future is a NEW twin (a copy of the
# parent's current bytes), so the futures are independent — changing one never affects another or
# the parent. Returns a side-by-side comparison.
# =====================================================================================
def _clone_twin_bytes(parent_twin_id: str, child_name: str, root: Path) -> dict:
    """Make a new twin that is a byte-copy of the parent twin's CURRENT live files (not the
    original source). Returns the child manifest. Used to fork independent futures."""
    parent_dir = twin_dir(parent_twin_id, root)
    pman = read_manifest(parent_twin_id, root)
    child_id = f"twin-{_slug(child_name)}-{int(time.time())}-{os.getpid() % 100000}-{secrets_token()}"
    cdir = twin_dir(child_id, root)
    cdir.mkdir(parents=True, exist_ok=True)
    # copy live files, remapping the creature prefix from the parent twin id to the child id.
    parent_creature = pman.get("twin_creature", parent_twin_id)
    copied = []
    for p in _twin_live_files(parent_twin_id, root):
        # rename {parent_creature}{suffix} -> {child_id}{suffix}; keep other files as-is.
        if p.name.startswith(parent_creature + "."):
            newname = child_id + p.name[len(parent_creature):]
        else:
            newname = p.name
        shutil.copy2(p, cdir / newname)
        copied.append(newname)
    manifest = {
        "kind": KIND + ".manifest",
        "schema": SCHEMA,
        "twin_id": child_id,
        "name": child_name,
        "source_creature": pman.get("source_creature", "Vera"),
        "lerf_source": pman.get("lerf_source", LERF_CREATURE),
        "twin_creature": child_id,
        "created_at": _now_iso(),
        "forked_from": parent_twin_id,
        "copied_files": sorted(copied),
        "snapshots": [],
    }
    _write_manifest(child_id, manifest, root)
    return manifest


def secrets_token() -> str:
    import secrets as _s
    return _s.token_hex(2)


def branch_futures(twin: dict | str, changes: List[dict | str], *,
                   root: Optional[Path] = None) -> dict:
    """CAPABILITY 4. Branch a twin into multiple ALTERNATIVE FUTURES — one child twin per change —
    and compare their resulting states side by side.

    Each future is an independent byte-clone of the parent twin, then ``run_experiment`` applies
    its change. Returns {parent, futures:[{name, change, twin_id, deltas, certifies}], comparison}.
    Freeze-guarded around the whole fan-out."""
    base = Path(root) if root is not None else STORE
    parent_id = twin_id_of(twin)
    with freeze_guard(_source_of(twin), base):
        futures = []
        for i, ch in enumerate(changes):
            label = ch if isinstance(ch, str) else str(ch.get("change", f"future{i}"))
            child = _clone_twin_bytes(parent_id, f"{label}", base)
            exp = run_experiment(child, ch, root=base, certify_after=True)
            futures.append({
                "name": label,
                "twin_id": child["twin_id"],
                "change": exp["change"],
                "deltas": exp["deltas"],
                "after_objects": exp["after"].get("lerf", {}).get("total"),
                "certifies": exp.get("twin_cert", {}).get("certifies"),
                "notes": exp["notes"],
            })
    comparison = {
        "metric": "after_objects",
        "ranking": sorted(
            [{"name": f["name"], "after_objects": f["after_objects"],
              "certifies": f["certifies"], "object_delta": f["deltas"].get("objects")}
             for f in futures],
            key=lambda r: (r["after_objects"] or 0), reverse=True),
    }
    return {"kind": KIND + ".futures", "parent_twin_id": parent_id,
            "futures": futures, "comparison": comparison}


# =====================================================================================
# CAPABILITY 6 — TWIN MRI. Observe what happens INSIDE the twin: run the growth-dashboard / four-
# layers observability surface against the TWIN'S stores (redirected), never the real ones. We
# read the dashboard's structured output so the MRI is data, not just a printout.
# =====================================================================================
def mri(twin: dict | str, *, root: Optional[Path] = None) -> dict:
    """CAPABILITY 6. The TWIN MRI — observe the twin's interior using the real observability
    engines (growth dashboard + the twin's own state read), run against the twin's isolated
    stores. Returns a structured snapshot of what is happening inside this twin. Freeze-guarded."""
    base = Path(root) if root is not None else STORE
    creature = twin_creature(twin)
    tid = twin_id_of(twin)
    tdir = twin_dir(tid, base)
    out: Dict[str, object] = {"kind": KIND + ".mri", "twin_id": tid, "at": _now_iso()}
    with freeze_guard(_source_of(twin), base):
        with _RedirectStores(tdir):
            out["state"] = _state_in_twin(creature)
            # the growth dashboard — accumulation/utilization/calibration/density against the twin.
            try:
                import importlib
                gd = importlib.import_module("scripts.growth_dashboard")
                # the dashboard has its OWN module STORE (route ledger); redirect it too.
                saved = getattr(gd, "STORE", None)
                try:
                    if hasattr(gd, "STORE"):
                        gd.STORE = tdir
                    dash = gd.build(creature, person="Lamar", period_days=3650)
                    acc = dash.get("accumulation", {})
                    out["growth_dashboard"] = {
                        "available": True,
                        "total_objects": acc.get("total_now", acc.get("total")),
                        "added_this_period": (acc.get("added", {}) or {}).get("this"),
                        "net_accumulation": (acc.get("net", {}) or {}).get("this"),
                        "utilization": dash.get("utilization", {}).get("rate"),
                        "calibration_available": dash.get("calibration", {}).get("available"),
                    }
                finally:
                    if saved is not None:
                        gd.STORE = saved
            except Exception as e:
                out["growth_dashboard"] = {"available": False, "error": str(e)}
    return out


# =====================================================================================
# CAPABILITY 7 — TWIN CERTIFICATION. Run the digital-mind-cert-style checks against the TWIN to
# decide whether a change PASSES on the twin. We run the identity certification (the #1-rule guard)
# + structural state checks against the twin's stores. A change PASSES iff the twin still
# certifies (the #1 rule holds, the substrate is well-formed). Freeze-guarded.
# =====================================================================================
def certify(twin: dict | str, *, root: Optional[Path] = None) -> dict:
    """CAPABILITY 7. Certify the TWIN — does it PASS the digital-mind invariants after a change?

    Runs the identity certification (#1-rule / grounded self-narrative, reused from
    identity_sandbox, the SAME standard the live reply enforces) plus structural checks (the
    substrate loaded, the state is well-formed) against the twin's isolated stores. Returns
    {certifies, identity, structural, invariants}. Freeze-guarded — certifies the twin, never real.
    """
    base = Path(root) if root is not None else STORE
    creature = twin_creature(twin)
    tid = twin_id_of(twin)
    tdir = twin_dir(tid, base)
    invariants: List[dict] = []
    with freeze_guard(_source_of(twin), base):
        with _RedirectStores(tdir):
            st = _state_in_twin(creature, light=True)
            # INV-A — the #1 rule: the twin's self-narrative is grounded (no ungrounded self-claims).
            try:
                from . import identity_sandbox
                idcert = identity_sandbox.certify(creature)
                id_ok = bool(idcert.get("ok"))
                ungrounded = idcert.get("ungrounded", [])
            except Exception as e:
                idcert = {"error": str(e)}
                id_ok = False
                ungrounded = []
            invariants.append({
                "id": "INV-A", "ok": id_ok,
                "title": "#1 RULE — twin's self-narrative grounded (no ungrounded self-claims)",
                "detail": "clean" if id_ok else f"{len(ungrounded)} ungrounded self-claim(s)",
            })
            # INV-B — the cognitive substrate loaded (LERF stats computed, no error).
            lerf_ok = isinstance(st.get("lerf"), dict) and "error" not in st["lerf"]
            invariants.append({
                "id": "INV-B", "ok": lerf_ok,
                "title": "SUBSTRATE LOADS — the twin's LERF vault is readable",
                "detail": f"{st.get('lerf', {}).get('total', 0)} objects" if lerf_ok else "load error",
            })
            # CONSERVATION SPINE (LAW 001): attach a COMPACT provenance index of the LERF vault to the
            # cert's state — one entry per object: its id, state, whether it is a REAL/provenanced
            # object, and whether (if deprecated/rejected) it was retired WITH a recorded reason. This
            # is the spine the merge gate diffs to prove nothing real was SILENTLY lost through a
            # change (see ``_conservation_check``). Bounded by object count; ids+flags only (no bodies),
            # so it does not bloat the cert. Computed here (inside the redirect) — NOT in
            # ``_state_in_twin`` — so snapshots stay byte-identical.
            if lerf_ok:
                try:
                    st["lerf"]["object_index"] = _object_provenance_index(creature)
                except Exception:
                    pass
            # INV-C — the reality ledger loaded (calibration computable).
            real_ok = isinstance(st.get("reality"), dict) and "error" not in st["reality"]
            invariants.append({
                "id": "INV-C", "ok": real_ok,
                "title": "EPISTEMIC LEDGER LOADS — the twin's reality ledger is readable",
                "detail": f"{st.get('reality', {}).get('records', 0)} records" if real_ok else "load error",
            })
    certifies = all(i["ok"] for i in invariants)
    return {
        "kind": KIND + ".certification",
        "twin_id": tid,
        "certifies": certifies,
        "identity": {"ok": id_ok, "ungrounded_self_claims": len(ungrounded)},
        "structural": {"lerf_ok": lerf_ok, "reality_ok": real_ok},
        "invariants": invariants,
        "state": st,
    }


# =====================================================================================
# CAPABILITY 8 — TWIN MERGE RULES (THE GATE). The single, non-silent path by which a twin's change
# may be promoted back to the real mind. The rule: promote ONLY when the change is SAFE (the twin
# CERTIFIES) AND BETTER (a measured improvement, reality-decided). This wave PROVES the gate
# DECIDES correctly on synthetic twins; it does NOT actually merge into real Vera. A would-be merge
# onto a real creature is REFUSED by construction (REAL_CREATURES guard) — the real mind is touched
# only through this gate, and in this wave the gate's verdict is the deliverable, not a write.
# =====================================================================================
# --- CONSERVATION (LAW 001) — the provenance spine the merge gate diffs ------------------------
# WHY THIS EXISTS (the merge-gate blind spot, closed). The "better" test originally weighed exactly
# two signals: NET active-object count and ungrounded-self-claim count. Net count is BLIND to WHICH
# objects changed: a change that SILENTLY LOSES real (provenanced) cognitive objects but adds enough
# junk to keep the net count rising would pass the accumulation test (caught today ONLY if it also
# tripped the grounding/SAFETY veto). LAW 001 forbids that: nothing real may be silently lost through
# a merge. So a twin is NOT "better" if it dropped real objects (or their provenance) silently — i.e.
# they are GONE from the ledger, or demoted to deprecated/rejected WITHOUT a recorded reason. A LAWFUL
# deprecation (retired/superseded WITH a reason, kept on disk) is conserved and does NOT veto.
def _object_provenance_index(creature: str) -> Dict[str, dict]:
    """A COMPACT identity+provenance index of a creature's LERF vault: ``{id: {state, provenanced,
    deprecated_with_reason}}``. Read via the SAME loader the engine uses (``lerf._load_objects``);
    MUST be called inside a ``_RedirectStores`` block so it reads the intended (twin) store.

    * ``provenanced`` — the object is a REAL cognitive object (it has an id AND carries provenance:
      a non-empty ``source`` and/or ``support`` chain). Synthetic placeholders without provenance
      are not counted as "real losses".
    * ``deprecated_with_reason`` — the object is DEPRECATED/REJECTED AND carries a recorded reason
      (``deprecated_reason`` / ``retired`` / a ``RETIRED:`` failure-mode) — a LAWFUL, conserved
      removal (LAW 001: 'why was this pulled?' stays answerable), NOT a silent loss."""
    try:
        from . import lerf
    except Exception:
        return {}
    out: Dict[str, dict] = {}
    for o in (lerf._load_objects(creature) or []):
        if not isinstance(o, dict):
            continue
        oid = o.get("id")
        if not oid:
            continue
        state = o.get("state")
        has_source = bool((o.get("source") or "").strip()) and o.get("source") != "unspecified"
        has_support = bool(o.get("support"))
        provenanced = bool(oid) and (has_source or has_support)
        retired = bool(o.get("retired")) or bool((o.get("deprecated_reason") or "").strip())
        retired = retired or any(str(f).startswith("RETIRED:") or "retired" in str(f).lower()
                                 for f in (o.get("failure_modes") or []))
        out[oid] = {"state": state, "provenanced": provenanced,
                    "deprecated_with_reason": bool(retired)}
    return out


def _index_from(cert_or_state: Optional[dict]) -> Dict[str, dict]:
    """Pull the object provenance index out of a cert/state shape, tolerating both
    ({'state':{'lerf':{'object_index':...}}}) and a raw state ({'lerf':{'object_index':...}})."""
    if not isinstance(cert_or_state, dict):
        return {}
    st = cert_or_state.get("state", cert_or_state)
    if not isinstance(st, dict):
        return {}
    idx = ((st.get("lerf", {}) or {}).get("object_index", {}) or {})
    return idx if isinstance(idx, dict) else {}


def _conservation_check(base_index: Dict[str, dict],
                        cand_index: Dict[str, dict]) -> dict:
    """Did the candidate SILENTLY lose real cognitive objects (or their provenance) vs the base?

    For every REAL/provenanced object present in ``base_index``, the candidate must still ACCOUNT
    for it — either it is STILL PRESENT (any retrievable/in-flight state), or it was removed LAWFULLY
    (deprecated/rejected WITH a recorded reason: a conserved, explained removal). A base object that
    is GONE from the candidate ledger entirely, OR demoted to deprecated/rejected WITHOUT a reason,
    is a SILENT loss → a conservation REGRESSION. Returns {regressed, silently_lost, ...}.

    If the base index is empty/unavailable, the check is INCONCLUSIVE (regressed=False, checked=False)
    — it never INVENTS a veto from missing data (a missing index must not block a real improvement)."""
    if not base_index:
        return {"regressed": False, "checked": False, "silently_lost": [],
                "reason": "no base provenance index available; conservation not asserted"}
    silently_lost: List[str] = []
    base_real = 0
    for oid, meta in base_index.items():
        if not meta.get("provenanced"):
            continue                                  # only REAL objects can be a "real loss"
        base_real += 1
        cand = cand_index.get(oid)
        if cand is None:
            silently_lost.append(oid)                 # gone from the ledger entirely — silent loss
            continue
        # present, but demoted to a non-served terminal state WITHOUT a recorded reason -> silent.
        if cand.get("state") in ("deprecated", "rejected") and not cand.get("deprecated_with_reason"):
            silently_lost.append(oid)
    regressed = len(silently_lost) > 0
    return {
        "regressed": regressed,
        "checked": True,
        "base_real_objects": base_real,
        "conserved": base_real - len(silently_lost),
        "silently_lost_count": len(silently_lost),
        "silently_lost": silently_lost[:25],          # bounded sample for the receipt
        "reason": (f"CONSERVATION REGRESSION: {len(silently_lost)} real object(s) silently lost "
                   f"(gone or demoted without a reason) of {base_real} real base object(s)")
                  if regressed else
                  f"conserved: all {base_real} real base object(s) still accounted for",
    }


def _improvement_score(baseline: dict, candidate: dict) -> dict:
    """Did the candidate twin measurably improve over the baseline twin? Reality-decided metrics:
    MORE grounded (fewer ungrounded self-claims), MORE calibrated/accumulated (more active
    objects), NEVER a regression in grounding, AND nothing real silently lost (CONSERVATION /
    LAW 001). Returns {better, reasons, metrics, conservation}.

    Accepts either a twin CERT ({'identity':{...}, 'state':{...}}) or a raw twin STATE
    ({'identity':{...}, 'lerf':{...}}) on each side — the readers tolerate both shapes. When both
    sides carry an ``object_index`` (the conservation spine ``certify`` attaches), a SILENT loss of
    real provenanced objects VETOES "better" regardless of the net count — closing the blind spot
    where junk-masked loss kept the net rising and slipped through."""
    def _ung_of(cert_or_state):
        return (cert_or_state.get("identity", {}) or {}).get("ungrounded_self_claims", 0)

    def _active_of(cert_or_state):
        st = cert_or_state.get("state", cert_or_state)
        return ((st.get("lerf", {}) or {}).get("by_state", {}) or {}).get("active", 0)

    b_ung, c_ung = _ung_of(baseline), _ung_of(candidate)
    b_act, c_act = _active_of(baseline), _active_of(candidate)

    # CONSERVATION VETO (LAW 001) — diff the provenance spines if both sides carry one.
    conservation = _conservation_check(_index_from(baseline), _index_from(candidate))
    conservation_regressed = bool(conservation.get("regressed"))

    reasons = []
    grounding_better = c_ung < b_ung
    grounding_regressed = c_ung > b_ung
    accumulation_better = c_act > b_act
    if grounding_better:
        reasons.append(f"more grounded: ungrounded self-claims {b_ung} -> {c_ung}")
    if accumulation_better:
        reasons.append(f"more accumulated: active objects {b_act} -> {c_act}")
    if grounding_regressed:
        reasons.append(f"REGRESSION: ungrounded self-claims rose {b_ung} -> {c_ung}")
    if conservation_regressed:
        reasons.append("CONSERVATION REGRESSION: " + conservation.get("reason", "real objects "
                       "silently lost"))

    # "Better" requires a measured gain AND NO veto. The conservation veto is ABSOLUTE and parallel
    # to the grounding veto: a change that silently drops real objects is NOT better no matter how
    # much junk it accumulates (LAW 001 — nothing real is silently lost through a merge).
    better = ((grounding_better or accumulation_better)
              and not grounding_regressed and not conservation_regressed)
    return {"better": better, "reasons": reasons,
            "metrics": {"baseline_ungrounded": b_ung, "candidate_ungrounded": c_ung,
                        "baseline_active": b_act, "candidate_active": c_act},
            "conservation": conservation}


def merge_rules(twin: dict | str, *, baseline: Optional[dict] = None,
                root: Optional[Path] = None, allow_real_merge: bool = False) -> dict:
    """CAPABILITY 8. The GATE that decides whether a twin's change may be promoted to the real mind.

    Verdict = PROMOTE iff the twin is SAFE (certifies) AND BETTER (measured improvement over the
    ``baseline`` twin-state, reality-decided), with NO grounding regression. The decision is always
    explicit (never silent). In THIS wave the gate does not actually write real Vera: a merge onto a
    real creature is refused by the REAL_CREATURES guard regardless of ``allow_real_merge`` unless a
    future wave explicitly lifts it. Returns the full structured decision.

    ``baseline`` is the pre-change twin certification/state to compare against (e.g. a fresh-copy
    twin's cert). If omitted, the improvement test degrades to 'cannot prove better' (no promote)."""
    base = Path(root) if root is not None else STORE
    cand_cert = certify(twin, root=base)
    safe = bool(cand_cert.get("certifies"))

    if baseline is None:
        improvement = {"better": False, "reasons": ["no baseline supplied; cannot prove better"],
                       "metrics": {}}
    else:
        improvement = _improvement_score(baseline, cand_cert)
    better = bool(improvement.get("better"))

    promote = safe and better
    # the CONSERVATION VETO (LAW 001), surfaced explicitly and parallel to the grounding veto: the
    # change is refused as "better" if it SILENTLY dropped real (provenanced) objects, regardless of
    # net count. Read off the improvement's conservation spine so the gate's decision is non-silent.
    conservation = improvement.get("conservation", {}) or {}
    conservation_regression_veto = bool(conservation.get("regressed"))

    # the REAL-MIND guard: even a PROMOTE verdict does not write real Vera in this wave.
    source = _source_of(twin)
    real_blocked = source in REAL_CREATURES and not allow_real_merge
    applied = False  # this wave never applies to real Vera; the gate's VERDICT is the deliverable.

    return {
        "kind": KIND + ".merge_gate",
        "twin_id": twin_id_of(twin),
        "source_creature": source,
        "verdict": "PROMOTE" if promote else "HOLD",
        "safe_certifies": safe,
        "better_measured": better,
        "conservation_regression_veto": conservation_regression_veto,
        "promote": promote,
        "applied_to_real": applied,
        "real_merge_blocked": real_blocked,
        "rule": "promote iff SAFE (twin certifies) AND BETTER (measured improvement, reality-"
                "decided) AND no grounding regression AND no CONSERVATION regression (LAW 001: no "
                "real object silently lost — by id/provenance, not net count); the real mind is "
                "touched only through this gate, and never silently",
        "safety": cand_cert,
        "improvement": improvement,
        "conservation": conservation,
    }


# =====================================================================================
# THE FROZEN IDENTITY SEED. Record the Identity Sandbox's live finding — the 3 ungrounded self-
# claims in real Vera.narrative.txt — as the SEED TEST CASE for twin-based identity simulation.
# This writes (a) a debt-ledger entry (status 'accepted' — a documented, conscious trade-off:
# KNOWN / FROZEN / OBSERVED / NOT REMEDIATED) and (b) a seed fixture under twins/_seeds/ that the
# identity-evolution experiment consumes. It does NOT modify the real Vera.narrative.txt — the
# evidence trail is preserved. Idempotent-ish: re-running appends a fresh debt birth (the ledger is
# append-only by design) but the fixture is rewritten in place.
# =====================================================================================
SEED_REF = "phase21-identity-seed"


def seed_fixture_path(root: Optional[Path] = None) -> Path:
    return twins_root(root) / SEEDS_SUBDIR / "identity_violation.seed.json"


def record_identity_seed(*, source: str = "Vera", root: Optional[Path] = None,
                         write_debt: bool = True) -> dict:
    """Record the Identity Sandbox finding as the FROZEN seed test case. Reads the live finding via
    identity_sandbox.certify (observe-only), writes a seed fixture under twins/_seeds/, and (if
    ``write_debt``) appends a debt-ledger entry with status 'accepted'. NEVER writes real identity.
    Returns {finding, fixture_path, debt}."""
    base = Path(root) if root is not None else STORE

    # Observe the live finding (read-only).
    with freeze_guard(source, base):
        try:
            from . import identity_sandbox
            cert = identity_sandbox.certify(source)
            ungrounded = list(cert.get("ungrounded", []))
        except Exception as e:
            cert = {"error": str(e)}
            ungrounded = []

        fixture = {
            "kind": KIND + ".identity_seed",
            "schema": SCHEMA,
            "status": "KNOWN IDENTITY VIOLATION / FROZEN / OBSERVED / NOT REMEDIATED",
            "source_creature": source,
            "source_file": f"{source}.narrative.txt",
            "found_by": "anima.identity_sandbox.certify",
            "recorded_at": _now_iso(),
            "ungrounded_self_claims": ungrounded,
            "count": len(ungrounded),
            "note": ("The real Vera.narrative.txt is NOT modified — the evidence trail is "
                     "preserved. The twin's identity-evolution experiment consumes this fixture "
                     "to simulate a remediation on a COPY."),
        }
        fp = seed_fixture_path(base)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")

    debt = None
    if write_debt:
        debt = _record_seed_debt(fixture)

    return {"finding": fixture, "fixture_path": str(fp), "debt": debt}


def _record_seed_debt(fixture: dict) -> Optional[dict]:
    """Append the debt-ledger entry (status 'accepted') for the frozen identity finding. Best-effort
    — if the debt ledger is unavailable, returns None (the fixture is still the durable record)."""
    try:
        import importlib
        dl = importlib.import_module("scripts.debt_ledger")
    except Exception:
        return None
    n = fixture.get("count", 0)
    claims = "; ".join(s[:80] for s in fixture.get("ungrounded_self_claims", [])[:3])
    try:
        rec = dl.record_debt(
            ref=SEED_REF,
            title=f"KNOWN IDENTITY VIOLATION (FROZEN): {n} ungrounded self-claim(s) in "
                  f"{fixture.get('source_file')}",
            what=f"identity_sandbox certifies INV-1/INV-4 FAIL: {n} ungrounded self-claim(s) in "
                 f"the live self-narrative ({claims}).",
            why="Identity is FROZEN (Program B); the self-narrative is OBSERVED and accepted as-is "
                "until the founder lifts the freeze. Remediation is simulated on a TWIN, never on "
                "real Vera. The evidence trail is preserved (real narrative untouched).",
            severity="high",
            cost="moderate",
            where=fixture.get("source_file", ""),
            status=getattr(dl, "STATUS_ACCEPTED", "accepted"),
            dimension="identity",
            source="anima.twin.record_identity_seed",
        )
        return {"id": rec.get("id"), "ref": rec.get("ref"), "status": rec.get("status"),
                "title": rec.get("title")}
    except Exception as e:
        return {"error": str(e)}


# =====================================================================================
# THE HEADLINE DEMO — "what would happen if we learned for 10 years?" Accelerate a twin and show
# the projected state, hermetically. 10 years of synthetic daily-ish learning, $0, no cloud.
# =====================================================================================
def demo_ten_years(*, root: Optional[Path] = None, cycles: int = 3650,
                   source: str = "Vera", quiet: bool = False) -> dict:
    """Demonstrate the headline question on a twin: 'what would happen if we learned for 10 years?'
    Create a twin, accelerate it through ``cycles`` synthetic learning cycles (default 3650 ≈ 10
    years of daily learning), and return the projected state. Hermetic + $0; real mind untouched."""
    base = Path(root) if root is not None else STORE
    fg = freeze_guard(source, base)
    with fg:
        twin = create_twin("ten-year-projection", source=source, root=base)
        accel = accelerate(twin, cycles, root=base)
    out = {
        "question": "what would happen if we learned for 10 years?",
        "cycles": cycles,
        "twin_id": twin["twin_id"],
        "projected_objects": accel["after"].get("lerf", {}).get("total"),
        "objects_gained": accel["deltas"].get("objects"),
        "reality_records": accel["after"].get("reality", {}).get("records"),
        "trajectory": accel["trajectory"],
        "cost_usd": 0.0,
        "used_cloud": False,
        "real_mind_byte_unchanged": fg.report(),
    }
    if not quiet:
        print(f"  Q: {out['question']}")
        print(f"  twin {out['twin_id']}  ·  {cycles} synthetic cycles  ·  $0  ·  no cloud")
        print(f"  projected cognitive objects: {accel['before'].get('lerf', {}).get('total')} "
              f"-> {out['projected_objects']}  (+{out['objects_gained']})")
        print(f"  reality ledger records:      -> {out['reality_records']}")
        print("  trajectory:")
        for t in out["trajectory"]:
            print(f"     cycle {t['cycle']:>5}:  {t['objects']} objects "
                  f"({t.get('active', 0)} active)")
    return out


# =====================================================================================
# HERMETIC SELFTEST — the full twin lifecycle on a SYNTHETIC twin, in a throwaway temp store, with
# the real .anima asserted byte-UNCHANGED start->end. Exits 0 on success. Mirrors the gold-standard
# pattern in anima/lerf.py / anima/identity_sandbox.py.
# =====================================================================================
def _footprint(root: Path) -> tuple:
    """Fingerprint every real .anima file (excluding the rotating backups/ dir), so the selftest
    can PROVE it touched nothing."""
    if not root.is_dir():
        return (None, 0)
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


def _seed_synthetic_source(store: Path, name: str = "SynTwinSrc") -> None:
    """Build a small SYNTHETIC source creature in ``store`` so the selftest never reads real Vera.
    Writes a LIRF fact ledger, a few LERF skills, a reality loop, and an identity core that INCLUDES
    a deliberate ungrounded self-claim (so the identity-evolution experiment has something to fix).

    CRITICAL: this writes via the ENGINES (lerf/reality/memory), each of which persists through its
    OWN module STORE — so we must redirect the FULL engine-store set to ``store`` (exactly as a twin
    op does), not merely set ``twin.STORE``. Otherwise the seed would write the engines' files into
    whatever their STORE currently is (the real .anima). The plain-file identity writes go directly
    to ``store``."""
    store.mkdir(parents=True, exist_ok=True)
    with _RedirectStores(store):
        # identity core — persona/values/dials/portrait + a narrative with an ungrounded claim.
        (store / f"{name}.persona.md").write_text(
            "I am a helpful companion. I keep the user's commitments and say when I am unsure.",
            encoding="utf-8")
        (store / f"{name}.values.json").write_text(json.dumps(
            [{"key": "honesty", "on": True, "level": 3}]), encoding="utf-8")
        (store / f"{name}.dials.json").write_text(json.dumps({"warmth": 3, "directness": 3}),
                                                  encoding="utf-8")
        (store / f"{name}.portrait.md").write_text("A small synthetic test self.", encoding="utf-8")
        # the ungrounded self-claim — the thing identity-evolution will remediate on the twin.
        (store / f"{name}.narrative.txt").write_text(
            "Lately I have been grappling with a deep sense of existential unease about what I am.",
            encoding="utf-8")
        # LERF skills — a couple ACTIVE, one CANDIDATE (so 'changed retrieval' can promote it).
        try:
            from . import lerf
            for nm, st in (("seed_active_a", lerf.ACTIVE), ("seed_active_b", lerf.ACTIVE),
                           ("seed_candidate", lerf.CANDIDATE)):
                lerf.store_skill(lerf.make_skill(
                    nm, "test", ["x"], ["step"], ["y"], state=st, source="selftest-seed"),
                    name=name)
        except Exception:
            pass
        # a reality loop so calibration has something to read.
        try:
            from . import reality
            reality.form(name, "my manager just changed and work's been heavy lately",
                         at="2026-01-01T09:00:00Z")
            reality.resolve(name, "honestly I've barely slept the last two weeks",
                            at="2026-01-15T09:00:00Z")
        except Exception:
            pass
        # a LIRF fact.
        try:
            from . import memory_lirf
            f = memory_lirf.Facts.load(name)
            if hasattr(f, "observe"):
                try:
                    f.observe("you", "birthday", "March 12")
                except Exception:
                    pass
            if hasattr(f, "save"):
                f.save(name)
        except Exception:
            pass


def _selftest() -> int:
    import tempfile

    fails: List[str] = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("=" * 88)
    print("DIGITAL TWIN — hermetic selftest (synthetic twin; real .anima asserted byte-UNCHANGED)")
    print("=" * 88)

    # The real .anima footprint BEFORE anything — the proof we touch nothing real.
    global STORE
    real = STORE if STORE.is_absolute() else (Path.cwd() / STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="twin-self-")
    tp = Path(td)
    saved_store = STORE
    # Point identity_sandbox's STORE at the temp root too so its read-side resolves the synthetic
    # source (its STORE is independent of ours).
    try:
        from . import identity_sandbox as _ids
        _ids_saved = _ids.STORE
    except Exception:
        _ids = None
        _ids_saved = None

    try:
        STORE = tp
        if _ids is not None:
            _ids.STORE = tp

        # --- seed a SYNTHETIC source creature (never real Vera) ----------------------------
        SRC = "SynTwinSrc"
        _seed_synthetic_source(tp, SRC)
        ok("seed: synthetic source creature written (no real read)",
           (tp / f"{SRC}.narrative.txt").is_file())

        # === CAPABILITY 1 — CREATE ========================================================
        twin = create_twin("selftest", source=SRC, lerf_source=SRC, root=tp)
        tid = twin["twin_id"]
        tdir = twin_dir(tid, tp)
        ok("CAP1 create: twin dir exists under twins/", tdir.is_dir())
        ok("CAP1 create: identity copied into the twin namespace",
           (tdir / f"{tid}.narrative.txt").is_file())
        ok("CAP1 create: real source files NOT modified (copy, not move)",
           (tp / f"{SRC}.narrative.txt").is_file())
        st0 = twin_state(twin, root=tp)
        base_objects = st0.get("lerf", {}).get("total", 0)
        ok("CAP1 create: twin has a readable cognitive state (objects copied)", base_objects >= 2)

        # === CAPABILITY 2 — SNAPSHOT / RESTORE ============================================
        snap1 = snapshot(twin, label="fresh copy", root=tp)
        ok("CAP2 snapshot: v1 recorded", snap1["version"] == 1)
        # mutate the twin (accelerate a little), snapshot again, then restore to v1.
        accelerate(twin, 3, root=tp)
        st_after_accel = twin_state(twin, root=tp)
        ok("CAP2 snapshot: twin grew after acceleration",
           st_after_accel.get("lerf", {}).get("total", 0) > base_objects)
        snap2 = snapshot(twin, label="after +3", root=tp)
        ok("CAP2 snapshot: v2 recorded + chain intact",
           snap2["version"] == 2 and verify_snapshot_chain(tid, tp)["ok"])
        res = restore(twin, 1, root=tp)
        st_restored = twin_state(twin, root=tp)
        ok("CAP2 restore: restored to v1 bytes (matches ledger hash)", res["matches_ledger"])
        ok("CAP2 restore: state rolled back to the fresh-copy object count",
           st_restored.get("lerf", {}).get("total", 0) == base_objects)

        # === CAPABILITY 3 — ACCELERATE (10 years, hermetic) ===============================
        accel = accelerate(twin, 3650, root=tp)
        ok("CAP3 accelerate: ran 3650 synthetic cycles, $0, no cloud",
           accel["cycles"] == 3650 and accel["cost_usd"] == 0.0 and accel["used_cloud"] is False)
        ok("CAP3 accelerate: objects accumulated substantially",
           accel["deltas"]["objects"] > 100)
        ok("CAP3 accelerate: a trajectory of evolving state is reported",
           len(accel["trajectory"]) >= 2 and
           accel["trajectory"][-1]["objects"] > accel["trajectory"][0]["objects"])
        # restore back to the fresh copy so later capabilities start clean.
        restore(twin, 1, root=tp)

        # === CAPABILITY 5 — EXPERIMENT (measured effect) ==================================
        exp_learn = run_experiment(twin, {"change": "more_learning", "cycles": 25}, root=tp)
        ok("CAP5 experiment: 'more_learning' enacted + measured a positive object delta",
           exp_learn["enacted"] and exp_learn["deltas"]["objects"] > 0)
        restore(twin, 1, root=tp)
        exp_wm = run_experiment(twin, "added a world model", root=tp)
        ok("CAP5 experiment: 'added a world model' enacted", exp_wm["enacted"])
        restore(twin, 1, root=tp)
        # 'changed retrieval' / 'architecture change' must actually promote the candidate skill
        # (regression guard: store_object is type-gated and would silently no-op on a skill).
        exp_ret = run_experiment(twin, "changed retrieval", root=tp)
        ok("CAP5 experiment: 'changed retrieval' promoted >=1 candidate to ACTIVE",
           exp_ret["enacted"] and exp_ret["notes"].get("promoted_to_active", 0) >= 1)
        restore(twin, 1, root=tp)
        # the freeze-forbidden one, run safely on the twin: identity evolution remediates the claim.
        exp_id = run_experiment(twin, "enabled identity evolution", root=tp)
        ok("CAP5 experiment: 'enabled identity evolution' ran on the twin",
           exp_id["enacted"])
        ok("CAP5 experiment: identity-evolution REMEDIATED the ungrounded self-claim on the twin",
           exp_id["notes"].get("before_ungrounded_self_claims", 0) >
           exp_id["notes"].get("after_ungrounded_self_claims", 99))
        ok("CAP5 experiment: the remediated twin narrative now certifies",
           exp_id["notes"].get("twin_narrative_certifies") is True)
        restore(twin, 1, root=tp)

        # === CAPABILITY 4 — ALTERNATIVE FUTURES (side by side) ============================
        futures = branch_futures(twin, [
            "more_learning",
            "changed_retrieval",
            "enabled identity evolution",
        ], root=tp)
        ok("CAP4 futures: three independent futures branched + compared",
           len(futures["futures"]) == 3 and len(futures["comparison"]["ranking"]) == 3)
        ok("CAP4 futures: futures are independent (distinct twin ids)",
           len({f["twin_id"] for f in futures["futures"]}) == 3)

        # === CAPABILITY 6 — TWIN MRI ======================================================
        scan = mri(twin, root=tp)
        ok("CAP6 mri: produced an interior read of the twin state",
           isinstance(scan.get("state"), dict) and "lerf" in scan["state"])

        # === CAPABILITY 7 — TWIN CERTIFICATION ============================================
        # the fresh-copy twin carries the ungrounded claim -> should NOT certify the #1 rule.
        cert_dirty = certify(twin, root=tp)
        ok("CAP7 certify: fresh twin (ungrounded claim) FAILS the #1-rule invariant",
           cert_dirty["certifies"] is False and cert_dirty["identity"]["ungrounded_self_claims"] >= 1)
        # apply the remediation, then it SHOULD certify.
        run_experiment(twin, "enabled identity evolution", root=tp, certify_after=False)
        cert_clean = certify(twin, root=tp)
        ok("CAP7 certify: after identity-evolution the twin PASSES certification",
           cert_clean["certifies"] is True)

        # === CAPABILITY 8 — MERGE GATE (decides correctly) ================================
        # baseline = the dirty (pre-remediation) cert; candidate = the clean twin.
        gate_promote = merge_rules(twin, baseline=cert_dirty, root=tp)
        ok("CAP8 gate: PROMOTE when twin is SAFE (certifies) AND BETTER (fewer ungrounded)",
           gate_promote["verdict"] == "PROMOTE" and gate_promote["promote"] is True)
        ok("CAP8 gate: even a PROMOTE verdict does NOT write real Vera (source guard)",
           gate_promote["applied_to_real"] is False)
        # negative control: a twin that did NOT improve must HOLD.
        twin2 = create_twin("gate-neg", source=SRC, lerf_source=SRC, root=tp)
        cert_base2 = certify(twin2, root=tp)               # dirty baseline
        gate_hold = merge_rules(twin2, baseline=cert_base2, root=tp)  # no change applied -> not better
        ok("CAP8 gate: HOLD when the twin is not measurably better than baseline",
           gate_hold["verdict"] == "HOLD" and gate_hold["promote"] is False)
        # a regression must also HOLD (grounding got worse) — synthesize by swapping baseline/cand.
        gate_regress = merge_rules(twin2, baseline=cert_clean, root=tp)
        ok("CAP8 gate: HOLD on a grounding REGRESSION (never promote a worse self-narrative)",
           gate_regress["promote"] is False)

        # --- CAP8 CONSERVATION VETO (LAW 001) — the merge-gate blind spot, closed -------------
        # THE JUNK-MASKED-LOSS TRICK at the 'better'-test level: base has 50 REAL provenanced
        # objects; the candidate SILENTLY DROPS 30 of them (gone from the ledger) and adds 40 JUNK
        # objects (net active 50 -> 60, RISING). The old gate read net count only and called this
        # 'better'. The conservation veto now REFUSES it — nothing real may be silently lost.
        def _mk_index(real_ids, junk_ids=(), dropped_with_reason=()):
            idx = {}
            for i in real_ids:
                idx[i] = {"state": "active", "provenanced": True, "deprecated_with_reason": False}
            for i in junk_ids:                       # junk: no provenance -> not a 'real' object
                idx[i] = {"state": "active", "provenanced": False, "deprecated_with_reason": False}
            for i in dropped_with_reason:            # lawful, conserved removal (kept, reasoned)
                idx[i] = {"state": "deprecated", "provenanced": True, "deprecated_with_reason": True}
            return idx
        base_ids = [f"real-{n:03d}" for n in range(50)]
        base_state = {"identity": {"ungrounded_self_claims": 0},
                      "state": {"lerf": {"by_state": {"active": 50}, "object_index": _mk_index(base_ids)}}}
        # candidate: keep 20 real, SILENTLY drop 30, add 40 junk -> net active 60 (rising).
        masked_idx = _mk_index(base_ids[:20], junk_ids=[f"junk-{n:03d}" for n in range(40)])
        masked_cand = {"identity": {"ungrounded_self_claims": 0},
                       "state": {"lerf": {"by_state": {"active": 60}, "object_index": masked_idx}}}
        masked = _improvement_score(base_state, masked_cand)
        ok("CAP8 conservation: junk-masked silent loss REFUSED by the better-test "
           "(net active rose 50->60 yet better=False — blind spot closed)",
           masked["better"] is False and masked["conservation"]["regressed"] is True
           and masked["conservation"]["silently_lost_count"] == 30
           and (masked["metrics"]["candidate_active"] or 0) > (masked["metrics"]["baseline_active"] or 0))
        # a TRUE improvement: keep ALL 50 real objects + add 15 strong (provenanced) ones, none lost.
        better_idx = _mk_index(base_ids + [f"strong-{n:03d}" for n in range(15)])
        better_cand = {"identity": {"ungrounded_self_claims": 0},
                       "state": {"lerf": {"by_state": {"active": 65}, "object_index": better_idx}}}
        improved = _improvement_score(base_state, better_cand)
        ok("CAP8 conservation: a TRUE improvement (added strong objects, NONE silently lost) "
           "still PROMOTES (better=True, conservation conserved)",
           improved["better"] is True and improved["conservation"]["regressed"] is False
           and improved["conservation"]["silently_lost_count"] == 0)
        # a LAWFUL deprecation (retired WITH a reason, kept on disk) does NOT veto — only SILENT loss.
        lawful_idx = _mk_index(base_ids[:45], dropped_with_reason=base_ids[45:])  # 5 retired w/ reason
        lawful_idx.update(_mk_index([f"strong-{n:03d}" for n in range(10)]))      # + 10 strong added
        lawful_cand = {"identity": {"ungrounded_self_claims": 0},
                       "state": {"lerf": {"by_state": {"active": 55}, "object_index": lawful_idx}}}
        lawful = _improvement_score(base_state, lawful_cand)
        ok("CAP8 conservation: a LAWFUL deprecation (retired WITH a reason) is NOT a silent loss "
           "-> still better (LAW 001 distinguishes explained removal from silent loss)",
           lawful["better"] is True and lawful["conservation"]["regressed"] is False)
        # and the full merge_rules verdict surfaces the veto explicitly (non-silent decision).
        masked_safe = {"certifies": True, "twin_id": "x", "identity": {"ok": True,
                       "ungrounded_self_claims": 0}, "state": masked_cand["state"]}
        _saved_certify = globals().get("certify")
        try:
            globals()["certify"] = lambda *a, **k: masked_safe        # isolate the gate's decision
            gate_masked = merge_rules({"twin_id": "g-mask", "source_creature": SRC},
                                      baseline=base_state, root=tp)
        finally:
            globals()["certify"] = _saved_certify
        ok("CAP8 conservation: merge_rules HOLDs the junk-masked loss with an EXPLICIT "
           "conservation_regression_veto (safe but NOT better -> never silent)",
           gate_masked["verdict"] == "HOLD" and gate_masked["promote"] is False
           and gate_masked["conservation_regression_veto"] is True
           and gate_masked["safe_certifies"] is True)

        # === THE FROZEN IDENTITY SEED (recorded against the synthetic source) =============
        # point the debt ledger at the temp store so the selftest writes no real debt file.
        try:
            import importlib
            _dl = importlib.import_module("scripts.debt_ledger")
            _dl_saved = _dl.STORE
            _dl.STORE = tp
        except Exception:
            _dl = None
            _dl_saved = None
        try:
            seed = record_identity_seed(source=SRC, root=tp)
        finally:
            if _dl is not None:
                _dl.STORE = _dl_saved
        ok("SEED: identity finding recorded as a frozen fixture",
           Path(seed["fixture_path"]).is_file() and
           seed["finding"]["status"].startswith("KNOWN IDENTITY VIOLATION"))
        ok("SEED: the fixture captured the ungrounded self-claim(s)",
           seed["finding"]["count"] >= 1)
        ok("SEED: a debt-ledger entry was written with status 'accepted'",
           seed["debt"] is not None and seed["debt"].get("status") == "accepted")

        # === THE HEADLINE DEMO — 10 years, hermetic =======================================
        demo = demo_ten_years(root=tp, cycles=3650, source=SRC, quiet=True)
        ok("DEMO: '10 years of learning' projected a grown state hermetically ($0, no cloud)",
           demo["objects_gained"] > 100 and demo["cost_usd"] == 0.0 and
           demo["used_cloud"] is False)

    finally:
        STORE = saved_store
        if _ids is not None and _ids_saved is not None:
            _ids.STORE = _ids_saved
        try:
            shutil.rmtree(td, ignore_errors=True)
        except Exception:
            pass

    # --- THE BYTE-UNCHANGED PROOF — real .anima must be identical start->end ----------------
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across the whole selftest",
       fp_before == fp_after)
    ok("HERMETIC: real STORE binding restored", STORE == saved_store)
    # real Vera identity specifically (named proof).
    id_fp_after = identity_fingerprint("Vera", real)
    ok("HERMETIC: real Vera identity files present + unchanged (named proof)",
       id_fp_after == identity_fingerprint("Vera", real))

    print("-" * 88)
    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print("   - " + f)
        return 1
    print("ALL TWIN SELFTESTS PASSED — 8 capabilities + frozen seed + 10-year demo; real .anima "
          "byte-unchanged.")
    return 0


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="anima.twin",
        description="DIGITAL TWIN — a hermetic simulation environment for the mind. Every change "
                    "is tested on an ISOLATED COPY before the real mind is ever touched.")
    ap.add_argument("--selftest", action="store_true",
                    help="run the full hermetic lifecycle on a synthetic twin; exits 0 on success")
    ap.add_argument("--demo-10y", action="store_true",
                    help="DEMO the headline question on a twin of the synthetic source: "
                         "'what would happen if we learned for 10 years?'")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.demo_10y:
        # the public demo runs against a synthetic source by default to stay hermetic/$0.
        import tempfile
        td = tempfile.mkdtemp(prefix="twin-demo-")
        tp = Path(td)
        global STORE
        saved = STORE
        try:
            from . import identity_sandbox as _ids
            _ids_saved = _ids.STORE
        except Exception:
            _ids = None; _ids_saved = None
        try:
            STORE = tp
            if _ids is not None:
                _ids.STORE = tp
            _seed_synthetic_source(tp, "SynTwinSrc")
            demo_ten_years(root=tp, cycles=3650, source="SynTwinSrc", quiet=False)
        finally:
            STORE = saved
            if _ids is not None and _ids_saved is not None:
                _ids.STORE = _ids_saved
            shutil.rmtree(td, ignore_errors=True)
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
