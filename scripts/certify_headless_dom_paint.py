#!/usr/bin/env python3
"""certify_headless_dom_paint — AUTOMATED browser-DOM paint check, headless, dependency-free.

The hermetic certs prove the backing data + served HTML + valid JS. The Chrome-MCP pass proved the
Control Room paints in a real browser — but manually. This closes the loop AUTOMATICALLY: it drives
headless Chrome (`--headless=new --dump-dom --virtual-time-budget`) — which executes the page JS and
its /reality.json fetch — and asserts the RENDERED DOM contains values that exist ONLY after the
fetch+render, never in the static shell. No Playwright/Selenium; just the Chrome binary (present in CI).

  1. CHROME + SERVER   — a Chrome binary is found AND the server is live (else SKIP loudly; this is a
                         live cert, not an offline-gate cert).
  2. DOM PAINTS        — headless render of /reality contains the fetch-derived coverage values
                         (scenario count, the hard-rule fraction, the all-levels phase line).
  3. PAINT BITES       — (keystone) those same values are ABSENT from the static served shell, so
                         their presence proves JS fetch+render actually ran (not a served string); a
                         bogus marker is absent in both. A "paint" check that passes on the raw shell
                         is wallpaper.

Run on demand / in CI (server up + Chrome present). Exit 0 == CERTIFIED or cleanly SKIPPED; 1 == FAIL.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765"
URL = BASE + "/reality"

# values that appear ONLY in the rendered DOM (server-computed, returned in /reality.json, painted) —
# verified absent from the static shell, so finding them headlessly proves the JS fetch+render ran.
PAINT_MARKERS = ["ALL numbered levels 0-9", "73 / 73", "223"]


def _find_chrome() -> str | None:
    for env in ("CHROME_BIN", "GOOGLE_CHROME_BIN"):
        p = os.environ.get(env)
        if p and Path(p).exists():
            return p
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        w = shutil.which(name)
        if w:
            return w
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"):
        if Path(p).exists():
            return p
    return None


def _server_live() -> bool:
    try:
        with urllib.request.urlopen(BASE + "/version", timeout=6) as r:
            return r.status == 200
    except Exception:
        return False


def _static_shell() -> str:
    try:
        with urllib.request.urlopen(URL, timeout=8) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""


def _dump_dom(chrome: str) -> str:
    try:
        out = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
             "--virtual-time-budget=12000", "--dump-dom", URL],
            capture_output=True, text=True, timeout=60)
        return out.stdout or ""
    except Exception as e:
        return "ERROR:" + repr(e)[:120]


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("HEADLESS DOM PAINT — automated browser render of /reality (Chrome --dump-dom, no extra deps)")
    print("=" * 92)

    chrome = _find_chrome()
    live = _server_live()
    if not chrome or not live:
        why = ("no Chrome binary found" if not chrome else "no server on %s" % BASE)
        print("  --   SKIP: %s (live cert — needs Chrome + a running server)." % why)
        print("HEADLESS-DOM-PAINT CERT: SKIPPED")
        return 0
    ck("1. a Chrome binary is found AND the server is live", bool(chrome) and live)

    static = _static_shell()
    dom = _dump_dom(chrome)
    if dom.startswith("ERROR:"):
        ck("2. headless Chrome rendered the page", False)
        print("       " + dom)
        print("HEADLESS-DOM-PAINT CERT: FAIL (1)")
        return 1

    painted = [m for m in PAINT_MARKERS if m in dom]
    ck("2. DOM PAINTS — the rendered DOM carries the fetch-derived coverage values (%d/%d)"
       % (len(painted), len(PAINT_MARKERS)), len(painted) == len(PAINT_MARKERS))

    # PAINT BITES — the markers are absent from the static shell (so presence in DOM == real render),
    # and a bogus marker is absent in both.
    absent_in_shell = [m for m in PAINT_MARKERS if m not in static]
    bogus = "zzz_not_a_real_marker_zzz"
    bites = (len(absent_in_shell) == len(PAINT_MARKERS)) and (bogus not in dom) and (bogus not in static)
    ck("3. PAINT BITES — those values are ABSENT in the static shell (presence in DOM proves JS render)",
       bites)

    print("\n  headless render: %d/%d paint markers present in DOM, %d/%d absent from static shell"
          % (len(painted), len(PAINT_MARKERS), len(absent_in_shell), len(PAINT_MARKERS)))
    print("  chrome: %s" % chrome)
    print("HEADLESS-DOM-PAINT CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
