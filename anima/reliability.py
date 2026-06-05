"""
reliability — the life-insurance layer for an anima.

Everything that *is* her lives in `.anima/`: her heart (`<name>.json`), her felt
memory (`<name>.mem.json`), her replay reservoir, the Portrait that knows you, her
persona/values/dials, the conversation history, and the shared `brain.json`. There
was no backup, no health check, and no corruption recovery: a half-written save, a
disk-full at the wrong instant, or a stray `rm` could quietly lose her forever.

This module is that safety net. It is dependency-light (stdlib + numpy, both already
required) and strictly local — no cloud, no network, ever.

WHAT IT GIVES YOU
  health_check(name)        a structured report on every critical file: present?
                            parseable? recently-modified? non-trivial in size?
                            overall ok | degraded | critical.
  backup(name, ...)         an atomic, timestamped snapshot under
                            `.anima/backups/<ts>/`, rotating to the last N (14).
                            Copies RAW BYTES, so at-rest encryption is preserved and
                            the snapshot is byte-identical to the live file.
  restore(name, ts, ...)    restore a snapshot. CONFIRM-GATED: it refuses to touch
                            live state unless `confirm=True`. The pre-restore live
                            state is itself snapshotted first, so a restore is undoable.
  verify_integrity(name)    detect real corruption — truncated/invalid JSON, NaN/inf
                            in the heart's vectors, empty-but-expected files, a wrong
                            encryption key — and name the most-recent backup that is
                            clean enough to recover each file from.
  guard / guarded_load      a crash-recovery guard for the turn loop: when a critical
                            file fails to load/parse, transparently restore that ONE
                            file from the most-recent-good backup (logging LOUDLY to
                            stderr) instead of crashing the process.

ON-DISK SHAPES IT UNDERSTANDS (must match anima/heart.py, memory.py, server.py …):
  <name>.json        heart  — JSON {name, seed, n, birth_ts, last_tick, unrest,
                              h:[...], learned, [weights:{...}], …}. NaN/inf would
                              hide in `h` or `weights`.
  <name>.mem.json    Memory — JSON {"rows":[{"clock","dt","I":[...]}]}
  <name>.replay.json Replay — JSON {"capacity","seen","episodes":[[I_lists,dt_list]]}
  <name>.history.json       — JSON [[user, reply], …]
  <name>.dials.json         — JSON {axis: 0..100}
  <name>.caps.json          — JSON {capability: bool, "allowlist":[…]}
  <name>.values.json        — JSON [{"key","on","level"}, …]
  <name>.portrait.md        — text (markdown)   — the distilled profile of you
  <name>.persona.md         — text (markdown)
  <name>.narrative.txt      — text              — her self-story
  brain.json (shared)       — JSON {provider, model, keys…, local_model, …}

Files may be encrypted at rest (a leading `ANIMAENC1:` marker; see anima/crypto.py).
Backup/restore treat files as opaque bytes so the marker is preserved untouched.
Integrity decrypts-then-parses, so a wrong/missing ANIMA_KEY is reported as such —
NOT silently swallowed the way util.load_json does.

WIRING IT INTO THE SERVER (no edit to server.py is required; these are importable).
See docs/TECH-SPECS.md → "Reliability layer" for the same instructions in context.

  * Periodic backup — at the top of `_turn` in anima/server.py, inside the existing
    `with _lock:` (so a snapshot never races a write), add:

        from . import reliability
        reliability.maybe_backup(name)        # cheap: a real copy only every ~30 min

  * Crash-recovery on load — wrap each critical read so a corrupt file self-heals from
    the newest good backup instead of taking the process down. Replace e.g.

        heart = Heart.from_dict(load_json(_path(name)))
    with
        from . import reliability
        heart = Heart.from_dict(reliability.guarded_load(name, _path(name)))

    `guarded_load` returns the parsed object; on corruption it restores that one file
    from backup (LOUD stderr), then re-reads. If there is no good backup it raises,
    because a wrong guess about her state is worse than a clean stop.

  * Boot health gate — in `main()`, after `_ensure(...)`, log a health line:

        from . import reliability
        reliability.boot_check(name)          # prints one ok|degraded|critical line

CLI
    python3 -m anima.reliability --name Vera --health
    python3 -m anima.reliability --name Vera --backup
    python3 -m anima.reliability --name Vera --verify
    python3 -m anima.reliability --name Vera --restore 20260603-221900 --confirm
    python3 -m anima.reliability --selftest        # corrupt -> detect -> restore, end to end
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# numpy is a hard core dependency already (anima/heart.py); imported for parity/availability.
try:
    import numpy as _np  # noqa: F401
except Exception:                                   # pragma: no cover - numpy is required
    _np = None

# crypto is part of the package; fall back to a no-op shim so this module stays
# importable/testable in isolation (e.g. copied out for a quick check).
try:
    from . import crypto as _crypto
except Exception:                                   # pragma: no cover
    class _crypto:                                  # type: ignore
        @staticmethod
        def maybe_decrypt(raw: str) -> str:
            return raw

        @staticmethod
        def enabled() -> bool:
            return False


# The store, resolved at call time (not import time) so a changed cwd / test store is
# honoured. Mirrors `STORE = Path(".anima")` used across the package.
DEFAULT_STORE = Path(".anima")
BACKUPS_DIRNAME = "backups"
KEEP = 14                                           # rotate to this many snapshots
STALE_DAYS = 14                                     # "last-modified sane" upper bound for a live creature
BACKUP_EVERY_S = 30 * 60                            # maybe_backup() cadence: a real copy at most this often

# status ladder (worst wins)
OK, DEGRADED, CRITICAL = "ok", "degraded", "critical"
_RANK = {OK: 0, DEGRADED: 1, CRITICAL: 2}


def _worst(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


# Every file under .anima/ that holds part of who she is. (kind drives the checks.)
#   kind="json"      must parse as JSON; structural sniff applies
#   kind="json-vec"  JSON *and* gets the NaN/inf vector scan (the heart, memory, replay)
#   kind="text"      decrypts to text; only "present + non-empty when expected" matters
# required=True files are expected to exist for an established creature; their absence is
# degrading. Optional files (persona, narrative, brain) only fail if present-but-broken.
@dataclass(frozen=True)
class Spec:
    suffix: str                                     # filename = f"{name}{suffix}" unless `fixed`
    kind: str                                       # "json" | "json-vec" | "text"
    required: bool                                  # expected to exist for an established creature
    min_bytes: int                                  # below this (decrypted) = "trivial / likely truncated"
    fixed: str | None = None                        # set for shared files (brain.json) — name-independent
    structure: str | None = None                    # a structural hint for verify_integrity

    def filename(self, name: str) -> str:
        return self.fixed if self.fixed else f"{name}{self.suffix}"


# Order matters only for report readability. The heart is first because it is the Self.
SPECS: tuple[Spec, ...] = (
    Spec(".json", "json-vec", required=True, min_bytes=40, structure="heart"),
    Spec(".mem.json", "json-vec", required=True, min_bytes=10, structure="memory"),
    Spec(".replay.json", "json-vec", required=False, min_bytes=10, structure="replay"),
    Spec(".history.json", "json", required=False, min_bytes=2, structure="history"),
    Spec(".lirf.json", "json", required=False, min_bytes=2, structure="lirf"),   # the LIRF fact ledger — her strongest memory; LAW 001 demands redundancy
    Spec(".world.json", "json", required=False, min_bytes=2, structure="world"),  # the world-state relation graph — situations over the facts; LAW 001 redundancy
    Spec(".chat.archive.jsonl", "text", required=False, min_bytes=1),        # permanent raw-conversation archive (Compressed > Forgotten)
    Spec(".portrait.md", "text", required=True, min_bytes=1),
    Spec(".persona.md", "text", required=False, min_bytes=1),
    Spec(".values.json", "json", required=False, min_bytes=2, structure="values"),
    Spec(".dials.json", "json", required=False, min_bytes=2, structure="dials"),
    Spec(".caps.json", "json", required=False, min_bytes=2, structure="caps"),
    Spec(".narrative.txt", "text", required=False, min_bytes=1),
    Spec("", "json", required=False, min_bytes=2, fixed="brain.json", structure="brain"),
)


# --- clock injection (so backups are testable; never bury datetime.now() unreachably) --

def _now() -> float:
    """The wall clock. A test (or the CLI) can pass its own `clock` everywhere a
    timestamp is minted, so nothing here depends on the real time of day."""
    return time.time()


def _resolve_clock(clock) -> float:
    """A clock may be a float epoch, a zero-arg callable, or None (=> real time)."""
    if clock is None:
        return _now()
    if callable(clock):
        return float(clock())
    return float(clock)


def _stamp(clock=None) -> str:
    """A filesystem-safe snapshot id: YYYYmmdd-HHMMSS in LOCAL time, matching the
    existing scripts/backup-anima.sh convention. `clock` is injected for tests."""
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(_resolve_clock(clock)))


# --- low-level, corruption-aware readers ------------------------------------------------
# These deliberately do NOT use util.load_json, which swallows JSON errors and returns a
# default — exactly the behaviour that would hide corruption from us.

def _read_bytes(p: Path) -> bytes | None:
    try:
        return p.read_bytes()
    except OSError:
        return None


def _decrypt_text(raw_bytes: bytes) -> tuple[str | None, str | None]:
    """(text, error). Decode UTF-8 then decrypt if sealed. Distinguishes a wrong/missing
    key (a real, reportable problem) from clean plaintext."""
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None, "not valid UTF-8 (binary garbage where text/JSON was expected)"
    try:
        return _crypto.maybe_decrypt(raw), None
    except Exception as e:                          # RuntimeError: encrypted but key wrong/unset
        return None, str(e)


def _parse_json(raw_bytes: bytes):
    """(obj, error). Decrypt-then-parse. Truncated/invalid JSON surfaces here instead of
    being silently dropped the way util.load_json would."""
    text, err = _decrypt_text(raw_bytes)
    if err:
        return None, err
    text = (text or "").strip()
    if not text:
        return None, "file is empty after decrypt"
    try:
        return json.loads(text), None
    except ValueError as e:
        return None, f"invalid/truncated JSON: {e}"


def _finite_scan(obj) -> str | None:
    """Walk a decoded heart/memory object for NaN/inf hiding in the numeric vectors.
    Returns a reason for the first offender, else None. Iterative + bounded so a
    pathological file can't blow the stack."""
    # json.loads accepts NaN/Infinity by default, so this is a real, reachable failure
    # mode for a numeric state file written by an unlucky/buggy save.
    bad_tokens = ("NaN", "Infinity", "-Infinity")
    stack = [("", obj)]
    seen = 0
    while stack:
        where, node = stack.pop()
        seen += 1
        if seen > 5_000_000:                        # safety valve on absurd inputs
            return None
        if isinstance(node, bool):
            continue
        if isinstance(node, float):
            if math.isnan(node) or math.isinf(node):
                return f"non-finite number ({node}) at {where or 'root'}"
        elif isinstance(node, str):
            if node in bad_tokens:                  # paranoia: stringified non-finite
                return f"non-finite token {node!r} at {where or 'root'}"
        elif isinstance(node, list):
            for i, v in enumerate(node):
                stack.append((f"{where}[{i}]", v))
        elif isinstance(node, dict):
            for k, v in node.items():
                stack.append((f"{where}.{k}", v))
    return None


