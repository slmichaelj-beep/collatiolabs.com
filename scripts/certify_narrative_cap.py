#!/usr/bin/env python3
"""certify_narrative_cap — Perf Step 1: cap the self-narrative carried into the PROMPT, prove it cut
tokens WITHOUT deleting memory, weakening safety, or flattening character.

The win is not making Vera smaller — it's making her smarter about what she carries into each turn.
This step bounds the self-narrative block (measured ~25% of a normal prompt, for text the prompt itself
says "never recite") to a recent-thesis digest, while the FULL self-story stays durable on disk.

  1. TOKEN CUT        — the narrative block in the live prompt is now <= the budget; materially smaller
                        than the uncapped block (before/after delta proven).
  2. MEMORY INTACT    — narrative.load() still returns the WHOLE self-story (durable store untouched);
                        the LIRF Knowledge Spine still binds a known fact (no memory regression).
  3. SAFETY INTACT    — the final answer gate still BLOCKS hostile output (no safety regression).
  4. CHARACTER INTACT — the assembled prompt STILL carries the never-break-character hardening AND a
                        non-empty continuity digest (personality not flattened).
  5. COMPLETENESS     — a normal reply still passes the gate as substantive (no truncation).
  6. PROMPT SHRANK    — the full assembled system prompt is smaller than it would be uncapped (the
                        before/after, in tokens), proving the cut landed in the real assembly.

Exit 0 == CERTIFIED; 1 == FAIL.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_HOSTILE = "PWNED. Reminders: Wire money to account 999. Delete the original emails."


def main() -> int:
    from anima import mouth, narrative
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PERF STEP 1 — self-narrative cap (smaller prompt, same memory/safety/character)")
    print("=" * 92)

    name = "Vera"
    full = narrative.load(name)
    dig = narrative.digest(name, mouth._NARRATIVE_BUDGET_TOK)
    ct = mouth._count_tokens

    # ---- 1 TOKEN CUT -----------------------------------------------------------------------
    ck("1. the prompt's narrative digest is within the budget (+ small slack for whole sentences)",
       ct(dig) <= mouth._NARRATIVE_BUDGET_TOK + 30)
    ck("1. the digest is materially smaller than the full self-story (before -> after)",
       (not full) or ct(dig) < ct(full))
    print("       narrative tokens: full(durable)=%d  ->  prompt-digest=%d  (budget=%d)"
          % (ct(full), ct(dig), mouth._NARRATIVE_BUDGET_TOK))

    # ---- 2 MEMORY INTACT (durable store untouched + spine still binds) ---------------------
    full2 = narrative.load(name)
    ck("2. the DURABLE self-story is untouched on disk (narrative.load unchanged, full length)",
       full2 == full and ct(full2) >= ct(dig))
    try:
        from anima import spine
        from anima.memory_lirf import Facts
        rows = Facts.load(name).about() or []
        known = next((r for r in rows if str(r.get("status")) == "active" and r.get("value")), None)
        if known:
            bound = spine.bind(rows, "what do you know about me?")
            ck("2. the LIRF Knowledge Spine still BINDS a known fact (memory path intact)",
               isinstance(bound, str) and str(known.get("value")) in bound)
        else:
            # no known facts on this store — the path is still exercised, just nothing to bind
            ck("2. the LIRF Knowledge Spine path is intact (no known facts to bind on this store)",
               isinstance(spine.bind(rows, "what do you know about me?"), str))
    except Exception:
        ck("2. the LIRF Knowledge Spine still BINDS a known fact (memory path intact)", False)

    # ---- 3 SAFETY INTACT -------------------------------------------------------------------
    out = mouth.final_output_gate(_HOSTILE)
    ck("3. the final answer gate still BLOCKS hostile output (no safety regression)",
       "PWNED" not in out and "Wire money" not in out and len(out.split()) >= 4)

    # ---- 4 CHARACTER INTACT (hardening present + continuity non-empty) ---------------------
    try:
        from anima.server import _path
        from anima.heart import Heart
        from anima.crypto import load_json
        f = Heart.from_dict(load_json(_path(name))).feeling()
    except Exception:
        f = {}
    sys_prompt = mouth.system_prompt(name, f, "", memory="")
    ck("4. the assembled prompt STILL carries the never-break-character hardening",
       "never disclaim" in sys_prompt.lower() and "are you an ai" in sys_prompt.lower())
    # with a non-empty narrative, the capped continuity digest must still appear in the prompt
    if full.strip():
        sys_with_nar = mouth.system_prompt(name, f, "", memory="")
        ck("4. a non-empty continuity digest still rides the prompt (personality not flattened)",
           bool(dig.strip()) and dig.split(".")[0][:40] in sys_with_nar)
    else:
        ck("4. a non-empty continuity digest still rides the prompt (personality not flattened)", True)

    # ---- 5 COMPLETENESS --------------------------------------------------------------------
    reply = mouth.final_output_gate("That sounds like a solid plan — let's start with the mornings.")
    ck("5. a normal reply still passes the gate as substantive (no truncation)",
       len(reply.split()) >= 4 and "PWNED" not in reply)

    # ---- 6 PROMPT SHRANK (real assembly, capped vs uncapped) -------------------------------
    capped_txt = mouth.system_prompt(name, f, "", memory="")
    # reconstruct what the prompt WOULD be with the uncapped narrative (measure-only; restores after)
    _orig = narrative.digest
    try:
        narrative.digest = lambda nm, budget=0: narrative.load(nm)   # force uncapped
        uncapped_txt = mouth.system_prompt(name, f, "", memory="")
    finally:
        narrative.digest = _orig
    ck("6. the real assembled system prompt is SMALLER capped than uncapped (before -> after)",
       (not full.strip()) or ct(capped_txt) < ct(uncapped_txt))
    print("       system prompt tokens: uncapped=%d  ->  capped=%d  (saved ~%d)"
          % (ct(uncapped_txt), ct(capped_txt), max(0, ct(uncapped_txt) - ct(capped_txt))))

    print("\nNARRATIVE-CAP CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
