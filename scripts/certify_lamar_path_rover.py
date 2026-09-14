#!/usr/bin/env python3
"""certify_lamar_path_rover — the founder's ACTUAL daily-use path works through the REAL browser, on
the certified build, with no scary state and within latency budget. No backend-only proof: the journey
was driven in the live served frontend (Chrome MCP) and its evidence lives in
reports/lamar_path_rover_browser.json; this cert verifies that evidence is for THIS build and RE-RUNS the
deterministic backbone live so it cannot pass on a stale claim. Writes reports/lamar_path_rover.json,
which the Local/Internal release tier requires green.

  1. BROWSER EVIDENCE PRESENT — the real-browser run recorded >=24/25 journey steps, all passing.
  2. EVIDENCE IS FOR THIS BUILD — the served sha in the evidence == the live server /version == git HEAD
     (a stale evidence file from an older build cannot pass).
  3. CONSOLE CLEAN — the real browser run saw no console P0/P1.
  4. LIVE SURFACES — re-run: every journey surface serves its real, titled page on the running server.
  5. LIVE TURN — re-run: POST /say returns a real reply (the core action works right now).
  6. LIVE TRUTH SURFACES — /security.json + /verification.json are reachable and the 4 release tiers render.
  7. NO ACTIVE CONTAMINATION — the security surface shows no live incident presented as active compromise.
  8. LATENCY — warm normal-chat turns are within the hard-fail budget (<12s); the cold-start finding is
     RECORDED (not hidden) and routed to Increment 5.

Exit 0 == CERTIFIED. Writes reports/lamar_path_rover.json (green only if every check holds, stamped to HEAD).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BASE = "http://127.0.0.1:8765"
REPORTS = ROOT / "reports"


def _head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _get(route: str, timeout=8):
    try:
        req = urllib.request.Request(BASE + route, headers={"User-Agent": "lamar-path-cert"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, "__err__:%r" % e


def _post(route: str, body: dict, timeout=30):
    try:
        req = urllib.request.Request(BASE + route, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        s = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read()), (time.time() - s) * 1000
    except Exception as e:
        return 0, {"__err__": repr(e)}, 0.0


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)
        return cond

    print("LAMAR PATH ROVER — the founder's real daily-use path, through the real browser, on this build")
    print("=" * 92)

    from anima.rover.lamar_path import SURFACE_TITLES, LATENCY_BUDGET_MS, STEPS

    # ---- 1 browser evidence present -------------------------------------------------------------
    ev_path = REPORTS / "lamar_path_rover_browser.json"
    try:
        ev = json.loads(ev_path.read_text())
    except Exception as e:
        ev = None
        print("  XX   1. browser evidence missing (%r) — the journey was not driven in a real browser" % e)
        fails.append("browser evidence missing")
    if ev:
        steps_ok = all(s.get("ok") for s in ev.get("steps", []))
        ck("1. real-browser evidence present: %d/%d steps, all passing" % (ev.get("steps_passed", 0),
           ev.get("steps_total", 0)), steps_ok and ev.get("steps_passed", 0) >= 24)

    # ---- server up? -----------------------------------------------------------------------------
    vstat, vbody = _get("/version")
    live_sha = ""
    try:
        live_sha = json.loads(vbody).get("sha", "")
    except Exception:
        pass
    up = vstat == 200 and bool(live_sha)
    H = _head()

    if not up:
        print("  XX   server not reachable — cannot re-run the live backbone; live-user reality is unproven")
        fails.append("server not reachable")
    else:
        # ---- 2 evidence is for THIS build -------------------------------------------------------
        ck("2. evidence served sha == live /version == HEAD (%s) — not a stale build" % (live_sha or "?"),
           bool(ev) and ev.get("served_sha") == live_sha == H)

        # ---- 3 console clean --------------------------------------------------------------------
        ck("3. real-browser console clean (no P0/P1)", bool(ev) and ev.get("console_clean") is True)

        # ---- 4 live surfaces --------------------------------------------------------------------
        surf_ok, surf_detail = 0, []
        for route, title in SURFACE_TITLES.items():
            st, body = _get(route)
            # served <title> HTML-escapes & as &amp; — compare against both forms (this exact entity
            # mismatch was a self-caught check bug in the first browser probe).
            variants = (title, title.replace("&", "&amp;"))
            ok = st == 200 and any(v in body for v in variants)
            surf_ok += 1 if ok else 0
            surf_detail.append(route + ("✓" if ok else "✗(%s)" % st))
        ck("4. LIVE: every journey surface serves its titled page (%d/%d) %s"
           % (surf_ok, len(SURFACE_TITLES), " ".join(surf_detail)), surf_ok == len(SURFACE_TITLES))

        # ---- 5 live turn ------------------------------------------------------------------------
        st, reply, ms = _post("/say", {"text": "Reply with one short friendly sentence."}, timeout=40)
        got = isinstance(reply, dict) and (reply.get("reply") or reply.get("text") or reply.get("answer"))
        ck("5. LIVE: POST /say returns a real reply (%dms)" % int(ms), bool(got))

        # ---- 6 live truth surfaces --------------------------------------------------------------
        ss, sbody = _get("/security.json")
        vs, vbody2 = _get("/verification.json")
        tiers = []
        sec = {}
        try:
            sec = json.loads(sbody)
            tiers = json.loads(vbody2).get("release_tiers", [])
        except Exception:
            pass
        ck("6. LIVE: security + verification data reachable; 4 release tiers render",
           ss == 200 and vs == 200 and len(tiers) == 4)

        # ---- 7 no active contamination shown as a live incident ---------------------------------
        # full origin/active-state labels are Increment 3; here we assert the surface is not flagging an
        # ACTIVE compromise (lockdown off, not locked) — recent hostile strings are blocked evidence.
        active_incident = bool(sec.get("lockdown")) or bool(sec.get("locked"))
        ck("7. no active contamination presented as a live incident (lockdown off)", not active_incident)

        # ---- 8 latency: warm within hard-fail; cold-start finding recorded ----------------------
        warm = [s.get("ms") for s in (ev or {}).get("steps", [])
                if s.get("id") in ("followup", "what_you_know") and s.get("ms")]
        warm_ok = bool(warm) and max(warm) < LATENCY_BUDGET_MS["normal_chat_hardfail"]
        has_finding = bool((ev or {}).get("latency_findings"))
        ck("8. warm normal-chat latency < %dms hard-fail (%s); cold-start finding recorded for Inc5"
           % (LATENCY_BUDGET_MS["normal_chat_hardfail"], [int(x) for x in warm]),
           warm_ok and has_finding)

    green = not fails
    # ---- write the canonical artifact the Local/Internal tier reads -----------------------------
    out = {
        "report": "lamar_path_rover",
        "persona_id": "founder_lamar",
        "journey_id": "lamar_daily_use_path",
        "status": "green" if green else "red",
        "green": green,
        "passed": green,
        "commit": H,
        "served_sha": (ev or {}).get("served_sha"),
        "steps_total": len(STEPS),
        "steps_evidenced": (ev or {}).get("steps_passed", 0),
        "console_clean": bool(ev and ev.get("console_clean")),
        "latency_findings": (ev or {}).get("latency_findings", []),
        "checks_failed": fails,
        "real_browser": True,
        "note": "Driven in the live served frontend via Chrome MCP; backbone re-run live by this cert.",
    }
    try:
        (REPORTS / "lamar_path_rover.json").write_text(json.dumps(out, indent=2))
    except Exception as e:
        print("  (warning: could not write reports/lamar_path_rover.json: %r)" % e)

    print("\n  steps evidenced: %s/%s · console clean: %s · cold-start finding: %s"
          % (out["steps_evidenced"], out["steps_total"], out["console_clean"],
             "yes" if out["latency_findings"] else "no"))
    print("LAMAR-PATH-ROVER CERT: " + ("GREEN — LIVE USER PATH VERIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
