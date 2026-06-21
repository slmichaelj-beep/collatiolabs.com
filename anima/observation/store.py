"""observation.store — append-only observation event log: .anima/<name>.observation.jsonl.

Redirectable (module STORE) so hermetic certs sandbox it like every other store.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from anima import secure_store

STORE = Path(".anima")


def default_store() -> Path:
    env = os.environ.get("ANIMA_STORE")
    return Path(env) if env else STORE


def path_for(name: str, store: Path | None = None) -> Path:
    return (store or default_store()) / f"{name}.observation.jsonl"


def append(name: str, event: dict, store: Path | None = None) -> dict:
    secure_store.append_jsonl(path_for(name, store), event)
    return event


def load(name: str, store: Path | None = None, limit: int = 0) -> list[dict]:
    p = path_for(name, store)
    if not p.exists():
        return []
    out = []
    for line in secure_store.read_jsonl_lines(p):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out[-limit:] if limit else out
