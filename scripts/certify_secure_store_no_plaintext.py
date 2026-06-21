#!/usr/bin/env python3
"""certify_secure_store_no_plaintext — private append ledgers seal raw text when ANIMA_KEY is set.

This is the first sovereign-security adversarial cert. It reproduces the prior weakness:
Truth Ledger and Observation Store wrote raw JSONL even when ANIMA_KEY was present.

The cert runs in a temporary working directory so crypto salt/key material cannot contaminate
the real repo .anima. It then writes synthetic secrets through the production ledger APIs,
reads the raw bytes from disk, and proves:

  A. raw truth bytes do NOT contain the secret
  B. raw observation bytes do NOT contain the secret
  C. both ledgers are physically marked encrypted
  D. normal load paths still recover the original records

Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails: list[str] = []

    def ck(label: str, cond: bool):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("SECURE STORE — ANIMA_KEY seals private append ledgers")
    print("=" * 78)
    t0 = time.perf_counter()

    old_cwd = Path.cwd()
    old_key = os.environ.get("ANIMA_KEY")
    old_store = os.environ.get("ANIMA_STORE")

    with tempfile.TemporaryDirectory(prefix="vera-secstore-") as td:
        work = Path(td)
        store = work / "store"
        os.chdir(work)
        os.environ["ANIMA_KEY"] = "cert-secret-passphrase"
        os.environ["ANIMA_STORE"] = str(store)

        from anima.truth import ledger as truth_ledger
        from anima.truth import schema as truth_schema
        from anima.observation import store as observation_store

        name = "SecureStoreCert"
        secret = "RAW_SECRET_SHOULD_NOT_APPEAR_7b1d7f"

        ev = truth_schema.make(
            "secure-store-probe",
            secret,
            "system",
            provenance_kind="system_cert",
            scope="system",
            confidence=1.0,
            actor="cert",
            risk="sensitive",
        )
        truth_ledger.emit(name, ev, store=store)
        observation_store.append(name, {"kind": "secure_store_probe", "secret": secret}, store=store)

        truth_path = truth_ledger.path_for(name, store)
        obs_path = observation_store.path_for(name, store)
        truth_raw = truth_path.read_text(encoding="utf-8")
        obs_raw = obs_path.read_text(encoding="utf-8")

        ck("A1: raw Truth Ledger bytes do NOT contain the synthetic secret",
           secret not in truth_raw)
        ck("A2: raw Observation Store bytes do NOT contain the synthetic secret",
           secret not in obs_raw)
        ck("B1: Truth Ledger physical line is encrypted with ANIMAENC marker",
           truth_raw.startswith("ANIMAENC1:"))
        ck("B2: Observation Store physical line is encrypted with ANIMAENC marker",
           obs_raw.startswith("ANIMAENC1:"))

        loaded_truth = truth_ledger.load(name, store=store)
        loaded_obs = observation_store.load(name, store=store)
        ck("C1: Truth Ledger load still recovers the original secret",
           any(x.get("claim") == secret for x in loaded_truth))
        ck("C2: Observation Store load still recovers the original secret",
           any(x.get("secret") == secret for x in loaded_obs))

        os.chdir(old_cwd)

    if old_key is None:
        os.environ.pop("ANIMA_KEY", None)
    else:
        os.environ["ANIMA_KEY"] = old_key
    if old_store is None:
        os.environ.pop("ANIMA_STORE", None)
    else:
        os.environ["ANIMA_STORE"] = old_store

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_secure_store_no_plaintext", "green" if green else "red",
                files_observed=[
                    "anima/secure_store.py",
                    "anima/truth/ledger.py",
                    "anima/observation/store.py",
                    "anima/crypto.py",
                ],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nSECURE-STORE-NO-PLAINTEXT CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())