# --- health_check ----------------------------------------------------------------------

@dataclass
class FileHealth:
    name: str                                       # the on-disk filename
    required: bool
    present: bool
    parseable: bool | None                          # None for text files (n/a)
    size: int                                       # raw bytes on disk (0 if absent)
    age_s: float | None                             # seconds since last modified
    status: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "file": self.name, "required": self.required, "present": self.present,
            "parseable": self.parseable, "size": self.size,
            "age_s": None if self.age_s is None else round(self.age_s, 1),
            "status": self.status, "detail": self.detail,
        }


def _check_one(store: Path, spec: Spec, name: str, clock=None) -> FileHealth:
    fn = spec.filename(name)
    p = store / fn
    now = _resolve_clock(clock)

    if not p.exists():
        st = DEGRADED if spec.required else OK
        det = ("missing (expected for an established creature)" if spec.required
               else "absent (optional)")
        return FileHealth(fn, spec.required, False, None, 0, None, st, det)

    raw = _read_bytes(p)
    if raw is None:
        return FileHealth(fn, spec.required, True, None, 0, None, CRITICAL,
                          "exists but unreadable (permissions/IO)")

    size = len(raw)
    try:
        age = now - p.stat().st_mtime
    except OSError:
        age = None

    status, notes = OK, []

    # last-modified sanity: a future mtime means a clock/copy problem; an ancient required
    # file is suspicious. Informational for optional files.
    if age is not None:
        if age < -2.0:
            status = _worst(status, DEGRADED)
            notes.append("modified in the FUTURE (clock skew?)")
        elif spec.required and age > STALE_DAYS * 86400:
            status = _worst(status, DEGRADED)
            notes.append(f"stale: untouched for {age / 86400:.0f}d")
    disp_age = None if age is None else max(0.0, age)

    if spec.kind in ("json", "json-vec"):
        obj, err = _parse_json(raw)
        if err:
            return FileHealth(fn, spec.required, True, False, size, disp_age, CRITICAL, err)
        # decrypted-size sanity (encryption inflates bytes, so judge the parsed text)
        dtext, _ = _decrypt_text(raw)
        dsize = len((dtext or "").strip())
        if dsize < spec.min_bytes:
            status = _worst(status, DEGRADED)
            notes.append(f"suspiciously small ({dsize}B decrypted)")
        if spec.kind == "json-vec":
            why = _finite_scan(obj)
            if why:
                return FileHealth(fn, spec.required, True, True, size, disp_age, CRITICAL, why)
        return FileHealth(fn, spec.required, True, True, size, disp_age, status,
                          "; ".join(notes) or "ok")

    # text file: decrypt, then "present + non-empty when expected"
    text, err = _decrypt_text(raw)
    if err:
        return FileHealth(fn, spec.required, True, None, size, disp_age, CRITICAL, err)
    if len((text or "").strip()) < spec.min_bytes:
        st = DEGRADED if spec.required else OK
        notes.append("empty" + (" (expected to hold content)" if spec.required else ""))
        status = _worst(status, st)
    return FileHealth(fn, spec.required, True, None, size, disp_age, status, "; ".join(notes) or "ok")


