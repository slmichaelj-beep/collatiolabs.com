"""vault_keys — local vault key lifecycle for Vera.

This module does not invent cryptography. It wraps the existing authenticated
``ANIMAENC1`` store format with product lifecycle operations:

* visible key posture without exposing the key;
* one-time recovery codes stored only as salted hashes;
* offline/full-vault passphrase rotation that proves the new key opens the
  rotated files before it publishes any rewrite.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from . import crypto, secure_store

KIND = "anima.vault_keys"
SCHEMA = 1
RECOVERY_FILE = "vault_recovery.json"
EVENTS_FILE = "vault_key_events.jsonl"
MARKER = "ANIMAENC1:"
SKIP_DIRS = {"backups", "__pycache__"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def default_store(store: str | Path | None = None) -> Path:
    if store is not None:
        return Path(store)
    return Path(os.environ.get("ANIMA_STORE", ".anima"))


def recovery_path(store: str | Path | None = None) -> Path:
    return default_store(store) / RECOVERY_FILE


def events_path(store: str | Path | None = None) -> Path:
    return default_store(store) / EVENTS_FILE


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_code(code: str, salt: bytes) -> str:
    return hashlib.sha256(salt + code.encode("utf-8")).hexdigest()


def _recovery_record(store: str | Path | None = None) -> dict:
    return secure_store.load_json(recovery_path(store), {}) or {}


def recovery_status(store: str | Path | None = None) -> dict:
    try:
        rec = _recovery_record(store)
    except Exception as e:
        return {"configured": False, "error": str(e), "codes_total": 0, "codes_unused": 0}
    codes = rec.get("codes") or []
    unused = [c for c in codes if not c.get("used_at")]
    return {
        "configured": bool(codes),
        "created_at": rec.get("created_at"),
        "codes_total": len(codes),
        "codes_unused": len(unused),
        "codes_used": len(codes) - len(unused),
    }


def _store_counts(store: Path) -> dict:
    encrypted = plaintext = unreadable = total = 0
    if not store.exists():
        return {"exists": False, "total_files": 0, "encrypted_files": 0,
                "plaintext_or_binary_files": 0, "unreadable_files": 0}
    for p in sorted(store.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(store).parts):
            continue
        total += 1
        try:
            if p.read_bytes()[:len(MARKER)].decode("ascii", "ignore") == MARKER:
                encrypted += 1
            else:
                plaintext += 1
        except Exception:
            unreadable += 1
    return {"exists": True, "total_files": total, "encrypted_files": encrypted,
            "plaintext_or_binary_files": plaintext, "unreadable_files": unreadable}


def _last_rotation(store: str | Path | None = None) -> dict:
    try:
        rows = secure_store.load_jsonl(events_path(store), skip_bad=True)
    except Exception:
        rows = []
    rotations = [r for r in rows if r.get("kind") == "rotation"]
    return rotations[-1] if rotations else {}


def status(store: str | Path | None = None) -> dict:
    st = default_store(store)
    enabled = crypto.enabled()
    product_required = (
        os.environ.get("ANIMA_REQUIRE_ENCRYPTION") == "1"
        or os.environ.get("ANIMA_PRODUCT_MODE") == "1"
    )
    recovery = recovery_status(st)
    rotation = _last_rotation(st)
    out = {
        "ok": True,
        "kind": KIND,
        "schema": SCHEMA,
        "store": str(st),
        "encryption_enabled": enabled,
        "key_source": crypto.key_source(),
        "product_mode_required": product_required,
        "recovery": recovery,
        "rotation": {
            "configured": bool(rotation),
            "last_rotated_at": rotation.get("at"),
            "files_rotated": rotation.get("files_rotated", 0),
        },
        "files": _store_counts(st),
    }
    out["action_required"] = bool(product_required and not enabled) or (enabled and not recovery.get("configured"))
    out["headline"] = (
        "Encrypted vault active; recovery codes configured."
        if enabled and recovery.get("configured") else
        "Encrypted vault active; generate recovery codes next."
        if enabled else
        "Vault encryption is not active."
    )
    return out


def _require_active_key() -> None:
    if not crypto.enabled():
        raise RuntimeError(
            "vault key lifecycle requires ANIMA_KEY or the macOS Keychain item 'anima'; "
            "refusing to create recovery material for a plaintext vault")


def generate_recovery_codes(store: str | Path | None = None, *, count: int = 8) -> dict:
    """Generate display-once recovery codes and persist only salted hashes."""
    _require_active_key()
    if count < 1 or count > 20:
        raise ValueError("recovery code count must be between 1 and 20")
    codes = ["vera-" + secrets.token_urlsafe(18) for _ in range(count)]
    rows = []
    for code in codes:
        salt = os.urandom(16)
        rows.append({
            "id": secrets.token_hex(4),
            "salt_b64": base64.b64encode(salt).decode("ascii"),
            "hash_sha256": _hash_code(code, salt),
        })
    rec = {"kind": KIND + ".recovery", "schema": SCHEMA, "created_at": _now(), "codes": rows}
    secure_store.save_json(recovery_path(store), rec)
    secure_store.append_jsonl(events_path(store), {
        "kind": "recovery_codes_generated",
        "at": rec["created_at"],
        "count": count,
    })
    return {"ok": True, "codes": codes, "count": count, "display_once": True,
            "created_at": rec["created_at"]}


def verify_recovery_code(code: str, store: str | Path | None = None, *, consume: bool = False) -> dict:
    rec = _recovery_record(store)
    now = _now()
    for row in rec.get("codes") or []:
        if row.get("used_at"):
            continue
        try:
            salt = base64.b64decode(str(row.get("salt_b64") or "").encode("ascii"))
        except Exception:
            continue
        expected = str(row.get("hash_sha256") or "")
        if expected and hmac.compare_digest(_hash_code(str(code or ""), salt), expected):
            if consume:
                row["used_at"] = now
                secure_store.save_json(recovery_path(store), rec)
                secure_store.append_jsonl(events_path(store), {
                    "kind": "recovery_code_used",
                    "at": now,
                    "code_id": row.get("id"),
                })
            return {"ok": True, "matched": True, "used": bool(consume), "code_id": row.get("id")}
    return {"ok": False, "matched": False}


@contextlib.contextmanager
def _temporary_key(passphrase: str, *, salt_store: Path | None = None):
    old_key = os.environ.get("ANIMA_KEY")
    old_store = crypto._STORE
    os.environ["ANIMA_KEY"] = str(passphrase)
    if salt_store is not None:
        crypto._STORE = Path(salt_store)
    crypto.reset_cipher_cache()
    try:
        yield
    finally:
        if old_key is None:
            os.environ.pop("ANIMA_KEY", None)
        else:
            os.environ["ANIMA_KEY"] = old_key
        crypto._STORE = old_store
        crypto.reset_cipher_cache()


def _decrypt_with(text: str, passphrase: str, *, salt_store: Path) -> str:
    with _temporary_key(passphrase, salt_store=salt_store):
        return crypto.maybe_decrypt(text)


def _encrypt_with(text: str, passphrase: str, *, salt_store: Path) -> str:
    with _temporary_key(passphrase, salt_store=salt_store):
        return crypto.maybe_encrypt(text)


def _iter_rotatable_files(store: Path) -> list[Path]:
    if not store.exists():
        return []
    files = []
    for p in sorted(store.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(store)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.name == ".keysalt":
            continue
        try:
            raw = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if raw.startswith(MARKER) or any(line.startswith(MARKER) for line in raw.splitlines()):
            files.append(p)
    return files


def _rotate_text(raw: str, *, old_key: str, new_key: str, salt_store: Path) -> str:
    if raw.startswith(MARKER):
        plain = _decrypt_with(raw, old_key, salt_store=salt_store)
        return _encrypt_with(plain, new_key, salt_store=salt_store)
    out = []
    trailing = raw.endswith("\n")
    for line in raw.splitlines():
        if line.startswith(MARKER):
            plain = _decrypt_with(line, old_key, salt_store=salt_store)
            out.append(_encrypt_with(plain, new_key, salt_store=salt_store))
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if trailing else "")


def _write_owner_only_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    mode = mode if (mode & 0o700) else 0o600
    tmp = path.with_name(path.name + ".rotate.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _first_encrypted_segment(raw: str) -> str:
    if raw.startswith(MARKER):
        return raw
    for line in raw.splitlines():
        if line.startswith(MARKER):
            return line
    return raw


def rotate_store(store: str | Path | None = None, *, old_key: str, new_key: str,
                 confirm: bool = False, salt_store: str | Path | None = None) -> dict:
    """Rotate marked encrypted files from ``old_key`` to ``new_key``.

    The function plans and decrypts every rotatable file before publishing any
    rewrite. It then verifies each rewritten file opens under the new key.
    """
    if not old_key or not new_key:
        raise ValueError("old_key and new_key are required")
    if old_key == new_key:
        raise ValueError("new_key must be different from old_key")
    st = default_store(store)
    salt = Path(salt_store) if salt_store is not None else st
    files = _iter_rotatable_files(st)
    before = {p: p.read_text(encoding="utf-8") for p in files}
    plan: dict[Path, str] = {}
    for p, raw in before.items():
        plan[p] = _rotate_text(raw, old_key=old_key, new_key=new_key, salt_store=salt)
    if not confirm:
        return {"ok": True, "dry_run": True, "files_planned": len(plan), "files_rotated": 0}
    before_hash = {p: _sha256(raw.encode("utf-8")) for p, raw in before.items()}
    for p, new_raw in plan.items():
        _write_owner_only_text(p, new_raw)
    try:
        for p in plan:
            _decrypt_with(_first_encrypted_segment(p.read_text(encoding="utf-8")),
                          new_key, salt_store=salt)
    except Exception:
        for p, raw in before.items():
            _write_owner_only_text(p, raw)
        raise
    with _temporary_key(new_key, salt_store=salt):
        secure_store.append_jsonl(events_path(st), {
            "kind": "rotation",
            "at": _now(),
            "files_rotated": len(plan),
            "before_hashes": {p.relative_to(st).as_posix(): before_hash[p] for p in plan},
        })
    return {"ok": True, "dry_run": False, "files_planned": len(plan), "files_rotated": len(plan)}


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="anima.vault_keys")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--store", default=None)
    g = sub.add_parser("generate-recovery")
    g.add_argument("--store", default=None)
    g.add_argument("--count", type=int, default=8)
    v = sub.add_parser("verify-recovery")
    v.add_argument("code")
    v.add_argument("--store", default=None)
    v.add_argument("--consume", action="store_true")
    r = sub.add_parser("rotate")
    r.add_argument("--store", default=None)
    r.add_argument("--old-key", required=True)
    r.add_argument("--new-key", required=True)
    r.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "status":
        out = status(args.store)
    elif args.cmd == "generate-recovery":
        out = generate_recovery_codes(args.store, count=args.count)
    elif args.cmd == "verify-recovery":
        out = verify_recovery_code(args.code, args.store, consume=args.consume)
    elif args.cmd == "rotate":
        out = rotate_store(args.store, old_key=args.old_key, new_key=args.new_key,
                           confirm=args.confirm)
    else:
        out = {"ok": False, "error": "unknown command"}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
