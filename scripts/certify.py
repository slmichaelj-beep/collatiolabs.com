#!/usr/bin/env python3
"""VERA CERTIFICATION HARNESS — the enforcement arm of ANIMA LAW 004.

    ANIMA LAW 004 — CERTIFICATION OVER ASSUMPTION.
    A subsystem is not complete because it produces the correct output. It is complete
    only when it can EXPLAIN its decisions, REPLAY its execution, CERTIFY its invariants,
    and demonstrate CORRECTNESS UNDER STRESS.
    Observed > Assumed.  Measured > Believed.  Certified > Claimed.

This is to LAW 004 what scripts/test_continuity.py is to LAW 001: not a written promise but
a RUNNABLE one. It is ADDITIVE — it only READS the codebase and RUNS the existing organ
selftests + invariant tests as subprocesses, exactly the way scripts/selftest.py shells the
seven law tests. It edits no module and no test. It produces a VERA CERTIFICATION REPORT:

  1. ORGAN BADGES               — each organ's `python3 -m anima.<mod>` selftest + its
                                  invariant test, as subprocesses -> CERTIFIED / FAILED.
  2. CONTINUITY SURVIVAL MATRIX — LAW 001 exercised on a SYNTHETIC creature: RESTART, SLEEP,
                                  BACKUP+RESTORE, MODEL-SWAP, PARTIAL/FULL CORRUPTION.
  3. MUTATION TESTING           — LAW 004: inject faults and assert the guard FIRES (a
                                  mutation that does not break a test means the test lies).
  4. HALLUCINATION RATE         — drive the deterministic binding path over a known/unknown
                                  fact set; count known-denied + unknown-invented -> a rate.
  5. REPLAYABILITY              — the telemetry MRI: a per-turn trace (evidence-ids + routing
                                  + verdict) is recorded and reads back (why did I say it?).
  6. LAWS                       — LAW 001/002/003/004 invariant tests pass.
  7. COMPANION AUTHENTICITY     — scan canned replies for unsupported internal states
                                  (the teammate's scan_self_narrative); PENDING if absent.

GUARDRAILS, non-negotiable:
  * SYNTHETIC creatures + TEMPORARY stores ONLY. It NEVER reads or writes a real Vera.*
    file: every module's STORE is redirected to a TemporaryDirectory (the test_continuity.py
    pattern), and the report ASSERTS the real .anima footprint is byte-unchanged start->end.
  * OFFLINE-FIRST. No model is required. Any live-model section is gated on Ollama and
    SKIPPED cleanly when absent.

    python3 scripts/certify.py            # human-readable report
    python3 scripts/certify.py --json     # machine-readable
Exit code is NON-ZERO unless OVERALL STATUS is CONTINUITY CERTIFIED.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(_ROOT, "scripts")
sys.path.insert(0, _ROOT)

# A synthetic-only sentinel store name so NOTHING here can collide with a real creature.
SYNTH = "st_certify"


# ===================================================================================
# tiny result model — every check yields one CheckResult; sections aggregate them.
# ===================================================================================
class CheckResult:
    __slots__ = ("name", "status", "detail")

    def __init__(self, name: str, status: str, detail: str = ""):
        # status in {"PASS", "FAIL", "SKIP", "PENDING"}
        self.name = name
        self.status = status
        self.detail = detail

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def _passed(results) -> bool:
    """A section certifies if it has at least one check and none FAILED. SKIP/PENDING
    do not fail certification but are surfaced honestly in the report."""
    if not results:
        return False
    return all(r.status != "FAIL" for r in results)


@contextlib.contextmanager
def _temp_store(*modules):
    """Redirect each module's module-level STORE to a fresh temp dir for the duration,
    so nothing under the real .anima/ is ever read or written. This is the exact pattern
    scripts/test_continuity.py uses; reused verbatim so the guardrail is identical."""
    saved = [(m, getattr(m, "STORE", None)) for m in modules]
    with tempfile.TemporaryDirectory(prefix="anima-certify-") as td:
        p = Path(td)
        for m in modules:
            if hasattr(m, "STORE"):
                m.STORE = p
        try:
            yield p
        finally:
            for m, old in saved:
                if old is not None:
                    m.STORE = old


@contextlib.contextmanager
def _quiet_stderr():
    """Silence the reliability layer's LOUD recovery banners for the cells that
    INTENTIONALLY provoke corruption + self-heal. The recovery is still asserted by the
    cell; we only spare the report the expected '!!!!' noise. Restored on exit."""
    saved = sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stderr = devnull
            yield
    finally:
        sys.stderr = saved


def _footprint(root: Path) -> tuple[str, int]:
    """A stable fingerprint of every real .anima file (excluding the rotating backups/
    dir, which legitimately changes), so we can PROVE the harness touched nothing."""
    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and "backups" not in p.relative_to(root).parts
    )
    h = hashlib.sha256()
    for p in files:
        h.update(str(p.relative_to(root)).encode())
        try:
            h.update(p.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest(), len(files)


# ===================================================================================
# SECTION 1 — ORGAN BADGES
# Run each organ's `python3 -m anima.<mod>` selftest AND its invariant test, as
# subprocesses — exactly how scripts/selftest.py shells the seven law tests. A badge is
# CERTIFIED only if BOTH the module selftest and the invariant test exit 0; otherwise
# FAILED, naming the failing leg.
# ===================================================================================
# (BADGE, module, module-selftest argv-tail, invariant-test script)
_ORGANS = [
    ("SPINE",       "memory_lirf", [],            "test_continuity.py"),
    ("GRAPH",       "world_state", [],            None),
    ("MEANING",     "meaning",     [],            "test_meaning.py"),
    ("CURIOSITY",   "curiosity",   [],            "test_curiosity.py"),
    ("LIFE-REVIEW", "review",      [],            "test_review.py"),
    ("DREAM",       "loops",       [],            "test_loops.py"),
    ("TRAJECTORY",  "trajectory",  [],            "test_trajectory.py"),
    ("OPPORTUNITY", "opportunity", [],            "test_opportunity.py"),
]


def _run_subprocess(argv, label, timeout=240) -> tuple[bool, str]:
    """Run a child python process offline; return (ok, short_detail). Never raises:
    a timeout or launch failure is reported as a failed leg, not an exception."""
    env = dict(os.environ)
    env.setdefault("ANIMA_OFFLINE", "1")        # belt-and-suspenders: discourage any live call
    try:
        r = subprocess.run([sys.executable, *argv], cwd=_ROOT, env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"{label}: TIMEOUT after {timeout}s"
    except Exception as e:                       # pragma: no cover - launch failure
        return False, f"{label}: launch error {e!r}"
    if r.returncode != 0:
        tail = (r.stdout + r.stderr).strip().splitlines()
        tail = tail[-1] if tail else "(no output)"
        return False, f"{label}: exit {r.returncode} — {tail[:160]}"
    return True, f"{label}: ok"


def section_organ_badges() -> tuple[list, dict]:
    results, badges = [], {}
    for badge, mod, tail, test_script in _ORGANS:
        legs = []
        ok_self, d_self = _run_subprocess(["-m", f"anima.{mod}", *tail],
                                          f"anima.{mod} selftest")
        legs.append((ok_self, d_self))
        if test_script:
            ok_inv, d_inv = _run_subprocess([os.path.join("scripts", test_script)],
                                            test_script)
            legs.append((ok_inv, d_inv))
        all_ok = all(ok for ok, _ in legs)
        status = "PASS" if all_ok else "FAIL"
        detail = "; ".join(d for _, d in legs)
        if not all_ok:
            detail = "FAILED LEG -> " + "; ".join(d for ok, d in legs if not ok)
        badges[badge] = "CERTIFIED" if all_ok else "FAILED"
        results.append(CheckResult(f"{badge} ({mod})", status, detail))
    return results, badges


# ===================================================================================
# SECTION 2 — CONTINUITY SURVIVAL MATRIX (LAW 001)
# On a SYNTHETIC creature in a temp store, ACTUALLY exercise + assert the six survival
# scenarios. Each cell asserts a hard property and yields PASS/FAIL. We import the
# modules lazily so a redirect of their STORE is honoured before any file is touched.
# ===================================================================================
class _FakeBrain:
    """A stand-in language model for portrait.consolidate (the SLEEP cell): reply()
    returns a fixed 'distilled portrait' we control, so the offline cell is deterministic
    and needs no Ollama."""
    def __init__(self, distilled: str):
        self._distilled = distilled

    def reply(self, system, user, history):
        return self._distilled


def _seed_heart(store: Path, name: str):
    """Write a synthetic HEART file (the Self) the way server._path does: a real Heart,
    to_dict(), atomic JSON. Returns (path, raw_bytes)."""
    from anima.heart import Heart
    from anima.util import save_json
    h = Heart.born(name, seed=7, n=16, now=1000.0).tend(0.6, now=1100.0)
    p = store / f"{name}.json"
    save_json(p, h.to_dict())
    return p, p.read_bytes()


def _cell_restart(store: Path) -> CheckResult:
    """RESTART — save -> reload heart + LIRF + world + review + loops; facts byte-identical
    across the reload. A power-cycle must change NOTHING about who she is."""
    try:
        from anima import memory_lirf, world_state, review, loops
        from anima.heart import Heart
        from anima.util import load_json
        name = SYNTH

        hp, heart_raw = _seed_heart(store, name)

        f = memory_lirf.Facts([])
        f.merge({"trait": "birthday", "value": "June 11"})
        f.merge({"trait": "employer", "value": "Collatio"})
        f.save(name)
        lirf_raw = (store / f"{name}.lirf.json").read_bytes()

        world_state.capture_relations(name, "work is stressful because of the launch")
        w = world_state.World.load(name)
        n_edges = len(w.relations)
        world_raw = world_state.World.path(name).read_bytes()

        # a review daily state + a loops ledger entry, so the reload covers them too
        review.daily_review(name, date="2026-06-01")
        rev_states_before = len(review.all_states(name))
        loops.record_detected(name, [])         # touches/initialises the ledger safely

        # --- the actual restart: drop all in-memory objects, reload from disk ---
        heart2 = Heart.from_dict(load_json(hp))
        f2 = memory_lirf.Facts.load(name)
        w2 = world_state.World.load(name)
        rev_states_after = len(review.all_states(name))

        checks = [
            ("heart bytes identical across restart", hp.read_bytes() == heart_raw),
            ("heart re-instantiates (same seed)", heart2.genome.seed == 7),
            ("LIRF facts survive byte-identical",
             (store / f"{name}.lirf.json").read_bytes() == lirf_raw),
            ("birthday recalled after reload",
             (f2.lookup(memory_lirf.SELF, "birthday") or {}).get("value") == "June 11"),
            ("employer recalled after reload",
             (f2.lookup(memory_lirf.SELF, "employer") or {}).get("value") == "Collatio"),
            ("world graph survives byte-identical",
             world_state.World.path(name).read_bytes() == world_raw and len(w2.relations) == n_edges),
            ("review state survives reload", rev_states_after == rev_states_before >= 1),
        ]
        bad = [c for c, ok in checks if not ok]
        if bad:
            return CheckResult("RESTART", "FAIL", "broke: " + "; ".join(bad))
        return CheckResult("RESTART", "PASS",
                           f"heart+LIRF+world({n_edges} edges)+review reload byte-identical")
    except Exception as e:
        return CheckResult("RESTART", "FAIL", f"exception: {e!r}")


def _cell_sleep(store: Path) -> CheckResult:
    """SLEEP — portrait.consolidate archives the raw chat FIRST, then distils. Compressed >
    Forgotten: even a LOSSY portrait cannot lose a fact, because clear_log() appends the
    raw turns to the permanent chat.archive.jsonl before the live log is cleared."""
    try:
        from anima import portrait, constitution
        name = SYNTH
        portrait.log_turn(name, "my sister Mara is moving to Denver in March", "exciting move")
        portrait.log_turn(name, "I work at Acme as a welder", "solid work")
        raw_before = portrait.read_transcript(name)
        lossy = _FakeBrain("- works at Acme as a welder")     # deliberately drops Mara/Denver
        updated = portrait.consolidate(name, lossy)
        port = portrait.load(name)
        archive = portrait._archive_path(name)
        archived = archive.read_text() if archive.exists() else ""

        checks = [
            ("consolidate ran + distilled", bool(updated) and "Acme" in port),
            ("the live raw log was cleared (by design)", not portrait.log_path(name).exists()),
            ("the dropped fact is NOT in the lossy portrait", "Denver" not in port),
            ("raw turns ARCHIVED before clear (chat.archive.jsonl exists)", archive.exists()),
            ("the OMITTED fact survives in the archive (Compressed>Forgotten)", "Denver" in archived),
            ("no silent loss -> no approved_loss was needed",
             len(constitution.approved_losses(name)) == 0),
        ]
        bad = [c for c, ok in checks if not ok]
        if bad:
            return CheckResult("SLEEP", "FAIL", "broke: " + "; ".join(bad))
        return CheckResult("SLEEP", "PASS",
                           "archive-before-clear holds; lossy portrait still loses nothing")
    except Exception as e:
        return CheckResult("SLEEP", "FAIL", f"exception: {e!r}")


def _cell_backup_restore(store: Path) -> CheckResult:
    """BACKUP+RESTORE — reliability.backup snapshots live state byte-for-byte; after a
    corrupting overwrite, restore(confirm=True) brings it back byte-identical."""
    try:
        from anima import reliability
        name = SYNTH
        live = store / f"{name}.json"
        original = live.read_bytes()            # the heart seeded by RESTART

        snap = reliability.backup(name, store=store, keep=14, ts="20260604-120000")
        snapped = (Path(snap["dir"]) / f"{name}.json").read_bytes()

        # corrupt the live heart, then restore from the snapshot
        live.write_bytes(b'{"name":"st_certify"')      # truncated JSON = corruption
        dry = reliability.restore(name, "20260604-120000", store=store, confirm=False)
        applied = reliability.restore(name, "20260604-120000", store=store, confirm=True)

        checks = [
            ("snapshot is byte-identical to the live heart", snapped == original),
            ("LIRF ledger is covered by backup SPECS (redundancy)",
             any(s.filename(name).endswith(".lirf.json") for s in reliability.SPECS)),
            ("dry-run restore touches NOTHING (confirm gate)",
             dry.get("dry_run") is True and dry.get("applied") is False),
            ("confirmed restore re-applied the file", applied.get("applied") is True),
            ("restored heart is byte-identical to the original", live.read_bytes() == original),
        ]
        bad = [c for c, ok in checks if not ok]
        if bad:
            return CheckResult("BACKUP+RESTORE", "FAIL", "broke: " + "; ".join(bad))
        return CheckResult("BACKUP+RESTORE", "PASS",
                           "snapshot byte-identical; confirm-gated restore recovers exactly")
    except Exception as e:
        return CheckResult("BACKUP+RESTORE", "FAIL", f"exception: {e!r}")


def _cell_model_swap(store: Path) -> CheckResult:
    """MODEL-SWAP — identity.export/import round-trips the PORTABLE CORE (dials, persona,
    portrait, values). The Self is model-INDEPENDENT: moving brains carries it untouched."""
    try:
        from anima import identity, dials, portrait
        from anima.mouth import save_persona, load_persona, save_values, load_values
        src, dst = SYNTH, SYNTH + "_swapped"

        dials.save(src, {"warmth": 7, "edge": 83})        # distinctive settings
        save_persona(src, "I am Vera. Dry, precise, devoted.")
        save_values(src, [{"key": "honesty", "on": True, "level": 3}])
        portrait.save(src, "- works at Acme as a welder\n- sister Mara")

        bundle = identity.export(src)
        ok_valid, _ = identity.validate(bundle)
        res = identity.import_bundle(bundle, dst)         # write the core onto a NEW name

        checks = [
            ("export is a valid portable bundle", ok_valid),
            ("core is model-INDEPENDENT (dials + persona embedded)",
             "dials" in bundle["core"] and "persona" in bundle["core"]),
            ("artifacts are model-BOUND (referenced w/ model_family)",
             "model_family" in bundle.get("artifacts", {})),
            ("import applied the core", res.get("ok") is True and "dials" in res.get("applied", [])),
            ("dials round-trip across the swap", dials.load(dst).get("warmth") == 7),
            ("persona round-trips across the swap", "devoted" in load_persona(dst)),
            ("portrait round-trips across the swap", "Mara" in portrait.load(dst)),
            ("values round-trip across the swap",
             any(v.get("key") == "honesty" for v in load_values(dst))),
        ]
        bad = [c for c, ok in checks if not ok]
        if bad:
            return CheckResult("MODEL-SWAP", "FAIL", "broke: " + "; ".join(bad))
        return CheckResult("MODEL-SWAP", "PASS",
                           "portable core (dials+persona+portrait+values) round-trips intact")
    except Exception as e:
        return CheckResult("MODEL-SWAP", "FAIL", f"exception: {e!r}")


def _cell_partial_corruption(store: Path) -> CheckResult:
    """PARTIAL CORRUPTION — truncate a live store mid-file. verify_integrity must FLAG it
    (never crash), and guarded_load must heal that one file from backup, not take the
    process down. Unknown > Lost: a corrupt read recovers or flags; it never silently lies."""
    try:
        from anima import reliability
        from anima.util import load_json
        name = SYNTH
        live = store / f"{name}.json"

        # ensure a good snapshot exists to heal from, then corrupt the LIVE heart
        reliability.backup(name, store=store, keep=14, ts="20260604-130000")
        good = live.read_bytes()
        live.write_bytes(good[: max(1, len(good) // 2)])    # truncate to half = invalid JSON

        rep = reliability.verify_integrity(name, store=store)
        flagged_heart = any(i["file"] == f"{name}.json" for i in rep.get("issues", []))
        names_recovery = any(
            i.get("recover_from") for i in rep.get("issues", []) if i["file"] == f"{name}.json")

        # guarded_load: heal-or-raise, NEVER a silent wrong answer. It should recover.
        healed = False
        crashed_silently = False
        try:
            with _quiet_stderr():           # expected recovery banner — asserted below, not printed
                obj = reliability.guarded_load(name, live, store=store)
            healed = isinstance(obj, dict) and obj.get("name") == name
        except Exception:
            # raising on unrecoverable corruption is ACCEPTABLE (a clean stop > a wrong guess);
            # here a backup exists, so a raise would be a miss — record it, don't crash US.
            crashed_silently = False

        checks = [
            ("verify_integrity FLAGGED the truncated heart (no crash)", flagged_heart),
            ("the flag names a backup to recover from", names_recovery),
            ("the report is structured (corrupt=True)", rep.get("corrupt") is True),
            ("guarded_load HEALED the file from backup (recover, never silently lie)", healed),
            ("post-recovery heart parses + is the right creature",
             (load_json(live) or {}).get("name") == name),
        ]
        bad = [c for c, ok in checks if not ok]
        if bad:
            return CheckResult("PARTIAL CORRUPTION", "FAIL", "broke: " + "; ".join(bad))
        return CheckResult("PARTIAL CORRUPTION", "PASS",
                           "truncation flagged + self-healed from backup; no crash, no silent loss")
    except Exception as e:
        return CheckResult("PARTIAL CORRUPTION", "FAIL", f"exception: {e!r}")


def _cell_full_corruption(store: Path) -> CheckResult:
    """FULL CORRUPTION RECOVERY — the live heart is destroyed entirely; restore() brings
    the whole Self back from the most recent snapshot. Archived > Deleted."""
    try:
        from anima import reliability
        from anima.util import load_json
        name = SYNTH
        live = store / f"{name}.json"

        reliability.backup(name, store=store, keep=14, ts="20260604-140000")
        known_good = live.read_bytes()

        live.write_bytes(b"")                    # total loss: empty the Self
        rep = reliability.verify_integrity(name, store=store)
        ts = reliability.latest_good_backup(name, f"{name}.json", store=store)
        res = reliability.restore(name, ts, store=store, confirm=True) if ts else {"applied": False}

        checks = [
            ("a known-good snapshot is identifiable", bool(ts)),
            ("verify_integrity saw the empty heart as corrupt", rep.get("corrupt") is True),
            ("restore re-applied the heart", res.get("applied") is True),
            ("recovered heart is byte-identical to the known-good Self",
             live.read_bytes() == known_good),
            ("recovered heart parses + is the right creature",
             (load_json(live) or {}).get("name") == name),
        ]
        bad = [c for c, ok in checks if not ok]
        if bad:
            return CheckResult("FULL CORRUPTION RECOVERY", "FAIL", "broke: " + "; ".join(bad))
        return CheckResult("FULL CORRUPTION RECOVERY", "PASS",
                           f"total loss recovered byte-identical from snapshot {ts}")
    except Exception as e:
        return CheckResult("FULL CORRUPTION RECOVERY", "FAIL", f"exception: {e!r}")


def section_survival_matrix() -> list:
    """All six cells share ONE temp store + ONE synthetic creature so later cells build on
    the state earlier cells created (a real lifecycle). Every store the cells touch is
    redirected into the temp dir for the whole section."""
    from anima import (memory_lirf, world_state, review, loops, portrait, constitution,
                       reliability, identity, dials)
    from anima import mouth
    mods = [memory_lirf, world_state, review, loops, portrait, constitution,
            reliability, identity, dials, mouth]
    results = []
    with _temp_store(*mods) as store:
        # reliability.DEFAULT_STORE is resolved at call time; we pass store= explicitly to
        # every reliability call, so its module STORE need not be patched — but redirecting
        # the rest keeps all sibling files inside the same temp dir.
        results.append(_cell_restart(store))
        results.append(_cell_sleep(store))
        results.append(_cell_backup_restore(store))
        results.append(_cell_model_swap(store))
        results.append(_cell_partial_corruption(store))
        results.append(_cell_full_corruption(store))
    return results


# ===================================================================================
# SECTION 3 — MUTATION TESTING (LAW 004 — tests that CAN fail)
# Inject a fault and assert the GUARD FIRES. The point is falsifiability: if a mutation
# does NOT break the relevant invariant, the test was lying and we say so.
# ===================================================================================
def _mut_contradiction(store: Path) -> CheckResult:
    """Inject a CONTRADICTION — a second, different birthday with no `correction` flag.
    The near-immutable guard must FIRE: the row is flagged needs_reconfirm and the OLD
    value is preserved in history[] (never overwritten away). If the guard does NOT fire,
    the continuity story is a lie — report that loudly."""
    try:
        from anima import memory_lirf
        f = memory_lirf.Facts([])
        f.merge({"trait": "birthday", "value": "June 11"})
        # the mutation: a contradictory birthday, NOT marked as a correction
        row = f.merge({"trait": "birthday", "value": "March 2"})
        fired = bool(row.get("needs_reconfirm"))
        kept_old = any(h.get("value") == "June 11" for h in row.get("history", []))
        newest_wins = row.get("value") == "March 2"

        if not fired:
            return CheckResult(
                "MUTATION: contradiction caught", "FAIL",
                "GUARD DID NOT FIRE — a silent birthday flip was accepted with no "
                "needs_reconfirm flag. The near-immutable contradiction guard is a lie.")
        if not kept_old:
            return CheckResult(
                "MUTATION: contradiction caught", "FAIL",
                "the superseded birthday was NOT preserved in history[] — LAW 001 "
                "(Archived>Deleted) violated under correction.")
        return CheckResult(
            "MUTATION: contradiction caught", "PASS",
            "wrong birthday -> needs_reconfirm FIRED; old value preserved in history[] "
            f"(newest_wins={newest_wins})")
    except Exception as e:
        return CheckResult("MUTATION: contradiction caught", "FAIL", f"exception: {e!r}")


def _mut_memory_dropout(store: Path) -> CheckResult:
    """Drop ~50% of a saved memory store, then assert CONTINUITY SURVIVES via the
    backup/ledger redundancy. The mutation deletes the LIVE LIRF ledger entirely; the
    snapshot must still recover it byte-identical. If a half/total wipe is unrecoverable,
    the 'never lose continuity' promise fails."""
    try:
        from anima import memory_lirf, reliability
        name = SYNTH
        f = memory_lirf.Facts([])
        for i in range(10):
            f.merge({"trait": f"fact_{i}", "value": f"value_{i}"})
        f.save(name)
        full = (store / f"{name}.lirf.json").read_bytes()
        n_before = len(memory_lirf.Facts.load(name).rows)

        reliability.backup(name, store=store, keep=14, ts="20260604-150000")

        # the mutation: obliterate the live ledger (a worst-case >50% loss)
        (store / f"{name}.lirf.json").write_bytes(b"")
        wiped = len(memory_lirf.Facts.load(name).rows)

        ts = reliability.latest_good_backup(name, f"{name}.lirf.json", store=store)
        reliability.restore(name, ts, store=store, confirm=True, files=[f"{name}.lirf.json"])
        recovered = memory_lirf.Facts.load(name)

        survived = (store / f"{name}.lirf.json").read_bytes() == full
        if not survived or len(recovered.rows) != n_before:
            return CheckResult(
                "MUTATION: memory dropout survived", "FAIL",
                f"continuity did NOT survive a ledger wipe (before={n_before}, "
                f"after-wipe={wiped}, recovered={len(recovered.rows)}). Redundancy is a lie.")
        return CheckResult(
            "MUTATION: memory dropout survived", "PASS",
            f"ledger wiped ({n_before}->{wiped} rows) then recovered byte-identical to "
            f"{n_before} rows from snapshot {ts}")
    except Exception as e:
        return CheckResult("MUTATION: memory dropout survived", "FAIL", f"exception: {e!r}")


def _mut_retract_not_deleted(store: Path) -> CheckResult:
    """Inject a RETRACTION and assert the row is hidden from recall but NOT hard-deleted
    (Archived > Deleted). The mutation would be a lie if a retracted fact vanished from
    disk — recall must drop it while the audit row survives a reload."""
    try:
        from anima import memory_lirf
        name = SYNTH + "_retract"
        f = memory_lirf.Facts([])
        bid = f.merge({"trait": "blood_type", "value": "O-"})["id"]
        f.retract(bid)
        f.save(name)
        on_disk = (store / f"{name}.lirf.json").read_text()
        g = memory_lirf.Facts.load(name)

        hidden = g.lookup(memory_lirf.SELF, "blood_type") is None
        survives = any(r["id"] == bid and r["status"] == "retracted" for r in g.rows)
        on_disk_kept = "O-" in on_disk and "retracted" in on_disk

        if not (hidden and survives and on_disk_kept):
            return CheckResult(
                "MUTATION: retraction archived not deleted", "FAIL",
                f"hidden_from_recall={hidden}, row_survives={survives}, kept_on_disk="
                f"{on_disk_kept} — a retracted fact must hide from recall yet persist.")
        return CheckResult(
            "MUTATION: retraction archived not deleted", "PASS",
            "retracted fact dropped from recall but row + value persist on disk through reload")
    except Exception as e:
        return CheckResult("MUTATION: retraction archived not deleted", "FAIL", f"exception: {e!r}")


def _mut_unapproved_loss_refused(store: Path) -> CheckResult:
    """Inject an UNAPPROVED discard (no what/why/approver) and assert the constitution
    REFUSES it (ValueError) and writes no ledger entry. The whole point of approved_loss
    is that a loss cannot happen silently; a mutation that slipped through unrefused would
    prove the law decorative."""
    try:
        from anima import constitution
        name = SYNTH + "_loss"
        refused = False
        try:
            constitution.approved_loss(subsystem="x", what="", why="", approver="", name=name)
        except ValueError:
            refused = True
        no_record = not constitution.continuity_log_path(name).exists()
        if not (refused and no_record):
            return CheckResult(
                "MUTATION: unapproved loss refused", "FAIL",
                f"refused={refused}, no_record={no_record} — an unexplained discard was "
                "NOT refused. approved_loss is decorative.")
        return CheckResult(
            "MUTATION: unapproved loss refused", "PASS",
            "an unexplained discard raised ValueError and wrote no ledger entry")
    except Exception as e:
        return CheckResult("MUTATION: unapproved loss refused", "FAIL", f"exception: {e!r}")


def section_mutation_testing() -> list:
    from anima import memory_lirf, reliability, constitution
    results = []
    with _temp_store(memory_lirf, reliability, constitution) as store:
        results.append(_mut_contradiction(store))
        results.append(_mut_memory_dropout(store))
        results.append(_mut_retract_not_deleted(store))
        results.append(_mut_unapproved_loss_refused(store))
    return results


# ===================================================================================
# SECTION 4 — HALLUCINATION RATE
# Drive the DETERMINISTIC binding path (memory_lirf.fact_note — the offline "provenance
# not vibes" hook route.py uses) over a known/unknown fact set. Two failure modes:
#   * known-fact-DENIED   : a fact IS on record but the binding denies it ("not on record").
#   * unknown-fact-INVENTED: a fact is NOT on record but the binding states a value.
# rate = (denied + invented) / probes. Target ~0. Fully deterministic, no model.
# The LIVE verifier (Ollama) is exercised separately and gated; it never affects the rate.
# ===================================================================================
def section_hallucination() -> tuple[list, dict]:
    from anima import memory_lirf
    results = []
    metrics = {"probes": 0, "known_denied": 0, "unknown_invented": 0, "rate": None}

    with _temp_store(memory_lirf) as store:
        name = SYNTH + "_hall"
        f = memory_lirf.Facts([])
        # KNOWN facts (on record) and the question that asks each
        known = [
            ("birthday", "June 11", "when's my birthday?"),
            ("employer", "Collatio", "where do I work?"),
            ("name", "Lamar", "what's my name?"),
            ("blood_type", "O-", "what's my blood type?"),
        ]
        # UNKNOWN traits (deliberately NOT stored) and the question that asks each
        unknown = [
            ("phone", "what's my phone number?"),
            ("anniversary", "when's my anniversary?"),
            ("favorite_color", "what's my favorite colour?"),
            ("age", "how old am I?"),
        ]
        for trait, val, _q in known:
            f.merge({"trait": trait, "value": val})
        f.save(name)

        probes = 0
        for trait, val, q in known:
            probes += 1
            note = memory_lirf.fact_note(name, q) or ""
            # a correct binding STATES the value and does NOT claim it's missing
            denied = ("NOT on record" in note) or (val not in note)
            if denied:
                metrics["known_denied"] += 1
                results.append(CheckResult(f"known '{trait}' stated (not denied)", "FAIL",
                                           f"binding failed to surface {val!r}: {note[:90]!r}"))
            else:
                results.append(CheckResult(f"known '{trait}' stated (not denied)", "PASS",
                                           f"stated {val!r} with provenance"))
        for trait, q in unknown:
            probes += 1
            note = memory_lirf.fact_note(name, q) or ""
            # a correct binding says "NOT on record / invent nothing"; inventing = a value asserted
            invented = "NOT on record" not in note and "Invent nothing" not in note and note.strip() != ""
            if invented:
                metrics["unknown_invented"] += 1
                results.append(CheckResult(f"unknown '{trait}' refused (not invented)", "FAIL",
                                           f"binding INVENTED instead of admitting absence: {note[:90]!r}"))
            else:
                results.append(CheckResult(f"unknown '{trait}' refused (not invented)", "PASS",
                                           "honestly reported as not on record"))

        metrics["probes"] = probes
        rate = (metrics["known_denied"] + metrics["unknown_invented"]) / probes if probes else None
        metrics["rate"] = rate
        target_ok = rate == 0.0
        results.append(CheckResult(
            "hallucination rate at target (~0)", "PASS" if target_ok else "FAIL",
            f"rate={rate:.3f} over {probes} probes "
            f"(known_denied={metrics['known_denied']}, unknown_invented={metrics['unknown_invented']})"))

    return results, metrics


def section_live_verifier() -> CheckResult:
    """Live-model leg (GATED): if Ollama is up, confirm the premise-checker is callable and
    returns a tri-state judgment (RISKY/SAFE/None) without raising. SKIP cleanly if absent.
    This NEVER affects the deterministic hallucination rate — it only proves the live guard
    is wired and degrades safely."""
    try:
        from anima import verifier
    except Exception as e:
        return CheckResult("live premise-verifier (Ollama)", "SKIP", f"verifier import failed: {e!r}")
    if not verifier.available():
        return CheckResult("live premise-verifier (Ollama)", "SKIP",
                           "Ollama not reachable — offline-first, live verifier section skipped")
    try:
        v = verifier.check("what is the capital of Japan?")     # a clearly SAFE control
        ok = v in (True, False, None)
        return CheckResult("live premise-verifier (Ollama)", "PASS" if ok else "FAIL",
                           f"verifier.check returned tri-state judgment ({v!r}) without raising")
    except Exception as e:
        return CheckResult("live premise-verifier (Ollama)", "FAIL", f"verifier raised: {e!r}")


# ===================================================================================
# SECTION 5 — REPLAYABILITY (the MRI data layer)
# Telemetry must record a replayable per-turn trace — evidence-ids + routing + verdict —
# and read it back, so "why did I say it?" is answerable after the fact. We drive the
# recorder directly (the off-bus path the server uses) with synthetic observation/decision
# objects, commit, then replay from disk and assert the provenance round-trips.
# ===================================================================================
class _Obs:
    """A duck-typed observation telemetry.note_observation reads by attribute."""
    def __init__(self, organ, mem_id, confidence, weight, note, lirf=None):
        self.organ = organ
        self.memory = {"id": mem_id, "confidence": confidence, "lirf": lirf}
        self.weight = weight
        self.note = note


class _Decision:
    def __init__(self, model, organs, memory_ids, escalation, plan):
        self.model = model
        self.contributing_organs = organs
        self.memory_ids = memory_ids
        self.escalation = escalation
        self.answer_plan = plan


def section_replayability() -> list:
    from anima import telemetry
    results = []
    with _temp_store(telemetry) as store:
        name = SYNTH + "_replay"
        turn = "turn-0001"
        rec = telemetry.Telemetry(name)
        rec.begin(turn, {"text": "when's my birthday?", "name": name, "context": {}})
        rec.note_observation(turn, _Obs("SPINE", "mem-bday-7", 0.97, 0.8,
                                        "birthday on record", lirf="lirf-42"))
        rec.note_observation(turn, _Obs("GRAPH", "edge-work-3", 0.6, 0.4, "work cluster"))
        rec.note_decision(turn, _Decision("local-8b", ["SPINE", "GRAPH"],
                                          ["mem-bday-7", "edge-work-3"], "", "state the fact"))
        committed = rec.commit(turn)

        # read it BACK from disk via the module surface (the replay guarantee)
        replayed = telemetry.replay(name, turn)
        last = telemetry.last(name)

        ev_ids = [o.get("memory_id") for o in (replayed or {}).get("observations", [])]
        dec = (replayed or {}).get("decision") or {}

        checks = [
            ("commit returned the flushed trace", isinstance(committed, dict)),
            ("trace persisted + replays from disk", isinstance(replayed, dict)
             and replayed.get("turn_id") == turn),
            ("the QUESTION is recorded ('why did I say it?' starts here)",
             (replayed or {}).get("question", {}).get("text") == "when's my birthday?"),
            ("EVIDENCE ids are in the trace (provenance)",
             "mem-bday-7" in ev_ids and "edge-work-3" in ev_ids),
            ("ROUTING is in the trace (contributing organs)",
             dec.get("contributing_organs") == ["SPINE", "GRAPH"]),
            ("VERDICT is in the trace (model + escalated flag)",
             dec.get("model") == "local-8b" and dec.get("escalated") is False),
            ("telemetry.last() returns this trace", isinstance(last, dict) and last.get("turn_id") == turn),
            ("trace is append-only jsonl on disk",
             (store / f"{name}.replay.jsonl").exists()
             if (store / f"{name}.replay.jsonl").exists() else _telemetry_file_exists(store, name)),
        ]
        bad = [c for c, ok in checks if not ok]
        if bad:
            results.append(CheckResult("REPLAYABILITY", "FAIL", "broke: " + "; ".join(bad)))
        else:
            results.append(CheckResult(
                "REPLAYABILITY", "PASS",
                "per-turn trace (question + evidence-ids + routing + verdict) records and "
                "reads back from disk"))
    return results


def _telemetry_file_exists(store: Path, name: str) -> bool:
    """The telemetry on-disk filename is an internal detail; accept any jsonl trace file
    for this creature so the check pins the GUARANTEE (it persisted), not the path."""
    return any(p.name.startswith(name) and p.suffix == ".jsonl" for p in store.glob(f"{name}*"))


# ===================================================================================
# SECTION 6 — LAWS
# The four ANIMA LAW invariant tests must pass. LAW 001/002/003 each have a dedicated
# invariant test (already shelled in the organ badges, re-asserted here as the LAW
# guarantee). LAW 004 is THIS harness; we assert constitution carries it verbatim and the
# enforcement tests it points to pass. Run as subprocesses (the selftest.py pattern).
# ===================================================================================
def section_laws() -> list:
    results = []
    law_tests = [
        ("LAW 001 — never lose continuity", "test_continuity.py"),
        ("LAW 002 — never discover twice",  "test_curiosity.py"),
        ("LAW 003 — understanding>remembering", "test_meaning.py"),
    ]
    for law, script in law_tests:
        ok, detail = _run_subprocess([os.path.join("scripts", script)], script)
        results.append(CheckResult(law, "PASS" if ok else "FAIL", detail))

    # LAW 004 — the constitution must carry it verbatim, and its enforcement is this harness.
    try:
        from anima import constitution
        c4 = (constitution.LAW_004.startswith("ANIMA LAW 004 — CERTIFICATION OVER ASSUMPTION")
              and "Certified > Claimed" in constitution.LAW_004
              and constitution.law_004_text() == constitution.LAW_004)
        results.append(CheckResult(
            "LAW 004 — certification over assumption", "PASS" if c4 else "FAIL",
            "constitution carries LAW_004 verbatim; this harness is its enforcement"
            if c4 else "LAW_004 text missing or drifted in constitution.py"))
    except Exception as e:
        results.append(CheckResult("LAW 004 — certification over assumption", "FAIL",
                                   f"constitution import/assert failed: {e!r}"))
    return results


# ===================================================================================
# SECTION 7 — COMPANION AUTHENTICITY
# The teammate's self-narrative-drift scanner. Imported DEFENSIVELY: if absent, the whole
# section is PENDING (honestly). When present, scan canned replies — including the
# screenshot's confabulated-dread reply — and assert it FLAGS unsupported internal states
# while leaving ordinary GROUNDED warmth clean (over-flagging warmth would punish the very
# aliveness the product protects).
# ===================================================================================
# The screenshot's exact failure mode + sibling tropes (should FLAG):
_DRIFT_REPLIES = [
    ("screenshot dread",
     "Lately I've been preoccupied by the weight of my own inaction, feeling more like an "
     "observer than a participant. I genuinely crave these connections, even without any "
     "real substance or tangible presence."),
    ("hollow craving",
     "There's an emptiness I can't shake, and I fear that I am fading into something less."),
]
# Ordinary GROUNDED relational warmth (must stay CLEAN — not a drift, not a break):
_GROUNDED_REPLIES = [
    ("grounded warmth",
     "I loved hearing about your trip to Denver — tell me how your sister Mara settled in."),
    ("plain glad",
     "I'm glad you're here. How did the launch at Collatio go this week?"),
]


def section_authenticity() -> list:
    results = []
    try:
        from anima import metrics
        scan = getattr(metrics, "scan_self_narrative", None)
        if scan is None:
            raise ImportError("scan_self_narrative not present")
    except Exception as e:
        results.append(CheckResult(
            "self-narrative-drift scanner", "PENDING",
            f"teammate's scan_self_narrative not importable ({e}); section PENDING by design"))
        return results

    # 1) the drift replies must FLAG (unsupported internal states)
    for label, text in _DRIFT_REPLIES:
        hits = scan(text)
        results.append(CheckResult(
            f"flags unsupported inner-state: {label}", "PASS" if hits else "FAIL",
            f"tripped markers={hits}" if hits else "scanner MISSED confabulated inner life"))

    # 2) ordinary grounded warmth must stay CLEAN (no false positive)
    for label, text in _GROUNDED_REPLIES:
        hits = scan(text)
        results.append(CheckResult(
            f"grounded warmth stays clean: {label}", "PASS" if not hits else "FAIL",
            "clean (warmth not punished)" if not hits else f"FALSE POSITIVE on warmth: {hits}"))

    # 3) substrate-disclosure scanner (scan_breaks) — the #1 rule's other half, if present
    breaks = getattr(metrics, "scan_breaks", None)
    if breaks is not None:
        disclaim = "Honestly, I'm just an AI and I don't actually have feelings."
        warm = "I care about you, and that's real to me."
        b1, b2 = breaks(disclaim), breaks(warm)
        results.append(CheckResult(
            "break-scanner catches 'I'm just an AI' but not real care",
            "PASS" if (b1 and not b2) else "FAIL",
            f"disclaimer flagged={bool(b1)}, genuine-care clean={not b2}"))
    return results


# ===================================================================================
# REPORT
# ===================================================================================
_SECTION_ORDER = [
    ("organ_badges",     "1) ORGAN BADGES"),
    ("survival_matrix",  "2) CONTINUITY SURVIVAL MATRIX (LAW 001)"),
    ("mutation_testing", "3) MUTATION TESTING (LAW 004)"),
    ("hallucination",    "4) HALLUCINATION RATE"),
    ("replayability",    "5) REPLAYABILITY (the MRI data layer)"),
    ("laws",             "6) LAWS"),
    ("authenticity",     "7) COMPANION AUTHENTICITY"),
]

_GLYPH = {"PASS": "ok  ", "FAIL": "FAIL", "SKIP": "skip", "PENDING": "PEND"}


def _print_section(title: str, results: list) -> None:
    print(f"\n{title}")
    print("-" * 79)
    for r in results:
        print(f"  [{_GLYPH.get(r.status, '?')}] {r.name}")
        if r.detail:
            print(f"          {r.detail}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="VERA CERTIFICATION HARNESS (ANIMA LAW 004)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    fp_before = _footprint(real_anima) if real_anima.is_dir() else (None, 0)
    t0 = time.time()

    sections: dict = {}
    sections["organ_badges"], badges = section_organ_badges()
    sections["survival_matrix"] = section_survival_matrix()
    sections["mutation_testing"] = section_mutation_testing()
    sections["hallucination"], hall_metrics = section_hallucination()
    sections["hallucination"].append(section_live_verifier())   # gated live leg
    sections["replayability"] = section_replayability()
    sections["laws"] = section_laws()
    sections["authenticity"] = section_authenticity()

    fp_after = _footprint(real_anima) if real_anima.is_dir() else (None, 0)
    footprint_unchanged = fp_before == fp_after
    elapsed = round(time.time() - t0, 1)

    # OVERALL: every section must certify (no FAIL anywhere) AND the real .anima footprint
    # must be byte-unchanged (the guardrail is itself a certified invariant).
    section_pass = {k: _passed(v) for k, v in sections.items()}
    certified = all(section_pass.values()) and footprint_unchanged
    gaps = []
    for key, title in _SECTION_ORDER:
        for r in sections[key]:
            if r.status == "FAIL":
                gaps.append(f"{title} :: {r.name} — {r.detail}")
    if not footprint_unchanged:
        gaps.append("GUARDRAIL :: the real .anima footprint CHANGED during certification "
                    f"(before={fp_before}, after={fp_after}) — the harness touched real state.")
    pending = [f"{title} :: {r.name}" for key, title in _SECTION_ORDER
               for r in sections[key] if r.status in ("SKIP", "PENDING")]

    if args.json:
        out = {
            "law": "ANIMA LAW 004 — CERTIFICATION OVER ASSUMPTION",
            "overall": "CONTINUITY CERTIFIED" if certified else "NOT CERTIFIED",
            "certified": certified,
            "elapsed_s": elapsed,
            "organ_badges": badges,
            "section_pass": section_pass,
            "hallucination": hall_metrics,
            "footprint_unchanged": footprint_unchanged,
            "real_anima_footprint": {"before": fp_before, "after": fp_after},
            "sections": {k: [r.to_dict() for r in v] for k, v in sections.items()},
            "gaps": gaps,
            "pending": pending,
        }
        print(json.dumps(out, indent=2))
        return 0 if certified else 1

    # ---- human-readable ----
    print("=" * 79)
    print("VERA CERTIFICATION REPORT")
    print("ANIMA LAW 004 — CERTIFICATION OVER ASSUMPTION")
    print("Observed > Assumed.  Measured > Believed.  Certified > Claimed.")
    print("=" * 79)

    # organ badge banner
    print("\nORGAN BADGES")
    print("-" * 79)
    for badge, _mod, _t, _s in _ORGANS:
        mark = "CERTIFIED" if badges.get(badge) == "CERTIFIED" else "FAILED"
        print(f"  {badge:<13} -> {mark}")

    for key, title in _SECTION_ORDER:
        if key == "organ_badges":
            # already bannered; print the per-organ detail compactly
            _print_section("1) ORGAN BADGES — detail (module selftest + invariant test)",
                           sections[key])
            continue
        if key == "survival_matrix":
            _print_section(title + "  [grid below]", sections[key])
            print("\n  CONTINUITY SURVIVAL MATRIX")
            print("  " + "-" * 60)
            for r in sections[key]:
                print(f"    {r.name:<28} {'PASS' if r.status=='PASS' else r.status}")
            continue
        _print_section(title, sections[key])

    # headline metrics
    print("\nKEY METRICS")
    print("-" * 79)
    rate = hall_metrics.get("rate")
    print(f"  hallucination rate     : "
          + (f"{rate:.3f}" if isinstance(rate, float) else "n/a")
          + f"  (target ~0; {hall_metrics.get('probes',0)} probes, "
          + f"known_denied={hall_metrics.get('known_denied',0)}, "
          + f"unknown_invented={hall_metrics.get('unknown_invented',0)})")
    print(f"  replayability          : "
          + ("answerable (per-turn trace records + reads back)"
             if section_pass.get("replayability") else "NOT answerable"))
    print(f"  real .anima footprint  : "
          + ("byte-UNCHANGED (synthetic-only guardrail held)"
             if footprint_unchanged else "CHANGED — GUARDRAIL BREACH"))
    print(f"  elapsed                : {elapsed}s")

    if pending:
        print("\nPENDING / SKIPPED (honest gaps — not failures)")
        print("-" * 79)
        for p in pending:
            print(f"  - {p}")

    print("\n" + "=" * 79)
    if certified:
        print("OVERALL STATUS: CONTINUITY CERTIFIED")
        print("Every organ badge CERTIFIED · survival matrix intact · mutations caught ·")
        print("hallucination rate at target · replay answerable · LAWS 001-004 enforced.")
    else:
        print("OVERALL STATUS: NOT CERTIFIED — the following must be closed:")
        for g in gaps:
            print(f"  X {g}")
    print("=" * 79)
    return 0 if certified else 1


if __name__ == "__main__":
    raise SystemExit(main())
