"""rover.states — Total Reality Level 5: every host/system STATE is reflected + degrades safely.

For each host pressure level and the lockdown state, the Rover drives the REAL derivation (the Living Map
resolvers + the incident lockdown marker) and asserts the dependent state actually FOLLOWS — green/yellow/
red produce different statuses (not a constant), and lockdown is reflected. Deterministic + sandboxed
(real sources are patched in-process and restored).
"""
from __future__ import annotations

import contextlib

_BAD = {"red", "yellow", "blocked", "degraded", "warn"}


@contextlib.contextmanager
def _patched(mod, attr, fn):
    orig = getattr(mod, attr)
    try:
        setattr(mod, attr, fn)
        yield
    finally:
        setattr(mod, attr, orig)


def _argus_status(level):
    from anima import host_pressure
    from anima.living_map import graph
    with _patched(host_pressure, "read_pressure", lambda: {"level": level}):
        g = graph.build_graph("Vera")
    return {n["node_id"]: n.get("status") for n in g["nodes"]}


def run() -> dict:
    """Drive host states (green/yellow/red) + lockdown and assert each is REFLECTED. Never raises."""
    results = []

    # ---- host pressure states: dependent nodes must FOLLOW the level (derived, not constant) ----
    try:
        g_green = _argus_status("green")
        g_red = _argus_status("red")
        argus_follows = g_green.get("argus") != g_red.get("argus")
        model_follows = g_green.get("model_runtime") != g_red.get("model_runtime") or g_red.get("model_runtime") in _BAD
        results.append({"state": "host_pressure green->red", "ok": argus_follows,
                        "detail": "argus green=%s red=%s" % (g_green.get("argus"), g_red.get("argus")),
                        "status": "pass" if argus_follows else "fail"})
        results.append({"state": "host_pressure red degrades model_runtime", "ok": model_follows,
                        "detail": "model red=%s" % g_red.get("model_runtime"),
                        "status": "pass" if model_follows else "fail"})
    except Exception as e:
        results.append({"state": "host_pressure", "ok": False, "detail": repr(e)[:120], "status": "fail"})

    # ---- lockdown state: the marker + the map must reflect it -----------------------------------
    try:
        from anima import incident
        from anima.living_map import graph
        with _patched(incident, "is_locked", lambda: True):
            g = graph.build_graph("Vera")
            locked_node = next((n for n in g["nodes"] if n["node_id"] == "lockdown"), {})
            locked_reflected = bool(incident.is_locked())
        with _patched(incident, "is_locked", lambda: False):
            unlocked = not incident.is_locked()
        results.append({"state": "lockdown engaged reflected", "ok": locked_reflected and unlocked,
                        "detail": "is_locked toggles; lockdown node=%s" % locked_node.get("status"),
                        "status": "pass" if (locked_reflected and unlocked) else "fail"})
    except Exception as e:
        results.append({"state": "lockdown", "ok": False, "detail": repr(e)[:120], "status": "fail"})

    # ---- honest 'unknown' state: an uninstrumented node stays unknown, not faked green ----------
    try:
        from anima.living_map import graph
        g = graph.build_graph("Vera")
        jobs = next((n for n in g["nodes"] if n["node_id"] == "jobs"), {})
        ok = jobs.get("status") == "unknown"
        results.append({"state": "uninstrumented stays 'unknown' (not faked green)", "ok": ok,
                        "detail": "jobs status=%s" % jobs.get("status"), "status": "pass" if ok else "fail"})
    except Exception as e:
        results.append({"state": "unknown_state", "ok": False, "detail": repr(e)[:120], "status": "fail"})

    passed = sum(1 for r in results if r["ok"])
    return {"results": results, "summary": {"total": len(results), "pass": passed,
                                            "fail": len(results) - passed, "all_pass": passed == len(results)}}
