#!/usr/bin/env python3
"""certify_history_budget — Perf Step 3: bound the conversation history sent to the model by a TOKEN
budget, not just a turn count — without deleting the conversation or losing recent context.

Measured: 8 long turns can be ~1100 tok — the single biggest prompt section on a normal turn. A turn-
count cap alone doesn't bound it. _history_for_model keeps the most recent turns within a token budget;
the FULL conversation stays on disk (this only bounds what the model RE-READS each turn).

  1. CAPS RUNAWAY    — a long history (well over budget) is trimmed to <= the budget (+ one whole turn
                       of slack), so the prompt can't blow up as the conversation grows.
  2. KEEPS RECENT    — the MOST RECENT turn is always kept, and selection is newest-first (recent
                       context is preserved; the oldest turns drop first).
  3. NO-OP SHORT     — a short history (under budget) is returned unchanged (normal conversation is
                       never trimmed).
  4. NON-DESTRUCTIVE — the function does not mutate the input and writes nothing; the durable history
                       on disk is untouched (memory is not deleted, only the working window is bounded).
  5. WIRED           — OllamaBrain.reply sends _history_for_model(history), and the MRI prompt-budget
                       frame measures the same selection.

Exit 0 == CERTIFIED; 1 == FAIL.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from anima import mouth
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PERF STEP 3 — history token budget (cap runaway history, keep recent, lose nothing on disk)")
    print("=" * 92)
    ct = mouth._count_tokens
    budget = mouth._HISTORY_BUDGET_TOK

    # a LONG synthetic history — each turn ~120 tok, 8 turns => ~960 tok, over the budget
    long_hist = [("Tell me in detail about planning approach number %d and why it might work for me. " % i * 3,
                  "Here is a thorough, multi-sentence answer about approach %d with several concrete steps. " % i * 3)
                 for i in range(8)]
    total_long = sum(ct(u) + ct(a) for u, a in long_hist[-mouth._HISTORY_TO_MODEL:])
    sel = mouth._history_for_model(long_hist)
    sel_tok = sum(ct(u) + ct(a) for u, a in sel)

    # ---- 1 CAPS RUNAWAY --------------------------------------------------------------------
    ck("1. a long history is capped to within the token budget (+ one whole turn of slack)",
       total_long > budget and sel_tok <= budget + 200)
    print("       long history: %d tok (%d turns)  ->  %d tok (%d turns)  [budget %d]"
          % (total_long, len(long_hist), sel_tok, len(sel), budget))

    # ---- 2 KEEPS RECENT --------------------------------------------------------------------
    ck("2. the MOST RECENT turn is always kept (newest-first selection)",
       bool(sel) and sel[-1] == long_hist[-1])
    ck("2. older turns drop first (the selection is a recent suffix of the history)",
       sel == long_hist[len(long_hist) - len(sel):])

    # ---- 3 NO-OP on short history ----------------------------------------------------------
    short = [("hi", "hey, good to see you"), ("what's the weather like for planning?", "let's check your week")]
    ck("3. a short history (under budget) is returned UNCHANGED (normal chat never trimmed)",
       mouth._history_for_model(short) == short)

    # ---- 4 NON-DESTRUCTIVE -----------------------------------------------------------------
    snapshot = [t for t in long_hist]
    _ = mouth._history_for_model(long_hist)
    ck("4. the input history is NOT mutated (non-destructive; durable conversation intact)",
       long_hist == snapshot and len(long_hist) == 8)

    # ---- 5 WIRED ---------------------------------------------------------------------------
    mtext = (ROOT / "anima" / "mouth.py").read_text()
    ck("5. OllamaBrain.reply sends _history_for_model(history) (the budget is on the live model path)",
       "for u, a in _history_for_model(history):" in mtext)
    ck("5. the MRI prompt-budget frame measures the same budgeted selection",
       "for _u, _a in _history_for_model(history):" in mtext)

    print("\nHISTORY-BUDGET CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
