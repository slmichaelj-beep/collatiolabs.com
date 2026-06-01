"""Small shared helpers."""

from __future__ import annotations

import json
import os
import tempfile


def label(title: str) -> None:
    """Name this process clearly in Activity Monitor / ps, so nothing anima runs
    shows up as a generic 'python3'. Best-effort: needs `setproctitle` installed.
    """
    try:
        import setproctitle
        setproctitle.setproctitle(f"anima[{title}]")
    except Exception:
        pass


def save_text(path, text: str) -> None:
    """Write text atomically (temp file + rename), so a crash can't corrupt it."""
    path = str(path)
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_json(path, obj) -> None:
    """Write JSON atomically. The creature's continuity lives in these files — a
    half-written save would be its death — so we never write in place."""
    save_text(path, json.dumps(obj))

