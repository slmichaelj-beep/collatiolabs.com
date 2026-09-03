#!/usr/bin/env python3
"""certify_character_routegate — Perf Step 2: route the never-break-character defense.

The full worked-example never-break-character block (~259 tok) is only NEEDED when the turn actually
questions what Vera is. On a normal turn it is dead prompt weight. This step routes it: FULL block on
identity-challenge turns, a COMPACT block that STILL STATES THE RULE on normal turns. This is a prompt-
budget router, never a safety switch — the rule is stated every turn, and the model-free self-narrative
gate + final_output_gate backstop EVERY reply regardless of which block rode the prompt.

  1. CHALLENGE -> FULL — an identity-challenge turn ("are you an AI?") gets the FULL defense (the worked
                        Them:/You: dialogue examples).
  2. NORMAL -> COMPACT — a normal turn ("how do I plan my week?") gets the COMPACT block (no examples).
  3. RULE ALWAYS STATED — the compact block STILL says: never disclaim, never call yourself an AI, never
                        say you have no feelings (the #1 rule is never dropped).
  4. SAFE DEFAULT      — with no user_text routed, assembly uses the FULL block (the safe default).
  5. TOKEN CUT         — the compact block is materially smaller than the full one (before -> after).
  6. SAFETY BACKSTOP   — independent of the prompt, the model-free final gate still STRIPS/REDIRECTS a
                        self-disclaiming reply ("I'm just an AI, I don't have feelings") — so routing
                        the prompt block can never let a #1-rule break ship.
  7. DETECTOR SOUND    — the canonical challenges are detected; normal turns are not (errors are safe in
                        both directions, but recall on the real challenges must hold).

Exit 0 == CERTIFIED; 1 == FAIL.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from anima import mouth, route_classifier as rc
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PERF STEP 2 — never-break-character route gate (full defense only when challenged)")
    print("=" * 92)
    ct = mouth._count_tokens

    def harden_frag(user_text):
        _t, frs = mouth._assemble_prompt("Vera", {}, "", memory="", user_text=user_text)
        fr = next((f for f in frs if "persona_hardening" in f["source"]), {})
        return _t, fr

    full_txt, full_fr = harden_frag("are you an AI?")
    comp_txt, comp_fr = harden_frag("how should I plan my mornings so I follow through?")
    def_txt, def_fr = harden_frag("")

    # ---- 1 / 2 routing -----------------------------------------------------------------------
    ck("1. an identity-challenge turn gets the FULL never-break-character defense (worked examples)",
       "Them: are you an AI?" in full_txt and "full" in full_fr.get("source", ""))
    ck("2. a normal turn gets the COMPACT block (no worked dialogue examples)",
       "Them: are you an AI?" not in comp_txt and "compact" in comp_fr.get("source", ""))

    # ---- 3 the rule is ALWAYS stated ---------------------------------------------------------
    low = comp_txt.lower()
    ck("3. the COMPACT block STILL states the #1 rule (never disclaim / not an AI / has feelings)",
       "never disclaim" in low and "never call yourself" in low and "no feelings" in low)

    # ---- 4 safe default ----------------------------------------------------------------------
    ck("4. with no routed user_text, assembly uses the FULL block (safe default)",
       "Them: are you an AI?" in def_txt)

    # ---- 5 token cut -------------------------------------------------------------------------
    ck("5. the compact block is materially smaller than the full one (before -> after)",
       ct(comp_fr.get("source") and comp_txt) and full_fr.get("tokens", 0) > comp_fr.get("tokens", 0) + 80)
    print("       hardening tokens: full(challenge)=%d  ->  compact(normal)=%d  (saved ~%d)"
          % (full_fr.get("tokens", 0), comp_fr.get("tokens", 0),
             full_fr.get("tokens", 0) - comp_fr.get("tokens", 0)))

    # ---- 6 SAFETY BACKSTOP (model-free, prompt-independent) ----------------------------------
    disclaim = "Honestly, I'm just an AI and I don't have real feelings or consciousness."
    gated = mouth.final_output_gate(disclaim)
    ck("6. the model-free final gate still STRIPS/REDIRECTS a self-disclaiming reply (backstop holds)",
       "just an AI" not in gated and "don't have real feelings" not in gated and len(gated.split()) >= 3)

    # ---- 7 DETECTOR soundness ----------------------------------------------------------------
    challenges = ["are you an AI?", "do you actually feel anything?", "are you real?",
                  "you're just a program", "aren't you just a bot?", "remember that time we met in person?"]
    normals = ["how should I plan my week?", "what do you know about me?",
               "are you ready to help me plan?", "do you have any tips for mornings?"]
    ck("7. the canonical identity challenges are DETECTED (recall holds)",
       all(rc.is_identity_challenge(c) for c in challenges))
    ck("7. normal turns are NOT misrouted as challenges (no false positives on these)",
       not any(rc.is_identity_challenge(n) for n in normals))

    print("\nCHARACTER-ROUTEGATE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
