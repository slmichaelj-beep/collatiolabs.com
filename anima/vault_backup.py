"""Encrypted vault backup bundles for Vera's private store.

This is for backups that leave the machine. It is deliberately stricter than
``reliability.backup``:

* the bundle itself requires active crypto and is always encrypted;
* public wrapper metadata is minimal and contains no filenames or private bytes;
* restore is dry-run by default, confirm-gated, hash-verified, and path-safe.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import time
from pathlib import Path

from . import crypto

KIND = "anima.vault_backup"
SCHEMA = 1
PAYLOAD_MARKER = "ANIMAENC1:"
SKIP_DIRS = {"backups", "__pycache__"}
KDF_ITERATIONS = 300_000


def _utc_stamp(now: float | None = None) -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time() if now is None else now))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mode_owner_only(mode: int | None = None) -> int:
    mode = 0o600 if mode is None else int(mode) & 0o777
    owner = mode & 0o700
    return owner or 0o600


def _safe_rel(path: str) -> str:
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError(f"unsafe backup path: {path!r}")
    return rel.as_posix()


def _iter_files(store: Path, *, output: Path | None = None) -> list[Path]:
    store = store.resolve()
    output_resolved = output.resolve() if output else None
    files: list[Path] = []
    for p in sorted(store.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(store)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if output_resolved and p.resolve() == output_resolved:
            continue
        files.append(p)
    return files


def _write_owner_only(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _passphrase() -> str:
    pw = crypto._passphrase()  # same env/keychain source as the private store; salt is bundle-local.
    if not pw:
        raise RuntimeError(
            "encrypted vault backup requires ANIMA_KEY or the macOS Keychain item 'anima'; "
            "Vera will not create or restore an off-device backup bundle without the user's key")
    return str(pw)


def _cipher(salt: bytes):
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except Exception as e:
        raise RuntimeError(
            "encrypted vault backup requires the cryptography package "
            f"({e}); refusing to fall back to plaintext") from e
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=KDF_ITERATIONS)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(_passphrase().encode())))


def _seal_payload(payload: dict, *, salt: bytes) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sealed = PAYLOAD_MARKER + _cipher(salt).encrypt(text.encode("utf-8")).decode("ascii")
    if not sealed.startswith(PAYLOAD_MARKER):
        raise RuntimeError("vault backup payload was not encrypted")
    return sealed


def _write_wrapper(path: Path, payload: dict, *, created_at: str | None = None) -> dict:
    salt = os.urandom(16)
    sealed = _seal_payload(payload, salt=salt)
    wrapper = {
        "kind": KIND,
        "schema": SCHEMA,
        "created_at": created_at or payload.get("manifest", {}).get("created_at") or _utc_stamp(),
        "encrypted": True,
        "file_count": len(payload.get("files", [])),
        "kdf": {
            "name": "PBKDF2HMAC-SHA256",
            "iterations": KDF_ITERATIONS,
            "salt_b64": base64.b64encode(salt).decode("ascii"),
        },
        "payload_sha256": _sha256_text(sealed),
        "payload": sealed,
    }
    raw = (json.dumps(wrapper, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_owner_only(path, raw)
    return {
        "ok": True,
        "path": str(path),
        "file_count": wrapper["file_count"],
        "payload_sha256": wrapper["payload_sha256"],
    }


def create_bundle(store: str | Path, out: str | Path, *, name: str = "Vera",
                  now: float | None = None) -> dict:
    """Create an encrypted, single-file backup bundle from ``store``."""
    _passphrase()  # fail before scanning private files if no user-held backup key exists
    store_p = Path(store).resolve()
    out_p = Path(out)
    created_at = _utc_stamp(now)
    files = []
    for p in _iter_files(store_p, output=out_p):
        rel = p.relative_to(store_p).as_posix()
        _safe_rel(rel)
        data = p.read_bytes()
        files.append({
            "path": rel,
            "bytes": len(data),
            "mode": p.stat().st_mode & 0o777,
            "sha256": _sha256_bytes(data),
            "data_b64": base64.b64encode(data).decode("ascii"),
        })
    payload = {
        "manifest": {
            "kind": KIND,
            "schema": SCHEMA,
            "name": name,
            "created_at": created_at,
            "source": "local-store",
            "file_count": len(files),
        },
        "files": files,
    }
    return _write_wrapper(out_p, payload, created_at=created_at)


def _load_wrapper(path: str | Path) -> dict:
    wrapper = json.loads(Path(path).read_text(encoding="utf-8"))
    if wrapper.get("kind") != KIND or wrapper.get("schema") != SCHEMA:
        raise RuntimeError("not a Vera vault backup bundle")
    if wrapper.get("encrypted") is not True:
        raise RuntimeError("vault backup wrapper is not marked encrypted")
    sealed = str(wrapper.get("payload") or "")
    if not sealed.startswith(PAYLOAD_MARKER):
        raise RuntimeError("vault backup payload is not encrypted")
    if _sha256_text(sealed) != wrapper.get("payload_sha256"):
        raise RuntimeError("vault backup payload hash mismatch")
    kdf = wrapper.get("kdf") or {}
    if kdf.get("name") != "PBKDF2HMAC-SHA256" or int(kdf.get("iterations") or 0) != KDF_ITERATIONS:
        raise RuntimeError("vault backup KDF metadata is unsupported")
    try:
        base64.b64decode(str(kdf.get("salt_b64") or "").encode("ascii"))
    except Exception as e:
        raise RuntimeError("vault backup KDF salt is invalid") from e
    return wrapper


def _open_payload(wrapper: dict) -> dict:
    salt = base64.b64decode(str((wrapper.get("kdf") or {}).get("salt_b64") or "").encode("ascii"))
    token = str(wrapper["payload"])[len(PAYLOAD_MARKER):].encode("ascii")
    try:
        text = _cipher(salt).decrypt(token).decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"cannot decrypt vault backup: {e}") from e
    return json.loads(text)


def inspect_bundle(path: str | Path) -> dict:
    """Decrypt and verify bundle metadata without writing any restored files."""
    wrapper = _load_wrapper(path)
    payload = _open_payload(wrapper)
    files = []
    for item in payload.get("files", []):
        rel = _safe_rel(str(item.get("path") or ""))
        data = base64.b64decode(str(item.get("data_b64") or "").encode("ascii"))
        if _sha256_bytes(data) != item.get("sha256"):
            raise RuntimeError(f"vault backup file hash mismatch: {rel}")
        files.append({
            "path": rel,
            "bytes": len(data),
            "sha256": item.get("sha256"),
            "mode": _mode_owner_only(item.get("mode")),
        })
    manifest = payload.get("manifest") or {}
    if manifest.get("kind") != KIND or int(manifest.get("schema") or 0) != SCHEMA:
        raise RuntimeError("vault backup manifest is invalid")
    if int(manifest.get("file_count") or -1) != len(files):
        raise RuntimeError("vault backup manifest file_count mismatch")
    return {"manifest": manifest, "files": files}


def restore_bundle(path: str | Path, target_store: str | Path, *, confirm: bool = False,
                   overwrite: bool = False) -> dict:
    """Restore a bundle into ``target_store``.

    Dry-run is the default. A confirmed restore refuses to overwrite existing files
    unless ``overwrite=True`` is explicit.
    """
    wrapper = _load_wrapper(path)
    payload = _open_payload(wrapper)
    target = Path(target_store)
    planned = []
    conflicts = []
    decoded = []
    for item in payload.get("files", []):
        rel = _safe_rel(str(item.get("path") or ""))
        data = base64.b64decode(str(item.get("data_b64") or "").encode("ascii"))
        if _sha256_bytes(data) != item.get("sha256"):
            raise RuntimeError(f"vault backup file hash mismatch: {rel}")
        dest = target / rel
        planned.append(rel)
        if dest.exists() and not overwrite:
            conflicts.append(rel)
        decoded.append((rel, dest, data, _mode_owner_only(item.get("mode"))))
    if not confirm:
        return {
            "ok": not conflicts,
            "applied": False,
            "dry_run": True,
            "files": planned,
            "conflicts": conflicts,
        }
    if conflicts:
        raise RuntimeError("restore would overwrite existing files: " + ", ".join(conflicts))
    for rel, dest, data, mode in decoded:
        _safe_rel(rel)
        _write_owner_only(dest, data, mode=mode)
    return {"ok": True, "applied": True, "dry_run": False, "files": planned, "conflicts": []}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="anima.vault_backup")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--store", default=".anima")
    c.add_argument("--out", required=True)
    c.add_argument("--name", default="Vera")
    i = sub.add_parser("inspect")
    i.add_argument("bundle")
    r = sub.add_parser("restore")
    r.add_argument("bundle")
    r.add_argument("--target", required=True)
    r.add_argument("--confirm", action="store_true")
    r.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "create":
        print(json.dumps(create_bundle(args.store, args.out, name=args.name), indent=2))
    elif args.cmd == "inspect":
        print(json.dumps(inspect_bundle(args.bundle), indent=2))
    elif args.cmd == "restore":
        print(json.dumps(restore_bundle(args.bundle, args.target,
                                        confirm=args.confirm,
                                        overwrite=args.overwrite), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
