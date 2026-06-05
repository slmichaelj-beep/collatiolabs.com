"""Small shared helpers: process labelling and atomic, optionally-encrypted I/O."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import crypto


def label(title: str) -> None:
    """Name this process clearly in Activity Monitor / ps, so nothing anima runs
    shows up as a generic 'python3'. Best-effort: needs `setproctitle` installed.
    """
    try:
        import setproctitle
        setproctitle.setproctitle(f"anima[{title}]")
    except Exception:
        pass


def _atomic_write(path, text: str) -> None:
    """Write text atomically (temp file + rename) so a crash can't corrupt it.

    Durability: the bytes are flushed and fsync'd to the disk BEFORE os.replace, so a
    crash/power-loss in the window between write and rename cannot leave a zero-length or
    half-written file in place — the rename only ever publishes a fully-persisted temp file
    (the failure mode the old docstring promised but didn't actually guard). fsync is
    best-effort: on the rare platform/FS where it isn't available we still get the atomic
    rename, just without the extra durability barrier — never a crash."""
    path = str(path)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            try:
                os.fsync(f.fileno())          # persist the data before we publish it
            except OSError:
                pass                          # fsync unsupported here — atomic rename still holds
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_text(path, text: str) -> None:
    _atomic_write(path, crypto.maybe_encrypt(text))


def save_json(path, obj) -> None:
    """Atomic + (if ANIMA_KEY set) encrypted JSON write. The creature's continuity
    lives in these files — a half-written or readable-anywhere save would be a
    problem — so writes are atomic and optionally sealed."""
    save_text(path, json.dumps(obj))


def load_text(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return crypto.maybe_decrypt(p.read_text())
    except OSError:
        return default


def load_json(path, default=None):
    text = load_text(path, None)
    if text is None:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default
