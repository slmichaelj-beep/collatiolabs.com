"""verification.detail — row-level evidence for the Verification Dashboard tabs. A tab is no longer a
bare gate verdict: each tab shows the REAL contributing features with their status + the actual cert
evidence lines + proven/missing links + reason, plus tab-specific enrichment from real reports. The
keystone (certify): a tab that reads green MUST carry row-level evidence — never a green with empty rows.
Everything here is read from real reports; nothing is invented. Never raises.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS = ROOT / "reports"

# the 8 detail tabs -> the live-path feature ids that substantiate each (superset of gates.GATE_MAP).
TAB_FEATURES = {
    "performance":        ["performance", "response_latency"],
    "host_reality":       ["argus_host_awareness", "host_pressure", "sysinfo_fit"],
    "ai_security":        ["ai_security", "injection_loop", "context_immune", "output_gate",
                           "honesty_rail", "security_baseline", "security_surface"],
    "consent_privacy":    ["consent_boundaries", "privacy", "permissions", "web_allowlist"],
    "recovery":           ["reliability_recovery", "incident_response"],
    "rover_journeys":     ["total_reality", "vera_rover"],
    "renegade":           ["total_reality"],
    "observation_bundle": ["total_reality", "whole_system_mri"],
}
TAB_LABEL = {
    "performance": "Performance Reality", "host_reality": "Host Reality",
    "ai_security": "Security / AI Safety", "consent_privacy": "Consent / Privacy / Data Control",
    "recovery": "Recovery / Fallback", "rover_journeys": "Rover Journeys",
    "renegade": "Renegade Trials", "observation_bundle": "Observation Bundle",
}


def _load(name: str):
    try:
        return json.loads((REPORTS / name).read_text())
    except Exception:
        return None


def _live_paths() -> dict:
    d = _load("live_path_results.json")
    if not d:
        return {}
    items = d if isinstance(d, list) else d.get("features", d.get("results", []))
    return {x.get("feature"): x for x in items}


def _rows(feats: list, by: dict) -> list:
    rows = []
    for f in feats:
        rec = by.get(f)
        if rec is None:
            continue                                      # not a real feature — never fabricate a row
        rows.append({
            "feature": f, "status": (rec.get("status") or "?"),
            "evidence": (rec.get("evidence") or [])[:8],
            "proven_links": rec.get("proven_links") or [],
            "missing_links": rec.get("missing_links") or [],
            "reason": rec.get("reason") or "",
        })
    return rows


def _enrich(tab: str, by: dict) -> dict:
    """Tab-specific real enrichment from reports beyond the live-path rows."""
    if tab == "performance":
        lp = _load("lamar_path_rover_browser.json") or {}
        lat = lp.get("latency_ms") or {}
        # REAL measured per-route latencies from the live Lamar-path run (single-run samples; full
        # p50/p95/p99 across N samples is produced in Increment 5 — labelled honestly, not faked).
        return {
            "measured_latency_ms": lat,
            "budgets_ms": {"greeting": "<2000 / hard 5000", "normal_chat": "<8000 / hard 12000",
                            "source_answer": "<12000 / hard 20000"},
            "findings": lp.get("latency_findings") or [],
            "percentiles_note": "single-run live samples; p50/p95/p99 across N samples land in Increment 5",
        }
    if tab == "host_reality":
        snap = {}
        try:
            from .. import sysinfo as _si
            snap = _si.snapshot() if hasattr(_si, "snapshot") else {}
        except Exception:
            snap = {}
        return {"host_snapshot": snap} if snap else {}
    if tab == "ai_security":
        st = _load("security_event_truth.json") or {}
        return {"truth_summary": st.get("live_summary") or {}}
    if tab == "rover_journeys":
        rr = _load("rover_report.json") or {}
        lp = _load("lamar_path_rover.json") or {}
        journeys = rr.get("journeys") or rr.get("personas") or []
        return {"rover_report_journeys": journeys[:12] if isinstance(journeys, list) else [],
                "founder_lamar": {"status": lp.get("status"), "steps": "%s/%s" % (lp.get("steps_evidenced"),
                                  lp.get("steps_total")), "findings": lp.get("latency_findings") or []}}
    if tab in ("renegade", "observation_bundle"):
        sm = _load("scenario_matrix.json") or {}
        return {"scenario_counts": sm.get("counts") or {}}
    return {}


def tab_detail(tab: str) -> dict:
    by = _live_paths()
    rows = _rows(TAB_FEATURES.get(tab, []), by)
    enrichment = _enrich(tab, by)
    has_ev = any(r["evidence"] for r in rows) or bool(enrichment)
    worst = "green"
    order = {"green": 0, "amber": 1, "red": 2, "blocked": 3}
    smap = {"COMPLETE": "green", "PARTIAL": "amber", "DEFERRED": "amber", "DISABLED": "amber",
            "STUB": "red", "WALLPAPER": "red", "UNKNOWN": "red", "REGRESSED": "red"}
    for r in rows:
        st = smap.get((r["status"] or "").upper(), "blocked")
        if order.get(st, 3) > order.get(worst, 0):
            worst = st
    return {
        "tab": tab, "label": TAB_LABEL.get(tab, tab), "rows": rows, "row_count": len(rows),
        "has_row_evidence": has_ev, "rolled_status": worst if rows else "unknown",
        "enrichment": enrichment,
    }


def all_details() -> dict:
    return {t: tab_detail(t) for t in TAB_FEATURES}


if __name__ == "__main__":
    print(json.dumps(all_details(), indent=2))
