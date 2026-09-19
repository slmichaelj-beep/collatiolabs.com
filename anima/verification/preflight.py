"""verification.preflight — external-dependency readiness, measured before the full gate runs.

Local-first Vera leans on a separate daemon (Argus, :8787). A cert that hits a live daemon can flake on
the daemon's readiness, not on a product defect. So we PREFLIGHT the dependency: is it running, how fast
does it answer, what code, which build — recorded as evidence so a PARTIAL caused by a cold/slow daemon
is classified as an environmental-dependency state, never hand-waved or mistaken for a product gap.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "reports" / "external_dependencies.json"

ARGUS_PORTS = range(8787, 8799)         # Argus binds 8787, falls back to 8788..8798
SLOW_MS = 750.0                         # reachable but slower than this == degraded


def _probe(url: str, timeout: float = 3.0):
    """(code, latency_ms, body_head) for a GET; (None, latency, '') on connection error."""
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(2048).decode("utf-8", "replace")
            return r.status, (time.monotonic() - t0) * 1000.0, body
    except Exception:
        return None, (time.monotonic() - t0) * 1000.0, ""


def argus_preflight() -> dict:
    """Probe the Argus daemon across its port range. Returns a structured readiness record. Never raises."""
    found = None
    for port in ARGUS_PORTS:
        code, ms, body = _probe("http://127.0.0.1:%d/" % port)
        if code == 200 and ("argus-token" in body or "Argus" in body):
            ver = "unknown"
            m = re.search(r"Argus[^<]*?v?(\d+\.\d+(?:\.\d+)?)", body)
            if m:
                ver = m.group(1)
            found = {"port": port, "code": code, "latency_ms": round(ms, 1), "version": ver}
            break
    if not found:
        state = "unavailable"
        rec = {"daemon": "argus", "state": state, "port": None, "code": None,
               "latency_ms": None, "version": None}
    else:
        state = "degraded" if found["latency_ms"] > SLOW_MS else "running"
        rec = {"daemon": "argus", "state": state, **found}
    rec["slow_threshold_ms"] = SLOW_MS
    return rec


def external_dependencies() -> dict:
    """All external-dependency readiness records (currently Argus; extensible). Never raises."""
    deps = [argus_preflight()]
    return {"dependencies": deps,
            "any_unavailable": any(d["state"] == "unavailable" for d in deps),
            "any_degraded": any(d["state"] == "degraded" for d in deps)}


def write(rec: dict | None = None) -> dict:
    rec = rec or external_dependencies()
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rec, indent=2))
    except Exception:
        pass
    return rec


def render_block(rec: dict | None = None) -> str:
    """The EXTERNAL DEPENDENCY STATE block for the gate output."""
    rec = rec or external_dependencies()
    lines = ["EXTERNAL DEPENDENCY STATE:"]
    for d in rec["dependencies"]:
        lat = ("%.0fms" % d["latency_ms"]) if d.get("latency_ms") is not None else "n/a"
        lines.append("  %-12s %-11s port=%s code=%s latency=%s version=%s"
                     % (d["daemon"] + ":", d["state"], d.get("port"), d.get("code"), lat, d.get("version")))
    return "\n".join(lines)


if __name__ == "__main__":
    r = external_dependencies()
    print(render_block(r))
    print(json.dumps(r, indent=2))
