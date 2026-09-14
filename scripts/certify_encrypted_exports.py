#!/usr/bin/env python3
"""certify_encrypted_exports — portable/export/training artifacts are sealed by default.

W03's remaining plaintext surfaces were user-chosen exports and Forge training datasets.
This cert proves the product posture:
  * portable mind, full mind, identity, and Forge datasets write ANIMAENC1 at rest by default;
  * raw files do not contain a synthetic secret;
  * normal load/materialization APIs recover the original payload;
  * plaintext remains available only through the explicit allow_plaintext escape hatch.
"""
from __future__ import annotations

import json
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

    def ck(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    def mode600(path: Path) -> bool:
        return (path.stat().st_mode & 0o777) == 0o600

    print("ENCRYPTED EXPORTS — portable/full/identity/forge sealed by default")
    print("=" * 82)
    t0 = time.perf_counter()

    old_cwd = Path.cwd()
    old_key = os.environ.get("ANIMA_KEY")
    with tempfile.TemporaryDirectory(prefix="encrypted-export-cert-") as td:
        os.chdir(td)
        os.environ["ANIMA_KEY"] = "encrypted-export-cert-key"
        try:
            from anima import forge, identity, platform, portable

            secret = "EXPORT_SECRET_42bff7"

            portable_bundle = {
                "manifest": {"schema": "vera.portable-mind", "person": "Portable_" + secret},
                "identity": [{"trait": "secret", "value": secret}],
            }
            pp = portable.save_bundle(portable_bundle, Path("portable.json"))
            praw = pp.read_text(encoding="utf-8")
            ck("A1: portable save_bundle writes ANIMAENC by default", praw.startswith("ANIMAENC1:"))
            ck("A2: portable raw bytes do not expose the secret", secret not in praw)
            ck("A3: portable load_bundle recovers the bundle",
               portable.load_bundle(pp)["identity"][0]["value"] == secret)
            pplain = portable.save_bundle(portable_bundle, Path("portable.plain.json"),
                                          allow_plaintext=True)
            ck("A4: portable plaintext export requires explicit allow_plaintext",
               secret in pplain.read_text(encoding="utf-8"))
            ck("A5: portable plaintext escape hatch writes owner-only permissions",
               mode600(pplain))

            full_bundle = {
                "manifest": {"schema": platform.SCHEMA, "person": "Full_" + secret},
                "identity_bundle": portable_bundle,
                "vault": [{"id": "obj_" + secret, "type": "heuristic", "state": "active"}],
            }
            fp = platform.save_bundle(full_bundle, Path("full-mind.json"))
            fraw = fp.read_text(encoding="utf-8")
            ck("B1: platform save_bundle writes ANIMAENC by default", fraw.startswith("ANIMAENC1:"))
            ck("B2: platform raw bytes do not expose the secret", secret not in fraw)
            ck("B3: platform load_bundle recovers the bundle",
               platform.load_bundle(fp)["vault"][0]["id"].endswith(secret))
            fplain = platform.save_bundle(full_bundle, Path("full-mind.plain.json"),
                                          allow_plaintext=True)
            ck("B4: platform plaintext export requires explicit allow_plaintext",
               secret in fplain.read_text(encoding="utf-8"))
            ck("B5: platform plaintext escape hatch writes owner-only permissions",
               mode600(fplain))

            ip = Path("identity.json")
            identity.to_file("Identity_" + secret, str(ip))
            iraw = ip.read_text(encoding="utf-8")
            ck("C1: identity.to_file writes ANIMAENC by default", iraw.startswith("ANIMAENC1:"))
            ck("C2: identity raw bytes do not expose the secret", secret not in iraw)
            ck("C3: identity.from_file recovers the bundle",
               identity.from_file(str(ip)).get("name") == "Identity_" + secret)
            ipt = Path("identity.plain.json")
            identity.to_file("Identity_" + secret, str(ipt), allow_plaintext=True)
            ck("C4: identity plaintext export requires explicit allow_plaintext",
               secret in ipt.read_text(encoding="utf-8"))
            ck("C5: identity plaintext escape hatch writes owner-only permissions",
               mode600(ipt))

            data_dir = Path("forge-data")
            doc = " ".join([secret] * 80)
            n_train, n_valid = forge.build_dataset([doc], data_dir, words=20)
            ck("D1: forge build_dataset produced train/valid rows", n_train > 0 and n_valid >= 0)
            train_raw = (data_dir / "train.jsonl").read_text(encoding="utf-8")
            valid_raw = (data_dir / "valid.jsonl").read_text(encoding="utf-8")
            ck("D2: forge train dataset writes ANIMAENC by default", train_raw.startswith("ANIMAENC1:"))
            ck("D3: forge valid dataset writes ANIMAENC by default", valid_raw.startswith("ANIMAENC1:"))
            ck("D4: forge raw dataset bytes do not expose the secret",
               secret not in train_raw and secret not in valid_raw)
            ck("D5: forge load_dataset_file recovers JSONL text",
               secret in forge.load_dataset_file(data_dir / "train.jsonl"))
            with forge.materialized_dataset(data_dir) as mat:
                mat_path = Path(mat)
                ck("D6: forge materialized dataset exists during trainer handoff",
                   (mat_path / "train.jsonl").exists())
                ck("D7: forge materialized dataset contains trainer-readable JSONL",
                   json.loads((mat_path / "train.jsonl").read_text(encoding="utf-8").splitlines()[0])["text"])
                ck("D8: forge materialized train file is owner-only",
                   mode600(mat_path / "train.jsonl"))
            ck("D9: forge materialized dataset is removed after handoff", not mat_path.exists())

            plain_dir = Path("forge-plain")
            forge.build_dataset([doc], plain_dir, words=20, allow_plaintext=True)
            ck("D10: forge plaintext dataset requires explicit allow_plaintext",
               secret in (plain_dir / "train.jsonl").read_text(encoding="utf-8"))
            ck("D11: forge plaintext dataset writes owner-only permissions",
               mode600(plain_dir / "train.jsonl"))
        finally:
            os.chdir(old_cwd)
            if old_key is None:
                os.environ.pop("ANIMA_KEY", None)
            else:
                os.environ["ANIMA_KEY"] = old_key

    green = not fails
    try:
        from anima.verification.cert_result import emit
        emit("certify_encrypted_exports", "green" if green else "red",
             files_observed=[
                 "anima/secure_store.py",
                 "anima/portable.py",
                 "anima/platform.py",
                 "anima/identity.py",
                 "anima/forge.py",
                 "scripts/certify_encrypted_exports.py",
             ],
             evidence_paths=["reports/cert_results/certify_encrypted_exports.json"],
             failures=fails,
             duration_sec=time.perf_counter() - t0,
             next_action="" if green else "Fix encrypted export/package defaults")
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nENCRYPTED-EXPORTS CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
