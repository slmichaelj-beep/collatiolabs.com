#!/usr/bin/env python3
"""certify_vault_key_lifecycle — first-run vault key lifecycle is real.

This cert closes the remaining product slice around at-rest encryption lifecycle:

  * no recovery material can be created for a plaintext vault;
  * recovery codes are display-once and stored only as salted hashes;
  * recovery codes are one-time when consumed;
  * wrong-key rotation fails before mutation;
  * confirmed rotation rewrites encrypted files, old key fails, new key reads;
  * /security.json and /security/action expose the lifecycle without persisting keys.
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


def _reset_crypto() -> None:
    from anima import crypto
    crypto.reset_cipher_cache()


def _set_key(key: str | None) -> None:
    if key is None:
        os.environ.pop("ANIMA_KEY", None)
    else:
        os.environ["ANIMA_KEY"] = key
    _reset_crypto()


def main() -> int:
    fails: list[str] = []

    def ck(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("VAULT KEY LIFECYCLE — recovery hashes, rotation, visibility")
    print("=" * 84)
    t0 = time.perf_counter()

    old_cwd = Path.cwd()
    old_key = os.environ.get("ANIMA_KEY")
    old_store = os.environ.get("ANIMA_STORE")
    old_disable = os.environ.get("ANIMA_DISABLE_KEYCHAIN")

    with tempfile.TemporaryDirectory(prefix="vera-vault-keys-cert-") as td:
        root = Path(td)
        os.chdir(root)
        store = root / ".anima"
        store.mkdir()
        os.environ["ANIMA_STORE"] = str(store)
        os.environ["ANIMA_DISABLE_KEYCHAIN"] = "1"
        _set_key(None)

        from anima import secure_store, vault_keys, server

        no_key_status = vault_keys.status(store)
        ck("A1: status is honest when no vault key is active",
           no_key_status["encryption_enabled"] is False
           and no_key_status["key_source"] == "none")
        try:
            vault_keys.generate_recovery_codes(store, count=2)
            no_key_refused = False
        except RuntimeError as e:
            no_key_refused = "plaintext vault" in str(e)
        ck("A2: recovery-code generation refuses a plaintext vault",
           no_key_refused)

        old_secret = "old-vault-key-cert"
        new_secret = "new-vault-key-cert"
        final_secret = "final-vault-key-cert"
        private_text = "VAULT_LIFECYCLE_PRIVATE_TEXT_6e8b11"
        _set_key(old_secret)
        secure_store.save_json(store / "profile.json", {"secret": private_text, "n": 1})
        secure_store.save_text(store / "note.md", "note:" + private_text)
        secure_store.append_jsonl(store / "events.jsonl", {"secret": private_text, "n": 2})

        recovery = vault_keys.generate_recovery_codes(store, count=3)
        codes = recovery.get("codes") or []
        recovery_raw = (store / vault_keys.RECOVERY_FILE).read_text(encoding="utf-8")
        ck("B1: recovery generation returns display-once codes",
           recovery.get("ok") is True and len(codes) == 3 and recovery.get("display_once") is True)
        ck("B2: recovery registry is encrypted at rest",
           recovery_raw.startswith("ANIMAENC1:"))
        ck("B3: raw recovery registry contains no recovery code plaintext",
           all(code not in recovery_raw for code in codes))
        ck("B4: raw private stores contain no synthetic private text",
           all(private_text.encode("utf-8") not in p.read_bytes()
               for p in (store / "profile.json", store / "note.md", store / "events.jsonl")))

        first = codes[0]
        ck("B5: a valid recovery code verifies",
           vault_keys.verify_recovery_code(first, store).get("matched") is True)
        ck("B6: consuming a recovery code makes it one-time",
           vault_keys.verify_recovery_code(first, store, consume=True).get("used") is True
           and vault_keys.verify_recovery_code(first, store).get("matched") is False)
        keyed_status = vault_keys.status(store)
        keyed_dump = json.dumps(keyed_status)
        ck("B7: status exposes posture but not recovery codes",
           keyed_status["encryption_enabled"] is True
           and keyed_status["recovery"]["configured"] is True
           and all(code not in keyed_dump for code in codes))

        before = {p.relative_to(store).as_posix(): p.read_bytes()
                  for p in sorted(store.rglob("*")) if p.is_file()}
        dry = vault_keys.rotate_store(store, old_key=old_secret, new_key=new_secret, confirm=False)
        after_dry = {p.relative_to(store).as_posix(): p.read_bytes()
                     for p in sorted(store.rglob("*")) if p.is_file()}
        ck("C1: rotation dry-run plans files without mutating bytes",
           dry["dry_run"] is True and dry["files_planned"] >= 4 and before == after_dry)

        try:
            vault_keys.rotate_store(store, old_key="wrong-old-key", new_key=new_secret, confirm=True)
            wrong_refused = False
        except RuntimeError:
            wrong_refused = True
        after_wrong = {p.relative_to(store).as_posix(): p.read_bytes()
                       for p in sorted(store.rglob("*")) if p.is_file()}
        ck("C2: wrong old key refuses rotation before any mutation",
           wrong_refused and before == after_wrong)

        rotated = vault_keys.rotate_store(store, old_key=old_secret, new_key=new_secret, confirm=True)
        after_rotate = {p.relative_to(store).as_posix(): p.read_bytes()
                        for p in sorted(store.rglob("*")) if p.is_file()}
        ck("C3: confirmed rotation rewrites encrypted files",
           rotated["ok"] is True and rotated["files_rotated"] >= 4
           and any(before.get(k) != after_rotate.get(k) for k in before))

        _set_key(old_secret)
        try:
            secure_store.load_json(store / "profile.json", {})
            old_key_failed = False
        except RuntimeError:
            old_key_failed = True
        ck("C4: old key can no longer open the rotated vault",
           old_key_failed)

        _set_key(new_secret)
        ck("C5: new key opens JSON/text/JSONL stores after rotation",
           secure_store.load_json(store / "profile.json", {}).get("secret") == private_text
           and private_text in (secure_store.load_text(store / "note.md", "") or "")
           and secure_store.load_jsonl(store / "events.jsonl")[0].get("secret") == private_text)
        ck("C6: unconsumed recovery code still verifies after rotation",
           vault_keys.verify_recovery_code(codes[1], store).get("matched") is True)

        surface = server._security_data("Vera")
        surface_dump = json.dumps(surface)
        ck("D1: /security.json data includes vault posture",
           isinstance(surface.get("vault"), dict)
           and surface["vault"]["encryption_enabled"] is True
           and surface["counts"]["vault_action_required"] in (0, 1))
        ck("D2: /security.json does not leak vault keys or recovery codes",
           old_secret not in surface_dump and new_secret not in surface_dump
           and all(code not in surface_dump for code in codes))

        generated = server._security_action("Vera", {"action": "vault_recovery_generate", "count": 2})
        generated_codes = generated.get("codes") or []
        generated_raw = (store / vault_keys.RECOVERY_FILE).read_text(encoding="utf-8")
        ck("D3: security action can generate display-once recovery codes",
           generated.get("ok") is True and len(generated_codes) == 2)
        ck("D4: security action persists only encrypted recovery hashes",
           generated_raw.startswith("ANIMAENC1:")
           and all(code not in generated_raw for code in generated_codes))

        rotated_by_server = server._security_action(
            "Vera",
            {"action": "vault_rotate", "old_key": new_secret, "new_key": final_secret, "confirm": True},
        )
        rotate_dump = json.dumps(rotated_by_server)
        ck("D5: security action rotates the vault without echoing keys",
           rotated_by_server.get("ok") is True
           and new_secret not in rotate_dump and final_secret not in rotate_dump)
        ck("D6: server switches the running process to the new key",
           os.environ.get("ANIMA_KEY") == final_secret
           and secure_store.load_json(store / "profile.json", {}).get("secret") == private_text)

        html = (ROOT / "anima" / "web" / "security.html").read_text(encoding="utf-8")
        first_launch = (ROOT / "anima" / "first_launch.py").read_text(encoding="utf-8")
        ck("E1: Security UI renders a Vault tab and recovery/rotation controls",
           "Vault" in html and "vault_recovery_generate" in html and "vault_rotate" in html)
        ck("E2: Vault UI does not persist secrets to localStorage",
           "localStorage.setItem" not in html and "VAULT_CODES" in html)
        ck("E3: first-launch setup includes vault and recovery checks",
           '"vault"' in first_launch and '"recovery"' in first_launch and "vault_keys.status" in first_launch)

    os.chdir(old_cwd)
    if old_key is None:
        os.environ.pop("ANIMA_KEY", None)
    else:
        os.environ["ANIMA_KEY"] = old_key
    if old_store is None:
        os.environ.pop("ANIMA_STORE", None)
    else:
        os.environ["ANIMA_STORE"] = old_store
    if old_disable is None:
        os.environ.pop("ANIMA_DISABLE_KEYCHAIN", None)
    else:
        os.environ["ANIMA_DISABLE_KEYCHAIN"] = old_disable
    _reset_crypto()

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_vault_key_lifecycle", "green" if green else "red",
                files_observed=[
                    "anima/crypto.py",
                    "anima/vault_keys.py",
                    "anima/server.py",
                    "anima/first_launch.py",
                    "anima/web/security.html",
                    "scripts/certify_vault_key_lifecycle.py",
                ],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nVAULT-KEY-LIFECYCLE CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
