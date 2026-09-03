"""
host_window — Phase 2 of the Whole-System MRI.

Captures a three-point host snapshot (before / during / after a Vera turn) using ONLY
the certified, read-only Argus read surface (/mri, /ask, /timeline).

Certified read set (NON-NEGOTIABLE):
  GET /mri       → HostMRIFrame: shape + counts + findings + blind_spots + status
  POST /ask      → deterministic host Q&A
  GET /timeline  → narrated recent history

NOT in the certified read set (refused):
  /system, /events, /action_log (NOT used here), /simulate (NOT used here)
  Any mutating endpoint — this module has zero host-action capability.

NON-NEGOTIABLES (verified in selftest):
  * read-only  — no mutating call, no host action
  * certified read set only — /mri, /ask, /timeline; /capabilities for the handshake
  * graceful-unavailable — off/down → {"unavailable": True, "reason": "..."}, never raises
  * local-first — Argus client enforces loopback-only; nothing leaves the Mac
  * no .anima writes — this module never writes any .anima file
"""

from __future__ import annotations

import time
from typing import Optional


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _argus_client():
    """Return the module-level ArgusClient (may already be discovered)."""
    from .tools.argus_client import client as _client
    return _client()


def _is_on(name: str) -> bool:
    """Is host_awareness enabled for this creature?"""
    try:
        from .host_awareness import is_on
        return is_on(name)
    except Exception:
        return False


def _safe_float(v) -> Optional[float]:
    """Cast to float or None."""
    try:
        return float(v)
    except Exception:
        return None


def _safe_int(v) -> Optional[int]:
    """Cast to int or None."""
    try:
        return int(v)
    except Exception:
        return None


def _extract_shape(mri: dict) -> Optional[dict]:
    """
    Extract the /mri `shape` field (the z-score fingerprint produced by Argus).

    The /mri payload may carry a top-level `shape` key — a dict of dimension →
    z-score float.  Returns it as-is (or None if absent/malformed).
    """
    shape = mri.get("shape")
    if isinstance(shape, dict):
        return shape
    return None


def _extract_counts(mri: dict) -> Optional[dict]:
    """Extract counts (by_severity breakdown) from the /mri payload."""
    c = mri.get("counts")
    if isinstance(c, dict):
        return c
    return None


def _extract_resource(mri: dict, *keys: str) -> Optional[float]:
    """
    Walk the /mri dict looking for a resource field under several common key paths.
    Returns a float or None (honest null — never fabricated).
    """
    # Direct top-level
    for k in keys:
        v = mri.get(k)
        f = _safe_float(v)
        if f is not None:
            return f
    # Under a 'resources' sub-dict
    res = mri.get("resources")
    if isinstance(res, dict):
        for k in keys:
            f = _safe_float(res.get(k))
            if f is not None:
                return f
    return None


def _numeric_delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """b - a, or None if either is unavailable."""
    if a is None or b is None:
        return None
    return b - a


def _shape_delta(before_shape: Optional[dict], after_shape: Optional[dict]) -> Optional[dict]:
    """
    Per-dimension diff of the /mri shape z-score fingerprint: after[dim] - before[dim].

    Returns a dict of {dimension: delta} for every dimension present in both snapshots.
    Dimensions present in only one snapshot are included with None (honest absence).
    Returns None if both shapes are absent.
    """
    if before_shape is None and after_shape is None:
        return None
    bs = before_shape or {}
    as_ = after_shape or {}
    dims = set(bs) | set(as_)
    result = {}
    for dim in sorted(dims):
        bv = _safe_float(bs.get(dim))
        av = _safe_float(as_.get(dim))
        result[dim] = _numeric_delta(bv, av)
    return result if result else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def capture_host_state(name: str) -> dict:
    """
    ONE fast, guarded snapshot of host state from the certified Argus.

    Reads only GET /mri from the certified read set.  Returns a dict:
      {
        "ts":          float (epoch seconds),
        "shape":       dict | None   (z-score fingerprint from /mri),
        "counts":      dict | None   (by_severity counts),
        "by_severity": dict | None   (shortcut to counts["by_severity"]),
        "blind_spots": list[str],
        "status":      str | None,
        # Raw resource fields exposed by /mri (honest null when absent):
        "cpu_pct":     float | None,
        "memory_mb":   float | None,
        "swap_mb":     float | None,
        "disk_io_mb":  float | None,
        "network_mb":  float | None,
        "thermal":     str | None,
        # Any additional raw fields from /mri payload
      }

    If host_awareness is OFF, or Argus is unavailable/uncertified:
      {"unavailable": True, "reason": "..."}

    Never raises; bounded execution (it runs inside a live turn).
    """
    ts = time.time()

    # Gate 1: feature must be ON
    if not _is_on(name):
        return {"unavailable": True, "reason": "host_awareness OFF"}

    # Gate 2: certified Argus must be reachable
    try:
        c = _argus_client()
        if not c.available():
            return {"unavailable": True, "reason": "Argus unavailable or uncertified"}
    except Exception as exc:
        return {"unavailable": True, "reason": f"Argus client error: {exc}"}

    # Read /mri (the only endpoint this function uses)
    try:
        mri = c.mri()
    except Exception as exc:
        return {"unavailable": True, "reason": f"/mri read failed: {exc}"}

    if not isinstance(mri, dict):
        return {"unavailable": True, "reason": "/mri returned non-dict payload"}

    # Extract certified fields
    counts = _extract_counts(mri)
    by_sev = counts.get("by_severity") if isinstance(counts, dict) else None
    shape = _extract_shape(mri)
    blind_spots = [str(b) for b in (mri.get("blind_spots") or [])]
    status = mri.get("status")

    # Resource fields — honest null for anything not present in the /mri payload
    cpu_pct   = _extract_resource(mri, "cpu_pct",   "cpu",   "cpu_percent")
    memory_mb = _extract_resource(mri, "memory_mb", "memory", "rss_mb", "mem_mb")
    swap_mb   = _extract_resource(mri, "swap_mb",   "swap")
    disk_io_mb = _extract_resource(mri, "disk_io_mb", "disk_io", "disk_read_mb", "disk_write_mb")
    network_mb = _extract_resource(mri, "network_mb", "network", "net_mb", "network_io_mb")
    thermal   = mri.get("thermal")

    return {
        "ts":          ts,
        "shape":       shape,
        "counts":      counts,
        "by_severity": by_sev,
        "blind_spots": blind_spots,
        "status":      status,
        "cpu_pct":     cpu_pct,
        "memory_mb":   memory_mb,
        "swap_mb":     swap_mb,
        "disk_io_mb":  disk_io_mb,
        "network_mb":  network_mb,
        "thermal":     thermal,
    }