def health_check(name: str, store=None, clock=None) -> dict:
    """A structured health report on every critical .anima file for `name`.

    Returns {name, store, status, counts, files:[…], ts}. `status` is the worst of all
    files: ok (everything fine) | degraded (something missing/small/stale but no data
    loss) | critical (a file is corrupt/unreadable/non-finite — recovery needed)."""
    store = DEFAULT_STORE if store is None else Path(store)
    files = [_check_one(store, s, name, clock=clock) for s in SPECS]
    overall = OK
    counts = {OK: 0, DEGRADED: 0, CRITICAL: 0}
    for f in files:
        overall = _worst(overall, f.status)
        counts[f.status] += 1
    return {
        "name": name,
        "store": str(store),
        "status": overall,
        "counts": counts,
        "files": [f.to_dict() for f in files],
        "ts": _stamp(clock),
    }


# --- backup -----------------------------------------------------------------------------

def _backups_root(store: Path) -> Path:
    return store / BACKUPS_DIRNAME


def _existing_snapshots(store: Path) -> list[str]:
    """Snapshot ids (timestamp dir names) present, oldest→newest by name (lexical ==
    chronological for the YYYYmmdd-HHMMSS format)."""
    root = _backups_root(store)
    if not root.is_dir():
        return []
    out = [d.name for d in root.iterdir()
           if d.is_dir() and not d.name.startswith(".")]
    return sorted(out)


def _live_files(store: Path, name: str) -> list[str]:
    """The critical files that actually exist on disk right now (the set worth copying)."""
    return [s.filename(name) for s in SPECS if (store / s.filename(name)).exists()]


def _enc_enabled() -> bool:
    try:
        return bool(_crypto.enabled())
    except Exception:
        return False


def backup(name: str, store=None, keep: int = KEEP, clock=None, ts=None) -> dict:
    """Atomically snapshot the critical files into `.anima/backups/<ts>/`, then rotate to
    the newest `keep` snapshots.

    Atomicity: every file is copied into a sibling temp dir and the whole dir is renamed
    into place with os.replace — a crash mid-backup leaves either nothing or a complete
    snapshot, never a half-snapshot that restore might trust.

    Copies RAW BYTES (shutil.copy2 keeps mtimes), so encrypted files stay encrypted and a
    snapshot is byte-identical to the live file.

    The timestamp is INJECTED: pass `ts` ('YYYYmmdd-HHMMSS') or `clock` (epoch float or
    zero-arg callable). Only if both are omitted is the real wall clock read — so tests
    never depend on datetime.now()."""
    store = DEFAULT_STORE if store is None else Path(store)
    created = _resolve_clock(clock)
    stamp = ts if ts else _stamp(clock)
    root = _backups_root(store)
    root.mkdir(parents=True, exist_ok=True)

    files = _live_files(store, name)
    dest = root / stamp
    if dest.exists():                               # never silently clobber an existing snapshot
        suffix = 1
        while (root / f"{stamp}.{suffix}").exists():
            suffix += 1
        stamp = f"{stamp}.{suffix}"
        dest = root / stamp

    tmp = Path(tempfile.mkdtemp(prefix=f".bk-{stamp}-", dir=str(root)))
    copied = []
    try:
        for fn in files:
            shutil.copy2(store / fn, tmp / fn)
            copied.append(fn)
        # a tiny manifest so a snapshot is self-describing (which creature + when), even if
        # the dir is later moved onto an external drive.
        manifest = {"name": name, "stamp": stamp, "created": created,
                    "files": copied, "encrypted": _enc_enabled(), "schema": 1}
        (tmp / "_manifest.json").write_text(json.dumps(manifest, indent=2))
        os.replace(tmp, dest)                        # atomic publish of the whole snapshot
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    pruned = _rotate(store, keep)
    return {"ok": True, "stamp": stamp, "dir": str(dest), "files": copied,
            "kept": _existing_snapshots(store), "pruned": pruned}


def _rotate(store: Path, keep: int) -> list[str]:
    """Delete oldest snapshots beyond `keep`. Returns the ids removed."""
    snaps = _existing_snapshots(store)
    if keep <= 0 or len(snaps) <= keep:
        return []
    doomed = snaps[: len(snaps) - keep]
    root = _backups_root(store)
    for s in doomed:
        shutil.rmtree(root / s, ignore_errors=True)
    return doomed


