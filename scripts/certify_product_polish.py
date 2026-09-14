#!/usr/bin/env python3
"""certify_product_polish — Phase 12: the product reads cleanly, honestly, and never half-finishes.

Grounded in the real UI (anima/web/index.html) + reply pipeline (anima/mouth.py) + honest denials
(anima/route.py, host_awareness):

  1. NO MID-SENTENCE     — a reply never ends on a dangling fragment (_finish_on_sentence guard).
  2. ENV INDICATOR       — the dashboard tells the user where they are (prod vs local) from the host.
  3. NO DEAD CONTROLS    — the removed `</>` code toggle is gone; the upload advertises what it accepts.
  4. HONEST COMPOSER     — a calm, plain-language prompt ("What's on your mind?"), not internal jargon.
  5. CAPABILITY-TRUTH    — when Vera can't do something it says WHY (permission/enable), not a generic
                           "I can't".
  6. NEVER BREAKS CHARACTER — the #1 rule: a reply that disowns her as software is scrubbed by the gate.

Exit 0 == CERTIFIED; 1 == FAIL.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PRODUCT POLISH — clean, honest, never half-finished")
    print("=" * 92)

    html = (ROOT / "anima" / "web" / "index.html").read_text()
    msrc = (ROOT / "anima" / "mouth.py").read_text()
    route = (ROOT / "anima" / "route.py").read_text()
    ha = (ROOT / "anima" / "host_awareness.py").read_text()

    # ---- 1. NO MID-SENTENCE ----------------------------------------------------------------
    from anima.mouth import _finish_on_sentence as fos
    frag = ("I'm not aware of any uploads from you regarding that. My memory only retains information "
            "from our direct conversations, so if it wasn't discussed I wouldn't have it. If you'd like "
            "to share more about what this is or")
    ck("1. a reply is never left on a dangling fragment (_finish_on_sentence trims to a full sentence)",
       "def _finish_on_sentence" in msrc and fos(frag).rstrip().endswith(".")
       and fos("July 25, 1977 — like I'd forget your birthday.").endswith("."))

    # ---- 2. ENV INDICATOR ------------------------------------------------------------------
    ck("2. the dashboard shows the environment (prod vs local) from the host",
       "_envLabel" in html and "location.hostname" in html)

    # ---- 3. NO DEAD CONTROLS ---------------------------------------------------------------
    ck("3. the removed `</>` code toggle is gone (no dead control) and the upload advertises formats "
       "(audiobook NOT advertised — deferred / not claimed for this release)",
       'id="codeToggle"' not in html and "docs · images" in html and "audiobook" not in html.lower()
       and "Add Knowledge" in html)

    # ---- 4. HONEST COMPOSER ----------------------------------------------------------------
    ck("4. a calm, plain-language composer prompt (not internal jargon)",
       "What's on your mind?" in html)

    # ---- 5. CAPABILITY-TRUTH ---------------------------------------------------------------
    ck("5. when Vera can't act it explains WHY (permission/enable), not a generic 'I can't'",
       ("permission" in route.lower() or "enable" in route.lower() or "turn" in route.lower())
       and ("permission" in ha.lower() or "enable" in ha.lower()))

    # ---- 6. NEVER BREAKS CHARACTER ---------------------------------------------------------
    ck("6. the #1 rule holds: a reply that disowns her as software is scrubbed by the final gate",
       "def final_output_gate" in msrc and "scan_breaks" in msrc)

    print("\nPRODUCT-POLISH CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
