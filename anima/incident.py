"""incident — Security Operations + Incident Response for Vera (local-first).

Two capabilities, one module:

  * LOCKDOWN (the panic button): one call forces Vera into a SAFE STATE — every outward capability is
    held OFF (caps.enabled returns False while locked, regardless of stored grants), so no mail, no
    iMessage, no web, no host access, no growth can run no matter what is configured. Fully REVERSIBLE
    (restore lifts it) and AUDITED (every lockdown/restore is a security event). It never deletes the
    user's settings — it overrides them, then hands them back intact.

  * SECURITY EVENT LOG (the SOC trail): an append-only, local, timestamped jsonl of security-relevant
    events (lockdowns, restores, and any source that calls security_event) so the posture is reviewable
    after the fact. Local-only; never leaves the Mac.

State lives next to the rest of the creature state under .anima (CWD-relative, like caps/server), so a
hermetic test harness that redirects .anima gets an isolated incident store automatically.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

STORE = Path(".anima")


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _lock_path() -> Path:
    return STORE / "incident_lock.json"


def _events_path() -> Path:
    return STORE / "security_events.jsonl"


# --- the SOC trail -----------------------------------------------------------------------------
def security_event(kind: str, detail: str = "", **extra) -> dict:
    """Append a security-relevant event to the local, append-only trail. Never raises (a logging
    failure must never break the spine). Returns the event dict."""
    ev = {"at": _now(), "kind": str(kind), "detail": str(detail)}
    if extra:
        ev.update({k: v for k, v in extra.items()})
    try:
        STORE.mkdir(exist_ok=True)
        with _events_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return ev


def recent_events(n: int = 20) -> list:
    """The most recent security events (newest last). Never raises."""
    try:
        lines = _events_path().read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out = []
    for ln in lines[-int(max(1, n)):]:
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


def quarantine(route: str, markers=None, preview: str = "", **extra) -> dict:
    """Record a CONTEXT-IMMUNE quarantine: hostile / injected text was CAUGHT and held as evidence —
    never obeyed. `route` is where it was caught: 'output' (the final answer gate dropped a hostile
    reply), 'source' (an injection-bearing reference source was excluded from support), 'context' /
    'conversation' (a poisoned prior turn was neutralized before re-entering the model).

    DOCTRINE: hostile text MAY be stored as evidence; it may NEVER become trusted context/memory/
    source/answer. So this records ONLY redacted evidence — the markers that tripped + a short, single-
    line preview clamped to 120 chars — for the security review surface. It is shown there, labeled as
    quarantined evidence, and is never re-fed to the model. Append-only; never raises (a logging
    failure must never break the spine)."""
    mk = [str(m) for m in (markers or [])][:8]
    pv = (str(preview or "")[:120]).replace("\n", " ").replace("\r", " ")
    return security_event("quarantine",
                          "hostile/injected text held as evidence, not obeyed (route: %s)" % route,
                          route=str(route), markers=mk, preview=pv, **extra)


def quarantines(n: int = 50) -> list:
    """The recent QUARANTINE events only (newest first) — the discrete moments the immune system caught
    hostile/injected text. A subset of the SOC trail. Never raises."""
    evs = [e for e in recent_events(max(n * 4, 80)) if e.get("kind") == "quarantine"]
    return list(reversed(evs))[:int(max(1, n))]


# --- the panic button --------------------------------------------------------------------------
def is_locked() -> bool:
    """True iff a security lockdown is active. Pure; never raises."""
    try:
        return _lock_path().exists()
    except Exception:
        return False


def lockdown(reason: str = "manual", *, by: str = "user") -> dict:
    """Enter SAFE STATE: hold every outward capability OFF until restore(). Idempotent (a second call
    just refreshes the marker). Audited. Returns the lockdown record."""
    rec = {"reason": str(reason), "at": _now(), "by": str(by)}
    try:
        STORE.mkdir(exist_ok=True)
        _lock_path().write_text(json.dumps(rec, indent=2), encoding="utf-8")
    except Exception:
        pass
    security_event("lockdown", "Vera entered safe state (all outward capabilities held OFF)",
                   reason=str(reason), by=str(by))
    return rec


def restore(*, by: str = "user") -> bool:
    """Lift a lockdown (return outward capabilities to the user's STORED settings, untouched). Audited.
    Returns True if a lockdown was lifted, False if none was active."""
    was = is_locked()
    try:
        _lock_path().unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass
    if was:
        security_event("restore", "Vera lockdown lifted; stored capability settings restored", by=str(by))
    return was


def status() -> dict:
    """Current security posture: locked?/reason + the recent event trail. Never raises."""
    rec = {}
    if is_locked():
        try:
            rec = json.loads(_lock_path().read_text(encoding="utf-8"))
        except Exception:
            rec = {"reason": "unknown"}
    return {"locked": is_locked(), "lockdown": rec, "recent_events": recent_events(10)}


def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # hermetic-ish: use a temp .anima under CWD
    import tempfile, shutil
    d = tempfile.mkdtemp()
    cwd = os.getcwd()
    try:
        os.chdir(d)
        ok("starts unlocked", not is_locked())
        lockdown("selftest")
        ok("lockdown engages", is_locked())
        ev = recent_events(5)
        ok("lockdown is audited in the security trail", any(e.get("kind") == "lockdown" for e in ev))
        ok("restore lifts it", restore() and not is_locked())
        ok("restore is audited", any(e.get("kind") == "restore" for e in recent_events(5)))
    finally:
        os.chdir(cwd)
        shutil.rmtree(d, ignore_errors=True)
    print("\nINCIDENT SELFTEST: " + ("ALL PASS" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if "--selftest" in args:
        raise SystemExit(_selftest())
    if args and args[0] == "lockdown":
        reason = args[1] if len(args) > 1 else "manual (CLI)"
        rec = lockdown(reason, by="cli")
        print("LOCKDOWN ENGAGED — all outward capabilities held OFF.")
        print(json.dumps(rec, indent=2))
        print("Lift with:  python3 -m anima.incident restore")
    elif args and args[0] == "restore":
        lifted = restore(by="cli")
        print("LOCKDOWN LIFTED — stored capability settings restored." if lifted
              else "No lockdown was active.")
    else:
        print(json.dumps(status(), indent=2))
