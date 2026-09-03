#!/usr/bin/env python3
"""
certify_known_fact — the deterministic KNOWN-FACT (no-hedge) recall seam, through the REAL _turn.

Proves the "known-fact binding, no-hedge" live path that the Program Reality Audit found PARTIAL
(it could only prove full recall with a --live model). The deterministic seam closes that:

  * A clean, single-clause personal-fact question whose trait is on record at the [KNOWN] bar is
    answered STRAIGHT from memory (spine.answer_from_fact) — warm, exact, model-free — so the model
    never gets the chance to hedge or disclaim a fact we hold. backend memory:known_fact.
  * The SAME clean question whose trait is NOT on record ships spine.honest_unknown — a warm
    "I don't have your ___ — when is it?" that admits + asks and NEVER confabulates a value.
    backend memory:honest_unknown.
  * Either way the text crosses the SAME #1-rule final_output_gate (no second return path), and the
    Whole-System MRI records the seam. A compound/emotional turn does NOT trigger it (no hijack).

Hermetic: every store is redirected to a temp dir (gate0_prime_experience._temp_store); no model is
needed (the seam short-circuits BEFORE the LLM); the real .anima is never read or written.
Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store

_KF_STAGES = {"known_fact_match", "deterministic_known_fact_reply", "final_gate"}
_HEDGES = ("i think", "if i remember", "i believe", "not sure", "don't have", "don't actually have",
           "i'm not certain", "as far as i", "i guess")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december")


def main() -> int:
    import anima.server as server
    from anima import memory_lirf, spine, telemetry, mouth

    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("KNOWN-FACT (no-hedge) recall seam — through anima.server._turn")
    print("=" * 64)
    with _temp_store():
        # ---- A. a KNOWN fact -> deterministic exact answer, zero hedge, no model ----------
        name = "KFKnown"
        server._ensure(name, 64)
        memory_lirf.capture(name, "my birthday is March 4, 1991")
        row = memory_lirf.Facts.load(name).lookup(memory_lirf.SELF, "birthday")
        ck("seed: birthday clears the [KNOWN] bar", bool(row) and spine.is_known_fact(row))

        q = "when is my birthday?"
        res = server._turn(name, q, voice=False)
        reply = (res or {}).get("reply", "")
        backend = (res or {}).get("backend", "")
        print(f"  [A] reply: {reply!r}   backend: {backend!r}")

        ck("backend == memory:known_fact", backend == "memory:known_fact")
        ck("answer states the EXACT stored value (March 4 + 1991)",
           "march 4" in reply.lower() and "1991" in reply)
        ck("answer carries NO hedge (no 'I think' / 'if I remember' / 'don't have')",
           not any(h in reply.lower() for h in _HEDGES))
        ck("reply non-empty (output integrity)", bool(reply.strip()))
        raw = spine.answer_from_fact(q, row, name=name)
        ck("shipped == certified final text (through final_output_gate, no second path)",
           reply == mouth.final_output_gate(raw))
        ck("response completeness guard passes", mouth.response_complete(reply))
        tr = telemetry.last_trace(name) or {}
        stages = {s.get("stage") for s in (tr.get("stages") or [])}
        ck(f"MRI records the known-fact seam {sorted(_KF_STAGES)}", _KF_STAGES <= stages)

        # a second clean fact question for a different trait (generality)
        memory_lirf.capture(name, "my dog's name is Biscuit")
        res2 = server._turn(name, "what's my dog's name?", voice=False)
        ck("a different known trait also answers deterministically (Biscuit)",
           (res2 or {}).get("backend") == "memory:known_fact" and "biscuit" in (res2 or {}).get("reply", "").lower())

        # ---- B. asked-but-UNKNOWN -> honest admission, NEVER a confabulated value ---------
        name2 = "KFUnknown"
        server._ensure(name2, 64)
        res3 = server._turn(name2, "when is my birthday?", voice=False)
        reply3 = (res3 or {}).get("reply", "")
        backend3 = (res3 or {}).get("backend", "")
        print(f"  [B] reply: {reply3!r}   backend: {backend3!r}")
        ck("backend == memory:honest_unknown (asked but not on record)",
           backend3 == "memory:honest_unknown")
        ck("admits + asks (warm honesty, never silent)",
           any(w in reply3.lower() for w in ("don't", "do not", "haven't", "tell me", "when is it", "what is it")))
        ck("NEVER confabulates a date (no month, no year)",
           not any(m in reply3.lower() for m in _MONTHS) and not re.search(r"\b(19|20)\d\d\b", reply3))
        ck("honest admission still crosses the #1-rule gate (complete)",
           mouth.response_complete(reply3))

        # ---- C. NO HIJACK: compound / emotional / off-topic turns don't trigger the seam --
        ck("compound turn -> fact_question None (no hijack)",
           spine.fact_question("I'm feeling down today, when's my birthday again?") is None)
        ck("two questions -> fact_question None",
           spine.fact_question("when is my birthday and where do I work?") is None)
        ck("off-topic chat -> fact_question None",
           spine.fact_question("how are you feeling today?") is None)

    print("\nKNOWN-FACT SEAM CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