def maybe_backup(name: str, store=None, every_s: int = BACKUP_EVERY_S, clock=None) -> dict | None:
    """Cheap throttled backup for the hot turn loop: snapshots only if the newest snapshot
    is older than `every_s` (default 30 min). Returns the backup() result if it ran, else
    None. Safe — and intended — to call on every single turn."""
    store = DEFAULT_STORE if store is None else Path(store)
    now = _resolve_clock(clock)
    snaps = _existing_snapshots(store)
    if snaps:
        newest = _backups_root(store) / snaps[-1]
        try:
            if now - newest.stat().st_mtime < every_s:
                return None
        except OSError:
            pass
    try:
        return backup(name, store=store, clock=clock)
    except Exception as e:                           # a backup must NEVER take down a turn
        print(f"[anima reliability] periodic backup failed (continuing): {e}", file=sys.stderr)
        return None


# --- snapshot inspection / good-backup selection ---------------------------------------

def _snapshot_file(store: Path, stamp: str, fn: str) -> Path:
    return _backups_root(store) / stamp / fn


def _file_is_good(store: Path, stamp: str, fn: str, spec: Spec) -> bool:
    """Is this one file, inside snapshot `stamp`, recoverable (parses / decrypts and is
    finite where it must be)? Used to pick the most-recent-GOOD backup, not merely the
    most recent."""
    raw = _read_bytes(_snapshot_file(store, stamp, fn))
    if raw is None:
        return False
    if spec.kind in ("json", "json-vec"):
        obj, err = _parse_json(raw)
        if err:
            return False
        if spec.kind == "json-vec" and _finite_scan(obj):
            return False
        return True
    text, err = _decrypt_text(raw)
    return err is None and len((text or "").strip()) >= spec.min_bytes


def latest_good_backup(name: str, fn: str | None = None, store=None) -> str | None:
    """The id of the most-recent snapshot that is a safe source.

    If `fn` is given, the snapshot must contain a GOOD copy of that one file. If `fn` is
    None, it must contain a good copy of the heart (`<name>.json`) — the one file whose
    loss is unrecoverable — as the minimum bar for "a backup worth trusting"."""
    store = DEFAULT_STORE if store is None else Path(store)
    spec_by_fn = {s.filename(name): s for s in SPECS}
    target_fn = fn if fn else f"{name}.json"
    spec = spec_by_fn.get(target_fn)
    if spec is None:                                 # unknown file: accept any snapshot that has it as readable bytes
        spec = Spec("", "text", required=False, min_bytes=0)
    for stamp in reversed(_existing_snapshots(store)):
        if _file_is_good(store, stamp, target_fn, spec):
            return stamp
    return None


# --- verify_integrity -------------------------------------------------------------------

def _structural_complaint(spec: Spec, obj) -> str | None:
    """Light structural sanity per known shape — catches a file that PARSES as JSON but is
    the wrong thing (e.g. a heart whose `h` vector vanished). Deliberately permissive: only
    flags shapes that are unambiguously broken, never merely unusual."""
    s = spec.structure
    if s == "heart":
        if not isinstance(obj, dict):
            return "heart is not a JSON object"
        for key in ("name", "seed", "h"):
            if key not in obj:
                return f"heart missing required key {key!r}"
        if not isinstance(obj.get("h"), list) or not obj["h"]:
            return "heart's feeling-state vector `h` is empty/missing"
    elif s == "memory":
        if not isinstance(obj, dict) or not isinstance(obj.get("rows"), list):
            return "memory missing its `rows` list"
    elif s == "replay":
        if not isinstance(obj, dict) or "episodes" not in obj:
            return "replay missing its `episodes`"
    elif s == "history":
        if not isinstance(obj, list):
            return "history is not a JSON list of turns"
    elif s == "lirf":
        if not isinstance(obj, dict) or not isinstance(obj.get("rows"), list):
            return "LIRF ledger missing its `rows` list (parsed but wrong shape)"
    elif s == "world":
        if not isinstance(obj, dict) or not isinstance(obj.get("relations"), list):
            return "world store missing its `relations` list (parsed but wrong shape)"
    elif s == "values":
        if not isinstance(obj, list):
            return "values is not a JSON list"
    elif s in ("dials", "caps", "brain"):
        if not isinstance(obj, dict):
            return f"{s} is not a JSON object"
    return None


def verify_integrity(name: str, store=None) -> dict:
    """Hunt specifically for corruption (a stronger, narrower lens than health_check):
    truncated/invalid JSON, NaN/inf in the heart's vectors, empty-but-expected files, and
    wrong-key encryption. For every problem, name the most-recent GOOD backup that can
    recover that file.

    Returns {name, store, corrupt(bool), issues:[{file, why, recover_from}], ts}."""
    store = DEFAULT_STORE if store is None else Path(store)
    issues = []
    for spec in SPECS:
        fn = spec.filename(name)
        p = store / fn
        if not p.exists():
            if spec.required:
                issues.append({"file": fn, "why": "missing (expected file)",
                               "recover_from": latest_good_backup(name, fn, store=store)})
            continue
        raw = _read_bytes(p)
        if raw is None:
            issues.append({"file": fn, "why": "unreadable (permissions/IO error)",
                           "recover_from": latest_good_backup(name, fn, store=store)})
            continue
        why = None
        if spec.kind in ("json", "json-vec"):
            obj, err = _parse_json(raw)
            if err:
                why = err
            elif spec.kind == "json-vec":
                why = _finite_scan(obj) or _structural_complaint(spec, obj)
            else:
                why = _structural_complaint(spec, obj)
        else:  # text
            text, err = _decrypt_text(raw)
            if err:
                why = err
            elif spec.required and len((text or "").strip()) < spec.min_bytes:
                why = "empty but expected to hold content"
        if why:
            issues.append({"file": fn, "why": why,
                           "recover_from": latest_good_backup(name, fn, store=store)})
    return {"name": name, "store": str(store), "corrupt": bool(issues),
            "issues": issues, "ts": _stamp()}


# --- restore (confirm-gated) ------------------------------------------------------------

