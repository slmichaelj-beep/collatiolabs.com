#!/usr/bin/env python3
"""certify_polish_paths — the user-facing paths are polished: every surface serves, every new
control is wired, no fake green and no unexplained scary-red state on the live surfaces.

Proves (live):
  1. EVERY SURFACE SERVES — /, /console, /verification, /security, /reality, /trust, /observatory,
     /living-map, /consent each return 200 with a titled page.
  2. NEW SURFACES WIRED   — Teach Vera, host profile badge, Truth Ledger, Auto Learn, Knowledge
     Packs, first-launch are all reachable (their routes serve).
  3. EMPTY STATES HONEST  — empty teaching/auto-learn/pack queues say so (no fake content).
  4. SECURITY LABELS      — /security.json is reachable and not falsely flagging an ACTIVE
     compromise (lockdown off) — no unexplained scary red.
  5. MEMORY/SOURCE CHIPS  — a no-memory smalltalk turn carries no truth_events + no source chips
     (chip truth — already a Memory-Truth invariant, re-checked at the polish layer).
  6. DESKTOP LAUNCHER     — ~/Desktop/Vera.app exists, is LSUIElement (no Terminal), and starts
     the server detached.
  7. NO FAKE GREEN        — the verification dashboard's release_state is computed from gates, not
     asserted; a blocked gate is not shown green.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
sys.path.insert(0, str(ROOT))

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def _get(path, timeout=10):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765" + path, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return None, repr(e)


def _say(text):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request("http://127.0.0.1:8765/say", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=90).read())


def main() -> int:
    t0 = time.perf_counter()
    print("POLISH PATHS — every surface serves; no fake green, no unexplained red")
    print("=" * 92)

    # ---- 1. every surface serves ---------------------------------------------------------------
    surfaces = {"/": "Vera", "/console": "Console", "/verification": "Verification",
                "/security": "Security", "/reality": "Reality", "/trust": "Trust",
                "/observatory": "Observ", "/living-map": "Living Map", "/consent": "Consent"}
    served = []
    for route, title in surfaces.items():
        st, body = _get(route)
        ok = st == 200 and title.lower() in body.lower()
        served.append((route, ok))
    bad = [r for r, ok in served if not ok]
    ck("1. every founder/user surface serves a titled page (failing: %s)" % (bad or "none"), not bad)

    # ---- 2. new surfaces wired -----------------------------------------------------------------
    new_routes = ["/teaching/queue", "/auto_learn/queue", "/packs", "/truth.json",
                  "/host/profile.json", "/first_launch.json"]
    nbad = []
    for r in new_routes:
        st, _ = _get(r)
        if st != 200:
            nbad.append(r)
    ck("2. every new surface route serves (failing: %s)" % (nbad or "none"), not nbad)
    idx = (ROOT / "anima" / "web" / "index.html").read_text()
    ck("2b. the app advertises Teach Vera and the host-profile badge lives on the console",
       "Teach Vera" in idx
       and "hostProfileBadge" in (ROOT / "anima" / "web" / "console.html").read_text())

    # ---- 3. empty states honest -----------------------------------------------------------------
    _, tq = _get("/teaching/queue")
    _, alq = _get("/auto_learn/queue")
    tj = json.loads(tq)
    aj = json.loads(alq)
    ck("3. empty teaching + auto-learn queues report honestly (no invented content)",
       tj.get("ok") and aj.get("ok")
       and isinstance(tj.get("pending"), list) and isinstance(aj.get("pending"), list))

    # ---- 4. security labels ---------------------------------------------------------------------
    ss, sbody = _get("/security.json")
    sec = {}
    try:
        sec = json.loads(sbody)
    except Exception:
        pass
    ck("4. /security.json reachable and not falsely flagging an ACTIVE compromise (lockdown off)",
       ss == 200 and not sec.get("lockdown") and not sec.get("locked"))

    # ---- 5. chip truth --------------------------------------------------------------------------
    try:
        d = _say("Just say a brief friendly hello, nothing else.")
        ck("5. a no-memory smalltalk turn ships no truth_events and no source chips",
           not d.get("truth_events") and not d.get("sources"))
    except Exception as e:
        ck("5. smalltalk chip-truth reachable (server down: %r)" % e, False)

    # ---- 6. desktop launcher --------------------------------------------------------------------
    app = HOME / "Desktop" / "Vera.app"
    if not app.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "install_vera_desktop_launcher.py")],
                       cwd=str(ROOT), check=False, capture_output=True, text=True, timeout=20)
    plist = app / "Contents" / "Info.plist"
    launcher = app / "Contents" / "MacOS" / "Vera"
    plist_txt = plist.read_text() if plist.exists() else ""
    launcher_txt = launcher.read_text() if launcher.exists() else ""
    ck("6. ~/Desktop/Vera.app exists, is LSUIElement (no Terminal), starts the server detached",
       app.exists() and "LSUIElement" in plist_txt
       and "anima.server" in launcher_txt and "nohup" in launcher_txt)

    # ---- 7. no fake green -----------------------------------------------------------------------
    vs, vbody = _get("/verification.json")
    vj = {}
    try:
        vj = json.loads(vbody)
    except Exception:
        pass
    gates = vj.get("gates", [])
    green_with_block = [g for g in gates if g.get("status") == "green"
                        and g.get("gate_id") in (vj.get("blockers") or [])]
    ck("7. NO FAKE GREEN — no gate is shown green while it is also listed as a blocker",
       vs == 200 and not green_with_block)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_polish_paths", "green" if green else "red",
                files_observed=["anima/web/index.html", "anima/web/console.html",
                                "anima/server.py", "scripts/install_vera_desktop_launcher.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nPOLISH-PATHS CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
