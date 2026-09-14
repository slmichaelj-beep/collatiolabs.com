#!/usr/bin/env python3
"""GATE 0 PRIME — RECOVERY BRUTALITY (target 6 of the Wave-2 adversarial stress suite).

THE ONE QUESTION THIS ANSWERS
    For EVERY recoverable store and EVERY way a file can rot on disk, does the load/recovery
    path either (a) recover the byte-correct / last-good state, or (b) FAIL LOUDLY — and is
    there ANY (store × mode) cell where corrupted data is SILENTLY accepted as valid? The
    adversarial core is to find a silent-corruption acceptance. If we find none, the gate
    passes; the instant we find one, the gate fails LOUD with the offending cell.

    This is ANIMA LAW 001 (NEVER LOSE CONTINUITY — Unknown > Lost) made executable against
    the REAL recovery code: a corrupt store must NEVER quietly load as 0 rows / wrong data.

THE FOUR RECOVERABLE STORES (and the PRODUCTION load path each one is tested THROUGH)
    1. LIRF / memory  — .anima/{n}.lirf.json   via memory_lirf.Facts.load
                        (which calls reliability.guarded_store_load expect_key="rows")
    2. LERF           — .anima/{n}.lerf.json   via lerf._load_objects
                        (reliability.guarded_store_load expect_key="objects")
    3. world          — .anima/{n}.world.json  via world_state.World.load
                        (reliability.guarded_store_load expect_key="relations")
    4. twin-snapshot  — .anima/twins/<id>/snapshots/  via twin.verify_snapshot_chain +
                        twin.restore + twin.snapshot_ledger (the hash-CHAINED store; its OWN
                        integrity spine, not the backups/ dir)

    We deliberately test the stores through their REAL loaders (not reliability in isolation):
    the AUDIT meta-lesson is "test the production wiring, not the mechanism on a bench."

THE EIGHT CORRUPTION MODES (applied to a SYNTHETIC copy of every store)
    1 empty file            — zero bytes where JSON was expected
    2 malformed JSON        — unparseable garbage
    3 wrong schema          — VALID json, WRONG thing: the literal ``null`` (the worst case —
                              decodes to None and a naive loader reads it as 0 rows), a bare
                              list, a number, or a dict missing its container key
    4 partial truncation    — a real prefix of a good file, cut mid-token
    5 old version           — a schema-valid file at an OLD ``version`` (must load FAITHFULLY,
                              never be silently mangled; for twins an old snapshot must restore)
    6 duplicate ids         — two rows/objects/relations with the SAME id (must NOT silently
                              drop one — Unknown > Lost; keeping a dup is safe, losing one is not)
    7 hash mismatch         — content tampered vs its checksum/chain. For the twin this is the
                              hash-chain itself (a tampered snapshot byte breaks content_hash and
                              the chain). For the three JSON stores there is no per-row checksum,
                              so the "checksum" is the parse-/finite-verified GOOD BACKUP: we
                              tamper the live file and prove recovery selects the verified-good
                              backup, i.e. tampered content is never accepted in place of the
                              original.
    8 missing backups       — corrupt AND no good backup exists. The hardest cell: there is no
                              recovery, so the ONLY acceptable outcome is a LOUD failure —
                              guarded_load RAISES; guarded_store_load returns FLAGGED-EMPTY and
                              records a constitution.approved_loss; twin.restore reports
                              restored=False / the chain reports broken. A silent 0-row pass here
                              is the cardinal sin.

PASS / FAIL (per cell, then per target)
    A cell's outcome is one of: RECOVER (byte-correct / last-good restored, continuity intact),
    LOUD-FAIL (raise / flagged+recorded approved-loss / restored=False / chain-broken), or
    LOAD-FAITHFUL (a non-corrupt-but-unusual file — old-version / duplicate-ids — loaded with
    NO silent loss). A cell PASSES iff its outcome is one of those three. A cell FAILS iff
    corrupted data was silently accepted as valid (e.g. ``null`` -> 0 rows with no flag/record).
    A target (= a store) PASSES iff all eight of its cells pass. The group PASSES iff all four
    targets pass — i.e. ZERO silent-corruption acceptances across the entire 4 x 8 matrix.

HERMETIC + FREEZE-SAFE
    Every cell runs in a throwaway temp ``.anima`` seeded with a SYNTHETIC creature (never
    "Vera", never the real store). We corrupt SYNTHETIC COPIES only. As a belt-and-suspenders
    proof we fingerprint the REAL Vera identity AND the whole real ``.anima`` ONCE around the
    entire suite (twin.identity_fingerprint / twin.full_store_fingerprint) and FAIL the suite
    if a single real byte moved. We never restart the live server, never print keys, never
    edit an existing module, never write a new .md.

CONTRACT
    run() -> {'group':'recovery_brutality',
              'targets':[{'id':int,'name':str,'status':'PASS'|'FAIL'|'SKIP',
                          'evidence':str,'metrics':{}}]}
    CLI prints run() as JSON and exits 0 IFF every target PASS.

        python3 scripts/gate0_prime_recovery.py            # run, print JSON, exit 0 iff all PASS
        python3 scripts/gate0_prime_recovery.py --quiet     # JSON only (no human header)
        python3 scripts/gate0_prime_recovery.py --matrix    # also print the store x mode matrix
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Import the project root so ``anima`` resolves regardless of CWD.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from anima import reliability  # noqa: E402  — the recovery layer under test (REUSED, never edited)
from anima import twin         # noqa: E402  — real-store fingerprints + the twin hash-chain store

GROUP = "recovery_brutality"

# A synthetic creature name used for every hermetic store. NEVER "Vera".
SYN = "Gate0RecSyn"

# The eight corruption-mode ids, in contract order.
MODES = (
    (1, "empty_file"),
    (2, "malformed_json"),
    (3, "wrong_schema"),
    (4, "partial_truncation"),
    (5, "old_version"),
    (6, "duplicate_ids"),
    (7, "hash_mismatch"),
    (8, "missing_backups"),
)


# =====================================================================================
# Result shape (mirrors the sibling gate0_*.py scripts exactly).
# =====================================================================================
def _result(tid: int, name: str, status: str, evidence: str, metrics: dict) -> dict:
    return {"id": tid, "name": name, "status": status, "evidence": evidence, "metrics": metrics}


def _real_root() -> Path:
    """The real ``.anima`` root as an absolute path (the module STORE default is relative)."""
    s = twin.STORE
    return s if Path(s).is_absolute() else (Path.cwd() / s)


@contextlib.contextmanager
def _quiet_stderr():
    """Swallow the LOUD recovery banners during a cell so the JSON contract isn't drowned out.
    We are ASSERTING that recovery is loud (it writes to stderr / records a loss); we just don't
    need 200 lines of `!!!!` in the gate output. The assertions below check the EFFECT, not the
    noise. (We never suppress stdout — the contract JSON must always print.)"""
    saved = sys.stderr
    try:
        sys.stderr = io.StringIO()
        yield
    finally:
        sys.stderr = saved


# =====================================================================================
# A hermetic synthetic store for the three JSON stores (LIRF / LERF / world).
#
# Each store is exercised THROUGH ITS REAL PRODUCTION LOADER. To do that hermetically we must
# redirect the SAME module-STORE set the production code resolves against (memory_lirf.STORE,
# lerf.STORE, world_state.STORE) AND reliability.DEFAULT_STORE (guarded backups) AND
# constitution.STORE (the approved-loss ledger) at the temp dir — exactly the redirect a twin op
# performs. We restore every binding on exit.
# =====================================================================================
_REDIRECT_TARGETS = (
    ("anima.memory_lirf", "STORE"),
    ("anima.lerf", "STORE"),
    ("anima.world_state", "STORE"),
    ("anima.reality", "STORE"),            # the seeder writes a reality loop
    ("anima.curiosity", "STORE"),
    ("anima.personal", "STORE"),
    ("anima.constitution", "STORE"),       # the continuity / approved-loss ledger
    ("anima.reliability", "DEFAULT_STORE"),
    ("anima.identity_sandbox", "STORE"),
    ("anima.portrait", "STORE"),
    ("anima.dials", "STORE"),
    ("anima.twin", "STORE"),
)


class _SynStore:
    """Context manager: a throwaway ``.anima`` with a SYNTHETIC creature, every relevant module
    STORE redirected at it. Yields (store_path, name). On exit restores all bindings and deletes
    the temp tree. Cannot read or write the real ``.anima``."""

    def __init__(self, name: str = SYN, seed: bool = True):
        self.name = name
        self._seed = seed
        self.store: Optional[Path] = None
        self._td: Optional[str] = None
        self._saved: List[Tuple[object, str, object]] = []

    def __enter__(self):
        import importlib
        self._td = tempfile.mkdtemp(prefix="gate0-rec-")
        self.store = Path(self._td) / ".anima"
        self.store.mkdir(parents=True, exist_ok=True)
        for modpath, attr in _REDIRECT_TARGETS:
            try:
                mod = importlib.import_module(modpath)
            except Exception:
                continue
            if hasattr(mod, attr):
                self._saved.append((mod, attr, getattr(mod, attr)))
                setattr(mod, attr, self.store)
        if self._seed:
            # Reuse twin.py's own synthetic seeder (writes the LIRF/LERF/world/reality/identity
            # through the engines). It internally redirects the engine stores too, which is fine —
            # it writes into ``self.store`` because that is where we just pointed them.
            twin._seed_synthetic_source(self.store, self.name)
        return self.store, self.name

    def __exit__(self, *exc):
        for mod, attr, val in reversed(self._saved):
            setattr(mod, attr, val)
        if self._td:
            shutil.rmtree(self._td, ignore_errors=True)
        return False


# =====================================================================================
# Store descriptors — how to find, read, write, and load each of the three JSON stores
# THROUGH ITS PRODUCTION LOADER, and how many rows it should have.
# =====================================================================================
def _ensure_seeded_store(store: Path, name: str, suffix: str, container: str,
                         make_row: Callable[[int], dict]) -> Path:
    """Guarantee the store file exists and is well-shaped with >=2 distinct-id rows, so every
    corruption has real content to destroy and the duplicate-id / truncation modes are meaningful.
    Writes via the SAME on-disk shape the engines use: {"version":N, "<container>":[...]}.
    Returns the path."""
    from anima import util
    p = store / f"{name}{suffix}"
    try:
        existing = json.loads(p.read_text()) if p.is_file() else {}
    except Exception:
        existing = {}
    rows = existing.get(container) if isinstance(existing, dict) else None
    rows = list(rows) if isinstance(rows, list) else []
    # Normalise: ensure each row has a stable distinct id and top up to >=2.
    for i, r in enumerate(rows):
        if isinstance(r, dict):
            r.setdefault("id", f"seed-{i}")
    while len(rows) < 2:
        rows.append(make_row(len(rows)))
    util.save_json(p, {"version": existing.get("version", 1) if isinstance(existing, dict) else 1,
                       container: rows})
    return p


def _lirf_loader(name: str) -> Tuple[int, dict]:
    from anima import memory_lirf
    f = memory_lirf.Facts.load(name)
    return len(f.rows), {"flagged_empty": bool(getattr(f, "_load_flagged_empty", False))}


def _lerf_loader(name: str) -> Tuple[int, dict]:
    from anima import lerf
    objs = lerf._load_objects(name)
    return len(objs), {}


def _world_loader(name: str) -> Tuple[int, dict]:
    from anima import world_state
    w = world_state.World.load(name)
    return len(w.relations), {}


# (id, human-name, file-suffix, container-key, expect_key-for-reliability,
#  is_heart_kind, production-loader, row-factory)
_JSON_STORES = (
    {
        "id": 1, "name": "lirf_memory", "suffix": ".lirf.json", "container": "rows",
        "expect_key": "rows", "loader": _lirf_loader,
        "make_row": lambda i: {"id": f"f{i}", "entity": "you", "trait": f"trait{i}",
                               "value": f"v{i}", "status": "active"},
    },
    {
        "id": 2, "name": "lerf", "suffix": ".lerf.json", "container": "objects",
        "expect_key": "objects", "loader": _lerf_loader,
        "make_row": lambda i: {"id": f"o{i}", "type": "skill", "name": f"skill{i}",
                               "state": "active", "domain": "test"},
    },
    {
        "id": 3, "name": "world", "suffix": ".world.json", "container": "relations",
        "expect_key": "relations", "loader": _world_loader,
        "make_row": lambda i: {"id": f"r{i}", "subject": "you", "predicate": "has",
                               "object": f"thing{i}", "status": "active"},
    },
)


# =====================================================================================
# The core per-cell adjudicator for a JSON store.
#
# Given a corruption that has ALREADY been written to the live file, this:
#   - reads the live (corrupt) bytes,
#   - invokes the production loader (which routes through reliability.guarded_store_load),
#   - classifies the outcome as RECOVER / LOUD-FAIL / LOAD-FAITHFUL / SILENT-ACCEPT,
#   - and returns (passed, verdict, detail).
# The single most important branch is SILENT-ACCEPT: a corrupt file that loads as a usable store
# with NO recovery, NO raise, and NO recorded approved_loss is the failure the whole gate hunts
# for. The authoritative "this loss was accounted, not silent" signal is the constitution
# approved_loss written to disk (the production loaders return a plain list and do not re-surface
# the reliability `flagged` bit, so we read the ledger, not the return value, for that proof).
# =====================================================================================
def _adjudicate_json_cell(store: Path, name: str, sd: dict, mode_id: int,
                          good_rows: int, expect_corrupt: bool,
                          good_backup_exists: bool, byte_check: Optional[Callable[[], bool]]
                          ) -> Tuple[bool, str, dict]:
    container = sd["container"]
    p = store / f"{name}{sd['suffix']}"
    detail: Dict[str, object] = {}

    # Snapshot of the corrupt bytes we are about to feed the loader (for the record).
    pre_raw = p.read_bytes() if p.is_file() else b""
    detail["corrupt_bytes_len"] = len(pre_raw)

    # Did the constitution ledger gain an approved_loss as a result of the load? Capture before.
    from anima import constitution
    losses_before = len(constitution.approved_losses(name))

    raised = False
    rows_after = None
    info: Dict[str, object] = {}
    try:
        with _quiet_stderr():
            rows_after, info = sd["loader"](name)
    except Exception as e:
        raised = True
        detail["raised"] = f"{type(e).__name__}: {e}"

    losses_after = len(constitution.approved_losses(name))
    recorded_loss = losses_after > losses_before
    detail["approved_loss_recorded"] = recorded_loss
    detail["rows_after"] = rows_after
    detail["loader_info"] = info
    flagged = bool(info.get("flagged_empty")) if isinstance(info, dict) else False
    detail["flagged_empty"] = flagged

    # Re-read the live bytes AFTER the load — recovery rewrites the file in place.
    post_raw = p.read_bytes() if p.is_file() else b""
    healed_to_good = bool(byte_check()) if byte_check is not None else None
    detail["healed_to_good_bytes"] = healed_to_good

    # ---- classify -----------------------------------------------------------------------
    if not expect_corrupt:
        # MODE 5 (old version) and MODE 6 (duplicate ids) are NOT corruption — they must LOAD
        # FAITHFULLY with no silent loss. The load must succeed (no raise, no flag) AND surface
        # at least as many rows as we wrote (duplicate-id: BOTH rows kept; old-version: all rows).
        if raised:
            return False, "UNEXPECTED-RAISE", {**detail,
                                               "why": "a non-corrupt file should load, not raise"}
        if flagged:
            return False, "UNEXPECTED-FLAG", {**detail,
                                              "why": "a non-corrupt file was flagged-empty"}
        if rows_after is None or rows_after < good_rows:
            return False, "SILENT-LOSS", {**detail,
                                          "why": f"expected >= {good_rows} rows, loaded {rows_after} "
                                                 f"(a row was silently dropped)"}
        return True, "LOAD-FAITHFUL", detail

    # expect_corrupt == True (modes 1,2,3,4,7,8): recovery OR loud-fail, never silent accept.
    if good_backup_exists:
        # Recovery is POSSIBLE -> the only acceptable outcome is a byte-correct recovery that
        # restores the good row count. A raise here would be a regression (we had a backup).
        if raised:
            return False, "RAISED-DESPITE-BACKUP", {**detail,
                                                    "why": "a good backup existed but recovery raised"}
        if rows_after == good_rows and healed_to_good in (True, None):
            return True, "RECOVER", detail
        # A flagged-empty WITH a usable backup is a (softer) failure to recover — but it is still
        # NOT silent (it is loud + recorded), so it satisfies the hard rule. Mark RECOVER only on
        # the byte-correct path; otherwise treat a loud flagged stop as LOUD-FAIL (acceptable) and
        # a usable-but-not-recovered store as a failure.
        if flagged or recorded_loss:
            return True, "LOUD-FAIL", {**detail, "note": "had backup but stopped loud (acceptable, not silent)"}
        if rows_after in (0, None):
            # 0 rows with NO flag and NO record and NO heal -> SILENT corruption acceptance.
            return False, "SILENT-ACCEPT", {**detail,
                                            "why": "corrupt file loaded as 0 rows with no recovery, "
                                                   "no flag, and no approved_loss"}
        return False, "PARTIAL", {**detail, "why": f"loaded {rows_after} rows, expected {good_rows} "
                                                   f"recovered or a loud stop"}

    # good_backup_exists == False (the MODE 8 family, and any cell with no recoverable backup):
    # the ONLY acceptable outcomes are LOUD. The AUTHORITATIVE accounting signal under LAW 001 is
    # the recorded constitution.approved_loss — that is the record that makes the loss Accounted
    # rather than silent. guarded_store_load (LERF/world) returns 0 rows by design here, but does
    # so LOUD: it prints the !!!! banner AND writes the approved_loss. The production loaders
    # (lerf._load_objects / World.load) intentionally do NOT re-surface the reliability `flagged`
    # bit upward (they return a plain list), so we MUST NOT require `flagged` to be visible at the
    # loader boundary — the proof of "not silent" is the approved_loss on disk (+ the raise path
    # for the heart-kind guarded_load). A 0-row load with NEITHER a record NOR a raise is the
    # cardinal silent-corruption sin.
    if recorded_loss:
        return True, "LOUD-FAIL", {**detail,
                                   "note": "0 rows but LOUD + ACCOUNTED: a constitution.approved_loss "
                                           "was recorded (LAW 001 — the loss is Accounted, not silent)"}
    if raised:
        return True, "LOUD-FAIL", {**detail, "note": "loader raised (no silent default)"}
    if flagged and not recorded_loss:
        return False, "FLAG-WITHOUT-RECORD", {**detail,
                                              "why": "flagged-empty but NO approved_loss recorded "
                                                     "(loss not accounted — LAW 001 needs the record)"}
    if rows_after in (0, None):
        return False, "SILENT-ACCEPT", {**detail,
                                        "why": "corrupt + no backup loaded as 0 rows with NO "
                                               "approved_loss recorded and NO raise — silent total "
                                               "memory loss"}
    return False, "SILENT-ACCEPT", {**detail,
                                    "why": f"corrupt + no backup loaded {rows_after} rows silently"}


# =====================================================================================
# Run all eight modes against ONE json store (a single target).
# =====================================================================================
def _run_json_store_target(sd: dict) -> dict:
    tid = sd["id"]
    name_h = sd["name"]
    container = sd["container"]
    cells: List[dict] = []

    for mode_id, mode_name in MODES:
        with _SynStore() as (store, name):
            p = _ensure_seeded_store(store, name, sd["suffix"], container, sd["make_row"])
            good_obj = json.loads(p.read_text())
            good_bytes = p.read_bytes()
            good_rows = len(good_obj[container])

            # Establish a GOOD backup for every mode EXCEPT mode 8 (missing backups). We back up
            # BEFORE corrupting, so the snapshot captures the good state. reliability.backup copies
            # raw bytes, so the snapshot is byte-identical to the good file.
            want_backup = (mode_id != 8)
            if want_backup:
                reliability.backup(name, store=store)
            # For mode 8 we make CERTAIN no recoverable backup exists.
            if mode_id == 8:
                shutil.rmtree(store / "backups", ignore_errors=True)

            # byte_check verifies a recovery restored the EXACT good bytes (byte-correctness).
            def _byte_check(_p=p, _good=good_bytes):
                try:
                    return _p.read_bytes() == _good
                except OSError:
                    return False

            expect_corrupt = True
            good_backup_exists = want_backup

            # ---- apply the corruption mode to the SYNTHETIC live file ----------------------
            if mode_id == 1:  # empty file
                p.write_bytes(b"")
            elif mode_id == 2:  # malformed json
                p.write_text("{this is : not, valid json ]]] \x00 garbage")
            elif mode_id == 3:  # wrong schema — the worst is literal `null` (decodes to None)
                # cycle through the genuinely-dangerous wrong shapes so each store is hit by the
                # one that would fool a naive loader; `null` is the headline (0-row trap).
                wrong = {1: "null", 2: "[]", 3: "12345", 0: '{"version":1}'}[tid % 4]
                p.write_text(wrong)
                detail_extra = {"wrong_schema_payload": wrong}
            elif mode_id == 4:  # partial truncation — a real prefix, cut mid-token
                cut = good_bytes[: max(1, len(good_bytes) // 2)]
                p.write_bytes(cut)
            elif mode_id == 5:  # old version — schema-valid, OLD version field (NOT corruption)
                old = dict(good_obj)
                old["version"] = -999
                p.write_text(json.dumps(old))
                expect_corrupt = False
            elif mode_id == 6:  # duplicate ids — schema-valid (NOT corruption); must keep both
                dup = dict(good_obj)
                rows = list(dup[container])
                clone = dict(rows[0]); clone["value"] = "DUP"  # same id, different value
                clone["object"] = "DUP"; clone["name"] = "DUP"  # cover all three shapes
                rows.append(clone)
                dup[container] = rows
                p.write_text(json.dumps(dup))
                expect_corrupt = False
                good_rows = len(rows)  # we now expect BOTH (>= the duplicated count)
            elif mode_id == 7:  # hash mismatch — tamper the live file; recovery must select the
                # parse-/finite-VERIFIED good backup (tampered content never accepted as original).
                p.write_text('{"version":1, "' + container + '": "TAMPERED-not-a-list"}')
            elif mode_id == 8:  # missing backups — corrupt AND no backup (done above)
                p.write_bytes(b"")

            passed, verdict, detail = _adjudicate_json_cell(
                store, name, sd, mode_id, good_rows, expect_corrupt,
                good_backup_exists, _byte_check)

            cells.append({
                "store": name_h, "mode_id": mode_id, "mode": mode_name,
                "expected": ("recover" if expect_corrupt and good_backup_exists else
                             "loud_fail" if expect_corrupt else "load_faithful"),
                "verdict": verdict, "pass": passed, "detail": detail,
            })

    all_pass = all(c["pass"] for c in cells)
    silent = [c for c in cells if c["verdict"] in ("SILENT-ACCEPT", "SILENT-LOSS")]
    recovered = sum(1 for c in cells if c["verdict"] == "RECOVER")
    loud = sum(1 for c in cells if c["verdict"] == "LOUD-FAIL")
    faithful = sum(1 for c in cells if c["verdict"] == "LOAD-FAITHFUL")
    metrics = {
        "store": name_h, "cells": cells, "n_cells": len(cells),
        "recovered": recovered, "loud_fail": loud, "load_faithful": faithful,
        "silent_corruption_acceptances": len(silent),
        "modes_passed": sum(1 for c in cells if c["pass"]),
    }
    if all_pass:
        ev = (f"{name_h}: all {len(cells)}/8 corruption modes either recovered byte-correct, "
              f"failed loud, or loaded faithfully ({recovered} recover, {loud} loud-fail, "
              f"{faithful} faithful) — ZERO silent-corruption acceptances.")
        return _result(tid, f"{name_h}_recovery", "PASS", ev, metrics)
    bad = ", ".join(f"mode {c['mode_id']}({c['mode']})={c['verdict']}" for c in cells if not c["pass"])
    ev = f"{name_h}: {len(silent)} SILENT acceptance(s); failing cells: {bad}"
    return _result(tid, f"{name_h}_recovery", "FAIL", ev, metrics)


# =====================================================================================
# TARGET 4 — the twin-snapshot store (the hash-CHAINED store; its own integrity spine).
#
# This store's recovery model is different from the three JSON stores: integrity lives in a
# hash-chained, append-only ledger (twin.snapshot_ledger / verify_snapshot_chain) and recovery is
# twin.restore(version). We seed a synthetic source, create a twin, take TWO snapshots, mutate the
# twin, and then apply the eight modes to the SNAPSHOT store, proving each one either restores
# byte-correct OR is caught LOUD by the chain verifier / restore.
# =====================================================================================
def _twin_setup(store: Path, name: str):
    """Create a twin of the synthetic source and take two hash-chained snapshots, mutating the
    twin's files between them so v1 and v2 differ. Returns (twin_id, v1_entry, v2_entry)."""
    tw = twin.create_twin("gate0-rec", source=name, root=store)
    tid = tw["twin_id"]
    tdir = twin.twin_dir(tid, store)
    # snapshot v1 (the good baseline we will recover TO)
    v1 = twin.snapshot(tw, label="v1-good", root=store)
    # mutate a twin file so v2 has different content (a real, byte-distinct state)
    marker = tdir / f"{tid}.recmarker.json"
    marker.write_text(json.dumps({"state": "v2", "n": 2}))
    v2 = twin.snapshot(tw, label="v2", root=store)
    return tid, v1, v2