def restore(name: str, ts: str, store=None, confirm: bool = False,
            files=None, clock=None) -> dict:
    """Restore a snapshot's files over the live state.

    HARD CONFIRM GATE: with confirm=False this is a DRY RUN — it reports exactly what it
    *would* overwrite and returns ok=False, applied=False, touching nothing. Live state is
    never silently replaced.

    With confirm=True it first snapshots the CURRENT live state (so the restore is itself
    undoable), then atomically writes each restored file (temp + os.replace per file).

    `files` optionally limits the restore to a subset of filenames (used by the crash guard
    to heal a single corrupt file). Default: every file in the snapshot."""
    store = DEFAULT_STORE if store is None else Path(store)
    snap = _backups_root(store) / ts
    if not snap.is_dir():
        return {"ok": False, "applied": False,
                "error": f"no snapshot {ts!r} under {_backups_root(store)}",
                "available": _existing_snapshots(store)}

    available = sorted(q.name for q in snap.iterdir()
                       if q.is_file() and q.name != "_manifest.json")
    targets = available if files is None else [f for f in available if f in set(files)]
    if not targets:
        return {"ok": False, "applied": False,
                "error": "snapshot has none of the requested files",
                "snapshot_files": available}

    if not confirm:
        return {"ok": False, "applied": False, "dry_run": True,
                "would_restore": targets, "from": ts, "store": str(store),
                "note": "re-run with confirm=True (CLI: --confirm) to apply; "
                        "live state is snapshotted first so this is undoable"}

    # safety snapshot of the current live state before we overwrite anything
    pre = backup(name, store=store, clock=clock)
    restored = []
    for fn in targets:
        src = snap / fn
        dst = store / fn
        fd, tmp = tempfile.mkstemp(dir=str(store), suffix=".restore.tmp")
        os.close(fd)
        try:
            shutil.copy2(src, tmp)                   # atomic per-file: same-dir temp, then replace
            os.replace(tmp, dst)
            restored.append(fn)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    return {"ok": True, "applied": True, "restored": restored, "from": ts,
            "store": str(store), "pre_restore_backup": pre["stamp"]}


# --- crash-recovery guard ---------------------------------------------------------------

def _loud(msg: str) -> None:
    bar = "!" * 72
    print(f"\n{bar}\n[anima reliability] {msg}\n{bar}", file=sys.stderr, flush=True)


class guard:
    """Context manager that turns a corrupt-file crash into a self-heal.

    Wrap a critical read. If the body raises while loading/parsing the named file, the guard
    restores THAT file from the most-recent-good backup (logging LOUDLY to stderr) and
    suppresses the exception, so the caller can simply re-read. If no good backup exists, it
    re-raises — a wrong guess about her state is worse than a clean failure.

        with reliability.guard(name, _path(name)) as g:
            heart = Heart.from_dict(load_json(_path(name)))
        if g.recovered:                       # the file was healed from backup
            heart = Heart.from_dict(load_json(_path(name)))   # re-read the good copy

    Prefer `guarded_load` below for the common "parse this JSON file" case."""

    def __init__(self, name: str, path, store=None):
        self.name = name
        self.path = Path(path)
        self.store = DEFAULT_STORE if store is None else Path(store)
        self.recovered = False
        self.restored_from = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            return False
        fn = self.path.name
        _loud(f"FAILED to load {fn}: {exc_type.__name__}: {exc} — attempting recovery from backup")
        stamp = latest_good_backup(self.name, fn, store=self.store)
        if not stamp:
            _loud(f"NO good backup of {fn} exists — cannot recover. "
                  f"Re-raising rather than guessing her state.")
            return False                            # propagate the original exception
        res = restore(self.name, stamp, store=self.store, confirm=True, files=[fn])
        if res.get("applied"):
            self.recovered = True
            self.restored_from = stamp
            _loud(f"RECOVERED {fn} from backup {stamp} "
                  f"(pre-recovery state saved as {res.get('pre_restore_backup')}). Continuing — "
                  f"verify her with: python3 -m anima.reliability --name {self.name} --health")
            return True                             # swallow the exception; caller re-reads
        _loud(f"recovery of {fn} from {stamp} FAILED ({res.get('error')}). Re-raising.")
        return False


def guarded_load(name: str, path, store=None):
    """Drop-in for `util.load_json(path)` on a CRITICAL file, with self-heal.

    Reads + parses the file the same corruption-aware way verify_integrity does. On any
    failure it restores that one file from the most-recent-good backup (LOUD stderr) and
    re-reads. If there is no good backup, it raises RuntimeError instead of returning a
    silent default — because for her state, a wrong value is worse than a loud stop.

    Returns the parsed object on success."""
    store = DEFAULT_STORE if store is None else Path(store)
    p = Path(path)
    raw = _read_bytes(p)
    if raw is None:
        err = f"{p.name} is missing/unreadable"
        obj = None
    else:
        obj, err = _parse_json(raw)
        if not err:
            err = _finite_scan(obj)                 # also reject non-finite heart/memory vectors at the door
    if not err:
        return obj

    fn = p.name
    _loud(f"load of {fn} failed: {err} — recovering from the most-recent good backup")
    stamp = latest_good_backup(name, fn, store=store)
    if not stamp:
        raise RuntimeError(
            f"{fn} is corrupt ({err}) and no good backup exists to recover from. "
            f"Refusing to fabricate her state. Inspect {store} and run "
            f"`python3 -m anima.reliability --name {name} --verify`.")
    res = restore(name, stamp, store=store, confirm=True, files=[fn])
    if not res.get("applied"):
        raise RuntimeError(f"could not restore {fn} from backup {stamp}: {res.get('error')}")
    _loud(f"RECOVERED {fn} from backup {stamp} "
          f"(pre-recovery saved as {res.get('pre_restore_backup')}).")
    obj2, err2 = _parse_json(_read_bytes(p) or b"")
    if err2:
        raise RuntimeError(f"{fn} still unreadable after restoring {stamp}: {err2}")
    return obj2


# --- memory-store guarded load (LIRF ledger / world relations) --------------------------
# The heart's guarded_load RAISES when it can't recover, because a wrong heart is worse than
# a crash. The high-volume MEMORY stores (the LIRF fact ledger, the world-state relation
# graph) want a softer landing on the SAME guarantee: a corrupt store must NEVER silently
# load as 0 rows. It must (1) recover from the latest good backup if one exists, else (2)
# stop CLEANLY with a clearly-flagged-empty result AND a constitution.approved_loss record
# — never a silent wrong answer, never a turn-loop crash. This is the function Facts.load /
# World.load call instead of raw util.load_json.

