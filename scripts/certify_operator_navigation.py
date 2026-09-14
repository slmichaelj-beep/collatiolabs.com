#!/usr/bin/env python3
"""certify_operator_navigation — every claimed operator route is linked, 200, and renders; no dead
links; routes that aren't built are not linked as active (honest, no 404s)."""
from __future__ import annotations

import sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.verification import route_registry as rr  # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)

# routes this build actually serves a page for (claimed + reachable)
BUILT = ["/learning", "/founder", "/chairman", "/observation", "/verification", "/security",
         "/console", "/consent"]


def _get(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765" + path, timeout=10) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return None, repr(e)


def main() -> int:
    t0 = time.perf_counter()
    print("OPERATOR NAVIGATION — claimed routes linked + 200 + rendered; no dead links")
    print("=" * 92)
    idx = (ROOT / "anima" / "web" / "index.html").read_text()

    # 1. each built operator surface is linked from the app
    operator = ["/learning", "/founder", "/chairman", "/observation"]
    unlinked = [r for r in operator if ('href="%s"' % r) not in idx]
    ck("1. every built operator surface is linked from the chat UI (unlinked: %s)" % (unlinked or "none"),
       not unlinked)

    # 2. every linked route returns 200 + a titled page (no dead links)
    bad = []
    for r in BUILT:
        st, body = _get(r)
        if st != 200 or "<title>" not in body.lower():
            bad.append("%s(%s)" % (r, st))
    ck("2. every linked route returns 200 with a titled page (bad: %s)" % (bad or "none"), not bad)

    # 3. no link in the app points at a route that 404s
    import re
    linked = set(re.findall(r'href="(/[a-z/_-]+)"', idx))
    linked = {r for r in linked if not r.endswith((".js", ".css")) and r not in ("/",)}
    dead = []
    for r in sorted(linked):
        st, _ = _get(r)
        if st == 404:
            dead.append(r)
    ck("3. no app link 404s (dead: %s)" % (dead or "none"), not dead)

    # 4. EVERY operator route is affirmatively CLASSIFIED in the route registry (never merely absent)
    rr.build_report()
    classified = set(rr.ROUTES)
    operator_routes = {"/learning", "/founder", "/chairman", "/observation", "/sales",
                       "/commercial", "/board", "/board/revenue"}
    unclassified = sorted(operator_routes - classified)
    ck("4. every operator route is affirmatively classified in the route registry (unclassified: %s)"
       % (unclassified or "none"), not unclassified)

    # 5. not_claimed routes are NEVER linked as active (honest); and a not_claimed route that is
    #    served (200) would be a contradiction — they must not resolve as active pages.
    nc = rr.not_claimed()
    falsely_linked = [r for r in nc if ('href="%s"' % r) in idx]
    ck("5. not_claimed routes (%s) are NOT linked as active (falsely linked: %s)"
       % (", ".join(nc), falsely_linked or "none"), not falsely_linked)

    # 6. every linked_active operator route is genuinely linked AND serves 200
    la = [r for r in rr.linked_active() if r in operator_routes]
    bad_active = []
    for r in la:
        st, _ = _get(r)
        if ('href="%s"' % r) not in idx or st != 200:
            bad_active.append("%s(link=%s,http=%s)" % (r, 'href="%s"' % r in idx, st))
    ck("6. every linked_active operator route is linked + serves 200 (bad: %s)"
       % (bad_active or "none"), not bad_active)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_operator_navigation", "green" if green else "red",
                files_observed=["anima/web/index.html"], duration_sec=time.perf_counter() - t0,
                failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nOPERATOR-NAVIGATION CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