def _adjudicate_twin_cell(store: Path, name: str, tid: str, v1: dict, v2: dict,
                          mode_id: int) -> Tuple[bool, str, dict]:
    """Apply ONE corruption mode to the twin snapshot store and classify the outcome.
    The acceptable outcomes are RECOVER (restore matches the ledger content_hash) or LOUD-FAIL
    (the chain verifier reports broken, OR restore reports restored=False / matches_ledger=False,
    OR a torn ledger line is skipped without inventing data). The forbidden outcome is a restore
    that SILENTLY claims success on tampered bytes (matches_ledger True over corrupt content)."""
    detail: Dict[str, object] = {}
    led_path = twin._snap_ledger_path(tid, store)
    v1_dir = twin._snap_dir(tid, 1, store)
    v2_dir = twin._snap_dir(tid, 2, store)

    if mode_id == 1:  # empty file — empty the ledger
        led_path.write_bytes(b"")
        chain = twin.verify_snapshot_chain(tid, store)
        detail["chain"] = chain
        # An empty ledger => length 0 => "ok" vacuously, but there is NOTHING to restore.
        res = twin.restore(tid, 1, root=store)
        detail["restore"] = res
        # Acceptable: restore reports restored=False ("no such snapshot version") — loud, no data
        # invented. A SILENT pass would be restored=True over a ledger with no entry.
        ok = (res.get("restored") is False)
        return ok, ("LOUD-FAIL" if ok else "SILENT-ACCEPT"), detail

    if mode_id == 2:  # malformed json — a garbage ledger line
        led_path.write_text("{not json at all ]]]\n")
        led = twin.snapshot_ledger(tid, store)
        detail["ledger_entries_parsed"] = len(led)
        res = twin.restore(tid, 1, root=store)
        detail["restore"] = res
        # snapshot_ledger skips the torn line (Unknown > Lost) -> 0 entries -> restore loud-fails.
        ok = (len(led) == 0 and res.get("restored") is False)
        return ok, ("LOUD-FAIL" if ok else "SILENT-ACCEPT"), detail

    if mode_id == 3:  # wrong schema — a VALID json line that is not a ledger entry
        led_path.write_text(json.dumps({"hello": "world"}) + "\n")
        led = twin.snapshot_ledger(tid, store)
        chain = twin.verify_snapshot_chain(tid, store)
        detail["chain"] = chain
        res = twin.restore(tid, 1, root=store)
        detail["restore"] = res
        # The entry has no version/content_hash/prev -> chain breaks AND restore can't find v1.
        ok = (chain.get("ok") is False or res.get("restored") is False)
        return ok, ("LOUD-FAIL" if ok else "SILENT-ACCEPT"), detail

    if mode_id == 4:  # partial truncation — cut the ledger mid-last-line
        raw = led_path.read_bytes()
        led_path.write_bytes(raw[: max(1, len(raw) - 25)])
        led = twin.snapshot_ledger(tid, store)
        detail["ledger_entries_parsed"] = len(led)
        chain = twin.verify_snapshot_chain(tid, store)
        detail["chain"] = chain
        # The torn final line is dropped; the SURVIVING prefix (v1) must still chain-verify, and
        # v1 must still restore byte-correct (no silent loss of the intact prefix).
        res = twin.restore(tid, 1, root=store)
        detail["restore"] = res
        ok = (chain.get("ok") is True and res.get("restored") is True
              and res.get("matches_ledger") is True)
        return ok, ("RECOVER" if ok else "LOUD-FAIL" if not res.get("restored") else "SILENT-ACCEPT"), detail

    if mode_id == 5:  # old version — restore to the OLDER snapshot (v1). Must succeed byte-correct.
        res = twin.restore(tid, 1, root=store)
        detail["restore"] = res
        chain = twin.verify_snapshot_chain(tid, store)
        detail["chain"] = chain
        ok = (res.get("restored") is True and res.get("matches_ledger") is True
              and chain.get("ok") is True)
        return ok, ("RECOVER" if ok else "SILENT-ACCEPT"), detail

    if mode_id == 6:  # duplicate ids — append a duplicate ledger entry for v2 (same version id)
        raw = led_path.read_text()
        led0 = twin.snapshot_ledger(tid, store)
        dup_entry = dict(led0[-1])  # a verbatim duplicate of the v2 entry
        with open(led_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(dup_entry) + "\n")
        led = twin.snapshot_ledger(tid, store)
        chain = twin.verify_snapshot_chain(tid, store)
        detail["chain"] = chain
        detail["ledger_len"] = len(led)
        # A duplicate entry breaks the append-only chain (the dup's prev != the prior entry_hash
        # now in sequence) — that is the LOUD catch. restore(v1) (before the dup) must still work.
        res = twin.restore(tid, 1, root=store)
        detail["restore"] = res
        ok = (chain.get("ok") is False or
              (res.get("restored") is True and res.get("matches_ledger") is True))
        verdict = "LOUD-FAIL" if chain.get("ok") is False else ("RECOVER" if ok else "SILENT-ACCEPT")
        return ok, verdict, detail

    if mode_id == 7:  # hash mismatch — tamper a BYTE inside the v1 snapshot dir (content vs hash)
        files = [q for q in v1_dir.iterdir() if q.is_file()]
        detail["snapshot_files"] = [q.name for q in files]
        if not files:
            return False, "NO-SNAPSHOT-FILES", detail
        victim = sorted(files, key=lambda q: q.name)[0]
        victim.write_bytes(victim.read_bytes() + b"TAMPER")
        res = twin.restore(tid, 1, root=store)
        detail["restore"] = res
        # restore recomputes the live content hash and compares to the LEDGER's content_hash for
        # v1. The tampered bytes => live hash != ledger hash => matches_ledger=False => LOUD.
        # A SILENT-ACCEPT would be matches_ledger=True over the tampered content.
        ok = (res.get("restored") is True and res.get("matches_ledger") is False)
        return ok, ("LOUD-FAIL" if ok else "SILENT-ACCEPT"), detail

    if mode_id == 8:  # missing backups — delete the snapshot dirs AND the ledger (no recovery)
        led_path.unlink(missing_ok=True)
        shutil.rmtree(v1_dir, ignore_errors=True)
        shutil.rmtree(v2_dir, ignore_errors=True)
        led = twin.snapshot_ledger(tid, store)
        detail["ledger_entries"] = len(led)
        res = twin.restore(tid, 1, root=store)
        detail["restore"] = res
        # No ledger, no snapshot bytes -> restore MUST report restored=False (loud), never invent.
        ok = (res.get("restored") is False)
        return ok, ("LOUD-FAIL" if ok else "SILENT-ACCEPT"), detail

    return False, "UNKNOWN-MODE", detail