def host_window_delta(before: dict, during: dict, after: dict) -> dict:
    """
    Compute the host window delta from three capture_host_state() snapshots.

    Returns:
      {
        "host_before":    dict,
        "host_during":    dict,
        "host_after":     dict,
        "shape_delta":    dict | None  (per-dimension z-score diff: after - before),
        "blind_spots":    list[str]    (union across all three snapshots),
        "cpu_delta":      float | None,
        "memory_delta_mb": float | None,
        "disk_io_delta":  float | None,
        "network_delta":  float | None,
        "thermal":        str | None   (from `after`, falling back to `during`),
      }

    If any snapshot carries {"unavailable": True}, degrades gracefully:
      {"host_window": "unavailable", "reason": ...}
    and never raises.

    shape_delta is the primary resource-deviation signal (before vs after).
    Resource deltas (cpu_delta, memory_delta_mb, disk_io_delta, network_delta)
    are computed as after - before; null when the field was not exposed by /mri.
    """
    # Graceful-unavailable: any snapshot missing → report cleanly
    for label, snap in (("before", before), ("during", during), ("after", after)):
        if not isinstance(snap, dict):
            return {"host_window": "unavailable",
                    "reason": f"snapshot '{label}' is not a dict"}
        if snap.get("unavailable"):
            return {"host_window": "unavailable",
                    "reason": f"snapshot '{label}' unavailable: {snap.get('reason', '?')}"}

    # shape_delta: the primary deviation signal (before → after)
    sdelta = _shape_delta(before.get("shape"), after.get("shape"))

    # blind_spots: union of all three
    bs_union: list[str] = []
    seen: set[str] = set()
    for snap in (before, during, after):
        for b in (snap.get("blind_spots") or []):
            s = str(b)
            if s not in seen:
                bs_union.append(s)
                seen.add(s)

    # Resource deltas: after - before; honest null when field absent in /mri
    cpu_delta        = _numeric_delta(before.get("cpu_pct"),   after.get("cpu_pct"))
    memory_delta_mb  = _numeric_delta(before.get("memory_mb"), after.get("memory_mb"))
    disk_io_delta    = _numeric_delta(before.get("disk_io_mb"), after.get("disk_io_mb"))
    network_delta    = _numeric_delta(before.get("network_mb"), after.get("network_mb"))

    # thermal: prefer after, fall back to during
    thermal = after.get("thermal") or during.get("thermal")

    return {
        "host_before":     before,
        "host_during":     during,
        "host_after":      after,
        "shape_delta":     sdelta,
        "blind_spots":     bs_union,
        "cpu_delta":       cpu_delta,
        "memory_delta_mb": memory_delta_mb,
        "disk_io_delta":   disk_io_delta,
        "network_delta":   network_delta,
        "thermal":         thermal,
    }


def host_window(
    name: str,
    before: Optional[dict] = None,
    during: Optional[dict] = None,
    after: Optional[dict] = None,
) -> dict:
    """
    Convenience entry point.  Captures `during` if the three snapshots are not supplied,
    and builds the host-window delta block the UnifiedTrace expects.

    The owner (_turn) will pass real before/during/after from its three-point capture;
    this function handles the single-snapshot convenience case transparently.

    Always returns either a full delta dict (from host_window_delta) or the graceful
    unavailable record {"host_window": "unavailable", "reason": ...}.
    Never raises.
    """
    try:
        if before is None and during is None and after is None:
            # Convenience: capture once, use as all three positions
            snap = capture_host_state(name)
            if snap.get("unavailable"):
                return {"host_window": "unavailable", "reason": snap.get("reason", "unavailable")}
            before = during = after = snap

        # If the caller provided only some snapshots, fill in missing ones gracefully
        if during is None:
            during = capture_host_state(name)
        if before is None:
            before = during
        if after is None:
            after = during

        return host_window_delta(before, during, after)
    except Exception as exc:
        return {"host_window": "unavailable", "reason": f"host_window error: {exc}"}
