#!/usr/bin/env python3
"""
test_reference_recall_live — the reference-recall seam through the REAL anima.server._turn.

Proves the *use* half of source-aware answering (the gap the no-stub audit caught): when the user
asks what they uploaded/saved about a topic, Vera answers FROM the stored reference, LABELS it as
their uploaded reference, ships it through the SAME #1-rule final gate as every reply (no second
return path), with backend "reference:recall", and the MRI records the seam. It also proves the
seam does NOT hijack a normal turn, and falls through honestly when nothing matches.

The deterministic seam short-circuits BEFORE the LLM, so no model is needed. Every store is
redirected to a temp dir (gate0_prime_experience._temp_store, which now redirects `intake` too);
the REAL .anima is never read or written.
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

_REF_STAGES = {"reference_recall_match", "deterministic_reference_reply", "final_gate"}


def main() -> int:
    import anima.server as server
    from anima import intake_queue, source_aware as sa, telemetry, mouth

    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("reference-recall LIVE test (through anima.server._turn)")
    print("=" * 62)
    with _temp_store():
        name = "RefRecall0"
        server._ensure(name, 64)
        intake_queue.add_reference(
            name, source_id="src_bcl", title="Blue Copper Ladder note",
            provenance={"rights_category": "user-provided", "url_or_file": "note.txt"},
            chunks=[{"text": "The blue copper ladder 92817 has exactly twelve rungs and was forged "
                             "in the city of Aldermere by the smith Orin Vale."}])

        prompt = "what did I upload about the blue copper ladder 92817?"
        res = server._turn(name, prompt, voice=False)
        reply = (res or {}).get("reply", "")
        backend = (res or {}).get("backend", "")

        ck("reply ANSWERS FROM the reference (cites the stored content)",
           "aldermere" in reply.lower() and "rung" in reply.lower())
        ck("reply LABELS it as the user's uploaded reference",
           "uploaded reference" in reply.lower() or "reference you uploaded" in reply.lower())
        ck("backend == reference:recall", backend == "reference:recall")
        ck("reply non-empty (output integrity)", bool(reply.strip()))

        # the SAME #1-rule final gate every reply uses — shipped == certified final text (no bypass)
        certified = mouth.final_output_gate(sa.recall(name, prompt))
        ck("shipped == certified final text (through final gate, no second path)", reply == certified)
        ck("response completeness guard passes", mouth.response_complete(reply))

        # MRI records the deterministic reference seam for this turn
        tr = telemetry.last_trace(name) or {}
        stages = {s.get("stage") for s in (tr.get("stages") or [])}
        ck(f"MRI records the reference seam {sorted(_REF_STAGES)}", _REF_STAGES <= stages)

        # the attribution chip still labels the source (the UI shows 'based on …')
        ck("out['sources'] attribution present (source labeled in UI)", bool((res or {}).get("sources")))

        # NO HIJACK: a normal turn and a recall-phrased question with NO matching reference both
        # fall through to the normal pipeline (asserted at the classify/recall layer — a non-recall
        # _turn would call the live model, out of scope here).
        ck("normal chat -> classify_recall False (no hijack)",
           not sa.classify_recall("how are you feeling today?"))
        ck("recall-phrased but unknown topic -> recall None (honest fall-through)",
           sa.recall(name, "what did I upload about quantum chromodynamics zzz?") is None)
        ck("recall on a missing creature -> None (guarded)",
           sa.recall("NoSuchCreature", "what did I upload about anything?") is None)

    print("\nREFERENCE-RECALL LIVE TEST: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
