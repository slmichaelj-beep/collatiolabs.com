"""observation.store — append-only observation event log: .anima/<name>.observation.jsonl.

Redirectable (module STORE) so hermetic certs sandbox it like every other store.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

STORE = Path(".anima")


def default_store() -> Path:
    env = os.environ.get("ANIMA_STORE")
    return Path(env) if env else STORE


def path_for(name: str, store: Path | None = None) -> Path:
    return (store or default_store()) / f"{name}.observation.jsonl"


def append(name: str, event: dict, store: Path | None = None) -> dict:
    p = path_for(name, store)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def load(name: str, store: Path | None = None, limit: int = 0) -> list[dict]:
    p = path_for(name, store)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out[-limit:] if limit else out