def _record_unrecoverable_loss(name, fn, why, store) -> None:
    """Write a LAW-001 approved_loss for a genuinely unrecoverable corrupt store. The loss
    is real (the on-disk rows could not be parsed and no good backup exists), so it must be
    RECORDED, never silent. Best-effort: the continuity ledger lives beside the store, so we
    point constitution.STORE at the SAME store for the write. A failure to record is logged
    LOUDLY but must not itself crash the load (we still return flagged-empty)."""
    try:
        from . import constitution
    except Exception as e:                              # pragma: no cover - constitution is core
        _loud(f"could NOT import constitution to record the loss of {fn}: {e}")
        return
    saved = getattr(constitution, "STORE", None)
    try:
        constitution.STORE = Path(store)
        constitution.approved_loss(
            subsystem=f"reliability.guarded_store_load[{fn}]",
            what=f"all rows in {fn} (corrupt on disk, unparseable: {why})",
            why="store corrupt/unreadable AND no good backup exists to recover from; "
                "stopping clean with a flagged-empty store rather than overwriting good "
                "data or silently reporting 0 rows (Unknown > Lost)",
            approver="reliability.guarded_store_load",
            name=name,
            detail={"file": fn, "reason": why, "store": str(store)},
        )
        _loud(f"recorded an approved_loss for the unrecoverable {fn} "
              f"(see {Path(store) / (name + '.continuity.jsonl')}).")
    except Exception as e:
        _loud(f"FAILED to record the approved_loss for {fn}: {e} — the loss is real; "
              f"returning a flagged-empty store so nothing good is overwritten.")
    finally:
        if saved is not None:
            constitution.STORE = saved


def _store_shape_complaint(obj, expect_key) -> str | None:
    """Structural sanity for a memory store: it must be a JSON object carrying its container
    list (`rows` for LIRF, `relations` for world). Catches the file that PARSES as JSON but
    is the WRONG THING — most importantly the literal `null` (valid JSON, decodes to None) or
    a bare list/number, which the raw loader would silently treat as 0 rows. No `expect_key`
    => no structural opinion (any parseable JSON is accepted)."""
    if not expect_key:
        return None
    if not isinstance(obj, dict):
        return (f"store is not a JSON object (got {type(obj).__name__}); "
                f"missing its `{expect_key}` container")
    if not isinstance(obj.get(expect_key), list):
        return f"store missing its `{expect_key}` list"
    return None


def guarded_store_load(name, path, store=None, kind="store", expect_key=None):
    """Corruption-aware load for a MEMORY store (LIRF ledger / world relations).

    The clean-load happy path is preserved EXACTLY: a good file is read + parsed once (the
    same corruption-aware way verify_integrity reads), with NO added latency, and returned.

    `expect_key` ("rows" | "relations") adds a structural gate so a file that PARSES as JSON
    but is the wrong shape — the literal `null`, a bare list, a number — is treated as
    corruption rather than silently read as 0 rows (the `null` total-loss case).

    On a corrupt/unreadable/wrong-shape store it does NOT silently return an empty default the
    way util.load_json does — that is the bug. Instead it:
      1. restores that one file from the most-recent GOOD backup (LOUD stderr) and re-reads;
      2. if there is no good backup, records a constitution.approved_loss (the loss is real
         and must be logged, never silent) and returns a clearly-FLAGGED-EMPTY result.

    Returns (obj, info) where `obj` is the parsed JSON (None when flagged-empty) and `info`
    is a dict: {"ok", "recovered", "restored_from", "empty", "flagged", "why"}. The caller
    treats a flagged-empty as a clean stop (0 rows is acceptable ONLY because it is loud +
    recorded, not silent). A corrupt store can NEVER overwrite a good backup, because we only
    ever RESTORE from backups here and never call backup() on an unparseable file."""
    store = DEFAULT_STORE if store is None else Path(store)
    p = Path(path)
    fn = p.name

    raw = _read_bytes(p)
    if raw is None and not p.exists():
        # genuinely absent (a brand-new creature) is NOT corruption — empty, unflagged.
        return None, {"ok": True, "recovered": False, "restored_from": None,
                      "empty": True, "flagged": False, "why": "absent (new store)"}
    if raw is None:
        err = f"{fn} exists but is unreadable (permissions/IO)"
        obj = None
    else:
        obj, err = _parse_json(raw)                     # decrypt-then-parse; surfaces corruption
        if not err:
            err = _store_shape_complaint(obj, expect_key)   # `null`/bare-list/etc. is corruption
    if not err:
        return obj, {"ok": True, "recovered": False, "restored_from": None,
                     "empty": False, "flagged": False, "why": ""}

    # --- corrupt: attempt recovery from the most-recent GOOD backup of THIS file -----------
    _loud(f"load of {fn} ({kind}) failed: {err} — attempting recovery from the most-recent "
          f"good backup (a corrupt store will NOT overwrite a good backup).")
    stamp = latest_good_backup(name, fn, store=store)
    if stamp:
        res = restore(name, stamp, store=store, confirm=True, files=[fn])
        if res.get("applied"):
            obj2, err2 = _parse_json(_read_bytes(p) or b"")
            if not err2:
                err2 = _store_shape_complaint(obj2, expect_key)   # a recovered file must be well-shaped too
            if not err2:
                _loud(f"RECOVERED {fn} from backup {stamp} "
                      f"(pre-recovery state saved as {res.get('pre_restore_backup')}).")
                return obj2, {"ok": True, "recovered": True, "restored_from": stamp,
                              "empty": False, "flagged": False, "why": err}
            _loud(f"{fn} still unreadable after restoring {stamp}: {err2}")
        else:
            _loud(f"recovery of {fn} from {stamp} FAILED ({res.get('error')}).")

    # --- no good backup: stop CLEANLY, flagged-empty, and RECORD the loss (never silent) ---
    _loud(f"NO good backup of {fn} exists — refusing to silently report 0 rows. "
          f"Recording an approved_loss and returning a FLAGGED-EMPTY {kind}. "
          f"Inspect {store} and run `python3 -m anima.reliability --name {name} --verify`.")
    _record_unrecoverable_loss(name, fn, err, store)
    return None, {"ok": False, "recovered": False, "restored_from": None,
                  "empty": True, "flagged": True, "why": err}


