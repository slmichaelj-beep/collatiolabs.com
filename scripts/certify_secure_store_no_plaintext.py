#!/usr/bin/env python3
"""certify_secure_store_no_plaintext — private append ledgers seal raw text when ANIMA_KEY is set.

This is the first sovereign-security adversarial cert. It reproduces the prior weakness:
private ledgers/stores wrote raw bytes even when ANIMA_KEY was present.

The cert runs in a temporary working directory so crypto salt/key material cannot contaminate
the real repo .anima. It then writes synthetic secrets through the production store APIs,
reads the raw bytes from disk, and proves:

  A. raw truth bytes do NOT contain the secret
  B. raw observation bytes do NOT contain the secret
  C. company/consent/curiosity/telemetry/whole-MRI private stores are also sealed
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
        from anima.company import storage as company_storage
        from anima.consent import policy as consent_policy
        from anima import curiosity, telemetry, whole_mri

        name = "SecureStoreCert"
        secret = "RAW_SECRET_SHOULD_NOT_APPEAR_7b1d7f"

        # Redirect module-level stores that do not take a store= argument.
        consent_policy.STORE = store
        curiosity.STORE = store
        telemetry.STORE = store
        whole_mri.STORE = store

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
        company_storage.save(name, "secure_store_probe", {"secret": secret}, store=store)
        consent_policy._save(name, {"probe": {"secret": secret}})
        consent_policy._save_pending(name, [{"pending_id": "p_cert", "candidate": {"text": secret},
                                             "status": "pending"}])
        curiosity.mark_asked(name, {"slot": "secure_store_probe", "_question": secret})
        telemetry._append(name, {"kind": "secure_store_probe", "secret": secret})
        telemetry._append_mri(name, {"kind": "secure_store_probe", "secret": secret})
        trace = whole_mri.assemble(turn_id=whole_mri.mint_turn_id(),
                                   vera={"response": secret}, route="llm", input_kind="chat")
        whole_mri.record(name, trace)

        truth_path = truth_ledger.path_for(name, store)
        obs_path = observation_store.path_for(name, store)
        company_path = company_storage.company_dir(name, store) / "secure_store_probe.json"
        consent_path = consent_policy._path(name)
        consent_pending_path = consent_policy._pending_path(name)
        curiosity_path = curiosity.ledger_path(name)
        telemetry_path = telemetry._path(name)
        telemetry_mri_path = telemetry._mri_path(name)
        whole_mri_path = whole_mri._trace_path(name)
        truth_raw = truth_path.read_text(encoding="utf-8")
        obs_raw = obs_path.read_text(encoding="utf-8")
        company_raw = company_path.read_text(encoding="utf-8")
        consent_raw = consent_path.read_text(encoding="utf-8")
        consent_pending_raw = consent_pending_path.read_text(encoding="utf-8")
        curiosity_raw = curiosity_path.read_text(encoding="utf-8")
        telemetry_raw = telemetry_path.read_text(encoding="utf-8")
        telemetry_mri_raw = telemetry_mri_path.read_text(encoding="utf-8")
        whole_mri_raw = whole_mri_path.read_text(encoding="utf-8")

        ck("A1: raw Truth Ledger bytes do NOT contain the synthetic secret",
           secret not in truth_raw)
        ck("A2: raw Observation Store bytes do NOT contain the synthetic secret",
           secret not in obs_raw)
        ck("A3: raw company storage bytes do NOT contain the synthetic secret",
           secret not in company_raw)
        ck("A4: raw consent storage bytes do NOT contain the synthetic secret",
           secret not in consent_raw and secret not in consent_pending_raw)
        ck("A5: raw curiosity/telemetry/whole-MRI bytes do NOT contain the synthetic secret",
           all(secret not in raw for raw in (curiosity_raw, telemetry_raw,
                                            telemetry_mri_raw, whole_mri_raw)))
        ck("B1: Truth Ledger physical line is encrypted with ANIMAENC marker",
           truth_raw.startswith("ANIMAENC1:"))
        ck("B2: Observation Store physical line is encrypted with ANIMAENC marker",
           obs_raw.startswith("ANIMAENC1:"))
        ck("B3: company + consent JSON files are encrypted with ANIMAENC marker",
           company_raw.startswith("ANIMAENC1:") and consent_raw.startswith("ANIMAENC1:")
           and consent_pending_raw.startswith("ANIMAENC1:"))
        ck("B4: curiosity/telemetry/whole-MRI JSONL lines are encrypted with ANIMAENC marker",
           curiosity_raw.startswith("ANIMAENC1:") and telemetry_raw.startswith("ANIMAENC1:")
           and telemetry_mri_raw.startswith("ANIMAENC1:") and whole_mri_raw.startswith("ANIMAENC1:"))

        loaded_truth = truth_ledger.load(name, store=store)
        loaded_obs = observation_store.load(name, store=store)
        ck("C1: Truth Ledger load still recovers the original secret",
           any(x.get("claim") == secret for x in loaded_truth))
        ck("C2: Observation Store load still recovers the original secret",
           any(x.get("secret") == secret for x in loaded_obs))
        ck("C3: company + consent load paths still recover the original secret",
           company_storage.load(name, "secure_store_probe", store=store).get("secret") == secret
           and consent_policy.load(name).get("probe", {}).get("secret") == secret
           and consent_policy._load_pending(name)[0].get("candidate", {}).get("text") == secret)
        ck("C4: curiosity/telemetry/whole-MRI load paths still recover the original secret",
           "secure_store_probe" in curiosity.asked_keys(name)
           and telemetry._read(name)[0].get("secret") == secret
           and telemetry._read_mri(name)[0].get("secret") == secret
           and whole_mri.all(name)[0].get("vera", {}).get("response") == secret)

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
                    "anima/company/storage.py",
                    "anima/consent/policy.py",
                    "anima/curiosity.py",
                    "anima/telemetry.py",
                    "anima/whole_mri.py",
                    "anima/crypto.py",
                ],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nSECURE-STORE-NO-PLAINTEXT CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
