"""
host_awareness — Vera's OPT-IN awareness of host + outbound-network state, via Argus.

This is KNOWLEDGE about the machine Vera runs on (which apps are talking to the network, and
which connections look worth a glance) — not identity, not agency. It belongs to Program A
(the mind), and it is DEFAULT-OFF: until the user turns on `host_awareness` in settings, every
entry point here is a provable no-op (no Argus call, nothing read).

Design:
  * OPT-IN: gated on caps.enabled(name, "host_awareness"). Off -> {"on": False}, no I/O.
  * LOCAL-FIRST: reads only the local Argus (anima.tools.argus_client, loopback-only). Nothing
    about the host leaves the Mac. Under a CLOUD brain the specifics are REDACTED (host/process/
    IP are private) — only counts survive, exactly like the personal-fact block is blanked.
  * HUMAN-LEVEL: each notable item is framed issue -> what it means -> what to do, never a raw
    dump (feedback_human_level_issues_and_actions).
  * HONEST + GUARDED: when Argus isn't running it says so ("the monitor isn't on") and never
    fabricates a network picture. Any failure degrades to a safe, empty-but-truthful summary.
  * NO AGENCY: this module only READS and SUMMARISES. Pausing a destination is a separate,
    confirm-gated power (caps host_block + the approval bridge in server.py); nothing here acts.
"""

from __future__ import annotations

from typing import Optional

from . import caps


def is_on(name: str) -> bool:
    """Has the user opted into host awareness for this creature?"""
    try:
        return caps.enabled(name, "host_awareness")
    except Exception:
        return False


_SEV_ORDER = {"high": 3, "watch": 2, "low": 1, "info": 0}
_ACTION_HUMAN = {
    "investigate": "worth investigating — open Argus to see who and why",
    "review":      "worth a glance — probably fine, but unusual",
    "allow":       "looks expected — nothing to do",
}


def _humanize(f: dict) -> dict:
    """One finding -> issue / what it means / what to do (plain language). Read-only: this wave
    only surfaces; it never offers an action."""
    sev = str(f.get("severity") or "info")
    action_key = str(f.get("recommended_action") or "review")
    todo = _ACTION_HUMAN.get(action_key, "worth a glance")
    return {
        "severity": sev,
        "issue": f.get("title") or f.get("what_happened") or "unrecognized connection",
        "what_happened": f.get("what_happened") or "",
        "means": f.get("why_it_matters") or "",
        "todo": todo,
        "confidence": f.get("confidence"),
        # a stable handle the approval bridge can preview/confirm a pause against
        "flow_key": (f.get("related_flows") or [None])[0],
    }


def status(name: str) -> dict:
    """Cheap state: is awareness on, and is the monitor reachable? No findings fetched."""
    if not is_on(name):
        return {"on": False, "available": False}
    try:
        from .tools.argus_client import client
        return {"on": True, "available": bool(client().available())}
    except Exception:
        return {"on": True, "available": False}


def summary(name: str, *, cloud_safe: bool = False, limit: int = 5) -> dict:
    """The host-awareness picture for `name`, human-level. Always returns a dict; never raises.

    OFF            -> {"on": False}
    ON, no monitor -> {"on": True, "available": False, "headline": "the monitor isn't running"}
    ON + monitor   -> counts + a headline + the most notable items (issue/means/todo)
    cloud_safe=True -> counts + a redacted headline only (host specifics are private)
    """
    if not is_on(name):
        return {"on": False}
    try:
        from .tools.argus_client import client
        c = client()
        if not c.available():
            return {"on": True, "available": False,
                    "headline": "Host awareness is on, but the Argus monitor isn't running."}
        mri = c.mri() or {}
    except Exception:
        return {"on": True, "available": False,
                "headline": "Host awareness is on, but the monitor couldn't be reached."}

    counts = (mri.get("counts") or {}).get("by_severity", {}) or {}
    high = int(counts.get("high", 0))
    watch = int(counts.get("watch", 0))
    low = int(counts.get("low", 0))
    info = int(counts.get("info", 0))
    total = high + watch + low + info
    flagged = high + watch
    base = {
        "on": True,
        "available": True,
        "status": mri.get("status"),
        "totals": {"findings": total, "high": high, "watch": watch, "low": low, "info": info},
    }

    # CLOUD REDACTION — host/process/IP are private; a cloud brain gets counts only.
    if cloud_safe:
        base["headline"] = (
            f"{total} host findings ({flagged} worth a look)." if total
            else "Nothing notable on the host right now.")
        base["redacted"] = True
        return base

    findings = mri.get("findings") or []
    findings = [f for f in findings if isinstance(f, dict)]
    findings.sort(key=lambda f: _SEV_ORDER.get(str(f.get("severity")), 0), reverse=True)
    notable = [_humanize(f) for f in findings[:max(1, int(limit))]
               if str(f.get("severity")) in ("watch", "high")]

    if flagged == 0:
        base["headline"] = (
            f"{total} outbound connections, all looking expected — nothing flagged."
            if total else "No outbound connections observed right now.")
    else:
        base["headline"] = (
            f"{total} outbound connections; {flagged} worth a glance"
            + (f" ({high} higher-priority)" if high else "") + ".")
    base["notable"] = notable
    bs = mri.get("blind_spots") or []
    if bs:
        base["blind_spots"] = [str(b) for b in bs][:3]
    return base


def notable(name: str, *, limit: int = 8) -> list:
    """The watch/high findings worth surfacing (for the approval bridge). [] when off/down."""
    s = summary(name, cloud_safe=False, limit=limit)
    return s.get("notable", []) if s.get("on") and s.get("available") else []


def line(name: str, *, cloud_safe: bool = False) -> Optional[str]:
    """A single grounded sentence Vera can weave into a turn, or None when there's nothing to
    say (off / monitor down / nothing notable). NEVER fabricates — silence over invention."""
    s = summary(name, cloud_safe=cloud_safe)
    if not s.get("on") or not s.get("available"):
        return None
    head = s.get("headline")
    return head if (head and s.get("totals", {}).get("findings")) else None


def history(name: str, *, hours: int = 12) -> Optional[dict]:
    """Argus's narrated recent history (/timeline), or None when off/down. Read-only."""
    if not is_on(name):
        return None
    try:
        from .tools.argus_client import client
        c = client()
        return c.timeline(hours) if c.available() else None
    except Exception:
        return None


def actions(name: str) -> Optional[dict]:
    """Argus's own action audit log (/action_log), or None when off/down. Read-only — this is
    Argus reporting what IT did; Vera takes no host action in this wave."""
    if not is_on(name):
        return None
    try:
        from .tools.argus_client import client
        c = client()
        return c.action_log() if c.available() else None
    except Exception:
        return None
