#!/usr/bin/env python3
"""certify_new_surfaces_rover — the new surfaces are REACHABLE and RENDER in a real browser.

Drives /learning, /founder, /chairman through a real browser engine (Playwright Chromium),
asserting each serves its titled page, renders its data section (not a stuck 'loading…'), and
throws no console errors / page errors. Also asserts each is reachable from the chat UI's nav.
"""
from __future__ import annotations

import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)

SURFACES = [
    ("/learning", "Learning Integrity", "Active Memories"),
    ("/founder", "Where do we stand", "Founder decisions needed"),
    ("/chairman", "Where should my capital", "Ventures"),
]


def main() -> int:
    t0 = time.perf_counter()
    print("NEW-SURFACES ROVER — /learning, /founder, /chairman render in a real browser")
    print("=" * 92)

    # reachable from the chat UI nav
    idx = (ROOT / "anima" / "web" / "index.html").read_text()
    ck("0. all three surfaces are linked from the chat UI settings drawer",
       'href="/learning"' in idx and 'href="/founder"' in idx and 'href="/chairman"' in idx)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        ck("playwright available", False)
        print("  (playwright missing: %r)" % e)
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for route, title_frag, body_frag in SURFACES:
            errs = []
            pg = browser.new_page()
            pg.on("console", lambda m, E=errs: E.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e, E=errs: E.append(str(e)))
            try:
                pg.goto("http://127.0.0.1:8765" + route, wait_until="networkidle", timeout=25000)
                title = pg.title()
                # wait for the data section to populate (not stuck on 'loading…')
                try:
                    pg.wait_for_function(
                        "frag => document.body.innerText.toLowerCase().includes(frag.toLowerCase())",
                        arg=body_frag, timeout=12000)
                    rendered = True
                except Exception:
                    rendered = False
                body = pg.inner_text("body")
                ck("%s serves its titled page (title=%r)" % (route, title),
                   title_frag.lower() in (title + " " + body).lower())
                ck("%s rendered its data section (not stuck loading)" % route, rendered)
                ck("%s console + page errors clean (errs=%d)" % (route, len(errs)), not errs)
            except Exception as e:
                ck("%s reachable (%r)" % (route, e), False)
            finally:
                pg.close()
        browser.close()

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_new_surfaces_rover", "green" if green else "red",
                files_observed=["anima/web/learning.html", "anima/web/founder.html",
                                "anima/web/chairman.html", "anima/web/index.html"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nNEW-SURFACES-ROVER CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