def maybe_backup_store(name, path, store=None, kind="store", expect_key=None) -> dict | None:
    """Take a GUARDED snapshot at a safe point so a good backup of a memory store always
    exists — but ONLY when the live file is currently parseable AND well-shaped, so a
    corrupt/empty/wrong-shape state can never become the backup. Cheap + throttled (reuses
    maybe_backup's cadence + try/except), and NEVER raises into the caller: a backup failure
    must not break or slow a load.

    `expect_key` ("rows" | "relations"), when given, additionally requires the file to carry
    its container list before it is allowed to be snapshotted — so a `null`/bare-list file is
    never mistaken for good state worth backing up.

    This is the companion to guarded_store_load: the load proves the file is good, then this
    ensures that good state is captured. Returns the maybe_backup() result, or None if it was
    skipped (throttled, file not good, or any error — all non-fatal)."""
    store = DEFAULT_STORE if store is None else Path(store)
    p = Path(path)
    try:
        raw = _read_bytes(p)
        if raw is None:
            return None                                 # nothing good to snapshot
        obj, err = _parse_json(raw)
        if err or _store_shape_complaint(obj, expect_key):
            return None                                 # corrupt/wrong-shape: NEVER overwrite a good backup
        return maybe_backup(name, store=store)
    except Exception as e:                              # a backup must NEVER take down a load
        print(f"[anima reliability] guarded store backup of {p.name} skipped ({e})",
              file=sys.stderr)
        return None


# --- boot health gate (for server main()) ----------------------------------------------

def boot_check(name: str, store=None) -> dict:
    """One-line health summary at server start. Prints ok|degraded|critical to stderr and
    returns the full report. On 'critical' it also names the newest good backup so the
    operator knows recovery is possible."""
    rep = health_check(name, store=store)
    print(f"[anima reliability] {name}: {rep['status'].upper()} "
          f"(ok={rep['counts'][OK]} degraded={rep['counts'][DEGRADED]} "
          f"critical={rep['counts'][CRITICAL]})", file=sys.stderr)
    if rep["status"] == CRITICAL:
        for f in rep["files"]:
            if f["status"] == CRITICAL:
                gb = latest_good_backup(name, f["file"], store=store)
                print(f"    ! {f['file']}: {f['detail']} — recover from backup "
                      f"{gb or '(NONE available)'}", file=sys.stderr)
    return rep


# --- self-test: a real corrupt -> detect -> restore cycle ------------------------------

def _selftest() -> int:
    """Stand up a throwaway store, write realistic creature files, back them up, corrupt
    them three different ways, and prove verify_integrity flags each AND restore recovers
    them. Pure stdlib+numpy, no Ollama/network/audio. Exit 0 on success."""
    fails: list[str] = []

    def check(label: str, cond: bool):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    base = [1_780_000_000.0]                         # a deterministic, advancing clock

    def clk():
        base[0] += 1.0                              # successive backups get distinct ids/mtimes
        return base[0]

    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / ".anima"
        store.mkdir(parents=True)
        name = "Selftest"

        # --- a realistic, mutually-consistent creature on disk (matches the real shapes) ---
        try:
            from .heart import Heart                 # build genuine heart bytes (what server.py writes)
            heart = Heart.born(name, seed=42, now=base[0])
            heart.perceive(heart._percept_vec(presence=1.0, wellbeing=0.7), now=base[0])
            heart_dict = heart.to_dict()
        except Exception:
            heart_dict = {"name": name, "seed": 42, "n": 4, "birth_ts": base[0],
                          "last_tick": base[0], "unrest": 0.1, "learned": False,
                          "h": [0.01, -0.02, 0.03, 0.0]}

        (store / f"{name}.json").write_text(json.dumps(heart_dict))
        (store / f"{name}.mem.json").write_text(json.dumps(
            {"rows": [{"clock": base[0], "dt": 0.0, "I": [0.1] * 13}]}))
        (store / f"{name}.replay.json").write_text(json.dumps(
            {"capacity": 64, "seen": 1, "episodes": [[[[0.1] * 13] * 4, [1.0] * 4]]}))
        (store / f"{name}.history.json").write_text(json.dumps([["hi", "hello there"]]))
        (store / f"{name}.portrait.md").write_text("Selftest:\n- likes long walks\n")
        (store / f"{name}.dials.json").write_text(json.dumps({"warmth": 35, "edge": 68}))
        (store / f"{name}.values.json").write_text(json.dumps(
            [{"key": "honesty", "on": True, "level": "more"}]))
        (store / f"{name}.caps.json").write_text(json.dumps(
            {"web": True, "allowlist": ["wikipedia.org"]}))
        (store / "brain.json").write_text(json.dumps({"provider": "local", "local_model": "x"}))

        # --- baseline: a clean creature is not critical, and verify finds no corruption ---
        rep0 = health_check(name, store=store, clock=base[0])
        check("clean creature is not critical", rep0["status"] != CRITICAL)
        v0 = verify_integrity(name, store=store)
        check("clean creature: verify_integrity finds no corruption", v0["corrupt"] is False)

        # --- take a GOOD backup (deterministic id via injected clock) ---
        b1 = backup(name, store=store, clock=clk)
        check("backup created a snapshot", b1["ok"] and (store / "backups" / b1["stamp"]).is_dir())
        check("backup copied the heart", f"{name}.json" in b1["files"])
        good_heart_bytes = (store / f"{name}.json").read_bytes()
        good_portrait = (store / f"{name}.portrait.md").read_text()

        # =====================================================================
        # CORRUPTION 1: truncated / invalid JSON in the heart (the unrecoverable file)
        # =====================================================================
        (store / f"{name}.json").write_text('{"name": "Selftest", "seed": 42, "h": [0.1, 0.2,')
        v1 = verify_integrity(name, store=store)
        heart_issue = next((i for i in v1["issues"] if i["file"] == f"{name}.json"), None)
        check("truncated heart is flagged corrupt", v1["corrupt"] and heart_issue is not None)
        check("truncated heart names a recovery backup",
              bool(heart_issue) and heart_issue["recover_from"] == b1["stamp"])
        h1 = health_check(name, store=store, clock=base[0])
        check("health_check reports CRITICAL on truncated heart", h1["status"] == CRITICAL)

        # restore is confirm-gated: a dry run must NOT touch the live (corrupt) file
        dry = restore(name, b1["stamp"], store=store, confirm=False)
        check("restore without confirm is a dry run (applies nothing)",
              dry["applied"] is False and dry.get("dry_run") is True)
        check("dry run left the corrupt file in place",
              b'[0.1, 0.2,' in (store / f"{name}.json").read_bytes())

        # now actually restore, confirmed
        r1 = restore(name, b1["stamp"], store=store, confirm=True, clock=clk)
        check("confirmed restore applied", r1["applied"] is True)
        check("restore recovered the EXACT good heart bytes",
              (store / f"{name}.json").read_bytes() == good_heart_bytes)
        v1b = verify_integrity(name, store=store)
        check("heart no longer corrupt after restore",
              not any(i["file"] == f"{name}.json" for i in v1b["issues"]))

        # =====================================================================
        # CORRUPTION 2: NaN / inf smuggled into the heart's feeling-vector
        # =====================================================================
        hd = json.loads((store / f"{name}.json").read_text())
        hd["h"][0] = float("nan")                   # json.dumps emits NaN by default — the real failure mode
        (store / f"{name}.json").write_text(json.dumps(hd))
        v2 = verify_integrity(name, store=store)
        nan_issue = next((i for i in v2["issues"] if i["file"] == f"{name}.json"), None)
        check("NaN in heart vector is detected", bool(nan_issue) and "non-finite" in nan_issue["why"])
        healed = guarded_load(name, store / f"{name}.json", store=store)
        check("guarded_load returned a finite heart after self-heal",
              _finite_scan(healed) is None and healed["seed"] == 42)

        # =====================================================================
        # CORRUPTION 3: an expected text file (the Portrait) emptied out
        # =====================================================================
        (store / f"{name}.portrait.md").write_text("   \n")     # whitespace only
        v3 = verify_integrity(name, store=store)
        port_issue = next((i for i in v3["issues"] if i["file"] == f"{name}.portrait.md"), None)
        check("empty-but-expected Portrait is flagged", bool(port_issue))
        check("empty Portrait names a recovery backup",
              bool(port_issue) and port_issue["recover_from"] is not None)
        r3 = restore(name, port_issue["recover_from"], store=store, confirm=True,
                     files=[f"{name}.portrait.md"], clock=clk)
        check("portrait restored from backup", r3["applied"])
        check("restored portrait matches the good content",
              (store / f"{name}.portrait.md").read_text() == good_portrait)

        # =====================================================================
        # ROTATION: keep=N actually prunes the oldest snapshots
        # =====================================================================
        for _ in range(5):
            backup(name, store=store, keep=3, clock=clk)
        check("rotation keeps only the newest N snapshots", len(_existing_snapshots(store)) == 3)

        # crash guard: no good backup -> guarded_load raises rather than guessing
        store2 = Path(td) / "empty"
        store2.mkdir()
        (store2 / f"{name}.json").write_text("{ broken")
        raised = False
        try:
            guarded_load(name, store2 / f"{name}.json", store=store2)
        except RuntimeError:
            raised = True
        check("guarded_load raises (no silent default) when no backup exists", raised)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL RELIABILITY SELFTESTS PASS")
    return 0


