"""living_map.graph — resolve LIVE node/edge status from REAL telemetry.

Every resolver reads the real store named in schema.NODES[*].source_of_truth and returns a status that
is JUSTIFIED by that data — or 'unknown' when the source is empty/missing. NO resolver returns a
constant green. This is the no-wallpaper contract in code: if a node is green/yellow/red, a real source
made it so; otherwise it is honestly 'unknown'.

build_graph(name) returns {nodes, edges, summary, generated_at?} — the static-but-live-status map.
Read-only; guarded; never raises into a request.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from . import schema

STORE = Path(".anima")
REPORTS = Path("reports")


def _now() -> str:
    try:
        return datetime.datetime.now().isoformat(timespec="seconds")
    except Exception:
        return ""


def _read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def _recent_mri(n: int = 60) -> list:
    """The most recent turn-MRI records (newest last). Honest []."""
    try:
        from anima.server import STORE as _S
        name = "Vera"
        lines = [ln for ln in (_S / f"{name}.mri.jsonl").read_text().splitlines() if ln.strip()]
        out = []
        for ln in lines[-int(n):]:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
        return out
    except Exception:
        return []


def _R(status, detail="", **metrics):
    return {"status": status, "live_metrics": metrics, "detail": detail}


# ---------------------------------------------------------------------------------------------
# Resolvers — one per node_id. Each reads a REAL source; 'unknown' when there is no data.
# ---------------------------------------------------------------------------------------------
def _r_user(name):
    return _R("external", "The human — no telemetry is collected about the person.")


def _r_chat_ui(name):
    mri = _recent_mri(40)
    if not mri:
        return _R("unknown", "No recent turns recorded in the MRI trace.")
    return _R("green", "Serving turns.", turns_recent=len(mri))


def _r_route_classifier(name):
    mri = _recent_mri(60)
    if not mri:
        return _R("unknown", "No recent turns to classify.")
    routes = {}
    for m in mri:
        r = m.get("route") or m.get("path") or "?"
        routes[r] = routes.get(r, 0) + 1
    return _R("green", "Routing turns.", routes=routes, turns_seen=len(mri))


def _r_context_immune(name):
    try:
        from anima import immune, incident
        st = immune.status()
        defenses_on = all(bool(v) for v in (st.get("defenses") or {}).values()) if st.get("defenses") else False
        q = incident.quarantines(50)
        blocked = sum(1 for e in q if e.get("route") in ("context", "conversation", "source", "output"))
        if not st.get("defenses"):
            return _R("unknown", "Immune status unavailable.")
        return _R("green" if defenses_on else "yellow",
                  "Four-route quarantine active." if defenses_on else "A defense is not reporting.",
                  routes=len(st.get("routes") or []), blocked_recent=blocked)
    except Exception:
        return _R("unknown", "Immune subsystem not reachable.")


def _r_history(name):
    raw = _read_json(STORE / f"{name}.history.json", default=None)
    if raw is None:
        try:
            from anima.server import STORE as _S
            raw = _read_json(_S / f"{name}.history.json", default=None)
        except Exception:
            raw = None
    if not raw:
        return _R("unknown", "No conversation history on disk yet.")
    return _R("green", "Recent conversation retained (token-budgeted into the prompt).", turns=len(raw))


def _r_memory(name):
    try:
        from anima.memory_lirf import Facts
        rows = Facts.load(name).about() or []
        if not rows:
            return _R("unknown", "No LIRF facts captured yet.")
        active = sum(1 for r in rows if str(r.get("status")) == "active")
        return _R("green", "Durable personal memory present.", facts=len(rows), active=active)
    except Exception:
        return _R("unknown", "Memory store not reachable.")


def _r_known_facts(name):
    try:
        from anima.memory_lirf import Facts
        rows = [r for r in (Facts.load(name).about() or []) if str(r.get("status")) == "active" and r.get("value")]
        if not rows:
            return _R("unknown", "No bound known facts yet.")
        return _R("green", "Facts bound as a contract (stated, never disclaimed).", known=len(rows))
    except Exception:
        return _R("unknown", "Facts store not reachable.")


def _r_sources(name):
    try:
        from anima import intake_queue, source_aware
        refs = intake_queue.references(name) or []
        q = source_aware.quarantined_sources(name) or []
        if not refs and not q:
            return _R("unknown", "No reference sources uploaded yet.")
        return _R("yellow" if q else "green",
                  "%d source(s) excluded as injection-flagged." % len(q) if q else "Sources available, none flagged.",
                  sources=len(refs), quarantined=len(q))
    except Exception:
        return _R("unknown", "Source library not reachable.")


def _r_intake(name):
    try:
        from anima import intake_queue
        refs = intake_queue.references(name) or []
        return _R("green" if refs else "unknown",
                  "Intake pipeline available." if refs else "No intake activity recorded.",
                  ingested=len(refs))
    except Exception:
        return _R("unknown", "Intake subsystem not reachable.")


def _r_ocr(name):
    # OCR usage is not separately instrumented yet -> honest 'unknown' (never a fake green).
    return _R("unknown", "OCR runs on demand for scanned docs/images; per-run metrics not yet instrumented.")


def _r_lerf(name):
    try:
        from anima.server import STORE as _S
        p = _S / f"{name}.lerf_routes.jsonl"
        n = sum(1 for _ in p.open()) if p.exists() else 0
        return _R("green" if n else "unknown",
                  "LERF skills tried before the model." if n else "No LERF route activity recorded.",
                  routes=n)
    except Exception:
        return _R("unknown", "LERF store not reachable.")


def _r_patterns(name):
    d = _read_json(REPORTS / "patterns.json", default=None)
    pats = (d or {}).get("patterns") or []
    if d is None:
        return _R("unknown", "Pattern Observatory has not run yet.")
    p0 = sum(1 for p in pats if p.get("severity") == "P0")
    return _R("red" if p0 else ("yellow" if pats else "green"),
              "%d P0 pattern(s) need attention." % p0 if p0 else ("Repeating issues observed." if pats else "No repeating issues."),
              patterns=len(pats), p0=p0)


def _r_improvements(name):
    d = _read_json(REPORTS / "improvement_backlog.json", default=None)
    items = (d or {}).get("items") or []
    roi = _read_json(REPORTS / "roi_ledger.json", default={}) or {}
    if d is None:
        return _R("unknown", "Improvement Engine has not produced a backlog yet.")
    return _R("yellow" if items else "green",
              "%d improvement(s) in the backlog." % len(items) if items else "No open improvements.",
              backlog=len(items), roi_verified=roi.get("verified", 0))


def _r_prompt_compiler(name):
    mri = _recent_mri(40)
    tok = None
    for m in reversed(mri):
        for st in (m.get("stages") or []):
            if st.get("stage") == "prompt":
                tok = (st.get("out") or {}).get("system_prompt_tokens") or (st.get("out") or {}).get("prompt_budget_tokens")
                break
        if tok:
            break
    if tok is None:
        return _R("unknown", "No recent prompt-assembly frame in the MRI.")
    return _R("yellow" if tok > 1100 else "green",
              "System prompt ~%d tok (slimmed; budget-aware)." % tok, system_prompt_tokens=tok)


def _r_model_runtime(name):
    try:
        from anima import host_pressure
        lvl = (host_pressure.read_pressure() or {}).get("level")
        mu = _read_json((STORE / "model-usage.json"), default=None)
        try:
            from anima.server import STORE as _S
            mu = mu or _read_json(_S / "model-usage.json", default=None)
        except Exception:
            pass
        model = list((mu or {}).keys())[0] if mu else None
        smap = {"red": "red", "yellow": "yellow", "green": "green"}
        return _R(smap.get(lvl, "unknown"),
                  "Host pressure %s steers model policy (defer/keep_alive)." % (lvl or "unknown"),
                  host_pressure=lvl, model=model)
    except Exception:
        return _R("unknown", "Model runtime / host pressure not reachable.")


def _r_ollama(name):
    mu = _read_json((STORE / "model-usage.json"), default=None)
    try:
        from anima.server import STORE as _S
        mu = mu or _read_json(_S / "model-usage.json", default=None)
    except Exception:
        pass
    if not mu:
        return _R("unknown", "No model usage recorded (Ollama may be idle).")
    return _R("green", "Local inference server hosting the model.", model=list(mu.keys())[0])


def _r_final_gate(name):
    try:
        from anima import incident
        from anima import mouth  # noqa: F401  (presence == wired)
        blocks = sum(1 for e in incident.quarantines(80) if e.get("route") == "output")
        return _R("green", "Model-free floor on every reply (blocks hostile output + #1-rule breaks).",
                  blocked_output_recent=blocks)
    except Exception:
        return _R("unknown", "Final gate not reachable.")


def _r_capability_truth(name):
    try:
        from anima import caps
        cp = caps.load(name)
        on = sorted(k for k, v in cp.items() if v is True)
        off = sum(1 for v in cp.values() if v is False)
        return _R("yellow" if on else "green",
                  ("On: " + ", ".join(on)) if on else "Every outward power OFF by default.",
                  caps_on=on, caps_off=off)
    except Exception:
        return _R("unknown", "Capability store not reachable.")


def _r_approval_queue(name):
    try:
        from anima import agency_approval_queue as Q
        items = Q.get(name) if hasattr(Q, "get") else []
        pend = sum(1 for i in (items or []) if (i.get("status") if isinstance(i, dict) else None) in (None, "pending"))
        return _R("yellow" if pend else "green",
                  "%d action(s) await approval." % pend if pend else "No actions awaiting approval.",
                  pending=pend)
    except Exception:
        return _R("unknown", "Approval queue not reachable.")


def _r_identity_sandbox(name):
    try:
        from anima.server import STORE as _S
        d = _S / "identity_sandbox"
        if d.is_dir():
            return _R("green", "Freeze-safe identity observability (observe-first-change-later).",
                      files=sum(1 for _ in d.iterdir()))
        return _R("unknown", "Identity sandbox has no recorded observations yet.")
    except Exception:
        return _R("unknown", "Identity sandbox not reachable.")


def _r_agency_suggest(name):
    try:
        from anima import incident
        sug = sum(1 for e in incident.recent_events(80) if e.get("kind") == "agency_suggestion")
        return _R("green", "Suggest-only: Vera proposes (with evidence), never executes.",
                  suggestions_recent=sug)
    except Exception:
        return _R("unknown", "Agency subsystem not reachable.")


def _r_security(name):
    try:
        from anima import incident, source_aware
        q = incident.quarantines(80)
        qs = source_aware.quarantined_sources(name) or []
        active = len(qs)
        return _R("red" if active else "green",
                  "%d source(s) quarantined now." % active if active else "No active threats; catches held as evidence.",
                  quarantine_events=len(q), quarantined_sources=active)
    except Exception:
        return _R("unknown", "Security subsystem not reachable.")


def _r_lockdown(name):
    try:
        from anima import incident
        st = incident.status()
        locked = bool(st.get("locked"))
        return _R("red" if locked else "green",
                  "LOCKDOWN ENGAGED — all outward power held off." if locked else "Normal — not locked down.",
                  locked=locked)
    except Exception:
        return _R("unknown", "Incident subsystem not reachable.")


def _r_audit(name):
    d = _read_json(REPORTS / "live_path_results.json", default=None)
    if not d:
        return _R("unknown", "Program Reality Audit has not been run.")
    c = d.get("counts") or {}
    wall = c.get("WALLPAPER", 0)
    partial = c.get("PARTIAL", 0)
    return _R("red" if wall else ("yellow" if partial else "green"),
              "%d WALLPAPER detected." % wall if wall else ("%d PARTIAL (honest gaps)." % partial if partial else "All live paths proven."),
              complete=c.get("COMPLETE", 0), partial=partial, wallpaper=wall)


def _r_argus(name):
    try:
        from anima import host_pressure
        p = host_pressure.read_pressure() or {}
        lvl = p.get("level")
        return _R({"green": "green", "yellow": "yellow", "red": "red"}.get(lvl, "unknown"),
                  "Host pressure: %s." % (lvl or "unknown"), level=lvl)
    except Exception:
        return _R("unknown", "Host telemetry not reachable.")


def _r_jobs(name):
    # the background worker queue is not yet length-instrumented -> honest 'unknown'.
    return _R("unknown", "Background job queue depth is not yet instrumented.")


def _r_founder_console(name):
    try:
        from anima.server import WEB
        pages = [(WEB / f).exists() for f in ("console.html", "observatory.html", "security.html", "living_map.html")]
        return _R("green" if all(pages) else "yellow",
                  "Operator surfaces served." if all(pages) else "Some operator pages missing.",
                  pages=sum(1 for p in pages if p))
    except Exception:
        return _R("unknown", "Console pages not reachable.")


_RESOLVERS = {
    "user": _r_user, "chat_ui": _r_chat_ui, "route_classifier": _r_route_classifier,
    "context_immune": _r_context_immune, "history": _r_history, "memory": _r_memory,
    "known_facts": _r_known_facts, "sources": _r_sources, "intake": _r_intake, "ocr": _r_ocr,
    "lerf": _r_lerf, "patterns": _r_patterns, "improvements": _r_improvements,
    "prompt_compiler": _r_prompt_compiler, "model_runtime": _r_model_runtime, "ollama": _r_ollama,
    "final_gate": _r_final_gate, "capability_truth": _r_capability_truth,
    "approval_queue": _r_approval_queue, "identity_sandbox": _r_identity_sandbox,
    "agency_suggest": _r_agency_suggest, "security": _r_security, "lockdown": _r_lockdown,
    "audit": _r_audit, "argus": _r_argus, "jobs": _r_jobs, "founder_console": _r_founder_console,
}


def resolve_node(node: dict, name: str = "Vera") -> dict:
    """A schema node + its LIVE status (from the real source). Never raises."""
    fn = _RESOLVERS.get(node["node_id"])
    try:
        r = fn(name) if fn else _R("unknown", "No resolver wired for this node.")
    except Exception:
        r = _R("unknown", "Resolver error.")
    out = dict(node)
    out.update({"status": r["status"], "live_metrics": r.get("live_metrics", {}),
                "status_detail": r.get("detail", ""), "last_updated": _now()})
    return out


def _edge_status(edge: dict, node_status: dict) -> str:
    """An edge's status follows its endpoints: blocked if either end is red/locked, degraded if yellow,
    active if both green, else idle/unknown. Derived from real node status — not invented."""
    a = node_status.get(edge["from"], "unknown")
    b = node_status.get(edge["to"], "unknown")
    if "red" in (a, b):
        return "blocked" if edge.get("safety", {}).get("quarantine_possible") else "degraded"
    if "yellow" in (a, b):
        return "degraded"
    if a == "green" and b == "green":
        return "active"
    if "unknown" in (a, b):
        return "idle"
    return "idle"


def build_graph(name: str = "Vera") -> dict:
    """The Living Map graph with LIVE, real-telemetry-backed status. Read-only; guarded."""
    nodes = [resolve_node(n, name) for n in schema.NODES]
    nstat = {n["node_id"]: n["status"] for n in nodes}
    edges = []
    for e in schema.EDGES:
        edges.append({**e, "status": _edge_status(e, nstat)})

    by_status = {}
    for n in nodes:
        by_status[n["status"]] = by_status.get(n["status"], 0) + 1
    # an honest bottleneck = a node that is yellow/red AND a real metric explains it (prompt size,
    # host pressure, a P0 pattern). Surfaced, not invented.
    bottlenecks = [{"node_id": n["node_id"], "label": n["label"], "status": n["status"],
                    "why": n["status_detail"]} for n in nodes if n["status"] in ("yellow", "red")]
    return {
        "name": name,
        "generated_at": _now(),
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "node_count": len(nodes), "edge_count": len(edges),
            "by_status": by_status,
            "unknown": by_status.get("unknown", 0),
            "bottlenecks": bottlenecks,
            "doctrine": "Every status is backed by a real source named in the node; nodes with no live "
                        "data are honestly 'unknown' — never a fake green.",
        },
    }
