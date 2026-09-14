"""patterns — the Pattern Observatory detectors + the Pattern object.

Phase 5 of the Vera moonshot.  This is the layer that turns *observation* into
*engineering work orders*:

    pattern  ->  evidence  ->  root cause  ->  recommended fix  ->  required cert

A `Pattern` is a recurring shape seen across turns and/or features, carried with
enough to act on it: a stable id, how often it recurs (``frequency``), how badly it
hurts (``severity`` P0/P1/P2), the ``evidence`` (turn_ids and/or feature refs that
prove it), the ``root_cause``, the ``recommended_fix``, the ``cert_required`` to
prove the fix, and the ``expected_improvement``.

``detect(traces, audit_results)`` runs every detector and returns the Patterns the
evidence supports — and ONLY those.  A detector that finds nothing returns nothing
(no false positives); a detector with no inputs degrades gracefully (empty + a note),
never crashes on a missing field.

Two evidence streams feed the detectors:

  1. Whole-System MRI traces (anima/whole_mri.all(name) — turn_id, route,
     vera/argus/quality/cost/safety).  We reuse anima.whole_mri_shape — the Phase 6/7
     library that already classifies a turn's SHAPE and emits per-turn work orders —
     as the per-turn detector primitive, then aggregate identical shapes into a named
     Pattern with a frequency.  We do NOT re-derive the shape math here.

  2. The Program Reality Audit (reports/live_path_results.json) — which already
     classifies each feature COMPLETE / PARTIAL / WALLPAPER with a root cause.  This
     is a PRIMARY input: a WALLPAPER/PARTIAL feature becomes a Pattern directly, with
     the audit's own root_cause as evidence.

------------------------------------------------------------------------------------
CANONICAL WORKED EXAMPLE — "source retrieved but not used"
------------------------------------------------------------------------------------
A turn is detected as `source_use` when a source was retrieved/labeled for it
(quality.source_labeled true, or a source chip / argus source label, or lerf objects
were used) but the answer did NOT route through the source (route != "source" /
backend != reference:recall / quality.source_used is false).  The reference-recall
seam was bypassed; the user got a model answer while a labeled source sat unused.

NOTE: this was just FIXED via the reference-recall seam, so on the CURRENT traces it
should be RARE (a source-routed turn now carries source_labeled=true and route=source).
We keep the detector precisely so a regression resurfaces as a ready-made work order:
the moment a future trace shows "labeled but route=llm / source_used=false", the
Observatory reproposes the source-recall build with its cert attached.
------------------------------------------------------------------------------------
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # the per-turn SHAPE library (reused, not duplicated)
    from . import whole_mri_shape as _shape
except Exception:  # pragma: no cover - allow direct-script execution
    import whole_mri_shape as _shape  # type: ignore

try:
    from . import root_cause as _rc
except Exception:  # pragma: no cover
    import root_cause as _rc  # type: ignore


# ===================================================================================
# The Pattern object — exactly the founder's schema.
# ===================================================================================
@dataclass
class Pattern:
    """A recurring shape, carried as a certifiable work order.

    Schema (the founder's):
      pattern_id, title, frequency, severity (P0|P1|P2),
      evidence [turn_ids / feature refs], root_cause, recommended_fix,
      cert_required [...], expected_improvement {...}.
    """
    pattern_id: str
    title: str
    frequency: int
    severity: str                       # "P0" | "P1" | "P2"
    evidence: List[Any] = field(default_factory=list)
    root_cause: str = ""
    recommended_fix: str = ""
    cert_required: List[str] = field(default_factory=list)
    expected_improvement: Dict[str, Any] = field(default_factory=dict)
    # Non-schema breadcrumb: where this came from ("audit:<feature>" / "traces").
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _from_remediation(
    pattern_id: str,
    *,
    frequency: int,
    evidence: List[Any],
    severity: Optional[str] = None,
    source: str = "",
    root_cause: Optional[str] = None,
    recommended_fix: Optional[str] = None,
    cert_required: Optional[List[str]] = None,
    expected_improvement: Optional[Dict[str, Any]] = None,
    title: Optional[str] = None,
) -> Pattern:
    """Stamp a Pattern from the canonical remediation map, allowing a detector to
    OVERRIDE specific fields (e.g. the audit supplies its own root_cause text, or a
    single-occurrence regression is graded P1 instead of the default).

    Keeping the remediation in one place (root_cause.py) means the report and the
    detector cannot drift on a known pattern's fix/cert."""
    rem = _rc.remediation_for(pattern_id)
    return Pattern(
        pattern_id=pattern_id,
        title=title or _rc.title_for(pattern_id),
        frequency=int(frequency),
        severity=severity or _rc.default_severity_for(pattern_id),
        evidence=list(evidence),
        root_cause=root_cause if root_cause is not None else rem["root_cause"],
        recommended_fix=recommended_fix if recommended_fix is not None else rem["recommended_fix"],
        cert_required=list(cert_required if cert_required is not None else rem["cert_required"]),
        expected_improvement=dict(
            expected_improvement if expected_improvement is not None else rem["expected_improvement"]
        ),
        source=source,
    )


# ===================================================================================
# Tiny safe accessors (mirror whole_mri_shape's tolerance).
# ===================================================================================
def _block(trace: Any, key: str) -> dict:
    if not isinstance(trace, dict):
        return {}
    b = trace.get(key)
    return b if isinstance(b, dict) else {}


def _as_bool(v: Any) -> Optional[bool]:
    return v if isinstance(v, bool) else None


def _short(turn_id: Any) -> str:
    return _shape._short(turn_id)


def _backend(trace: dict) -> str:
    """The backend string for a turn, tolerant of where the producer put it."""
    resp = _block(trace, "response") or _block(_block(trace, "vera"), "response")
    b = resp.get("backend") if isinstance(resp, dict) else None
    if not b:
        gen = _block(_block(trace, "vera"), "generation")
        b = gen.get("backend") or gen.get("model")
    return str(b or "")


# ===================================================================================
# AUDIT-FED detectors (PRIMARY input: reports/live_path_results.json).
#
# The audit already finds WALLPAPER / PARTIAL features WITH root causes. We map the
# named features onto canonical Patterns so each carries a certifiable work order.
# Feature name -> (pattern_id, severity override or None).
# ===================================================================================
_AUDIT_FEATURE_PATTERN = {
    "conversation_repair": ("conversation_repair", "P0"),
    "capability_truth": ("capability_truth", None),
    "source_aware_answering": ("source_use", None),
    "universal_knowledge_intake": ("uki_commit", None),
    "response_completeness": ("completeness", None),
}


def _audit_features(audit_results: Any) -> List[dict]:
    """Pull the per-feature list out of whatever audit shape we were handed.

    Accepts: the live_path_results.json dict ({"features": [...]}), a bare list of
    feature dicts, or None.  Never raises."""
    if isinstance(audit_results, dict):
        feats = audit_results.get("features")
        if isinstance(feats, list):
            return [f for f in feats if isinstance(f, dict)]
        return []
    if isinstance(audit_results, list):
        return [f for f in audit_results if isinstance(f, dict)]
    return []


def detect_from_audit(audit_results: Any) -> List[Pattern]:
    """Emit Patterns from the Program Reality Audit.

    A feature classified WALLPAPER or PARTIAL is a real, proven defect with a real
    root cause already written — promote it to a Pattern (frequency = 1 feature) and
    attach the canonical remediation.  COMPLETE / UNKNOWN features emit nothing.

    The marquee case: if live_path_results marks `conversation_repair` WALLPAPER (it
    does), this emits the P0 "Correction lost — memory known but not superseded"
    Pattern with the audit's root_cause and the conversation-repair cert."""
    out: List[Pattern] = []
    for feat in _audit_features(audit_results):
        name = feat.get("feature")
        status = str(feat.get("status", "")).upper()
        if name not in _AUDIT_FEATURE_PATTERN:
            continue
        # Only the broken / incomplete features become work orders.
        if status not in ("WALLPAPER", "PARTIAL", "REGRESSED"):
            continue

        pattern_id, sev_override = _AUDIT_FEATURE_PATTERN[name]

        # Build evidence: a feature ref + the audit's own reason + its evidence lines.
        evidence: List[Any] = [f"feature:{name}", f"status:{status}"]
        reason = feat.get("reason")
        ev_lines = feat.get("evidence") or []
        if isinstance(ev_lines, list):
            evidence.extend(str(e) for e in ev_lines[:4])
        missing = feat.get("missing_links") or []
        if isinstance(missing, list) and missing:
            evidence.append("missing_links:" + ",".join(str(m) for m in missing))

        # WALLPAPER on a contract-blocking feature is P0; PARTIAL keeps its default
        # unless the map names an override.
        if status == "WALLPAPER":
            severity = sev_override or "P0"
        elif status == "REGRESSED":
            severity = "P0"
        else:  # PARTIAL
            severity = sev_override or _rc.default_severity_for(pattern_id)

        # The audit's prose root cause is more specific than the generic map text —
        # prefer it, but KEEP the canonical fix + cert (that's the build to do).
        out.append(_from_remediation(
            pattern_id,
            frequency=1,
            evidence=evidence,
            severity=severity,
            source=f"audit:{name}",
            root_cause=str(reason) if reason else None,
        ))
    return out


# ===================================================================================
# TRACE-FED detectors (Whole-System MRI).  We REUSE whole_mri_shape per-turn, then
# aggregate identical shapes into named Patterns with a frequency.
# ===================================================================================

def _source_retrieved_but_not_used(trace: dict) -> bool:
    """The canonical detector. A source was retrieved/labeled for the turn, but the
    answer did NOT route through it.

    Positive evidence of availability:
        quality.source_labeled true, OR a source chip / argus source label, OR
        cost.lerf_objects_used > 0, OR vera.* carries sources.
    Evidence the source was NOT used:
        route not in {source, reference, hybrid}, backend != reference:recall, and
        quality.source_used is not True.

    Conservative: fires only when availability is positive AND use is clearly absent.
    """
    q = _block(trace, "quality")
    labeled = _as_bool(q.get("source_labeled")) is True
    chip = bool(q.get("source_chip") or q.get("source_chips"))
    argus = _block(trace, "argus")
    argus_src = bool(argus.get("source_labeled") or argus.get("sources"))
    available = labeled or chip or argus_src or _shape._sources_were_available(trace)
    if not available:
        return False

    # Was the source actually used?
    used = _as_bool(q.get("source_used"))
    if used is True:
        return False
    route = trace.get("route")
    if route in ("source", "reference", "hybrid"):
        return False
    if "reference:recall" in _backend(trace):
        return False
    # Available, and no positive signal that it was used -> retrieved-but-not-used.
    return True


def detect_source_use(traces: List[dict]) -> List[Pattern]:
    """Aggregate the canonical 'source retrieved but not used' shape into a Pattern.

    On post-fix traces this should be empty (source-routed turns carry
    source_labeled=true AND route=source). A future regression repopulates it."""
    hits = [t for t in traces if isinstance(t, dict) and _source_retrieved_but_not_used(t)]
    if not hits:
        return []
    evidence = [
        {"turn_id": t.get("turn_id"), "route": t.get("route"),
         "source_labeled": _block(t, "quality").get("source_labeled"),
         "source_used": _block(t, "quality").get("source_used"),
         "backend": _backend(t)}
        for t in hits
    ]
    return [_from_remediation(
        "source_use",
        frequency=len(hits),
        evidence=evidence,
        source="traces",
    )]


# --- the shape-derived families: map a whole_mri_shape suggested_action onto a
#     canonical pattern_id, then aggregate. This is the REUSE seam. -----------------
_ACTION_TO_PATTERN = {
    "Route this shape to LERF / reduce retrieval.": "llm_vs_deterministic",
    "Avoid the LLM for this shape.": "llm_vs_deterministic",
    "Improve source labels.": "source_use",
    "Fix completeness (the reply was too thin).": "completeness",
    "Strengthen the final gate.": "completeness",
    "Investigate host contention during this turn shape.": "host_resource_spike",
    "Cache an Argus call (reuse one /mri snapshot).": "retrieval_depth_cost",
}


def detect_from_shapes(traces: List[dict]) -> List[Pattern]:
    """Run whole_mri_shape.work_orders over the batch and fold identical shapes into
    named Patterns.

    whole_mri_shape already decides, per turn and never fabricated, that a turn was
    slow+llm-on-a-simple-shape / source-unlabeled / gate-stripped / incomplete /
    host-heavy / expensive-with-redundant-argus.  We group those per-turn orders by
    the canonical pattern they belong to, set frequency = #turns, and stamp the
    remediation.  Patterns already covered by the dedicated source-use detector are
    de-duplicated by turn_id so a turn is not double-counted."""
    if not traces:
        return []
    try:
        orders = _shape.work_orders(traces)
    except Exception:
        orders = []
    if not orders:
        return []

    grouped: Dict[str, Dict[str, Any]] = {}
    for o in orders:
        action = o.get("suggested_action") or ""
        pid = _ACTION_TO_PATTERN.get(action)
        if not pid:
            continue
        g = grouped.setdefault(pid, {"turn_ids": [], "evidence": []})
        tid = o.get("turn_id")
        if tid in g["turn_ids"]:
            continue
        g["turn_ids"].append(tid)
        g["evidence"].append({
            "turn_id": tid,
            "shape": o.get("shape"),
            "issue": o.get("issue"),
            "detail": o.get("evidence"),
        })

    out: List[Pattern] = []
    for pid, g in grouped.items():
        out.append(_from_remediation(
            pid,
            frequency=len(g["turn_ids"]),
            evidence=g["evidence"],
            source="traces",
        ))
    return out


# ===================================================================================
# CROSS-SOURCE detectors that read a store directly (intake / capability) and degrade
# gracefully when the store is absent or empty.
# ===================================================================================

def detect_uki_not_committed(name: Optional[str], audit_results: Any = None) -> List[Pattern]:
    """UKI planned but not committed: intake records with committed=false /
    parse_status needs_dependency (the URL/PDF gap).

    Reads anima.intake_queue.queue(name) if available. On the real store every record
    may be committed (clean) -> empty. Never raises; missing module/store -> empty."""
    if not name:
        return []
    records: List[dict] = []
    try:
        from . import intake_queue as _iq  # type: ignore
        records = list(_iq.queue(name) or [])
    except Exception:
        try:
            import intake_queue as _iq  # type: ignore
            records = list(_iq.queue(name) or [])
        except Exception:
            return []

    pending: List[dict] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        committed = r.get("committed")
        prov = r.get("provenance") if isinstance(r.get("provenance"), dict) else {}
        parse_status = r.get("parse_status") or prov.get("parse_status")
        needs_dep = (parse_status == "needs_dependency")
        state = str(r.get("state", ""))
        # Uncommitted, OR explicitly stalled on a missing dependency, OR a non-terminal
        # state that never reached durable commit.
        if committed is False or needs_dep:
            pending.append(r)
        elif committed is None and state and state not in ("active",):
            pending.append(r)

    if not pending:
        return []
    evidence = [
        {"source_id": r.get("source_id"), "title": r.get("title"),
         "detected_type": r.get("detected_type"), "committed": r.get("committed"),
         "state": r.get("state")}
        for r in pending
    ]
    return [_from_remediation(
        "uki_commit",
        frequency=len(pending),
        evidence=evidence,
        source="intake_queue",
    )]


# ===================================================================================
# The merge + the public entry point.
# ===================================================================================

def _merge(patterns: List[Pattern]) -> List[Pattern]:
    """Collapse duplicate pattern_ids that arrived from different streams (e.g. the
    audit AND the traces both flagged `source_use`) into one Pattern: union the
    evidence, sum the distinct frequency, and keep the strongest (lowest-rank)
    severity.  Stable order: by severity, then by frequency desc, then by id."""
    by_id: Dict[str, Pattern] = {}
    for p in patterns:
        cur = by_id.get(p.pattern_id)
        if cur is None:
            by_id[p.pattern_id] = Pattern(
                pattern_id=p.pattern_id, title=p.title, frequency=p.frequency,
                severity=p.severity, evidence=list(p.evidence), root_cause=p.root_cause,
                recommended_fix=p.recommended_fix, cert_required=list(p.cert_required),
                expected_improvement=dict(p.expected_improvement), source=p.source,
            )
            continue
        # Merge into the existing one.
        cur.frequency += p.frequency
        cur.evidence.extend(p.evidence)
        # Strongest severity wins.
        if _rc.severity_rank(p.severity) < _rc.severity_rank(cur.severity):
            cur.severity = p.severity
        # Prefer a concrete (audit-supplied) root cause over the generic map text.
        if p.source.startswith("audit:") and p.root_cause:
            cur.root_cause = p.root_cause
        if p.source and p.source not in cur.source:
            cur.source = (cur.source + "+" + p.source) if cur.source else p.source

    merged = list(by_id.values())
    merged.sort(key=lambda x: (_rc.severity_rank(x.severity), -x.frequency, x.pattern_id))
    return merged


def detect(traces: Optional[List[dict]], audit_results: Any, *,
           name: Optional[str] = None) -> List[Pattern]:
    """Run every detector and return the ranked, de-duplicated list of Patterns.

    Inputs:
      traces        — list of Whole-System MRI trace dicts (anima.whole_mri.all(name)).
                      May be None/empty: trace detectors degrade to nothing.
      audit_results — the Program Reality Audit (live_path_results.json dict or its
                      "features" list). PRIMARY input. May be None.
      name          — creature name, used by store-reading detectors (intake/UKI).

    Returns Patterns sorted P0 first.  Emits a Pattern only when the evidence supports
    it — never fabricated.  Never raises on a missing field or absent store."""
    traces = [t for t in (traces or []) if isinstance(t, dict)]
    found: List[Pattern] = []

    # 1. The audit is primary — it already proved the defects with root causes.
    found.extend(detect_from_audit(audit_results))

    # 2. The canonical trace detector (source retrieved but not used).
    found.extend(detect_source_use(traces))

    # 3. The reused per-turn SHAPE families (llm-vs-deterministic, completeness,
    #    host spike, retrieval-depth cost, source labeling).
    found.extend(detect_from_shapes(traces))

    # 4. Store-reading cross-source detectors.
    found.extend(detect_uki_not_committed(name, audit_results))

    return _merge(found)


# ===================================================================================
# Convenience loaders for the CLI (kept here so the CLI stays thin).
# ===================================================================================

def load_audit(reports_dir: Path) -> Optional[dict]:
    """Load the Program Reality Audit from reports/. Prefers live_path_results.json
    (the per-feature classifier output); never raises."""
    for fname in ("live_path_results.json", "program_reality_audit.json"):
        p = Path(reports_dir) / fname
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


__all__ = [
    "Pattern",
    "detect",
    "detect_from_audit",
    "detect_source_use",
    "detect_from_shapes",
    "detect_uki_not_committed",
    "load_audit",
]
