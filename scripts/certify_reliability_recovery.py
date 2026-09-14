#!/usr/bin/env python3
"""
certify_reliability_recovery — the life-insurance layer: a corrupted store is RECOVERED from a
backup, with the loss accounted for. Proven through the SAME reliability functions the live load
paths call (and through memory_lirf.Facts.load itself — the function a real turn runs).

Everything that IS the creature lives in .anima/ — her heart, the LIRF fact ledger (her strongest
memory), the world relations, the Portrait. Reliability is the safety net. This certifies that
contract end-to-end, hermetically + OFFLINE (no Ollama, no network):

  A. ATOMIC BACKUP — backup() snapshots the critical files into .anima/backups/<ts>/, copying RAW
     bytes (byte-identical to live, so at-rest encryption survives) plus a self-describing manifest.
  B. DETECT + RESTORE (3 real corruptions) — a truncated heart, NaN smuggled into the heart's
     feeling-vector, and an emptied-out Portrait are EACH flagged by verify_integrity (which names
     the most-recent good backup); health_check goes CRITICAL on the truncated heart; restore is
     confirm-gated (a dry run touches nothing) and a confirmed restore recovers the EXACT good bytes;
     guarded_load returns a finite heart after self-heal.
  C. THE LIVE PATH — corrupt the REAL LIRF ledger on disk, then call the PRODUCTION
     memory_lirf.Facts.load(name) (the SAME function a live turn calls): it self-heals (recovers the
     captured fact rows from backup) instead of silently returning 0 rows. A SECOND corruption with
     NO backup makes Facts.load stop CLEANLY (flagged-empty, 0 rows) AND record a
     constitution.approved_loss in the continuity ledger — the loss is accounted, never silent.
  D. ROTATION IS ACCOUNTED — backup(keep=N) prunes the oldest snapshots AND records an
     approved_loss (subsystem reliability._rotate) naming exactly which ids were pruned (LAW 001:
     Archived > Deleted; a sanctioned, bounded discard is never silent).
  E. SELFTEST — python3 -m anima.reliability --selftest passes the full corrupt->detect->restore
     cycle end to end.

Hermetic: memory_lirf/world_state stores are redirected by _temp_store; reliability.DEFAULT_STORE
and constitution.STORE (the continuity ledger) are redirected here too. The real .anima is
fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import reliability, memory_lirf, constitution
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("RELIABILITY RECOVERY — corrupt store recovered from backup, with the loss accounted for")
    print("=" * 88)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        # Redirect the two stores _temp_store doesn't cover so backups + the continuity ledger
        # (constitution.approved_loss) resolve against the temp dir, never the real .anima.
        saved_rel = getattr(reliability, "DEFAULT_STORE", None)
        saved_con = getattr(constitution, "STORE", None)
        reliability.DEFAULT_STORE = tp
        constitution.STORE = tp
        try:
            store = tp
            name = "RelCert"

            # A deterministic, advancing clock so successive backups get distinct ids/mtimes.
            base = [1_780_000_000.0]

            def clk():
                base[0] += 1.0
                return base[0]

            # ---- A realistic, mutually-consistent creature on disk (the real shapes) ----------
            try:
                from anima.heart import Heart
                heart = Heart.born(name, seed=42, now=base[0])
                heart_dict = heart.to_dict()
            except Exception:
                heart_dict = {"name": name, "seed": 42, "n": 4, "birth_ts": base[0],
                              "last_tick": base[0], "unrest": 0.1, "learned": False,
                              "h": [0.01, -0.02, 0.03, 0.0]}
            (store / f"{name}.json").write_text(json.dumps(heart_dict))
            (store / f"{name}.portrait.md").write_text("RelCert:\n- founder, hates being coddled\n")
            good_heart_bytes = (store / f"{name}.json").read_bytes()
            good_portrait = (store / f"{name}.portrait.md").read_text()

            # ---- A. ATOMIC BACKUP (raw bytes + manifest) --------------------------------------
            b1 = reliability.backup(name, store=store, clock=clk)
            snap_dir = store / "backups" / b1["stamp"]
            ck("A1: backup() created an atomic timestamped snapshot dir", b1["ok"] and snap_dir.is_dir())
            ck("A2: the snapshot copied the heart + portrait",
               f"{name}.json" in b1["files"] and f"{name}.portrait.md" in b1["files"])
            ck("A3: the snapshot heart is byte-identical to live (raw-byte copy; encryption survives)",
               (snap_dir / f"{name}.json").read_bytes() == good_heart_bytes)
            ck("A4: the snapshot is self-describing (a _manifest.json names the creature)",
               (snap_dir / "_manifest.json").is_file()
               and json.loads((snap_dir / "_manifest.json").read_text()).get("name") == name)

            # ---- B. DETECT + RESTORE — three real corruptions ---------------------------------
            # B-1: truncated / invalid JSON in the heart (the unrecoverable file).
            (store / f"{name}.json").write_text('{"name": "RelCert", "seed": 42, "h": [0.1, 0.2,')
            v1 = reliability.verify_integrity(name, store=store)
            heart_issue = next((i for i in v1["issues"] if i["file"] == f"{name}.json"), None)
            ck("B1: a truncated heart is flagged corrupt by verify_integrity",
               v1["corrupt"] and heart_issue is not None)
            ck("B2: verify_integrity names the most-recent good backup to recover from",
               bool(heart_issue) and heart_issue["recover_from"] == b1["stamp"])
            ck("B3: health_check goes CRITICAL on the truncated heart",
               reliability.health_check(name, store=store, clock=base[0])["status"] == "critical")

            # restore is confirm-gated: a dry run must NOT touch the live (corrupt) file.
            dry = reliability.restore(name, b1["stamp"], store=store, confirm=False)
            ck("B4: restore WITHOUT confirm is a dry run that applies nothing",
               dry["applied"] is False and dry.get("dry_run") is True
               and b'[0.1, 0.2,' in (store / f"{name}.json").read_bytes())
            r1 = reliability.restore(name, b1["stamp"], store=store, confirm=True, clock=clk)
            ck("B5: a confirmed restore recovers the EXACT good heart bytes",
               r1["applied"] is True and (store / f"{name}.json").read_bytes() == good_heart_bytes)

            # B-2: NaN smuggled into the heart's feeling-vector (json.dumps emits NaN by default).
            hd = json.loads((store / f"{name}.json").read_text())
            if isinstance(hd.get("h"), list) and hd["h"]:
                hd["h"][0] = float("nan")
            else:
                hd["h"] = [float("nan")]
            (store / f"{name}.json").write_text(json.dumps(hd))
            v2 = reliability.verify_integrity(name, store=store)
            nan_issue = next((i for i in v2["issues"] if i["file"] == f"{name}.json"), None)
            ck("B6: NaN in the heart's vector is detected as non-finite corruption",
               bool(nan_issue) and "non-finite" in nan_issue["why"])
            healed = reliability.guarded_load(name, store / f"{name}.json", store=store)
            ck("B7: guarded_load self-heals and returns a FINITE heart",
               reliability._finite_scan(healed) is None and healed.get("seed") == 42)

            # B-3: an expected text file (the Portrait) emptied to whitespace.
            (store / f"{name}.portrait.md").write_text("   \n")
            v3 = reliability.verify_integrity(name, store=store)
            port_issue = next((i for i in v3["issues"] if i["file"] == f"{name}.portrait.md"), None)
            ck("B8: an empty-but-expected Portrait is flagged + names a recovery backup",
               bool(port_issue) and port_issue["recover_from"] is not None)
            r3 = reliability.restore(name, port_issue["recover_from"], store=store, confirm=True,
                                     files=[f"{name}.portrait.md"], clock=clk)
            ck("B9: the Portrait is restored byte-for-byte from backup",
               r3["applied"] and (store / f"{name}.portrait.md").read_text() == good_portrait)

            # ---- C. THE LIVE PATH — corrupt the REAL LIRF ledger, load via PRODUCTION code -----
            # memory_lirf.STORE is redirected by _temp_store; assert it before driving the live path.
            ck("C0: memory_lirf store is the redirected temp store (no real-.anima reads/writes)",
               memory_lirf.STORE == tp)
            # Use a DISTINCT creature for the live-LIRF path (so this section's backups are its own).
            lname = "RelCertLive"
            f = memory_lirf.Facts([])
            f.merge({"trait": "dog", "value": "Zephyrqx"})   # a durable user fact
            f.save(lname)
            led = memory_lirf.Facts.path(lname)
            # A clean load through the live path returns the captured fact and is not flagged.
            clean = memory_lirf.Facts.load(lname)
            ck("C1: a clean LIRF ledger loads the captured fact and is NOT flagged",
               any(r.get("value") == "Zephyrqx" for r in clean.rows)
               and getattr(clean, "_load_flagged_empty", False) is False)
            # Capture the good ledger as a backup — the recovery source the live.py periodic daemon
            # maintains via maybe_backup_store. (We snapshot explicitly so the cadence-throttle in
            # maybe_backup_store, which keys off the newest snapshot across the whole store, can't
            # skip it under this cert's earlier backups — the recovery SOURCE is what section C proves.)
            reliability.backup(lname, store=store, clock=clk)
            ck("C2: a good backup of the LIRF ledger exists as the recovery source",
               reliability.latest_good_backup(lname, led.name, store=tp) is not None)
            # Now CORRUPT the live ledger and load it through the SAME production function.
            led.write_text('{ truncated json, "rows": [')
            healed_facts = memory_lirf.Facts.load(lname)
            ck("C3: LIVE PATH — a corrupt LIRF ledger self-heals on memory_lirf.Facts.load "
               "(recovers the fact rows from backup, NOT a silent 0-row store)",
               any(r.get("value") == "Zephyrqx" for r in healed_facts.rows)
               and getattr(healed_facts, "_load_flagged_empty", False) is False)

            # C-2: a corrupt ledger with NO good backup -> flagged-empty + recorded approved_loss.
            name2 = "RelCertNB"
            (store / f"{name2}.lirf.json").write_text("null")   # valid JSON, wrong shape: total-loss case
            stopped = memory_lirf.Facts.load(name2)
            ck("C4: with NO backup, the live load stops CLEANLY (flagged-empty, 0 rows) — "
               "never a silently-wrong store",
               stopped.rows == [] and getattr(stopped, "_load_flagged_empty", False) is True)
            losses2 = constitution.approved_losses(name2)
            ck("C5: the unrecoverable loss is RECORDED in the continuity ledger (accounted, not silent)",
               any("reliability.guarded_store_load" in (L.get("subsystem") or "") for L in losses2))

            # ---- D. ROTATION IS ACCOUNTED -----------------------------------------------------
            name3 = "RelCertRot"
            (store / f"{name3}.json").write_text(json.dumps({"name": name3, "seed": 7, "h": [0.1, 0.2]}))
            last = None
            for _ in range(5):
                last = reliability.backup(name3, store=store, keep=2, clock=clk)
            ck("D1: rotation keeps only the newest N snapshots (bounded backups dir)",
               len(reliability._existing_snapshots(store)) == 2)
            ck("D2: rotation actually pruned the oldest snapshot(s)", bool(last and last["pruned"]))
            rot_losses = [L for L in constitution.approved_losses(name3)
                          if "reliability._rotate" in (L.get("subsystem") or "")]
            ck("D3: each prune records an approved_loss naming the pruned ids (LAW 001: Archived > Deleted)",
               len(rot_losses) >= 1 and "keep=2" in rot_losses[0].get("what", ""))
        finally:
            if saved_rel is not None:
                reliability.DEFAULT_STORE = saved_rel
            if saved_con is not None:
                constitution.STORE = saved_con

    # ---- E. SELFTEST — the module's own end-to-end corrupt->detect->restore cycle -------------
    cp = subprocess.run([sys.executable, "-m", "anima.reliability", "--selftest"],
                        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    ck("E1: python3 -m anima.reliability --selftest passes (exit 0 + ALL ... PASS)",
       cp.returncode == 0 and "ALL RELIABILITY SELFTESTS PASS" in (cp.stdout or ""))

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nRELIABILITY-RECOVERY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
