"""constitution — the laws the creature is built to obey, as enforced code.

A written law is decoration; an *enforced* law is architecture. This module is the
machine-readable seat of ANIMA LAW 001 — NEVER LOSE CONTINUITY. The law text lives
here verbatim as a constant so every subsystem reads from one source of truth, and
the single privileged operation the law permits — discarding information — is gated
through `approved_loss()`, which REFUSES to be decorative: it demands a named higher
approver and writes an immutable, append-only record of exactly what was given up,
why, and on whose authority. No approval, no record; no record, no loss.

Pure and dependency-light: standard library only (json, os, datetime, pathlib).
It writes one append-only file (`.anima/<name>.continuity.jsonl`) and reads nothing
back that could be lost. Importing it has no side effects.

    from anima import constitution
    constitution.approved_loss(
        subsystem="portrait.consolidate",
        what="raw chat.jsonl for Vera (2026-06-04, 41 turns)",
        why="distilled into portrait; raw transcript no longer needed verbatim",
        approver="sleep-cycle/operator",
    )
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Where the creature's life is kept. Mirrors anima.portrait / anima.memory_lirf so
# the continuity ledger sits beside the things it protects. Overridable for tests.
STORE = Path(os.environ.get("ANIMA_STORE", ".anima"))

LAW_ID = "ANIMA LAW 001"
LAW_TITLE = "NEVER LOSE CONTINUITY"

# ---------------------------------------------------------------------------------
# THE LAW — verbatim. Do not paraphrase, soften, or "improve" this text. Subsystems
# and tests read THIS constant; if the words ever need to change, they change here,
# once, and the change is itself a loss that should be recorded.
# ---------------------------------------------------------------------------------
LAW_001 = (
    "ANIMA LAW 001 — NEVER LOSE CONTINUITY. "
    "The system may change models, prompts, storage engines, architectures, "
    "operating systems, cloud providers, devices, and interfaces. The relationship "
    "must survive all of them. No subsystem may discard information unless a higher "
    "subsystem explicitly approves the loss. "
    "Unknown > Lost. Compressed > Forgotten. Archived > Deleted. Observed > Assumed."
)

# The three corollaries, named, so code can reference them individually. Each maps a
# tempting destructive shortcut to the strictly-better preserving alternative.
COROLLARIES = (
    "Unknown > Lost.",        # Keep a fact you can no longer interpret rather than erasing it.
    "Compressed > Forgotten.",  # Summarise/distil rather than drop; capture meaning before raw goes.
    "Archived > Deleted.",    # Move out of the hot path rather than destroy; cold storage beats /dev/null.
    "Observed > Assumed.",    # A trait/value from EVIDENCE outranks one assumed; never assert past what was observed.
)

# Machine-readable gloss-ordering for anyone who wants to assert "we chose the better
# side": preserving verbs rank strictly above their destructive twin.
PRESERVE_OVER_DESTROY = {
    "lost": "unknown",        # prefer Unknown   over Lost
    "forgotten": "compressed",  # prefer Compressed over Forgotten
    "deleted": "archived",    # prefer Archived  over Deleted
}


def law_text() -> str:
    """The full, verbatim law. Single source of truth for prompts, docs, and tests."""
    return LAW_001


def corollaries() -> tuple[str, ...]:
    """The three preservation corollaries, in order."""
    return COROLLARIES


def continuity_log_path(name: str) -> Path:
    """Append-only ledger of every explicitly-approved information loss for `name`."""
    return STORE / f"{name}.continuity.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def approved_loss(
    subsystem: str,
    what: str,
    why: str,
    approver: str,
    *,
    name: str = "Vera",
    detail: dict | None = None,
) -> dict:
    """Record an EXPLICITLY-APPROVED discard of information — the one carve-out the
    law allows ("...unless a higher subsystem explicitly approves the loss").

    This is what makes the law real rather than decorative: a subsystem that wants to
    drop data must (1) name itself, (2) state exactly *what* it is giving up, (3) state
    *why*, and (4) name the *higher* authority that approved it — and the act is written
    to an append-only ledger so the loss is itself never silently lost. Call this
    immediately BEFORE the destructive operation, never after.

    All four reasons are required and must be non-empty; an unapproved or unexplained
    loss raises `ValueError` (the law has no silent path). Returns the recorded entry.

    Failures to write the ledger are NOT swallowed — if we cannot record the loss, the
    caller must not proceed with the loss.
    """
    subsystem = (subsystem or "").strip()
    what = (what or "").strip()
    why = (why or "").strip()
    approver = (approver or "").strip()
    missing = [k for k, v in (
        ("subsystem", subsystem), ("what", what), ("why", why), ("approver", approver),
    ) if not v]
    if missing:
        raise ValueError(
            f"{LAW_ID}: a loss requires explicit {', '.join(missing)} — "
            "no subsystem may discard information without naming what, why, and a "
            "higher approver. Refusing to record (and therefore to permit) the loss."
        )

    entry = {
        "law": LAW_ID,
        "at": _now_iso(),
        "subsystem": subsystem,
        "what": what,
        "why": why,
        "approver": approver,
    }
    if detail:
        entry["detail"] = detail

    # Append-only, atomic-ish: O_APPEND keeps concurrent writers from clobbering and
    # never truncates an existing ledger. We intentionally do NOT use a rewrite-the-
    # whole-file pattern here — the ledger of losses must itself obey Archived>Deleted.
    path = continuity_log_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return entry


def approved_losses(name: str = "Vera") -> list[dict]:
    """Read back the continuity ledger (oldest→newest). Empty if nothing was ever lost
    under approval — which, under the law, is the desired default."""
    path = continuity_log_path(name)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            # A corrupt line is itself information — keep it visible rather than drop it.
            out.append({"_unparsed": line})
    return out


__all__ = [
    "LAW_ID",
    "LAW_TITLE",
    "LAW_001",
    "COROLLARIES",
    "PRESERVE_OVER_DESTROY",
    "law_text",
    "corollaries",
    "approved_loss",
    "approved_losses",
    "continuity_log_path",
]