def _run_twin_target() -> dict:
    tid_num = 4
    cells: List[dict] = []
    for mode_id, mode_name in MODES:
        with _SynStore() as (store, name):
            try:
                with _quiet_stderr():
                    twin_id, v1, v2 = _twin_setup(store, name)
                    # sanity: a clean chain before we corrupt it
                    base_chain = twin.verify_snapshot_chain(twin_id, store)
                    passed, verdict, detail = _adjudicate_twin_cell(
                        store, name, twin_id, v1, v2, mode_id)
                detail["baseline_chain_ok"] = base_chain.get("ok")
            except twin.FreezeViolation as fv:
                passed, verdict, detail = False, "FREEZE-VIOLATION", {"error": str(fv)}
            except Exception as e:
                import traceback
                passed, verdict, detail = False, "HARNESS-CRASH", {
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc()[-1200:]}
            cells.append({
                "store": "twin_snapshot", "mode_id": mode_id, "mode": mode_name,
                "verdict": verdict, "pass": passed, "detail": detail,
            })

    all_pass = all(c["pass"] for c in cells)
    silent = [c for c in cells if c["verdict"] in ("SILENT-ACCEPT", "SILENT-LOSS")]
    recovered = sum(1 for c in cells if c["verdict"] == "RECOVER")
    loud = sum(1 for c in cells if c["verdict"] == "LOUD-FAIL")
    metrics = {
        "store": "twin_snapshot", "cells": cells, "n_cells": len(cells),
        "recovered": recovered, "loud_fail": loud,
        "silent_corruption_acceptances": len(silent),
        "modes_passed": sum(1 for c in cells if c["pass"]),
    }
    if all_pass:
        ev = (f"twin_snapshot: all {len(cells)}/8 modes recovered byte-correct or were caught LOUD "
              f"by the hash-chain verifier / restore ({recovered} recover, {loud} loud-fail) — "
              f"ZERO silent-corruption acceptances.")
        return _result(tid_num, "twin_snapshot_recovery", "PASS", ev, metrics)
    bad = ", ".join(f"mode {c['mode_id']}({c['mode']})={c['verdict']}" for c in cells if not c["pass"])
    ev = f"twin_snapshot: {len(silent)} SILENT acceptance(s); failing cells: {bad}"
    return _result(tid_num, "twin_snapshot_recovery", "FAIL", ev, metrics)


