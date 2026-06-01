"""
crypto — optional at-rest encryption for the creature's private files.

If ANIMA_KEY is set in the environment, everything anima writes under .anima/
(her weights, memory, Portrait) is encrypted with a key derived from that
passphrase, so the files — including backup copies on an external drive — are
unreadable without it. If ANIMA_KEY is unset, files stay plaintext (no change).

THREAT MODEL, honestly:
  * It protects the files if they're copied off the machine — a lost/stolen
    backup drive, another user account — and adds defense-in-depth over FileVault.
  * It does NOT protect against someone who already has your unlocked Mac AND the
    passphrase (the running server needs it in memory).
  * If you lose the passphrase, the files are unrecoverable. The key IS the
    creature. Store it somewhere safe and separate from the backups.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

_MARKER = "ANIMAENC1:"
_STORE = Path(".anima")
_fernet = None
_resolved = False


def _salt() -> bytes:
    _STORE.mkdir(exist_ok=True)
    p = _STORE / ".keysalt"
    if p.exists():
        return p.read_bytes()
    s = os.urandom(16)
    p.write_bytes(s)
    return s


def _cipher():
    global _fernet, _resolved
    if _resolved:
        return _fernet
    _resolved = True
    pw = os.environ.get("ANIMA_KEY")
    if not pw:
        return None
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except Exception as e:
        # fail loud: never silently store plaintext when the user asked for encryption
        raise SystemExit(
            "ANIMA_KEY is set but the 'cryptography' package isn't working "
            f"({e}). Install it:  pip install --force-reinstall cryptography\n"
            "Refusing to run unencrypted while a key is set.")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_salt(), iterations=200_000)
    _fernet = Fernet(base64.urlsafe_b64encode(kdf.derive(pw.encode())))
    return _fernet


def enabled() -> bool:
    return _cipher() is not None


def maybe_encrypt(text: str) -> str:
    c = _cipher()
    return _MARKER + c.encrypt(text.encode()).decode() if c else text


def maybe_decrypt(raw: str) -> str:
    if not raw.startswith(_MARKER):
        return raw                          # plaintext (pre-encryption) — pass through
    c = _cipher()
    if c is None:
        raise RuntimeError("this file is encrypted but ANIMA_KEY is not set")
    try:
        return c.decrypt(raw[len(_MARKER):].encode()).decode()
    except Exception:
        raise RuntimeError("ANIMA_KEY does not match this file (wrong passphrase)")
