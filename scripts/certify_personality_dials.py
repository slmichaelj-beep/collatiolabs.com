#!/usr/bin/env python3
"""
certify_personality_dials — the eight 0-100 personality sliders in Settings -> 'Personality'.

Vera's manner (never her honesty) is tuned by eight dials. This certifies the DETERMINISTIC
contract floor through the SAME anima.dials functions the server's GET/POST /dials calls and the
web panel renders:

  A. LOAD WITH SANE DEFAULTS — a fresh creature's dials are Vera's real temperament (dials.DEFAULT:
     warmth DOWN, edge/openness UP), NOT a flat all-50; dials.ui() (the exact payload GET /dials
     returns to the panel) is one row per axis (8), each carrying key + label + a current value.
  B. SAVE IS DURABLE — dials.save({warmth:90, edge:10}) returns the saved values AND re-reading
     dials.load() FRESH from disk still shows warmth 90 / edge 10 (restart-survival).
  C. CLAMP + COERCE — save clamps an over-range value to 100, an under-range to 0, a non-numeric
     to the neutral 50, and silently drops an unknown key. No corrupt input can persist an
     out-of-range or junk manner.
  D. ENDPOINT ROUND-TRIP + PURE COMPILE — the GET(ui) -> save -> GET(ui) round-trip is value-stable,
     and to_prompt() is a pure deterministic function of the dials (same dials -> same directives),
     which is exactly how POST /dials feeds the live manner.

Hermetic + offline: dials.STORE is in gate0_prime_experience._temp_store's redirect set, so
.anima/{name}.dials.json lands in a temp dir; the real .anima is fingerprinted before/after and
asserted byte-identical. No model, no network. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import dials
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PERSONALITY DIALS — eight 0-100 sliders (manner, never honesty)")
    print("=" * 64)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        N = "DialsCert"

        # ---- A. LOAD WITH SANE DEFAULTS ---------------------------------------------
        d0 = dials.load(N)
        ck("A1: a fresh creature's dials == Vera's real DEFAULT temperament",
           d0 == dials.DEFAULT)
        ck("A2: the default is a deliberate character, not a flat all-50",
           d0.get("warmth") == 35 and d0.get("edge") == 68 and d0 != {a["key"]: 50 for a in dials.AXES})
        rows = dials.ui(N)
        ck("A3: ui() (the GET /dials payload) has one row per axis (8)", len(rows) == len(dials.AXES) == 8)
        ck("A4: every ui row carries key + label + a current value",
           all(set(r) >= {"key", "label", "value"} for r in rows)
           and {r["key"] for r in rows} == {a["key"] for a in dials.AXES})
        ck("A5: ui values are 0-100 ints matching the loaded dials",
           all(isinstance(r["value"], int) and 0 <= r["value"] <= 100 for r in rows)
           and {r["key"]: r["value"] for r in rows} == d0)

        # ---- B. SAVE IS DURABLE ------------------------------------------------------
        saved = dials.save(N, {"warmth": 90, "edge": 10})
        ck("B1: save returns the saved values", saved.get("warmth") == 90 and saved.get("edge") == 10)
        reloaded = dials.load(N)            # fresh read from disk
        ck("B2: a saved dial value is DURABLE on reload (restart-survival)",
           reloaded.get("warmth") == 90 and reloaded.get("edge") == 10)
        ck("B3: untouched axes keep their default on a partial save",
           reloaded.get("openness") == dials.DEFAULT["openness"])

        # ---- C. CLAMP + COERCE -------------------------------------------------------
        cl = dials.save(N, {"warmth": 999, "edge": -50, "playfulness": "abc", "bogus_axis": 7})
        ck("C1: an over-range value clamps to 100", cl.get("warmth") == 100)
        ck("C2: an under-range value clamps to 0", cl.get("edge") == 0)
        ck("C3: a non-numeric value coerces to the neutral 50", cl.get("playfulness") == 50)
        ck("C4: an unknown key is silently dropped (never persisted)", "bogus_axis" not in cl)
        ck("C5: every persisted value is an in-range 0-100 int",
           all(isinstance(v, int) and 0 <= v <= 100 for v in cl.values()))

        # ---- D. ENDPOINT ROUND-TRIP + PURE COMPILE -----------------------------------
        # the GET(ui) -> POST(save) -> GET(ui) round-trip the panel does is value-stable.
        before = {r["key"]: r["value"] for r in dials.ui(N)}
        dials.save(N, before)
        after = {r["key"]: r["value"] for r in dials.ui(N)}
        ck("D1: GET -> save -> GET round-trip is value-stable", before == after)
        # to_prompt is how POST /dials shapes the live manner: a pure function of the dials.
        ck("D2: to_prompt is a pure deterministic function of the dials",
           dials.to_prompt(after) == dials.to_prompt(after))
        ck("D3: a strong off-neutral dial is reflected in the compiled directives, "
           "a neutral one is omitted",
           ("warmth" in dials.to_prompt({"warmth": 0}).lower() or
            "cool" in dials.to_prompt({"warmth": 0}).lower())
           and dials.to_prompt({k: 50 for k in (a["key"] for a in dials.AXES)}) == "")

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nPERSONALITY-DIALS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