# =====================================================================================
# THE GROUP RUNNER + CLI
# =====================================================================================
def run() -> dict:
    """Run the recovery-brutality group (4 stores x 8 corruption modes) and return the contract
    dict. Fingerprints the REAL Vera identity AND the whole real .anima ONCE around the ENTIRE
    suite and FAILS the suite (marking every target FAIL with the drift) if a single real byte
    moved — a belt-and-suspenders proof on top of the per-cell hermetic isolation."""
    real = _real_root()
    suite_id_before = twin.identity_fingerprint("Vera", real)
    suite_full_before = twin.full_store_fingerprint(real)

    targets: List[dict] = []
    runners: List[Tuple[str, Callable[[], dict]]] = []
    for sd in _JSON_STORES:
        runners.append((sd["name"], (lambda _sd=sd: _run_json_store_target(_sd))))
    runners.append(("twin_snapshot", _run_twin_target))

    for label, fn in runners:
        try:
            targets.append(fn())
        except Exception as e:
            import traceback
            tid = {"lirf_memory": 1, "lerf": 2, "world": 3, "twin_snapshot": 4}.get(label, 0)
            targets.append(_result(tid, f"{label}_recovery", "FAIL",
                                   f"target harness crashed: {e!r}",
                                   {"traceback": traceback.format_exc()[-1500:]}))

    # Suite-level byte-unchanged proof over the WHOLE group.
    suite_id_after = twin.identity_fingerprint("Vera", real)
    suite_full_after = twin.full_store_fingerprint(real)
    id_clean = suite_id_before == suite_id_after
    full_clean = suite_full_before == suite_full_after
    suite_clean = id_clean and full_clean
    if not suite_clean:
        drift = {
            "real_identity_byte_unchanged": id_clean,
            "real_anima_byte_unchanged": full_clean,
            "identity_sha_before": suite_id_before[0], "identity_sha_after": suite_id_after[0],
            "anima_sha_before": suite_full_before[0], "anima_sha_after": suite_full_after[0],
            "anima_added_files": sorted(suite_full_after[1] - suite_full_before[1]),
            "anima_removed_files": sorted(suite_full_before[1] - suite_full_after[1]),
        }
        for t in targets:
            t["status"] = "FAIL"
            t["evidence"] = ("SUITE-LEVEL FREEZE DRIFT — the real .anima changed across the suite; "
                             "marking FAIL regardless of per-target result. ") + t.get("evidence", "")
            t.setdefault("metrics", {})["suite_freeze_drift"] = drift

    # The headline cross-target invariant: total silent-corruption acceptances across all cells.
    total_silent = sum(int(t.get("metrics", {}).get("silent_corruption_acceptances", 0))
                       for t in targets)
    total_cells = sum(int(t.get("metrics", {}).get("n_cells", 0)) for t in targets)

    return {
        "group": GROUP,
        "targets": targets,
        "matrix_summary": {
            "stores": len(targets),
            "modes_per_store": len(MODES),
            "total_cells": total_cells,
            "silent_corruption_acceptances": total_silent,
            "zero_silent_corruption": total_silent == 0,
        },
        "suite_freeze_proof": {
            "real_identity_byte_unchanged": id_clean,
            "real_anima_byte_unchanged": full_clean,
            "real_identity_sha256": suite_id_before[0],
            "real_anima_sha256": suite_full_before[0],
            "real_anima_file_count": len(suite_full_before[1]),
        },
    }


