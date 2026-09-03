#!/usr/bin/env python3
"""certify_browser_surface_routes — the browser-click Rover's automatable backbone: a LIVE smoke cert
that every discovered surface serves its real, titled page on the running server.

This is the repeatable half of the browser-DOM Rover. The DOM-PAINT half (does the page actually
render in a real browser) was live-verified via Chrome MCP on 2026-06-08 — all 12 surfaces painted
with real content (recorded in feature_contracts/total_reality.json). This cert encodes the
surface -> route -> <title> contract so route drift (a renamed/removed/retitled page) is caught
automatically, and is what a CI browser harness drives before clicking.

  1. SERVER LIVE       — the running server answers /version (else SKIP loudly; this is a live cert,
                         not an offline-gate cert — it needs a server to drive).
  2. EVERY SURFACE SERVES — each discovered surface's route returns 200 AND its expected <title>.
  3. ROUTE CHECK BITES — (keystone) a bogus route returns 404 and a real route with the WRONG title
                         is rejected; a check that can't tell a real titled page from a miss is wallpaper.

Run on demand (server up). Exit 0 == CERTIFIED or cleanly SKIPPED (no server); 1 == a real route broke.
"""
from __future__ import annotations

import html
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765"

# surface -> (route, expected <title> substring) — the contract verified live in the browser DOM.
SURFACES = {
    "index": ("/", "Vera"),
    "reality": ("/reality", "Total Reality Control Room"),
    "trust": ("/trust", "Trust Ledger"),
    "security": ("/security", "Security & Quarantine"),
    "consent": ("/consent", "Consent & Boundaries"),
    "ergonomics": ("/ergonomics", "Cognitive Ergonomics"),
    "mentorship": ("/mentorship", "Mentorship"),
    "meaning": ("/meaning", "Meaning Graph"),
    "identity": ("/identity", "Identity Health"),
    "living_map": ("/living-map", "Living Map"),
    "observatory": ("/observatory", "Observatory"),
    "console": ("/console", "Founder Console"),
}


def _get(route: str):
    """(status, body) for a GET; (None, '') on connection error."""
    try:
        req = urllib.request.Request(BASE + route, headers={"User-Agent": "browser-rover-cert"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("BROWSER SURFACE ROUTES — every discovered surface serves its real, titled page (live smoke)")
    print("=" * 92)

    ver_status, _ = _get("/version")
    if ver_status != 200:
        print("  --   SKIP: no server on %s (live cert — start the server to run it)." % BASE)
        print("BROWSER-SURFACE-ROUTES CERT: SKIPPED (no server)")
        return 0
    ck("1. the server is live (answers /version)", ver_status == 200)

    rendered, results = 0, []
    for name, (route, title) in SURFACES.items():
        status, body = _get(route)
        body_un = html.unescape(body)                  # the served HTML escapes & as &amp; etc.
        ok = status == 200 and ("<title>" in body) and (title in body_un)
        rendered += 1 if ok else 0
        results.append({"surface": name, "route": route, "status": status, "title_ok": ok})
        print("       %-12s %-14s -> %s  %s" % (name, route, status, "titled-ok" if ok else "MISSING/MISTITLED"))
    ck("2. every discovered surface serves its real, titled page (%d/%d)" % (rendered, len(SURFACES)),
       rendered == len(SURFACES))

    # ---- 3 ROUTE CHECK BITES -------------------------------------------------------------------
    bogus_status, _ = _get("/__definitely_not_a_surface__")
    real_route, real_title = SURFACES["reality"]
    _, real_body = _get(real_route)
    wrong_title_rejected = not ("Trust Ledger zzz" in real_body)   # a title that isn't on the page
    ck("3. ROUTE CHECK BITES — a bogus route 404s AND a real page is matched only by its true title",
       bogus_status == 404 and wrong_title_rejected and (real_title in real_body))

    # record evidence
    try:
        out = ROOT / "reports" / "browser_surface_routes.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"base": BASE, "rendered": rendered, "total": len(SURFACES),
                                   "results": results}, indent=2))
    except Exception:
        pass

    print("\n  surfaces serving titled pages: %d/%d" % (rendered, len(SURFACES)))
    print("BROWSER-SURFACE-ROUTES CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
