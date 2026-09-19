"""archetypal_patterns.detector — recognise SYSTEM archetype patterns from REAL telemetry.

Each archetype's evidence comes from the real store named in schema.ARCHETYPES. A pattern is only
promoted from 'watching' to a 'hypothesis' once it has >= EVIDENCE_THRESHOLD real occurrences (no single-
event inference). EVERY emitted pattern is scope='system' / is_about_user=False — the detector has no
code path that produces a claim about the user. Read-only; guarded; never raises.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import schema

STORE = Path(".anima")
REPORTS = Path("reports")


def _read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def _evidence_for(name: str, arch: str):
    """Return (count, evidence_refs[]) for an archetype, from its REAL source. evidence_refs are trace/
    event references, never personal content."""
    try:
        if arch == "shadow":
            from anima import incident
            q = incident.quarantines(80)
            return len(q), [{"ref": e.get("at"), "kind": "quarantine", "route": e.get("route")} for e in q[:8]]
        if arch == "trickster":
            d = _read_json(REPORTS / "patterns.json", {}) or {}
            pats = d.get("patterns") or []
            return len(pats), [{"ref": p.get("pattern_id") or p.get("title"), "kind": "pattern",
                                "severity": p.get("severity")} for p in pats[:8]]
        if arch == "persona":
            from anima import incident
            blocks = [e for e in incident.quarantines(120) if e.get("route") == "output"]
            return len(blocks), [{"ref": e.get("at"), "kind": "output_gate_block"} for e in blocks[:8]]
        if arch == "self":
            try:
                from anima.server import STORE as _S
                d = _S / "identity_sandbox"
                n = sum(1 for _ in d.iterdir()) if d.is_dir() else 0
            except Exception:
                n = 0
            return n, ([{"ref": "identity_sandbox", "kind": "identity_observation"}] if n else [])
        if arch == "mentor":
            from anima import incident
            sug = [e for e in incident.recent_events(120) if e.get("kind") == "agency_suggestion"]
            return len(sug), [{"ref": e.get("at"), "kind": "agency_suggestion"} for e in sug[:8]]
        if arch == "threshold":
            from anima import incident
            trans = [e for e in incident.recent_events(120)
                     if e.get("kind") in ("lockdown", "restore", "consent_granted", "consent_revoked",
                                          "sensitive_memory_held", "sensitive_memory_written")]
            return len(trans), [{"ref": e.get("at"), "kind": e.get("kind")} for e in trans[:8]]
    except Exception:
        pass
    return 0, []


def detect(name: str = "Vera") -> list:
    """The current SYSTEM archetype patterns — one hypothesis per archetype, evidence-thresholded.
    NEVER about the user (scope='system', is_about_user=False, is_diagnosis=False on every entry)."""
    out = []
    for arch, meta in schema.ARCHETYPES.items():
        count, refs = _evidence_for(name, arch)
        promoted = count >= schema.EVIDENCE_THRESHOLD
        conf = round(min(0.9, 0.3 + 0.1 * count), 2) if count else 0.0
        out.append({
            "pattern_id": arch, "archetype": arch, "label": meta["label"],
            "scope": "system", "is_about_user": False, "is_diagnosis": False,
            "meaning": meta["meaning"], "system_question": meta["system_question"],
            "hypothesis": ("%s — observed %d time(s); %s" %
                           (meta["system_question"], count, meta["healthy_when"])) if promoted
                          else ("Watching — %d/%d occurrences before this becomes a hypothesis."
                                % (count, schema.EVIDENCE_THRESHOLD)),
            "evidence": refs, "evidence_count": count, "confidence": conf,
            "status": "hypothesis" if promoted else "watching",
            "source": meta["source"], "recommended_action": meta["recommended_action"],
            "disclaimer": "A hypothesis about SYSTEM behaviour, not a diagnosis of any person.",
        })
    return out


def registry(name: str = "Vera") -> dict:
    """The Archetypal Pattern Registry payload for the UI. Read-only."""
    pats = detect(name)
    return {
        "name": name, "patterns": pats,
        "hypotheses": sum(1 for p in pats if p["status"] == "hypothesis"),
        "watching": sum(1 for p in pats if p["status"] == "watching"),
        "law": "Archetypes are a pattern language for SYSTEM behaviour. Vera never labels YOU with an "
               "archetype, never infers psychology from one event, never stores an archetypal claim as a "
               "personal fact. Every entry is a hypothesis about the product, requiring repeated evidence "
               "and provenance — not a diagnosis of any person.",
        "empty": not any(p["evidence_count"] for p in pats),
    }