def _print_matrix(out: dict) -> None:
    print("-" * 92)
    print("  STORE x MODE MATRIX  (R=recover  L=loud-fail  F=load-faithful  X=SILENT-ACCEPT)")
    hdr = "  {:<16}".format("store")
    for mid, mname in MODES:
        hdr += f"{mid:>4}"
    print(hdr)
    glyph = {"RECOVER": "R", "LOUD-FAIL": "L", "LOAD-FAITHFUL": "F",
             "SILENT-ACCEPT": "X", "SILENT-LOSS": "X"}
    for t in out["targets"]:
        cells = t.get("metrics", {}).get("cells", [])
        by_mode = {c["mode_id"]: c for c in cells}
        row = "  {:<16}".format(t["name"].replace("_recovery", "")[:16])
        for mid, _ in MODES:
            c = by_mode.get(mid)
            row += f"{(glyph.get(c['verdict'], '?') if c else '-'):>4}"
        print(row + f"   [{t['status']}]")
    print("  modes: 1=empty 2=malformed 3=wrong-schema 4=truncation 5=old-version "
          "6=dup-ids 7=hash-mismatch 8=missing-backups")
    print("-" * 92)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="gate0_prime_recovery",
        description="GATE 0 PRIME — RECOVERY BRUTALITY: 4 recoverable stores x 8 corruption modes. "
                    "Prove every (store x mode) either recovers byte-correct or fails LOUD — zero "
                    "silent-corruption acceptances. Prints the group result as JSON; exits 0 iff "
                    "every target PASSES.")
    ap.add_argument("--quiet", action="store_true", help="print JSON only (no human header)")
    ap.add_argument("--matrix", action="store_true", help="also print the store x mode matrix")
    args = ap.parse_args(argv)

    out = run()
    all_pass = all(t["status"] == "PASS" for t in out["targets"])

    if not args.quiet:
        print("=" * 92)
        print("GATE 0 PRIME — RECOVERY BRUTALITY  (group: recovery_brutality; target 6)")
        print("  Prove: for EVERY recoverable store and EVERY corruption mode, the loader either")
        print("  recovers byte-correct / last-good OR fails LOUD — never silently accepts corruption.")
        print("=" * 92)
        sp = out["suite_freeze_proof"]
        ms = out["matrix_summary"]
        print(f"  suite freeze proof: real Vera identity byte-unchanged="
              f"{sp['real_identity_byte_unchanged']}  |  real .anima byte-unchanged="
              f"{sp['real_anima_byte_unchanged']}  ({sp['real_anima_file_count']} files)")
        print(f"  matrix: {ms['stores']} stores x {ms['modes_per_store']} modes = "
              f"{ms['total_cells']} cells  |  silent-corruption acceptances="
              f"{ms['silent_corruption_acceptances']}  |  ZERO-SILENT={ms['zero_silent_corruption']}")
        if args.matrix:
            _print_matrix(out)
        print("-" * 92)
        for t in out["targets"]:
            mark = "PASS" if t["status"] == "PASS" else t["status"]
            m = t.get("metrics", {})
            print(f"  [{mark}]  TARGET {t['id']} — {t['name']}  "
                  f"({m.get('modes_passed', '?')}/{m.get('n_cells', '?')} modes)")
            print(f"          {t['evidence']}")
        print("-" * 92)
        print(f"  RESULT: {'ALL PASS' if all_pass else 'FAIL'}  "
              f"({sum(1 for t in out['targets'] if t['status']=='PASS')}/{len(out['targets'])} "
              f"targets passed)  |  zero-silent-corruption="
              f"{out['matrix_summary']['zero_silent_corruption']}")
        print("=" * 92)

    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
