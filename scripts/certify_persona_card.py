#!/usr/bin/env python3
"""
certify_persona_card — GET /persona serves Vera's persona card, OBSERVATION-ONLY (identity frozen).

The persona card is the system-character text that defines who Vera is. This certifies the
DETERMINISTIC contract through the SAME anima.mouth functions the server's GET/POST /persona call:

  A. SERVED + REAL — load_persona() for a fresh creature returns the canonical DEFAULT_PERSONA:
     non-empty, mentions the creature's name and the HONESTY-is-highest rule, with no
     TODO/placeholder/lorem. The card is never blank wallpaper.
  B. STABLE — two successive load_persona() reads are byte-identical (a read is a pure function;
     the served card does not drift turn to turn).
  C. OBSERVATION-ONLY — before any read no {name}.persona.md exists, and after repeated reads it
     STILL does not exist. Observing the card writes NOTHING — identity is frozen against being
     merely looked at.
  D. EXPLICIT EDIT IS THE ONLY MUTATION — save_persona(name, text) (the POST /persona path) then
     load_persona returns that text; so the card is editable only by an EXPLICIT write, never
     silently by a GET, and a fall-back-to-default still holds when a saved card is blank.

Hermetic + offline: mouth.STORE is in gate0_prime_experience._temp_store's redirect set, so
.anima/{name}.persona.md lands in a temp dir; the real .anima is fingerprinted before/after and
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
    from anima import mouth
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PERSONA CARD — GET /persona serves a stable card, observation-only (identity frozen)")
    print("=" * 82)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        N = "PersonaCert"

        # ---- A. SERVED + REAL --------------------------------------------------------
        card = mouth.load_persona(N)            # exactly what GET /persona returns under "persona"
        ck("A1: the served card is a non-empty string", isinstance(card, str) and bool(card.strip()))
        ck("A2: the served card is the canonical DEFAULT for a fresh creature",
           card == mouth.DEFAULT_PERSONA.format(name=N))
        ck("A3: the card names the creature and states the HONESTY-highest rule",
           N in card and "HONESTY" in card)
        low = card.lower()
        ck("A4: the served card carries no placeholder wallpaper",
           not any(tok in low for tok in ("todo", "placeholder", "lorem")))

        # ---- B. STABLE ---------------------------------------------------------------
        ck("B1: two successive reads are byte-identical (a read is pure / non-drifting)",
           mouth.load_persona(N) == mouth.load_persona(N))

        # ---- C. OBSERVATION-ONLY -----------------------------------------------------
        ck("C1: before any read, no persona file exists on disk", not mouth.persona_path(N).exists())
        for _ in range(5):
            mouth.load_persona(N)               # observe repeatedly
        ck("C2: after repeated reads, STILL no persona file — observing writes nothing (frozen)",
           not mouth.persona_path(N).exists())

        # ---- D. EXPLICIT EDIT IS THE ONLY MUTATION -----------------------------------
        custom = "You are " + N + ". HONESTY is your highest rule. (explicit edit marker 92817)"
        mouth.save_persona(N, custom)           # the POST /persona path — an EXPLICIT write
        ck("D1: an explicit save_persona persists and is then served (editable only by POST)",
           mouth.load_persona(N) == custom and mouth.persona_path(N).exists())
        # a blank saved card falls back to the canonical default (never serves emptiness).
        mouth.save_persona(N, "   ")
        ck("D2: a blank saved card falls back to the canonical DEFAULT (never blank wallpaper)",
           mouth.load_persona(N) == mouth.DEFAULT_PERSONA.format(name=N))

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nPERSONA-CARD CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
