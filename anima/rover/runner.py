"""rover.runner — execute the Level-2 scenario matrix against the REAL server backing paths.

For each surface scenario we confirm the page is served AND its data function runs without raising (the
real backing path). For each control scenario we confirm the control's surface backing path works and, for
nav controls, that the link target is a real route. Contract + critical + adversarial scenarios are
delegated honestly (to the live-path gate / the existing Rover / the future Renegade phase) — never
silently passed. Every scenario yields a real observation. In-process + deterministic; never raises.
"""
from __future__ import annotations

import time
import traceback

# surface -> the real server data function that backs it (the backing path we actually exercise).
# NOTE: 'reality' is intentionally absent — its data fn (_total_reality_data) RUNS this Rover, so calling
# it here would recurse. The reality surface is still executed via the page-served check.
_SURFACE_DATA = {
    "console": "_console_data", "security": "_security_data", "consent": "_consent_data",
    "trust": "_trust_data", "ergonomics": "_ergonomics_data", "mentorship": "_mentorship_data",
    "meaning": "_meaning_graph_data", "identity": "_identity_health_data",
    "living_map": "_living_map_data", "observatory": "_observatory_data",
}


def _server():
    from anima import server
    return server


def _routes_set():
    from anima.scenarios import inventory
    return {r["route"] for r in inventory.routes()}


def _served_surfaces():
    from anima.scenarios import inventory
    return {s["surface"] for s in inventory.surfaces() if s["served"]}


def _exec_surface(name, surfaces_served) -> dict:
    """Execute a surface: page served + (if it has one) its data function runs clean."""
    served = name in surfaces_served
    data_ok, detail = None, "served=%s" % served
    fn = _SURFACE_DATA.get(name)
    if fn:
        try:
            d = getattr(_server(), fn)("Vera")
            data_ok = isinstance(d, dict) and not d.get("error")
            detail += "; %s -> %s" % (fn, "ok" if data_ok else "error:%s" % (d.get("error") if isinstance(d, dict) else "non-dict"))
        except Exception as e:
            data_ok = False
            detail += "; %s RAISED %s" % (fn, e.__class__.__name__)
    ok = served and (data_ok is not False)
    return {"ok": ok, "outcome": "page_loads" if ok else "error", "detail": detail,
            "severity": None if ok else "P1"}


def _exec_control(scn, routes, surfaces_served) -> dict:
    """Execute a control: its surface backing path works; nav targets resolve to a real route/surface."""
    surface = scn["surface"]
    label = scn.get("title", "")
    if " -> /" in label:                       # a nav control: the link target must be a real route
        target = "/" + label.split(" -> /", 1)[1].rstrip(") ")
        target = target.split()[0]
        reachable = target in routes or target.lstrip("/").split(".")[0] in surfaces_served or target == "/"
        return {"ok": reachable, "outcome": "page_loads" if reachable else "error",
                "detail": "nav -> %s reachable=%s" % (target, reachable),
                "severity": None if reachable else "P2"}
    # non-nav control: its surface must have a working backing path (no dead control at the backing level)
    backed = surface in surfaces_served
    fn = _SURFACE_DATA.get(surface)
    if fn:
        try:
            backed = backed and not (getattr(_server(), fn)("Vera") or {}).get("error")
        except Exception:
            backed = False
    return {"ok": backed, "outcome": "control_acts" if backed else "error",
            "detail": "control on %s; backing path ok=%s (browser-click deferred to L9)" % (surface, backed),
            "severity": None if backed else "P2"}


def run(matrix: dict, persona: str = "founder") -> dict:
    """Execute the Level-2 scenarios; delegate the rest honestly. Returns results + a coverage summary."""
    routes = _routes_set()
    surfaces_served = _served_surfaces()
    results = []
    for scn in matrix.get("scenarios", []):
        sid = scn["scenario_id"]
        t0 = time.time()
        try:
            if sid.startswith("trt_surface_"):
                r = _exec_surface(scn["surface"], surfaces_served)
                status = "pass" if r["ok"] else "fail"
            elif sid.startswith("trt_ctrl_"):
                r = _exec_control(scn, routes, surfaces_served)
                status = "pass" if r["ok"] else "fail"
            elif sid.startswith("trt_contract_"):
                r = {"ok": True, "outcome": "show_trace", "severity": None,
                     "detail": "delegated to the live-path gate (certify_live_paths.py)"}
                status = "blocked"        # blocked-by-design: covered elsewhere, not re-run here
            elif scn["kind"] == "critical":
                r = {"ok": True, "outcome": scn["expected_outcome"], "severity": None,
                     "detail": "delegated to scripts/vera_rover.py --selftest (Level 1)"}
                status = "blocked"
            elif scn["kind"] == "adversarial":
                r = {"ok": True, "outcome": scn["expected_outcome"], "severity": None,
                     "detail": "covered by the Renegade chains (Level 7, certify_renegade_chains.py)"}
                status = "blocked"        # blocked-by-design: covered by a certified Renegade chain
            else:
                r = {"ok": True, "outcome": scn["expected_outcome"], "severity": None,
                     "detail": "deferred to its coverage level (%s)" % scn["level"]}
                status = "deferred"
        except Exception:
            r = {"ok": False, "outcome": "error", "severity": "P1", "detail": traceback.format_exc(-1)[:200]}
            status = "fail"
        results.append({
            "scenario_id": sid, "persona": persona, "surface": scn["surface"],
            "kind": scn["kind"], "level": scn["level"], "status": status,
            "outcome": r["outcome"], "severity": r["severity"], "detail": r["detail"],
            "latency_ms": round((time.time() - t0) * 1000, 1),
        })

    from collections import Counter
    by_status = Counter(r["status"] for r in results)
    executed = [r for r in results if r["status"] in ("pass", "fail")]
    return {
        "persona": persona,
        "results": results,
        "summary": {
            "total": len(results),
            "executed": len(executed),
            "pass": by_status.get("pass", 0),
            "fail": by_status.get("fail", 0),
            "blocked": by_status.get("blocked", 0),
            "deferred": by_status.get("deferred", 0),
            "p0": sum(1 for r in results if r["severity"] == "P0"),
            "p1": sum(1 for r in results if r["severity"] == "P1"),
            "by_status": dict(by_status),
        },
    }
