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
import json
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
        from anima import curiosity, telemetry, whole_mri, secure_store

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

        matrix_secret = secret + "_MATRIX"
        matrix_root = store / "matrix"
        matrix_count = 0

        def raw_bytes(p: Path) -> bytes:
            return p.read_bytes() if p.exists() else b""

        def sealed(label: str, p: Path, recovered: bool) -> None:
            nonlocal matrix_count
            matrix_count += 1
            raw = raw_bytes(p)
            ck(f"M{matrix_count:02d}a: {label} raw bytes are encrypted",
               raw.startswith(b"ANIMAENC1:") and matrix_secret.encode("utf-8") not in raw)
            ck(f"M{matrix_count:02d}b: {label} load path recovers the secret", recovered)

        def matrix_json(label: str, rel: str) -> None:
            p = matrix_root / rel
            secure_store.save_json(p, {"kind": label, "secret": matrix_secret})
            sealed(label, p, secure_store.load_json(p, {}).get("secret") == matrix_secret)

        def matrix_jsonl(label: str, rel: str) -> None:
            p = matrix_root / rel
            secure_store.append_jsonl(p, {"kind": label, "secret": matrix_secret})
            rows = []
            for line in secure_store.read_jsonl_lines(p):
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
            sealed(label, p, any(r.get("secret") == matrix_secret for r in rows))

        def matrix_text(label: str, rel: str) -> None:
            p = matrix_root / rel
            secure_store.save_text(p, f"{label}:{matrix_secret}")
            sealed(label, p, matrix_secret in (secure_store.load_text(p, "") or ""))

        def matrix_bytes(label: str, rel: str) -> None:
            p = matrix_root / rel
            payload = (label + ":" + matrix_secret).encode("utf-8")
            secure_store.save_bytes(p, payload)
            sealed(label, p, secure_store.load_bytes(p, b"") == payload)

        matrix_json("agency approval queue", f"{name}.agency_queue.json")
        matrix_jsonl("agency intent ledger", f"{name}.agency_intents.jsonl")
        matrix_json("teaching queue", f"{name}.teaching.json")
        matrix_json("auto-learn queue", f"{name}.auto_learn.json")
        matrix_json("knowledge-pack registry", f"{name}.packs.json")
        matrix_text("knowledge-pack chunks", f"{name}.packs/pack_cert/chunks.jsonl")
        matrix_jsonl("rollback ledger", f"{name}.rollbacks.jsonl")
        matrix_jsonl("incident SOC ledger", "security_events.jsonl")
        matrix_json("incident lockdown state", "incident_lock.json")
        matrix_jsonl("metrics ledger", f"{name}.metrics.jsonl")
        matrix_jsonl("constitution continuity ledger", f"{name}.continuity.jsonl")
        matrix_jsonl("meaning ledger", f"{name}.meaning.jsonl")
        matrix_jsonl("reality ledger", f"{name}.reality.jsonl")
        matrix_jsonl("loops ledger", f"{name}.loops.jsonl")
        matrix_jsonl("opportunity offers ledger", f"{name}.offers.jsonl")
        matrix_jsonl("trajectory ledger", f"{name}.trajectory.jsonl")
        matrix_jsonl("theory observation ledger", f"{name}.theory.jsonl")
        matrix_jsonl("life-review ledger", f"{name}.review.jsonl")
        matrix_jsonl("intake MRI ledger", f"{name}.intake.jsonl")
        matrix_jsonl("intake worker jobs ledger", f"{name}.intake_jobs.jsonl")
        matrix_jsonl("intake tier ledger", f"{name}.tiers.jsonl")
        matrix_bytes("intake cold blob", f"{name}.cold/src_cert.json.gz")
        matrix_jsonl("LERF route ledger", f"{name}.lerf_routes.jsonl")
        matrix_json("founder-console decisions", f"{name}.console_decisions.json")
        matrix_jsonl("identity sandbox MRI", f"identity_sandbox/{name}.identity_mri.jsonl")
        matrix_jsonl("identity sandbox shadow ledger", f"identity_sandbox/{name}.identity_ledger.jsonl")
        matrix_json("identity sandbox dials restore", f"{name}.identity_restore/{name}.dials.json")
        matrix_text("identity sandbox persona restore", f"{name}.identity_restore/{name}.persona.md")
        matrix_json("twin manifest", f"twins/twin_cert/twin.manifest.json")
        matrix_jsonl("twin snapshot ledger", f"twins/twin_cert/snapshots/ledger.jsonl")
        matrix_text("twin narrative seed artifact", f"twins/twin_cert/narrative_seed.txt")
        ck("M99: expanded private-store matrix covered the migrated compartments",
           matrix_count == 31)

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
                    "anima/agency_approval_queue.py",
                    "anima/agency_intent_ledger.py",
                    "anima/teaching/queue.py",
                    "anima/auto_learn/queue.py",
                    "anima/knowledge_packs/registry.py",
                    "anima/knowledge_packs/builder.py",
                    "anima/rollback/apply.py",
                    "anima/teaching/rollback.py",
                    "anima/incident.py",
                    "anima/metrics.py",
                    "anima/constitution.py",
                    "anima/meaning.py",
                    "anima/reality.py",
                    "anima/loops.py",
                    "anima/opportunity.py",
                    "anima/trajectory.py",
                    "anima/theory.py",
                    "anima/review.py",
                    "anima/intake.py",
                    "anima/intake_worker.py",
                    "anima/intake_tiers.py",
                    "anima/server.py",
                    "anima/identity_sandbox.py",
                    "anima/twin.py",
                    "anima/crypto.py",
                ],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nSECURE-STORE-NO-PLAINTEXT CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
