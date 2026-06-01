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


def save_json(path, obj) -> None:
    """Write JSON atomically: a crash mid-write can never corrupt the file.

    The creature's whole continuity lives in these files — a half-written save
    would be its death. So we write a temp file and atomically rename over the
    target (os.replace is atomic on the same filesystem).
    """
    path = str(path)
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

