"""Global egress guardrails.

Zero-egress mode is the hard privacy switch: no cloud provider calls, no public
web fetches, no weather/location lookups. Local loopback model servers are still
local compute and are not treated as off-device egress.
"""
from __future__ import annotations

import os


class EgressBlocked(RuntimeError):
    pass


def zero_enabled() -> bool:
    return os.environ.get("ANIMA_ZERO_EGRESS", "").strip().lower() in {"1", "true", "yes", "on"}


def require(kind: str, target: str = "") -> None:
    if zero_enabled():
        suffix = f": {target}" if target else ""
        raise EgressBlocked(f"zero-egress mode is on; blocked {kind}{suffix}")


def blocked_result(kind: str, target: str = "") -> dict:
    suffix = f": {target}" if target else ""
    return {"ok": False, "error": f"zero-egress mode is on; blocked {kind}{suffix}"}
