"""secure_store — one path for private Vera persistence.

This is the first sovereign-vault substrate: JSON/text plus append-only JSONL
that honors anima.crypto's at-rest encryption marker when ANIMA_KEY is set.

Important shape: append-only ledgers encrypt one JSON object per physical line,
so they stay appendable while raw disk bytes no longer expose private text.
"""
from __future__ import annotations

import json
import os
import base64
from pathlib import Path

from . import crypto, util

_BYTES_MARKER = "ANIMABYTES1:"


def save_text(path: str | Path, text: str) -> None:
    util.save_text(path, text)


def load_text(path: str | Path, default=None):
    return util.load_text(path, default)


def save_json(path: str | Path, obj) -> None:
    util.save_json(path, obj)


def load_json(path: str | Path, default=None):
    return util.load_json(path, default)


def save_export_text(path: str | Path, text: str, *, allow_plaintext: bool = False) -> None:
    """Save a user-portable export with encryption by default.

    Exports are meant to leave Vera, so plaintext is a real option. It must be explicit:
    callers pass allow_plaintext=True when they intentionally need a human/tool-readable
    JSON/JSONL artifact.
    """
    if allow_plaintext:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
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
        return
    if not crypto.enabled():
        raise RuntimeError(
            "encrypted export requires ANIMA_KEY or the macOS Keychain item 'anima'; "
            "pass allow_plaintext=True only for an intentional plaintext export")
    save_text(path, text)


def save_export_json(path: str | Path, obj, *, allow_plaintext: bool = False,
                     trailing_newline: bool = False) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    if trailing_newline:
        text += "\n"
    save_export_text(path, text, allow_plaintext=allow_plaintext)


def load_export_text(path: str | Path, default=None):
    return load_text(path, default)


def load_export_json(path: str | Path, default=None):
    text = load_export_text(path, None)
    if text is None:
        return default
    return json.loads(text)


def save_bytes(path: str | Path, data: bytes) -> None:
    """Save bytes through the text crypto layer without exposing raw binary at rest."""
    payload = _BYTES_MARKER + base64.b64encode(bytes(data or b"")).decode("ascii")
    util.save_text(path, payload)


def load_bytes(path: str | Path, default=None):
    """Load bytes saved by save_bytes, while tolerating legacy plaintext binary files."""
    p = Path(path)
    if not p.exists():
        return default
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    text = crypto.maybe_decrypt(text)
    if not text.startswith(_BYTES_MARKER):
        return raw
    return base64.b64decode(text[len(_BYTES_MARKER):].encode("ascii"))


def append_jsonl(path: str | Path, obj) -> None:
    """Append one JSON object as one encrypted-at-rest line when crypto is enabled."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False)
    sealed = crypto.maybe_encrypt(line)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(sealed + "\n")
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


def read_jsonl_lines(path: str | Path) -> list[str]:
    """Return decrypted physical JSONL lines.

    Mixed old plaintext and new encrypted lines are supported. Wrong/missing keys
    fail loud through crypto.maybe_decrypt rather than silently falling back.
    """
    p = Path(path)
    if not p.exists():
        return []
    out: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(crypto.maybe_decrypt(line))
    return out


def load_jsonl(path: str | Path, *, skip_bad: bool = False) -> list[dict]:
    out: list[dict] = []
    for line in read_jsonl_lines(path):
        try:
            out.append(json.loads(line))
        except Exception:
            if not skip_bad:
                raise
    return out
