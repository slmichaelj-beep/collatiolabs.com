"""living_map.simulation — Milestone 4: SIMULATION. Pull a lever -> predicted impact.

The prediction is NOT a guess: it is computed by RE-RUNNING THE REAL status derivation (the same
resolvers Milestone 1 uses) under a hypothetical input, in a sandbox that patches a real source in-process
and RESTORES it — never touching the real store. Every simulation declares its assumptions, a confidence,
and the cert that would gate shipping a real change. Read-only + sandboxed; never mutates Vera state.
"""
from __future__ import annotations

import contextlib

from . import graph


@contextlib.contextmanager
def _patched(dotted_setter):
    """Temporarily replace a real source function, yield, then ALWAYS restore it (sandbox seatbelt)."""
    restores = []
    try:
        for mod, attr, fn in dotted_setter:
            restores.append((mod, attr, getattr(mod, attr)))
            setattr(mod, attr, fn)
        yield
    finally:
        for mod, attr, orig in reversed(restores):
            setattr(mod, attr, orig)


def _lever_patches(lever_id: str):
    """Map a lever id to the REAL source(s) it hypothetically changes. Returns (patches, meta) or None."""
    try:
        from anima import host_pressure
    except Exception:
        host_pressure = None
    try:
        from anima import incident
    except Exception:
        incident = None

    if lever_id in ("host_pressure_red", "host_pressure_yellow", "host_pressure_green") and host_pressure:
        level = lever_id.rsplit("_", 1)[1]
        return ([(host_pressure, "read_pressure", (lambda lv=level: (lambda: {"level": lv}))())],
                {"label": "Host pressure -> %s" % level,
                 "source": "host_pressure.read_pressure (the real Argus reading)",
                 "assumptions": ["Only host pressure changes; every other source is held at its current real value.",
                                 "The model-runtime and Argus nodes derive their status directly from this reading."],
                 "confidence": 0.9,
                 "required_cert": "certify_living_map_no_wallpaper.py (status-is-derived) + certify_host_pressure"})
    if lever_id == "lockdown_on" and incident:
        return ([(incident, "is_locked", lambda: True)],
                {"label": "Security lockdown -> engaged",
                 "source": "incident.is_locked (the real lockdown marker)",
                 "assumptions": ["A lockdown is engaged; outward capabilities would be held OFF at the caps gate.",
                                 "Other sources are held at their current real values."],
                 "confidence": 0.75,
                 "required_cert": "certify_incident_response.py + certify_security_surface.py"})
    return None


def levers() -> list:
    """The available simulation levers (for the UI). Each names the real source it would change."""
    out = []
    for lid in ("host_pressure_red", "host_pressure_yellow", "host_pressure_green", "lockdown_on"):
        p = _lever_patches(lid)
        if p:
            out.append({"id": lid, "label": p[1]["label"], "source": p[1]["source"],
                        "confidence": p[1]["confidence"]})
    return out


def _status_by_node(g: dict) -> dict:
    return {n["node_id"]: n.get("status") for n in (g.get("nodes") or [])}


def simulate(name: str = "Vera", lever_id: str = "host_pressure_red") -> dict:
    """Predict the impact of a lever by re-running the REAL derivation under it, sandboxed. Returns the
    predicted node-status changes + assumptions + confidence + required cert. Read-only; never raises."""
    patch = _lever_patches(lever_id)
    if not patch:
        return {"name": name, "lever": lever_id, "ok": False,
                "error": "unknown lever", "available": [l["id"] for l in levers()], "sandboxed": True}
    patches, meta = patch
    try:
        baseline = graph.build_graph(name)
        with _patched(patches):
            predicted = graph.build_graph(name)
    except Exception as e:
        return {"name": name, "lever": lever_id, "ok": False, "error": str(e), "sandboxed": True}

    b, p = _status_by_node(baseline), _status_by_node(predicted)
    changes = [{"node_id": nid, "from": b.get(nid), "to": p.get(nid)}
               for nid in p if b.get(nid) != p.get(nid)]

    # sandbox self-check: the real source is restored, so a fresh build matches the baseline again
    after = _status_by_node(graph.build_graph(name))
    sandbox_clean = (after == b)

    return {
        "name": name,
        "lever": lever_id,
        "label": meta["label"],
        "ok": True,
        "sandboxed": True,
        "sandbox_clean": sandbox_clean,
        "assumptions": meta["assumptions"],
        "confidence": meta["confidence"],
        "required_cert": meta["required_cert"],
        "predicted_changes": changes,
        "changed_count": len(changes),
        "baseline_at": baseline.get("generated_at"),
        "doctrine": "The prediction is computed by re-running the REAL status derivation under a "
                    "hypothetical source value, in a sandbox that restores the source afterwards. Nothing "
                    "is hardcoded; nothing real is changed. Shipping the change would require the named cert.",
    }