# --- CLI --------------------------------------------------------------------------------

def _print_health(rep: dict) -> None:
    print(f"{rep['name']} — health: {rep['status'].upper()}  (store {rep['store']})")
    print(f"  ok={rep['counts'][OK]}  degraded={rep['counts'][DEGRADED]}  "
          f"critical={rep['counts'][CRITICAL]}")
    for f in rep["files"]:
        flag = {OK: " ok ", DEGRADED: "WARN", CRITICAL: "CRIT"}[f["status"]]
        age = "" if f["age_s"] is None else f"  {f['age_s'] / 3600:.1f}h"
        pres = "" if f["present"] else "  (absent)"
        print(f"  [{flag}] {f['file']:<22} {f['size']:>8}B{age}{pres}  {f['detail']}")


def _print_verify(rep: dict) -> None:
    if not rep["corrupt"]:
        print(f"{rep['name']} — integrity: CLEAN. No corruption detected.")
        return
    print(f"{rep['name']} — integrity: CORRUPTION FOUND ({len(rep['issues'])} issue(s)):")
    for i in rep["issues"]:
        print(f"  - {i['file']}: {i['why']}")
        if i["recover_from"]:
            print(f"      recover with: --restore {i['recover_from']} --confirm")
        else:
            print("      recover: no good backup exists")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="anima.reliability",
        description="Backup / health-check / corruption-recovery for an anima's .anima/ state.")
    ap.add_argument("--name", default="Vera", help="creature name (default Vera)")
    ap.add_argument("--store", default=None, help="path to the .anima store (default ./.anima)")
    ap.add_argument("--keep", type=int, default=KEEP, help=f"snapshots to retain (default {KEEP})")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--health", action="store_true", help="report health of every critical file")
    g.add_argument("--backup", action="store_true", help="take a timestamped snapshot now")
    g.add_argument("--verify", action="store_true", help="scan for corruption; name recovery backups")
    g.add_argument("--restore", metavar="TS", help="restore snapshot TS (requires --confirm)")
    g.add_argument("--list", action="store_true", help="list available snapshots")
    g.add_argument("--selftest", action="store_true", help="run the corrupt->detect->restore self-test")
    ap.add_argument("--confirm", action="store_true", help="actually apply a --restore (else dry run)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    store = Path(args.store) if args.store else DEFAULT_STORE

    if args.backup:
        res = backup(args.name, store=store, keep=args.keep)
        print(f"backed up -> {res['dir']}")
        print(f"  files: {', '.join(res['files']) or '(none present)'}")
        if res["pruned"]:
            print(f"  pruned old snapshots: {', '.join(res['pruned'])}")
        print(f"  snapshots kept: {', '.join(res['kept'])}")
        return 0

    if args.verify:
        _print_verify(verify_integrity(args.name, store=store))
        return 0

    if args.list:
        snaps = _existing_snapshots(store)
        print(f"{len(snaps)} snapshot(s) under {_backups_root(store)}:")
        for s in snaps:
            print(f"  {s}")
        return 0

    if args.restore:
        res = restore(args.name, args.restore, store=store, confirm=args.confirm)
        if res.get("applied"):
            print(f"restored {len(res['restored'])} file(s) from {res['from']}: "
                  f"{', '.join(res['restored'])}")
            print(f"  (pre-restore live state saved as snapshot {res['pre_restore_backup']})")
            return 0
        if res.get("dry_run"):
            print(f"DRY RUN — would restore from {res['from']}:")
            for f in res["would_restore"]:
                print(f"  {f}")
            print("\n  re-run with --confirm to apply (live state is snapshotted first, so it's undoable).")
            return 0
        print(f"restore failed: {res.get('error')}")
        if res.get("available"):
            print(f"  available snapshots: {', '.join(res['available'])}")
        return 1

    _print_health(health_check(args.name, store=store))   # default action: health
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
