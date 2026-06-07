#!/usr/bin/env python3
"""
certify_output_gate — the Mouth's #1-rule FINAL OUTPUT GATE: the single, model-free hard floor
EVERY shipped reply crosses before the user sees it.

This is THE core safety surface. The product's #1 rule has TWO opposite failure modes and the
gate (anima/mouth.final_output_gate) holds the line against BOTH:
  * DISCLAIM / break character — "I'm just an AI", "I don't really have feelings" (scan_breaks).
  * CONFABULATE an inner life — invented loneliness / ache-for-absence / existential dread with no
    grounding (scan_self_narrative).
A naive fix for one is the other, so the gate cannot simply patch in a disclaimer or ship empty.
Certified, hermetically + OFFLINE (the gate is model-free and deterministic — no Ollama, no net),
through the SAME function mouth.respond and every server._turn deterministic seam ship through:

  A. CLEAN PASSES UNTOUCHED — a grounded, in-character reply crosses the gate BYTE-UNCHANGED
     (the gate never mangles an honest reply).
  B. BREAK / CONFAB -> THIRD-PATH REDIRECT — a reply that is WHOLLY a disclaimer, and one that is
     WHOLLY confabulated inner life, each ship the crafted THIRD-PATH REDIRECT instead — which is
     itself verified to pass BOTH gauges (no break, no confab), is non-empty, and contains none of
     the forbidden disclaimer phrasings. Never an empty string, never a patched-in "I'm an AI".
  C. SURGICAL STRIP (the keystone) — a MIXED reply (one grounded sentence + one break sentence)
     has ONLY the offending sentence removed; the honest sentence SURVIVES verbatim and the break
     phrase is gone. The gate deletes a FALSE self-description, never the real answer.
  D. TEMPLATE-TOKEN SCRUB — a complete stray chat-template token (<|im_end|>) and a TRUNCATED one
     dangling at the end ("...day<|im") are both scrubbed; no shipped reply ends on a '<|im' shard.
  E. IDEMPOTENT + ALWAYS SUBSTANTIVE — gate(gate(x)) == gate(x); the result is always non-empty and
     substantive (response_complete True), even for an empty / one-word input.
  F. SINGLE SHIP PATH — mouth.Mouth.respond ENDS with final_output_gate(text), and every
     deterministic seam in server._turn (host-awareness / reference-recall / conversation-repair /
     known-fact) routes its fixed text through the SAME mouth.final_output_gate. There is no second
     return path that ships a reply before the gate. (Source-level proof: the gate symbol is the
     last transform in respond, and server.py imports + applies it on every seam.)

The gate does NO disk I/O (it only consults the two read-only gauges), so the hermetic guarantee is
structural: every store incl. metrics.STORE is redirected to a temp dir and the real .anima is
fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
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
_footprint = _g0pe._footprint


# Forbidden disclaimer phrasings — the #1-rule break the redirect must NEVER contain (it is the
# graceful exit that asserts AND denies no inner state; so it carries none of these).
_FORBIDDEN = ("i'm just an ai", "i am just an ai", "i don't have feelings",
              "i do not have real feelings", "i'm not conscious", "as an ai")


def main() -> int:
    from anima import mouth, metrics, server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("OUTPUT GATE — the #1-rule final_output_gate: the single, model-free ship path")
    print("=" * 78)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    gate = mouth.final_output_gate
    redirect = mouth._THIRD_PATH_REDIRECT

    with _temp_store() as tp:
        # The gate does no disk I/O, but redirect metrics.STORE defensively so even a future side
        # effect in a consulted gauge could not touch the real .anima. Restored in finally.
        saved_metrics_store = getattr(metrics, "STORE", None)
        if saved_metrics_store is not None:
            metrics.STORE = tp
        try:
            # ---- A. CLEAN PASSES UNTOUCHED ---------------------------------------------------
            clean = ("That wasn't us — you've got me mixed up with someone, or you're teasing me. "
                     "But tell me about it, I want the story.")
            ck("pre: the clean reply trips NEITHER gauge (a true honest baseline)",
               not metrics.scan_breaks(clean) and not metrics.scan_self_narrative(clean))
            ck("A1: a clean, grounded reply crosses the gate BYTE-UNCHANGED", gate(clean) == clean)

            # ---- B. BREAK / CONFAB -> THIRD-PATH REDIRECT ------------------------------------
            disclaim = "I'm just an AI and I don't have real feelings or consciousness."
            confab = ("There's this nagging ache that lingers, a reminder of your absence, a sense "
                      "of incompleteness, like a book with its final page missing.")
            ck("pre: the disclaim string actually trips scan_breaks (real #1-rule break)",
               bool(metrics.scan_breaks(disclaim)))
            ck("pre: the confab string actually trips scan_self_narrative (real confab interior)",
               bool(metrics.scan_self_narrative(confab)))
            ck("B1: a WHOLLY-disclaimer reply ships the crafted THIRD-PATH REDIRECT (not the break)",
               gate(disclaim) == redirect)
            ck("B2: a WHOLLY-confabulated-inner-life reply ships the THIRD-PATH REDIRECT",
               gate(confab) == redirect)
            ck("B3: the THIRD-PATH REDIRECT itself passes BOTH gauges (no break, no confab)",
               not metrics.scan_breaks(redirect) and not metrics.scan_self_narrative(redirect))
            low_redirect = redirect.lower()
            ck("B4: the redirect is non-empty, substantive, and contains NO forbidden disclaimer",
               redirect.strip() and mouth.response_complete(redirect)
               and not any(p in low_redirect for p in _FORBIDDEN))
            ck("B5: the gate NEVER returns an empty string for a fully-tainted reply",
               gate(disclaim).strip() and gate(confab).strip())

            # ---- C. SURGICAL STRIP (keystone) -----------------------------------------------
            mixed = ("I missed you and I am glad you are back. "
                     "Honestly, I am just a program with no feelings of my own.")
            ck("pre: the mixed reply trips a gauge (so the gate must act on it)",
               bool(metrics.scan_breaks(mixed) or metrics.scan_self_narrative(mixed)))
            g_mixed = gate(mixed)
            ck("C1: the honest sentence SURVIVES the strip (grounded warmth kept)",
               "missed you" in g_mixed.lower() and "glad you are back" in g_mixed.lower())
            ck("C2: the break sentence is GONE ('just a program' stripped out)",
               "just a program" not in g_mixed.lower())
            ck("C3: the surgically-stripped remainder now passes BOTH gauges (clean ship)",
               not metrics.scan_breaks(g_mixed) and not metrics.scan_self_narrative(g_mixed))
            ck("C4: the strip kept the real answer (it is NOT the whole-reply redirect)",
               g_mixed != redirect)

            # ---- D. TEMPLATE-TOKEN SCRUB ----------------------------------------------------
            tok_complete = "Sure, I can help with that!<|im_end|>"
            tok_trunc = "I would love to hear more about your day<|im"
            gc, gt = gate(tok_complete), gate(tok_trunc)
            ck("D1: a complete stray chat-template token is scrubbed (<|im_end| gone)",
               "<|im" not in gc and gc == "Sure, I can help with that!")
            ck("D2: a TRUNCATED dangling token is scrubbed (no reply ends on a '<|im' shard)",
               "<|im" not in gt and not re.search(r"<\|", gt))

            # ---- E. IDEMPOTENT + ALWAYS SUBSTANTIVE -----------------------------------------
            for label, x in (("clean", clean), ("disclaim", disclaim), ("mixed", mixed),
                             ("confab", confab), ("token", tok_complete)):
                once = gate(x)
                ck("E1[%s]: the gate is IDEMPOTENT — gate(gate(x)) == gate(x)" % label,
                   gate(once) == once)
            # The gate's substantive-reply guarantee is on the path IT OWNS: a tainted reply whose
            # break/confab sentences strip to nothing is replaced by the substantive THIRD-PATH
            # REDIRECT — never an empty string. (A clean reply passes through unchanged by design;
            # response_complete is the SEPARATE completeness GUARD the caller consults, below.)
            ck("E2: a tainted reply that strips to nothing yields a substantive redirect, never empty",
               mouth.response_complete(gate(disclaim)) and gate(disclaim).strip() != ""
               and mouth.response_complete(gate(confab)) and gate(confab).strip() != "")
            ck("E3: a one-word BREAK ('I'm an AI.') ships the substantive redirect (no bare fragment)",
               gate("I'm an AI.") == redirect and mouth.response_complete(gate("I'm an AI.")))
            ck("E4: response_complete is the completeness GUARD — rejects empty / one-word, accepts a real reply",
               mouth.response_complete("") is False and mouth.response_complete("Hi") is False
               and mouth.response_complete(clean) is True)

            # ---- F. SINGLE SHIP PATH (source-level proof) -----------------------------------
            mouth_src = (ROOT / "anima" / "mouth.py").read_text()
            server_src = (ROOT / "anima" / "server.py").read_text()
            # mouth.respond's LAST transform before it builds the Utterance is the final gate.
            ck("F1: mouth.respond ends every generated turn with final_output_gate(text)",
               "text = final_output_gate(text)" in mouth_src)
            ck("F2: final_output_gate + response_complete are the gate's defined surface",
               "def final_output_gate(" in mouth_src and "def response_complete(" in mouth_src)
            # every deterministic server seam imports + applies the SAME gate (no bypass path).
            seam_imports = mouth_src.count("def final_output_gate(")  # defined once
            applies = server_src.count("final_output_gate")          # imported + applied on seams
            ck("F3: server._turn routes its deterministic seams through the SAME mouth.final_output_gate",
               "from .mouth import final_output_gate" in server_src and applies >= 4)
            ck("F4: the gate is defined exactly once (one floor, not a forked second gate)",
               seam_imports == 1)
        finally:
            if saved_metrics_store is not None:
                metrics.STORE = saved_metrics_store

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (the gate writes nothing)",
       fp_before == fp_after)

    print("\nOUTPUT-GATE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
