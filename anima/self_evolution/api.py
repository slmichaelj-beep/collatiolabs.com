"""self_evolution.api — assemble the /self dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from anima.company import storage
from . import observe as _obs, heal as _heal, evolve as _ev


def dashboard(name: str, store: Path | None = None) -> dict:
    sm = storage.load(name, "self_map", store, default=None)
    if not sm:
        sm = _obs.self_map(name, store=store)
    doctrine = storage.load(name, "self_doctrine", store, default={"incidents": [], "clean": True})
    return {
        "ok": True,
        "self_map": {"systems": len(sm["systems"]), "frozen_systems": sm["frozen_systems"]},
        "frozen_systems": sm["frozen_systems"],
        "self_heal_policy": _heal.policy(),
        "autonomy": _ev.autonomy_policy(),
        "doctrine": {"clean": doctrine.get("clean", True), "incidents": doctrine.get("incidents", [])},
        "honesty": "self-modification is governed; the constitutional core (identity/authority/budget/"
                   "safety/truth/observation/Diamond/rollback) is frozen and never auto-mutated; "
                   "repairs need diagnosis + rollback; promotion needs certs + Diamond.",
    }
