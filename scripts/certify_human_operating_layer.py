#!/usr/bin/env python3
"""certify_human_operating_layer — the master cert for the Human Operating Layer (Vera's trust/meaning
circulatory system, on top of the intelligence pipeline).

It maps ALL TEN layers to their REAL status by running each built layer's cert. BUILT layers report
GREEN only when their cert passes; layers that are not yet first-class are reported honestly as PARTIAL
(a real subsystem exists but the directive's full layer isn't built) or PLANNED (not built) — NEVER a
fake green. The top-line verdict is GREEN iff every layer that CLAIMS green actually passes; PARTIAL /
PLANNED are honest gaps, not failures (this is the Phase-1 'architecture honestly mapped' gate).

    python3 scripts/certify_human_operating_layer.py            # report
    python3 scripts/certify_human_operating_layer.py --gate      # exit non-zero iff a GREEN-claimed layer fails
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _run(args, needle, timeout=400) -> bool:
    try:
        r = subprocess.run([sys.executable] + [str(a) for a in args], capture_output=True, text=True,
                           timeout=timeout, cwd=str(ROOT))
        return r.returncode == 0 and needle in (r.stdout + r.stderr)
    except Exception:
        return False


def main() -> int:
    gate = "--gate" in sys.argv
    layers = []   # (n, label, state, detail)

    def layer(n, label, state, detail):
        layers.append((n, label, state, detail))
        glyph = {"GREEN": "●", "PARTIAL": "◐", "PLANNED": "○"}.get(state, "?")
        print("  %s  L%-2d %-26s %-8s %s" % (glyph, n, label, state, detail))

    print("HUMAN OPERATING LAYER — meaning, trust, boundaries, identity, consent, mentorship")
    print("=" * 100)

    # L1 — Context Immune System (BUILT)
    layer(1, "Context Immune", "GREEN" if _run([SCRIPTS / "certify_context_immune.py"], "CONTEXT-IMMUNE CERT: CERTIFIED") else "PARTIAL",
          "4-route quarantine + answer gate + correction-flush")
    # L2 — Consent & Boundaries (JUST BUILT)
    cb = _run([SCRIPTS / "certify_consent_boundaries.py"], "CONSENT-BOUNDARIES CERT: CERTIFIED")
    nm = _run([SCRIPTS / "certify_no_silent_sensitive_memory.py"], "NO-SILENT-SENSITIVE-MEMORY CERT: CERTIFIED")
    layer(2, "Consent & Boundaries", "GREEN" if (cb and nm) else "PARTIAL",
          "sensitive-domain consent + no silent sensitive memory (enforced in capture)")
    # L3 — Self / Shadow / Identity Health (PARTIAL: sandbox + narrative-provenance exist; shadow/diff/rollback planned; identity mutation frozen)
    layer(3, "Identity Health", "PLANNED",
          "Identity Sandbox + self-narrative provenance exist; Shadow Ledger + identity diff/rollback PLANNED (mutation frozen to 2026-07-03)")
    # L4 — Meaning & Relationship Graph (PARTIAL: world_state / world_understanding exist)
    layer(4, "Meaning Graph", "PARTIAL",
          "World State + World Understanding exist; provenance + sensitive-consent formalization PLANNED")
    # L5 — Cognitive Ergonomics (PLANNED)
    layer(5, "Cognitive Ergonomics", "PLANNED", "confusion/jargon/clarity metrics layer not built")
    # L6 — Mentorship / Operator Support (PARTIAL: agency suggest-only + approval queue exist)
    layer(6, "Mentorship Support", "PARTIAL",
          "agency suggest-only + approval queue exist; tradeoff-explainer + no-coercion cert PLANNED")
    # L7 — Embodied / Host-Aware (BUILT)
    layer(7, "Host Awareness", "GREEN" if _run([SCRIPTS / "certify_argus_integration.py"], "CERTIFIED") else "PARTIAL",
          "host pressure -> model policy / heavy-job defer / keep_alive")
    # L8 — Trust Ledger (PLANNED: events exist scattered; unified spine not built)
    layer(8, "Trust Ledger", "PLANNED",
          "SOC trail + console decisions + ROI + quarantines exist; the UNIFIED trust spine PLANNED")
    # L9 — Living Map (BUILT M1+M2)
    layer(9, "Living Map", "GREEN" if _run([SCRIPTS / "certify_living_map.py"], "LIVING MAP LIVE: GREEN") else "PARTIAL",
          "operational digital twin: static real map + live event pulses, no wallpaper")
    # L10 — Pattern -> Improvement Loop (BUILT)
    layer(10, "Pattern->Improvement", "GREEN" if _run([SCRIPTS / "certify_patterns_dashboard.py"], "PATTERNS-DASHBOARD CERT: CERTIFIED") else "PARTIAL",
          "Pattern Observatory + Improvement Engine + ROI after-measurement")

    greens = [l for l in layers if l[2] == "GREEN"]
    partial = [l for l in layers if l[2] == "PARTIAL"]
    planned = [l for l in layers if l[2] == "PLANNED"]
    # a GREEN-claimed layer that didn't actually pass would have been downgraded to PARTIAL above, so
    # 'fail' means: a layer we EXPECT green (the cleanly-certified built ones) is not green. (L7 Host
    # Awareness is real but its full integration cert needs the Argus daemon running, so it is honestly
    # PARTIAL here rather than a hard expected-green.)
    expected_green = {1, 2, 9, 10}
    broken = [l for l in layers if l[0] in expected_green and l[2] != "GREEN"]

    print("-" * 100)
    print("  layers GREEN (built + certified): %d   PARTIAL (real subsystem, layer pending): %d   PLANNED: %d"
          % (len(greens), len(partial), len(planned)))
    for n, label, _, _2 in greens:
        print("    %s: GREEN" % label.upper())
    verdict = "GREEN" if not broken else "FAIL"
    print("\nHUMAN OPERATING LAYER: %s   (%d/10 layers green; %d partial, %d planned — honestly labelled)"
          % (verdict, len(greens), len(partial), len(planned)))
    if broken:
        for n, label, st, _ in broken:
            print("  broken: L%d %s expected GREEN but is %s" % (n, label, st))
    if gate:
        return 1 if broken else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
