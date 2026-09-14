#!/usr/bin/env python3
"""certify_encrypted_backup_restore — off-device vault backups are sealed and restorable.

This cert proves the product backup floor:
  * creating a backup requires the user's encryption secret;
  * the bundle wrapper exposes only safe metadata and the raw bundle hides private bytes;
  * the bundle carries its own public KDF salt, so restore is not tied to a local .keysalt;
  * dry-run restore writes nothing; confirmed restore recovers exact bytes;
  * tamper, wrong-key, overwrite, and path traversal attempts fail closed.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reset_crypto() -> None:
    from anima import crypto
    crypto._fernet = None
    crypto._resolved = False


def _mode600(path: Path) -> bool:
    return (path.stat().st_mode & 0o777) == 0o600


def main() -> int:
    fails: list[str] = []

    def ck(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("ENCRYPTED BACKUP/RESTORE — sealed off-device vault bundle")
    print("=" * 78)
    t0 = time.perf_counter()

    old_cwd = Path.cwd()
    old_key = os.environ.get("ANIMA_KEY")
    old_disable_keychain = os.environ.get("ANIMA_DISABLE_KEYCHAIN")
    with tempfile.TemporaryDirectory(prefix="vera-vault-backup-cert-") as td:
        root = Path(td)
        os.chdir(root)
        os.environ["ANIMA_DISABLE_KEYCHAIN"] = "1"
        os.environ.pop("ANIMA_KEY", None)
        _reset_crypto()

        from anima import secure_store, vault_backup

        store = root / ".anima"
        store.mkdir()
        secret = "VAULT_BACKUP_SECRET_983ff"
        (store / "Vera.json").write_text(json.dumps({"name": "Vera", "private": secret}))
        (store / "notes.txt").write_text("plaintext source still must be sealed: " + secret)
        (store / "blob.bin").write_bytes(b"\x00\x01private-binary-" + secret.encode("utf-8"))

        try:
            vault_backup.create_bundle(store, root / "no-key.vab", name="Vera")
            no_key_refused = False
        except RuntimeError as e:
            no_key_refused = "requires ANIMA_KEY" in str(e)
        ck("A1: creating an off-device vault backup without a user key is refused",
           no_key_refused)

        os.environ["ANIMA_KEY"] = "vault-backup-cert-key"
        _reset_crypto()
        secure_store.save_text(store / "sealed.md", "sealed source: " + secret)
        original = {
            p.relative_to(store).as_posix(): p.read_bytes()
            for p in sorted(store.rglob("*")) if p.is_file()
        }

        bundle = root / "vera.vab"
        meta = vault_backup.create_bundle(store, bundle, name="Vera", now=1_780_000_000.0)
        raw = bundle.read_text(encoding="utf-8")
        wrapper = json.loads(raw)
        ck("A2: bundle file is owner-only", _mode600(bundle))
        ck("A3: wrapper is marked as an encrypted Vera vault backup",
           wrapper.get("kind") == vault_backup.KIND and wrapper.get("encrypted") is True)
        ck("A4: wrapper carries a public bundle salt, not the private payload",
           bool((wrapper.get("kdf") or {}).get("salt_b64")) and wrapper["payload"].startswith("ANIMAENC1:"))
        ck("A5: raw backup bytes do not expose plaintext source secrets or filenames",
           secret not in raw and "notes.txt" not in raw and "sealed.md" not in raw)
        ck("A6: wrapper payload hash matches the encrypted payload",
           meta["payload_sha256"] == wrapper["payload_sha256"])

        info = vault_backup.inspect_bundle(bundle)
        paths = {f["path"] for f in info["files"]}
        ck("B1: inspect decrypts and verifies the manifest under the correct key",
           info["manifest"]["name"] == "Vera" and {"Vera.json", "notes.txt", "sealed.md", "blob.bin"} <= paths)

        target = root / "restore-target"
        dry = vault_backup.restore_bundle(bundle, target, confirm=False)
        ck("B2: restore is dry-run by default and writes nothing",
           dry["dry_run"] is True and dry["applied"] is False and not target.exists())
        applied = vault_backup.restore_bundle(bundle, target, confirm=True)
        restored = {
            p.relative_to(target).as_posix(): p.read_bytes()
            for p in sorted(target.rglob("*")) if p.is_file()
        }
        ck("B3: confirmed restore recovers every file byte-for-byte",
           applied["applied"] is True and restored == original)
        ck("B4: restored files are owner-only",
           all(_mode600(p) for p in target.rglob("*") if p.is_file()))

        try:
            vault_backup.restore_bundle(bundle, target, confirm=True)
            overwrite_refused = False
        except RuntimeError as e:
            overwrite_refused = "overwrite existing files" in str(e)
        ck("C1: confirmed restore refuses to overwrite existing files by default",
           overwrite_refused)
        ck("C2: explicit overwrite restores cleanly",
           vault_backup.restore_bundle(bundle, target, confirm=True, overwrite=True)["applied"] is True)

        tampered = root / "tampered.vab"
        shutil.copy2(bundle, tampered)
        tw = json.loads(tampered.read_text(encoding="utf-8"))
        tw["payload"] = tw["payload"][:-8] + "AAAAAAAA"
        tampered.write_text(json.dumps(tw))
        try:
            vault_backup.inspect_bundle(tampered)
            tamper_refused = False
        except RuntimeError as e:
            tamper_refused = "hash mismatch" in str(e)
        ck("C3: encrypted payload tampering is rejected before restore",
           tamper_refused)

        os.environ["ANIMA_KEY"] = "wrong-vault-backup-cert-key"
        _reset_crypto()
        try:
            vault_backup.inspect_bundle(bundle)
            wrong_key_refused = False
        except RuntimeError as e:
            wrong_key_refused = "cannot decrypt vault backup" in str(e)
        ck("C4: wrong user key cannot inspect or restore the backup",
           wrong_key_refused)

        os.environ["ANIMA_KEY"] = "vault-backup-cert-key"
        _reset_crypto()
        malicious_payload = {
            "manifest": {"kind": vault_backup.KIND, "schema": vault_backup.SCHEMA,
                         "name": "Vera", "created_at": "20260622-000000", "file_count": 1},
            "files": [{
                "path": "../escape.txt",
                "bytes": 5,
                "mode": 0o600,
                "sha256": "3733cd977ff8eb18b987357e22ced99f46097f4ec111e09f8f13959cd6646fff",
                "data_b64": base64.b64encode(b"owned").decode("ascii"),
            }],
        }
        malicious = root / "malicious.vab"
        vault_backup._write_wrapper(malicious, malicious_payload, created_at="20260622-000000")
        try:
            vault_backup.restore_bundle(malicious, root / "mal-target", confirm=True)
            traversal_refused = False
        except ValueError as e:
            traversal_refused = "unsafe backup path" in str(e)
        ck("C5: path traversal inside an encrypted payload is rejected before writing",
           traversal_refused and not (root / "escape.txt").exists())

    os.chdir(old_cwd)
    if old_key is None:
        os.environ.pop("ANIMA_KEY", None)
    else:
        os.environ["ANIMA_KEY"] = old_key
    if old_disable_keychain is None:
        os.environ.pop("ANIMA_DISABLE_KEYCHAIN", None)
    else:
        os.environ["ANIMA_DISABLE_KEYCHAIN"] = old_disable_keychain
    _reset_crypto()

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_encrypted_backup_restore", "green" if green else "red",
                files_observed=["anima/vault_backup.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nENCRYPTED-BACKUP-RESTORE CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
